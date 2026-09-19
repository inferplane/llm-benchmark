"""Reproduce the reviewed sample from pinned upstream dev.json.

uv run python -m scenarios.finqa_audited.prepare --source /path/to/dev.json
No network or candidate model calls. Rejects a different source or selection.
"""
import argparse
import hashlib
import json
import random
from fractions import Fraction

from bench import finqa


def prepare(source_path):
    scenario = finqa.ROOT / "scenarios/finqa_audited"
    audit = json.loads((scenario / "selection-audit.json").read_text())
    raw = source_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != audit["source_sha256"]:
        raise ValueError("not the pinned upstream source")
    old = {r["source_id"] for r in finqa.read_rows(finqa.ROOT / "data/finqa-dev.jsonl")}
    rows = sorted((r for r in json.loads(raw) if r["id"] not in old), key=lambda r: r["id"])
    random.Random(audit["seed"]).shuffle(rows)
    assert finqa.digest([r["id"] for r in rows]) == audit["candidate_order_sha256"]
    result = []
    for decision in audit["records"]:
        source = rows[decision["candidate_index"]]
        assert source["id"] == decision["source_id"]
        assert source["qa"]["question"] == decision["question"]
        assert source["qa"]["program"] == decision["reference_program"]
        if decision["decision"] == "exclude":
            continue
        record = finqa.prepare([source], audit["source_revision"], "dev", 1, 13)[0]
        record["audit"] = {key: decision[key] for key in (
            "candidate_index", "canonical_unit", "requested_unit", "expected_rational", "reason",
        )}
        assert round(float(Fraction(decision["expected_rational"])), 5) == record["gold_answer"]
        result.append(record)
    assert len(result) == 20
    return result


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    records = prepare(args.source)
    target = finqa.ROOT / "data/finqa-audited-dev.jsonl"
    if (finqa.ROOT / "scenarios/finqa_audited/freeze.json").exists():
        assert records == finqa.read_rows(target), "frozen dataset cannot be replaced"
        print("Frozen dataset reproduced exactly")
    else:
        finqa.write_rows(target, records)
        print("Prepared reviewed 20-question sample")
