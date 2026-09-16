"""Validate complete results and compute matched source-cluster comparisons."""

import hashlib
import json
import statistics
import sys
from decimal import Decimal
from pathlib import Path

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT))

from bench.run import dedupe_latest, load_config, load_dataset
from bench.report import AXES, paired_cluster_ci95, raw_judge_scores, source_document_id


def read_latest(name):
    return {
        (row["model"], row["id"]): row
        for row in dedupe_latest(load_dataset([RUN / name]), lambda r: (r["model"], r["id"]))
    }


def main():
    protocol = json.loads((RUN / "protocol.json").read_text())
    cfg = load_config()
    assert hashlib.sha256((ROOT / "config.toml").read_bytes()).hexdigest() == protocol["config_sha256"]
    assert hashlib.sha256((RUN / "dataset.jsonl").read_bytes()).hexdigest() == protocol["dataset_sha256"]
    segments = {row["id"]: row for row in load_dataset([RUN / "dataset.jsonl"])}
    models = protocol["models"]
    assert models == ["grok-4.3", "grok-4.6"] and len(segments) == 3300
    expected = {(model, id_) for model in models for id_ in segments}
    translations = read_latest("translations.jsonl")
    judgments = read_latest("judgments.jsonl")
    assert translations.keys() == judgments.keys() == expected, "Incomplete or unexpected keys"
    for key in expected:
        t, j = translations[key], judgments[key]
        assert t.get("error") is None and j.get("error") is None, key
        assert t.get("response_status") == "completed" and t["output_text"].strip(), key
        assert (t["src_lang"], t["tgt_lang"]) == (
            segments[key[1]]["src_lang"], segments[key[1]]["tgt_lang"]), key
        assert raw_judge_scores(j) is not None, key
        assert abs(j["overall"] - statistics.mean(j[axis] for axis in AXES)) < 0.001, key

    groups = {
        "all": list(segments),
        "flores": [id_ for id_, s in segments.items() if s["doc_type"] == "flores"],
        "synthetic": [id_ for id_, s in segments.items() if s["doc_type"] != "flores"],
    }
    comparisons = {}
    for group, ids in groups.items():
        deltas = [judgments[("grok-4.6", id_)]["overall"]
                  - judgments[("grok-4.3", id_)]["overall"] for id_ in sorted(ids)]
        clusters = {}
        for id_, delta in zip(sorted(ids), deltas):
            clusters.setdefault(source_document_id(id_), []).append(delta)
        stats = {}
        for model in models:
            rows = [judgments[(model, id_)] for id_ in ids]
            raw = [raw_judge_scores(row) for row in rows]
            stats[model] = {
                "segments": len(rows),
                "judge_overall": round(statistics.mean(row["overall"] for row in rows), 3),
                "judge": {axis: round(statistics.mean(row[axis] for row in rows), 3)
                          for axis in AXES},
                "quality_pass_segments": sum(
                    all(score[axis] >= 4 for score in scores for axis in AXES) for scores in raw),
                "high_risk_segments": sum(
                    any(score["numbers_entities_dates"] <= 2 for score in scores) for scores in raw),
                "judge_disagreement_segments": sum(
                    abs(Decimal(str(scores[0]["overall"])) - Decimal(str(scores[1]["overall"]))) >= 1
                    for scores in raw),
            }
        comparisons[group] = {
            "candidate_model": "grok-4.6", "reference_model": "grok-4.3",
            "paired_segments": len(ids), "paired_source_documents": len(clusters),
            "wins": sum(delta > 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "losses": sum(delta < 0 for delta in deltas),
            "mean_delta": round(statistics.mean(deltas), 3),
            "mean_delta_ci95": paired_cluster_ci95(clusters),
            "bootstrap_unit": "source_document", "models": stats,
        }

    costs = {}
    configurations = {model["name"]: model for model in cfg["models"]}
    for model in models:
        rows = [row for (name, _), row in translations.items() if name == model]
        tokens_in = sum(row["tokens_in"] for row in rows)
        tokens_out = sum(row["tokens_out"] for row in rows)
        configuration = configurations[model]
        total = (tokens_in * configuration["price_in"] + tokens_out * configuration["price_out"]) / 1e6
        reported_total = round(total, 4)
        passes = comparisons["all"]["models"][model]["quality_pass_segments"]
        costs[model] = {
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_total_usd": reported_total,
            "cost_per_segment_usd": round(reported_total / len(rows), 5),
            "cost_per_quality_pass_usd": round(reported_total / passes, 5) if passes else None,
        }

    report = json.loads((ROOT / "docs/results" / f"{RUN.name}.json").read_text())
    assert {model["name"] for model in report["models"]} == set(models)
    for model in report["models"]:
        name = model["name"]
        for group in groups:
            actual = model["aggregate"] if group == "all" else model["by_track"][group]
            for key, value in comparisons[group]["models"][name].items():
                assert actual[key] == value, (name, group, key, actual[key], value)
        for key, value in costs[name].items():
            if not key.startswith("tokens_"):
                assert model["aggregate"][key] == value, (name, key)
        a = model["aggregate"]
        assert a["translation_failures"] == a["judge_failures"] == a["not_yet_judged"] == 0
        assert a["successful_translations"] == a["judged_segments"] == 3300
        if name == "grok-4.6":
            assert a["throughput_tok_s"] is None
            assert model["run_config"]["request_timeouts_s"] == [120, 600]
        else:
            assert a["throughput_tok_s"] is not None
            assert model["run_config"]["request_timeout_s"] == 120

    result = {
        "run_id": RUN.name, "comparisons": comparisons, "whole_model_costs": costs,
        "validated_translation_keys": len(translations),
        "validated_judgment_keys": len(judgments),
        "protocol_sha256": hashlib.sha256((RUN / "protocol.json").read_bytes()).hexdigest(),
        "prompt_sha256": protocol["prompt_sha256"],
        "rubric_sha256": protocol["rubric_sha256"],
    }
    (RUN / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
