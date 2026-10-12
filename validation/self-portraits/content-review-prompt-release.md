# Prompt expansion release review

**PASS — all 41 public pages.** Minimum individual score: 95.5/100; 0 Critical per page and at most 3 Warnings. The existing user-authorized four held states are retained.

Scope: 34 actual-model artworks, 4 held-status pages, 2 unavailable pages, and gallery. 38 models expose 54 exact prompt texts,including 16 initial/latest pairs.

## New original artworks

| Model | Score | Critical | Warnings | SHA-256 |
|---|---:|---:|---:|---|
| grok-4.7 | 96.5 | 0 | 3 | 1738dc44bf73d5605dfec2136c1194bb24cc129523277269f85f2213a62a829c |
| glm-5.3 | 97.5 | 0 | 2 | bff88dd7ced3b5761881f0a764a69e77e43c075421c024e301a2578ed5088c69 |

## All public pages

| Model/page | Page kind | Score | Warnings | Verdict |
|---|---|---:|---:|---|
| gallery | gallery | 100 | 0 | PASS |
| claude-haiku-4.5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| claude-sonnet-4.5 | model_authored_artwork_with_prompt | 95.5 | 3 | PASS |
| claude-sonnet-5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| claude-haiku-5.5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| claude-sonnet-5.5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| claude-opus-5.5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| claude-fable-5.1 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| nova-pro | model_authored_artwork_with_prompt | 95.5 | 3 | PASS |
| kimi-k3 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| nova-lite | model_authored_artwork_with_prompt | 97.0 | 2 | PASS |
| amazon-translate | unavailable_status | 100 | 0 | PASS |
| gpt-5.4 | model_authored_artwork_with_prompt | 97.0 | 2 | PASS |
| gpt-5.5 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| gpt-5.6-terra | model_authored_artwork_with_prompt | 97.0 | 2 | PASS |
| gpt-5.6-luna | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| gpt-6-luna | model_authored_artwork_with_prompt | 100 | 0 | PASS |
| gpt-6-astra | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| gpt-6.1-sol | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| grok-4.3 | model_authored_artwork_with_prompt | 96.5 | 2 | PASS |
| grok-4.6 | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| grok-4.7 | model_authored_artwork_with_prompt | 96.5 | 3 | PASS |
| nova-micro | held_status_with_inert_prompt_text | 100 | 0 | PASS |
| nemotron-nano-3-30b | held_status_with_inert_prompt_text | 100 | 0 | PASS |
| glm-4.7-flash | model_authored_artwork_with_prompt | 95.5 | 3 | PASS |
| glm-5.3 | model_authored_artwork_with_prompt | 97.5 | 2 | PASS |
| gpt-oss-20b | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| gpt-oss-120b | model_authored_artwork_with_prompt | 95.5 | 3 | PASS |
| qwen3-32b | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| nemotron-super-3-120b | model_authored_artwork_with_prompt | 98.0 | 2 | PASS |
| llama4-scout | model_authored_artwork_with_prompt | 96.0 | 3 | PASS |
| ministral-14b | model_authored_artwork_with_prompt | 96.0 | 3 | PASS |
| qwen3-235b-a22b | model_authored_artwork_with_prompt | 96.0 | 3 | PASS |
| llama4-maverick | model_authored_artwork_with_prompt | 97.0 | 2 | PASS |
| llama-3.3-70b-bedrock | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| gemma-4-31b-bedrock | model_authored_artwork_with_prompt | 98.5 | 1 | PASS |
| llama-3.1-8b | held_status_with_inert_prompt_text | 100 | 0 | PASS |
| llama-3.3-70b | model_authored_artwork_with_prompt | 97.0 | 2 | PASS |
| gemma-4-31b | unavailable_status | 100 | 0 | PASS |
| qwen3.6-27b | model_authored_artwork_with_prompt | 100 | 0 | PASS |
| exaone-3.5-32b | held_status_with_inert_prompt_text | 100 | 0 | PASS |

## Verification

- Every model wrapper checked at 375/768/1280px: no overflow, outside controls,script errors or failed references.
- All 38 native prompt dialogs passed keyboard opening,focus,Escape/focus restoration,mobile fitting and executable-markup exclusion.
- All 54 displayed/exported prompt texts exactly match recorded SHA values; first requests match the earliest preserved request records. All 54 raw links render exact plaintext.
- All 32 previously approved artwork bytes are unchanged; both new works match actual API responses.
- Four held artwork/preview files remain absent. Their earlier code may appear only as inert text within genuine repair prompts; original REVIEW grades remain separately recorded.
- No credential,ARN or private-IP disclosure found in the release material.
- Release JSON records hashes for all body/shared/provenance/prompt files and the complete 210-file release inventory.

## Evidence

- `/tmp/prompt-expansion-review/release-browser.json`
- `/tmp/prompt-expansion-review/browser-v1.json`
- `/tmp/prompt-expansion-review/release`
- `/tmp/prompt-expansion-review/release-<model>-{page,dialog}-<width>.jpg`

Reviewer performed no deployment and changed no application or artwork source.
