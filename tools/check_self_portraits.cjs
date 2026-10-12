/* Run each model's actual artwork in Chromium; save diagnostics and previews.
   PLAYWRIGHT_MODULE and CHROMIUM_PATH select existing local installations. */
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "..");
const base = "http://self-portrait.test/";

async function main() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    args: ["--no-sandbox"],
  });
  // The browser is offline. Only this tool's exact allowlist can supply bytes.
  // Generated code never gets network access or access to benchmark data.
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }, offline: true,
    serviceWorkers: "block", permissions: [], acceptDownloads: false,
  });
  const allowed = new Map([
    [base + "models/portraits.css", { file: path.join(root, "docs/models/portraits.css"), type: "text/css" }],
    [base + "models/readability.css", { file: path.join(root, "docs/models/readability.css"), type: "text/css" }],
    [base + "models/viewer.js", { file: path.join(root, "docs/models/viewer.js"), type: "application/javascript" }],
    [base + "favicon.svg", { file: path.join(root, "docs/favicon.svg"), type: "image/svg+xml" }],
  ]);
  await context.route("**/*", async route => {
    const item = allowed.get(route.request().url());
    if (!item || route.request().method() !== "GET") return route.abort("blockedbyclient");
    const headers = { "Content-Type": item.type + "; charset=utf-8" };
    if (item.artwork) headers["Content-Security-Policy"] = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' data:; img-src data: blob:; connect-src 'none'; font-src 'none'; frame-src 'none'; worker-src 'none'; media-src 'none'; form-action 'none'; base-uri 'none'; sandbox allow-scripts";
    await route.fulfill({ status: 200, headers, body: fs.readFileSync(item.file) });
  });
  await context.routeWebSocket("**/*", socket => socket.close());
  const catalog = JSON.parse(fs.readFileSync(path.join(root, "docs/models/catalog.json"), "utf8"));
  const selected = process.argv[2] ? new Set(process.argv[2].split(",")) : null;
  const results = [], feedback = {};
  for (const model of catalog.filter(item => item.status === "generated" && (!selected || selected.has(item.model)))) {
    if (!/^[a-z0-9][a-z0-9.-]*$/.test(model.model)) throw new Error("Unsafe model path");
    allowed.set(`${base}models/${model.model}/`, { file: path.join(root, "docs/models", model.model, "index.html"), type: "text/html" });
    allowed.set(`${base}models/${model.model}/artwork.html`, { file: path.join(root, "docs/models", model.model, "artwork.html"), type: "text/html", artwork: true });
    for (const name of ["prompt.txt", "initial-prompt.txt", "implementation-cost.json"]) {
      const file = path.join(root, "docs/models", model.model, name);
      if (fs.existsSync(file)) allowed.set(`${base}models/${model.model}/${name}`, { file, type: name.endsWith(".json") ? "application/json" : "text/plain" });
    }
    const page = await context.newPage();
    const errors = [], warnings = [], network = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      if (message.type() === "error" && /Content Security Policy|violates.*directive/i.test(message.text())) errors.push(message.text().slice(0, 300));
    });
    page.on("request", request => {
      if (!allowed.has(request.url()) && !request.url().startsWith("data:") && !request.url().startsWith("blob:")) network.push(request.url());
    });
    const response = await page.goto(`${base}models/${model.model}/`, { waitUntil: "load" });
    await page.waitForTimeout(700);
    const directory = path.join(root, "docs/models", model.model);
    await page.screenshot({ path: path.join(directory, "preview.jpg"), type: "jpeg", quality: 75 });
    const promptButton = page.locator("[data-open-prompts]");
    if (await promptButton.count()) {
      await promptButton.click();
      const dialog = page.locator("#prompt-dialog");
      const texts = await dialog.locator("pre").allTextContents();
      const expected = fs.readFileSync(path.join(directory, "prompt.txt"), "utf8");
      if (texts.at(-1) !== expected) errors.push("Prompt dialog does not display the actual request text.");
      await page.keyboard.press("Escape");
      if (await dialog.isVisible()) errors.push("Prompt dialog Escape did not close.");
    }
    const costButton = page.locator("[data-open-cost]");
    if (await costButton.count()) {
      await page.locator(".viewer-actions > details > summary").click();
      await costButton.click();
      const cost = JSON.parse(fs.readFileSync(path.join(directory, "implementation-cost.json"), "utf8"));
      const dialog = page.locator("#cost-dialog");
      if (await dialog.locator("tbody tr").count() !== cost.recorded_attempts) errors.push("Cost dialog request count differs from records.");
      await page.keyboard.press("Escape");
      if (await dialog.isVisible()) errors.push("Cost dialog Escape did not close.");
      await page.locator(".viewer-actions > details > summary").click();
    }
    const frame = page.frames().find(item => item.url().endsWith("/artwork.html"));
    if (!frame) { errors.push("The artwork iframe did not load."); }
    let initial = "";
    let details = {};
    if (frame) {
      initial = await frame.locator("body").innerText();
      details = await frame.evaluate(() => ({
        text: document.body.innerText.slice(0, 1600),
        canvases: document.querySelectorAll("canvas").length,
        svgs: document.querySelectorAll("svg").length,
        canvasDetails: Array.from(document.querySelectorAll("canvas")).map(canvas => {
          const rect = canvas.getBoundingClientRect();
          const context = canvas.getContext("2d");
          const sample = new Set();
          if (context && canvas.width && canvas.height) for (let x = 1; x < 10; x++) for (let y = 1; y < 10; y++) {
            const pixel = context.getImageData(Math.floor(canvas.width * x / 10), Math.floor(canvas.height * y / 10), 1, 1).data;
            sample.add(Array.from(pixel).join(","));
          }
          return { width: canvas.width, height: canvas.height, cssWidth: rect.width, cssHeight: rect.height, sampledColors: sample.size };
        }),
        buttons: Array.from(document.querySelectorAll("button")).map(button => ({
          text: button.innerText, id: button.id,
          visible: button.getBoundingClientRect().width > 0 && button.getBoundingClientRect().height > 0,
        })),
      }));
      const normalized = initial.toLowerCase().replace(/[^a-z0-9.]/g, "");
      const identity = model.model.replace(/-bedrock$/, "").match(/[a-z]+|\d+(?:\.\d+)*/g) || [];
      if (!identity.every(part => normalized.includes(part)) && !details.canvases) errors.push("The displayed text does not contain the requested model name.");
      const artworkBox = await page.locator("iframe").boundingBox();
      if (artworkBox) {
        await page.mouse.move(artworkBox.x + 10, artworkBox.y + 10);
        await page.waitForTimeout(60);
      }
      const buttons = frame.locator("button");
      for (let index = 0; index < Math.min(await buttons.count(), 5); index++) {
        const button = buttons.nth(index);
        if (await button.isEnabled() && await button.evaluate(element => element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }))) {
          await button.click({ timeout: 3000 }).catch(error => errors.push("Control click: " + error.message.slice(0, 200)));
          await page.waitForTimeout(120);
        }
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    if (frame) {
      // Desktop clicks may have opened a modal. Test the fresh mobile page;
      // background controls being inert behind an open modal is expected.
      await frame.goto(frame.url(), { waitUntil: "load" });
      await page.waitForTimeout(700);
    }
    await page.waitForTimeout(200);
    if (await promptButton.count()) {
      await promptButton.click();
      const mobileDialog = await page.locator("#prompt-dialog").evaluate(dialog => {
        const r = dialog.getBoundingClientRect();
        return { fits: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight,
          overflow: dialog.scrollWidth > dialog.clientWidth + 1 };
      });
      if (!mobileDialog.fits || mobileDialog.overflow) errors.push("Mobile prompt dialog overflows viewport.");
      await page.locator("[data-close-prompts]").click();
    }
    if (await costButton.count()) {
      await page.locator(".viewer-actions > details > summary").click();
      await costButton.click();
      const fits = await page.locator("#cost-dialog").evaluate(dialog => {
        const rect = dialog.getBoundingClientRect();
        return rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight
          && dialog.scrollWidth <= dialog.clientWidth + 1;
      });
      if (!fits) errors.push("Mobile cost dialog overflows viewport.");
      await page.keyboard.press("Escape");
      await page.locator(".viewer-actions > details > summary").click();
    }
    if (frame) {
      const mobile = await frame.evaluate(() => {
        const controls = Array.from(document.querySelectorAll("button")).filter(button => {
          return button.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
        }).map(button => {
          const rect = button.getBoundingClientRect();
          return { text: button.innerText, inside: rect.top >= 0 && rect.left >= -1 && rect.right <= innerWidth + 1 && rect.bottom <= innerHeight + 1 };
        });
        return { horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1, controls };
      });
      for (const control of await frame.locator("button").all()) {
        if (!await control.isEnabled() || !await control.evaluate(element => element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }))) continue;
        const label = await control.innerText();
        try {
          // Scrollable artworks may place usable controls below the fold.
          // A trial click scrolls and checks occlusion without invoking handlers.
          await control.click({ trial: true, timeout: 3000 });
        } catch {
          errors.push(`Mobile 390px: control cannot be reached by scrolling: ${label}`);
        }
      }
      details.mobile = mobile;
      if (mobile.horizontalOverflow) warnings.push("Mobile 390px: horizontal overflow requires visual review for clipping.");
    }
    if (network.length) errors.push("External network requests are not allowed: " + [...new Set(network)].join(", "));
    const result = { model: model.model, httpStatus: response.status(), errors: [...new Set(errors)], warnings, ...details };
    results.push(result);
    if (errors.length) feedback[model.model] = result.errors;
    console.log(`${errors.length ? "ISSUES" : warnings.length ? "WARN" : "PASS"} ${model.model}: ${[...new Set([...errors, ...warnings])].join("; ") || "iframe, text, controls, mobile, no script errors"}`);
    await page.close();
    allowed.delete(`${base}models/${model.model}/`);
    allowed.delete(`${base}models/${model.model}/artwork.html`);
    allowed.delete(`${base}models/${model.model}/prompt.txt`);
    allowed.delete(`${base}models/${model.model}/initial-prompt.txt`);
    allowed.delete(`${base}models/${model.model}/implementation-cost.json`);
  }
  await browser.close();
  const validation = path.join(root, "validation/self-portraits");
  fs.mkdirSync(validation, { recursive: true });
  const previousPath = path.join(validation, "browser-check.json");
  const previous = selected && fs.existsSync(previousPath) ? JSON.parse(fs.readFileSync(previousPath, "utf8")).filter(item => !selected.has(item.model)) : [];
  const merged = [...previous, ...results];
  const allFeedback = Object.fromEntries(merged.filter(item => item.errors.length).map(item => [item.model, item.errors]));
  fs.writeFileSync(previousPath, JSON.stringify(merged, null, 2));
  fs.writeFileSync(path.join(validation, "feedback.json"), JSON.stringify(allFeedback, null, 2));
  console.log(`Checked ${results.length} model-authored artworks; ${Object.keys(feedback).length} need the author's revision.`);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
