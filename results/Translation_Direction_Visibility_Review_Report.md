# Translation Direction Visibility — Content Review

**Final verdict: PASS — 97.5/100; 0 Critical, 2 Warnings.** The reviewed candidate meets the ≥85/100 deployment gate and independently passes the Critical and Warning count bands. The two remaining Warnings concern existing heatmap typography and contrast.

## Review metadata

| Field | Value |
|---|---|
| Date | 2026-10-19 UTC |
| Review type | Interactive HTML benchmark dashboard |
| Iteration | 2, independent review after two corrections |
| Procedure | Installed aws-content-plugin 3.0.4 content-review-agent, Codex runtime and workflow |
| Scale | 100 points, including real Chromium visual testing |
| Candidate reviewed | `/tmp/llm-translation-release-20261019`, corrections based on `a9d63a2` |
| Supporting validation inspected | `validation/customer-view/translation-directions.cjs` |
| Browser evidence | Independent local Playwright/Chromium session against a loopback-only preview |
| Ownership | Review report only; reviewer did not edit application files or deploy |

Reviewed file SHA-256:

```text
c97db5965dd4030e25ab4070a6600fefa21af8b15f52052725e4c5b30bcdb124  docs/app.js
3093520e5e4a984f07e90d5929513810c1e20677f11dcda557f14a18ddb19d4e  docs/index.html
```

## Quality gate

Each category starts at full points. Each noncritical defect deducts one quarter of that category's maximum; deductions are summed within the category, then rounded once to the nearest 0.5, with .25/.75 rounded upward. Noncritical category scores have a floor of 1. A Critical defect scores its category zero. Score, Critical count and Warning count are evaluated independently; the worst band sets the verdict.

| Category | Maximum | Score | Critical | Warning | Evidence |
|---|---:|---:|---:|---:|---|
| Layout | 8 | 8 | 0 | 0 | Valid heading sequence, contained scrolling, no page overflow in five viewport sizes |
| Terminology | 8 | 8 | 0 | 0 | Direction labels, 1–5 quality scale and whole-model cost units are consistent |
| No Hallucination | 12 | 12 | 0 | 0 | Rendered values matched the repository's measured JSON; no new service/capability claims |
| Language Consistency | 8 | 8 | 0 | 0 | Korean explanation with consistent English technical labels |
| No Sensitive Data | 12 | 12 | 0 | 0 | Target-source scan and rendered screenshots showed no credentials, private addresses or contact PII |
| Content-Type Quality | 2 | 2 | 0 | 0 | Heatmap, scatter charts, legends and source labels render |
| Icon Usage | 5 | 5 | 0 | 0 | No broken icons; no AWS architecture icon requirements apply |
| Renders Correctly | 5 | 5 | 0 | 0 | Zero page/console errors, warnings or failed HTTP requests observed |
| Interactions Work | 5 | 5 | 0 | 0 | Four direction buttons, report changes, cohort controls and theme toggle execute |
| Readability | 5 | 5 | 0 | 0 | Heatmap comes first; lengthy explanations are disclosed on demand |
| Accessibility | 5 | 2.5 | 0 | 2 | W3 and W4 |
| Structural Completeness | 5 | 5 | 0 | 0 | Quality, cost, recommendations, samples, diagnostics and methodology retained |
| Data Accuracy & External References | 5 | 5 | 0 | 0 | Values, per-cell run provenance and consistent cohort eligibility verified |
| Legal Compliance | 5 | 5 | 0 | 0 | No new third-party assets or detected copyright infringement; third-party dashboard is not an AWS-branded deliverable |
| Message Clarity | 5 | 5 | 0 | 0 | Instructions distinguish merged heatmap from selected-report charts |
| Duplication/Gaps | 5 | 5 | 0 | 0 | No required source section omitted |
| **Total** | **100** | **97.5** | **0** | **2** | **PASS** |

## Critical issues

None observed.

## Warning issues

### W3 — Important heatmap text is below the review rubric's minimum size

| Field | Value |
|---|---|
| Location | `docs/index.html:216`, `docs/index.html:222`, `docs/index.html:240` |
| Original | `font-size: 12px;` / `font-size: 12.5px;` |
| Evidence | Computed direction buttons: 12px; score/model cells: 12.5px; instructions and source line: 13px, at desktop and mobile sizes |
| Problem | These are below this content rubric's 14pt minimum. This is a rubric requirement, not a claim that WCAG itself mandates a minimum font size |
| Action | Increase important heatmap text and controls, retaining the scroll container and responsive layout |
| Deduction | Combined with W4: 2 × 1.25 = 2.5 from Accessibility |

### W4 — Muted heatmap text has insufficient normal-text contrast

| Field | Value |
|---|---|
| Location | `docs/index.html:24`, `docs/index.html:45`, `docs/index.html:233`; heatmap panel note |
| Original | `--ink-muted: #86806E;` / `--ink-muted: #6E7690;` |
| Evidence | Light theme: `#86806E` on white, 3.94:1. Dark theme: `#6E7690` on `#131B2C`, 3.81:1 |
| Problem | Small explanatory text and pair labels fall below the rubric's 4.5:1 contrast requirement |
| Action | Use a darker light-theme muted color and a lighter dark-theme muted color, then verify both themes |
| Deduction | Combined with W3: 2.5 from Accessibility |

Repeated font-size and contrast occurrences are consolidated by their respective shared styling causes, rather than counted as separate warnings for each cell.

## Resolved findings

| Finding | Correction | Independent confirmation |
|---|---|---|
| W1: Instructions incorrectly promised a report switch | `docs/index.html:460` explains supplementary KO/EN heatmap results and selected-report charts | Direction buttons preserve the run selector while source labels correctly identify supplementary reports |
| W2: Supplemental sources bypassed the cohort filter | `docs/app.js:1080` applies the selected recorded cohort to every source; `docs/index.html:470` discloses exclusion of unlabeled results | Both latest and older integrated selections show 27 original-cohort or 5 explicit-cohort heatmap models consistently across directions. Unlabeled English observations are excluded; English directions retain the measured EN↔KO pair |
| Cell-level provenance was ambiguous when sources were combined | `docs/app.js:828`–`833` publishes source title, exact run ID and recorded cohort in each populated cell's title | Verified every populated cell's source run ID and cohort label against the matching source JSON |

The older integrated report can retain 2 selected-report chart models while the supplementary heatmap includes 5 models recorded under the same cohort. This is consistent with the now-disclosed independent source scope; models from a different or unrecorded cohort do not enter the filtered heatmap.

## Independent verification

- Real Chromium checks covered KO → X, EN → X, X → KO and X → EN; every direction populated, including the KO column for English directions.
- The final independent oracle compared 8,438 rendered cells with published JSON using the selected/integrated/default source precedence, across the default report, latest integrated report, older integrated report and available cohorts. Values matched; populated cells also identified the correct run and cohort.
- Screen widths 1920, 3840, 768, 390 and 320 pixels had no document-level horizontal overflow. At 390 and 320 pixels, the first score row was visible within the 844-pixel viewport.
- Both scatter charts had nonzero dimensions and datasets. Theme switching preserved the heatmap.
- Captured and inspected desktop, mobile, chart and dark-theme screenshots. No screenshot showed exposed secrets or broken assets.
- Zero JavaScript page errors, console errors, console warnings or failed network responses occurred during the successful visual review sessions.
- Reviewed the updated regression script's source-derived expectations, cohort exclusions, source tooltip assertions, mobile sticky-label checks and single-report/empty-state scenarios.
- Independently executed `validation/customer-view/translation-directions.cjs` against the candidate: **PASS, 13,336 values/provenance checks**, including preserved chart selection, cohort isolation, mobile sticky labels, both themes, single-report EN↔KO and empty-state recovery.
- Temporary preview servers and Chromium processes were shut down after review.

Final evidence artifacts: `/tmp/translation-final-content-review.json`, `/tmp/translation-final-review-cohort.json`, `/tmp/translation-final-review-1920.png`, `/tmp/translation-final-review-3840.png`, `/tmp/translation-final-review-768.png`, `/tmp/translation-final-review-390.png`, `/tmp/translation-final-review-320.png`, `/tmp/translation-final-review-charts.png`, `/tmp/translation-final-review-dark.png`.

## Source-omission findings

Source material was the delegated change brief, repository instructions, published measurement JSON and baseline dashboard. No separate customer briefing document or external reference article was provided.

| Source section / requirement | Output status | Note |
|---|---|---|
| Four KO/EN translation directions | INCLUDED | All four have populated matrices |
| KO column for English directions | INCLUDED | EN/KO and KO/EN appear |
| Visible measured values and report origin | INCLUDED | Values, source titles, per-cell run/cohort provenance and consistent cohort scope verified |
| Quality and cost charts near the start | INCLUDED | Heatmap first, cost/quality charts next |
| Whole-model cost and timing caveat | INCLUDED | Remains visible with detailed explanation under a disclosure |
| Financial/general track choice | INCLUDED | Moved into chart section; heatmap identifies its all-document scope |
| Family legend and model provenance | INCLUDED | Preserved under a disclosure |
| Interpretation and methodological caveats | INCLUDED | Collapsed rather than removed |
| Recommendations, comparison table and samples | INCLUDED | Retained below the charts |
| Diagnostics, language coverage, history and methodology | INCLUDED | Retained |

No required source section was omitted. Existing measurements were validated against repository JSON; re-measuring model performance or refreshing provider pricing was outside this dashboard-only change.

## Revision checklist

- [x] W1: Correct merged-source instructions.
- [x] W2: Make cohort scope consistent across supplemental reports.
- [ ] W3: Increase heatmap text sizes to the rubric minimum.
- [ ] W4: Improve muted-text contrast in both themes.

| Fix set | Critical | Warnings | Projected score | Projected verdict |
|---|---:|---:|---:|---|
| Current candidate | 0 | 2 | 97.5 | PASS, verified |
| All warnings | 0 | 0 | 100 | PASS, subject to verification |

Next step: proceed through the authorized release workflow with these exact reviewed application hashes. W3 and W4 remain non-blocking improvements under this rubric. Any further application change requires corresponding re-verification.
