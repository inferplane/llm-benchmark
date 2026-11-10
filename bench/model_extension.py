"""Add newly released models to every published benchmark surface.

Generic successor of the one-off ``bench/*_benchmark.py`` extension modules
(Kimi K3, GPT-6 Luna, Claude Haiku 5.5, GPT-6.1 Terra). One *extension tag*
(``YYYYMMDD`` plus an optional letter) freezes a contract that binds the new
models' config entries, every dataset/prompt/rubric/judge set and the
collection code before any paid call. Each surface then composes the new
measurements onto the latest published report without touching historical
models, samples or evaluations:

* Korean translation, explicit cohort: 3,300 segments, sol + fable-5 judges
  -> ``docs/results/integrated-YYYY-MM-DD.json``
* English pivot: 3,080 segments, graded once per judge set
  (sol + fable-5, and astra + fable-5.1 which stays the dashboard default)
  -> ``docs/results/en-pivot-<tag>.json`` and ``-judge2``
* Audited financial QA (20 questions) -> ``docs/finqa-results/finqa-ext-<tag>``
* TAT-QA 200 -> ``docs/tatqa-results/tatqa-api-200-<tag>.json``

Used both by hand and by ``.github/workflows/model-benchmark.yml`` (started
by the daily Bedrock What's New watcher). Collection policy, identical to the
earlier extensions: one candidate attempt per scheduled input (configured
transport retries allowed); an interrupted collection resumes only inputs
with no recorded attempt; failures and capped outputs stay failures; only
returned translations are graded; candidates are never regenerated for
grading. Judge calls may be retried. Cost figures are measured-usage
estimates, not invoices.

    uv run python3 -m bench.model_extension estimate --models claude-fable-5.2 --tag 20261110
    uv run python3 -m bench.model_extension all --models claude-fable-5.2 --tag 20261110 --max-usd 400
"""
import argparse
import asyncio
import copy
import hashlib
import html
import json
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bench import finqa, finqa_audited as qa, finqa_compare, judge, report, run, tatqa

ROOT = finqa.ROOT
VALIDATION = ROOT / "validation/extensions"
KO_SOURCE = ROOT / "results/grok-explicit-2026-09-16/dataset.jsonl"
EN_SOURCES = [ROOT / "data" / f for f in (
    "flores-en.jsonl", "synthetic-en.jsonl", "flores-to-en.jsonl", "synthetic-to-en.jsonl")]
RUBRIC = ROOT / "scenarios/translation/rubric.txt"
KO_SEGMENTS, EN_SEGMENTS, QA_QUESTIONS, TATQA_QUESTIONS = 3300, 3080, 20, 200
ALT_JUDGE_SET = "astra-fable51"
TAG = re.compile(r"\d{8}[a-z]?")
STAGES = ("ko", "en", "qa", "tatqa")
POLICY = (
    "One candidate attempt per scheduled input with configured transport retries; an interrupted "
    "collection resumes only inputs without any recorded attempt. No candidate regeneration, "
    "reasoning change or cap increase after seeing outcomes. Empty/capped/failed responses remain "
    "failures. Returned translations are graded once per judge set with the unchanged rubric; the "
    "English responses are generated once and reused by both judge sets. Quality is conditional on "
    "gradable returned text. Costs are measured-usage estimates for successful calls (fresh input, "
    "output, cache read and cache write priced separately), not the experiment invoice. All prior "
    "model snapshots are preserved; prompt cohort and measurement dates are reported."
)


# ── small helpers ────────────────────────────────────────────────────────────
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def now():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


def effort_of(model):
    return model.get("bedrock_reasoning_effort") or model.get("mantle_reasoning_effort")


class Extension:
    """All paths and run ids derived from (tag, models)."""

    def __init__(self, tag, names):
        if not TAG.fullmatch(tag):
            raise SystemExit(f"tag must look like 20261110 or 20261110b, got {tag!r}")
        if not names:
            raise SystemExit("--models is required")
        self.tag, self.names = tag, sorted(set(names))
        date = f"{tag[:4]}-{tag[4:6]}-{tag[6:8]}{tag[8:]}"
        self.folder = VALIDATION / tag
        self.contract = self.folder / "contract.json"
        self.ko_run, self.en_run = f"bedrock-ext-{tag}", f"en-pivot-ext-{tag}"
        self.en_run2 = self.en_run + "-judge2"
        self.qa_run, self.tatqa_run = f"finqa-ext-{tag}", f"tatqa-ext-{tag}"
        self.ko_comparison = f"integrated-{date}"
        self.en_comparison, self.en_comparison2 = f"en-pivot-{tag}", f"en-pivot-{tag}-judge2"
        self.tatqa_comparison = f"tatqa-api-200-{tag}"
        self.ko_dir, self.en_dir = run.RESULTS_DIR / self.ko_run, run.RESULTS_DIR / self.en_run
        self.en_dir2 = run.RESULTS_DIR / self.en_run2
        self.qa_dir, self.tatqa_dir = finqa.RESULTS / self.qa_run, tatqa.RESULTS / self.tatqa_run

    def models(self, cfg=None):
        cfg = cfg or run.load_config()
        by_name = {m["name"]: m for m in cfg["models"]}
        missing = [n for n in self.names if n not in by_name]
        if missing:
            raise SystemExit(f"not in config.toml: {missing}")
        models = [by_name[n] for n in self.names]
        for m in models:
            if not m.get("enabled", True):
                raise SystemExit(f"{m['name']} is enabled = false in config.toml")
            if m["api"] not in ("bedrock", "bedrock_mantle") or m.get("base_url"):
                raise SystemExit(f"{m['name']}: only managed Bedrock/Mantle APIs are supported")
            if not all(isinstance(m.get(k), (int, float)) for k in ("price_in", "price_out")):
                raise SystemExit(f"{m['name']}: price_in/price_out required")
        return models


# ── base discovery ───────────────────────────────────────────────────────────
# Bases are recorded at freeze for provenance but resolved again at report
# time (after the CI branch merges main), so an extension that was merged in
# the meantime is not silently dropped from the "latest" comparison. Only the
# collection inputs (datasets, prompts, judges, collection code) are binding.
def bases(ext=None):
    own = {ext.ko_comparison, ext.en_comparison, ext.en_comparison2, ext.qa_run, ext.tatqa_comparison} if ext else set()
    ko = [p for p in sorted(report.DOCS_RESULTS_DIR.glob("integrated-*.json"), key=lambda p: p.stem) if p.stem not in own]
    pattern = re.compile(r"en-pivot-(\d{8}[a-z]?)")
    tags = sorted({m.group(1) for p in report.DOCS_RESULTS_DIR.glob("en-pivot-*.json")
                   if (m := pattern.fullmatch(p.stem)) and p.stem not in own})
    qa_id = next(r["id"] for r in read(finqa.REPORTS / "index.json")["runs"] if r["id"] not in own)
    tatqa_id = next(r["id"] for r in read(tatqa.REPORTS / "index.json")["runs"] if r["id"] not in own)
    return {"ko": ko[-1], "en": report.DOCS_RESULTS_DIR / f"en-pivot-{tags[-1]}.json",
            "en2": report.DOCS_RESULTS_DIR / f"en-pivot-{tags[-1]}-judge2.json",
            "qa": finqa.REPORTS / f"{qa_id}.json", "tatqa": tatqa.REPORTS / f"{tatqa_id}.json"}


# ── contract ─────────────────────────────────────────────────────────────────
COLLECTION_FILES = [  # binding: changing any of these after freeze fails verify()
    Path(run.__file__), Path(judge.__file__), Path(finqa.__file__), Path(qa.__file__),
    Path(tatqa.__file__), run.PROMPT_PATH, RUBRIC, qa.SCENARIO / "prompt.txt",
    tatqa.SCENARIO / "prompt.txt", ROOT / "uv.lock",
]


def identity(ext, cfg=None, base_paths=None):
    cfg = cfg or run.load_config()
    models = ext.models(cfg)
    base_paths = base_paths or bases(ext)
    ko_parent = read(base_paths["ko"])
    # The latest explicit extension records the row digest of the same 3,300
    # inputs (the original grok-explicit report recorded a file hash instead).
    explicit = [r for r in ko_parent["source_reports"] if r["cohort"] == "explicit"][-1]
    assert sha(run.PROMPT_PATH)[:12] == explicit["prompt_sha256"], "Korean explicit prompt changed"
    assert sha(RUBRIC)[:12] == explicit["rubric_sha256"], "translation rubric changed"
    ko_rows, en_rows = finqa.read_rows(KO_SOURCE), run.load_dataset(EN_SOURCES)
    assert len(ko_rows) == KO_SEGMENTS and finqa.digest(ko_rows) == explicit["dataset_sha256"]
    en_parent = read(base_paths["en"])
    assert len(en_rows) == EN_SEGMENTS and finqa.digest(en_rows) == en_parent["manifest"]["dataset_sha256"]
    assert sha(run.PROMPT_PATH)[:12] == en_parent["manifest"]["prompt_sha256"]
    tatqa_rows = finqa.read_rows(tatqa.DATASET)
    tatqa.validate_records(tatqa_rows)
    present = {key: {m["name"] for m in read(path)["models"]} for key, path in base_paths.items()}
    for key, names in present.items():
        clash = names & set(ext.names)
        assert not clash, f"{sorted(clash)} already published in {rel(base_paths[key])}"
    return {
        "tag": ext.tag, "models": models,
        "reasoning_effort": {m["name"]: effort_of(m) for m in models},
        "bases": {key: {"path": rel(path), "sha256": sha(path), "run_id": read(path)["run_id"]}
                  for key, path in base_paths.items()},
        "files": {rel(p): sha(p) for p in COLLECTION_FILES},
        "datasets": {"ko_sha256": finqa.digest(ko_rows), "en_sha256": finqa.digest(en_rows),
                     "qa_sha256": finqa.digest(finqa.read_rows(qa.DATASET)),
                     "tatqa_sha256": finqa.digest(tatqa_rows)},
        "aws_region": cfg["aws"]["region"],
        "translation_scenario": cfg["scenario"]["translation"],
        "qa_scenario": cfg["scenario"]["finqa_audited"], "tatqa_scenario": cfg["scenario"]["tatqa"],
        "max_output_tokens": run.MAX_OUTPUT_TOKENS, "request_timeout_s": run.REQUEST_TIMEOUT_S,
        "temperature": 0,
        "temperature_omitted_model_ids": sorted(run.MANTLE_NO_TEMPERATURE | run.BEDROCK_NO_TEMPERATURE),
        "translation_cohort": "explicit", "policy": POLICY,
    }


def freeze(ext, max_usd=None):
    if ext.contract.exists():
        verify(ext)
        return read(ext.contract)
    for path in (ext.ko_dir, ext.en_dir, ext.qa_dir, ext.tatqa_dir):
        assert not path.exists(), f"{rel(path)} exists without a contract; use a new --tag"
    expected = identity(ext)
    estimate = estimate_cost(ext)
    if max_usd is not None and estimate["total_usd"] > max_usd:
        raise SystemExit(f"estimated ${estimate['total_usd']:.2f} exceeds --max-usd {max_usd}; nothing frozen")
    finqa.write_json(ext.contract, {"frozen_at": now(), "identity": expected,
                                    "extension_module_sha256": sha(__file__),
                                    "cost_estimate": estimate, "max_usd": max_usd})
    finqa.write_rows(ext.ko_dir / "dataset.jsonl", finqa.read_rows(KO_SOURCE))
    finqa.write_rows(ext.en_dir / "dataset.jsonl", run.load_dataset(EN_SOURCES))
    print(f"Frozen {ext.tag}: {', '.join(ext.names)} · estimate ${estimate['total_usd']:.2f}")
    return read(ext.contract)


def verify(ext, base_paths=None):
    """Binding fields must be unchanged; `bases` is provenance (see bases())."""
    saved = read(ext.contract)
    current = identity(ext, base_paths=base_paths or bases(ext))
    for key in current:
        if key != "bases":
            assert current[key] == saved["identity"][key], f"contract field changed since freeze: {key}"
    return saved


def composition_record(ext, base_paths):
    return {"composed_at": now(), "bases": {k: {"path": rel(p), "sha256": sha(p), "run_id": read(p)["run_id"]}
                                            for k, p in base_paths.items()},
            "code_sha256": {rel(p): sha(p) for p in (Path(__file__), Path(report.__file__), Path(finqa_compare.__file__))}}


# ── cost estimate (from the GPT-6.1 Terra addition's measured usage) ─────────
def _scale(model, ref):
    """Price ratio vs the measured reference model, weighting output 3:1."""
    return (model["price_in"] + 3 * model["price_out"]) / (ref["price_in"] + 3 * ref["price_out"])


def estimate_cost(ext):
    """Upper-bound-ish estimate before freezing; aborts the run when too high.

    Candidate usage is the GPT-6.1 Terra extension's measured cost (reasoning
    low, same inputs) scaled by price and a 2x reasoning/verbosity margin;
    judge cost per graded segment is taken directly from that extension's
    three judge cohorts. TAT-QA/QA use the reference's measured cost."""
    cfg = run.load_config()
    terra = next(m for m in cfg["models"] if m["name"] == "gpt-6.1-terra")
    ko = read(report.DOCS_RESULTS_DIR / "bedrock-gpt-6.1-terra-20261027.json")
    en = read(report.DOCS_RESULTS_DIR / "en-pivot-gpt-6.1-terra-20261027.json")
    en2 = read(report.DOCS_RESULTS_DIR / "en-pivot-gpt-6.1-terra-20261027-judge2.json")
    finqa_ref = read(finqa.REPORTS / "finqa-gpt-6.1-terra-20261027.json")
    tq = read(tatqa.REPORTS / "tatqa-api-200-20261027.json")
    tq_ref = next(m for m in tq["models"] if m["name"] == "gpt-6.1-terra")
    qa_ref = next(m for m in finqa_ref["models"] if m["name"] == "gpt-6.1-terra")
    judges_per_model = ko["judge_cost"]["cost_usd_total"] + en["judge_cost"]["cost_usd_total"] + en2["judge_cost"]["cost_usd_total"]
    rows, margin = [], 2.0
    for model in ext.models(cfg):
        s = _scale(model, terra) * margin
        candidate = s * (ko["models"][0]["aggregate"]["cost_total_usd"] + en["models"][0]["aggregate"]["cost_total_usd"]
                         + tq_ref["metrics"]["estimated_cost_usd"] + qa_ref["aggregate"]["estimated_cost_usd"])
        rows.append({"model": model["name"], "candidate_usd": round(candidate, 2), "judges_usd": round(judges_per_model, 2)})
    total = sum(r["candidate_usd"] + r["judges_usd"] for r in rows)
    return {"reference": "gpt-6.1-terra extension 2026-10-27 (measured)", "margin": margin,
            "models": rows, "total_usd": round(total, 2)}


def spent(ext):
    """Measured candidate cost so far plus judge cost (measured, or estimated
    per still-ungraded returned translation from the reference cohorts)."""
    prices = {m["name"]: m for m in read(ext.contract)["identity"]["models"]}
    def cost(rows):
        total = 0.0
        for r in rows:
            m = prices.get(r.get("model"))
            if m is None or r.get("error") or r.get("tokens_in") is None:
                continue
            total += (r["tokens_in"] * m["price_in"] + r["tokens_out"] * m["price_out"]
                      + r.get("cache_read_tokens", 0) * m.get("price_cache_read", m["price_in"])
                      + r.get("cache_write_tokens", 0) * m.get("price_cache_write", m["price_in"])) / 1e6
        return total
    candidate = sum(cost(finqa.read_rows(f)) for f in (
        ext.ko_dir / "translations.jsonl", ext.en_dir / "translations.jsonl", ext.qa_dir / "answers.jsonl",
        *ext.tatqa_dir.glob("models/*/answers.jsonl")) if f.exists())
    ref = {"ko": ("bedrock-gpt-6.1-terra-20261027", ext.ko_dir), "en": ("en-pivot-gpt-6.1-terra-20261027", ext.en_dir),
           "en2": ("en-pivot-gpt-6.1-terra-20261027-judge2", ext.en_dir)}
    judges = 0.0
    for key, (run_id, folder) in ref.items():
        reference = read(report.DOCS_RESULTS_DIR / f"{run_id}.json")
        per_segment = reference["judge_cost"]["cost_usd_total"] / reference["models"][0]["aggregate"]["segments"]
        path = folder / "translations.jsonl"
        returned = sum(1 for r in run.dedupe_latest(finqa.read_rows(path), lambda r: (r["model"], r["id"]))
                       if not r.get("error")) if path.exists() else 0
        judges += per_segment * returned
    return {"candidate_usd": round(candidate, 2), "judges_usd_estimate": round(judges, 2),
            "total_usd": round(candidate + judges, 2)}


# ── preflight: one live call per model with its configured settings ──────────
async def preflight(ext):
    import boto3
    from botocore.config import Config
    cfg = run.load_config()
    prompt = run.build_prompt({"src_lang": "ko", "tgt_lang": "en", "doc_type": "synthetic",
                               "src_text": "당사의 2026년 3분기 연결 영업이익은 전년 동기 대비 12.4% 증가한 1조 2,345억 원입니다."})
    results = {}
    for model in ext.models(cfg):
        try:
            if model["api"] == "bedrock":
                client = boto3.client("bedrock-runtime", region_name=cfg["aws"]["region"],
                                      config=Config(read_timeout=run.REQUEST_TIMEOUT_S))
                r = await run.call_bedrock(client, model["model_id"], prompt, reasoning_effort=model.get("bedrock_reasoning_effort"))
            else:
                r = await run.call_mantle(boto3.Session(), model.get("mantle_region", "us-east-1"), model["model_id"],
                                          prompt, reasoning_effort=model.get("mantle_reasoning_effort"))
            run._validate_result(r)
            results[model["name"]] = {"ok": True, "text": r["text"], "tokens_in": r["tokens_in"],
                                      "tokens_out": r["tokens_out"], "finish_reason": r.get("finish_reason")}
        except Exception as error:  # report every model, then fail
            message = str(error)
            hint = "set omit_temperature = true in config.toml" if "temperature" in message.lower() else None
            results[model["name"]] = {"ok": False, "error_type": type(error).__name__, "error": message[:500], "hint": hint}
    out = {"checked_at": now(), "results": results}
    finqa.write_json(ext.folder / "preflight.json", out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return int(not all(v["ok"] for v in results.values()))


# ── collection ───────────────────────────────────────────────────────────────
def _attempted(path):
    return {(r["model"], r["id"]) for r in finqa.read_rows(path)} if path.exists() else set()


async def collect_translation(ext, stage):
    saved = verify(ext)
    folder, run_id = (ext.ko_dir, ext.ko_run) if stage == "ko" else (ext.en_dir, ext.en_run)
    dataset = finqa.read_rows(folder / "dataset.jsonl")
    key = "ko_sha256" if stage == "ko" else "en_sha256"
    assert finqa.digest(dataset) == saved["identity"]["datasets"][key]
    finqa.write_json(folder / "extension.json", saved)
    attempted = _attempted(folder / "translations.jsonl")
    status = 0
    for name in ext.names:
        # Resume only never-attempted inputs: a recorded failure is a result.
        pending = [s for s in dataset if (name, s["id"]) not in attempted]
        if not pending:
            print(f"[{stage}] {name}: all {len(dataset)} inputs already attempted")
            continue
        pending_path = folder / f"pending-{name}.jsonl"
        finqa.write_rows(pending_path, pending)
        try:
            summary = await run.main_async(SimpleNamespace(
                models=name, run_id=run_id, dataset=str(pending_path), pairs=None, limit=None))
        finally:
            pending_path.unlink(missing_ok=True)
        status |= int(summary["failed"] != 0)
    return status


async def collect_qa(ext):
    saved = verify(ext)
    path = ext.qa_dir / "manifest.json"
    if not path.exists():
        ext.qa_dir.mkdir(parents=True, exist_ok=True)
        args = SimpleNamespace(models=",".join(ext.names), run_id=ext.qa_run, dataset=qa.DATASET, limit=None)
        with finqa.locked(ext.qa_dir):
            return await finqa.run_candidates(args, ext.qa_dir, scenario_name="finqa_audited", extra_contract=saved)
    # Resume after an interruption: finqa.run_candidates would re-request
    # recorded failures, so close the interrupted execution and request only
    # never-attempted questions under the same frozen contract.
    with finqa.locked(ext.qa_dir):
        manifest = read(path)
        assert manifest["contract"]["evaluation_protocol"] == saved, "QA contract changed"
        records = finqa.read_rows(ext.qa_dir / "dataset.jsonl")
        attempted = _attempted(ext.qa_dir / "answers.jsonl")
        pending = {name: [r for r in records if (name, r["id"]) not in attempted] for name in ext.names}
        for execution in manifest["executions"]:
            if not execution.get("finished_at"):
                execution.update(finished_at=now(), interrupted=True)
        if not any(pending.values()):
            finqa.write_json(path, manifest)
            print("[qa] already collected")
            return 0
        cfg = run.load_config()
        prompt_text = (ext.qa_dir / "prompt.txt").read_text()
        cache = run.ResultCache(ext.qa_dir / "answers.jsonl")
        execution = {"started_at": now(), "models": [], "resumed_never_attempted_only": True}
        manifest["executions"].append(execution)
        finqa.write_json(path, manifest)
        status = 0
        for model in manifest["contract"]["models"]:
            if pending[model["name"]]:
                summary = await run.run_model(model, pending[model["name"]], cache, cfg["aws"]["region"],
                                              manifest["contract"]["concurrency_default"],
                                              prompt_builder=lambda row: finqa.build_prompt(row, prompt_text=prompt_text))
                execution["models"].append(summary)
                status |= int(summary["failed"] != 0)
                finqa.write_json(path, manifest)
        execution["finished_at"] = now()
        finqa.write_json(path, manifest)
        return status


def tatqa_contract(ext, cfg):
    records = finqa.read_rows(tatqa.DATASET)
    metadata = read(tatqa.SCENARIO / "provenance.json")
    prompt_text = (tatqa.SCENARIO / "prompt.txt").read_text()
    subset = {**cfg, "models": [m for m in cfg["models"] if m["name"] in ext.names]}
    contract = tatqa.make_contract(subset, records, metadata, prompt_text, cfg["scenario"]["tatqa"]["parallel_models"])
    contract["extension_contract_sha256"] = sha(ext.contract)
    return contract, records, prompt_text


async def collect_tatqa(ext):
    verify(ext)
    cfg = run.load_config()
    contract, records, prompt_text = tatqa_contract(ext, cfg)
    for record in records:
        tatqa.build_prompt(record, prompt_text)
    tatqa.freeze_run(ext.tatqa_dir, ext.tatqa_run, contract, records, prompt_text)
    status = 0
    for model in contract["models"]:
        model_dir = ext.tatqa_dir / "models" / model["name"]
        events = finqa.read_rows(model_dir / "executions.jsonl") if (model_dir / "executions.jsonl").exists() else []
        if any(e["event"] == "finished" for e in events):
            print(f"[tatqa] {model['name']}: already collected")
            continue
        with tatqa.execution_lock(model_dir):
            tatqa.load_run(ext.tatqa_dir)
            model_dir.mkdir(parents=True, exist_ok=True)
            cache = tatqa.TATQACache(model_dir / "answers.jsonl")
            attempted = _attempted(model_dir / "answers.jsonl")
            pending = [r for r in records if (model["name"], r["id"]) not in attempted]
            event_id = f"{os.getpid()}-{tatqa.now()}"
            tatqa.append_event(model_dir / "executions.jsonl", {"event": "started", "id": event_id, "started_at": tatqa.now(),
                                                                 "pending": len(pending), "contract_sha256": finqa.digest(contract)})
            summary = await run.run_model(model, pending, cache, contract["aws_region"], contract["concurrency_default"],
                                          prompt_builder=lambda row: tatqa.build_prompt(row, prompt_text))
            tatqa.append_event(model_dir / "executions.jsonl", {"event": "finished", "id": event_id,
                                                                 "finished_at": tatqa.now(), "summary": summary})
            status |= int(summary["failed"] != 0)
    return status


# ── grading ──────────────────────────────────────────────────────────────────
def clone_for_judge2(ext):
    """Same English responses, second judge set, separate judgments file."""
    ext.en_dir2.mkdir(parents=True, exist_ok=True)
    for filename in ("translations.jsonl", "dataset.jsonl"):
        shutil.copy2(ext.en_dir / filename, ext.en_dir2 / filename)
    judges = verify(ext)["identity"]["translation_scenario"]["judge_sets"][ALT_JUDGE_SET]
    manifest = {**copy.deepcopy(read(ext.en_dir / "manifest.json")), "run_id": ext.en_run2,
                "collection_source_run_id": ext.en_run, "judge_models": [j["model_id"] for j in judges]}
    for execution in manifest["executions"]:
        execution["judge_models"] = manifest["judge_models"]
    finqa.write_json(ext.en_dir2 / "manifest.json", manifest)


async def grade(ext, target):
    saved = verify(ext)
    scenario = saved["identity"]["translation_scenario"]
    folder, run_id, judge_set = {
        "ko": (ext.ko_dir, ext.ko_run, None), "en": (ext.en_dir, ext.en_run, None),
        "en2": (ext.en_dir2, ext.en_run2, ALT_JUDGE_SET)}[target]
    if target == "en2":
        clone_for_judge2(ext)
    judges = scenario["judge_sets"][judge_set] if judge_set else scenario["judges"]
    binding = {"translations_sha256": sha(folder / "translations.jsonl"), "contract_sha256": sha(ext.contract),
               "judges": judges, "candidate_regenerated": False}
    path = folder / "judge-input.json"
    if path.exists():
        # Translations may grow only when an interrupted collection resumed;
        # the judge set and contract never change under existing grades.
        previous = read(path)
        assert previous["judges"] == judges and previous["contract_sha256"] == binding["contract_sha256"], "judge inputs changed"
    finqa.write_json(path, binding)
    summary = await judge.main_async(SimpleNamespace(run_id=run_id, dataset=str(folder / "dataset.jsonl"),
                                                     limit=None, concurrency=32, judge_set=judge_set))
    return int(summary["failed"] != 0)


# ── reports ──────────────────────────────────────────────────────────────────
def capped(row):
    details = row.get("translation_error_details", {})
    return (row.get("finish_reason") in ("length", "max_tokens") or
            details.get("incomplete_reason") == "max_output_tokens")


def translation_rows(folder, dataset, names):
    rows = run.dedupe_latest(finqa.read_rows(folder / "translations.jsonl"), lambda r: (r["model"], r["id"]))
    ids = {r["id"] for r in dataset}
    assert {(r["model"], r["id"]) for r in rows} == {(n, i) for n in names for i in ids}, "incomplete collection"
    for row in rows:
        if row.get("error") is None:
            run._validate_result({"text": row["output_text"], **{k: row.get(k, 0) for k in (
                "tokens_in", "tokens_out", "cache_read_tokens", "cache_write_tokens")}})
    return rows


def model_text(model):
    effort = effort_of(model)
    return (f"{model['name']} · {model['model_id']} · temperature "
            f"{'생략' if model['model_id'] in run.BEDROCK_NO_TEMPERATURE | run.MANTLE_NO_TEMPERATURE else '0'}"
            f" · reasoning {effort or '제공자 기본값'} · 출력 상한{run.MAX_OUTPUT_TOKENS}")


def translation_report(ext, stage, judge_target):
    saved = verify(ext)
    folder = {"ko": ext.ko_dir, "en": ext.en_dir, "en2": ext.en_dir2}[judge_target]
    run_id = {"ko": ext.ko_run, "en": ext.en_run, "en2": ext.en_run2}[judge_target]
    dataset = finqa.read_rows(folder / "dataset.jsonl")
    rows = translation_rows(folder, dataset, ext.names)
    judgments = run.dedupe_latest(finqa.read_rows(folder / "judgments.jsonl"), lambda r: (r["model"], r["id"]))
    successful = [r for r in rows if r.get("error") is None and r.get("output_text")]
    graded = {(r["model"], r["id"]) for r in judgments if r.get("error") is None and report.raw_judge_scores(r) is not None}
    pending = {(r["model"], r["id"]) for r in successful} - graded
    assert not pending, f"{len(pending)} returned translations not graded yet; rerun judge-{judge_target}"
    scenario = copy.deepcopy(saved["identity"]["translation_scenario"])
    if judge_target == "en2":
        scenario["judges"] = scenario["judge_sets"][ALT_JUDGE_SET]
    cfg = run.load_config()
    new = report.build_report(run_id, scenario, cfg["models"], [folder / "dataset.jsonl"])
    assert sorted(m["name"] for m in new["models"]) == ext.names
    total = len(dataset)
    for entry in new["models"]:
        mine = [r for r in rows if r["model"] == entry["name"]]
        ok = [r for r in mine if r.get("error") is None]
        entry["collection_diagnostics"] = {
            "scheduled_inputs": total, "recorded_attempts": sum(r.get("request_attempt", 1) for r in mine),
            "returned_outputs": len(ok), "unreturned_outputs": total - len(ok),
            "capped_outputs": sum(capped(r) for r in mine),
            "capped_with_text": sum(capped(r) and r.get("error") is None for r in mine),
            "capped_without_text": sum(capped(r) and r.get("error") is not None for r in mine),
            "all_input_quality_coverage": len(ok) / total,
            "error_types": dict(Counter(r.get("translation_error_details", {}).get("type", "unknown") for r in mine if r.get("error"))),
        }
    all_judgments = finqa.read_rows(folder / "judgments.jsonl")
    new["grading_diagnostics"] = {
        "recorded_rows": len(all_judgments), "latest_successful_segments": len(graded),
        "failed_evaluation_attempts": sum(bool(r.get("error")) for r in all_judgments),
        "candidate_regenerated_for_grading": False, "unreturned_evaluator_usage_cost_included": False,
    }
    new.update(measurement_contract=saved, measured_dataset_sha256=finqa.digest(dataset))
    language = "한국어↔15개 언어 · 3300개 입력" if stage == "ko" else "영어↔14개 언어 · 3080개 입력"
    new["interpretation"] = (
        f"{language} · 신규 모델 추가 ({ext.tag}): " + "; ".join(model_text(m) for m in saved["identity"]["models"]) +
        ". 첫 시도 결과(실패·상한 도달 포함)를 보존했고 품질은 채점 가능한 반환 출력 기준입니다. "
        "비용은 반환 성공 호출의 입력·출력·캐시 읽기·쓰기 요금 추정치입니다.")
    if stage == "en":
        new["interpretation"] += " 두 평가자 조합은 동일한 번역 응답을 각각 채점합니다."
    if new["grading_diagnostics"]["failed_evaluation_attempts"]:
        new["interpretation"] += (f' 평가 요청 실패 {new["grading_diagnostics"]["failed_evaluation_attempts"]}건은 같은 평가 '
                                  "설정으로 재시도했고 번역은 다시 생성하지 않았습니다.")
    return new


def merge_samples(result, new, names):
    incoming = {s["id"]: s for s in new["samples"]}
    assert set(incoming) == {s["id"] for s in result["samples"]}, "sample selection differs from base"
    for sample in result["samples"]:
        other = incoming[sample["id"]]
        assert {k: v for k, v in sample.items() if k != "by_model"} == {k: v for k, v in other.items() if k != "by_model"}
        for name in names:
            sample["by_model"][name] = copy.deepcopy(other["by_model"][name])


def ko_comparison(ext, new, base_paths):
    base = read(base_paths["ko"])
    assert base["dataset"] == new["dataset"]
    result = copy.deepcopy(base)
    for entry in sorted(new["models"], key=lambda m: m["name"]):
        result["models"].append({**copy.deepcopy(entry), "evaluation_cohort": "explicit", "source_report": ext.ko_run})
    merge_samples(result, new, ext.names)
    count = len(result["models"])
    explicit = sum(m.get("evaluation_cohort") == "explicit" for m in result["models"])
    result.update(run_id=ext.ko_comparison, title=f"통합 벤치마크 결과 · {count}개 모델",
                  comparison_note=(f"기존{len(base['models'])}개 결과에 {', '.join(ext.names)} 실측을 추가했습니다. "
                                   f"기존 지시{count - explicit}개와 명시적 지시{explicit}개는 프롬프트·측정 시점이 다릅니다."))
    label = re.sub(r"\s*\d+개 모델$", "", result["cohorts"]["explicit"])
    result["cohorts"]["explicit"] = f"{label}·{'·'.join(ext.names)} {explicit}개 모델"
    result["source_reports"].append({
        "run_id": ext.ko_run, "cohort": "explicit", "report_sha256": sha(report.DOCS_RESULTS_DIR / f"{ext.ko_run}.json"),
        "prompt_sha256": new["manifest"]["prompt_sha256"], "rubric_sha256": new["manifest"]["rubric_sha256"],
        "dataset_sha256": new["measured_dataset_sha256"]})
    result["extension_contract"] = new["measurement_contract"]
    result["composition"] = composition_record(ext, base_paths)
    result["parent_run_id"] = base["run_id"]
    result["interpretation"] = (base.get("interpretation") or "") + "\n\n" + new["interpretation"]
    assert result["models"][:len(base["models"])] == base["models"]
    return result


def en_comparison(ext, new, alternate, base_paths):
    saved = read(ext.contract)
    base = read(base_paths["en2" if alternate else "en"])
    assert base["dataset"] == new["dataset"]
    result = copy.deepcopy(base)
    result["models"].extend(copy.deepcopy(sorted(new["models"], key=lambda m: m["name"])))
    merge_samples(result, new, ext.names)
    result.update(
        run_id=ext.en_comparison2 if alternate else ext.en_comparison,
        title=f"영어 중심 번역 비교 · 판정 {'astra+fable-5.1' if alternate else 'sol+fable-5'} · {len(result['models'])}개 모델",
        default=alternate, parent_run_id=base["run_id"], extension_contract=saved,
        composition=composition_record(ext, base_paths))
    result["source_runs"].extend(copy.deepcopy(new["source_runs"]))
    result["source_compatibility"] = report.source_compatibility(result["source_runs"])
    result["manifest"] = copy.deepcopy(new["manifest"])
    result["judge_cost"] = {"source_estimates": [copy.deepcopy(base["judge_cost"]), copy.deepcopy(new["judge_cost"])],
                            "cost_usd_total": round(base["judge_cost"]["cost_usd_total"] + new["judge_cost"]["cost_usd_total"], 4),
                            "judges": copy.deepcopy(base["judge_cost"]["judges"]) + copy.deepcopy(new["judge_cost"]["judges"])}
    result["interpretation"] = ((base.get("interpretation") or "") + "\n\n" + new["interpretation"] +
                                f" 기존{len(base['models'])}개 모델의 점수·비용·샘플은 그대로 보존했습니다. 측정 시점은 다릅니다.")
    assert result["models"][:len(base["models"])] == base["models"]
    return result


def qa_comparison(ext, base_paths):
    saved = verify(ext, base_paths)
    manifest, dataset, predictions = finqa.load_run(ext.qa_dir)
    contract, i = manifest["contract"], saved["identity"]
    assert dataset == finqa.read_rows(qa.DATASET) and len(dataset) == QA_QUESTIONS
    assert contract["evaluation_protocol"] == saved and sorted(m["name"] for m in contract["models"]) == ext.names
    assert contract["dataset_sha256"] == i["datasets"]["qa_sha256"]
    assert all(e.get("finished_at") and e["started_at"] >= saved["frozen_at"] for e in manifest["executions"])
    rows = run.dedupe_latest(finqa.read_rows(ext.qa_dir / "answers.jsonl"), lambda r: (r["model"], r["id"]))
    base = read(base_paths["qa"])
    result = copy.deepcopy(base)
    result.update(run_id=ext.qa_run, parent_run_id=base["run_id"], extension_contract=saved,
                  composition=composition_record(ext, base_paths))
    for model in contract["models"]:
        name = model["name"]
        evaluations = []
        for record in dataset:
            raw = predictions.get((name, record["id"]))
            evaluations.append({"model": name, "id": record["id"], "question": record["question"],
                                "output_text": raw.get("output_text") if raw else None,
                                "gold_answer": record["gold_answer"], "reference_answer": record["reference_answer"],
                                "reference_program": record["reference_program"], **qa.evaluate_one(record, raw)})
        mine = [r for r in rows if r["model"] == name]
        a = finqa.summarize(evaluations)
        a.update(finqa_compare.performance_of(mine, model))
        a.update(
            strict_correct=sum(e["strict_correct"] for e in evaluations),
            format_adjusted=sum(bool(e["normalizations"]) for e in evaluations),
            execution_accuracy_ci95=qa.wilson(a["correct"], QA_QUESTIONS),
            program_valid=sum(e["program_valid"] for e in evaluations),
            unit_valid=sum(e["unit_valid"] for e in evaluations),
            requested_unit_compliant=sum(e["requested_unit_compliant"] for e in evaluations),
            unit_errors=sum(e.get("evaluation_error_code") in {"invalid_unit", "incompatible_unit"} for e in evaluations),
            truncated=sum(e.get("evaluation_error_code") == "truncated" for e in evaluations),
            cache_read_tokens=sum(r.get("cache_read_tokens", 0) for r in mine if not r.get("error")),
            cache_write_tokens=sum(r.get("cache_write_tokens", 0) for r in mine if not r.get("error")))
        result["models"].append({
            "name": name, "provider": model["api"], "aggregate": a,
            "status": "incomplete" if a["request_failed"] else "complete",
            "run_config": model, "source_run_id": ext.qa_run, "pricing_valid_until": None, "serving_config": None,
            "request_settings": {"temperature": "omitted/provider default" if model["model_id"] in i["temperature_omitted_model_ids"] else 0,
                                 "reasoning_effort": effort_of(model) or "omitted/provider default",
                                 "chat_template_kwargs": None, "max_output_tokens": i["max_output_tokens"],
                                 "concurrency": contract["concurrency_default"]}})
        result["evaluations"].extend(evaluations)
    result["warnings"].insert(0, (f"기존{len(base['models'])}개 모델의 점수·비용은 보존하고 {', '.join(ext.names)}만 "
                                  "동일20문항·프롬프트·채점기로 추가 측정했습니다. 측정 시점·호출 코드·단가는 다릅니다."))
    result["source_runs"].append({
        "run_id": ext.qa_run, "manifest_sha256": finqa.digest(manifest),
        "answers_sha256": finqa.digest(list(predictions.values())), "dataset_sha256": contract["dataset_sha256"],
        "started_at": manifest["executions"][0]["started_at"], "finished_at": manifest["executions"][-1]["finished_at"]})
    assert result["models"][:len(base["models"])] == base["models"]
    assert result["evaluations"][:len(base["evaluations"])] == base["evaluations"]
    return result


def publish_qa(result, names):
    esc = lambda value: html.escape(str(value))
    title = f"감사된 금융 QA · {len(result['models'])}개 모델"
    page = ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>body{{font:18px/1.6 system-ui;margin:2rem;overflow-wrap:anywhere}}'
            'table{border-collapse:collapse;white-space:nowrap}td,th{padding:.6rem;border:1px solid #ccc}pre{white-space:pre-wrap}'
            f'.scroll{{overflow:auto}}</style><a href="../finqa.html">금융 QA 대시보드</a><h1>{esc(title)}</h1>')
    page += "".join(f"<p>{esc(w)}</p>" for w in result["warnings"])
    page += "<div class=scroll><table><tr><th>모델</th><th>정답</th><th>정답률</th><th>비용/문항</th></tr>"
    for m in sorted(result["models"], key=lambda m: (-m["aggregate"]["execution_accuracy"], m["name"])):
        a = m["aggregate"]
        cost = a["estimated_cost_per_question_usd"]
        page += "<tr>" + "".join(f"<td>{esc(v)}</td>" for v in (
            m["name"], f'{a["correct"]}/{QA_QUESTIONS}', f'{a["execution_accuracy"]:.1%}',
            f"${cost:.5f}" if cost is not None else "—")) + "</tr>"
    page += "</table></div>"
    for m in result["models"]:
        page += f'<details><summary>{esc(m["name"])} · 원본·판정·설정</summary><pre>{esc(json.dumps(m, ensure_ascii=False, indent=2))}</pre>'
        page += "".join("<pre>" + esc(json.dumps(e, ensure_ascii=False, indent=2)) + "</pre>"
                        for e in result["evaluations"] if e["model"] == m["name"])
        page += "</details>"
    page += "<details><summary>평가 규약</summary><pre>" + esc(result["policy"]) + "</pre></details></html>"
    finqa.write_json(finqa.REPORTS / f"{result['run_id']}.json", result)
    (finqa.REPORTS / f"{result['run_id']}.html").write_text(page)
    index_path = finqa.REPORTS / "index.json"
    index = read(index_path)
    label = f"{', '.join(names)} 추가 · {title}"
    index["runs"] = [{"id": result["run_id"], "label": label}] + [r for r in index["runs"] if r["id"] != result["run_id"]]
    index["latest"] = result["run_id"]
    finqa.write_json(index_path, index)


def tatqa_comparison(ext, base_paths):
    verify(ext, base_paths)
    new = tatqa.compose_report(ext.tatqa_dir)
    assert sorted(m["name"] for m in new["models"]) == ext.names
    assert all(m["status"] != "not_run" for m in new["models"]), "TAT-QA collection missing"
    base = read(base_paths["tatqa"])
    assert base["dataset"] == new["dataset"] and base["contract"]["dataset_sha256"] == new["contract"]["dataset_sha256"]
    assert base["contract"]["prompt_sha256"] == new["contract"]["prompt_sha256"], "TAT-QA prompt changed"
    result = copy.deepcopy(base)
    result["models"].extend(copy.deepcopy(new["models"]))
    incoming = {s["id"]: s for s in new["samples"]}
    for sample in result["samples"]:
        sample["predictions"].extend(copy.deepcopy(incoming[sample["id"]]["predictions"]))
    result.update(run_id=ext.tatqa_comparison, generated_at=tatqa.now(), parent_run_id=base["run_id"],
                  composition=composition_record(ext, base_paths))
    result.setdefault("extension_runs", []).append({
        "run_id": ext.tatqa_run, "contract_sha256": new["contract_sha256"], "contract": new["contract"],
        "models": ext.names, "extension_contract_sha256": sha(ext.contract)})
    assert result["models"][:len(base["models"])] == base["models"]
    return result


def report_all(ext):
    base_paths = bases(ext)  # latest published reports, excluding this extension's own
    verify(ext, base_paths)  # same datasets/prompts, and the new models are not already published
    ko = translation_report(ext, "ko", "ko")
    report.write_report(ko)
    report.write_report(ko_comparison(ext, ko, base_paths))
    for alternate in (False, True):
        new = translation_report(ext, "en", "en2" if alternate else "en")
        report.write_report(new)
        report.write_report(en_comparison(ext, new, alternate, base_paths))
    publish_qa(qa_comparison(ext, base_paths), ext.names)
    tatqa.write_report(tatqa_comparison(ext, base_paths))
    summary = summarize(ext)
    finqa.write_json(ext.folder / "summary.json", summary)
    (ext.folder / "README.md").write_text(summary_markdown(ext, summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def summarize(ext):
    """Headline numbers for the PR body and validation README."""
    out = {"tag": ext.tag, "models": {}}
    reports = {"ko": ext.ko_run, "en": ext.en_run, "en2": ext.en_run2}
    for key, run_id in reports.items():
        data = read(report.DOCS_RESULTS_DIR / f"{run_id}.json")
        out.setdefault("judge_cost_usd", {})[key] = data["judge_cost"]["cost_usd_total"]
        for m in data["models"]:
            a = m["aggregate"]
            out["models"].setdefault(m["name"], {})[key] = {
                "segments": a["segments"], "successful": a["successful_translations"],
                "judge_overall": a.get("judge_overall"), "cost_total_usd": a["cost_total_usd"],
                "capped": m["collection_diagnostics"]["capped_outputs"]}
    qa_report = read(finqa.REPORTS / f"{ext.qa_run}.json")
    tq = read(tatqa.REPORTS / f"{ext.tatqa_comparison}.json")
    for name in ext.names:
        a = next(m for m in qa_report["models"] if m["name"] == name)["aggregate"]
        out["models"][name]["qa"] = {"correct": a["correct"], "questions": QA_QUESTIONS, "cost_usd": a["estimated_cost_usd"]}
        t = next(m for m in tq["models"] if m["name"] == name)["metrics"]
        out["models"][name]["tatqa"] = {"exact_match": t["exact_match"], "f1": t["f1"], "cost_usd": t["estimated_cost_usd"]}
    out["published"] = [f"docs/results/{ext.ko_comparison}.json", f"docs/results/{ext.en_comparison}.json",
                        f"docs/results/{ext.en_comparison2}.json", f"docs/finqa-results/{ext.qa_run}.json",
                        f"docs/tatqa-results/{ext.tatqa_comparison}.json"]
    return out


def summary_markdown(ext, s):
    lines = [f"# Model extension {ext.tag}: {', '.join(ext.names)}", "",
             "Generated by `bench.model_extension report`; see `contract.json` for the frozen inputs.", "",
             "| Model | KO judge (sol+fable-5) | EN judge (sol+fable-5) | EN judge (astra+fable-5.1) | FinQA 20 | TAT-QA EM / F1 | Candidate cost (KO+EN) |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    fmt = lambda v: "—" if v is None else f"{v:.3f}"
    for name, m in s["models"].items():
        lines.append(f"| {name} | {fmt(m['ko']['judge_overall'])} | {fmt(m['en']['judge_overall'])} | {fmt(m['en2']['judge_overall'])} | "
                     f"{m['qa']['correct']}/{m['qa']['questions']} | {m['tatqa']['exact_match']:.3f} / {m['tatqa']['f1']:.3f} | "
                     f"${m['ko']['cost_total_usd'] + m['en']['cost_total_usd']:.2f} |")
    lines += ["", f"Judge cost estimates (USD): {json.dumps(s['judge_cost_usd'])}", "",
              "Published: " + ", ".join(f"`{p}`" for p in s["published"]), ""]
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────
async def run_all(ext, max_usd):
    if not ext.contract.exists() and await preflight(ext):
        raise SystemExit("preflight failed; see preflight.json")
    freeze(ext, max_usd)
    status = 0
    # Candidate collections run one at a time so latency/throughput are not
    # measured under self-inflicted overlapping load.
    for stage in STAGES:
        status |= await {"ko": lambda: collect_translation(ext, "ko"), "en": lambda: collect_translation(ext, "en"),
                         "qa": lambda: collect_qa(ext), "tatqa": lambda: collect_tatqa(ext)}[stage]()
    # Judges only read candidate outputs; grading the three cohorts concurrently
    # does not affect any candidate measurement.
    results = await asyncio.gather(grade(ext, "ko"), grade(ext, "en"), grade(ext, "en2"))
    if any(results):
        raise SystemExit("some judge calls failed; rerun `judge-*` (cached grades are kept), then `report`")
    report_all(ext)
    return status


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["estimate", "budget", "preflight", "freeze", "verify", "run-ko", "run-en", "run-qa",
                                       "run-tatqa", "judge-ko", "judge-en", "judge-en2", "report", "all"])
    p.add_argument("--models", required=True, help="comma-separated config.toml names")
    p.add_argument("--tag", required=True, help="YYYYMMDD[letter]")
    p.add_argument("--max-usd", type=float, help="abort before freezing when the estimate exceeds this")
    args = p.parse_args(argv)
    ext = Extension(args.tag, [n.strip() for n in args.models.split(",") if n.strip()])
    c = args.command
    if c == "estimate":
        print(json.dumps(estimate_cost(ext), indent=2))
    elif c == "budget":
        # Exit 4 when measured + projected judge cost exceeds --max-usd.
        out = spent(ext)
        print(json.dumps(out, indent=2))
        return 4 if args.max_usd is not None and out["total_usd"] > args.max_usd else 0
    elif c == "preflight":
        return asyncio.run(preflight(ext))
    elif c == "freeze":
        freeze(ext, args.max_usd)
    elif c == "verify":
        verify(ext)
        print(f"Extension {ext.tag} contract verified")
    elif c.startswith("run-"):
        # Exit 3 = finished with recorded candidate failures (a valid result,
        # kept in the report); exceptions still exit 1.
        collect = {"run-ko": lambda: collect_translation(ext, "ko"), "run-en": lambda: collect_translation(ext, "en"),
                   "run-qa": lambda: collect_qa(ext), "run-tatqa": lambda: collect_tatqa(ext)}[c]
        return 3 if asyncio.run(collect()) else 0
    elif c.startswith("judge-"):
        return asyncio.run(grade(ext, c[6:]))
    elif c == "report":
        report_all(ext)
    else:
        return 3 if asyncio.run(run_all(ext, args.max_usd)) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
