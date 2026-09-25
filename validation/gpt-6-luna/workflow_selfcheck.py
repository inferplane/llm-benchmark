"""Exercise the actual collector/report pipeline with mocked provider calls."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import luna_benchmark as b, finqa, run, report, judge

parent = b.verify_parent()
base_translation = b.read(b.BASE_TRANSLATION)
base_qa = b.read(b.BASE_QA)
cfg = run.load_config()
scores = {axis: 4 for axis in [*report.AXES, "overall"]}
scores["judges_used"] = [j["name"] for j in cfg["scenario"]["translation"]["judges"]]
for name in scores["judges_used"]:
    scores.update({f"{name}_{axis}": 4 for axis in [*report.AXES, "overall"]})
    scores.update({f"{name}_tokens_in": 10, f"{name}_tokens_out": 20})
scores["chrf"] = None

with tempfile.TemporaryDirectory(prefix="luna-workflow-") as tmp:
    root = Path(tmp)
    with (patch.object(b, "CONTRACT", root / "contract.json"),
          patch.object(b, "FOLDER", root / "runs" / b.TRANSLATION_RUN),
          patch.object(b, "verify_parent", return_value=parent),
          patch.object(finqa, "RESULTS", root / "qa"),
          patch.object(finqa, "REPORTS", root / "public-qa"),
          patch.object(run, "RESULTS_DIR", root / "runs"),
          patch.object(report, "RESULTS_DIR", root / "runs"),
          patch.object(judge, "RESULTS_DIR", root / "runs"),
          patch.object(report, "DOCS_RESULTS_DIR", root / "public")):
        b.freeze()
        output = {"text": '{"program":"add(1, 0)","unit":"ratio"}', "tokens_in": 10, "tokens_out": 20,
                  "cache_read_tokens": 30, "cache_write_tokens": 40, "reported_input_tokens": 80,
                  "reported_model": "openai.gpt-6-luna", "response_status": "completed",
                  "reported_reasoning": {"effort": "medium"}}
        with (patch.object(run, "make_client", return_value=object()),
              patch.object(run, "call_mantle", new=AsyncMock(return_value=output)) as candidate,
              redirect_stdout(io.StringIO())):
            assert asyncio.run(b.measure("qa")) == 0
        assert candidate.await_count == 20
        result = b.qa_report()
        assert len(result["models"]) == 30 and len(result["evaluations"]) == 600
        assert result["models"][:-1] == base_qa["models"]
        assert result["evaluations"][:-20] == base_qa["evaluations"]
        finqa.write_json(finqa.REPORTS / "index.json", {"runs": []})
        b.publish_qa(result)
        assert "30개 모델" in (finqa.REPORTS / f"{b.QA_RUN}.html").read_text()

        calls = 0
        async def generate(*args, **kwargs):
            global calls
            calls += 1
            if calls == 1:
                error = run.InvalidResponseError("fixture output limit")
                error._request_context = {"phase": "response_validation", "response_status": "incomplete",
                                          "incomplete_reason": "max_output_tokens"}
                error._failed_response = {"output_text": "partial output", "response_status": "incomplete"}
                raise error
            return {**output, "text": "offline translated text"}
        with (patch.object(run, "make_client", return_value=object()),
              patch.object(run, "call_mantle", side_effect=generate),
              redirect_stdout(io.StringIO())):
            assert asyncio.run(b.measure("translation")) == 1
        assert calls == 3300
        b.translation_sources()
        try:
            asyncio.run(b.measure("translation"))
        except AssertionError:
            pass
        else:
            raise AssertionError("candidate regeneration allowed")
        with (patch("boto3.Session", return_value=object()), patch("boto3.client", return_value=object()),
              patch.object(judge, "judge_one", new=AsyncMock(return_value=scores)) as grading,
              redirect_stdout(io.StringIO())):
            assert asyncio.run(b.judge_translations()) == 0
        assert grading.await_count == 3299
        new = b.translation_report()
        diagnostics = new["models"][0]["collection_diagnostics"]
        assert diagnostics["unreturned_outputs"] == 1 and diagnostics["capped_outputs"] == 1
        assert diagnostics["failed_with_partial_text"] == 1
        # Each success costs (10*.11 +20*.55 +30*.011 +40*.1375)/1M = .00001793.
        assert new["models"][0]["aggregate"]["cost_total_usd"] == .0592
        report.write_report(new)
        combined = b.translation_comparison(new)
        assert len(combined["models"]) == 31 and combined["models"][:-1] == base_translation["models"]
        for old, current in zip(base_translation["samples"], combined["samples"]):
            assert all(current["by_model"][k] == v for k, v in old["by_model"].items())
        path = b.FOLDER / "manifest.json"
        original = path.read_bytes()
        for key, value in [("model_id", "wrong"), ("mantle_region", "wrong"), ("price_cache_write", 0),
                           ("temperature_omitted", False), ("mantle_reasoning_effort", "high")]:
            manifest = b.read(path)
            manifest["models"][0][key] = value
            manifest["executions"][0]["models"][0][key] = value
            finqa.write_json(path, manifest)
            try:
                b.translation_sources()
            except AssertionError:
                pass
            else:
                raise AssertionError(f"accepted model mutation: {key}")
            path.write_bytes(original)
        path = b.FOLDER / "translations.jsonl"
        rows = finqa.read_rows(path)
        rows[1]["output_text"] = "changed after judging"
        finqa.write_rows(path, rows)
        try:
            b.translation_report()
        except AssertionError:
            pass
        else:
            raise AssertionError("accepted stale judgments")
print("PASS: 20 QA +3300 translation mocked calls; failure/cap coverage, cache costs,")
print("      source/settings mutations, judge binding, and all previous results preserved.")
