# Gemma Bedrock Lotte — narrow independent review

**REVIEW93/100, Critical0, Warnings4. Source is not yet publication-approved.**

Exact original source: `ad75231b7bb555c041dd03249f343c31fdda9b79b2700e5d6cdcbf7652d64827`. Requested/reported model: `google.gemma-4-31b`. The original response bytes match. No model code was edited.

Initialization and all four drawing clicks now work without errors. Four stages produce real3D geometry, completed bounds reach555, camera keys/reset work, and reduced-motion startup is static. Required task features are present.

Remaining precise fixes:

- `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:86` — Diagram labels, model information and keyboard hints remain16px; the SVG555m annotation renders below19px. Fix: Use at least19px meaningful rendered text, including diagram labels/annotations or readable equivalents.
- `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:136` — The four focusable diagramDIVs have onclick only. Actual Enter/Space tests leave the camera unchanged, while clicking changes it. Fix: Use native buttons or implement Enter/Space activation consistently for all four diagram controls.
- `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:262` — The initial/reset camera crops the crown of the555-high model; the1280px screenshot shows the upper tower outside the view. Fix: Fit the whole model in its initial/reset pose while preserving your own visual treatment.
- `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:108` — At375px the tall nearly full-width overlay panel covers the3D model and its pointer surface. Scrolling the panel does not expose a usable model area. Fix: Adapt or collapse/reflow your own mobile controls so the3D model is visible and directly operable alongside accessible controls.

The user explicitly renewed the Gemma-only repair goal on2026-10-14; this is the first check in that authorized repair episode. Historical source/re-review counts remain preserved. A targeted same-author correction is authorized; no cohort rerun is required.

First-prompt fairness audit independently confirmed38models share one exact task text after full configured model_ID then model-name replacement: SHA`f64db398759d2ccccfb0129b9c3911bfb2d8c5d3cc1ec747f641f66044fef46e`. Initial requested output caps differ:18×8192,16×16384,4×6144. Temperature/reasoning settings and later repair histories also differ. This supports “same initial task body apart from identity,” not a controlled one-shot comparison of repaired final outputs.

Browser evidence: `/tmp/model-lotte-review/gemma-4-31b-bedrock/ad75231b7bb5/browser.json` and `browser-targeted-gemma.json`; desktop/mobile screenshots in the same frozen directory.
