"""Complete mocked3300 population with real failure/cap classifications; no APIs."""
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch,AsyncMock
from bench import kimi_benchmark as k,kimi_observed as o,finqa as f,run as r,report,judge
parent=k.verify_parent();base=json.loads((report.DOCS_RESULTS_DIR/f'{k.BASE_TRANSLATION}.json').read_text())
scores={a:4 for a in [*report.AXES,'overall']};scores['judges_used']=['sol','fable-5'];scores['chrf']=None
for name in scores['judges_used']:
 scores.update({name+'_'+a:4 for a in [*report.AXES,'overall']});scores[name+'_tokens_in']=10;scores[name+'_tokens_out']=20
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp)
 with patch.object(k,'CONTRACT',root/'contract.json'),patch.object(k,'verify_parent',return_value=parent),patch.object(r,'RESULTS_DIR',root/'runs'),patch.object(report,'RESULTS_DIR',root/'runs'),patch.object(judge,'RESULTS_DIR',root/'runs'),patch.object(report,'DOCS_RESULTS_DIR',root/'public'):
  k.freeze();calls=[0]
  async def call(*args,**kwargs):
   i=calls[0];calls[0]+=1
   return {'text':'' if i in (0,1) else 'visible translation','tokens_in':10,'tokens_out':4096 if i in (0,2) else 20,'cache_read_tokens':30,'cache_write_tokens':40,'finish_reason':'max_tokens' if i in (0,2) else 'end_turn'}
  with patch.object(r,'make_client',return_value=object()),patch.object(r,'call_bedrock',new=call):
   assert asyncio.run(k.measure_translation())==1
  assert calls[0]==3300
  o.establish_policy()
  with patch('boto3.Session',return_value=object()),patch('boto3.client',return_value=object()),patch.object(judge,'judge_one',new=AsyncMock(return_value=scores)) as mocked:
   assert asyncio.run(o.run_judges())==0
   assert mocked.await_count==3298
  result=o.build_report();model=result['models'][0];a=model['aggregate'];d=model['collection_diagnostics']
  assert a['segments']==3300 and a['translation_failures']==2 and a['quality_eligible_segments']==3298
  assert d['recorded_attempts']==3300 and d['capped_outputs']==2 and d['capped_with_text']==d['capped_without_text']==1 and d['regenerated_attempts']==0
  assert a['cost_total_usd']==1.8412,(a['cost_total_usd'],d)
  f.write_json(report.DOCS_RESULTS_DIR/f'{k.BASE_TRANSLATION}.json',base);f.write_json(report.DOCS_RESULTS_DIR/f'{k.TRANSLATION_RUN}.json',result)
  combined=o.comparison();assert len(combined['models'])==30 and combined['models'][:-1]==base['models']
  path=k.translation_folder()/'translations.jsonl';original=path.read_bytes();rows=f.read_rows(path);rows.pop();f.write_rows(path,rows)
  try:o.validate()
  except ValueError:pass
  else:raise AssertionError('missing attempt accepted')
  path.write_bytes(original)
  rows=f.read_rows(path);rows[0]['error']=None;rows[0]['output_text']='invented';f.write_rows(path,rows)
  try:o.verify_policy()
  except (ValueError,r.InvalidResponseError):pass
  else:raise AssertionError('changed failed observation accepted')
  print('PASS3300 first attempts;3298 judged;2failed/2capped preserved;fee1.8412;old29 preserved;mutation rejected')
