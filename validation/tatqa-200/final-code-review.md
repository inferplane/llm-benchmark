# Final TAT-QA code and result review

Date: 2026-10-27. **PASS — no open Important or Critical findings.**

This review covers the current TAT-QA implementation, frozen execution contract, final report and dashboard code. It follows the requesting-code-review workflow and the prior [execution preflight](code-review.md). Presentation/content review is a separate gate. No candidate calls, report rewrites or implementation edits were performed by this reviewer.

## Final artifact

- Run: `tatqa-api-200-20261027`.
- Report: `docs/tatqa-results/tatqa-api-200-20261027.json`.
- Report SHA-256: `c667a06faaa4f91d2822d1ef870e846972942875d6d7cadec3becb8aa51705fb`.
- Contract SHA-256: `0a202145e2a3b978e783abbfefbd6f11e58330a7ae23c576f6190cc12f2d67a3`.
- 35 models × 200 questions = 7,000 retained latest responses; 200 distinct table contexts.
- 6,811 scored responses and 189 invalid responses; zero missing responses, final request failures or truncations.
- 7,001 append-only attempt rows include one historical failed attempt followed by a successful retry. Every model has one started and one finished execution event. Final metrics use the latest row per model/question.

## Evidence and conclusions

**Frozen execution:** The adapter and money-path code still match the pre-call reviewed hashes. `load_run` verifies the complete frozen contract, source inputs, prompt and relevant code/dependency hashes. The manifest was created before the first execution event, and every started event identifies the same contract. The final report reproduces the manifest's contract, dataset metadata, protocol and complete model roster.

**Scores and denominators:** Independently recomputed all 7,000 final response scores and compared every sample's prediction hash, raw output, status, parsed answer, scale, EM and F1. Recomputed model aggregates, coverage and all answer-type aggregates. Every model retains a denominator of 200; all 189 invalid responses score zero. Sample questions, table contents, paragraphs, context IDs and gold values match the frozen dataset. No type-level cost or throughput fields are present.

**Money path:** Independently summed retained input, output and cache token counts against frozen configured rates for every model. Reported totals and per-question costs match the documented rounding. Successful invalid responses remain billed. The sum of model estimates is **$14.9194**, excluding the historical failed attempt and any unrecorded charges; this is not an invoice total. The durable truncation regression check preserves billed usage while assigning zero quality, and missing/genuine failed responses still withhold incomplete estimates.

**Dashboard behavior:** Question text, source cells, answers, raw outputs, errors and provenance are rendered using `textContent` or text nodes. No untrusted content is inserted through `innerHTML`. Run IDs are restricted before path construction, source links remain within the pinned HTTPS upstream repository, and result fetches explicitly use `cache: "no-store"`. The UI visibly explains the full denominator, JSON-format failures, missing responses, request failures and truncations; unavailable cost uses an explanatory dash. Coverage is explicitly distinguished from accuracy, and format compliance is disclosed beside the principal scores. Small score differences and the distinction between table contexts and independent source reports are also disclosed. Empty/error states hide stale result tables and provide retry behavior. Browser/content checks are maintained by the separate content reviewer.

**Compatibility and scope:** Existing FinQA and translation result logic is preserved; existing-page changes add scenario navigation and its asset cache key. Models and historical rates remain configuration-driven, provider transports are unchanged, and no GPU resources are introduced.

## Checks executed

All focused required checks passed:

```text
UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache uv run --frozen --no-sync python -m bench.tatqa --selfcheck
UV_CACHE_DIR=/tmp/llm-benchmark-uv-cache uv run --frozen --no-sync python -m bench.report --selfcheck
node --check docs/tatqa.js
git diff --check
```

A final read-only reconciliation additionally verified all final rows, execution events, prediction hashes, aggregates, type metrics, token counts and prices against the exact report hash above. The earlier in-progress report was superseded; this review is bound to the completed artifact.

## Reviewed code hashes

| File | SHA-256 |
|---|---|
| `bench/tatqa.py` | `1c4834589582189d4a286ecab058b4d19644c82b5c86457af78e63cfb382d09c` |
| `bench/report.py` | `11daa071bb058f79c7dc34f469dc6db50d0d26a989d86900beb81a5721ae2f5c` |
| `docs/tatqa.html` | `b7d7317e67e6665a612c5df7134aa7660784fbe40f828c5ac9c22e142c638a28` |
| `docs/tatqa.js` | `06fc75ac5a3c76ddd2076390e228fa3b2a67ca623e792e935f58d78c5d7f23e9` |
| `docs/tatqa.css` | `790b6a19919ba1e295ad11b4574ddcf901ff93ca2ffed6c65868e51ee2132421` |

Base HEAD at review: `07e21c5473a03e6e834625f64f672d3fc9e0bb5f`. The review includes the working-tree changes and new files, with hashes binding the files above.

Remaining limitations are disclosed rather than silently corrected: official scoring quirks remain, published-test contamination is unmeasured, model reasoning configurations differ, annotations were not individually financially re-audited, and configured-rate estimates exclude failed/retried-call charges. These are not new merge blockers.
