const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');const root=path.resolve(__dirname,'../..');
const ctx={window:{},Intl};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'docs/customer.js'),'utf8'),ctx);const B=ctx.window.BenchmarkView;
const tr=JSON.parse(fs.readFileSync(path.join(root,'docs/results/integrated-2026-09-25.json')));
const qa=JSON.parse(fs.readFileSync(path.join(root,'docs/finqa-results/finqa-gpt-6-luna-20260925.json')));
for(const [name,key] of Object.entries({'gpt-6-luna':'gpt','gpt-oss-120b':'gpt','claude-sonnet-5':'claude','kimi-k3':'china','qwen3.6-27b':'china','glm-4.7-flash':'china','nova-lite':'us','amazon-translate':'us','llama4-maverick':'us','grok-4.6':'us','gemma-4-31b-bedrock':'us','nemotron-nano-3-30b':'us','exaone-3.5-32b':'other','ministral-14b':'other','unknown':'other'}))assert.equal(B.family(name).key,key,name);
assert.equal(new Set(Object.values(B.groups).map(g=>g.color)).size,5);
const luna=tr.models.find(m=>m.name==='gpt-6-luna');
assert.equal(B.measure(luna,'translation').cost*10000,.5124/3300*10000);
assert.equal(B.money(null),'견적 확인 필요');assert.equal(B.money(0),'$0.00');assert.notEqual(B.money(.000016),'$0.00');assert.equal(B.money(.0000001),'<$0.000001');
for(const choice of B.shortlist(tr.models,'translation')) {
 assert.equal(new Set(choice.candidates.map(v=>v.cohort)).size,choice.candidates.length);
 for(const v of choice.candidates){assert(v.complete);assert(v.score>=4);assert(tr.models.includes(v.model));}
}
assert.equal(B.shortlist(qa.models,'qa')[1].candidates[0].name,'gpt-6-luna');
assert.equal(B.workload(qa.models.find(m=>m.aggregate.execution_accuracy===0),'qa'),'수치 정확성 재검증 필요');
for(const choice of B.shortlist(qa.models,'qa'))for(const v of choice.candidates)assert(v.score>=.9);
const incomplete=JSON.parse(JSON.stringify(luna));incomplete.aggregate.translation_failures=1;
assert.equal(B.shortlist([incomplete],'translation').flatMap(x=>x.candidates).length,0);
const low=JSON.parse(JSON.stringify(luna));low.by_track.synthetic.judge_overall=3;
assert.equal(B.shortlist([low],'translation').flatMap(x=>x.candidates).length,0);
const noPrice=JSON.parse(JSON.stringify(luna));noPrice.aggregate.cost_total_usd=null;noPrice.aggregate.cost_per_segment_usd=null;
assert.equal(B.shortlist([noPrice],'translation')[0].candidates.length,1);
assert.equal(B.shortlist([noPrice],'translation')[1].candidates.length,0);
assert(B.escape('<img src=x onerror=alert(1)>').startsWith('&lt;img'));
assert(B.cards(tr.models,'translation','synthetic',10000).includes('data-model="gpt-6-luna"'));

assert.equal(B.pair('a','a',['a','b']).join(','),'a,b');
assert.equal(B.pair('b','a',['a','b']).join(','),'b,a');
assert.equal(B.pair('a','a',['a']).join(','),'a,a');
console.log('PASS family mapping, cohort-isolated shortlist, quality thresholds, incomplete/missing cost handling, exact volume scaling and escaped output');
