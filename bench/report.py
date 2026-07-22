"""Aggregate a run's translations + judgments into the dashboard JSON schema.

Reads results/{run_id}/{translations,judgments}.jsonl, joins on (model, id),
computes quality/cost/latency aggregates per model — plus quality-only
breakdowns by language pair and by dataset track (FLORES human-reference vs
synthetic financial-domain) — and writes docs/results/{run_id}.json + rewrites
docs/results/index.json.

Cost and throughput are reported ONLY at the whole-model level, never per-pair
or per-track: every pair/track for a model shares the same concurrent GPU
batch, so a subset's own completion-timestamp span doesn't measure that
subset's isolated throughput — it's contaminated by whatever else that model
was serving at the same time. Slicing a number that can't be correctly sliced
would be worse than not reporting it.

Usage:
    uv run python3 -m bench.report --run-id smoke-test
"""

import argparse
import json
import random
import statistics
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

from bench.run import DATA_DIR, dedupe_latest, load_dataset

SCHEMA_VERSION = 2
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
RESULTS_DIR = ROOT / "results"
DOCS_RESULTS_DIR = ROOT / "docs/results"
AXES = ["adequacy", "terminology", "numbers_entities_dates", "fluency", "format"]
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 13

# Standard high-resource vs lower-resource split (by web/training-corpus size —
# CJK + major European languages vs. Southeast/South Asian + Arabic + Turkish),
# not a threshold fit to this run's own scores — the point is to check whether
# an *independently defined* language grouping predicts a quality gap, not to
# carve out whichever split happens to look biggest after the fact.
LANG_GROUP = {
    "en": "major", "ja": "major", "zh": "major", "es": "major", "fr": "major",
    "de": "major", "pt": "major", "ru": "major", "it": "major",
    "vi": "other", "id": "other", "th": "other", "ar": "other", "hi": "other", "tr": "other",
}


def load_config() -> dict:
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def bootstrap_ci95(values: list[float]) -> list[float] | None:
    """Percentile bootstrap 95% CI on the mean. Needed because a 0.1-0.2 gap
    between two models' judge_overall on a few dozen segments can be pure
    noise — report a range, not a false-precision point estimate."""
    if len(values) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    lo = means[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]
    return [round(lo, 3), round(hi, 3)]


def compute_cost(model_cfg: dict, tokens_in: int, tokens_out: int, throughput_tok_s: float | None) -> tuple[float, float | None]:
    """Returns (cost_total_usd, usd_per_mtok_out)."""
    if model_cfg.get("gpu_hourly_usd") is not None:
        if not throughput_tok_s:
            return 0.0, None
        usd_per_mtok_out = model_cfg["gpu_hourly_usd"] / (throughput_tok_s * 3600) * 1e6
        return round(usd_per_mtok_out * tokens_out / 1e6, 4), round(usd_per_mtok_out, 4)
    if model_cfg.get("price_per_char") is not None:
        # Amazon Translate (api="translate") bills per INPUT character, not
        # per token in/out — verified live against aws.amazon.com/translate/pricing.
        # bench.run.call_translate stores char counts under tokens_in/tokens_out
        # so this model flows through the same ResultCache/report.py join as every
        # LLM candidate, but cost here reads only tokens_in (=src chars); there is
        # no separate "output" price to apply to tokens_out.
        cost_total = tokens_in * model_cfg["price_per_char"]
        usd_per_mtok_out = cost_total / (tokens_out / 1e6) if tokens_out else None
        return round(cost_total, 4), (round(usd_per_mtok_out, 4) if usd_per_mtok_out is not None else None)
    price_in = model_cfg.get("price_in", 0)
    price_out = model_cfg.get("price_out", 0)
    cost_total = tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
    usd_per_mtok_out = cost_total / (tokens_out / 1e6) if tokens_out else None
    return round(cost_total, 4), (round(usd_per_mtok_out, 4) if usd_per_mtok_out is not None else None)


def expand_judges_with_fallbacks(judges_cfg: list[dict]) -> list[dict]:
    """A judge's fallback (see config.toml's fallback_model_id — currently
    only fable-5's content-filter fallback to opus-4.8) is a genuinely
    different model at a different price, so it needs its own entry in the
    list compute_judge_cost prices over — otherwise its `{fallback_name}_
    tokens_in/out` fields (written by bench/judge.py's
    call_judge_with_fallback) would go completely unpriced and uncounted."""
    expanded = list(judges_cfg)
    for j in judges_cfg:
        if j.get("fallback_name"):
            expanded.append({
                "name": j["fallback_name"], "model_id": j["fallback_model_id"],
                "price_in": j.get("fallback_price_in"), "price_out": j.get("fallback_price_out"),
            })
    return expanded


def compute_judge_cost(judgments: list[dict], judges_cfg: list[dict]) -> dict:
    """Judge cost is a run-level spend independent of how many candidate
    models exist — not part of any candidate's own cost_per_segment_usd,
    which is translation-side only (see CLAUDE.md). Two judges (see
    config.toml's scenario.translation.judges) score every segment
    independently and get billed at their own price — bench/judge.py stores
    each judge's tokens under a `{name}_tokens_in/out` prefix rather than one
    blended pair, since sol and fable-5 have different per-token rates and
    summing tokens before pricing would misattribute cost between them.
    Priced from each judge's own price_in/out, not [[models]] — judges are
    deliberately excluded from the candidate list (avoids a judge scoring
    its own tier), so they have no [[models]] entry."""
    per_judge = []
    cost_total = 0.0
    any_unpriced = False
    for j in judges_cfg:
        name = j["name"]
        tokens_in = sum(judg.get(f"{name}_tokens_in") or 0 for judg in judgments)
        tokens_out = sum(judg.get(f"{name}_tokens_out") or 0 for judg in judgments)
        judged = sum(1 for judg in judgments if judg.get(f"{name}_tokens_in") is not None)
        price_in, price_out = j.get("price_in"), j.get("price_out")
        if price_in is None or price_out is None:
            any_unpriced = True
            cost_usd = None
        else:
            cost_usd = round(tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out, 4)
            cost_total += cost_usd
        per_judge.append({
            "judge_model": j["model_id"], "name": name, "judged_segments": judged,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd,
        })
    return {"judges": per_judge, "cost_usd_total": None if any_unpriced else round(cost_total, 4)}


def wall_clock_seconds(successful_rows: list[dict]) -> float:
    """True elapsed time for a batch: earliest true start (a row's completion
    timestamp minus its own latency) to the latest completion. Using only the
    min/max of completion timestamps (the previous implementation) undercounts
    by roughly one request's duration, since the first request's processing
    time isn't visible until after it's already finished."""
    if not successful_rows:
        return 0.0
    starts, ends = [], []
    for r in successful_rows:
        ts = datetime.fromisoformat(r["timestamp"])
        starts.append(ts - timedelta(seconds=r.get("latency_s") or 0))
        ends.append(ts)
    return (max(ends) - min(starts)).total_seconds()


def aggregate_quality(rows: list[dict]) -> dict:
    """Quality-only aggregate — safe to compute on any subset (pair, track, or
    the whole model), since none of these fields depend on shared-batch timing.

    `rows` carries `translation_error` and `judge_error` as separate fields
    (see build_report) — a judge failure must never be mistaken for a
    translation failure, or a perfectly good translation silently drops out of
    cost/quality aggregation just because the judge call itself errored.
    """
    successful = [r for r in rows if r.get("translation_error") is None and r.get("output_text")]
    translation_failures = len(rows) - len(successful)

    # "never judged yet" (bench/judge.py hasn't run for this segment) is a
    # different state from "judge was attempted and errored" — conflating them
    # made a report built right after bench/run.py (before judging) claim 100%
    # judge failure instead of 0% judged-so-far.
    judge_attempted = [r for r in successful if r.get("judge_attempted")]
    judged = [r for r in judge_attempted if r.get("judge_error") is None and r.get("overall") is not None]
    judge_failures = len(judge_attempted) - len(judged)
    not_yet_judged = len(successful) - len(judge_attempted)
    judge_axes = {a: round(statistics.mean(r[a] for r in judged), 3) for a in AXES} if judged else {}
    overalls = [r["overall"] for r in judged]
    judge_overall = round(statistics.mean(overalls), 3) if overalls else None
    judge_overall_median = round(statistics.median(overalls), 3) if overalls else None

    chrf_rows = [r["chrf"] for r in successful if r.get("chrf") is not None]
    chrf = round(statistics.mean(chrf_rows), 2) if chrf_rows else None

    return {
        "judge_overall": judge_overall,
        "judge_overall_median": judge_overall_median,
        "judge_overall_ci95": bootstrap_ci95(overalls),
        "judge": judge_axes,
        "chrf": chrf,
        "segments": len(rows),
        "successful_translations": len(successful),
        "translation_failures": translation_failures,
        "judged_segments": len(judged),
        "judge_failures": judge_failures,
        "not_yet_judged": not_yet_judged,
    }


def aggregate_full(rows: list[dict], model_cfg: dict, src_chars_by_id: dict[str, int]) -> dict:
    """Everything in aggregate_quality, plus cost/throughput/latency — only
    valid at the whole-model level (see module docstring)."""
    quality = aggregate_quality(rows)
    successful = [r for r in rows if r.get("translation_error") is None and r.get("output_text")]

    tokens_in_total = sum(r["tokens_in"] or 0 for r in successful)
    tokens_out_total = sum(r["tokens_out"] or 0 for r in successful)
    latencies = [r["latency_s"] for r in successful if r.get("latency_s") is not None]

    wall_s = wall_clock_seconds(successful)
    throughput_tok_s = round(tokens_out_total / wall_s, 2) if wall_s > 0 else None
    cost_total, usd_per_mtok_out = compute_cost(model_cfg, tokens_in_total, tokens_out_total, throughput_tok_s)

    src_chars_total = sum(src_chars_by_id.get(r["id"], 0) for r in successful)
    cost_per_segment_usd = round(cost_total / len(successful), 5) if successful else None
    cost_per_1k_src_chars_usd = round(cost_total / (src_chars_total / 1000), 5) if src_chars_total else None

    return {
        **quality,
        "usd_per_mtok_out": usd_per_mtok_out,
        "cost_total_usd": cost_total,
        "cost_per_segment_usd": cost_per_segment_usd,
        "cost_per_1k_src_chars_usd": cost_per_1k_src_chars_usd,
        "latency_e2e_p50_s": percentile(latencies, 0.5),
        "latency_e2e_p95_s": percentile(latencies, 0.95),
        "throughput_tok_s": throughput_tok_s,
    }


def track_of(doc_type: str) -> str:
    return "flores" if doc_type == "flores" else "synthetic"


def run_config_of(model_cfg: dict, default_concurrency: int) -> dict:
    cfg = {"concurrency": model_cfg.get("concurrency", default_concurrency)}
    if model_cfg.get("gpu_hourly_usd") is not None:
        cfg.update({
            "gpu_hourly_usd": model_cfg["gpu_hourly_usd"],
            "gpu_instance_type": model_cfg.get("gpu_instance_type"),
            "tensor_parallel_size": model_cfg.get("tensor_parallel_size"),
            "quantization": model_cfg.get("quantization"),
            "extra_vllm_args": model_cfg.get("extra_vllm_args"),  # e.g. --enforce-eager, --quantization=fp8 — affects throughput comparability
            "warmup_excluded": False,  # throughput includes any cold-start; not yet measured separately
        })
    elif model_cfg.get("price_per_char") is not None:
        # Amazon Translate has no token-based pricing to report — a per-char
        # rate instead, so it gets its own branch rather than being squeezed
        # into price_in_usd_per_mtok/price_out_usd_per_mtok (which would be
        # None/None and read as "unpriced" in the dashboard).
        cfg["price_per_char_usd"] = model_cfg["price_per_char"]
    else:
        cfg.update({"price_in_usd_per_mtok": model_cfg.get("price_in"), "price_out_usd_per_mtok": model_cfg.get("price_out")})
        if model_cfg.get("mantle_reasoning_effort") is not None:
            cfg["mantle_reasoning_effort"] = model_cfg["mantle_reasoning_effort"]
        if model_cfg.get("bedrock_reasoning_effort") is not None:
            cfg["bedrock_reasoning_effort"] = model_cfg["bedrock_reasoning_effort"]
    return cfg


SAMPLES_PER_PAIR = 7


def build_samples(joined: list[dict], segments: list[dict], per_pair: int = SAMPLES_PER_PAIR) -> list[dict]:
    """A small, fixed-size (per_pair x pairs) subset of segments with every
    model's raw output alongside the source/reference, for the dashboard's
    sample-inspection view. Deliberately not "every segment x every model" —
    at full scale (3170 segments x 27 models) that would be tens of MB of
    JSON fetched on every dashboard load.

    Selection is round-robin across doc_type within each pair (sorted ids
    within each type), not a flat sort — a flat `sorted(ids)[:per_pair]`
    would starve any doc_type whose id prefix sorts later ("flores-" < "synthetic-"
    lexically), so a pair with both tracks would show 100% FLORES and 0%
    synthetic. This was a real bug, not a hypothetical: it silently produced
    a 150-sample set with zero synthetic (financial-domain) documents."""
    seg_by_id = {s["id"]: s for s in segments}
    ids_by_pair_type: dict[str, dict[str, list[str]]] = {}
    for seg in segments:
        pair = f"{seg['src_lang']}-{seg['tgt_lang']}"
        ids_by_pair_type.setdefault(pair, {}).setdefault(seg["doc_type"], []).append(seg["id"])

    sample_ids = set()
    for pair, by_type in ids_by_pair_type.items():
        type_queues = [sorted(ids) for ids in by_type.values()]
        picked = []
        while len(picked) < per_pair and any(type_queues):
            for q in type_queues:
                if q and len(picked) < per_pair:
                    picked.append(q.pop(0))
        sample_ids.update(picked)

    rows_by_id: dict[str, list[dict]] = {}
    for r in joined:
        if r["id"] in sample_ids:
            rows_by_id.setdefault(r["id"], []).append(r)

    samples = []
    for seg_id in sorted(sample_ids):
        seg = seg_by_id.get(seg_id)
        if seg is None:
            continue
        by_model = {}
        for r in rows_by_id.get(seg_id, []):
            by_model[r["model"]] = {
                "output_text": r.get("output_text"),
                "translation_error": r.get("translation_error"),
                "judge_error": r.get("judge_error"),
                "overall": r.get("overall"),
                "judge": {a: r.get(a) for a in AXES},
                "chrf": r.get("chrf"),
            }
        samples.append({
            "id": seg_id,
            "pair": f"{seg['src_lang']}-{seg['tgt_lang']}",
            "doc_type": seg["doc_type"],
            "src_text": seg["src_text"],
            "ref_text": seg.get("ref_text"),
            "by_model": by_model,
        })
    return samples


def build_report(run_id: str, scenario_cfg: dict, models_cfg: list[dict], dataset_paths: list[Path]) -> dict:
    run_dir = RESULTS_DIR / run_id
    translations = dedupe_latest(load_jsonl(run_dir / "translations.jsonl"), lambda r: (r["model"], r["id"]))
    judgments = dedupe_latest(load_jsonl(run_dir / "judgments.jsonl"), lambda r: (r["model"], r["id"]))
    judgments_by_key = {(j["model"], j["id"]): j for j in judgments}

    segments = load_dataset(dataset_paths)
    src_chars_by_id = {s["id"]: len(s["src_text"]) for s in segments}
    doc_type_by_id = {s["id"]: s["doc_type"] for s in segments}

    joined = []
    for t in translations:
        j = judgments_by_key.get((t["model"], t["id"]), {})
        row = {**t, "translation_error": t.get("error"), "judge_attempted": bool(j)}
        for k, v in j.items():
            if k == "error":
                row["judge_error"] = v
            elif k not in ("model", "id"):
                row[k] = v
        row.setdefault("judge_error", None)
        row["doc_type"] = doc_type_by_id.get(t["id"], t.get("doc_type"))
        joined.append(row)

    model_cfg_by_name = {m["name"]: m for m in models_cfg}
    default_concurrency = scenario_cfg["concurrency_default"]

    models_out = []
    for name, model_cfg in model_cfg_by_name.items():
        rows = [r for r in joined if r["model"] == name]
        if not rows:
            continue

        by_pair = {}
        for src, tgt in {(r["src_lang"], r["tgt_lang"]) for r in rows}:
            pair_rows = [r for r in rows if r["src_lang"] == src and r["tgt_lang"] == tgt]
            by_pair[f"{src}-{tgt}"] = aggregate_quality(pair_rows)

        by_track = {}
        for track in {track_of(r["doc_type"]) for r in rows}:
            track_rows = [r for r in rows if track_of(r["doc_type"]) == track]
            by_track[track] = aggregate_quality(track_rows)

        # Non-ko side of each pair determines its resource group (see LANG_GROUP) —
        # ko is the pivot language in every pair, never itself the classified side.
        by_lang_group = {}
        for group in ("major", "other"):
            group_rows = [r for r in rows if LANG_GROUP.get(r["src_lang"] if r["src_lang"] != "ko" else r["tgt_lang"]) == group]
            if group_rows:
                by_lang_group[group] = aggregate_quality(group_rows)

        # "openai" api covers both the real OpenAI API and vLLM (OpenAI-compatible);
        # a base_url means it's a self-hosted GPU model, not the managed OpenAI API.
        provider = "vllm" if model_cfg.get("base_url") else model_cfg["api"]
        models_out.append({
            "name": name,
            "provider": provider,
            "run_config": run_config_of(model_cfg, default_concurrency),
            "aggregate": aggregate_full(rows, model_cfg, src_chars_by_id),
            "by_pair": by_pair,
            "by_track": by_track,
            "by_lang_group": by_lang_group,
        })

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    # Optional, hand-authored per-run interpretation note (results/<run_id>/interpretation.md).
    # Never auto-generated from the aggregates at render time — a curated read of the actual
    # numbers, not a templated "top model is X" that would misfire on close CI overlaps.
    interpretation_path = run_dir / "interpretation.md"
    interpretation = interpretation_path.read_text(encoding="utf-8").strip() if interpretation_path.exists() else None

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "scenario": "translation",
        "interpretation": interpretation,
        "dataset": {
            "flores_per_pair": scenario_cfg["flores_per_pair"],
            "synthetic_per_pair": scenario_cfg["synthetic_per_pair"],
            "pairs": len({(r["src_lang"], r["tgt_lang"]) for r in joined}),
            "tracks": {t: sum(1 for id_, dt in doc_type_by_id.items() if track_of(dt) == t) for t in ("flores", "synthetic")},
        },
        "manifest": manifest,
        "judge_cost": compute_judge_cost(judgments, expand_judges_with_fallbacks(scenario_cfg["judges"])),
        "models": models_out,
        "samples": build_samples(joined, segments),
    }


def write_report(report: dict):
    DOCS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_RESULTS_DIR / f"{report['run_id']}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    run_files = sorted(p.name for p in DOCS_RESULTS_DIR.glob("*.json") if p.name != "index.json")
    (DOCS_RESULTS_DIR / "index.json").write_text(json.dumps(run_files, indent=2), encoding="utf-8")
    return out_path


def _selfcheck():
    """Money-path self-check: hand-computed cost/aggregate must match compute_cost/aggregate_full."""
    api_model = {"api": "bedrock", "price_in": 1.0, "price_out": 5.0}
    cost, per_mtok = compute_cost(api_model, tokens_in=1_000_000, tokens_out=500_000, throughput_tok_s=100)
    assert cost == 1.0 + 2.5, f"expected 3.5, got {cost}"
    # usd_per_mtok_out blends input+output cost, amortized over output tokens: 3.5 / 0.5 = 7.0
    assert per_mtok == 7.0, f"expected 7.0 usd/mtok_out, got {per_mtok}"

    vllm_model = {"api": "openai", "gpu_hourly_usd": 3600.0}  # $1/sec, easy mental math
    cost, per_mtok = compute_cost(vllm_model, tokens_in=0, tokens_out=1_000_000, throughput_tok_s=1000)
    # 1000 tok/s -> 1M tokens takes 1000s -> $1000 spent producing 1M output tokens
    assert per_mtok == 1000.0, f"expected 1000.0, got {per_mtok}"
    assert cost == 1000.0, f"expected 1000.0, got {cost}"

    # Amazon Translate: billed per INPUT character (tokens_in here IS char
    # count, see bench.run.call_translate) — tokens_out must NOT be priced,
    # unlike every LLM branch above.
    translate_model = {"api": "translate", "price_per_char": 0.000015}
    cost, per_mtok = compute_cost(translate_model, tokens_in=1000, tokens_out=1200, throughput_tok_s=None)
    assert cost == 0.015, f"expected 0.015, got {cost}"
    assert per_mtok == round(0.015 / (1200 / 1e6), 4), per_mtok

    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([], 0.5) is None

    # wall_clock_seconds must include the first request's own duration, not just
    # the span between completion timestamps (see docstring) — two 10s-latency
    # requests completing at t=10s and t=15s (5s apart) actually span 15s of
    # wall clock (the first one was already running from t=0), not 5s.
    rows_timing = [
        {"timestamp": "2026-01-01T00:00:10+00:00", "latency_s": 10.0},
        {"timestamp": "2026-01-01T00:00:15+00:00", "latency_s": 10.0},
    ]
    assert wall_clock_seconds(rows_timing) == 15.0, wall_clock_seconds(rows_timing)

    # translation_error vs judge_error must be independent: a translation that
    # succeeded but whose judge call failed must still count as a successful
    # translation (tokens/cost intact) while contributing zero judged segments.
    # "d" additionally covers not-yet-judged (judge.py hasn't run for it at
    # all) — distinct from "b"'s judge-attempted-and-errored.
    rows = [
        {"model": "m", "id": "a", "translation_error": None, "judge_error": None, "judge_attempted": True,
         "output_text": "x", "tokens_in": 10, "tokens_out": 5, "latency_s": 1.0,
         "timestamp": "2026-01-01T00:00:01+00:00", "overall": 4.0, **{a: 4.0 for a in AXES}, "chrf": 50.0},
        {"model": "m", "id": "b", "translation_error": None, "judge_error": "judge timed out", "judge_attempted": True,
         "output_text": "y", "tokens_in": 10, "tokens_out": 5, "latency_s": 1.0,
         "timestamp": "2026-01-01T00:00:01+00:00", "overall": None, **{a: None for a in AXES}, "chrf": None},
        {"model": "m", "id": "c", "translation_error": "throttled", "judge_error": None, "judge_attempted": False,
         "output_text": None, "tokens_in": None, "tokens_out": None, "latency_s": None, "timestamp": None,
         "overall": None, **{a: None for a in AXES}, "chrf": None},
        {"model": "m", "id": "d", "translation_error": None, "judge_error": None, "judge_attempted": False,
         "output_text": "z", "tokens_in": 10, "tokens_out": 5, "latency_s": 1.0,
         "timestamp": "2026-01-01T00:00:01+00:00", "overall": None, **{a: None for a in AXES}, "chrf": None},
    ]
    agg = aggregate_full(rows, {"api": "bedrock", "price_in": 1.0, "price_out": 1.0}, src_chars_by_id={})
    assert agg["segments"] == 4
    assert agg["successful_translations"] == 3, agg["successful_translations"]  # a, b, d — not c
    assert agg["translation_failures"] == 1
    assert agg["judged_segments"] == 1  # only a
    assert agg["judge_failures"] == 1   # only b: attempted and errored
    assert agg["not_yet_judged"] == 1   # only d: never attempted
    assert agg["judge_overall"] == 4.0
    assert agg["chrf"] == 50.0
    assert agg["cost_per_segment_usd"] == round(agg["cost_total_usd"] / 3, 5)

    # judge cost is a run-level spend independent of candidate count, split
    # across two independently-priced judges (see config.toml's
    # scenario.translation.judges) — a judgment with null tokens for a given
    # judge (that judge's call errored) must not count as judged by that
    # judge or contribute tokens, but must not crash the sum, and each
    # judge's tokens must be priced at that judge's own rate, not blended.
    judgments_jc = [
        {"judge-a_tokens_in": 1_000_000, "judge-a_tokens_out": 500_000, "judge-b_tokens_in": 2_000_000, "judge-b_tokens_out": 100_000},
        {"judge-a_tokens_in": None, "judge-a_tokens_out": None, "judge-b_tokens_in": 2_000_000, "judge-b_tokens_out": 100_000},
    ]
    judges_jc = [
        {"name": "judge-a", "model_id": "m-a", "price_in": 1.0, "price_out": 5.0},
        {"name": "judge-b", "model_id": "m-b", "price_in": 2.0, "price_out": 10.0},
    ]
    jc = compute_judge_cost(judgments_jc, judges_jc)
    by_name = {j["name"]: j for j in jc["judges"]}
    assert by_name["judge-a"]["judged_segments"] == 1, jc  # only the first row
    assert by_name["judge-a"]["cost_usd"] == 3.5, jc  # 1M/1M tok @ $1/$5 = 1.0 + 2.5
    assert by_name["judge-b"]["judged_segments"] == 2, jc  # both rows
    assert by_name["judge-b"]["cost_usd"] == 10.0, jc  # 4M in @ $2 + 200k out @ $10 = 8.0 + 2.0
    assert jc["cost_usd_total"] == 13.5, jc  # 3.5 + 10.0

    # expand_judges_with_fallbacks must add the fallback as its OWN priced
    # entry (a different model at a different rate — see config.toml's
    # fallback_model_id) — a judge with no fallback configured must pass
    # through unchanged.
    judges_with_fb = [
        {"name": "sol", "model_id": "m-sol", "price_in": 5.0, "price_out": 30.0},
        {"name": "fable-5", "model_id": "m-fable", "price_in": 10.0, "price_out": 50.0,
         "fallback_name": "fable-5-fallback", "fallback_model_id": "m-opus", "fallback_price_in": 5.0, "fallback_price_out": 25.0},
    ]
    expanded = expand_judges_with_fallbacks(judges_with_fb)
    assert [j["name"] for j in expanded] == ["sol", "fable-5", "fable-5-fallback"], expanded
    fb_entry = expanded[-1]
    assert fb_entry["model_id"] == "m-opus" and fb_entry["price_in"] == 5.0 and fb_entry["price_out"] == 25.0, fb_entry
    unpriced_judges = [{"name": "judge-a", "model_id": "m-a", "price_in": None, "price_out": None}]
    assert compute_judge_cost(judgments_jc, unpriced_judges)["cost_usd_total"] is None

    # build_samples: capped at per_pair per pair regardless of how many
    # segments/models exist, deterministic (lowest ids), and every model's
    # row for a sampled id shows up under by_model — including failures.
    segs = [
        {"id": "flores-1-ko-en", "src_lang": "ko", "tgt_lang": "en", "doc_type": "flores", "src_text": "a", "ref_text": "A"},
        {"id": "flores-2-ko-en", "src_lang": "ko", "tgt_lang": "en", "doc_type": "flores", "src_text": "b", "ref_text": "B"},
        {"id": "flores-3-ko-en", "src_lang": "ko", "tgt_lang": "en", "doc_type": "flores", "src_text": "c", "ref_text": "C"},
    ]
    joined_s = [
        {"model": "m1", "id": "flores-1-ko-en", "output_text": "x", "translation_error": None, "judge_error": None, "overall": 4.0, **{a: 4.0 for a in AXES}, "chrf": 50.0},
        {"model": "m2", "id": "flores-1-ko-en", "output_text": None, "translation_error": "throttled", "judge_error": None, "overall": None, **{a: None for a in AXES}, "chrf": None},
    ]
    samples = build_samples(joined_s, segs, per_pair=2)
    assert len(samples) == 2, samples  # capped at 2 of the 3 available for this pair
    assert [s["id"] for s in samples] == ["flores-1-ko-en", "flores-2-ko-en"]  # lowest ids, deterministic
    s1 = samples[0]
    assert s1["src_text"] == "a" and s1["ref_text"] == "A"
    assert set(s1["by_model"]) == {"m1", "m2"}
    assert s1["by_model"]["m2"]["translation_error"] == "throttled"

    # LANG_GROUP must cover exactly the 15 non-ko languages (matches docs/app.js's
    # LANG_ORDER) with no language in both groups — a typo here would silently
    # drop a language pair out of both the "major" and "other" breakdowns.
    lang_order = {"en", "ja", "zh", "es", "fr", "de", "pt", "ru", "it", "vi", "id", "th", "ar", "hi", "tr"}
    assert set(LANG_GROUP) == lang_order, set(LANG_GROUP) ^ lang_order
    assert set(LANG_GROUP.values()) == {"major", "other"}

    print("selfcheck OK")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id")
    p.add_argument("--dataset", help="comma-separated jsonl paths (default: data/flores.jsonl,data/synthetic.jsonl)")
    p.add_argument("--selfcheck", action="store_true")
    args = p.parse_args()

    _selfcheck()
    if args.selfcheck:
        return
    if not args.run_id:
        raise SystemExit("--run-id required (or pass --selfcheck alone)")

    cfg = load_config()
    dataset_paths = [Path(p) for p in args.dataset.split(",")] if args.dataset else [
        DATA_DIR / "flores.jsonl", DATA_DIR / "synthetic.jsonl",
    ]
    report = build_report(args.run_id, cfg["scenario"]["translation"], cfg["models"], dataset_paths)
    out_path = write_report(report)
    print(f"wrote {out_path}")
    print(f"models in report: {[m['name'] for m in report['models']]}")


if __name__ == "__main__":
    main()
