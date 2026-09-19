# FinQA presentation, verifier and retained-result review

**Scoped preliminary verdict: REQUEST CHANGES before publishing. 0 Critical, 1 Major, 2 Minor findings.**

Exact reviewed HEAD: **`0d5a4c5ed636f77163866fe6e8066225e72d1073`**, 2026-09-19, `/tmp/llm-benchmark-finqa-audited`.

Scope: `docs/finqa.js`, `docs/finqa.html`, `scenarios/finqa_audited/verify_results.py`, and retained-source handling, with direct checks of the first two GPU runs and arithmetic across all 26 retained models. The frozen evaluator and dataset semantics were not re-reviewed. `verify_freeze()` passed. No repository files were edited, no model/deployment calls were made, and no real report or verification record was published.

The working tree was clean at entry. A concurrent parent edit to `docs/finqa.html` appeared later. Browser tests used a preserved copy matching the **committed** HTML; this report does not approve that subsequent edit. Other primary reviewed file hashes remained unchanged.

## P1 — Major: verifier fails on retained Sonnet 5 p95 due to floating-point evaluation order

**Location:** `scenarios/finqa_audited/verify_results.py:92`; comparison context: frozen `bench/report.py:70–76`.

The verifier requires exact equality between the published p95 and:

```python
round(latencies[18] * .95 + latencies[19] * .05, 3)
```

For the **actual retained `claude-sonnet-5` responses**, the two relevant sorted latencies are `2.511` and `2.661`. The frozen report computes linear interpolation using `(n - 1) * p`, subtraction and addition. Its intermediate is `2.5185000000000004`, which rounds to **`2.519`**. The verifier's differently ordered arithmetic produces `2.5185`, which rounds to **`2.518`**.

This is a reproducible false failure on valid retained data, not evidence of source/report corruption. The verifier stops before it can emit its verification record.

**Reproduction:** Composed the real 26 retained models with two explicitly synthetic missing-model fixtures, entirely under `/tmp`, using the unchanged frozen composition code. The unmodified verifier failed at line 92 with the expected `AssertionError`. The failure is caused by the retained Sonnet 5 rows, not the synthetic additions. An initial independent scan of the 26 real sources found the same mismatch before any fixtures were created.

**Required correction:** Change the **unfrozen verifier**, not the frozen report/evaluator. Reproduce the frozen interpolation operation order independently from sorted raw latencies, or use a narrowly specified rounding-boundary comparison with an explicit rationale. Add the actual `[2.511, 2.661]` upper-tail case as a regression check. Avoid changing already frozen historical metrics merely to satisfy the new verifier.

An in-memory diagnostic copy that relaxed only this known assertion to a one-millisecond boundary tolerance passed every other verifier assertion on the 26-real-plus-2-synthetic fixture. That diagnostic is not an approval of the original verifier and is not a proposed repository change.

## P2 — Minor: GPU token verification trusts a stale pass record rather than recomputing its comparison

**Location:** `scenarios/finqa_audited/verify_results.py:68–72`.

The verifier checks the input-token ledger's ID set and maximum context size, then trusts `token-count-check.json` containing an empty `differences` list and the same physical row count. It does not compare `input-token-counts.json` values with the actual response `tokens_in`, enforce unique ledger rows, or bind the cached check to hashes of both inputs.

**Negative probe:** In a temporary copy, changed one Qwen ledger count to `1` while leaving its cached empty-differences record unchanged. After isolating P1 in the in-memory diagnostic verifier, verification still passed. No retained repository evidence was changed.

**Current data:** Independent direct joins by question ID found that **all 20 Llama and all 20 Qwen input counts actually match their retained responses**, with no duplicate ledger IDs. Thus this is a verifier coverage gap, not a finding of incorrect current tokens or context overflow.

**Recommendation:** Recompute the per-ID token comparison from current retained inputs in `verify_results.py`; also require exactly 20 unique ledger rows and valid integer counts. Alternatively, bind any cached comparison to verified source/ledger hashes.

## P3 — Minor: static normalization explanation applies the newer method to strict historical pilots

**Location:** committed `docs/finqa.html:122–124`.

The static explanation says JSON fences and arrays of operation strings are normalized, and strict-format correctness plus normalization counts are recorded in the detailed report. It remains visible after selecting the old single-model pilots. Those artifacts use the original strict evaluator and do not contain the newer `strict_correct` / `format_adjusted` fields.

The main new/old protocol label and method paragraph switch correctly, so this is a localized explanatory inconsistency rather than a merged leaderboard or incorrect score.

**Recommendation:** Qualify that explanation by run type or explicitly identify the strict historical pilots. The subsequent parent HTML edit was not included in this exact-HEAD finding.

## Retained-result accounting and source arithmetic

At the reviewed commit, **26 models × 20 = 520 received responses** are retained. All 520 have successful transport metadata; no physical retries or duplicate retained keys were found in those runs.

The evaluator statuses reconcile:

| Classification | Count |
| --- | ---: |
| Scored, correct or incorrect | 381 |
| Invalid program/unit | 137 |
| Capped evaluation failure | 2 |
| Missing among these 26 scheduled model sets | 0 |
| Total received | **520** |

“520 received” must not be described as “520 completed/non-truncated answers.” The two capped answers are retained Llama responses with `finish_reason="length"` and **4,096 output tokens each**. They remain in the denominator and are not missing responses or transport failures. The remaining two model sets were not yet retained at this HEAD; no claim of 560 real responses is made.

The real GPU outcomes and independent arithmetic:

| Item | Llama 3.1 8B | Qwen 3.6 27B |
| --- | ---: | ---: |
| Received / expected | 20 / 20 | 20 / 20 |
| Capped failures | 2 | 0 |
| Correct / 20 | 0 / 20 | 16 / 20 |
| Invalid program/unit | 16 | 1 |
| Scored incorrect | 2 | 3 |
| Maximum retained input tokens | 2,408 | 2,610 |
| Maximum input + 4,096 output cap | 6,504 | 6,706 |
| Frozen context limit | 8,192 | 8,192 |
| Response-window seconds | 270.867485 | 28.417079 |
| Rounded throughput, tokens/s | 34.76 | 41.67 |
| p50 seconds | 10.807 | 26.911 |
| p95 seconds | 270.616 | 27.800 |
| Audited displayed total cost | **withheld** | **$0.0447** |
| Audited displayed cost/question | **withheld** | **$0.00224** |

The raw successful-transport GPU estimate for Llama would be `$0.1224`, but the audited composition correctly suppresses it because two answers are capped. It is **not** a publishable audited cost for that model. Qwen's estimate matches independent calculation from retained timestamps, latencies, token totals and manifest hourly rate.

Direct arithmetic across the 26 real runs matched published-path configured token costs or GPU response-window cost estimates. Expired-price Sonnet 5 correctly has no estimated cost; the source fee is not silently replaced with zero. All independently checked p50 values matched. P1 is the only p95 exact-equality mismatch found.

These cost checks verify the documented configured-rate estimates, not actual provider invoices, GPU provisioning/idle spend, or effective provider reasoning defaults.

## Browser and full-pipeline fixture checks

Because the real all-28 report cannot yet be generated, copied the **26 committed source sets** to `/tmp/finqa-presentation-0d5a4c5/runs` and added synthetic fixtures only for `llama-3.3-70b` and `exaone-3.5-32b`. Used unchanged `audited.compose()` and `write_report()` with redirected results/output roots to generate a **temporary test report**. No synthetic rows entered the repository or actual experiment.

Headless Chromium served every request from intercepted local fixture files; no external network was used. Checks passed:

- 28 model rows, 14 columns; no JavaScript page errors.
- Llama displays two failures and zero missing responses; both cost cells are withheld.
- Expired-price Sonnet 5 displays withheld cost with the specific expiration diagnostic.
- Qwen displays `$0.00224` per question.
- Capped-answer diagnostic is visible when its details panel is opened.
- With two successful synthetic models, the summary correctly says **27 normally terminated models**, not 28.
- Cost sorting places both missing costs after finite costs.
- Five history entries are retained; audited versus old protocol/method labels and audit-link visibility switch correctly.
- At a 390-pixel mobile viewport, the document does not overflow horizontally; the wide metric table scrolls within its container.

The reviewed committed index still points to the old real report, as expected before actual all-28 publication. The audited report and its index update exist only in the temporary test directory. They must not be mistaken for collected final results.

## Artifacts and reproducibility

- Source/metric checks and full-fixture reproduction: `/tmp/finqa-presentation-check.py`
- Unmodified verifier failure log: `/tmp/finqa-presentation-check.log`
- Browser check: `/tmp/finqa-presentation-browser.cjs`
- Browser log: `/tmp/finqa-presentation-browser.log`
- Mobile screenshot: `/tmp/finqa-presentation-0d5a4c5/mobile.png`
- Explicitly modified **in-memory diagnostic only**: `/tmp/finqa-verifier-secondary-check.py`
- Secondary assertion/token-mutation log: `/tmp/finqa-verifier-secondary-check.log`
- All 26 source hashes, independent metrics and actual capped IDs: `/tmp/finqa-presentation-0d5a4c5/source-checks.json`

The source-check manifest's SHA-256 is:

```text
9e4ade95f260081ceed1cae348787a983360a7500524e78b02a9cc03758d17e6
```

Python checks used `UV_PROJECT_ENVIRONMENT=/home/atomoh/llm-benchmark/.venv`, `UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache`, `PYTHONDONTWRITEBYTECODE=1`, and `uv run --offline --no-sync`. Browser execution used escalation only to launch local Chromium. All generated artifacts and mutated test evidence were under `/tmp`.

## Exact reviewed SHA-256

Primary committed files:

```text
8445062b1b4b52ed2d789aa7bce3ce80ed5449d29010963e0de437ad9a8c7dcb  docs/finqa.js
ebf6ac8fdb8c43a1483c40fabf7553432282bfeda7d866cbf68cfbefaa25b36e  docs/finqa.html
af4409e902afbe6c5558bd8d83b58365c80ad68815f63949a7ba4b4acfcbced5  scenarios/finqa_audited/verify_results.py
2625b06d93e656991d6e0a9c9ae508253bced15f1fadbce2e46b751e0a263513  scenarios/finqa_audited/freeze.json
```

Llama source set, relative to `results/finqa/finqa-audited-20260919-llama-3.1-8b/`:

```text
e5f5d7bc41276ae802207e190403581907239d6327cc2a5d8e997ec973adc160  answers.jsonl
00b74c23bb700d53f01431553581615d4a28587fb05c892d7c48dceff49e75e3  manifest.json
db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6  dataset.jsonl
723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7  prompt.txt
6bca7372359c9615a91f0aca8241507def97ffff11a56965133b2699910a1a24  serving.json
212b9146f1bfa5964e51a3e904fd33857a365aa955873e69a959b30af1999f21  input-token-counts.json
1e03d0f05215a57a538c2e87ac4527e35a157f188e1ee8be5ee59f44d2a32ed8  token-count-check.json
```

Qwen source set, relative to `results/finqa/finqa-audited-20260919-qwen3.6-27b/`:

```text
1485a096534b2c80018d3e3471b2ceab60a95c209c11d76f36f4cd51d158c443  answers.jsonl
e4defe5dcebcf9567e4c8a1df2122a48dfc1bf4939a44d3a7b3140dafcdbb485  manifest.json
db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6  dataset.jsonl
723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7  prompt.txt
6ea115e6ef0a85caf86d8eea552da25e88d849503bcf6dd09d85b0bc13c0aec5  serving.json
005fb5de7ce490a566fe0712033a02b844313a0058a25665b00843655941854b  input-token-counts.json
1e03d0f05215a57a538c2e87ac4527e35a157f188e1ee8be5ee59f44d2a32ed8  token-count-check.json
```

For every retained source examined, bytes were checked against the exact commit, using the committed SHA-256 object ID for Git LFS files. The complete 26-model identity ledger is in the hashed source-check manifest.

**Publication gate:** resolve P1 in the unfrozen verifier and rerun it against the eventual **560 real responses**. Review any subsequent presentation changes and obtain the final full-HEAD review. This scoped preliminary report does not authorize publication/merge or replace that final review.

---

## Exact-HEAD re-review — 2d701c847f4be1bf293ba5a9f84cfc61350739b2

**2026-09-19 verdict: PASS for this scoped preliminary re-review. P1, P2 and P3 are resolved; zero unresolved Critical, Major or Minor findings in the reviewed changes.** This supersedes the earlier presentation/verifier verdict for the exact files below. It does **not** verify 560 real responses or approve final publication/merge.

Reviewed the committed diff from `0d5a4c5` to **`2d701c847f4be1bf293ba5a9f84cfc61350739b2`**. HEAD remained unchanged during verification. The in-progress, untracked EXAONE results directory was left untouched and excluded from this review. No repository files were edited and no model calls were made.

### Finding disposition

| Finding | Verified resolution |
| --- | --- |
| P1 — p95 false failure | The new `raw_percentile()` independently sorts source latencies and follows the frozen binary-float interpolation operation order. Both p50 and p95 use it. The actual `[2.511, 2.661]` upper-tail regression returns **2.519**. The unmodified committed verifier now passes the existing 26-real-plus-2-synthetic fixture without the earlier diagnostic tolerance or any in-memory verifier change. |
| P2 — stale token-ledger pass | Verification requires exactly 20 rows with the full expected ID set, nonnegative integer counts that exclude booleans, and a direct per-ID equality check against retained response `tokens_in`. Six mutations were rejected: changed count with stale cached pass, boolean, negative, float, appended duplicate row, and duplicate ID replacing another ID. None emitted a verification record. |
| P3 — historical method wording | The HTML now explicitly limits normalization to the multi-model comparisons and identifies the initial single-model Nova Lite pilots as strict, unnormalized historical records. Browser checks confirmed the qualification is present. |

The additional script URL change to `finqa.js?v=audited-20260919` is correctly formed and loads the intended script in the offline browser. It gives the new HTML a distinct script URL from the previously unversioned one. The 14-column rendering, cost suppression/sorting, capped/missing counts, history, method switching and mobile checks still pass. This test does not establish the state of any deployed CDN or already cached HTML.

### Executed checks and limits

- `verify_freeze()` passed; the freeze file and frozen implementation were not changed.
- Executed the **actual committed** `verify_results.verify()` against the existing temporary 26-real-plus-2-synthetic completion fixture. All assertions passed, including the retained Sonnet 5 p95, two capped Llama responses, expired Sonnet pricing, Qwen cost and serving/token evidence.
- Redirected the successful verification write to `/tmp/finqa-presentation-2d701c8/fixture-verification.json`. No real `result-verification.json` or final report was written.
- All six token-ledger negative checks failed as intended; the temporary ledger was restored in `finally`.
- Headless Chromium used intercepted local files only, including the new HTML and unchanged JS from this commit. It passed the existing presentation checks plus explicit assertions for the versioned script URL and historical-pilot wording.

Logs:

```text
/tmp/finqa-2d701c8-verifier.log
/tmp/finqa-2d701c8-browser.log
```

Browser test source and screenshot:

```text
/tmp/finqa-2d701c8-browser.cjs
/tmp/finqa-presentation-2d701c8/mobile.png
```

**Fixture warning:** the verifier's console prints its standard “all28 / 560 received responses” message, but this invocation still used **26 real source sets plus 2 synthetic test sets**. It is a verifier regression test, not evidence that the real final run is complete. Neither ongoing EXAONE results nor the subsequent final GPU results were substituted into this fixture.

### Exact re-reviewed SHA-256

Each hash was checked against both the working file and the exact committed blob:

```text
dea37b93985f4e25cbdb54fb8354cb089689d36b673b26e4de75b3cf796baa90  docs/finqa.html
8445062b1b4b52ed2d789aa7bce3ce80ed5449d29010963e0de437ad9a8c7dcb  docs/finqa.js
4f93acee2c9441358cb332fe005b46f36701f9841581ba1807ef6a2c285554b5  scenarios/finqa_audited/verify_results.py
2625b06d93e656991d6e0a9c9ae508253bced15f1fadbce2e46b751e0a263513  scenarios/finqa_audited/freeze.json
```

**Outstanding final gate:** generate the report from all **560 real retained responses**, run the corrected verifier on those real sources, and obtain the final full-HEAD review before publication/merge. This scoped PASS does not waive that gate.
