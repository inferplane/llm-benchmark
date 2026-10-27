"""Read-only progress of frozen candidate collection."""
import json
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bench import run
root=Path(__file__).resolve().parents[2]
directory=root/'results/tatqa/tatqa-api-200-20261027'
manifest=json.loads((directory/'manifest.json').read_text())
counts=Counter(); models=[]
for model in manifest['contract']['models']:
    path=directory/'models'/model['name']/'answers.jsonl'
    rows=run.dedupe_latest(run.load_dataset([path]),lambda r:(r['model'],r['id'])) if path.exists() else []
    success=sum(r.get('error') is None for r in rows)
    failed=len(rows)-success
    counts['received']+=len(rows); counts['successful_requests']+=success; counts['request_failures']+=failed
    counts['completed_models']+=len(rows)==200
    if rows and len(rows)<200:
        models.append({'model':model['name'],'received':len(rows),'success':success,'failed':failed})
print(json.dumps({'scheduled':7000,**counts,'active_models':models},indent=2))
