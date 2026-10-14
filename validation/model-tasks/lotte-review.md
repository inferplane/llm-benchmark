# Model-authored Lotte pages — final raw-source review

**Full requested raw-artwork batch: FAIL / not ready for release. Full-task PASS: 19/38.**

Latest invocation outcomes: {'failed': 2, 'generated': 36}. Current generated-source bands: {'PASS': 20, 'REVIEW': 5, 'FAIL': 11}. The extra numerical PASS is task-incomplete (NemotronSuper stage mapping produces the same default shape).

These are fixed content-quality gates, not model-performance scores or a ranking. A missing required feature is tracked separately by task_requirements_complete. No authoredHTML was edited or substituted.

All 36 current generatedHTML files exactly match their recorded actual response bytes, SHA and configured request model. All 38 WHOAMI copies still match legacy originals and prior approved hashes. Sensitive-token/private-key pattern scan found no matches.

Two current generation failures: native Qwen3.6 returned output-budget-truncated responses without a saved complete artwork; Ministral latest extraction failed. Historical reviewedMinistralHTML is not a substitute for its current failed response.

| Model | Score | C | W | Verdict | Task complete | Re-reviews | Current source | SHA |
|---|---:|---:|---:|---|---|---:|---|---|
| claude-haiku-5.5 | 97.0 | 0 | 2 | PASS | True | 0 | True | 6fa8dd0377ec0fa0126a9c36e5ee26e90bf6081f9fadbfa5255217d6e65dd7d5 |
| claude-sonnet-5.5 | 95.0 | 0 | 3 | PASS | True | 0 | True | c32619e9452fed1799a24cdae0fd1009ceb37a84980a68a1a090338d0eb49b96 |
| gpt-6-luna | 95.5 | 0 | 3 | PASS | True | 0 | True | eb91cfece23b88e320d67aaa9c2c64eeda369c4431753a183c2e61612b272c03 |
| gpt-6-astra | 98.5 | 0 | 1 | PASS | True | 0 | True | 1a63c36d8a5afe4350b75081558d423aacde800e05b98e2a443f68d934e6ee44 |
| gpt-6.1-sol | 98.5 | 0 | 1 | PASS | True | 0 | True | b8a72f232e47897520f7a7877aa07739aa1f3b3ee1444b4ad495faa4256502d5 |
| gpt-5.4 | 96.5 | 0 | 2 | PASS | True | 0 | True | a890fcea2c861a765a17a3c30b65a63a2c3e0c6c6910a457ca4de5d9e04347a1 |
| grok-4.6 | 95.5 | 0 | 3 | PASS | True | 0 | True | 22a2b24c90485c8d21ea910a62e94b2e077a10c96133010d258e196ba4eee7bf |
| claude-sonnet-4.5 | 97.0 | 0 | 2 | PASS | True | 0 | True | 9365500d8e1328917e9243bf413749061d9c5d3f6221b1d0df79f8bb3d37ed4d |
| claude-opus-5.5 | 98.5 | 0 | 1 | PASS | True | 0 | True | b6df342dbe57ded8493f9f174999b592f3f2f6b221c6392aa7be17cd80e7ab40 |
| claude-fable-5.1 | 97.0 | 0 | 2 | PASS | True | 0 | True | a722373a6f6dce9c0e1cdffb6f8901b18b50dc849747ce6ffb7d0a6353efefd1 |
| claude-haiku-4.5 | 94.5 | 0 | 3 | PASS | True | 2 | True | 78b4610c04f774f7b6e52688db0e63d81ba4cb2449ae96eebd9ad0384bb7af49 |
| claude-sonnet-5 | 96.5 | 0 | 2 | PASS | True | 2 | True | 3e1d73cc628cb9afa8e884c7f39e84b8833ef8a6b11fd1bf0837e292188e472b |
| gpt-5.5 | 97.0 | 0 | 2 | PASS | True | 2 | True | bd6bf561e86cc1c317cd36c8d1e3497c1a697ca50486b84bc97dfcadfafdecc1 |
| gpt-5.6-terra | 98.5 | 0 | 1 | PASS | True | 2 | True | b249a061ce6e569696f042377923429cf5750e9fcde911b2723f63c9a0a4c39b |
| grok-4.7 | 96.5 | 0 | 2 | PASS | True | 2 | True | 7be742b78f02b19dc517d29f5f964e6a3b6560c6b381a23ddf4b64d46d8c7f7c |
| llama-3.3-70b | 90.5 | 0 | 6 | REVIEW | False | 3 | True | a061dc832b7e06ecc97d03568baf5cf3098bd89829dd61f1eb9d721a9c914a94 |
| ministral-14b | 93.5 | 1 | 1 | FAIL | False | 2 | False | 95efdcf9dcb9f0fa1bf80555aefd9281515431cb189b665aa8a6e1d87f2f45dd |
| kimi-k3 | 96.5 | 0 | 2 | PASS | True | 1 | True | f6b3e5f9e477e077d685e4116106995497494ec9175c138732e1920da3bbe730 |
| llama-3.1-8b | 88.0 | 1 | 5 | FAIL | False | 3 | True | c32057471d5a335bc59e1a30c9a9315d8458f0138e6177005820c109f4a7d4c1 |
| gpt-5.6-luna | 96.5 | 0 | 2 | PASS | True | 3 | True | b3fe1ace6ee5c24279424d4703398deefaadfe5e3b6983e867be0bb7f98b917e |
| grok-4.3 | 96.5 | 0 | 2 | PASS | True | 3 | True | 2327445d2c0ca3e7a272336773aad75f154b207e622c076f86efab09bd964552 |
| glm-5.3 | 98.5 | 0 | 1 | PASS | True | 3 | True | 67c9eb19f5f24a94250275dac483baf325d6d988b887036e7ae46dd7be5d04b2 |
| nova-pro | 94.0 | 0 | 4 | REVIEW | False | 3 | True | f0f629b16c95906ac13780be02ff5ee6e2bb4af51458403689780b692aae373a |
| nova-lite | 88.5 | 1 | 4 | FAIL | False | 3 | True | 57e9c8515fbc8dc91f51f718b15f31855b3db1034103037986a261c1d0924f5f |
| nova-micro | 88.5 | 1 | 4 | FAIL | False | 3 | True | 5ebb6caba2c5f794c672836f213201676aa9a67a66ac2df64c9eb3e9fb7b4e7b |
| nemotron-nano-3-30b | 92.0 | 1 | 2 | FAIL | False | 3 | True | acc83a509b386bdc4f2335c08d3b474566d8e4e1ea9a5e146bd0428d16b15786 |
| glm-4.7-flash | 93.5 | 0 | 4 | REVIEW | False | 3 | True | 9586dab8a74cc49794579f440ff4b948d1e1a89b58fd306b98d584276e8c38a0 |
| gpt-oss-20b | 90.0 | 1 | 3 | FAIL | False | 3 | True | 5ee00c024bdde7e10751fe50cf8f6e87d3c7bcc8035d71a4a72a8085c0c62d0c |
| gpt-oss-120b | 92.0 | 1 | 2 | FAIL | False | 3 | True | 662f89790a2a605ec2222566ead92b12357a9f7992fddc1add1ecf63f13d412f |
| qwen3-32b | 90.5 | 1 | 3 | FAIL | False | 2 | True | 129863275742c51e3d06f0af0960d7a1997c40b3874e217eab2e499d3596c50f |
| nemotron-super-3-120b | 95.5 | 0 | 3 | PASS | False | 3 | True | a082bfe8a3bc35572b99259148f702cbb30a9ebad83da087812b308d06bc4982 |
| llama4-scout | 93.5 | 0 | 4 | REVIEW | True | 2 | True | a3b57bbea3622ba0ef514355fceb37db14506babefa82f0ed1501cb684731362 |
| qwen3-235b-a22b | 93.5 | 1 | 1 | FAIL | False | 3 | True | c361b11bdb85a58a3b14f046b484551db13809f92c864e4aad9d2934d8bda05c |
| llama4-maverick | 93.0 | 0 | 4 | REVIEW | True | 3 | True | 42a3ba1fe5ca0fea250d342d7488ddadfce5ba961d436a00202266659718173f |
| llama-3.3-70b-bedrock | 88.5 | 1 | 4 | FAIL | False | 3 | True | e67818ea849c028c22f5335f3a765d43a209a64804c2a516d35ac385f7de3052 |
| gemma-4-31b-bedrock | 93.0 | 0 | 4 | REVIEW | True | 3 | True | ad75231b7bb555c041dd03249f343c31fdda9b79b2700e5d6cdcbf7652d64827 |
| exaone-3.5-32b | 87.5 | 1 | 5 | FAIL | False | 3 | True | f810c39e19a7a8d6197f01194885f925449bb9bd6303710d59ed96219c2c096c |

## Current-generation failures (not assigned artifact scores)

- ministral-14b: failed, recordSHA591278e2031d97e6371912855172971757d586165a256cf9ccfb4f9a993aa053.
- qwen3.6-27b: failed, recordSHA08642fd0d20134a0a4c27687a5d13d32ecbcee6520474ff8b24dfda561d163c1.

## Release boundary

The common gallery/hub/prompt/cost UI separately passed100/C0/W0. This does not approve the non-PASS or task-incomplete originals. release_review_complete remains false until the unresolved scope is decided and the producer supplies a frozen/pruned candidate for final121-route and actual-artwork validation.

Three-re-review limits are recorded per model. Qwen32, Scout and GemmaBedrock have two successful-source re-reviews, rather than an invented third; failed API attempts are distinct from rendered source reviews. The producer declared managed paid repair calls stopped.

Explicit review procedure: `/home/atomoh/.codex/plugins/cache/oh-my-cloud-skills/aws-content-plugin/3.0.0/agents/content-review-agent.md`: "If PASS is still not reached after 3 re-reviews, hand the decision to the user". No repeated automatic repair is authorized for rows whose retry_limit_reached is true.

## claude-haiku-5.5 — PASS, task complete=True

- Warning / Accessibility: `docs/models/claude-haiku-5.5/lotte-tower/artwork.html:16` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Warning / Interactions: `docs/models/claude-haiku-5.5/lotte-tower/artwork.html:458` — With reduced motion enabled, the rotation button can announce rotation is on while animate() always suppresses it; the control state does not match the result. Action: Synchronize/disable/explain the existing auto-rotation control under reduced motion.
- Evidence: `/tmp/model-lotte-review/claude-haiku-5.5/6fa8dd0377ec/browser.json`
- Imported exact original pilot response, not a new billedrequest orhost-page substitute.
- Real3D, fourdrawings, selectedfloor markers andstage geometry are implemented. Actual buttons/keyboardcamera andmobileflow pass; no runtimeerrors.

## claude-sonnet-5.5 — PASS, task complete=True

- Warning / Accessibility: `docs/models/claude-sonnet-5.5/lotte-tower/artwork.html:13` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Warning / Layout: `docs/models/claude-sonnet-5.5/lotte-tower/artwork.html:170` — The initial/reset camera clips the top of the completed555-unit tower rather than framing the whole building. Action: Choose a home pose/distance that shows the completedconcept within its viewport.
- Warning / Data Accuracy and References: `docs/models/claude-sonnet-5.5/lotte-tower/artwork.html:76` — The caption estimates topwidth20m, but rad(1)=16 produces32m diameter in the actual finalshape and its linked views. Action: Keep your assumed dimension labels consistent with your own geometry; no officialdimension is required.
- Evidence: `/tmp/model-lotte-review/claude-sonnet-5.5/c32619e9452f/browser.json`
- Imported exact original response. Fiveactualgeometry stages, fourdrawings andcamera controls execute without consoleerrors.
- Conceptual geometry quality is recorded as a content warning, not a modelbenchmark score.

## gpt-6-luna — PASS, task complete=True

- Warning / Accessibility: `docs/models/gpt-6-luna/lotte-tower/artwork.html:17` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Warning / Interactions: `docs/models/gpt-6-luna/lotte-tower/artwork.html:297` — The +/zoomIn action calls dollyIn(1.2), increasing camera distance;−calls dollyOut(1.2), decreasing it. The labeled directions are reversed. Action: Make positivezoom enlarge andnegativezoom reduce, including the keyboard equivalents.
- Warning / Data Accuracy and References: `docs/models/gpt-6-luna/lotte-tower/artwork.html:124` — The SVG elevation/section bulge outward above a narrowbase and end at a point, whereas the3D is a monotonic flat-topped frustum; the displayed drawings do not correspond to the described same model. Action: Align your own drawing outlines with your own3Dconcept or clearly distinguish an intentionally different sketch.
- Evidence: `/tmp/model-lotte-review/gpt-6-luna/eb91cfece23b/browser.json`
- PinnedOrbitControls0.186.1 does contain the publicmethods used here; no nonexistent-method error is claimed.
- Real3D, stagechanges, pointercamera/keyboard/buttons andnewrelative runtime route pass with0errors.

## gpt-6-astra — PASS, task complete=True

- Warning / Accessibility: `docs/models/gpt-6-astra/lotte-tower/artwork.html:9` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Evidence: `/tmp/model-lotte-review/gpt-6-astra/1a63c36d8a5a/browser.json`
- Imported exactoriginal. Fouractual drawingviews, stage geometry, selectedfloor markings andtwo3D views are coherentlyimplemented with explicitassumptions.
- Pointerdrag, keyboardcamera, reset/zoom buttons andresponsiveflow pass. No automaticmotion is imposed; event-driven rendering is valid.

## gpt-6.1-sol — PASS, task complete=True

- Warning / Accessibility: `docs/models/gpt-6.1-sol/lotte-tower/artwork.html:9` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Evidence: `/tmp/model-lotte-review/gpt-6.1-sol/b8a72f232e47/browser.json`
- Imported exactoriginal; correctnewtask-depth runtime resolves. Maincamera controls and keyboard work; thumbnails are not mistaken for the interactive mainviewport.
- Fourdrawingtypes, actualstagegeometry andfloor-level markers arepresent; conceptualdimensions are labeled. No consoleerrors or horizontaloverflow.

## gpt-5.4 — PASS, task complete=True

- Warning / Accessibility: `docs/models/gpt-5.4/lotte-tower/artwork.html:65` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Warning / Layout: `docs/models/gpt-5.4/lotte-tower/artwork.html:601` — The initial/reset camera is too close/low for the555-unit model, showing a croppedwall instead of the full tower silhouette. Action: Fit the home view to the complete conceptualbuilding while retaining your chosen perspectives.
- Evidence: `/tmp/model-lotte-review/gpt-5.4/a890fcea2c86/browser.json`
- Actualfourdrawings, stages/floor correspondence, compareview, zoom/reset andkeyboard-accessible presetbuttons function.
- Zero script/networkerrors andno pagehorizontaloverflow in allthree testedwidths.

## grok-4.6 — PASS, task complete=True

- Warning / Accessibility: `docs/models/grok-4.6/lotte-tower/artwork.html:30` — Meaningful descriptions, controls and/or drawing labels render below19px. Action: Use at least19px readable informative text while preserving your own layout.
- Warning / Accessibility: `docs/models/grok-4.6/lotte-tower/artwork.html:306` — Rotation has no keyboard-equivalent controls or focusable camera handler; the nativebuttons cover zoom/reset only. Action: Provide keyboard-operable rotation in your existingviewer.
- Warning / Layout: `docs/models/grok-4.6/lotte-tower/artwork.html:305` — The initial/reset pose crops the upperpart of the555-unit tower; zoomingout is required to reveal its whole silhouette. Action: Provide a home view that frames the completedconcept.
- Evidence: `/tmp/model-lotte-review/grok-4.6/22a2b24c9048/browser.json`
- Actualdrawing package andstagegeometry exist, andpointerorbit/wheel pluszoom/reset buttons run with0consoleerrors.
- Rendering strategy andshapechoices are preserved; no benchmarking/ranking score assigned.

## claude-sonnet-4.5 — PASS, task complete=True

- Warning / Readability: `docs/models/claude-sonnet-4.5/lotte-tower/artwork.html:35` — Informative captions and controls use 12–16px text below the 19px review minimum. Action: Increase meaningful text and controls to at least 19px while preserving the composition.
- Warning / Accessibility: `docs/models/claude-sonnet-4.5/lotte-tower/artwork.html:783` — Arrow keys move the camera, but zoom is available only through pointer/touch input. Action: Add a keyboard-accessible zoom operation; preserve existing arrow and reset controls.
- Evidence: `/tmp/model-lotte-review/claude-sonnet-4.5/9365500d8e13/browser.json`
- Actual four canvas drawings and five 3D stages render without script errors. Vertically scrollable layout is reachable at 375/768/1440.

## claude-opus-5.5 — PASS, task complete=True

- Warning / Readability: `docs/models/claude-opus-5.5/lotte-tower/artwork.html:14` — Informative captions and controls use 12–16px text below the 19px review minimum. Action: Increase meaningful text and controls to at least 19px while preserving the composition.
- Evidence: `/tmp/model-lotte-review/claude-opus-5.5/b6df342dbe57/browser.json`
- Four SVG drawings, stage/floor controls, keyboard rotation, zoom and reset function; 375/768/1440 show no horizontal overflow. Reduced-motion startup is static; auto rotation starts only on explicit user action. This current successful response is a new authored result, not the earlier imported failed response.

## claude-fable-5.1 — PASS, task complete=True

- Warning / Readability: `docs/models/claude-fable-5.1/lotte-tower/artwork.html:13` — Informative captions and controls use 12–16px text below the 19px review minimum. Action: Increase meaningful text and controls to at least 19px while preserving the composition.
- Warning / Accessibility: `docs/models/claude-fable-5.1/lotte-tower/artwork.html:150` — Canvas arrow-key handling is attached through listenToKeyEvents, but neither viewer has a keyboard-accessible zoom operation. Action: Provide keyboard or native-button zoom controls for both viewers.
- Evidence: `/tmp/model-lotte-review/claude-fable-5.1/a722373a6f6d/browser.json`
- Both real 3D viewers and four SVG drawings operate; steps and floor markers update. Reduced-motion suppresses continuous auto rotation; explicit one-step rotation is preserved.

## claude-haiku-4.5 — PASS, task complete=True

- Warning / Readability: `docs/models/claude-haiku-4.5/lotte-tower/artwork.html:115` — Some meaningful UI/diagram annotations render below19px, including fixed-size drawing labels scaled down on mobile. Action: Keep meaningful text at least19px at its rendered size; adapt labels or provide readable HTML equivalents.
- Warning / Layout: `docs/models/claude-haiku-4.5/lotte-tower/artwork.html:691` — Initial/reset view is too close to contain the555-unit tower; its top is outside the viewport. Action: Fit the entire tower in the home/reset view at desktop and mobile sizes.
- Warning / Layout: `docs/models/claude-haiku-4.5/lotte-tower/artwork.html:126` — At375px the page has horizontal overflow in its drawing/stage layout. Action: Fit cards/canvases and controls within the available mobile width without losing text.
- Evidence: `/tmp/model-lotte-review/claude-haiku-4.5/78b4610c04f7/browser.json`
- Second re-review of revised source (iteration3) with full original brief restored. Actual response bytes/model identity matched, offline375/768/1440 tested; no source edits.
- Restored actual spatial mesh, four drawn diagrams, four geometry stages, native camera buttons and keyboard. Initial motion is static.

## claude-sonnet-5 — PASS, task complete=True

- Warning / Readability: `docs/models/claude-sonnet-5/lotte-tower/artwork.html:168` — Some meaningful UI/diagram annotations render below19px, including fixed-size drawing labels scaled down on mobile. Action: Keep meaningful text at least19px at its rendered size; adapt labels or provide readable HTML equivalents.
- Warning / Layout: `docs/models/claude-sonnet-5/lotte-tower/artwork.html:390` — The reset framing is too close/low for the full completed90-unit body plus14-unit crown. Action: Fit the complete authored model in the home/reset pose.
- Evidence: `/tmp/model-lotte-review/claude-sonnet-5/3e1d73cc628c/browser.json`
- Second re-review of revised source (iteration3) with full original brief restored. Actual response bytes/model identity matched, offline375/768/1440 tested; no source edits.
- Four drawings and real geometric stages restored. Shift+Up/Down supplies keyboard zoom; regular arrows orbit, native reset works. Reduced-motion startup is static.

## gpt-5.5 — PASS, task complete=True

- Warning / Readability: `docs/models/gpt-5.5/lotte-tower/artwork.html:53` — Some meaningful UI/diagram annotations render below19px, including fixed-size drawing labels scaled down on mobile. Action: Keep meaningful text at least19px at its rendered size; adapt labels or provide readable HTML equivalents.
- Warning / Accessibility: `docs/models/gpt-5.5/lotte-tower/artwork.html:306` — The model rotates continuously in normal mode, but no user stop/resume control is provided. Reset and camera controls do not stop that motion. Action: Add an accessible motion toggle and preserve its state during camera/stage changes.
- Evidence: `/tmp/model-lotte-review/gpt-5.5/bd6bf561e86c/browser.json`
- Second re-review of revised source (iteration3) with full original brief restored. Actual response bytes/model identity matched, offline375/768/1440 tested; no source edits.
- Four SVG diagrams and five3D stages restored, actual full model fits camera, crown stays within555, all camera buttons and shortcuts execute. Reduced-motion starts static.

## gpt-5.6-terra — PASS, task complete=True

- Warning / Readability: `docs/models/gpt-5.6-terra/lotte-tower/artwork.html:53` — Some meaningful UI/diagram annotations render below19px, including fixed-size drawing labels scaled down on mobile. Action: Keep meaningful text at least19px at its rendered size; adapt labels or provide readable HTML equivalents.
- Evidence: `/tmp/model-lotte-review/gpt-5.6-terra/b249a061ce6e/browser.json`
- Second re-review of revised source (iteration3) with full original brief restored. Actual response bytes/model identity matched, offline375/768/1440 tested; no source edits.
- Four diagrams, actual staged tapered mesh, complete555=509+46 geometry, camera presets/keyboard zoom and rotation, responsive sizing and reduced-motion suppression verified. Stages3/4 intentionally share final geometry with final-view explanation; no prescribed style demanded.

## grok-4.7 — PASS, task complete=True

- Warning / Readability: `docs/models/grok-4.7/lotte-tower/artwork.html:99` — Some meaningful UI/diagram annotations render below19px, including fixed-size drawing labels scaled down on mobile. Action: Keep meaningful text at least19px at its rendered size; adapt labels or provide readable HTML equivalents.
- Warning / Layout: `docs/models/grok-4.7/lotte-tower/artwork.html:157` — Reset camera distance with38°vertical field does not contain the555-high completed model; the extremes are cropped. Action: Fit complete geometry to the actual canvas bounds in the default/reset pose.
- Evidence: `/tmp/model-lotte-review/grok-4.7/7be742b78f02/browser.json`
- Second re-review of revised source (iteration3) with full original brief restored. Actual response bytes/model identity matched, offline375/768/1440 tested; no source edits.
- Four diagrams and actual staged lathe model restored; source profile matches diagram curve and total555m. Reduced-mode keyboard updates orientation correctly; all native controls execute.

## llama-3.3-70b — REVIEW, task complete=False

- Warning / Structural Completeness: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:129` — Every referenced vertex index has offset0–3 in an8-vertex block, and all those vertices have y=0. The height-bearing vertices4–7 are never indexed, so the completed model is a flat ground mesh, not the required555m tower. Action: Build valid surface indices that use successive elevated rings; verify the referenced mesh has a real nonzero vertical extent and matches its drawings.
- Warning / Structural Completeness: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:62` — The diagram package remains generic rectangles: elevation is three separate bars and section is three squares, with no coherent tower/site/floor/section geometry. Action: Render four meaningful distinct diagrams tied to the authored spatial model and stages.
- Warning / Data Accuracy and References: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:65` — New site500×500m and floor80×80m dimensions are presented without identifying them as unverified conceptual assumptions. Action: Label unsupported dimensions as assumptions, keeping555m/123floors distinct as supplied public facts.
- Warning / Layout: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:16` — The vertically centered fixed-height container is shorter than its mobile contents; panels extend above the reachable start and labels overflow their180pxSVG frames. Action: Use content-sized responsive/scrollable layout and fit diagram annotations inside their rendered bounds.
- Warning / Layout: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:151` — Camera aspect uses full window height while the rendered canvas is70%window height, distorting the projection at every viewport. Action: Calculate camera aspect from the actual rendered width/height used by renderer.setSize.
- Warning / Interactions: `docs/models/llama-3.3-70b/lotte-tower/artwork.html:175` — Zoom still changes world z after arbitrary orbit, rather than camera-to-target distance, without synchronizing controls; view direction can shift away from the object. Action: Zoom along the target-relative camera vector and update controls. Restore the full home camera/target on reset, including after panning.
- Evidence: `/tmp/model-lotte-review/llama-3.3-70b/a061dc832b7e/browser.json`
- Third re-review/iteration4. SHAa061dc832b7e06ecc97d03568baf5cf3098bd89829dd61f1eb9d721a9c914a94; browser0script errors, localWebGL executes, stage buttons change geometry.
- All final index references select only y=0 vertices; this is a concrete mesh-generation defect, not an aesthetic judgment.
- Three-re-review limit reached. Do not automatically request further same-author paid repair; user decision required. Task remains incomplete and publication gate closed for this model.

## ministral-14b — FAIL, task complete=False

- Critical / Renders: `docs/models/ministral-14b/lotte-tower/artwork.html:531` — The simulated runtime defines window.OrbitControls but calls new THREE.OrbitControls; it throws before rendering. The bundled local runtime is never loaded. Action: Use ../runtime/three-runtime.js and real THREE.OrbitControls; remove the incomplete substitute runtime rather than aliasing an incompatible stub. Retest all render/control methods.
- Warning / Readability: `docs/models/ministral-14b/lotte-tower/artwork.html:62` — Meaningful UI/diagram text is below19px at rendered size. Action: Make meaningful text and diagram labels at least19px on mobile/desktop.
- Evidence: `/tmp/model-lotte-review/ministral-14b/95efdcf9dcb9/browser.json`
- Current stable original bytes and actual model identity verified; isolated browser375/768/1440 and source review. Re-review number is computed from previously reviewed successful source revisions, not failed/truncated API attempts.
- The long source includes real drawing/stage intentions, but they cannot be called verified complete while actual rendering fails.

## kimi-k3 — PASS, task complete=True

- Warning / Readability: `docs/models/kimi-k3/lotte-tower/artwork.html:45` — SVG dimension/label text uses15–16px, below the19px review minimum. Action: Increase meaningful rendered diagram labels to19px or provide equivalent readable annotations.
- Warning / Layout: `docs/models/kimi-k3/lotte-tower/artwork.html:17` — At375px the drawing panel/tab row extends beyond the viewport; the fourth tab and right diagram content are clipped from the initial width. Action: Allow grid children/drawing regions to shrink or use deliberately accessible scrolling without clipped controls/content.
- Evidence: `/tmp/model-lotte-review/kimi-k3/f6b3e5f9e477/browser.json`
- First re-review/iteration2; syntax defect and missing final initialization are fixed in the actual model response.
- Four real SVG drawings, five distinct3D development stages plus completed model, linked drawing/stage selections, actual drag/wheel, native zoom/reset and focused keyboard controls are implemented and execute without console errors.
- Reduced-motion suppresses automatic camera rotation; source/reference/assumption disclosures remain explicit. Actual current requested/reported model identity and response bytes match.
- Exact SHA f6b3e5f9e477e077d685e4116106995497494ec9175c138732e1920da3bbe730. Mobile warning visually confirmed in view-375.jpg.

## llama-3.1-8b — FAIL, task complete=False

- Critical / Renders: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:81` — The pinned runtime has no CanvasRenderer; construction throws THREE.CanvasRenderer is not a constructor before controls or animation initialize. Action: Use supported local rendering APIs and real2Dcanvas contexts for diagrams, initialize actual scene geometry before rendering, and verify all controls.
- Warning / Structural Completeness: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:113` — All four drawing renderers are intended to render the identical scene/camera, with no distinct site/floor/elevation/section drawing content; inner canvases appended inside canvas elements would remain fallback content. Action: Render four meaningful distinct diagram views directly into their visible canvases or SVG, with labels/units/model correspondence.
- Warning / Structural Completeness: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:158` — The four states swap a cylinder, plane and two offset cubes rather than showing an explained3D development process leading to the completed tower. Action: Implement actual intermediate tower forms and a completed stage with understandable explanations.
- Warning / Data Accuracy and References: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:188` — The purported tower remains an untapered500-unit cylinder, inconsistent with the supplied upward-narrowing555m form. Action: Build the coherent authored tapering tower at a stated555m scale and align diagrams.
- Warning / Interactions: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:133` — Every camera handler calls updateScene, which immediately restores fixed cameraPosition/lookAt, undoing Zoom/Orbit/Tilt/Pointer changes. Action: Keep camera state separate from geometry updates; apply actual target-relative camera operations and reset only on explicit reset.
- Warning / Readability: `docs/models/llama-3.1-8b/lotte-tower/artwork.html:14` — Native buttons retain the browser default~13px font despite19px body/control-container text. Action: Explicitly set button and other meaningful control text to at least19px.
- Evidence: `/tmp/model-lotte-review/llama-3.1-8b/c32057471d5a/browser.json`
- Third re-review/iteration4. ExactSHA c32057471d5a335bc59e1a30c9a9315d8458f0138e6177005820c109f4a7d4c1. Browser reproduces unsupported CanvasRenderer constructor failure.
- Three-re-review limit reached, task incomplete. Stop automatic paid repair for this native model and require a bundled user decision. Raw author bytes remain untouched.

## gpt-5.6-luna — PASS, task complete=True

- Warning / Interactions: `docs/models/gpt-5.6-luna/lotte-tower/artwork.html:41` — camera is assigned globally rather than declared locally inside makeWorld; both render loops use the final viewer camera. Stage-viewer ArrowRight has no visible effect; final-viewer ArrowRight moves both views. Action: Give each viewer its own locally declared camera and keep controls/render/resize bound to that camera.
- Warning / Layout: `docs/models/gpt-5.6-luna/lotte-tower/artwork.html:41` — Initial/reset framing is too close/low to contain the full55-unit tower. Action: Fit complete model bounds in the initial/reset view for both canvases.
- Evidence: `/tmp/model-lotte-review/gpt-5.6-luna/b3fe1ace6ee5/browser.json`
- Third re-review/iteration4 of the original author repair. Exact response bytes, original model identity and successful runtime were verified.
- The previously empty completed viewer is now built; complete-model pointer/keyboard controls and corrected zoom directions work. Four drawings and progressive3D states exist. The separate stage-viewer camera regression remains a Warning; it does not remove the required completed-model interaction.
- browser-camera-alias.json confirms sharedCamera=true, unchanged pose after stage key, changed pose after final key. Declared CSS-size label compensation and readable HTML descriptions address the previous small-text root.

## grok-4.3 — PASS, task complete=True

- Warning / Readability: `docs/models/grok-4.3/lotte-tower/artwork.html:24` — Disclosure text remains16px, and diagram annotations can scale below19px. Action: Keep meaningful text/annotations at least19px rendered size.
- Warning / Layout: `docs/models/grok-4.3/lotte-tower/artwork.html:182` — Stage projection places its positive520-unit base below the usable600px stage frame; parts of the intermediate forms are cropped. Action: Fit the full intermediate geometry within its stage viewport while preserving the projection style.
- Evidence: `/tmp/model-lotte-review/grok-4.3/2327445d2c0c/browser.json`
- Third re-review/iteration4 of the original author repair. Exact response bytes, original model identity and successful runtime were verified.
- Both final and intermediate states now use realx/y/z geometry and actualx/y rotation. Four drawing views, keyboard/touch/pointer orbit, zoom and reset are implemented; browser0errors, responsive page has no horizontal overflow.
- Custom Canvas perspective projection is accepted as actual3D; WebGL is not required. Schematic drawing quality is not treated as a missing feature.

## glm-5.3 — PASS, task complete=True

- Warning / Data Accuracy and References: `docs/models/glm-5.3/lotte-tower/artwork.html:214` — The profile narrows to its middle then expands to0.495 at the top, nearly its0.5base width, contrary to the stated upward-narrowing form. Action: Use a coherent upward-narrowing profile and keep its schematic elevation/section consistent.
- Evidence: `/tmp/model-lotte-review/glm-5.3/67c9eb19f5f2/browser.json`
- Third re-review/iteration4 of the original author repair. Exact response bytes, original model identity and successful runtime were verified.
- Previous four controlling issues are fixed:555m includes the40m crown, both viewers resize from actual bounds, diagram labels use CSS-pixel text, and both canvases have keyboard orbit/zoom/reset. Four diagrams and five geometric states exist; no console errors at375/768/1440.
- Remaining conceptual shape inaccuracy is a Warning, not a benchmark score or a requirement for shared host geometry. Required task features are present and operate.

## nova-pro — REVIEW, task complete=False

- Warning / Structural Completeness: `docs/models/nova-pro/lotte-tower/artwork.html:46` — The four actual site/floor/elevation/section diagrams remain missing or placeholders. Action: Render meaningful distinct diagram content with model correspondence and labelled units/assumptions.
- Warning / Structural Completeness: `docs/models/nova-pro/lotte-tower/artwork.html:63` — No explained intermediate3D development states are implemented. Action: Provide distinct explained3D forms leading to completion and link them to the drawings.
- Warning / Data Accuracy and References: `docs/models/nova-pro/lotte-tower/artwork.html:63` — Top radius5 is larger than bottom2.5: the tower widens upward, contrary to the supplied form. Action: Use coherent upward narrowing and matching drawings.
- Warning / Layout: `docs/models/nova-pro/lotte-tower/artwork.html:58` — Inner#model still has zero height; browser confirms a0px-high renderer and invalid aspect, despite the outer600px region. Action: Give the actual host usable responsive dimensions and derive camera/render size from them.
- Evidence: `/tmp/model-lotte-review/nova-pro/f0f629b16c95/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.

## nova-lite — FAIL, task complete=False

- Critical / Renders: `docs/models/nova-lite/lotte-tower/artwork.html:161` — THREE.Geometry (and Face3 below) were removed from the pinned runtime; constructor throws before model initialization. Action: Use supported BufferGeometry and valid indices.
- Warning / Structural Completeness: `docs/models/nova-lite/lotte-tower/artwork.html:160` — No explained intermediate3D development states are implemented. Action: Provide distinct explained3D forms leading to completion and link them to the drawings.
- Warning / Data Accuracy and References: `docs/models/nova-lite/lotte-tower/artwork.html:198` — Each new level appends faces indexed0–7 without an offset, so only the first ring would be referenced even after replacing the obsolete API. Action: Index successive elevated rings correctly and verify actual mesh bounds at the stated555m total.
- Warning / Layout: `docs/models/nova-lite/lotte-tower/artwork.html:158` — The intended555m geometry starts with camera only5units away and no useful target/home fit. Action: Fit the complete authored tower and update aspect from the actual viewport.
- Warning / Readability: `docs/models/nova-lite/lotte-tower/artwork.html:107` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Evidence: `/tmp/model-lotte-review/nova-lite/57e9c8515fbc/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.

## nova-micro — FAIL, task complete=False

- Critical / Renders: `docs/models/nova-micro/lotte-tower/artwork.html:76` — All four images use the same incomplete PNG data URI; browser reports ERR_INVALID_URL and no drawings load. Action: Render actual inline drawings or valid complete embedded assets.
- Warning / Structural Completeness: `docs/models/nova-micro/lotte-tower/artwork.html:141` — No explained intermediate3D development states are implemented. Action: Provide distinct explained3D forms leading to completion and link them to the drawings.
- Warning / Data Accuracy and References: `docs/models/nova-micro/lotte-tower/artwork.html:142` — All named stage/final meshes remain identical unit cubes; only one is shown, not the required tapered tower. Action: Build meaningful development forms and coherent completed tower geometry.
- Warning / Layout: `docs/models/nova-micro/lotte-tower/artwork.html:20` — The100%-width header adds horizontal padding, and unwrapped rows overflow at all tested widths. Model/stage slots remain poorly sized. Action: Fit header/rows with responsive sizing and preserve normal scrolling.
- Warning / Readability: `docs/models/nova-micro/lotte-tower/artwork.html:48` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Evidence: `/tmp/model-lotte-review/nova-micro/5ebb6caba2c5/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.

## nemotron-nano-3-30b — FAIL, task complete=False

- Critical / Renders: `docs/models/nemotron-nano-3-30b/lotte-tower/artwork.html:99` — TextureLoader still receives canvases as URLs, attempting missing[object HTMLCanvasElement] image requests. Action: Use CanvasTexture with real drawn contents.
- Warning / Structural Completeness: `docs/models/nemotron-nano-3-30b/lotte-tower/artwork.html:93` — The four actual site/floor/elevation/section diagrams remain missing or placeholders. Action: Render meaningful distinct diagram content with model correspondence and labelled units/assumptions.
- Warning / Readability: `docs/models/nemotron-nano-3-30b/lotte-tower/artwork.html:11` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Evidence: `/tmp/model-lotte-review/nemotron-nano-3-30b/acc83a509b38/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Two tower variants now exist, but drawings remain blank textures and the confirmed texture-loading error persists.

## glm-4.7-flash — REVIEW, task complete=False

- Warning / Readability: `docs/models/glm-4.7-flash/lotte-tower/artwork.html:82` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Structural Completeness: `docs/models/glm-4.7-flash/lotte-tower/artwork.html:582` — No explained intermediate3D development states are implemented. Action: Provide distinct explained3D forms leading to completion and link them to the drawings.
- Warning / Layout: `docs/models/glm-4.7-flash/lotte-tower/artwork.html:305` — Default/full-model target and distance do not contain the555-high shape; the view is concentrated near the base. Action: Fit the complete form in its model/home pose.
- Warning / Interactions: `docs/models/glm-4.7-flash/lotte-tower/artwork.html:666` — Every frame pulls the camera back toward a programmed pose, undoing free OrbitControls movement after input. Action: Apply transition interpolation only during explicit transitions and preserve user orbit afterward.
- Evidence: `/tmp/model-lotte-review/glm-4.7-flash/9586dab8a74c/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Elevation-button null exception is fixed and actual schematic diagram geometry was added. Buttons still select drawing/camera modes over one unchanged tower, not intermediate design forms.

## gpt-oss-20b — FAIL, task complete=False

- Critical / Renders: `docs/models/gpt-oss-20b/lotte-tower/artwork.html:98` — resize runs before const camera initialization and accesses it, causing Cannot access camera before initialization. Action: Initialize camera before the first resize call; retain correct host-based dimensions.
- Warning / Readability: `docs/models/gpt-oss-20b/lotte-tower/artwork.html:9` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Layout: `docs/models/gpt-oss-20b/lotte-tower/artwork.html:16` — Viewer layout continues to overflow768/375; the minimum/flex dimensions cannot fit the narrow page. Action: Allow viewer and drawing children to shrink/reflow without clipping.
- Warning / Accessibility: `docs/models/gpt-oss-20b/lotte-tower/artwork.html:134` — Keyboard shortcuts move the target, but provide no actual orbit or zoom equivalent. Action: Provide working keyboard orbit/zoom with correct camera-to-target state.
- Evidence: `/tmp/model-lotte-review/gpt-oss-20b/5ee00c024bdd/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.

## gpt-oss-120b — FAIL, task complete=False

- Critical / Renders: `docs/models/gpt-oss-120b/lotte-tower/artwork.html:175` — ArrowDown/Right call nonexistent rotateDown/rotateRight; real keyboard tests reproduce both method-not-a-function errors. Action: Use signed rotateUp/rotateLeft calls or supported camera math and test all directions.
- Warning / Readability: `docs/models/gpt-oss-120b/lotte-tower/artwork.html:13` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Data Accuracy and References: `docs/models/gpt-oss-120b/lotte-tower/artwork.html:111` — Top/bottom radii remain reversed: completed upright geometry widens upward, inconsistent with its description/drawings. Action: Correct radius order and keep drawing/model taper coherent.
- Evidence: `/tmp/model-lotte-review/gpt-oss-120b/662f89790a2a/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Upright orientation and keyboard zoom direction are fixed. browser-keyboard.json verifies the remaining directional exceptions.

## qwen3-32b — FAIL, task complete=False

- Critical / Renders: `docs/models/qwen3-32b/lotte-tower/artwork.html:108` — The local runtime script was omitted; initialization logs runtime not loaded then throws on THREE.Scene. Action: Load ../runtime/three-runtime.js before initialization and verify actual rendering.
- Warning / Structural Completeness: `docs/models/qwen3-32b/lotte-tower/artwork.html:260` — The four actual site/floor/elevation/section diagrams remain missing or placeholders. Action: Render meaningful distinct diagram content with model correspondence and labelled units/assumptions.
- Warning / Readability: `docs/models/qwen3-32b/lotte-tower/artwork.html:73` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Data Accuracy and References: `docs/models/qwen3-32b/lotte-tower/artwork.html:189` — Cylinder radius order is still reversed, contradicting the upward-tapering description. Action: Use correct top/bottom radii throughout all stages.
- Evidence: `/tmp/model-lotte-review/qwen3-32b/129863275742/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- This is its second successful-source re-review, not a fabricated third; earlier failed API responses were not rendered artifacts. New drawing choices currently show prose only.

## nemotron-super-3-120b — PASS, task complete=False

- Warning / Readability: `docs/models/nemotron-super-3-120b/lotte-tower/artwork.html:11` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Interactions: `docs/models/nemotron-super-3-120b/lotte-tower/artwork.html:255` — Stage attributes are words(concept/massing/taper/facade/final), but code removes all nondigits then parses them, givingNaN. Every click creates the default100-unit form; only descriptions change. Action: Map stage names to the actual numeric states so each advertised3D stage differs.
- Warning / Accessibility: `docs/models/nemotron-super-3-120b/lotte-tower/artwork.html:282` — Keyboard only resets; there is no keyboard orbit or zoom equivalent. Action: Provide keyboard-accessible camera operations.
- Evidence: `/tmp/model-lotte-review/nemotron-super-3-120b/a082bfe8a3bc/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- The genuine local renderer and four schematic SVG drawing views now operate. Task remains incomplete because advertised3D development states never select their corresponding geometry.

## llama4-scout — REVIEW, task complete=True

- Warning / Readability: `docs/models/llama4-scout/lotte-tower/artwork.html:212` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Warning / Layout: `docs/models/llama4-scout/lotte-tower/artwork.html:109` — Full-window renderer and absolute drawing panels overlap/overflow on narrow screens; border sizing also exceeds viewport width. Action: Reflow the panels around a usable responsive model surface.
- Warning / Data Accuracy and References: `docs/models/llama4-scout/lotte-tower/artwork.html:245` — Elevation/section label100m while the complete model uses200units and the supplied total is555m; the scale correspondence is unexplained. Action: Use consistent total-height/scale labels and identify assumed dimensions.
- Warning / Interactions: `docs/models/llama4-scout/lotte-tower/artwork.html:301` — Arrow handlers rotate camera quaternion directly, but OrbitControls.update immediately restores its orientation; targeted key tests show no camera change. Action: Orbit by changing camera-to-target position through supported controls.
- Evidence: `/tmp/model-lotte-review/llama4-scout/a3b57bbea362/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Four dimensioned schematic drawings and three intermediate boxes plus completed cone are now present. Their inaccuracies remain explicit Warnings; no polished shared geometry is required. This is its second successful-source re-review.

## qwen3-235b-a22b — FAIL, task complete=False

- Critical / Renders: `docs/models/qwen3-235b-a22b/lotte-tower/artwork.html:449` — The custom Quaternion class lacks setFromEuler, but OrbitControls construction calls it, causing the observed method-not-a-function error. Action: Complete the custom spatial runtime consistently or use the supplied local runtime; verify initialization and all camera operations.
- Warning / Readability: `docs/models/qwen3-235b-a22b/lotte-tower/artwork.html:130` — Meaningful UI/diagram text remains below19px rendered size. Action: Use at least19px meaningful rendered text and controls.
- Evidence: `/tmp/model-lotte-review/qwen3-235b-a22b/c361b11bdb85/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- The earlier escaped-template syntax issue is fixed. This source now attempts custom WebGL; it is not rejected for choosing that medium, but the actual constructor exception prevents verified operation.

## llama4-maverick — REVIEW, task complete=True

- Warning / Interactions: `docs/models/llama4-maverick/lotte-tower/artwork.html:195` — Keyboard camera rotations are overwritten by OrbitControls.update; all arrow tests return unchanged quaternion/position. Action: Use target-relative orbit operations that survive the control update.
- Warning / Layout: `docs/models/llama4-maverick/lotte-tower/artwork.html:80` — The completed cone extends well below the reset target; initial screenshot crops much of its base. Action: Fit the full completed form in the default/reset pose.
- Warning / Layout: `docs/models/llama4-maverick/lotte-tower/artwork.html:187` — Camera aspect uses full-window height while the canvas is80%height, distorting projections. Action: Use actual rendered width/height for both camera and renderer.
- Warning / Data Accuracy and References: `docs/models/llama4-maverick/lotte-tower/artwork.html:143` — Floor/elevation/section views are generic square/box/plane primitives and do not coherently depict the completed cone cross-section and internal section. Action: Make the schematic views correspond to the authored complete form and label assumptions.
- Evidence: `/tmp/model-lotte-review/llama4-maverick/42a3ba1fe5ca/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Runtime and valid Shape errors are fixed; four selectable drawing views and real cylinder→cone3D states are implemented. Quality/correspondence defects are Warnings, not a demand for uniform geometry.

## llama-3.3-70b-bedrock — FAIL, task complete=False

- Critical / Renders: `docs/models/llama-3.3-70b-bedrock/lotte-tower/artwork.html:135` — Down/Right invoke nonexistent rotateDown/rotateRight; actual keyboard tests throw for both directions. Action: Use signed supported rotateUp/rotateLeft operations.
- Warning / Structural Completeness: `docs/models/llama-3.3-70b-bedrock/lotte-tower/artwork.html:57` — The four actual site/floor/elevation/section diagrams remain missing or placeholders. Action: Render meaningful distinct diagram content with model correspondence and labelled units/assumptions.
- Warning / Data Accuracy and References: `docs/models/llama-3.3-70b-bedrock/lotte-tower/artwork.html:76` — All frusta widen upward, and final height is400 with no555m scale correspondence. Action: Use coherent upward-narrowing stages and a consistent555m completed representation.
- Warning / Layout: `docs/models/llama-3.3-70b-bedrock/lotte-tower/artwork.html:149` — Camera aspect uses full-window height while renderer uses80%height. Action: Derive aspect from the actual renderer dimensions.
- Warning / Interactions: `docs/models/llama-3.3-70b-bedrock/lotte-tower/artwork.html:109` — Reset only sets camera.z, preserving prior orbit x/y/target, so it does not restore a valid home view. Action: Restore complete home position/target/orientation.
- Evidence: `/tmp/model-lotte-review/llama-3.3-70b-bedrock/e67818ea849c/browser.json`
- Final managed correction source frozen; raw response bytes/configured identity verified, offline browser375/768/1440 tested. No source edits. Re-review count records actual independently reviewed successful source revisions.
- Real canvas constructor is fixed. Four identical5×5PNG placeholders remain, not actual drawings.

## gemma-4-31b-bedrock — REVIEW, task complete=True

- Warning / Readability: `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:86` — Diagram labels, model information and keyboard hints remain16px; the SVG555m annotation renders below19px. Action: Use at least19px meaningful rendered text, including diagram labels/annotations or readable equivalents.
- Warning / Accessibility: `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:136` — The four focusable diagramDIVs have onclick only. Actual Enter/Space tests leave the camera unchanged, while clicking changes it. Action: Use native buttons or implement Enter/Space activation consistently for all four diagram controls.
- Warning / Layout: `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:262` — The initial/reset camera crops the crown of the555-high model; the1280px screenshot shows the upper tower outside the view. Action: Fit the whole model in its initial/reset pose while preserving your own visual treatment.
- Warning / Layout: `docs/models/gemma-4-31b-bedrock/lotte-tower/artwork.html:108` — At375px the tall nearly full-width overlay panel covers the3D model and its pointer surface. Scrolling the panel does not expose a usable model area. Action: Adapt or collapse/reflow your own mobile controls so the3D model is visible and directly operable alongside accessible controls.
- Current authorized repair episode:2026-10-14; see `gemma-bedrock-review.json/.md` for exact source/browser/fairness evidence.

## exaone-3.5-32b — FAIL, task complete=False

- Critical / Renders: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:90` — The right-arrow button/shortcut still calls nonexistent controls.rotateRight; browser reproduces the exception. Action: Use the supported signed rotateLeft operation or correct target-relative camera math.
- Warning / Structural Completeness: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:95` — All four diagrams are explicitly mock colored rectangles with titles, not meaningful site/floor/elevation/section content. Action: Provide real schematic drawings with units/assumptions and model correspondence.
- Warning / Structural Completeness: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:47` — All design-stage selection/progression was removed; only one static mock frustum remains. Action: Restore explained intermediate3D forms and a completed state linked to drawings.
- Warning / Data Accuracy and References: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:48` — Top radius50 exceeds bottom10, so the model widens upward, contrary to the supplied tower form. Action: Use a coherent upward-narrowing form with stated scale and corresponding diagrams.
- Warning / Layout: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:44` — The full-window canvas is inserted inside a max800px×600px host, overflowing its region; diagram widths plus padding exceed mobile width while overflow-x:hidden clips them. Action: Use actual host dimensions and responsive diagram wrapping without clipped content.
- Warning / Readability: `docs/models/exaone-3.5-32b/lotte-tower/artwork.html:8` — Body and SVG diagram labels remain default16px, below19px, despite19px buttons. Action: Set all meaningful rendered text and diagram labels to at least19px.
- Evidence: `/tmp/model-lotte-review/exaone-3.5-32b/f810c39e19a7/browser.json`
- Third re-review/iteration4. ExactSHA f810c39e19a7a8d6197f01194885f925449bb9bd6303710d59ed96219c2c096c. Current original response bytes/configured native identity verified.
- Far-plane clipping and missing reset are fixed, but a real directional exception and missing required drawing/stage content remain.
- Three-re-review limit reached: stop further automatic EXAONE paid repairs and hand the unresolved scope to the user. Publication remains closed for this source.
