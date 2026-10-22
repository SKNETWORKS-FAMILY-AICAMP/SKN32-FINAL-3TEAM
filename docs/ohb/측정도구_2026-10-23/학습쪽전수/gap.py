import json,re,sys,collections
sys.path.insert(0,'.')
from app import claimscope as cs
G={json.loads(l)['id']:json.loads(l) for l in open('data/derived/golden/golden.jsonl',encoding='utf-8') if l.strip()}
d0={p['id']:p for p in json.load(open('build/eval/pg_B1022_dev_V0.json',encoding='utf-8'))['rows']}
d7=json.load(open('build/eval/pg_B1022_dev_V7.json',encoding='utf-8'))['rows']
def base(t): t=t.strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
gap=collections.defaultdict(list)
for p in d7:
    q=d0[p['id']]
    if p['enc_risk'] and not q['enc_risk']:
        # 열리는 문장들
        ss=[s for s in p['sents'] if s['floor'] and not cs.claim_guard(s['text'])]
        gap[p['gold']].append((p,ss))
for g,v in gap.items(): print(g,len(v))
def feat(name,fn):
    print('\n##',name)
    for g in ('위반','적법','모호'):
        c=collections.Counter()
        for p,ss in gap[g]:
            for s in ss[:1]: c[fn(p,s)]+=1
        print(g, c.most_common(14))
feat('provenance',lambda p,s:G[p['id']].get('provenance'))
feat('구역',lambda p,s:G[p['id']].get('구역'))
feat('조건',lambda p,s:G[p['id']].get('조건'))
feat('인코더1위',lambda p,s:s['enc_top'])
feat('사전보류후보 있음',lambda p,s:bool(s['hold_dict']))
feat('사전후보=인코더1위',lambda p,s:bool(s['enc_top'] and s['enc_top'] in s['hold_dict']))
feat('글자수',lambda p,s:min(len(s['text'].strip())//5*5,40))
feat('숫자포함',lambda p,s:bool(re.search(r'\d',s['text'])))
feat('쉼표포함',lambda p,s:',' in s['text'])
print('\n## 적법 38 전부')
for p,ss in gap['적법']: print(' ',G[p['id']].get('provenance'),G[p['id']].get('조건'),ss[0]['enc_top'],'|',ss[0]['text'][:50])
print('\n## 위반 예 40')
import random; random.seed(1)
for p,ss in random.sample(gap['위반'],40): print(' ',G[p['id']].get('provenance'),ss[0]['enc_top'],'|',ss[0]['text'][:50])
