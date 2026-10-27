# Terra delivery browser verification

Overall verdict: **PASS**. Seven delivery routes and all six new translation selections were verified. No production file was changed by the reviewer.

| Surface | Result |
| --- | --- |
| Model catalog and Terra model home | PASS |
| Portrait and tower production wrappers | PASS |
| Financial QA dashboard and standalone Terra report | PASS |
| Translation default, six run selectors, two sample tracks, timing disclosure | PASS |

All seven pages loaded without JavaScript/console errors, console warnings, failed/blocked requests or horizontal overflow at desktop 1280px, tablet 768px and phone 375px. The tests ran in offline Playwright/Chromium with an explicit local-file allowlist and a SHA-256-verified CDN/font cache; 29 cached third-party URLs were served from disk during dashboard tests, with no external network access. Original artwork retained `sandbox="allow-scripts"` and restrictive CSP with the pinned local Three runtime. Every served local file hash still matches the current final file.

## Gallery and financial QA

Catalog search/family filtering and empty state work. Terra home links to both tasks and displays their recorded costs. Both wrappers render their original canvases; the tower loads local Three.js revision 186 without fallback. Prompt dialogs exactly match recorded text and show the correct hash. Cost dialogs show $0.017889/$0.040506 and one recorded attempt, mark them as estimates, and disclose exclusions. Keyboard opening, modal background blocking, Escape dismissal and focus restoration pass at all three viewport sizes.

Financial QA defaults to `finqa-gpt-6.1-terra-20261027`, lists 32 models and displays Terra’s 19/20 (95%) result. All 20 questions are available. Selecting Terra and changing the question displays actual answers; calculation disclosure opens. Volume recalculation, invalid-volume feedback, cost sorting and standalone report links work.

## Translation dashboard

The default is `en-pivot-20261027-judge2`, with 40 models, the synthetic financial-document track and all comparison cohorts. Terra’s table row renders and its detail button expands. The inspector contains 196 samples.

The following six selectors each render Terra’s model row and actual translations for both a FLORES sentence and a financial document. Financial samples use the report’s document types (`disclosure`, `earnings`, `fund`, `terms`), rather than a literal `synthetic` document type.

| Run | Terra translated / judged | Samples |
| --- | ---: | ---: |
| `bedrock-gpt-6.1-terra-20261027` | 3,300 / 3,300 | 210 |
| `en-pivot-gpt-6.1-terra-20261027` | 3,080 / 3,080 | 196 |
| `en-pivot-gpt-6.1-terra-20261027-judge2` | 3,080 / 3,080 | 196 |
| `integrated-2026-10-27` | 3,300 / 3,300 | 210 |
| `en-pivot-20261027` | 3,080 / 3,080 | 196 |
| `en-pivot-20261027-judge2` | 3,080 / 3,080 | 196 |

Switching general/combined/financial tracks updates the visible row. The Korean integrated run remains available as `integrated-2026-10-27` with Terra included; it does not replace the default English report.

The exact scheduling note is present in all six report interpretations and in Terra’s `measurement_scheduling`. Opening the existing **측정 기록과 해석** disclosure makes it readable in every selection, including on phones. That disclosure is collapsed on initial load. The note explains that Korean/English collection overlapped, that each job’s concurrency was 8 while the shared service received concurrent requests, and that latency/throughput observations are limited for comparison with isolated-load experiments. [Phone timing-note evidence](delivery-review-translation-caveat-mobile.png).

## Recorded warnings and evidence

The already-passing original-artwork accessibility warnings from [content-review.md](content-review.md) remain: small informative text, and tiny/low-contrast tower drawing labels. No new delivery defect was found.

Evidence: [gallery/QA browser results](delivery-browser.models-financial-qa.json), [translation browser results](delivery-browser.translation.json), [translation sample screenshot](delivery-review-translation-sample-desktop.png), [delivery summary](delivery-review.json). The local [offline probe](delivery-browser.cjs) records exact used local and cached resource hashes. This is a local delivery smoke review; live GitHub Pages/CDN propagation is outside its scope.
