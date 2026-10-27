"""Disclose observed collection overlap without changing measured scores or costs."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "gpt-6.1-terra"
KOREAN = "bedrock-gpt-6.1-terra-20261027"
ENGLISH = "en-pivot-gpt-6.1-terra-20261027"
NOTE = (
    "GPT-6.1 Terra의 한국어·영어 번역 수집 시간이 일부 겹쳤습니다. 각 작업의 동시성은 8이지만 "
    "같은 모델 서비스에 동시 요청이 발생했습니다. 금융 QA·모델 소개·롯데타워 생성도 한국어 "
    "번역 수집 중에 수행했습니다. 지연·처리량은 관측값이며 단독 부하 실험과 직접 비교에 한계가 있습니다."
)
GRADING_NOTE = (
    "한국어 채점 프로세스는 3,280건을 저장한 뒤 종료되어, 완료된 채점을 보존하고 남은 20건을 "
    "같은 설정으로 이어서 채점했습니다. 번역 응답은 다시 생성하지 않았습니다. "
    "응답 사용량을 받지 못한 중단 평가 호출의 청구액은 채점 비용 추정치에 포함되지 않습니다."
)


def read(path):
    return json.loads(path.read_text())


def interval(run_id):
    manifest = read(ROOT / "results" / run_id / "manifest.json")
    assert len(manifest["executions"]) == 1
    execution = manifest["executions"][0]
    return {"started_at": execution["started_at"], "finished_at": execution["finished_at"]}


def metadata():
    periods = {KOREAN: interval(KOREAN), ENGLISH: interval(ENGLISH)}
    start = max(datetime.fromisoformat(value["started_at"]) for value in periods.values())
    finish = min(datetime.fromisoformat(value["finished_at"]) for value in periods.values())
    assert finish > start
    return {"candidate_collection_intervals": periods,
            "translation_overlap_seconds": (finish - start).total_seconds(),
            "per_job_concurrency": 8, "isolated_model_service_load": False,
            "other_overlapping_candidate_tasks": ["finqa_audited", "whoami", "lotte-tower"],
            "note": NOTE}


def main():
    scheduling = metadata()
    report_ids = [KOREAN, ENGLISH, ENGLISH + "-judge2", "integrated-2026-10-27",
                  "en-pivot-20261027", "en-pivot-20261027-judge2"]
    reports = {run_id: read(ROOT / "docs/results" / f"{run_id}.json") for run_id in report_ids}
    for run_id, report in reports.items():
        assert report["run_id"] == run_id
        candidate = next(model for model in report["models"] if model["name"] == NAME)
        candidate["measurement_scheduling"] = scheduling
        if NOTE not in report.get("interpretation", ""):
            report["interpretation"] = (report.get("interpretation") or "") + "\n\n" + NOTE
        if run_id in (KOREAN, "integrated-2026-10-27"):
            candidate["evaluation_execution_note"] = GRADING_NOTE
            if GRADING_NOTE not in report["interpretation"]:
                report["interpretation"] += "\n\n" + GRADING_NOTE
        if run_id == "integrated-2026-10-27":
            candidate_report = ROOT / "docs/results" / f"{KOREAN}.json"
            source = next(source for source in report["source_reports"] if source["run_id"] == KOREAN)
            source["report_sha256"] = hashlib.sha256(candidate_report.read_bytes()).hexdigest()
        (ROOT / "docs/results" / f"{run_id}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (Path(__file__).parent / "scheduling.json").write_text(json.dumps(scheduling, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(scheduling, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
