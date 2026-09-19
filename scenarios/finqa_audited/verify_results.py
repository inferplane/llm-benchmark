"""Verify published artifacts against retained sources and direct cost arithmetic.

uv run python -m scenarios.finqa_audited.verify_results --run-id finqa-audited-20260919
No API calls or score changes. Writes a verification record after all assertions pass.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from bench import finqa, finqa_audited as audited, run as runner


def verify(run_id):
    frozen = audited.verify_freeze()
    report_path = finqa.REPORTS / f"{run_id}.json"
    report = json.loads(report_path.read_text())
    # This equality proves reproducibility, not independent semantic correctness.
    assert report == audited.compose(run_id)
    records = finqa.read_rows(audited.DATASET)
    wanted = {r["id"] for r in records}
    assert len(report["models"]) == 28 and len(report["evaluations"]) == 560
    config = {m["name"]: m for m in runner.load_config()["models"]}
    checks = []
    for model in report["models"]:
        name = model["name"]
        directory = finqa.RESULTS / model["source_run_id"]
        manifest = json.loads((directory / "manifest.json").read_text())
        physical = finqa.read_rows(directory / "answers.jsonl")
        responses = runner.dedupe_latest(physical, lambda r: (r["model"], r["id"]))
        assert len(responses) == 20 and {r["id"] for r in responses} == wanted
        assert all(r["model"] == name for r in responses)
        assert all(r["error"] is None and r.get("response_status", "completed") == "completed" for r in responses)
        capped = sum(r.get("finish_reason") in {"length", "max_tokens"} for r in responses)
        assert manifest["contract"]["evaluation_protocol"] == frozen
        assert datetime.fromisoformat(manifest["executions"][0]["started_at"]) >= datetime.fromisoformat(frozen["frozen_at"])
        evaluations = [r for r in report["evaluations"] if r["model"] == name]
        assert len(evaluations) == 20 and {r["id"] for r in evaluations} == wanted
        a = model["aggregate"]
        assert a["questions"] == 20 and a["correct"] == sum(r["correct"] for r in evaluations)
        assert a["execution_accuracy"] == a["correct"]/20
        assert a["missing"] == 0 and a["truncated"] == capped
        assert a["request_failed"] == capped  # transport succeeded; capped text is not a completed answer
        assert a["incorrect_result"] + a["correct"] + a["invalid_program"] + a["request_failed"] == 20
        assert model["status"] == ("incomplete" if capped else "complete")
        by_id = {r["id"]: r for r in responses}
        assert all(r["prediction_sha256"] == finqa.digest(by_id[r["id"]]) for r in evaluations)

        # Independent arithmetic from all successful response token totals and
        # the historical model rates. Match documented shared-report rounding.
        cfg = manifest["contract"]["models"][0]
        tokens_in = sum(r["tokens_in"] for r in responses)
        tokens_out = sum(r["tokens_out"] for r in responses)
        assert a["tokens_in"] == tokens_in and a["tokens_out"] == tokens_out
        expected_cost = None
        expired = config[name].get("pricing_valid_until", "9999-12-31") < manifest["executions"][0]["started_at"][:10]
        if cfg.get("base_url"):
            serving = json.loads((directory / "serving.json").read_text())
            assert serving["model_id"] == cfg["model_id"]
            assert serving["node_instance_type"] == cfg["gpu_instance_type"]
            assert serving["tensor_parallel_size"] == cfg["tensor_parallel_size"]
            assert serving["max_model_len"] == 8192
            assert serving["enable_service_links"] is False
            assert all(flag in serving["vllm_args"] for flag in cfg.get("extra_vllm_args", []))
            assert serving["image_id"].endswith(frozen["protocol"]["scenario_config"]["vllm_image"].split("@")[1])
            assert datetime.fromisoformat(serving["verified_before_call_at"]) <= datetime.fromisoformat(manifest["executions"][0]["started_at"])
            token_counts = json.loads((directory / "input-token-counts.json").read_text())
            assert {r["id"] for r in token_counts} == wanted
            assert max(r["input_tokens"] for r in token_counts) + 4096 <= 8192
            token_check = json.loads((directory / "token-count-check.json").read_text())
            assert token_check["checked_responses"] == len(physical) and not token_check["differences"]
            if len(manifest["executions"]) == 1:
                ends = [datetime.fromisoformat(r["timestamp"]) for r in responses]
                starts = [end - timedelta(seconds=r["latency_s"]) for end, r in zip(ends, responses)]
                seconds = (max(ends)-min(starts)).total_seconds()
                throughput = round(tokens_out/seconds, 2)
                assert a["throughput_tok_s"] == throughput
                expected_cost = round(cfg["gpu_hourly_usd"]*tokens_out/(throughput*3600), 4)
        elif not expired:
            expected_cost = round(tokens_in*cfg["price_in"]/1e6 + tokens_out*cfg["price_out"]/1e6, 4)
        if a["request_failed"]:
            expected_cost = None
        assert a["estimated_cost_usd"] == expected_cost, (name, a["estimated_cost_usd"], expected_cost)
        assert a["estimated_cost_per_question_usd"] == (round(expected_cost/20, 5) if expected_cost is not None else None)
        if a["request_failed"]:
            assert a["cost_unavailable_reason"] == "incomplete_responses"
        elif expired:
            assert a["cost_unavailable_reason"] == "configured_price_expired"
        latencies = sorted(r["latency_s"] for r in responses)
        assert a["latency_p50_s"] == round((latencies[9]+latencies[10])/2, 3)
        assert a["latency_p95_s"] == round(latencies[18]*.95+latencies[19]*.05, 3)
        checks.append({
            "model": name, "physical_attempt_rows": len(physical), "retained_responses": 20,
            "transport_failures": 0, "truncated_answers": capped,
            "correct": a["correct"], "status_counts": dict(Counter(r["status"] for r in evaluations)),
            "cost_verified_usd": expected_cost, "answers_file_sha256": audited.sha(directory / "answers.jsonl"),
            "manifest_file_sha256": audited.sha(directory / "manifest.json"),
        })
    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(), "run_id": run_id,
        "report_sha256": audited.sha(report_path), "models": checks,
        "scope": "28/560 original-response coverage, frozen inputs/settings, JSON reproducibility, direct cost/latency arithmetic, GPU serving/token/context evidence. Dataset semantics and evaluator correctness are covered by separate pre-call reviews/tests.",
    }
    finqa.write_json(audited.SCENARIO / "result-verification.json", result)
    print("PASS: all28 / 560 received responses, explicit capped-answer accounting, frozen provenance, costs, latency, GPU context/serving")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    verify(parser.parse_args().run_id)
