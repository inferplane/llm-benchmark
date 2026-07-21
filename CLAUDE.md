# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A benchmark harness for financial-industry LLM selection: which models give the
best cost/quality tradeoff for specific customer scenarios. The first (and
currently only) scenario is Korean↔15-language financial document translation,
comparing Bedrock models, OpenAI API models, and open-weight models served via
vLLM on the shared `mall-apne2-mgmt` EKS cluster (ap-northeast-2 — see
`../aws-ec2-benchmark` for that cluster's own tooling/conventions; this repo
only adds a dedicated GPU NodePool to it, see below). Results accumulate as
JSON and are visualized by a static dashboard on GitHub Pages.

## Commands

```bash
uv sync                                    # install deps (Python 3.12 via uv)

# dataset prep (writes data/*.jsonl)
uv run python3 -m bench.dataset flores                    # needs HF_TOKEN + accepted license for openlanguagedata/flores_plus
uv run python3 -m bench.dataset flores --limit 2           # smoke run
uv run python3 -m bench.dataset synthetic                  # generates via Bedrock Sonnet, no extra creds beyond AWS
uv run python3 -m bench.dataset synthetic --limit 1 --concurrency 5

# translation runner (writes results/<run_id>/translations.jsonl)
uv run python3 -m bench.run --models nova-lite --pairs ko-en,en-ko --limit 5
uv run python3 -m bench.run --run-id my-run --dataset /tmp/smoke.jsonl   # --dataset overrides data/*.jsonl for ad-hoc smoke tests

# judge (writes results/<run_id>/judgments.jsonl); no API key needed — SigV4
# via bench.run.call_mantle, uses whatever AWS credentials are already active
uv run python3 -m bench.judge --run-id my-run --limit 20

# aggregate to the dashboard (writes docs/results/<run_id>.json + index.json)
uv run python3 -m bench.report --run-id my-run
uv run python3 -m bench.report --selfcheck    # money-path check (cost math, aggregation) — no run-id needed

# preview the dashboard locally
python3 -m http.server 8000 -d docs   # then open localhost:8000/index.html

# vLLM on the shared mgmt cluster — see deploy/serve.sh header for full usage.
# No manual scale-down step: Karpenter terminates the GPU node ~60s after you
# delete the deployment (deploy/karpenter-gpu.yaml's consolidateAfter).
deploy/serve.sh llama-3.1-8b 1        # short name from the case statement, or a raw HF id; TP = tensor-parallel-size
kubectl --context mall-apne2-mgmt -n llm-bench delete deployment vllm   # done with this model
```

There is no test suite. Correctness on the money/aggregation path is covered by
`bench/report.py --selfcheck` (hand-computed assertions); `bench/judge.py`'s
parsing logic (`parse_scores`, `build_rubric_prompt`) is pure and can be
exercised directly in a `python3 -c` one-liner without hitting any API.

## Architecture

**Scenario as a seam, not a registry.** A scenario is a directory under
`scenarios/<name>/` (`prompt.txt` + `rubric.txt`) plus a `[scenario.<name>]`
table in `config.toml`. `bench/run.py` and `bench/judge.py` currently hardcode
the `translation` scenario's prompt-building (`build_prompt`,
`build_rubric_prompt`); adding a second scenario means adding its directory,
its config section, and a second prompt-builder function — not a plugin
registry. Don't build one preemptively.

**`config.toml` is the single source of truth for models.** Every model is one
`[[models]]` table with a `name`, an `api` (`"bedrock"` | `"openai"` |
`"bedrock_mantle"`), and pricing. vLLM models use `api = "openai"` with a
`base_url` pointing at a `kubectl port-forward`'d endpoint, since vLLM's
OpenAI-compatible server lets `bench/run.py` reuse one `AsyncOpenAI` client
for both real OpenAI and self-hosted models. `bench/report.py` derives the
four-way provider label (`bedrock` / `openai` / `vllm` / `bedrock_mantle`)
from `api` + whether `base_url` is set — that derived label, not `api`, is
what the dashboard colors by. Models default `enabled = true`; set `enabled =
false` to keep a model configured but skip it in runs (e.g. while its
credentials aren't wired up yet).

**OpenAI's proprietary models (gpt-5.4/5.5/gpt-5.6-sol/terra/luna, including
the judge model) — and now xAI's `grok-4.3` (launched on Bedrock 2026-06-15) —
are called via Bedrock's `bedrock-mantle` endpoint, not each provider's own
API — no `OPENAI_API_KEY` needed at all.** `bench/run.py::call_mantle`
signs each request with the caller's own AWS SigV4 credentials
(`boto3.Session().get_credentials()`), service name `bedrock-mantle`. Three
non-obvious things learned by testing live against the real endpoint, not by
reading docs (which were themselves sometimes ambiguous or contradicted by
what actually works):
- The path is `/openai/v1/responses`, **not** the plain `/v1/responses` other
  Bedrock-hosted models use — the plain path 400s with "does not support the
  '/v1/responses' API" for every `openai.gpt-5.*` model, no exceptions found.
- These models only support the **Responses API** (`input`/`output`, message
  items with `content: [{type: "output_text", text: ...}]`), not Chat
  Completions — `call_mantle` is a separate function from `call_openai`, not
  a parameter tweak, because the request/response shapes genuinely differ.
- **`gpt-5.6-sol`/`terra`/`luna` and `gpt-5.5` reject the `temperature`
  parameter outright** (400 `unsupported_parameter`) — only `gpt-5.4` in our
  roster accepts it. This is a real, verified exception to the
  decoding-parity goal elsewhere in this file, not an oversight:
  `MANTLE_NO_TEMPERATURE` in `bench/run.py` hardcodes which model IDs must
  omit it, and `write_manifest` records `temperature_omitted` per model so
  reports are honest about which models ran under different sampling
  conditions. JSON-mode for the judge uses `text: {format: {type:
  "json_object"}}` (Responses API's nesting), not Chat Completions'
  `response_format`.
- Per-model `mantle_region` in `config.toml` matters: `gpt-5.6-sol` is only
  available in `us-east-1`/`us-east-2`; the others also work in `us-west-2`.
- **Mantle-only models never show up in `aws bedrock list-foundation-models`
  or `list-inference-profiles`** — confirmed live for both the existing
  `openai.gpt-5.*` entries and `xai.grok-4.3` (checked us-west-2/us-east-1/
  us-east-2, all empty for both). Don't use those two list APIs to check
  whether a new mantle-hosted model is real or to find its exact ID — check
  the model's own AWS docs page (`model-card-<provider>-<model>.html`) and
  verify by actually calling `call_mantle` against the live endpoint, the
  same as every other fact in this section.
- **`xai.grok-4.3` reuses `call_mantle` as-is** (same `/openai/v1/responses`
  path, same SigV4 auth, same Responses API shape) — no new integration code
  needed beyond `reasoning_effort` support. Unlike the `MANTLE_NO_TEMPERATURE`
  models, grok-4.3 *does* accept `temperature` — but reasoning is always-on by
  default (effort defaults to `"low"` per AWS's model card), which would bias
  its cost/latency against every non-reasoning model in the roster for a task
  (translation) that doesn't need chain-of-thought. `mantle_reasoning_effort =
  "none"` in `config.toml` disables it, threaded through `call_mantle`'s
  `reasoning_effort` param into the Responses API's `reasoning: {"effort":
  ...}` field — same rationale as Qwen3.6's `enable_thinking = false`.
  Recorded in the manifest/report (`mantle_reasoning_effort`, alongside
  `temperature_omitted`) for the same "be honest about non-uniform decoding
  conditions" reason.
- **`google.gemma-4-31b` is mantle-hosted too, and is the first non-OpenAI/xAI
  model verified against `call_mantle`** — added as `gemma-4-31b-bedrock`
  specifically as the managed-API route around the vLLM `gemma-4-31b` dead end
  (see below). It answers fine on `/openai/v1/responses` but, like the
  OpenAI reasoning tiers, 400s on `temperature` — confirmed live and added to
  `MANTLE_NO_TEMPERATURE`. Don't assume `MANTLE_NO_TEMPERATURE` is an
  OpenAI-only list; check any new mantle model live regardless of provider.

**Every Bedrock model priced at or under $1/1M output tokens (latest
generation per provider only — no `llama-3.2`/`mistral-7b`/`mixtral`/
`ministral-3b`/`8b`/`gemma-3`) has a `[[models]]` entry**, added in one batch
(`nova-micro`, `nemotron-nano-3-30b`, `glm-4.7-flash`, `gpt-oss-20b`/`120b`,
`qwen3-32b`, `nemotron-super-3-120b`, `llama4-scout`/`maverick`,
`ministral-14b`, `qwen3-235b-a22b`, `llama-3.3-70b-bedrock`,
`gemma-4-31b-bedrock`) after checking real per-model on-demand pricing via
`aws pricing get-products` (list-foundation-models doesn't carry price).
Two things this added to `bench/run.py::call_bedrock`, both applicable beyond
this specific batch:
- **Output parsing no longer indexes `content[0]`** — reasoning models
  (gpt-oss) put a `reasoningContent` block before the text block in Converse's
  response, so it now picks `next(b for b in content if "text" in b)`. Safe
  for every existing non-reasoning model too.
- **`bedrock_reasoning_effort` in `config.toml`** (set on `gpt-oss-20b`/`120b`)
  passes `additionalModelRequestFields: {"reasoning_effort": ...}` into
  Converse — same rationale as `mantle_reasoning_effort`/`enable_thinking`:
  gpt-oss reasons by default, and translation doesn't need chain-of-thought.
  Echoed in the manifest and `report.py::run_config_of`, same allowlist
  pattern as `extra_vllm_args`.
- **`llama-3.3-70b-bedrock` (this batch) and `llama-3.3-70b` (the vLLM entry
  below) are the same weights, served two different ways** — deliberately
  kept as two separate `[[models]]` entries (not deduped) so a report can
  show managed-API cost vs. self-hosted-GPU cost for one identical model
  side by side. The `-bedrock` suffix exists only to avoid a `name` collision.

**Pipeline stages cache independently and compose via the filesystem, not
in-process:** `bench/dataset.py` → `data/*.jsonl` → `bench/run.py` →
`results/<run_id>/translations.jsonl` → `bench/judge.py` →
`results/<run_id>/judgments.jsonl` → `bench/report.py` →
`docs/results/<run_id>.json`. Every stage's cache is an append-only JSONL
keyed by `(model, segment id)` (see `ResultCache` in `bench/run.py`, reused by
`bench/judge.py`) — **only a successful row marks a key as done**; a failed
attempt (throttled, timed out) is retried on the next run, not skipped
forever. This means a key can have multiple rows on disk (failures followed
by a success) — always dedupe to the last row per `(model, id)` via
`bench.run.dedupe_latest` before aggregating (both `bench/judge.py` and
`bench/report.py` do this). `bench/report.py` joins translations and
judgments on that key, but keeps `translation_error` and `judge_error` as
**separate fields** — a translation that succeeded but whose judge call
failed must still count as a successful translation (tokens/cost intact,
`judge_failures` +1), and a segment `judge.py` simply hasn't reached yet is
`not_yet_judged`, not a failure. Collapsing these (e.g. `{**translation,
**judgment}` with both having an `error` key) was a real, previously-shipped
bug: a judge-side error silently zeroed out that segment's cost/token data.

**Decoding must be held constant across providers to compare them at all.**
`bench/run.py::call_bedrock`/`call_openai` both pin `temperature=0` and the
same `MAX_OUTPUT_TOKENS` cap — Bedrock's Converse API silently falls back to
each model's own default sampling temperature (e.g. Nova ~0.7) if
`inferenceConfig` is omitted, which was making Bedrock models non-deterministic
and non-comparable against the greedy-decoded OpenAI/vLLM side. **`claude-sonnet-5`
is a real exception on the plain Bedrock side, same shape as
`MANTLE_NO_TEMPERATURE`**: it 400s with "`temperature` is deprecated for this
model" (caught by an actual smoke run through the pipeline — this model
hadn't been exercised end-to-end before, only used as `bench/dataset.py`'s
synthetic-reference generator, a separate code path). `BEDROCK_NO_TEMPERATURE`
in `bench/run.py` hardcodes this exclusion the same way
`MANTLE_NO_TEMPERATURE` does, and `write_manifest`'s `temperature_omitted`
check covers both sets.

**Never let a benchmark candidate contaminate its own reference.** The
synthetic dataset's reference translations are generated by claude-sonnet-4.5
(`bench/dataset.py`), which is itself a candidate model — showing that
reference to the judge, or scoring chrF against it, would bias results toward
Claude-family outputs on exactly the segments meant to test financial-domain
robustness. `bench/judge.py` gates both the judge's `reference_block` and chrF
computation on `seg["ref_source"] != "llm"`: only FLORES's human references
are ever shown. `bench/report.py` additionally reports `by_track`
(`"flores"` vs `"synthetic"`, from `doc_type`) so the two are never blurred
into one averaged number.

**Cost and throughput are reported only at the whole-model level — never
per-pair or per-track.** All of a model's segments (across every pair/track)
share one concurrent batch on the same GPU/API quota; slicing throughput by a
subset would measure that subset mixed with whatever else the model was
serving at the same time, not its isolated rate. `by_pair`/`by_track` in the
report schema carry quality fields only (`aggregate_quality`); cost/throughput
live solely in the top-level `aggregate` (`aggregate_full`, `bench/report.py`).
Within that whole-model aggregate: API models are priced from
`price_in`/`price_out` (config) × measured tokens; vLLM models from
`gpu_hourly_usd` (config) ÷ measured throughput, where the wall-clock window
(`wall_clock_seconds`) starts at the *earliest* `timestamp - latency_s` across
all rows (not the earliest completion timestamp) — using completion
timestamps alone undercounts elapsed time by roughly one request's duration.
The **primary cost metric is `cost_per_segment_usd`**, not
`usd_per_mtok_out`: since every model translates the identical segment set,
normalizing by output tokens instead rewards verbosity (a wordier model looks
cheaper per token even though it costs more per document). `usd_per_mtok_out`
is still computed and shown as a secondary number.

**Every run writes a `manifest.json`** (`bench/run.py::write_manifest`) next
to its `translations.jsonl`: git commit, prompt/rubric hashes, dataset size,
generation parameters, judge model, and per-model `run_config` (GPU instance
type, tensor-parallel size, concurrency) — this is what lets you explain "why
did this differ from last week's run" later. `bench/report.py` embeds it
verbatim into the published report under `"manifest"`.

**The dashboard (`docs/`) is intentionally zero-build**: vanilla JS +
Chart.js from a CDN, no npm/vite. `docs/results/*.json` files are both the
data and the deploy artifact — publishing a new run is `git add docs/results
&& git push` with GitHub Pages serving `/docs`. `docs/app.js` fetches with
`cache: "no-store"` deliberately: these files change on every push and have
no `Cache-Control` header, so the default browser cache will otherwise keep
serving a stale `index.json` after a new run is committed (this was a real
bug, not a hypothetical).

**The report's `"samples"` field (`bench/report.py::build_samples`) is a
small, fixed-size subset (`SAMPLES_PER_PAIR` = 5 segments per pair) for the
dashboard's sample-inspector view** — every model's raw output alongside the
source/reference, for eyeballing actual translation quality rather than just
aggregate scores. Deliberately not "every segment × every model": at full
scale that would be tens of MB fetched on every page load. **Selection must
round-robin across `doc_type` within each pair, not a flat `sorted(ids)[:n]`
— a flat sort was a real, shipped bug**: FLORES ids all start with
`"flores-"` and synthetic ids with `"synthetic-"`, and `'f' < 's'`
lexically, so a flat sort always exhausted a pair's `per_pair` budget on
FLORES before synthetic was ever considered — the sample view silently
showed 0 financial-domain documents out of 150 samples, defeating the whole
point of a sample inspector for a financial-translation benchmark. Also
worth knowing when reading the samples list: FLORES is an n-way-aligned
corpus (the same underlying sentence ids exist in every language pair), so
all 15 `ko-X` pairs' FLORES samples are literal translations of the *same*
5 Korean sentences — not a bug, just how FLORES is structured; only the
synthetic-track samples differ per pair.

**vLLM runs on `mall-apne2-mgmt`, a shared EKS cluster with other live
tenants — not a cluster this repo owns.** There used to be a standalone
eksctl-created cluster for this; it was deleted in favor of the existing
shared mgmt cluster once that was pointed out. `deploy/karpenter-gpu.yaml`
adds a dedicated `gpu-bench` Karpenter `EC2NodeClass`/`NodePool` to it
(mirrors the cluster's existing `benchmark` EC2NodeClass's subnet/SG/IAM-role
wiring — confirmed against the *live* cluster, not the checked-in configs in
`../aws-ec2-benchmark`, which that repo's own CLAUDE.md documents as drifted
from reality). Unlike a single-purpose cluster, **the `gpu-bench` NodePool
_should_ taint its nodes** (`gpu-bench=true:NoSchedule`) — every other
NodePool/nodegroup on this cluster is already tainted, and CoreDNS/system
pods run on a separate dedicated node set, so tainting here doesn't repeat
the DNS-outage mistake from the old single-node cluster; it prevents other
teams' non-GPU workloads from landing on (and wasting) an expensive GPU node.
`deploy/vllm.yaml`'s pod carries the matching toleration and deploys into its
own `llm-bench` namespace (not `default`) to stay clearly separated from
other tenants' resources. It still sets `enableServiceLinks: false`: Kubernetes
auto-injects `<SERVICE_NAME>_PORT` env vars for service discovery, and since
the Service is named `vllm`, that becomes `VLLM_PORT` — colliding with vLLM's
own identically-named internal engine-port env var and crashing it with
"VLLM_PORT ... appears to be a URI". This was a real crash loop, not a
hypothetical risk; don't reintroduce it (e.g. by renaming the Service without
also restoring this).

**A vLLM pod stuck at "Loading model from scratch..." with no new log lines
for 10+ minutes is not necessarily hung — check disk usage and per-process
CPU time before killing it.** For a 30B+ model with a cold (fresh `emptyDir`)
cache, the checkpoint download itself can take 15+ minutes depending on
node-to-HF network throughput, and `huggingface_hub`'s download progress
bars don't reliably stream through `kubectl logs` (no new log line appears
between "Using FlashAttention version" and the eventual "Loading safetensors
checkpoint shards" line, even while gigabytes are actively moving). Confirmed
live, twice, on `exaone-3.5-32b` (TP=4): `kubectl exec ... du -sh
/root/.cache/huggingface/hub/...` showed steady byte growth the whole time,
and `top` inside the pod showed one worker process (whichever rank's shards
were slowest to fetch) pinned at 50-80% CPU while the other 3 idled at
near-0% waiting at an NCCL barrier — that asymmetry is normal for TP>1 during
loading, not a sign of deadlock. **A real hang looks different: 0% CPU on
every worker process AND zero byte growth in the HF cache dir for several
consecutive checks** — that combination is what actually happened once this
session (a genuine cross-rank init deadlock, unrelated to this) and is the
right signal to kill and retry, not log staleness alone. Killing a merely-slow
pod throws away the entire partial download (`emptyDir` cache is lost) and
forces a full 100+GB re-download from zero — a real cost paid once here from
misdiagnosing "slow" as "stuck."

**Every `kubectl` call in `deploy/serve.sh` hardcodes `--context
mall-apne2-mgmt`** rather than trusting the ambient current-context — another
session on this shared kubeconfig has changed the current-context before
(documented in `../aws-ec2-benchmark/CLAUDE.md`). Don't refactor that away.
`deploy/serve.sh` also (idempotently) applies `deploy/karpenter-gpu.yaml` and
installs an `nvidia-device-plugin` DaemonSet scoped to `gpu-bench` nodes on
every invocation — no device plugin ran on this cluster before this repo's
GPU nodes existed, and re-applying is harmless. `deploy/vllm.yaml` itself is
still rendered per-model via `envsubst` (`$MODEL`, `$TP`, `$INSTANCE_TYPE`);
`deploy/serve.sh` looks up `model_id`/`tensor_parallel_size`/`gpu_instance_type`
from `config.toml` by name (not a second hardcoded mapping — that would drift),
creates the `hf-token` secret on first use, and blocks on `kubectl
port-forward` so the caller can immediately point `bench/run.py --dataset
...` at `base_url = "http://localhost:8000/v1"`. No manual scale-down step is
needed: Karpenter's `consolidateAfter: 60s` on `WhenEmpty` tears the GPU node
down automatically once the `vllm` Deployment is deleted.

**A single long-lived `kubectl port-forward` drops connections under a full-scale
run and needs an auto-restart wrapper, not just a bare `serve.sh` invocation.**
Confirmed live: `llama-3.1-8b` at concurrency=32 over the full 3170-segment
dataset threw 591 generic `httpx.ConnectError: Connection error.` failures
(~19% of segments) — all traced to the single `kubectl port-forward` process
dying mid-run, not a vLLM or model issue (the smoke-test-scale runs earlier
never hit this because they were far shorter). `ResultCache` makes the retry
free (only failed segments re-run), but for any full-scale vLLM run, wrap the
port-forward in a restart loop (`while true; do kubectl ... port-forward ...; sleep 1; done &`)
instead of a single `kubectl port-forward` in the foreground — this was not
needed for the pilot-scale smoke tests, only surfaced at real full-run volume.

**`$INSTANCE_TYPE` in the pod's `nodeSelector` is required, not optional —
`nvidia.com/gpu` alone doesn't distinguish GPU memory size.** Kubernetes'
`nvidia.com/gpu` resource is a bare *count*; a request for "1 GPU" is satisfied
equally by a 22GB `g6.4xlarge` or a 96GB GPU, and Karpenter provisions
whichever candidate is *cheapest*, not whichever has enough VRAM for the
model being deployed. This silently OOM'd a 27B model onto a 22GB GPU on a
live deploy (`CUDA out of memory... GPU 0 has a total capacity of 22.03 GiB`)
before the nodeSelector pin was added. Never remove it, and never widen a
model's instance-type list to include a too-small GPU "just in case."

**`--max-model-len=8192` is hardcoded in `deploy/vllm.yaml` for every vLLM
model — also not optional.** Some models in this roster have a native context
window far beyond what a financial-translation segment ever needs (Qwen3.6:
262144 tokens) — without capping it, vLLM reserves enough KV cache for the
*full* native context at startup and fails immediately with "KV cache is
needed... larger than the available KV cache memory," even on an
otherwise-correctly-sized GPU (hit live on Qwen3.6-27B on `g6.12xlarge`,
which has plenty of VRAM for the model weights). This also keeps every model
on the same decoding-context budget, same intent as `MAX_OUTPUT_TOKENS`.

**Per-model vLLM flags go through `extra_vllm_args` in `config.toml` (a list
of raw `--flag`/`--flag=value` strings), not new hardcoded YAML.**
`deploy/serve.sh` reads the list and renders each element as an indented
`- --flag` line into `deploy/vllm.yaml`'s `args:` block via the
`EXTRA_VLLM_ARGS_YAML` envsubst variable (empty when unset). Two live-verified
uses in the current roster: `exaone-3.5-32b` needs
`["--trust-remote-code", "--enforce-eager"]` (its HF repo ships custom
modeling code vLLM won't load without the first; the second is required
because a 32B fp16 model leaves only ~4.9GiB/GPU free on `g6.12xlarge` after
weights+KV cache, and CUDA-graph capture then OOMs — 23 crash-loop restarts
before `--enforce-eager` was added). **Any flag added here that changes
decoding or perf must also surface in the manifest**: `bench/run.py`'s
`write_manifest` and `bench/report.py`'s `run_config_of` both echo
`extra_vllm_args` verbatim (they're explicit allowlists, not generic
key-passthroughs — a new perf-affecting field has to be added to both, as
`extra_vllm_args` was). `--enforce-eager` in particular means that model's
throughput isn't CUDA-graph-accelerated like the other vLLM entries — a real
cross-model throughput caveat, which is exactly why it's recorded, not hidden.

**`gemma-4-31b` is disabled (`enabled = false`) because it cannot be served on
any GPU this cluster can provision — this is a documented dead end, not an
unfinished TODO to keep retrying.** Gemma 4 is multimodal; its vision encoder
is replicated in full on every GPU (NOT tensor-parallel-sharded) and vLLM's
`--quantization` flag does not quantize it. Live results, in order: OOM on
`g6.12xlarge` (4×L4 22GB) fp16; OOM again on `g6.48xlarge` (8×L4, *same*
22GB/GPU — more GPUs of the same per-GPU size buy nothing for a replicated
component); on `g6e.12xlarge` (4×L40S, ~44GB/GPU) with `--quantization=fp8`
the language weights did shrink (~9.7GiB/GPU, confirmed in vLLM's "Model
loading took" line) but total per-GPU use still hit ~41/44GiB and OOM'd at
KV-cache init — the unquantized, unsharded vision encoder alone eats ~30GB+
per GPU. A real fix needs an 80GB-class GPU (A100/H100 — p4d/p4de/p5), a
different cost tier this NodePool doesn't provision and one that undercuts the
"efficient open-weight model" premise anyway. Revisit only for a text-only
Gemma 4 checkpoint or if this cluster gains an 80GB-GPU NodePool.

**Instance sizing is g6 (NVIDIA L4)**, `g6.4xlarge` (1 GPU/22GB) for ≤13B,
`g6.12xlarge` (4 GPU/89GB, TP=4) for 27-32B, `g6.48xlarge` (8 GPU/179GB, TP=8)
for 70B — see `config.toml`'s `gpu_instance_type`/`tensor_parallel_size` per
model. **Do not switch this to g7e** ("RTX PRO Server 6000", 96GB/GPU — would
let 27-32B run on a single GPU with no tensor-parallel at all, and it's
cheaper than g6.12xlarge) **without checking this cluster's Karpenter version
first.** Verified twice live (once with a 1-AZ constraint, once with all 3
AZs allowed, ruling out a zone-capacity fluke): scheduling a pod requesting
`nvidia.com/gpu` with `node.kubernetes.io/instance-type: g7e.4xlarge` always
fails with "no instance type met all requirements," even though `aws ec2
describe-instance-types` confirms the instance type and its GPU spec exist.
Root cause: this cluster runs Karpenter v1.9.0
(`kubectl -n karpenter get deployment -o jsonpath='{.items[0].spec.template.spec.containers[0].image}'`),
and `g7e.4xlarge` only appears in Karpenter's own instance-type reference
docs under the v1.14 (latest) version — the AWS API knows about it, this
Karpenter's bundled data doesn't yet. Revisit if that cluster's Karpenter
gets upgraded past whatever version actually added g7e support.

**`HF_TOKEN` is only required for the actually-gated vLLM models — verify with
`HfApi().model_info(id).gated` before assuming, and re-verify with a real
`hf_hub_download()` call, not just `model_info()`/`dataset_info()` succeeding**
(those return public metadata regardless of gating — only an actual file
download enforces the real access check; this cost real back-and-forth before
being caught). Confirmed live: Llama-3.1-8B and Llama-3.3-70B are
`gated="manual"`, needing a human reviewer at Meta to approve the request —
this can take anywhere from minutes to longer, unlike Google's/HF's own
gates, which auto-approve near-instantly. Gemma-4-31B-it, Qwen3.6-27B, and
EXAONE-3.5-32B-Instruct are **not** gated at all — no token needed. Don't
assume every open-weight model needs a token, and don't assume every gate
approves on the same timeline.

**Check for newer model releases before trusting this file's or your own
training data's model roster — this codebase's knowledge lags in real time.**
Mid-session, live checks turned up: Gemma 4 (released 2026-04-02, superseded
Gemma 3 in `config.toml` — also dropped the gate Gemma 3 had) and Qwen3.6
(released 2026-04-22, superseded Qwen3 — also ungated). Qwen3.6's chat
template defaults to emitting a `<think>...</think>` block unless
`enable_thinking: false` is passed (verified against the live
`tokenizer_config.json`) — `bench/run.py::call_openai`'s `chat_template_kwargs`
parameter (forwarded to vLLM as `extra_body`) exists specifically for this;
`config.toml`'s `qwen3.6-27b` entry sets it. If a future model swap has a
similar non-default chat-template behavior, follow the same pattern rather
than post-processing `<think>` tags out of `output_text`.

## Known limitations (accepted for now, not bugs to silently "fix")

- **Sample size is config-driven, not fixed** — both `flores_per_pair` (100)
  and `synthetic_per_pair` (10) were scaled up from an initial 20/5 pilot.
  Unlike FLORES (fixed-seed shuffle + slice — growing `per_pair` only appends
  new ids, safe to bump anytime), `bench/dataset.py`'s synthetic generator
  fully overwrites `synthetic.jsonl` on every regen and is LLM-generated
  (not sampled from a fixed corpus), so content under stable ids like
  `synthetic-ko0` changes on every regen even at temperature=0. **This is
  not hypothetical — it happened live**: an earlier scale-up regenerated
  `synthetic.jsonl` while 13 models' translations/judgments from a prior run
  were already cached under those same ids, silently pointing them at
  different underlying text. Fixed by deleting every affected `synthetic-*`
  row from that run's `translations.jsonl`/`judgments.jsonl` and letting
  them redo against the new file. **Any future bump to `synthetic_per_pair`
  needs that same invalidate-and-redo step for every existing run** — a
  config edit alone is not enough and will silently corrupt existing runs'
  synthetic-track numbers. `judge_overall_ci95` (bootstrap 95% CI, computed
  in `bench/report.py::bootstrap_ci95`) narrows with N but can still overlap
  between close models — don't assert a ranking when it does. Any further
  scale-up is a real $ decision (judge cost scales linearly with segments ×
  candidate models, and real-run judge pricing turned out to be
  FLORES-segment-length-sensitive — verified ~$0.0059/FLORES-judgment vs
  ~$0.0160/synthetic-judgment from an actual run, not a flat estimate); get
  an explicit go-ahead before bumping these, don't silently default upward.
- **No deterministic number/date/currency extraction** — the judge's
  `numbers_entities_dates` axis is still purely LLM-based, not cross-checked
  against a regex-extracted ground truth. Worth adding; not implemented.
- **Single judge, no pairwise/blind comparison, no human spot-check** — the
  judge model (`gpt-5.6-sol`) is never shown candidate model names, but
  same-provider-family bias (judging gpt-5.4/5.5/5.6-terra candidates) isn't
  otherwise mitigated. A second judge on a sample, or blind pairwise A/B for
  close scores, is the documented upgrade path — not built.
- **Latency comparison across providers is directional only**: concurrency
  differs by design (API default 8, vLLM 32), and Bedrock's sync `converse()`
  is wrapped in `asyncio.to_thread` rather than called natively async — p50/p95
  numbers aren't measuring the same thing across providers.
- **No financial-domain track with real human-reviewed documents.** The
  "synthetic" track is LLM-generated financial-style documents (robustness
  stress test), not actual reviewed financial filings — acquiring/licensing
  real documents for a proper human-reference financial track is out of scope
  for this codebase alone.
