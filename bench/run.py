"""Translation benchmark runner.

Fans out each enabled model over the dataset (data/*.jsonl) concurrently,
records tokens/latency, and caches results per (model, segment id) so a
rerun after a partial failure only pays for what's missing.

Usage:
    uv run python3 -m bench.run --models nova-lite --pairs ko-en,en-ko --limit 5
    uv run python3 -m bench.run --run-id 2026-07-15 --dataset /tmp/smoke.jsonl
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
PROMPT_PATH = ROOT / "scenarios/translation/prompt.txt"
PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
MAX_OUTPUT_TOKENS = 4096  # shared cap for Bedrock + OpenAI/vLLM so no provider gets a bigger budget by default

# These bedrock-mantle models reject the `temperature` param outright (verified
# live: 400 "Unsupported parameter"): OpenAI's reasoning tiers, plus
# google.gemma-4-31b (which otherwise answers fine on the mantle path). gpt-5.4
# and grok-4.3 are the roster's mantle models that still accept it. This means
# decoding parity (see call_bedrock/call_openai) cannot be perfectly uniform
# across every model — it's an intrinsic limitation of these specific model
# IDs, not a config knob, hence hardcoded here rather than in config.toml.
MANTLE_NO_TEMPERATURE = {"openai.gpt-5.6-sol", "openai.gpt-5.6-terra", "openai.gpt-5.6-luna", "openai.gpt-5.5", "google.gemma-4-31b"}

# Same exception, plain Bedrock Converse API this time: claude-sonnet-5 400s
# with "`temperature` is deprecated for this model" (verified live via a
# smoke run — this model hadn't gone through the pipeline before). Kept
# separate from MANTLE_NO_TEMPERATURE since it's a different API/provider,
# but write_manifest's temperature_omitted check covers both sets.
# claude-fable-5 (used as the second judge, see config.toml's
# scenario.translation.judges) rejects it too, same "deprecated" error.
BEDROCK_NO_TEMPERATURE = {"us.anthropic.claude-sonnet-5", "us.anthropic.claude-fable-5"}

# claude-sonnet-5 defaults to extended thinking; on long synthetic financial
# documents it can burn the entire MAX_OUTPUT_TOKENS budget on reasoningContent
# and hit max_tokens before emitting any text block at all — 6 real failures
# in a full run, reproduced live: disabling thinking (thinking: {type:
# disabled}) restores end_turn + a normal text block on the identical prompt.
BEDROCK_DISABLE_THINKING = {"us.anthropic.claude-sonnet-5"}

LANG_NAMES = {
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese", "es": "Spanish",
    "fr": "French", "de": "German", "pt": "Portuguese", "ru": "Russian", "it": "Italian",
    "vi": "Vietnamese", "id": "Indonesian", "th": "Thai", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish",
}


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def load_dataset(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            records.extend(json.loads(line) for line in f if line.strip())
    return records


def dedupe_latest(rows: list[dict], key_fn) -> list[dict]:
    """Keep only the last row per key. Rows are appended chronologically, so a
    retried segment (failed, then later succeeded) leaves stale rows behind —
    downstream consumers must not average a failure and its successful retry
    together as if they were two segments."""
    latest = {}
    for r in rows:
        latest[key_fn(r)] = r
    return list(latest.values())


def filter_dataset(records: list[dict], pairs: set[str] | None, limit: int | None) -> list[dict]:
    if pairs:
        records = [r for r in records if f"{r['src_lang']}-{r['tgt_lang']}" in pairs]
    if limit:
        # cap per (src_lang, tgt_lang) direction, not globally, so a smoke run still covers every requested pair
        capped, counts = [], {}
        for r in records:
            key = (r["src_lang"], r["tgt_lang"])
            if counts.get(key, 0) >= limit:
                continue
            counts[key] = counts.get(key, 0) + 1
            capped.append(r)
        records = capped
    return records


class ResultCache:
    """Append-only jsonl cache keyed by (model, segment id); thread/coroutine-safe append.

    Only a *successful* row marks a key as seen — a failed attempt (throttled,
    timed out, etc.) must be retried on the next run, not silently skipped
    forever. A key can therefore have multiple rows on disk (failures followed
    by a success); consumers must dedupe to the last row per key (see
    `dedupe_latest`), not average every row as if each were a distinct segment.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seen: set[tuple[str, str]] = set()
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    row = json.loads(line)
                    if row.get("error") is None:
                        self.seen.add((row["model"], row["id"]))
        self._lock = asyncio.Lock()

    def has(self, model: str, seg_id: str) -> bool:
        return (model, seg_id) in self.seen

    async def append(self, row: dict):
        async with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row.get("error") is None:
                self.seen.add((row["model"], row["id"]))


def build_prompt(seg: dict) -> str:
    return PROMPT_TEMPLATE.format(
        src_lang=LANG_NAMES.get(seg["src_lang"], seg["src_lang"]),
        tgt_lang=LANG_NAMES.get(seg["tgt_lang"], seg["tgt_lang"]),
        src_text=seg["src_text"],
    )


async def call_bedrock(client, model_id: str, prompt: str, reasoning_effort: str | None = None) -> dict:
    # temperature=0 + a shared max-token cap so Bedrock isn't compared against
    # OpenAI/vLLM under different decoding conditions (Bedrock defaults to each
    # model's own sampling temperature — e.g. Nova defaults to ~0.7 — when
    # inferenceConfig is omitted, which was silently making every Bedrock model
    # non-deterministic and non-comparable).
    inference_config = {"maxTokens": MAX_OUTPUT_TOKENS}
    if model_id not in BEDROCK_NO_TEMPERATURE:
        inference_config["temperature"] = 0

    additional_fields = {}
    if reasoning_effort:
        # gpt-oss (and other reasoning-on-by-default Bedrock models) emit a
        # chain-of-thought unless dialed down — same rationale as grok-4.3's
        # mantle_reasoning_effort / Qwen3.6's enable_thinking: translation
        # doesn't need CoT, and leaving it on biases cost/latency vs the
        # non-reasoning roster. Field name verified live per model.
        additional_fields["reasoning_effort"] = reasoning_effort
    if model_id in BEDROCK_DISABLE_THINKING:
        additional_fields["thinking"] = {"type": "disabled"}
    kwargs = {"additionalModelRequestFields": additional_fields} if additional_fields else {}

    def _invoke():
        return client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig=inference_config,
            **kwargs,
        )

    resp = await asyncio.to_thread(_invoke)
    # Not content[0]: reasoning models put a reasoningContent block before the
    # text block, so pick the first block that actually carries text.
    text = next(b["text"] for b in resp["output"]["message"]["content"] if "text" in b)
    usage = resp["usage"]
    return {"text": text, "tokens_in": usage["inputTokens"], "tokens_out": usage["outputTokens"]}


async def call_openai(client, model_id: str, prompt: str, chat_template_kwargs: dict | None = None) -> dict:
    # chat_template_kwargs is for vLLM models whose chat template defaults to
    # emitting reasoning content (e.g. Qwen3.6's template wraps a <think> block
    # by default unless enable_thinking=False is passed) — passed through
    # vLLM's OpenAI-compatible extra_body, not a real OpenAI API parameter.
    extra_body = {"chat_template_kwargs": chat_template_kwargs} if chat_template_kwargs else {}
    resp = await client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,
        extra_body=extra_body,
    )
    text = resp.choices[0].message.content
    usage = resp.usage
    return {"text": text, "tokens_in": usage.prompt_tokens, "tokens_out": usage.completion_tokens}


def mantle_url(region: str) -> str:
    # NOT the plain /v1/responses path other Bedrock-hosted models use — every
    # OpenAI proprietary model (gpt-5.4/5.5/5.6-*) on bedrock-mantle requires
    # this openai/-prefixed path specifically; verified live, the plain path
    # 400s with "does not support the '/v1/responses' API".
    return f"https://bedrock-mantle.{region}.api.aws/openai/v1/responses"


async def call_mantle(
    session, region: str, model_id: str, prompt: str,
    response_format: dict | None = None, reasoning_effort: str | None = None,
) -> dict:
    """Calls proprietary models hosted on Bedrock's bedrock-mantle endpoint
    (OpenAI's gpt-5.4/5.5/gpt-5.6-sol/terra/luna, xAI's grok-4.3), authenticated
    with the caller's own AWS SigV4 credentials — no OPENAI_API_KEY or separate
    Bedrock API key needed. `session` is a boto3.Session (kept outside this
    function so its credential provider can refresh across many calls;
    freezing once at call time here is what makes each request pick up a
    refreshed token if the session's underlying credentials rotate)."""
    import httpx
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    payload = {"model": model_id, "input": [{"role": "user", "content": prompt}], "max_output_tokens": MAX_OUTPUT_TOKENS}
    if model_id not in MANTLE_NO_TEMPERATURE:
        payload["temperature"] = 0
    if response_format:
        payload["text"] = {"format": response_format}
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    body = json.dumps(payload)
    url = mantle_url(region)
    req = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(session.get_credentials().get_frozen_credentials(), "bedrock-mantle", region).add_auth(req)
    prepared = req.prepare()

    async with httpx.AsyncClient(timeout=120) as http:
        resp = await http.post(url, content=body, headers=dict(prepared.headers))
    resp.raise_for_status()
    data = resp.json()

    text = "".join(
        part["text"]
        for item in data.get("output", []) if item.get("type") == "message"
        for part in item.get("content", []) if part.get("type") == "output_text"
    )
    usage = data.get("usage", {})
    return {"text": text, "tokens_in": usage.get("input_tokens"), "tokens_out": usage.get("output_tokens")}


def make_client(model_cfg: dict, aws_region: str):
    if model_cfg["api"] == "bedrock":
        import boto3
        return boto3.client("bedrock-runtime", region_name=aws_region)
    elif model_cfg["api"] == "bedrock_mantle":
        import boto3
        return boto3.Session()
    else:
        from openai import AsyncOpenAI
        import os
        base_url = model_cfg.get("base_url")
        api_key = os.environ.get("OPENAI_API_KEY", "EMPTY" if base_url else None)
        if api_key is None:
            raise RuntimeError("OPENAI_API_KEY not set")
        return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=3)


async def run_model(model_cfg: dict, segments: list[dict], cache: ResultCache, aws_region: str, default_concurrency: int):
    name = model_cfg["name"]
    todo = [s for s in segments if not cache.has(name, s["id"])]
    if not todo:
        print(f"[{name}] all {len(segments)} segments cached, skipping")
        return
    try:
        client = make_client(model_cfg, aws_region)
    except Exception as e:
        print(f"[{name}] SKIPPED — client init failed: {e}")
        return

    sem = asyncio.Semaphore(model_cfg.get("concurrency", default_concurrency))

    async def one(seg: dict):
        async with sem:
            prompt = build_prompt(seg)
            t0 = time.monotonic()
            try:
                if model_cfg["api"] == "bedrock":
                    result = await call_bedrock(
                        client, model_cfg["model_id"], prompt,
                        reasoning_effort=model_cfg.get("bedrock_reasoning_effort"),
                    )
                elif model_cfg["api"] == "bedrock_mantle":
                    result = await call_mantle(
                        client, model_cfg.get("mantle_region", "us-east-1"), model_cfg["model_id"], prompt,
                        reasoning_effort=model_cfg.get("mantle_reasoning_effort"),
                    )
                else:
                    result = await call_openai(client, model_cfg["model_id"], prompt, model_cfg.get("chat_template_kwargs"))
                error = None
            except Exception as e:
                result = {"text": None, "tokens_in": None, "tokens_out": None}
                error = str(e)
            latency = time.monotonic() - t0
            await cache.append({
                "model": name, "id": seg["id"], "src_lang": seg["src_lang"], "tgt_lang": seg["tgt_lang"],
                "doc_type": seg["doc_type"], "output_text": result["text"],
                "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"],
                "latency_s": round(latency, 3), "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    print(f"[{name}] running {len(todo)} segments (concurrency={sem._value})")
    await asyncio.gather(*(one(s) for s in todo))


async def main_async(args):
    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    default_concurrency = scenario["concurrency_default"]

    dataset_paths = [Path(p) for p in args.dataset.split(",")] if args.dataset else [
        DATA_DIR / "flores.jsonl", DATA_DIR / "synthetic.jsonl",
    ]
    segments = load_dataset(dataset_paths)
    if not segments:
        raise SystemExit(f"no segments loaded from {dataset_paths} — run bench/dataset.py first or pass --dataset")

    pairs = set(args.pairs.split(",")) if args.pairs else None
    segments = filter_dataset(segments, pairs, args.limit)
    print(f"{len(segments)} segments selected")

    wanted_models = set(args.models.split(",")) if args.models else None
    models = [
        m for m in cfg["models"]
        if m.get("enabled", True) and (wanted_models is None or m["name"] in wanted_models)
    ]
    if not models:
        raise SystemExit("no models selected (check --models and config.toml `enabled` flags)")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    cache = ResultCache(RESULTS_DIR / run_id / "translations.jsonl")
    print(f"run_id={run_id} models={[m['name'] for m in models]}")

    started_at = datetime.now(timezone.utc).isoformat()
    for model_cfg in models:
        await run_model(model_cfg, segments, cache, cfg["aws"]["region"], default_concurrency)
    finished_at = datetime.now(timezone.utc).isoformat()

    write_manifest(run_id, cfg, scenario, models, segments, started_at, finished_at)
    print(f"done -> {cache.path}")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5
        )
        # on a repo with no commits yet, git exits non-zero but still prints the
        # literal string "HEAD" to stdout (the unresolved symbolic ref) — a
        # naive `stdout.strip() or None` treats that as a real commit hash.
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def write_manifest(run_id, cfg, scenario, models, segments, started_at, finished_at):
    """Reproducibility record for a run: what code/data/config produced it, so a
    result can be explained later ('why did this differ from last week's run?')."""
    manifest = {
        "run_id": run_id,
        "git_commit": _git_commit(),
        "prompt_sha256": _sha256_file(PROMPT_PATH),
        "rubric_sha256": _sha256_file(ROOT / "scenarios/translation/rubric.txt"),
        "dataset_segments": len(segments),
        "judge_models": [j["model_id"] for j in scenario["judges"]],
        "generation_parameters": {"temperature": 0, "max_tokens": MAX_OUTPUT_TOKENS},
        "models": [
            {
                "name": m["name"], "api": m["api"], "model_id": m["model_id"],
                "concurrency": m.get("concurrency", scenario["concurrency_default"]),
                "gpu_hourly_usd": m.get("gpu_hourly_usd"),
                "gpu_instance_type": m.get("gpu_instance_type"),
                "tensor_parallel_size": m.get("tensor_parallel_size"),
                "extra_vllm_args": m.get("extra_vllm_args"),
                "mantle_region": m.get("mantle_region"),
                "mantle_reasoning_effort": m.get("mantle_reasoning_effort"),
                "bedrock_reasoning_effort": m.get("bedrock_reasoning_effort"),
                # some OpenAI reasoning-tier models on bedrock-mantle, and
                # claude-sonnet-5 on plain Bedrock, reject `temperature`
                # outright — see MANTLE_NO_TEMPERATURE/BEDROCK_NO_TEMPERATURE.
                # Recorded per-model rather than assumed from
                # generation_parameters above, since it's a real exception to
                # the decoding-parity intent.
                "temperature_omitted": m["model_id"] in MANTLE_NO_TEMPERATURE or m["model_id"] in BEDROCK_NO_TEMPERATURE,
                "thinking_disabled": m["model_id"] in BEDROCK_DISABLE_THINKING,
                "warmup_excluded": False,  # throughput includes cold-start; not yet implemented
            }
            for m in models
        ],
        "started_at": started_at,
        "finished_at": finished_at,
    }
    (RESULTS_DIR / run_id / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", help="comma-separated model names (default: all enabled)")
    p.add_argument("--pairs", help="comma-separated src-tgt pairs e.g. ko-en,en-ko (default: all)")
    p.add_argument("--limit", type=int, help="max segments per direction (smoke runs)")
    p.add_argument("--dataset", help="comma-separated jsonl paths (default: data/flores.jsonl,data/synthetic.jsonl)")
    p.add_argument("--run-id", help="default: current UTC timestamp")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
