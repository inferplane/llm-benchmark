# TAT-QA preflight review

Date: 2026-10-27. Status: source/design checks passed; subsequent backend execution review passed at the hashes in [code-review.md](code-review.md). No model API requests were made for this review.

## Verified source and cohort

- Pinned upstream revision: `870accc41953dcde885aabeb963d94aabdc0fbc3` at [NExTplusplus/TAT-QA](https://github.com/NExTplusplus/TAT-QA/tree/870accc41953dcde885aabeb963d94aabdc0fbc3).
- Released test gold contains 1,663 questions across 277 distinct table UIDs. Table contents are also unique across those 277 contexts. Table UIDs do **not** establish distinct annual-report documents; describe the selected sample as **200 distinct table contexts**.
- Answer-type counts: 714 span, 699 arithmetic, 210 multi-span, 40 count. Proposed quotas of 86, 84, 25 and 5 preserve their approximate proportions in a 200-question sample.
- Current configuration selects 35 enabled generative API models: 24 Bedrock and 11 Mantle. Models with `base_url`, disabled models and translation-only services are excluded. This count includes `gpt-6.1-terra`.
- The existing Sonnet 5 configuration records a 2026-10-11 pricing recheck and cancellation of its previously planned increase. No selected model currently has an explicit `pricing_valid_until` field. This review verified those configuration facts; it did not independently re-price the models.

## Executable evaluator evidence

Using Python 3.12.13 and real SciPy 1.18.1, all **1,663** source gold answers were extracted by upstream `extract_gold_answers`, converted to nonempty lists of strings, and scored against their own annotations through upstream `TaTQAEmAndF1`: **1,663 EM=1 / F1=1; zero failures or exceptions**. This establishes compatible annotation formats and scoring mechanics, **not semantic correctness of each financial answer**.

Additional upstream probes confirmed:

| Case | EM / F1 | Implication |
|---|---|---|
| Scalar numeric `0` against gold zero | 0 / 0 | Upstream truthiness check treats scalar zero as missing. |
| `["0"]` against gold zero | 1 / 1 | Adapter must use nonempty string lists. |
| `23.42` with percent scale, `0.2342` without scale, or `23.42%` | 1 / 1 each | Preserve official percentage behavior. |
| Reversed `["beta", "alpha"]` against `["alpha", "beta"]` | 1 / 1 | Preserve official ordering normalization. |
| Joined `["alpha beta"]` against `["alpha", "beta"]` | 1 / 1 | Official scorer joins sorted spans; do not impose stricter span boundaries. |
| Mixed `["alpha", 2]` passed directly | TypeError | Stringify individual values before upstream sorting. |
| `["1e-05"]` against gold `1` | 1 / 1 | Upstream numeric parser does not preserve exponent notation. |
| `["0.00001"]` against gold `1` | 0 / 0 | Serialize JSON numeric values in decimal notation before passing strings to upstream. |
| `1.23456` against gold `1.23` | 1 / 1 | Official arithmetic rounding is intentional. |

## Corrections communicated before calls

1. Pass scalar/list values as a nonempty string list, preserving zero and mixed-list support. Convert numeric JSON values to non-exponent decimal text so Python's float formatting cannot turn `0.00001` into upstream's erroneous `1e-05` interpretation. Preserve supplied string answers under the documented official normalization policy.
2. Reject malformed JSON, duplicate keys, nonfinite values, booleans, nulls, nested answer structures and empty answers. Catch decoder recursion errors so one deeply nested response cannot abort the complete report. All invalid responses remain zero in the full denominator.
3. Treat every response status other than `completed` as a failed/nonterminal response; retain truncation separately.
4. Freeze source/data/prompt, scorer/adapter/provider-runner, cost implementation and dependency hashes, along with the complete roster, generation settings, concurrency and historical prices. Resume must reject changed contracts. Report all frozen model/question pairs, including absent rows; withhold incomplete cost estimates.

Implementation of these corrections and the complete dataset/run/report flow was subsequently reviewed in [code-review.md](code-review.md). Use that hash-bound review for backend execution clearance; publication still requires actual-result and presentation checks.

## Source hashes (SHA-256)

| File | SHA-256 |
|---|---|
| Released test gold | `c4d08418359c1d76468dec420ee748a37f48c06b63cb8ec2766f19d5d314b597` |
| Upstream `tatqa_metric.py` | `2aeeac479f89f8c76300af1cc0e8d098eb86af84bc386b38b6ab4af484a6dea8` |
| Upstream `tatqa_utils.py` | `a84bb2f960737cf0a53733637a674cc4b20ef030a2be6a4b21dc2c4356f415ec` |
| Upstream evaluator license | `46e27ffbc49c3fd44a9595c2213f8a5f4319a81b53238e49ce1eec39e7e25662` |
