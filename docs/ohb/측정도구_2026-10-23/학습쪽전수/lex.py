import json,re,sys,collections,math,random,csv
sys.path.insert(0,'.')
from app import claimscope as cs
from preprocess import devsplit, encoder_resplit as rsp
G=[json.loads(l) for l in open('data/derived/golden/golden.jsonl',encoding='utf-8') if l.strip()]
dev=set(devsplit.dev_ids(G)); plan=rsp.plan(G)
def design(r): return r['id'] not in dev and (r.get('split')=='train' or plan.get(r['id'])==rsp.TRAIN) and r.get('unit')=='문장'
def base(t): t=(t or '').strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
blocked=lambda t: base(t) and not cs.claim_guard(t)
V=[r['text'] for r in G if design(r) and r.get('조건') in ('A','B','C') and blocked(r['text'])]
Lg=[r['text'] for r in G if design(r) and r.get('조건') in ('D','L') and blocked(r['text'])]
N=list(csv.DictReader(open('build/legit/ksr_review900_20261011.csv',encoding='utf-8-sig')))
LL=[r for r in N if r['판독(사람)'].strip()=='적법' and not r['애매표시'].strip()]
hold=set()
for c in ['화장품','식품','건기식']:
    k=sorted({r['제품종류'] for r in LL if r['품목']==c}); hold|={(c,x) for x in random.Random(42).sample(k,5)}
Ln=[r['text'] for r in N if (r['품목'],r['제품종류']) not in hold and r['판독(사람)'].strip().startswith('적법') and blocked(r['text'])]
L=Lg+Ln
JOSA=re.compile(r'(으로|에서|에게|까지|부터|처럼|보다|이나|으로써|을|를|이|가|은|는|의|에|로|과|와|도|만)$')
def toks(t):
    out=set()
    for w in re.findall(r'[가-힣A-Za-z0-9%]+',t):
        out.add(w); s=JOSA.sub('',w)
        if len(s)>=2: out.add(s)
    return out
cv=collections.Counter(); cl=collections.Counter()
for t in V: cv.update(toks(t))
for t in L: cl.update(toks(t))
print('막힌 위반',len(V),'막힌 적법',len(L),'(골든',len(Lg),'· 900',len(Ln),')')
res=[]
for w,a in cv.items():
    b=cl[w]
    if a<4 or len(w)<2: continue
    lo=math.log((a+0.5)/len(V))-math.log((b+0.5)/len(L))
    res.append((lo,a,b,w))
res.sort(reverse=True)
for lo,a,b,w in res[:120]: print(f'{w}:{a}/{b}:{lo:.1f}',end='  ')
print()
json.dump([w for lo,a,b,w in res if b==0 and a>=4 and lo>=1.5],open('/tmp/lexcand.json','w'),ensure_ascii=False)
