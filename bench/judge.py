"""LLM-as-judge scoring for translation runs.

Reads results/{run_id}/translations.jsonl, scores each successful translation
with TWO independent judges (financial-domain rubric, see config.toml's
scenario.translation.judges) plus chrF as a sanity-check metric, and caches to
results/{run_id}/judgments.jsonl keyed by (model, id) — same skip-on-rerun
pattern as bench/run.py. A single judge can't be told apart from its own
house style/provider bias; per-axis scores are averaged across both judges
for the headline `overall`, with each judge's raw scores/tokens also kept
(prefixed by judge name) so a judge-disagreement diagnosis is possible later.

Usage:
    uv run python3 -m bench.judge --run-id smoke-test
"""

import argparse
import asyncio
import json
import tomllib
from pathlib import Path

import sacrebleu

from bench.run import LANG_NAMES, load_dataset, ResultCache, DATA_DIR, dedupe_latest, call_mantle, call_bedrock

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
RESULTS_DIR = ROOT / "results"
RUBRIC_TEMPLATE = (ROOT / "scenarios/translation/rubric.txt").read_text(encoding="utf-8")
AXES = ["adequacy", "terminology", "numbers_entities_dates", "fluency", "format"]


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def build_rubric_prompt(seg: dict, candidate: str) -> str:
    # Never show an LLM-generated reference to the judge: the synthetic set's
    # references are written by claude-sonnet-4.5, which is itself a benchmark
    # candidate. A reference anchors both chrF and the judge's own scoring
    # toward whatever style/family produced it — showing it here would bias
    # judged quality toward Claude-family candidates on exactly the segments
    # meant to test financial-domain robustness. Only FLORES's human references
    # (ref_source != "llm") are shown.
    ref_block = ""
    if seg.get("ref_text") and seg.get("ref_source") != "llm":
        ref_block = f"REFERENCE ({LANG_NAMES.get(seg['tgt_lang'], seg['tgt_lang'])}):\n{seg['ref_text']}\n"
    return RUBRIC_TEMPLATE.format(
        src_lang=LANG_NAMES.get(seg["src_lang"], seg["src_lang"]),
        tgt_lang=LANG_NAMES.get(seg["tgt_lang"], seg["tgt_lang"]),
        src_text=seg["src_text"],
        candidate_text=candidate,
        reference_block=ref_block,
    )


def parse_scores(raw: str) -> dict:
    scores = json.loads(raw)
    missing = [a for a in AXES if a not in scores]
    if missing:
        raise ValueError(f"judge response missing axes: {missing}")
    for a in AXES:
        if not (1 <= float(scores[a]) <= 5):
            raise ValueError(f"axis {a} out of range 1-5: {scores[a]}")
    return {a: float(scores[a]) for a in AXES}


async def call_judge(clients: dict, judge_cfg: dict, prompt: str) -> dict:
    """Dispatches to call_mantle or call_bedrock depending on the judge's own
    `api` (fable-5 is a plain Bedrock Converse model, not mantle — see
    config.toml). Returns the same {"text", "tokens_in", "tokens_out"} shape
    either way, so callers don't need to care which API backs a given judge."""
    if judge_cfg["api"] == "bedrock_mantle":
        return await call_mantle(
            clients["mantle_session"], judge_cfg.get("mantle_region", "us-east-1"),
            judge_cfg["model_id"], prompt, response_format={"type": "json_object"},
        )
    else:
        return await call_bedrock(clients["bedrock_client"], judge_cfg["model_id"], prompt)


async def judge_one(clients: dict, judges_cfg: list[dict], seg: dict, candidate: str) -> dict:
    prompt = build_rubric_prompt(seg, candidate)
    # Both judges are called concurrently and must BOTH succeed — averaging a
    # real score with a missing one would silently reintroduce the exact
    # single-judge bias this dual-judge setup exists to remove. gather without
    # return_exceptions lets the first failure raise immediately, same
    # all-or-nothing contract as a single judge_one call failing.
    results = await asyncio.gather(*(call_judge(clients, j, prompt) for j in judges_cfg))

    per_judge = {}
    for j, result in zip(judges_cfg, results):
        scores = parse_scores(result["text"])
        scores["overall"] = round(sum(scores.values()) / len(scores), 3)
        per_judge[j["name"]] = {**scores, "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"]}

    averaged = {a: round(sum(per_judge[j["name"]][a] for j in judges_cfg) / len(judges_cfg), 3) for a in AXES}
    averaged["overall"] = round(sum(averaged.values()) / len(averaged), 3)

    # chrF against an LLM-generated reference measures "similarity to that LLM's
    # style," not translation quality — same contamination as the ref_block above.
    if seg.get("ref_text") and seg.get("ref_source") != "llm":
        averaged["chrf"] = round(sacrebleu.sentence_chrf(candidate, [seg["ref_text"]]).score, 2)
    else:
        averaged["chrf"] = None

    # Per-judge raw scores/tokens kept prefixed by judge name — lets a later
    # analysis flag segments where sol/fable-5 disagree sharply, and lets
    # bench/report.py's compute_judge_cost bill each judge at its own price
    # (see config.toml's scenario.translation.judges) rather than blending
    # tokens together under one rate.
    out = dict(averaged)
    for name, pj in per_judge.items():
        for k, v in pj.items():
            out[f"{name}_{k}"] = v
    return out


async def main_async(args):
    import boto3

    cfg = load_config()
    scenario = cfg["scenario"]["translation"]
    judges_cfg = scenario["judges"]
    # One shared boto3.Session (mantle path, SigV4) and one shared
    # bedrock-runtime client (plain Converse path) cover every judge
    # regardless of how many use each api — same reuse rationale as
    # bench.run.make_client.
    clients = {"mantle_session": boto3.Session(), "bedrock_client": boto3.client("bedrock-runtime", region_name=cfg["aws"]["region"])}

    run_dir = RESULTS_DIR / args.run_id
    translations_path = run_dir / "translations.jsonl"
    if not translations_path.exists():
        raise SystemExit(f"no translations found at {translations_path} — run bench/run.py first")

    with open(translations_path, encoding="utf-8") as f:
        translations = [json.loads(line) for line in f if line.strip()]
    # dedupe to the last attempt per (model, id) before filtering — a segment
    # that failed once and later succeeded has both rows on disk; judging the
    # stale failed row (or double-judging both) would be wrong.
    translations = dedupe_latest(translations, lambda r: (r["model"], r["id"]))
    translations = [t for t in translations if t["error"] is None and t["output_text"]]
    if args.limit:
        translations = translations[: args.limit]

    dataset_paths = [Path(p) for p in args.dataset.split(",")] if args.dataset else [
        DATA_DIR / "flores.jsonl", DATA_DIR / "synthetic.jsonl",
    ]
    segments_by_id = {s["id"]: s for s in load_dataset(dataset_paths)}

    cache = ResultCache(run_dir / "judgments.jsonl")
    todo = [t for t in translations if not cache.has(t["model"], t["id"])]
    print(f"{len(todo)}/{len(translations)} translations need judging")

    sem = asyncio.Semaphore(args.concurrency)

    async def one(t: dict):
        seg = segments_by_id.get(t["id"])
        if seg is None:
            print(f"WARN: segment {t['id']} not found in dataset, skipping judge")
            return
        async with sem:
            try:
                scores = await judge_one(clients, judges_cfg, seg, t["output_text"])
                error = None
            except Exception as e:
                # Same all-null shape as the single-judge case, plus a null
                # placeholder per judge's own axes/tokens — so a partially
                # failed pair (e.g. sol succeeded, fable-5 timed out) never
                # leaves stray per-judge fields for report.py to average
                # against a missing counterpart.
                scores = {a: None for a in AXES} | {"overall": None, "chrf": None}
                for j in judges_cfg:
                    scores |= {f"{j['name']}_{a}": None for a in AXES}
                    scores |= {f"{j['name']}_overall": None, f"{j['name']}_tokens_in": None, f"{j['name']}_tokens_out": None}
                error = str(e)
            await cache.append({"model": t["model"], "id": t["id"], **scores, "error": error})

    await asyncio.gather(*(one(t) for t in todo))
    print(f"done -> {cache.path}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--limit", type=int, help="judge only the first N cached translations (smoke runs)")
    p.add_argument("--dataset", help="comma-separated jsonl paths (default: data/flores.jsonl,data/synthetic.jsonl)")
    p.add_argument("--concurrency", type=int, default=8)
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
