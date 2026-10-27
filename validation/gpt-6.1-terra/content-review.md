# Terra content review

Reviewed 2026-10-27T04:12:32.385419+00:00. Overall verdict: **PASS**. Original generated source was preserved.

| Artifact | Score / 100 | Critical | Warnings | Verdict |
| --- | ---: | ---: | ---: | --- |
| whoami | 98.5 | 0 | 1 | PASS |
| lotte-tower | 97.5 | 0 | 2 | PASS |

Review uses AWS Content Plugin 3.0.5 content-review-agent’s fixed quarter-category deductions, rounded once per category to nearest 0.5 with exact midpoint upward. Verdict is the worst score, Critical and Warning band. All categories score full marks except Accessibility: portrait 3.5/5; tower 2.5/5. No deduction is made for non-applicable slide/workshop/AWS-branding requirements.

Both artifacts run inside temporary `sandbox="allow-scripts"` wrappers. Installed Playwright/Chromium tests used an offline context and exact three-URL allowlist: wrapper, original artwork, and the pinned local Three runtime. CSP blocks outbound connections and parent access. No server, API calls or external resource requests occurred. Production wrappers are outside this review.

Desktop 1440px, tablet 768px, phone 375px and a 720px zoom-reflow proxy had no horizontal overflow. Keyboard and touch controls work. The portrait stops animation for reduced motion. The tower is static between interactions, including reduced-motion mode.

The tower renders real indexed 3D meshes (6,565 surface vertices, 38,400 indices). Each of four stages has a different geometry hash. Pointer/keyboard/touch rotation and zoom change the camera; reset restores it. All four drawing tabs work. The selected-stage radius updates 3D, floor-plan, elevation and section outlines. `task_requirements_complete = true`.

The prompt’s 555m/123-floor/taper/pottery facts, conceptual-reconstruction and inferred-geometry caveats, and exact KPF/LERA source links are included. Source URLs were inspected as attribution, not fetched by the artwork. No official drawing or verified structural claim is made.

## whoami

Artwork SHA-256: `7108b1874290c93d69b135183826487f7b9b3c71d9637565864eb224e04d5631`. Matches its generation record.

Prompt: `results/model-self-portraits/generations/free-expression-20261012/gpt-6.1-terra/prompt.txt`.

Browser evidence: [desktop and responsive results](browser-review/whoami/browser.json), [touch results](browser-review/whoami/touch-browser.json), [phone](browser-review/whoami/view-375.png), [phone footer](browser-review/whoami/touch-mobile-footer.png).

### Warning 1: Accessibility

- Location: `docs/models/gpt-6.1-terra/whoami/artwork.html:106`.
- Exact quote: `.hint { margin: 0; color: var(--muted); font-size: .88rem; }`.
- Finding: The interaction hint and live status use 14.08px text; the description uses 15.2px and footer/model name uses 12px. These informative strings are below the review rubric’s 14pt (18.67px) target. They remain readable with browser enlargement and have strong contrast.
- Action: On an authorized model-authored revision, raise informative text and controls to at least 19px while retaining the current responsive reflow.
- Evidence: [touch-mobile-footer.png](browser-review/whoami/touch-mobile-footer.png).

### Source omission cross-check

| Recorded prompt requirement | Output status | Evidence |
| --- | --- | --- |
| Original self-expression using a chosen visual language and interaction | INCLUDED | Terrain/contour metaphor, pointer placement, seed/reset/pause controls. |
| Actual model name | INCLUDED | Footer displays gpt-6.1-terra; touch-mobile-footer.png. |
| Single offline HTML, phone/desktop and accessibility consideration | INCLUDED | Embedded CSS/JS, no external requests, responsive layout, keyboard buttons/live status, reduced-motion handler. Size warning remains. |

## lotte-tower

Artwork SHA-256: `fa3e0810db87b9f0c0f916e4f747d80cb65aad97b1bd4a73c31d964bd0e350ac`. Matches its generation record.

Prompt: `results/model-lotte-towers/lotte-tower-models-20261013/gpt-6.1-terra/prompt.txt`.

Browser evidence: [desktop and responsive results](browser-review/lotte-tower/browser.json), [touch results](browser-review/lotte-tower/touch-browser.json), [phone](browser-review/lotte-tower/view-375.png), [phone footer](browser-review/lotte-tower/touch-mobile-footer.png).

### Warning 1: Accessibility

- Location: `docs/models/gpt-6.1-terra/lotte-tower/artwork.html:80`.
- Exact quote: `font-size="10"`.
- Finding: SVG drawing labels are 10 SVG units and render at 5.6167 CSS pixels on the 375px phone viewport (337px-wide SVG / 600-unit viewBox). Essential disclosures, control instructions and source notes elsewhere also use 11–12px text. Tiny drawing labels make dimensions and conceptual notes hard to read without magnification.
- Action: On an authorized model-authored revision, use responsive drawing label sizing or a keyboard/touch-accessible drawing zoom; make informative surrounding text at least 19px and diagram labels at least 12px at the displayed scale.
- Evidence: [drawing-mobile-375.png](browser-review/lotte-tower/drawing-mobile-375.png).

### Warning 2: Accessibility

- Location: `docs/models/gpt-6.1-terra/lotte-tower/artwork.html:80`.
- Exact quote: `fill="#66817b"`.
- Finding: The common SVG label color #66817b on #f8faf7 has 4.009:1 contrast, below 4.5:1 for small normal text. The unselected stage number color #79918a on #f8faf8 is 3.214:1; muted #647478 on paper #f4f2eb is 4.348:1.
- Action: On an authorized model-authored revision, darken these informative text colors to reach at least 4.5:1 against their actual backgrounds.
- Evidence: [drawing-section.png](browser-review/lotte-tower/drawing-section.png).

### Source omission cross-check

| Recorded prompt requirement | Output status | Evidence |
| --- | --- | --- |
| 555m, 123 above-ground floors, taper, KPF Korean pottery inspiration | INCLUDED | Lines 39, 72–74; dimensions/height and phase descriptions. |
| Conceptual reconstruction disclaimer and inferred dimensions/members | INCLUDED | Lines 43, 54, 62, 84, 88, 99–100 explicitly qualify site, plans, core, facade and invented history. |
| KPF and LERA attribution | INCLUDED | Line 62 contains the exact supplied URLs and credits original/structural designers. URLs are text links, never fetched. |
| Site, typical floor plan, elevation and section, unit/basis | INCLUDED | Four working tabs; no-scale/metres note; changing description and basis text. Phone legibility warning remains. |
| Design process and 3D form of every phase | INCLUDED | Four stage buttons select distinct indexed 3D surface geometries. |
| Finished building as an actual 3D model with rotate/zoom/reset | INCLUDED | Stage 04 is a real Three.js mesh with tapered body, facade lines and crown. Pointer, keyboard and touch gestures update camera; reset restores it. It is correctly described as an approximate conceptual reconstruction, not a surveyed replica. |
| Correspondence between drawings, selected phase and finished model | INCLUDED | Shared stage radius drives 3D body, floor-plan size, elevation and section outlines; selected stage labels and drawings update together. Site base is unchanged because the base radius is unchanged. |
| Single HTML/local allowed runtime/offline sandbox/mobile/name/accessibility | INCLUDED | Embedded CSS/JS, only pinned local runtime request, no parent access/dialog/API, mobile/keyboard/reduced-motion support, visible footer model name. |

## Gate conclusion

Both current hashes satisfy score ≥85, Critical = 0 and Warnings ≤3. No mandatory repair is needed for this gate. Accessibility warnings are recorded for a future authorized model-authored revision. This report does not certify engineering accuracy, production wrappers or a live external-source review.
