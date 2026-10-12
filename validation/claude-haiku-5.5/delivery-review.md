# Haiku5.5 benchmarks and artwork cost — final delivery PASS

Reviewed2026-10-12T13:46:54.482470+00:00. Candidate`/tmp/llm-benchmark-gh-pages`. `release_review_complete=true`.

44publication HTML targets PASS; minimum96.0/100; Critical0; maximum3Warnings per artifact. All297public-doc file hashes are recorded in JSON. Public-tree SHA-256:`e39d5077d50068f4b4c5ebb1971ea561f0b560424addaff036965662fd5c39e7`.

- Translation:3300unique inputs/3300successful outputs/3300latest complete judgments. Raw judgment history3303rows includes3ReadTimeouts, retried with frozen settings; no candidate regeneration.
- Single/integrated reports independently rebuilt exactly. Prior31model snapshots and all oldsample entries preserved; cohorts27original/5explicit.
- Translation candidate-token estimate independently calculated0.62687603USD→display0.6269USD. Unknown failed evaluator usage is explicitly excluded from evaluator-cost estimates.
- Default dashboard shows32models including Haiku5.5/GPT6Luna, financial synthetic score4.57; mixed-track4.728 is only shown when explicitly selecting alltracks.
- QA:31models, Haiku18/20; prior30models/evaluations unchanged. Default dashboard contains Haiku5.5 andGPT6Luna.
- All38original artwork bytes unchanged. All66archived implementation requests independently recomputed, with correctedUSGeo rates/cache handling and no reasoning/current-copy double count.
- Fee dialogs, cost/unknown-usage/GPUexclusion disclosures, model filtering, keyboard details, Escape/focus restoration and default dashboards pass375/768/1280checks with0runtime/network errors.
- Source contracts/ASTproofs and hand-computed money selfchecks pass.267public/newbenchmark text files scanned:0credential/private-key matches. No unrelated rootpilots copied.

## Publication grades

| Target | Score | Critical | Warnings | Verdict |
|---|---:|---:|---:|---|
|model-gallery|100|0|0|PASS|
|model-cost:claude-haiku-4.5|98.5|0|1|PASS|
|model-cost:claude-sonnet-4.5|97.5|0|2|PASS|
|model-cost:claude-sonnet-5|96.5|0|2|PASS|
|model-cost:claude-haiku-5.5|98.5|0|1|PASS|
|model-cost:claude-sonnet-5.5|98.5|0|1|PASS|
|model-cost:claude-opus-5.5|100|0|0|PASS|
|model-cost:claude-fable-5.1|100|0|0|PASS|
|model-cost:nova-pro|97.5|0|2|PASS|
|model-cost:kimi-k3|98.5|0|1|PASS|
|model-cost:nova-lite|96.5|0|2|PASS|
|model-cost:gpt-5.4|97.0|0|3|PASS|
|model-cost:gpt-5.5|98.5|0|1|PASS|
|model-cost:gpt-5.6-terra|98.5|0|1|PASS|
|model-cost:gpt-5.6-luna|96.0|0|3|PASS|
|model-cost:gpt-6-luna|96.5|0|3|PASS|
|model-cost:gpt-6-astra|98.5|0|1|PASS|
|model-cost:gpt-6.1-sol|100|0|0|PASS|
|model-cost:grok-4.3|98.5|0|1|PASS|
|model-cost:grok-4.6|98.5|0|1|PASS|
|model-cost:grok-4.7|98.5|0|1|PASS|
|model-cost:nova-micro|97.0|0|2|PASS|
|model-cost:nemotron-nano-3-30b|96.0|0|3|PASS|
|model-cost:glm-4.7-flash|97.5|0|2|PASS|
|model-cost:glm-5.3|97.0|0|2|PASS|
|model-cost:gpt-oss-20b|96.5|0|2|PASS|
|model-cost:gpt-oss-120b|96|0|3|PASS|
|model-cost:qwen3-32b|96.0|0|3|PASS|
|model-cost:nemotron-super-3-120b|96.5|0|2|PASS|
|model-cost:llama4-scout|96.5|0|2|PASS|
|model-cost:ministral-14b|98.5|0|1|PASS|
|model-cost:qwen3-235b-a22b|96|0|3|PASS|
|model-cost:llama4-maverick|98.5|0|1|PASS|
|model-cost:llama-3.3-70b-bedrock|98.5|0|1|PASS|
|model-cost:gemma-4-31b-bedrock|96|0|3|PASS|
|model-cost:llama-3.1-8b|97.5|0|2|PASS|
|model-cost:llama-3.3-70b|96.0|0|3|PASS|
|model-cost:qwen3.6-27b|96|0|3|PASS|
|model-cost:exaone-3.5-32b|97.5|0|2|PASS|
|finqa-dashboard|98.5|0|1|PASS|
|finqa-haiku-detail|98.5|0|1|PASS|
|translation-dashboard|97.5|0|2|PASS|
|status:amazon-translate|100|0|0|PASS|
|status:gemma-4-31b|100|0|0|PASS|

## Current-scope warnings

- `docs/customer.css:20`: Several informative labels, guidance and table/details text render below the14pt minimum, including14px notes and12–16px labels. This is existing shared typography, not a new data error. Action:Use at least19px for informative text while preserving scrolling layouts.
- `docs/finqa-results/finqa-claude-haiku-5.5-20261012.html:1`: The report uses18px body/controls, below the14pt minimum. Action:Use at least19px informative text.
- `docs/customer.css:20`: Default translation-dashboard explanatory labels/notes and some table controls use12–18px text, below the14pt minimum. Existing shared typography remains. Action:Use at least19px for informative text while preserving responsive scrolling.
- `docs/index.html:45`: The default light-theme result-selector label uses this muted foreground on the light page; computed color contrast is about3.55:1 against#F6F3EA, below4.5:1. Action:Increase the contrast of informative muted labels.

Unchanged artwork warnings remain inherited from the prior independent review and are reproduced in the JSON publication grades. No issue was erased to reach the gate.

## Evidence

- full_cost_and_QA_browser:`/tmp/haiku-delivery-review/frozen-131853/browser.json`
- corrected_three_rate_UI_recheck:`/tmp/haiku-delivery-review/frozen-132242/browser.json`
- independent_all38_cost_recalculation:`/tmp/haiku-delivery-review/cost-audit.json`
- prior_original_artwork_review:`/home/atomoh/llm-benchmark/validation/self-portraits/free-expression-review.json`
- prior_original_artwork_review_sha256:`650511938963ba855e4acaf7c122552f44850776c11fa6b43c5ba0afb9ae53f0`
- final_candidate_browser:`/tmp/haiku-delivery-review/final-134032/browser.json`
- translation_retry_cost_disclosure_browser:`/tmp/haiku-delivery-review/final-134032/translation-disclosure-browser.json`
- translation_independent_replay:`/tmp/haiku-delivery-review/translation-audit.json`
- public_source_freeze:`/tmp/haiku-delivery-review/final-134032/manifest.json`
- existing_CDN_font_snapshot:`/tmp/haiku-delivery-review/vendor/manifest.json`

Only the two owned delivery-review reports were changed. Deployment is performed by the authorized coordinator.
