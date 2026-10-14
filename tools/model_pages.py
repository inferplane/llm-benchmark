"""Publish model/task routes while preserving each actual author's source."""

import argparse
import hashlib
import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bench import run
from tools import generate_self_portraits as ui
from tools.self_portrait_costs import implementation_cost
from tools.generate_lotte_towers import RECORDS as LOTTE_RECORDS, RUNTIME

MODELS = ROOT / "docs/models"
WHOAMI_RECORDS = ROOT / "results/model-self-portraits/generations/free-expression-20261012"
LABELS = {"generated": "모델 직접 작성", "pending": "작성 대기", "failed": "생성 실패",
          "unavailable": "실행 불가", "not_generative": "코드 생성 없음", "review_held": "검수 보류"}
TASKS = {"whoami": ("나는, 이런 모델입니다.", "각 모델이 직접 표현한 미디어아트 자기소개"),
         "lotte-tower": ("롯데월드타워를 모델링하다.", "각 모델이 직접 작성한 도면·설계 과정·완성 3D")}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_conditions(model, directory, record):
    attempts = []
    for path in (directory / "attempts").glob("*/record.json"):
        row = read(path)
        attempts.append((row.get("requested_at", ""), path, row))
    if not attempts:
        return None
    _, first_path, first = min(attempts, key=lambda item: item[0])
    text = first_path.with_name("prompt.txt").read_text()
    normalized = text.replace(model["model_id"], "{model_id}").replace(model["name"], "{name}")
    return {
        "initial_prompt_normalized_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "initial_max_output_tokens": first.get("max_output_tokens"),
        "latest_max_output_tokens": record.get("max_output_tokens"),
        "initial_temperature": first.get("temperature"),
        "latest_temperature": record.get("temperature"),
        "initial_reasoning_effort": first.get("bedrock_reasoning_effort"),
        "recorded_requests": len(attempts),
        "followup_requests": max(0, len(attempts) - 1),
        "final_outputs_are_controlled_one_shot_comparison": False,
    }


def status_panel(name, task, status, record, review):
    """Explain the current publication state using matching review evidence."""
    esc = ui.escape
    message = record.get("reason", "작성 모델의 원본 또는 독립 검수를 기다리고 있습니다.")
    details = ""
    if status == "failed":
        message = "최신 요청에서 완결된 HTML을 생성하지 못했습니다. 공개할 수 있는 최신 구현이 없습니다."
    elif status == "review_held":
        if review and review.get("artwork_sha256") == record.get("artwork_sha256"):
            message = "모델의 구현은 생성됐지만 독립 검수의 공개 기준을 충족하지 못해 보류했습니다."
            findings = review.get("findings", [])
            if any(
                row.get("severity") == "Critical" and "THREE.Geometry" in row.get("quote", "")
                for row in findings
            ):
                message += " 제공된 3D 실행 환경에서 지원하지 않는 THREE.Geometry를 사용해 화면 초기화에 실패했습니다."
            verdicts = {"FAIL": "실패", "REVIEW": "수정 필요", "PASS": "통과"}
            verdict = verdicts.get(review.get("verdict"), review.get("verdict", "미확인"))
            verdict_label = "품질 검수" if review.get("verdict") == "PASS" else "검수 결과"
            details = (
                f'<p>{verdict_label}: {esc(verdict)} · 치명적 문제 {esc(review.get("critical", 0))}개 · '
                f'경고 {esc(review.get("warnings", 0))}개.</p>'
            )
            if task == "lotte-tower" and review.get("task_requirements_complete") is False:
                details += "<p>도면·설계 과정·완성 3D의 필수 요구사항도 충족하지 못했습니다.</p>"
            if findings:
                severity = {"Critical": "치명적 문제", "Warning": "경고", "Suggestion": "개선 제안"}
                details += (
                    '<details class="review-findings"><summary>검수 지적 사항 원문</summary>'
                    '<p>실제 검수 기록의 원문입니다. 각 항목은 현재 생성된 코드에 대한 지적입니다.</p><ul>'
                    + "".join(
                        f'<li><strong>{esc(severity.get(row.get("severity"), row.get("severity", "")))}</strong>'
                        f'<p lang="en">{esc(row.get("problem", ""))}</p></li>'
                        for row in findings
                    )
                    + "</ul></details>"
                )
            details += '<p>프롬프트와 비용은 상단에서, 전체 검수 기록은 <a href="provenance.json">작성 기록 원문</a>에서 확인할 수 있습니다.</p>'
        else:
            message = "모델의 구현은 생성됐습니다. 현재 원본과 일치하는 독립 검수 결과를 기다리고 있습니다."
    return (
        f'<main class="unavailable review-status"><h1>{esc(name)}</h1><h2>{esc(TASKS[task][0])}</h2>'
        f'<p>{esc(LABELS.get(status, status))}</p><p>{esc(message)}</p>{details}</main>'
    )


def task_page(model, task, reviews):
    name = model["name"]
    directory = MODELS / name / task
    directory.mkdir(parents=True, exist_ok=True)
    records = WHOAMI_RECORDS if task == "whoami" else LOTTE_RECORDS
    record_path = records / name / "record.json"
    record = read(record_path) if record_path.exists() else {"status": "pending"}
    if not model.get("enabled", True):
        record = {**record, "status": "unavailable", "reason": "기존 GPU 메모리 제약으로 비활성인 모델입니다."}
    if model["api"] == "translate":
        record = {**record, "status": "not_generative", "reason": "번역 서비스이며 HTML을 작성하는 모델이 아닙니다."}
    if task == "whoami":
        # The old raw-source URLs remain valid; copied bytes aren't regenerated.
        for filename in ("artwork.html", "preview.jpg"):
            source = MODELS / name / filename
            if source.exists() and not (directory / filename).exists():
                shutil.copy2(source, directory / filename)
    status = record["status"]
    artifact = directory / "artwork.html"
    review = reviews.get(name) if reviews is not None else None
    if status == "generated":
        if reviews is not None and not (
            review and review.get("verdict") == "PASS" and review.get("score", 0) >= 85
            and review.get("critical") == 0 and review.get("warnings", 999) <= 3
            and review.get("artwork_sha256") == record["artwork_sha256"]
            and (task != "lotte-tower" or review.get("task_requirements_complete") is True)
        ):
            status = "review_held"
        if artifact.exists():
            assert sha(artifact) == record["artwork_sha256"], name
        elif status == "generated":
            raise AssertionError(f"Approved original is missing: {name}/{task}")
    ui.RECORDS = records
    prompts = ui.recorded_prompts(name, record)
    active = {row["file"] for row in prompts}
    for filename in ("prompt.txt", "initial-prompt.txt"):
        if filename not in active:
            (directory / filename).unlink(missing_ok=True)
    for row in prompts:
        (directory / row["file"]).write_text(row["text"])
    generation = record.get("generation", records.name)
    cost = implementation_cost(model, records / name, generation) if record_path.exists() else {
        "kind": "not_measured", "generation": generation, "estimated_total_usd": None, "recorded_attempts": 0}
    provenance = {
        "model": name, "task": task, "requested_model_id": model["model_id"],
        "provider": "vllm" if model.get("base_url") else model["api"], "family": ui.family(model),
        "generation": generation, "source_records": str((records / name).relative_to(ROOT)),
        "status": status, "generation_status": record["status"],
        "artwork_sha256": record.get("artwork_sha256"), "content_review": review,
        "prompt_sha256": record.get("prompt_sha256"),
        "initial_prompt_sha256": prompts[0]["sha256"] if prompts else None,
        "implementation_cost": cost,
        **{key: record[key] for key in (
            "request_id", "response_id", "requested_at", "generated_at", "reported_model",
            "tokens_in", "tokens_out", "max_output_tokens", "temperature", "temperature_sent",
            "bedrock_reasoning_effort", "reported_reasoning", "finish_reason") if key in record},
    }
    conditions = request_conditions(model, records / name, record) if task == "lotte-tower" else None
    if conditions:
        provenance["request_conditions"] = conditions
    imported = records / name / "import-provenance.json"
    if imported.exists():
        history = read(imported)
        provenance["imported_history"] = history
        provenance["current_response_reused"] = (
            sha(record_path) == history.get("original_record_sha256")
            and record.get("status") == "generated"
        )
    for filename, value in (("provenance.json", provenance), ("implementation-cost.json", cost)):
        ui.write_json(directory / filename, value)
    esc = ui.escape
    panel = (
        f'<iframe title="{esc(name)} · {esc(task)} 원본 구현" data-artwork="artwork.html" sandbox="allow-scripts" '
        'allow="autoplay \'none\'; camera \'none\'; microphone \'none\'; geolocation \'none\'"></iframe>'
        if status == "generated" else
        status_panel(name, task, status, record, review)
    )
    note = (
        "도면·형상은 공개 자료 기반의 개념 재구성이며 공식 시공 도면이 아닙니다."
        if task == "lotte-tower" else
        "작품은 해당 모델의 실제 응답입니다." if status == "generated" else
        "현재 이 페이지는 모델의 작성·검수 상태를 안내합니다."
    )
    fee = '<button type="button" data-open-cost>구현 비용 내역</button>' if cost["kind"] != "not_measured" else ""
    original = '<a href="artwork.html" target="_blank" rel="noopener">원본 구현 ↗</a>' if status == "generated" else ""
    condition_note = (
        f'<p>최초 출력 한도: {conditions["initial_max_output_tokens"]:,} 토큰 · '
        f'최신 요청 한도: {conditions["latest_max_output_tokens"]:,} 토큰 · '
        f'추가 요청: {conditions["followup_requests"]}회.<br>'
        '최초 요청 본문은 공통이며, 이후 수정 요청과 출력 한도는 모델별로 다릅니다. '
        '최종본은 동일 조건의 일회성 성능 비교 결과로 해석할 수 없습니다.</p>'
        if conditions else ""
    )
    directory.joinpath("index.html").write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(name)} · {esc(task)}</title><link rel="icon" href="../../../favicon.svg">'
        '<link rel="stylesheet" href="../../portraits.css"><link rel="stylesheet" href="../../readability.css">'
        '<script src="../../viewer.js" defer></script></head><body class="viewer"><header class="viewer-bar">'
        f'<a href="../">← 모델 홈</a><span><strong>{esc(name)} · {esc(task)}</strong>'
        f'<small>{esc(LABELS.get(status, status))}</small><small>{esc(ui.cost_summary(cost))}</small></span>'
        '<div class="viewer-actions">' + ('<button type="button" data-open-prompts>프롬프트</button>' if prompts else "")
        + f'<details><summary>작성 기록</summary><section><p>{esc(model["model_id"])}</p><p>{note}</p>{condition_note}'
        + fee + f'<a href="provenance.json" target="_blank" rel="noopener">작성자·응답 기록</a>{original}'
        + '</section></details></div></header>' + panel
        + ui.prompt_dialog(prompts, name, initial_first=task == "lotte-tower")
        + ui.cost_dialog(cost, name) + '</body></html>'
    )
    return provenance


def model_home(model, tasks):
    esc = ui.escape
    name = model["name"]
    cards = []
    for task, item in tasks.items():
        directory = MODELS / name / task
        preview = (
            f'<img src="{task}/preview.jpg" alt="{esc(name)}의 {esc(task)} 실제 화면" loading="lazy">'
            if (directory / "preview.jpg").exists() and item["status"] == "generated"
            else f'<div class="placeholder"><span>{task.upper()}</span><strong>{esc(TASKS[task][0])}</strong></div>'
        )
        cards.append(f'<a class="portrait-card" href="{task}/"><div class="preview">{preview}</div>'
                     f'<div class="caption"><small>{task.upper()}</small><h2>{esc(TASKS[task][0])}</h2>'
                     f'<p>{esc(TASKS[task][1])}</p><span>{esc(LABELS.get(item["status"], item["status"]))} ↗</span>'
                     f'<p class="implementation-cost">{esc(ui.cost_summary(item["implementation_cost"]))}</p></div></a>')
    (MODELS / name / "index.html").write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{esc(name)} · 모델 홈</title><link rel="stylesheet" href="../portraits.css">'
        '<link rel="stylesheet" href="../readability.css"></head><body class="catalog">'
        f'<header><a href="../">← 전체 모델</a><span>{esc(ui.family(model))}</span></header>'
        f'<main><section class="intro"><p>ONE MODEL · TWO EXPERIENCES</p><h1>{esc(name)}</h1>'
        f'<div>{esc(model["model_id"])}<br>이 모델의 두 가지 항목과 작성 상태를 확인하세요. 실제 결과가 있는 항목에서 원본·프롬프트·비용을 볼 수 있습니다.</div></section>'
        '<section class="portrait-grid" style="grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr))">'
        + "".join(cards) + '</section></main></body></html>'
    )


def model_alias(model, target):
    """Preserve old URLs while directing visitors to the configured model."""
    assert not model.get("enabled", True), "Only inactive entries can be page aliases"
    assert target.get("enabled", True) and target["api"] in {"bedrock", "bedrock_mantle"}
    name = model["name"]
    redirects = {}
    for task in ("", *TASKS):
        directory = MODELS / name / task
        directory.mkdir(parents=True, exist_ok=True)
        relative = ("../" if not task else "../../") + target["name"] + "/"
        if task:
            relative += task + "/"
        esc = ui.escape
        directory.joinpath("index.html").write_text(
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="refresh" content="0;url={esc(relative)}">'
            f'<title>{esc(target["name"])} · Bedrock</title>'
            '<style>body{margin:0;padding:32px;background:#111310;color:#ece8de;'
            'font:19px/1.7 system-ui,sans-serif}a{color:#d7eb98}</style></head><body>'
            '<p>Gemma의 Bedrock 결과 페이지로 이동합니다.</p>'
            f'<a href="{esc(relative)}">{esc(target["name"])} 결과 보기</a></body></html>'
        )
        redirects[task or "home"] = relative
    entry = {
        "alias": name, "target_model": target["name"],
        "requested_model_id": target["model_id"], "provider": target["api"],
        "redirects": redirects,
    }
    ui.write_json(MODELS / name / "model.json", entry)
    return entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lotte-review")
    args = parser.parse_args(argv)
    cfg = run.load_config()
    whoami = {row["model"]: row for row in read(ROOT / "validation/self-portraits/free-expression-review.json")["artifacts"]}
    lotte = {row["model"]: row for row in read(Path(args.lotte_review))["artifacts"]} if args.lotte_review else None
    entries, cards, aliases = [], [], []
    configured = {model["name"]: model for model in cfg["models"]}
    for model in cfg["models"]:
        if model.get("page_alias"):
            aliases.append(model_alias(model, configured[model["page_alias"]]))
            continue
        tasks = {task: task_page(model, task, whoami if task == "whoami" else lotte) for task in TASKS}
        model_home(model, tasks)
        entry = {"model": model["name"], "requested_model_id": model["model_id"], "family": ui.family(model), "tasks": tasks}
        ui.write_json(MODELS / model["name"] / "model.json", entry)
        entries.append(entry)
        esc = ui.escape
        preview_file = MODELS / model["name"] / "whoami/preview.jpg"
        preview = (
            f'<img src="{esc(model["name"])}/whoami/preview.jpg" alt="{esc(model["name"])}의 WHOAMI 실제 화면" loading="lazy">'
            if preview_file.exists() and tasks["whoami"]["status"] == "generated" else
            f'<div class="placeholder"><span>{esc(ui.family(model))}</span><strong>{esc(model["name"])}</strong></div>'
        )
        cards.append(f'<a class="portrait-card" href="{esc(model["name"])}/" data-family="{esc(ui.family(model))}" '
                     f'data-name="{esc(model["name"])}"><div class="preview">{preview}</div><div class="caption">'
                     f'<h2>{esc(model["name"])}</h2><p>WHOAMI · {esc(LABELS.get(tasks["whoami"]["status"], tasks["whoami"]["status"]))}</p>'
                     f'<p>LOTTE TOWER · {esc(LABELS.get(tasks["lotte-tower"]["status"], tasks["lotte-tower"]["status"]))}</p></div></a>')
    ui.write_json(MODELS / "catalog.json", entries)
    ui.write_json(MODELS / "aliases.json", aliases)
    shutil.copy2(ROOT / "tools/lotte_tower_prompt.txt", MODELS / "lotte-tower-initial-prompt.txt")
    families = sorted({entry["family"] for entry in entries})
    filters = '<button type="button" data-family="all" class="active" aria-pressed="true">전체</button>' + "".join(
        f'<button type="button" data-family="{ui.escape(value)}" aria-pressed="false">{ui.escape(value)}</button>'
        for value in families
    )
    (MODELS / "index.html").write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>모델별 구현 · WHOAMI / LOTTE TOWER</title><link rel="stylesheet" href="portraits.css">'
        '<link rel="stylesheet" href="readability.css"><script src="catalog.js" defer></script></head><body class="catalog"><header><a href="../">LLM BENCHMARK</a>'
        '<span>EACH MODEL’S OWN IMPLEMENTATION</span></header><main><section class="intro"><p>MODEL / EXPERIENCE</p>'
        '<h1>하나의 모델,<br>두 개의 화면.</h1><div>모델을 선택하고 WHOAMI 자기소개와 LOTTE TOWER 3D 모델링을 확인하세요.'
        '<br>각 모델의 원본 코드·프롬프트·작성 비용을 항목별로 분리했습니다.</div>'
        '<div>롯데타워의 최초 요청 본문은 공통입니다. 최종본에는 모델별 추가 수정과 서로 다른 출력 한도가 적용됐습니다.'
        ' 최초 결과·수정본의 조건은 각 페이지의 작성 기록에서 확인하세요. '
        '<a href="lotte-tower-initial-prompt.txt">공통 최초 프롬프트 ↗</a></div></section>'
        '<section class="toolbar"><label class="search"><span>모델 검색</span><input id="search" type="search" '
        'placeholder="모델 이름 검색" autocomplete="off"></label><div class="filters" aria-label="모델 계열 필터">'
        + filters + '</div></section><section class="portrait-grid">'
        + "".join(cards) + '</section><p id="empty" hidden>검색 조건에 맞는 모델이 없습니다.</p></main></body></html>'
    )
    print("Model/task pages built:", len(entries), "models,", len(TASKS), "tasks;",
          len(aliases), "compatibility aliases")


if __name__ == "__main__":
    main()
