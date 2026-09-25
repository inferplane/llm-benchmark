const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base=process.env.BENCHMARK_SITE || 'http://127.0.0.1:8782/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || undefined,args:['--no-sandbox']});
 try {
  const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.goto(base);await p.locator('.model-row').first().waitFor();
  assert.equal(await p.locator('.workload-card').count(),3);assert.equal(await p.locator('.model-row').count(),31);
  assert.equal(await p.locator('#customer-family-legend .model-family').count(),5);
  assert.equal(await p.locator('#model-table-body tr.model-row td').count(),31*6);
  assert(!/실패|미반환|tok\/s/.test(await p.locator('#model-table-body tr.model-row').allInnerTexts().then(a=>a.join(''))));
  assert.equal(await p.locator('#sample-detail tbody tr').count(),2);
  const row=p.locator('.model-row').filter({has:p.locator('button',{hasText:'gpt-6-luna'})});
  assert.equal(await row.locator('.model-family').getAttribute('data-family'),'gpt');
  await p.locator('#customer-volume').fill('1000');assert.match(await row.locator('td').nth(4).innerText(),/0\.1553/);
  await p.locator('#customer-volume').fill('0');assert.equal(await p.locator('#customer-volume').getAttribute('aria-invalid'),'true');assert.match(await p.locator('#volume-feedback').innerText(),/1,000건/);await p.locator('#customer-volume').fill('1000');
  await row.locator('button').click();assert.equal(await row.locator('button').getAttribute('aria-expanded'),'true');
  assert.match(await p.locator('#'+await row.getAttribute('data-detail')).innerText(),/출력 미반환 0건/);
  await p.locator('#recommendations-body a[data-model="gpt-6-luna"]').first().click();
  assert.equal(await p.locator('#sample-model-a').inputValue(),'gpt-6-luna');
  assert.match(await p.locator('#sample-detail tbody').innerText(),/gpt-6-luna/);
  await p.locator('#hero-panel').evaluate(el=>el.closest('details').open=true);
  await p.waitForTimeout(200);
  const chart=await p.locator('#scatter-chart').evaluate(c=>({width:c.width,labels:Chart.getChart(c).data.datasets.map(x=>x.label)}));
  assert(chart.width>0);assert(chart.labels.includes('GPT 계열')&&chart.labels.includes('중국 모델'));
  await p.selectOption('#cohort-select','explicit');assert.equal(await p.locator('.model-row').count(),4);
  await p.selectOption('#cohort-select','all');
  await p.locator('#track-toggle button[data-track="flores"]').click();assert.match(await p.locator('#model-table-score-head').innerText(),/일반 문장/);
  await p.locator('#theme-toggle').click();
  await p.setViewportSize({width:390,height:844});await p.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth,null,{timeout:5000});
  await p.goto(base+'finqa.html');await p.locator('#model-body tr').first().waitFor();
  assert.equal(await p.locator('#model-body tr').count(),30);assert.equal(await p.locator('#qa-recommendations .workload-card').count(),3);
  const qaRow=p.locator('#model-body tr').filter({has:p.locator('strong',{hasText:'gpt-6-luna'})});
  assert.match(await qaRow.innerText(),/18 \/ 20 · 90\.0%/);assert.equal(await qaRow.locator('.model-family').getAttribute('data-family'),'gpt');
  await p.locator('#customer-volume').fill('1000');assert.match(await qaRow.locator('td').nth(4).innerText(),/\$0\.31/);
  await p.selectOption('#qa-question','finqa-dev-AES/2003/page_52.pdf-1');
  await p.selectOption('#qa-model-a','gpt-6-luna');await p.selectOption('#qa-model-b','gpt-5.6-terra');
  assert.match(await p.locator('#qa-example-body').innerText(),/613/);assert.match(await p.locator('#qa-example-body').innerText(),/59/);
  assert.match(await p.locator('#qa-example-body .answer').first().innerText(),/검토 필요/);
  assert.match(await p.locator('#qa-example-body .answer').nth(1).innerText(),/정답과 일치/);
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const options=await p.locator('#run-select option').evaluateAll(xs=>xs.map(x=>x.value));
  for(const option of options){await p.selectOption('#run-select',option);assert((await p.locator('#model-body tr').count())>0);}
  assert.deepEqual(errors,[]);
  console.log('PASS both customer views, five family colors, cohort filters, accurate volume quotes, candidate links, two-model outputs, QA wrong-answer visibility, chart resize, mobile/dark mode and historical reports');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
