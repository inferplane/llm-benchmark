"""Compare the translation roster's generative models on identical FinQA inputs.

Consumes immutable per-model runs; never makes model API calls.
uv run python -m bench.finqa_compare --run-id finqa-all-20260918
"""

import argparse
from datetime import date
import hashlib
import html
import json
from pathlib import Path
import re

from bench import finqa
from bench import report as translation_report
from bench import run as runner

POLICY = """FinQA execution comparison v2: every model uses identical questions and prompt.
Only an enclosing JSON markdown fence and a JSON array of program-step strings
are normalized. Normalization never edits numbers, operations, references or
units; nested expressions and table references remain invalid. Raw strict
correctness and normalization counts are retained separately.
Final results are rounded to five decimals and compared exactly with qa.exe_ans.
All selected questions, including failed/missing responses, remain in the denominator.
The dataset has known unit/denominator inconsistencies. This small dev sample
compares this protocol; it is not a validated financial-reasoning leaderboard.
Costs use configured model rates and retained successful responses, including
incorrect or invalid answers. Failed requests, retries and judge costs are not
estimated. Self-hosted runtime cost excludes model download, provisioning and
idle time, and is unavailable after multiple invocations. Expired configured
prices are withheld. No per-subset cost or throughput is computed.
"""


def normalize_prediction(prediction):
    """Unwrap formatting only, preserving every arithmetic operation verbatim."""
    if prediction is None or prediction.get("error") is not None:
        return prediction, []
    text = prediction.get("output_text")
    if not isinstance(text, str):
        return prediction, []
    normalized = []
    match = re.fullmatch(r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match[1]
        normalized.append("json_fence")
    try:
        obj = json.loads(text)
    except ValueError:
        return prediction, []  # no extraction from explanations or broken JSON
    if isinstance(obj, dict) and isinstance(obj.get("program"), list):
        steps = obj["program"]
        if not steps or not all(isinstance(step, str) and finqa.STEP.fullmatch(step.strip()) for step in steps):
            return prediction, []
        obj = {**obj, "program": ", ".join(steps)}
        text = json.dumps(obj, ensure_ascii=False)
        normalized.append("program_step_array")
    if not normalized:
        return prediction, []
    return {**prediction, "output_text": text}, normalized


def evaluate_one(record, prediction):
    strict = finqa.score(record, prediction)
    normalized, changes = normalize_prediction(prediction)
    scored = finqa.score(record, normalized)
    return {
        **scored, "prediction_sha256": finqa.digest(prediction),
        "strict_correct": strict["correct"], "strict_status": strict["status"],
        "normalizations": changes,
    }


def performance_of(predictions, model_cfg, invocations=1, pricing_valid_until=None, as_of=None):
    """Reuse the existing model-level money path, withholding incomplete estimates."""
    rows = [{**row, "translation_error": row.get("error")} for row in predictions]
    aggregate = translation_report.aggregate_full(rows, model_cfg, {})
    complete = bool(rows) and aggregate["successful_translations"] == len(rows)
    expired = pricing_valid_until is not None and (as_of or date.today().isoformat()) > pricing_valid_until
    reason = "configured_price_expired" if expired else ("incomplete_responses" if not complete else None)
    if model_cfg.get("base_url") and invocations != 1:
        reason = "multiple_gpu_invocations"
    return {
        "estimated_cost_usd": aggregate["cost_total_usd"] if reason is None else None,
        "estimated_cost_per_question_usd": aggregate["cost_per_segment_usd"] if reason is None else None,
        "cost_unavailable_reason": reason,
        "latency_p50_s": aggregate["latency_e2e_p50_s"],
        "latency_p95_s": aggregate["latency_e2e_p95_s"],
        "throughput_tok_s": aggregate["throughput_tok_s"] if invocations == 1 else None,
        "tokens_in": sum(row.get("tokens_in") or 0 for row in rows if row["translation_error"] is None),
        "tokens_out": sum(row.get("tokens_out") or 0 for row in rows if row["translation_error"] is None),
    }


def compose(run_id, source_root=finqa.RESULTS, cfg=None, roster=None):
    cfg = cfg or runner.load_config()
    configs = {model["name"]: model for model in cfg["models"]}
    if roster is None:
        roster = json.loads((finqa.ROOT / "docs/results/integrated-2026-09-17.json").read_text())
    names = [model["name"] for model in roster["models"]]
    models, sources, excluded, samples = [], [], [], []
    shared, records = None, None
    for name in names:
        current = configs[name]
        if current["api"] == "translate":
            excluded.append({"name": name, "reason": "번역 전용 서비스로 수치 질의응답을 지원하지 않음"})
            continue
        if not current.get("enabled", True):
            excluded.append({"name": name, "reason": "config.toml에서 비활성화됨"})
            continue
        directory = source_root / f"{run_id}-{name}"
        manifest, rows, predictions = finqa.load_run(directory)
        contract = manifest["contract"]
        if len(contract["models"]) != 1 or contract["models"][0]["name"] != name:
            raise ValueError(f"source model mismatch: {name}")
        # Bind the display name to the actual provider model, route, reasoning,
        # chat template, GPU and request settings. Pricing is historical metadata
        # and may gain a later expiry annotation without changing generation.
        metadata_keys = {"enabled", "price_in", "price_out", "price_per_char",
                         "gpu_hourly_usd", "pricing_valid_until"}
        expected = {key: value for key, value in current.items() if key not in metadata_keys}
        observed = {key: value for key, value in contract["models"][0].items() if key not in metadata_keys}
        if expected != observed:
            changed = sorted(key for key in expected.keys() | observed.keys()
                             if expected.get(key) != observed.get(key))
            raise ValueError(f"source execution settings differ for {name}: {', '.join(changed)}")
        if not rows:
            raise ValueError("empty comparison dataset")
        # Sharing a model name isn't enough: every question/prompt/generation cap must match.
        identity = {key: contract[key] for key in (
            "dataset_sha256", "prompt_sha256", "max_output_tokens", "temperature",
            "temperature_omitted_model_ids", "request_timeout_s",
            "aws_region", "concurrency_default", "runner_sha256", "finqa_sha256",
        )}
        if shared is None:
            shared, records = identity, rows
        elif shared != identity:
            raise ValueError(f"incompatible comparison inputs for {name}")
        if hashlib.sha256((directory / "prompt.txt").read_bytes()).hexdigest() != identity["prompt_sha256"]:
            raise ValueError(f"prompt snapshot changed for {name}")
        scores = []
        raw_rows = []
        for record in rows:
            prediction = predictions.get((name, record["id"]))
            scores.append({"model": name, **evaluate_one(record, prediction)})
            if prediction is not None:
                raw_rows.append(prediction)
            samples.append({
                "model": name, "id": record["id"], "question": record["question"],
                "output_text": prediction.get("output_text") if prediction else None,
                "gold_answer": record["gold_answer"], "reference_answer": record["reference_answer"],
                "reference_program": record["reference_program"], **scores[-1],
            })
        aggregate = finqa.summarize(scores)
        aggregate["strict_correct"] = sum(row["strict_correct"] for row in scores)
        aggregate["format_adjusted"] = sum(bool(row["normalizations"]) for row in scores)
        model_cfg = contract["models"][0]
        performance = performance_of(
            raw_rows, model_cfg, len(manifest["executions"]),
            current.get("pricing_valid_until"), manifest["executions"][0]["started_at"][:10],
        )
        if len(raw_rows) != len(rows):
            performance.update(estimated_cost_usd=None, estimated_cost_per_question_usd=None,
                               cost_unavailable_reason="missing_responses")
        aggregate.update(performance)
        state = "complete" if not aggregate["request_failed"] and not aggregate["missing"] else "incomplete"
        serving = None
        if model_cfg.get("base_url"):
            serving = json.loads((directory / "serving.json").read_text())
            if (serving["model_id"] != model_cfg["model_id"]
                    or serving["node_instance_type"] != model_cfg["gpu_instance_type"]
                    or serving["tensor_parallel_size"] != model_cfg["tensor_parallel_size"]
                    or serving["max_model_len"] != 8192 or not serving.get("image_id")):
                raise ValueError(f"GPU serving configuration mismatch for {name}")
        models.append({
            "name": name, "provider": "vllm" if model_cfg.get("base_url") else model_cfg["api"],
            "status": state, "aggregate": aggregate,
            "run_config": model_cfg, "source_run_id": manifest["run_id"],
            "pricing_valid_until": current.get("pricing_valid_until"),
            "serving_config": serving,
        })
        sources.append({
            "run_id": manifest["run_id"], "manifest_sha256": finqa.digest(manifest),
            "answers_sha256": finqa.digest(list(predictions.values())),
            "dataset_sha256": contract["dataset_sha256"],
            "started_at": manifest["executions"][0]["started_at"],
            "finished_at": manifest["executions"][-1].get("finished_at"),
        })
    if not models:
        raise ValueError("no comparable generative models")
    return {
        "scenario": "finqa", "run_id": run_id, "models": models,
        "dataset_sha256": shared["dataset_sha256"], "prompt_sha256": shared["prompt_sha256"],
        "generation_parameters": shared, "source_runs": sources, "excluded_models": excluded,
        "assessment_scope": "multi_model_protocol_comparison",
        "evaluator": "finqa-execution-v2",
        "evaluator_sha256": finqa.digest({
            "compare_code": Path(__file__).read_text(), "finqa_code": Path(finqa.__file__).read_text(),
            "policy": POLICY,
        }),
        "dataset": {"questions": len(records), "split": "dev", "source": "FinQA", "seed": 13},
        "warnings": [
            "동일 문항·프롬프트의 모델 비교입니다. 20문항과 원본 단위·분모 불일치로 금융 업무 전반의 순위를 뜻하지 않습니다.",
            "코드블록·계산 단계 목록 표현만 공통 정규화했습니다. 이전 파일럿의 엄격한 형식 채점과 점수를 직접 비교하지 마세요.",
            "모델별 기존 추론·동시성 설정을 유지했습니다. 추정 비용은 설정 단가와 성공 응답 기준이며 전체 실험 청구액이 아닙니다.",
        ],
        "policy": POLICY, "evaluations": samples,
    }


def write_comparison(report, output_root=finqa.REPORTS):
    name = report["run_id"]
    finqa.write_json(output_root / f"{name}.json", report)
    rows = []
    for model in sorted(report["models"], key=lambda m: (-m["aggregate"]["execution_accuracy"], m["name"])):
        a = model["aggregate"]
        cost = a["estimated_cost_per_question_usd"]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            model["name"], f'{a["correct"]}/{a["questions"]}', f'{a["execution_accuracy"]:.1%}',
            a["strict_correct"], a["format_adjusted"], a["invalid_program"], a["request_failed"],
            a["missing"], f"${cost:.5f}" if cost is not None else "—",
            a["latency_p50_s"] if a["latency_p50_s"] is not None else "—",
        )) + "</tr>")
    page = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FinQA 전체 모델 비교</title>
<style>body{font:18px/1.6 system-ui;margin:2rem;color:#172337;overflow-wrap:anywhere}
table{border-collapse:collapse;white-space:nowrap}th,td{padding:.7rem;border:1px solid #ccd3dd;text-align:right}
th:first-child,td:first-child{text-align:left}pre{white-space:pre-wrap}.scroll{overflow:auto}</style>
<nav><a href="../finqa.html">금융 수치 추론 대시보드</a> · <a href="../index.html">번역 벤치마크</a></nav>
<h1>FinQA 전체 모델 비교</h1>"""
    page += f"<p>{len(report['models'])}개 모델 · 동일 {report['dataset']['questions']}문항 · 실행 {html.escape(name)}</p>"
    page += "".join(f"<p>{html.escape(warning)}</p>" for warning in report["warnings"])
    page += "<div class=scroll><table><thead><tr>" + "".join(f"<th>{value}</th>" for value in (
        "모델", "정답/전체", "실행 정답률", "정규화 전 정답", "형식 정규화", "계산식 실행불가",
        "요청 실패", "미응답", "추정 비용/문항", "지연 p50(s)",
    )) + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    page += "<h2>제외 대상</h2>" + "".join(f"<p>{html.escape(item['name'])}: {html.escape(item['reason'])}</p>"
                                           for item in report["excluded_models"])
    for model in report["models"]:
        page += f"<details><summary>{html.escape(model['name'])} · 문항별 응답과 판정</summary>"
        page += "<pre>" + html.escape(json.dumps({
            "run_config": model["run_config"], "serving_config": model["serving_config"],
            "cost_unavailable_reason": model["aggregate"]["cost_unavailable_reason"],
        }, ensure_ascii=False, indent=2)) + "</pre>"
        for sample in report["evaluations"]:
            if sample["model"] == model["name"]:
                page += "<pre>" + html.escape(json.dumps(sample, ensure_ascii=False, indent=2)) + "</pre>"
        page += "</details>"
    page += "<details><summary>평가·비용 규칙</summary><pre>" + html.escape(POLICY) + "</pre></details></html>"
    (output_root / f"{name}.html").write_text(page)
    index_path = output_root / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"runs": []}
    index["runs"] = [{"id": name, "label": f"전체 {len(report['models'])}개 모델 비교"}] + [
        entry for entry in index["runs"] if entry["id"] != name
    ]
    index["latest"] = name
    finqa.write_json(index_path, index)


def selfcheck():
    import tempfile
    record = {
        "id": "test", "table": [["item", "value"], ["revenue", "20"]],
        "pre_text": [], "post_text": [], "gold_answer": 20.0, "gold_evidence": ["table_1"],
        "question": "What is revenue?", "reference_answer": "20", "reference_program": "add(20, 0)",
    }
    raw = {"output_text": '{"program":"add(20, 0)","evidence":["table_1"]}', "error": None}
    fenced = {**raw, "output_text": "```json\n" + raw["output_text"] + "\n```"}
    steps = {**raw, "output_text": '{"program":["add(10, 5)", "add(#0, 5)"],"evidence":["table_1"]}'}
    assert evaluate_one(record, raw)["correct"] and evaluate_one(record, raw)["strict_correct"]
    assert evaluate_one(record, fenced)["correct"] and not evaluate_one(record, fenced)["strict_correct"]
    assert evaluate_one(record, steps)["correct"] and not evaluate_one(record, steps)["strict_correct"]
    for invalid in (
        '{"program":["add(10, 5)", 5]}', '{"program":[]}',
        '{"program":["add(1", "2)"]}',
        '{"program":["add(10, 5), add(#0, 5)"]}',
        'Explanation: ' + raw["output_text"],
        '```json\n' + raw["output_text"] + '\n```\nExplanation',
        '{"program":["add(table_1, 0)"]}', '{"program":["add(20, 0, 0)"]}',
        '{"program":["add(20, 0)", "divide(#0, 100)"]}',
    ):
        assert not evaluate_one(record, {**raw, "output_text": invalid})["correct"], invalid
    # Normalization must not repair a sign or scale error.
    wrong = {**raw, "output_text": '```json\n{"program":"add(-20, 0)"}\n```'}
    assert not evaluate_one(record, wrong)["correct"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        configs = [{"name": name, "model_id": name + "-id", "api": "bedrock", "price_in": 1, "price_out": 5}
                   for name in ("model-a", "model-b")]
        cfg = {"models": [*configs, {"name": "translator", "api": "translate"}]}
        roster = {"models": [{"name": item["name"]} for item in cfg["models"]]}
        prompt = "fixture prompt"
        identity = {
            "dataset_sha256": finqa.digest([record]),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "max_output_tokens": 4096, "temperature": 0, "aws_region": "us-west-2",
            "concurrency_default": 2, "runner_sha256": "fixture", "finqa_sha256": "fixture",
            "temperature_omitted_model_ids": [], "request_timeout_s": 600,
        }
        for model, output in zip(configs, (raw, fenced)):
            name = "fixture-" + model["name"]
            directory = root / name
            directory.mkdir()
            (directory / "prompt.txt").write_text(prompt)
            finqa.write_rows(directory / "dataset.jsonl", [record])
            finqa.write_rows(directory / "answers.jsonl", [{
                **output, "model": model["name"], "id": record["id"],
                "tokens_in": 10, "tokens_out": 5, "latency_s": 1,
                "timestamp": "2026-09-18T01:00:01+00:00",
            }])
            finqa.write_json(directory / "manifest.json", {
                "run_id": name, "contract": {**identity, "models": [model]},
                "executions": [{"started_at": "2026-09-18T01:00:00+00:00",
                                "finished_at": "2026-09-18T01:00:01+00:00"}],
            })
        comparison = compose("fixture", root, cfg, roster)
        assert len(comparison["models"]) == 2 and len(comparison["excluded_models"]) == 1
        assert [m["aggregate"]["correct"] for m in comparison["models"]] == [1, 1]
        assert [m["aggregate"]["strict_correct"] for m in comparison["models"]] == [1, 0]
        source_path = root / "fixture-model-a/manifest.json"
        original_source = json.loads(source_path.read_text())
        for key, value in (
            ("model_id", "different-provider-model"), ("api", "bedrock_mantle"),
            ("base_url", "http://different-server"), ("bedrock_reasoning_effort", "high"),
            ("chat_template_kwargs", {"enable_thinking": True}), ("concurrency", 32),
        ):
            changed = json.loads(json.dumps(original_source))
            changed["contract"]["models"][0][key] = value
            finqa.write_json(source_path, changed)
            try:
                compose("fixture", root, cfg, roster)
            except ValueError:
                pass
            else:
                raise AssertionError(f"changed inference setting accepted: {key}")
        finqa.write_json(source_path, original_source)
        write_comparison(comparison, root / "public")
        assert json.loads((root / "public/index.json").read_text())["latest"] == "fixture"
        # A failed latest attempt must override an old success, not silently disappear.
        path = root / "fixture-model-a/answers.jsonl"
        previous = finqa.read_rows(path)
        finqa.write_rows(path, [*previous, {**previous[0], "error": "timeout"}])
        failed = compose("fixture", root, cfg, roster)
        assert failed["models"][0]["status"] == "incomplete"
        assert failed["models"][0]["aggregate"]["request_failed"] == 1
        assert failed["models"][0]["aggregate"]["estimated_cost_usd"] is None
        # Matching model names cannot rescue a different prompt or missing source.
        path = root / "fixture-model-b/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["contract"]["prompt_sha256"] = "changed"
        finqa.write_json(path, manifest)
        try:
            compose("fixture", root, cfg, roster)
        except ValueError:
            pass
        else:
            raise AssertionError("mixed prompts were accepted")
        path.unlink()
        try:
            compose("fixture", root, cfg, roster)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("missing source model was silently omitted")
    print("FinQA comparison normalization/provenance selfcheck OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    if not args.run_id:
        parser.error("--run-id is required")
    finqa.run_directory(args.run_id)  # validate the output name before forming paths
    report = compose(args.run_id)
    write_comparison(report)
    print(f"published {len(report['models'])} models -> {finqa.REPORTS / (args.run_id + '.html')}")


if __name__ == "__main__":
    main()
