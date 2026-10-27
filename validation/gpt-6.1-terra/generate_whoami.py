"""Use the retained collector with the active model/task route hierarchy."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench import run
from tools import generate_self_portraits as collector


def main():
    cfg = run.load_config()
    model = next(m for m in cfg["models"] if m["name"] == "gpt-6.1-terra")
    collector.GENERATION = "free-expression-20261012"
    collector.RECORDS = ROOT / "results/model-self-portraits/generations" / collector.GENERATION
    collector.ARTIFACT_SUBDIR = "whoami"
    run.MAX_OUTPUT_TOKENS = 16384
    asyncio.run(collector.generate_one(model, cfg["aws"]["region"], asyncio.Semaphore(1)))


if __name__ == "__main__":
    main()
