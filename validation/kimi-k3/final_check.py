"""Read-only real-result checks; run after both reports exist. No model calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import json
from decimal import Decimal
from datetime import datetime, timezone
from bench import kimi_benchmark as k, kimi_observed as observed, finqa, report, run


def check():
    cfg = k.model_config()
    outputs = {}
    for label, path, rebuild, observations, money_key in [
        ('qa', finqa.REPORTS/f'{k.QA_RUN}.json', k.qa_comparison,
         finqa.RESULTS/k.QA_RUN/'answers.jsonl', 'estimated_cost_usd'),
        ('translation', report.DOCS_RESULTS_DIR/f'{k.TRANSLATION_COMPARISON}.json', observed.comparison,
         k.translation_folder()/'translations.jsonl', 'cost_total_usd'),
    ]:
        published = json.loads(path.read_text())
        assert published == rebuild(), label
        raw = finqa.read_rows(observations)
        latest = run.dedupe_latest(raw, lambda r: (r['model'], r['id']))
        assert len(latest) == (20 if label == 'qa' else 3300)
        assert all(r['model'] == k.NAME for r in latest)
        usable = [r for r in latest if r.get('error') is None and r.get('output_text')]
        if label == 'qa':
            assert len(usable) == 20
        model = next(m for m in published['models'] if m['name'] == k.NAME)
        total = Decimal(0)
        counts = {}
        for field, price in [('tokens_in','price_in'),('tokens_out','price_out'),
                             ('cache_read_tokens','price_cache_read'),('cache_write_tokens','price_cache_write')]:
            counts[field] = sum(r.get(field, 0) for r in usable)
            total += Decimal(counts[field])*Decimal(str(cfg[price]))/Decimal(1_000_000)
        # Display uses binary-float rounding to 4 decimals. Independent decimal
        # arithmetic must lie within half that display unit, not a new fee policy.
        displayed = Decimal(str(model['aggregate'][money_key]))
        assert abs(displayed-total) <= Decimal('.00005000001'), (label, total, displayed)
        assert model['aggregate']['cache_read_tokens'] == counts['cache_read_tokens']
        assert model['aggregate']['cache_write_tokens'] == counts['cache_write_tokens']
        outputs[label] = {'rows_on_disk':len(raw),'retained':len(latest),'usable_outputs':len(usable),
                          'recorded_failed_attempts':sum(r.get('error') is not None for r in raw),
                          'usage':counts,'exact_configured_cost_usd':str(total),'displayed_cost_usd':str(displayed),
                          'report_sha256':k.sha(path),'source_sha256':k.sha(observations)}
    print(json.dumps(outputs,ensure_ascii=False,indent=2))
    finqa.write_json(k.CONTRACT.parent/'final-verification.json',{
        'verified_at':datetime.now(timezone.utc).isoformat(),'checks':outputs,
        'scope':'Real retained outputs only; full source/contract/grade coverage and parent snapshot preservation checked by exact rebuilding; fee arithmetic independently checked with Decimal.'})
    return outputs

if __name__=='__main__':check()
