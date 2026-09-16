# Grok explicit-instruction retest

The user approved repeating the comparison after the three-case diagnostic
showed sensitivity to ambiguous preservation instructions.

## Fixed protocol

- Evaluate Grok 4.3 and Grok 4.6 on all existing 3,300 records each: 3,000
  FLORES and 300 synthetic, covering 30 translation directions.
- Use the diagnostic's clarified translation prompt: preserve semantic values
  and identities, use target-language notation, translate table text while
  preserving structure. Keep the existing judge rubric unchanged.
- Both candidates use Mantle us-west-2, reasoning low, temperature zero,
  output cap 4,096, concurrency eight per model, maximum four attempts.
- Run both model batches concurrently in the same process and evaluation
  window. Candidate model IDs and pricing come only from config.toml.
- Freeze the selected dataset, prompt, rubric and configuration fingerprints
  before generation. Verify them before resuming any cached work.
- Use a new run directory. Obtain new translations and dual-judge scores for
  every key; no diagnostic or historical responses contribute.
- Preserve the filesystem boundary between translation, judging and reports.
  A per-experiment reproduction script invokes the existing translation
  runner; judging/reporting use their existing separate CLIs.

## Execution and validation

1. Commit the explicit prompt, matched configuration and reproduction script
   with its frozen inputs before making benchmark calls.
2. Run the reproduction script and judge each available translation in
   batches; resume only incomplete keys until all 6,600 are complete.
3. Build a two-model report, without including old-prompt results. Compare the
   two models on matched IDs using source-document-clustered confidence
   intervals, independently verify costs and coverage, and inspect examples.
4. Write reader-facing findings about quality, costs and comparison conditions.
   Do not include operational troubleshooting narratives in the dashboard.
5. Run relevant selfchecks and browser QA, obtain independent code/content
   review of the latest HEAD, satisfy CI/branch rules, merge and verify Pages.

The three-case diagnostic is not a representative sample or a new ranking.
The full retest establishes results under this explicit prompt and matched
settings; it does not isolate every change from the July experiment.
