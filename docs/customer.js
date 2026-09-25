/* Customer-facing interpretation of retained measurements; no new benchmark scores. */
"use strict";
window.BenchmarkView = (() => {
  const groups = {
    gpt: {label:"GPT 계열", color:"#2563eb"},
    claude: {label:"Claude 계열", color:"#8b5cf6"},
    china: {label:"중국 모델", color:"#d97706"},
    us: {label:"그 외 미국 모델", color:"#0d9488"},
    other: {label:"한국·유럽·기타", color:"#64748b"},
  };
  function family(name) {
    const n = String(name).toLowerCase();
    const key = /^gpt-/.test(n) ? "gpt" : /^claude-/.test(n) ? "claude" :
      /^(kimi|qwen|glm|deepseek|yi)-/.test(n) || n.startsWith("qwen") ? "china" :
      /^(nova|amazon|llama|llama4|grok|gemma|nemotron)-/.test(n) ? "us" : "other";
    return {key, ...groups[key]};
  }
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const money = v => !Number.isFinite(v) ? "견적 확인 필요" : v>0 && v<.000001 ? "<$0.000001" :
    new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:v>0 && v<.01 ? 6 : 4}).format(v);
  const time = v => Number.isFinite(v) && v >= 0 ? `${v.toFixed(2)}초` : "측정값 없음";
  function badge(name) {
    const g = family(name);
    return `<span class="model-family" data-family="${g.key}" style="--family:${g.color}"><span class="family-dot" aria-hidden="true"></span>${escape(g.label)}</span>`;
  }
  function legend() {
    return Object.entries(groups).map(([key,g]) => `<span class="model-family" data-family="${key}" style="--family:${g.color}"><span class="family-dot" aria-hidden="true"></span>${g.label}</span>`).join("");
  }
  function measure(m, scenario, track="synthetic") {
    const a = m.aggregate || {};
    const qa = scenario === "qa";
    const q = qa || track === "all" ? a : m.by_track?.[track];
    const successful = qa ? !(a.request_failed || a.missing || a.truncated) && a.response_coverage === 1 :
      a.successful_translations > 0 && a.translation_failures === 0 && a.judge_failures === 0 &&
      a.quality_eligible_segments === a.successful_translations && !(m.collection_diagnostics?.capped_outputs);
    const total=qa ? a.estimated_cost_usd : a.cost_total_usd;
    const units=qa ? a.questions : a.successful_translations;
    const unitCost=Number.isFinite(total) && units>0 ? total/units :
      qa ? a.estimated_cost_per_question_usd : a.cost_per_segment_usd;
    return {model:m, name:m.name, cohort:m.evaluation_cohort || "shared",
      score:qa ? a.execution_accuracy : q?.judge_overall,
      latency:qa ? a.latency_p50_s ?? a.response_latency_median_s : a.latency_e2e_p50_s,
      cost:unitCost,
      total:qa ? a.estimated_cost_usd : a.cost_total_usd,
      complete:successful, quality:q};
  }
  // Selection stays inside each translation prompt cohort. No blended cross-cohort winner.
  function shortlist(models, scenario, track="synthetic") {
    const measured = models.map(m => measure(m,scenario,track));
    const cohortKeys = [...new Set(measured.map(m => m.cohort))];
    const threshold = scenario === "qa" ? .9 : 4;
    return ["quality","volume","interactive"].map(kind => ({kind, candidates:cohortKeys.flatMap(cohort => {
      let pool = measured.filter(m => m.cohort===cohort && m.complete && Number.isFinite(m.score) && m.score >= threshold);
      if (kind !== "quality") pool = pool.filter(m => m.score >= threshold && Number.isFinite(m.cost) && (kind!=="interactive" || Number.isFinite(m.latency)));
      if (!pool.length) return [];
      pool.sort((a,b) => (kind === "quality" ? b.score-a.score : kind === "volume" ? a.cost-b.cost : a.latency-b.latency) ||
        (a.cost ?? Infinity)-(b.cost ?? Infinity) || a.name.localeCompare(b.name));
      return pool.slice(0,scenario==="qa" && kind==="quality" ? 2 : 1);
    })}));
  }
  function pair(preferred, other, names) {
    const first=names.includes(preferred) ? preferred : names[0] || "";
    const second=other!==first && names.includes(other) ? other : names.find(name=>name!==first) || first;
    return [first,second];
  }
  function workload(m,scenario,track="synthetic") {
    const v=measure(m,scenario,track);
    if (!v.complete || !Number.isFinite(v.score)) return "도입 전 추가 확인";
    if (v.score < (scenario==="qa" ? .9 : 4)) return scenario==="qa" ? "수치 정확성 재검증 필요" : "검수 부담을 확인할 초안 작업";
    if (Number.isFinite(v.latency) && v.latency<=2) return "대화형 도우미·반복 업무 검토";
    return "품질 중심의 문서 처리 검토";
  }
  function cards(models,scenario,track,volume) {
    const qa=scenario==="qa";
    const titles=qa ? ["정확성이 중요한 수치 확인","반복 질의의 비용 절감","고객·직원이 기다리는 응답"] :
      ["고객에게 전달할 문서의 번역 초안","대량 문서의 비용 절감","화면에서 바로 확인하는 번역"];
    const reasons=qa ? ["표본 정답률 90% 이상에서 관측 정답률 우선. 동률은 비용이 낮은 두 후보를 표시합니다.","표본 정답률 90% 이상 후보 중 추정 비용이 낮은 모델입니다.","표본 정답률 90% 이상 후보 중 한 건 응답 시간이 짧은 모델입니다."] :
      ["각 비교 조건 안에서 4/5 이상이며 관측 품질이 높은 후보입니다.","번역 평가 4/5 이상 후보 중 비용이 낮은 모델입니다.","번역 평가 4/5 이상 후보 중 한 건 응답 시간이 짧은 모델입니다."];
    return shortlist(models,scenario,track).map((entry,i) => `<article class="workload-card"><span class="customer-kicker">${["QUALITY FIRST","COST FIRST","RESPONSE FIRST"][i]}</span><h3>${titles[i]}</h3><p>${reasons[i]}</p>${entry.candidates.length ? entry.candidates.map(v => `<div class="candidate" style="--family:${family(v.name).color}">${badge(v.name)}<strong>${escape(v.name)}</strong>${!qa && v.cohort!=="shared" ? `<small>비교 조건 ${v.cohort==="explicit" ? "B" : "A"}</small>` : ""}<dl><div><dt>${qa ? "정답" : "번역 평가"}</dt><dd>${qa ? `${v.model.aggregate.correct}/${v.model.aggregate.questions} · ${(v.score*100).toFixed(0)}%` : `${v.score.toFixed(2)}/5`}</dd></div><div><dt>한 건 응답</dt><dd>${time(v.latency)}</dd></div><div><dt>${volume.toLocaleString("ko-KR")}건 예상 비용</dt><dd>${money(Number.isFinite(v.cost) ? v.cost*volume : null)}</dd></div></dl><a data-model="${escape(v.name)}" href="${qa ? "#qa-examples" : "#samples-panel"}">실제 결과물 확인 ↓</a></div>`).join("") : '<p>이 조건으로 추천할 만큼의 측정 근거가 없습니다.</p>'}</article>`).join("");
  }
  return {groups,family,escape,money,time,badge,legend,measure,shortlist,pair,workload,cards};
})();
