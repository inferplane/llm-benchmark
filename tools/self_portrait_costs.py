"""Estimate recorded artwork requests only; never change an author's code."""

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path


TOKEN_FIELDS = ("tokens_in", "tokens_out", "cache_read_tokens", "cache_write_tokens")
PRICE_FIELDS = ("price_in", "price_out", "price_cache_read", "price_cache_write")


def token_cost(model, usage):
    """Unrounded USD; cache classes are separate, reasoning is already output."""
    total = Decimal(0)
    for token_key, price_key in zip(TOKEN_FIELDS, PRICE_FIELDS):
        count = usage.get(token_key, 0)
        if type(count) is not int or count < 0:
            raise ValueError("invalid token count")
        if not count:
            continue
        price = model.get(price_key)
        if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
            raise ValueError(f"missing or invalid {price_key}")
        total += Decimal(count) * Decimal(str(price)) / 1_000_000
    return total


def gpu_cost(hourly, seconds):
    if type(hourly) not in (int, float) or not math.isfinite(hourly) or hourly < 0:
        raise ValueError("invalid GPU hourly rate")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("invalid request duration")
    return Decimal(str(hourly)) * Decimal(str(seconds)) / 3600


def usage_of(response):
    if "tokens_in" in response and "tokens_out" in response:
        usage = {key: response.get(key, 0) for key in TOKEN_FIELDS}
    elif isinstance(response.get("usage"), dict):
        # Mantle incomplete responses retain raw inclusive Responses usage.
        raw = response["usage"]
        details = raw.get("input_tokens_details") or {}
        read = details.get("cached_tokens", 0)
        write = details.get("cache_write_tokens", 0)
        if type(raw.get("input_tokens")) is not int or type(read) is not int or type(write) is not int:
            return None
        usage = dict(zip(TOKEN_FIELDS, (raw["input_tokens"] - read - write,
                                        raw.get("output_tokens"), read, write)))
    else:
        return None
    return usage if all(type(value) is int and value >= 0 for value in usage.values()) else None


def implementation_cost(model, directory: Path, generation):
    paths = sorted((directory / "attempts").glob("*/record.json"))
    if not paths:
        return {"kind": "not_measured", "generation": generation, "estimated_total_usd": None,
                "recorded_attempts": 0}
    native = model["api"] == "openai" and bool(model.get("base_url"))
    total = Decimal(0)
    final_cost = None
    counts = dict.fromkeys(TOKEN_FIELDS, 0)
    attempts = []
    unknown_usage = 0
    missing_duration = 0
    successful = 0
    seconds_total = 0.0
    latest = json.loads((directory / "record.json").read_text())
    for path in paths:
        record = json.loads(path.read_text())
        assert record["model_id"] == model["model_id"], "attempt model differs from config"
        successful += record["status"] == "generated"
        response_path = next((path.with_name(name) for name in ("response.json", "incomplete-response.json")
                              if path.with_name(name).exists()), None)
        usage = usage_of(json.loads(response_path.read_text())) if response_path else None
        unknown_usage += usage is None
        if usage:
            for key in TOKEN_FIELDS:
                counts[key] += usage[key]
        cost = None
        duration = None
        if native:
            end = record.get("generated_at") or record.get("failed_at")
            if end and record.get("requested_at"):
                duration = (datetime.fromisoformat(end) - datetime.fromisoformat(record["requested_at"])).total_seconds()
                cost = gpu_cost(model["gpu_hourly_usd"], duration)
                seconds_total += duration
            else:
                missing_duration += 1
        elif usage:
            cost = token_cost(model, usage)
        if cost is not None:
            total += cost
        if record.get("requested_at") == latest.get("requested_at"):
            final_cost = float(cost) if cost is not None else None
        attempts.append({
            "requested_at": record.get("requested_at"), "status": record["status"],
            "request_id": record.get("request_id"), "usage_available": usage is not None,
            "estimated_cost_usd": float(cost) if cost is not None else None,
            "request_seconds": duration, "record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest() if response_path else None,
        })
    counted = sum(row["estimated_cost_usd"] is not None for row in attempts)
    return {
        "kind": "gpu_request_time" if native else "api_tokens", "generation": generation,
        "currency": "USD", "price_source": "config.toml",
        "price_snapshot": {key: model[key] for key in (*PRICE_FIELDS, "gpu_hourly_usd") if key in model},
        "estimated_total_usd": float(total) if counted else None,
        "estimated_final_response_usd": final_cost,
        "recorded_attempts": len(attempts), "successful_code_responses": successful,
        "additional_attempts": max(0, len(attempts) - 1), "known_cost_attempts": counted,
        "unknown_usage_attempts": unknown_usage, "missing_duration_attempts": missing_duration,
        "total_request_seconds": seconds_total if native else None, "tokens": counts,
        "complete_request_estimate": missing_duration == 0 if native else counted == len(attempts),
        "excludes": ["reviewer_and_coordinator_calls", "historical_generations", "taxes_and_discounts"]
        + (["GPU_model_loading_and_idle_time", "other_infrastructure"] if native else
           ["requests_without_returned_usage"]),
        "attempts": attempts,
    }


def _selfcheck():
    # $1 input + $2.50 output + $0.10 cache read + $0.375 cache write.
    rates = {"price_in": 1, "price_out": 5, "price_cache_read": .1, "price_cache_write": 1.25}
    assert token_cost(rates, dict(zip(TOKEN_FIELDS, (1_000_000, 500_000, 1_000_000, 300_000)))) == Decimal("3.975")
    assert token_cost({"price_out": .55}, {"tokens_out": 1}) == Decimal("0.00000055")
    assert gpu_cost(3.6, 100) == Decimal("0.1")
    inclusive = usage_of({"usage": {"input_tokens": 100, "output_tokens": 20,
                                  "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 10}}})
    assert inclusive == dict(zip(TOKEN_FIELDS, (60, 20, 30, 10)))
    assert usage_of({"text": "timeout"}) is None
    # A billed truncated response ($3.50), timeout (unknown), and repaired
    # response ($3.975) total $7.475. The current response copy isn't another call.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = {**rates, "api": "bedrock", "model_id": "offline"}
        for index, status in enumerate(("failed", "failed", "generated")):
            folder = root / "attempts" / str(index)
            folder.mkdir(parents=True)
            record = {"model_id": "offline", "status": status,
                      "requested_at": f"2026-10-12T00:0{index}:00+00:00"}
            (folder / "record.json").write_text(json.dumps(record))
            if index != 1:
                usage = dict(zip(TOKEN_FIELDS, (1_000_000, 500_000, 1_000_000 if index == 2 else 0,
                                                300_000 if index == 2 else 0)))
                (folder / "response.json").write_text(json.dumps(usage))
            if index == 2:
                (root / "record.json").write_text(json.dumps(record))
                (root / "response.json").write_text(json.dumps(usage))
        result = implementation_cost(config, root, "fixture")
        assert result["recorded_attempts"] == 3 and result["known_cost_attempts"] == 2
        assert result["unknown_usage_attempts"] == 1 and not result["complete_request_estimate"]
        assert result["estimated_total_usd"] == 7.475 and result["estimated_final_response_usd"] == 3.975
    for usage in ({"tokens_in": -1}, {"tokens_out": True}):
        try:
            token_cost(rates, usage)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid usage accepted")
