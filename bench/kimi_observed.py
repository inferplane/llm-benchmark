"""Report all Kimi translation attempts, including real empty/capped outcomes.

Collector, prompts, dataset, rubric and judges stay under the original pre-call
contract. This separate reporting policy is explicitly recorded after collection
and before judging; it does not regenerate, repair, or discard failed attempts.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from bench import kimi_benchmark as k, finqa, report, run, judge

POLICY = """One recorded collector attempt per scheduled input, all3300 inputs retained.
No regeneration or output-cap increase to remove empty or capped outcomes.
Use the originally frozen translation rubric and two judges on returned nonempty
outputs, including visible capped outputs. Empty/invalid responses remain translation
failures with no invented judgment. Report quality coverage and cap counts explicitly.
Existing quality statistics are conditional on eligible returned translations, not
an all-input success score. Cost estimates cover successfully returned text only;
failed-call cache usage is not fully retained, so this is not a total experiment bill.
This reporting policy was recorded after observing collection outcomes, before judging."""


def validate():
    saved = k.verify_contract()
    identity = saved["identity"]
    folder = k.translation_folder()
    data = finqa.read_rows(folder/"dataset.jsonl")
    if len(data) != 3300 or len({r["id"] for r in data}) != 3300 or finqa.digest(data) != identity["translation_dataset_sha256"]:
        raise ValueError("full3300 input identity differs")
    if json.loads((folder/"extension.json").read_text()) != saved:
        raise ValueError("collector pre-call receipt differs")
    manifest = json.loads((folder/"manifest.json").read_text())
    if manifest["run_id"] != k.TRANSLATION_RUN or len(manifest.get("executions", [])) != 1:
        raise ValueError("this observation policy requires one full collector invocation")
    execution = manifest["executions"][0]
    if any(manifest.get(key) != value for key, value in execution.items()):
        raise ValueError("manifest/history disagree")
    if execution["started_at"] < saved["frozen_at"] or not execution.get("finished_at"):
        raise ValueError("collector incomplete or predates freeze")
    required = {
        "dataset_segments": 3300, "dataset_sha256": identity["translation_dataset_sha256"],
        "aws_region": identity["aws_region"],
        "generation_parameters": {"temperature": 0, "max_tokens": identity["max_output_tokens"]},
        "prompt_sha256": identity["translation_prompt_sha256"][:12],
        "rubric_sha256": identity["translation_rubric_sha256"][:12],
    }
    if any(execution.get(key) != value for key, value in required.items()):
        raise ValueError("collector generation/input contract differs")
    if len(execution["models"]) != 1:
        raise ValueError("unexpected collector roster")
    model = identity["model"]
    expected_model = {key: model[key] for key in (
        "name", "api", "model_id", "price_in", "price_out", "price_cache_read", "price_cache_write")}
    expected_model.update(
        concurrency=model.get("concurrency", identity["translation_scenario"]["concurrency_default"]),
        temperature_omitted=True, thinking_disabled=False,
        request_max_attempts=model.get("request_max_attempts", 1),
        bedrock_reasoning_effort=model.get("bedrock_reasoning_effort"),
    )
    if any(execution["models"][0].get(key) != value for key, value in expected_model.items()):
        raise ValueError("collector model/settings differ")
    rows = finqa.read_rows(folder/"translations.jsonl")
    expected = {r["id"]: r for r in data}
    if len(rows) != 3300 or {(r["model"], r["id"]) for r in rows} != {(k.NAME, key) for key in expected}:
        raise ValueError("missing/duplicate/unexpected attempts")
    for row in rows:
        if row["timestamp"] < saved["frozen_at"] or row["request_attempt"] != 1:
            raise ValueError("attempt chronology/retry differs")
        if any(row[key] != expected[row["id"]][key] for key in ("src_lang", "tgt_lang", "doc_type")):
            raise ValueError("attempt metadata differs")
        if row["error"] is None:
            run._validate_result({"text": row["output_text"], **{key: row.get(key, 0) for key in (
                "tokens_in", "tokens_out", "cache_read_tokens", "cache_write_tokens")}})
        elif not row.get("translation_error_details"):
            raise ValueError("failure lacks retained diagnostic")
    return saved, data, rows


def identity():
    saved, data, rows = validate()
    return {
        "policy": POLICY, "original_contract_sha256": k.sha(k.CONTRACT),
        **k.judge_identity(saved), "reporter_sha256": k.sha(__file__),
        "model": saved["identity"]["model"],
    }


def policy_path():
    return k.translation_folder()/"observation-policy.json"


def establish_policy():
    expected = identity()
    path = policy_path()
    if path.exists():
        if json.loads(path.read_text())["identity"] != expected:
            raise ValueError("recorded observation policy differs")
    else:
        if (k.translation_folder()/"judgments.jsonl").exists():
            raise ValueError("must record reporting policy before judging")
        finqa.write_json(path, {"recorded_at": datetime.now(timezone.utc).isoformat(),
                               "recorded_after_collection": True, "identity": expected})


def verify_policy():
    saved = json.loads(policy_path().read_text())
    if saved["identity"] != identity():
        raise ValueError("observation inputs/policy changed")
    return saved


async def run_judges():
    establish_policy()
    original = k.verify_contract()
    path = k.translation_folder()/"judge-input.json"
    receipt = k.judge_identity(original)
    if path.exists() and json.loads(path.read_text()) != receipt:
        raise ValueError("judge input changed")
    finqa.write_json(path, receipt)
    args = SimpleNamespace(run_id=k.TRANSLATION_RUN, dataset=str(k.translation_folder()/"dataset.jsonl"),
                           limit=None, concurrency=8)
    outcome = await judge.main_async(args)
    return int(outcome["failed"] != 0)


def build_report():
    policy = verify_policy()
    saved, data, rows = validate()
    returned = [r for r in rows if r["error"] is None and r.get("output_text")]
    failed = [r for r in rows if r["error"] is not None]
    wanted = {(r["model"], r["id"]) for r in returned}
    judgments = run.dedupe_latest(finqa.read_rows(k.translation_folder()/"judgments.jsonl"),
                                  lambda r: (r["model"], r["id"]))
    if {(r["model"], r["id"]) for r in judgments} != wanted or len(judgments) != len(wanted):
        raise ValueError("judgment coverage must equal returned outputs exactly")
    if any(r.get("error") is not None or report.raw_judge_scores(r) is None for r in judgments):
        raise ValueError("unresolved/incomplete paired judgments")
    if json.loads((k.translation_folder()/"judge-input.json").read_text()) != k.judge_identity(saved):
        raise ValueError("judgments refer to different inputs")
    cfg = run.load_config()
    result = report.build_report(k.TRANSLATION_RUN, cfg["scenario"]["translation"], cfg["models"],
                                 [k.translation_folder()/"dataset.jsonl"])
    if [m["name"] for m in result["models"]] != [k.NAME]:
        raise ValueError("unexpected model in report")
    a = result["models"][0]["aggregate"]
    if (a["segments"] != 3300 or a["translation_failures"] != len(failed) or
            any(a[key] != len(returned) for key in ("successful_translations", "judged_segments", "quality_eligible_segments"))):
        raise ValueError("observed coverage differs from report")
    capped = [r for r in rows if r.get("finish_reason") in ("length", "max_tokens")]
    diagnostics = {
        "scheduled_inputs": 3300, "recorded_attempts": len(rows), "returned_outputs": len(returned),
        "unreturned_outputs": len(failed), "capped_outputs": len(capped),
        "capped_with_text": sum(r["error"] is None and bool(r.get("output_text")) for r in capped),
        "capped_without_text": sum(r["error"] is not None for r in capped),
        "error_types": dict(Counter(r["translation_error_details"]["type"] for r in failed)),
        "regenerated_attempts": 0, "all_input_quality_coverage": len(returned)/3300,
    }
    result["models"][0]["collection_diagnostics"] = diagnostics
    result["measurement_contract"] = saved
    result["observation_policy"] = policy
    result["measured_dataset_sha256"] = finqa.digest(data)
    result["interpretation"] = (
        f"3300개 입력의 최초 수집 결과를 보존했습니다. 반환된 번역 {len(returned)}개를 두 평가자로 채점했고, "
        f"출력 미반환 {len(failed)}건과 상한 도달 {len(capped)}건을 표시합니다(두 범주는 겹칠 수 있음). "
        "재생성이나 토큰 상한 변경은 하지 않았습니다. 품질 점수는 평가 가능한 출력 기준이며 "
        "요청 전체의 성공률과 다릅니다. 비용은 출력이 반환된 부분의 추정치로 실패 호출의 청구액을 포함하지 않습니다.")
    return result


def comparison():
    new = json.loads((report.DOCS_RESULTS_DIR/f"{k.TRANSLATION_RUN}.json").read_text())
    if new != build_report():
        raise ValueError("report does not reproduce from first-attempt observations")
    base = json.loads((report.DOCS_RESULTS_DIR/f"{k.BASE_TRANSLATION}.json").read_text())
    result = k.append_translation(base, new, k.sha(report.DOCS_RESULTS_DIR/f"{k.TRANSLATION_RUN}.json"))
    result["observation_policy"] = new["observation_policy"]
    result["interpretation"] += "\n\n" + new["interpretation"]
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["policy", "judge", "report"])
    args = p.parse_args()
    if args.command == "policy":
        establish_policy()
    elif args.command == "judge":
        raise SystemExit(asyncio.run(run_judges()))
    else:
        report.write_report(build_report())
        print(report.write_report(comparison()))


if __name__ == "__main__":
    main()
