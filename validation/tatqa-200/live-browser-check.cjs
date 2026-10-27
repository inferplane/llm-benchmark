'use strict';
const assert = require('assert/strict');
const fs = require('fs');
const { chromium } = require('/home/atomoh/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');
const out = 'validation/tatqa-200';
(async () => {
  const browser = await chromium.launch({
    executablePath: '/home/atomoh/.cache/ms-playwright/chromium-1234/chrome-linux/chrome',
    headless: true, args: ['--no-sandbox']
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [], checks = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    const response = await page.goto('https://inferplane.github.io/llm-benchmark/tatqa.html', { waitUntil: 'networkidle' });
    assert.equal(response.status(), 200);
    await page.locator('#model-body tr').first().waitFor();
    assert.equal(await page.locator('#model-body tr').count(), 35);
    assert.equal(await page.locator('#sample-select option').count(), 200);
    assert.match(await page.locator('#question-count').innerText(), /200/);
    assert.match(await page.locator('#context-count').innerText(), /200/);
    checks.push('35 models and 200 questions/contexts loaded from public Pages');
    await page.selectOption('#sample-model-a', 'gpt-6.1-terra');
    assert.match(await page.locator('#sample-answers').innerText(), /gpt-6\.1-terra/);
    await page.selectOption('#type-select', 'arithmetic');
    assert.equal(await page.locator('#type-body tr').count(), 35);
    checks.push('Terra answer comparison and arithmetic type controls work');
    for (const width of [1280, 375]) {
      await page.setViewportSize({ width, height: 900 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: `${out}/live-${width}.png` });
      checks.push(`viewport ${width}: no page overflow`);
    }
    assert.deepEqual(errors, []);
    const result = { status: 'PASS', verified_at: new Date().toISOString(),
      url: page.url(), checks, errors, model_rows: 35, question_options: 200 };
    fs.writeFileSync(`${out}/live-browser.json`, JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
