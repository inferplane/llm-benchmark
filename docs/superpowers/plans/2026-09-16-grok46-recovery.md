# Grok 4.6 request recovery

## Evidence and scope

The September 13 run attempted 3,300 translations. After four calls per
persistent failure, 55 keys still have empty error strings and latencies around
120 seconds. Failed inputs include a 29-character sentence; a length-limit
explanation is unsupported. On September 16, five formerly failed inputs,
including all three financial documents, completed with the same generation
settings in 5.5–24.6 seconds. Four used the original 120-second limit; the fifth
used a 300-second diagnostic limit but completed in under 12 seconds.

The historical server-side stall cannot be reconstructed from blank errors
without request IDs. Confirmed harness problems are lossy exception recording,
no classified retry policy inside a run, and success exit status despite
unfinished requests. Do not claim that increasing the timeout caused recovery.

## Implementation

- Keep the model, region, temperature request, reasoning `low`, prompt, rubric,
  dataset and 4,096 output-token cap unchanged.
- Keep the existing 120-second Mantle timeout, expose it in execution metadata.
- Give Grok 4.6 `request_max_attempts = 4` (initial call plus at most three retries).
  Other models retain one outer attempt by default.
- Retry only transient transport/service failures with bounded backoff; do not
  retry invalid requests, authorization failures or content-policy refusals.
- Preserve every attempt as append-only JSONL, with nonempty error text and
  separately named translation/judgment error details. Never mark empty or
  incomplete responses done.
- Translation and judge CLIs must return nonzero when requested work remains.
  Successful cache entries remain reusable.
- Add offline regression checks for retry/resume, failure diagnostics, terminal
  response validation and CLI completion. No new test framework.
- Record retry settings in both manifest and report configuration allowlists.

## Recovery and publication

- Run only the 55 failed source IDs in a new `grok-4.6-2026-09-16` directory.
  Preserve September 13 observations and original failures.
- Judge the recovered outputs with the same two judges.
- Combine `full-2026-07-18`, `grok-4.6-2026-09-13` and the new recovery run using
  the existing source-aware report path. Mixed-source throughput stays
  unavailable; token-priced cost and quality remain computable.
- Require all 3,300 translation keys and their judgments to be successful.
- Publish the updated interpretation and diagnosis, validate, review the latest
  PR HEAD, fix any blocking findings, merge and verify the deployed artifacts.
