# Kimi first-attempt observation reporter — independent review

**Verdict: PASS for recording this reporting policy and judging usable outputs once the collector has finished and all 3,300 actual first attempts validate.**

**Findings: 0 Critical, 0 Major, 0 Minor in the reviewed working-file scope.** Zero model failures is **not** a completion requirement. The required population is all 3,300 actual first attempts, with paired judgments for usable returned outputs and explicit failure/cap/quality-coverage accounting.

Date: 2026-09-20. Worktree: `/home/atomoh/llm-benchmark/.worktrees/kimi-k3`.
Committed HEAD at review: `c8a96d055bd07a2e2caf1e7107a0c42ed5f481d3`.
This approval binds the **working-file hashes below**, including the new reporter/policy/tests. It is not a final exact-HEAD review of subsequently generated results.

No repository code edits, provider/model calls, real policy creation, real judging or publication were performed by this reviewer.

## Reviewed behavior

`bench/kimi_observed.py` faithfully handles legitimate unsuccessful collection outcomes without changing the generator or grader:

- Requires the original valid extension contract, frozen 3,300-record dataset identity, pre-call receipt and exactly one completed collector invocation.
- Checks actual manifest input/generation/model settings and consistency with the execution record.
- Requires exactly 3,300 physical rows and 3,300 expected unique `(model, input)` keys, each recorded as collector attempt 1. Missing, duplicate, unexpected or regenerated rows are rejected.
- Preserves failed rows with retained diagnostics. Successful rows must have valid nonempty text and valid token classes.
- Records a separate policy identity containing the original contract hash, full translation-file hash, dataset/rubric/judge identity, model and new reporter hash.
- Explicitly states that this policy was chosen **after observing collection outcomes and before judging**, rather than claiming original preregistration.
- Refuses initial policy creation if judgments already exist. Once recorded, changed source text or reporting policy invalidates the binding.
- Uses the unchanged judge orchestration, two judges and rubric for nonempty returned outputs, **including capped text**. Empty/invalid unreturned outputs do not receive invented judgments.
- Requires the final judgment key set to equal the returned-output key set exactly, with two valid raw-score groups and no unresolved judgment failures.
- Reports all-input attempt counts, returned/unreturned counts, cap totals split by text availability, failure types, zero regenerated collector attempts and all-input quality coverage.
- Preserves the historical 29 models and their sample entries unchanged when appending the observed Kimi result.

The existing success-only `kimi_benchmark` publication guard remains unchanged and continues to reject failed outputs. The separate reporter is an explicit accounting-policy extension, not an attempt to conceal that guard's failure or regenerate bad model answers.

## Denominators, caps and costs

The report retains all 3,300 attempts in collection statistics. Quality statistics are explicitly conditional on the returned outputs eligible for the unchanged two-judge evaluation; they are not presented as an all-input success score.

Failed/unreturned and capped categories can overlap. The implementation counts a blank capped response in both categories, while a nonempty capped response is retained for judging. `capped_with_text` and `capped_without_text` reconcile with the total caps.

Costs use ordinary input/output plus cache-read/write token classes from successfully returned text only. Nonempty capped responses remain in that estimate. Empty/invalid failed-call fees are not invented from incomplete retained cache usage. The interpretation and policy explicitly say this is **not a total experiment bill**.

The shared per-segment cost consequently divides that returned-output estimate by the returned population, consistent with the unchanged report implementation. The new diagnostics additionally expose the full scheduled population and quality coverage.

The revised `validation/kimi-k3/final_check.py` now rebuilds translation results with `kimi_observed.comparison()` and independently sums costs only over usable output rows. It no longer incorrectly requires every translation attempt to succeed. QA retains its separate original checks.

## Independent offline workflow

Ran the actual collection/report/judging orchestration in temporary fixtures with provider functions and boto3 client/session construction mocked. No live API was called.

The fixture deliberately contains:

| Outcome | Count |
| --- | ---: |
| Ordinary returned outputs | 3,297 |
| Nonempty capped output | 1 |
| Empty non-capped failure | 1 |
| Empty capped failure | 1 |
| All first attempts | **3,300** |

Verified outcomes:

- Collection returns a nonzero failure result while still retaining all **3,300 completed first attempts**.
- The original success-only guard rejects this population; the observation validator correctly accepts it.
- Exactly **3,298 paired judgments** are produced. The nonempty capped text is included; neither empty failure is judged.
- Aggregate segments remain 3,300; translation failures are 2; successful/judged/quality-eligible counts are all 3,298.
- Diagnostics show 2 capped outputs, split 1 with text / 1 without text, and quality coverage `3298 / 3300`.
- Independent decimal arithmetic gives **$1.8412482**, displayed as **$1.8412**, excluding the two failed rows and including the visible capped output.
- Full report rebuilding and append succeed, preserving all old 29 model objects and their entries in all 210 displayed samples.
- Missing input coverage, a duplicate row replacing another input, a second-attempt marker, an invented judgment for a failed output, and changed source text after policy/judging are all rejected.
- Policy recording occurs after the fixture collector's finish time and before judgments exist.

Also ran the parent's complete `validation/kimi-k3/observed_selfcheck.py`; it passed the 3,300-attempt / 3,298-judgment / failure-cap-cost-preservation checks and source-mutation rejection.

Evidence:

```text
/tmp/kimi-observed-independent.py
/tmp/kimi-observed-independent.log
/tmp/kimi-observed-parent-selfcheck.log
```

The first test attempt reached correct coverage/cost results but encountered `/tmp` filesystem exhaustion while copying a parent report. That was an environmental failure. Both complete tests were subsequently rerun successfully with temporary fixture storage beneath the existing UV cache:

```text
/home/atomoh/llm-benchmark/.worktrees/.uv-cache/kimi-observed-review-tmp
```

Those temporary fixtures were cleaned up. No original data or repository code was altered. Python execution used the requested shared venv/cache, `PYTHONDONTWRITEBYTECODE=1` and `uv run --offline --no-sync`.

## Actual-data observation and scope limits

A read-only snapshot during review contained **3,235 unique first attempts**, 10 invalid/empty responses and 40 cap terminations. Some blank failures ended with `end_turn`; others ended with `max_tokens`. This confirms why failure count and cap count must remain distinct.

**Those are interim counts, not final benchmark totals.** Collection was still running. At the last actual-state check there was no completed collection manifest, no actual judgment file and no recorded observation policy. The reporter appropriately requires completed 3,300-row collection before permitting policy establishment.

`kimi_benchmark.verify_contract()` continued to pass. Collector, original Kimi extension module, cost code and judge code remained unchanged. The original frozen grader/dataset are not redefined or rescored by this reporting change. Previously approved generation/grading logic was reused as regression context rather than independently redesigned.

The parent refined the reporter's interpretation wording during review. The final workflow tests and approval use the final reporter hash `8c197e…` below, not the initially read `7c09a4…` snapshot.

## Exact reviewed SHA-256

New/updated reporting and validation files:

```text
8c197efe0a8332c3c0a8b4b94942189000542c4df076b98d92ea1e35fc5c077a  bench/kimi_observed.py
520e18e91ebbcafd6ba0190d7b42d4b1e850500dcaabe55ad3c557df98e9e24c  validation/kimi-k3/observation-policy.md
1cf60ca90bbdb466c4dc87eea989acfe524b69a82102e9d3e4a5f92d4cf376bf  validation/kimi-k3/observed_selfcheck.py
8d7e20bc7bfc4b52079e9ed3377e98023dfdd8444efbe207393e95aac2640344  validation/kimi-k3/final_check.py
```

Unchanged supporting code and original pre-call contract:

```text
473ab314b59586deaa3433ed4c17f9153b8956200007919887826778fa359f88  bench/kimi_benchmark.py
6acd0b170c08620e2d1c6b628d964c29d44747a1548e9cfe018a948db7c9e2db  bench/run.py
48733dd5d678b8e655a752ad4a7c356daaea1c32ecf454b78ab40d358c4375da  bench/report.py
9b1d479ae002f729b830c9e8a56f72575d94c9c36d867f1e1c0aaad31350c8b9  bench/judge.py
f30c8b5995ad42bc3a7b51405bcab046fb43f000f03c4151fdca710765ae3912  validation/kimi-k3/qa-extension.json
```

**Next gate:** finish collection without regenerating failed/capped observations; let the validator establish exactly 3,300 first attempts; record this reviewed policy before judging; judge all usable returned outputs with the original pair/rubric. Final real counts, costs, reports, public presentation and committed exact HEAD still require verification before publication/merge.

---

## Exact committed pre-judge review — 25297b5fc96500b281cfd8f57631376526148791

**2026-09-20 verdict: PASS. The pre-judge gate is cleared at exact HEAD `25297b5fc96500b281cfd8f57631376526148791`: 0 Critical, 0 Major, 0 Minor findings.**

The real terminal collection has now been validated. Proceed by recording the reviewed post-collection policy, then judging the **3,286 usable returned outputs**, including the 38 nonempty capped outputs, with the unchanged judge pair and rubric. The 14 empty/invalid outputs remain unjudged translation failures. No regeneration, cap change or requirement that every model response succeed is introduced.

### Committed scope and approval reuse

Reviewed all seven changed files against preceding HEAD `c8a96d055bd07a2e2caf1e7107a0c42ed5f481d3`. Their working bytes match commit `25297b5…`.

The observer, policy document, failure/cap selfcheck and adapted final checker exactly match the hashes approved in the preceding working-file review. Reused that review and its independent full-workflow tests. Newly inspected the committed dashboard changes and README integration. The collector, original Kimi extension, prompts, grader, cost code and original contract remain unchanged; original-contract verification passes.

No real policy was established, no judge/provider APIs were invoked, and no repository code or source data was edited by this review.

### Actual completed collection

Ran the committed observer's `validate()` against the actual retained files, without writing anything:

| Population | Verified count |
| --- | ---: |
| Physical first-attempt rows | **3,300** |
| Unique expected `(model, input)` keys | **3,300** |
| Usable nonempty returned outputs | **3,286** |
| Empty/invalid unreturned outputs | **14** |
| Explicit cap terminations | **40** |
| Capped with usable text | **38** |
| Capped without returned text | **2** |
| Recorded attempt numbers other than 1 | **0** |

All 14 failures carry `InvalidResponseError` diagnostics. The two blank capped outcomes are included in both the 14 unreturned and 40 capped counts; they are not 54 distinct failed inputs. The remaining capped outputs are retained for ordinary paired quality evaluation.

The validator also confirms the completed single collector invocation, full dataset identity, receipt, model/generation/pricing settings, row metadata and chronology. At the actual-state check, **neither `judgments.jsonl` nor `observation-policy.json` existed**, consistent with the requested pre-judge gate.

Actual retained identities at review:

```text
5eda0b9f1aba12238d79e5eeba2baf45e5ac2fef1429bcaee0e2b0957e54e180  results/bedrock-kimi-k3-20260920/translations.jsonl
e69342c6dcf3ad3b80b5a7db4a5a8dbc17cdf0fec9a6a376e6c47efd87f382a4  results/bedrock-kimi-k3-20260920/manifest.json
```

These are source-verification results, not quality scores or final published-cost approval.

### Tests and UI/policy checks

Reran the committed `validation/kimi-k3/observed_selfcheck.py` successfully. It exercises 3,300 mocked first attempts with two empty failures and two capped outcomes (one overlapping), produces exactly 3,298 paired judgments, verifies the full-population diagnostics and **$1.8412** returned-output estimate, preserves all old 29 models, and rejects changed/missing source observations.

The earlier independent tests remain applicable by exact reporter hash, including rejection of duplicate/regenerated attempts and fabricated judgments for empty failures.

Executed the committed `renderModelTable()` function in an isolated DOM test with the real collection counts. It renders:

```text
전체 입력 3,300건 · 출력 미반환 14건 · 상한 도달 40건 (중복 가능)
```

The historical-model normal-state rendering is unchanged. Confirmed that `docs/index.html` loads the versioned `app.js?v=kimi-k3-20260920` URL. This was a focused rendering test of the changed labels, not a browser review of ungenerated final judgment results.

The policy document explicitly distinguishes post-collection/pre-judge reporting from original preregistration, conditional quality statistics from all-input success, and returned-output fee estimates from total failed-call billing. The adapted final checker uses `kimi_observed.comparison()` and returned-output fee arithmetic; it does not reimpose the obsolete all-success translation requirement.

Logs:

```text
/tmp/kimi-observed-25297b5-actual.log
/tmp/kimi-observed-25297b5-selfcheck.log
/tmp/kimi-observed-25297b5-ui.log
```

Temporary fixture storage used the existing UV-cache scratch directory because `/tmp` remains nearly full. Fixtures were isolated from real results and removed afterward.

### Exact committed hashes

```text
8c197efe0a8332c3c0a8b4b94942189000542c4df076b98d92ea1e35fc5c077a  bench/kimi_observed.py
373fe255ce42c28271251ac74dda051e118f792351cb9941b620fb00015d1ea5  docs/app.js
3c5cd31ea5e1962642120145c5e7264e19933dabcf73351a49bd1635038afb33  docs/index.html
fb52fef954d1a06111d5a177d7316447b761507ffcaeca21f85ff632bdef1801  validation/kimi-k3/README.md
8d7e20bc7bfc4b52079e9ed3377e98023dfdd8444efbe207393e95aac2640344  validation/kimi-k3/final_check.py
520e18e91ebbcafd6ba0190d7b42d4b1e850500dcaabe55ad3c557df98e9e24c  validation/kimi-k3/observation-policy.md
1cf60ca90bbdb466c4dc87eea989acfe524b69a82102e9d3e4a5f92d4cf376bf  validation/kimi-k3/observed_selfcheck.py
```

**Remaining final gate:** after paired judging, require exact coverage of the 3,286 usable outputs, preserved 3,300 first attempts, explicit failure/cap coverage, correct returned-output fee arithmetic and reproducible public artifacts. Review the final measured-result HEAD before merge/publication. This approval clears actual judging under the reviewed policy; it does not claim that future judgment outputs have already passed verification.
