"use strict";

const errorLabels = {
  unsupported_reference: "숫자 대신 표·본문 참조",
  wrong_arity: "연산 인자 개수 오류",
  invalid_json: "JSON 형식 오류",
  invalid_payload: "JSON 객체 형식 오류",
  invalid_program: "기타 계산식 오류",
};
const byId = (id) => document.getElementById(id);
const percent = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
const count = (value) => Number.isFinite(value) ? value.toLocaleString("ko-KR") : "—";
const validId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(id);

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`결과 요청 실패 (${response.status})`);
  return response.json();
}

function addRow(body, values) {
  const row = document.createElement("tr");
  for (const value of values) {
    const cell = document.createElement("td");
    if (value instanceof Node) cell.append(value);
    else cell.textContent = value;
    row.append(cell);
  }
  body.append(row);
}

function renderSelected(entry) {
  const { report, id } = entry;
  byId("model-body").replaceChildren();
  byId("diagnostics").replaceChildren();
  byId("warnings").replaceChildren();
  for (const warning of report.warnings || []) {
    const p = document.createElement("p");
    p.className = "sub";
    p.textContent = warning;
    byId("warnings").append(p);
  }
  for (const model of report.models) {
    const m = model.aggregate;
    addRow(byId("model-body"), [
      model.name, `${count(m.correct)} / ${count(m.questions)}`, percent(m.execution_accuracy),
      count(m.incorrect_result), count(m.invalid_program), count(m.request_failed), count(m.missing),
    ]);
    const p = document.createElement("p");
    const causes = Object.entries(m.invalid_program_causes || {})
      .filter(([, n]) => n > 0).map(([code, n]) => `${errorLabels[code] || code} ${count(n)}건`);
    p.textContent = `${model.name} — ${causes.join(" · ") || "계산식 실행 불가 없음"}`;
    byId("diagnostics").append(p);
  }
  if (report.models.length === 1) {
    const { name, aggregate: m } = report.models[0];
    byId("result-summary").textContent = `${name} · 정답 ${count(m.correct)}/${count(m.questions)} · ${percent(m.execution_accuracy)}`;
  } else {
    byId("result-summary").textContent = `${report.models.length}개 모델 결과`;
  }
  byId("detail-link").href = `finqa-results/${id}.html`;
  byId("json-link").href = `finqa-results/${id}.json`;
}

async function main() {
  try {
    const index = await loadJson("finqa-results/index.json");
    if (!Array.isArray(index.runs) || !index.runs.length ||
        !index.runs.every((entry) => validId(entry.id)) ||
        !index.runs.some((entry) => entry.id === index.latest) ||
        new Set(index.runs.map((entry) => entry.id)).size !== index.runs.length) {
      throw new Error("실행 목록이 올바르지 않습니다.");
    }
    const entries = await Promise.all(index.runs.map(async (entry) => {
      const report = await loadJson(`finqa-results/${entry.id}.json`);
      if (report.scenario !== "finqa" || report.run_id !== entry.id ||
          !Array.isArray(report.models) || !report.models.length) {
        throw new Error("FinQA 결과 형식이 올바르지 않습니다.");
      }
      return { ...entry, report };
    }));
    const select = byId("run-select");
    for (const entry of entries) {
      const option = document.createElement("option");
      option.value = entry.id;
      option.textContent = `${entry.id === index.latest ? "최신 · " : ""}${entry.label}`;
      select.append(option);
      for (const model of entry.report.models) {
        const link = document.createElement("a");
        link.href = `finqa-results/${entry.id}.html`;
        link.textContent = entry.label;
        const m = model.aggregate;
        addRow(byId("history-body"), [
          link, model.name, `${count(m.correct)} / ${count(m.questions)}`,
          percent(m.execution_accuracy), count(m.invalid_program),
        ]);
      }
    }
    select.value = index.latest;
    select.addEventListener("change", () => renderSelected(entries.find((entry) => entry.id === select.value)));
    renderSelected(entries.find((entry) => entry.id === index.latest));
    byId("results").hidden = false;
    byId("status").textContent = "";
  } catch (error) {
    byId("status").textContent = `${error.message} 새로고침하거나 아래의 상세 보고서를 열어주세요.`;
    const link = document.createElement("a");
    link.href = "finqa-results/finqa-nova-lite-pilot-v3-20260917.html";
    link.textContent = " 최신 파일럿 상세 보고서";
    byId("status").append(link);
  }
}

main();
