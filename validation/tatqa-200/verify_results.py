"""Independent report/provenance/denominator verification; no candidate calls."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import tatqa
from bench.vendor.tatqa.tatqa_metric import TaTQAEmAndF1

parser=argparse.ArgumentParser()
parser.add_argument('--run-id',required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[2]
directory=root/'results/tatqa'/args.run_id
manifest,records,predictions,events=tatqa.load_run(directory)
path=root/'docs/tatqa-results'/f'{args.run_id}.json'
report=json.loads(path.read_text())
assert report['run_id']==args.run_id and report['scenario']=='tatqa'
assert report['contract_sha256']==manifest['contract_sha256']
assert report['contract']==manifest['contract']
assert len(records)==len(report['samples'])==report['dataset']['questions']==200
assert len({r['id'] for r in records})==len({r['context_id'] for r in records})==200
assert Counter(r['answer_type'] for r in records)=={'span':86,'arithmetic':84,'multi-span':25,'count':5}
expected=[m['name'] for m in manifest['contract']['models']]
assert [m['name'] for m in report['models']]==expected
assert len(expected)==35 and 'gpt-6.1-terra' in expected
assert report['dataset']['dataset_sha256']==tatqa.digest(records)
assert hashlib.sha256((root/'scenarios/tatqa/source-test-gold.json').read_bytes()).hexdigest()==report['dataset']['source_sha256']
byid={r['id']:r for r in records}
counts=Counter()
for model in report['models']:
    name=model['name']; m=model['metrics']
    assert m['total']==200
    assert sum(m[key] for key in ['scored','invalid','request_failures','missing','truncated'])==200
    scores=[tatqa.evaluate_one(r,predictions.get((name,r['id']))) for r in records]
    assert m['correct']==sum(s['exact_match'] for s in scores)
    assert abs(m['exact_match']-sum(s['exact_match'] for s in scores)/200)<1e-12
    assert abs(m['f1']-sum(s['f1'] for s in scores)/200)<1e-12
    assert 0<=m['exact_match']<=1 and 0<=m['f1']<=1
    assert m['missing']==0, f'unexecuted questions: {name}'
    assert sum(t['total'] for t in model['by_answer_type'].values())==200
    assert sum(t['correct'] for t in model['by_answer_type'].values())==m['correct']
    for quality in model['by_answer_type'].values():
        assert set(quality)=={'total','exact_match','f1','correct'}
    if m['request_failures']:
        assert m['estimated_cost_usd'] is None
    elif m['cost_unavailable_reason'] is None:
        config=model['run_config']
        raw=[predictions[(name,r['id'])] for r in records]
        # Recalculate recorded-token cost independently of report helpers.
        total_in=sum(r.get('tokens_in') or 0 for r in raw)
        total_out=sum(r.get('tokens_out') or 0 for r in raw)
        expected_cost=total_in*config['price_in']/1e6+total_out*config['price_out']/1e6
        for field,price in [('cache_read_tokens','price_cache_read'),('cache_write_tokens','price_cache_write')]:
            tokens=sum(r.get(field) or 0 for r in raw)
            if tokens:
                expected_cost+=tokens*config[price]/1e6
        expected_cost=round(expected_cost,4)
        assert m['tokens_in']==total_in and m['tokens_out']==total_out
        assert abs(m['estimated_cost_usd']-expected_cost)<1e-9
        assert abs(m['estimated_cost_per_question_usd']-round(expected_cost/200,5))<1e-9
    for s in scores: counts[s['status']]+=1
for sample in report['samples']:
    r=byid[sample['id']]
    assert sample['question']==r['question'] and sample['table']==r['table']
    assert sample['paragraphs']==r['paragraphs']
    assert [p['model'] for p in sample['predictions']]==expected
    assert sample['gold_answer']==r['gold']['answer'] and sample['gold_scale']==r['gold']['scale']
# Gold normalization independent of the strict adapter, using upstream metric.
for r in records:
    gold=r['gold']; a=gold['answer'] if isinstance(gold['answer'],list) else [gold['answer']]
    metric=TaTQAEmAndF1(); metric(gold,[str(x) for x in a],gold['scale'])
    assert metric.get_overall_metric()[:2]==(1,1)
attempt_rows=[row for name in expected for row in tatqa.read_rows(directory/'models'/name/'answers.jsonl')]
result={'status':'PASS','verified_at':datetime.now(timezone.utc).isoformat(),'run_id':args.run_id,
        'models':len(expected),'questions_per_model':200,'question_contexts':200,'scheduled_answers':7000,
        'latest_response_rows':len(predictions),'statuses':dict(counts),'gold_roundtrip':200,
        'recorded_attempt_rows':len(attempt_rows),'recorded_failed_attempts':sum(row.get('error') is not None for row in attempt_rows),
        'dataset_sha256':report['dataset']['dataset_sha256'],'contract_sha256':manifest['contract_sha256'],
        'report_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(root/'validation/tatqa-200/results-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
