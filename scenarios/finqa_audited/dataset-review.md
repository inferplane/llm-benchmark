# Independent preliminary FinQA dataset review

Date: 2026-09-19  
Worktree: `/tmp/llm-benchmark-finqa-audited`  
Declared upstream revision: `0f16e2867befa6840783e58be38c9efb9229d742`

## Gate decision

**REQUEST CHANGES before candidate model calls.** Independently recomputed arithmetic agrees with all 20 `audit.expected_rational` values. However, two selected questions do not uniquely establish the intended answer under a strict full-document ambiguity gate: candidate 22 (HOLX annual compensation) and candidate 26 (GPN acquisition scope). Exclude those unchanged questions. The other 18 pass the document-grounding review, subject to the nonblocking qualifications below.

Findings on the initial snapshot: **0 Critical, 2 Major, 3 Minor**. The three Minor findings concern audit wording, exclusion explanations, and inherited OCR artifacts; they do not require additional exclusions from the 18 passing records. **Minor m1 was corrected by the parent during report preparation and verified in the closing addendum; 2 Major and 2 Minor remain open.**

This is a preliminary dataset gate, **not** a final exact-HEAD PR review or approval of the evaluator. No candidate outputs exist or were reviewed. No model API calls, benchmark evaluator execution, network calls, or repository edits were made. The only authored artifact is this report.

## Reviewed bytes and method

| File | SHA256 |
| --- | --- |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-audited-dev.jsonl` | `a99b12e0f65d344ec85230b3fe9ff81a640df027ac90ca1454ec419e686bc246` |
| `/tmp/llm-benchmark-finqa-audited/scenarios/finqa_audited/selection-audit.json` | `e58e689b00ca5cb9ca5d43009c14632da8f21644c5bc3dcc0135cbb5776e03f9` |
| `/tmp/finqa-upstream/dataset/dev.json` | `a847fb7e0d61a3125a1e2909852df6b89f1ee64d2c5ff1bf689e332214deee51` |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-dev.jsonl` — old-ID exclusion check only | `bcd7f9fbf8e6821afd32f2dab837371e86a2bc275d43a7f0cc14a61499d12a64` |

I read the complete `pre_text`, `post_text`, normalized `table`, and upstream `table_ori` for all 20 selected records and all 13 excluded candidates, not merely `gold_inds` or selection evidence snippets. “Full document” here means the full visible page context in the supplied upstream JSON; original PDFs and unseen pages were not available or independently authenticated.

For each selected record, I independently transcribed the relevant operands from that context and computed with Python standard-library `fractions.Fraction`. I did not import benchmark modules, execute reference programs, or use the main evaluator. All 20 resulting fractions exactly equal the audited rational values. Arithmetic agreement is reported separately from semantic validity.

Additional checks passed:

- All 20 questions, normalized tables, and complete pre/post text arrays exactly match their corresponding upstream records.
- Every selected record's source revision equals the declared pin; the source-file SHA256 matches the selection manifest.
- All 20 selected source IDs are unique and absent from the old 20-record dataset.
- The selection has 33 candidates, 20 includes, and 13 excludes. Selected audit units, rational values, reasons, and candidate indices match the selection records.
- Independently sorting upstream IDs, removing the old 20 IDs, and shuffling with seed `20260919` reproduces all first 33 candidate IDs in order.
- SHA256 of `json.dumps(full_shuffled_candidate_ids)` reproduces `candidate_order_sha256`: `f6a3d2abfb1bbea63de90b8ed845804842fa40d1d81d3875e12d823ed542da9d`.
- Dataset and selection SHA256 values were unchanged when rechecked after substantive inspection.

Provenance limitation: `/tmp/finqa-upstream` is an extracted directory, not a Git checkout. The pin is supplied provenance, corroborated by the declared local source hash; I could not independently verify Git-object membership in that revision locally.

In the evidence references below, `text_N` indexes concatenated `pre_text + post_text`; table indices refer to the upstream normalized table. JSONL line numbers are one-based; candidate indices are zero-based.

## Major findings

### Major M1 — Candidate 22: yearly recognition is not established by total divided by duration

Record: `HOLX/2012/page_113.pdf-2`, dataset line 14.

Question: “what is the expected yearly stock-based compensation expense over the remaining vesting period, (in millions)?”

`text_26` supplies $23.2 million to be recognized over approximately 3.5 remaining years. Thus `23.2 / 3.5 = 232/35 = 6.628571429` million dollars **per year as an annualized average** is valid arithmetic. However, the full visible document provides neither an annual recognition schedule nor a statement that the expense is spread evenly. A total expense and duration alone do not establish what will be recognized in each year.

The audit silently changes “expected yearly ... expense” into “annual average expense.” Its numerical gold is conditional on that interpretation, rather than uniquely established by the question and document. The omitted time dimension also matters when describing the answer: this is an annualized rate, not the total remaining expense.

**Action:** exclude the unchanged question before model calls. If rewritten examples are allowed, an explicitly labeled revised question asking for the annualized average, or assuming even recognition, could be reviewed separately. A private audit assumption cannot disambiguate the model-visible question.

### Major M2 — Candidate 26: the acquisition scope is not uniquely identified

Record: `GPN/2009/page_70.pdf-3`, dataset line 17.

Question: “what percent of assets acquired by the acquisition are non-tangible assets?”

The audited `18658/19427 = 96.041591599%` correctly describes the table: goodwill 13,536 plus customer-related intangibles 4,091 plus contract-based intangibles 1,031, divided by gross assets acquired 19,427. Gross assets, rather than net assets 16,594, are the appropriate denominator **for that table**.

But `text_7–13` says the table aggregates multiple fiscal-2008 acquisitions, including LFS Spain and U.S. money-transfer branch locations. The question names no acquisition or group. The same visible page also describes a separate Canadian purchase in `text_17–19`: a customer list and long-term merchant referral agreement for $1.7 million, all assigned to those intangible items, with $0.1 million expensed immediately. That purchase gives a materially different reading of the unnamed acquisition (100% intangible consideration at acquisition), and `text_20` introduces another acquisition.

This is a concrete scope alternative in the supplied context, not merely a missing company name. There is no question-level instruction selecting the aggregate table. The existing exclusion of candidate 27 for an unnamed segment amid multiple segment results applies the same conservative principle.

**Action:** exclude the unchanged question before model calls. An explicitly revised question identifying the fiscal-2008 business acquisitions summarized in the table could pass, but would need separate review.

## Per-item review of all 20 selected records

### 1. Candidate 1 — `HII/2017/page_104.pdf-1` — PASS

JSONL line 1. Senior-note issuance-cost percentage change, 2016 to 2017.

`text_22` gives $19m in 2016 and $15m in 2017. Independent calculation: `(15 − 19) / 19 = −4/19`, or **−21.052631579%**. Canonical unit `ratio`; requested unit `percent`. The 2016 denominator and negative sign are correct. Credit-facility costs in `text_17` and the table's total debt-issuance-cost deduction are different scopes and must not replace the senior-note values. Inherited unrelated table OCR is noted under Minor m3.

### 2. Candidate 2 — `RE/2015/page_33.pdf-1` — PASS

JSONL line 2. Commercial mortgage-backed securities book-to-market ratio.

`text_7` states book value $264.9m and market value $266.3m for the same portfolio, in the December 2015 context. Independent calculation: `264.9 / 266.3 = 2649/2663 =` **0.994742771311**. Canonical and requested units `ratio`. Book is the numerator; market is the denominator. Portfolio ratings and investment-income table yields are unrelated.

### 3. Candidate 3 — `LMT/2013/page_74.pdf-2` — PASS

JSONL line 3. Aeronautics share of the specified 2011 severance actions.

`text_15` gives $49m Aeronautics, $48m Space Systems, and $39m IS&GS/corporate, totaling $136m, all net of state tax benefits. Independent calculation: `49 / (49 + 48 + 39) = 49/136`, or **36.029411765%**. Canonical `ratio`; requested `percent`. The context establishes the severance-charge amounts; the $88m earnings impact and the 2012/2013 actions are not the denominator.

### 4. Candidate 4 — `ETR/2008/page_355.pdf-4` — PASS

JSONL line 4. Gas-customer percentage change between 2007 and 2008.

`text_5` gives approximately 86,000 gas customers at December 31, 2007 and 93,000 at December 31, 2008. Independent calculation: `(93000 − 86000) / 86000 = 7/86`, or **8.139534884%**. Canonical `ratio`; requested `percent`. Electric-customer counts and revenue figures are excluded. The percentage inherits the approximate precision of the reported customer counts.

### 5. Candidate 5 — `ETR/2002/page_86.pdf-4` — PASS

JSONL line 5. Sum of the notes with seven and eight annual installments.

`text_9–11` identifies the NYPA transaction and the seven approximately $108m installments followed by eight $20m installments. Independent undiscounted scheduled-payment sum: `7 × 108 + 8 × 20 =` **916 million USD**. Canonical and requested units `usd_million`, with scale supplied by the text rather than explicitly requested in the question. This is the installment sum, not a present-value calculation at the mentioned implicit interest rate. The separate Indian Point 2 obligation in `text_12` is outside the named installment schedule.

### 6. Candidate 6 — `IP/2007/page_75.pdf-4` — PASS

JSONL line 6. Tax-audit settlement benefit as a percentage of the recorded 2007 tax provision.

`text_2` gives a $41m benefit and the $415m recorded provision. Independent calculation: `41 / 415`, or **9.879518072%**. Canonical `ratio`; requested `percent`. The positive benefit magnitude is compared with the recorded provision. The $423m special-item-adjusted provision and $8m other benefits answer different questions; neither belongs in this denominator/numerator.

### 7. Candidate 8 — `SNPS/2006/page_69.pdf-2` — PASS

JSONL line 7. Goodwill as a percentage of total purchase price.

The HPL acquisition discussion gives $3.4m goodwill in `text_14`; the table explicitly uses thousands and totals $15,704 thousand. Independent calculation: `3400 / 15704 = 425/1963`, or **21.650534896%**. Canonical `ratio`; requested `percent`. Include prior investment and acquisition-related costs in total purchase price; cash paid alone is not the requested denominator. The source goodwill is rounded to $0.1m; the rational is exact arithmetic on displayed inputs, not additional underlying valuation precision. Later acquisition discussion supplies no competing goodwill figure.

### 8. Candidate 9 — `ETR/2002/page_86.pdf-1` — PASS

JSONL line 8. Maturity/sinking-fund percentage change explicitly **from 2005 to 2004**.

`text_6` identifies the debt-outstanding-at-December-2002 maturity schedule, excluding lease obligations, in thousands. Table values are 540,372 for 2005 and 925,005 for 2004. Independent calculation: `(925005 − 540372) / 540372 = 128211/180124`, or **71.179298705%**. Canonical `ratio`; requested `percent`. The unusual backward direction is explicit and must be respected. Do not reverse the base year or add the separate noncash-capable sinking requirements from `text_7`.

### 9. Candidate 13 — `ABMD/2009/page_88.pdf-3` — PASS

JSONL line 9. Total contingent payments if all targets are achieved.

`text_28` lists dollar payments of 5,583,333, 5,583,333, and 5,583,334. Independent calculation: their sum is **16,750,000 USD**. Canonical and requested units `usd`. The nearby “in thousands” declaration applies to the tax-benefit table, not these explicitly dollar-denominated payments. `text_29–31` discusses already-paid milestones and final cash/share settlement; it does not reduce the total for all targets to the unpaid balance or cash-only portion.

### 10. Candidate 14 — `LMT/2015/page_54.pdf-1` — PASS

JSONL line 10. Average MFC net sales, 2013–2015, in millions.

`text_5–7` identifies the MFC table and million-dollar scale. Net sales are 6,795, 7,092, and 6,770. Independent calculation: `(6795 + 7092 + 6770) / 3 = 20657/3 =` **6,885.666666667 million USD**. Canonical and requested units `usd_million`. Use three annual observations, not two intervals. The preceding IS&GS discussion and operating-profit row are different scopes.

### 11. Candidate 17 — `CB/2010/page_88.pdf-2` — PASS

JSONL line 11. Average catastrophe losses, 2008–2010, in millions.

`text_1` reports net pre-tax catastrophe losses of $567m, $137m, and $366m for those three years. Independent calculation: `(567 + 137 + 366) / 3 = 1070/3 =` **356.666666667 million USD**. Canonical and requested units `usd_million`. The table's catastrophe-related ratio adjustments include reinstatement premiums and are not loss amounts. Prior-period development is another metric.

### 12. Candidate 18 — `OKE/2012/page_52.pdf-1` — PASS

JSONL line 12. Employees covered by collective bargaining agreements.

`text_19–20` fixes the date at January 31, 2013, despite the filing's 2012 source ID. Covered employees total `406 + 299 = 705`, matching the text; all employees total 4,859. Independent calculation: `705/4859`, or **14.509158263%**. Canonical `ratio`; requested `percent`. The denominator is the company employee total, not only Kansas Gas Service or one union. The legacy “15%” answer is rounded, not the exact audit gold.

### 13. Candidate 21 — `PM/2018/page_31.pdf-2` — PASS

JSONL line 13. Postretirement discount-rate percentage change, 2017–2018.

`text_30` and the postretirement row establish year-end rates of 3.79% and 3.97%. Independent calculation: `(3.97 − 3.79) / 3.79 = 18/379`, or **4.749340369%**. Canonical `ratio`; requested `percent`. The raw change is 0.18 percentage points, but the question explicitly asks percentage change. Pension-plan rates and projected expense changes are not relevant operands.

### 14. Candidate 22 — `HOLX/2012/page_113.pdf-2` — ISSUE, Major M1

JSONL line 14. Independent annualized-average calculation: `23.2 / 3.5 = 232/35 =` **6.628571429 million USD/year**. The audited numerical fraction is correct for that interpretation. The question asks expected yearly expense without specifying an average or even recognition. Full evidence and exclusion action are given in M1. Existing `usd_million` units describe monetary scale but do not express the annual-rate qualification.

### 15. Candidate 24 — `MO/2012/page_44.pdf-1` — PASS

JSONL line 15. Higher tobacco/health judgment charges relative to the operating-companies-income increase.

`text_10` expressly identifies the smokeable-products comparison as 2011 versus 2010; `text_12` pairs $87m higher charges with a $119m income increase. Independent calculation: `87/119`, or **73.109243697%**. Canonical `ratio`; requested `percent`. This compares magnitudes; the charges offset income growth, rather than contribute positively to it. The separate 2012 smokeless-products growth mention supplies no matching tobacco/health judgment-charge comparison.

### 16. Candidate 25 — `ETFC/2014/page_26.pdf-1` — PASS

JSONL line 16. Common-stock return from 2009 to 2014.

`text_0` specifies cumulative total return with dividend reinvestment from December 31, 2009 through December 31, 2014. The E*TRADE row moves from 100 to 137.81. Independent calculation: `(137.81 − 100) / 100 = 3781/10000`, or **37.81%**. Canonical `ratio`; requested `percent`. This is cumulative return, not annualized return or an index comparison.

### 17. Candidate 26 — `GPN/2009/page_70.pdf-3` — ISSUE, Major M2

JSONL line 17. Independent table-specific calculation: `(13536 + 4091 + 1031) / 19427 = 18658/19427`, or **96.041591599%**. Canonical `ratio`; requested `percent` are correct for the table. Gross assets reconcile: `18658 + 267 + 502 = 19427`. The unresolved issue is which acquisition the question means, not the fraction, classification of goodwill, or gross-assets denominator. See M2.

### 18. Candidate 28 — `AES/2015/page_117.pdf-3` — PASS

JSONL line 18. Average proportional recoverable environmental capital expenditures, 2013–2015.

`text_26` explicitly gives IPL's proportional recoverable environmental capex of $110m, $163m, and $205m. Independent calculation: `(110 + 163 + 205) / 3 = 478/3 =` **159.333333333 million USD**. Canonical and requested units `usd_million`. These are already proportional amounts, so no second ownership adjustment is justified. The table's 51/56/75 values concern non-recoverable expenditures. The audit should retain the IPL attribution; these are the visible recoverable amounts, not a separately established worldwide AES total.

### 19. Candidate 30 — `SWKS/2006/page_81.pdf-1` — PASS; Minor m1

JSONL line 19. Total pension-liability adjustment from 2004 to 2006.

`text_14` explicitly introduces minimum-pension-liability adjustments **“in thousands.”** The table runs from October 1, 2004 through September 29, 2006, with signed changes −351 and +538. Independent calculation: `−351 + 538 =` **+187 thousand USD**, corroborated by `−599 − (−786) = 187`. Canonical and source-implied answer scale `usd_thousand` are justified. Sum changes, not cumulative balances, and do not double-count the duplicate accumulated-other-comprehensive-loss column. The positive sign describes the displayed adjustment, not a claim that the underlying pension obligation grew by that amount.

The question does not explicitly request thousands, but the supplied table introduction establishes its natural reporting scale. The audit's “Need source scale confirmation” is stale, as the user already noted; it is not a reason to exclude this item.

### 20. Candidate 32 — `K/2013/page_62.pdf-2` — PASS

JSONL line 20. Interest-rate contracts as a percentage of total derivatives in 2013.

`text_6` identifies notional amounts as of December 28, 2013. Table amounts are 2,400 for interest-rate contracts and `517 + 2400 + 361 = 3278` total. Independent calculation: `2400/3278 = 1200/1639`, or **73.215375229%**. Canonical `ratio`; requested `percent`. These are notional-value shares, not contract counts or fair-value shares; the visible numeric table establishes the basis. Use the 2013 column, not 2012.

## Review of the 13 existing exclusions

All 13 may remain excluded. This review does not require reinstating a questionable example. “Severity if included” below distinguishes defects in an excluded item from active findings in the selected dataset.

| Candidate / source ID | Exclusion assessment and independent reasoning | Severity if included unchanged |
| --- | --- | --- |
| 0 — `HIG/2008/page_318.pdf-1` | **Keep excluded.** The question combines GAAP stockholders' equity and aggregate statutory capital. `text_11–15` distinguishes $9.3bn GAAP equity from $13.8bn statutory capital/surplus. `6047/13777` computes only the table's Life Operations statutory-surplus share. It cannot establish the requested combined accounting scope. | Major |
| 7 — `JPM/2008/page_85.pdf-3` | **Keep excluded.** The table labels 136,104 as total Tier 1 capital. Dividing by risk-weighted assets 1,244,659 does not establish the question's common-equity Tier 1 numerator. The full context does not supply that numerator. | Major |
| 10 — `VTR/2007/page_47.pdf-3` | **Keep excluded conservatively.** `14669 × 43.89 = 643822.41` USD correctly estimates the listed repurchases, but `text_10` restricts them to Q4 2007. An all-2007 repurchase total is not established. “Based on the given average price” could refer only to listed repurchases, so the existing explanation should describe ambiguity, not prove that the listed arithmetic is wrong. | Major ambiguity |
| 11 — `UNP/2014/page_25.pdf-2` | **Keep excluded.** Hypothetically applying 5% growth gives `22560 × 1.05 = 23688`, whereas the source program gives 22560.05. More importantly, `text_11–14` discusses overall 2013 freight ARC growth; `text_13` does not establish an agricultural-specific growth rate. The nearby agriculture sentence only says revenue declined slightly. Fixing the arithmetic alone would not resolve the question's metric/period premise. | Major |
| 12 — `AES/2003/page_52.pdf-2` | **Keep excluded.** Q4 sales proceeds are `145 + 78 + 150 = 373` million USD. The $23m August transaction falls outside the three months ended December 2003. The source's 396 includes that out-of-period sale. The U.K. Medway row provides both £47m and $78m; use its dollar amount consistently. | Major |
| 15 — `IP/2005/page_35.pdf-4` | **Keep excluded; refine explanation.** `text_0` dates the schedule at December 31, 2005, while maturity columns begin in 2006. Thus “in 2005” might mean the reporting date, not payments falling due in 2005. Either way, `1181/4617` arbitrarily limits the requested total to 2006. Across all displayed maturities, total debt is 12,204 and total obligations 18,535, giving `12204/18535` rather than `1181/4617`. The reference's first-column restriction is unsupported. | Major |
| 16 — `LMT/2012/page_47.pdf-4` | **Keep excluded as a reference-integrity choice.** The question itself is answerable: the Space Systems table and `text_16` give `(1083 + 1063 + 1030)/3 = 3176/3 = 1058.666666667` million USD. The textual answer 1059 rounds correctly; the malformed source program produces 526.5. Describe this as a program/gold defect, not intrinsic question ambiguity. Reinstatement is not required. | Major if malformed executable gold is used |
| 19 — `MRO/2008/page_69.pdf-3` | **Keep excluded.** `text_21` supplies the 2008 annual average $91.90/barrel and end-2008 $24.97/barrel, not end-2007. Their difference 66.93 answers an annual-average-to-year-end comparison, not the requested endpoint comparison. Other benchmark oil prices in the full document do not supply the missing synthetic-crude/vacuum-gas endpoint. | Major |
| 20 — `HOLX/2010/page_124.pdf-1` | **Keep excluded conservatively.** `text_5` gives $2.1bn cash and the thousands table gives 2,094,800; `text_10` instead says $2.1m. The table ratio `2094800/6156900` is approximately 34.02%, but the visible source contains an explicit scale contradiction. The exclusion avoids silently repairing that text. | Major source contradiction |
| 23 — `GPN/2017/page_77.pdf-3` | **Keep excluded.** `265982 − 203828 = 62154` thousand USD is explicitly total identifiable net assets, including 42,721 customer intangibles, 27,954 technology, and 2,901 trade name. Removing those yields `62154 − 42721 − 27954 − 2901 = −11422` thousand USD, also equal to `45826 + 2337 − 9788 − 49797`. The supplied reference does not answer net tangible assets. | Major |
| 27 — `IP/2009/page_37.pdf-3` | **Keep excluded.** Consumer Packaging gives `433 − 17 = 416` million USD, but the unnamed segment also permits other readings: U.S. Market Pulp `140 − (−156) = 296`, or North American Consumer Packaging `343 − 8 = 335`, with further adjusted variants. The full document makes the missing scope material. | Major |
| 29 — `ABMD/2007/page_52.pdf-2` | **Keep excluded.** The table supports both 8,381 thousand USD current obligations and `8381/14090`, approximately 59.482%, as a share. “How much ... are current?” does not uniquely request a percentage. Source units establish the amount scale but do not choose amount versus share. | Major ambiguity |
| 31 — `VTR/2007/page_47.pdf-1` | **Keep excluded.** Adding 14,669 Q4-2007 repurchased shares to the February 15, 2008 outstanding count of 138,311,810 yields 138,326,479, but requires an unsupported assumption of no intervening share-count changes. The page also mentions employee restricted-stock withholding and a reinvestment/stock-purchase plan; it provides no complete reconciliation. | Major |

## Nonblocking findings and scoring boundaries

### Minor m1 — Stale SWKS audit wording

Both selected audit and selection reason say “Need source scale confirmation.” Replace that sentence with the explicit `text_14` thousands evidence and retain the signed reconciliation. This is a known pending correction, not a newly discovered missing-unit defect.

### Minor m2 — Exclusion explanations should distinguish source defects from question defects

Refine candidates 11, 15, and 16 as described above: UNP also lacks a supported agricultural ARC rate; IP has an as-of-date interpretation but still an unsupported first-maturity-column denominator; LMT has an answerable average with a malformed reference program. These refinements strengthen provenance and do not change any exclusion decision.

### Minor m3 — Inherited OCR defects remain in otherwise passing visible context

Some upstream normalized tables replace em dashes with literal `2014`: HII's redeemed/not-yet-issued note balances, ABMD's zero ending tax-benefit balance, and AES's absent service-concession entries. `table_ori` confirms these are dash artifacts. The copied candidate tables preserve them exactly.

These entries are not used by the passing questions' calculations, and their required evidence is explicit elsewhere in the same visible context, so I do not require exclusion. Nevertheless, “audited” should not imply that every cell in the context was verified as a faithful PDF transcription. Any later normalization of those cells changes the reviewed bytes and needs to be recorded and rechecked.

### Boundaries for the forthcoming evaluator review

The retained upstream `gold_answer`, `reference_answer`, and `reference_program` fields are legacy provenance, not a substitute for the audited rational values. Rounded references such as OKE “15%,” SNPS “22%,” and LMT “6886” differ from exact arithmetic on displayed inputs. K's reference answer “73.22” even omits the percent sign despite the question requesting percent.

For this review, `ratio` values are fractions of one and `percent` displays multiply those fractions by 100. Currency scale follows the cited local context; physically equivalent amounts such as SWKS 187 thousand USD and 187,000 USD must not be confused with different monetary values. Conversely, a 100-fold percentage scaling error must not be accepted merely because both representations are numeric.

Several source inputs are explicitly approximate or rounded. Exact fractions mean exact arithmetic on those displayed inputs; this report does not approve any particular output rounding tolerance. The parent’s unit-aware evaluator, tolerance policy, prompt construction, and exclusion of private audit/gold material from model input require their own implementation review.

## Required disposition

Remove unchanged candidates 22 and 26 before calls, reconcile selection counts and reviewed-file hashes, and independently review any replacement records. Retain the other 18 passing questions and the 13 existing exclusions, with the nonblocking audit corrections above. This report does not authorize a final PR merge or certify a later HEAD.

## Closing addendum: parent's concurrent SWKS wording correction verified

The final hash check detected concurrent parent edits. I verified that **the sole byte-level change in each of the two files** was replacing `Need source scale confirmation.` with `text_14 explicitly states in thousands.` Reversing that sentence in memory reproduces each original reviewed SHA256 exactly. No question, table, visible text, rational value, unit, selection decision, or other byte changed.

| Updated reviewed file | SHA256 after verified wording correction |
| --- | --- |
| `data/finqa-audited-dev.jsonl` | `1c4bf30e681bcdb2c8bc98f2674e74eef3c81b74c8941309001b27379bb08fe3` |
| `scenarios/finqa_audited/selection-audit.json` | `4776858b0e5e2669a471afa08de48359493cc43b4b6a0bcce8e49fb01f8714b5` |

Minor m1 is resolved in these updated bytes. All per-item judgments, both Major findings, and the request-changes gate decision remain unchanged. The original hash table identifies the initial review snapshot; this addendum extends the same dataset assessment to the two updated hashes above.

## Replacement review — 36-candidate selection, 2026-09-19

### Updated hash-bound gate decision

**REQUEST CHANGES: 19 selected records PASS; candidate 34 has one new Major ambiguity.** Prior Major M1 (candidate 22) and Major M2 (candidate 26) are resolved by exclusion. Candidate 35 passes. Candidate 33 is correctly excluded. There are **0 open Critical and 1 open Major** in this updated selected dataset; prior nonblocking Minor m2 and m3 remain.

This decision applies specifically to the following bytes and supersedes the earlier gate decision for these updated files:

| Reviewed file | SHA256 |
| --- | --- |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-audited-dev.jsonl` | `5aa422118bf6be2ff65bdfb13051ec55adcd2355d0cc6e9ecf5b473f3ef48079` |
| `/tmp/llm-benchmark-finqa-audited/scenarios/finqa_audited/selection-audit.json` | `91265c3d280bff78bb0c59c6cb4dff04b31dcebb735d4ad5d89806368fe418ad` |
| `/tmp/finqa-upstream/dataset/dev.json` | `a847fb7e0d61a3125a1e2909852df6b89f1ee64d2c5ff1bf689e332214deee51` |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-dev.jsonl` — old-ID exclusion baseline | `bcd7f9fbf8e6821afd32f2dab837371e86a2bc275d43a7f0cc14a61499d12a64` |

I read the complete visible `pre_text`, `post_text`, normalized table, and original table for candidates 33, 34, and 35 from the same pinned-source JSON. Arithmetic below uses independent standard-library rational calculations, not source-program execution or the benchmark evaluator. No candidate calls or repository edits were made; only this report was appended.

### Replacement candidate 34 — `CME/2017/page_97.pdf-1` — ISSUE, Major M3

Updated JSONL line 19.

Question: “how many class a common stocks issued and outstanding were issued between 2016 and 2017 in thousands?”

The source's `text_1–2` introduces capital-stock shares outstanding. The table expressly uses thousands and reports Class A common stock issued and outstanding of 338,240 at December 31, 2016 and 339,235 at December 31, 2017. Independent calculation:

`339235 − 338240 = 995` thousand shares, equivalent to **995,000 shares**.

Thus the audit's `995/1`, `canonical_unit = count_thousand`, and `requested_unit = count_thousand` are correct **for the net increase in the reported stock count**. Authorized Class A shares of 1,000,000 thousand and the fractional-thousand Class B rows are not operands. No monetary unit, percentage, or annual average is appropriate.

However, the question's verb is **“were issued”**, which can ask how many shares were issued during the period, rather than the net change in shares issued and outstanding at two dates. The complete visible page contains no issuance/retirement reconciliation and no statement that there were no offsetting retirements or other share-count movements. Its remaining discussion concerns trading, voting, transfer, and director-election rights, not Class A share-count activity.

As a mathematical demonstration of the missing information, both of the following are compatible with the two displayed balances: issuance of 995 thousand with no retirement, or issuance of 1,095 thousand and retirement of 100 thousand. Both produce the same net increase of 995 thousand; gross issuance differs. This is an illustration of underdetermination, not an assertion that CME actually made those transactions.

The parent and audit identify the intended answer as a net change, but that qualification is absent from the model-visible question. Labeling a stock balance “issued and outstanding” does not make its year-over-year difference a uniquely established gross issuance flow. Under the strict gate already applied to HOLX's yearly-versus-average wording, accepting a private reinterpretation here would be inconsistent.

**Action:** exclude candidate 34 unchanged before model calls. If rewritten questions are permitted, “What was the net increase in Class A common shares issued and outstanding from December 31, 2016 to December 31, 2017, in thousands?” would establish the independently verified answer, but must be recorded and reviewed as a changed question. This finding concerns question/metric ambiguity, not an arithmetic or unit error.

### Replacement candidate 35 — `CNP/2010/page_31.pdf-1` — PASS

Updated JSONL line 20.

Question: “considering the state of arkansas, what is the percentage of residential customers concerning the total customers?”

`text_5` identifies the table as natural-gas distribution customer counts by state as of December 31, 2010. The Arkansas row supplies 390,668 residential customers, 48,033 commercial/industrial customers, and 438,701 total customers.

Independent reconciliation and calculation:

`390668 + 48033 = 438701`

`390668 / 438701 = 390668/438701 = 0.8905108490748825…`

Requested percentage: **89.05108490748825…%**, or approximately **89.05%**.

The exact fraction matches `audit.expected_rational`; `canonical_unit = ratio` and `requested_unit = percent` are correct. Both numerator and denominator refer to Arkansas at the same date. The denominator is not the all-state 3,263,224-customer total, and it is not commercial/industrial customers alone.

The 42% residential share in `text_4` measures total gas **throughput**, not Arkansas customer counts. The seasonal 71% in `text_8`, supplier-volume percentages, and hedging percentages likewise measure different things. The question explicitly identifies the state and customer metric, and the full document introduces no competing Arkansas customer population or date. No exclusion issue found.

### Newly excluded candidate 33 — `LMT/2006/page_90.pdf-3` — exclusion upheld

Question: “at december 31, 2006 what was the ratio of the expected future pension benefits after 2012 compared to 2008”

The pension-benefits column supplies 1,490 million for 2008 and 9,530 million for the combined **2012–2016** period. The original table explicitly labels that final row “Years 2012 – 2016”; the normalized label “years 2012 2013 2016” is an OCR artifact, not separate annual observations.

`9530/1490 = 953/149 = 6.395973154…` correctly computes **2012–2016 inclusive divided by 2008**. It does not compute benefits strictly after 2012. The visible text and table do not separate 2012 from 2013–2016, nor provide the complete post-2016 horizon if “after 2012” is read without an ending year. Nonqualified-plan liabilities, pension contributions, and operating-lease commitments elsewhere on the page do not supply the missing pension-payment breakdown.

The new `period_ambiguity` exclusion reason is justified. Keep excluded; the source reference's numerator would create a Major period mismatch if this item were included unchanged.

### Full updated selection and retained-record verification

The final selected candidate indices are:

`1, 2, 3, 4, 5, 6, 8, 9, 13, 14, 17, 18, 21, 24, 25, 28, 30, 32, 34, 35`.

The excluded candidate indices are:

`0, 7, 10, 11, 12, 15, 16, 19, 20, 22, 23, 26, 27, 29, 31, 33`.

Checks passed:

- Exactly 36 candidates, 16 exclusions, and 20 selected records; dataset order exactly matches the included selection records.
- Candidates 22 and 26 are absent from the dataset and now have exclusion reasons accurately describing M1 and M2.
- The original 13 exclusions remain intact, with the same nonblocking explanation refinements previously recommended under Minor m2.
- **All retained 18 records are unchanged, including their audit fields.** To establish this against an already reviewed hash rather than rely on the parent's assertion, I reconstructed the prior 20-record dataset in memory by taking the current retained records and reinserting the two previously reviewed removed records with their original audit metadata. Its serialized SHA256 exactly reproduced the prior reviewed dataset hash `1c4bf30e681bcdb2c8bc98f2674e74eef3c81b74c8941309001b27379bb08fe3`.
- Similarly, truncating the updated selection to its original 33 candidates and restoring only the previously reviewed include decisions/metadata for candidates 22 and 26 reproduced the prior selection hash `4776858b0e5e2669a471afa08de48359493cc43b4b6a0bcce8e49fb01f8714b5`. This confirms there were no hidden changes to the other original selection records.
- All 20 current questions, complete visible text arrays, and normalized tables still match the corresponding upstream source records. Every selected audit field agrees with its selection entry.
- All 20 selected source IDs are unique and absent from the old benchmark's 20 IDs.
- Independently rebuilding the seed-`20260919` candidate order reproduces all first 36 candidates and the full candidate-order SHA256 `f6a3d2abfb1bbea63de90b8ed845804842fa40d1d81d3875e12d823ed542da9d`.
- The source-file hash still matches the selection manifest. The prior limitation concerning an extracted source directory rather than a Git checkout remains unchanged.

The carried-forward 18 PASS judgments plus candidate 35 yield **19 PASS** records. Candidate 34's arithmetic passes, but its unchanged question does not pass the strict ambiguity gate.

### Disposition for these updated hashes

Keep candidates 22, 26, and 33 excluded; retain the 18 previously approved records and candidate 35. Exclude or explicitly revise candidate 34, then rebind the gate to the regenerated dataset and selection hashes and independently review any replacement.

This is still a preliminary dataset-only decision. It does not approve evaluator behavior, prompt construction, UI/code changes, candidate outputs, or a final exact-HEAD PR.

## Final pre-call dataset gate — 38-candidate selection, 2026-09-19

### Decision: APPROVED for the exact dataset and selection hashes below

**All 20 selected questions PASS the full-visible-document dataset review. There are 0 unresolved Critical and 0 unresolved Major dataset findings.** Prior Major M1, M2, and M3 are resolved by excluding candidates 22, 26, and 34 respectively. The replacement AES question passes. All 18 excluded candidates may remain excluded.

This is the final pre-call **dataset** approval for the following bytes. It supersedes the earlier request-changes decisions for these updated files; the earlier sections remain as review history.

| Reviewed file | SHA256 |
| --- | --- |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-audited-dev.jsonl` | `db21d90c2f96a942576d173e13a068f880d14b2e16a244153d90eaa0fef08ab6` |
| `/tmp/llm-benchmark-finqa-audited/scenarios/finqa_audited/selection-audit.json` | `daf08588d7d27771456028d4e20041533b62ca3f4c6b05f6dec33602162ba745` |
| `/tmp/finqa-upstream/dataset/dev.json` | `a847fb7e0d61a3125a1e2909852df6b89f1ee64d2c5ff1bf689e332214deee51` |
| `/tmp/llm-benchmark-finqa-audited/data/finqa-dev.jsonl` — old-ID exclusion baseline | `bcd7f9fbf8e6821afd32f2dab837371e86a2bc275d43a7f0cc14a61499d12a64` |

Declared upstream revision remains `0f16e2867befa6840783e58be38c9efb9229d742`. Approval covers questions, audited numerical values, units, and their grounding in the complete visible source text/table. It is not final exact-HEAD PR approval or a review of the evaluator, UI, prompt construction, or candidate outputs. No candidate calls or repository edits were made during this review; this report is the only authored file.

### Replacement candidate 37 — `AES/2003/page_52.pdf-1` — PASS

Final JSONL line 20.

Question: “for the three months ended march 2003 what were the total sales proceeds for subsidiaries assets in millions?”

I read the entire visible source context, including all 22 concatenated text entries, all ten transaction rows, and `table_ori`. `text_3–5` describes the company's subsidiary asset-sale initiative and identifies the chart as sales closed during 2003. `text_6` and the table heading establish proceeds in millions.

The quarter ended March 2003 comprises January through March 2003. The complete table contains exactly four transactions in that period:

| Transaction | Completion | Proceeds, USD millions |
| --- | --- | ---: |
| CILCORP/Medina Valley | January 2003 | 495 |
| AES Ecogen/AES Mt. Stuart | January 2003 | 59 |
| Mountainview | March 2003 | 30 |
| Kelvin | March 2003 | 29 |

Independent arithmetic, without executing the reference program:

`(495 + 59) + (30 + 29) = 554 + 59 = 613` million USD.

`audit.expected_rational = 613/1`, `canonical_unit = usd_million`, and `requested_unit = usd_million` are justified. Equivalent amount: **613,000,000 USD**. This is a sum of proceeds, with no denominator, averaging, annualization, or change-of-balance assumption.

The table provides no February sale. Songas closed in April and is outside Q1; all July, August, November, and December sales are also excluded. The dual-currency U.K. rows occur later in the year and introduce no exchange-rate requirement for this calculation. The dollar amounts for Australia and South Africa are presented in the same proceeds column as the U.S. transactions; the location column does not instruct conversion into local currencies.

The later Brazilian subsidiary-restructuring narrative does not identify an additional Q1 asset sale or proceeds amount. Its financing and ownership discussion cannot be added to the Q1 proceeds total. Unlike the excluded December-quarter question on this same source page, the selected operands all fall within the requested three-month period.

The upstream free-text `qa.answer` and copied `reference_answer` are empty for this record. That is a legacy annotation omission, **not missing audited gold**: the visible question and source support 613 independently, the audit records `613/1`, and the upstream numeric `exe_ans` is also 613.0. Keep the distinction visible in provenance; scoring/display must use the audited gold rather than require the legacy answer string. No dataset exclusion is warranted.

### Newly excluded candidate 36 — `BLL/2010/page_28.pdf-2` — exclusion upheld

Question: “did the five year total return on ball corporation outperform the dj containers & packaging index?”

I read the full pre/post text, normalized table, and original table. `text_0–1` explicitly defines the five-year period ending December 31, 2010, with $100 invested December 31, 2005 and dividends reinvested. The relevant ending values are 178.93 for Ball and 123.56 for the DJ Containers & Packaging index.

Independent comparison:

- Ball cumulative return: `(178.93 − 100) / 100 = 7893/10000 = 78.93%`.
- Index cumulative return: `(123.56 − 100) / 100 = 589/2500 = 23.56%`.
- `78.93% > 23.56%`, so the independently supported answer is **yes**.

The upstream `greater(178.93, 105.34)` uses the index's December 31, **2009** endpoint instead. Its boolean result happens to agree, but the temporal operands do not answer the specified same-period comparison. The updated exclusion reason accurately records this defect.

Keep excluded as a reference-integrity selection choice. The question itself is answerable and the boolean label is correct; this is not an intrinsically ambiguous question or an incorrect yes/no label. No reinstatement is required, and a coincidentally correct boolean does not validate the source program's reasoning.

### Final selected-item ledger

The detailed full-context judgments for the retained records in earlier sections carry forward. This table binds all 20 PASS outcomes to the final dataset order. Every rational below was rechecked with independently transcribed operands using `fractions.Fraction`; no benchmark module or main evaluator was used.

| Final JSONL line | Candidate | Source ID | Independent canonical value | Canonical / requested unit | Gate |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | `HII/2017/page_104.pdf-1` | `−4/19` | ratio / percent | PASS |
| 2 | 2 | `RE/2015/page_33.pdf-1` | `2649/2663` | ratio / ratio | PASS |
| 3 | 3 | `LMT/2013/page_74.pdf-2` | `49/136` | ratio / percent | PASS |
| 4 | 4 | `ETR/2008/page_355.pdf-4` | `7/86` | ratio / percent | PASS |
| 5 | 5 | `ETR/2002/page_86.pdf-4` | `916/1` | usd_million / usd_million | PASS |
| 6 | 6 | `IP/2007/page_75.pdf-4` | `41/415` | ratio / percent | PASS |
| 7 | 8 | `SNPS/2006/page_69.pdf-2` | `425/1963` | ratio / percent | PASS |
| 8 | 9 | `ETR/2002/page_86.pdf-1` | `128211/180124` | ratio / percent | PASS |
| 9 | 13 | `ABMD/2009/page_88.pdf-3` | `16750000/1` | usd / usd | PASS |
| 10 | 14 | `LMT/2015/page_54.pdf-1` | `20657/3` | usd_million / usd_million | PASS |
| 11 | 17 | `CB/2010/page_88.pdf-2` | `1070/3` | usd_million / usd_million | PASS |
| 12 | 18 | `OKE/2012/page_52.pdf-1` | `705/4859` | ratio / percent | PASS |
| 13 | 21 | `PM/2018/page_31.pdf-2` | `18/379` | ratio / percent | PASS |
| 14 | 24 | `MO/2012/page_44.pdf-1` | `87/119` | ratio / percent | PASS |
| 15 | 25 | `ETFC/2014/page_26.pdf-1` | `3781/10000` | ratio / percent | PASS |
| 16 | 28 | `AES/2015/page_117.pdf-3` | `478/3` | usd_million / usd_million | PASS |
| 17 | 30 | `SWKS/2006/page_81.pdf-1` | `187/1` | usd_thousand / usd_thousand | PASS |
| 18 | 32 | `K/2013/page_62.pdf-2` | `1200/1639` | ratio / percent | PASS |
| 19 | 35 | `CNP/2010/page_31.pdf-1` | `390668/438701` | ratio / percent | PASS |
| 20 | 37 | `AES/2003/page_52.pdf-1` | `613/1` | usd_million / usd_million | PASS |

### Final selection and identity checks

All checks passed:

- Counts reconcile: **38 candidates = 20 selected + 18 excluded**. Selected order exactly matches dataset order.
- Excluded indices are `0, 7, 10, 11, 12, 15, 16, 19, 20, 22, 23, 26, 27, 29, 31, 33, 34, 36`. All have review coverage in this report.
- Candidate 34 is removed, with an exclusion reason that accurately addresses the gross-versus-net issuance finding. The prior 16 exclusions remain unchanged.
- **The retained 19 records are byte-identical to their previously reviewed versions.** Inserting the previously reviewed CME record back into the current retained set and omitting the new AES record reproduces the prior dataset SHA256 exactly: `5aa422118bf6be2ff65bdfb13051ec55adcd2355d0cc6e9ecf5b473f3ef48079`.
- Reconstructing the previous 36-candidate selection by dropping candidates 36–37 and restoring only candidate 34's original include metadata reproduces the prior selection SHA256 exactly: `91265c3d280bff78bb0c59c6cb4dff04b31dcebb735d4ad5d89806368fe418ad`. No other earlier selection entries changed.
- Every current selected question, complete pre/post text array, and normalized table matches its upstream source record. Audit metadata matches its selection entry, including units, rational value, reason, and candidate index.
- All 20 independent fractions equal the audited fractions exactly. All source-revision fields match the declared pin.
- All selected source IDs are unique and absent from the old 20-item benchmark.
- Sorting source IDs, removing the old 20 IDs, and independently shuffling with seed `20260919` reproduces all first 38 candidate IDs and the unchanged full-order SHA256 `f6a3d2abfb1bbea63de90b8ed845804842fa40d1d81d3875e12d823ed542da9d`.
- The upstream source and old-ID baseline hashes remain those documented above.

The earlier nonblocking observations remain: some exclusion explanations could be more precise (Minor m2), and unrelated inherited OCR cells are not faithful original-table transcriptions (Minor m3). Neither affects the selected answers or blocks this dataset gate. SWKS's unit-note correction remains verified.

**Final disposition: the exact 20-record dataset above is approved at the full-visible-text pre-call dataset gate.** No additional selected-item exclusion is required. Approval does not extend to later changed bytes without checking the changes, unseen PDF pages, or the separate final PR review.
