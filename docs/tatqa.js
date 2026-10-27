"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const types = {
    span: { label: "단일 답 추출", description: "표나 본문에서 하나의 답을 찾는 질문입니다." },
    arithmetic: { label: "계산", description: "여러 수치를 읽고 계산해야 하는 질문입니다." },
    "multi-span": { label: "여러 답 추출", description: "하나 이상의 답 항목을 함께 찾아야 하는 질문입니다." },
    count: { label: "개수 세기", description: "조건에 맞는 항목의 개수를 세는 질문입니다." },
  };
  const providers = { bedrock: "Bedrock Runtime", bedrock_mantle: "Bedrock Mantle", openai: "OpenAI 호환 API", vllm: "자체 호스팅" };
  const reasons = {
    configured_price_expired: "설정 단가 유효기간 만료",
    incomplete_responses: "불완전한 응답 기록으로 비용 계산 불가",
    missing_responses: "누락 응답으로 비용 계산 불가",
    multiple_gpu_invocations: "여러 GPU 실행이 섞여 비용 계산 불가",
    missing_token_usage: "사용 토큰 정보 누락",
    missing_pricing: "설정 단가 없음",
    self_hosted_separate_cohort: "자체 호스팅 모델은 별도 실행군",
    self_hosted_requires_separate_execution_cohort: "자체 호스팅 모델은 별도 실행군 필요",
    disabled_in_config: "설정에서 비활성화",
    translation_only_service: "번역 전용 서비스",
  };
  const statuses = {
    scored: "채점 완료", ok: "채점 완료", success: "채점 완료", valid: "채점 완료",
    invalid: "형식 오류 · 0점", invalid_json: "JSON 형식 오류 · 0점", invalid_payload: "답변 형식 오류 · 0점",
    request_failed: "요청 실패 · 0점", request_failure: "요청 실패 · 0점", request_error: "요청 실패 · 0점",
    missing: "응답 누락 · 0점", truncated: "출력 잘림 · 0점",
  };
  const count = (value) => Number.isFinite(value) ? value.toLocaleString("ko-KR") : "—";
  const percent = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
  const money = (value) => Number.isFinite(value) && value >= 0 ? `$${value.toFixed(5)}` : "—";
  const seconds = (value) => Number.isFinite(value) && value >= 0 ? `${value.toFixed(2)}초` : "—";
  const validId = (id) => typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(id);
  const answerText = (value) => value === null || value === undefined ? "—" :
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const scaleText = (value) => value === "" ? "배율 없음" : value === null || value === undefined ? "—" : String(value);
  let entries = [], selectedReport = null, loadVersion = 0;
  const reports = new Map();

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }

  function family(name) {
    return window.BenchmarkView?.family(name) || { label: "모델", color: "#64748b" };
  }

  function modelCell(model) {
    const cell = element("th", undefined, "model-name-cell");
    cell.scope = "row";
    cell.style.setProperty("--family", family(model.name).color);
    cell.append(element("span", model.name, "model-name"), element("span", `${family(model.name).label} · ${providers[model.provider] || model.provider || "제공 경로 미기록"}${model.status === "not_run" ? " · 미실행" : ""}`, "model-provider"));
    return cell;
  }

  function metricCell(value, sub, emphasis = false) {
    const cell = element("td");
    cell.append(element("span", value, emphasis ? "metric-main" : ""));
    if (sub) cell.append(element("span", sub, "metric-sub"));
    return cell;
  }

  function costCell(value, reason) {
    const cell = metricCell(money(value));
    if (!Number.isFinite(value) && reason) cell.append(element("span", reasons[reason] || String(reason), "cost-reason"));
    return cell;
  }

  function fillOptions(select, options, chosen) {
    select.replaceChildren();
    for (const [value, label] of options) {
      const option = element("option", label);
      option.value = value;
      select.append(option);
    }
    if (options.some(([value]) => value === chosen)) select.value = chosen;
  }

  function sortedModels() {
    const order = byId("sort-select").value;
    const key = order === "cost" ? "estimated_cost_per_question_usd" : order === "latency" ? "latency_p50_s" : order;
    return [...selectedReport.models].sort((a, b) => {
      if (order === "name") return a.name.localeCompare(b.name);
      const av = a.metrics[key], bv = b.metrics[key];
      if (Number.isFinite(av) !== Number.isFinite(bv)) return Number.isFinite(av) ? -1 : 1;
      const difference = Number.isFinite(av) ? (order === "cost" || order === "latency" ? av - bv : bv - av) : 0;
      return difference || a.name.localeCompare(b.name);
    });
  }

  function renderModels() {
    const models = sortedModels();
    byId("model-body").replaceChildren();
    byId("coverage-body").replaceChildren();
    for (const model of models) {
      const m = model.metrics;
      const row = element("tr");
      row.append(modelCell(model), metricCell(percent(m.exact_match), `${count(m.correct)} / ${count(m.total)} 완전 일치`, true),
        metricCell(percent(m.f1), undefined, true), metricCell(percent(m.response_coverage)), metricCell(seconds(m.latency_p50_s)),
        costCell(m.estimated_cost_per_question_usd, m.cost_unavailable_reason));
      byId("model-body").append(row);
      const diagnostic = element("tr");
      diagnostic.append(modelCell(model), metricCell(`${count(m.scored)} / ${count(m.total)}`), metricCell(count(m.invalid)),
        metricCell(count(m.request_failures)), metricCell(count(m.missing)), metricCell(count(m.truncated)),
        metricCell(seconds(m.latency_p95_s)), costCell(m.estimated_cost_usd, m.cost_unavailable_reason),
        metricCell(`${count(m.tokens_in)} / ${count(m.tokens_out)}`));
      byId("coverage-body").append(diagnostic);
    }
    const complete = models.filter((m) => m.metrics.response_coverage === 1 && m.metrics.missing === 0 && m.metrics.request_failures === 0).length;
    byId("comparison-summary").textContent = `${models.length}개 모델 · 모델당 ${count(selectedReport.dataset.questions)}문항 · 전체 문항에 잘림 없는 응답이 있는 모델 ${complete}/${models.length}개. ${complete < models.length ? "미완료·실패 문항을 포함한 점수입니다. 아래 응답 상태를 확인하세요." : "응답을 받았어도 형식 오류는 0점입니다."}`;
    renderTypes();
  }

  function renderTypes() {
    if (!selectedReport) return;
    const key = byId("type-select").value;
    byId("type-summary").textContent = `${types[key].label} · ${count(selectedReport.dataset.answer_types[key])}문항. ${types[key].description}`;
    byId("type-body").replaceChildren();
    for (const model of sortedModels()) {
      const m = model.by_answer_type?.[key] || {};
      const row = element("tr");
      row.append(modelCell(model), metricCell(`${count(m.correct)} / ${count(m.total)}`), metricCell(percent(m.exact_match)), metricCell(percent(m.f1)));
      byId("type-body").append(row);
    }
  }

  function filteredSamples() {
    const type = byId("sample-type").value;
    return (selectedReport.samples || []).filter((sample) => type === "all" || sample.answer_type === type);
  }

  function renderSampleOptions() {
    const previous = byId("sample-select").value;
    const samples = filteredSamples();
    fillOptions(byId("sample-select"), samples.map((sample, index) => [String(index), `${index + 1}. ${String(sample.question || sample.id).slice(0, 100)}`]), previous);
    byId("sample-select").disabled = !samples.length;
    renderSample();
  }

  function renderEvidence(sample, question) {
    const table = Array.isArray(sample.table) ? sample.table : sample.table?.table;
    const paragraphs = Array.isArray(sample.paragraphs) ? sample.paragraphs : [];
    const evidence = element("details");
    evidence.append(element("summary", "질문에 제공된 표·본문 근거 보기"));
    if (Array.isArray(table) && table.length) {
      const scroll = element("div", undefined, "scroll");
      scroll.tabIndex = 0;
      scroll.setAttribute("role", "region");
      scroll.setAttribute("aria-label", "질문에 제공된 원문 표");
      const sourceTable = element("table");
      sourceTable.append(element("caption", "모델 입력의 원문 표", "sr-only"));
      const body = element("tbody");
      table.forEach((values, index) => {
        if (!Array.isArray(values)) return;
        const row = element("tr");
        for (const value of values) {
          const cell = element(index === 0 ? "th" : "td", value ?? "");
          if (index === 0) cell.scope = "col";
          row.append(cell);
        }
        body.append(row);
      });
      sourceTable.append(body);
      scroll.append(sourceTable);
      evidence.append(scroll);
    }
    for (const paragraph of paragraphs) evidence.append(element("p", typeof paragraph === "string" ? paragraph : paragraph.text ?? "", "source-paragraph"));
    if (!table?.length && !paragraphs.length) {
      evidence.append(element("p", "이 결과 파일에는 표·본문 입력이 포함되지 않았습니다. 실행의 고정 데이터 기록과 공식 원문에서 근거를 확인하세요.", "customer-note"));
      const link = element("a", "고정한 공식 test 원문 ↗");
      link.href = "https://github.com/NExTplusplus/TAT-QA/blob/870accc41953dcde885aabeb963d94aabdc0fbc3/dataset_raw/tatqa_dataset_test_gold.json";
      evidence.append(link, element("p", `문항 ID: ${sample.id}`, "sample-caption"));
    }
    question.append(evidence);
  }

  function renderSample() {
    if (!selectedReport) return;
    const sample = filteredSamples()[Number(byId("sample-select").value)];
    byId("sample-question").replaceChildren();
    byId("sample-answers").replaceChildren();
    if (!sample) {
      byId("sample-question").append(element("p", "이 유형의 질문별 결과가 없습니다. 전체 결과 JSON을 확인하세요."));
      return;
    }
    const question = byId("sample-question");
    question.append(element("p", `${types[sample.answer_type]?.label || sample.answer_type} · ${sample.id}`, "sample-caption"),
      element("p", sample.question, "question-text"), element("p", `공식 정답: ${answerText(sample.gold_answer)} · scale: ${scaleText(sample.gold_scale)}`));
    renderEvidence(sample, question);
    for (const id of ["sample-model-a", "sample-model-b"]) {
      const name = byId(id).value;
      const prediction = (sample.predictions || []).find((p) => p.model === name);
      const status = prediction?.status || "missing";
      const answer = element("article", undefined, "sample-answer");
      answer.style.setProperty("--family", family(name).color);
      answer.append(element("h3", name), element("span", statuses[status] || status, "status-tag"),
        element("pre", prediction ? answerText(prediction.answer) : "응답 기록 없음"),
        element("p", `scale: ${scaleText(prediction?.scale)}`, "sample-caption"),
        element("p", `EM ${percent(prediction?.exact_match ?? (prediction ? null : 0))} · F1 ${percent(prediction?.f1 ?? (prediction ? null : 0))}`, "sample-caption"));
      if (prediction?.error) answer.append(element("p", prediction.error, "customer-note"));
      if (prediction?.evaluation_error) answer.append(element("p", prediction.evaluation_error, "customer-note"));
      if (prediction?.output_text !== null && prediction?.output_text !== undefined) {
        const raw = element("details");
        raw.append(element("summary", "원본 출력 보기"), element("pre", prediction.output_text));
        answer.append(raw);
      }
      byId("sample-answers").append(answer);
    }
  }

  function renderProtocol(report) {
    byId("protocol-description").textContent = report.protocol.description || "";
    byId("protocol-limitations").replaceChildren();
    const limitations = report.protocol.limitations;
    for (const value of Array.isArray(limitations) ? limitations : limitations ? [limitations] : []) {
      byId("protocol-limitations").append(element("li", value));
    }
    // Keep external provenance links inside the pinned upstream repository.
    try {
      const source = new URL(report.dataset.source_url);
      if (source.protocol === "https:" && source.hostname === "github.com" && source.pathname.startsWith("/NExTplusplus/TAT-QA/")) {
        byId("source-link").href = source.href;
      }
    } catch (_) { /* The static pinned source link remains available. */ }
    byId("provenance").replaceChildren();
    const info = {
      "실행 ID": report.run_id, "보고서 생성 시각": report.generated_at, "사용 split": report.dataset.split, "선정 seed": report.dataset.seed,
      "원본 revision": report.dataset.source_revision, "원본 SHA-256": report.dataset.source_sha256,
      "고정 표본 SHA-256": report.dataset.dataset_sha256, "평가기 revision": report.protocol.official_evaluator_revision,
      "실행 계약 SHA-256": report.contract_sha256, "프롬프트 SHA-256": report.contract?.prompt_sha256,
    };
    for (const [label, value] of Object.entries(info)) byId("provenance").append(element("dt", label), element("dd", value ?? "미기록"));
    const excluded = report.excluded_models || [];
    const labels = excluded.map((model) => typeof model === "string" ? model : `${model.name || model.model || "모델 미기록"} (${reasons[model.reason] || model.reason || "사유 미기록"})`);
    byId("excluded-models").textContent = `${report.models.length}개 모델이 이 실행에 포함됩니다. ${labels.length ? `제외 모델 ${labels.length}개: ${labels.join(" · ")}.` : "기록된 제외 모델이 없습니다."} 자체 호스팅 GPU 모델은 별도 실행군이 필요합니다.`;
    const settings = byId("generation-settings");
    settings.replaceChildren();
    const recorded = report.models.filter((model) => model.request_settings);
    if (recorded.length) {
      settings.append(element("h3", "모델별 생성 조건"));
      const scroll = element("div", undefined, "scroll");
      scroll.tabIndex = 0;
      scroll.setAttribute("role", "region");
      scroll.setAttribute("aria-label", "모델별 생성 조건");
      const table = element("table");
      const head = element("thead"), heading = element("tr");
      for (const label of ["모델", "temperature", "추론 설정", "출력 토큰 상한", "동시성"]) {
        const cell = element("th", label); cell.scope = "col"; heading.append(cell);
      }
      head.append(heading);
      const body = element("tbody");
      for (const model of recorded) {
        const config = model.request_settings;
        const row = element("tr");
        row.append(modelCell(model), metricCell(config.temperature ?? "미기록"), metricCell(config.reasoning_effort ?? "미기록"),
          metricCell(count(config.max_output_tokens)), metricCell(count(config.concurrency)));
        body.append(row);
      }
      table.append(head, body); scroll.append(table); settings.append(scroll);
      settings.append(element("p", "생략된 설정은 제공자 기본값을 사용하므로 실제 추론량이 모델 간 동일하다고 가정하지 않습니다.", "customer-note"));
    }
  }

  function validateReport(report, id) {
    if (!report || report.scenario !== "tatqa" || report.run_id !== id || report.dataset?.questions !== 200 ||
        report.dataset?.documents !== 200 || !report.dataset.answer_types || !report.protocol ||
        !Array.isArray(report.models) || !report.models.length ||
        new Set(report.models.map((model) => model.name)).size !== report.models.length ||
        report.models.some((model) => typeof model.name !== "string" || !model.name || !model.metrics || model.metrics.total !== 200)) {
      throw new Error("TAT-QA 200문항 결과 형식이 올바르지 않습니다.");
    }
    for (const model of report.models) {
      for (const key of ["exact_match", "f1", "response_coverage"]) {
        const value = model.metrics[key];
        if (value !== null && value !== undefined && (!Number.isFinite(value) || value < 0 || value > 1)) {
          throw new Error("TAT-QA 점수 형식이 올바르지 않습니다.");
        }
      }
    }
    return report;
  }

  async function loadJson(path) {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) {
      if (response.status === 404) throw new Error("게시된 결과 파일을 찾지 못했습니다.");
      throw new Error(`결과를 불러오지 못했습니다 (HTTP ${response.status}).`);
    }
    try { return await response.json(); }
    catch (_) { throw new Error("결과 JSON 형식이 올바르지 않습니다."); }
  }

  function setLoadState(state, message) {
    byId("load-state").dataset.state = state;
    byId("load-status").textContent = message;
    byId("retry-load").hidden = state !== "error" && state !== "empty";
    byId("results").hidden = state !== "ready";
    if (state !== "ready") byId("model-count").textContent = "—";
  }

  async function selectRun(id) {
    const version = ++loadVersion;
    setLoadState("loading", "결과를 불러오는 중…");
    try {
      const report = reports.get(id) || validateReport(await loadJson(`tatqa-results/${id}.json`), id);
      if (version !== loadVersion) return;
      reports.set(id, report);
      selectedReport = report;
      byId("model-count").textContent = `${report.models.length}개`;
      byId("question-count").replaceChildren(document.createTextNode(count(report.dataset.questions)), element("small", "문항"));
      byId("context-count").replaceChildren(document.createTextNode(count(report.dataset.documents)), element("small", "맥락"));
      byId("json-link").href = `tatqa-results/${id}.json`;
      byId("run-note").textContent = `실행 ID: ${id}`;
      renderModels();
      const names = sortedModels().map((model) => [model.name, model.name]);
      fillOptions(byId("sample-model-a"), names);
      fillOptions(byId("sample-model-b"), names, names[1]?.[0]);
      renderSampleOptions();
      renderProtocol(report);
      setLoadState("ready", "");
    } catch (error) {
      if (version !== loadVersion) return;
      setLoadState("error", `${error.message} 다시 불러오기를 눌러 재시도하세요. 아래 평가 방식과 출처는 계속 확인할 수 있습니다.`);
    }
  }

  async function main() {
    setLoadState("loading", "결과를 불러오는 중…");
    try {
      const index = await loadJson("tatqa-results/index.json");
      if (!index || !Array.isArray(index.runs)) throw new Error("실행 목록 형식이 올바르지 않습니다.");
      if (!index.runs.length) {
        setLoadState("empty", "아직 게시된 결과가 없습니다. 실제 실행 결과가 게시되면 200문항의 모델 비교를 확인할 수 있습니다.");
        return;
      }
      if (!validId(index.latest) || !index.runs.every((entry) => validId(entry.id)) ||
          !index.runs.some((entry) => entry.id === index.latest) || new Set(index.runs.map((entry) => entry.id)).size !== index.runs.length) {
        throw new Error("실행 목록 형식이 올바르지 않습니다.");
      }
      entries = index.runs;
      fillOptions(byId("run-select"), entries.map((entry) => [entry.id, `${entry.id === index.latest ? "최신 · " : ""}${entry.label || entry.id}`]), index.latest);
      await selectRun(index.latest);
    } catch (error) {
      setLoadState("error", `${error.message} 다시 불러오기를 눌러 재시도하세요. 아래 평가 방식과 출처는 계속 확인할 수 있습니다.`);
    }
  }

  const groups = window.BenchmarkView?.groups || {};
  for (const group of Object.values(groups)) {
    const badge = element("span", undefined, "model-family");
    badge.style.setProperty("--family", group.color);
    const dot = element("span", undefined, "family-dot");
    dot.setAttribute("aria-hidden", "true");
    badge.append(dot, document.createTextNode(group.label));
    byId("family-legend").append(badge);
  }
  byId("run-select").addEventListener("change", () => selectRun(byId("run-select").value));
  byId("sort-select").addEventListener("change", () => { if (selectedReport) renderModels(); });
  byId("type-select").addEventListener("change", renderTypes);
  byId("sample-type").addEventListener("change", renderSampleOptions);
  for (const id of ["sample-select", "sample-model-a", "sample-model-b"]) byId(id).addEventListener("change", renderSample);
  byId("retry-load").addEventListener("click", () => { reports.clear(); main(); });
  main();
})();
