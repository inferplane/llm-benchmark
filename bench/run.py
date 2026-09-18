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
import math
import random
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
PROMPT_PATH = ROOT / "scenarios/translation/prompt.txt"
PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
MAX_OUTPUT_TOKENS = 4096  # shared cap for Bedrock + OpenAI/vLLM so no provider gets a bigger budget by default
REQUEST_TIMEOUT_S = 600  # a valid Grok response took 276s; allow completion without changing decoding
MAX_RETRY_DELAY_S = 30
TRANSIENT_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}

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
# claude-opus-4-8 (fable-5's content-filter fallback judge, same config
# section) also rejects it, same error.
BEDROCK_NO_TEMPERATURE = {"us.anthropic.claude-sonnet-5", "us.anthropic.claude-fable-5", "us.anthropic.claude-opus-4-8"}

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
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    self._record_latest(row)
        self._lock = asyncio.Lock()

    def _record_latest(self, row: dict):
        key = (row["model"], row["id"])
        success = all(row.get(field) is None for field in ("error", "translation_error", "judge_error"))
        # Judgment rows have scores instead of output_text. Legacy translation
        # successes have no response_status and remain valid without rewriting.
        if "output_text" in row or self.path.name == "translations.jsonl":
            text = row.get("output_text")
            success = success and isinstance(text, str) and bool(text.strip())
            success = success and row.get("response_status", "completed") == "completed"
        if success:
            self.seen.add(key)
        else:
            self.seen.discard(key)

    def has(self, model: str, seg_id: str) -> bool:
        return (model, seg_id) in self.seen

    async def append(self, row: dict):
        async with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._record_latest(row)


def build_prompt(seg: dict) -> str:
    return PROMPT_TEMPLATE.format(
        src_lang=LANG_NAMES.get(seg["src_lang"], seg["src_lang"]),
        tgt_lang=LANG_NAMES.get(seg["tgt_lang"], seg["tgt_lang"]),
        src_text=seg["src_text"],
    )


class ContentFilteredError(Exception):
    """Bedrock Converse returned stopReason == "content_filtered" (an empty
    content list — a real safety-system block, not a text/parsing failure).
    Verified live on claude-fable-5 as deterministic: the identical prompt
    hit the same verdict on 3/3 repeat calls, on FLORES sentences with no
    apparent sensitive content (e.g. tuberculosis statistics, Casablanca's
    naming history) — so callers must NOT treat this as a retriable error the
    way a timeout/500 is; blind retries never recover it. Distinguished from
    a plain crash so bench/judge.py's dual-judge scoring can let this judge
    abstain on the segment instead of failing the whole judgment."""


class InvalidResponseError(ValueError):
    """A provider response cannot count as a completed translation."""


class RunnerInputError(ValueError):
    """Controlled local validation messages safe to show without provider data."""


def _safe_identifier(value) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/=-]{0,199}", value):
        return value
    return None


def _retry_after_seconds(value) -> float | None:
    """Accept seconds or an HTTP date, never unbounded or nonfinite delays."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(str(value))
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, MAX_RETRY_DELAY_S)


def failure_details(exception: Exception) -> dict:
    """Classify failures without serializing bodies, URLs, prompts or signed headers.

    Keep the original exception class even when its message is empty. Provider
    messages can echo the request; use safe, locally generated descriptions and
    only allowlisted response metadata instead.
    """
    import httpx
    from botocore.exceptions import (
        ClientError, ConnectionClosedError, ConnectTimeoutError,
        EndpointConnectionError, ReadTimeoutError,
    )
    from openai import APIConnectionError, APIStatusError

    kind = type(exception).__name__
    details = {"type": kind, "message": f"{kind} during model request", "retryable": False}
    if isinstance(exception, ContentFilteredError):
        details["message"] = "Content was refused by the provider safety system"
    elif isinstance(exception, InvalidResponseError):
        details["message"] = "Provider response was not completed, nonempty text with valid usage"
    elif isinstance(exception, (httpx.TimeoutException, ConnectTimeoutError, ReadTimeoutError)):
        details.update(message=f"{kind}: request timed out", retryable=True)
    elif isinstance(exception, (
        httpx.NetworkError, httpx.RemoteProtocolError, EndpointConnectionError,
        ConnectionClosedError, APIConnectionError,
    )):
        details.update(message=f"{kind}: transport failed", retryable=True)

    headers = {}
    if isinstance(exception, (httpx.HTTPStatusError, APIStatusError)):
        response = exception.response
        status = response.status_code
        details.update(
            http_status=status, message=f"{kind}: provider returned HTTP {status}",
            retryable=status in TRANSIENT_HTTP_STATUSES,
        )
        headers = response.headers
    elif isinstance(exception, ClientError):
        # Generic classification is confined to this cross-provider error
        # boundary; provider functions preserve the actual SDK exception.
        metadata = exception.response.get("ResponseMetadata", {})
        code = exception.response.get("Error", {}).get("Code")
        status = metadata.get("HTTPStatusCode")
        transient_codes = {
            "Throttling", "ThrottlingException", "TooManyRequestsException",
            "RequestTimeout", "RequestTimeoutException", "ModelTimeoutException",
            "ServiceUnavailable", "ServiceUnavailableException",
            "InternalFailure", "InternalServerException", "InternalServerError",
        }
        fatal_codes = {
            "AccessDenied", "AccessDeniedException", "UnauthorizedException",
            "UnrecognizedClientException", "InvalidClientTokenId",
            "ExpiredToken", "ExpiredTokenException", "SignatureDoesNotMatch",
            "ValidationException", "ValidationError", "InvalidParameterException",
            "ContentFilteredException", "ContentPolicyViolationException",
        }
        details["retryable"] = code not in fatal_codes and (
            code in transient_codes or status in TRANSIENT_HTTP_STATUSES
        )
        if isinstance(status, int):
            details["http_status"] = status
        if safe_code := _safe_identifier(code):
            details["code"] = safe_code
            details["message"] = f"{kind}: provider returned {safe_code}"
        if request_id := _safe_identifier(metadata.get("RequestId")):
            details["request_id"] = request_id
        headers = metadata.get("HTTPHeaders", {})

    for header in ("x-amzn-requestid", "x-amzn-request-id", "x-request-id"):
        if request_id := _safe_identifier(headers.get(header)):
            details["request_id"] = request_id
            break
    if (delay := _retry_after_seconds(headers.get("retry-after"))) is not None:
        details["retry_after_s"] = delay

    # call_mantle attaches only these fields, then re-raises the same exception.
    context = getattr(exception, "_request_context", {})
    if context.get("phase") in {
        "credentials", "request_headers", "response_headers", "response_body", "response_validation",
    }:
        details["phase"] = context["phase"]
    if request_id := _safe_identifier(context.get("request_id")):
        details["request_id"] = request_id
    if isinstance(context.get("http_status"), int):
        details["http_status"] = context["http_status"]
    response_status = context.get("response_status")
    if isinstance(response_status, str) and response_status in {
        "completed", "failed", "incomplete", "in_progress", "queued", "cancelled",
    }:
        details["response_status"] = response_status
    return details


def _validate_result(result: dict):
    text = result.get("text")
    if not isinstance(text, str) or not text.strip():
        raise InvalidResponseError("empty output")
    if result.get("response_status", "completed") != "completed":
        raise InvalidResponseError("nonterminal output")
    for field in ("tokens_in", "tokens_out"):
        value = result.get(field)
        if type(value) is not int or value < 0:
            raise InvalidResponseError("invalid usage")


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
    if resp.get("stopReason") == "content_filtered":
        raise ContentFilteredError(f"content filtered by Bedrock safety system for model {model_id}")
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


async def call_translate(client, src_lang: str, tgt_lang: str, src_text: str) -> dict:
    """Amazon Translate's TranslateText — a managed, non-LLM MT baseline. No
    prompt/temperature/tokens: it's billed per INPUT character (not tokens),
    verified live against aws.amazon.com/translate/pricing and
    docs.aws.amazon.com/translate/latest/dg/what-is-limits.html (10,000-byte
    synchronous input cap — well above this dataset's longest source segment,
    ~5KB). Returns char counts under the tokens_in/tokens_out keys so it flows
    through the same ResultCache/report.py cost path as every LLM candidate;
    bench/report.py's compute_cost reads price_per_char instead of
    price_in/price_out for this api type and ignores tokens_out for pricing
    (there IS no separate "output" price), but still stores it for parity
    with the other rows' schema and any token-count-based diagnostics.
    boto3 has no async client, so the synchronous call is offloaded via
    asyncio.to_thread — same pattern as call_bedrock."""
    def _invoke():
        return client.translate_text(
            Text=src_text, SourceLanguageCode=src_lang, TargetLanguageCode=tgt_lang,
        )

    resp = await asyncio.to_thread(_invoke)
    text = resp["TranslatedText"]
    return {"text": text, "tokens_in": len(src_text), "tokens_out": len(text)}


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
    from botocore.exceptions import NoCredentialsError

    payload = {"model": model_id, "input": [{"role": "user", "content": prompt}], "max_output_tokens": MAX_OUTPUT_TOKENS}
    if model_id not in MANTLE_NO_TEMPERATURE:
        payload["temperature"] = 0
    if response_format:
        payload["text"] = {"format": response_format}
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    context = {"phase": "credentials"}
    try:
        body = json.dumps(payload)
        url = mantle_url(region)
        req = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
        credentials = session.get_credentials()
        if credentials is None:
            raise NoCredentialsError()
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-mantle", region).add_auth(req)
        prepared = req.prepare()

        context["phase"] = "request_headers"
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as http:
            # Stream only at the transport layer so response headers/request ID
            # survive a stalled body. The model still receives a nonstreaming
            # Responses request, with exactly the original generation settings.
            async with http.stream("POST", url, content=body, headers=dict(prepared.headers)) as resp:
                context.update(phase="response_headers", http_status=resp.status_code)
                for header in ("x-amzn-requestid", "x-amzn-request-id", "x-request-id"):
                    if request_id := _safe_identifier(resp.headers.get(header)):
                        context["request_id"] = request_id
                        break
                resp.raise_for_status()
                context["phase"] = "response_body"
                await resp.aread()
                context["phase"] = "response_validation"
                data = resp.json()

        if not isinstance(data, dict):
            raise InvalidResponseError("response is not an object")
        context["response_status"] = data.get("status")
        output = data.get("output")
        if not isinstance(output, list):
            raise InvalidResponseError("output is not a list")
        text_parts = []
        for item in output:
            if not isinstance(item, dict):
                raise InvalidResponseError("invalid output item")
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                raise InvalidResponseError("invalid message content")
            for part in content:
                if not isinstance(part, dict):
                    raise InvalidResponseError("invalid content part")
                if part.get("type") == "refusal":
                    raise ContentFilteredError("Mantle content refusal")
                if part.get("type") == "output_text":
                    if not isinstance(part.get("text"), str):
                        raise InvalidResponseError("invalid output text")
                    text_parts.append(part["text"])
            if item.get("status", "completed") != "completed":
                raise InvalidResponseError("nonterminal message")
        if data.get("status") != "completed" or data.get("error") is not None:
            raise InvalidResponseError("nonterminal or failed response")
        usage = data.get("usage")
        if not isinstance(usage, dict):
            raise InvalidResponseError("missing usage")
        result = {
            "text": "".join(text_parts),
            "tokens_in": usage.get("input_tokens"), "tokens_out": usage.get("output_tokens"),
            "response_status": "completed", "http_status": context["http_status"],
        }
        if "request_id" in context:
            result["request_id"] = context["request_id"]
        if response_id := _safe_identifier(data.get("id")):
            result["response_id"] = response_id
        _validate_result(result)
        return result
    except Exception as error:
        error._request_context = context
        raise


def make_client(model_cfg: dict, aws_region: str):
    if model_cfg["api"] == "bedrock":
        import boto3
        from botocore.config import Config
        options = {"config": Config(retries={"total_max_attempts": 1, "mode": "standard"})} if "request_max_attempts" in model_cfg else {}
        return boto3.client(
            "bedrock-runtime", region_name=aws_region,
            **options,
        )
    elif model_cfg["api"] == "bedrock_mantle":
        import boto3
        return boto3.Session()
    elif model_cfg["api"] == "translate":
        import boto3
        from botocore.config import Config
        options = {"config": Config(retries={"total_max_attempts": 1, "mode": "standard"})} if "request_max_attempts" in model_cfg else {}
        return boto3.client(
            "translate", region_name=model_cfg.get("translate_region", aws_region),
            **options,
        )
    else:
        from openai import AsyncOpenAI
        import os
        base_url = model_cfg.get("base_url")
        api_key = os.environ.get("OPENAI_API_KEY", "EMPTY" if base_url else None)
        if api_key is None:
            raise RuntimeError("OPENAI_API_KEY not set")
        # Explicit outer retry policies own the attempt trail. Other models
        # retain their existing SDK retry behavior.
        return AsyncOpenAI(api_key=api_key, base_url=base_url,
                           max_retries=0 if "request_max_attempts" in model_cfg else 3)


async def run_model(model_cfg: dict, segments: list[dict], cache: ResultCache, aws_region: str, default_concurrency: int,
                    *, prompt_builder=None):
    name = model_cfg["name"]
    segments = dedupe_latest(segments, lambda seg: seg["id"])
    todo = [s for s in segments if not cache.has(name, s["id"])]
    summary = {
        "model": name, "requested": len(segments), "cached": len(segments) - len(todo),
        "successful": len(segments) - len(todo), "failed": len(todo), "request_attempts": 0,
    }
    if not todo:
        print(f"[{name}] all {len(segments)} segments cached, skipping")
        return summary
    try:
        max_attempts = model_cfg.get("request_max_attempts", 1)
        concurrency = model_cfg.get("concurrency", default_concurrency)
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("request_max_attempts must be a positive integer")
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError("concurrency must be a positive integer")
        client = make_client(model_cfg, aws_region)
    except Exception as e:
        details = failure_details(e)
        summary["client_error_details"] = details
        print(f"[{name}] client init failed: {details['message']}")
        return summary

    sem = asyncio.Semaphore(concurrency)

    async def one(seg: dict):
        for attempt in range(1, max_attempts + 1):
            details = None
            async with sem:
                t0 = time.monotonic()
                summary["request_attempts"] += 1
                try:
                    # TranslateText uses raw source text instead of a prompt.
                    prompt = None if model_cfg["api"] == "translate" else (prompt_builder or build_prompt)(seg)
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
                    elif model_cfg["api"] == "translate":
                        result = await call_translate(client, seg["src_lang"], seg["tgt_lang"], seg["src_text"])
                    else:
                        result = await call_openai(client, model_cfg["model_id"], prompt, model_cfg.get("chat_template_kwargs"))
                    _validate_result(result)
                except Exception as e:
                    result = {"text": None, "tokens_in": None, "tokens_out": None}
                    details = failure_details(e)
                latency = time.monotonic() - t0
                row = {
                    "model": name, "id": seg["id"], "src_lang": seg["src_lang"], "tgt_lang": seg["tgt_lang"],
                    "doc_type": seg["doc_type"], "output_text": result["text"],
                    "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"],
                    "latency_s": round(latency, 3), "error": details["message"] if details else None,
                    "request_attempt": attempt, "request_max_attempts": max_attempts,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                if details:
                    row["translation_error_details"] = details
                else:
                    for field in ("request_id", "response_id", "response_status", "http_status"):
                        if field in result:
                            row[field] = result[field]
                # Append before deciding on a retry: every failed call survives
                # retry exhaustion, interruption, and a subsequent resume.
                await cache.append(row)
            if details is None:
                summary["successful"] += 1
                summary["failed"] -= 1
                return
            if not details["retryable"] or attempt == max_attempts:
                return
            delay = min(MAX_RETRY_DELAY_S, random.uniform(0.5, 1.5) * 2 ** min(attempt - 1, 6))
            delay = max(delay, details.get("retry_after_s", 0))
            # Release the concurrency slot while backing off.
            await asyncio.sleep(delay)

    print(f"[{name}] running {len(todo)} segments (concurrency={concurrency}, max_attempts={max_attempts})")
    try:
        await asyncio.gather(*(one(s) for s in todo))
    finally:
        # Reuse one client for the model, then release its connection pool.
        if model_cfg["api"] == "openai" and hasattr(client, "close"):
            await client.close()
        elif model_cfg["api"] in {"bedrock", "translate"} and hasattr(client, "close"):
            client.close()
    return summary


async def main_async(args):
    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    default_concurrency = scenario["concurrency_default"]

    dataset_paths = [Path(p) for p in args.dataset.split(",")] if args.dataset else [
        DATA_DIR / "flores.jsonl", DATA_DIR / "synthetic.jsonl",
    ]
    segments = load_dataset(dataset_paths)
    if not segments:
        raise RunnerInputError("no segments loaded; run bench/dataset.py first or pass --dataset")

    pairs = set(args.pairs.split(",")) if args.pairs else None
    segments = filter_dataset(segments, pairs, args.limit)
    segments = dedupe_latest(segments, lambda seg: seg["id"])
    if not segments:
        raise RunnerInputError("no segments selected; check --pairs and --limit")
    print(f"{len(segments)} segments selected")

    wanted_models = set(args.models.split(",")) if args.models else None
    models = [
        m for m in cfg["models"]
        if m.get("enabled", True) and (wanted_models is None or m["name"] in wanted_models)
    ]
    if not models:
        raise RunnerInputError("no models selected (check --models and config.toml enabled flags)")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    cache = ResultCache(RESULTS_DIR / run_id / "translations.jsonl")
    print(f"run_id={run_id} models={[m['name'] for m in models]}")

    started_at = datetime.now(timezone.utc).isoformat()
    completions = []
    for model_cfg in models:
        completions.append(await run_model(model_cfg, segments, cache, cfg["aws"]["region"], default_concurrency))
    finished_at = datetime.now(timezone.utc).isoformat()
    summary = {
        field: sum(completion[field] for completion in completions)
        for field in ("requested", "successful", "failed", "cached", "request_attempts")
    }
    summary["models"] = completions
    # An explicitly requested disabled/unknown model must not silently vanish.
    unavailable = (wanted_models or set()) - {model["name"] for model in models}
    if unavailable:
        summary["unavailable_models"] = sorted(unavailable)
        summary["requested"] += len(unavailable) * len(segments)
        summary["failed"] += len(unavailable) * len(segments)
    write_manifest(
        run_id, cfg, scenario, models, segments, started_at, finished_at,
        completion_summary=summary,
    )
    print(f"successful={summary['successful']} failed={summary['failed']} -> {cache.path}")
    return summary


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


def write_manifest(run_id, cfg, scenario, models, segments, started_at, finished_at, completion_summary=None):
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
                "request_timeout_s": REQUEST_TIMEOUT_S if m["api"] == "bedrock_mantle" else None,
                "mantle_background": m.get("mantle_background", False),
                "request_max_attempts": m.get("request_max_attempts", 1),
                "bedrock_reasoning_effort": m.get("bedrock_reasoning_effort"),
                "translate_region": m.get("translate_region"),
                "price_per_char": m.get("price_per_char"),
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
    if completion_summary is not None:
        manifest["completion_summary"] = completion_summary
    path = RESULTS_DIR / run_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        history = previous.get("executions") or [previous]
    # Keep flat snapshots, including the complete legacy manifest on first
    # resume. Top-level fields still describe the latest invocation for callers
    # using the original write_manifest signature/schema.
    manifest["executions"] = [*history, dict(manifest)]
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _selfcheck_diagnostics():
    """Offline checks: blank exceptions must retain their class and retry policy."""
    import httpx
    from botocore.exceptions import ClientError, NoCredentialsError, ParamValidationError

    assert callable(globals().get("failure_details")), "failure_details export is missing"
    for error, retryable in [
        (httpx.ReadTimeout(""), True),
        (httpx.ConnectTimeout(""), True),
        (httpx.ConnectError(""), True),
        (httpx.RemoteProtocolError(""), True),
        (ContentFilteredError("private prompt"), False),
        (NoCredentialsError(), False),
        (ParamValidationError(report="private prompt"), False),
        (ValueError("Authorization: private prompt"), False),
    ]:
        details = failure_details(error)
        assert details["type"] == type(error).__name__, details
        assert details["message"].strip() and details["retryable"] is retryable, details
        assert "private prompt" not in json.dumps(details), details

    request = httpx.Request("POST", "https://example.invalid/?signature=private")
    for status in [400, 401, 403, 404, 408, 422, 429, 500, 502, 503, 504]:
        response = httpx.Response(
            status, request=request, text="private prompt",
            headers={"x-amzn-requestid": "req-check", "retry-after": "2"},
        )
        details = failure_details(httpx.HTTPStatusError("private prompt", request=request, response=response))
        assert details["retryable"] is (status in {408, 429, 500, 502, 503, 504}), details
        assert details["http_status"] == status and details["request_id"] == "req-check", details
        assert details["retry_after_s"] == 2, details
        assert "private" not in json.dumps(details), details
    for value in ["nan", "inf", "-1", "private prompt"]:
        response = httpx.Response(429, request=request, headers={"retry-after": value})
        details = failure_details(httpx.HTTPStatusError("", request=request, response=response))
        assert "retry_after_s" not in details, details
    for code, status, retryable in [
        ("ThrottlingException", 400, True),
        ("ServiceUnavailableException", 503, True),
        ("ValidationException", 400, False),
        ("AccessDeniedException", 403, False),
        ("ValidationException", 500, False),
    ]:
        details = failure_details(ClientError({
            "Error": {"Code": code, "Message": "private prompt"},
            "ResponseMetadata": {"HTTPStatusCode": status, "RequestId": "aws-check"},
        }, "Converse"))
        assert details["retryable"] is retryable and details["request_id"] == "aws-check", details
        assert "private prompt" not in json.dumps(details), details


def _selfcheck_cache():
    """Latest failure/empty output must invalidate success; legacy judgments still work."""
    import tempfile

    async def check(directory):
        path = Path(directory) / "translations.jsonl"
        cache = ResultCache(path)
        good = {"model": "check", "id": "one", "output_text": "translated", "error": None}
        await cache.append(good)
        assert cache.has("check", "one"), "legacy successful translations must remain reusable"
        await cache.append({**good, "error": ""})
        assert not cache.has("check", "one"), "latest failure must override historical success"
        assert not ResultCache(path).has("check", "one"), "reload must use the same latest-row rule"
        await cache.append({**good, "output_text": "   "})
        assert not cache.has("check", "one"), "empty translation cannot be cached as done"
        await cache.append({**good, "response_status": "incomplete"})
        assert not cache.has("check", "one"), "incomplete translation cannot be cached as done"
        await cache.append(good)
        assert ResultCache(path).has("check", "one")
        judge_cache = ResultCache(Path(directory) / "judgments.jsonl")
        await judge_cache.append({"model": "check", "id": "one", "judge_overall": 4, "error": None})
        assert judge_cache.has("check", "one"), "judge rows have no output_text"

    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(check(directory))


def _selfcheck_mantle():
    """Exercise real signing/HTTP parsing with an in-memory HTTP transport."""
    import httpx
    from botocore.credentials import Credentials
    from types import SimpleNamespace
    from unittest.mock import patch

    session = SimpleNamespace(get_credentials=lambda: Credentials("offline", "offline"))
    client_class = httpx.AsyncClient
    completed = {
        "id": "response-check", "status": "completed", "error": None,
        "output": [{"type": "message", "status": "completed", "content": [
            {"type": "output_text", "text": "translated"},
        ]}],
        "usage": {"input_tokens": 9, "output_tokens": 3},
    }

    async def invoke(response_or_error):
        def handle(request):
            payload = json.loads(request.content)
            assert payload["temperature"] == 0 and payload["max_output_tokens"] == 4096
            assert payload["reasoning"] == {"effort": "low"}
            assert payload.get("stream", False) is False, "transport streaming must not alter generation"
            assert request.extensions["timeout"]["read"] == 600
            if isinstance(response_or_error, Exception):
                raise response_or_error
            return response_or_error

        transport = httpx.MockTransport(handle)
        with patch("httpx.AsyncClient", side_effect=lambda **kwargs: client_class(transport=transport, **kwargs)):
            return await call_mantle(
                session, "us-west-2", "xai.grok-4.6", "offline prompt", reasoning_effort="low",
            )

    async def check():
        # The pre-fix implementation silently accepted all these as successes.
        invalid = [
            {**completed, "status": "incomplete"},
            {**completed, "status": "failed", "error": {"code": "invalid_prompt", "message": "private"}},
            {**completed, "status": "in_progress"},
            {**completed, "status": None},
            {**completed, "status": []},
            {**completed, "output": []},
            {**completed, "output": [{"type": "message", "content": [{"type": "output_text", "text": " "}]}]},
            {**completed, "output": [{"type": "message", "status": "in_progress", "content": [
                {"type": "output_text", "text": "partial"},
            ]}]},
            {**completed, "usage": None},
            {**completed, "usage": {"input_tokens": 9, "output_tokens": None}},
            {**completed, "usage": {"input_tokens": 9, "output_tokens": -1}},
            {**completed, "usage": {"input_tokens": True, "output_tokens": 3}},
        ]
        for payload in invalid:
            try:
                await invoke(httpx.Response(200, json=payload, headers={"x-request-id": "req-invalid"}))
            except InvalidResponseError as error:
                details = failure_details(error)
                assert details["phase"] == "response_validation" and details["request_id"] == "req-invalid"
            else:
                raise AssertionError("invalid Mantle response was accepted as success")
        result = await invoke(httpx.Response(200, json=completed, headers={"x-request-id": "req-success"}))
        assert result["text"] == "translated" and result["tokens_out"] == 3
        assert result["request_id"] == "req-success" and result["response_status"] == "completed"
        refusal = {**completed, "output": [{"type": "message", "content": [
            {"type": "refusal", "refusal": "private prompt"},
        ]}]}
        try:
            await invoke(httpx.Response(200, json=refusal))
        except ContentFilteredError as error:
            assert failure_details(error)["retryable"] is False
        else:
            raise AssertionError("content refusal was accepted")
        try:
            await invoke(httpx.ReadTimeout(""))
        except httpx.ReadTimeout as error:
            assert failure_details(error)["phase"] == "request_headers"
        else:
            raise AssertionError("transport timeout was swallowed")

        class BrokenBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                raise httpx.ReadTimeout("")
                yield b""  # mark as an async generator

        try:
            await invoke(httpx.Response(200, stream=BrokenBody(), headers={"x-amzn-requestid": "req-body"}))
        except httpx.ReadTimeout as error:
            details = failure_details(error)
            assert details["phase"] == "response_body" and details["request_id"] == "req-body", details
            assert details["http_status"] == 200
        else:
            raise AssertionError("response body timeout was swallowed")

    asyncio.run(check())


def _selfcheck_runner():
    """Retries must leave an audit trail, resume safely, and report unfinished work."""
    import httpx
    import tempfile
    from unittest.mock import AsyncMock, patch

    model = {
        "name": "offline", "api": "bedrock_mantle", "model_id": "xai.grok-4.6",
        "request_max_attempts": 4,
    }
    segment = {"id": "one", "src_lang": "ko", "tgt_lang": "en", "src_text": "offline", "doc_type": "flores"}
    success = {
        "text": "translated", "tokens_in": 9, "tokens_out": 3,
        "response_status": "completed", "request_id": "req-check",
    }
    request = httpx.Request("POST", "https://example.invalid")
    bad_request = httpx.HTTPStatusError(
        "private prompt", request=request, response=httpx.Response(400, request=request),
    )

    async def no_wait(seconds):
        assert 0 <= seconds <= 30, "retry sleep must be bounded"

    async def check(directory):
        cache = ResultCache(Path(directory) / "recovery" / "translations.jsonl")
        with (
            patch(__name__ + ".make_client", return_value=object()),
            patch(__name__ + ".call_mantle", new=AsyncMock(side_effect=[httpx.ReadTimeout(""), success])),
            patch("asyncio.sleep", new=no_wait),
        ):
            summary = await run_model(model, [segment], cache, "us-west-2", 1)
        rows = load_dataset([cache.path])
        assert len(rows) == 2, "a transient error must retry and retain both attempts"
        assert rows[0]["translation_error_details"]["type"] == "ReadTimeout" and rows[0]["error"]
        assert rows[1]["error"] is None and rows[1]["request_id"] == "req-check"
        assert [row["request_attempt"] for row in rows] == [1, 2]
        assert summary["requested"] == 1 and summary["successful"] == 1
        assert summary["failed"] == 0 and summary["request_attempts"] == 2
        with patch(__name__ + ".make_client", side_effect=AssertionError("resume must not initialize a client")):
            summary = await run_model(model, [segment], ResultCache(cache.path), "us-west-2", 1)
        assert summary["cached"] == 1 and summary["request_attempts"] == 0 and summary["failed"] == 0
        assert len(load_dataset([cache.path])) == 2

        for label, cfg, outcome, attempts in [
            ("fatal", model, bad_request, 1),
            ("exhausted", model, httpx.ReadTimeout(""), 4),
            ("default", {k: v for k, v in model.items() if k != "request_max_attempts"}, httpx.ReadTimeout(""), 1),
            ("empty", model, {**success, "text": ""}, 1),
        ]:
            cache = ResultCache(Path(directory) / label / "translations.jsonl")
            fake_call = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
            with (
                patch(__name__ + ".make_client", return_value=object()),
                patch(__name__ + ".call_mantle", new=fake_call),
                patch("asyncio.sleep", new=no_wait),
            ):
                summary = await run_model(cfg, [segment], cache, "us-west-2", 1)
            rows = load_dataset([cache.path])
            assert len(rows) == attempts and summary["request_attempts"] == attempts, (label, rows, summary)
            assert summary["failed"] == 1 and summary["successful"] == 0, summary
            assert all(row["error"] and row["translation_error_details"]["type"] for row in rows)
            assert not ResultCache(cache.path).has("offline", "one")

        with patch(__name__ + ".make_client", side_effect=RuntimeError("private credentials")):
            summary = await run_model(model, [segment], ResultCache(Path(directory) / "init.jsonl"), "us-west-2", 1)
        assert summary["failed"] == 1 and summary["request_attempts"] == 0
        assert summary["client_error_details"]["type"] == "RuntimeError"
        assert "private credentials" not in json.dumps(summary)

    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(check(directory))


def _selfcheck_client_attempts():
    """Explicit outer policies own retries; other models retain SDK behavior."""
    from unittest.mock import patch

    with patch("boto3.client", return_value=object()) as client:
        for api in ("bedrock", "translate"):
            make_client({"api": api}, "us-west-2")
            assert "config" not in client.call_args.kwargs, "Do not disable existing SDK retries implicitly"
            make_client({"api": api, "request_max_attempts": 4}, "us-west-2")
            assert client.call_args.kwargs["config"].retries["total_max_attempts"] == 1
    with patch("openai.AsyncOpenAI", return_value=object()) as client:
        make_client({"api": "openai", "base_url": "http://offline.invalid"}, "us-west-2")
        assert client.call_args.kwargs["max_retries"] == 3
        make_client({"api": "openai", "base_url": "http://offline.invalid", "request_max_attempts": 4}, "us-west-2")
        assert client.call_args.kwargs["max_retries"] == 0


def _selfcheck_manifest():
    """Resuming must preserve prior provenance while exposing effective retry settings."""
    import tempfile
    from unittest.mock import patch

    models = [
        {"name": "offline", "api": "bedrock_mantle", "model_id": "xai.grok-4.6", "request_max_attempts": 4},
        {"name": "legacy", "api": "bedrock", "model_id": "offline"},
    ]
    scenario = {"concurrency_default": 1, "judges": []}
    with tempfile.TemporaryDirectory() as directory, patch(__name__ + ".RESULTS_DIR", Path(directory)):
        run_dir = Path(directory) / "check"
        run_dir.mkdir()
        path = run_dir / "manifest.json"
        original = {"run_id": "check", "started_at": "original-start", "custom_original_evidence": {"keep": True}}
        path.write_text(json.dumps(original), encoding="utf-8")
        write_manifest("check", {}, scenario, models, [], "new-start", "new-end")
        manifest = json.loads(path.read_text())
        assert manifest.get("executions", [None])[0] == original, "resuming must preserve the original manifest"
        assert manifest["models"][0]["request_timeout_s"] == 600
        assert manifest["models"][0]["request_max_attempts"] == 4
        assert manifest["models"][1]["request_max_attempts"] == 1
        assert manifest["generation_parameters"] == {"temperature": 0, "max_tokens": 4096}
        write_manifest(
            "check", {}, scenario, models, [], "third-start", "third-end",
            completion_summary={"requested": 1, "successful": 0, "failed": 1, "request_attempts": 4},
        )
        manifest = json.loads(path.read_text())
        assert len(manifest["executions"]) == 3 and manifest["executions"][0] == original
        assert manifest["executions"][1]["started_at"] == "new-start"
        assert manifest["completion_summary"]["failed"] == 1
        assert all("executions" not in execution for execution in manifest["executions"])


def _selfcheck_cli():
    """A failed client must produce a manifest and nonzero CLI status."""
    import contextlib
    import io
    import tempfile
    from types import SimpleNamespace
    from unittest.mock import patch

    model = {"name": "offline", "api": "bedrock_mantle", "model_id": "xai.grok-4.6"}
    cfg = {"aws": {"region": "us-west-2"}, "scenario": {"translation": {
        "concurrency_default": 1, "judges": [],
    }}, "models": [model]}
    segment = {"id": "one", "src_lang": "ko", "tgt_lang": "en", "src_text": "offline", "doc_type": "flores"}
    with (
        tempfile.TemporaryDirectory() as directory,
        patch(__name__ + ".RESULTS_DIR", Path(directory)),
        patch(__name__ + ".load_config", return_value=cfg),
        patch(__name__ + ".make_client", side_effect=RuntimeError("private credentials")),
    ):
        dataset = Path(directory) / "offline.jsonl"
        dataset.write_text(json.dumps(segment) + "\n", encoding="utf-8")
        args = SimpleNamespace(dataset=str(dataset), pairs=None, limit=None, models="offline", run_id="async-failed")
        summary = asyncio.run(main_async(args))
        assert isinstance(summary, dict) and summary["failed"] == 1, "main_async must report unfinished work"
        manifest = json.loads((Path(directory) / "async-failed" / "manifest.json").read_text())
        assert manifest["completion_summary"]["failed"] == 1
        assert main(["--dataset", str(dataset), "--models", "offline", "--run-id", "cli-failed"]) == 1
        assert (Path(directory) / "cli-failed" / "manifest.json").exists()
        cache = ResultCache(Path(directory) / "cached" / "translations.jsonl")
        asyncio.run(cache.append({**segment, "model": "offline", "output_text": "translated", "error": None}))
        assert main(["--dataset", str(dataset), "--models", "offline", "--run-id", "cached"]) == 0
        cases = [
            (["--dataset", str(Path(directory) / "missing.jsonl")], "no segments loaded"),
            (["--dataset", str(dataset), "--pairs", "en-ja"], "no segments selected"),
            (["--dataset", str(dataset), "--models", "unknown"], "no models selected"),
        ]
        for arguments, expected in cases:
            error_output = io.StringIO()
            with contextlib.redirect_stderr(error_output):
                assert main(arguments) == 1
            assert expected in error_output.getvalue(), error_output.getvalue()
        with patch(__name__ + ".main_async", side_effect=ValueError("private provider payload")):
            error_output = io.StringIO()
            with contextlib.redirect_stderr(error_output):
                assert main([]) == 1
            assert "private provider payload" not in error_output.getvalue()


def _selfcheck():
    for check in (
        _selfcheck_diagnostics, _selfcheck_cache, _selfcheck_mantle,
        _selfcheck_runner, _selfcheck_client_attempts, _selfcheck_manifest, _selfcheck_cli,
    ):
        check()
        print(f"PASS {check.__name__}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", help="comma-separated model names (default: all enabled)")
    p.add_argument("--pairs", help="comma-separated src-tgt pairs e.g. ko-en,en-ko (default: all)")
    p.add_argument("--limit", type=int, help="max segments per direction (smoke runs)")
    p.add_argument("--dataset", help="comma-separated jsonl paths (default: data/flores.jsonl,data/synthetic.jsonl)")
    p.add_argument("--run-id", help="default: current UTC timestamp")
    p.add_argument("--selfcheck", action="store_true", help="run offline reliability checks without API calls")
    args = p.parse_args(argv)
    if args.selfcheck:
        _selfcheck()
        return 0
    try:
        summary = asyncio.run(main_async(args))
    except RunnerInputError as error:
        print(f"runner failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"runner failed: {failure_details(error)['message']}", file=sys.stderr)
        return 1
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
