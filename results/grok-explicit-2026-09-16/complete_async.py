"""Finish missing translations with durable Mantle background request IDs.

Run only after stopping the blocking reproduction driver. The inference
parameters and frozen inputs are unchanged; only response delivery changes.
https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-mantle.html
"""

import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT))

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from bench.run import (
    MAX_OUTPUT_TOKENS, REQUEST_TIMEOUT_S, ContentFilteredError, InvalidResponseError,
    ResultCache, _validate_result, build_prompt, failure_details, load_config,
    load_dataset, mantle_url, write_manifest,
)
from reproduce import execution_lock

WAIT_LIMIT_S = 3600
POLL_INTERVAL_S = 10
SUBMIT_INTERVAL_S = 2
MAX_OUTSTANDING_JOBS = 64


def stamp():
    return datetime.now(timezone.utc).isoformat()


async def execute():
    config = load_config()
    protocol = json.loads((RUN / "protocol.json").read_text())
    for key, path in [
        ("config_sha256", ROOT / "config.toml"),
        ("prompt_sha256", ROOT / "scenarios/translation/prompt.txt"),
        ("rubric_sha256", ROOT / "scenarios/translation/rubric.txt"),
        ("dataset_sha256", RUN / "dataset.jsonl"),
    ]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != protocol[key]:
            raise RuntimeError(f"{key} differs from the frozen protocol")
    protocol_sha = hashlib.sha256((RUN / "protocol.json").read_bytes()).hexdigest()
    if json.loads((RUN / "execution.json").read_text())["protocol_sha256"] != protocol_sha:
        raise RuntimeError("Execution protocol changed")

    model_lookup = {m["name"]: m for m in config["models"]}
    models = [{**model_lookup[name], "mantle_background": True} for name in protocol["models"]]
    segments = load_dataset([RUN / "dataset.jsonl"])
    assert len(segments) == 3300 and MAX_OUTPUT_TOKENS == 4096
    for model in models:
        assert model["api"] == "bedrock_mantle" and model["mantle_region"] == "us-west-2"
        assert model["mantle_reasoning_effort"] == "low"
        assert model.get("concurrency", config["scenario"]["translation"]["concurrency_default"]) == 8

    cache = ResultCache(RUN / "translations.jsonl")
    ledger_path = RUN / "background-requests.jsonl"
    ledger = {(r["model"], r["id"]): r for r in load_dataset([ledger_path])}
    ledger_lock = asyncio.Lock()
    session = boto3.Session()
    counters = {model["name"]: {"new_inferences": 0, "retrieved_inferences": 0} for model in models}
    semaphores = {model["name"]: asyncio.Semaphore(8) for model in models}
    cached = {model["name"]: sum(cache.has(model["name"], s["id"]) for s in segments)
              for model in models}
    if sum(len(segments) - value for value in cached.values()) > 100:
        raise RuntimeError("This completion adapter is limited to at most100 missing keys")
    job_limits = {model["name"]: asyncio.Semaphore(MAX_OUTSTANDING_JOBS) for model in models}
    submit_locks = {model["name"]: asyncio.Lock() for model in models}
    next_submission = {model["name"]: 0.0 for model in models}
    started = stamp()

    async def remember(handle):
        async with ledger_lock:
            with ledger_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(handle, ensure_ascii=False) + "\n")
            ledger[(handle["model"], handle["id"])] = handle

    def sign(method, url, body=None):
        request = AWSRequest(method=method, url=url, data=body,
                             headers={"Content-Type": "application/json"})
        SigV4Auth(session.get_credentials().get_frozen_credentials(),
                  "bedrock-mantle", "us-west-2").add_auth(request)
        return dict(request.prepare().headers)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        async def retrieve(url, name):
            for attempt in range(4):
                async with semaphores[name]:
                    response = await client.get(url, headers=sign("GET", url), timeout=30)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()

        async def submit(name, url, body, handle):
            for attempt in range(4):
                async with submit_locks[name]:
                    await asyncio.sleep(max(0, next_submission[name] - time.monotonic()))
                    next_submission[name] = time.monotonic() + SUBMIT_INTERVAL_S
                async with semaphores[name]:
                    handle = {**handle, "started_at": stamp(), "status": "submitting",
                              "submission_attempt": attempt + 1}
                    await remember(handle)
                    counters[name]["new_inferences"] += 1
                    response = await client.post(url, content=body, headers=sign("POST", url, body))
                if response.status_code >= 400:
                    await remember({**handle, "status": "rejected" if response.status_code < 500 else "submission_unknown",
                                    "http_status": response.status_code})
                if response.status_code == 429 and attempt < 3:
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json(), handle

        async def one(model, segment):
            name, id_ = model["name"], segment["id"]
            if cache.has(name, id_):
                return
            async with job_limits[name]:
                payload = {
                    "model": model["model_id"],
                    "input": [{"role": "user", "content": build_prompt(segment)}],
                    "temperature": 0, "max_output_tokens": 4096,
                    "reasoning": {"effort": "low"}, "background": True,
                    "service_tier": "default",
                }
                body = json.dumps(payload)
                payload_sha = hashlib.sha256(body.encode()).hexdigest()
                handle = ledger.get((name, id_))
                if handle and handle.get("status") == "rejected":
                    handle = None  # an explicit4xx response did not accept an inference
                url = mantle_url(model["mantle_region"])
                request_started = stamp()
                try:
                    if handle:
                        if handle["payload_sha256"] != payload_sha or handle["protocol_sha256"] != protocol_sha:
                            raise RuntimeError("Stored inference belongs to different inputs")
                        if not handle.get("response_id"):
                            raise RuntimeError("Previous submission has unknown acceptance; do not submit a duplicate")
                        counters[name]["retrieved_inferences"] += 1
                        request_started = handle["started_at"]
                        target = f"{url}/{quote(handle['response_id'], safe='')}"
                        data = await retrieve(target, name)
                    else:
                        handle = {
                            "model": name, "id": id_, "payload_sha256": payload_sha,
                            "protocol_sha256": protocol_sha, "started_at": request_started,
                            "status": "submitting", "response_id": None,
                        }
                        data, handle = await submit(name, url, body, handle)
                        request_started = handle["started_at"]
                        if not isinstance(data.get("id"), str) or not data["id"]:
                            raise InvalidResponseError("Background response has no ID")
                        handle = {**handle, "response_id": data["id"], "status": data.get("status")}
                        await remember(handle)
                        target = f"{url}/{quote(data['id'], safe='')}"

                    deadline = time.monotonic() + WAIT_LIMIT_S
                    while data.get("status") in {"queued", "in_progress"}:
                        if time.monotonic() >= deadline:
                            print(f"pending {name} {id_}; stored ID can be resumed", flush=True)
                            return
                        await asyncio.sleep(POLL_INTERVAL_S)
                        data = await retrieve(target, name)
                    if data.get("id") != handle["response_id"] or data.get("model") != model["model_id"]:
                        raise InvalidResponseError("Retrieved response identity mismatch")
                    await remember({**handle, "status": data.get("status"), "observed_at": stamp()})
                    if data.get("status") != "completed" or data.get("error") is not None:
                        raise InvalidResponseError("Background inference did not complete")
                    messages = [item for item in data.get("output", []) if item.get("type") == "message"]
                    if any(item.get("status", "completed") != "completed"
                           or item.get("role", "assistant") != "assistant" for item in messages):
                        raise InvalidResponseError("Background response has an incomplete assistant message")
                    parts = [part for item in messages for part in item.get("content", [])]
                    if any(part.get("type") == "refusal" for part in parts):
                        raise ContentFilteredError("Background inference refused content")
                    usage = data.get("usage") or {}
                    result = {
                        "text": "".join(part["text"] for part in parts if part.get("type") == "output_text"),
                        "tokens_in": usage.get("input_tokens"), "tokens_out": usage.get("output_tokens"),
                        "response_status": "completed",
                    }
                    _validate_result(result)
                    await cache.append({
                        "model": name, "id": id_, "src_lang": segment["src_lang"],
                        "tgt_lang": segment["tgt_lang"], "doc_type": segment["doc_type"],
                        "output_text": result["text"], "tokens_in": result["tokens_in"],
                        "tokens_out": result["tokens_out"], "error": None,
                        "response_id": handle["response_id"], "response_status": "completed",
                        "response_delivery": "background", "request_timeout_s": REQUEST_TIMEOUT_S,
                        "latency_s": round((datetime.now(timezone.utc) - datetime.fromisoformat(request_started)).total_seconds(), 3),
                        "timestamp": stamp(),
                    })
                    await remember({**handle, "status": "completed", "observed_at": stamp()})
                    print(f"completed {name} {id_}", flush=True)
                except Exception as error:
                    # A retrieval failure does not submit another inference.
                    # Preserve the accepted ID for a later resume.
                    print(json.dumps({"model": name, "id": id_, "error": failure_details(error)}), flush=True)

        try:
            await asyncio.gather(*(one(model, segment) for model in models for segment in segments))
        finally:
            summaries = []
            for model in models:
                name = model["name"]
                successful = sum(cache.has(name, s["id"]) for s in segments)
                summaries.append({
                    "model": name, "requested": len(segments), "successful": successful,
                    "failed": len(segments) - successful, "cached": cached[name],
                    "request_attempts": counters[name]["new_inferences"],
                    "retrieved_inferences": counters[name]["retrieved_inferences"],
                })
            summary = {key: sum(row[key] for row in summaries)
                       for key in ("requested", "successful", "failed", "cached", "request_attempts")}
            summary["models"] = summaries
            write_manifest(RUN.name, config, config["scenario"]["translation"], models, segments,
                           started, stamp(), completion_summary=summary)
            path = RUN / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest.update(dataset_sha256=protocol["dataset_sha256"], protocol_sha256=protocol_sha,
                            protocol=protocol, response_delivery="background",
                            background_poll_interval_s=POLL_INTERVAL_S,
                            background_wait_limit_s=WAIT_LIMIT_S,
                            background_max_outstanding_jobs_per_model=MAX_OUTSTANDING_JOBS,
                            background_submission_interval_s=SUBMIT_INTERVAL_S,
                            background_poll_request_timeout_s=30,
                            delivery_policy=json.loads((RUN / "delivery-policy.json").read_text()))
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(summary), flush=True)
    return int(summary["failed"] != 0)


def main():
    with execution_lock():
        return asyncio.run(execute())


if __name__ == "__main__":
    sys.exit(main())
