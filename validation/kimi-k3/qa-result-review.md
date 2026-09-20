# Independent PR 10 Kimi K3 QA result review

Date: 2026-09-20. Worktree: `/home/atomoh/llm-benchmark/.worktrees/kimi-k3`.
Observed code HEAD: `b8e8f7ce9c4a4ab12643f51fcd873b42a9da90d6`.
Parent comparison base: `7305b4943800759cbac35efe8438c2de6de3a074` (local merge-base with main).

## Decision

**PASS for this result-review scope: 20/20 independently correct, 20/20 strict raw formats, and 20/20 requested units compliant.** No answer-dependent scale/sign/denominator repair is needed. The direct cache-aware cost is **$0.2696100**, correctly reported as **$0.2696**. The original 28 model records and 560 evaluations are preserved unchanged in the new 29-model, 580-evaluation report.

Findings: **Critical 0; Major 0; Minor 0.** Observable-settings and provenance limits are documented below. This is a result sidecar, not the final exact-HEAD code review; the planned Huygens review is still required. It makes no claim that the ongoing 3,300-item translation collection or its evaluations are complete.

No APIs, network requests, candidate models, main grader, benchmark interpreter, `evaluate_one`, `verify-parent`, or cost function were invoked. All checks used local reads and independent standard-library arithmetic/parsing. No repository files were changed; only this report was written.

## Exact reviewed input hashes

Hashes here are SHA256 of file bytes. Paths are relative to the worktree above.

| File | SHA256 |
| --- | --- |
| `results/finqa/finqa-kimi-k3-20260920/answers.jsonl` | `9ad29930ae16bc6f6eb9e94bab946ce7df1ac04a19c487be3201d7e6cd293d08` |
| `results/finqa/finqa-kimi-k3-20260920/manifest.json` | `408186e0a334382a033795d592d6cdcc3c68f87a0b872e516db00119aab48326` |
| `results/finqa/finqa-kimi-k3-20260920/dataset.jsonl` | `db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6` |
| `results/finqa/finqa-kimi-k3-20260920/prompt.txt` | `723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7` |
| `docs/finqa-results/finqa-kimi-k3-20260920.json` | `94a3813fff141321b7c42017fa335dc7874649e8cd82a30b585b63e88c69e654` |
| `docs/finqa-results/finqa-audited-20260919.json` | `8352c1b90b1fed3a8e78a313cca7493203409f820c0de4966e510cb6ea0a273e` |
| `validation/kimi-k3/qa-extension.json` | `f30c8b5995ad42bc3a7b51405bcab046fb43f000f03c4151fdca710765ae3912` |
| `validation/kimi-k3/pricing-us-standard.json` | `1e756a21bd1a81c11dccd85a481ac8c6db42f0d055acb1a98b4d70a9f0f1207d` |
| `validation/kimi-k3/live-check.json` | `4c9bf9bdff5495d48193a35a252e74f2a6e793613f1a5d5b2918d32fd78ff7b8` |
| `data/finqa-audited-dev.jsonl` | `db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6` |
| `scenarios/finqa_audited/prompt.txt` | `723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7` |
| `scenarios/finqa_audited/selection-audit.json` | `daf08588d7d27771456028d4e20041533b62ca3f4c6b05f6dec33602162ba745` |
| `scenarios/finqa_audited/freeze.json` | `2625b06d93e656991d6e0a9c9ae508253bced15f1fadbce2e46b751e0a263513` |
| `scenarios/finqa_audited/dataset-review.md` | `5467817b170ab052679260379f91c7d3e084e39cf33be6699c68239ea520402f` |
| `bench/finqa.py` | `bd4b05630aa05d80eecc3d9045f6c7465aa81041239df9dfeca661f08eb0cda8` |
| `bench/finqa_audited.py` | `5c3bebb856196c593e4273a8283c0402bf9def4c14c5d6ed6cb1954caf03997a` |
| `bench/finqa_compare.py` | `8b3eeb66dcbe0347d114eb99fcc976f7f09b370eae145591bb1a119f64cdecd4` |
| `bench/run.py` | `6acd0b170c08620e2d1c6b628d964c29d44747a1548e9cfe018a948db7c9e2db` |
| `bench/kimi_benchmark.py` | `473ab314b59586deaa3433ed4c17f9153b8956200007919887826778fa359f88` |
| `bench/report.py` | `48733dd5d678b8e655a752ad4a7c356daaea1c32ecf454b78ab40d358c4375da` |
| `config.toml` | `e32ca14acb6f193fd65835d56cae6e12bae4b432a41b7a186856876b05fbfe77` |

The raw dataset remains the previously approved `db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6`. The contract's `b814465bce83b3ba4afd168112d9e1059c6a41d3052b893a032cd9652aaba099` is instead the independently reproduced digest of the parsed record list serialized using `json.dumps(..., sort_keys=True, ensure_ascii=False, allow_nan=False)`. This difference is serialization, not different questions. The same canonical serialization is used for the report's manifest/answer source digests; file-byte hashes are listed separately above.

## Independent answer checks

I read every raw answer and compared its operands, dates, metric, denominator, sign, and declared unit with the already approved full-document expectations. A separate parser required a complete JSON object with string program and explicit unit, rejected duplicate JSON keys, consumed the full binary-operation sequence, and allowed only backward result references and numeric constants. Arithmetic used `fractions.Fraction`. The single table-average program resolves the exact `net sales` row and averages its three numeric cells; no benchmark implementation was imported.

Expected fractions were the independently established source calculations from the prior dataset review. Every returned canonical fraction matches them exactly, as well as the frozen rational gold, before the grader's five-decimal rounding step. Twelve percent programs explicitly multiply by 100 and declare `percent`; the independent canonical comparison divides these outputs by 100. The ratio and currency programs already use their requested canonical scales. No format normalization, missing-unit inference, magnitude-based scaling, or other repair was applied.

The ledger is in approved dataset order. “Raw line” identifies the actual physical answer line, since concurrent completion changes ordering. Programs and units are copied exactly from raw output. Canonical values below are independent results.

| Raw line | Candidate / source ID | Returned program | Declared unit | Canonical result | Verdict |
| --- | --- | --- | --- | --- | --- |
| 2 | 1 — `HII/2017/page_104.pdf-1` | `subtract(15, 19), divide(#0, 19), multiply(#1, const_100)` | `percent` | `-4/19` | PASS |
| 1 | 2 — `RE/2015/page_33.pdf-1` | `divide(264.9, 266.3)` | `ratio` | `2649/2663` | PASS |
| 4 | 3 — `LMT/2013/page_74.pdf-2` | `divide(49, 136), multiply(#0, const_100)` | `percent` | `49/136` | PASS |
| 3 | 4 — `ETR/2008/page_355.pdf-4` | `subtract(93000, 86000), divide(#0, 86000), multiply(#1, const_100)` | `percent` | `7/86` | PASS |
| 6 | 5 — `ETR/2002/page_86.pdf-4` | `multiply(7, 108), multiply(8, 20), add(#0, #1)` | `usd_million` | `916` | PASS |
| 5 | 6 — `IP/2007/page_75.pdf-4` | `divide(41, 415), multiply(#0, const_100)` | `percent` | `41/415` | PASS |
| 7 | 8 — `SNPS/2006/page_69.pdf-2` | `divide(3400, 15704), multiply(#0, const_100)` | `percent` | `425/1963` | PASS |
| 9 | 9 — `ETR/2002/page_86.pdf-1` | `subtract(925005, 540372), divide(#0, 540372), multiply(#1, const_100)` | `percent` | `128211/180124` | PASS |
| 8 | 13 — `ABMD/2009/page_88.pdf-3` | `add(5583333, 5583333), add(#0, 5583334)` | `usd` | `16750000` | PASS |
| 16 | 14 — `LMT/2015/page_54.pdf-1` | `table_average(net sales, none)` | `usd_million` | `20657/3` | PASS |
| 10 | 17 — `CB/2010/page_88.pdf-2` | `add(366, 137), add(#0, 567), divide(#1, 3)` | `usd_million` | `1070/3` | PASS |
| 11 | 18 — `OKE/2012/page_52.pdf-1` | `divide(705, 4859), multiply(#0, const_100)` | `percent` | `705/4859` | PASS |
| 12 | 21 — `PM/2018/page_31.pdf-2` | `subtract(3.97, 3.79), divide(#0, 3.79), multiply(#1, const_100)` | `percent` | `18/379` | PASS |
| 13 | 24 — `MO/2012/page_44.pdf-1` | `divide(87, 119), multiply(#0, const_100)` | `percent` | `87/119` | PASS |
| 14 | 25 — `ETFC/2014/page_26.pdf-1` | `subtract(137.81, 100.00), divide(#0, 100.00), multiply(#1, const_100)` | `percent` | `3781/10000` | PASS |
| 15 | 28 — `AES/2015/page_117.pdf-3` | `add(205, 163), add(#0, 110), divide(#1, 3)` | `usd_million` | `478/3` | PASS |
| 20 | 30 — `SWKS/2006/page_81.pdf-1` | `add(-351, 538)` | `usd_thousand` | `187` | PASS |
| 17 | 32 — `K/2013/page_62.pdf-2` | `divide(2400, 3278), multiply(#0, const_100)` | `percent` | `1200/1639` | PASS |
| 18 | 35 — `CNP/2010/page_31.pdf-1` | `divide(390668, 438701), multiply(#0, const_100)` | `percent` | `390668/438701` | PASS |
| 19 | 37 — `AES/2003/page_52.pdf-1` | `add(495, 59), add(#0, 30), add(#1, 29)` | `usd_million` | `613` | PASS |

Specific semantic checks:

- HII uses senior-note issuance costs 15 and 19, not total debt or credit-facility costs, and retains the negative change.
- ETR respects the explicit backward comparison from 2005 to 2004 and uses 540,372 as the denominator. Its NYPA answer sums the seven and eight installment groups without adding the separate Indian Point 2 liability.
- SNPS uses 3,400 thousand goodwill against 15,704 thousand purchase price. The model has already reconciled source scales in its raw operands; the evaluator does not repair a 1,000-fold error.
- ABMD sums the three dollar contingent payments and declares `usd`, avoiding the unrelated tax table's thousands scale.
- MFC's table average is `(6770 + 7092 + 6795)/3`, or `20657/3` million USD.
- PM computes relative percentage change, not merely the 0.18 percentage-point difference. ETFC computes cumulative return, not annualized return.
- AES 2015 uses recoverable proportional environmental capex from the footnote, not non-recoverable table values. AES 2003 includes only January/March sales: `495 + 59 + 30 + 29 = 613` million USD.
- SWKS sums signed changes `−351 + 538 = +187` thousand USD; the source explicitly establishes thousands. CNP uses Arkansas customer counts, not throughput or all-state counts.

Every evidence ID exists in the supplied context. Legacy evidence-list exact equality is 16/20, consistent with the report's 0.8; this is separate from the 20/20 numeric/unit conclusion. Nonmatching sets for HII, ETR's year comparison, Kellogg, and SWKS do not invalidate the operands: they omit unrelated legacy citations or context already available in the full document. This review does not claim 20/20 standalone evidence-list completeness.

All 20 new evaluation records preserve the corresponding raw `output_text`; their prediction digests match independently computed canonical digests of the raw rows. Their raw execution values match the independent fractions, and all record strict correctness, requested-unit compliance, and no normalizations. I did not obtain the independent answer by trusting those flags.

## Direct cache-cost calculation

I parsed the saved AWS Price List response itself. Its four records identify Kimi K3, region `us-west-2`, service tier `standard`; each dimension is quoted per **1K tokens**. Multiplying those rates by 1,000 gives the configured per-million rates below. The saved records have publication date 2026-09-17 and effective date 2026-09-01, both preceding the run. This validates the supplied historical rate schedule locally; it is not a fresh AWS query or a bill audit.

| Charge category | Raw summed tokens | Saved USD / 1K tokens | USD / million | Exact charge USD |
| --- | ---: | ---: | ---: | ---: |
| Uncached input | 140 | 0.0033 | 3.30 | 0.0004620 |
| Output | 6,987 | 0.0165 | 16.50 | 0.1152855 |
| Cache read | 0 | 0.00033 | 0.33 | 0.0000000 |
| Cache write, 30 minutes | 37,300 | 0.004125 | 4.125 | 0.1538625 |
| **Total** | | | | **0.2696100** |

Calculation: `(140×3.30 + 6987×16.50 + 0×0.33 + 37300×4.125) / 1,000,000 = 0.2696100` USD. I used `Decimal` arithmetic, not the repository's cost calculation. Four-decimal reporting yields **$0.2696**. The model-level cost per scheduled question is `$0.2696100 / 20 = $0.0134805`, correctly displayed at five decimals as **$0.01348**. All four raw token sums match the report aggregate and rates match the model contract and config entry.

The cache counters must be charged separately from `tokens_in`. The saved live probes reconcile `7 + 1694 + 36 = 1737` total tokens for cache creation and `7 + 1694 + 90 = 1791` for cache reading. These show that the provider's 7 ordinary input tokens do not already include the 1,694 cached tokens. In this QA run each request reports 7 uncached input tokens and zero cache-read tokens; total input-side volume is **37,440 tokens**, of which 37,300 were cache writes. Charging only 140 input tokens would omit $0.1538625. Conversely, charging cache-write tokens again at the ordinary input rate would double-charge them.

Output billing uses all 6,987 reported output tokens, not a count reconstructed from the short visible JSON. The retained rows do not split reasoning-token usage. The estimate covers these successful QA responses under the saved Standard US rate schedule; it excludes separate preflight probes, translation collection, and any unrecorded provider or SDK activity. No whole-experiment invoice total is claimed.

## Completeness and observable request settings

The answers file contains exactly 20 valid rows, 20 unique expected IDs, and 20 unique request IDs. There are no extra IDs or repeated attempts to discard. Each row records `error: null`, `finish_reason: end_turn`, `request_attempt: 1`, and `request_max_attempts: 1`; none has a failed-response/error-details payload. All outputs are complete JSON programs. Maximum recorded output usage is **2,257 tokens** (MFC), below the 4,096 cap. No missing answer, recorded failure, or visible truncation was found.

The manifest records one execution with requested=20, cached=0, successful=20, failed=0, request_attempts=20. The new contract was frozen at **2026-09-20T12:39:24.647293+00:00**. Execution began at **12:40:15.572583+00:00** and finished at **12:40:52.355348+00:00**; all answer timestamps fall inside that interval and after freeze.

The contract specifies `api=bedrock`, profile `us.moonshotai.kimi-k3`, region `us-west-2`, concurrency 2, max output 4,096, and timeout 600 seconds. The hashed collector explicitly omits temperature for this profile. The shared numeric `temperature: 0` field must not be presented as effective Kimi sampling temperature; the new report correctly says **omitted/provider default**. The saved live check records rejection with temperature present and successful calls after omission, but does not retain the original full ValidationException response.

No reasoning-effort override is configured. The saved preflight probes record `reasoning_content_present: true`; the QA report appropriately attributes the observation to preflight. The actual 20 QA rows do not retain reasoning blocks, a reasoning-effort value, or reasoning-token counts. Thus provider-default reasoning is the configured behavior and was observed in probes, but I cannot certify an identical effective reasoning budget per QA call or parity with the older models. The QA rows also do not retain an echoed provider model identifier or full HTTP request/response envelopes. Request IDs, terminal status, frozen snapshots, source hashes, and the selected profile support local provenance, not independent packet-level/provider authentication.

## Contract and prompt/source identity

The run manifest, `validation/kimi-k3/qa-extension.json`, and report's extension-contract object are identical. New source-run manifest and answer digests in the report independently reproduce. The extension's parent report and parent freeze hashes match the actual files.

The Kimi dataset and prompt snapshots match the approved shared dataset and prompt byte for byte. The evaluator, DSL, and normalizer match the original parent freeze; the collector, extension, and cost-code hashes match the separate new contract. The newer collector is not misrepresented as the old frozen collector. The contract binds these reviewed source files:

| Identity field | File |
| --- | --- |
| evaluator_sha256 | `bench/finqa_audited.py` |
| dsl_sha256 | `bench/finqa.py` |
| normalizer_sha256 | `bench/finqa_compare.py` |
| collector_sha256 | `bench/run.py` |
| extension_sha256 | `bench/kimi_benchmark.py` |
| cost_code_sha256 | `bench/report.py` |

The unchanged prompt builder uses only question, full indexed pre/post text, and table fields, excluding private audit/gold annotations. Identical snapshots plus that unchanged builder establish matching reconstructed QA input. Complete wire payloads are not retained, so this is a source/snapshot check rather than a transport-byte comparison. Translation-related fields in the extension contract were not treated as evidence of completed translation work.

## Parent preservation

Direct comparison verifies that the new report's first 28 model objects equal the parent model objects exactly, including scores, costs, configurations, and statuses. Its first 560 evaluation objects equal the parent's 560 exactly; the only appended evaluations are the 20 Kimi records. The first 28 source-run objects are also identical. Parent generation parameters and protocol freeze are preserved under explicitly parent-named fields.

All 28 retained run directories were checked, covering **112 files**: answers, manifest, dataset, and prompt for each. The 56 JSONL files are tracked via Git LFS: their actual file SHA256 and size match the base commit's LFS pointers. The other 56 files match the base Git blobs byte for byte. A raw Git LFS pointer is not mistaken for the hydrated JSONL content. Each parent source's canonical manifest and deduplicated-answer digest also matches the preserved report, and every parent dataset/prompt matches the approved snapshots.

This verifies preservation against base commit `7305b4943800759cbac35efe8438c2de6de3a074`, not merely self-consistency between two newly generated reports. Parent answers were not regraded by this sidecar; their identity and the stored 560 evaluation objects were verified without calling the main evaluator.

The following source ledger records exact parent answer/manifest file hashes. Each listed run also has the shared dataset byte hash `db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6` and shared prompt byte hash `723996abba008acfc67ec298ded769cbdcbd0af071b72f794d853b9aa50504c7`. Paths are `results/finqa/<run_id>/<file>`.

| Parent run ID | answers.jsonl SHA256 | manifest.json SHA256 |
| --- | --- | --- |
| `finqa-audited-20260919-claude-haiku-4.5` | `7f73f8b49f6de23da56f47ae268efb982526bc8a8b7fdda62dba7f2e765cbf6f` | `f91a29fa3b6f781b5602133f055e98d9efa7fcacec9e13820ea20791a0ec3ddd` |
| `finqa-audited-20260919-claude-sonnet-4.5` | `0eca3e2e16ac9440c89101b2ca0cbd76fd1f013ca668b9778bbd6d1d977e5d87` | `16a50e44d1bf629052cf693a4c1f67a1a5db42ebfc1bb52268f35a7a61eee853` |
| `finqa-audited-20260919-claude-sonnet-5` | `94ec50ad76e878a65dc2e472ed6c20694809eb09709e95f74ec6993b5d698f05` | `46521d803946fd8178a04f2f5e76159aa5d071678bf2098e9c86375113e101aa` |
| `finqa-audited-20260919-nova-pro` | `7bd5dc5909d6a2df243a6428ef5ca889a945280b43742ea05b9071ac1c29ea14` | `af2f9ba8808f90a7306e2ddc618bf7852e67abc48e6b021694f9b1df80457c45` |
| `finqa-audited-20260919-nova-lite` | `c89862ad0470b2c5a7c4c8f83a862839de8fa5dc2234cac4e335b93570a999ce` | `fc3a92423e3a87672a955af4ddfdd185133754045ff1affcd6fb1ff09089796d` |
| `finqa-audited-20260919-gpt-5.4` | `13bc2cce44d252fad9b831b82192192a5aaddc1da0f712dd38875ed8e01e49fb` | `a0e58ca6e950d9d081df280b975f732333682de19ec58fc4f6d1667f9fa62184` |
| `finqa-audited-20260919-gpt-5.5` | `bc68a419dcf19baf657e96c5aad1026d96bcdb09627e6948bb0320b245b36532` | `6e4e141e0e7653420071fd63e1c5fe2fef246ff2e3d82e275f5ac8e3202178d7` |
| `finqa-audited-20260919-gpt-5.6-terra` | `9c8f464c8d3fc334efddd798e6b65302e57819ee5f2247739c29438d54a477ef` | `67a02d4fd6b4b33cd1a1d78bade53cf9222441be57b89b280164fb47b6c91be0` |
| `finqa-audited-20260919-gpt-5.6-luna` | `51da05ea56fe079570bd0d25fae88b71d6cf8a5acf664214e4d47bd4cb2c1815` | `52c7aec07e5bd7ba0926146dde1c1a9d796ce0437587de4cca8390b710911009` |
| `finqa-audited-20260919-nova-micro` | `797b367a2aa60088a8414090504f740c47eac540c11eff425cd4322d305c3330` | `b87a632dc3757aeaae334e6f92e949dbb63eba9973212d46a8ebe73d480193aa` |
| `finqa-audited-20260919-nemotron-nano-3-30b` | `c9499f8ab4732dbf6f9f61e60f0ade212cf90a7d0afe438c5b95770e67886a38` | `226b93a72e60d3a50d44934c2e52a1bb998238eca5e9ac747ebcf4a88a3889cf` |
| `finqa-audited-20260919-glm-4.7-flash` | `9f16e8f48d2c34f0ac256f5af64a264cab2aadbfac83340a3319f4d6fe75c8b3` | `faa609c36c14d78eee4b356bdb6b7d35645586eafaa8176f069e21f6f7ed1ecc` |
| `finqa-audited-20260919-gpt-oss-20b` | `7dc028db7cd3f13c156eecf460540e3f3673fc585e3f3c64760313d568fc26c4` | `bb558939093809f9f3e55fcf35b84586c46b8e59b87700384d18440aa72226b3` |
| `finqa-audited-20260919-gpt-oss-120b` | `f8660a771a6fbf327358c09a1b1416993ba21bb3f028b8030f11430dea665e79` | `d0c8ae0a197e4a94c456f7ac665602c31da2200ad31ab88011804d0b6f2e335a` |
| `finqa-audited-20260919-qwen3-32b` | `8d1b0f6391a9b7e3b0a8da8e922afcf5b9efdc65a4da0e1534d6ff4cc1098191` | `bd85c51359e560f996c41cdd0d243a6756e33b99068d6003427bb5476e2025cd` |
| `finqa-audited-20260919-nemotron-super-3-120b` | `f8495d45de1eecd5c8eb1628555bdf1e4d2d996211078f58e9ece18c4a616eb3` | `c5fda2903b0baad860f8095443efe6458439fd02697b4658a62af11adbff6880` |
| `finqa-audited-20260919-llama4-scout` | `045be0009a12dd56a041514138cc89e806b74e48c4b1343b07d520fbe2bf4784` | `4c3e7e23db93c587276b786c8a5e3802a43df6369b888a3577afcf5fa964b756` |
| `finqa-audited-20260919-ministral-14b` | `6c3095084af7e9f298a3eb3777ea05623db2beb81e6f56f38d39c51079f8eb14` | `c83cb3c49ab8d1e4dd49a503fc32cd3f85471bb93adeae7d3b7c55901cdd3ea5` |
| `finqa-audited-20260919-qwen3-235b-a22b` | `5122a967b3b3296653be771cae6745cc46043d792889b83702587f5ee106ec3b` | `70afcaef22fb1d3eed838e035d948bccb4c0139c9d6145c152e4e069f3904716` |
| `finqa-audited-20260919-llama4-maverick` | `227242ef35d34acdff8b3fbffc147c9b8134b69b838e47eef1aea1162f644586` | `ee8d06de1e7dd2b51be043926e7c187e1c5259b086b01a405560867738698e28` |
| `finqa-audited-20260919-llama-3.3-70b-bedrock` | `53460be9457e2c19c15a9c54e44f548b5f1ba0b5f70a78edf0f2a999f3c31280` | `d995be2eb45cce318e4efd08dd121931779d2b7e6a312ee1cb94bf5c738d5967` |
| `finqa-audited-20260919-gemma-4-31b-bedrock` | `c1e82d221532419210ea99a6d8ea94d9e616fda8229172035679bbc7d879c3bb` | `ec94943f223dc58c501f51a51a7e89dfc048371301e872bd41013b13b262a775` |
| `finqa-audited-20260919-llama-3.1-8b` | `e5f5d7bc41276ae802207e190403581907239d6327cc2a5d8e997ec973adc160` | `00b74c23bb700d53f01431553581615d4a28587fb05c892d7c48dceff49e75e3` |
| `finqa-audited-20260919-llama-3.3-70b` | `f5c1417699427ba81c6024ddf965fe85028c02f1da66ac3f4fe3f95779550bc4` | `bc1ebbe04cd364d5fc9b373d055f308d39bf54dd5ec8c4bb8b585ad0ad069814` |
| `finqa-audited-20260919-qwen3.6-27b` | `1485a096534b2c80018d3e3471b2ceab60a95c209c11d76f36f4cd51d158c443` | `e4defe5dcebcf9567e4c8a1df2122a48dfc1bf4939a44d3a7b3140dafcdbb485` |
| `finqa-audited-20260919-exaone-3.5-32b` | `5aad96d62df15fb5a388e3126da074d3e271edf41c14c573461bfccc7518289f` | `37847e789f56dc81406212b60096ca7b4ad38d2f3c70dcf33f414e593efb0f8c` |
| `finqa-audited-20260919-grok-4.3` | `7decc306bf95ff00e515038d78e9f59101a8304d1604b317689ee7a33b287f9e` | `1f4ee1d0969aaefe6892176bf493e3c8c53e11171557f7408b999c3b6bd39964` |
| `finqa-audited-20260919-grok-4.6` | `1876666e1ee1c9556404990e49d0b07acedd7570ac92e964558d11fd298067db` | `ebcc09bfa05e75ad59c874abb047d443fec5d51a2de5d889e597f782c6d20418` |

## Final disposition

The reviewed retained QA artifacts support **20/20 strict Kimi correctness, 20/20 unit compliance, and the reported $0.2696 cache-aware estimate**, while preserving the original 28 models and 560 evaluations. No result correction or rerun is recommended. Keep final PR approval separate: Huygens must review the eventual exact HEAD, and the ongoing translation work needs its own completed-results verification.
