"""Pinned official-rule TAT-QA subset benchmark; no LLM judge."""

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
import random
import re
from pathlib import Path
from decimal import Decimal
import tempfile

from bench import finqa_compare
from bench import run as runner
from bench.vendor.tatqa.tatqa_metric import TaTQAEmAndF1

SCALES = {"", "thousand", "million", "billion", "percent"}
ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "scenarios/tatqa"
QUOTAS = {"span": 86, "arithmetic": 84, "multi-span": 25, "count": 5}
REVISION = "870accc41953dcde885aabeb963d94aabdc0fbc3"
SOURCE_SHA256 = "c4d08418359c1d76468dec420ee748a37f48c06b63cb8ec2766f19d5d314b597"
SOURCE_URL = f"https://raw.githubusercontent.com/NExTplusplus/TAT-QA/{REVISION}/dataset_raw/tatqa_dataset_test_gold.json"
DATASET = SCENARIO / "dataset.jsonl"
RESULTS = ROOT / "results/tatqa"
REPORTS = ROOT / "docs/tatqa-results"
LIMITATIONS = [
    "200-question official-rule test subset; not the full official TAT-QA leaderboard.",
    "200 distinct table contexts do not imply 200 independent annual reports or companies.",
    "Published gold test answers may have appeared in model training data; contamination is unmeasured.",
    "Existing provider/model reasoning settings are preserved; omitted defaults and reasoning budgets may differ.",
    "Malformed, missing, failed and truncated responses score zero in the full scheduled denominator.",
    "Upstream numeric rounding, percent handling and joined multi-span normalization are preserved.",
    "Costs use frozen configured rates, include incorrect/invalid successful responses, and exclude failed calls, retries and infrastructure.",
    "Configured prices with an expired validity date are withheld; estimates are not experiment invoices.",
    "Self-hosted GPUs and translation-only services are excluded from this API cohort.",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(",", ":")).encode("utf-8", errors="surrogatepass")).hexdigest()


def read_rows(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        # Escapes preserve malformed Unicode in retained raw provider text
        # without allowing a lone surrogate to abort evidence publication.
        json.dump(value, stream, ensure_ascii=True, allow_nan=False, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows))


def append_event(path, row):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()


def now():
    return datetime.now(timezone.utc).isoformat()


def select_records(source, seed):
    rng = random.Random(seed)
    pools = {kind: [] for kind in QUOTAS}
    seen_ids, contexts = set(), set()
    for document in sorted(source, key=lambda d: d["table"]["uid"]):
        context_id = document["table"]["uid"]
        if context_id in contexts:
            raise ValueError("duplicate source table context")
        contexts.add(context_id)
        for question in sorted(document["questions"], key=lambda q: q["uid"]):
            if question["uid"] in seen_ids or question["answer_type"] not in QUOTAS:
                raise ValueError("duplicate question or unknown answer type")
            seen_ids.add(question["uid"])
            pools[question["answer_type"]].append((document, question))
    selected, used = [], set()
    # Rarest types first ensures the small count population can get contexts.
    # Selection examines only IDs and declared types, never candidate output.
    for kind in sorted(QUOTAS, key=QUOTAS.get):
        candidates = pools[kind][:]
        rng.shuffle(candidates)
        count = 0
        for document, question in candidates:
            context_id = document["table"]["uid"]
            if context_id in used:
                continue
            selected.append({
                "id": question["uid"], "context_id": context_id,
                "table": document["table"]["table"],
                "paragraphs": [p["text"] for p in sorted(document["paragraphs"], key=lambda p: p["order"])],
                "question": question["question"], "answer_type": kind,
                "gold": question, "src_lang": "en", "tgt_lang": "en", "doc_type": "tatqa",
            })
            used.add(context_id)
            count += 1
            if count == QUOTAS[kind]:
                break
        if count != QUOTAS[kind]:
            raise ValueError(f"cannot satisfy unique-context quota for {kind}")
    rng.shuffle(selected)
    validate_records(selected)
    return selected


def validate_records(records):
    if (len(records) != 200 or len({row["id"] for row in records}) != 200
            or len({row["context_id"] for row in records}) != 200
            or Counter(row["answer_type"] for row in records) != QUOTAS):
        raise ValueError("TAT-QA requires 200 unique questions/contexts and frozen type quotas")
    for row in records:
        if row.get("doc_type") != "tatqa" or row["gold"]["answer_type"] != row["answer_type"]:
            raise ValueError("not a prepared TAT-QA record")


def build_prompt(record, prompt_text):
    # Explicit allowlist keeps all gold annotations, including type, offline.
    payload = {"table": record["table"], "paragraphs": record["paragraphs"], "question": record["question"]}
    return prompt_text + "\n" + json.dumps(payload, ensure_ascii=False, allow_nan=False)


def prepare():
    source_path = SCENARIO / "source-test-gold.json"
    if sha(source_path) != SOURCE_SHA256:
        raise ValueError("pinned official source checksum mismatch")
    cfg = runner.load_config()["scenario"]["tatqa"]
    if (cfg["seed"], cfg["sample_size"], cfg["split"], cfg["source_revision"]) != (20261027, 200, "test", REVISION):
        raise ValueError("this protocol freezes seed, size, split and source revision")
    source = json.loads(source_path.read_text())
    records = select_records(source, cfg["seed"])
    metadata = {
        "questions": 200, "documents": 200, "contexts": 200,
        "context_definition": "distinct released table UID; not independent source reports",
        "answer_types": QUOTAS, "source_url": SOURCE_URL, "source_revision": REVISION,
        "source_sha256": SOURCE_SHA256, "dataset_sha256": digest(records),
        "seed": cfg["seed"], "split": cfg["split"], "license": "CC BY 4.0",
        "source_questions": sum(len(d["questions"]) for d in source), "source_contexts": len(source),
        "source_answer_types": dict(Counter(q["answer_type"] for d in source for q in d["questions"])),
        "selection": "seeded sorted-ID permutations; smallest type quota first; one question per table UID",
        "selected_ids": [row["id"] for row in records],
    }
    if DATASET.exists() and read_rows(DATASET) != records:
        raise ValueError("prepared dataset differs; investigate rather than overwriting")
    write_rows(DATASET, records)
    write_json(SCENARIO / "provenance.json", metadata)
    print(f"Prepared {len(records)} questions / {len({r['context_id'] for r in records})} table contexts: {digest(records)}")
    return records, metadata


def summarize(scores):
    total = len(scores)
    counts = Counter(row["status"] for row in scores)
    return {
        "total": total, "exact_match": sum(row["exact_match"] for row in scores) / total if total else 0,
        "f1": sum(row["f1"] for row in scores) / total if total else 0,
        "correct": sum(row["correct"] for row in scores),
        "response_coverage": (counts["scored"] + counts["invalid"]) / total if total else 0,
        "scored": counts["scored"], "invalid": counts["invalid"],
        "request_failures": counts["request_failed"], "missing": counts["missing"],
        "truncated": counts["truncated"],
    }


def cohort_of(cfg):
    models, excluded = [], []
    for model in cfg["models"]:
        if not model.get("enabled", True):
            reason = "disabled_in_config"
        elif model["api"] == "translate":
            reason = "translation_only_service"
        elif model.get("base_url"):
            reason = "self_hosted_requires_separate_execution_cohort"
        else:
            if model["api"] not in {"openai", "bedrock", "bedrock_mantle"}:
                raise ValueError(f"unsupported generative API: {model['api']}")
            models.append(model)
            continue
        excluded.append({"name": model["name"], "reason": reason})
    if not models or len({m["name"] for m in cfg["models"]}) != len(cfg["models"]):
        raise ValueError("empty/duplicate model roster")
    return models, excluded


def make_contract(cfg, records, metadata, prompt_text, parallel_models):
    models, excluded = cohort_of(cfg)
    scenario = cfg["scenario"]["tatqa"]
    if type(parallel_models) is not int or parallel_models < 1:
        raise ValueError("parallel_models must be a positive integer")
    if type(scenario["concurrency_default"]) is not int or scenario["concurrency_default"] < 1:
        raise ValueError("concurrency_default must be a positive integer")
    for model in models:
        for key in ("concurrency", "request_max_attempts"):
            if key in model and (type(model[key]) is not int or model[key] < 1):
                raise ValueError(f"{model['name']}: {key} must be a positive integer")
    paths = {"adapter": Path(__file__), "runner": Path(runner.__file__),
             "cost_aggregate": ROOT / "bench/report.py", "cost_adapter": Path(finqa_compare.__file__),
             "official_metric": ROOT / "bench/vendor/tatqa/tatqa_metric.py",
             "official_utils": ROOT / "bench/vendor/tatqa/tatqa_utils.py", "dependencies": ROOT / "uv.lock"}
    return {
        "scenario": "tatqa", "dataset": metadata, "dataset_sha256": digest(records),
        "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        "source_sha256": SOURCE_SHA256, "source_revision": REVISION,
        "models": models, "excluded_models": excluded, "config_sha256": sha(ROOT / "config.toml"),
        "scenario_config": scenario, "aws_region": cfg["aws"]["region"],
        "parallel_models": parallel_models, "concurrency_default": scenario["concurrency_default"],
        "max_output_tokens": runner.MAX_OUTPUT_TOKENS, "request_timeout_s": runner.REQUEST_TIMEOUT_S,
        "temperature": 0,
        "temperature_omitted_model_ids": sorted(runner.MANTLE_NO_TEMPERATURE | runner.BEDROCK_NO_TEMPERATURE),
        "bedrock_disable_thinking_model_ids": sorted(runner.BEDROCK_DISABLE_THINKING),
        "code_sha256": {name: sha(path) for name, path in paths.items()},
        "protocol": {"description": "TAT-QA official-rule 200-question test subset; strict JSON answer and scale; all scheduled questions remain in denominator.",
                     "official_evaluator_revision": REVISION, "limitations": LIMITATIONS,
                     "upstream_metric_sha256": "2aeeac479f89f8c76300af1cc0e8d098eb86af84bc386b38b6ab4af484a6dea8",
                     "upstream_utils_sha256": "a84bb2f960737cf0a53733637a674cc4b20ef030a2be6a4b21dc2c4356f415ec",
                     "json_numeric_serialization": "non-exponent decimal strings preserve numeric JSON values; string answers unchanged",
                     "normalizations": ["complete outer JSON markdown fence"]},
    }


@contextmanager
def execution_lock(directory, *, blocking=False):
    # Locks live outside published evidence; all processes hash the absolute
    # run/model directory. Kernel releases them on interruption or process exit.
    path = Path(tempfile.gettempdir()) / ("llm-benchmark-tatqa-" + hashlib.sha256(str(Path(directory).resolve()).encode()).hexdigest() + ".lock")
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as error:
            raise ValueError(f"execution already active: {directory}") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@asynccontextmanager
async def run_slot(directory, parallel_models):
    locked = None
    while locked is None:
        for slot in range(parallel_models):
            candidate = execution_lock(Path(directory) / "parallel-slots" / str(slot))
            try:
                candidate.__enter__()
            except ValueError:
                continue
            locked = candidate
            break
        if locked is None:
            await asyncio.sleep(.05)
    try:
        yield
    finally:
        locked.__exit__(None, None, None)


def freeze_run(directory, run_id, contract, records, prompt_text):
    directory = Path(directory)
    path = directory / "manifest.json"
    with execution_lock(directory, blocking=True):
        if path.exists():
            manifest = json.loads(path.read_text())
            if manifest["contract"] != contract:
                raise ValueError("immutable run contract changed; use a new run-id")
            load_run(directory)
            return manifest
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("run artifacts exist without manifest; use a new run-id")
        directory.mkdir(parents=True, exist_ok=True)
        write_rows(directory / "dataset.jsonl", records)
        (directory / "prompt.txt").write_text(prompt_text)
        manifest = {"run_id": run_id, "created_at": now(), "contract": contract,
                    "contract_sha256": digest(contract)}
        write_json(path, manifest)  # final pre-call durable freeze
        return manifest


def load_run(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    contract = manifest["contract"]
    if manifest.get("contract_sha256") != digest(contract):
        raise ValueError("run contract checksum mismatch")
    records = read_rows(directory / "dataset.jsonl")
    validate_records(records)
    if digest(records) != contract["dataset_sha256"]:
        raise ValueError("run dataset snapshot changed")
    if sha(directory / "prompt.txt") != contract["prompt_sha256"]:
        raise ValueError("run prompt snapshot changed")
    if sha(__file__) != contract["code_sha256"]["adapter"]:
        raise ValueError("frozen scoring adapter changed")
    for name, path in (("runner", Path(runner.__file__)), ("dependencies", ROOT / "uv.lock"),
                       ("official_metric", ROOT / "bench/vendor/tatqa/tatqa_metric.py"),
                       ("official_utils", ROOT / "bench/vendor/tatqa/tatqa_utils.py"),
                       ("cost_aggregate", ROOT / "bench/report.py"),
                       ("cost_adapter", Path(finqa_compare.__file__))):
        if sha(path) != contract["code_sha256"][name]:
            raise ValueError(f"frozen scoring/cost code changed: {name}")
    predictions, events = {}, {}
    ids = {r["id"] for r in records}
    for model in contract["models"]:
        name = model["name"]
        model_dir = directory / "models" / name
        raw = read_rows(model_dir / "answers.jsonl")
        if any(row.get("model") != name or row.get("id") not in ids for row in raw):
            raise ValueError(f"foreign prediction row: {name}")
        for row in runner.dedupe_latest(raw, lambda row: (row["model"], row["id"])):
            predictions[(name, row["id"])] = row
        events[name] = read_rows(model_dir / "executions.jsonl")
    return manifest, records, predictions, events


async def run_candidates(args):
    cfg = runner.load_config()
    records = read_rows(DATASET)
    validate_records(records)
    metadata = json.loads((SCENARIO / "provenance.json").read_text())
    if metadata["dataset_sha256"] != digest(records) or sha(SCENARIO / "source-test-gold.json") != SOURCE_SHA256:
        raise ValueError("prepared data/provenance changed")
    prompt_text = (SCENARIO / "prompt.txt").read_text()
    for record in records:
        build_prompt(record, prompt_text)  # validate every candidate input before freeze/calls
    parallel = args.parallel_models if args.parallel_models is not None else cfg["scenario"]["tatqa"]["parallel_models"]
    contract = make_contract(cfg, records, metadata, prompt_text, parallel)
    wanted = set(args.models.split(",")) if args.models else {model["name"] for model in contract["models"]}
    available = {model["name"] for model in contract["models"]}
    if not wanted or not wanted <= available:
        raise ValueError(f"unknown/excluded requested models: {sorted(wanted - available)}")
    directory = RESULTS / args.run_id
    freeze_run(directory, args.run_id, contract, records, prompt_text)
    print(f"Frozen {args.run_id}: {len(contract['models'])} API models, 200 questions, parallel_models={parallel}, contract={digest(contract)}")
    if args.freeze_only:
        return 0
    semaphore = asyncio.Semaphore(parallel)
    async def one(model):
        async with semaphore:
            model_dir = directory / "models" / model["name"]
            with execution_lock(model_dir):
                # Validate snapshots and every code hash before an invocation.
                load_run(directory)
                model_dir.mkdir(parents=True, exist_ok=True)
                cache = TATQACache(model_dir / "answers.jsonl")
                pending = [row for row in records if not cache.has(model["name"], row["id"])]
                if not pending:
                    return {"model": model["name"], "failed": 0, "cached": 200}
                event_id = f"{os.getpid()}-{now()}"
                event_path = model_dir / "executions.jsonl"
                append_event(event_path, {"event": "started", "id": event_id, "started_at": now(),
                                         "pending": len(pending), "contract_sha256": digest(contract)})
                try:
                    async with run_slot(directory, parallel):
                        summary = await runner.run_model(model, records, cache, contract["aws_region"],
                                                         contract["concurrency_default"],
                                                         prompt_builder=lambda row: build_prompt(row, prompt_text))
                except BaseException as error:
                    append_event(event_path, {"event": "interrupted", "id": event_id,
                                             "finished_at": now(), "error_type": type(error).__name__})
                    raise
                completed = sum(cache.has(model["name"], record["id"]) for record in records)
                summary.update(successful=completed, failed=len(records) - completed)
                append_event(event_path, {"event": "finished", "id": event_id,
                                         "finished_at": now(), "summary": summary})
                return summary
    summaries = await asyncio.gather(*(one(model) for model in contract["models"] if model["name"] in wanted))
    print(json.dumps({"run_id": args.run_id, "models": summaries}, ensure_ascii=False))
    return int(any(summary["failed"] for summary in summaries))


def performance_for(predictions, model, total, invocations=1, as_of=None):
    # Scoring status never overwrites a transport error. A token-limited
    # successful transport still has retained, billed token usage.
    performance = finqa_compare.performance_of(predictions, model, invocations,
                                               model.get("pricing_valid_until"), as_of)
    if len(predictions) != total and performance["cost_unavailable_reason"] != "configured_price_expired":
        performance.update(estimated_cost_usd=None, estimated_cost_per_question_usd=None,
                           cost_unavailable_reason="missing_responses")
    return performance


def compose_report(directory):
    manifest, records, predictions, events = load_run(directory)
    contract = manifest["contract"]
    models, samples = [], []
    all_scores = {}
    for model in contract["models"]:
        name = model["name"]
        scores = [evaluate_one(record, predictions.get((name, record["id"]))) for record in records]
        all_scores[name] = {row["id"]: row for row in scores}
        metrics = summarize(scores)
        raw = [predictions[(name, row["id"])] for row in records if (name, row["id"]) in predictions]
        starts = [event for event in events[name] if event["event"] == "started"]
        as_of = starts[0]["started_at"][:10] if starts else manifest["created_at"][:10]
        performance = performance_for(raw, model, len(records), max(1, len(starts)), as_of)
        metrics.update(performance)
        by_type = {}
        for kind in QUOTAS:
            subset = [score for record, score in zip(records, scores) if record["answer_type"] == kind]
            quality = summarize(subset)
            by_type[kind] = {key: quality[key] for key in ("total", "exact_match", "f1", "correct")}
        models.append({
            "name": name, "provider": model["api"], "metrics": metrics, "by_answer_type": by_type,
            "status": "not_run" if not raw and not starts else ("complete" if not metrics["missing"] and not metrics["request_failures"] and not metrics["truncated"] else "incomplete"),
            "run_config": model, "invocations": len(starts),
            "request_settings": {
                "temperature": "omitted/provider default" if model["model_id"] in contract["temperature_omitted_model_ids"] else 0,
                "reasoning_effort": model.get("mantle_reasoning_effort", model.get("bedrock_reasoning_effort", "omitted/provider default; effective value unknown")),
                "chat_template_kwargs": model.get("chat_template_kwargs"),
                "max_output_tokens": contract["max_output_tokens"],
                "concurrency": model.get("concurrency", contract["concurrency_default"]),
                "request_max_attempts": model.get("request_max_attempts", 1),
            },
        })
    for record in records:
        sample_predictions = []
        for model in contract["models"]:
            name = model["name"]
            prediction = predictions.get((name, record["id"]))
            score = all_scores[name][record["id"]]
            sample_predictions.append({"model": name, **score,
                                       "output_text": prediction.get("output_text") if prediction else None,
                                       "error": prediction.get("error") if prediction else None,
                                       "failed_response": prediction.get("failed_response") if prediction else None,
                                       "prediction_sha256": digest(prediction)})
        samples.append({"id": record["id"], "context_id": record["context_id"],
                        "question": record["question"], "answer_type": record["answer_type"],
                        "gold_answer": record["gold"]["answer"], "gold_scale": record["gold"]["scale"],
                        "table": record["table"], "paragraphs": record["paragraphs"],
                        "predictions": sample_predictions})
    return {"run_id": manifest["run_id"], "scenario": "tatqa", "generated_at": now(),
            "dataset": contract["dataset"], "protocol": contract["protocol"],
            "contract_sha256": manifest["contract_sha256"], "contract": contract,
            "models": models, "excluded_models": contract["excluded_models"], "samples": samples}


def write_report(report):
    REPORTS.mkdir(parents=True, exist_ok=True)
    write_json(REPORTS / f"{report['run_id']}.json", report)
    path = REPORTS / "index.json"
    index = json.loads(path.read_text()) if path.exists() else {"latest": None, "runs": []}
    index["runs"] = [r for r in index["runs"] if r["id"] != report["run_id"]]
    index["runs"].insert(0, {"id": report["run_id"], "label": report["run_id"]})
    index["latest"] = report["run_id"]
    write_json(path, index)


def strict_prediction(text):
    """Unwrap a complete outer fence only; never extract/repair an answer."""
    if not isinstance(text, str):
        raise ValueError("response is not text")
    match = re.fullmatch(r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*", text,
                         re.DOTALL | re.IGNORECASE)
    if match:
        text = match[1]
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError("nonfinite JSON number")
    obj = json.loads(text, object_pairs_hook=object_pairs, parse_constant=reject_constant)
    if not isinstance(obj, dict) or set(obj) != {"answer", "scale"}:
        raise ValueError("exactly answer and scale required")
    if not isinstance(obj["scale"], str) or obj["scale"] not in SCALES:
        raise ValueError("invalid scale")
    answers = obj["answer"] if isinstance(obj["answer"], list) else [obj["answer"]]
    if not answers or any(type(a) not in (str, int, float) for a in answers):
        raise ValueError("answer must be scalar or nonempty flat scalar list")
    for answer in answers:
        if isinstance(answer, str):
            answer.encode("utf-8")  # reject unpaired JSON Unicode surrogates
            if not answer.strip():
                raise ValueError("empty answer")
        elif not math.isfinite(answer):
            raise ValueError("nonfinite answer")
    # Plain decimal is value-preserving JSON-number serialization, not answer
    # repair. Upstream's regex misreads strings such as '1e-05' as 1. Keep
    # candidate string answers unchanged, including their original notation.
    strings = [answer if isinstance(answer, str) else format(Decimal(str(answer)), "f")
               for answer in answers]
    return obj, strings, bool(match)


def is_truncated(prediction):
    if not prediction:
        return False
    details = prediction.get("translation_error_details") or {}
    failed = prediction.get("failed_response") or {}
    reasons = [prediction.get("finish_reason"), failed.get("finish_reason"),
               details.get("incomplete_reason"), details.get("stop_reason")]
    return (any(reason in {"length", "max_tokens", "max_output_tokens", "model_length"}
                for reason in reasons) or failed.get("response_status") == "incomplete"
            or prediction.get("response_status") == "incomplete")


class TATQACache(runner.ResultCache):
    """Scenario cache must not mark an explicitly truncated request done."""
    def _record_latest(self, row):
        super()._record_latest(row)
        if is_truncated(row):
            self.seen.discard((row["model"], row["id"]))


def evaluate_one(record, prediction):
    scored = {"id": record["id"], "exact_match": 0.0, "f1": 0.0,
              "correct": False, "answer": None, "scale": None, "fence_stripped": False}
    if prediction is None:
        return {**scored, "status": "missing"}
    if is_truncated(prediction):
        return {**scored, "status": "truncated"}
    if prediction.get("error") is not None or prediction.get("response_status", "completed") != "completed":
        return {**scored, "status": "request_failed"}
    try:
        obj, answers, fenced = strict_prediction(prediction.get("output_text"))
        metric = TaTQAEmAndF1()
        # A nonempty string list preserves zero and avoids upstream mixed-type
        # sorting failures. All answer normalization stays inside upstream.
        metric(record["gold"], answers, obj["scale"])
        em, f1, _, _ = metric.get_overall_metric()
        if not all(math.isfinite(value) for value in (em, f1)):
            raise ValueError("nonfinite evaluator result")
        return {**scored, "exact_match": float(em), "f1": float(f1), "correct": em == 1,
                "answer": obj["answer"], "scale": obj["scale"], "fence_stripped": fenced,
                "status": "scored"}
    except (ValueError, TypeError, OverflowError, KeyError, RecursionError) as error:
        return {**scored, "status": "invalid", "evaluation_error": str(error)}


def _selfcheck():
    gold = {"id": "numeric", "gold": {"answer_type": "arithmetic", "answer": 12,
            "scale": "million", "answer_from": "table", "derivation": "6+6"}}
    prediction = {"output_text": '{"answer":12,"scale":"million"}', "error": None}
    assert evaluate_one(gold, prediction)["exact_match"] == 1, "official scaled arithmetic"
    assert evaluate_one(gold, prediction)["f1"] == 1
    zero = {**gold, "gold": {**gold["gold"], "answer": 0, "scale": ""}}
    assert evaluate_one(zero, {"output_text": '{"answer":0,"scale":""}'})["exact_match"] == 1
    one = {**gold, "gold": {**gold["gold"], "answer": 1, "scale": ""}}
    assert evaluate_one(one, {"output_text": '{"answer":0.00001,"scale":""}'})["exact_match"] == 0, "numeric JSON must preserve its decimal value"
    assert evaluate_one(gold, {"output_text": '{"answer":12,"scale":""}'})["exact_match"] == 0
    assert evaluate_one(gold, None)["status"] == "missing"
    assert evaluate_one(gold, {"error": "network"})["status"] == "request_failed"
    assert evaluate_one(gold, {"error": "bad", "finish_reason": "length"})["status"] == "truncated"
    for text in ('{"answer":NaN,"scale":""}', '{"answer":1e999,"scale":""}',
                 '{"answer":true,"scale":""}', '{"answer":null,"scale":""}',
                 '{"answer":[["x"]],"scale":""}', '{"answer":[],"scale":""}',
                 '{"answer":12,"answer":13,"scale":"million"}',
                 '{"answer":12,"scale":"million","reason":"x"}',
                 'Explanation {"answer":12,"scale":"million"}',
                 '{"answer":12,"scale":"Million"}'):
        assert evaluate_one(gold, {"output_text": text})["status"] == "invalid", text
    surrogate = '{"answer":"\\ud800","scale":""}'
    assert evaluate_one(gold, {"output_text": surrogate})["status"] == "invalid", "unpaired Unicode must zero safely"
    span = {"id": "span", "gold": {"answer_type": "span", "answer": ["the net income"],
            "scale": "", "answer_from": "text", "derivation": ""}}
    assert evaluate_one(span, {"output_text": '{"answer":"NET income","scale":""}'})["exact_match"] == 1
    assert evaluate_one(span, {"output_text": '{"answer":"income","scale":""}'})["f1"] == .67
    multi = {**span, "gold": {**span["gold"], "answer_type": "multi-span", "answer": ["alpha", "beta"]}}
    assert evaluate_one(multi, {"output_text": '{"answer":["beta","alpha"],"scale":""}'})["exact_match"] == 1
    assert evaluate_one(multi, {"output_text": '{"answer":["alpha"],"scale":""}'})["f1"] == .67
    assert evaluate_one(gold, {"output_text": '```json\n{"answer":12,"scale":"million"}\n```'})["fence_stripped"]
    source = json.loads((SCENARIO / "source-test-gold.json").read_text())
    records = select_records(source, 20261027)
    assert len(records) == 200, "selected dataset must contain 200 questions"
    assert len({r["context_id"] for r in records}) == 200
    assert records == select_records(source, 20261027)
    reordered = [{**document, "questions": list(reversed(document["questions"]))}
                 for document in reversed(source)]
    assert records == select_records(reordered, 20261027), "source ordering cannot affect selection"
    template = (SCENARIO / "prompt.txt").read_text()
    for record in records:
        changed_gold = {**record, "gold": {"answer": "SECRET-GOLD", "derivation": "SECRET-DERIVATION"},
                        "answer_type": "SECRET-TYPE"}
        assert build_prompt(record, template) == build_prompt(changed_gold, template)
        payload = json.loads(build_prompt(record, template)[len(template):])
        assert set(payload) == {"table", "paragraphs", "question"}
        answer = {"answer": record["gold"]["answer"], "scale": record["gold"]["scale"]}
        assert evaluate_one(record, {"output_text": json.dumps(answer)})["exact_match"] == 1, record["id"]
    # Restore the one import change and check the exact pinned upstream bytes.
    metric_source = (ROOT / "bench/vendor/tatqa/tatqa_metric.py").read_bytes()
    restored = metric_source.replace(b"from .tatqa_utils import *", b"from tatqa_utils import *")
    # apply_patch may add a terminal newline to the upstream file.
    upstream_hash = "2aeeac479f89f8c76300af1cc0e8d098eb86af84bc386b38b6ab4af484a6dea8"
    assert hashlib.sha256(restored).hexdigest() == upstream_hash or hashlib.sha256(restored.rstrip(b"\n")).hexdigest() == upstream_hash
    assert sha(ROOT / "bench/vendor/tatqa/tatqa_utils.py") == "a84bb2f960737cf0a53733637a674cc4b20ef030a2be6a4b21dc2c4356f415ec"
    scores = [evaluate_one(gold, prediction), evaluate_one(gold, None),
              evaluate_one(gold, {"error": "failed"}),
              evaluate_one(gold, {"output_text": "broken"})]
    aggregate = summarize(scores)
    assert aggregate["total"] == 4 and aggregate["exact_match"] == .25
    assert aggregate["scored"] == 1 and aggregate["missing"] == 1
    assert evaluate_one(gold, {"output_text": prediction["output_text"], "response_status": "failed"})["status"] == "request_failed", "nonterminal provider status cannot score"
    deep = '{"answer":' + '[' * 1100 + '"x"' + ']' * 1100 + ',"scale":""}'
    assert evaluate_one(gold, {"output_text": deep})["status"] == "invalid", "deep JSON must not abort report"
    cfg = runner.load_config()
    metadata = {"questions": 200, "documents": 200, "answer_types": QUOTAS,
                "dataset_sha256": digest(records), "seed": 20261027, "split": "test"}
    template = (SCENARIO / "prompt.txt").read_text()
    contract = make_contract(cfg, records, metadata, template, 4)
    assert not any(model.get("base_url") or model["api"] == "translate" or not model.get("enabled", True)
                   for model in contract["models"])
    def rejects(call):
        try:
            call()
        except ValueError:
            return
        raise AssertionError("expected immutable contract rejection")
    with tempfile.TemporaryDirectory(prefix="tatqa-selfcheck-") as temporary:
        directory = Path(temporary) / "run"
        freeze_run(directory, "selfcheck", contract, records, template)
        assert freeze_run(directory, "selfcheck", contract, records, template)["contract"] == contract
        for key, changed in (("parallel_models", 1), ("max_output_tokens", 1),
                             ("prompt_sha256", "0" * 64), ("dataset_sha256", "0" * 64)):
            rejects(lambda key=key, changed=changed: freeze_run(directory, "selfcheck", {**contract, key: changed}, records, template))
        (directory / "prompt.txt").write_text(template + "changed")
        rejects(lambda: load_run(directory))
        (directory / "prompt.txt").write_text(template)
        model = contract["models"][0]
        model_dir = directory / "models" / model["name"]
        model_dir.mkdir(parents=True)
        answer = {"model": model["name"], "id": records[0]["id"], "error": None,
                  "output_text": json.dumps({"answer": records[0]["gold"]["answer"], "scale": records[0]["gold"]["scale"]}),
                  "tokens_in": 100, "tokens_out": 10, "latency_s": 1,
                  "timestamp": "2026-10-27T00:00:01+00:00"}
        truncated_path = Path(temporary) / "truncated.jsonl"
        write_rows(truncated_path, [{**answer, "finish_reason": "max_tokens"}])
        assert not TATQACache(truncated_path).has(model["name"], answer["id"]), "truncated requests must remain resumable"
        write_rows(model_dir / "answers.jsonl", [{**answer, "error": "first failure"}, answer])
        report = compose_report(directory)
        metrics = report["models"][0]["metrics"]
        assert metrics["total"] == 200 and metrics["correct"] == 1 and metrics["exact_match"] == .005
        assert metrics["missing"] == 199 and metrics["scored"] == 1
        assert metrics["response_coverage"] == .005 and metrics["estimated_cost_usd"] is None
        assert report["models"][1]["metrics"]["missing"] == 200
        assert sum(row["total"] for row in report["models"][0]["by_answer_type"].values()) == 200
        assert all(set(row) == {"total", "correct", "exact_match", "f1"}
                   for row in report["models"][0]["by_answer_type"].values())
        write_rows(model_dir / "answers.jsonl", [{**answer, "id": "foreign"}])
        rejects(lambda: load_run(directory))
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["contract"]["code_sha256"]["runner"] = "0" * 64
        manifest["contract_sha256"] = digest(manifest["contract"])
        write_json(directory / "manifest.json", manifest)
        rejects(lambda: load_run(directory))
        async def check_slots():
            entered = asyncio.Event()
            async def waiting():
                async with run_slot(Path(temporary), 1):
                    entered.set()
            async with run_slot(Path(temporary), 1):
                task = asyncio.create_task(waiting())
                await asyncio.sleep(.01)
                assert not entered.is_set(), "cohort concurrency cap must span processes"
            await asyncio.wait_for(task, 1)
            assert entered.is_set()
        asyncio.run(check_slots())
        # Exercise the actual shared runner/cache with an offline transport.
        # One failed request is retried once on resume; invalid successful JSON
        # is cached and never gets an answer-dependent retry.
        fixture_cfg = json.loads(json.dumps(cfg))
        fixture_cfg["models"] = [{"name": "selfcheck-api", "api": "bedrock", "model_id": "offline",
                                  "price_in": 1, "price_out": 2, "concurrency": 2}]
        fixture_cfg["scenario"]["tatqa"]["parallel_models"] = 1
        originals = (runner.load_config, runner.make_client, runner.call_bedrock, globals()["RESULTS"])
        calls = []
        class OfflineClient:
            def close(self):
                pass
        async def offline_call(client, model_id, prompt, **kwargs):
            calls.append(prompt)
            if len(calls) == 1:
                raise OSError("offline failure fixture")
            return {"text": "invalid JSON", "tokens_in": 100, "tokens_out": 10, "finish_reason": "end_turn"}
        try:
            import io
            from contextlib import redirect_stdout
            runner.load_config = lambda: fixture_cfg
            runner.make_client = lambda model, region: OfflineClient()
            runner.call_bedrock = offline_call
            globals()["RESULTS"] = Path(temporary) / "offline-runs"
            args = argparse.Namespace(run_id="offline", models=None, parallel_models=None, freeze_only=True)
            with redirect_stdout(io.StringIO()):
                assert asyncio.run(run_candidates(args)) == 0 and not calls
                args.freeze_only = False
                assert asyncio.run(run_candidates(args)) == 1 and len(calls) == 200
                assert asyncio.run(run_candidates(args)) == 0 and len(calls) == 201
                assert asyncio.run(run_candidates(args)) == 0 and len(calls) == 201
            offline_dir = globals()["RESULTS"] / "offline"
            assert len(read_rows(offline_dir / "models/selfcheck-api/answers.jsonl")) == 201
            complete = compose_report(offline_dir)["models"][0]["metrics"]
            assert complete["total"] == 200 and complete["invalid"] == 200 and complete["correct"] == 0
            assert complete["response_coverage"] == 1 and complete["missing"] == 0
            assert abs(complete["estimated_cost_usd"] - .024) < 1e-12
            assert abs(complete["estimated_cost_per_question_usd"] - .00012) < 1e-12
            assert len([e for e in read_rows(offline_dir / "models/selfcheck-api/executions.jsonl")
                        if e["event"] == "started"]) == 2
            with execution_lock(offline_dir / "models/selfcheck-api"):
                rejects(lambda: asyncio.run(run_candidates(args)))
        finally:
            runner.load_config, runner.make_client, runner.call_bedrock, globals()["RESULTS"] = originals
    print("TAT-QA selfcheck passed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("prepare")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--models", help="execute selected names from the full frozen API roster")
    run_parser.add_argument("--parallel-models", type=int)
    run_parser.add_argument("--freeze-only", action="store_true")
    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if hasattr(args, "run_id") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.run_id):
        parser.error("run-id must be a safe basename")
    if args.selfcheck:
        _selfcheck()
    elif args.command == "prepare":
        prepare()
    elif args.command == "run":
        return asyncio.run(run_candidates(args))
    elif args.command == "report":
        report = compose_report(RESULTS / args.run_id)
        write_report(report)
        print(f"Report: {REPORTS / (args.run_id + '.json')}; {len(report['models'])} models × {report['dataset']['questions']} questions")
    else:
        parser.error("choose prepare, run, report or --selfcheck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
