"""Generate model-owned Lotte Tower HTML under the model/task hierarchy."""

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench import run
from tools import generate_self_portraits as collector

GENERATION = "lotte-tower-models-20261013"
RECORDS = ROOT / "results/model-lotte-towers" / GENERATION
PILOT = ROOT / "results/architecture-3d/lotte-world-tower-20261013-pilot"
PROMPT = ROOT / "tools/lotte_tower_prompt.txt"
MODELS = ROOT / "docs/models"
RUNTIME = ROOT / "docs/lotte-tower/runtime"
LOW_EFFORT_CLAUDE = {
    "claude-haiku-5.5", "claude-sonnet-5.5", "claude-opus-5.5",
    "claude-fable-5.1", "claude-sonnet-5",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_html(text):
    """Extract the author's complete document without modifying its bytes."""
    start = re.search(r"<!doctype\s+html\b|<html\b", text, re.I)
    end = list(re.finditer(r"</html\s*>", text, re.I))
    if not start or not end:
        raise ValueError("Model response is not a complete HTML document")
    code = text[start.start():end[-1].end()]
    if not re.search(r"<body\b", code, re.I):
        raise ValueError("Model response lacks body")
    for tag in re.findall(r"<(?:script|iframe)\b[^>]*>", code, re.I):
        source = re.search(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        if source and source[1] != "../runtime/three-runtime.js":
            raise ValueError("Only the pinned local Three.js runtime is permitted")
    return code


def initialize(models):
    RECORDS.mkdir(parents=True, exist_ok=True)
    for model in models:
        name = model["name"]
        directory = MODELS / name / "lotte-tower"
        directory.mkdir(parents=True, exist_ok=True)
        runtime = MODELS / name / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        for filename in ("three-runtime.js", "LICENSE"):
            shutil.copy2(RUNTIME / filename, runtime / filename)
        source = PILOT / name
        target = RECORDS / name
        if not target.exists() and (source / "record.json").exists():
            record = json.loads((source / "record.json").read_text())
            # Import original records unchanged; their actual generation remains
            # in record.json. No copied attempt is another paid call.
            shutil.copytree(source, target)
            original = ROOT / "docs/architecture-3d" / name / "artwork.html"
            if record["status"] == "generated":
                assert sha(original) == record["artwork_sha256"]
                shutil.copy2(original, directory / "artwork.html")
            collector.write_json(target / "import-provenance.json", {
                "source_records": str(source.relative_to(ROOT)),
                "original_generation": record.get("generation"),
                "original_record_sha256": sha(source / "record.json"),
                "import_is_not_an_additional_request": True,
            })
    manifest = {
        "task": "lotte-tower", "generation": GENERATION, "prompt_sha256": sha(PROMPT),
        "runtime_sha256": sha(RUNTIME / "three-runtime.js"),
        "models": [{"name": model["name"], "model_id": model["model_id"]} for model in models],
        "policy": "Only original model HTML, no coordinator/other-model substitutions. "
                  "Retained pilot requests are imported once unchanged, with provenance. "
                  "Token budgets and request settings are recorded per attempt.",
    }
    collector.write_json(RECORDS / "manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="actual comma-separated config names")
    parser.add_argument("--managed", action="store_true")
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--feedback")
    parser.add_argument("--fresh-repair", action="store_true")
    parser.add_argument("--repair-language", choices=("ko", "en"), default="ko")
    parser.add_argument("--retry-episode")
    parser.add_argument("--native-port", type=int, help="isolated loopback forwarding for this task")
    parser.add_argument("--prompt-file", help="recorded task-specific request template")
    args = parser.parse_args()
    cfg = run.load_config()
    initialize(cfg["models"])
    if args.init_only:
        return
    requested = set(args.models.split(",")) if args.models else {
        model["name"] for model in cfg["models"]
        if model.get("enabled", True) and model["api"] != "translate"
    }
    wanted = [model for model in cfg["models"] if model["name"] in requested]
    if {model["name"] for model in wanted} != requested:
        parser.error("Unknown configured model")
    if args.managed:
        wanted = [model for model in wanted if not model.get("base_url")]
    if not 1024 <= args.max_output_tokens <= 16384:
        parser.error("Unsafe output budget")
    if args.temperature is not None and any(not model.get("base_url") for model in wanted):
        parser.error("Sampling override is for self-hosted artwork only")
    if args.retry_episode and not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", args.retry_episode):
        parser.error("Unsafe retry episode")
    if args.native_port is not None and (
        not 1024 <= args.native_port <= 65535 or any(not model.get("base_url") for model in wanted)
    ):
        parser.error("Native forwarding port requires self-hosted models and a non-privileged port")
    if args.prompt_file and (len(wanted) != 1 or not Path(args.prompt_file).is_file()):
        parser.error("Custom request template requires one model and an existing file")
    feedback = json.loads(Path(args.feedback).read_text()) if args.feedback else {}
    prepared = []
    for model in wanted:
        options = dict(model)
        if args.prompt_file:
            options["_prompt_file"] = args.prompt_file
        if args.native_port is not None:
            options["base_url"] = f"http://127.0.0.1:{args.native_port}/v1"
        if model["name"] in LOW_EFFORT_CLAUDE or model["name"] == "kimi-k3":
            options["_art_effort"] = "low"
        if model["name"] == "grok-4.6":
            options["_art_stream"] = True
        if args.temperature is not None:
            options["_art_temperature"] = args.temperature
        if model["name"] in feedback:
            options["_feedback"] = feedback[model["name"]]
            options["_fresh_repair"] = args.fresh_repair
            options["_feedback_language"] = args.repair_language
        if args.retry_episode:
            options["_retry_episode"] = args.retry_episode
            options["request_max_attempts"] = 1
        prepared.append(options)
    collector.OUTPUT = MODELS
    collector.ARTIFACT_SUBDIR = "lotte-tower"
    collector.RECORDS = RECORDS
    collector.PROMPT = PROMPT
    collector.GENERATION = GENERATION
    collector.extract_html = extract_html
    run.MAX_OUTPUT_TOKENS = args.max_output_tokens
    async def generate():
        limiter = asyncio.Semaphore(1)
        for model in prepared:
            await collector.generate_one(model, cfg["aws"]["region"], limiter)
    asyncio.run(generate())
    if prepared and all(model.get("base_url") for model in prepared):
        # Native authors run one at a time. Refresh their local viewer before
        # the waiting independent reviewer opens it; publication stays gated.
        from tools import model_pages
        review = ROOT / "validation/model-tasks/lotte-review.json"
        model_pages.main(["--lotte-review", str(review)])


if __name__ == "__main__":
    main()
