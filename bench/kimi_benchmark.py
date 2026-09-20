"""Add Kimi measurements to retained translation and audited-QA snapshots.

The 2026-09-19 QA freeze is never rewritten. Its evaluator/data remain byte
identical; a new extension contract records the new collector and candidate.
Historical transport reproduction still requires the original Git revision.
"""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
from types import SimpleNamespace

from bench import finqa, finqa_audited as qa, finqa_compare, report, run, judge

NAME = "kimi-k3"
BASE_QA = "finqa-audited-20260919"
QA_RUN = "finqa-kimi-k3-20260920"
BASE_TRANSLATION = "integrated-2026-09-17"
TRANSLATION_RUN = "bedrock-kimi-k3-20260920"
TRANSLATION_COMPARISON = "integrated-2026-09-20"
CONTRACT = finqa.ROOT / "validation/kimi-k3/qa-extension.json"
TRANSLATION_SOURCE = finqa.ROOT / "results/grok-explicit-2026-09-16/dataset.jsonl"


def translation_folder():
    return run.RESULTS_DIR/TRANSLATION_RUN


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_config():
    return next(m for m in run.load_config()["models"] if m["name"] == NAME)


def verify_parent():
    """Verify retained artifacts and unchanged grading, without rewriting a freeze."""
    frozen = json.loads(qa.FREEZE.read_text())
    p = frozen["protocol"]
    for path, key in (
        (qa.DATASET, None), (qa.SCENARIO/"prompt.txt", "prompt_sha256"),
        (qa.__file__, "evaluator_sha256"), (finqa.__file__, "dsl_sha256"),
        (finqa_compare.__file__, "normalizer_sha256"),
        (qa.SCENARIO/"selection-audit.json", "selection_audit_sha256"),
        (qa.SCENARIO/"dataset-review.md", "dataset_review_sha256"),
    ):
        if key and sha(path) != p[key]:
            raise ValueError(f"parent grading artifact changed: {path}")
    data = finqa.read_rows(qa.DATASET)
    if finqa.digest(data) != p["dataset_sha256"]:
        raise ValueError("parent dataset changed")
    base = json.loads((finqa.REPORTS/f"{BASE_QA}.json").read_text())
    proof = json.loads((qa.SCENARIO/"result-verification.json").read_text())
    if sha(finqa.REPORTS/f"{BASE_QA}.json") != proof["report_sha256"]:
        raise ValueError("parent report differs from its retained verification")
    if base["protocol_freeze"] != frozen or len(base["models"]) != 28 or len(base["evaluations"]) != 560:
        raise ValueError("not the retained 28-model parent")
    if [m["name"] for m in base["models"]] != [m["name"] for m in p["models"]]:
        raise ValueError("parent roster differs")
    for model in base["models"]:
        folder = finqa.RESULTS/model["source_run_id"]
        manifest, records, predictions = finqa.load_run(folder)
        if records != data or manifest["contract"]["evaluation_protocol"] != frozen:
            raise ValueError("parent source differs")
        if sha(folder/"prompt.txt") != p["prompt_sha256"]:
            raise ValueError("parent prompt differs")
        for record in records:
            raw = predictions[(model["name"], record["id"])]
            evaluated = qa.evaluate_one(record, raw)
            stored = next(e for e in base["evaluations"] if e["model"] == model["name"] and e["id"] == record["id"])
            if any(stored[key] != value for key, value in evaluated.items()):
                raise ValueError("parent result no longer reproduces under its unchanged grader")
    return base, data, frozen


def extension_identity():
    base, records, frozen = verify_parent()
    cfg = run.load_config()
    return {
        "kind": "single-model audited-QA extension", "model": model_config(),
        "parent_report_sha256": sha(finqa.REPORTS/f"{BASE_QA}.json"),
        "parent_freeze_sha256": sha(qa.FREEZE),
        "dataset_sha256": finqa.digest(records),
        "prompt_sha256": frozen["protocol"]["prompt_sha256"],
        "evaluator_sha256": sha(qa.__file__), "dsl_sha256": sha(finqa.__file__),
        "normalizer_sha256": sha(finqa_compare.__file__),
        "collector_sha256": sha(run.__file__), "extension_sha256": sha(__file__),
        "cost_code_sha256": sha(report.__file__),
        "aws_region": cfg["aws"]["region"],
        "concurrency_default": cfg["scenario"]["finqa_audited"]["concurrency_default"],
        "max_output_tokens": run.MAX_OUTPUT_TOKENS,
        "scenario": "finqa_audited", "temperature": 0, "request_timeout_s": run.REQUEST_TIMEOUT_S,
        "temperature_omitted_model_ids": sorted(run.MANTLE_NO_TEMPERATURE | run.BEDROCK_NO_TEMPERATURE),
        "translation_dataset_sha256": finqa.digest(finqa.read_rows(TRANSLATION_SOURCE)),
        "translation_prompt_sha256": sha(run.PROMPT_PATH),
        "translation_rubric_sha256": sha(finqa.ROOT/"scenarios/translation/rubric.txt"),
        "translation_scenario": cfg["scenario"]["translation"],
        "judge_code_sha256": sha(judge.__file__),
    }


def freeze():
    identity = extension_identity()
    if CONTRACT.exists():
        if json.loads(CONTRACT.read_text())["identity"] != identity:
            raise ValueError("extension changed; do not reuse its contract/run")
    else:
        finqa.write_json(CONTRACT, {"frozen_at": datetime.now(timezone.utc).isoformat(), "identity": identity})
    dataset = translation_folder()/"dataset.jsonl"
    if dataset.exists():
        if finqa.digest(finqa.read_rows(dataset)) != identity["translation_dataset_sha256"]:
            raise ValueError("translation snapshot changed")
    else:
        if (translation_folder()/"translations.jsonl").exists():
            raise ValueError("translations without a frozen dataset")
        finqa.write_rows(dataset, finqa.read_rows(TRANSLATION_SOURCE))


def verify_contract():
    saved = json.loads(CONTRACT.read_text())
    if saved["identity"] != extension_identity():
        raise ValueError("extension no longer matches pre-call contract")
    return saved


async def measure_qa():
    saved = verify_contract()
    directory = finqa.run_directory(QA_RUN)
    directory.mkdir(parents=True, exist_ok=True)
    args = SimpleNamespace(models=NAME, run_id=QA_RUN, dataset=qa.DATASET, limit=None)
    with finqa.locked(directory):
        return await finqa.run_candidates(args, directory, scenario_name="finqa_audited", extra_contract=saved)


async def measure_translation():
    saved = verify_contract()
    folder = translation_folder()
    dataset = folder/"dataset.jsonl"
    if finqa.digest(finqa.read_rows(dataset)) != saved["identity"]["translation_dataset_sha256"]:
        raise ValueError("translation dataset snapshot changed")
    receipt = folder/"extension.json"
    if receipt.exists() and json.loads(receipt.read_text()) != saved:
        raise ValueError("translation extension receipt changed")
    finqa.write_json(receipt, saved)  # before candidate calls
    args = SimpleNamespace(models=NAME, run_id=TRANSLATION_RUN, dataset=str(dataset), pairs=None, limit=None)
    summary = await run.main_async(args)
    return int(summary["failed"] != 0)


def verify_translation_sources(require_judgments=True):
    saved = verify_contract()
    identity = saved["identity"]
    folder = translation_folder()
    dataset = finqa.read_rows(folder/"dataset.jsonl")
    expected = {r["id"]: r for r in finqa.read_rows(TRANSLATION_SOURCE)}
    if (len(dataset) != 3300 or len(expected) != 3300 or
            finqa.digest(dataset) != identity["translation_dataset_sha256"] or
            {r["id"]: r for r in dataset} != expected):
        raise ValueError("translation full dataset identity/coverage differs")
    if json.loads((folder/"extension.json").read_text()) != saved:
        raise ValueError("translation missing or different pre-call receipt")
    manifest = json.loads((folder/"manifest.json").read_text())
    if manifest["run_id"] != TRANSLATION_RUN:
        raise ValueError("translation run ID mismatch")
    if not manifest.get("executions") or any(manifest.get(k) != v for k, v in manifest["executions"][-1].items()):
        raise ValueError("translation top-level manifest differs from its last execution")
    m = identity["model"]
    for execution in manifest["executions"]:
        if execution["started_at"] < saved["frozen_at"] or execution["dataset_segments"] != len(expected):
            raise ValueError("translation execution predates freeze or has different coverage")
        if execution["dataset_sha256"] != identity["translation_dataset_sha256"] or execution["aws_region"] != identity["aws_region"]:
            raise ValueError("translation input content or region differs")
        if execution["generation_parameters"] != {"temperature": 0, "max_tokens": identity["max_output_tokens"]}:
            raise ValueError("translation generation settings differ")
        if execution["prompt_sha256"] != identity["translation_prompt_sha256"][:12] or execution["rubric_sha256"] != identity["translation_rubric_sha256"][:12]:
            raise ValueError("translation prompt/rubric differs")
        if len(execution["models"]) != 1:
            raise ValueError("translation execution contains unexpected models")
        observed = execution["models"][0]
        for key in ("name", "api", "model_id", "price_in", "price_out", "price_cache_read", "price_cache_write"):
            if observed[key] != m[key]:
                raise ValueError(f"translation model {key} differs")
        if observed["concurrency"] != m.get("concurrency", identity["translation_scenario"]["concurrency_default"]):
            raise ValueError("translation concurrency differs")
        if not observed["temperature_omitted"] or observed["thinking_disabled"]:
            raise ValueError("translation effective decoding differs")
        if observed["request_max_attempts"] != m.get("request_max_attempts", 1):
            raise ValueError("translation retry settings differ")
        if observed.get("bedrock_reasoning_effort") != m.get("bedrock_reasoning_effort"):
            raise ValueError("translation reasoning setting differs")
    rows = run.dedupe_latest(finqa.read_rows(folder/"translations.jsonl"), lambda r: (r["model"], r["id"]))
    if len(rows) != len(expected) or {(r["model"], r["id"]) for r in rows} != {(NAME, key) for key in expected}:
        raise ValueError("translation actual coverage incomplete or unexpected")
    for row in rows:
        if row.get("error") is not None or not row.get("output_text"):
            raise ValueError("translation has unresolved request failures")
        if row["timestamp"] < saved["frozen_at"]:
            raise ValueError("translation observation predates contract")
        for key in ("src_lang", "tgt_lang", "doc_type"):
            if row[key] != expected[row["id"]][key]:
                raise ValueError("translation observation metadata differs from full dataset")
    if require_judgments:
        receipt = json.loads((folder/"judge-input.json").read_text())
        if receipt != judge_identity(saved):
            raise ValueError("judge input/configuration binding differs")
        judgments = run.dedupe_latest(finqa.read_rows(folder/"judgments.jsonl"), lambda r: (r["model"], r["id"]))
        if len(judgments) != len(expected) or {(r["model"], r["id"]) for r in judgments} != {(NAME, key) for key in expected}:
            raise ValueError("judgment coverage incomplete")
        if any(r.get("error") is not None or report.raw_judge_scores(r) is None for r in judgments):
            raise ValueError("judgment errors or missing independent scores")
    return dataset


def judge_identity(saved):
    return {"translations_sha256": sha(translation_folder()/"translations.jsonl"),
            "dataset_sha256": saved["identity"]["translation_dataset_sha256"],
            "rubric_sha256": saved["identity"]["translation_rubric_sha256"],
            "judge_code_sha256": saved["identity"]["judge_code_sha256"],
            "judges": saved["identity"]["translation_scenario"]["judges"]}


async def judge_translation():
    saved = verify_contract()
    verify_translation_sources(require_judgments=False)
    path = translation_folder()/"judge-input.json"
    identity = judge_identity(saved)
    if path.exists() and json.loads(path.read_text()) != identity:
        raise ValueError("cannot reuse judgments after candidate text/settings changed")
    if not path.exists() and (translation_folder()/"judgments.jsonl").exists():
        raise ValueError("unbound pre-existing judgments")
    finqa.write_json(path, identity)
    args = SimpleNamespace(run_id=TRANSLATION_RUN, dataset=str(translation_folder()/"dataset.jsonl"),
                           limit=None, concurrency=8)
    summary = await judge.main_async(args)
    return int(summary["failed"] != 0)


def build_translation_report():
    dataset = verify_translation_sources()
    cfg = run.load_config()
    result = report.build_report(TRANSLATION_RUN, cfg["scenario"]["translation"], cfg["models"],
                                 [translation_folder()/"dataset.jsonl"])
    if [m["name"] for m in result["models"]] != [NAME]:
        raise ValueError("unexpected translation models")
    a = result["models"][0]["aggregate"]
    if any(a[key] != len(dataset) for key in ("segments", "successful_translations", "judged_segments", "quality_eligible_segments")):
        raise ValueError("translation generation/judgment metrics incomplete")
    result["measurement_contract"] = verify_contract()
    result["measured_dataset_sha256"] = finqa.digest(dataset)
    return result


def qa_comparison():
    saved = verify_contract()
    base, records, frozen = verify_parent()
    folder = finqa.RESULTS/QA_RUN
    manifest, measured, predictions = finqa.load_run(folder)
    c = manifest["contract"]
    if (c["evaluation_protocol"] != saved or measured != records or c["models"] != [model_config()]
            or c["dataset_sha256"] != saved["identity"]["dataset_sha256"]
            or c["runner_sha256"] != saved["identity"]["collector_sha256"]
            or sha(folder/"prompt.txt") != saved["identity"]["prompt_sha256"]
            or manifest["executions"][0]["started_at"] < saved["frozen_at"]):
        raise ValueError("Kimi measured source differs from its pre-call contract")
    for field in ("aws_region", "concurrency_default", "max_output_tokens", "temperature_omitted_model_ids",
                  "temperature", "request_timeout_s", "scenario"):
        if c[field] != saved["identity"][field]:
            raise ValueError(f"Kimi run {field} differs from its contract")
    if c["finqa_sha256"] != saved["identity"]["dsl_sha256"] or c["prompt_sha256"] != saved["identity"]["prompt_sha256"]:
        raise ValueError("Kimi run grading/input code differs")
    if manifest["run_id"] != QA_RUN:
        raise ValueError("Kimi QA run ID differs")
    evaluations = []
    raw_rows = []
    for record in records:
        raw = predictions.get((NAME, record["id"]))
        score = qa.evaluate_one(record, raw)
        evaluations.append({
            "model": NAME, "id": record["id"], "question": record["question"],
            "output_text": raw.get("output_text") if raw else None,
            "gold_answer": record["gold_answer"], "reference_answer": record["reference_answer"],
            "reference_program": record["reference_program"], **score,
        })
        if raw is not None:
            raw_rows.append(raw)
    aggregate = finqa.summarize(evaluations)
    aggregate.update(finqa_compare.performance_of(raw_rows, c["models"][0], len(manifest["executions"])))
    aggregate.update(
        strict_correct=sum(e["strict_correct"] for e in evaluations),
        format_adjusted=sum(bool(e["normalizations"]) for e in evaluations),
        execution_accuracy_ci95=qa.wilson(aggregate["correct"], len(records)),
        program_valid=sum(e["program_valid"] for e in evaluations),
        unit_valid=sum(e["unit_valid"] for e in evaluations),
        requested_unit_compliant=sum(e["requested_unit_compliant"] for e in evaluations),
        unit_errors=sum(e.get("evaluation_error_code") in {"invalid_unit", "incompatible_unit"} for e in evaluations),
        truncated=sum(e.get("evaluation_error_code") == "truncated" for e in evaluations),
        cache_read_tokens=sum(r.get("cache_read_tokens", 0) for r in raw_rows if r.get("error") is None),
        cache_write_tokens=sum(r.get("cache_write_tokens", 0) for r in raw_rows if r.get("error") is None),
    )
    if aggregate["request_failed"] or aggregate["missing"]:
        aggregate.update(estimated_cost_usd=None, estimated_cost_per_question_usd=None,
                         cost_unavailable_reason="incomplete_responses")
    kimi = {
        "name": NAME, "provider": "bedrock", "aggregate": aggregate,
        "status": "incomplete" if aggregate["request_failed"] or aggregate["missing"] else "complete",
        "run_config": c["models"][0], "source_run_id": QA_RUN,
        "pricing_valid_until": None, "serving_config": None,
        "request_settings": {"temperature": "omitted/provider default",
                             "reasoning_effort": "omitted/provider default; reasoningContent observed in preflight",
                             "chat_template_kwargs": None, "max_output_tokens": c["max_output_tokens"],
                             "concurrency": c["concurrency_default"]},
    }
    result = copy.deepcopy(base)
    result.update(run_id=QA_RUN, parent_run_id=BASE_QA, extension_contract=saved)
    result["parent_protocol_freeze"] = result.pop("protocol_freeze")
    result["parent_generation_parameters"] = result.pop("generation_parameters")
    result["models"].append(kimi)
    result["evaluations"].extend(evaluations)
    result["warnings"].insert(0, "이전 28개 모델의 결과를 보존하고 Kimi K3만 같은 20문항·프롬프트·채점기로 추가 측정했습니다. 측정 시점과 호출 코드 버전은 다릅니다.")
    result["source_runs"].append({
        "run_id": QA_RUN, "manifest_sha256": finqa.digest(manifest),
        "answers_sha256": finqa.digest(list(predictions.values())),
        "dataset_sha256": c["dataset_sha256"],
        "started_at": manifest["executions"][0]["started_at"],
        "finished_at": manifest["executions"][-1].get("finished_at"),
    })
    assert result["models"][:-1] == base["models"] and result["evaluations"][:-20] == base["evaluations"]
    return result


def publish_qa(result):
    """Render the extension with dynamic counts; do not alter the frozen writer."""
    escaped = lambda x: html.escape(str(x))
    page = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>금융 QA · Kimi K3 추가 비교</title><style>body{font:18px/1.6 system-ui;margin:2rem;overflow-wrap:anywhere}table{border-collapse:collapse;white-space:nowrap}th,td{padding:.7rem;border:1px solid #ccc}.scroll{overflow:auto}pre{white-space:pre-wrap}</style>
<a href="../finqa.html">금융 QA 대시보드</a><h1>금융 QA · Kimi K3 추가 비교</h1>"""
    page += f'<p>{len(result["models"])}개 모델 · 동일 20문항 · 기존 28개 결과 보존</p>'
    page += "".join(f"<p>{escaped(w)}</p>" for w in result["warnings"])
    page += "<p>Kimi 비용은 일반 입력·출력과 실제 캐시 읽기·쓰기 토큰의 표준 단가를 합산한 추정치입니다.</p>"
    page += "<div class=scroll><table><tr><th>모델</th><th>정답</th><th>정답률</th><th>추정 비용/문항</th><th>잘림</th></tr>"
    for model in sorted(result["models"], key=lambda m: (-m["aggregate"]["execution_accuracy"], m["name"])):
        a = model["aggregate"]
        cost = a["estimated_cost_per_question_usd"]
        page += "<tr>" + "".join(f"<td>{escaped(v)}</td>" for v in (
            model["name"], f'{a["correct"]}/20', f'{a["execution_accuracy"]:.1%}',
            f"${cost:.5f}" if cost is not None else "—", a.get("truncated", 0))) + "</tr>"
    page += "</table></div>"
    for model in result["models"]:
        page += f'<details><summary>{escaped(model["name"])} · 원본·판정·설정</summary><pre>'
        page += escaped(json.dumps(model, ensure_ascii=False, indent=2)) + "</pre>"
        for row in result["evaluations"]:
            if row["model"] == model["name"]:
                page += "<pre>" + escaped(json.dumps(row, ensure_ascii=False, indent=2)) + "</pre>"
        page += "</details>"
    page += "<details><summary>평가 규약</summary><pre>" + escaped(result["policy"]) + "</pre></details></html>"
    finqa.write_json(finqa.REPORTS/f"{QA_RUN}.json", result)
    (finqa.REPORTS/f"{QA_RUN}.html").write_text(page)
    index_path = finqa.REPORTS/"index.json"
    index = json.loads(index_path.read_text())
    index["runs"] = [{"id": QA_RUN, "label": "Kimi K3 추가 · 감사된 금융 QA · 29개 모델"}] + [
        r for r in index["runs"] if r["id"] != QA_RUN]
    index["latest"] = QA_RUN
    finqa.write_json(index_path, index)


def translation_comparison():
    base_path = report.DOCS_RESULTS_DIR/f"{BASE_TRANSLATION}.json"
    new_path = report.DOCS_RESULTS_DIR/f"{TRANSLATION_RUN}.json"
    base, new = (json.loads(p.read_text()) for p in (base_path, new_path))
    if new.get("run_id") != TRANSLATION_RUN or new != build_translation_report():
        raise ValueError("translation report does not reproduce from complete frozen sources")
    return append_translation(base, new, sha(new_path))


def append_translation(base, new, report_sha):
    if base["dataset"] != new["dataset"] or [m["name"] for m in new["models"]] != [NAME]:
        raise ValueError("translation dataset/model coverage differs")
    original = next(r for r in base["source_reports"] if r["cohort"] == "original")
    if (new["manifest"]["prompt_sha256"] != original["prompt_sha256"] or
            new["manifest"]["rubric_sha256"] != original["rubric_sha256"]):
        raise ValueError("translation prompt/rubric differs from original cohort")
    result = copy.deepcopy(base)
    kimi = copy.deepcopy(new["models"][0])
    kimi.update(evaluation_cohort="original", source_report=TRANSLATION_RUN)
    result["models"].append(kimi)
    new_samples = {s["id"]: s for s in new["samples"]}
    if len(new_samples) != len(base["samples"]):
        raise ValueError("sample coverage differs")
    for sample in result["samples"]:
        incoming = new_samples[sample["id"]]
        if {k: v for k, v in sample.items() if k != "by_model"} != {k: v for k, v in incoming.items() if k != "by_model"}:
            raise ValueError("sample metadata differs")
        sample["by_model"][NAME] = copy.deepcopy(incoming["by_model"][NAME])
    result.update(run_id=TRANSLATION_COMPARISON, title="통합 벤치마크 결과 · 30개 모델",
                  comparison_note="기존 29개 결과를 보존하고 Kimi K3의 추가 실측을 합쳤습니다. 기존 번역 지시 28개 모델과 명시적 지시 Grok 2개 모델은 지시가 다르며, 측정 시점도 다릅니다.")
    result["cohorts"]["original"] = "기존 번역 지시 · Kimi 포함 28개 모델"
    result["source_reports"].append({
        "run_id": TRANSLATION_RUN, "cohort": "original",
        "report_sha256": report_sha,
        "prompt_sha256": new["manifest"]["prompt_sha256"],
        "rubric_sha256": new["manifest"]["rubric_sha256"],
        "dataset_sha256": new.get("measured_dataset_sha256"),
    })
    result["interpretation"] = (
        "Kimi K3는 us.moonshotai.kimi-k3, US 표준 요금으로 측정했습니다. temperature 미지원으로 생략하며 추론은 제공자 기본값입니다. "
        "캐시 읽기·쓰기 토큰을 구분해 비용에 반영합니다. 이전 모델의 점수·비용은 재계산하지 않았습니다.")
    assert result["models"][:-1] == base["models"]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["freeze", "run-qa", "run-translation", "judge-translation",
                                      "report-qa", "report-translation", "verify-parent", "selfcheck"])
    args = p.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command == "run-qa":
        raise SystemExit(asyncio.run(measure_qa()))
    elif args.command == "report-qa":
        publish_qa(qa_comparison())
    elif args.command == "run-translation":
        raise SystemExit(asyncio.run(measure_translation()))
    elif args.command == "judge-translation":
        raise SystemExit(asyncio.run(judge_translation()))
    elif args.command == "report-translation":
        report.write_report(build_translation_report())
        print(report.write_report(translation_comparison()))
    elif args.command == "verify-parent":
        verify_parent()
        print("All 560 historical judgments reproduce; frozen grading/data artifacts unchanged")
    else:
        selfcheck()


def selfcheck():
    from tempfile import TemporaryDirectory
    from unittest.mock import AsyncMock, patch
    import sys
    module = sys.modules[__name__]
    base, records, frozen = verify_parent()
    by_question = {r["question"]: r for r in records}
    async def candidate(client, model_id, prompt, reasoning_effort=None):
        assert model_id == model_config()["model_id"]
        d = json.loads(prompt.split("\nDOCUMENT:\n", 1)[1])
        assert set(d) == {"question", "pre_text", "post_text", "table"}
        record = by_question[d["question"]]
        return {"text": json.dumps({"program": record["reference_program"], "unit": record["audit"]["canonical_unit"]}),
                "tokens_in": 10, "tokens_out": 20, "cache_read_tokens": 30, "cache_write_tokens": 40,
                "finish_reason": "end_turn"}
    with TemporaryDirectory() as directory:
        temporary = Path(directory)
        # Parent verification is exercised above; the mock isolates new-run I/O.
        with patch.object(module, "CONTRACT", temporary/"extension.json"), \
             patch.object(module, "verify_parent", return_value=(base, records, frozen)), \
             patch.object(finqa, "RESULTS", temporary/"runs"), \
             patch.object(run, "RESULTS_DIR", temporary/"translation-runs"), \
             patch.object(report, "RESULTS_DIR", temporary/"translation-runs"):
            freeze()
            with patch.object(run, "make_client", return_value=object()), \
                 patch.object(run, "call_bedrock", new=candidate):
                assert asyncio.run(measure_qa()) == 0
            result = qa_comparison()
            assert len(result["models"]) == 29 and len(result["evaluations"]) == 580
            assert result["models"][:-1] == base["models"]
            assert result["evaluations"][:-20] == base["evaluations"]
            a = result["models"][-1]["aggregate"]
            assert a["correct"] == 20 and a["cache_read_tokens"] == 600 and a["cache_write_tokens"] == 800
            # Twenty requests: (10*3.3+20*16.5+30*.33+40*4.125)*20/1M = .010758.
            assert a["estimated_cost_usd"] == .0108
            folder = finqa.RESULTS/QA_RUN
            original = json.loads((folder/"manifest.json").read_text())
            for field in ("max_output_tokens", "aws_region", "concurrency_default", "finqa_sha256",
                          "temperature", "request_timeout_s", "scenario"):
                bad = copy.deepcopy(original)
                bad["contract"][field] = 7 if field in ("max_output_tokens", "concurrency_default", "temperature", "request_timeout_s") else "wrong"
                finqa.write_json(folder/"manifest.json", bad)
                try:
                    qa_comparison()
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"accepted changed {field}")
            finqa.write_json(folder/"manifest.json", original)
            # Full 3300-ID fixture validates actual source coverage, not the
            # 210 display samples. It never calls models or writes public data.
            data = finqa.read_rows(TRANSLATION_SOURCE)
            cfg = run.load_config()
            translation_dir = translation_folder()
            finqa.write_json(translation_dir/"extension.json", json.loads(CONTRACT.read_text()))
            run.write_manifest(TRANSLATION_RUN, cfg, cfg["scenario"]["translation"], [model_config()], data,
                               datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            translations = [{
                "id": r["id"], "model": NAME, "src_lang": r["src_lang"], "tgt_lang": r["tgt_lang"],
                "doc_type": r["doc_type"], "output_text": "fixture", "error": None,
                "tokens_in": 1, "tokens_out": 1, "timestamp": datetime.now(timezone.utc).isoformat(), "latency_s": 1,
            } for r in data]
            finqa.write_rows(translation_dir/"translations.jsonl", translations)
            assert len(verify_translation_sources(require_judgments=False)) == 3300
            finqa.write_rows(translation_dir/"translations.jsonl", translations[:1])
            try:
                verify_translation_sources(require_judgments=False)
            except ValueError:
                pass
            else:
                raise AssertionError("configured 3300 metadata accepted actual one-row source")
            finqa.write_rows(translation_dir/"translations.jsonl", translations)
            tm = json.loads((translation_dir/"manifest.json").read_text())
            bad_model = copy.deepcopy(tm)
            bad_model["executions"][0]["models"][0]["model_id"] = "not-kimi"
            finqa.write_json(translation_dir/"manifest.json", bad_model)
            try:
                verify_translation_sources(require_judgments=False)
            except ValueError:
                pass
            else:
                raise AssertionError("wrong actual model accepted")
            finqa.write_json(translation_dir/"manifest.json", tm)
            finqa.write_json(translation_dir/"judge-input.json", judge_identity(json.loads(CONTRACT.read_text())))
            judgments = []
            for row in translations:
                j = {"id": row["id"], "model": NAME, "error": None, "judges_used": ["sol", "fable-5"]}
                for axis in [*report.AXES, "overall"]:
                    j[axis] = 4
                    j["sol_"+axis] = 4
                    j["fable-5_"+axis] = 4
                judgments.append(j)
            finqa.write_rows(translation_dir/"judgments.jsonl", judgments)
            assert len(verify_translation_sources()) == 3300
            # A stale judgment receipt cannot validate a changed candidate text.
            translations[0]["output_text"] = "changed"
            finqa.write_rows(translation_dir/"translations.jsonl", translations)
            try:
                verify_translation_sources()
            except ValueError:
                pass
            else:
                raise AssertionError("judgment receipt accepted changed translation text")
            bad = json.loads(CONTRACT.read_text())
            bad["identity"]["model"]["model_id"] = "wrong"
            finqa.write_json(CONTRACT, bad)
            try:
                verify_contract()
            except ValueError:
                pass
            else:
                raise AssertionError("changed extension accepted")
        original_translation = json.loads((report.DOCS_RESULTS_DIR/f"{BASE_TRANSLATION}.json").read_text())
        origin = next(r for r in original_translation["source_reports"] if r["cohort"] == "original")
        source_name = original_translation["models"][0]["name"]
        added = {
            "dataset": copy.deepcopy(original_translation["dataset"]),
            "manifest": {"prompt_sha256": origin["prompt_sha256"], "rubric_sha256": origin["rubric_sha256"]},
            "models": [{**copy.deepcopy(original_translation["models"][0]), "name": NAME}],
            "samples": [{**copy.deepcopy(s), "by_model": {NAME: copy.deepcopy(s["by_model"][source_name])}}
                        for s in original_translation["samples"]],
        }
        reports = temporary/"reports"
        finqa.write_json(reports/f"{BASE_TRANSLATION}.json", original_translation)
        finqa.write_json(reports/f"{TRANSLATION_RUN}.json", added)
        with patch.object(report, "DOCS_RESULTS_DIR", reports):
            combined = append_translation(original_translation, added, "fixture")
            assert len(combined["models"]) == 30 and combined["models"][:-1] == original_translation["models"]
            assert len(combined["samples"]) == len(original_translation["samples"])
            bad = copy.deepcopy(added)
            bad["samples"][0]["src_text"] += "changed"
            finqa.write_json(reports/f"{TRANSLATION_RUN}.json", bad)
            try:
                append_translation(original_translation, bad, "fixture")
            except ValueError:
                pass
            else:
                raise AssertionError("changed translation sample accepted")
    print("Parent560 reproduction + mocked Kimi20 extension/cache fees + mutation rejection OK")


if __name__ == "__main__":
    main()
