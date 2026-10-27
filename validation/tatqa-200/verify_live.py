"""Verify GitHub Pages serves the exact reviewed assets and 200-question report."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://inferplane.github.io/llm-benchmark/"
index = json.loads((ROOT / "docs/tatqa-results/index.json").read_text())
report_path = f"tatqa-results/{index['latest']}.json"
paths = ["tatqa.html", "tatqa.js", "tatqa.css", "index.html", "app.js", "finqa.html",
         "tatqa-results/index.json", report_path]
checks = []
live_report = None
for relative in paths:
    request = Request(BASE + relative, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        assert response.status == 200, relative
        data = response.read()
    local = (ROOT / "docs" / relative).read_bytes()
    assert data == local, f"published asset differs: {relative}"
    checks.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
    if relative == report_path:
        live_report = json.loads(data)

assert live_report["dataset"]["questions"] == 200
assert live_report["dataset"]["documents"] == 200
assert len(live_report["models"]) == 35
assert any(model["name"] == "gpt-6.1-terra" for model in live_report["models"])
assert all(model["metrics"]["total"] == 200 and model["metrics"]["missing"] == 0
           for model in live_report["models"])
assert len(live_report["samples"]) == 200
assert all(len(sample["predictions"]) == 35 for sample in live_report["samples"])
result = {"status": "PASS", "verified_at": datetime.now(timezone.utc).isoformat(),
          "url": BASE + "tatqa.html", "run_id": index["latest"],
          "models": 35, "questions_per_model": 200, "scheduled_answers": 7000,
          "assets": checks}
(ROOT / "validation/tatqa-200/live-verification.json").write_text(
    json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
