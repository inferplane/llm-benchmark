# TAT-QA implementation review

Date: 2026-10-27. Verdict: **no open Important or Critical blockers for the authorized paid API execution** at the file hashes below. This is backend execution clearance, not confirmation of model availability, completed benchmark results, dashboard review or publication readiness. No paid requests were made by this reviewer.

Scope: `bench/tatqa.py`, vendored evaluator and license, scenario prompt/data/provenance, model-cohort selection, dependency changes, and the added money-path assertions in `bench/report.py`. Existing provider transports and the shared cost implementation were inspected for integration behavior. The frontend is reviewed separately.

## Findings resolved before execution

| Finding | Resolution verified |
|---|---|
| Upstream treats scalar numeric zero as an absent prediction and cannot sort mixed numeric/string lists. | Adapter supplies nonempty lists of strings; zero and mixed-list cases pass. |
| Python can serialize a numeric answer as `1e-05`, which upstream incorrectly interprets as 1. | Numeric JSON values use non-exponent decimal strings; candidate string values preserve official behavior. Numeric `0.00001` no longer matches gold 1. |
| Deeply nested JSON, failed provider status and lone Unicode surrogates could escape the intended invalid/failure handling. | Recursion errors become invalid responses; noncompleted status scores zero; invalid UTF-8 string values are rejected. A surrogate response now produces a writable zero-score report row. |
| Report loading initially omitted frozen provider-runner and dependency hashes. | Loading validates the runner, lockfile, adapter, official metric/utils and both cost implementations, in addition to dataset/prompt/contract integrity. |
| Separate processes could each consume their own full parallel-model allowance. | Shared advisory OS slot locks now enforce the run-wide bound; per-model locks reject overlapping executions. |
| A late cost change converted grading truncation into a synthetic API error, dropping valid billed usage. | Removed the synthetic error. A successful transport with a truncated answer scores zero while retaining its actual token counts and cost. Genuine API errors/missing rows still withhold the complete-model estimate. |

## Verified behavior

- Prepared data contains exactly 200 unique question IDs and 200 distinct table-context IDs with quotas 86 span / 84 arithmetic / 25 multi-span / 5 count. Reversing source context order leaves selection unchanged. Dataset digest: `f2d55367f68684ffddfdac138fb22075003290fd7a8e4106e8b425fa3e238a71`.
- All 200 candidate prompts contain only the original table, paragraph text and question. Sentinel substitutions in gold/type/ID metadata do not reach any prompt. All selected gold answers round-trip correctly.
- The pinned upstream source has 1,663 successful gold round-trips with real SciPy. Vendoring changes only the metric's relative import and terminal newline; the utility and license files are unchanged. See [preflight-review.md](preflight-review.md) for source hashes and the distinction between scoring compatibility and semantic annotation accuracy.
- The frozen cohort has 35 enabled generative API models, including `gpt-6.1-terra`. Self-hosted, disabled and translation-only entries are excluded explicitly. Candidate IDs, prices and generation settings come from the configuration.
- Full-roster reporting preserves all 200 scheduled rows per model. An independent fixture containing one correct response, one invalid response, one request failure and 197 missing responses produces EM/F1 0.005, not a successful-response-only average. Retry rows deduplicate to the last observation, and models with no responses remain visible.
- Costs and timing remain model-level only. At $1/$2 per million input/output tokens, 200 responses with 100 input and 10 output tokens each cost $0.024 total and $0.00012 per question. These values also hold for billed truncated responses, with 20,000 input and 2,000 output tokens retained. Missing-response estimates are withheld. Invalid JSON does not erase successful transport usage.
- Durable offline runner checks cover pre-call freeze without requests, a failed request retried on explicit resume, successful invalid JSON cached without answer-dependent retries, append-only observations, and rejection of overlapping model execution. Truncated responses remain zero and are eligible only for an explicitly invoked resume; the authorized run is one pass.
- Changed contracts, foreign response IDs and changed frozen code are rejected. Both per-model ownership locks and shared run slots release through their context managers. A separate-process probe confirmed a busy slot could not be entered and became available after release; its subprocess-reaping step timed out in this environment, so no clean-exit claim is made for that auxiliary probe. The durable slot selfcheck passes.

## Final checks

All required checks below ran against the final reviewed adapter and report hashes and exited zero:

```text
uv run --offline python -m bench.tatqa --selfcheck
  TAT-QA selfcheck passed
uv run --offline python -m bench.report --selfcheck
  selfcheck OK
git diff --check
  no output
```

An isolated cache directory was supplied to `uv` for the review environment. Additional final direct checks confirmed the prepared dataset digest, rejected-surrogate report serialization, and the separation of zero truncation quality from preserved billed cost/tokens. Temporary fixtures were not written to published result directories.

## Reviewed hashes (SHA-256)

| File | SHA-256 |
|---|---|
| `bench/tatqa.py` | `1c4834589582189d4a286ecab058b4d19644c82b5c86457af78e63cfb382d09c` |
| `bench/report.py` | `11daa071bb058f79c7dc34f469dc6db50d0d26a989d86900beb81a5721ae2f5c` |
| `bench/run.py` | `6231e052930cf6da1fe5982fdced1d91d2bb15a829dc6be519acede5b4a7b4b3` |
| `bench/finqa_compare.py` | `8b3eeb66dcbe0347d114eb99fcc976f7f09b370eae145591bb1a119f64cdecd4` |
| `bench/vendor/tatqa/tatqa_metric.py` | `b8286fb1799164781c209fa4c2509877ebe4d256e8e0fe74e75b4b73f77ab59f` |
| `bench/vendor/tatqa/tatqa_utils.py` | `a84bb2f960737cf0a53733637a674cc4b20ef030a2be6a4b21dc2c4356f415ec` |
| `uv.lock` | `58de9e05712f779aa40b4b75899fe23d7eff8548069671337169b10923394c50` |
| `scenarios/tatqa/prompt.txt` | `4737861665df7d791ce3ee76cc9f2804805f840d74127b1e5aeae1fb7889b4c5` |

Remaining interpretation limits are disclosed by the protocol: this is a 200-question official-rule subset, table contexts are not independently verified annual reports, published-test contamination is unmeasured, reasoning settings can differ between providers, and estimates exclude failed/retried requests rather than represent complete invoices. This review did not independently validate every annotation's financial meaning or re-price the existing model roster.
