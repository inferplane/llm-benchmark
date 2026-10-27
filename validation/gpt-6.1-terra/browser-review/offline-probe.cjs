const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/home/atomoh/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');
const root='/home/atomoh/llm-benchmark',out='/tmp/terra-content-review',base='https://terra-review.test/';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:'/home/atomoh/.cache/ms-playwright/chromium-1234/chrome-linux/chrome',args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--force-webrtc-ip-handling-policy=disable_non_proxied_udp']});
for(const task of ['whoami','lotte-tower']){
 const dir=out+'/'+task;fs.mkdirSync(dir,{recursive:true});const prefix=base+'models/gpt-6.1-terra/',arturl=prefix+task+'/artwork.html',runtimeurl=prefix+'runtime/three-runtime.js',wrapurl=prefix+task+'/review.html';
 const original=fs.readFileSync(root+'/docs/models/gpt-6.1-terra/'+task+'/artwork.html'),runtime=fs.readFileSync(root+'/docs/models/gpt-6.1-terra/runtime/three-runtime.js');
 const wrapper='<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;height:100%}iframe{width:100%;height:100%;border:0;display:block}</style><iframe title="Original Terra artifact" sandbox="allow-scripts" src="artwork.html"></iframe>';
 const allowed=new Map([[wrapurl,{body:wrapper,type:'text/html'}],[arturl,{body:original,type:'text/html',art:true}],[runtimeurl,{body:runtime,type:'application/javascript'}]]);
 const r={task,artwork_sha256:sha(original),runtime_sha256:sha(runtime),sandbox:'allow-scripts',offline:true,exact_allowlist:[...allowed.keys()],requests:[],blockedRequests:[],errors:[],warnings:[],controls:[],drawings:[],stages:[],views:[]};
 const context=await browser.newContext({offline:true,serviceWorkers:'block',permissions:[],acceptDownloads:false,viewport:{width:1440,height:900},deviceScaleFactor:1});
 await context.route('**/*',async route=>{const req=route.request(),res=allowed.get(req.url());r.requests.push({url:req.url(),method:req.method()});if(!res||req.method()!=='GET'){r.blockedRequests.push(req.url());return route.abort('blockedbyclient')};const headers={'Content-Type':res.type+';charset=utf-8','Access-Control-Allow-Origin':'*'};if(res.art)headers['Content-Security-Policy']="default-src 'none';script-src 'unsafe-inline' "+runtimeurl+";style-src 'unsafe-inline';img-src data: blob:;connect-src 'none';font-src 'none';worker-src 'none';frame-src 'none';media-src 'none';form-action 'none';base-uri 'none';sandbox allow-scripts";await route.fulfill({status:200,headers,body:res.body})});
 await context.routeWebSocket('**/*',s=>{r.blockedRequests.push('WebSocket');s.close()});
 await context.addInitScript(()=>{
  window.__scenes=[];window.__glDraws=0;window.__draw2d=0;
  let three;
  Object.defineProperty(window,'THREE',{configurable:true,get(){return three},set(v){three=v;const Orig=v.WebGLRenderer;if(Orig)v.WebGLRenderer=class extends Orig{constructor(...args){super(...args);const render=this.render.bind(this);this.render=(scene,camera)=>{let e=window.__scenes.find(e=>e.renderer===this);if(!e){e={renderer:this};window.__scenes.push(e)}Object.assign(e,{scene,camera});return render(scene,camera)}}}}});
  const original=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(type,...args){const c=original.call(this,type,...args);if(c&&!c.__reviewWrapped){if(/^webgl/.test(type)){for(const name of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced'])if(c[name]){const f=c[name].bind(c);c[name]=(...x)=>{window.__glDraws++;return f(...x)}}}else if(type==='2d'){const f=c.fillRect.bind(c);c.fillRect=(...x)=>{window.__draw2d++;return f(...x)}}c.__reviewWrapped=true}return c};
 });
 const page=await context.newPage();page.on('pageerror',e=>r.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')r.errors.push(m.text());else if(m.type()==='warning')r.warnings.push(m.text())});
 const getframe=async()=>await page.locator('iframe').elementHandle().then(e=>e.contentFrame());let frame;
 const state=async()=>frame.evaluate(()=>({draws2d:window.__draw2d,glDraws:window.__glDraws,revision:window.THREE?.REVISION,scenes:window.__scenes.map(e=>{const objects=[];e.scene.traverse(o=>{if(o.geometry){const p=o.geometry.attributes.position;objects.push({type:o.type,geometry:o.geometry.type,vertices:p?.count||0,index:o.geometry.index?.count||0,positions:p?Array.from(p.array):[],matrix:o.matrixWorld.elements})}});return{camera:e.camera.position.toArray(),rotation:e.camera.quaternion.toArray(),objects}})}));
 const compact=s=>({...s,scenes:s.scenes.map(e=>({...e,objects:e.objects.map(o=>({...o,positions_sha256:sha(JSON.stringify(o.positions)),positions:undefined}))}))});
 try{
  await page.goto(wrapurl);await page.waitForTimeout(600);frame=await getframe();r.initial={state:compact(await state()),text:await frame.locator('body').innerText()};
  await page.screenshot({path:dir+'/desktop-top.png'});
  if(task==='whoami'){
   for(const id of ['seed','reset','motion']){const b=frame.locator('#'+id);await b.focus();const before=compact(await state());await page.keyboard.press('Enter');await page.waitForTimeout(80);r.controls.push({id,before,after:compact(await state()),label:await b.innerText(),status:await frame.locator('#status').innerText(),focused:await b.evaluate(e=>document.activeElement===e)})}
   await frame.locator('#art').click({position:{x:100,y:100}});r.pointerStatus=await frame.locator('#status').innerText();
  }else{
   const canvas=frame.locator('canvas');const before=compact(await state());await canvas.focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('+');r.cameraKeyboard={before,after:compact(await state())};
   const box=await canvas.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+100,box.y+box.height/2+30,{steps:8});await page.mouse.up();r.cameraDrag=compact(await state());await page.mouse.wheel(0,-240);await page.waitForTimeout(80);r.cameraWheel=compact(await state());await frame.locator('#reset').click();r.cameraReset=compact(await state());
   for(const tab of await frame.locator('[data-drawing]').all()){await tab.click();r.drawings.push({id:await tab.getAttribute('data-drawing'),name:await frame.locator('#drawing-name').innerText(),description:await frame.locator('#drawing-desc').innerText(),basis:await frame.locator('#drawing-basis').innerText(),svg:await frame.locator('#drawing').innerHTML()});await frame.locator('#drawing').screenshot({path:dir+'/drawing-'+await tab.getAttribute('data-drawing')+'.png'})}
   await frame.locator('[data-drawing=plan]').click();
   for(const step of await frame.locator('[data-stage]').all()){await step.focus();await page.keyboard.press('Enter');r.stages.push({id:await step.getAttribute('data-stage'),label:await frame.locator('#model-label').innerText(),state:compact(await state()),drawing:await frame.locator('#drawing').innerHTML(),description:await frame.locator('#stage-desc').innerText()});await canvas.screenshot({path:dir+'/stage-'+await step.getAttribute('data-stage')+'.png'})}
   await frame.locator('[data-drawing=elevation]').click();await frame.locator('[data-drawing=elevation]').focus();await page.keyboard.press('ArrowRight');r.tabKeyboard={selected:await frame.locator('[aria-selected=true]').getAttribute('data-drawing'),focused:await frame.locator('[aria-selected=true]').evaluate(e=>document.activeElement===e)};
  }
  for(const [width,height] of [[1440,900],[768,1024],[375,844],[720,900]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(200);await frame.evaluate(()=>scrollTo(0,0));r.views.push(await frame.evaluate(()=>({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth+1,scrollHeight:document.documentElement.scrollHeight,fonts:[...document.querySelectorAll('button,p,a,footer,svg text')].filter(e=>e.getBoundingClientRect().width).map(e=>({text:e.textContent.trim().slice(0,75),font:getComputedStyle(e).fontSize,color:getComputedStyle(e).color,rect:e.getBoundingClientRect().toJSON()})),canvasRects:[...document.querySelectorAll('canvas')].map(e=>e.getBoundingClientRect().toJSON())})));
   await page.screenshot({path:dir+'/view-'+width+'.png'});
   if(task==='lotte-tower'){await frame.locator('#drawing').scrollIntoViewIfNeeded();await page.screenshot({path:dir+'/drawing-mobile-'+width+'.png'});await frame.locator('.process').scrollIntoViewIfNeeded();await page.screenshot({path:dir+'/process-'+width+'.png'})}
  }
  await page.setViewportSize({width:375,height:844});await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await page.waitForTimeout(400);frame=await getframe();r.reduced={before:compact(await state()),motionLabel:task==='whoami'?await frame.locator('#motion').innerText():null};await page.waitForTimeout(450);r.reduced.after=compact(await state());await page.screenshot({path:dir+'/reduced-375.png'});
 }catch(e){r.harnessError=e.stack}
 fs.writeFileSync(dir+'/browser.json',JSON.stringify(r,null,2));console.log(task,JSON.stringify({hash:r.artwork_sha256,errors:r.errors,warnings:r.warnings,blocked:r.blockedRequests,harnessError:r.harnessError,gl:r.initial?.state.glDraws,views:r.views.map(v=>({width:v.width,overflow:v.overflow}))}));await context.close();
}
await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
