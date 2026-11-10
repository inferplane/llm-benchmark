"""Daily Bedrock What's New watcher: draft config entries for new models.

Run by ``.github/workflows/bedrock-model-watch.yml``. Claude Haiku 5.5 (via
Bedrock Converse) does the two language tasks: classifying recent Amazon
Bedrock announcements, and extracting facts from the model's AWS model card.
Everything Haiku returns is checked against deterministic evidence before it
can reach ``config.toml``:

* the model ID must be listed by ``ListFoundationModels`` (Converse models),
  or appear verbatim in the AWS model card (Mantle-only models);
* every extracted price must appear verbatim as ``$<price>`` in the card;
* temperature handling and reasoning effort are decided by a live probe
  call, not by the card text.

A model passing every check is appended with ``enabled = true`` and handed to
``bench.model_extension`` by the workflow. Anything uncertain (no verifiable
price, failed probe, zero quota) is appended with ``enabled = false`` so a
human reviews the draft PR; no benchmark is started for it.

    uv run python3 tools/bedrock_model_watch.py --lookback-days 2 --out watch.json
    uv run python3 tools/bedrock_model_watch.py --dry-run      # classify only, no edits
"""
import argparse
import asyncio
import email.utils
import hashlib
import html
import json
import re
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench import run  # noqa: E402

FEED = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
HAIKU = "us.anthropic.claude-haiku-5-5"
REGIONS = ("us-west-2", "us-east-1")
EVIDENCE = ROOT / "validation/model-watch"
USER_AGENT = "llm-benchmark-model-watch/1.0 (+https://github.com/inferplane/llm-benchmark)"
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{1,48}")
MARKER = "# ── auto-added by tools/bedrock_model_watch.py ──"


ALLOWED_HOSTS = ("aws.amazon.com", "docs.aws.amazon.com")


def fetch(url, limit=3_000_000):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"refusing to fetch {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read(limit).decode("utf-8", "replace")


def text_of(page):
    page = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    page = html.unescape(page)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", page)).strip()


# ── Haiku 5.5 ────────────────────────────────────────────────────────────────
def haiku(client, system, prompt, max_tokens=2048):
    """One Converse call; temperature omitted (Haiku 5.5 rejects it)."""
    response = client.converse(
        modelId=HAIKU, system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
        additionalModelRequestFields={"output_config": {"effort": "low"}})
    text = "".join(b.get("text", "") for b in response["output"]["message"]["content"])
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"Haiku returned no JSON object: {text[:200]!r}")
    return json.loads(match.group(0))


CLASSIFY = """You triage AWS What's New posts for an LLM benchmark. Answer only with JSON:
{"new_model": bool, "models": [{"name": str, "provider": str}], "reason": str}
new_model is true ONLY when the post announces that one or more specific foundation models
(text-generating LLMs) became available for inference in Amazon Bedrock in commercial AWS
Regions. It is false for: AgentCore/agents/tools/features, GovCloud-only or China-only launches,
region expansions of models that were already available elsewhere, limited/eligible-customer-only
previews, embedding/image/video/speech-only models, price or quota changes, and anything that is not Bedrock."""

EXTRACT = """Extract facts from an Amazon Bedrock model card. Copy values exactly as written; use null when
the card does not state them. Answer only with JSON:
{"model_id": str|null, "us_geo_inference_id": str|null, "endpoints": [str], "apis": [str],
 "price_per_mtok": {"tier": str|null, "input": str|null, "output": str|null, "cache_read": str|null, "cache_write": str|null},
 "price_basis": "US Geo/CRIS"|"In-Region us-east-1"|"Global"|"none",
 "temperature_note": str|null, "reasoning_effort_values": [str], "default_reasoning_effort": str|null,
 "config_name": str}
Prices: Standard tier, per 1M tokens, the US Geo / US CRIS row when present, otherwise the
us-east-1 In-Region row, otherwise Global; copy them like "4.40" without "$".
config_name: lowercase hyphenated short name in the style of these existing names: {examples}."""


# ── deterministic evidence ───────────────────────────────────────────────────
def listed_models(boto3):
    """modelId -> {name, provider, profile_only, us_profile} across regions."""
    found = {}
    for region in REGIONS:
        bedrock = boto3.client("bedrock", region_name=region)
        profiles = {p["inferenceProfileId"] for page in bedrock.get_paginator("list_inference_profiles").paginate()
                    for p in page["inferenceProfileSummaries"]}
        for m in bedrock.list_foundation_models()["modelSummaries"]:
            if "TEXT" not in m.get("outputModalities", []) or m.get("modelLifecycle", {}).get("status") != "ACTIVE":
                continue
            us = f"us.{m['modelId']}"
            found.setdefault(m["modelId"], {"name": m["modelName"], "provider": m["providerName"],
                                            "profile_only": m.get("inferenceTypesSupported") == ["INFERENCE_PROFILE"],
                                            "us_profile": us if us in profiles else None})
    return found


def configured_ids(cfg):
    ids = set()
    for m in cfg["models"]:
        ids.add(m["model_id"])
        ids.add(m["model_id"].removeprefix("us.").removeprefix("global."))
    return ids


def money(value):
    """Haiku's price string -> canonical token, or None."""
    if value is None:
        return None
    value = str(value).strip().lstrip("$").replace(",", "")
    return value if re.fullmatch(r"\d+(\.\d+)?", value) and 0 < float(value) < 1000 else None


def has_amount(line, value):
    # Exact amount: "$4" must not match "$4.40", nor "$4.4" match "$4.40".
    return re.search(rf"\${re.escape(value)}(?![\d.]|\.\d)", line) is not None


def verified_prices(card_text, extracted):
    """Every price must sit on ONE card line (a pricing-table row) together
    with the other extracted prices; a US row is preferred. Returns floats or
    None per field plus the matched row, so unrelated "$x" mentions elsewhere
    in the card can never be combined into a price."""
    values = {k: money(extracted.get(k)) for k in ("input", "output", "cache_read", "cache_write")}
    if not values["input"] or not values["output"] or float(values["output"]) < float(values["input"]):
        return {k: None for k in values}, None
    rows = [line for line in card_text.splitlines()
            if has_amount(line, values["input"]) and has_amount(line, values["output"])]
    rows.sort(key=lambda line: ("US" not in line, len(line)))
    if not rows:
        return {k: None for k in values}, None
    row = rows[0]
    return {k: float(v) if v and has_amount(row, v) else None for k, v in values.items()}, row[:200]


def comment_safe(value, limit=160):
    """Text from Haiku/the web only ever lands inside one TOML comment line."""
    return re.sub(r"[^A-Za-z0-9 _.:/()%$,+=#-]", " ", str(value))[:limit]


async def probe(model):
    """Live call: does temperature=0 work, and does the configured effort answer?"""
    import boto3
    from botocore.config import Config
    prompt = "Translate into English. Output only the translation.\n\n총보수는 연 0.45%입니다."
    effort_key = "bedrock_reasoning_effort" if model["api"] == "bedrock" else "mantle_reasoning_effort"
    outcome = {"temperature_rejected": False}
    for attempt in ("with_temperature", "without_temperature"):
        try:
            if model["api"] == "bedrock":
                client = boto3.client("bedrock-runtime", region_name="us-west-2", config=Config(read_timeout=300, retries={"total_max_attempts": 2}))
                result = await run.call_bedrock(client, model["model_id"], prompt, reasoning_effort=model.get(effort_key))
            else:
                result = await run.call_mantle(boto3.Session(), model.get("mantle_region", "us-east-1"), model["model_id"],
                                               prompt, reasoning_effort=model.get(effort_key))
            run._validate_result(result)
            outcome.update(ok=True, text=result["text"][:200], tokens_out=result["tokens_out"])
            return outcome
        except Exception as error:
            message = str(error)
            if attempt == "with_temperature" and "temperature" in message.lower():
                outcome["temperature_rejected"] = True
                (run.BEDROCK_NO_TEMPERATURE if model["api"] == "bedrock" else run.MANTLE_NO_TEMPERATURE).add(model["model_id"])
                continue
            outcome.update(ok=False, error_type=type(error).__name__, error=message[:300])
            return outcome
    return outcome


def toml_block(entry, notes):
    lines = [f"# {line}" for line in notes] + ["[[models]]"]
    for key in ("name", "api", "model_id", "mantle_region", "price_in", "price_out", "price_cache_read",
                "price_cache_write", "omit_temperature", "bedrock_reasoning_effort", "mantle_reasoning_effort", "enabled"):
        if entry.get(key) is None:
            continue
        value = entry[key]
        lines.append(f"{key} = {json.dumps(value) if isinstance(value, str) else str(value).lower() if isinstance(value, bool) else value}")
    return "\n".join(lines) + "\n"


# ── main flow ────────────────────────────────────────────────────────────────
def recent_bedrock_items(feed_xml, lookback_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    # The feed never carries a DTD. Refusing one up front rules out entity
    # expansion tricks without adding a parser dependency (uv.lock is hashed
    # into frozen benchmark contracts); stdlib ElementTree never fetches
    # external entities.
    if re.search(r"<!(DOCTYPE|ENTITY)", feed_xml, re.I):
        raise ValueError("refusing a What's New feed that declares a DTD/entities")
    items = []
    for item in ET.fromstring(feed_xml).findall("./channel/item"):
        title = item.findtext("title") or ""
        category = item.findtext("category") or ""
        published = email.utils.parsedate_to_datetime(item.findtext("pubDate"))
        if published < cutoff or not ("amazon-bedrock" in category or "bedrock" in title.lower()):
            continue
        items.append({"title": title.strip(), "link": item.findtext("link"), "published": published.isoformat(),
                      "description": text_of(item.findtext("description") or "")[:3000]})
    return items


def card_url(item_page_text, item_page_html):
    for url in re.findall(r'href="(https://docs\.aws\.amazon\.com/bedrock/latest/userguide/model-card-[^"#?]+\.html)', item_page_html):
        return url
    return None


async def process(args):
    import boto3
    cfg = run.load_config()
    runtime = boto3.client("bedrock-runtime", region_name="us-west-2")
    feed_xml = fetch(FEED)
    items = recent_bedrock_items(feed_xml, args.lookback_days)
    listed = listed_models(boto3)
    known = configured_ids(cfg)
    names_in_use = {m["name"] for m in cfg["models"]}
    if args.known_ids:  # model IDs / names already drafted on unmerged auto/* or bench/* branches
        for line in Path(args.known_ids).read_text().splitlines():
            kind, _, value = line.strip().partition(" ")
            if kind == "id":
                known |= {value, value.removeprefix("us.").removeprefix("global.")}
            elif kind == "name":
                names_in_use.add(value)
    examples = ", ".join(m["name"] for m in cfg["models"][-12:])
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "feed": FEED, "items": [], "added": []}
    blocks = []
    for item in items:
        verdict = haiku(runtime, CLASSIFY, json.dumps(item, ensure_ascii=False))
        entry = {"item": item, "classification": verdict}
        report["items"].append(entry)
        if not verdict.get("new_model"):
            continue
        page_html = fetch(item["link"])
        url = card_url(text_of(page_html), page_html)
        entry["model_card"] = url
        if not url:
            entry["skipped"] = "no AWS model card link in the announcement"
            continue
        card_html = fetch(url)
        card = text_of(card_html)
        facts = haiku(runtime, EXTRACT.replace("{examples}", examples), card[:60000])
        entry["extracted"] = facts
        base_id = facts.get("model_id")
        if not base_id or base_id not in card:
            entry["skipped"] = "model id not found verbatim in the card"
            continue
        if base_id in known or (facts.get("us_geo_inference_id") or "") in known:
            entry["skipped"] = "already configured"
            continue
        if base_id in listed:
            api = "bedrock"
            meta = listed[base_id]
            model_id = meta["us_profile"] or (base_id if not meta["profile_only"] else None)
        elif "bedrock-mantle" in card and any("mantle" in str(e).lower() for e in facts.get("endpoints", [])):
            api, model_id = "bedrock_mantle", base_id
        else:
            entry["skipped"] = "not listed by ListFoundationModels and no bedrock-mantle endpoint"
            continue
        if not model_id:
            entry["skipped"] = "inference-profile-only model without a US Geo profile"
            continue
        name = (facts.get("config_name") or "").strip().lower()
        if not NAME.fullmatch(name) or name in names_in_use:
            entry["skipped"] = f"unusable config_name {name!r}"
            continue
        prices, price_row = verified_prices(card, facts.get("price_per_mtok") or {})
        entry["price_row"] = price_row
        efforts = [e.lower() for e in facts.get("reasoning_effort_values") or []]
        effort = "low" if "low" in efforts else None
        model = {"name": name, "api": api, "model_id": model_id,
                 "mantle_region": "us-east-1" if api == "bedrock_mantle" else None,
                 "price_in": prices["input"], "price_out": prices["output"],
                 "price_cache_read": prices["cache_read"], "price_cache_write": prices["cache_write"],
                 ("bedrock_reasoning_effort" if api == "bedrock" else "mantle_reasoning_effort"): effort}
        live = await probe(model) if not args.dry_run else {"ok": None}
        entry["probe"] = live
        model["omit_temperature"] = True if live.get("temperature_rejected") else None
        reasons = []
        if prices["input"] is None or prices["output"] is None:
            reasons.append("input/output price not verifiable in the model card")
        if price_row is not None and "US" not in price_row:
            reasons.append("matched price row is not a US row; US Geo rate needs review")
        if live.get("ok") is False:
            reasons.append(f"live probe failed: {live.get('error_type')}")
        model["enabled"] = not reasons
        today = datetime.now(timezone.utc).date().isoformat()
        notes = [f"{name} - auto-drafted {today} from {comment_safe(item['link'])}",
                 f"Model card: {comment_safe(url)} (sha256 {hashlib.sha256(card_html.encode()).hexdigest()[:16]})",
                 f"Prices taken from one card row (Standard, per 1M tokens): {comment_safe(price_row or 'none')}",
                 f"Live probe: temperature {'rejected -> omitted' if live.get('temperature_rejected') else 'accepted'}; "
                 f"reasoning effort {effort or 'not configurable/not set'}."]
        notes += [f"NEEDS REVIEW: {comment_safe(r)}" for r in reasons]
        blocks.append(toml_block(model, notes))
        names_in_use.add(name)
        known.add(model_id)
        report["added"].append({"name": name, "model_id": model_id, "enabled": model["enabled"], "needs_review": reasons})
    if blocks and not args.dry_run:
        config = (ROOT / "config.toml").read_text()
        if MARKER not in config:
            config = config.rstrip("\n") + "\n\n" + MARKER + "\n"
        updated = config.rstrip("\n") + "\n\n" + "\n".join(blocks)
        # Never write an unparsable config, and never anything beyond exactly
        # the intended new tables (a guard against injected TOML).
        before, after = tomllib.loads(config)["models"], tomllib.loads(updated)["models"]
        intended = [a["name"] for a in report["added"]]
        assert after[:len(before)] == before and [m["name"] for m in after[len(before):]] == intended
        assert len({m["name"] for m in after}) == len(after), "duplicate model name"
        (ROOT / "config.toml").write_text(updated)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / f"{datetime.now(timezone.utc):%Y%m%d}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out + "\n")
    print(out)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lookback-days", type=float, default=2.0)
    parser.add_argument("--out", help="write the watch report JSON here")
    parser.add_argument("--known-ids", help="file of model IDs already drafted elsewhere (one per line)")
    parser.add_argument("--dry-run", action="store_true", help="classify and extract only; no probe, no config edits")
    args = parser.parse_args()
    report = asyncio.run(process(args))
    ready = [a["name"] for a in report["added"] if a["enabled"]]
    review = [a["name"] for a in report["added"] if not a["enabled"]]
    github_output = __import__("os").environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as stream:
            stream.write(f"ready={','.join(ready)}\nreview={','.join(review)}\nadded={len(report['added'])}\n")


if __name__ == "__main__":
    main()
