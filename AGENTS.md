<!-- generated-by: co-agent · source: CLAUDE.md · claude-md-sha: adb71121addf · generated-at: 2026-07-20 · DO NOT EDIT — edit CLAUDE.md then run /co-agent sync-context -->

> You are an external reviewer for this repo — project context below, distilled from CLAUDE.md. This file is shared verbatim by Kiro, Codex, and Agy (not a per-AI copy).

# Project Context

LLM benchmark harness for financial-industry translation quality/cost comparison
(Bedrock, OpenAI API, and open-weight models on vLLM). One scenario so far:
Korean↔15-language document translation.

## Stack

- Python 3.12, managed with `uv` (no separate venv/pip workflow).
- Dashboard: vanilla JS + Chart.js from CDN, zero build step (`docs/`), deployed via GitHub Pages.
- Infra: vLLM runs on `mall-apne2-mgmt`, a **shared** EKS cluster with other live tenants (not
  owned by this repo) — Karpenter NodePool/EC2NodeClass + raw `kubectl` manifests, no Helm/CDK.

## Commands

```bash
uv sync
uv run python3 -m bench.dataset flores      # needs HF_TOKEN + accepted license
uv run python3 -m bench.dataset synthetic
uv run python3 -m bench.run --models nova-lite --pairs ko-en,en-ko --limit 5
uv run python3 -m bench.judge --run-id <id>          # no API key — SigV4 via existing AWS credentials
uv run python3 -m bench.report --run-id <id>
uv run python3 -m bench.report --selfcheck            # cost/aggregation correctness check
python3 -m http.server 8000 -d docs                    # preview dashboard locally
```

No test framework/CI. Correctness on the money path is `bench/report.py --selfcheck`
(hand-computed assertions on `compute_cost`/`aggregate_full`/`wall_clock_seconds`).
`bench/judge.py`'s pure parsing functions (`parse_scores`, `build_rubric_prompt`) are
checkable directly with a `python3 -c` one-liner, no API calls needed.

## Architecture boundaries

- **Scenario = directory + config, not a registry.** `scenarios/<name>/{prompt,rubric}.txt`
  + a `[scenario.<name>]` table in `config.toml`. `bench/run.py`/`bench/judge.py` currently
  hardcode the `translation` scenario's prompt-building functions. A second scenario adds
  its own directory/config/builder function — don't add a plugin/registry abstraction for it.
- **`config.toml` is the only source of truth for models.** Every model is one `[[models]]`
  table with `api` (`bedrock`|`openai`|`bedrock_mantle`) + pricing. vLLM models are
  `api = "openai"` with a `base_url` set — that's the sole signal distinguishing "self-hosted"
  from "real OpenAI API" (see `bench/report.py`'s provider derivation). Don't read pricing
  or model IDs from anywhere else.
- **OpenAI's proprietary models (gpt-5.4/5.5/gpt-5.6-sol/terra/luna, including the judge) go
  through Bedrock's `bedrock-mantle` endpoint (`api = "bedrock_mantle"`), authenticated with
  the caller's own AWS SigV4 credentials — no `OPENAI_API_KEY` anywhere in this codebase.**
  Verified live, not from docs alone: the path is `/openai/v1/responses` (the plain
  `/v1/responses` 400s for every one of these model IDs), it's Responses-API-only (no Chat
  Completions), and `gpt-5.6-sol`/`terra`/`luna`/`gpt-5.5` reject `temperature` outright — only
  `gpt-5.4` accepts it. `bench/run.py::MANTLE_NO_TEMPERATURE` hardcodes the exception list.
- **Pipeline stages compose via the filesystem, not in-process calls**: `bench/dataset.py` →
  `data/*.jsonl` → `bench/run.py` → `results/<run_id>/translations.jsonl` → `bench/judge.py` →
  `results/<run_id>/judgments.jsonl` → `bench/report.py` → `docs/results/<run_id>.json`. Each
  stage's cache is append-only JSONL keyed by `(model, segment id)`, and **only a successful
  row marks a key done** — a failed attempt is retried on the next run, so a key can have
  multiple rows on disk. Always dedupe to the last row per key via `bench.run.dedupe_latest`
  before aggregating.
- **`translation_error` and `judge_error` are separate fields, never merged.** A translation
  that succeeded but whose judge call failed must still count as a successful translation
  (tokens/cost intact); a segment `judge.py` hasn't reached yet is `not_yet_judged`, not a
  failure. A naive `{**translation, **judgment}` merge (both having an `error` key) was a real
  shipped bug that zeroed out cost data for any segment whose judge call errored.
- **Cost/throughput exist only at the whole-model level** — never per-pair or per-track
  (`by_pair`/`by_track` carry quality fields only, via `aggregate_quality`). A model's segments
  all share one concurrent batch, so a subset's completion-timestamp span is contaminated by
  whatever else that model was serving at the same time. The primary cost metric is
  `cost_per_segment_usd` (every model translates the same fixed segment set), not
  `usd_per_mtok_out` — normalizing by output tokens rewards verbose models with a misleadingly
  low per-token rate.
- **Decoding parameters are pinned identically across providers**: `temperature=0` and one
  `MAX_OUTPUT_TOKENS` cap, set explicitly in both `call_bedrock` (via `inferenceConfig`) and
  `call_openai`. Omitting Bedrock's `inferenceConfig` silently falls back to each model's own
  default sampling temperature — that made Bedrock non-comparable against the greedy-decoded
  OpenAI/vLLM side.
- **A benchmark candidate must never generate its own reference.** The synthetic dataset's
  references are written by claude-sonnet-4.5, itself a candidate — `bench/judge.py` never
  shows the judge a reference or computes chrF when `seg["ref_source"] == "llm"` (only FLORES's
  human references are used for either). `by_track` (`flores` vs `synthetic`) keeps the two
  scored populations visibly separate in the report.

## Banned patterns (repo-specific, not generic advice)

- **Never call `kubectl` without `--context mall-apne2-mgmt`** in `deploy/serve.sh` — this is a
  shared kubeconfig; another session has changed the ambient current-context before. Don't
  refactor the hardcoded `kubectl(){ command kubectl --context mall-apne2-mgmt ... }` wrapper away.
- **Never remove the `gpu-bench` taint/toleration pair.** Unlike a single-purpose cluster, every
  NodePool on `mall-apne2-mgmt` is already tainted and CoreDNS/system pods run on a separate
  dedicated node set — removing this taint would let other teams' non-GPU workloads land on (and
  waste) an expensive GPU node, the opposite of the risk on a dedicated cluster.
- **Never drop `$INSTANCE_TYPE` from the pod's `nodeSelector` in `deploy/vllm.yaml`.**
  `nvidia.com/gpu` is a bare GPU count — Karpenter will provision the cheapest instance type in
  the NodePool that satisfies the count, not the one with enough VRAM. Silently OOM'd a 27B
  model onto a 22GB GPU on a live deploy before this was pinned.
- **Never drop `--max-model-len=8192` from `deploy/vllm.yaml`.** Some models here have a native
  context window far beyond what a translation segment needs (Qwen3.6: 262144) — without the
  cap, vLLM reserves KV cache for the full native context and fails to start even on an
  otherwise-correctly-sized GPU.
- **Don't switch GPU sizing to the g7e family without checking this cluster's Karpenter
  version.** Verified twice live (including with all 3 AZs allowed, ruling out a capacity
  fluke): scheduling fails with "no instance type met all requirements" for g7e.4xlarge even
  though the AWS API confirms it exists — this cluster's Karpenter is v1.9.0, and g7e only
  appears in Karpenter's own docs under v1.14. `deploy/karpenter-gpu.yaml` stays on g6
  (NVIDIA L4) / g6e (L40S) until that cluster's Karpenter is upgraded. The NodePool's zone
  list is restricted to `ap-northeast-2a` only: g6e schedules in 2a/2b, but 2b's subnet
  (tagged production/platform) blocks HF downloads with an instant HTTP 504 — a firewall,
  not a routing gap. Don't widen the zone list back to 2b.
- **Per-model vLLM flags go through `config.toml`'s `extra_vllm_args` list, not new hardcoded
  YAML.** `deploy/serve.sh` renders each element into `deploy/vllm.yaml`'s `args:` block via the
  `EXTRA_VLLM_ARGS_YAML` envsubst var. Any perf/decoding-affecting flag added there must also be
  echoed into the manifest — `bench/run.py::write_manifest` and `bench/report.py::run_config_of`
  are explicit allowlists (not generic key-passthroughs), so a new field has to be added to both.
  `exaone-3.5-32b` uses `["--trust-remote-code", "--enforce-eager"]` (custom HF modeling code +
  a too-tight 4.9GiB/GPU fit that OOMs at CUDA-graph capture); its throughput is therefore not
  graph-accelerated — a real cross-model caveat, which is why it's recorded, not hidden.
- **Don't kill a vLLM pod just because `kubectl logs` has been silent for 10+ minutes at
  "Loading model from scratch..." — check `du -sh` on the HF cache dir and `top` inside the pod
  first.** A cold-cache 30B+ download can take 15+ minutes with no new log line (HF's progress
  bars don't reliably stream through `kubectl logs`); one straggling TP worker at 50-80% CPU
  while others idle near 0% (NCCL barrier wait) is normal, not a deadlock. A real hang is 0% CPU
  everywhere AND zero cache-dir growth across several checks. Killing a merely-slow pod discards
  the whole `emptyDir` download and forces a full re-download from zero.
- **A single `kubectl port-forward` isn't durable enough for a full-scale vLLM run.** Confirmed
  live: `llama-3.1-8b` at concurrency=32 over 3170 segments hit ~19% `Connection error.` failures
  from the port-forward process dying mid-run — not a model issue. Wrap it in a restart loop for
  any full (non-smoke) run.
- **`bench/report.py::build_samples` must round-robin across `doc_type` per pair, never a flat
  `sorted(ids)[:n]`.** `"flores-" < "synthetic-"` lexically, so a flat sort silently produced a
  150-sample set with zero synthetic (financial-domain) documents — shipped, then fixed.
- **Mantle-only models (`openai.gpt-5.*`, `xai.grok-4.3`) never show up in `list-foundation-models`/
  `list-inference-profiles`** — verify a new one via its AWS docs model-card page and a live
  `call_mantle` test, not those list APIs. `grok-4.3` reuses `call_mantle` unchanged; it needed
  `mantle_reasoning_effort = "none"` (reasoning defaults on) for decoding parity, same rationale
  as Qwen3.6's `enable_thinking = false`.
- **Never bump `synthetic_per_pair` without invalidating existing runs' cached `synthetic-*` rows
  first.** Unlike FLORES (fixed-seed shuffle+slice, safe to grow), `bench/dataset.py`'s synthetic
  generator fully overwrites `synthetic.jsonl` with fresh LLM output on every regen — the content
  under stable ids like `synthetic-ko0` changes even at temperature=0. This silently corrupted a
  prior run's cache live; the fix was deleting every affected `synthetic-*` row from that run's
  `translations.jsonl`/`judgments.jsonl` before letting it redo against the new file.
- **Don't retry `gemma-4-31b` on more/bigger g6/g6e GPUs — it's a documented dead end**
  (`enabled = false`). It's multimodal; the vision encoder is replicated per-GPU (not TP-sharded)
  and isn't quantized by `--quantization`, eating ~30GB+/GPU. OOM'd on g6.12xlarge, g6.48xlarge,
  and g6e.12xlarge+fp8. Needs an 80GB-class GPU this NodePool doesn't provision. Revisit only for
  a text-only Gemma 4 checkpoint or a new 80GB-GPU NodePool.
- **Never name the vLLM Service `vllm`** (or reintroduce it) without `enableServiceLinks: false`
  on the pod. Kubernetes auto-injects `<SERVICE_NAME>_PORT`; a service named `vllm` collides
  with vLLM's own `VLLM_PORT` env var and crashes the engine ("VLLM_PORT ... appears to be a
  URI"). Already happened once.
- **`docs/app.js` fetches with `cache: "no-store"` deliberately** — not leftover debug code.
  `docs/results/*.json` changes every run and has no `Cache-Control` header, so the default
  cache silently serves a stale `index.json` after a push. Don't "clean up" this option.
- **Never merge `translation_error`/`judge_error` into one `error` field**, and never treat
  `not_yet_judged` (no judgment row exists) the same as `judge_failures` (judged and errored) —
  see Architecture boundaries above.

## Review checklist

- Cost/report changes: does `bench/report.py --selfcheck` still pass? Any new cost or timing
  path needs a hand-computed assertion added to `_selfcheck()`, not a new test file/framework.
- New model in `config.toml`: real `model_id` + pricing verified against a live source
  (`aws bedrock list-inference-profiles`, `aws pricing get-products`, or the provider's own
  pricing page), not guessed from training-data memory. Sonnet-5's promotional pricing has an
  expiry date noted in a config comment — re-check it if it's past.
- New/changed cost or quality field: does it stay scoped correctly — model-level only for
  cost/throughput, any-subset-safe for quality (see Architecture boundaries)?
- Deploy manifest changes: keep the `gpu-bench` taint/toleration and `--context
  mall-apne2-mgmt`, and don't name a Service `vllm` without `enableServiceLinks: false`
  (see Banned patterns). This is a shared cluster — any new resource should stay scoped to
  the `llm-bench` namespace and the `gpu-bench` NodePool, not touch other tenants'.
- Known non-issue: `g6.4xlarge` (1 GPU/22GB) can't run the 27B+ models already listed in
  `config.toml` — `gpu_instance_type` per model documents which size each one needs; that's
  expected, not a bug to flag.
- Known limitation, not a bug to "fix" unprompted: current sample size (20 FLORES + 5 synthetic
  per direction) is pilot-scale; `judge_overall_ci95` will often overlap between close models.
  Scaling it up is a real $ decision for the user, not something to do silently.
- New vLLM model: check gating with a real `hf_hub_download()` call, not just
  `model_info()`/`dataset_info()` succeeding (those return public metadata regardless of
  gating). Currently only Llama-3.1-8B/3.3-70B are gated (manual, Meta-reviewed — can take a
  while); Gemma-4-31B-it, Qwen3.6-27B, and EXAONE-3.5-32B-Instruct are not gated at all.
- New vLLM model: check its chat template for non-default behavior (e.g. Qwen3.6 emits
  `<think>` by default) and use `chat_template_kwargs` in its `config.toml` entry if so, rather
  than post-processing the model's output text.
- Before trusting this file's or your own training data's model roster, check for newer
  releases live — Gemma 4 and Qwen3.6 both superseded what this repo originally used
  mid-session, and both also happened to drop the gating their predecessors had.
