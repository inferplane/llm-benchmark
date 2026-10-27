"""Frozen English-pivot addition; reuse translations for two judge sets."""
import argparse
import asyncio
import copy
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench import finqa, judge, report, run, terra_benchmark as terra

DIRECTORY = Path(__file__).resolve().parent
CONTRACT = DIRECTORY / "en-pivot-contract.json"
RUN_ID = "en-pivot-gpt-6.1-terra-20261027"
PATHS = [ROOT / "data" / f for f in (
    "flores-en.jsonl", "synthetic-en.jsonl", "flores-to-en.jsonl", "synthetic-to-en.jsonl")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def identity():
    cfg = run.load_config()
    rows = run.load_dataset(PATHS)
    base = read(ROOT / "docs/results/en-pivot-20261019.json")
    assert len(rows) == 3080 and finqa.digest(rows) == base["manifest"]["dataset_sha256"]
    assert sha(run.PROMPT_PATH)[:12] == base["manifest"]["prompt_sha256"]
    assert sha(ROOT / "scenarios/translation/rubric.txt")[:12] == base["manifest"]["rubric_sha256"]
    return {
        "model": terra.model(), "dataset_sha256": finqa.digest(rows),
        "scenario": cfg["scenario"]["translation"], "aws_region": cfg["aws"]["region"],
        "max_output_tokens": run.MAX_OUTPUT_TOKENS, "request_timeout_s": run.REQUEST_TIMEOUT_S,
        "files": {str(p.relative_to(ROOT)): sha(p) for p in (
            Path(__file__), Path(run.__file__), Path(judge.__file__), Path(report.__file__),
            run.PROMPT_PATH, ROOT / "scenarios/translation/rubric.txt",
            ROOT / "docs/results/en-pivot-20261019.json",
            ROOT / "docs/results/en-pivot-20261019-judge2.json", *PATHS)},
        "policy": terra.POLICY + " Reuse identical candidate responses for independent judge sets.",
    }


def freeze():
    contract = {"frozen_at": datetime.now(timezone.utc).isoformat(), "identity": identity()}
    folder = run.RESULTS_DIR / RUN_ID
    if CONTRACT.exists():
        assert read(CONTRACT)["identity"] == contract["identity"]
    else:
        assert not (folder / "manifest.json").exists()
        finqa.write_json(CONTRACT, contract)
        finqa.write_rows(folder / "dataset.jsonl", run.load_dataset(PATHS))


def verify():
    contract = read(CONTRACT)
    assert contract["identity"] == identity(), "English-pivot contract changed"
    assert finqa.digest(finqa.read_rows(run.RESULTS_DIR / RUN_ID / "dataset.jsonl")) == contract["identity"]["dataset_sha256"]
    return contract


async def measure():
    saved = verify()
    folder = run.RESULTS_DIR / RUN_ID
    assert not (folder / "manifest.json").exists(), "do not regenerate candidates"
    finqa.write_json(folder / "extension.json", saved)
    summary = await run.main_async(SimpleNamespace(
        models=terra.NAME, run_id=RUN_ID, dataset=str(folder / "dataset.jsonl"), pairs=None, limit=None))
    return int(summary["failed"] != 0)


def collected():
    saved = verify()
    folder = run.RESULTS_DIR / RUN_ID
    manifest = read(folder / "manifest.json")
    assert len(manifest["executions"]) == 1 and manifest.get("finished_at")
    assert manifest["dataset_sha256"] == saved["identity"]["dataset_sha256"]
    rows = run.dedupe_latest(finqa.read_rows(folder / "translations.jsonl"), lambda r: (r["model"], r["id"]))
    terra.validate_rows(rows, finqa.read_rows(folder / "dataset.jsonl"), saved["frozen_at"])
    return folder, manifest, rows


async def grade(alternate):
    source, manifest, rows = collected()
    run_id = RUN_ID + ("-judge2" if alternate else "")
    folder = run.RESULTS_DIR / run_id
    judges = verify()["identity"]["scenario"]
    selected = judges["judge_sets"]["astra-fable51"] if alternate else judges["judges"]
    if alternate:
        folder.mkdir(parents=True, exist_ok=True)
        for filename in ("translations.jsonl", "dataset.jsonl"):
            target = folder / filename
            if target.exists():
                assert sha(target) == sha(source / filename)
            else:
                shutil.copy2(source / filename, target)
        cloned = {**copy.deepcopy(manifest), "run_id": run_id,
                  "collection_source_run_id": RUN_ID,
                  "judge_models": [j["model_id"] for j in selected]}
        for execution in cloned["executions"]:
            execution["judge_models"] = cloned["judge_models"]
        finqa.write_json(folder / "manifest.json", cloned)
    binding = {"translation_sha256": sha(folder / "translations.jsonl"),
               "contract_sha256": sha(CONTRACT), "judges": selected,
               "candidate_regenerated": False}
    path = folder / "judge-input.json"
    if path.exists():
        assert read(path) == binding
    else:
        assert not (folder / "judgments.jsonl").exists()
        finqa.write_json(path, binding)
    summary = await judge.main_async(SimpleNamespace(
        run_id=run_id, dataset=str(folder / "dataset.jsonl"), limit=None,
        concurrency=32, judge_set="astra-fable51" if alternate else None))
    return int(summary["failed"] != 0)


def compose(alternate):
    folder, _, rows = collected()
    run_id = RUN_ID + ("-judge2" if alternate else "")
    scenario = copy.deepcopy(verify()["identity"]["scenario"])
    if alternate:
        scenario["judges"] = scenario["judge_sets"]["astra-fable51"]
    judgments = run.dedupe_latest(finqa.read_rows(run.RESULTS_DIR / run_id / "judgments.jsonl"), lambda r: (r["model"], r["id"]))
    successful = [r for r in rows if not r.get("error")]
    assert {(r["model"], r["id"]) for r in judgments} == {(r["model"], r["id"]) for r in successful}
    assert all(not r.get("error") and report.raw_judge_scores(r) is not None for r in judgments)
    new = report.build_report(run_id, scenario, run.load_config()["models"], [folder / "dataset.jsonl"])
    assert len(new["models"]) == 1 and new["models"][0]["name"] == terra.NAME
    new["measurement_contract"] = read(CONTRACT)
    new["interpretation"] = "GPT-6.1 Terra · 영어↔14개 언어 · 동일3080개 입력 · reasoning low · temperature 생략 · 출력 상한4096. 두 평가자 조합은 동일한 번역 응답을 각각 채점합니다."
    report.write_report(new)
    suffix = "-judge2" if alternate else ""
    base_path = ROOT / f"docs/results/en-pivot-20261019{suffix}.json"
    base = read(base_path)
    assert base["dataset"] == new["dataset"]
    result = copy.deepcopy(base)
    result["models"].append(copy.deepcopy(new["models"][0]))
    incoming = {s["id"]: s for s in new["samples"]}
    assert set(incoming) == {s["id"] for s in base["samples"]}
    for sample in result["samples"]:
        other = incoming[sample["id"]]
        assert {k: v for k, v in sample.items() if k != "by_model"} == {k: v for k, v in other.items() if k != "by_model"}
        sample["by_model"][terra.NAME] = copy.deepcopy(other["by_model"][terra.NAME])
    result.update(run_id="en-pivot-20261027" + suffix,
        title=f"영어 중심 번역 비교 · 판정 {'astra+fable-5.1' if alternate else 'sol+fable-5'} · 40개 모델",
        default=alternate, parent_run_id=base["run_id"], extension_contract=read(CONTRACT))
    # Keep measured execution manifests in their source runs. A composite has
    # no pooled wall clock or synthetic candidate execution.
    result["source_runs"].extend(copy.deepcopy(new["source_runs"]))
    result["source_compatibility"] = report.source_compatibility(result["source_runs"])
    result["manifest"] = copy.deepcopy(new["manifest"])
    result["judge_cost"] = {"source_estimates": [copy.deepcopy(base["judge_cost"]), copy.deepcopy(new["judge_cost"])],
        "cost_usd_total": round(base["judge_cost"]["cost_usd_total"] + new["judge_cost"]["cost_usd_total"], 4),
        "judges": copy.deepcopy(base["judge_cost"]["judges"]) + copy.deepcopy(new["judge_cost"]["judges"])}
    result["interpretation"] = base.get("interpretation", "") + "\n\n" + new["interpretation"] + " 기존39개 모델의 점수·비용·샘플은 그대로 보존했습니다. 측정 시점은 다릅니다."
    assert result["models"][:-1] == base["models"]
    report.write_report(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run", "judge", "judge2", "report", "report2", "verify"))
    args = parser.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command == "run":
        raise SystemExit(asyncio.run(measure()))
    elif args.command.startswith("judge"):
        raise SystemExit(asyncio.run(grade(args.command == "judge2")))
    elif args.command.startswith("report"):
        compose(args.command == "report2")
    else:
        verify()
        print("English-pivot contract verified")


if __name__ == "__main__":
    main()
