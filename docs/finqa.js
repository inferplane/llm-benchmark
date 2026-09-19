"use strict";

const errorLabels = {
  unsupported_reference: "숫자 대신 표·본문 참조",
  wrong_arity: "연산 인자 개수 오류",
  invalid_json: "JSON 형식 오류",
  invalid_payload: "JSON 객체 형식 오류",
  invalid_program: "기타 계산식 오류",
  invalid_unit: "선언 단위 누락·오류",
  incompatible_unit: "단위 차원 불일치",
  truncated: "출력 상한에 따른 잘림",
};
const byId = (id) => document.getElementById(id);
const percent = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
const count = (value) => Number.isFinite(value) ? value.toLocaleString("ko-KR") : "—";
const validId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(id);
const providerLabel = { bedrock: "Bedrock Runtime", bedrock_mantle: "Bedrock Mantle", vllm: "자체 호스팅" };
const costReasonLabel = {
  configured_price_expired: "설정 단가 유효기간 만료로 비용 미표시",
  multiple_gpu_invocations: "여러 GPU 실행이 섞여 비용 미표시",
  incomplete_responses: "실패 응답이 있어 비용 미표시",
  missing_responses: "미응답이 있어 비용 미표시",
};
let selectedEntry = null;
let fallbackId = "finqa-audited-20260919";
const usd = (value) => Number.isFinite(value) ? `$${value.toFixed(5)}` : "—";
const seconds = (value) => Number.isFinite(value) ? value.toFixed(2) : "—";

function sortedModels(models) {
  const order = byId("sort-select").value;
  const metric = (model) => order === "cost" ? model.aggregate.estimated_cost_per_question_usd :
    order === "latency" ? model.aggregate.latency_p50_s : model.aggregate.execution_accuracy;
  return [...models].sort((a, b) => {
    if (order === "name") return a.name.localeCompare(b.name);
    const av = metric(a), bv = metric(b);
    if (Number.isFinite(av) !== Number.isFinite(bv)) return Number.isFinite(av) ? -1 : 1;
    const diff = Number.isFinite(av) ? (order === "accuracy" ? bv - av : av - bv) : 0;
    return diff || a.name.localeCompare(b.name);
  });
}

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
  selectedEntry = entry;
  const { report, id } = entry;
  const audited = report.assessment_scope === "audited_financial_qa";
  byId("protocol-label").textContent = audited ? "감사된 금융 QA · 선언 단위 환산" : "구 규약 · 공식 실행값 일치";
  byId("method-summary").textContent = audited ?
    "이전 20문항을 제외하고 고정 seed 20260919 순서에서 문항을 감사한 새 20문항입니다. 원문과 정답의 단위·분모·시점을 호출 전에 검토했습니다. 계산식 결과를 모델이 선언한 단위로 환산하고, 기준 단위에서 소수점 다섯 자리로 한 번 반올림해 비교합니다. 표본은 사전 선별된 개발 데이터이며 공식 FinQA 점수가 아닙니다." :
    "기존 seed 13의 20문항입니다. 계산식 최종 값을 소수점 다섯 자리로 반올림해 공식 qa.exe_ans와 비교합니다. 단위·분모 불일치가 확인된 과거 규약이므로 새 평가 점수와 직접 비교하지 마세요.";
  byId("audit-links").hidden = !audited;
  byId("model-body").replaceChildren();
  byId("diagnostics").replaceChildren();
  byId("warnings").replaceChildren();
  byId("excluded").replaceChildren();
  for (const warning of report.warnings || []) {
    const p = document.createElement("p");
    p.className = "sub";
    p.textContent = warning;
    byId("warnings").append(p);
  }
  for (const item of report.excluded_models || []) {
    const p = document.createElement("p");
    p.textContent = `제외: ${item.name} — ${item.reason}`;
    byId("excluded").append(p);
  }
  for (const model of sortedModels(report.models)) {
    const m = model.aggregate;
    addRow(byId("model-body"), [
      model.name, providerLabel[model.provider] || "—", `${count(m.correct)} / ${count(m.questions)}`, percent(m.execution_accuracy),
      m.execution_accuracy_ci95 ? m.execution_accuracy_ci95.map(percent).join(" – ") : "—",
      usd(m.estimated_cost_per_question_usd), `${seconds(m.latency_p50_s ?? m.response_latency_median_s)} / ${seconds(m.latency_p95_s)}`,
      count(m.incorrect_result), count(m.invalid_program), count(m.unit_valid), count(m.requested_unit_compliant),
      count(m.format_adjusted), count(m.request_failed), count(m.missing),
    ]);
    const p = document.createElement("p");
    const causes = Object.entries(m.invalid_program_causes || {})
      .filter(([, n]) => n > 0).map(([code, n]) => `${errorLabels[code] || code} ${count(n)}건`);
    p.textContent = `${model.name} — ${causes.join(" · ") || "계산식 실행 불가 없음"}` +
      (m.cost_unavailable_reason ? ` · ${costReasonLabel[m.cost_unavailable_reason] || "비용 추정 불가"}` : "") +
      (audited ? ` · 추론 설정: ${model.request_settings?.reasoning_effort ?? "확인 불가"}` : "");
    byId("diagnostics").append(p);
  }
  if (report.models.length === 1) {
    const { name, aggregate: m } = report.models[0];
    byId("result-summary").textContent = `${name} · 정답 ${count(m.correct)}/${count(m.questions)} · ${percent(m.execution_accuracy)}`;
  } else {
    const completed = report.models.filter((m) => m.aggregate.request_failed === 0 && m.aggregate.missing === 0).length;
    byId("result-summary").textContent = `${report.models.length}개 모델 · 동일 ${count(report.dataset?.questions)}문항 · 응답 수집 완료 ${completed}개`;
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
    fallbackId = index.latest;
    const loaded = await Promise.allSettled(index.runs.map(async (entry) => {
      const report = await loadJson(`finqa-results/${entry.id}.json`);
      if (report.scenario !== "finqa" || report.run_id !== entry.id ||
          !Array.isArray(report.models) || !report.models.length) {
        throw new Error("FinQA 결과 형식이 올바르지 않습니다.");
      }
      return { ...entry, report };
    }));
    const entries = loaded.filter((result) => result.status === "fulfilled").map((result) => result.value);
    if (!entries.some((entry) => entry.id === index.latest)) throw new Error("최신 비교 결과를 불러오지 못했습니다.");
    const select = byId("run-select");
    for (const entry of entries) {
      const option = document.createElement("option");
      option.value = entry.id;
      option.textContent = `${entry.id === index.latest ? "최신 · " : ""}${entry.label}`;
      select.append(option);
      const link = document.createElement("a");
      link.href = `finqa-results/${entry.id}.html`;
      link.textContent = entry.label;
      const single = entry.report.models.length === 1 ? entry.report.models[0] : null;
      const m = single?.aggregate;
      addRow(byId("history-body"), [
        link, single?.name || `${entry.report.models.length}개 모델`,
        single ? `${count(m.correct)} / ${count(m.questions)}` : "모델별 상세",
        percent(m?.execution_accuracy), count(m?.invalid_program),
      ]);
    }
    select.value = index.latest;
    select.addEventListener("change", () => renderSelected(entries.find((entry) => entry.id === select.value)));
    byId("sort-select").addEventListener("change", () => renderSelected(selectedEntry));
    renderSelected(entries.find((entry) => entry.id === index.latest));
    byId("results").hidden = false;
    byId("status").textContent = entries.length === index.runs.length ? "" : "일부 이전 실행을 불러오지 못했습니다. 사용 가능한 결과를 표시합니다.";
  } catch (error) {
    byId("status").textContent = `${error.message} 새로고침하거나 아래의 상세 보고서를 열어주세요.`;
    const link = document.createElement("a");
    link.href = `finqa-results/${fallbackId}.html`;
    link.textContent = " 최신 결과 상세 보고서";
    byId("status").append(link);
  }
}

main();
