"""Ask each actual configured model to implement its own HTML artwork.

No human-authored artwork or fallback model is used. The common catalog and
sandbox viewer are navigation/provenance only; artwork.html is extracted from
the selected model's recorded response without editing the implementation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench import run

OUTPUT = ROOT / "docs/models"
RECORDS = ROOT / "results/model-self-portraits"
PROMPT = ROOT / "tools/self_portrait_prompt.txt"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as file:
        file.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary = Path(file.name)
    temporary.replace(path)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def family(model: dict) -> str:
    identifier = model["model_id"].lower()
    for needle, label in (
        ("anthropic", "Claude"), ("openai", "OpenAI"), ("amazon.nova", "Amazon Nova"),
        ("xai", "xAI"), ("meta", "Meta"), ("qwen", "Qwen"), ("google", "Google"),
        ("nvidia", "NVIDIA"), ("mistral", "Mistral"), ("moonshot", "Moonshot AI"),
        ("zai", "Z.AI"), ("exaone", "LG AI Research"),
    ):
        if needle in identifier:
            return label
    return "Amazon Translate" if model["api"] == "translate" else "Other"


def extract_html(text: str) -> str:
    # Only remove response framing; never repair or rewrite the model's code.
    start = re.search(r"<!doctype\s+html\b|<html\b", text, re.IGNORECASE)
    end = list(re.finditer(r"</html\s*>", text, re.IGNORECASE))
    if start is None or not end or end[-1].end() <= start.start():
        raise ValueError("Model response is not a complete HTML document")
    result = text[start.start():end[-1].end()]
    if not re.search(r"<body\b", result, re.IGNORECASE):
        raise ValueError("Model response has no body element")
    if re.search(r"<(?:script|iframe)\b[^>]*\bsrc\s*=", result, re.IGNORECASE):
        raise ValueError("External executable dependencies are not allowed")
    return result


def record_of(name: str) -> dict:
    path = RECORDS / name / "record.json"
    return json.loads(path.read_text()) if path.exists() else {"status": "pending"}


def build_catalog(models: list[dict], reviews: dict | None = None) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for model in models:
        name = model["name"]
        directory = OUTPUT / name
        directory.mkdir(parents=True, exist_ok=True)
        record = record_of(name)
        status = record["status"]
        review = reviews.get(name) if reviews is not None else None
        if status == "generated" and reviews is not None:
            artwork = directory / "artwork.html"
            actual_sha256 = hashlib.sha256(artwork.read_bytes()).hexdigest() if artwork.exists() else None
            approved = (
                review is not None
                and review.get("verdict") == "PASS"
                and review.get("score", 0) >= 85
                and review.get("critical") == 0
                and review.get("warnings", 999) <= 3
                and review.get("artwork_sha256") == record.get("artwork_sha256")
                and actual_sha256 == record.get("artwork_sha256")
                and record.get("model_id") == model["model_id"]
            )
            if not approved:
                status = "review_held"
        labels = {
            "generated": "모델 직접 작성", "pending": "생성 대기", "failed": "생성 실패",
            "unavailable": "실행 불가", "not_generative": "코드 생성 기능 없음",
            "review_held": "검수 보류",
        }
        attribution = {
            "model": name, "requested_model_id": model["model_id"],
            "provider": "vllm" if model["api"] == "openai" and model.get("base_url") else model["api"],
            "family": family(model),
            **{key: record[key] for key in (
                "generated_at", "request_id", "response_id",
                "reported_model", "artwork_sha256", "prompt_sha256",
                "tokens_in", "tokens_out", "finish_reason", "max_output_tokens",
                "reported_reasoning", "reasoning_tokens", "temperature", "temperature_sent",
            ) if key in record},
            "status": status,
            "generation_status": record["status"],
        }
        if review is not None:
            attribution["content_review"] = {
                key: review[key] for key in ("score", "critical", "warnings", "verdict")
                if key in review
            }
        write_json(directory / "provenance.json", attribution)
        entries.append(attribution)
        if status == "generated":
            panel = f'<iframe title="{escape(name)} 모델이 구현한 자기표현 작품" data-artwork="artwork.html" sandbox="allow-scripts" allow="autoplay \'none\'; camera \'none\'; microphone \'none\'; geolocation \'none\'"></iframe>'
        else:
            reason = (
                "작성 모델의 실제 응답은 보존했습니다. 동작 검수를 통과하지 못해 작품 공개를 보류합니다."
                if status == "review_held" else
                record.get("reason", "아직 이 모델의 응답을 받지 않았습니다.")
            )
            panel = f'<main class="unavailable"><h1>{escape(name)}</h1><p>{escape(labels.get(status, status))}</p><p>{escape(reason)}</p><p>다른 모델이나 운영자가 대신 만든 작품은 표시하지 않습니다.</p></main>'
        directory.joinpath("index.html").write_text(f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(name)} · 모델이 만든 자기표현</title>
<link rel="icon" href="../../favicon.svg"><link rel="stylesheet" href="../portraits.css"><link rel="stylesheet" href="../readability.css"><script src="../viewer.js" defer></script></head>
<body class="viewer"><header class="viewer-bar"><a href="../">← 모델 목록</a><span><strong>{escape(name)}</strong><small>{escape(labels.get(status, status))}</small></span>
<details><summary>작성 기록</summary><section><p>요청 모델: {escape(model["model_id"])}</p><p>상태: {escape(labels.get(status, status))}</p>
<p>{escape(record.get('generated_at', ''))}</p><p>작품 코드와 디자인은 이 모델의 실제 응답입니다. 목록과 이 표시줄은 실행 도구가 제공합니다.</p>
<a href="provenance.json" target="_blank" rel="noopener">작성자·응답 기록</a>{'<a href="artwork.html" target="_blank" rel="noopener">원본 작품만 열기 ↗</a>' if status == 'generated' else ''}</section></details></header>{panel}</body></html>""")
    generated = sum(item["status"] == "generated" for item in entries)
    cards = []
    for entry in entries:
        name = entry["model"]
        status = entry["status"]
        preview = (
            f'<img src="{escape(name)}/preview.jpg" loading="lazy" alt="{escape(name)}이 직접 구현한 작품 화면" onerror="this.remove()">'
            if status == "generated" and (OUTPUT / name / "preview.jpg").exists() else
            f'<div class="placeholder"><span>{escape(family(next(m for m in models if m["name"] == name)))}</span><strong>{escape(name)}</strong></div>'
        )
        cards.append(f'<a class="portrait-card" href="{escape(name)}/" data-family="{escape(entry["family"])}" data-name="{escape(name)}"><div class="preview">{preview}</div><div class="caption"><small>{escape(entry["family"])}</small><h2>{escape(name)}</h2><span class="status {status}">{escape(labels.get(status, status))} ↗</span></div></a>')
    families = list(dict.fromkeys(entry["family"] for entry in entries))
    filters = '<button data-family="all" class="active" aria-pressed="true">전체</button>' + "".join(f'<button data-family="{escape(value)}" aria-pressed="false">{escape(value)}</button>' for value in families)
    OUTPUT.joinpath("index.html").write_text(f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>모델이 만든 자기표현 · LLM Self Portraits</title><link rel="icon" href="../favicon.svg"><link rel="stylesheet" href="portraits.css"><link rel="stylesheet" href="readability.css"><script src="catalog.js" defer></script></head>
<body class="catalog"><header><a href="../index.html">LLM BENCHMARK ↗</a><span>SELF PORTRAITS</span></header>
<main><section class="intro"><p>A SHARED BRIEF · EACH MODEL'S OWN CODE</p><h1>나는, 이런 모델입니다.</h1><div>모델마다 같은 기본 요청을 받았습니다.<br>“자신을 표현하는 미디어아트 웹페이지를 직접 구현해 주세요.”<br>발견된 코드 오류는 작성 모델에 돌려보내 수정받았습니다.<br>각 작품은 해당 모델이 반환한 코드 그대로입니다.{'<br>검수 보류 항목은 작품 대신 상태를 표시합니다.' if reviews is not None else ''}</div><p class="total">{generated}개 모델 {'작품 공개' if reviews is not None else '직접 작성'} · 전체 {len(entries)}개 항목</p></section>
<div class="toolbar"><div class="filters">{filters}</div><label>모델 찾기 <input type="search" id="search" placeholder="Claude, GPT, Qwen…"></label></div>
<section class="portrait-grid" aria-label="각 모델이 직접 만든 작품">{''.join(cards)}</section>
<p id="empty" hidden>해당하는 모델이 없습니다.</p></main><footer>작성 모델과 실제 응답 기록은 각 작품의 ‘작성 기록’에서 확인할 수 있습니다.<br>코드 생성이 불가능하거나 실제 응답이 없는 항목은 작품 대신 그 상태를 표시합니다.</footer></body></html>""")
    write_json(OUTPUT / "catalog.json", entries)


async def generate_one(model: dict, aws_region: str, limiter: asyncio.Semaphore) -> None:
    name = model["name"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", name):
        raise ValueError("Unsafe configured model path")
    previous = record_of(name)
    artwork = OUTPUT / name / "artwork.html"
    same_source = (
        artwork.exists()
        and previous.get("model_id") == model["model_id"]
        and hashlib.sha256(artwork.read_bytes()).hexdigest() == previous.get("artwork_sha256")
    )
    if previous["status"] == "generated" and same_source and not model.get("_feedback"):
        print(f"Cached {name}", flush=True)
        return
    directory = RECORDS / name
    directory.mkdir(parents=True, exist_ok=True)
    if model["api"] == "translate":
        write_json(directory / "record.json", {"status": "not_generative", "reason": "Amazon Translate는 번역 서비스이며 HTML 코드를 생성하는 LLM이 아닙니다."})
        return
    if not model.get("enabled", True):
        write_json(directory / "record.json", {"status": "unavailable", "reason": "config.toml에서 비활성인 자체 배포 후보입니다. 알려진 GPU 메모리 제약 때문에 실행하지 않습니다."})
        return
    async with limiter:
        print(f"Requesting {name} ({model['model_id']})", flush=True)
        prompt = PROMPT.read_text().replace("{name}", name).replace("{model_id}", model["model_id"])
        if model.get("_feedback"):
            response = directory / "response.txt"
            previous_code = response.read_text() if response.exists() and not model.get("_fresh_repair") else ""
            prompt = (
                f"You are the original author, model {name}, served as {model['model_id']}. "
                "Repair your OWN previously generated standalone HTML. This is a bug-fix task, "
                "not a new creative brief. Preserve your own art and Korean poem. "
                "Return ONLY one complete corrected HTML document, all tags closed. "
                "No explanation, no Markdown fence, no snippets. No external dependencies or network. "
                "Stay compact (about 3000 code output tokens).\n\nYOUR PREVIOUS FULL RESPONSE:\n"
                + previous_code
                + "\n\nMANDATORY BROWSER REVIEW FIXES. Apply EVERY item below to the returned code; "
                "do not merely repeat your old code. The diagnostic list is the controlling repair request:\n"
                + json.dumps(model["_feedback"], ensure_ascii=False)
                + ("\n\nThe previous implementation was unreliable; implement a fresh minimal version "
                   "yourself. Use DOM text and native buttons, one RAF controller, and keep all requirements."
                   if model.get("_fresh_repair") else "")
                + "\n\nReturn the complete repaired HTML now."
            )
        directory.joinpath("prompt.txt").write_text(prompt)
        if model["api"] == "bedrock":
            import boto3
            from botocore.config import Config
            client = boto3.client(
                "bedrock-runtime", region_name=aws_region,
                config=Config(connect_timeout=15, read_timeout=600,
                              retries={"total_max_attempts": 1, "mode": "standard"}),
            )
        else:
            client = run.make_client(model, aws_region)
        temperature_sent = not (
            model["api"] == "bedrock" and model["model_id"] in run.BEDROCK_NO_TEMPERATURE
            or model["api"] == "bedrock_mantle" and model["model_id"] in run.MANTLE_NO_TEMPERATURE
        )
        record = {
            "model": name, "model_id": model["model_id"], "api": model["api"],
            "requested_at": now(), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "max_output_tokens": run.MAX_OUTPUT_TOKENS,
            "temperature": model.get("_art_temperature", 0) if temperature_sent else None,
            "temperature_sent": temperature_sent,
        }
        attempt = directory / "attempts" / record["requested_at"].replace(":", "-")
        attempt.mkdir(parents=True, exist_ok=True)
        attempt.joinpath("prompt.txt").write_text(prompt)
        try:
            if model["api"] == "bedrock":
                result = await run.call_bedrock(client, model["model_id"], prompt, model.get("bedrock_reasoning_effort"))
            elif model["api"] == "bedrock_mantle":
                effort = model.get("mantle_reasoning_effort")
                if effort is None and model["model_id"].startswith("openai.") and model["model_id"] in run.MANTLE_NO_TEMPERATURE:
                    effort = "low"
                result = await run.call_mantle(client, model.get("mantle_region", aws_region), model["model_id"], prompt, reasoning_effort=effort)
            else:
                # Prove the serving endpoint actually has the requested weights.
                available = await client.models.list()
                if model["model_id"] not in {item.id for item in available.data}:
                    raise ValueError("Configured vLLM model is not served at this endpoint")
                if model.get("_art_temperature") is None:
                    result = await run.call_openai(client, model["model_id"], prompt, model.get("chat_template_kwargs"))
                else:
                    extra = {"chat_template_kwargs": model["chat_template_kwargs"]} if model.get("chat_template_kwargs") else {}
                    response = await client.chat.completions.create(
                        model=model["model_id"], messages=[{"role": "user", "content": prompt}],
                        temperature=model["_art_temperature"], max_tokens=run.MAX_OUTPUT_TOKENS,
                        extra_body=extra,
                    )
                    result = {"text": response.choices[0].message.content,
                              "tokens_in": response.usage.prompt_tokens,
                              "tokens_out": response.usage.completion_tokens,
                              "finish_reason": response.choices[0].finish_reason,
                              "reported_model": response.model}
            write_json(directory / "response.json", result)
            write_json(attempt / "response.json", result)
            directory.joinpath("response.txt").write_text(result["text"])
            code = extract_html(result["text"])
            if result.get("finish_reason") in ("length", "max_tokens"):
                raise ValueError("Model response reached its output budget")
            artwork.parent.mkdir(parents=True, exist_ok=True)
            artwork.write_text(code)
            record.update(
                status="generated", generated_at=now(),
                artwork_sha256=hashlib.sha256(code.encode()).hexdigest(),
                **{key: value for key, value in result.items() if key != "text"},
            )
            print(f"Generated {name}: {result['tokens_out']} output tokens", flush=True)
        except Exception as error:
            record.update(status="failed", failed_at=now(), error=run.failure_details(error))
            record["reason"] = record["error"]["message"]
            if isinstance(error, ValueError):
                record["reason"] = str(error)
            failed = getattr(error, "_failed_response", None)
            if failed:
                write_json(directory / "incomplete-response.json", failed)
                write_json(attempt / "incomplete-response.json", failed)
            print(f"Failed {name}: {record['reason']}", flush=True)
        finally:
            write_json(directory / "record.json", record)
            write_json(attempt / "record.json", record)
            if model["api"] == "openai":
                await client.close()
            elif model["api"] == "bedrock":
                client.close()


async def collect(args: argparse.Namespace) -> None:
    config = run.load_config()
    models = config["models"]
    selected = set(args.models.split(",")) if args.models else None
    wanted = [model for model in models if selected is None or model["name"] in selected]
    if args.feedback:
        feedback = json.loads(Path(args.feedback).read_text())
        wanted = [{**model, "_feedback": feedback.get(model["name"]), "_fresh_repair": args.fresh_repair} for model in wanted]
    if args.temperature is not None:
        if any(model["api"] != "openai" or not model.get("base_url") for model in wanted):
            raise ValueError("Art sampling override is only supported for configured self-hosted models")
        wanted = [{**model, "_art_temperature": args.temperature} for model in wanted]
    if selected and selected - {model["name"] for model in wanted}:
        raise ValueError(f"Unknown models: {sorted(selected - {model['name'] for model in wanted})}")
    if args.managed:
        wanted = [model for model in wanted if model["api"] != "openai"]
    build_catalog(models)
    semaphore = asyncio.Semaphore(args.concurrency)
    async def task(model):
        await generate_one(model, config["aws"]["region"], semaphore)
        build_catalog(models)
    await asyncio.gather(*(task(model) for model in wanted))
    build_catalog(models)
    count = sum(record_of(model["name"])["status"] == "generated" for model in models)
    print(f"Model-authored artworks: {count}/{len(models)}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="comma-separated config model names")
    parser.add_argument("--managed", action="store_true", help="only invoke configured managed endpoints")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--publication-review", help="independent review JSON; catalog-only mode withholds artworks without a matching PASS")
    parser.add_argument("--feedback", help="JSON mapping of model names to browser feedback; same author repairs its own code")
    parser.add_argument("--fresh-repair", action="store_true", help="same author rebuilds a minimal implementation from review requirements without copying the prior broken code")
    parser.add_argument("--temperature", type=float, help="isolated self-hosted artwork sampling override; benchmark defaults remain pinned")
    parser.add_argument("--max-output-tokens", type=int, default=run.MAX_OUTPUT_TOKENS,
                        help="isolated artwork request budget; does not change benchmark defaults")
    args = parser.parse_args()
    if args.publication_review and not args.catalog_only:
        parser.error("--publication-review requires --catalog-only")
    if args.concurrency < 1 or args.concurrency > 8:
        parser.error("concurrency must be between 1 and 8")
    if args.max_output_tokens < 1024 or args.max_output_tokens > 16384:
        parser.error("max-output-tokens must be between 1024 and 16384")
    if args.temperature is not None and not 0 <= args.temperature <= 1:
        parser.error("temperature must be between 0 and 1")
    run.MAX_OUTPUT_TOKENS = args.max_output_tokens
    if args.catalog_only:
        reviews = None
        if args.publication_review:
            report = json.loads(Path(args.publication_review).read_text())
            reviews = {item["model"]: item for item in report["artifacts"]}
        build_catalog(run.load_config()["models"], reviews)
    else:
        asyncio.run(collect(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
