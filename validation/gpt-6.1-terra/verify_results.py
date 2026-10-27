"""Read-only, independently calculated result/provenance checks; no API calls."""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench import finqa, run, terra_benchmark as terra

DIRECTORY = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cost(rows, model):
    return sum((sum(Decimal(row.get(field, 0)) * Decimal(str(model[price]))
        for field, price in (("tokens_in", "price_in"), ("tokens_out", "price_out"),
                             ("cache_read_tokens", "price_cache_read"), ("cache_write_tokens", "price_cache_write")))
        / Decimal(1_000_000) for row in rows if not row.get("error")), Decimal(0))


def execute(program, table):
    steps = re.findall(r"([a-z_]+)\(([^()]*)\)", program)
    assert re.sub(r"\s+", "", program) == ",".join(f"{op}({args})" for op, args in steps).replace(" ", "")
    results = []
    def number(value):
        value = value.strip()
        if value.startswith("#"):
            return results[int(value[1:])]
        if value.startswith("const_"):
            value = value[6:]
        value = value.replace(",", "").replace("$", "").strip()
        percent = value.endswith("%")
        if percent:
            value = value[:-1]
        if value.startswith("(") and value.endswith(")"):
            value = "-" + value[1:-1]
        return Fraction(value) / (100 if percent else 1)
    for operation, arguments in steps:
        left, right = [a.strip() for a in arguments.split(",", 1)]
        if operation == "table_average":
            row = next(row for row in table if row[0].strip().lower() == left.lower())
            values = [number(value) for value in row[1:]]
            result = sum(values) / len(values)
        else:
            a, b = number(left), number(right)
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                result = a / b
            else:
                raise AssertionError(operation)
        results.append(result)
    return results[-1]


def check_qa():
    published = read(finqa.REPORTS / f"{terra.QA_RUN}.json")
    base = read(terra.BASE_QA)
    assert published["models"][:-1] == base["models"]
    assert published["evaluations"][:-20] == base["evaluations"]
    dataset = finqa.read_rows(finqa.RESULTS / terra.QA_RUN / "dataset.jsonl")
    rows = run.dedupe_latest(finqa.read_rows(finqa.RESULTS / terra.QA_RUN / "answers.jsonl"), lambda r: (r["model"], r["id"]))
    assert len(rows) == len(dataset) == 20
    by_id = {r["id"]: r for r in rows}
    evaluations = {r["id"]: r for r in published["evaluations"][-20:]}
    correct = 0
    for segment in dataset:
        row = by_id[segment["id"]]
        assert not row.get("error") and row["response_status"] == "completed"
        obj = json.loads(row["output_text"])
        value = execute(obj["program"], segment["table"])
        unit = obj["unit"]
        assert unit == segment["audit"]["requested_unit"]
        if unit == "percent":
            value /= 100
        exact = Fraction(segment["audit"]["expected_rational"])
        verdict = round(value, 5) == round(exact, 5)
        assert evaluations[segment["id"]]["correct"] == verdict
        assert row["reported_input_tokens"] == sum(row.get(k, 0) for k in ("tokens_in", "cache_read_tokens", "cache_write_tokens"))
        correct += verdict
    model = published["models"][-1]
    exact_cost = cost(rows, terra.model())
    assert model["aggregate"]["correct"] == correct == 19
    assert model["aggregate"]["estimated_cost_usd"] == round(float(exact_cost), 4)
    return {"questions": 20, "independent_correct": correct, "exact_cost_usd": str(exact_cost),
            "previous_models_and_evaluations_preserved": True}


def check_translation(run_id, published_id, base_id, count, pairs):
    folder = ROOT / "results" / run_id
    rows = run.dedupe_latest(finqa.read_rows(folder / "translations.jsonl"), lambda r: (r["model"], r["id"]))
    dataset = finqa.read_rows(folder / "dataset.jsonl")
    assert len(rows) == len(dataset) == count
    assert set(r["id"] for r in rows) == set(r["id"] for r in dataset)
    coverage = Counter((r["src_lang"], r["tgt_lang"]) for r in rows)
    assert len(coverage) == pairs and set(coverage.values()) == {110}
    successful = [r for r in rows if not r.get("error")]
    judgments = run.dedupe_latest(finqa.read_rows(folder / "judgments.jsonl"), lambda r: (r["model"], r["id"]))
    assert len(judgments) == len(successful) and all(not r.get("error") for r in judgments)
    published = read(ROOT / "docs/results" / f"{published_id}.json")
    base = read(ROOT / "docs/results" / f"{base_id}.json")
    assert published["models"][:-1] == base["models"]
    for old, new in zip(base["samples"], published["samples"]):
        candidate_removed = {**new, "by_model": {k: v for k, v in new["by_model"].items() if k != terra.NAME}}
        assert candidate_removed == old
    model = published["models"][-1]
    exact_cost = cost(rows, terra.model())
    scheduling = read(DIRECTORY / "scheduling.json")
    assert model["measurement_scheduling"] == scheduling
    assert scheduling["note"] in published["interpretation"]
    assert model["aggregate"]["cost_total_usd"] == round(float(exact_cost), 4)
    assert model["aggregate"]["judged_segments"] == len(successful)
    for subset in (model["by_pair"], model["by_track"]):
        assert all(not any(k.startswith(("cost_", "throughput_")) for k in a) for a in subset.values())
    return {"segments": count, "pairs": pairs, "successful": len(successful),
            "judged": len(judgments), "exact_cost_usd": str(exact_cost),
            "previous_models_and_samples_preserved": True}


def check_scheduling():
    scheduling = read(DIRECTORY / "scheduling.json")
    intervals = scheduling["candidate_collection_intervals"]
    assert set(intervals) == {terra.TRANSLATION_RUN, "en-pivot-gpt-6.1-terra-20261027"}
    for run_id, period in intervals.items():
        manifest = read(ROOT / "results" / run_id / "manifest.json")
        assert len(manifest["executions"]) == 1
        assert period == {key: manifest["executions"][0][key] for key in ("started_at", "finished_at")}
    start = max(datetime.fromisoformat(period["started_at"]) for period in intervals.values())
    finish = min(datetime.fromisoformat(period["finished_at"]) for period in intervals.values())
    assert scheduling["translation_overlap_seconds"] == (finish - start).total_seconds() > 0
    assert scheduling["isolated_model_service_load"] is False
    integrated = read(ROOT / "docs/results" / f"{terra.COMPARISON}.json")
    source = next(source for source in integrated["source_reports"] if source["run_id"] == terra.TRANSLATION_RUN)
    assert source["report_sha256"] == sha(ROOT / "docs/results" / f"{terra.TRANSLATION_RUN}.json")
    return {"overlap_seconds": scheduling["translation_overlap_seconds"], "source_report_sha256_valid": True}


def check_artwork():
    reviews = read(DIRECTORY / "content-review.json")
    evidence = []
    for task, records in (("whoami", ROOT / "results/model-self-portraits/generations/free-expression-20261012"),
                          ("lotte-tower", ROOT / "results/model-lotte-towers/lotte-tower-models-20261013")):
        record = read(records / terra.NAME / "record.json")
        original = ROOT / "docs/models" / terra.NAME / task / "artwork.html"
        assert record["status"] == "generated" and record["reported_model"] == terra.model()["model_id"]
        assert record["artwork_sha256"] == sha(original)
        reviewed = next(r for r in reviews["artifacts"] if r["task"] == task)
        assert reviewed["artwork_sha256"] == sha(original)
        assert reviewed["verdict"] == "PASS" and reviewed["score"] >= 85 and reviewed["critical"] == 0 and reviewed["warnings"] <= 3
        if task == "lotte-tower":
            assert reviewed["task_requirements_complete"] is True
        provenance = read(original.with_name("provenance.json"))
        assert provenance["status"] == "generated" and provenance["artwork_sha256"] == sha(original)
        evidence.append({"task": task, "artwork_sha256": sha(original), "review_score": reviewed["score"]})
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-only", action="store_true")
    args = parser.parse_args()
    result = {"qa": check_qa()}
    if not args.qa_only:
        terra.verify()
        result["korean_translation"] = check_translation(terra.TRANSLATION_RUN, terra.COMPARISON, "integrated-2026-10-12", 3300, 30)
        result["english_translation"] = check_translation("en-pivot-gpt-6.1-terra-20261027", "en-pivot-20261027", "en-pivot-20261019", 3080, 28)
        result["english_translation_judge2"] = check_translation("en-pivot-gpt-6.1-terra-20261027-judge2", "en-pivot-20261027-judge2", "en-pivot-20261019-judge2", 3080, 28)
        result["scheduling"] = check_scheduling()
        source = ROOT / "results/en-pivot-gpt-6.1-terra-20261027/translations.jsonl"
        reused = ROOT / "results/en-pivot-gpt-6.1-terra-20261027-judge2/translations.jsonl"
        assert sha(source) == sha(reused)
        result["artwork"] = check_artwork()
        finqa.write_json(DIRECTORY / "final-verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
