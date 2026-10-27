'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const {chromium}=require('/home/atomoh/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');
const root=path.resolve('docs'),out=path.resolve('validation/tatqa-200');
const actual=process.argv.includes('--actual');
const index=JSON.parse(fs.readFileSync(actual?path.join(root,'tatqa-results/index.json'):'/tmp/tatqa-preview/tatqa-results/index.json','utf8'));
const report=JSON.parse(fs.readFileSync(actual?path.join(root,`tatqa-results/${index.latest}.json`):`/tmp/tatqa-preview/tatqa-results/${index.latest}.json`,'utf8'));
const result={mode:actual?'actual':'fixture',run_id:report.run_id,report_generated_at:report.generated_at,report_sha256:crypto.createHash('sha256').update(fs.readFileSync(actual?path.join(root,`tatqa-results/${index.latest}.json`):`/tmp/tatqa-preview/tatqa-results/${index.latest}.json`)).digest('hex'),missing_responses:report.models.reduce((n,m)=>n+m.metrics.missing,0),checks:[],console_errors:[],page_errors:[],unexpected_http_errors:[],screenshots:[],widths:[],font_samples:{}};
result.verified_at=new Date().toISOString();result.source_hashes=Object.fromEntries(['tatqa.html','tatqa.js','tatqa.css','app.js','index.html','finqa.html'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
const check=(name,condition)=>{assert.ok(condition,name);result.checks.push(name);};
(async()=>{
 const browser=await chromium.launch({executablePath:'/home/atomoh/.cache/ms-playwright/chromium-1234/chrome-linux/chrome',headless:true,args:['--no-sandbox']});
 try {
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 let mode='success';
 await context.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname!=='tatqa.local')return route.abort();
  const relative=url.pathname.replace(/^\//,'');
  if(relative==='tatqa-results/index.json')return route.fulfill({status:mode==='error'?503:200,contentType:'application/json',body:JSON.stringify(mode==='empty'?{latest:null,runs:[]}:index)});
  if(relative===`tatqa-results/${index.latest}.json`)return route.fulfill({contentType:'application/json',body:JSON.stringify(mode==='malformed'?{...report,scenario:'invalid'}:report)});
  const file=path.join(root,relative||'index.html');
  if(!fs.existsSync(file)||!fs.statSync(file).isFile())return route.fulfill({status:404,body:'missing'});
  return route.fulfill({contentType:relative.endsWith('.js')?'text/javascript':relative.endsWith('.css')?'text/css':relative.endsWith('.svg')?'image/svg+xml':relative.endsWith('.json')?'application/json':'text/html',body:fs.readFileSync(file)});
 });
 const page=await context.newPage();
 page.on('console',m=>{if(m.type()==='error'&&mode==='success')result.console_errors.push(m.text());});
 page.on('pageerror',e=>result.page_errors.push(e.message));
 page.on('response',r=>{if(r.status()>=400&&mode==='success')result.unexpected_http_errors.push({url:r.url(),status:r.status()});});
 await page.addInitScript(()=>{window.fetchModes=[];const old=window.fetch;window.fetch=(...args)=>{window.fetchModes.push(args[1]?.cache);return old(...args);};});
 await page.goto('http://tatqa.local/tatqa.html');
 await page.locator('#model-body tr').first().waitFor();
 check('report model count matches rendered rows',(await page.locator('#model-body tr').count())===report.models.length);
 check('all report fetches explicitly no-store',(await page.evaluate(()=>window.fetchModes)).every(x=>x==='no-store'));
 if(actual){check('35 models including Terra',report.models.length===35&&report.models.some(m=>m.name==='gpt-6.1-terra'));check('all 200 questions available',report.samples.length===200);}
 await page.keyboard.press('Tab');
 check('skip link first keyboard focus',await page.evaluate(()=>document.activeElement.classList.contains('skip-link')));
 await page.keyboard.press('Enter');
 check('skip link targets main',new URL(page.url()).hash==='#main');
 await page.locator('#sort-select').focus();await page.keyboard.press('End');await page.keyboard.press('Tab');
 check('sort select keyboard access',(await page.inputValue('#sort-select'))==='name');
 for(const order of ['exact_match','f1','cost','latency','name']){
  await page.selectOption('#sort-select',order);
  const names=await page.locator('#model-body tr .model-name').allTextContents();
  const metric={cost:'estimated_cost_per_question_usd',latency:'latency_p50_s'}[order]||order;
  const expected=[...report.models].sort((a,b)=>{if(order==='name')return a.name.localeCompare(b.name);const av=a.metrics[metric],bv=b.metrics[metric];if(Number.isFinite(av)!==Number.isFinite(bv))return Number.isFinite(av)?-1:1;return (Number.isFinite(av)?(['cost','latency'].includes(order)?av-bv:bv-av):0)||a.name.localeCompare(b.name);}).map(m=>m.name);
  check(`sorting ${order}`,JSON.stringify(names)===JSON.stringify(expected));
 }
 for(const type of ['span','arithmetic','multi-span','count']){
  await page.selectOption('#type-select',type);
  check(`type count ${type}`,(await page.locator('#type-summary').innerText()).includes(`${report.dataset.answer_types[type]}문항`));
  await page.selectOption('#sample-type',type);
  const n=report.samples.filter(s=>s.answer_type===type).length;
  check(`question filter ${type}`,(await page.locator('#sample-select option').count())===n);
 }
 await page.selectOption('#sample-type','all');
 await page.selectOption('#sample-select',String(report.samples.length-1));
 check('question switching shows selected text',(await page.locator('#sample-question').innerText()).includes(report.samples.at(-1).question));
 await page.selectOption('#sample-select','0');
 for(const [select,i] of [['sample-model-a',0],['sample-model-b',report.models.length-1]])await page.selectOption(`#${select}`,report.models[i].name);
 check('both model selectors change answer cards',JSON.stringify(await page.locator('#sample-answers h3').allTextContents())===JSON.stringify([report.models[0].name,report.models.at(-1).name]));
 const evidence=page.locator('#sample-question details');await evidence.locator('summary').focus();await page.keyboard.press('Enter');
 check('keyboard opens source evidence',await evidence.getAttribute('open')!==null);
 check('source table displays',await evidence.locator('table').count()>0);
 const raw=page.locator('#sample-answers details').first();if(await raw.count()){await raw.locator('summary').focus();await page.keyboard.press('Space');check('keyboard opens raw output',await raw.getAttribute('open')!==null);}
 check('untrusted text cannot create executable nodes',await page.locator('#sample-question img,#sample-question script,#sample-answers script').count()===0);
 await page.getByText('실행 범위·재현 정보',{exact:true}).click();
 check('generation settings listed',await page.locator('#generation-settings tbody tr').count()===report.models.length);
 const comparisonScroll=page.locator('[aria-label="모델별 EM F1 시간 비용 비교"]');await page.setViewportSize({width:375,height:900});await comparisonScroll.focus();await page.keyboard.press('ArrowRight');await page.waitForTimeout(180);check('wide comparison table scrolls by keyboard',await comparisonScroll.evaluate(e=>e.scrollLeft>0));await comparisonScroll.evaluate(e=>e.scrollLeft=0);
 for(const width of [375,768,1280]){
  await page.setViewportSize({width,height:900});
  const dims=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth}));
  check(`no horizontal page overflow at ${width}`,dims.page<=dims.viewport);
  result.widths.push(dims);
  const file=`content-${actual?'actual':'fixture'}-${width}.png`;
  await page.screenshot({path:path.join(out,file),fullPage:true});result.screenshots.push(file);
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,file.replace('.png','-hero.png'))});
  for(const [selector,section] of [['#sample-title','sample'],['#protocol-title','protocol']]){await page.locator(selector).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,file.replace('.png',`-${section}.png`))});}
 }
 for(const selector of ['body','.customer-note','.model-provider','.metric-sub','.sample-caption','nav a'])result.font_samples[selector]=await page.locator(selector).first().evaluate(e=>getComputedStyle(e).fontSize);
 for(const state of ['empty','malformed','error']){
  mode=state;await page.reload();await page.waitForFunction(()=>!document.querySelector('#load-status').textContent.includes('불러오는 중'));
  check(`${state} hides stale scores`,!(await page.locator('#results').isVisible()));
  check(`${state} offers retry`,await page.locator('#retry-load').isVisible());
 }
 mode='success';await page.locator('#retry-load').click();await page.locator('#model-body tr').first().waitFor();check('retry recovers real scores',await page.locator('#results').isVisible());
 check('no normal-load console errors',result.console_errors.length===0);check('no uncaught JS errors',result.page_errors.length===0);check('no unexpected HTTP failures',result.unexpected_http_errors.length===0);
 for(const file of ['index.html','finqa.html'])check(`${file} TAT-QA navigation`,fs.readFileSync(path.join(root,file),'utf8').includes('href="tatqa.html"'));
 result.verdict='PASS';
 } finally {await browser.close();fs.writeFileSync(path.join(out,`content-browser-${actual?'actual':'fixture'}.json`),JSON.stringify(result,null,2)+'\n');}
 console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
