"""Dataset prep for the translation scenario.

Subcommands:
    flores      pull FLORES-200 (openlanguagedata/flores_plus) subset, write data/flores.jsonl
    synthetic   generate financial-domain KR docs + reference translations, write data/synthetic.jsonl

Record shape (both subcommands, shared by bench/run.py):
    {"id": str, "src_lang": "ko", "tgt_lang": "en", "src_text": str, "ref_text": str|null,
     "doc_type": "flores"|"earnings"|"disclosure"|"terms"|"fund", "ref_source": "human"|"llm"}
"""

import argparse
import asyncio
import json
import random
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
DATA_DIR = ROOT / "data"
SEED = 13


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def build_flores(limit_per_pair: int | None = None, src_lang: str | None = None, to_lang: str | None = None) -> list[dict]:
    """Extract an n-way aligned FLORES subset for every ko<->target direction.

    FLORES-plus is long-format: one row per (sentence id, language). Rows sharing
    the same id are the same sentence across all languages, so a single pass
    groups rows by id, then any (src_lang, tgt_lang) pair is a lookup away.
    """
    from datasets import load_dataset

    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    codes = scenario["flores_codes"]  # e.g. {"ko": "kor_Hang", "en": "eng_Latn", ...}
    pivot = scenario["src_lang"]
    src_lang = src_lang or pivot
    # Extra source language (en): one-way src->X only, never X->src, and never
    # the pivot's own pairs (en->ko already lives in data/flores.jsonl).
    extra_src = src_lang != pivot
    targets = [t for t in scenario["targets"] if t != src_lang]
    per_pair = limit_per_pair or scenario["flores_per_pair"]
    if to_lang:  # reverse: every non-pivot, non-to_lang language -> to_lang
        targets = [t for t in scenario["targets"] if t != to_lang]
    wanted_codes = set(codes.values())

    ds = load_dataset("openlanguagedata/flores_plus", split="devtest")
    by_id: dict[str, dict[str, str]] = {}
    for row in ds:
        lang_code = f"{row['iso_639_3']}_{row['iso_15924']}"
        if lang_code not in wanted_codes:
            continue
        by_id.setdefault(row["id"], {})[lang_code] = row["text"]

    # keep only sentences present in every language we need
    complete_ids = [i for i, langs in by_id.items() if wanted_codes <= langs.keys()]
    rng = random.Random(SEED)
    rng.shuffle(complete_ids)

    records = []
    for tgt in targets:
        for a, b in (((tgt, to_lang),) if to_lang else ((src_lang, tgt),) if extra_src else ((src_lang, tgt), (tgt, src_lang))):
            for sent_id in complete_ids[:per_pair]:
                langs = by_id[sent_id]
                records.append({
                    "id": f"flores-{sent_id}-{a}-{b}",
                    "src_lang": a,
                    "tgt_lang": b,
                    "src_text": langs[codes[a]],
                    "ref_text": langs[codes[b]],
                    "doc_type": "flores",
                    "ref_source": "human",
                })
    return records


def _out_path(base: str, src_lang: str | None) -> Path:
    # Extra source languages get their own file: data/flores.jsonl and
    # data/synthetic.jsonl stay byte-stable so old runs/reports keep their
    # segment denominators.
    return DATA_DIR / (f"{base}-{src_lang}.jsonl" if src_lang else f"{base}.jsonl")


def cmd_flores(args):
    records = build_flores(limit_per_pair=args.limit, src_lang=args.src, to_lang=args.to)
    DATA_DIR.mkdir(exist_ok=True)
    out = _out_path("flores", f"to-{args.to}" if args.to else args.src)
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} rows -> {out}")


DOC_TYPES = ["earnings", "disclosure", "terms", "fund"]
DOC_TYPE_HINTS = {
    "earnings": "Format as a quarterly earnings report excerpt (실적발표), with a markdown table of "
                "매출/영업이익/순이익 across the last 3 quarters.",
    "disclosure": "Format as a regulatory disclosure filing (공시), e.g. a major shareholder change or "
                  "business agreement, with specific dates, amounts, and entity names.",
    "terms": "Format as terms and conditions clauses (약관) for a financial product, numbered clauses, "
             "with specific fee percentages and amounts.",
    "fund": "Format as a fund product description (펀드 설명서), with a markdown table of fees and "
            "historical annual returns, plus a risk disclosure paragraph.",
}
LANG_LABELS = {  # matches bench.run.LANG_NAMES; duplicated here to keep dataset.py import-light
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese", "es": "Spanish",
    "fr": "French", "de": "German", "pt": "Portuguese", "ru": "Russian", "it": "Italian",
    "vi": "Vietnamese", "id": "Indonesian", "th": "Thai", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish",
}

GENERATE_PROMPT = """You are generating a synthetic {lang} financial document for an LLM translation benchmark.
Write ONE realistic {lang} financial document. {hint}

Requirements:
- 300-600 tokens of {lang} text
- Include specific numbers, currency amounts, dates, and company/entity names
- Include at least one markdown table
- Output ONLY the document text (markdown), no preamble, no explanation
"""


async def _generate_doc(client, model_id: str, lang_code: str, doc_type: str) -> str:
    from bench.run import call_bedrock

    prompt = GENERATE_PROMPT.format(
        lang=LANG_LABELS[lang_code], hint=DOC_TYPE_HINTS[doc_type],
    )
    result = await call_bedrock(client, model_id, prompt)
    return result["text"]


async def _translate_doc(client, model_id: str, src_lang: str, tgt_lang: str, text: str) -> str:
    from bench.run import call_bedrock, build_prompt

    result = await call_bedrock(
        client, model_id, build_prompt({"src_lang": src_lang, "tgt_lang": tgt_lang, "src_text": text})
    )
    return result["text"]


async def build_synthetic_async(n_per_direction: int, concurrency: int) -> list[dict]:
    import boto3

    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    src_lang = scenario["src_lang"]
    targets = scenario["targets"]
    sonnet_id = next(m["model_id"] for m in cfg["models"] if m["name"] == "claude-sonnet-4.5")
    client = boto3.client("bedrock-runtime", region_name=cfg["aws"]["region"])
    sem = asyncio.Semaphore(concurrency)

    async def gen(lang, doc_type):
        async with sem:
            return await _generate_doc(client, sonnet_id, lang, doc_type)

    async def translate(a, b, text):
        async with sem:
            return await _translate_doc(client, sonnet_id, a, b, text)

    records = []

    # ko -> targets: n_per_direction Korean source docs, each translated into every target language
    doc_types_cycle = [DOC_TYPES[i % len(DOC_TYPES)] for i in range(n_per_direction)]
    ko_docs = await asyncio.gather(*(gen(src_lang, dt) for dt in doc_types_cycle))
    for i, (doc_type, ko_text) in enumerate(zip(doc_types_cycle, ko_docs)):
        translations = await asyncio.gather(*(translate(src_lang, tgt, ko_text) for tgt in targets))
        for tgt, ref_text in zip(targets, translations):
            records.append({
                "id": f"synthetic-ko{i}-{src_lang}-{tgt}", "src_lang": src_lang, "tgt_lang": tgt,
                "src_text": ko_text, "ref_text": ref_text, "doc_type": doc_type, "ref_source": "llm",
            })

    # anchor X -> ko: all 15 target languages, each with its own generated
    # source-language financial doc — widened from an en/ja-only 2-language
    # anchor set (FLORES alone covered the other 13 reverse directions, but
    # only with general-domain sentences, not financial-domain ones).
    for anchor in targets:
        anchor_doc_types = [DOC_TYPES[i % len(DOC_TYPES)] for i in range(n_per_direction)]
        anchor_docs = await asyncio.gather(*(gen(anchor, dt) for dt in anchor_doc_types))
        ko_refs = await asyncio.gather(*(translate(anchor, src_lang, text) for text in anchor_docs))
        for i, (doc_type, text, ref) in enumerate(zip(anchor_doc_types, anchor_docs, ko_refs)):
            records.append({
                "id": f"synthetic-{anchor}{i}-{anchor}-{src_lang}", "src_lang": anchor, "tgt_lang": src_lang,
                "src_text": text, "ref_text": ref, "doc_type": doc_type, "ref_source": "llm",
            })

    return records


async def build_synthetic_from_existing_async(src_lang: str, concurrency: int) -> list[dict]:
    """Extra-source synthetic track that reuses the source docs already in
    data/synthetic.jsonl (the `{src_lang}->ko` anchor rows) instead of
    generating new ones, so no existing id's content can change. Only the
    Sonnet reference translations into the other targets are new."""
    import boto3

    cfg = load_config()
    targets = [t for t in cfg["scenario"]["translation"]["targets"] if t != src_lang]
    sonnet_id = next(m["model_id"] for m in cfg["models"] if m["name"] == "claude-sonnet-4.5")
    client = boto3.client("bedrock-runtime", region_name=cfg["aws"]["region"])
    sem = asyncio.Semaphore(concurrency)

    with open(DATA_DIR / "synthetic.jsonl", encoding="utf-8") as f:
        anchors = [r for r in map(json.loads, f) if r["src_lang"] == src_lang and r["id"].startswith(f"synthetic-{src_lang}")]
    anchors.sort(key=lambda r: int(r["id"].split("-")[1][len(src_lang):]))
    if not anchors:
        raise SystemExit(f"no {src_lang}->* anchor docs in data/synthetic.jsonl")

    async def translate(tgt, text):
        async with sem:
            return await _translate_doc(client, sonnet_id, src_lang, tgt, text)

    records = []
    for anchor in anchors:
        idx = anchor["id"].split("-")[1]  # e.g. "en3"
        refs = await asyncio.gather(*(translate(tgt, anchor["src_text"]) for tgt in targets))
        for tgt, ref_text in zip(targets, refs):
            records.append({
                "id": f"synthetic-{idx}-{src_lang}-{tgt}", "src_lang": src_lang, "tgt_lang": tgt,
                "src_text": anchor["src_text"], "ref_text": ref_text, "doc_type": anchor["doc_type"], "ref_source": "llm",
            })
    return records


async def build_synthetic_to_async(to_lang: str, concurrency: int) -> list[dict]:
    """Reverse X->to_lang track: reuse the existing X->ko anchor docs in
    data/synthetic.jsonl and add Sonnet references into to_lang."""
    import boto3

    cfg = load_config()
    sources = [t for t in cfg["scenario"]["translation"]["targets"] if t != to_lang]
    sonnet_id = next(m["model_id"] for m in cfg["models"] if m["name"] == "claude-sonnet-4.5")
    client = boto3.client("bedrock-runtime", region_name=cfg["aws"]["region"])
    sem = asyncio.Semaphore(concurrency)
    with open(DATA_DIR / "synthetic.jsonl", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    anchors = [r for r in rows if r["tgt_lang"] == "ko" and r["src_lang"] in sources]
    assert len(anchors) == len(sources) * (len(anchors) // len(sources)) and anchors, "anchor docs missing"

    async def translate(r):
        async with sem:
            return await _translate_doc(client, sonnet_id, r["src_lang"], to_lang, r["src_text"])

    refs = await asyncio.gather(*(translate(r) for r in anchors))
    return [{
        "id": r["id"].rsplit("-", 1)[0] + f"-{to_lang}", "src_lang": r["src_lang"], "tgt_lang": to_lang,
        "src_text": r["src_text"], "ref_text": ref, "doc_type": r["doc_type"], "ref_source": "llm",
    } for r, ref in zip(anchors, refs)]


def cmd_synthetic(args):
    cfg = load_config()
    if args.to:
        records = asyncio.run(build_synthetic_to_async(args.to, args.concurrency))
        out = _out_path("synthetic", f"to-{args.to}")
        with open(out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(records)} rows -> {out}")
        return
    if args.src:
        records = asyncio.run(build_synthetic_from_existing_async(args.src, args.concurrency))
        out = _out_path("synthetic", args.src)
        with open(out, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(records)} rows -> {out}")
        return
    n = args.limit or cfg["scenario"]["translation"]["synthetic_per_pair"]
    records = asyncio.run(build_synthetic_async(n, args.concurrency))
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "synthetic.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} rows -> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_flores = sub.add_parser("flores", help="extract FLORES subset")
    p_flores.add_argument("--limit", type=int, default=None, help="override flores_per_pair for a smoke run")
    p_flores.add_argument("--src", default=None, help="extra source language (e.g. en): writes data/flores-<src>.jsonl with src->X pairs only")
    p_flores.add_argument("--to", default=None, help="reverse direction (e.g. en): X->en pairs, writes data/flores-to-<to>.jsonl")
    p_flores.set_defaults(func=cmd_flores)

    p_syn = sub.add_parser("synthetic", help="generate synthetic financial docs")
    p_syn.add_argument("--limit", type=int, default=None, help="override synthetic_per_pair (docs per direction) for a smoke run")
    p_syn.add_argument("--concurrency", type=int, default=5, help="parallel Bedrock calls (default 5, keep modest to avoid throttling)")
    p_syn.add_argument("--src", default=None, help="extra source language (e.g. en): reuse existing <src>->ko docs, translate into the other targets, write data/synthetic-<src>.jsonl")
    p_syn.add_argument("--to", default=None, help="reverse direction (e.g. en): reuse X->ko docs, translate into <to>, write data/synthetic-to-<to>.jsonl")
    p_syn.set_defaults(func=cmd_synthetic)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
