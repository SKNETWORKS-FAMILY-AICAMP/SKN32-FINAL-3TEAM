import json,re,sys
sys.path.insert(0,'.')
exec(open('/sessions/'+__import__('os').environ.get('USER','')+'/survey/alt.py').read().split("def rowcalc(")[0]) if False else None
from app import claimscope as cs
def base(t): t=t.strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
V1 = re.compile(r'(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$')
CUR = ['예방','강화','증가','향상','감소','최소화','도움','촉진','차단','항산화','항균','회복','해소','치료','면역력','혈액순환','배출','무첨가','무첨','NO','No','free','FREE','프리','무농약','유기농','친환경','천연','GMO','방부제','항생제','트랜스지방','칼로리','전문','대표','프리미엄','연구소','연구','개발','획득','돌파','전문의','피부과','FDA','시험','안전한','안전성','안심','풍부한','듬뿍','가득','ZERO','zero']
LC=re.compile('|'.join(sorted(map(re.escape,CUR),key=len,reverse=True))); NUMX=re.compile(r'\d+(\.\d+)?\s*(배|회|위)')
g=lambda t: cs.claim_guard(t) or (base(t) and bool(LC.search(t) or NUMX.search(t) or V1.search(t.strip())))
import collections
for name in ['dev','gpt213','cautionunk']:
    rows=json.load(open(f'build/eval/pg_B1022_{name}_V7.json',encoding='utf-8'))['rows']
    hit=collections.Counter(); ex=[]
    for p in rows:
        for s in p['sents']:
            if s['floor'] and not cs.claim_guard(s['text']) and g(s['text']):
                m=LC.search(s['text']) or NUMX.search(s['text']); w=m.group(0) if m else 'V1'
                if p['gold']=='위반': hit[w]+=1
                else: ex.append((p['gold'],w,s['text'][:45]))
    print('##',name,'위반에서 연 낱말',hit.most_common(30))
    for e in ex: print('   ',e)
