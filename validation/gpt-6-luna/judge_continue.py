"""Resume the unchanged translation judges with greater task concurrency.

Generation is already complete and immutable. Judge concurrency is scheduling,
not a candidate latency measurement or a decoding parameter. Completed paired
judgments are cached; an interrupted, unrecorded pair may be requested again.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import luna_benchmark as b, finqa, judge, run


async def main():
    expected = b.judge_identity()
    assert b.read(b.FOLDER / "judge-input.json") == expected
    rows = finqa.read_rows(b.FOLDER / "judgments.jsonl")
    completed = run.dedupe_latest(rows, lambda r: (r["model"], r["id"]))
    receipt = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "judge_input": expected, "scheduler_sha256": b.sha(__file__),
        "concurrency": 32, "prior_concurrency": 8,
        "completed_pairs_reused": sum(r.get("error") is None for r in completed),
        "prior_rows_sha256": b.sha(b.FOLDER / "judgments.jsonl"),
        "policy": "Only judge scheduling changes. No candidate requests or decoding changes. "
                  "Retain completed pairs; interrupted unrecorded judge calls may incur extra "
                  "unobserved charges not included in the report's judge-cost estimate.",
    }
    path = b.FOLDER / "judge-scheduling.json"
    if path.exists():
        previous = b.read(path)
        assert previous["judge_input"] == expected and previous["scheduler_sha256"] == receipt["scheduler_sha256"]
        history = previous.get("executions", [])
    else:
        history = []
    history.append(receipt)
    finqa.write_json(path, {"judge_input": expected, "scheduler_sha256": receipt["scheduler_sha256"], "executions": history})
    outcome = await judge.main_async(SimpleNamespace(
        run_id=b.TRANSLATION_RUN, dataset=str(b.FOLDER / "dataset.jsonl"), limit=None, concurrency=32))
    receipt.update(finished_at=datetime.now(timezone.utc).isoformat(), outcome=outcome)
    finqa.write_json(path, {"judge_input": expected, "scheduler_sha256": receipt["scheduler_sha256"], "executions": history})
    return int(outcome["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
