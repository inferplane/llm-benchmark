// LLM Translation Ledger — static dashboard, no build step.
// Reads docs/results/index.json + docs/results/<run_id>.json (schema_version 2,
// written by bench/report.py) and renders three views: cost/quality scatter,
// language-pair heatmap, and run history.

// Scenario nav — extension point for future benchmark scenarios (see
// CLAUDE.md: this repo's bench pipeline is scenario-agnostic by design, e.g.
// a future document-parsing benchmark). Adding a scenario is ONE entry here
// pointing at that scenario's own page — not a shared registry/plugin system,
// same "scenario = a seam, not a registry" rule the backend already follows.
// Mirrors ../aws-ec2-benchmark/site/js/app.js's TABS array + navbar pattern,
// but as separate static pages rather than SPA tabs: this dashboard's panels
// (language-pair heatmap, translation samples) are specific enough to
// translation that a structurally different scenario needs its own page
// rather than being squeezed into this one's conditional rendering.
const SCENARIOS = [
  { id: "translation", name: "번역: KO ↔ 15언어", href: "index.html" },
];

function renderScenarioNav() {
  const el = document.getElementById("scenario-nav-links");
  if (!el) return;
  el.innerHTML = SCENARIOS.map((s) => {
    const active = location.pathname.endsWith(`/${s.href}`) || (s.href === "index.html" && /\/(index\.html)?$/.test(location.pathname));
    return `<a href="${s.href}"${active ? ' class="active"' : ""}>${escapeHtml(s.name)}</a>`;
  }).join("");
}

const LANG_ORDER = ["en", "ja", "zh", "es", "fr", "de", "pt", "ru", "it", "vi", "id", "th", "ar", "hi", "tr"];
// "OpenAI via Bedrock" stopped being accurate once xAI's grok-4.3 and Google's
// gemma-4-31b-bedrock joined the bedrock_mantle roster alongside OpenAI's
// gpt-5.x — bedrock_mantle is a Bedrock API surface (the /openai/v1/responses
// path), not an OpenAI-specific one. "Bedrock Runtime" vs "Bedrock Mantle"
// names the two Bedrock-hosted APIs themselves instead of implying a vendor.
const PROVIDER_LABEL = { bedrock: "Bedrock Runtime", openai: "OpenAI", vllm: "vLLM (self-hosted)", bedrock_mantle: "Bedrock Mantle", translate: "Amazon Translate" };
const PROVIDER_VAR = { bedrock: "--bedrock", openai: "--openai", vllm: "--vllm", bedrock_mantle: "--bedrock-mantle", translate: "--translate" };
const TRACK_LABEL = { all: "전체 (FLORES+합성, 평균)", flores: "FLORES (일반 문장)", synthetic: "합성 금융문서" };
const AXIS_LABEL = { adequacy: "정확성", terminology: "용어", numbers_entities_dates: "숫자·개체·날짜", fluency: "유창성", format: "형식" };

// Default to the synthetic (financial-domain) track, not "all" — the hero
// chart previously always blended FLORES (general sentences) into the
// headline quality number even though the footer says the two tracks are
// never averaged together. For a financial customer, synthetic is the track
// that actually matters; "all" is kept as an explicit, clearly-labeled option.
const state = {
  runs: [], reports: [], current: null, direction: "from-ko", track: "synthetic", charts: {},
  qualitySort: "pass",
  langFilter: { minMajor: 0, minOther: 0, sortBy: "gap" },
  zoomMode: {}, // per-chartKey: "zoom" (drag = box-zoom) | "pan" (drag = move)
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

const ESCAPE_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ESCAPE_MAP[c]);
}

// marked's GFM "del" (strikethrough) tokenizer matches a SINGLE `~...~` as
// strikethrough, not just the strict-GFM `~~...~~` — Korean text commonly
// uses a lone "~" as a range dash ("4.2~4.8점"), which this codebase's own
// interpretation notes and translated financial documents both do. Left
// enabled, one lone tilde opens a strikethrough span that only closes at the
// NEXT lone tilde, often sentences later — a real, visible bug (large wrong
// <s> spans), not hypothetical. Disabling del entirely is safe: nothing in
// this dashboard's content has a legitimate use for strikethrough.
marked.use({ tokenizer: { del() { return undefined; } } });

// Synthetic financial documents (and model outputs translating them) are
// authored/produced in markdown (headers, bold, tables) — rendered here via
// marked, not shown as escaped plaintext with literal "#"/"**" characters.
// marked does NOT sanitize embedded raw HTML in its input, and this text is
// untrusted (LLM-generated) — DOMPurify.sanitize() on the OUTPUT HTML is the
// actual XSS guard, not marked itself.
function renderMarkdown(text) {
  if (!text) return "";
  return DOMPurify.sanitize(marked.parse(String(text), { breaks: true }));
}

// Financial-document tables can run wide (4-5 columns) inside an otherwise
// narrow dd/td — wrap each rendered <table> in its own horizontal-scroll
// container so it never forces the whole page to scroll sideways.
function wrapMdTables(root) {
  root.querySelectorAll(".md-content table").forEach((table) => {
    if (table.parentElement.classList.contains("md-table-wrap")) return;
    const wrap = document.createElement("div");
    wrap.className = "md-table-wrap";
    table.replaceWith(wrap);
    wrap.appendChild(table);
  });
}

function fmtUsd(v) {
  // adaptive precision: cost_per_segment_usd is typically $0.0001–$0.05,
  // usd_per_mtok_out is typically $0.1–$50 — fixed 2-3 decimals would round
  // the former to "$0.000" and lose all signal.
  if (v == null) return "—";
  if (v === 0) return "$0";
  const decimals = v < 0.001 ? 5 : v < 0.01 ? 4 : v < 1 ? 3 : 2;
  return `$${v.toFixed(decimals)}`;
}

function pairChip(src, tgt) {
  return `<span class="pair-chip">${src.toUpperCase()}/${tgt.toUpperCase()}</span>`;
}

// ── in-cell comparison bars ───────────────────────────────────────────────
// A background-gradient "bar" behind a table cell's own text, so a column of
// numbers (cost, judge score, throughput) reads as a bar chart at a glance
// without a separate chart. Two scales, matched to how skewed each column is:
//  - sqrt-of-max: cost_per_segment_usd and throughput span 100-1000x across
//    models (same skew the scatter's bubble radius already sqrt-scales for) —
//    linear-to-max would flatten everything but the top model to a sliver.
//  - observed min-max: judge/quality scores cluster tightly (e.g. 3.2-4.9) —
//    scaling 0-to-max would make every bar look nearly full (same reasoning
//    as the heatmap's observed-range rescale).
function barStyle(pct) {
  const p = Math.max(0, Math.min(100, pct || 0));
  return `background:linear-gradient(90deg, var(--gold-soft) ${p}%, transparent ${p}%);`;
}
function barPctSqrtMax(value, max) {
  if (value == null || !max) return 0;
  return Math.sqrt(Math.max(0, value) / max) * 100;
}
function barPctMinMax(value, lo, hi) {
  if (value == null) return 0;
  return hi > lo ? ((value - lo) / (hi - lo)) * 100 : 50;
}

// Builds "X 이상" threshold options (in 0.1 steps, highest first) spanning
// the ACTUAL observed range of `values`, so the dropdown never offers a
// threshold that matches nothing (too high) or the whole list (too low) for
// this particular run's score band. Preserves `selected` across rebuilds
// (falls back to "전체"/0 if that value fell out of range, e.g. after a run switch).
function populateThresholdSelect(selectId, values, selected) {
  const el = document.getElementById(selectId);
  if (!el || !values.length) return;
  const hi = Math.floor(Math.max(...values) * 10) / 10;
  const lo = Math.floor(Math.min(...values) * 10) / 10;
  const opts = ['<option value="0">전체</option>'];
  for (let t = hi; t >= lo; t = Math.round((t - 0.1) * 10) / 10) {
    opts.push(`<option value="${t.toFixed(1)}">${t.toFixed(1)} 이상</option>`);
  }
  el.innerHTML = opts.join("");
  el.value = [...el.options].some((o) => Number(o.value) === selected) ? String(selected) : "0";
}

// ── data loading ─────────────────────────────────────────────────────────────

async function loadRuns() {
  // no-store: results/*.json changes every time a new run is committed, and
  // browsers/CDNs will otherwise keep serving a stale index.json indefinitely
  // since these files have no Cache-Control header (GitHub Pages default).
  const idxResp = await fetch("results/index.json", { cache: "no-store" });
  const files = idxResp.ok ? await idxResp.json() : [];
  const reports = await Promise.all(
    files.map((f) => fetch(`results/${f}`, { cache: "no-store" }).then((r) => r.json()))
  );
  reports.sort((a, b) => (a.run_id < b.run_id ? -1 : 1)); // run_id is a sortable UTC timestamp
  return reports;
}

// ── scatter: cost vs quality ─────────────────────────────────────────────────

function paretoFrontier(points) {
  // maximize quality (y), minimize cost (x). cost_per_segment_usd is rounded to
  // 5 decimals in the report, so cheap models can land on the exact same x —
  // sort ties by y descending and skip repeat x values, so a same-cost point
  // that's dominated by a higher-quality point at that same cost never
  // slips onto the frontier.
  const sorted = [...points].sort((a, b) => a.x - b.x || b.y - a.y);
  const frontier = [];
  let maxY = -Infinity;
  let lastX = null;
  for (const p of sorted) {
    if (p.x === lastX) continue;
    lastX = p.x;
    if (p.y > maxY) {
      frontier.push(p);
      maxY = p.y;
    }
  }
  return frontier;
}

// Bubble radius encodes speed (latency_e2e_p50_s, inverted — lower latency =
// faster = bigger bubble). Scaled by sqrt so *area*, not radius, is
// proportional to speed (1/latency) — area is what the eye actually compares
// in a bubble chart, a linear radius mapping would exaggerate differences.
const BUBBLE_R_MIN = 5;
const BUBBLE_R_MAX = 22;

function speedToRadius(latencies, latency) {
  if (latency == null || latency <= 0) return BUBBLE_R_MIN;
  const speeds = latencies.filter((l) => l != null && l > 0).map((l) => 1 / l);
  if (!speeds.length) return BUBBLE_R_MIN;
  const minS = Math.min(...speeds), maxS = Math.max(...speeds);
  const speed = 1 / latency;
  if (maxS === minS) return (BUBBLE_R_MIN + BUBBLE_R_MAX) / 2;
  const t = Math.sqrt((speed - minS) / (maxS - minS));
  return BUBBLE_R_MIN + t * (BUBBLE_R_MAX - BUBBLE_R_MIN);
}

// Retain the original chart's display choice: omit gpt-5.5 to keep the linear
// x-axis focused on the other API models. It remains in tables and samples.
// Do not attach a fixed price multiple to this choice: new models and runs
// change the observed cost range.
const SCATTER_EXCLUDE_MODELS = new Set(["gpt-5.5"]);

// Shown only in the zoomed-in chart: the low-cost cluster is unreadable in
// the main chart even after excluding gpt-5.5, since it still spans a wide
// cost range. This second chart re-scales to just the cheap segment
// so bubble separation within that cluster is actually visible.
const SCATTER_ZOOM_MAX_COST = 0.0003;

// track: "all" uses the combined (never-averaged-with-cost) judge_overall;
// "flores"/"synthetic" reads the quality-only by_track split instead — cost
// still comes from the whole-model aggregate either way (cost/throughput are
// never sliced by track, see bench/report.py's module docstring).
function scatterPoints(report, filterFn, track) {
  return report.models
    .filter(filterFn)
    .map((m) => {
      const q = track === "all" ? m.aggregate : m.by_track?.[track];
      return {
        x: m.aggregate.cost_per_segment_usd,
        y: q?.judge_overall,
        ci95: q?.judge_overall_ci95,
        name: m.name,
        provider: m.provider,
        usdPerMtok: m.aggregate.usd_per_mtok_out,
        latencyP50: m.aggregate.latency_e2e_p50_s,
      };
    })
    .filter((p) => p.x != null && p.y != null);
}

function mixedCohorts(report) {
  return new Set(report.models.map((m) => m.evaluation_cohort).filter(Boolean)).size > 1;
}

function cohortBadge(model) {
  if (!model.evaluation_cohort) return "";
  return `<span class="cohort-label">${model.evaluation_cohort === "explicit" ? "명시적 지시" : "기존 지시"}</span>`;
}

function selectReport(report, cohort = "all") {
  const control = document.getElementById("cohort-control");
  const select = document.getElementById("cohort-select");
  control.hidden = !report.cohorts;
  select.innerHTML = `<option value="all">전체 모델 · 평가 조건별 관측값</option>` +
    Object.entries(report.cohorts || {}).map(([key, label]) =>
      `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join("");
  select.value = cohort;
  const models = report.models.filter((m) => cohort === "all" || m.evaluation_cohort === cohort);
  const names = new Set(models.map((m) => m.name));
  state.current = { ...report, models, samples: (report.samples || []).map((s) => ({
    ...s, by_model: Object.fromEntries(Object.entries(s.by_model).filter(([name]) => names.has(name))),
  })) };
  renderAll();
}

function renderScatterChart(report, { canvasId, legendId, chartKey, filterFn, emptyMsg }) {
  const canvas = document.getElementById(canvasId);
  const canvasWrap = canvas.closest(".chart-wrap");
  const legend = document.getElementById(legendId);

  // cost_per_segment_usd (not usd_per_mtok_out) is the x-axis: normalizing by
  // output tokens rewards verbose models with a misleadingly low $/1M rate —
  // cost per translated segment reflects what a bulk-translation job actually
  // costs, since every model translates the exact same fixed set of segments.
  const rawPoints = scatterPoints(report, filterFn, state.track);

  if (state.charts[chartKey]) {
    state.charts[chartKey].destroy();
    delete state.charts[chartKey];
  }

  if (!rawPoints.length) {
    canvas.hidden = true;
    if (!canvasWrap.querySelector(".empty-state")) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = `<span class="glyph">◐</span>${emptyMsg}`;
      canvasWrap.appendChild(empty);
    }
    legend.innerHTML = "";
    return;
  }
  canvas.hidden = false;
  canvasWrap.querySelector(".empty-state")?.remove();

  const allLatencies = rawPoints.map((p) => p.latencyP50);
  const points = rawPoints.map((p) => ({ ...p, r: speedToRadius(allLatencies, p.latencyP50) }));

  const providers = [...new Set(points.map((p) => p.provider))];
  // Explicit buttons, not a modifier-key convention (shift+drag, dblclick) —
  // those turned out to not be discoverable in practice. A mode toggle
  // switches what plain drag does (zoom vs. pan) so there's never an
  // ambiguous "which gesture does what" question, and reset is always one
  // visible click away regardless of how the chart got zoomed.
  if (!(chartKey in state.zoomMode)) state.zoomMode[chartKey] = "zoom";
  legend.innerHTML =
    providers.map((p) => `<span><span class="dot" style="background:${cssVar(PROVIDER_VAR[p] || "--ink-2")}"></span>${PROVIDER_LABEL[p] || p}</span>`).join("") +
    (mixedCohorts(report) ? `<span>평가 조건이 다른 관측값 · 프론티어는 그룹 선택 시 표시</span>` :
      `<span><span class="dot" style="background:${cssVar("--gold")}"></span>가성비 프론티어</span>`) +
    `<span class="legend-note">원 크기 = 속도 (클수록 빠름)</span>` +
    `<button type="button" class="theme-toggle zoom-mode-btn" data-chart="${chartKey}"></button>` +
    `<button type="button" class="theme-toggle" data-reset="${chartKey}">↺ 초기화</button>`;

  const datasets = providers.map((p) => ({
    label: PROVIDER_LABEL[p] || p,
    type: "bubble",
    data: points.filter((pt) => pt.provider === p),
    backgroundColor: cssVar(PROVIDER_VAR[p] || "--ink-2"),
    hoverBackgroundColor: cssVar(PROVIDER_VAR[p] || "--ink-2"),
  }));

  const frontier = paretoFrontier(points);
  if (!mixedCohorts(report)) datasets.push({
    label: "가성비 프론티어",
    type: "line",
    data: frontier,
    borderColor: cssVar("--gold"),
    backgroundColor: cssVar("--gold"),
    borderWidth: 2,
    pointRadius: 3,
    pointBackgroundColor: cssVar("--gold"),
    fill: false,
    tension: 0,
    order: 0,
  });

  const grid = cssVar("--gridline");
  const ink2 = cssVar("--ink-2");

  state.charts[chartKey] = new Chart(document.getElementById(canvasId), {
    data: { datasets },
    options: {
      maintainAspectRatio: false,
      scales: {
        x: {
          type: "linear",
          min: 0,
          title: { display: true, text: "세그먼트당 비용", color: ink2 },
          grid: { color: grid },
          ticks: { color: ink2, callback: (v) => fmtUsd(v) },
        },
        y: {
          title: { display: true, text: `Judge 종합 점수 (1–5) · ${TRACK_LABEL[state.track]}`, color: ink2 },
          min: 0, max: 5,
          grid: { color: grid },
          ticks: { color: ink2 },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const p = ctx.raw;
              const lines = [`${p.name} — ${fmtUsd(p.x)}/segment · quality ${p.y.toFixed(2)}`];
              if (p.ci95) lines.push(`95% CI: ${p.ci95[0].toFixed(2)}–${p.ci95[1].toFixed(2)}`);
              if (p.usdPerMtok != null) lines.push(`(${fmtUsd(p.usdPerMtok)}/1M output tokens)`);
              if (p.latencyP50 != null) lines.push(`p50 latency: ${p.latencyP50.toFixed(2)}s`);
              return lines;
            },
          },
        },
        // chartjs-plugin-zoom (loaded in index.html). Plain drag does ONE of
        // zoom-box or pan at a time, switched by the mode-toggle button
        // below — not by a modifier key, so it always does what the visible
        // button label says.
        zoom: {
          zoom: { drag: { enabled: state.zoomMode[chartKey] === "zoom", backgroundColor: "rgba(199,154,70,0.15)", borderColor: cssVar("--gold"), borderWidth: 1 }, mode: "xy" },
          pan: { enabled: state.zoomMode[chartKey] === "pan", mode: "xy" },
        },
      },
    },
  });

  setUpZoomControls(legend, chartKey);
}

function setUpZoomControls(legend, chartKey) {
  const modeBtn = legend.querySelector(".zoom-mode-btn");
  const syncModeLabel = () => {
    modeBtn.textContent = state.zoomMode[chartKey] === "zoom" ? "🔍 확대 모드" : "✋ 이동 모드";
  };
  syncModeLabel();
  modeBtn.addEventListener("click", () => {
    state.zoomMode[chartKey] = state.zoomMode[chartKey] === "zoom" ? "pan" : "zoom";
    syncModeLabel();
    const chart = state.charts[chartKey];
    const isZoom = state.zoomMode[chartKey] === "zoom";
    chart.options.plugins.zoom.zoom.drag.enabled = isZoom;
    chart.options.plugins.zoom.pan.enabled = !isZoom;
    chart.update();
  });
  legend.querySelector("[data-reset]").addEventListener("click", () => state.charts[chartKey]?.resetZoom());
}

function renderScatter(report) {
  renderScatterChart(report, {
    canvasId: "scatter-chart",
    legendId: "hero-legend",
    chartKey: "scatter",
    filterFn: (m) => !SCATTER_EXCLUDE_MODELS.has(m.name),
    emptyMsg: "세그먼트당 비용 또는 품질 데이터가 아직 없습니다 (judge 미실행이거나 vLLM 처리량 미측정).",
  });
}

function renderScatterZoom(report) {
  const thresholdText = fmtUsd(SCATTER_ZOOM_MAX_COST);
  document.getElementById("scatter-zoom-threshold").textContent = thresholdText;
  document.getElementById("scatter-zoom-threshold-2").textContent = thresholdText;
  renderScatterChart(report, {
    canvasId: "scatter-zoom-chart",
    legendId: "hero-zoom-legend",
    chartKey: "scatterZoom",
    filterFn: (m) => !SCATTER_EXCLUDE_MODELS.has(m.name) && (m.aggregate.cost_per_segment_usd ?? Infinity) <= SCATTER_ZOOM_MAX_COST,
    emptyMsg: `세그먼트당 비용 ${fmtUsd(SCATTER_ZOOM_MAX_COST)} 이하 모델이 없습니다.`,
  });
}

// ── recommended models: the frontier itself, not an invented "best pick" ────
// The Pareto frontier already IS "no cheaper model beats this quality" — so
// this callout renders those points directly rather than layering a separate
// subjective ranking on top of a chart that already answers the question.

function renderRecommendations(report) {
  const body = document.getElementById("recommendations-body");
  if (mixedCohorts(report)) {
    body.textContent = "전체 모델의 품질과 비용은 아래 표에서 확인하세요. 가성비 추천은 상단의 평가 조건에서 그룹을 선택하면 표시됩니다. 번역 지시가 다른 그룹 사이에는 통합 순위를 산출하지 않습니다.";
    return;
  }
  const points = scatterPoints(report, (m) => !SCATTER_EXCLUDE_MODELS.has(m.name), state.track);
  const frontier = paretoFrontier(points);

  if (!frontier.length) {
    body.innerHTML = `<div class="empty-state"><span class="glyph">◐</span>추천할 모델이 없습니다.</div>`;
    return;
  }

  const costMax = Math.max(...frontier.map((p) => p.x || 0));
  const scoreVals = frontier.map((p) => p.y).filter((v) => v != null);
  const scoreLo = Math.min(...scoreVals), scoreHi = Math.max(...scoreVals);

  const rowsHtml = frontier
    .slice()
    .reverse() // cheapest last → show best-quality-first
    .map((p, i) => {
      const dot = `<span class="dot" style="background:${cssVar(PROVIDER_VAR[p.provider] || "--ink-2")}"></span>`;
      const tag = i === 0 ? `<span class="reco-tag">최고 품질</span>` : i === frontier.length - 1 ? `<span class="reco-tag">최저 비용</span>` : "";
      const ci = p.ci95 ? ` <span class="ci-note">(95% CI ${p.ci95[0].toFixed(2)}–${p.ci95[1].toFixed(2)})</span>` : "";
      return `<tr>
        <td class="model-cell">${dot}${escapeHtml(p.name)} ${tag}</td>
        <td class="score-cell" style="text-align:left;${barStyle(barPctMinMax(p.y, scoreLo, scoreHi))}">${p.y.toFixed(2)}${ci}</td>
        <td class="score-cell" style="text-align:left;${barStyle(barPctSqrtMax(p.x, costMax))}">${fmtUsd(p.x)}</td>
      </tr>`;
    })
    .join("");

  body.innerHTML = `
    <div class="table-scroll" tabindex="0" role="region" aria-label="추천 모델 비교 표">
    <table class="sample-compare">
      <thead><tr><th>모델</th><th>Judge 종합 (${TRACK_LABEL[state.track]})</th><th>세그먼트당 비용</th></tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>
    </div>
    <p class="panel-note" style="margin-top:12px;">가성비 프론티어에 오른 ${frontier.length}개 모델 — 표의 각 모델보다 낮은 비용에서 더 높은 품질을 내는 모델은 이 런에 없습니다. 신뢰구간이 겹치는 모델 간 순위는 근소한 차이로 단정하지 마세요.</p>`;
}

// ── model detail table: every field report.py computes, one row per model ───
// The scatter/heatmap only ever surface a couple of numbers per model — this
// table is where cost, throughput, latency, per-track quality, judge sub-axes,
// and run_config (vLLM GPU/TP/concurrency, or API pricing) all actually live.

function runConfigLines(rc) {
  if (!rc) return "—";
  const lines = [];
  if (rc.mantle_region) lines.push(`Mantle 리전: ${rc.mantle_region}`);
  if (rc.temperature_omitted) lines.push("temperature: 미전송 (모델 예외)");
  if (rc.gpu_instance_type) {
    lines.push(`GPU: ${rc.gpu_instance_type} (TP=${rc.tensor_parallel_size ?? "?"}, 동시성=${rc.concurrency})`);
    if (rc.quantization) lines.push(`양자화: ${rc.quantization}`);
    if (rc.extra_vllm_args?.length) lines.push(`vLLM 옵션: ${rc.extra_vllm_args.join(" ")}`);
    lines.push(`GPU 시간당 비용: ${fmtUsd(rc.gpu_hourly_usd)}`);
  } else if (rc.price_per_char_usd != null) {
    // Amazon Translate: no tokens, no concurrency knob worth surfacing here —
    // just the per-character rate that actually drives its cost.
    lines.push(`단가: $${rc.price_per_char_usd.toFixed(6)}/문자 (입력 기준)`);
  } else {
    lines.push(`동시성: ${rc.concurrency}`);
    if (rc.price_in_usd_per_mtok != null) lines.push(`단가: ${fmtUsd(rc.price_in_usd_per_mtok)}/1M in · ${fmtUsd(rc.price_out_usd_per_mtok)}/1M out`);
    if (rc.mantle_reasoning_effort) lines.push(`reasoning effort: ${rc.mantle_reasoning_effort}`);
    if (rc.bedrock_reasoning_effort) lines.push(`reasoning effort: ${rc.bedrock_reasoning_effort}`);
  }
  return lines.map((l) => escapeHtml(l)).join("<br>");
}

function renderModelTable(report) {
  const body = document.getElementById("model-table-body");
  const scoreHead = document.getElementById("model-table-score-head");
  if (scoreHead) scoreHead.textContent = `Judge 종합 (${TRACK_LABEL[state.track]})`;
  // Sorted by Judge 종합 (track-aware, same score shown in the column) descending
  // — best quality first, not cost — matches how a reader actually scans this
  // table: "which models are good" before "which are cheap" (cost has its own
  // dedicated ordering in the 가성비 scatter/추천 모델 panels above).
  const trackScore = (m) => (state.track === "all" ? m.aggregate : m.by_track?.[state.track])?.judge_overall;
  const models = [...report.models]
    .filter((m) => m.aggregate.cost_per_segment_usd != null)
    .sort((a, b) => (trackScore(b) ?? -Infinity) - (trackScore(a) ?? -Infinity));

  if (!models.length) {
    body.innerHTML = `<tr><td colspan="6"><div class="empty-state"><span class="glyph">◐</span>모델 데이터가 없습니다.</div></td></tr>`;
    return;
  }

  const costMax = Math.max(...models.map((m) => m.aggregate.cost_per_segment_usd || 0));
  const throughputMax = Math.max(...models.map((m) => m.aggregate.throughput_tok_s || 0));
  const scoreVals = models.map((m) => (state.track === "all" ? m.aggregate : m.by_track?.[state.track])?.judge_overall).filter((v) => v != null);
  const scoreLo = scoreVals.length ? Math.min(...scoreVals) : 0;
  const scoreHi = scoreVals.length ? Math.max(...scoreVals) : 5;

  const rowsHtml = models
    .map((m, i) => {
      const a = m.aggregate;
      // headline score follows the same track selector as the scatter charts
      // (state.track, default "synthetic") — previously this always showed
      // aggregate.judge_overall (FLORES+synthetic combined, ~94% FLORES by
      // volume), which silently disagreed with the financial-domain-only
      // number shown above in the hero chart.
      const q = state.track === "all" ? a : m.by_track?.[state.track];
      const dot = `<span class="dot" style="background:${cssVar(PROVIDER_VAR[m.provider] || "--ink-2")}"></span>`;
      const ci = q?.judge_overall_ci95 ? ` <span class="ci-note">(${q.judge_overall_ci95[0].toFixed(2)}–${q.judge_overall_ci95[1].toFixed(2)})</span>` : "";
      const failNote = a.translation_failures || a.judge_failures ? `<span class="ci-note">${a.translation_failures}건 번역실패 · ${a.judge_failures}건 채점실패</span>` : "정상";

      const axesHtml = Object.entries(q?.judge || {})
        .map(([k, v]) => `<span class="axis-chip">${AXIS_LABEL[k] || k}: ${v.toFixed(2)}</span>`)
        .join(" ");
      const trackHtml = ["flores", "synthetic"]
        .filter((t) => m.by_track?.[t])
        .map((t) => `${TRACK_LABEL[t]}: ${m.by_track[t].judge_overall?.toFixed(2) ?? "—"}`)
        .join(" · ");

      return `
        <tr class="model-row" data-detail="detail-${i}">
          <td class="model-cell">${dot}${escapeHtml(m.name)} ${cohortBadge(m)}</td>
          <td class="score-cell" style="${barStyle(barPctSqrtMax(a.cost_per_segment_usd, costMax))}">${fmtUsd(a.cost_per_segment_usd)}</td>
          <td class="score-cell" style="${barStyle(barPctMinMax(q?.judge_overall, scoreLo, scoreHi))}">${q?.judge_overall != null ? q.judge_overall.toFixed(2) : "—"}${ci}</td>
          <td class="score-cell">${a.latency_e2e_p50_s?.toFixed(2) ?? "—"}s / ${a.latency_e2e_p95_s?.toFixed(2) ?? "—"}s</td>
          <td class="score-cell" style="${barStyle(barPctSqrtMax(a.throughput_tok_s, throughputMax))}">${a.throughput_tok_s?.toFixed(1) ?? "—"} tok/s</td>
          <td class="score-cell">${failNote}</td>
        </tr>
        <tr class="detail-row" id="detail-${i}" hidden>
          <td colspan="6">
            <div class="detail-grid">
              <div><strong>트랙별 품질</strong><br>${trackHtml || "—"}</div>
              <div><strong>Judge 세부 축</strong><br>${axesHtml || "—"}</div>
              <div><strong>실행 설정 (run_config)</strong><br>${runConfigLines(m.run_config)}</div>
            </div>
          </td>
        </tr>`;
    })
    .join("");

  body.innerHTML = rowsHtml;
  body.querySelectorAll(".model-row").forEach((row) => {
    row.addEventListener("click", () => {
      const detail = document.getElementById(row.dataset.detail);
      detail.hidden = !detail.hidden;
    });
  });
}

// ── quality diagnostics: complete raw judging, selected track only ─────────

function fmtQualityPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function fmtQualityCount(value) {
  return Number.isFinite(value) ? value.toLocaleString("ko-KR") : "—";
}

function fmtQualityDelta(value) {
  return Number.isFinite(value) ? `${value > 0 ? "+" : ""}${value.toFixed(3)}` : "—";
}

function qualityRateCell(quality, rateField, countField) {
  return `<td class="score-cell">${fmtQualityPercent(quality?.[rateField])}
    <small class="quality-sub">${fmtQualityCount(quality?.[countField])} / ${fmtQualityCount(quality?.quality_eligible_segments)}건</small></td>`;
}

function renderQualityDiagnostics(report) {
  const body = document.getElementById("quality-table-body");
  const baselineBody = document.getElementById("quality-baseline-body");
  document.getElementById("quality-track-note").textContent =
    `품질 트랙: ${TRACK_LABEL[state.track]} · 위 트랙 선택과 연동 · — 제공 안 됨`;

  // Read the fixed report contract. Never derive eligibility from the older
  // judged_segments count: merged scores can lack one judge's raw axes.
  const rows = report.models.map((model) => {
    const quality = state.track === "all" ? model.aggregate : model.by_track?.[state.track];
    const comparison = quality?.baseline_comparison;
    return {
      model, quality,
      baseline: comparison?.baseline_model === "amazon-translate" ? comparison : null,
    };
  });
  const sortValue = (row) => {
    if (state.qualitySort === "risk") return row.quality?.high_risk_rate;
    if (state.qualitySort === "p10") return row.quality?.judge_overall_p10;
    if (state.qualitySort === "baseline") return row.baseline?.mean_delta;
    return row.quality?.quality_pass_rate;
  };
  rows.sort((a, b) => {
    const av = sortValue(a), bv = sortValue(b);
    if (Number.isFinite(av) !== Number.isFinite(bv)) return Number.isFinite(av) ? -1 : 1;
    const delta = Number.isFinite(av) ? (state.qualitySort === "risk" ? av - bv : bv - av) : 0;
    return delta || a.model.name.localeCompare(b.model.name);
  });

  if (!rows.length) {
    const empty = `<div class="empty-state">모델 데이터가 없습니다.</div>`;
    body.innerHTML = `<tr><td colspan="7">${empty}</td></tr>`;
    baselineBody.innerHTML = `<tr><td colspan="5">${empty}</td></tr>`;
    return;
  }

  const modelCell = (model) => `<td class="model-cell"><span class="dot" style="background:${cssVar(PROVIDER_VAR[model.provider] || "--ink-2")}"></span>${escapeHtml(model.name)} ${cohortBadge(model)}</td>`;
  body.innerHTML = rows.map(({ model, quality: q }) => {
    // Cost comes ONLY from the whole-model field, even while synthetic or
    // FLORES is selected. Missing cost is unavailable, never recomputed using
    // a track's pass count or assumed to be free.
    const cost = model.aggregate?.cost_per_quality_pass_usd;
    return `<tr>
      ${modelCell(model)}
      ${qualityRateCell(q, "quality_pass_rate", "quality_pass_segments")}
      ${qualityRateCell(q, "high_risk_rate", "high_risk_segments")}
      <td class="score-cell">${Number.isFinite(q?.judge_overall_p10) ? q.judge_overall_p10.toFixed(2) : "—"}</td>
      ${qualityRateCell(q, "judge_disagreement_rate", "judge_disagreement_segments")}
      <td class="score-cell">${fmtQualityCount(q?.quality_eligible_segments)} / ${fmtQualityCount(q?.segments)}
        <small class="quality-sub">원점수 ${fmtQualityPercent(q?.quality_coverage_rate)} · 채점 ${fmtQualityPercent(q?.judge_coverage_rate)}</small>
        <small class="quality-sub">번역 성공 ${fmtQualityCount(q?.successful_translations)}건 기준</small></td>
      <td class="score-cell">${Number.isFinite(cost) ? fmtUsd(cost) : "—"}</td>
    </tr>`;
  }).join("");

  baselineBody.innerHTML = rows.map(({ model, baseline: b }) => {
    const ci = b?.mean_delta_ci95;
    const ciText = Array.isArray(ci) && ci.length === 2 && ci.every(Number.isFinite)
      ? `${fmtQualityDelta(ci[0])} ~ ${fmtQualityDelta(ci[1])}` : "—";
    return `<tr>
      ${modelCell(model)}
      <td class="score-cell">${fmtQualityCount(b?.paired_segments)}</td>
      <td class="score-cell">${fmtQualityPercent(b?.win_rate)} / ${fmtQualityPercent(b?.tie_rate)} / ${fmtQualityPercent(b?.loss_rate)}</td>
      <td class="score-cell">${fmtQualityDelta(b?.mean_delta)}</td>
      <td class="score-cell">${ciText}</td>
    </tr>`;
  }).join("");
}

// ── language coverage: major (high-resource) vs other (lower-resource) ──────
// LANG_GROUP membership lives in bench/report.py (by_lang_group is computed
// there) — this panel only reads the two pre-aggregated numbers per model,
// it doesn't re-derive the grouping client-side.

function renderLanguageCoverage(report) {
  const body = document.getElementById("lang-coverage-body");
  const note = document.getElementById("lang-coverage-summary");

  const rows = report.models
    .map((m) => {
      const maj = m.by_lang_group?.major?.judge_overall;
      const oth = m.by_lang_group?.other?.judge_overall;
      if (maj == null || oth == null) return null;
      return { name: m.name, provider: m.provider, maj, oth, gap: maj - oth, cost: m.aggregate.cost_per_segment_usd };
    })
    .filter(Boolean);

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="5"><div class="empty-state"><span class="glyph">◐</span>언어 그룹 데이터가 없습니다.</div></td></tr>`;
    note.textContent = "";
    return;
  }

  const avgMaj = rows.reduce((s, r) => s + r.maj, 0) / rows.length;
  const avgOth = rows.reduce((s, r) => s + r.oth, 0) / rows.length;
  note.textContent =
    `전 모델 평균: 주요 언어(EN/JA/ZH/ES/FR/DE/PT/RU/IT) ${avgMaj.toFixed(2)} vs 기타 언어(VI/ID/TH/AR/HI/TR) ${avgOth.toFixed(2)} — 평균 격차 ${(avgMaj - avgOth).toFixed(2)}점. 모델별 격차는 아래 표에서 크게 갈립니다.`;

  const GAP_WARN = 0.2; // gap beyond this is a real, model-specific weakness, not run-to-run noise (typical CI half-width here is ~0.02-0.03)

  // Threshold selects ("4.7 이상") are populated from THIS run's actual score
  // range, not a hardcoded list — a run with a narrower or shifted score band
  // (different judge, different models) would otherwise offer options that
  // match nothing or miss the range entirely.
  populateThresholdSelect("lang-filter-major", rows.map((r) => r.maj), state.langFilter.minMajor);
  populateThresholdSelect("lang-filter-other", rows.map((r) => r.oth), state.langFilter.minOther);

  // Shared min-max scale across BOTH columns, from the FULL (unfiltered) row
  // set — with a shared scale, a model's two bar lengths visually encode the
  // major/other gap itself, and the scale doesn't jump around as the filter
  // selection changes.
  const allScores = rows.flatMap((r) => [r.maj, r.oth]);
  const scoreLo = Math.min(...allScores), scoreHi = Math.max(...allScores);
  const costMax = Math.max(...rows.map((r) => r.cost || 0));

  const filtered = rows.filter((r) => r.maj >= state.langFilter.minMajor && r.oth >= state.langFilter.minOther);
  const compareCost = (a, b, descending = false) => {
    const aKnown = Number.isFinite(a.cost), bKnown = Number.isFinite(b.cost);
    if (aKnown !== bKnown) return aKnown ? -1 : 1;
    return aKnown ? (descending ? b.cost - a.cost : a.cost - b.cost) : 0;
  };
  const SORTERS = {
    gap: (a, b) => a.gap - b.gap,
    gap_desc: (a, b) => b.gap - a.gap,
    major_desc: (a, b) => b.maj - a.maj,
    other_desc: (a, b) => b.oth - a.oth,
    cost_asc: (a, b) => compareCost(a, b),
    cost_desc: (a, b) => compareCost(a, b, true),
  };
  const displayRows = [...filtered].sort(SORTERS[state.langFilter.sortBy] || SORTERS.gap);

  if (!displayRows.length) {
    body.innerHTML = `<tr><td colspan="5"><div class="empty-state"><span class="glyph">◐</span>이 조건에 맞는 모델이 없습니다 — 필터를 완화해 보세요.</div></td></tr>`;
  } else {
    body.innerHTML = displayRows
      .map((r) => {
        const dot = `<span class="dot" style="background:${cssVar(PROVIDER_VAR[r.provider] || "--ink-2")}"></span>`;
        const tag = r.gap >= GAP_WARN ? `<span class="reco-tag warn">저자원 언어 격차 큼</span>` : r.gap <= 0.05 ? `<span class="reco-tag">다국어 안정적</span>` : "";
        return `<tr>
          <td class="model-cell">${dot}${escapeHtml(r.name)} ${tag}</td>
          <td class="score-cell" style="${barStyle(barPctMinMax(r.maj, scoreLo, scoreHi))}">${r.maj.toFixed(2)}</td>
          <td class="score-cell" style="${barStyle(barPctMinMax(r.oth, scoreLo, scoreHi))}">${r.oth.toFixed(2)}</td>
          <td class="score-cell ${r.gap >= GAP_WARN ? "gap-warn" : ""}">${r.gap >= 0 ? "+" : ""}${r.gap.toFixed(2)}</td>
          <td class="score-cell" style="${barStyle(barPctSqrtMax(r.cost, costMax))}">${fmtUsd(r.cost)}</td>
        </tr>`;
      })
      .join("");
  }

  // The written recommendation always reads from the FULL row set, not the
  // filtered view — it's a finding about the run, not about whatever subset
  // the user currently has filtered into view.
  const sorted = [...rows].sort((a, b) => a.gap - b.gap);
  const stable = sorted.filter((r) => r.gap <= 0.05).sort((a, b) => compareCost(a, b));
  const worst = sorted.filter((r) => r.gap >= GAP_WARN).sort((a, b) => b.gap - a.gap);
  const recoEl = document.getElementById("lang-coverage-reco");
  if (mixedCohorts(report)) {
    recoEl.textContent = "언어별 관측 결과입니다. 모델 선택을 위한 추천은 평가 조건별 그룹에서 확인하세요.";
    return;
  }
  const bits = [];
  if (stable.length) {
    const cheapest = stable.find((r) => Number.isFinite(r.cost));
    const costNote = cheapest
      ? ` (비용이 확인된 모델 중 가장 저렴한 건 ${escapeHtml(cheapest.name)}, ${fmtUsd(cheapest.cost)}/segment)`
      : " (비용 정보는 제공되지 않습니다)";
    bits.push(`다국어 커버리지가 필요하면 <strong>${stable.slice(0, 3).map((r) => escapeHtml(r.name)).join(", ")}</strong> 등 격차 0.05점 이하 모델을 우선 검토하세요${costNote}.`);
  }
  if (worst.length) {
    bits.push(`반대로 <strong>${worst.slice(0, 3).map((r) => `${escapeHtml(r.name)}(+${r.gap.toFixed(2)})`).join(", ")}</strong>은 전체/주요 언어 점수는 무난해 보여도 기타 언어에서 크게 떨어지므로, 해당 언어권 문서를 다룬다면 전체 평균만 보고 고르지 마세요.`);
  }
  recoEl.innerHTML = bits.map((b) => `<p>${b}</p>`).join("");
}

// ── heatmap: model × language pair ──────────────────────────────────────────

function sequentialBg(value, lo, hi) {
  if (value == null) return "transparent";
  // Rescale to the OBSERVED score range for this heatmap render, not the full
  // 1-5 domain — real judge scores cluster tightly (e.g. 4.3-4.9), so a fixed
  // 1-5 scale put every cell at nearly the same alpha and the heatmap read as
  // flat. A degenerate range (lo===hi) falls back to a mid alpha.
  const t = hi > lo ? Math.max(0, Math.min(1, (value - lo) / (hi - lo))) : 0.5;
  const [r, g, b] = hexToRgb(cssVar("--gold").trim() || "#C79A46");
  return `rgba(${r},${g},${b},${(0.08 + t * 0.55).toFixed(2)})`;
}

function renderHeatmap(report) {
  const table = document.getElementById("heatmap-table");
  const isFromKo = state.direction === "from-ko";

  const pairsByModel = report.models.map((m) => ({
    name: m.name,
    provider: m.provider,
    pairs: Object.entries(m.by_pair).filter(([key]) => {
      const [src, tgt] = key.split("-");
      return isFromKo ? src === "ko" : tgt === "ko";
    }),
  }));

  const columns = isFromKo
    ? LANG_ORDER.filter((l) => pairsByModel.some((m) => m.pairs.some(([k]) => k === `ko-${l}`)))
    : LANG_ORDER.filter((l) => pairsByModel.some((m) => m.pairs.some(([k]) => k === `${l}-ko`)));

  const rows = pairsByModel.filter((m) => m.pairs.length > 0);

  const legend = document.getElementById("heatmap-legend");
  if (legend) {
    const providersHere = [...new Set(rows.map((r) => r.provider))];
    legend.innerHTML = providersHere
      .map((p) => `<span><span class="dot" style="background:${cssVar(PROVIDER_VAR[p] || "--ink-2")}"></span>${PROVIDER_LABEL[p] || p}</span>`)
      .join("");
  }

  if (!rows.length || !columns.length) {
    table.parentElement.innerHTML = `<div class="empty-state"><span class="glyph">◐</span>이 방향(${isFromKo ? "KO → X" : "X → KO"})에 대한 결과가 아직 없습니다.</div>`;
    return;
  }
  if (!table.isConnected) return; // parent was replaced by an earlier empty state; caller re-fetches DOM

  let head = `<thead><tr><th class="rowhead">모델</th>`;
  for (const l of columns) head += `<th>${isFromKo ? pairChip("ko", l) : pairChip(l, "ko")}</th>`;
  head += `</tr></thead>`;

  const allValues = rows.flatMap((r) => r.pairs.map(([, v]) => v.judge_overall).filter((v) => v != null));
  const lo = allValues.length ? Math.min(...allValues) : 1;
  const hi = allValues.length ? Math.max(...allValues) : 5;
  const scaleNote = document.getElementById("heatmap-scale-note");
  if (scaleNote) scaleNote.textContent = `색상 범위: ${lo.toFixed(2)} (연함) – ${hi.toFixed(2)} (진함)`;

  let body = `<tbody>`;
  for (const row of rows) {
    const providerColor = cssVar(PROVIDER_VAR[row.provider] || "--ink-2");
    body += `<tr><td class="rowhead" style="border-left-color:${providerColor}"><span class="dot" style="background:${providerColor}" title="${PROVIDER_LABEL[row.provider] || row.provider}"></span>${escapeHtml(row.name)}</td>`;
    for (const l of columns) {
      const key = isFromKo ? `ko-${l}` : `${l}-ko`;
      const entry = row.pairs.find(([k]) => k === key);
      const v = entry ? entry[1].judge_overall : null;
      body += v != null
        ? `<td class="cell" style="background:${sequentialBg(v, lo, hi)}">${v.toFixed(2)}</td>`
        : `<td class="cell empty">—</td>`;
    }
    body += `</tr>`;
  }
  body += `</tbody>`;
  table.innerHTML = head + body;
}

// ── history: judge score per model across runs ──────────────────────────────

function renderHistory(reports) {
  const body = document.getElementById("history-body");
  if (reports.length < 2) {
    body.innerHTML = `<div class="empty-state"><span class="glyph">◐</span>비교할 런이 2개 이상 쌓이면 히스토리 차트가 표시됩니다 (현재 ${reports.length}개).</div>`;
    return;
  }
  if (!body.querySelector("canvas")) {
    body.innerHTML = `<div class="chart-wrap short"><canvas id="history-chart"></canvas></div>`;
  }

  const runIds = reports.map((r) => r.run_id);
  const modelNames = [...new Set(reports.flatMap((r) => r.models.map((m) => m.name)))];
  const providerOf = {};
  for (const r of reports) for (const m of r.models) providerOf[m.name] = m.provider;

  const datasets = modelNames.map((name) => ({
    label: name,
    data: reports.map((r) => {
      const m = r.models.find((mm) => mm.name === name);
      return m ? m.aggregate.judge_overall : null;
    }),
    borderColor: cssVar(PROVIDER_VAR[providerOf[name]] || "--ink-2"),
    backgroundColor: cssVar(PROVIDER_VAR[providerOf[name]] || "--ink-2"),
    spanGaps: true,
    tension: 0.15,
    pointRadius: 3,
  }));

  if (state.charts.history) state.charts.history.destroy();
  const grid = cssVar("--gridline");
  const ink2 = cssVar("--ink-2");
  state.charts.history = new Chart(document.getElementById("history-chart"), {
    type: "line",
    data: { labels: runIds, datasets },
    options: {
      maintainAspectRatio: false,
      scales: {
        x: { grid: { color: grid }, ticks: { color: ink2 } },
        y: { min: 1, max: 5, grid: { color: grid }, ticks: { color: ink2 } },
      },
      plugins: { legend: { labels: { color: ink2 } } },
    },
  });
}

// ── sample inspector: per-segment, per-model translation comparison ─────────

// Landing sample for the inspector — a short, single-sentence FLORES
// segment (en→ko) rather than whichever id happens to sort first
// alphabetically, so the panel opens on something quick to read at a glance.
const DEFAULT_SAMPLE_ID = "flores-101-en-ko";

function renderSamples(report) {
  const select = document.getElementById("sample-select");
  const note = document.getElementById("samples-per-pair-note");
  const samples = report.samples || [];

  if (!samples.length) {
    note.textContent = "0";
    select.innerHTML = "";
    document.getElementById("sample-detail").innerHTML =
      `<div class="empty-state"><span class="glyph">◐</span>이 런에는 샘플 데이터가 없습니다.</div>`;
    return;
  }

  const perPair = samples.filter((s) => s.pair === samples[0].pair).length;
  note.textContent = String(perPair);

  const byPair = new Map();
  for (const s of samples) {
    if (!byPair.has(s.pair)) byPair.set(s.pair, []);
    byPair.get(s.pair).push(s);
  }

  const previousId = select.value;
  select.innerHTML = [...byPair.entries()]
    .map(([pair, group]) => {
      const options = group
        .map((s) => `<option value="${s.id}">${escapeHtml(truncate(s.src_text, 40))}</option>`)
        .join("");
      return `<optgroup label="${escapeHtml(pair)}">${options}</optgroup>`;
    })
    .join("");

  const defaultId = samples.some((s) => s.id === DEFAULT_SAMPLE_ID) ? DEFAULT_SAMPLE_ID : samples[0].id;
  const selectedId = samples.some((s) => s.id === previousId) ? previousId : defaultId;
  select.value = selectedId;
  renderSampleDetail(report, selectedId);
}

function truncate(text, n) {
  if (!text) return "";
  return text.length > n ? text.slice(0, n) + "…" : text;
}

function renderSampleDetail(report, sampleId) {
  const detail = document.getElementById("sample-detail");
  const sample = (report.samples || []).find((s) => s.id === sampleId);
  if (!sample) {
    detail.innerHTML = "";
    return;
  }

  const providerByModel = Object.fromEntries(report.models.map((m) => [m.name, m.provider]));
  const rows = Object.entries(sample.by_model)
    .map(([model, r]) => ({ model, provider: providerByModel[model], ...r }))
    .sort((a, b) => (b.overall ?? -1) - (a.overall ?? -1));

  const rowsHtml = rows
    .map((r) => {
      const dot = `<span class="dot" style="background:${cssVar(PROVIDER_VAR[r.provider] || "--ink-2")}"></span>`;
      if (r.translation_error != null) {
        return `<tr><td class="model-cell">${dot}${escapeHtml(r.model)}</td><td class="error-cell" colspan="2">번역 실패: ${escapeHtml(r.translation_error || "오류 설명이 기록되지 않았습니다.")}</td></tr>`;
      }
      const score = r.judge_error != null ? "judge 실패" : (r.overall != null ? r.overall.toFixed(2) : "채점 대기");
      const outHtml = r.output_text ? `<div class="md-content">${renderMarkdown(r.output_text)}</div>` : "—";
      return `<tr><td class="model-cell">${dot}${escapeHtml(r.model)}</td><td class="score-cell">${score}</td><td>${outHtml}</td></tr>`;
    })
    .join("");

  detail.innerHTML = `
    <p class="sample-origin">${sample.doc_type === "flores"
      ? "FLORES 일반 문장 · 참조 번역은 사람이 작성했습니다."
      : "합성 예시 · 원문과 참조 번역을 모델이 생성했습니다."}</p>
    <dl class="sample-source">
      <dt>원문 (${escapeHtml(sample.pair.split("-")[0].toUpperCase())})</dt>
      <dd><div class="md-content">${renderMarkdown(sample.src_text)}</div></dd>
      ${sample.ref_text ? `<dt>참조 번역</dt><dd><div class="md-content">${renderMarkdown(sample.ref_text)}</div></dd>` : ""}
    </dl>
    <div class="table-scroll" tabindex="0" role="region" aria-label="모델별 번역 샘플 비교 표">
    <table class="sample-compare">
      <thead><tr><th>모델</th><th>Judge 종합</th><th>번역 결과</th></tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>
    </div>`;
  wrapMdTables(detail);
}

// ── chrome: run selector, summary, direction/theme toggles ──────────────────

function renderRunProvenance(report) {
  const note = document.getElementById("run-provenance");
  if (report.comparison_note) {
    note.hidden = false;
    note.textContent = report.comparison_note;
    return;
  }
  const sources = report.source_runs || [];
  note.hidden = sources.length < 2;
  note.textContent = "";
  if (note.hidden) return;

  const label = (name) => name === "grok-4.6" ? "Grok 4.6" : name === "grok-4.3" ? "Grok 4.3" : name;
  const parts = [
    "모델별 평가 시점과 생성 조건이 다릅니다. 품질·비용·지연을 비교할 때 이 차이를 함께 고려하세요.",
  ];

  // Use recorded settings, so this caveat follows the selected report rather
  // than attributing today's Grok decoding configuration to historical runs.
  const recorded = sources.flatMap((source) => source.manifest?.models || []);
  const decoding = ["grok-4.6", "grok-4.3"].flatMap((name) => {
    const model = report.models.find((m) => m.name === name);
    if (!model) return [];
    const config = recorded.find((m) => m.name === name);
    const effort = model.run_config?.mantle_reasoning_effort ?? config?.mantle_reasoning_effort;
    const region = model.run_config?.mantle_region ?? config?.mantle_region;
    if (effort == null) return [];
    return [`${label(name)}: Mantle${region ? ` ${region}` : ""}, reasoning=${effort}`];
  });
  if (decoding.length) parts.push(`생성 조건: ${decoding.join(" / ")}. 모델별 reasoning 차이는 품질·지연 비교 시 함께 확인하세요.`);
  note.textContent = parts.join(" ");
}

function renderSummary(report) {
  renderRunProvenance(report);
  document.getElementById("run-summary").textContent =
    `${report.report_kind === "integrated" ? "통합 벤치마크 결과" : report.run_id} · 현재 ${report.models.length}개 모델 · ${report.dataset.pairs}개 언어쌍 방향`;
  document.getElementById("meta-dataset").textContent =
    `FLORES-200 ${report.dataset.flores_per_pair}쌍/방향 + 합성 금융문서 ${report.dataset.synthetic_per_pair}건/방향`;
  document.getElementById("meta-sample-size").textContent =
    `현재 언어 방향당 FLORES ${report.dataset.flores_per_pair} + 합성 ${report.dataset.synthetic_per_pair} — 판단이 근소한 차이(신뢰구간이 겹치는 경우)는 순위로 단정하지 않는 것을 권장합니다. judge_overall_ci95는 부트스트랩 95% 신뢰구간입니다.`;
}

function renderInterpretation(report) {
  const panel = document.getElementById("interpretation-panel");
  if (!report.interpretation) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const body = document.getElementById("interpretation-body");
  body.innerHTML = `<div class="md-content">${renderMarkdown(report.interpretation)}</div>`;
  wrapMdTables(body);
}

function renderAll() {
  const report = state.current;
  if (!report) return;
  renderSummary(report);
  renderInterpretation(report);
  renderScatter(report);
  renderScatterZoom(report);
  renderRecommendations(report);
  renderModelTable(report);
  renderQualityDiagnostics(report);
  renderLanguageCoverage(report);
  renderHeatmapSafe(report);
  renderSamples(report);
  renderHistory(state.reports.filter((r) => r.report_kind !== "integrated"));
}

function renderHeatmapSafe(report) {
  // heatmap panel body may have been replaced by an empty-state div on a prior
  // render (e.g. direction toggle with no data) — restore the table container first.
  const panel = document.getElementById("heatmap-panel");
  let scroll = panel.querySelector(".heatmap-scroll");
  scroll.innerHTML = `<table class="heatmap" id="heatmap-table"></table>`;
  renderHeatmap(report);
}

async function init() {
  renderScenarioNav();
  state.reports = await loadRuns();
  if (!state.reports.length) {
    document.getElementById("run-summary").textContent = "벤치마크 런이 아직 없습니다.";
    document.getElementById("interpretation-panel").hidden = true;
    const emptyRunHtml = `<div class="empty-state"><span class="glyph">◐</span>아직 게시된 런이 없습니다. bench/run.py → bench/judge.py → bench/report.py 를 실행해 첫 결과를 만들어 보세요.</div>`;
    document.querySelectorAll(`#hero-panel .chart-wrap, #heatmap-panel .heatmap-scroll`).forEach((el) => { el.innerHTML = emptyRunHtml; });
    document.getElementById("recommendations-body").innerHTML = emptyRunHtml;
    document.getElementById("model-table-body").innerHTML = `<tr><td colspan="6">${emptyRunHtml}</td></tr>`;
    renderQualityDiagnostics({ models: [] });
    document.getElementById("lang-coverage-body").innerHTML = `<tr><td colspan="5">${emptyRunHtml}</td></tr>`;
    document.getElementById("lang-coverage-summary").textContent = "";
    document.getElementById("lang-coverage-reco").innerHTML = "";
    renderHistory([]);
    return;
  }

  const select = document.getElementById("run-select");
  select.innerHTML = state.reports.map((r, i) => `<option value="${i}">${escapeHtml(r.title || r.run_id)}</option>`).join("");
  const integratedIndex = state.reports.findLastIndex((r) => r.report_kind === "integrated");
  select.selectedIndex = integratedIndex >= 0 ? integratedIndex : state.reports.length - 1;
  state.current = state.reports[select.selectedIndex];

  select.addEventListener("change", () => {
    selectReport(state.reports[Number(select.value)]);
  });
  document.getElementById("cohort-select").addEventListener("change", (event) => {
    selectReport(state.reports[Number(select.value)], event.target.value);
  });

  document.querySelectorAll("#direction-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#direction-toggle button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.direction = btn.dataset.dir;
      renderHeatmapSafe(state.current);
    });
  });

  document.querySelectorAll("#track-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#track-toggle button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.track = btn.dataset.track;
      renderScatter(state.current);
      renderScatterZoom(state.current);
      renderRecommendations(state.current);
      renderModelTable(state.current); // score column AND sort order are both track-aware
      renderQualityDiagnostics(state.current);
    });
  });

  document.getElementById("quality-sort").addEventListener("change", (e) => {
    state.qualitySort = e.target.value;
    renderQualityDiagnostics(state.current);
  });

  document.getElementById("lang-filter-major").addEventListener("change", (e) => {
    state.langFilter.minMajor = Number(e.target.value);
    renderLanguageCoverage(state.current);
  });
  document.getElementById("lang-filter-other").addEventListener("change", (e) => {
    state.langFilter.minOther = Number(e.target.value);
    renderLanguageCoverage(state.current);
  });
  document.getElementById("lang-coverage-sort").addEventListener("change", (e) => {
    state.langFilter.sortBy = e.target.value;
    renderLanguageCoverage(state.current);
  });

  const samplesToggle = document.getElementById("samples-toggle");
  const samplesBody = document.getElementById("samples-body");
  samplesToggle.addEventListener("click", () => {
    const expanded = samplesToggle.getAttribute("aria-expanded") === "true";
    samplesToggle.setAttribute("aria-expanded", String(!expanded));
    samplesToggle.textContent = expanded ? "샘플 보기 ▾" : "샘플 숨기기 ▴";
    samplesBody.hidden = expanded;
  });

  document.getElementById("sample-select").addEventListener("change", (e) => {
    renderSampleDetail(state.current, e.target.value);
  });

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = current;
    localStorage.setItem("theme", current);
    renderAll();
  });
  // Default theme is light (set via <html data-theme="light"> in index.html) —
  // only override it if the visitor has explicitly toggled before.
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;

  selectReport(state.current);
}

init();
