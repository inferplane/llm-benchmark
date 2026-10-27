# GPT-6.1 Terra addition — independent code review

Reviewed 2026-10-27 against the uncommitted addition. Scope: model configuration, request/cache accounting, frozen translation and financial-QA extension, and recorded self-introduction/Lotte Tower collection. No live API calls or dataset regeneration were performed.

## Findings

- Critical: none.
- Important: none.
- Minor: none remaining. The first review found that `preflight.py` would omit temperature in both cases after adding Terra to `MANTLE_NO_TEMPERATURE`. The updated script now explicitly removes Terra for the temperature-zero case and adds it for the omitted case. Saved live evidence was already valid; no repeated provider calls were needed.

## Evidence

- The preserved AWS official model-card HTML matches the SHA-256 in `pricing.json`. Its Programmatic Access table specifies `openai.gpt-6.1-terra` on `bedrock-mantle`, and its short-context In-Region pricing table specifies $1.10 ordinary input, $1.375 cache write, $0.055 cache read, and $5.50 output per million tokens, with the regional fee included. `config.toml` matches these values.
- `preflight.json` records a provider 400 for explicit temperature and a completed response from the exact Terra ID with reported reasoning effort `low`. `bench/run.py` omits temperature for Terra and uses the existing Responses inclusive-to-disjoint usage conversion. The offline scoped `_selfcheck_mantle()` passed, exercising ordinary input/cache read/cache write separation and omitted-temperature payloads for Terra.
- `bench.report --selfcheck` passed. Its new hand-computed Terra cost assertion is $1.551 for 400K ordinary input, 200K cache read, 400K cache write, and 100K output tokens; no old model or judge accounting path changes.
- Every file hash in the pre-call contract matched at review. `bench.terra_benchmark verify` passed, including reproduction of the original 560 financial-QA judgments. The translation dataset is copied from the retained 3,300-segment dataset; the QA extension uses the original frozen 20 questions and evaluator. The original translation prompt, rubric, and integrated report remain identical to HEAD.
- The completed QA collection contains 20 successful first-attempt rows from the exact Terra ID, all with reported effort `low`. The read-only `qa_report()` builder passed its preservation assertions: 32 models and 640 evaluations, with all prior 31 model snapshots and 620 evaluations retained. Terra has 19/20 correct, 34,672 separately accounted cache-write tokens, and $0.0547 estimated cost.
- Translation collection was still in progress during review. The sampled on-disk rows were successful first attempts from the exact Terra ID with effort `low`; full report/judgment completeness is deliberately enforced by the extension's later assertions. Translation comparison copies all prior model snapshots and only appends Terra; historical judge configuration is frozen and unchanged.
- Self-introduction and Lotte Tower each have one preserved generation attempt, completed provider responses from the exact Terra ID, `temperature_sent: false`, reported effort `low`, and the unchanged artwork cap of 16,384 tokens. The tracked Lotte Tower manifest change only appends Terra's identity.

## Assessment

No blocking issue in the reviewed addition. Full translation completion, final publication wiring, and rendered content review remain separate completion checks; this code review does not claim they have finished.

## English-pivot extension review

Additional scope: frozen `validation/gpt-6.1-terra/en_pivot.py`, reviewed during candidate collection.

### Findings

- Critical: none.
- Important: none remaining. The first review found that `compose()` did not revalidate the saved judgment-input binding or alternate cloned inputs before publication. The updated reporting function checks the current translation SHA, contract SHA, selected frozen judges, and `candidate_regenerated: false` in both branches; judge2 additionally compares cloned translation/dataset SHA and its exact intended manifest against the retained source. No actual response drift was observed.
- Minor: none.

### Evidence and limits

- Independent `verify()` passed. The 3,080-input dataset digest is `530c6af4e0b59ae9115a761c140f29979812768e7e760d041b6f5dc45c56768c`, exactly the parent digest. Both parent reports and all four original dataset files are included in the frozen file hashes. The original prompt and rubric hashes match the parent report.
- Candidate collection is one run; `measure()` rejects a second manifest. `grade(True)` copies retained translations and the dataset and selects `astra-fable51`; `grade(False)` selects the original `sol`/`fable-5` judges. The frozen source responses are not regenerated to obtain another judge opinion.
- The cloned alternate manifest explicitly records `collection_source_run_id` and retains the original candidate execution identity, settings, timestamps, and costs. Its alternate judge IDs are applied to the top level and execution snapshots. The source manifest itself is not changed.
- Offline composition fixtures exercised both reporting branches with provider calls and writes mocked out. Both produced 40 models and 196 samples, retaining all 39 historical model records and every historical `by_model` sample value unchanged. `judge_cost.judges` is a list in `compute_judge_cost` and both parents, so list concatenation is type/schema-compatible. The summed total and separately retained `source_estimates` are valid; concatenated per-source judge entries retain their original values.
- Both historical `source_runs` entries/manifests are copied and retained, with Terra's source appended; `source_compatibility` rechecks dataset/prompt/rubric hashes. No composite candidate wall clock is invented. Model-level performance/cost remains in the preserved model aggregates.
- `docs/app.js` sorts reports by run ID and selects the last `default: true` report. The new `en-pivot-20261027-judge2` composite is flagged true and sorts after the previous default; the other new English-pivot reports are not flagged. Existing no-store fetch behavior remains intact.
- The composition fixtures validate assembly and schema, not measured completion. Full English-pivot collection, judgment completeness, and final published report checks remain pending at this review point.
- Follow-up offline fixtures passed the corrected reporting functions and rejected changed translations and judgment bindings in both branches before report construction/publication. The alternate branch also rejected changed cloned datasets and manifests. Historical model/sample preservation still passed.
- The original frozen module is retained in `en-pivot-frozen.py` with its recorded hash. Independent `verify()` passed the AST comparison showing every module node outside the reviewed `identity()`/`compose()` changes (and the added `ast` import) is unchanged. Collection, request settings, dataset selection, grading, and candidate-generation code remain identical to the archive.
- Reviewed the new read-only `verify_results.py` and independently ran `--qa-only`: its Fraction-based program arithmetic reproduced 19/20 judgments, its Decimal billing calculation produced exactly `$0.054719500`, and all prior QA models/evaluations matched their retained parent. Its full translation/artwork checks appropriately await final artifacts.

## Selective model-page refresh review

Additional scope: `tools/model_pages.py --models`.

### Findings

- Critical: none.
- Important: none remaining. The initial empty-selector fallback issue is fixed: omitted selection uses full generation; explicit blank/whitespace or any empty comma-separated name is rejected before writes.
- Minor: none remaining. Required retained model/alias records are now checked before generation, and unselected aliases reuse their retained records without calling the alias writer.

### Evidence

- The real catalog has 40 entries; all 39 historical entries exactly match HEAD. Among tracked `docs/models` files, only `catalog.json` and the shared `index.html` currently differ, with Terra appended.
- Temporary offline CLI fixtures verified normal selection refreshes only the selected nonalias model, and no selector retains the existing full-generation behavior.
- Unknown model names exit with parser status 2 before any page calls. The empty-selector, partial-mutation, and unselected-alias findings above were reproduced with mocked collectors and temporary output directories; published pages were not changed by this review.
- Follow-up temporary fixtures passed all fixes: blank, whitespace-only, trailing-comma, unknown-name, missing-later-model, and missing-later-alias cases each exit 2 with zero page calls and no output files. A trimmed valid selector refreshes only the selected model's two tasks/home and preserves retained model/alias JSON exactly. Default full generation still visits every model task/home and every alias.
- Independently rechecked the current catalog: 40 entries, exactly one new Terra entry, with all 39 historical entries unchanged. `git diff --name-only -- docs/models` remains limited to shared `catalog.json` and `index.html`, so historical tracked model/task/alias page bytes remain identical to HEAD.

## Final scheduling disclosure review

Additional scope: `validation/gpt-6.1-terra/finalize_reports.py`, reviewed before execution on completed reports.

- Critical/Important/Minor: none.
- A temporary six-report fixture verified that only Terra's additive `measurement_scheduling`, each new report's interpretation caveat, and the integrated report's corresponding source SHA change. Historical model records, Terra scores/costs, samples, and judge-cost records remain identical.
- The fixture independently checked intersection arithmetic (300 seconds for the supplied example), verified the integrated `source_reports` SHA matches the newly finalized Korean report bytes, and ran the helper twice: all file bytes were identical on the second execution. Korean source finalization precedes its hash update in the integrated report, so no stale source hash is stored.
- Missing English completion provenance fails before any writes. All six reports are read before the write loop. The helper touches only explicitly listed new reports plus its scheduling evidence file; no frozen collector, original dataset, or historical report is rewritten.
- Real recorded Korean collection runs from `04:04:08.411652` through `04:15:25.783711` UTC. QA (`04:04:12.898458`–`04:04:25.655594`), Lotte Tower (`04:04:22.748799`–`04:05:02.821859`), and WHOAMI (`04:05:55.246856`–`04:06:10.423676`) occurred within that interval, supporting the visible caveat. The English collection already has a returned output at `04:10:43.936893`, before Korean completion, establishing overlap. Both translation jobs have frozen concurrency 8 and target the same configured Terra service.
- The exact real overlap duration remains pending the final English manifest at this review point. The helper derives it from the two completed execution intervals when run, rather than assuming a duration.

## Final grading-disclosure follow-up

- Critical/Important/Minor: none remaining. The initial proposed Korean note's 3,260/40 split conflicted with the authoritative resume log; it was corrected before publication to 3,280 preserved grades and 20 remaining grades. `judge-resume.log` records `20/3300 translations need judging` and subsequent completion of all 3,300. The earlier snapshot missed 20 rows written before the first process fully stopped.
- Korean grading now has 3,300 successful rows with no duplicate model/id keys. Candidate collection still has one execution, and an independent comparison of the current `judge-input.json` against `terra.judge_identity()` passed, proving the retained translations match the grading binding.
- The corrected finalizer fixture adds `evaluation_execution_note` and the visible grading caveat only to the two new Korean reports. It leaves scores, costs, judge-cost records, samples, and historical model records unchanged. A second execution produces identical bytes; the integrated source SHA remains valid after both scheduling and grading notes are added.
- English reporting fixtures exercised one failed judgment followed by its successful retry and a separate error-free alternate-judge run. `grading_diagnostics` correctly distinguishes recorded attempts, latest successful segments, and failed evaluation attempts. The visible retry/cost-estimate note appears only for the failed-attempt case and is carried into its composite report. Both repeated compositions produce identical records and preserve historical models and candidate aggregates.
- English frozen archive/AST verification still passes; the added diagnostics change only reporting. The independent scheduling/source-SHA verification function passed against finalized temporary fixtures.
- Both real collection manifests are now complete. Korean/English interval intersection is exactly **283.236593 seconds**, independently read through the finalizer's metadata function. English collection runs `04:10:42.547118`–`04:20:08.630690` UTC, and the earlier Korean interval ends at `04:15:25.783711`.
- English judgment completion and the full final artifact verification remain separate checks; this follow-up does not claim those were complete during review.
