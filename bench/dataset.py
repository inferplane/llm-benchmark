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


def build_flores(limit_per_pair: int | None = None) -> list[dict]:
    """Extract an n-way aligned FLORES subset for every ko<->target direction.

    FLORES-plus is long-format: one row per (sentence id, language). Rows sharing
    the same id are the same sentence across all languages, so a single pass
    groups rows by id, then any (src_lang, tgt_lang) pair is a lookup away.
    """
    from datasets import load_dataset

    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    codes = scenario["flores_codes"]  # e.g. {"ko": "kor_Hang", "en": "eng_Latn", ...}
    src_lang = scenario["src_lang"]
    targets = scenario["targets"]
    per_pair = limit_per_pair or scenario["flores_per_pair"]
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
        for a, b in ((src_lang, tgt), (tgt, src_lang)):
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


def cmd_flores(args):
    records = build_flores(limit_per_pair=args.limit)
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "flores.jsonl"
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


def cmd_synthetic(args):
    cfg = load_config()
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
    p_flores.set_defaults(func=cmd_flores)

    p_syn = sub.add_parser("synthetic", help="generate synthetic financial docs")
    p_syn.add_argument("--limit", type=int, default=None, help="override synthetic_per_pair (docs per direction) for a smoke run")
    p_syn.add_argument("--concurrency", type=int, default=5, help="parallel Bedrock calls (default 5, keep modest to avoid throttling)")
    p_syn.set_defaults(func=cmd_synthetic)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
