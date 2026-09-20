# Kimi K3 independent preflight code/protocol review

**Verdict: REQUEST CHANGES before bulk collection / freezing the extension. 0 Critical, 2 Major, 0 additional Minor findings.**

**Latest snapshot update:** the parent changed `bench/kimi_benchmark.py` during review to SHA-256 `08b97a4062d564cad255515a3f8ee1e8d335cdceaac6b0104134dd42ce472215`. I re-reviewed and reran the probes on that version. Six M1 mutations now reject, but temperature, timeout and scenario mutations still pass; M2 is unchanged. The detailed initial findings below preserve the original reproduction, and the final update section records the current disposition.

Date: 2026-09-20. Worktree: `/home/atomoh/llm-benchmark/.worktrees/kimi-k3`.
Base and current committed HEAD: **`7305b4943800759cbac35efe8438c2de6de3a074`** (`origin/main` as supplied).

This reviews the **uncommitted working-file hashes below**, not an exact committed PR HEAD. Scope: changes to `bench/run.py`, `bench/report.py`, `config.toml`, new `bench/kimi_benchmark.py`, and retained `validation/kimi-k3` evidence. No repository code edits, provider/model calls, actual extension freeze, publication, commits or subagents were used. Tests create temporary fixtures under `/tmp`.

## M1 — Major: QA source generation settings are not bound to the extension identity

**Location:** `bench/kimi_benchmark.py:116–127`, with extension identity at lines 71–88.

`qa_comparison()` checks the attached extension object, selected records/model, dataset digest, collector hash and actual prompt-file hash. It does not compare several actual run-contract fields with the extension's pre-call identity. A valid attachment therefore does not establish that the declared execution settings used by the source are the frozen settings.

**Reproduction:** Created a temporary extension using the real `freeze()` and ran the real `measure_qa()` wrapper for 20 mocked responses. Preserved the genuine extension attachment and all source responses, then changed each of the following manifest fields individually:

```text
max_output_tokens = 17
concurrency_default = 19
aws_region = "different"
temperature = 1
temperature_omitted_model_ids = []
request_timeout_s = 1
finqa_sha256 = "different"
scenario = "translation"
prompt_sha256 = "different"
```

**All nine mutations were accepted by `qa_comparison()`.** For example, the cap mutation produces an otherwise accepted audited extension displaying cap `17`, even though the extension identity freezes `4096`. The prompt file remains genuine, but a conflicting prompt hash in the source contract is also accepted.

This is a provenance-validation defect, not a claim that the normal wrapper presently emits those altered contracts. It is particularly important for this extension because historical transport cannot be re-executed by pretending the old freeze still matches the new collector.

**Required correction:** Before scoring, bind the actual source contract to the extension identity: scenario/run/model, cap, region, concurrency, temperature/omission policy, timeout, DSL and prompt hashes, in addition to existing dataset/collector checks. Add any missing generation-setting fields to the extension identity first, then freeze the corrected extension. Derive display settings from the verified contract. Add negative tests for each independently mutable field.

Keep the old freeze and frozen grading files unchanged; this correction belongs in the new extension module.

## M2 — Major: translation append accepts wrong or incomplete source reports based on metadata/sample checks

**Location:** `bench/kimi_benchmark.py:219–249`.

The translation append verifies only the summary `dataset` object, a model **display name**, prompt/rubric hash strings, and displayed sample metadata. It does not establish that the new report belongs to `TRANSLATION_RUN`, that its actual model/settings are Kimi, that all 3,300 source segments were measured, or that the source dataset and report metrics are bound to retained run evidence.

`base["dataset"]` describes configured coverage: it is not a content hash or proof of actual measured coverage. The parent original-cohort `dataset_sha256` is absent, and the new report's dataset hash is copied into the output without validation. Matching the 210 displayed samples cannot verify the remaining source population.

**Reproduction:** Supplied a temporary synthetic new-report file with:

- Matching advertised 3,300-segment dataset metadata and displayed sample metadata.
- Matching prompt/rubric strings.
- Model display name `kimi-k3`, but `run_config={"model_id":"not-kimi","temperature":9}`.
- Wrong top-level `run_id`, `manifest.dataset_sha256="wrong-full-dataset"` and an empty manifest model list.
- Aggregate `segments=1` and `successful_translations=1`.
- No retained translation source run backing that report.

`translation_comparison()` accepted it and produced the 30-model integrated comparison while retaining the full advertised dataset metadata.

**Required correction:** Bind the new translation report to its expected run ID, retained manifest/raw source observations, actual Kimi model and generation/pricing settings, and full selected dataset identity. Validate all expected unique segment IDs and actual coverage, including failed/missing/judgment coverage rather than treating configured counts as observed counts. If collection/evaluation is incomplete, reject final append or explicitly represent the incomplete population.

Before bulk collection, record the new translation input/code/settings identity so it can be checked afterward. For the historical original cohort's missing dataset digest, establish equivalence from retained source/dataset evidence rather than inventing an old hash or relying only on the sample subset. Preserve the existing 29 snapshots unchanged.

## Checks that passed

### Cache classes and pricing

The retained live evidence reconciles exactly:

```text
7 ordinary input + 1,694 cache write + 36 output = 1,737 total
7 ordinary input + 1,694 cache read  + 90 output = 1,791 total
```

The code correctly treats ordinary Converse `inputTokens` separately from cache reads/writes. It does not price cache usage as free ordinary input. It retains provider output-token usage rather than pricing only the visible `"OK"` text.

Independently parsed all four retained AWS Price List records for `us-west-2`, standard service tier, converting their per-1K-token units to per-million units:

| Token class | Configured USD / million | Retained SKU |
| --- | ---: | --- |
| Ordinary input | 3.30 | `TAH329YX2XBDXY7R` |
| Output | 16.50 | `3PTVWDVQ74UFBC4C` |
| Cache read | 0.33 | `MQ3ZZX8C4JGNYBHN` |
| Cache write, 30-minute class | 4.125 | `3H63F438ZC7RTEQ7` |

All four configuration values match that retained pricing evidence.

Independent exact-decimal calculations for the two retained probes:

```text
write probe: $0.00760485 → shared report rounding $0.0076
read probe:  $0.00206712 → shared report rounding $0.0021
```

The new money-path assertions also pass for a million tokens of each class: `$24.255`, and two equal rows aggregate to `$24.255` / `$12.1275` per row. Observed cache usage without configured cache prices raises rather than silently undercharging.

The actual request-path selfcheck confirms temperature is omitted for `us.moonshotai.kimi-k3` while Nova retains temperature, the output cap remains explicit, reasoning content is not mistaken for output text, and the two cache token classes survive response validation. The new cache-rate fields are included in translation run metadata and report run configuration.

These are checks against retained evidence and code, not a fresh AWS API or invoice validation. The retained Kimi smoke record and temperature-rejection observation were read; no new provider calls were made.

### Parent preservation and extension runtime

- `verify_parent()` successfully replays **all 560 parent QA judgments** using unchanged grading/data artifacts.
- The original `qa.verify_freeze()` rejects the current collector, as expected and explicitly documented. This is not a regression to bypass by rewriting the old freeze.
- The new extension identity binds the parent report/freeze hashes, dataset/prompt/grader identities, new collector, extension implementation and cost code.
- The real extension wrapper successfully collected 20 **mocked** rows in a temporary run directory.
- QA composition preserves the original 28 model objects and 560 evaluation objects unchanged.
- The mocked 20-write-probe batch retains 33,880 cache-write tokens and estimates `$0.1521`, consistent with independent arithmetic.
- Translation composition deep-copies existing model snapshots and appends Kimi rather than recalculating old scores/costs. M2 concerns its insufficient validation of the added source, not observed mutation of historical models.

### Offline suites

All passed:

```text
bench.run._selfcheck()
bench.report._selfcheck()
bench.finqa.selfcheck()
bench.finqa_compare.selfcheck()
```

Executed with:

```bash
UV_PROJECT_ENVIRONMENT=/home/atomoh/llm-benchmark/.venv \
UV_CACHE_DIR=/home/atomoh/llm-benchmark/.worktrees/.uv-cache \
PYTHONDONTWRITEBYTECODE=1 \
uv run --offline --no-sync ...
```

The mocked thread-based suite used escalation to avoid the known sandbox asyncio wake-up issue. No real request clients were invoked.

Independent probes and logs:

```text
/tmp/kimi-k3-independent-checks.py
/tmp/kimi-k3-independent-checks.log
/tmp/kimi-k3-selfchecks.log
```

The probe's synthetic translation report and mocked QA responses are deliberately invalid/temporary test inputs. They are not benchmark measurements and were not written to the repository.

## Exact reviewed file hashes

The four implementation/config hashes were captured before and after the independent probes and were unchanged. Later parent edits or added tests are not covered unless their resulting hashes match or are re-reviewed.

```text
d89af06bc276d52e35ed5f02fc80763d56595b1de1235e1db4a730227c504711  bench/kimi_benchmark.py
1e4b2ae0fe359919e042b9b5074561f062b46aa86056b5a4bab2c999ad596341  bench/run.py
48733dd5d678b8e655a752ad4a7c356daaea1c32ecf454b78ab40d358c4375da  bench/report.py
e32ca14acb6f193fd65835d56cae6e12bae4b432a41b7a186856876b05fbfe77  config.toml
4c9bf9bdff5495d48193a35a252e74f2a6e793613f1a5d5b2918d32fd78ff7b8  validation/kimi-k3/live-check.json
1e756a21bd1a81c11dccd85a481ac8c6db42f0d055acb1a98b4d70a9f0f1207d  validation/kimi-k3/pricing-us-standard.json
```

An initial broad `git status` encountered the sandbox's read-only `.git/lfs/tmp` restriction when Git LFS attempted a clean-filter temporary write. Scoped code diffs, file reads and hashes succeeded; that environmental error is not a product finding. No claim of a clean working tree is made: this is intentionally an uncommitted development diff.

**Gate:** resolve M1 and M2, rerun the negative binding/coverage checks, then establish the corrected pre-call contract(s) before bulk collection. Obtain the latest exact committed HEAD review after fixes and the final artifact checks before merge. This report does not approve the current uncommitted code for bulk Kimi calls or satisfy the final exact-HEAD PR review.

## Concurrent parent update re-reviewed

Latest re-reviewed `bench/kimi_benchmark.py`:

```text
08b97a4062d564cad255515a3f8ee1e8d335cdceaac6b0104134dd42ce472215  bench/kimi_benchmark.py
```

All other listed implementation/config/evidence hashes remained unchanged at recheck.

The update adds parent report-hash verification against retained `result-verification.json`, checks the parent roster, and rejects altered QA cap, default concurrency, AWS region, temperature-omission list, DSL hash and prompt hash. The new `bench.kimi_benchmark selfcheck` passes, including the mocked 29-model/580-evaluation append and its hand-computed `$0.0108` cache-inclusive fee.

Independent rerun on this exact newer file:

```text
REJECTED: max_output_tokens, concurrency_default, aws_region,
          temperature_omitted_model_ids, finqa_sha256, prompt_sha256
ACCEPTED: temperature=1, request_timeout_s=1, scenario="translation"
ACCEPTED: translation fixture with wrong run/model/dataset and one aggregate segment
```

**Current M1 disposition: partially resolved, still Major.** At new lines 121–137, bind/check the remaining scenario and request-contract fields before scoring. The new identity still lacks an explicit timeout/temperature field; either add those to the identity or validate the fixed convention explicitly as appropriate. Also bind the expected run identity rather than relying only on its directory name.

**Current M2 disposition: unresolved, still Major.** `translation_comparison()` remains the same permissive append path, now starting at line 229.

Recheck logs:

```text
/tmp/kimi-k3-independent-recheck.log
/tmp/kimi-k3-extension-selfcheck.log
```

No repository edits or live API calls were made during either review pass. Latest committed HEAD is still `7305b4943800759cbac35efe8438c2de6de3a074`; an exact committed-HEAD review is still required after fixes.

---

## Exact-HEAD re-review — 8f337a71cd2c9958a2490f3e595c21d179fc1897

**2026-09-20 verdict: REQUEST CHANGES before bulk calls. Previous M1 and M2 are resolved, but a new end-to-end blocker remains: 0 Critical, 1 Major (M3), 0 additional Minor findings.**

Resolved short HEAD `8f337a7` to **`8f337a71cd2c9958a2490f3e595c21d179fc1897`**. Reviewed all eight changed files against base `7305b4943800759cbac35efe8438c2de6de3a074`; every working file matched its committed blob. No repository edits or provider/model calls were made. The actual `validation/kimi-k3/qa-extension.json` still does not exist.

### Previous findings

**M1 resolved.** The QA identity now includes temperature, timeout and scenario; comparison binds these alongside cap, region, concurrency, omission policy, dataset, prompt/DSL/collector and model configuration, and requires the intended run ID. The mocked QA20/cache-price and negative-setting tests pass.

**M2 resolved as a source-validation defect.** Translation now has a pre-call full dataset snapshot/identity and extension receipt. Validation checks all 3,300 unique source IDs, metadata, errors and generation settings across the flat manifest and invocation history. It requires a pre-judge receipt binding the complete translation file, dataset, rubric, judge implementation and judge configuration, and complete paired raw-score judgments. Published new-report JSON must reproduce from those sources before append. Changed aggregate metrics can no longer stand in for a verified full source.

The new source checks correctly rejected independent mutations that altered **both** the top-level manifest and final execution: model ID, cache-write price, temperature omission, concurrency, retry count and reasoning effort. The complete real wrapper was also exercised with mocked collection and mocked judging, rather than only hand-built report fixtures.

### M3 — Major: actual collection prompt belongs to the explicit cohort, but append requires the original cohort

**Locations:** `bench/kimi_benchmark.py:81–104` (`extension_identity`), `140–152` (`measure_translation`), `380–386` (`append_translation`); shared collector prompt source at `bench/run.py:31–32`.

The pre-call identity and collector use the current `scenarios/translation/prompt.txt`. Its full SHA-256 is:

```text
002886c783e95ddbb6802dd9e425867a61bf2a4b3306afe513d8cb544f1c3ad8
```

That is the **explicit-instruction Grok cohort's** prompt (`002886c783e9` in historical manifests), not the original cohort's prompt (`932639fe5f75`).

However, `append_translation()` always selects `cohort == "original"` from the parent report and requires its prompt hash. It also labels Kimi as belonging to that original cohort. Thus the code's actual measurement path and intended append path cannot agree:

```text
actual current collector / frozen extension prompt: 002886c783e9
append-required original-cohort prompt:             932639fe5f75
rubric on both sides:                              d06c98b162ad
```

**Independent end-to-end reproduction:** Used the real `freeze()`, `measure_translation()`, `judge_translation()`, `build_translation_report()` and `translation_comparison()` with all I/O redirected to a temporary directory. Only provider response functions and boto3 client/session creation were mocked. The original 3,300-record snapshot, current prompt/configuration and actual collector/judge orchestration remained in use.

Results:

1. Collected all **3,300 mocked translations** through the real wrapper and validated their manifest/receipt.
2. Produced **3,300 mocked judgments**, each with two complete raw-score groups, through the real judge wrapper.
3. Verified judge-input binding and rebuilt the complete report; cache-inclusive cost was the independently expected `$1.7751`.
4. Wrote that genuine rebuilt test report under `/tmp`.
5. `translation_comparison()` passed exact rebuilding, then failed at line 386:

```text
ValueError: translation prompt/rubric differs from original cohort
```

The failure is **not** a fabricated mismatch or a stale file: it follows directly from this committed code's current prompt and the real historical parent metadata.

**Impact:** The proposed bulk command sequence can spend for all 3,300 translations and their two-judge evaluations, then fail at final append. Loosening the hash check would instead mislabel a different instruction cohort as original.

**Required correction before calls:** Make the intended translation cohort explicit and align the actual prompt builder, pre-call identity, comparison checks and cohort labels. Either execute the preserved original prompt if that is the intended experiment, or explicitly append Kimi to the explicit-instruction cohort with corresponding labels. Do not silently edit the frozen QA files or merely override a prompt hash while leaving `run.PROMPT_TEMPLATE` unchanged. Reject any selected-parent/prompt mismatch during pre-call freeze/validation, before candidate or judge calls.

Add an end-to-end regression using the actual selected prompt and existing parent metadata. The current append selfcheck manually supplies the original cohort's hash, so it bypasses the actual collector-to-append mismatch.

### Verification performed

All committed selfcheck suites passed:

```text
bench.kimi_benchmark.selfcheck()
bench.run._selfcheck()
bench.report._selfcheck()
bench.finqa.selfcheck()
bench.finqa_compare.selfcheck()
```

These establish the corrected local guards but do not override the end-to-end M3 failure.

Independent workflow checks passed through collection, source validation, judging, judge-input binding and raw report rebuilding. The unchanged collector/grade history distinction remains valid: `verify_parent()` replays the 560 old judgments with unchanged grading, without rewriting or pretending to satisfy the old transport freeze.

Evidence:

```text
/tmp/kimi-8f337a7-selfchecks.log
/tmp/kimi-8f337a7-workflow.py
/tmp/kimi-8f337a7-workflow.log
```

All measurements in that workflow are **mock fixtures**, not real Kimi results. Temporary files were removed after the test. No bulk collection, real freeze or publication occurred. The environment was the requested shared venv/cache with `uv run --offline --no-sync`; the thread-based selfcheck suite used escalation solely for the known sandbox wake-up issue.

### Exact committed file hashes

```text
428ac36f0f195865ba002b35a1b40b4fae0ba863f649d655ae015c85d1e5e34c  bench/kimi_benchmark.py
6acd0b170c08620e2d1c6b628d964c29d44747a1548e9cfe018a948db7c9e2db  bench/run.py
48733dd5d678b8e655a752ad4a7c356daaea1c32ecf454b78ab40d358c4375da  bench/report.py
e32ca14acb6f193fd65835d56cae6e12bae4b432a41b7a186856876b05fbfe77  config.toml
c095802785cf93c938c8cb08823f1953610c5d2002d97e1266b72af5899ec9cd  validation/kimi-k3/README.md
4c9bf9bdff5495d48193a35a252e74f2a6e793613f1a5d5b2918d32fd78ff7b8  validation/kimi-k3/live-check.json
1e756a21bd1a81c11dccd85a481ac8c6db42f0d055acb1a98b4d70a9f0f1207d  validation/kimi-k3/pricing-us-standard.json
3d2fcae6c43850068b88f870fec672980f4644da3583288ebd0116561148933d  CLAUDE.md
```

**Current gate:** resolve M3 and rerun the full mocked collect → judge → rebuild → append workflow at a new exact HEAD before bulk calls. The separate QA source checks passed, but the combined committed benchmark extension is not approved for the proposed bulk workflow.

---

## Exact-HEAD pre-call approval — cc1801ebdd7093f26a844d083d84c948ee564413

**2026-09-20 verdict: PASS for the pre-call gate at exact HEAD `cc1801ebdd7093f26a844d083d84c948ee564413`. All M1–M3 findings are resolved. Unresolved findings: 0 Critical, 0 Major, 0 Minor in this review scope.**

This supersedes the earlier request-changes verdicts for the committed bytes below. The reviewed workflow may proceed to freeze its extension and collect the planned **3,300 translations plus 20 QA answers**, using the explicitly selected translation cohort. This is not a final review of measurements that have not yet been collected, nor a merge/publication approval.

### M3 resolution and reused approvals

`TRANSLATION_COHORT` is now explicitly `"explicit"`. Before producing the extension identity/contract, the code checks the actual current prompt and rubric against that cohort's archived parent metadata. The extension identity includes both the selected cohort and the parent translation report hash.

The actual prompt remains unchanged:

```text
002886c783e95ddbb6802dd9e425867a61bf2a4b3306afe513d8cb544f1c3ad8
```

Confirmed that `run.PROMPT_TEMPLATE` equals the prompt-file contents, rather than relying on a substituted hash. Independently selecting `"original"` now raises before contract creation or candidate/judge calls.

Append validation, the new model's `evaluation_cohort`, its source-report cohort and the displayed explanation now agree: **27 original-instruction models plus 3 explicit-instruction models (the two Grok models and Kimi)**. The README accurately describes this selection. Existing model results and samples are retained unchanged.

The collector, cache-cost implementation, model configuration and retained pricing/live-probe evidence match the previously reviewed hashes. M1/M2 fixes remain in place; the earlier successful review of those guards is reused with fresh tests. The original 560 QA judgments still reproduce using the unchanged grader. The original transport freeze still correctly refuses the changed collector; it was not rewritten.

### Executed validation

The following passed on this exact HEAD:

```text
bench.kimi_benchmark.selfcheck()
bench.run._selfcheck()
bench.report._selfcheck()
validation/kimi-k3/workflow_selfcheck.py
```

The full workflow test uses the actual orchestration and archived dataset, with candidate/judge response functions and client creation mocked:

1. Real extension freeze/wrapper logic with temporary contract/dataset/receipt paths.
2. **3,300 mocked collection calls** and validation of full source coverage and manifest history.
3. Rejection of consistent flat-manifest/history mutations for model ID, cache-write price, temperature omission, concurrency, retries and reasoning effort.
4. **3,300 mocked judgments**, each carrying two complete raw-score groups, with a pre-judge input binding.
5. Rejection of a changed translation after the judge receipt was written.
6. Complete raw report rebuilding and exact cache-inclusive expected cost **$1.7751**.
7. Successful final append with **all 29 old model snapshots and their entries in all 210 samples unchanged**.
8. Rejection of altered published aggregate metrics through exact rebuilding.

The module selfcheck additionally passed QA20/cache-fee checks, 29-model/580-evaluation preservation, pre-call wrong-prompt rejection and negative QA binding checks.

Log:

```text
/tmp/kimi-cc1801e-recheck.log
```

All tests used the requested shared environment/cache and `uv run --offline --no-sync`. Escalation was used for the known thread/wake-up sandbox issue. No real model/provider calls or repository edits occurred. The successful 3,300-row tests are **mock fixtures**, not actual Kimi benchmark measurements. Confirmed that the real extension contract did not exist after testing.

### Exact committed hashes

All nine files changed from base `7305b4943800759cbac35efe8438c2de6de3a074` were checked against their committed blobs. HEAD remained unchanged:

```text
473ab314b59586deaa3433ed4c17f9153b8956200007919887826778fa359f88  bench/kimi_benchmark.py
6acd0b170c08620e2d1c6b628d964c29d44747a1548e9cfe018a948db7c9e2db  bench/run.py
48733dd5d678b8e655a752ad4a7c356daaea1c32ecf454b78ab40d358c4375da  bench/report.py
e32ca14acb6f193fd65835d56cae6e12bae4b432a41b7a186856876b05fbfe77  config.toml
f943a6660631ef2dd1a739a1e55c1915151452535da0aedbc08550ebe2254c85  validation/kimi-k3/README.md
efa21595fce7e64179651f066ea5c55fe75d379831158f0c6f681eaa1f266415  validation/kimi-k3/workflow_selfcheck.py
4c9bf9bdff5495d48193a35a252e74f2a6e793613f1a5d5b2918d32fd78ff7b8  validation/kimi-k3/live-check.json
1e756a21bd1a81c11dccd85a481ac8c6db42f0d055acb1a98b4d70a9f0f1207d  validation/kimi-k3/pricing-us-standard.json
3d2fcae6c43850068b88f870fec672980f4644da3583288ebd0116561148933d  CLAUDE.md
```

**Remaining delivery gate:** after actual collection, verify retained outputs, source/receipt bindings, cache token costs, grading completeness, public artifacts and the final exact PR HEAD before merge/publication. This pre-call approval does not imply those future results have already passed review.
