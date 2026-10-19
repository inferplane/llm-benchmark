const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const base = process.env.BENCHMARK_SITE || "http://127.0.0.1:8782/";
const root = path.resolve(__dirname, "../..");
const report = (file) => JSON.parse(fs.readFileSync(path.join(root, "docs/results", file)));
const reports = report("index.json").map(report).sort((a, b) => a.run_id.localeCompare(b.run_id));
const directions = ["from-ko", "to-ko", "from-en", "to-en"];
const ko = reports.findLast((r) => r.report_kind === "integrated");
const en = reports.findLast((r) => r.default === true);
let loaded = reports;
let checkedValues = 0;

(async () => {
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    await page.goto(base);
    await page.locator("#heatmap-table tbody tr").first().waitFor();

    async function checkDirection(direction) {
      assert.equal(await page.locator("#direction-toggle [aria-pressed=true]").getAttribute("data-dir"), direction);
      const title = await page.locator("#run-select option:checked").textContent();
      const selected = loaded.find((r) => (r.title || r.run_id) === title);
      assert(selected, "Run selector must refer to a published report");
      const cohort = await page.locator("#cohort-select").inputValue();
      const sources = [...new Set([selected,
        loaded.findLast((r) => r.report_kind === "integrated"),
        loaded.findLast((r) => r.default === true)].filter(Boolean))];
      const [side, pivot] = direction.split("-");
      const eligible = (model) => cohort === "all" || model.evaluation_cohort === cohort;
      const inDirection = (pair) => pair.split("-")[side === "from" ? 0 : 1] === pivot;
      const names = new Set(sources.flatMap((r) => r.models.filter(eligible)
        .filter((m) => Object.keys(m.by_pair || {}).some(inDirection)).map((m) => m.name)));
      const pairs = new Set(sources.flatMap((r) => r.models.filter(eligible)
        .flatMap((m) => Object.keys(m.by_pair || {}).filter(inDirection))));
      const headers = (await page.locator("#heatmap-table thead .pair-chip").allTextContents())
        .map((h) => h.toLowerCase().replace("/", "-"));
      assert.deepEqual([...headers].sort(), [...pairs].sort());
      const rows = await page.locator("#heatmap-table tbody tr").evaluateAll((elements) =>
        elements.map((row) => [...row.cells].map((cell) => ({ text: cell.textContent.trim(), title: cell.title }))));
      assert.deepEqual(rows.map(([name]) => name.text).sort(), [...names].sort());
      for (const [name, ...cells] of rows) {
        headers.forEach((pair, i) => {
          const source = sources.find((r) => r.models.some((m) =>
            m.name === name.text && eligible(m) && Object.hasOwn(m.by_pair || {}, pair)));
          const model = source?.models.find((m) => m.name === name.text && eligible(m));
          const value = model?.by_pair[pair]?.judge_overall;
          assert.equal(cells[i].text, value == null ? "—" : value.toFixed(2), `${name.text} ${pair}`);
          if (value != null) {
            checkedValues++;
            assert(cells[i].title.includes(source.run_id), "Cell tooltip must identify its actual run");
            const label = model.evaluation_cohort === "explicit" ? "B" : model.evaluation_cohort === "original" ? "A" : "미기록";
            assert(cells[i].title.includes(`평가 조건: ${label}`));
          }
        });
      }
      assert.equal(await page.locator("#model-table-body .model-row").count(), selected.models.filter(eligible).length);
      return selected;
    }

    await checkDirection("from-ko");
    const selectedRun = await page.locator("#run-select").inputValue();
    for (const direction of [...directions, "from-ko", "from-en"]) {
      await page.locator(`[data-dir="${direction}"]`).click();
      await checkDirection(direction);
      assert.equal(await page.locator("#run-select").inputValue(), selectedRun, "Direction must preserve selected charts/run");
      assert((await page.locator("#heatmap-table thead .pair-chip").count()) > 1);
    }
    assert.equal(await page.locator("#interpretation-details").getAttribute("open"), null);
    await page.evaluate(() => window.scrollTo(0, 0));
    const firstRow = await page.locator("#heatmap-table tbody tr").first().boundingBox();
    assert(firstRow.y + firstRow.height < 900, "Scores should be visible before scrolling");
    assert.equal(await page.locator("main > :first-child").getAttribute("id"), "heatmap-panel");
    for (const id of ["scatter-chart", "scatter-zoom-chart"]) {
      const chart = await page.locator(`#${id}`).evaluate((canvas) => ({
        width: canvas.width, height: canvas.height, datasets: Chart.getChart(canvas).data.datasets.length,
        hiddenByDetails: !!canvas.closest("details:not([open])"),
      }));
      assert(chart.width > 0 && chart.height > 0 && chart.datasets > 0 && !chart.hiddenByDetails);
    }
    await page.locator('[data-track="flores"]').click();
    assert.match(await page.locator("#model-table-score-head").innerText(), /일반 문장/);

    // Explicit/original filters must constrain supplemental reports too.
    for (const selected of [ko, reports.find((r) => r.run_id === "integrated-2026-09-17")]) {
      await page.selectOption("#run-select", String(reports.indexOf(selected)));
      for (const cohort of ["explicit", "original", "all"]) {
        await page.selectOption("#cohort-select", cohort);
        for (const direction of directions) {
          await page.locator(`[data-dir="${direction}"]`).click();
          await checkDirection(direction);
          if (cohort !== "all" && direction.endsWith("-en")) {
            assert.equal(await page.locator("#heatmap-table thead .pair-chip").count(), 1,
              "Unlabelled EN report must not enter a recorded evaluation cohort");
          }
        }
      }
    }

    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
      const row = await page.locator("#heatmap-table tbody tr").first().boundingBox();
      assert(row.y + row.height < 844, "Mobile first screen should include scores");
      const scroller = page.locator(".heatmap-scroll");
      await scroller.evaluate((element) => { element.scrollLeft = 200; element.scrollTop = 150; });
      const frame = await scroller.boundingBox();
      const model = await page.locator("#heatmap-table tbody .rowhead").nth(5).boundingBox();
      const header = await page.locator("#heatmap-table thead th").first().boundingBox();
      assert(Math.abs(model.x - frame.x) < 3, "Model labels must remain visible during horizontal scroll");
      assert(Math.abs(header.y - frame.y) < 3, "Pair labels must remain visible during vertical scroll");
      await page.locator('[data-dir="from-en"]').click();
      await checkDirection("from-en");
      await page.locator("#theme-toggle").click();
      await checkDirection("from-en");
      await page.screenshot({ path: `/tmp/translation-quality-${width}.png` });
    }

    // Single-report sites still expose the measured EN↔KO column.
    loaded = [ko];
    await page.route("**/results/index.json", (route) => route.fulfill({ json: [`${ko.run_id}.json`] }));
    await page.reload();
    await page.locator("#heatmap-table tbody tr").first().waitFor();
    for (const direction of ["from-en", "to-en", "from-ko"]) {
      await page.locator(`[data-dir="${direction}"]`).click();
      await checkDirection(direction);
    }
    // A genuinely unavailable direction stays selected and recovers on next click.
    loaded = [en];
    await page.unroute("**/results/index.json");
    await page.route("**/results/index.json", (route) => route.fulfill({ json: [`${en.run_id}.json`] }));
    await page.reload();
    await page.locator("#heatmap-table tbody tr").first().waitFor();
    await page.locator('[data-dir="from-ko"]').click();
    assert.equal(await page.locator("#direction-toggle [aria-pressed=true]").getAttribute("data-dir"), "from-ko");
    assert.match(await page.locator(".heatmap-scroll").innerText(), /결과가 아직 없습니다/);
    assert.equal(await page.locator("#heatmap-scale-note").innerText(), "");
    await page.locator("#theme-toggle").click();
    assert.equal(await page.locator("#direction-toggle [aria-pressed=true]").getAttribute("data-dir"), "from-ko");
    await page.locator('[data-dir="from-en"]').click();
    await checkDirection("from-en");
    assert.deepEqual(errors, []);
    console.log(`PASS ${checkedValues} values/provenance, four directions, preserved chart run, cohort isolation, visible charts, mobile/sticky labels, themes, EN↔KO and empty-state recovery`);
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
