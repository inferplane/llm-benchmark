# TAT-QA 200-question validation

This directory records verification of the new frozen TAT-QA test subset and static dashboard. Raw candidate responses and immutable execution manifests live in `results/tatqa/`; the published report lives in `docs/tatqa-results/`.

The official source is NExTplusplus/TAT-QA revision `870accc41953dcde885aabeb963d94aabdc0fbc3` (ACL 2021). Its released test gold contains 1,663 questions from 277 distinct table/paragraph contexts. The new sample contains 200 questions from 200 distinct contexts, with proportional answer-type quotas: span 86, arithmetic 84, multi-span 25, count 5. Context IDs do not establish independent companies or full annual-report documents.

The benchmark uses the pinned official EM/F1 evaluator with a strict JSON adapter. Formatting/request/missing/truncation failures retain the scheduled denominator. No judge API, model-generated references, answer repair or favorable reranking is used. Existing decoding/reasoning settings from config.toml are preserved and frozen.

`cost-estimate.json` is a pre-execution heuristic only. Final report costs use recorded tokens and frozen configured model rates; billing, retries and service integration costs may differ.

Deployment requires independent code review, a content-review PASS with score at least85/100, successful selfchecks and browser validation on actual results. Existing FinQA20, translation and model media artifacts remain separate.

The completed `tatqa-api-200-20261027` run covers 35 API models, including GPT-6.1 Terra, with 200 questions each. All 7,000 scheduled model/question pairs have final responses: 6,811 are scoreable and 189 invalid responses score zero. There are no final missing, failed or truncated responses. The 7,001 append-only attempt rows retain one Grok 4.6 timeout that succeeded under the existing transport retry policy. No candidate answers were regenerated to improve their scores.

`results-verification.json` binds the independently verified counts, gold round-trips, full-denominator scores and configured-rate costs to the final report hash. `verify_live.py` compares the published Pages assets byte-for-byte with the reviewed local files after deployment.

Published through [PR #20](https://github.com/inferplane/llm-benchmark/pull/20) at https://inferplane.github.io/llm-benchmark/tatqa.html. The Pages build/deployment completed successfully; `live-verification.json` confirms all eight published assets match the reviewed files. `live-browser.json` and `live-375.png` / `live-1280.png` record live interaction and responsive checks without browser errors. Rerun with `uv run python validation/tatqa-200/verify_live.py` and `node validation/tatqa-200/live-browser-check.cjs`.

The vendored `tatqa_utils.py` is byte-identical to the pinned upstream source, including an upstream blank line at EOF. Preserve its frozen hash; the staged whitespace check excludes that file and checks all other additions.
