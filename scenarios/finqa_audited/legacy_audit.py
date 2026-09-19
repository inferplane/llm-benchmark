"""Reproduce diagnosis of all 560 OLD responses; never changes historical scores."""
import json
from collections import Counter
from bench import finqa, finqa_compare

# Reviewed against the retained full document and table, before the new experiment.
# Multiple annotation and candidate errors can coexist; no corrected leaderboard.
NOTES = [
    ("ambiguous", "table_2:2007 contingent rent33m to2009 19m. Decrease amount14m; official (19-33)/33=-.42424 is a rate not explicitly requested."),
    ("ambiguous", "text_6/7:2010=503m and2008=814m. Question from2010 to2008 suggests (814-503)/503; official reverses direction (503-814)/814."),
    ("annotation_issue", "table_5 total5283.3; text_16 25% belongs to security segment, not clearly companywide. Official multiplies company total by security share. text_1 26% relates to plumbing1720.8."),
    ("ambiguous", "table_0=21829 and table_3=22203 are categories/total, not two time periods. Official calls their difference over21829 a percentage change."),
    ("clear", "table_4/5: signed non-tower cashflow-30584 / consolidated531822=-.05751; same period and scale."),
    ("clear", "table_1/7:2012 agriculture3280 / total freight19686=.16662; both millions, same2012 column."),
    ("clear", "table_5/10: goodwill64m / revised acquisition price549m=.11658."),
    ("clear", "text_31: expected2019 expense205m versus2018 160m; (205-160)/160=.28125."),
    ("unit_convention", "table_6:15.7%-15.1%=0.6 percentage points, represented by official .006 as a proportion. Relative percentage change would be a different operation."),
    ("clear", "table_2/6:2010 lease35269 / total249038=.14162; a percentage question with ratio-form official output."),
    ("clear", "table_2:431170 shares *48.11 dollars /1000000=20.74359 million; excludes other months."),
    ("unit_convention", "table_3:100 initial to89.27 yields-.1073 proportional return=-10.73%. Official subtracts only, retaining percentage-number scale-10.73."),
    ("clear", "table_6/7:2017 HTM47733 / investment securities247980=.19249. Ratio explicitly requested; other percent form is a unit-compliance issue."),
    ("annotation_issue", "table_2/7: automotive2077 / total freight20684=.10042. Official denominator21963 is total operating revenue including other revenue, contradicting question."),
    ("clear", "table_5/9:2010 casualty325 / total current liabilities2713=.11979."),
    ("clear", "table_1:2012 net revenue53341 to2013 52708; (52708-53341)/53341=-.01187. Year/day OCR strings are awkward but column years establish direction."),
    ("ambiguous", "table_3:2015 value99.90 vs inception100 implies cumulative-.1%; year2015-only return vs2014 105.72 differs. Question does not explicitly specify cumulative. Returning99.90 is asset value, not gain."),
    ("annotation_issue", "text_24/25: gain107m and sales5.4bn. Official107/5.4=19.81481 omits1000 unit conversion; same-units result107/5400=.0198148. Another.3bn sale category also exists. A candidate using table_3 balance1301 chooses a different denominator too."),
    ("clear", "table_1/2:2014 operating income88.2 / sales450.4=.19583."),
    ("unit_convention", "table_1/2:five-year terminal total-return indices148.92 and135.02 (base100); difference13.9 index/percentage points. Official13.9; equivalent ratio difference.139 requires unit context."),
]


def build():
    records = finqa.read_rows(finqa.DATASET)
    assert len(records) == len(NOTES) == 20
    questions = []
    for record, (quality, note) in zip(records, NOTES):
        assert finqa.execute(record["reference_program"], record["table"]) == record["gold_answer"]
        questions.append({
            "id": record["id"], "question": record["question"],
            "document_quality": quality, "audit_note": note,
            "official_program": record["reference_program"], "official_answer": record["gold_answer"],
            "reference_answer": record["reference_answer"],
        })
    roster = json.loads((finqa.ROOT / "docs/results/integrated-2026-09-17.json").read_text())
    rows, summaries = [], []
    for model in roster["models"]:
        name = model["name"]
        if name == "amazon-translate":
            continue
        directory = finqa.RESULTS / f"finqa-all-20260918-{name}"
        _, source, predictions = finqa.load_run(directory)
        assert source == records
        counts = Counter()
        for record, question in zip(records, questions):
            raw = predictions.get((name, record["id"]))
            evaluation = finqa_compare.evaluate_one(record, raw)
            category = evaluation["status"]
            scale_candidates = []
            if category == "scored":
                category = "official_match" if evaluation["correct"] else "other_numeric_or_interpretation_mismatch"
                if not evaluation["correct"]:
                    normalized, _ = finqa_compare.normalize_prediction(raw)
                    program = json.loads(normalized["output_text"])["program"]
                    steps = len(list(finqa.STEP.finditer(program)))
                    for operation in ("multiply", "divide"):
                        for scale in (100, 1000):
                            try:
                                value = finqa.execute(program + f", {operation}(#{steps-1}, {scale})", record["table"])
                            except (ValueError, ArithmeticError):
                                continue
                            if value == record["gold_answer"]:
                                scale_candidates.append(f"{operation}_{scale}")
                    if scale_candidates:
                        category = "scale_difference_candidate"
            counts[category] += 1
            rows.append({
                **evaluation, "model": name, "category": category,
                "document_quality": question["document_quality"],
                "diagnostic_scale_candidates": scale_candidates,
                "output_text": raw.get("output_text") if raw else None,
                "review_limit": "Scale candidates are diagnostic, not validated correct answers. Other mismatches are not necessarily model errors; consult question audit.",
            })
        summaries.append({"model": name, "counts": dict(counts)})
    assert len(rows) == 560 and len(summaries) == 28
    return {
        "run_id": "finqa-all-20260918", "audit_date": "2026-09-19",
        "scope": "Question-level evidence review plus reproducible full-roster diagnostics. Not a corrected score.",
        "questions": questions, "models": summaries, "evaluations": rows,
    }


if __name__ == "__main__":
    result = build()
    finqa.write_json(finqa.ROOT / "scenarios/finqa_audited/legacy-audit.json", result)
    finqa.write_json(finqa.REPORTS / "legacy-audit-20260919.json", result)
    print("20 question assessments and all28/560 legacy response diagnostics written")
