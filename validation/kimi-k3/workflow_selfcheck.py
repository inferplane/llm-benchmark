"""Full mocked extension workflow; no provider calls and only temporary writes."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch
from bench import kimi_benchmark as k, finqa as f, run as r, report, judge

parent = k.verify_parent()
base_translation = json.loads((report.DOCS_RESULTS_DIR/f"{k.BASE_TRANSLATION}.json").read_text())
cfg = r.load_config()
scores = {axis: 4 for axis in [*report.AXES, "overall"]}
scores["judges_used"] = [j["name"] for j in cfg["scenario"]["translation"]["judges"]]
for name in scores["judges_used"]:
    scores.update({f"{name}_{axis}": 4 for axis in [*report.AXES, "overall"]})
    scores.update({f"{name}_tokens_in": 10, f"{name}_tokens_out": 20})
scores["chrf"] = None

with tempfile.TemporaryDirectory(prefix="kimi-exact-head-") as tmp:
    root = Path(tmp)
    with (patch.object(k, "CONTRACT", root/"contract.json"),
          patch.object(k, "verify_parent", return_value=parent),
          patch.object(f, "RESULTS", root/"qa"),
          patch.object(r, "RESULTS_DIR", root/"runs"),
          patch.object(report, "RESULTS_DIR", root/"runs"),
          patch.object(judge, "RESULTS_DIR", root/"runs"),
          patch.object(report, "DOCS_RESULTS_DIR", root/"public")):
        k.freeze()
        candidate = AsyncMock(return_value={
            "text": "offline fixture translation", "tokens_in": 10, "tokens_out": 20,
            "cache_read_tokens": 30, "cache_write_tokens": 40, "finish_reason": "end_turn"})
        with patch.object(r, "make_client", return_value=object()), patch.object(r, "call_bedrock", new=candidate):
            assert asyncio.run(k.measure_translation()) == 0
        assert candidate.await_count == 3300
        assert len(k.verify_translation_sources(False)) == 3300
        print("PASS full real-wrapper mocked collection: 3300 requests and pre-call receipt")

        manifest_path = k.translation_folder()/"manifest.json"
        original_manifest = manifest_path.read_bytes()
        for field, value in [("model_id", "wrong"), ("price_cache_write", 0),
                             ("temperature_omitted", False), ("concurrency", 1),
                             ("request_max_attempts", 17), ("bedrock_reasoning_effort", "high")]:
            modified = json.loads(original_manifest)
            modified["models"][0][field] = value
            modified["executions"][-1]["models"][0][field] = value
            manifest_path.write_text(json.dumps(modified))
            try:
                k.verify_translation_sources(False)
            except ValueError:
                print("PASS rejects consistent flat/history model mutation:", field)
            else:
                raise AssertionError(field)
        manifest_path.write_bytes(original_manifest)

        with (patch("boto3.Session", return_value=object()), patch("boto3.client", return_value=object()),
              patch.object(judge, "judge_one", new=AsyncMock(return_value=scores)) as judging):
            assert asyncio.run(k.judge_translation()) == 0
        assert judging.await_count == 3300
        assert len(k.verify_translation_sources()) == 3300
        print("PASS full real-wrapper mocked judging: 3300 judgments, two raw score groups and input binding")

        translated = k.translation_folder()/"translations.jsonl"
        before = translated.read_bytes()
        changed = f.read_rows(translated)
        changed[0]["output_text"] = "different after judging"
        f.write_rows(translated, changed)
        try:
            k.verify_translation_sources()
        except ValueError:
            print("PASS stale judge-input rejected")
        else:
            raise AssertionError("stale input accepted")
        translated.write_bytes(before)

        built = k.build_translation_report()
        assert built["models"][0]["aggregate"]["segments"] == 3300
        assert built["models"][0]["aggregate"]["judged_segments"] == 3300
        # 3300 * (10*3.3+20*16.5+30*.33+40*4.125)/1M = 1.77507.
        assert built["models"][0]["aggregate"]["cost_total_usd"] == 1.7751
        f.write_json(report.DOCS_RESULTS_DIR/f"{k.BASE_TRANSLATION}.json", base_translation)
        f.write_json(report.DOCS_RESULTS_DIR/f"{k.TRANSLATION_RUN}.json", built)
        combined = k.translation_comparison()
        assert len(combined["models"]) == 30 and combined["models"][:-1] == base_translation["models"]
        assert len(combined["samples"]) == len(base_translation["samples"]) == 210
        for old, new in zip(base_translation["samples"], combined["samples"]):
            assert all(new["by_model"][name] == value for name,value in old["by_model"].items())
        print("PASS complete rebuild+append; 29 old models and all old sample entries preserved; cost $1.7751")

        bad = deepcopy(built)
        bad["models"][0]["aggregate"]["segments"] = 1
        f.write_json(report.DOCS_RESULTS_DIR/f"{k.TRANSLATION_RUN}.json", bad)
        try:
            k.translation_comparison()
        except ValueError:
            print("PASS changed published metrics rejected by exact source rebuild")
        else:
            raise AssertionError("tampered report accepted")
print("All exact-HEAD independent workflow probes completed without provider calls.")
