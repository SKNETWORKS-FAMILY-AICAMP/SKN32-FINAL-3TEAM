import json,sys
sys.path.insert(0,'.')
from app import claimscope as cs
def base(t): t=t.strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
for name in ['gpt213','cautionunk','m171']:
    rows=json.load(open(f'build/eval/pg_B1022_{name}_V7.json',encoding='utf-8'))['rows']
    print('##',name)
    for p in rows:
        for s in p['sents']:
            if s['floor'] and not cs.claim_guard(s['text']): print('  ',s['enc_top'],'|',s['text'][:60])
