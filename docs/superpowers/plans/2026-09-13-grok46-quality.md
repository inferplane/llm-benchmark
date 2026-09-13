# Grok 4.6 and translation quality metrics

The user approved adding Grok 4.6 and reevaluating the existing benchmark with
the six proposed quality metrics. Other financial tasks are recommendations,
not additional paid benchmark runs.

## Design and constraints

- Keep the existing 3,300 source segments, prompts, rubric and two judges.
- Preserve cached translations and judgments, including failed attempts.
- Add Grok 4.6 using a documented model ID, verified pricing and a live smoke call.
- Recompute existing models from their last `(model, id)` rows without model calls.
- Quality metrics operate on any subset; cost remains whole-model only.
- Preserve separate translation errors, judge errors, pending and incomplete
  per-judge coverage. Missing judgments must never become passing results.
- Numbers/entity/date risk is a judge flag, not a verified factual error.
- Historical model prices and execution provenance must remain identifiable.
- No new test framework, frontend build system, or scenario registry.

## Output contract

Quality aggregates add `quality_eligible_segments`, `quality_pass_segments`,
`quality_pass_rate`, `high_risk_segments`, `high_risk_rate`,
`judge_disagreement_segments`, `judge_disagreement_rate`,
`judge_overall_p10`, and `judge_coverage_rate`. Rates are fractions 0–1;
unavailable rates are null.

Eligibility requires complete raw scores from both actual judges, including
fallback identities. Passing requires every axis from both judges >=4.
High risk means either judge's numbers/entities/dates score <=2. Disagreement
means the absolute overall-score difference is >=1.

Whole-model aggregates add `cost_per_quality_pass_usd` only with complete quality
coverage and at least one pass. This uses the existing estimated translation
cost scope and excludes benchmark judge costs.

Whole-model and per-track quality aggregates add `baseline_comparison` against
`amazon-translate`: `baseline_model`, `paired_segments`, `win_rate`, `tie_rate`,
`loss_rate`, `mean_delta`, `mean_delta_ci95`, and `bootstrap_unit`.
Compare common valid segment IDs. Bootstrap source-document clusters so
multilingual copies do not masquerade as independent documents.

## Work

- [x] Verify Grok 4.6 documentation, credentials, decoding and live invocation.
- [x] Add hand-computed selfchecks, implement quality and paired comparisons.
- [x] Expose track-aware metrics and coverage in the dashboard.
- [ ] Run Grok 4.6 translation and both judges; retry transient failures.
- [ ] Publish a separate reevaluation report with explicit reuse provenance.
- [ ] Document findings and next scenarios: extraction, grounded QA, factual
      summarization, and instruction/format adherence.
- [ ] Run selfchecks and browser verification, then review the final diff.
- [ ] Create PR, check latest-HEAD AI reviews and required checks, fix any
      Critical/Major findings, and merge when all conditions are met.
