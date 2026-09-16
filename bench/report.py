"""Aggregate a run's translations + judgments into the dashboard JSON schema.

Reads results/{run_id}/{translations,judgments}.jsonl, joins on (model, id),
computes quality/cost/latency aggregates per model — plus quality-only
breakdowns by language pair and by dataset track (FLORES human-reference vs
synthetic financial-domain) — and writes docs/results/{run_id}.json + rewrites
docs/results/index.json. Optional --include-run sources load before the primary
run, deduplicating observations without copying or modifying their caches.

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
import re
import statistics
import tomllib
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from bench.run import BEDROCK_NO_TEMPERATURE, DATA_DIR, MANTLE_NO_TEMPERATURE, REQUEST_TIMEOUT_S, dedupe_latest, load_dataset

SCHEMA_VERSION = 2
ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.toml"
RESULTS_DIR = ROOT / "results"
DOCS_RESULTS_DIR = ROOT / "docs/results"
AXES = ["adequacy", "terminology", "numbers_entities_dates", "fluency", "format"]
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 13
QUALITY_PASS_MIN = 4
HIGH_RISK_MAX = 2
JUDGE_DISAGREEMENT_MIN = 1
BASELINE_MODEL = "amazon-translate"

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


def valid_score(value) -> bool:
    """Only finite numeric rubric scores in 1–5 count as observations."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 5


def valid_judgment(row: dict) -> bool:
    return (
        row.get("translation_error") is None and bool(row.get("output_text"))
        and bool(row.get("judge_attempted")) and row.get("judge_error") is None
        and all(valid_score(row.get(axis)) for axis in [*AXES, "overall"])
    )


def raw_judge_scores(row: dict) -> list[dict] | None:
    """Read two actual judges, never substitute averaged or stale primary scores.

    Explicit judges_used is authoritative, including malformed values. Only
    when that key is absent can legacy raw-score prefixes supply identities:
    exactly two groups, both with every axis and overall valid. Extra groups
    or incomplete evidence cannot establish which two judges contributed.
    """
    if "judges_used" in row:
        names = row["judges_used"]
    else:
        names = sorted({
            key[:-(len(axis) + 1)]
            for key in row for axis in [*AXES, "overall"]
            if key.endswith(f"_{axis}") and len(key) > len(axis) + 1
        })
    if (not isinstance(names, list) or len(names) != 2
            or not all(isinstance(name, str) and name for name in names)
            or names[0] == names[1]):
        return None
    scores = [{axis: row.get(f"{name}_{axis}") for axis in [*AXES, "overall"]} for name in names]
    return scores if all(valid_score(value) for score in scores for value in score.values()) else None


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
    judged = [r for r in judge_attempted if valid_judgment(r)]
    judge_failures = len(judge_attempted) - len(judged)
    not_yet_judged = len(successful) - len(judge_attempted)
    judge_axes = {a: round(statistics.mean(r[a] for r in judged), 3) for a in AXES} if judged else {}
    overalls = [r["overall"] for r in judged]
    judge_overall = round(statistics.mean(overalls), 3) if overalls else None
    judge_overall_median = round(statistics.median(overalls), 3) if overalls else None

    raw_scores = [scores for r in judged if (scores := raw_judge_scores(r)) is not None]
    eligible = len(raw_scores)
    passes = sum(all(score[a] >= QUALITY_PASS_MIN for score in scores for a in AXES) for scores in raw_scores)
    high_risk = sum(any(score["numbers_entities_dates"] <= HIGH_RISK_MAX for score in scores) for scores in raw_scores)
    disagreement = sum(round(abs(scores[0]["overall"] - scores[1]["overall"]), 3) >= JUDGE_DISAGREEMENT_MIN
                       for scores in raw_scores)

    chrf_rows = [r["chrf"] for r in successful if r.get("chrf") is not None]
    chrf = round(statistics.mean(chrf_rows), 2) if chrf_rows else None

    return {
        "judge_overall": judge_overall,
        "judge_overall_median": judge_overall_median,
        "judge_overall_p10": percentile(overalls, 0.1),
        "judge_overall_ci95": bootstrap_ci95(overalls),
        "quality_eligible_segments": eligible,
        "quality_pass_segments": passes,
        "quality_pass_rate": passes / eligible if eligible else None,
        "high_risk_segments": high_risk,
        "high_risk_rate": high_risk / eligible if eligible else None,
        "judge_disagreement_segments": disagreement,
        "judge_disagreement_rate": disagreement / eligible if eligible else None,
        "judge_coverage_rate": len(judged) / len(successful) if successful else None,
        "quality_coverage_rate": eligible / len(successful) if successful else None,
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

    # Cross-run deduplication can retain only a middle slice of an old batch.
    # Its timestamp span is not an independent batch measurement. Count ALL
    # rows here: a failed primary replacement still makes the old successful
    # rows a partial batch, even when only one source has successful rows.
    mixed_sources = len({row.get("translation_source_run") for row in rows}) > 1
    wall_s = wall_clock_seconds(successful) if not mixed_sources else 0.0
    throughput_tok_s = round(tokens_out_total / wall_s, 2) if wall_s > 0 else None
    if mixed_sources and model_cfg.get("gpu_hourly_usd") is not None:
        # compute_cost(None throughput) returns zero for legacy empty batches;
        # unknown mixed-run GPU spend must instead remain explicitly unknown.
        cost_total, usd_per_mtok_out = None, None
    else:
        cost_total, usd_per_mtok_out = compute_cost(model_cfg, tokens_in_total, tokens_out_total, throughput_tok_s)

    src_chars_total = sum(src_chars_by_id.get(r["id"], 0) for r in successful)
    cost_per_segment_usd = round(cost_total / len(successful), 5) if cost_total is not None and successful else None
    cost_per_1k_src_chars_usd = round(cost_total / (src_chars_total / 1000), 5) if cost_total is not None and src_chars_total else None
    # This retains the existing estimate: latest successful translation rows
    # only, excluding retries/failed attempts, judge spend and GPU idle/setup
    # outside the observed batch. Translation failures cannot be judged.
    passes = quality["quality_pass_segments"]
    complete_quality = quality["judged_segments"] == quality["quality_eligible_segments"] == len(successful)
    cost_per_quality_pass_usd = round(cost_total / passes, 5) if cost_total is not None and complete_quality and passes else None

    return {
        **quality,
        "usd_per_mtok_out": usd_per_mtok_out,
        "cost_total_usd": cost_total,
        "cost_per_segment_usd": cost_per_segment_usd,
        "cost_per_quality_pass_usd": cost_per_quality_pass_usd,
        "cost_per_1k_src_chars_usd": cost_per_1k_src_chars_usd,
        "latency_e2e_p50_s": percentile(latencies, 0.5),
        "latency_e2e_p95_s": percentile(latencies, 0.95),
        "throughput_tok_s": throughput_tok_s,
    }


def source_document_id(segment_id: str) -> str:
    """Keep multilingual copies together; unknown ID formats stay independent."""
    match = re.fullmatch(r"(flores-\d+|synthetic-[a-z]{2}\d+)-[a-z]{2}-[a-z]{2}", segment_id)
    return match.group(1) if match else segment_id


def paired_cluster_ci95(clusters: dict[str, list[float]]) -> list[float] | None:
    """Resample source documents, retaining every paired segment in each draw.

    The point estimate and bootstrap means are segment weighted, including
    when missing pairs give clusters different sizes. Sorting source IDs
    makes the seeded CI invariant to JSONL/model input order.
    """
    if len(clusters) < 2:
        return None
    summaries = [(sum(clusters[key]), len(clusters[key])) for key in sorted(clusters)]
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(summaries)
    means = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        total, count = 0.0, 0
        for _ in range(n):
            cluster_total, cluster_count = summaries[rng.randrange(n)]
            total += cluster_total
            count += cluster_count
        means.append(total / count)
    means.sort()
    return [round(means[int(0.025 * BOOTSTRAP_RESAMPLES)], 3),
            round(means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1], 3)]


def baseline_comparison(rows: list[dict], baseline_rows: list[dict]) -> dict:
    """Compare last observations on common valid averaged-score keys.

    Raw two-judge eligibility is deliberately independent: historical valid
    averaged judgments can be paired even if their raw scores are unavailable.
    """
    candidates = {r["id"]: r for r in rows}
    baseline = {r["id"]: r for r in baseline_rows}
    deltas, clusters = [], {}
    for key in sorted(candidates.keys() & baseline.keys()):
        if not valid_judgment(candidates[key]) or not valid_judgment(baseline[key]):
            continue
        delta = candidates[key]["overall"] - baseline[key]["overall"]
        deltas.append(delta)
        clusters.setdefault(source_document_id(key), []).append(delta)
    n = len(deltas)
    return {
        "baseline_model": BASELINE_MODEL,
        "paired_segments": n,
        "paired_source_documents": len(clusters),
        "win_rate": sum(delta > 0 for delta in deltas) / n if n else None,
        "tie_rate": sum(delta == 0 for delta in deltas) / n if n else None,
        "loss_rate": sum(delta < 0 for delta in deltas) / n if n else None,
        "mean_delta": round(statistics.mean(deltas), 3) if n else None,
        "mean_delta_ci95": paired_cluster_ci95(clusters),
        "bootstrap_unit": "source_document",
    }


def track_of(doc_type: str) -> str:
    return "flores" if doc_type == "flores" else "synthetic"


def metric_policy() -> dict:
    """Machine-readable thresholds plus the populations behind each metric."""
    return {
        "quality_eligibility": (
            "Successful translation with a valid averaged judgment and complete raw axes/overall "
            "for two distinct actual judges, including fallback identities. Explicit judges_used "
            "is authoritative and malformed values are unavailable. Only when judges_used is absent, "
            "recover identities from exactly two raw-score prefix groups, both complete and valid; "
            "extra groups or incomplete evidence are unavailable. Never infer raw scores from averages."
        ),
        "quality_pass": {"minimum_axis_score": QUALITY_PASS_MIN, "rule": "every axis from both judges"},
        "high_risk": {
            "maximum_numbers_entities_dates_score": HIGH_RISK_MAX,
            "rule": "either actual judge; a judge risk flag, not a verified factual error",
        },
        "judge_disagreement": {
            "minimum_overall_gap": JUDGE_DISAGREEMENT_MIN,
            "difference_rounding_decimals": 3,
        },
        "rates": {
            "scale": "fraction_0_1",
            "unavailable": None,
            "quality_rates_denominator": "quality_eligible_segments",
            "judge_coverage_rate": "judged_segments / successful_translations",
            "quality_coverage_rate": "quality_eligible_segments / successful_translations",
            "coverage_scope": (
                "Retained successful translations, not the full configured dataset. "
                "Translation failures are excluded and reported separately."
            ),
        },
        "judge_overall_p10": {
            "population": "valid averaged judgments",
            "method": "linear interpolation at sorted index (n - 1) * 0.1",
        },
        "baseline": {
            "model": BASELINE_MODEL,
            "scopes": ["aggregate", "by_track"],
            "population": "common valid averaged-judgment segment IDs; raw-score eligibility not required",
            "rates_denominator": "paired_segments",
            "win_tie_loss": "candidate overall greater than / exactly equal to / less than baseline overall",
            "mean_delta": "segment-weighted mean of candidate overall minus baseline overall; positive favors candidate",
            "bootstrap": {
                "method": "paired source-cluster percentile bootstrap on the segment-weighted mean delta",
                "unit": "source_document",
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence_level": 0.95,
                "cluster_ids": (
                    "FLORES sentence ID across languages/directions; synthetic source-language parent ID "
                    "across targets; unrecognized segment IDs remain independent"
                ),
                "ci_unavailable": "fewer than two paired source documents",
            },
        },
        "estimated_translation_cost": {
            "scope": "latest successful translation rows only; not total billed experiment spend",
            "excluded": [
                "superseded retries and failed translation attempts", "benchmark judge spend",
                "GPU setup/idle time outside each observed source-run batch",
            ],
            "pricing_source": "supplied model configuration; retain historical rates for reused models",
            "multi_run_timing": (
                "Throughput is unavailable when a model retains rows from multiple source runs, "
                "including failed replacements: retained subsets do not prove full source-batch membership. "
                "All GPU-derived costs are then null; token/character-priced costs remain available."
            ),
            "request_deadline_timing": (
                "Mantle throughput is also unavailable when recorded invocations changed the "
                "client request deadline. Fully cached invocations made no requests and are ignored. "
                "Recorded deadline history is exposed in run_config; token-priced costs remain available."
            ),
            "cost_per_quality_pass_usd": (
                "whole-model cost_total_usd / quality_pass_segments; null if zero passes or any successful "
                "translation lacks a valid judgment or complete raw two-judge scores"
            ),
        },
        "provenance": {
            "precedence": "included runs in argument order, then primary; last (model, id) row wins, including errors",
            "judgment_join": (
                "A retained judgment must have the same source run as its retained translation. "
                "A cross-run judgment is not attached; the translation remains not_yet_judged."
            ),
            "reused": "observations retained from included runs, rather than executed in the primary run",
            "source_manifests": (
                "Recorded historical provenance; a manifest may describe only the last execution "
                "and need not list every model in its caches."
            ),
            "recorded_model_run_configs": "per-model execution/pricing snapshots from a source's published report, if available",
            "judge_cost_scope": "retained judgments across all source runs, including reused judgments; not incremental primary-run spend",
            "compatibility": "conflicting available dataset/prompt/rubric hashes reject combination; missing hashes remain unverified",
        },
    }


def source_compatibility(source_runs: list[dict]) -> dict:
    """Check the hashes that manifests actually record, without inventing any."""
    checks = {}
    for key in ("dataset_sha256", "prompt_sha256", "rubric_sha256"):
        available = [(source["run_id"], source["manifest"][key]) for source in source_runs
                     if source.get("manifest") and source["manifest"].get(key)]
        if available:
            first_run, first_hash = available[0]
            for other_run, other_hash in available[1:]:
                if other_hash != first_hash:
                    raise ValueError(f"incompatible {key} in source runs {first_run!r} and {other_run!r}")
        status = "unavailable"
        if available:
            status = "partial" if len(available) < len(source_runs) else (
                "matched" if len(available) > 1 else "recorded"
            )
        checks[key] = {"status": status, "recorded_run_ids": [run_id for run_id, _ in available]}
    return checks


def load_report_sources(run_id: str, include_run_ids: list[str] | None) -> tuple[list, list, list, dict]:
    source_ids = [*dict.fromkeys(source_id for source_id in (include_run_ids or []) if source_id != run_id), run_id]
    source_runs = []
    for source_id in source_ids:
        source_dir = RESULTS_DIR / source_id
        if not source_dir.is_dir():
            raise FileNotFoundError(f"report source run does not exist: {source_dir}")
        manifest_path = source_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
        # Old manifests can describe just the most recent model execution.
        # Preserve published per-model snapshots separately, without treating
        # an incomplete manifest roster as an incompatibility.
        source_report_path = DOCS_RESULTS_DIR / f"{source_id}.json"
        recorded_configs = {}
        if source_id != run_id and source_report_path.exists():
            source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
            recorded_configs = {m["name"]: m["run_config"] for m in source_report.get("models", []) if "run_config" in m}
        source_runs.append({
            "run_id": source_id, "reused": source_id != run_id, "manifest": manifest,
            "recorded_model_run_configs": recorded_configs,
        })
    checks = source_compatibility(source_runs)  # reject before loading large caches
    translations, judgments = [], []
    for source_id in source_ids:
        source_dir = RESULTS_DIR / source_id
        translations.extend({**row, "translation_source_run": source_id}
                            for row in load_jsonl(source_dir / "translations.jsonl"))
        judgments.extend({**row, "judgment_source_run": source_id}
                         for row in load_jsonl(source_dir / "judgments.jsonl"))
    translations = dedupe_latest(translations, lambda r: (r["model"], r["id"]))
    judgments = dedupe_latest(judgments, lambda r: (r["model"], r["id"]))
    translation_counts = Counter(r["translation_source_run"] for r in translations)
    judgment_counts = Counter(r["judgment_source_run"] for r in judgments)
    for source in source_runs:
        source["retained_translations"] = translation_counts[source["run_id"]]
        source["retained_judgments"] = judgment_counts[source["run_id"]]
    return translations, judgments, source_runs, checks


def run_config_of(model_cfg: dict, default_concurrency: int) -> dict:
    model_id = model_cfg.get("model_id")
    cfg = {
        "concurrency": model_cfg.get("concurrency", default_concurrency),
        "temperature_omitted": model_id in MANTLE_NO_TEMPERATURE or model_id in BEDROCK_NO_TEMPERATURE,
        "request_max_attempts": model_cfg.get("request_max_attempts", 1),
    }
    if model_cfg.get("api") == "bedrock_mantle":
        cfg["mantle_region"] = model_cfg.get("mantle_region", "us-east-1")
        cfg["request_timeout_s"] = REQUEST_TIMEOUT_S
        cfg["response_delivery"] = "background" if model_cfg.get("mantle_background") else "blocking"
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


def recorded_model_invocations(name: str, source_ids: set[str], source_runs: list[dict]):
    """Only executions with actual inference or retrieval requests."""
    for source in source_runs:
        if source["run_id"] not in source_ids:
            continue
        manifest = source.get("manifest") or {}
        for execution in manifest.get("executions") or [manifest]:
            summary = next((m for m in execution.get("completion_summary", {}).get("models", [])
                            if m.get("model") == name), None)
            if (summary is not None and summary.get("request_attempts") == 0
                    and not summary.get("retrieved_inferences")):
                continue
            model = next((m for m in execution.get("models", []) if m.get("name") == name), None)
            if model is not None:
                yield model


def request_timeout_history(name: str, source_ids: set[str], source_runs: list[dict]) -> list:
    return sorted({
        m["request_timeout_s"] for m in recorded_model_invocations(name, source_ids, source_runs)
        if type(m.get("request_timeout_s")) in (int, float)
        and 0 < m["request_timeout_s"] < float("inf")
    })


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
                "translation_source_run": r.get("translation_source_run"),
                "judgment_source_run": r.get("judgment_source_run"),
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


def build_report(run_id: str, scenario_cfg: dict, models_cfg: list[dict], dataset_paths: list[Path],
                 include_run_ids: list[str] | None = None) -> dict:
    run_dir = RESULTS_DIR / run_id
    translations, judgments, source_runs, compatibility = load_report_sources(run_id, include_run_ids)
    judgments_by_key = {(j["model"], j["id"]): j for j in judgments}

    segments = load_dataset(dataset_paths)
    src_chars_by_id = {s["id"]: len(s["src_text"]) for s in segments}
    doc_type_by_id = {s["id"]: s["doc_type"] for s in segments}

    joined = []
    for t in translations:
        j = judgments_by_key.get((t["model"], t["id"]), {})
        # A newer translation of the same segment cannot inherit a score of
        # another run's output. Preserve the original within-run cache contract.
        if j.get("judgment_source_run") != t["translation_source_run"]:
            j = {}
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
    baseline_rows = [r for r in joined if r["model"] == BASELINE_MODEL]

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
            by_track[track]["baseline_comparison"] = baseline_comparison(
                track_rows, [r for r in baseline_rows if track_of(r["doc_type"]) == track])

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
        aggregate = aggregate_full(rows, model_cfg, src_chars_by_id)
        aggregate["baseline_comparison"] = baseline_comparison(rows, baseline_rows)
        run_config = run_config_of(model_cfg, default_concurrency)
        if model_cfg["api"] == "bedrock_mantle":
            timeouts = request_timeout_history(
                name, {r["translation_source_run"] for r in rows}, source_runs)
            if timeouts:
                run_config["request_timeout_s"] = timeouts[0] if len(timeouts) == 1 else None
            if len(timeouts) > 1:
                run_config["request_timeouts_s"] = timeouts
                aggregate["throughput_tok_s"] = None
                aggregate["throughput_unavailable_reason"] = "request_deadline_changed"
            deliveries = sorted({
                "background" if m.get("mantle_background") else "blocking"
                for m in recorded_model_invocations(
                    name, {r["translation_source_run"] for r in rows}, source_runs)
            })
            if deliveries:
                run_config["response_delivery"] = deliveries[0] if len(deliveries) == 1 else "mixed"
            if len(deliveries) > 1:
                run_config["response_deliveries"] = deliveries
                aggregate["throughput_tok_s"] = None
                aggregate.setdefault("throughput_unavailable_reason", "response_delivery_changed")
        models_out.append({
            "name": name,
            "provider": provider,
            "run_config": run_config,
            "aggregate": aggregate,
            "observation_provenance": {
                "translations_by_run": dict(Counter(r["translation_source_run"] for r in rows)),
                "judgments_by_run": dict(Counter(r["judgment_source_run"] for r in rows if r.get("judge_attempted"))),
            },
            "by_pair": by_pair,
            "by_track": by_track,
            "by_lang_group": by_lang_group,
        })

    manifest = source_runs[-1]["manifest"]

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
        "source_runs": source_runs,
        "source_compatibility": compatibility,
        "metric_policy": metric_policy(),
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
    """Hand-computed quality, cost, pairing and source-provenance checks."""
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

    # Raw thresholds must not use averaged axes (which can hide a judge's
    # low score), and fallback scores must follow the recorded actual names.
    def scored_row(seg_id, first, second, names=("judge-a", "judge-b")):
        first_scores, second_scores = dict(zip(AXES, first)), dict(zip(AXES, second))
        averaged = {a: (first_scores[a] + second_scores[a]) / 2 for a in AXES}
        row = {
            "model": "candidate", "id": seg_id, "translation_error": None,
            "judge_error": None, "judge_attempted": True, "output_text": "translated",
            "tokens_in": 1_000_000, "tokens_out": 500_000, "latency_s": 10.0,
            "timestamp": "2026-01-01T00:00:10+00:00", "judges_used": list(names),
            "overall": round(sum(averaged.values()) / 5, 3), **averaged,
            "src_lang": "ko", "tgt_lang": "en", "doc_type": "flores",
        }
        for name, scores in zip(names, (first_scores, second_scores)):
            row.update({f"{name}_{axis}": score for axis, score in scores.items()})
            row[f"{name}_overall"] = round(sum(scores.values()) / 5, 3)
        return row

    passed = scored_row("flores-1-ko-en", [4] * 5, [4] * 5)
    below_pass = scored_row("flores-2-ko-en", [3.999, 4, 4, 4, 4], [4] * 5)
    risk = scored_row("flores-3-ko-en", [5, 5, 2, 5, 5], [5] * 5)
    disagreement = scored_row("flores-4-ko-en", [3] * 5, [4] * 5)
    below_disagreement = scored_row("flores-5-ko-en", [3.001] * 5, [4] * 5)
    legacy = {k: v for k, v in passed.items()
              if not k.startswith("judge-a_") and not k.startswith("judge-b_") and k != "judges_used"}
    raw_rows = [passed, below_pass, risk, disagreement, below_disagreement]
    coverage = aggregate_quality([*raw_rows, legacy, *rows[1:]])
    assert coverage.get("quality_eligible_segments") == 5, coverage
    assert coverage["quality_pass_segments"] == 1 and coverage["quality_pass_rate"] == 0.2, coverage
    assert coverage["high_risk_segments"] == 1 and coverage["high_risk_rate"] == 0.2, coverage
    assert coverage["judge_disagreement_segments"] == 1 and coverage["judge_disagreement_rate"] == 0.2, coverage
    assert coverage["segments"] == 9 and coverage["successful_translations"] == 8, coverage
    assert coverage["judged_segments"] == 6 and coverage["judge_coverage_rate"] == 0.75, coverage
    assert coverage["quality_coverage_rate"] == 0.625, coverage  # 5 eligible / 8 successful translations
    assert coverage["judge_failures"] == 1 and coverage["not_yet_judged"] == 1, coverage
    assert coverage["translation_failures"] == 1, coverage

    fallback = scored_row("flores-6-ko-en", [4] * 5, [5] * 5,
                          names=("judge-a", "judge-b-fallback"))
    # Stale primary fields must not override the fallback that actually scored.
    fallback.update({f"judge-b_{a}": 1 for a in [*AXES, "overall"]})
    fq = aggregate_quality([fallback])
    assert fq["quality_eligible_segments"] == 1 and fq["quality_pass_rate"] == 1, fq
    assert fq["high_risk_rate"] == 0 and fq["judge_disagreement_rate"] == 1, fq
    decimal_boundary = scored_row("flores-8-ko-en", [5, 5, 3, 5, 5], [4, 4, 2, 4, 4])
    assert decimal_boundary["judge-a_overall"] == 4.6 and decimal_boundary["judge-b_overall"] == 3.6
    assert aggregate_quality([decimal_boundary])["judge_disagreement_rate"] == 1
    above_risk = scored_row("flores-7-ko-en", [5, 5, 2.001, 5, 5], [5] * 5)
    assert aggregate_quality([above_risk])["high_risk_rate"] == 0
    second_judge_risk = scored_row("flores-9-ko-en", [5] * 5, [5, 5, 2, 5, 5])
    assert aggregate_quality([second_judge_risk])["high_risk_rate"] == 1
    second_judge_below_pass = scored_row("flores-10-ko-en", [4] * 5, [4, 4, 4, 4, 3.999])
    assert aggregate_quality([second_judge_below_pass])["quality_pass_rate"] == 0

    # Historical sol/fable rows predate judges_used, but their raw prefixes
    # still identify both judges. Recover names, never substitute mean scores.
    legacy_raw = scored_row("flores-11-ko-en", [4] * 5, [5] * 5, names=("sol", "fable-5"))
    legacy_raw.pop("judges_used")
    legacy_quality = aggregate_quality([legacy_raw])
    assert legacy_quality["quality_eligible_segments"] == 1, legacy_quality
    assert legacy_quality["quality_coverage_rate"] == 1 and legacy_quality["quality_pass_rate"] == 1
    assert legacy_quality["high_risk_rate"] == 0 and legacy_quality["judge_disagreement_rate"] == 1
    assert "judges_used" not in legacy_raw  # report aggregation never modifies source observations
    assert aggregate_full([legacy_raw], api_model, {})["cost_per_quality_pass_usd"] == 3.5
    legacy_raw_risk = scored_row("synthetic-ko0-ko-en", [5] * 5, [5, 5, 2, 5, 5],
                                names=("sol", "fable-5"))
    legacy_raw_risk.pop("judges_used")
    legacy_risk_quality = aggregate_quality([legacy_raw_risk])
    assert legacy_risk_quality["quality_pass_rate"] == 0 and legacy_risk_quality["high_risk_rate"] == 1
    legacy_fallback = scored_row("flores-12-ko-en", [4] * 5, [5] * 5,
                                names=("sol", "fable-5-fallback"))
    legacy_fallback.pop("judges_used")
    assert aggregate_quality([legacy_fallback])["quality_pass_rate"] == 1
    ambiguous_raw = {**legacy_fallback, **{f"fable-5_{a}": 1 for a in [*AXES, "overall"]}}
    assert aggregate_quality([ambiguous_raw])["quality_eligible_segments"] == 0
    explicit_fallback = {**ambiguous_raw, "judges_used": ["sol", "fable-5-fallback"]}
    assert aggregate_quality([explicit_fallback])["quality_pass_rate"] == 1
    assert aggregate_quality([explicit_fallback])["high_risk_rate"] == 0
    for incomplete_legacy in (
        {k: v for k, v in legacy_raw.items() if k != "fable-5_overall"},
        {k: v for k, v in legacy_raw.items() if k != "fable-5_format"},
        {k: v for k, v in legacy_raw.items() if not k.startswith("fable-5_")},
        {**legacy_raw, "fable-5_overall": None},
        {**legacy_raw, "fable-5_format": float("nan")},
        {**legacy_raw, "fable-5_format": 6},
        {**legacy_raw, "fable-5_format": True},
        {**legacy_raw, "third-judge_overall": 4},  # a third partial group is ambiguous too
        legacy,  # averages alone still provide no raw evidence
    ):
        iq = aggregate_quality([incomplete_legacy])
        assert iq["quality_eligible_segments"] == 0 and iq["quality_pass_rate"] is None, iq
    for malformed_names in (None, [], "sol", ["sol"], ["sol", "sol"], ["sol", None],
                            ["sol", "fable-5", "fable-5-fallback"]):
        iq = aggregate_quality([{**legacy_raw, "judges_used": malformed_names}])
        assert iq["quality_eligible_segments"] == 0, iq

    # One judge, duplicate identities, malformed identities/raw axis/raw overall,
    # malformed scores and failed/pending judgments never become eligible.
    for incomplete in (
        {**passed, "judges_used": ["judge-a"]},
        {**passed, "judges_used": ["judge-a", "judge-a"]},
        {**passed, "judges_used": None},
        {**passed, "judge-b_format": None},
        {**passed, "judge-b_overall": None},
        {**passed, "judge-b_format": float("nan")},
        {**passed, "judge-b_format": 6},
        {**passed, "judge-b_format": True},
        {**passed, "judge_error": "timeout"},
        {**passed, "judge_attempted": False},
        {**passed, "translation_error": "failed"},
    ):
        iq = aggregate_quality([incomplete])
        assert iq["quality_eligible_segments"] == 0 and iq["quality_pass_rate"] is None, iq
        assert iq["high_risk_rate"] is None and iq["judge_disagreement_rate"] is None, iq

    no_rows = aggregate_quality([])
    assert no_rows["judge_coverage_rate"] is None and no_rows["quality_coverage_rate"] is None
    assert no_rows["judge_overall_p10"] is None
    p10_rows = [scored_row(f"flores-{n}-ko-en", [n] * 5, [n] * 5) for n in range(1, 6)]
    assert aggregate_quality(p10_rows)["judge_overall_p10"] == 1.4  # linear interpolation at index 0.4
    assert aggregate_quality([passed])["judge_overall_p10"] == 4
    assert aggregate_quality([legacy])["quality_coverage_rate"] == 0
    assert aggregate_quality([legacy])["judge_coverage_rate"] == 1
    assert "cost_per_quality_pass_usd" not in coverage  # quality subsets never carry cost

    # Two successful translations cost $7 at $1/$5 per Mtok, with one pass:
    # divide all successful translation spend by passes, not spend on passes.
    complete_cost = aggregate_full([passed, risk], api_model, {})
    assert complete_cost["cost_total_usd"] == 7 and complete_cost["cost_per_quality_pass_usd"] == 7, complete_cost
    assert aggregate_full([passed, risk, rows[2]], api_model, {})["cost_per_quality_pass_usd"] == 7
    assert aggregate_full([risk], api_model, {})["cost_per_quality_pass_usd"] is None
    assert aggregate_full([], api_model, {})["cost_per_quality_pass_usd"] is None
    for missing in (legacy, rows[1], rows[3], {**passed, "judge-b_format": None}):
        incomplete_cost = aggregate_full([passed, missing], api_model, {})
        assert incomplete_cost["cost_per_quality_pass_usd"] is None, incomplete_cost
    assert aggregate_full([passed, risk], translate_model, {})["cost_per_quality_pass_usd"] == 30
    # Concurrent requests span 10 seconds at $1/sec: no per-subset timing.
    assert aggregate_full([passed, risk], vllm_model, {})["cost_per_quality_pass_usd"] == 10

    # Paired comparison uses common valid keys, never independent model means
    # or raw-score eligibility. Exact score equality is a tie.
    paired_candidate = [
        scored_row("flores-1-ko-en", [5] * 5, [5] * 5),
        scored_row("flores-1-ko-ja", [5] * 5, [5] * 5),
        scored_row("flores-2-ko-en", [3] * 5, [3] * 5),
        scored_row("synthetic-ko0-ko-en", [4] * 5, [4] * 5),
        scored_row("flores-99-ko-en", [1] * 5, [1] * 5),  # candidate-only
        {**passed, "id": "flores-98-ko-en", "judge_error": "timeout"},
        {**passed, "id": "flores-97-ko-en", "translation_error": "failed"},
        {**passed, "id": "flores-96-ko-en", "judge_attempted": False},
        {**passed, "id": "flores-95-ko-en", "overall": float("nan")},
        {**passed, "id": "flores-94-ko-en"},  # baseline judgment fails
    ]
    paired_baseline = [{**legacy, "model": "amazon-translate", "id": r["id"]} for r in paired_candidate
                       if r["id"] != "flores-99-ko-en"]
    paired_baseline += [{**legacy, "model": "amazon-translate", "id": "flores-100-ko-en"}]
    paired_baseline[-2]["judge_error"] = "baseline timeout"
    paired = baseline_comparison(paired_candidate, paired_baseline)
    assert paired["baseline_model"] == "amazon-translate" and paired["paired_segments"] == 4, paired
    assert paired["win_rate"] == 0.5 and paired["tie_rate"] == 0.25 and paired["loss_rate"] == 0.25, paired
    assert paired["mean_delta"] == 0.25 and paired["paired_source_documents"] == 3, paired
    assert paired["bootstrap_unit"] == "source_document", paired
    assert paired == baseline_comparison(list(reversed(paired_candidate)), list(reversed(paired_baseline)))
    absent_baseline = baseline_comparison(paired_candidate, [])
    assert absent_baseline["paired_segments"] == 0 and absent_baseline["paired_source_documents"] == 0
    assert all(absent_baseline[k] is None for k in ("win_rate", "tie_rate", "loss_rate", "mean_delta", "mean_delta_ci95"))

    # Three multilingual copies of +1 share one source, the lone -1 another.
    # Resampling two source clusters gives -1, +0.5 or +1: CI [-1, 1].
    # Resampling four segments independently would give [-0.5, 1].
    cluster_candidate = [
        scored_row("flores-1-ko-en", [5] * 5, [5] * 5),
        scored_row("flores-1-ko-ja", [5] * 5, [5] * 5),
        scored_row("flores-1-en-ko", [5] * 5, [5] * 5),
        scored_row("flores-2-ko-en", [3] * 5, [3] * 5),
    ]
    cluster_baseline = [{**legacy, "id": r["id"]} for r in cluster_candidate]
    clustered = baseline_comparison(cluster_candidate, cluster_baseline)
    assert clustered["mean_delta"] == 0.5 and clustered["mean_delta_ci95"] == [-1, 1], clustered
    assert clustered["paired_source_documents"] == 2
    single_source = baseline_comparison(cluster_candidate[:3], cluster_baseline)
    assert single_source["paired_segments"] == 3 and single_source["paired_source_documents"] == 1
    assert single_source["mean_delta"] == 1 and single_source["mean_delta_ci95"] is None
    same_model = baseline_comparison(cluster_baseline, cluster_baseline)
    assert same_model["tie_rate"] == 1 and same_model["mean_delta_ci95"] == [0, 0]
    superseded = baseline_comparison([passed, {**passed, "judge_error": "latest failed"}], [legacy])
    assert superseded["paired_segments"] == 0  # never resurrect an earlier valid duplicate
    assert source_document_id("flores-123-ko-en") == source_document_id("flores-123-ja-ko") == "flores-123"
    assert source_document_id("synthetic-ko12-ko-en") == source_document_id("synthetic-ko12-ko-ja") == "synthetic-ko12"
    assert source_document_id("synthetic-en12-en-ko") == "synthetic-en12"
    assert source_document_id("synthetic-en12-en-ko") != source_document_id("synthetic-ko12-ko-en")
    assert source_document_id("unknown-parent-ko-en") == "unknown-parent-ko-en"

    # Exercise the actual filesystem join using tiny temporary INPUT fixtures;
    # never write a dashboard report or touch benchmark caches in this check.
    # Included observations load first, primary wins, and the latest failed
    # attempt must not silently fall back to an earlier successful judgment.
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        fixture_root = Path(temp_dir)
        source_ids = [str(fixture_root / "included"), str(fixture_root / "primary")]
        primary_id = source_ids[1]
        for source_id in source_ids:
            Path(source_id).mkdir()
        fixture_segments = [
            {"id": "flores-1-ko-en", "src_lang": "ko", "tgt_lang": "en",
             "src_text": "one", "doc_type": "flores"},
            {"id": "synthetic-ko0-ko-en", "src_lang": "ko", "tgt_lang": "en",
             "src_text": "two", "doc_type": "financial"},
        ]
        dataset_path = fixture_root / "dataset.jsonl"
        dataset_path.write_text("\n".join(json.dumps(s) for s in fixture_segments), encoding="utf-8")
        fixture_models = [
            {"name": "candidate", **api_model},
            {"name": "amazon-translate", **translate_model},
        ]
        fixture_scenario = {"concurrency_default": 8, "flores_per_pair": 1,
                            "synthetic_per_pair": 1, "judges": []}
        old_rows = [{**passed, "model": model, "id": seg["id"]}
                    for model in ("candidate", "amazon-translate") for seg in fixture_segments]
        new_row = scored_row("flores-1-ko-en", [5] * 5, [5] * 5)

        def write_inputs(source_id, input_rows, manifest):
            # Translation/judgment caches really are separate, both with their
            # own `error`; don't let a pre-joined fixture conceal join bugs.
            translation_keys = ("model", "id", "src_lang", "tgt_lang", "output_text",
                                "tokens_in", "tokens_out", "latency_s", "timestamp")
            translation_lines, judgment_lines = [], []
            for row in input_rows:
                translation_lines.append(json.dumps(
                    {**{key: row[key] for key in translation_keys}, "error": row.get("translation_error")}))
                judgment = {key: value for key, value in row.items()
                            if key in ("model", "id", "judges_used", "overall", *AXES)
                            or key.startswith(("judge-a_", "judge-b_"))}
                judgment_lines.append(json.dumps({**judgment, "error": row.get("judge_error")}))
            (Path(source_id) / "translations.jsonl").write_text("\n".join(translation_lines), encoding="utf-8")
            (Path(source_id) / "judgments.jsonl").write_text("\n".join(judgment_lines), encoding="utf-8")
            (Path(source_id) / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        old_manifest = {"run_id": source_ids[0], "prompt_sha256": "abc", "rubric_sha256": "def",
                        "models": [{"name": "amazon-translate"}]}  # partial historical roster is valid
        primary_manifest = {"run_id": primary_id, "prompt_sha256": "abc", "rubric_sha256": "def"}
        write_inputs(source_ids[0], old_rows, old_manifest)
        write_inputs(primary_id, [new_row, {**new_row, "judge_error": "timeout"}], primary_manifest)
        included_report = build_report(primary_id, fixture_scenario, fixture_models, [dataset_path],
                                       include_run_ids=[source_ids[0], source_ids[0]])
        assert included_report["run_id"] == primary_id and included_report["manifest"] == primary_manifest
        assert [s["run_id"] for s in included_report["source_runs"]] == source_ids
        assert [s["reused"] for s in included_report["source_runs"]] == [True, False]
        assert [s["retained_translations"] for s in included_report["source_runs"]] == [3, 1]
        assert [s["retained_judgments"] for s in included_report["source_runs"]] == [3, 1]
        included_model = next(m for m in included_report["models"] if m["name"] == "candidate")
        full = included_model["aggregate"]
        assert full["segments"] == 2 and full["successful_translations"] == 2
        assert full["judged_segments"] == 1 and full["judge_failures"] == 1
        assert full["cost_total_usd"] == 7 and full["cost_per_quality_pass_usd"] is None
        assert full["baseline_comparison"]["paired_segments"] == 1
        assert included_model["by_track"]["flores"]["baseline_comparison"]["paired_segments"] == 0
        assert included_model["by_track"]["synthetic"]["baseline_comparison"]["tie_rate"] == 1
        assert included_model["observation_provenance"]["translations_by_run"] == dict(zip(source_ids, [1, 1]))
        assert included_model["observation_provenance"]["judgments_by_run"] == dict(zip(source_ids, [1, 1]))
        for subset in [*included_model["by_pair"].values(), *included_model["by_lang_group"].values()]:
            assert "baseline_comparison" not in subset and "cost_per_quality_pass_usd" not in subset
        for subset in included_model["by_track"].values():
            assert "cost_per_quality_pass_usd" not in subset
        assert included_report["source_compatibility"]["prompt_sha256"]["status"] == "matched"
        assert included_report["source_compatibility"]["dataset_sha256"]["status"] == "unavailable"
        assert included_report["metric_policy"]["rates"]["scale"] == "fraction_0_1"
        sample = next(s for s in included_report["samples"] if s["id"] == new_row["id"])
        assert sample["by_model"]["candidate"]["translation_source_run"] == primary_id
        assert sample["by_model"]["amazon-translate"]["judgment_source_run"] == source_ids[0]

        # Last successful retry wins; primary-only mode retains its old meaning.
        write_inputs(primary_id, [new_row], primary_manifest)
        retry_report = build_report(primary_id, fixture_scenario, fixture_models, [dataset_path], [source_ids[0]])
        retry_model = next(m for m in retry_report["models"] if m["name"] == "candidate")
        assert retry_model["aggregate"]["baseline_comparison"]["win_rate"] == 0.5
        assert retry_model["aggregate"]["cost_per_quality_pass_usd"] == 3.5
        assert retry_model["aggregate"]["throughput_tok_s"] is None
        primary_only = build_report(primary_id, fixture_scenario, fixture_models, [dataset_path])
        assert len(primary_only["models"]) == len(primary_only["source_runs"]) == 1
        assert primary_only["models"][0]["aggregate"]["baseline_comparison"]["paired_segments"] == 0

        # A newly translated output cannot inherit a judgment of the old output
        # just because (model, id) matches. It remains pending, without raw scores.
        changed_row = {**new_row, "output_text": "a newly translated output"}
        write_inputs(primary_id, [changed_row], primary_manifest)
        (Path(primary_id) / "judgments.jsonl").unlink()
        pending_report = build_report(primary_id, fixture_scenario, fixture_models, [dataset_path], [source_ids[0]])
        pending_model = next(m for m in pending_report["models"] if m["name"] == "candidate")
        pending_quality = pending_model["aggregate"]
        assert pending_quality["successful_translations"] == 2 and pending_quality["judged_segments"] == 1, pending_quality
        assert pending_quality["not_yet_judged"] == 1 and pending_quality["judge_failures"] == 0, pending_quality
        assert pending_quality["quality_eligible_segments"] == 1
        assert pending_quality["cost_total_usd"] == 7 and pending_quality["cost_per_quality_pass_usd"] is None
        assert pending_model["by_track"]["flores"]["baseline_comparison"]["paired_segments"] == 0
        pending_sample = next(s for s in pending_report["samples"] if s["id"] == changed_row["id"])
        pending_output = pending_sample["by_model"]["candidate"]
        assert pending_output["output_text"] == "a newly translated output"
        assert pending_output["judgment_source_run"] is None and pending_output["overall"] is None
        assert pending_model["observation_provenance"]["judgments_by_run"] == {source_ids[0]: 1}

        # Real include-run partial overrides must not price a retained middle
        # segment as an isolated GPU batch. Old A ran at49–50s while overridden
        # old B occupied0–100s; new B runs for1s in a different execution.
        gpu_models = [
            {"name": "candidate", **vllm_model, "base_url": "http://localhost:8000/v1"},
            {"name": "amazon-translate", **translate_model},
        ]
        old_gpu_rows = [
            {**passed, "id": fixture_segments[0]["id"], "latency_s": 1,
             "timestamp": "2026-01-01T00:00:50+00:00"},
            {**passed, "id": fixture_segments[1]["id"], "latency_s": 100,
             "timestamp": "2026-01-01T00:01:40+00:00"},
        ]
        assert aggregate_full(old_gpu_rows, vllm_model, {})["cost_total_usd"] == 100
        replacement = {**passed, "id": fixture_segments[1]["id"], "latency_s": 1,
                       "timestamp": "2026-01-02T00:00:01+00:00"}
        baseline_fixture = [r for r in old_rows if r["model"] == "amazon-translate"]
        write_inputs(source_ids[0], old_gpu_rows + baseline_fixture, old_manifest)
        for replacement_error in (None, "timeout"):
            write_inputs(primary_id, [{**replacement, "translation_error": replacement_error}], primary_manifest)
            mixed_report = build_report(primary_id, fixture_scenario, gpu_models, [dataset_path], [source_ids[0]])
            mixed_gpu = next(m["aggregate"] for m in mixed_report["models"] if m["name"] == "candidate")
            assert mixed_gpu["throughput_tok_s"] is None, mixed_gpu
            assert all(mixed_gpu[field] is None for field in (
                "cost_total_usd", "cost_per_segment_usd", "cost_per_1k_src_chars_usd",
                "cost_per_quality_pass_usd", "usd_per_mtok_out")), mixed_gpu
            assert mixed_gpu["translation_failures"] == int(replacement_error is not None)
            assert mixed_gpu["quality_pass_segments"] == (1 if replacement_error else 2)
            # A different model retained entirely from the included run keeps
            # its full-model cost/throughput (the actual Grok reuse pattern).
            only_old = next(m["aggregate"] for m in mixed_report["models"] if m["name"] == "amazon-translate")
            assert only_old["cost_total_usd"] == 30 and only_old["throughput_tok_s"] is not None

        for hash_key in ("prompt_sha256", "rubric_sha256", "dataset_sha256"):
            write_inputs(source_ids[0], old_rows, {**old_manifest, hash_key: "first-hash"})
            write_inputs(primary_id, [new_row], {**primary_manifest, hash_key: "different-hash"})
            try:
                build_report(primary_id, fixture_scenario, fixture_models, [dataset_path], [source_ids[0]])
            except ValueError as exc:
                assert hash_key in str(exc) and source_ids[0] in str(exc) and primary_id in str(exc), exc
            else:
                raise AssertionError(f"conflicting {hash_key} must prevent combining runs")

        # A client-deadline change within one run invalidates throughput, not
        # token-priced cost. Two500K-output rows over5s otherwise give200Ktok/s.
        deadline_rows = [{**passed, "id": s["id"], "latency_s": 5}
                         for s in fixture_segments]
        deadline_models = [{"name": "candidate", **api_model, "api": "bedrock_mantle"}]
        early = {"models": [{"name": "candidate", "request_timeout_s": 120}],
                 "completion_summary": {"models": [{"model": "candidate", "request_attempts": 2}]}}
        late = {"models": [{"name": "candidate", "request_timeout_s": 600}],
                "completion_summary": {"models": [{"model": "candidate", "request_attempts": 1}]}}
        deadline_manifest = {**primary_manifest, "executions": [early, late]}
        write_inputs(primary_id, deadline_rows, deadline_manifest)
        deadline_report = build_report(primary_id, fixture_scenario, deadline_models, [dataset_path])
        deadline_model = deadline_report["models"][0]
        assert deadline_model["aggregate"]["throughput_tok_s"] is None
        assert deadline_model["aggregate"]["cost_total_usd"] == 7
        assert deadline_model["aggregate"]["cost_per_quality_pass_usd"] == 3.5
        assert deadline_model["run_config"]["request_timeout_s"] is None
        assert deadline_model["run_config"]["request_timeouts_s"] == [120, 600]

        # A model fully cached during the second invocation was never called
        # with its new deadline: retain its actual120s metadata and throughput.
        late["completion_summary"]["models"][0]["request_attempts"] = 0
        write_inputs(primary_id, deadline_rows, deadline_manifest)
        cached_report = build_report(primary_id, fixture_scenario, deadline_models, [dataset_path])
        cached_model = cached_report["models"][0]
        assert cached_model["aggregate"]["throughput_tok_s"] == 200000
        assert cached_model["run_config"]["request_timeout_s"] == 120

        # Background delivery also invalidates direct throughput comparisons
        # even if both invocations used the same network deadline.
        late["completion_summary"]["models"][0]["request_attempts"] = 1
        late["models"][0].update(request_timeout_s=120, mantle_background=True)
        write_inputs(primary_id, deadline_rows, deadline_manifest)
        delivery_report = build_report(primary_id, fixture_scenario, deadline_models, [dataset_path])
        delivery_model = delivery_report["models"][0]
        assert delivery_model["aggregate"]["throughput_tok_s"] is None
        assert delivery_model["aggregate"]["cost_total_usd"] == 7
        assert delivery_model["aggregate"]["cost_per_quality_pass_usd"] == 3.5
        assert delivery_model["run_config"]["response_delivery"] == "mixed"

    # Retained cross-run rows cannot prove full original batch membership.
    # Time-based metrics are unavailable; token/character costs remain additive.
    separate_batches = [
        {**passed, "translation_source_run": "old"},
        {**passed, "id": "flores-2-ko-en", "translation_source_run": "new",
         "timestamp": "2026-01-03T00:00:10+00:00"},
    ]
    batch_cost = aggregate_full(separate_batches, vllm_model, {})
    assert batch_cost["throughput_tok_s"] is None and batch_cost["cost_total_usd"] is None, batch_cost
    assert batch_cost["cost_per_quality_pass_usd"] is None
    mixed_api = aggregate_full(separate_batches, api_model, {})
    assert mixed_api["throughput_tok_s"] is None
    assert mixed_api["cost_total_usd"] == 7 and mixed_api["cost_per_quality_pass_usd"] == 3.5, mixed_api
    mixed_chars = aggregate_full(separate_batches, translate_model, {})
    assert mixed_chars["cost_total_usd"] == 30 and mixed_chars["cost_per_quality_pass_usd"] == 15

    # UI decoding provenance must survive when a source manifest only records
    # the last model executed. Region comes from config, omission from runner rules.
    grok_config = run_config_of({
        "api": "bedrock_mantle", "model_id": "xai.grok-4.6", "mantle_region": "us-west-2",
        "mantle_reasoning_effort": "low", "price_in": 2.2, "price_out": 6.6,
        "request_max_attempts": 4,
    }, 8)
    assert grok_config.get("mantle_region") == "us-west-2", grok_config
    assert grok_config["temperature_omitted"] is False and grok_config["mantle_reasoning_effort"] == "low"
    assert grok_config.get("request_max_attempts") == 4
    assert grok_config.get("request_timeout_s") == 600
    sol_config = run_config_of({"api": "bedrock_mantle", "model_id": "openai.gpt-5.6-sol"}, 8)
    assert sol_config["temperature_omitted"] is True
    assert sol_config["mantle_region"] == "us-east-1"  # runner default when not configured
    sonnet_config = run_config_of({"api": "bedrock", "model_id": "us.anthropic.claude-sonnet-5"}, 8)
    assert sonnet_config["temperature_omitted"] is True
    assert run_config_of(api_model, 8)["temperature_omitted"] is False
    assert run_config_of(api_model, 8)["request_max_attempts"] == 1
    assert "request_timeout_s" not in run_config_of(api_model, 8)

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
    p.add_argument("--include-run", action="append", default=[], metavar="RUN_ID",
                   help="reuse this run before primary observations (repeatable; primary wins duplicate keys)")
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
    report = build_report(args.run_id, cfg["scenario"]["translation"], cfg["models"], dataset_paths,
                          include_run_ids=args.include_run)
    out_path = write_report(report)
    print(f"wrote {out_path}")
    print(f"models in report: {[m['name'] for m in report['models']]}")


if __name__ == "__main__":
    main()
