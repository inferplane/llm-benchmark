"""Rebuild deliverables and independently check actual costs and QA arithmetic.

The pre-call collector/report-helper snapshot remains immutable. Correct its
copied generic 'bedrock' provider display label to the actual configured Mantle
API here; this presentation correction does not change scores or source rows.
"""
import argparse
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import luna_benchmark as b, finqa, report


def qa_result():
    result = b.qa_report()
    result["models"][-1]["provider"] = b.model()["api"]
    result["reporting_provenance"] = {
        "finalizer_sha256": b.sha(__file__), "contract_sha256": b.sha(b.CONTRACT),
        "display_correction": "Provider label derives from actual model api; scores, prices, and requests unchanged.",
    }
    return result


def translation_result():
    result = b.translation_report()
    scheduling = b.read(b.FOLDER / "judge-scheduling.json")
    assert scheduling["judge_input"] == b.judge_identity()
    assert scheduling["scheduler_sha256"] == b.sha(b.VALIDATION / "judge_continue.py")
    assert scheduling["executions"] and all(e.get("finished_at") for e in scheduling["executions"])
    result["judge_execution"] = scheduling
    result["interpretation"] += (
        " 채점은 완료된 판정을 재사용하며 동시 처리 수만8에서32로 변경했습니다. "
        "중단 시 저장되지 않은 평가자 호출 비용은 채점 비용 추정치에 포함되지 않습니다.")
    return result


def independent_qa_check(result):
    """No production DSL/evaluator calls: Fraction arithmetic on observed syntax."""
    by_id = {r["id"]: r for r in finqa.read_rows(b.qa.DATASET)}
    outcomes = []
    for e in result["evaluations"][-20:]:
        record = by_id[e["id"]]
        payload = json.loads(e["output_text"])
        program = payload["program"]
        steps = re.findall(r"([a-z_]+)\(([^()]*)\)", program)
        assert ",".join(f"{op}({args})" for op, args in steps).replace(" ", "") == program.replace(" ", "")
        values = []
        def number(text):
            text = text.strip()
            if text.startswith("#"):
                return values[int(text[1:])]
            return Fraction(text.removeprefix("const_"))
        for op, arguments in steps:
            args = arguments.split(",")
            if op == "table_average":
                assert args[1].strip() == "none"
                row = next(r for r in record["table"] if r[0].strip() == args[0].strip())
                cells = [Fraction(v.replace("$", "").replace(",", "").strip()) for v in row[1:]]
                value = sum(cells) / len(cells)
            else:
                left, right = map(number, args)
                if op == "add":
                    value = left + right
                elif op == "subtract":
                    value = left - right
                elif op == "multiply":
                    value = left * right
                elif op == "divide":
                    value = left / right
                else:
                    raise AssertionError(f"Unexpected observed operation {op}")
            values.append(value)
        value = values[-1]
        canonical, declared = record["audit"]["canonical_unit"], payload["unit"]
        assert declared == record["audit"]["requested_unit"]
        if declared == "percent" and canonical == "ratio":
            value /= 100
        else:
            assert declared == canonical
        expected = Fraction(record["audit"]["expected_rational"])
        correct = round(value, 5) == round(expected, 5)
        assert correct == e["correct"] == e["strict_correct"]
        outcomes.append({"id": e["id"], "computed_rational": str(value),
                         "expected_rational": str(expected), "correct": correct})
    assert sum(o["correct"] for o in outcomes) == 18
    return outcomes


def independent_cost(rows):
    m = b.model()
    columns = {"tokens_in": "price_in", "tokens_out": "price_out",
               "cache_read_tokens": "price_cache_read", "cache_write_tokens": "price_cache_write"}
    successful = [r for r in rows if r.get("error") is None]
    counts = {key: sum(r.get(key, 0) for r in successful) for key in columns}
    cost = sum(Decimal(counts[key]) * Decimal(str(m[price])) / Decimal(1_000_000)
               for key, price in columns.items())
    assert all(r["reported_input_tokens"] == r["tokens_in"] + r.get("cache_read_tokens", 0) +
               r.get("cache_write_tokens", 0) for r in successful)
    return {"successful_calls": len(successful), "counters": counts, "exact_usd": str(cost),
            "rounded_usd": float(round(cost, 4))}


def verify():
    qa = qa_result()
    assert b.read(finqa.REPORTS / f"{b.QA_RUN}.json") == qa
    tr = translation_result()
    assert b.read(report.DOCS_RESULTS_DIR / f"{b.TRANSLATION_RUN}.json") == tr
    combined = b.translation_comparison(tr)
    assert b.read(report.DOCS_RESULTS_DIR / f"{b.COMPARISON}.json") == combined
    qcost = independent_cost(finqa.read_rows(finqa.RESULTS / b.QA_RUN / "answers.jsonl"))
    tcost = independent_cost(finqa.read_rows(b.FOLDER / "translations.jsonl"))
    assert qcost["rounded_usd"] == qa["models"][-1]["aggregate"]["estimated_cost_usd"]
    assert tcost["rounded_usd"] == tr["models"][0]["aggregate"]["cost_total_usd"]
    assert len(qa["models"]) == 30 and len(qa["evaluations"]) == 600 and len(combined["models"]) == 31
    outcome = {"qa_arithmetic": independent_qa_check(qa), "qa_cost": qcost, "translation_cost": tcost,
               "translation_diagnostics": tr["models"][0]["collection_diagnostics"],
               "finalizer_sha256": b.sha(__file__),
               "files": {str(p.relative_to(b.ROOT)): b.sha(p) for p in [
                   finqa.REPORTS / f"{b.QA_RUN}.json", finqa.REPORTS / f"{b.QA_RUN}.html",
                   report.DOCS_RESULTS_DIR / f"{b.TRANSLATION_RUN}.json",
                   report.DOCS_RESULTS_DIR / f"{b.COMPARISON}.json",
                   b.FOLDER / "translations.jsonl", b.FOLDER / "judgments.jsonl",
                   finqa.RESULTS / b.QA_RUN / "answers.jsonl", b.CONTRACT,
                   b.FOLDER / "judge-scheduling.json", b.VALIDATION / "judge_continue.py"]}}
    finqa.write_json(b.VALIDATION / "final-verification.json", outcome)
    print(json.dumps({k: v for k, v in outcome.items() if k in ("qa_cost", "translation_cost", "translation_diagnostics")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["qa", "translation", "verify"])
    args = parser.parse_args()
    if args.command == "qa":
        result = qa_result()
        independent_qa_check(result)
        b.publish_qa(result)
    elif args.command == "translation":
        new = translation_result()
        report.write_report(new)
        report.write_report(b.translation_comparison(new))
    else:
        verify()
