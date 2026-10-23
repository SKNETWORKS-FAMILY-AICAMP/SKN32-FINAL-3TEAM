"""(ㄴ) 동작 · 상태 명사 끝 — 「X하 · X되 · X시키」가 코퍼스에 나오는 명사로 문장이 끝나면 개조식 서술로 본다."""
import json,re,sys,collections,csv,random,os
sys.path.insert(0,'.')
sys.path.insert(0,os.path.expanduser('~/survey'))
from scripts_wil import wil
from app import claimscope as cs
from preprocess import devsplit, encoder_resplit as rsp
G=[json.loads(l) for l in open('data/derived/golden/golden.jsonl',encoding='utf-8') if l.strip()]
dev=set(devsplit.dev_ids(G)); plan=rsp.plan(G)
design=[r['text'] for r in G if r['id'] not in dev and (r.get('split')=='train' or plan.get(r['id'])==rsp.TRAIN)]
law=[json.loads(l)['text'] for l in open('data/derived/chunks.jsonl',encoding='utf-8') if l.strip()]
N=list(csv.DictReader(open('build/legit/ksr_review900_20261011.csv',encoding='utf-8-sig')))
LL=[r for r in N if r['판독(사람)'].strip()=='적법' and not r['애매표시'].strip()]
hold=set()
for c in ['화장품','식품','건기식']:
    k=sorted({r['제품종류'] for r in LL if r['품목']==c}); hold|={(c,x) for x in random.Random(42).sample(k,5)}
n9=[r['text'] for r in N if (r['품목'],r['제품종류']) not in hold]
corpus=law+design+n9
SUF=r'(하|되|시키|해|돼|했|됐|한|된|할|될|함|됨|하여|되어)'
MINC=int(sys.argv[1]) if len(sys.argv)>1 else 2
cnt=collections.Counter()
for t in corpus:
    for m in re.finditer(r'(?<![가-힣])([가-힣]{2,4})'+SUF+r'(?=[^가-힣]|$|[가-힣])',t):
        cnt[m.group(1)]+=1
VN={w for w,c in cnt.items() if c>=MINC}
print('코퍼스 문장',len(corpus),'동작·상태 명사',len(VN),'(최소',MINC,'회)')
def vnend(t):
    t=re.sub(r'[\s.!?~·,\'"”’)\]]+$','',t.strip())
    m=re.search(r'([가-힣]+)$',t)
    if not m: return None
    w=m.group(1)
    for L in range(min(4,len(w)),1,-1):
        if w[-L:] in VN: return w[-L:]
    return None
def base(t): t=t.strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
V1=re.compile(r'(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$')
gV0=lambda t: cs.claim_guard(t)
gVN=lambda t: gV0(t) or (base(t) and vnend(t) is not None)
gVN1=lambda t: gVN(t) or (base(t) and bool(V1.search(t.strip())))
H={'V0':(gV0,gV0),'V1 · 분리':(lambda t: gV0(t) or (base(t) and bool(V1.search(t.strip()))),gV0),'(ㄴ) · 분리':(gVN,gV0),"(라′) (ㄴ)+V1 · 분리":(gVN1,gV0),"(라′) 분리 없음":(gVN1,gVN1)}
def rowcalc(p,gf,gc):
    floor=any(s['floor'] and gf(s['text']) for s in p['sents'])
    ty=set()
    for s in p['sents']:
        if s['conf_types'] and (not s['enc_judged'] or gc(s['text'])): ty|=set(s['conf_types'])
    return floor,bool(ty),bool(ty&set(p['labels']))
sets=[x for x in ['dev','gpt213','caution','cautionunk','m171','fnclty','n900x','gptfact'] if os.path.exists(f'build/eval/pg_B1022_{x}_V7.json')]
for name in sets:
    rows=json.load(open(f'build/eval/pg_B1022_{name}_V7.json',encoding='utf-8'))['rows']
    n=collections.Counter(p['gold'] for p in rows); gs=sorted(n,key=lambda g:('위반','적법','모호').index(g) if g in ('위반','적법','모호') else 9)
    print(f'\n### {name}',dict(n))
    for hn,(gf,gc) in H.items():
        fl=collections.Counter();cf=collections.Counter();ty=collections.Counter()
        for p in rows:
            f,c,t=rowcalc(p,gf,gc); fl[p['gold']]+=f; cf[p['gold']]+=c; ty[p['gold']]+=t
        print(f"  {hn:22s} 하한 "+' · '.join(f"{g} {fl[g]}" for g in gs)+" | 확정 "+' · '.join(f"{g} {cf[g]}"+(f"({ty[g]})" if g=='위반' else '') for g in gs)+' | 적법쪽 하한 상한 '+' · '.join(f"{g} {wil(fl[g],n[g])}" for g in gs if g not in ('위반','모호','조건없음')))
    # 새로 열린 비위반 문장
    ex=[];hitw=collections.Counter()
    for p in rows:
        for s in p['sents']:
            t=s['text']
            if s['floor'] and not gV0(t) and gVN1(t):
                w=vnend(t) or 'V1'
                if p['gold']=='위반': hitw[w]+=1
                pass
    print('   위반에서 연 끝말',hitw.most_common(25))
    lg=[(p['gold'],vnend(s['text']) or 'V1',s['text'][:40]) for p in rows if p['gold'] not in ('위반','모호','조건없음') for s in p['sents'] if s['floor'] and not gV0(s['text']) and gVN1(s['text'])]
    print('   적법쪽 새로 열린',len(lg),lg[:14])
    for e in ex: print('    비위반',e)
