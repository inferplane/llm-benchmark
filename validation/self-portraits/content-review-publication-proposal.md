# Publication proposal content review

**PASS for the proposed 39-page publication surface.** No deployment was performed and the user publication-scope choice is still pending.

The proposal contains 32 unchanged,independently approved model artworks; four held-status pages; two unavailable-status pages; and one gallery. The minimum individual score is95.5/100. Every proposed page has 0 Critical and at most 3 Warnings.

## Original artwork grades remain separate

| Held model | Original artwork score | Original verdict | Proposed page |
|---|---:|---|---|
| nova-micro | 95.5 | REVIEW | Status only: PASS 100/100 |
| nemotron-nano-3-30b | 94.5 | REVIEW | Status only: PASS 100/100 |
| llama-3.1-8b | 92.5 | REVIEW | Status only: PASS 100/100 |
| exaone-3.5-32b | 92.5 | REVIEW | Status only: PASS 100/100 |

Held artwork.html and preview.jpg files are absent from the proposal. No hidden iframe,raw-artwork link or raw-artwork request was found. Original source and records remain preserved in the workspace.

## Proposed-page results

| Model/page | Page kind | Score | Critical | Warnings | Verdict |
|---|---|---:|---:|---:|---|
| gallery | gallery | 100 | 0 | 0 | PASS |
| claude-haiku-4.5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| claude-sonnet-4.5 | unchanged_model_authored_artwork | 95.5 | 0 | 3 | PASS |
| claude-sonnet-5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| claude-haiku-5.5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| claude-sonnet-5.5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| claude-opus-5.5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| claude-fable-5.1 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| nova-pro | unchanged_model_authored_artwork | 95.5 | 0 | 3 | PASS |
| kimi-k3 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| nova-lite | unchanged_model_authored_artwork | 97.0 | 0 | 2 | PASS |
| amazon-translate | unavailable_status_only | 100 | 0 | 0 | PASS |
| gpt-5.4 | unchanged_model_authored_artwork | 97.0 | 0 | 2 | PASS |
| gpt-5.5 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| gpt-5.6-terra | unchanged_model_authored_artwork | 97.0 | 0 | 2 | PASS |
| gpt-5.6-luna | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| gpt-6-luna | unchanged_model_authored_artwork | 100 | 0 | 0 | PASS |
| gpt-6-astra | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| gpt-6.1-sol | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| grok-4.3 | unchanged_model_authored_artwork | 96.5 | 0 | 2 | PASS |
| grok-4.6 | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| nova-micro | held_status_only | 100 | 0 | 0 | PASS |
| nemotron-nano-3-30b | held_status_only | 100 | 0 | 0 | PASS |
| glm-4.7-flash | unchanged_model_authored_artwork | 95.5 | 0 | 3 | PASS |
| gpt-oss-20b | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| gpt-oss-120b | unchanged_model_authored_artwork | 95.5 | 0 | 3 | PASS |
| qwen3-32b | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| nemotron-super-3-120b | unchanged_model_authored_artwork | 98.0 | 0 | 2 | PASS |
| llama4-scout | unchanged_model_authored_artwork | 96.0 | 0 | 3 | PASS |
| ministral-14b | unchanged_model_authored_artwork | 96.0 | 0 | 3 | PASS |
| qwen3-235b-a22b | unchanged_model_authored_artwork | 96.0 | 0 | 3 | PASS |
| llama4-maverick | unchanged_model_authored_artwork | 97.0 | 0 | 2 | PASS |
| llama-3.3-70b-bedrock | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| gemma-4-31b-bedrock | unchanged_model_authored_artwork | 98.5 | 0 | 1 | PASS |
| llama-3.1-8b | held_status_only | 100 | 0 | 0 | PASS |
| llama-3.3-70b | unchanged_model_authored_artwork | 97.0 | 0 | 2 | PASS |
| gemma-4-31b | unavailable_status_only | 100 | 0 | 0 | PASS |
| qwen3.6-27b | unchanged_model_authored_artwork | 100 | 0 | 0 | PASS |
| exaone-3.5-32b | held_status_only | 100 | 0 | 0 | PASS |

## Verification

- Changed gallery and four held pages tested at 375/768/1280px in offline Chromium under a project URL prefix.
- Gallery: 38 cards, 32 artwork previews, four held placeholders; visible total matches. Family filtering,search and empty state work.
- Held pages:state is explicit; readable typography; no overflow; keyboard opens provenance; JSON-record links load.
- All 32 raw artwork hashes and viewer hashes match the original PASS rows; two unavailable pages also match their prior reviewed sources. Shared CSS/JS are unchanged.
- Local references resolve; no console/network errors or sensitive-data findings.
- The original raw-artwork report remains unchanged. It still records 35 PASS and 4 REVIEW across its original scope.

## Evidence

- Proposal: `/tmp/llm-benchmark-gh-pages/docs`
- Frozen browser evidence: `/tmp/portrait-review/publication-proposal-browser.json`
- Frozen sources: `/tmp/portrait-review/publication-proposal-source`
- Screenshots: `/tmp/portrait-review/proposal-<model>-<width>.jpg`
- Original report SHA-256: `fe536423266b244594bb15a3a664f8d9011aa9e16dabbd18959973db648b5d97`

**User choice remains required before this proposal is deployed.**
