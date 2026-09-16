"""Reproduce this fixed two-model translation experiment.

Prepare once before committing the inputs:
    uv run python results/grok-explicit-2026-09-16/reproduce.py prepare
Run or resume the translations:
    uv run python results/grok-explicit-2026-09-16/reproduce.py run
Judge/report separately with their existing CLIs and this dataset.jsonl.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent
ROOT = RUN_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from bench.run import (
    CONFIG, MAX_OUTPUT_TOKENS, PROMPT_PATH, ResultCache, _git_commit,
    load_config, load_dataset, run_model, write_manifest,
)

NAMES = ("grok-4.3", "grok-4.6")
RUBRIC = ROOT / "scenarios/translation/rubric.txt"


@contextmanager
def execution_lock():
    import fcntl
    with (RUN_DIR / ".execution.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another experiment writer is active") from error
        yield


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settings():
    cfg = load_config()
    models = [next(m for m in cfg["models"] if m["name"] == name) for name in NAMES]
    for model in models:
        assert model.get("enabled", True)
        assert model["api"] == "bedrock_mantle"
        assert model["mantle_region"] == "us-west-2"
        assert model["mantle_reasoning_effort"] == "low"
        assert model["request_max_attempts"] == 4
        assert model.get("concurrency", cfg["scenario"]["translation"]["concurrency_default"]) == 8
    assert MAX_OUTPUT_TOKENS == 4096
    return cfg, models


def prepare():
    if (RUN_DIR / "translations.jsonl").exists() or (RUN_DIR / "protocol.json").exists():
        raise RuntimeError("Frozen experiment already exists; use run to resume")
    cfg, models = settings()
    paths = [ROOT / "data/flores.jsonl", ROOT / "data/synthetic.jsonl"]
    segments = load_dataset(paths)
    assert len(segments) == len({s["id"] for s in segments}) == 3300
    tracks = Counter("flores" if s["doc_type"] == "flores" else "synthetic" for s in segments)
    assert tracks == {"flores": 3000, "synthetic": 300}
    pairs = Counter((s["src_lang"], s["tgt_lang"]) for s in segments)
    assert len(pairs) == 30 and set(pairs.values()) == {110}
    (RUN_DIR / "dataset.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in segments), encoding="utf-8")
    (RUN_DIR / "prompt.txt").write_bytes(PROMPT_PATH.read_bytes())
    (RUN_DIR / "rubric.txt").write_bytes(RUBRIC.read_bytes())
    protocol = {
        "run_id": RUN_DIR.name, "models": list(NAMES), "segments_per_model": 3300,
        "tracks_per_model": dict(tracks), "translation_directions": 30,
        "dataset_sha256": sha(RUN_DIR / "dataset.jsonl"),
        "source_files_sha256": {str(p.relative_to(ROOT)): sha(p) for p in paths},
        "prompt_sha256": sha(PROMPT_PATH), "rubric_sha256": sha(RUBRIC),
        "config_sha256": sha(CONFIG), "recorded_model_configs": models,
        "judge_configs": cfg["scenario"]["translation"]["judges"],
        "temperature": 0, "max_output_tokens": MAX_OUTPUT_TOKENS,
        "execution_mode": "concurrent_model_batches",
        "concurrency_per_model": 8, "total_candidate_concurrency": 16,
        "fresh_observations": True, "diagnostic_or_historical_results_included": False,
    }
    (RUN_DIR / "protocol.json").write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Prepared 3,300 frozen inputs for each of two models")


async def execute():
    cfg, models = settings()
    protocol = json.loads((RUN_DIR / "protocol.json").read_text())
    for key, path in [
        ("dataset_sha256", RUN_DIR / "dataset.jsonl"),
        ("prompt_sha256", PROMPT_PATH), ("rubric_sha256", RUBRIC), ("config_sha256", CONFIG),
    ]:
        if sha(path) != protocol[key]:
            raise RuntimeError(f"{key} differs from the frozen protocol; refusing cache reuse")
    assert sha(RUN_DIR / "prompt.txt") == protocol["prompt_sha256"]
    assert sha(RUN_DIR / "rubric.txt") == protocol["rubric_sha256"]
    protocol_sha = sha(RUN_DIR / "protocol.json")
    execution_path = RUN_DIR / "execution.json"
    if execution_path.exists():
        if json.loads(execution_path.read_text())["protocol_sha256"] != protocol_sha:
            raise RuntimeError("Protocol differs from the original execution")
    elif (RUN_DIR / "translations.jsonl").exists():
        raise RuntimeError("Translation cache has no recorded execution provenance")
    else:
        execution_path.write_text(json.dumps({
            "protocol_sha256": protocol_sha, "git_commit": _git_commit(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    segments = load_dataset([RUN_DIR / "dataset.jsonl"])
    cache = ResultCache(RUN_DIR / "translations.jsonl")
    started = datetime.now(timezone.utc).isoformat()
    summaries = await asyncio.gather(*(
        run_model(model, segments, cache, cfg["aws"]["region"], 8) for model in models
    ))
    summary = {key: sum(row[key] for row in summaries)
               for key in ("requested", "successful", "failed", "cached", "request_attempts")}
    summary["models"] = summaries
    write_manifest(
        RUN_DIR.name, cfg, cfg["scenario"]["translation"], models, segments,
        started, datetime.now(timezone.utc).isoformat(), completion_summary=summary,
    )
    path = RUN_DIR / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(dataset_sha256=protocol["dataset_sha256"],
                    protocol_sha256=protocol_sha, protocol=protocol)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary), flush=True)
    return int(summary["failed"] != 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run"])
    action = parser.parse_args().action
    if action == "prepare":
        prepare()
        return 0
    with execution_lock():
        return asyncio.run(execute())


if __name__ == "__main__":
    sys.exit(main())
