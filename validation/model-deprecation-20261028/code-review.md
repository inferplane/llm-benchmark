# Independent code review — 2026-10-28

**Verdict: PASS — ready to merge.** No Critical, Important or Minor findings.

Reviewed the working-tree changes against base revision
`d8478791d16c0eceeb9506905c1a3ffa94df75d8` on
`chore/bedrock-model-deprecation-20261028`. Review was read-only except for this
report and its JSON companion. No candidate inference or cloud mutation was
performed.

## Strengths

- The parsed config differs only by adding `enabled = false` to the nine requested
  Bedrock entries. All model IDs, prices, self-hosted entries, other models and
  non-model settings match the base revision.
- Existing selectors enforce the exclusions for new translation, FinQA and TAT-QA
  runs, including explicit model requests. No runner or frozen grader changes are
  necessary. TAT-QA's new API roster is exactly 26 models, reduced from 35.
- The audit accurately separates user-requested exclusions from provider status:
  four models have documented future EOL dates; five model cards retain Active/
  N/A; the saved lifecycle API response reports ACTIVE for all nine. Neither the
  comments nor the audit claim present endpoint unavailability.
- The historical TAT-QA contract still loads all 35 models and 200 questions.
  Historical artifacts, published reports, frozen scoring code and deployment
  manifests have no tracked changes. Website source and report hashes still match
  the previous 100/100 content review.
- The legacy audited FinQA freeze mismatch under the reduced current roster is
  documented with an original-revision replay instruction. The frozen protocol
  and grader remain intact.

## Findings

- Critical: none.
- Important: none.
- Minor: none.

## Fresh verification

Both commands exited 0:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache uv run --frozen --no-sync python -m bench.report --selfcheck
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache uv run --frozen --no-sync python -m bench.tatqa --selfcheck
```

Independent offline assertions also passed for the complete parsed-config diff,
the 35-to-26 TAT-QA roster difference, disabled-model rejection by each of the
three runner entrypoints before inference, historical TAT-QA `load_run()`, all six
reviewed website source hashes, the published report and contract hashes, and the
documented `finqa_audited.verify_freeze()` rejection. `git diff --check` passed.

The reviewed config SHA-256 is
`15a3c4de1bd4eeac86b012f54eb85a9681d82a810933cec42b801d303fab5894`.

## Declined to judge

- Whether any endpoint currently accepts paid inference requests: outside this
  config-exclusion task; no candidate calls were authorized or needed.
- The provider's eventual retirement schedule for the five Active/N/A cards:
  the user supplied no notice URL or effective date; the audit preserves this
  uncertainty and implements the requested policy.
- Redesigning legacy FinQA report composition to replay under a changed current
  roster: outside the requested exclusion and frozen-grader preservation scope;
  historical reproduction requires the original revision/config as documented.
- Re-running browser content review: no website content changed, and the exact
  reviewed website/report hashes were independently confirmed.

## Assessment

The change fulfills the requested exclusion policy using the existing model
enablement boundary. It preserves historical data and frozen evaluation contracts;
the one documented historical FinQA replay constraint does not require a change
to frozen code. No fixes are required before merge.
