"""Compose published model snapshots without pooling incompatible experiments.

Run: uv run python -m bench.integrated_report
"""

import copy
import argparse
import hashlib
import json

from bench.report import DOCS_RESULTS_DIR, ROOT, write_report

BASE = "grok-4.6-2026-09-16"
UPDATE = "grok-explicit-2026-09-16"
RUN_ID = "integrated-2026-09-17"
LABELS = {
    "original": "기존 번역 지시 · 27개 모델",
    "explicit": "명시적 번역 지시 · Grok 2개 모델",
}


def compose(base, update):
    """Keep complete per-model snapshots; never recompute cost or pair scores."""
    if base["dataset"] != update["dataset"]:
        raise ValueError("Dataset coverage differs")
    if base["manifest"]["rubric_sha256"] != update["manifest"]["rubric_sha256"]:
        raise ValueError("Rubrics differ")
    for report in (base, update):
        names = [m["name"] for m in report["models"]]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate model")
    replacements = {m["name"] for m in update["models"]}
    if replacements != {"grok-4.3", "grok-4.6"}:
        raise ValueError("Expected the two explicitly re-evaluated Grok models")
    if not replacements <= {m["name"] for m in base["models"]}:
        raise ValueError("Replacement model missing from base")
    source_models = [
        (base, "original", m) for m in base["models"] if m["name"] not in replacements
    ] + [(update, "explicit", m) for m in update["models"]]
    models = []
    for source, cohort, model in source_models:
        snapshot = copy.deepcopy(model)
        snapshot["evaluation_cohort"] = cohort
        snapshot["source_report"] = source["run_id"]
        models.append(snapshot)
    base_samples = {s["id"]: s for s in base["samples"]}
    update_samples = {s["id"]: s for s in update["samples"]}
    if (len(base_samples) != len(base["samples"]) or
            len(update_samples) != len(update["samples"]) or
            base_samples.keys() != update_samples.keys()):
        raise ValueError("Sample coverage differs")
    samples = []
    for seg_id, original in base_samples.items():
        latest = update_samples[seg_id]
        metadata = lambda s: {k: v for k, v in s.items() if k != "by_model"}
        if metadata(original) != metadata(latest):
            raise ValueError(f"Sample source/reference differs: {seg_id}")
        sample = copy.deepcopy(metadata(original))
        sample["by_model"] = {}
        for source, _, model in source_models:
            src = original if source is base else latest
            sample["by_model"][model["name"]] = copy.deepcopy(src["by_model"][model["name"]])
        samples.append(sample)
    return {
        "schema_version": base["schema_version"],
        "run_id": RUN_ID,
        "title": "통합 벤치마크 결과 · 29개 모델",
        "report_kind": "integrated",
        "scenario": base["scenario"],
        "dataset": copy.deepcopy(base["dataset"]),
        "metric_policy": copy.deepcopy(base["metric_policy"]),
        # No synthetic execution manifest or pooled judge bill: these belong
        # to the original experiments, including their superseded model rows.
        "source_reports": [
            {"run_id": r["run_id"], "cohort": cohort,
             "prompt_sha256": r["manifest"]["prompt_sha256"],
             "rubric_sha256": r["manifest"]["rubric_sha256"],
             "dataset_sha256": r["manifest"].get("dataset_sha256")}
            for r, cohort in ((base, "original"), (update, "explicit"))
        ],
        "cohorts": LABELS,
        "comparison_note": (
            "29개 모델의 최신 관측 결과입니다. 기존 27개 모델과 Grok 2개 모델은 번역 지시가 다릅니다. "
            "전체 보기는 결과 개요이며 동일 조건의 종합 순위가 아닙니다. "
            "평가 조건을 선택하면 해당 그룹의 결과와 가성비 프론티어를 볼 수 있습니다. "
            "기존 실행의 전체 데이터 해시는 없어 동일 입력 검증은 게시된 샘플 범위로 한정됩니다. "
            "모델별 생성 설정과 수집 시점은 원본 기록을 유지합니다."
        ),
        "models": models,
        "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    sources = [DOCS_RESULTS_DIR / f"{name}.json" for name in (BASE, UPDATE)]
    base, update = [json.loads(path.read_text()) for path in sources]
    report = compose(base, update)
    if args.selfcheck:
        assert len(report["models"]) == 29
        by_name = {m["name"]: m for m in report["models"]}
        for source in (base, update):
            for model in source["models"]:
                if source is base and model["name"] in {"grok-4.3", "grok-4.6"}:
                    continue
                snapshot = copy.deepcopy(by_name[model["name"]])
                assert snapshot.pop("source_report") == source["run_id"]
                snapshot.pop("evaluation_cohort")
                assert snapshot == model, model["name"]
        assert len(report["samples"]) == 210
        for sample in report["samples"]:
            assert set(sample["by_model"]) == set(by_name)
        assert "manifest" not in report and "judge_cost" not in report
        for mutation in ("dataset", "rubric", "sample", "duplicate"):
            bad = copy.deepcopy(update)
            if mutation == "dataset":
                bad["dataset"]["pairs"] = 1
            elif mutation == "rubric":
                bad["manifest"]["rubric_sha256"] = "different"
            elif mutation == "sample":
                bad["samples"][0]["src_text"] = "different"
            else:
                bad["models"].append(bad["models"][0])
            try:
                compose(base, bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Accepted incompatible {mutation}")
        print("integrated selfcheck OK: 29 preserved snapshots, 210 samples, mismatch guards")
        return
    for entry, path in zip(report["source_reports"], sources):
        entry["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    report["interpretation"] = (ROOT / "results" / RUN_ID / "interpretation.md").read_text()
    print(write_report(report))


if __name__ == "__main__":
    main()
