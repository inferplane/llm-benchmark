"""Audited FinQA-derived QA. Explicit units, pre-call freeze, retained raw answers.

Commands: selfcheck | freeze | run --models NAME --run-id ID | report --run-id ID
The original FinQA execution metric and historical artifacts remain separate.
"""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction
import hashlib
import html
import json
import math
from pathlib import Path

from bench import finqa, finqa_compare, run as runner

ROOT = finqa.ROOT
SCENARIO = ROOT / "scenarios/finqa_audited"
DATASET = ROOT / "data/finqa-audited-dev.jsonl"
FREEZE = SCENARIO / "freeze.json"
VERSION = "audited-financial-qa-v1"
UNITS = {
    "ratio": ("ratio", Fraction(1)),
    "percent": ("ratio", Fraction(1, 100)),
    # Point differences are not relative changes; never convert across dimensions.
    "percentage_point": ("point_difference", Fraction(1)),
    "usd": ("money", Fraction(1)),
    "usd_thousand": ("money", Fraction(1000)),
    "usd_million": ("money", Fraction(1000000)),
    "usd_billion": ("money", Fraction(1000000000)),
    "count": ("count", Fraction(1)),
    "count_thousand": ("count", Fraction(1000)),
    "boolean": ("boolean", Fraction(1)),
}
POLICY = """Audited financial QA v1, derived from FinQA dev; not official FinQA accuracy.
Twenty previously unused question IDs were selected in seeded order and audited before calls.
Ambiguous or inconsistent questions were excluded before observing candidate answers.
Every candidate receives the same document, table, question, prompt and output cap.
The candidate must declare its final program's unit. Only predeclared compatible units
convert to the question's canonical unit. No answer-dependent scale/sign/denominator repair.
Ratio and percent may represent the same proportion; percentage-point difference is a
different dimension. Requested-unit compliance is reported separately from numeric correctness.
Arithmetic uses exact rational operands for add/subtract/multiply/divide and table operations.
Exponentiation retains the bounded interpreter's floating-point implementation.
Round once, after conversion to the canonical unit, to five decimal places, ties to even.
All scheduled questions remain in the primary denominator, including invalid and failed responses.
Fences and arrays of complete operation strings may normalize; raw strict correctness remains.
Wilson 95% intervals describe this small screened sample, not population-wide model superiority.
Existing model-specific reasoning settings are preserved; provider defaults are not assumed equal.
Costs are configured-rate successful-response/runtime estimates, not total experiment bills.
Provisioning/download/idle GPU time and failed/retried calls are excluded; expired prices withheld.
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rational_number(text):
    """Same numeric syntax as FinQA, exact decimal/percent conversion."""
    if len(text) > 128:
        raise ValueError("numeric literal too long")
    finqa.number(text)  # syntax, finite float range, and constant validation
    text = text.strip().replace(",", "")
    if text.startswith("const_"):
        text = text[6:]
        if text == "m1":
            text = "-1"
    return Fraction(text[:-1].strip()) / 100 if text.endswith("%") else Fraction(text)


def rounded(value):
    value = value if isinstance(value, Fraction) else Fraction(str(value))
    with localcontext() as ctx:
        ctx.prec = max(60, len(str(abs(value.numerator))) + len(str(value.denominator)) + 10)
        return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
            Decimal("0.00001"), rounding=ROUND_HALF_EVEN)


def convert(value, source_unit, target_unit):
    if source_unit not in UNITS:
        raise finqa.ProgramError("invalid_unit", "missing or unsupported declared unit")
    if target_unit not in UNITS or UNITS[source_unit][0] != UNITS[target_unit][0]:
        raise finqa.ProgramError("incompatible_unit", "declared unit has the wrong dimension")
    if source_unit == "boolean":
        if value not in ("yes", "no"):
            raise finqa.ProgramError("incompatible_unit", "boolean unit requires yes or no")
        return value
    if isinstance(value, (str, bool)):
        raise finqa.ProgramError("incompatible_unit", "numeric unit requires a numeric result")
    value = value if isinstance(value, Fraction) else Fraction(str(value))
    return rounded(value * UNITS[source_unit][1] / UNITS[target_unit][1])


def _score(record, prediction):
    result = {
        "id": record["id"], "correct": False, "evidence_exact": False,
        "execution_result": None, "raw_execution_result": None,
        "canonical_unit": record["audit"]["canonical_unit"],
        "requested_unit": record["audit"]["requested_unit"], "declared_unit": None,
        "unit_valid": False, "requested_unit_compliant": False, "program_valid": False,
        "prediction_sha256": finqa.digest(prediction),
    }
    if prediction is None:
        return {**result, "status": "missing"}
    text = prediction.get("output_text")
    if (prediction.get("error") is not None or not isinstance(text, str) or not text.strip()
            or prediction.get("response_status", "completed") != "completed"):
        return {**result, "status": "request_failed"}
    if prediction.get("finish_reason") in {"length", "max_tokens"}:
        return {**result, "status": "request_failed", "evaluation_error_code": "truncated"}
    try:
        payload = json.loads(prediction["output_text"])
        if not isinstance(payload, dict):
            raise finqa.ProgramError("invalid_payload", "expected JSON object")
        value = finqa.execute(payload.get("program"), record["table"],
                              round_final=False, numeric_parser=rational_number)
        result.update(program_valid=True, raw_execution_result=str(value))
        unit = payload.get("unit")
        if not isinstance(unit, str):
            raise finqa.ProgramError("invalid_unit", "unit must be a declared string")
        result["declared_unit"] = unit
        canonical = convert(value, unit, result["canonical_unit"])
        expected = rounded(Fraction(record["audit"]["expected_rational"]))
        result.update(
            unit_valid=True, requested_unit_compliant=unit == result["requested_unit"],
            execution_result=float(canonical), correct=canonical == expected,
        )
    except (ValueError, TypeError, OverflowError, ArithmeticError) as error:
        code = "invalid_json" if isinstance(error, json.JSONDecodeError) else getattr(error, "code", "invalid_program")
        return {**result, "status": "invalid_program", "evaluation_error": str(error),
                "evaluation_error_code": code}
    evidence = payload.get("evidence")
    valid = (isinstance(evidence, list) and all(isinstance(item, str) for item in evidence)
             and set(evidence) <= finqa.evidence_ids(record))
    return {**result, "status": "scored", "evidence_valid": valid,
            "evidence_exact": valid and set(evidence) == set(record["gold_evidence"])}


def evaluate_one(record, prediction):
    strict = _score(record, prediction)
    normalized, changes = finqa_compare.normalize_prediction(prediction)
    result = _score(record, normalized)
    return {**result, "strict_correct": strict["correct"], "strict_status": strict["status"],
            "normalizations": changes, "prediction_sha256": finqa.digest(prediction)}


def protocol_identity():
    return {
        "version": VERSION, "policy": POLICY,
        "dataset_sha256": finqa.digest(finqa.read_rows(DATASET)),
        "prompt_sha256": sha(SCENARIO / "prompt.txt"),
        "selection_audit_sha256": sha(SCENARIO / "selection-audit.json"),
        "evaluator_sha256": sha(__file__), "dsl_sha256": sha(finqa.__file__),
        "normalizer_sha256": sha(finqa_compare.__file__), "runner_sha256": sha(runner.__file__),
        "units": {k: [dimension, str(scale)] for k, (dimension, scale) in UNITS.items()},
    }


def verify_freeze():
    saved = json.loads(FREEZE.read_text())
    if saved["protocol"] != protocol_identity():
        raise ValueError("frozen data/prompt/evaluator changed; do not reuse this protocol or run")
    return saved


def validate_dataset():
    records = finqa.read_rows(DATASET)
    selection = json.loads((SCENARIO / "selection-audit.json").read_text())
    old = {row["id"] for row in finqa.read_rows(ROOT / "data/finqa-dev.jsonl")}
    assert len(records) == 20 and len({r["id"] for r in records}) == 20
    assert not old.intersection(r["id"] for r in records)
    included = [r for r in selection["records"] if r["decision"] == "include"]
    assert [r["source_id"] for r in records] == [r["source_id"] for r in included]
    for record in records:
        expected = rounded(Fraction(record["audit"]["expected_rational"]))
        assert expected == Decimal(str(record["gold_answer"])), record["id"]
        assert record["audit"]["canonical_unit"] in UNITS
        result = evaluate_one(record, {
            "output_text": json.dumps({"program": record["reference_program"],
                                       "unit": record["audit"]["canonical_unit"]}), "error": None,
        })
        assert result["correct"], (record["id"], result)
        prompt = finqa.build_prompt(record, prompt_text=(SCENARIO / "prompt.txt").read_text())
        visible = json.loads(prompt.split("\nDOCUMENT:\n", 1)[1])
        assert set(visible) == {"question", "pre_text", "post_text", "table"}
    return records


def freeze():
    validate_dataset()
    saved = {"frozen_at": datetime.now(timezone.utc).isoformat(), "protocol": protocol_identity()}
    if FREEZE.exists():
        verify_freeze()
        return  # never silently replace the pre-call timestamp
    finqa.write_json(FREEZE, saved)


async def run_candidates(args):
    frozen = verify_freeze()
    args.dataset = str(DATASET)
    args.limit = None
    directory = finqa.run_directory(args.run_id)
    directory.mkdir(parents=True, exist_ok=True)
    with finqa.locked(directory):
        return await finqa.run_candidates(
            args, directory, scenario_name="finqa_audited", extra_contract=frozen)


def wilson(correct, total):
    if not total:
        return None
    z = 1.959963984540054
    p = correct / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total))/denominator
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator
    return [max(0, center-half), min(1, center+half)]


def compose(run_id):
    frozen = verify_freeze()
    comparison = finqa_compare.compose(run_id, evaluation_fn=evaluate_one)
    for model in comparison["models"]:
        directory = finqa.RESULTS / model["source_run_id"]
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["contract"].get("evaluation_protocol") != frozen:
            raise ValueError(f"unfrozen or different evaluation protocol: {model['name']}")
        if manifest["contract"]["scenario"] != "finqa_audited":
            raise ValueError("not an audited run")
        if manifest["executions"][0]["started_at"] < frozen["frozen_at"]:
            raise ValueError("candidate called before protocol freeze")
        evaluations = [r for r in comparison["evaluations"] if r["model"] == model["name"]]
        a = model["aggregate"]
        a.update(
            execution_accuracy_ci95=wilson(a["correct"], a["questions"]),
            program_valid=sum(r["program_valid"] for r in evaluations),
            unit_valid=sum(r["unit_valid"] for r in evaluations),
            requested_unit_compliant=sum(r["requested_unit_compliant"] for r in evaluations),
            unit_errors=sum(r.get("evaluation_error_code") in {"invalid_unit", "incompatible_unit"}
                            for r in evaluations),
            truncated=sum(r.get("evaluation_error_code") == "truncated" for r in evaluations),
        )
        if a["request_failed"] or a["missing"]:
            a.update(estimated_cost_usd=None, estimated_cost_per_question_usd=None,
                     cost_unavailable_reason="incomplete_responses")
        config = model["run_config"]
        model["request_settings"] = {
            "temperature": "omitted/provider default" if config["model_id"] in
                runner.MANTLE_NO_TEMPERATURE | runner.BEDROCK_NO_TEMPERATURE else 0,
            "reasoning_effort": config.get("mantle_reasoning_effort",
                config.get("bedrock_reasoning_effort", "omitted/provider default; effective value unknown")),
            "chat_template_kwargs": config.get("chat_template_kwargs"),
            "max_output_tokens": runner.MAX_OUTPUT_TOKENS,
            "concurrency": config.get("concurrency", 2),
        }
    comparison.update(
        assessment_scope="audited_financial_qa", evaluator=VERSION, evaluator_sha256=sha(__file__),
        policy=POLICY, protocol_freeze=frozen,
        dataset={"questions": 20, "split": "dev", "source": "FinQA-derived screened sample",
                 "seed": 20260919, "selection_audit": "audited-selection-20260919.json"},
        warnings=[
            "새 20문항의 정답·단위를 호출 전에 감사했습니다. 기존 FinQA 실행 점수와 직접 비교하지 마세요.",
            "모델이 선언한 단위로 환산합니다. 숫자를 보고 100배 차이를 임의로 정답 처리하지 않습니다.",
            "20문항·사전 선별 표본입니다. 95% 구간은 참고치이며 금융 업무 전반의 우열을 확정하지 않습니다.",
            "모델별 기존 추론 설정을 유지했습니다. 생략된 설정의 실제 기본값과 추론량이 같다고 보장하지 않습니다.",
            "비용은 설정 단가 기반 추정치입니다. 단가 만료·GPU 준비·유휴·실패 호출 비용 등 한계는 상세에 표시합니다.",
        ],
    )
    return comparison


def write_report(comparison):
    """Standalone complete evidence report; dashboard consumes the same JSON."""
    output = finqa.REPORTS
    output.mkdir(parents=True, exist_ok=True)
    run_id = comparison["run_id"]
    esc = lambda value: html.escape(str(value))
    page = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>감사된 금융 QA 비교</title>
<style>body{font:18px/1.6 system-ui;margin:2rem;color:#172337;overflow-wrap:anywhere}
table{border-collapse:collapse;white-space:nowrap}th,td{padding:.7rem;border:1px solid #ccd3dd}
pre{white-space:pre-wrap}.scroll{overflow:auto}</style>
<nav><a href="../finqa.html">금융 수치 추론 대시보드</a></nav><h1>감사된 금융 QA 비교</h1>"""
    page += f"<p>{esc(run_id)} · 28개 모델 × 20문항</p>"
    page += "".join(f"<p>{esc(w)}</p>" for w in comparison["warnings"])
    page += '<p><a href="audited-selection-20260919.json">문항 선정·제외 근거</a> · <a href="audited-dataset-20260919.json">문서·표·감사 정답</a> · <a href="legacy-audit-20260919.json">이전 560개 응답 진단</a></p>'
    page += "<div class=scroll><table><tr><th>모델</th><th>정답</th><th>정답률</th><th>95% 구간</th><th>선언 단위 유효</th><th>추정 비용/문항</th></tr>"
    for model in sorted(comparison["models"], key=lambda m: (-m["aggregate"]["execution_accuracy"], m["name"])):
        a = model["aggregate"]
        lo, hi = a["execution_accuracy_ci95"]
        cost = a["estimated_cost_per_question_usd"]
        cells = [model["name"], f'{a["correct"]}/20', f'{a["execution_accuracy"]:.1%}',
                 f"{lo:.1%}–{hi:.1%}", f'{a["unit_valid"]}/20',
                 f"${cost:.5f}" if cost is not None else "—"]
        page += "<tr>" + "".join(f"<td>{esc(v)}</td>" for v in cells) + "</tr>"
    page += "</table></div>"
    for model in comparison["models"]:
        page += f"<details><summary>{esc(model['name'])} · 원본 응답·판정·설정</summary><pre>"
        page += esc(json.dumps(model, ensure_ascii=False, indent=2)) + "</pre>"
        for row in comparison["evaluations"]:
            if row["model"] == model["name"]:
                page += "<pre>" + esc(json.dumps(row, ensure_ascii=False, indent=2)) + "</pre>"
        page += "</details>"
    page += "<details><summary>고정 평가 규약</summary><pre>" + esc(POLICY) + "</pre></details></html>"
    finqa.write_json(output / f"{run_id}.json", comparison)
    (output / f"{run_id}.html").write_text(page)
    finqa.write_json(output / "audited-selection-20260919.json",
                     json.loads((SCENARIO / "selection-audit.json").read_text()))
    finqa.write_json(output / "audited-dataset-20260919.json", finqa.read_rows(DATASET))
    index_path = output / "index.json"
    index = json.loads(index_path.read_text())
    index["runs"] = [{"id": run_id, "label": "감사된 금융 QA · 새 20문항 · 28개 모델"}] + [
        {**r, "label": r["label"] if "구 규약" in r["label"] else "구 규약 · " + r["label"]}
        for r in index["runs"] if r["id"] != run_id
    ]
    index["latest"] = run_id
    finqa.write_json(index_path, index)


def selfcheck():
    record = {"id": "check", "table": [], "pre_text": [], "post_text": [], "gold_evidence": [],
              "audit": {"canonical_unit": "ratio", "requested_unit": "percent",
                        "expected_rational": "9/32"}}
    def score(program, unit, rec=record):
        return evaluate_one(rec, {"output_text": json.dumps({"program": program, "unit": unit}), "error": None})
    assert score("divide(45, 160)", "ratio")["correct"]
    assert score("divide(45, 160), multiply(#0, 100)", "percent")["correct"]
    assert not score("divide(45, 160), multiply(#0, 100)", "ratio")["correct"]
    assert not score("divide(45, 160)", "percent")["correct"]
    assert score("divide(45, 160)", "ratio")["requested_unit_compliant"] is False
    for program in ("divide(-45, 160)", "divide(45, 205)", "divide(160, 45)"):
        assert not score(program, "ratio")["correct"]
    for unit in (None, [], "percentage_point", "usd", "Percent"):
        assert not score("divide(45, 160)", unit)["correct"]
    assert not score("divide(1, 0)", "ratio")["correct"]
    assert not score("divide(table_1, 160)", "ratio")["correct"]
    assert not score("divide(45, 160, 2)", "ratio")["correct"]
    assert convert(Fraction("3.4"), "usd_million", "usd_thousand") == Decimal("3400")
    assert convert(Fraction("3.4"), "usd_billion", "usd_million") == Decimal("3400")
    assert rounded(Fraction("0.000005")) == Decimal("0.00000")
    assert rounded(Fraction("0.000015")) == Decimal("0.00002")
    assert rounded(Fraction("-0.000015")) == Decimal("-0.00002")
    # No early rounding: 1/3 percent becomes .00333 ratio, not .0033333->bad equality.
    assert convert(Fraction(1, 3), "percent", "ratio") == Decimal("0.00333")
    assert finqa.execute("divide(1, 3), multiply(#0, 3)", [],
                         round_final=False, numeric_parser=rational_number) == 1
    raw = {"output_text": '{"program":"divide(45,160)","unit":"ratio"}', "error": None}
    assert evaluate_one(record, raw)["strict_correct"]
    fenced = {**raw, "output_text": "```json\n" + raw["output_text"] + "\n```"}
    assert evaluate_one(record, fenced)["correct"] and not evaluate_one(record, fenced)["strict_correct"]
    assert evaluate_one(record, None)["status"] == "missing"
    assert evaluate_one(record, {**raw, "finish_reason": "length"})["status"] == "request_failed"
    for low, high in (wilson(0, 20), wilson(20, 20), wilson(10, 20)):
        assert 0 <= low <= high <= 1
    validate_dataset()
    request_selfcheck()
    print("Audited units, negative controls, exact arithmetic, leakage and 20 gold references OK")


def request_selfcheck():
    """Inspect real transport payloads for every roster model, without network."""
    import httpx
    from botocore.credentials import Credentials
    from types import SimpleNamespace
    from unittest.mock import patch
    config = runner.load_config()
    roster = json.loads((ROOT / "docs/results/integrated-2026-09-17.json").read_text())
    names = {m["name"] for m in roster["models"]}
    client_class = httpx.AsyncClient

    async def check():
        checked = 0
        for model in config["models"]:
            if model["name"] not in names or model["api"] == "translate" or not model.get("enabled", True):
                continue
            checked += 1
            model_id = model["model_id"]
            if model["api"] == "bedrock_mantle":
                def handle(request):
                    payload = json.loads(request.content)
                    assert payload["model"] == model_id and payload["max_output_tokens"] == 4096
                    assert payload["input"] == [{"role": "user", "content": "offline audit"}]
                    assert ("temperature" in payload) == (model_id not in runner.MANTLE_NO_TEMPERATURE)
                    if "temperature" in payload:
                        assert payload["temperature"] == 0
                    effort = model.get("mantle_reasoning_effort")
                    assert payload.get("reasoning") == ({"effort": effort} if effort else None)
                    assert str(request.url) == runner.mantle_url(model.get("mantle_region", "us-east-1"))
                    return httpx.Response(200, json={
                        "model": model_id, "status": "completed", "error": None,
                        "reasoning": {"effort": effort},
                        "output": [{"type": "message", "status": "completed",
                                    "content": [{"type": "output_text", "text": "ok"}]}],
                        "usage": {"input_tokens": 1, "output_tokens": 2,
                                  "output_tokens_details": {"reasoning_tokens": 1}},
                    })
                with patch("httpx.AsyncClient", side_effect=lambda **kwargs:
                           client_class(transport=httpx.MockTransport(handle), **kwargs)):
                    result = await runner.call_mantle(
                        SimpleNamespace(get_credentials=lambda: Credentials("offline", "offline")),
                        model.get("mantle_region", "us-east-1"), model_id, "offline audit",
                        reasoning_effort=model.get("mantle_reasoning_effort"))
                assert result["reported_model"] == model_id and result["reasoning_tokens"] == 1
            elif model["api"] == "bedrock":
                def converse(**kwargs):
                    assert kwargs["modelId"] == model_id
                    params = kwargs["inferenceConfig"]
                    assert params["maxTokens"] == 4096
                    assert ("temperature" in params) == (model_id not in runner.BEDROCK_NO_TEMPERATURE)
                    if "temperature" in params:
                        assert params["temperature"] == 0
                    extra = kwargs.get("additionalModelRequestFields", {})
                    assert extra.get("reasoning_effort") == model.get("bedrock_reasoning_effort")
                    if model_id in runner.BEDROCK_DISABLE_THINKING:
                        assert extra["thinking"] == {"type": "disabled"}
                    return {"output": {"message": {"content": [{"text": "ok"}]}},
                            "usage": {"inputTokens": 1, "outputTokens": 2}, "stopReason": "end_turn"}
                result = await runner.call_bedrock(SimpleNamespace(converse=converse), model_id,
                    "offline audit", reasoning_effort=model.get("bedrock_reasoning_effort"))
                assert result["finish_reason"] == "end_turn"
            else:
                async def create(**kwargs):
                    assert kwargs["model"] == model_id and kwargs["temperature"] == 0
                    assert kwargs["max_tokens"] == 4096
                    assert kwargs["extra_body"].get("chat_template_kwargs") == model.get("chat_template_kwargs")
                    return SimpleNamespace(model=model_id,
                        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
                        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2))
                result = await runner.call_openai(
                    SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
                    model_id, "offline audit", model.get("chat_template_kwargs"))
                assert result["finish_reason"] == "stop" and result["reported_model"] == model_id
        assert checked == 28
    asyncio.run(check())
    print("28 actual request serializers checked offline; no API calls")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["selfcheck", "freeze", "run", "report"])
    parser.add_argument("--run-id")
    parser.add_argument("--models")
    args = parser.parse_args()
    if args.command == "selfcheck":
        selfcheck()
    elif args.command == "freeze":
        freeze()
    elif args.command == "run":
        if not args.models or not args.run_id:
            parser.error("run requires --models and --run-id")
        raise SystemExit(asyncio.run(run_candidates(args)))
    else:
        if not args.run_id:
            parser.error("report requires --run-id")
        write_report(compose(args.run_id))


if __name__ == "__main__":
    main()
