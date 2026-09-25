"""Frozen GPT-6 Luna extension: original datasets, grading, and retained peers.

One full first-attempt collection per scenario. Request/cap failures remain
failures; only successfully returned translations are sent to the old judges.
"""
import argparse
import asyncio
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
from types import SimpleNamespace

from bench import finqa, finqa_audited as qa, finqa_compare, judge, report, run
from bench.kimi_benchmark import verify_parent

NAME = "gpt-6-luna"
QA_RUN = "finqa-gpt-6-luna-20260925"
TRANSLATION_RUN = "bedrock-gpt-6-luna-20260925"
COMPARISON = "integrated-2026-09-25"
ROOT = finqa.ROOT
VALIDATION = ROOT / "validation/gpt-6-luna"
CONTRACT = VALIDATION / "contract.json"
BASE_QA = finqa.REPORTS / "finqa-kimi-k3-20260920.json"
BASE_TRANSLATION = report.DOCS_RESULTS_DIR / "integrated-2026-09-20.json"
SOURCE = ROOT / "results/grok-explicit-2026-09-16/dataset.jsonl"
FOLDER = run.RESULTS_DIR / TRANSLATION_RUN
POLICY = (
    "Preserve one recorded attempt for every input, including empty/capped/failed responses. "
    "No candidate regeneration, reasoning change, or cap increase after seeing outcomes. "
    "Grade successful returned translations with the existing two judges and rubric. "
    "Failed/nonterminal Responses remain failures even when partial text is retained. "
    "Translation quality is conditional on eligible returned text. Cost estimates cover "
    "successful calls with known token usage, not the entire experiment invoice. "
    "Preserve all prior model snapshots; report prompt cohort and measurement dates."
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def model():
    return next(m for m in run.load_config()["models"] if m["name"] == NAME)


def identity():
    verify_parent()  # Replay the original 560 judgments under the unchanged grader.
    cfg = run.load_config()
    files = [Path(__file__), Path(run.__file__), Path(report.__file__), Path(judge.__file__),
             Path(finqa.__file__), Path(qa.__file__), Path(finqa_compare.__file__),
             ROOT / "bench/kimi_benchmark.py", qa.DATASET, qa.FREEZE,
             qa.SCENARIO / "prompt.txt", run.PROMPT_PATH,
             ROOT / "scenarios/translation/rubric.txt", BASE_QA, BASE_TRANSLATION,
             VALIDATION / "pricing.json"]
    parent = read(BASE_TRANSLATION)
    explicit = next(r for r in parent["source_reports"] if r["cohort"] == "explicit")
    assert sha(run.PROMPT_PATH)[:12] == explicit["prompt_sha256"]
    assert sha(ROOT / "scenarios/translation/rubric.txt")[:12] == explicit["rubric_sha256"]
    assert len(parent["models"]) == 30 and len(read(BASE_QA)["models"]) == 29
    assert NAME not in {m["name"] for m in parent["models"]}
    return {
        "model": model(), "files": {str(p.relative_to(ROOT)): sha(p) for p in files},
        "translation_dataset_sha256": finqa.digest(finqa.read_rows(SOURCE)),
        "qa_dataset_sha256": finqa.digest(finqa.read_rows(qa.DATASET)),
        "aws_region": cfg["aws"]["region"], "translation_scenario": cfg["scenario"]["translation"],
        "qa_scenario": cfg["scenario"]["finqa_audited"],
        "max_output_tokens": run.MAX_OUTPUT_TOKENS, "request_timeout_s": run.REQUEST_TIMEOUT_S,
        "temperature": 0, "temperature_omitted": True,
        "temperature_omitted_model_ids": sorted(run.MANTLE_NO_TEMPERATURE | run.BEDROCK_NO_TEMPERATURE),
        "reasoning": "provider default; medium observed in preflight",
        "translation_cohort": "explicit", "policy": POLICY,
    }


def freeze():
    expected = identity()
    if CONTRACT.exists():
        assert read(CONTRACT)["identity"] == expected, "contract changed"
    else:
        assert not (FOLDER / "translations.jsonl").exists()
        assert not (finqa.RESULTS / QA_RUN).exists()
        finqa.write_json(CONTRACT, {"frozen_at": datetime.now(timezone.utc).isoformat(), "identity": expected})
    snapshot = FOLDER / "dataset.jsonl"
    if snapshot.exists():
        assert finqa.digest(finqa.read_rows(snapshot)) == expected["translation_dataset_sha256"]
    else:
        finqa.write_rows(snapshot, finqa.read_rows(SOURCE))


def verify():
    saved = read(CONTRACT)
    assert saved["identity"] == identity(), "pre-call contract no longer matches"
    return saved


async def measure(scenario):
    saved = verify()
    if scenario == "qa":
        directory = finqa.run_directory(QA_RUN)
        assert not (directory / "manifest.json").exists(), "do not regenerate first attempts"
        directory.mkdir(parents=True, exist_ok=True)
        args = SimpleNamespace(models=NAME, run_id=QA_RUN, dataset=qa.DATASET, limit=None)
        with finqa.locked(directory):
            return await finqa.run_candidates(args, directory, scenario_name="finqa_audited", extra_contract=saved)
    assert not (FOLDER / "manifest.json").exists(), "do not regenerate first attempts"
    assert finqa.digest(finqa.read_rows(FOLDER / "dataset.jsonl")) == saved["identity"]["translation_dataset_sha256"]
    finqa.write_json(FOLDER / "extension.json", saved)
    summary = await run.main_async(SimpleNamespace(
        models=NAME, run_id=TRANSLATION_RUN, dataset=str(FOLDER / "dataset.jsonl"), pairs=None, limit=None))
    return int(summary["failed"] != 0)


def validate_rows(rows, dataset, frozen_at):
    expected = {r["id"]: r for r in dataset}
    assert len(rows) == len(expected) == len(dataset)
    assert {(r["model"], r["id"]) for r in rows} == {(NAME, i) for i in expected}
    for row in rows:
        assert row["timestamp"] >= frozen_at and row["request_attempt"] == 1
        if row.get("error") is None:
            assert row["reported_model"] == model()["model_id"]
            assert row["response_status"] == "completed"
            assert row["reported_reasoning"]["effort"] == "medium"
            assert row["reported_input_tokens"] == (
                row["tokens_in"] + row.get("cache_read_tokens", 0) + row.get("cache_write_tokens", 0))
            run._validate_result({"text": row["output_text"], **{k: row.get(k, 0) for k in (
                "tokens_in", "tokens_out", "cache_read_tokens", "cache_write_tokens")}})
        else:
            assert row.get("translation_error_details")


def translation_sources():
    saved = verify()
    i = saved["identity"]
    dataset = finqa.read_rows(FOLDER / "dataset.jsonl")
    assert len(dataset) == 3300 and finqa.digest(dataset) == i["translation_dataset_sha256"]
    assert read(FOLDER / "extension.json") == saved
    manifest = read(FOLDER / "manifest.json")
    assert manifest["run_id"] == TRANSLATION_RUN and len(manifest["executions"]) == 1
    e = manifest["executions"][0]
    assert all(manifest.get(k) == v for k, v in e.items())
    assert e["started_at"] >= saved["frozen_at"] and e.get("finished_at")
    assert e["dataset_sha256"] == i["translation_dataset_sha256"] and e["dataset_segments"] == 3300
    assert e["aws_region"] == i["aws_region"]
    assert e["generation_parameters"] == {"temperature": 0, "max_tokens": i["max_output_tokens"]}
    assert e["prompt_sha256"] == sha(run.PROMPT_PATH)[:12]
    assert e["rubric_sha256"] == sha(ROOT / "scenarios/translation/rubric.txt")[:12]
    assert len(e["models"]) == 1
    m = e["models"][0]
    for key, value in model().items():
        if key != "enabled":
            assert m.get(key) == value, key
    assert m["temperature_omitted"] and not m["thinking_disabled"]
    assert m["concurrency"] == i["translation_scenario"]["concurrency_default"]
    assert m["request_max_attempts"] == 1 and m["mantle_reasoning_effort"] is None
    rows = finqa.read_rows(FOLDER / "translations.jsonl")
    validate_rows(rows, dataset, saved["frozen_at"])
    expected = {r["id"]: r for r in dataset}
    for r in rows:
        assert all(r[k] == expected[r["id"]][k] for k in ("src_lang", "tgt_lang", "doc_type"))
    return saved, dataset, rows


def judge_identity():
    saved, _, _ = translation_sources()
    return {"translations_sha256": sha(FOLDER / "translations.jsonl"),
            "contract_sha256": sha(CONTRACT),
            "judges": saved["identity"]["translation_scenario"]["judges"]}


async def judge_translations():
    binding = judge_identity()
    path = FOLDER / "judge-input.json"
    if path.exists():
        assert read(path) == binding
    else:
        assert not (FOLDER / "judgments.jsonl").exists()
        finqa.write_json(path, binding)
    summary = await judge.main_async(SimpleNamespace(
        run_id=TRANSLATION_RUN, dataset=str(FOLDER / "dataset.jsonl"), limit=None, concurrency=8))
    return int(summary["failed"] != 0)


def capped(row):
    details = row.get("translation_error_details", {})
    return (row.get("finish_reason") in ("length", "max_tokens") or
            details.get("incomplete_reason") == "max_output_tokens")


def translation_report():
    saved, dataset, rows = translation_sources()
    assert read(FOLDER / "judge-input.json") == judge_identity()
    successful = [r for r in rows if r.get("error") is None]
    judgments = run.dedupe_latest(finqa.read_rows(FOLDER / "judgments.jsonl"), lambda r: (r["model"], r["id"]))
    assert {(r["model"], r["id"]) for r in judgments} == {(r["model"], r["id"]) for r in successful}
    assert all(r.get("error") is None and report.raw_judge_scores(r) is not None for r in judgments)
    cfg = run.load_config()
    new = report.build_report(TRANSLATION_RUN, cfg["scenario"]["translation"], cfg["models"], [FOLDER / "dataset.jsonl"])
    assert [m["name"] for m in new["models"]] == [NAME]
    a = new["models"][0]["aggregate"]
    assert a["segments"] == 3300 and a["translation_failures"] == 3300 - len(successful)
    assert all(a[k] == len(successful) for k in ("successful_translations", "judged_segments", "quality_eligible_segments"))
    new.update(measurement_contract=saved, measured_dataset_sha256=finqa.digest(dataset))
    new["models"][0]["collection_diagnostics"] = {
        "scheduled_inputs": 3300, "recorded_attempts": len(rows), "returned_outputs": len(successful),
        "unreturned_outputs": 3300 - len(successful), "capped_outputs": sum(capped(r) for r in rows),
        "capped_with_text": sum(capped(r) and r.get("error") is None for r in rows),
        "capped_without_text": sum(capped(r) and r.get("error") is not None for r in rows),
        "regenerated_attempts": 0, "all_input_quality_coverage": len(successful) / 3300,
        "error_types": dict(Counter(r["translation_error_details"]["type"] for r in rows if r.get("error"))),
        "failed_with_partial_text": sum(bool(r.get("failed_response", {}).get("output_text")) for r in rows if r.get("error")),
    }
    new["interpretation"] = (
        "GPT-6 Luna · us-east-1 Mantle · temperature 생략 · 기본 추론 medium · 출력 상한4096. "
        "최초3300회 결과와 실패를 보존했습니다. 품질은 채점 가능한 반환 출력 기준입니다. "
        "비용은 반환 성공 호출의 일반 입력·출력·캐시 읽기·쓰기 요금 추정치이며 실패 호출 청구액은 제외합니다.")
    return new


def translation_comparison(new):
    base = read(BASE_TRANSLATION)
    assert base["dataset"] == new["dataset"]
    result = copy.deepcopy(base)
    result["models"].append({**copy.deepcopy(new["models"][0]), "evaluation_cohort": "explicit", "source_report": TRANSLATION_RUN})
    incoming = {s["id"]: s for s in new["samples"]}
    assert set(incoming) == {s["id"] for s in result["samples"]}
    for sample in result["samples"]:
        other = incoming[sample["id"]]
        assert {k: v for k, v in sample.items() if k != "by_model"} == {k: v for k, v in other.items() if k != "by_model"}
        sample["by_model"][NAME] = copy.deepcopy(other["by_model"][NAME])
    result.update(run_id=COMPARISON, title="통합 벤치마크 결과 · 31개 모델",
                  comparison_note="기존30개 결과에 GPT-6 Luna 실측을 추가했습니다. 기존 지시27개와 명시적 지시4개는 프롬프트·측정 시점이 다릅니다.")
    result["cohorts"]["explicit"] = "명시적 번역 지시 · Grok·Kimi·GPT-6 Luna 4개 모델"
    result["source_reports"].append({
        "run_id": TRANSLATION_RUN, "cohort": "explicit",
        "report_sha256": sha(report.DOCS_RESULTS_DIR / f"{TRANSLATION_RUN}.json"),
        "prompt_sha256": new["manifest"]["prompt_sha256"], "rubric_sha256": new["manifest"]["rubric_sha256"],
        "dataset_sha256": new["measured_dataset_sha256"],
    })
    result["extension_contract"] = new["measurement_contract"]
    result["interpretation"] = base.get("interpretation", "") + "\n\n" + new["interpretation"]
    assert result["models"][:-1] == base["models"]
    return result


def qa_report():
    saved = verify()
    folder = finqa.RESULTS / QA_RUN
    manifest, dataset, predictions = finqa.load_run(folder)
    c, i = manifest["contract"], saved["identity"]
    assert manifest["run_id"] == QA_RUN and len(manifest["executions"]) == 1
    assert manifest["executions"][0].get("finished_at") and manifest["executions"][0]["started_at"] >= saved["frozen_at"]
    assert dataset == finqa.read_rows(qa.DATASET) and len(dataset) == 20
    assert c["evaluation_protocol"] == saved and c["models"] == [model()]
    assert c["dataset_sha256"] == i["qa_dataset_sha256"]
    assert c["runner_sha256"] == sha(run.__file__) and c["finqa_sha256"] == sha(finqa.__file__)
    assert c["prompt_sha256"] == sha(qa.SCENARIO / "prompt.txt") == sha(folder / "prompt.txt")
    for field in ("aws_region", "max_output_tokens", "temperature", "temperature_omitted_model_ids", "request_timeout_s"):
        assert c[field] == i[field], field
    assert c["scenario"] == "finqa_audited" and c["concurrency_default"] == i["qa_scenario"]["concurrency_default"]
    rows = finqa.read_rows(folder / "answers.jsonl")
    validate_rows(rows, dataset, saved["frozen_at"])
    evaluations = []
    for record in dataset:
        raw = predictions[(NAME, record["id"])]
        evaluations.append({
            "model": NAME, "id": record["id"], "question": record["question"], "output_text": raw.get("output_text"),
            "gold_answer": record["gold_answer"], "reference_answer": record["reference_answer"],
            "reference_program": record["reference_program"], **qa.evaluate_one(record, raw)})
    a = finqa.summarize(evaluations)
    a.update(finqa_compare.performance_of(rows, model()))
    a.update(
        strict_correct=sum(e["strict_correct"] for e in evaluations),
        format_adjusted=sum(bool(e["normalizations"]) for e in evaluations),
        execution_accuracy_ci95=qa.wilson(a["correct"], 20),
        program_valid=sum(e["program_valid"] for e in evaluations),
        unit_valid=sum(e["unit_valid"] for e in evaluations),
        requested_unit_compliant=sum(e["requested_unit_compliant"] for e in evaluations),
        unit_errors=sum(e.get("evaluation_error_code") in {"invalid_unit", "incompatible_unit"} for e in evaluations),
        truncated=sum(e.get("evaluation_error_code") == "truncated" for e in evaluations),
        cache_read_tokens=sum(r.get("cache_read_tokens", 0) for r in rows if not r.get("error")),
        cache_write_tokens=sum(r.get("cache_write_tokens", 0) for r in rows if not r.get("error")))
    base = read(BASE_QA)
    result = copy.deepcopy(base)
    result.update(run_id=QA_RUN, parent_run_id=base["run_id"], extension_contract=saved)
    result["models"].append({
        "name": NAME, "provider": "bedrock", "aggregate": a,
        "status": "incomplete" if a["request_failed"] else "complete",
        "run_config": model(), "source_run_id": QA_RUN, "pricing_valid_until": None, "serving_config": None,
        "request_settings": {"temperature": "omitted/provider default", "reasoning_effort": i["reasoning"],
                             "chat_template_kwargs": None, "max_output_tokens": i["max_output_tokens"],
                             "concurrency": c["concurrency_default"]}})
    result["evaluations"].extend(evaluations)
    result["warnings"].insert(0, "기존29개 모델의 점수·비용은 보존하고 GPT-6 Luna만 동일20문항·프롬프트·채점기로 추가 측정했습니다. 측정 시점·호출 코드·단가는 다릅니다.")
    result["warnings"].insert(1, "GPT-6 Luna 비용은 상용 지역 처리 단가(일반 표준 단가+10%)로 캐시 읽기·쓰기를 구분한 추정치입니다.")
    result["source_runs"].append({
        "run_id": QA_RUN, "manifest_sha256": finqa.digest(manifest),
        "answers_sha256": finqa.digest(list(predictions.values())), "dataset_sha256": c["dataset_sha256"],
        "started_at": manifest["executions"][0]["started_at"], "finished_at": manifest["executions"][0]["finished_at"]})
    assert result["models"][:-1] == base["models"] and result["evaluations"][:-20] == base["evaluations"]
    return result


def publish_qa(result):
    # The historical audited writer hardcodes 28 models; keep it frozen.
    esc = lambda value: html.escape(str(value))
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>감사된 금융 QA · GPT-6 Luna 추가</title><style>body{font:18px/1.6 system-ui;margin:2rem;overflow-wrap:anywhere}table{border-collapse:collapse;white-space:nowrap}td,th{padding:.6rem;border:1px solid #ccc}pre{white-space:pre-wrap}.scroll{overflow:auto}</style><a href="../finqa.html">금융 QA 대시보드</a><h1>감사된 금융 QA · GPT-6 Luna 추가</h1>'
    page += f'<p>{len(result["models"])}개 모델 · 동일20문항</p>'
    page += "".join(f"<p>{esc(w)}</p>" for w in result["warnings"])
    page += "<div class=scroll><table><tr><th>모델</th><th>정답</th><th>정답률</th><th>비용/문항</th></tr>"
    for m in sorted(result["models"], key=lambda m: (-m["aggregate"]["execution_accuracy"], m["name"])):
        a = m["aggregate"]
        cost = a["estimated_cost_per_question_usd"]
        page += "<tr>" + "".join(f"<td>{esc(v)}</td>" for v in (m["name"], f'{a["correct"]}/20',
            f'{a["execution_accuracy"]:.1%}', f"${cost:.5f}" if cost is not None else "—")) + "</tr>"
    page += "</table></div>"
    for m in result["models"]:
        page += f'<details><summary>{esc(m["name"])} · 원본·판정·설정</summary><pre>'
        page += esc(json.dumps(m, ensure_ascii=False, indent=2)) + "</pre>"
        for e in result["evaluations"]:
            if e["model"] == m["name"]:
                page += "<pre>" + esc(json.dumps(e, ensure_ascii=False, indent=2)) + "</pre>"
        page += "</details>"
    page += "<details><summary>평가 규약</summary><pre>" + esc(result["policy"]) + "</pre></details></html>"
    finqa.write_json(finqa.REPORTS / f"{QA_RUN}.json", result)
    (finqa.REPORTS / f"{QA_RUN}.html").write_text(page)
    index_path = finqa.REPORTS / "index.json"
    index = read(index_path)
    index["runs"] = [{"id": QA_RUN, "label": "GPT-6 Luna 추가 · 감사된 금융 QA · 30개 모델"}] + [r for r in index["runs"] if r["id"] != QA_RUN]
    index["latest"] = QA_RUN
    finqa.write_json(index_path, index)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["freeze", "run-qa", "run-translation", "judge", "report-qa", "report-translation", "verify"])
    args = p.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command.startswith("run-"):
        raise SystemExit(asyncio.run(measure(args.command[4:])))
    elif args.command == "judge":
        raise SystemExit(asyncio.run(judge_translations()))
    elif args.command == "report-qa":
        publish_qa(qa_report())
    elif args.command == "report-translation":
        new = translation_report()
        report.write_report(new)
        report.write_report(translation_comparison(new))
    else:
        verify()
        print("Pre-call contract and 560 historical judgments verified")


if __name__ == "__main__":
    main()
