"""FinQA-style numerical QA: prepare -> run -> evaluate -> report.

Example: uv run python -m bench.finqa --help
No judge API is needed. Candidate model definitions come from config.toml.
"""

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import urllib.request

from bench import run as runner

ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "scenarios/finqa"
DATASET = ROOT / "data/finqa-dev.jsonl"
RESULTS = ROOT / "results/finqa"
REPORTS = ROOT / "docs/finqa-results"
MAX_STEPS = 64
STEP = re.compile(r"([a-z_]+)\(([^()]*)\)")
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
ERROR_LABELS = {
    "unsupported_reference": "숫자 대신 표·본문 참조 사용",
    "wrong_arity": "연산 인자 개수 오류",
    "invalid_json": "JSON 형식 오류",
    "invalid_payload": "JSON 객체 형식 오류",
    "invalid_program": "기타 계산식 오류",
}


class ProgramError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def read_rows(path: Path) -> list[dict]:
    return runner.load_dataset([path]) if path.exists() else []


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows))


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def run_directory(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", run_id):
        raise ValueError("run-id must be a simple name (letters, digits, _, -, .)")
    return RESULTS / run_id


@contextmanager
def locked(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another FinQA process is using this run") from None
        yield


def prepare(source: list[dict], revision: str, split: str, limit: int, seed: int) -> list[dict]:
    if not source or len({row["id"] for row in source}) != len(source):
        raise ValueError("source must contain unique, nonempty question IDs")
    if limit < 1 or limit > len(source):
        raise ValueError(f"sample size must be between 1 and {len(source)}")
    ordered = sorted(source, key=lambda row: row["id"])
    random.Random(seed).shuffle(ordered)
    records = []
    for row in ordered[:limit]:
        qa = row["qa"]
        gold = qa["exe_ans"]
        if not (type(gold) in (float, int) and math.isfinite(gold) or gold in ("yes", "no")):
            raise ValueError(f"invalid executable answer: {row['id']}")
        if not row["table"] or not qa["question"]:
            raise ValueError(f"missing document/question: {row['id']}")
        record = {
            "id": f"finqa-{split}-{row['id']}", "source_id": row["id"],
            "source_revision": revision, "split": split, "doc_type": "finqa",
            # Shared transport metadata only; this is not a translation pair.
            "src_lang": "en", "tgt_lang": "en",
            "question": qa["question"], "table": row["table"],
            "pre_text": row["pre_text"], "post_text": row["post_text"],
            "gold_answer": gold, "reference_answer": qa["answer"],
            "reference_program": qa["program"], "gold_evidence": sorted(qa["gold_inds"]),
        }
        if not set(record["gold_evidence"]) <= evidence_ids(record):
            raise ValueError(f"invalid gold evidence IDs: {row['id']}")
        records.append(record)
    return records


def evidence_ids(record: dict) -> set[str]:
    return {f"text_{i}" for i in range(len(record["pre_text"]) + len(record["post_text"]))} | {
        f"table_{i}" for i in range(len(record["table"]))
    }


def build_prompt(record: dict, *, prompt_text: str | None = None) -> str:
    """Allowlist visible fields: never serialize the record's answer annotations."""
    document = {
        "question": record["question"],
        "pre_text": {f"text_{i}": text for i, text in enumerate(record["pre_text"])},
        "table": {f"table_{i}": row for i, row in enumerate(record["table"])},
        "post_text": {f"text_{i + len(record['pre_text'])}": text
                      for i, text in enumerate(record["post_text"])},
    }
    template = SCENARIO.joinpath("prompt.txt").read_text() if prompt_text is None else prompt_text
    return template + "\nDOCUMENT:\n" + json.dumps(document, ensure_ascii=False)


def number(text: str) -> float:
    text = text.strip().replace(",", "")
    if text.startswith("const_"):
        text = text[6:]
        if text == "m1":
            text = "-1"
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    if not NUMBER.fullmatch(text):
        raise ValueError("invalid numeric argument")
    value = float(text) / (100 if percent else 1)
    if not math.isfinite(value):
        raise ValueError("nonfinite number")
    return value


def execute(program: str, table: list[list[str]]):
    """Bounded FinQA DSL interpreter; never eval/exec candidate text."""
    if not isinstance(program, str) or not program.strip() or len(program) > 16000:
        raise ValueError("missing or oversized program")
    remaining = program.strip()
    results = []
    while remaining:
        if len(results) >= MAX_STEPS:
            raise ValueError("too many steps")
        match = STEP.match(remaining)
        if not match:
            raise ValueError("invalid program syntax")
        op, arguments = match.groups()
        # Row labels may contain commas. The last comma separates argument2.
        args = arguments.rsplit(",", 1)
        if len(args) != 2:
            raise ProgramError("wrong_arity", "each operation requires two arguments")
        left, right = (arg.strip() for arg in args)

        def resolve(arg):
            if re.match(r"(?:table|text)_\d+", arg):
                raise ProgramError("unsupported_reference", f"numeric operand required, received {arg!r}")
            if re.fullmatch(r"#\d+", arg):
                index = int(arg[1:])
                if index >= len(results):
                    raise ValueError("forward reference")
                value = results[index]
                if not isinstance(value, (float, int)):
                    raise ValueError("non-numeric intermediate")
                return value
            return number(arg)

        if op in {"table_sum", "table_average", "table_min", "table_max"}:
            if "," in left and re.match(r"table_\d+", left):
                raise ProgramError("wrong_arity", "table operation requires one row label and none")
            if right != "none":
                raise ValueError("table operation requires none")
            by_label = {row[0]: row[1:] for row in table}
            if left not in by_label or not by_label[left]:
                raise ValueError("unknown or empty table row")
            # Same numeric cleanup as upstream process_row.
            values = [number(cell.replace("$", "").split("(")[0].strip()) for cell in by_label[left]]
            result = {
                "table_sum": lambda: sum(values),
                "table_average": lambda: sum(values) / len(values),
                "table_min": lambda: min(values), "table_max": lambda: max(values),
            }[op]()
        elif op in {"add", "subtract", "multiply", "divide", "exp", "greater"}:
            if "," in left or "," in right:
                raise ProgramError("wrong_arity", "arithmetic requires exactly two operands without thousands separators")
            a, b = resolve(left), resolve(right)
            if op == "add":
                result = a + b
            elif op == "subtract":
                result = a - b
            elif op == "multiply":
                result = a * b
            elif op == "divide":
                if b == 0:
                    raise ValueError("division by zero")
                result = a / b
            elif op == "exp":
                try:
                    result = math.pow(a, b)
                except (ValueError, OverflowError):
                    raise ValueError("invalid exponentiation") from None
            else:
                result = "yes" if a > b else "no"
        else:
            raise ValueError("unsupported operation")
        if isinstance(result, (float, int)) and not math.isfinite(result):
            raise ValueError("nonfinite result")
        results.append(result)
        remaining = remaining[match.end():].strip()
        if remaining:
            if not remaining.startswith(",") or not remaining[1:].strip():
                raise ValueError("invalid step separator")
            remaining = remaining[1:].strip()
    final = results[-1]
    return round(final, 5) if isinstance(final, (float, int)) else final


def score(record: dict, prediction: dict | None) -> dict:
    result = {"id": record["id"], "correct": False, "evidence_exact": False,
              "execution_result": None, "prediction_sha256": digest(prediction)}
    if prediction is None:
        return {**result, "status": "missing"}
    if (prediction.get("error") is not None or not prediction.get("output_text", "").strip()
            or prediction.get("response_status", "completed") != "completed"):
        return {**result, "status": "request_failed"}
    try:
        payload = json.loads(prediction["output_text"])
        if not isinstance(payload, dict):
            raise ProgramError("invalid_payload", "expected a JSON object")
        value = execute(payload.get("program"), record["table"])
    except (ValueError, TypeError, OverflowError) as error:
        code = "invalid_json" if isinstance(error, json.JSONDecodeError) else getattr(error, "code", "invalid_program")
        return {**result, "status": "invalid_program", "evaluation_error": str(error),
                "evaluation_error_code": code}
    evidence = payload.get("evidence")
    valid_evidence = (isinstance(evidence, list) and all(isinstance(item, str) for item in evidence)
                      and set(evidence) <= evidence_ids(record))
    return {
        **result, "status": "scored", "execution_result": value,
        "correct": value == record["gold_answer"],
        "evidence_exact": valid_evidence and set(evidence) == set(record["gold_evidence"]),
        "evidence_valid": valid_evidence,
    }


def summarize(evaluations: list[dict]) -> dict:
    total = len(evaluations)
    counts = {status: sum(row["status"] == status for row in evaluations)
              for status in ("scored", "invalid_program", "request_failed", "missing")}
    correct = sum(row["correct"] for row in evaluations)
    return {
        "questions": total, "correct": correct,
        "incorrect_result": counts["scored"] - correct,
        "invalid_program_causes": {
            code: sum(row.get("evaluation_error_code") == code for row in evaluations)
            for code in ERROR_LABELS
        },
        "execution_accuracy": correct / total if total else None,
        "response_coverage": (counts["scored"] + counts["invalid_program"]) / total if total else None,
        "evidence_exact_match": sum(row["evidence_exact"] for row in evaluations) / total if total else None,
        **counts,
    }


def cmd_prepare(args):
    cfg = runner.load_config()["scenario"]["finqa"]
    revision, split = cfg["source_revision"], cfg["split"]
    url = f"https://raw.githubusercontent.com/czyssrs/FinQA/{revision}/dataset/{split}.json"
    raw = args.source.read_bytes() if args.source else urllib.request.urlopen(url, timeout=60).read()
    records = prepare(json.loads(raw), revision, split, args.limit or cfg["sample_size"], cfg["seed"])
    # Existing runs retain their own immutable dataset snapshot.
    write_rows(args.output, records)
    write_json(args.output.with_suffix(".meta.json"), {
        "source_url": url if not args.source else None,
        "local_source": str(args.source) if args.source else None,
        "configured_revision": revision, "split": split, "seed": cfg["seed"],
        "source_sha256": hashlib.sha256(raw).hexdigest(), "dataset_sha256": digest(records),
        "questions": len(records),
    })
    print(f"prepared {len(records)} questions -> {args.output}")


async def run_candidates(args, directory: Path):
    cfg = runner.load_config()
    scenario = cfg["scenario"]["finqa"]
    prompt_text = SCENARIO.joinpath("prompt.txt").read_text()
    wanted = set(args.models.split(","))
    models = [model for model in cfg["models"] if model["name"] in wanted]
    if wanted != {model["name"] for model in models}:
        raise ValueError("unknown model name")
    if any(not model.get("enabled", True) or model["api"] == "translate" for model in models):
        raise ValueError("FinQA requires enabled generative models; Amazon Translate is unsupported")
    records = read_rows(args.dataset)
    if args.limit:
        records = records[:args.limit]
    if not records or len({row["id"] for row in records}) != len(records):
        raise ValueError("dataset must contain unique questions; run prepare first")
    for record in records:
        build_prompt(record, prompt_text=prompt_text)  # validate before any paid call
        if "gold_answer" not in record or record.get("doc_type") != "finqa":
            raise ValueError("not a prepared FinQA dataset")
    # Immutable run contract prevents stale answers after prompt/data/model changes.
    contract = {
        "scenario": "finqa", "dataset_sha256": digest(records),
        "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        "models": models, "aws_region": cfg["aws"]["region"],
        "concurrency_default": scenario["concurrency_default"],
        "max_output_tokens": runner.MAX_OUTPUT_TOKENS, "temperature": 0,
        "temperature_omitted_model_ids": sorted(runner.MANTLE_NO_TEMPERATURE | runner.BEDROCK_NO_TEMPERATURE),
        "request_timeout_s": runner.REQUEST_TIMEOUT_S,
        "runner_sha256": hashlib.sha256(Path(runner.__file__).read_bytes()).hexdigest(),
        "finqa_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    path = directory / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text())
        if manifest["contract"] != contract:
            raise ValueError("run contract changed; use a new run-id")
        if digest(read_rows(directory / "dataset.jsonl")) != contract["dataset_sha256"]:
            raise ValueError("run dataset snapshot changed")
    else:
        if (directory / "answers.jsonl").exists():
            raise ValueError("answers exist without a manifest; use a new run-id")
        manifest = {"run_id": args.run_id, "contract": contract, "executions": []}
        write_rows(directory / "dataset.jsonl", records)
        (directory / "prompt.txt").write_text(prompt_text)
        write_json(path, manifest)  # saved before any request, even on interruption
    cache = runner.ResultCache(directory / "answers.jsonl")
    execution = {"started_at": datetime.now(timezone.utc).isoformat(), "models": []}
    manifest["executions"].append(execution)
    write_json(path, manifest)
    for model in models:
        summary = await runner.run_model(model, records, cache, cfg["aws"]["region"],
                                         scenario["concurrency_default"],
                                         prompt_builder=lambda row: build_prompt(row, prompt_text=prompt_text))
        execution["models"].append(summary)
        write_json(path, manifest)
    execution["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, manifest)
    return int(any(summary["failed"] for summary in execution["models"]))


def load_run(directory: Path):
    manifest = json.loads((directory / "manifest.json").read_text())
    records = read_rows(directory / "dataset.jsonl")
    if digest(records) != manifest["contract"]["dataset_sha256"]:
        raise ValueError("run dataset snapshot changed")
    predictions = runner.dedupe_latest(read_rows(directory / "answers.jsonl"),
                                       lambda row: (row["model"], row["id"]))
    return manifest, records, {(row["model"], row["id"]): row for row in predictions}


def evaluator_digest() -> str:
    return digest({"code": Path(__file__).read_text(), "rubric": SCENARIO.joinpath("rubric.txt").read_text()})


def cmd_evaluate(directory: Path):
    manifest, records, predictions = load_run(directory)
    rows = []
    for model in manifest["contract"]["models"]:
        for record in records:
            rows.append({
                "model": model["name"], **score(record, predictions.get((model["name"], record["id"]))),
                "evaluator_sha256": evaluator_digest(),
            })
    # Append-only evaluation history; consumers retain the last row per key.
    with (directory / "evaluations.jsonl").open("a") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    print(f"evaluated {len(rows)} model/question pairs without judge API calls")


def cmd_report(directory: Path):
    manifest, records, predictions = load_run(directory)
    prompt_path = directory / "prompt.txt"
    warnings = ["형식 준수·문서 읽기·계산·원본 정답 단위가 섞인 파일럿입니다. 금융 추론 성능 순위로 사용하지 마세요."]
    if prompt_path.exists():
        snapshot = prompt_path.read_bytes()
        if hashlib.sha256(snapshot).hexdigest() != manifest["contract"]["prompt_sha256"]:
            raise ValueError("run prompt snapshot changed")
        if b"For a percentage/rate answer, return a fraction" in snapshot:
            warnings.append("이 실행의 백분율 강제 변환 지시는 일부 공식 정답 단위와 충돌합니다. "
                            "지시를 수정했어도 이 보고서의 응답은 수정 전 결과입니다.")
    else:
        warnings.append("실행 당시 프롬프트 원문이 없어 단위 지시를 확인할 수 없습니다.")
    evaluations = runner.dedupe_latest(read_rows(directory / "evaluations.jsonl"),
                                       lambda row: (row["model"], row["id"]))
    by_key = {(row["model"], row["id"]): row for row in evaluations}
    models = []
    all_rows = []
    for model in manifest["contract"]["models"]:
        rows = []
        for record in records:
            key = (model["name"], record["id"])
            row = by_key.get(key)
            if (row is None or row["prediction_sha256"] != digest(predictions.get(key))
                    or row["evaluator_sha256"] != evaluator_digest()):
                raise ValueError("evaluation missing or stale; run evaluate again")
            rows.append(row)
        metrics = summarize(rows)
        latest = [predictions[(model["name"], record["id"])] for record in records
                  if (model["name"], record["id"]) in predictions]
        latencies = [row["latency_s"] for row in latest
                     if row.get("error") is None and row.get("latency_s") is not None]
        metrics["response_latency_median_s"] = statistics.median(latencies) if latencies else None
        models.append({"name": model["name"], "aggregate": metrics})
        all_rows.extend(rows)
    report = {
        "scenario": "finqa", "run_id": manifest["run_id"], "models": models,
        "dataset_sha256": manifest["contract"]["dataset_sha256"],
        "prompt_sha256": manifest["contract"]["prompt_sha256"],
        "assessment_scope": "protocol_pilot", "warnings": warnings,
        "policy": SCENARIO.joinpath("rubric.txt").read_text(), "evaluations": all_rows,
    }
    write_json(directory / "report.json", report)
    write_json(REPORTS / f"{manifest['run_id']}.json", report)
    table_rows = []
    for model in models:
        m = model["aggregate"]
        table_rows.append(f"<tr><td>{html.escape(model['name'])}</td><td>{m['correct']} / {m['questions']}</td>"
                          f"<td>{m['execution_accuracy']:.1%}</td><td>{m['response_coverage']:.1%}</td>"
                          f"<td>{m['invalid_program']}</td><td>{m['request_failed']}</td>"
                          f"<td>{m['missing']}</td><td>{m['evidence_exact_match']:.1%}</td></tr>")
    page = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FinQA 금융 수치 추론</title>
<style>body{font:16px system-ui;margin:2rem;line-height:1.6;color:#172337}
table{border-collapse:collapse}th,td{padding:.7rem;border:1px solid #ccd3dd;text-align:right}
th:first-child,td:first-child{text-align:left}pre{white-space:pre-wrap}.scroll{overflow:auto}</style>
<h1>FinQA 금융 수치 추론</h1>"""
    page += f"<p>실행: {html.escape(manifest['run_id'])}</p>"
    page += "".join(f"<p><strong>{html.escape(warning)}</strong></p>" for warning in warnings)
    page += "<p>실행 정답률 = 계산 결과가 정답인 문항 / 선택한 전체 문항. 높을수록 좋습니다. " \
            "실패·미응답도 분모에 포함합니다. 개발용 소표본 결과이며 공식 리더보드 점수가 아닙니다.</p>"
    page += "<div class=scroll><table><thead><tr><th>모델</th><th>정답 / 전체</th><th>실행 정답률</th>" \
            "<th>응답 커버리지</th><th>모델 계산식 실행불가</th><th>요청 실패</th><th>미응답</th>" \
            "<th>근거 ID 완전일치율</th></tr></thead><tbody>" + "".join(table_rows) + "</tbody></table></div>"
    page += "<p>근거 지표는 정답 근거 ID 집합과의 일치 여부이며, 다른 타당한 근거도 불일치로 처리될 수 있습니다. " \
            "기존 모델별 추론 설정을 유지하며 단위·부호 오류를 자동 보정하지 않습니다.</p>"
    for model in models:
        m = model["aggregate"]
        causes = " · ".join(f"{ERROR_LABELS[code]} {count}건"
                            for code, count in m["invalid_program_causes"].items() if count)
        page += f"<p>{html.escape(model['name'])}: {html.escape(causes or '실행불가 없음')}." \
                f" 실행은 됐지만 정답과 다른 결과 {m['incorrect_result']}건.</p>"
    page += "<details><summary>문항별 원본 응답·실행 결과·정답 확인</summary>"
    records_by_id = {record["id"]: record for record in records}
    for row in all_rows:
        record = records_by_id[row["id"]]
        prediction = predictions.get((row["model"], row["id"])) or {}
        details = {
            "question": record["question"], "status": row["status"],
            "error": row.get("evaluation_error"), "output": prediction.get("output_text"),
            "execution_result": row["execution_result"], "gold_answer": record["gold_answer"],
            "reference_answer": record["reference_answer"], "reference_program": record["reference_program"],
        }
        page += f"<h3>{html.escape(row['model'])} · {html.escape(row['id'])}</h3><pre>" \
                + html.escape(json.dumps(details, ensure_ascii=False, indent=2)) + "</pre>"
    page += "</details><details><summary>평가 규칙</summary><pre>" + html.escape(report["policy"]) + "</pre></details></html>"
    REPORTS.joinpath(f"{manifest['run_id']}.html").write_text(page)
    print(f"report -> {REPORTS / (manifest['run_id'] + '.html')}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="prepare a fixed upstream dev subset; no LLM calls")
    prepare_parser.add_argument("--source", type=Path, help="local upstream-format JSON (records its hash)")
    prepare_parser.add_argument("--output", type=Path, default=DATASET)
    prepare_parser.add_argument("--limit", type=positive)
    run_parser = commands.add_parser("run", help="run explicitly selected models (billable)")
    run_parser.add_argument("--models", required=True)
    run_parser.add_argument("--dataset", type=Path, default=DATASET)
    run_parser.add_argument("--limit", type=positive)
    for command in ("evaluate", "report"):
        commands.add_parser(command)
    for command in ("run", "evaluate", "report"):
        commands.choices[command].add_argument("--run-id", required=True)
    commands.add_parser("selfcheck", help="offline evaluator and pipeline checks")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            cmd_prepare(args)
        elif args.command == "selfcheck":
            selfcheck()
        else:
            directory = run_directory(args.run_id)
            with locked(directory):
                if args.command == "run":
                    return asyncio.run(run_candidates(args, directory))
                elif args.command == "evaluate":
                    cmd_evaluate(directory)
                else:
                    cmd_report(directory)
    except (ValueError, KeyError, OSError) as error:
        print(f"FinQA failed: {error}", file=sys.stderr)
        return 1
    return 0


def selfcheck():
    from argparse import Namespace
    import tempfile
    from unittest.mock import AsyncMock, patch

    table = [["item", "2024", "2023"], ["revenue", "$ 120", "100"],
             ["margin", "25%", "50%"], ["net", "-5 (5)", "10"]]
    assert execute("subtract(120, 100), divide(#0, const_100)", table) == 0.2
    assert execute("divide(1, 3), multiply(#0, 3)", table) == 1  # round only final result
    assert execute("add(-5, const_m1)", table) == -6
    assert execute("add(25%, const_0)", table) == 0.25
    assert execute("greater(2, 1)", table) == "yes"
    assert execute("greater(1, 2)", table) == "no"
    assert execute("exp(2, 3)", table) == 8
    assert execute("table_sum(revenue, none)", table) == 220
    assert execute("table_average(margin, none)", table) == 0.375
    assert execute("table_min(net, none)", table) == -5
    assert execute("table_max(revenue, none)", table) == 120
    for invalid in ("divide(1, 0)", "add(#0, 1)", "add(nan, 1)", "add(1e309, 1)",
                    "exp(-1, 0.5)", "exp(10, 1000)", "eval(1, 2)", "add(1, 2),",
                    "add(1,2) junk", "add(1,2,3)", "table_sum(missing, none)", None, "",
                    ", ".join(["add(1, 2)"] * (MAX_STEPS + 1))):
        try:
            execute(invalid, table)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid program: {invalid}")
    raw = [{"id": "fixture-1", "table": table, "pre_text": ["Revenue in millions."],
            "post_text": [], "qa": {"question": "Revenue increase?", "exe_ans": 20.0,
                                   "answer": "SECRET ANSWER", "program": "SECRET PROGRAM",
                                   "gold_inds": {"table_1": "SECRET EVIDENCE"}}}]
    records = prepare(raw, "fixture", "dev", 1, 13)
    record = records[0]
    assert prepare(raw, "fixture", "dev", 1, 13) == records
    assert "SECRET" not in build_prompt(record)
    prediction = {"output_text": '{"program":"subtract(120, 100)","evidence":["table_1"]}',
                  "error": None, "latency_s": 1}
    good = score(record, prediction)
    assert good["correct"] and good["evidence_exact"]
    assert not score(record, {**prediction, "output_text": '{"program":"subtract(100, 120)"}'})["correct"]
    assert not score(record, {**prediction, "output_text": '{"program":"divide(20, 100)"}'})["correct"]
    assert score(record, {**prediction, "output_text": "20"})["status"] == "invalid_program"
    for program, code in (
        ("divide(table_5, table_4)", "unsupported_reference"),
        ("divide(table_2[88.2], table_1[450.4])", "unsupported_reference"),
        ("add(#0, 8310, 44.99)", "wrong_arity"),
        ("table_min(table_1, table_2, table_3)", "wrong_arity"),
    ):
        checked = score(record, {**prediction, "output_text": json.dumps({"program": program})})
        assert checked["evaluation_error_code"] == code and not checked["correct"], checked
    assert score(record, {**prediction, "output_text": "not JSON"})["evaluation_error_code"] == "invalid_json"
    assert score(record, {**prediction, "error": "timeout"})["status"] == "request_failed"
    assert score(record, None)["status"] == "missing"
    totals = summarize([good, score(record, None), score(record, {**prediction, "output_text": "20"})])
    assert totals["execution_accuracy"] == 1 / 3 and totals["response_coverage"] == 2 / 3
    assert totals["invalid_program_causes"]["invalid_payload"] == 1
    assert summarize([])["execution_accuracy"] is None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dataset = root / "input.jsonl"
        write_rows(dataset, records)
        cfg = {"aws": {"region": "us-west-2"}, "scenario": {"finqa": {"concurrency_default": 1}},
               "models": [{"name": "offline", "api": "bedrock", "model_id": "offline"}]}
        args = Namespace(models="offline", dataset=dataset, limit=None, run_id="selfcheck")
        directory = root / "run"
        directory.mkdir()
        response = {"text": prediction["output_text"], "tokens_in": 10, "tokens_out": 5}
        with (patch.object(runner, "load_config", return_value=cfg),
              patch.object(runner, "make_client", return_value=object()),
              patch.object(runner, "call_bedrock", new=AsyncMock(return_value=response)) as call,
              patch(__name__ + ".REPORTS", root / "reports")):
            assert asyncio.run(run_candidates(args, directory)) == 0
            assert "SECRET" not in call.call_args.args[2]
            assert asyncio.run(run_candidates(args, directory)) == 0
            assert call.call_count == 1
            cmd_evaluate(directory)
            cmd_report(directory)
            report = json.loads((directory / "report.json").read_text())
            assert report["models"][0]["aggregate"]["execution_accuracy"] == 1
            assert report["assessment_scope"] == "protocol_pilot"
            assert report["prompt_sha256"] == json.loads((directory / "manifest.json").read_text())["contract"]["prompt_sha256"]
            # Last failed retry replaces a former success and makes old evaluation stale.
            rows = read_rows(directory / "answers.jsonl")
            write_rows(directory / "answers.jsonl", [*rows, {**rows[0], "error": "timeout"}])
            try:
                cmd_report(directory)
            except ValueError:
                pass
            else:
                raise AssertionError("stale evaluation accepted")
            cmd_evaluate(directory)
            cmd_report(directory)
            report = json.loads((directory / "report.json").read_text())
            assert report["models"][0]["aggregate"]["execution_accuracy"] == 0
            assert report["models"][0]["aggregate"]["request_failed"] == 1
            altered = [{**record, "question": "changed content under same ID"}]
            write_rows(dataset, altered)
            try:
                asyncio.run(run_candidates(args, directory))
            except ValueError:
                pass
            else:
                raise AssertionError("changed dataset reused cached answers")
    print("FinQA selfcheck OK")


if __name__ == "__main__":
    sys.exit(main())
