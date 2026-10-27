# GPT-6.1 Terra benchmark addition

Measured on 2026-10-27 using the caller's AWS credentials and
`openai.gpt-6.1-terra` through the us-east-1 Bedrock Mantle Responses endpoint.
The live preflight confirmed that `temperature=0` is rejected; requests omit
temperature and explicitly use reasoning `low`. No OpenAI API key is used.

## Sources and frozen conditions

- [AWS model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-terra.html)
  and [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra).
  Saved copies and hashes are in `pricing.json`; `config.toml` remains the only
  runtime source of model IDs and rates.
- Standard In-Region short-context rates, USD per million tokens: fresh input
  1.10, output 5.50, cache read 0.055, cache write 1.375. Regional fee included.
- Korean translation: the unchanged 3,300-segment snapshot from
  `grok-explicit-2026-09-16`, 30 directions, 100 FLORES plus 10 synthetic
  segments per direction. The existing explicit prompt and sol/fable-5 judges
  are retained. `contract.json` binds code, data, rates and generation settings.
- English translation: the unchanged 3,080-segment English-pivot set, 28
  directions, 100 FLORES plus 10 synthetic segments per direction.
  `en-pivot-contract.json` binds its original dataset order and settings.
  sol/fable-5 and astra/fable-5.1 independently grade the **same** candidate
  responses, not two candidate generations. The latter remains the dashboard
  default judge cohort.
- Both translation jobs use concurrency 8, output cap 4,096 and one candidate
  attempt per segment. Judge concurrency is 32. Successful cached grades are
  retained if a judge-only retry is needed.
- Financial QA uses the existing 20 audited financial questions, original
  prompt and exact arithmetic grader, concurrency 2 and cap 4,096. This is the
  existing small audited set, not a full official FinQA dataset evaluation.
- WHOAMI and Lotte Tower use the original task prompts, output cap 16,384,
  direct model generation and unchanged generated HTML. Original source hashes
  are bound to generation records, published provenance and review evidence.

The English helper's archived precollection file is `en-pivot-frozen.py`.
Additional report-time drift assertions were added after collection started;
an AST comparison proves all collection and grading functions unchanged.

## Financial QA and artwork

Financial QA: **19/20 (95%)**, all responses completed, no truncation or output
repair. Independent Fraction arithmetic replays all 20 programs. Exact
candidate inference cost is **$0.054719500**, excluding preflight and review
calls. The one incorrect question is
`finqa-dev-SWKS/2006/page_81.pdf-1`.

Content gate: WHOAMI **98.5/100**, Lotte Tower **97.5/100**, both PASS with no
critical findings. Lotte Tower includes working 3D, four construction stages,
plan/elevation/section drawings, pointer/keyboard/touch controls and attribution.
The original generated pages retain their small-text/diagram-contrast warnings;
see `content-review.md` and `content-review.json` for exact findings.

Historical model results and example data are retained verbatim when composing
the new comparisons. `tools/model_pages.py --models gpt-6.1-terra` refreshes only
the new model's routes and the shared catalog; all other model pages and alias
records are preserved. `code-review.md` records independent review evidence.

## Translation collection

All **6,380 translations succeeded**: Korean 3,300/3,300, English 3,080/3,080.
Exact candidate inference costs are **$2.835875350** and **$2.318696050**,
respectively (**$5.154571400** combined). These costs exclude judge/preflight
calls and the separate financial/artwork tasks. There were no failed candidate
calls and no additional candidate attempts.

The first Korean judge process exited with code 143 after saving 3,280 grades.
The same judge configuration resumed the remaining 20, preserving all completed
grades. No candidate response was regenerated. Any usage not returned by
interrupted evaluator calls is unknown and excluded from the judge cost
estimate. English sol/fable-5 also had an evaluator response JSON parsing
failure; its failed row is retained and only its grade is retried under the same
conditions. `grading_diagnostics` records the final evaluation attempt count.

## Completed translation scores

| Population and judge cohort | Segments | Overall mean / 5 | Synthetic financial mean / 5 | Successful-pair judge cost estimate |
| --- | ---: | ---: | ---: | ---: |
| Korean, sol/fable-5 | 3,300 | 4.909 | 4.883 | $67.8263 |
| English, sol/fable-5 | 3,080 | 4.933 | 4.957 | $52.1575 |
| English, astra/fable-5.1 (dashboard default) | 3,080 | 4.948 | 4.943 | $55.5450 |

All rows are fully graded with zero remaining translation/judge failures and
zero pending grades. English responses are counted in each judge cohort but
were generated only once. Combined successful-pair judge cost estimate is
**$175.5288**, separate from the $5.154571400 candidate translation cost;
unreturned evaluator usage is excluded. These are Terra addition costs, not
the historical comparison reports' cumulative costs.

The new comparisons contain 33 Korean models, 40 English models and 32 financial
QA models. The model catalog contains 40 entries. All prior model results,
samples/evaluations and nonselected model/task page bytes remain unchanged.
`final-verification.json` records independent exact cost/coverage/arithmetic,
source hash, scheduling and artwork provenance assertions.
`delivery-review.json` and `delivery-review.md` record the completed browser
review: seven routes, all six new translation selectors, both sample tracks,
correct dashboard defaults and the timing disclosure at desktop/tablet/phone
widths. No console errors, blocked requests or horizontal overflow were found.
The timing note is accessible in the existing, initially collapsed measurement
disclosure. Original-artwork accessibility warnings remain documented above.

## Performance interpretation

The Korean and English candidate collection intervals partly overlap, and
financial QA/artwork generation also ran during Korean collection. Each
translation job uses concurrency 8, but combined load on the same model service
is higher during overlap. Reported latency/throughput are observed values with
this limitation, not an isolated load comparison. `scheduling.json` records the
actual intervals and overlap, also disclosed in the new dashboard reports.
The translation collection overlap is 283.236593 seconds, derived from the
completed execution manifests rather than guessed from response timestamps.

Inference costs include separately priced fresh input, output, cache read and
cache write usage. Judge costs are separate. They are measured-usage estimates,
not the whole experiment's AWS bill. Historical models were measured on other
dates and retain their original prompt and judge cohorts.

## Offline reproduction of reports and verification

Candidate responses already exist: **do not rerun `run-translation`, `run-qa`
or the English `run` command**. No dataset regeneration or candidate answer
revision is needed. To rebuild the reports from these frozen responses:

```bash
export UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache
uv run python -m bench.terra_benchmark report-translation
uv run python -m bench.terra_benchmark report-qa
uv run python validation/gpt-6.1-terra/en_pivot.py report
uv run python validation/gpt-6.1-terra/en_pivot.py report2
uv run python validation/gpt-6.1-terra/finalize_reports.py
uv run python tools/model_pages.py --models gpt-6.1-terra --lotte-review validation/model-tasks/lotte-review.json
uv run python -m bench.report --selfcheck
uv run python validation/gpt-6.1-terra/en_pivot.py verify
uv run python validation/gpt-6.1-terra/verify_results.py
git diff --check
```

The full runner selfcheck also passed (`run-selfcheck.log`). It needs a working
thread-notification environment; this sandbox hangs at `asyncio.to_thread`
completion, so that selfcheck was run outside the sandbox with no model API
calls. Browser checks use offline local assets and explicitly cached CDN files.
Deployment uses the existing GitHub Pages configuration: `main`, `/docs`.
The reviewed dashboard, reports and model routes are published together;
historical measurements and generated originals stay unchanged.

## Deployment routes

- [Translation dashboard](https://inferplane.github.io/llm-benchmark/)
- [Financial QA](https://inferplane.github.io/llm-benchmark/finqa.html)
- [Terra WHOAMI](https://inferplane.github.io/llm-benchmark/models/gpt-6.1-terra/whoami/)
- [Terra Lotte Tower](https://inferplane.github.io/llm-benchmark/models/gpt-6.1-terra/lotte-tower/)

The content gate and delivery review are PASS. Deployment verification checks
the GitHub Pages build commit and live response hashes against the reviewed
local assets, including both original artwork hashes and the new report
indexes. Raw JSONL caches use Git LFS; `docs/results/*.json` remain ordinary
Git files because GitHub Pages does not resolve LFS pointers.
