"""Verify the exact Terra ID/settings before freezing benchmark requests."""
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench import run

DIRECTORY = Path(__file__).resolve().parent
MODEL_ID = "openai.gpt-6.1-terra"


async def check():
    import httpx
    session = run.make_client({"api": "bedrock_mantle"}, "us-east-1")
    run.MAX_OUTPUT_TOKENS = 128
    records = []
    client_class = httpx.AsyncClient
    async def read_response(response):
        # call_mantle raises on status before reading a streamed error body.
        # Keep the provider's exact validation message in preflight evidence.
        await response.aread()
    for label, omit_temperature in (("temperature-zero", False), ("temperature-omitted", True)):
        if omit_temperature:
            run.MANTLE_NO_TEMPERATURE.add(MODEL_ID)
        else:
            run.MANTLE_NO_TEMPERATURE.discard(MODEL_ID)
        try:
            with patch("httpx.AsyncClient", side_effect=lambda **kwargs: client_class(
                **kwargs, event_hooks={"response": [read_response]})):
                response = await run.call_mantle(session, "us-east-1", MODEL_ID,
                    "Translate into English; return only the translation: 매출이 전년 대비 10% 증가했습니다.",
                    reasoning_effort="low")
            records.append({"case": label, "result": response})
        except httpx.HTTPStatusError as error:
            records.append({"case": label, "http_status": error.response.status_code,
                            "response_body": error.response.text})
    (DIRECTORY / "preflight.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    assert records[0].get("http_status") == 400, records[0]
    assert "temperature" in records[0]["response_body"], records[0]
    assert records[1]["result"]["response_status"] == "completed"
    assert records[1]["result"]["reported_reasoning"]["effort"] == "low"
    (DIRECTORY / "preflight.json").write_text(json.dumps({
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "model_id": MODEL_ID, "region": "us-east-1", "checks": records,
    }, ensure_ascii=False, indent=2) + "\n")
    for label, url in (
        ("aws-model-card", "https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-terra.html"),
        ("openai-model", "https://developers.openai.com/api/docs/models/gpt-6.1-terra"),
    ):
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
        (DIRECTORY / f"{label}.html").write_bytes(response.content)
        print(label, response.status_code, hashlib.sha256(response.content).hexdigest())
    print(json.dumps(records, ensure_ascii=False))


def main():
    asyncio.run(check())


if __name__ == "__main__":
    main()
