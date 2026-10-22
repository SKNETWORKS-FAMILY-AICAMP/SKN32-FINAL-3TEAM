import re, collections, sys
sys.path.insert(0, '.')
exec(open(__import__('os').path.expanduser('~/survey/guard_survey.py'), encoding='utf-8').read().split("V1 = re.compile")[0])
from app import claimscope as cs
V1 = re.compile(r'(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$')
EFF = re.compile(r'(도움|예방|완화|개선|강화|억제|증가|증진|감소|향상|보습|조절|건강|해소|회복|치료|완치|효과|효능|촉진|방지|유지|관리|케어|진정|미백|탄력|재생|활력|면역|해독|디톡스|다이어트|감량|숙면|쾌변|쑥쑥|팡팡|튼튼|든든|매끈|촉촉|쫀쫀)\s*[.!?~]*\s*$')
INGR = re.compile(r'(함유|첨가|성분|원료)\s*[.!?~]*\s*$')
def base(t):
    t=(t or '').strip()
    return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
def g0(t): return cs.claim_guard(t)
EFD = re.compile(r'(도움|예방|완화|강화|억제|증가|증진|감소|향상|보습|조절|건강)\s*[.!?~]*\s*$')
C = {
 'Ed 효능명사끝(자료 목록만)': lambda t: g0(t) or (base(t) and bool(EFD.search(t.strip()))),
 'V0': g0,
 'V1 관형형': lambda t: g0(t) or (base(t) and bool(V1.search(t.strip()))),
 'E 효능명사끝': lambda t: g0(t) or (base(t) and bool(EFF.search(t.strip()))),
 'E+V1': lambda t: g0(t) or (base(t) and bool(EFF.search(t.strip()) or V1.search(t.strip()))),
 'I 성분끝': lambda t: g0(t) or (base(t) and bool(INGR.search(t.strip()))),
 'V7 조건없음': lambda t: base(t),
}
tab = collections.defaultdict(collections.Counter); flips=collections.defaultdict(list)
for r in rows:
    k=(r['src'],r['cls'])
    v0=g0(r['text'])
    for name,f in C.items():
        v=f(r['text']); tab[(name,k)]['참']+=v; tab[(name,k)]['n']+=1
        if v and not v0 and len(flips[(name,k)])<8: flips[(name,k)].append(r['text'][:45])
keys=sorted({k for _,k in tab})
print('후보 | ' + ' | '.join(f'{a}·{b}' for a,b in keys))
for name in C:
    print(name, '|', ' | '.join(f"{tab[(name,k)]['참']}/{tab[(name,k)]['n']} ({tab[(name,k)]['참']/tab[(name,k)]['n']:.0%})" for k in keys))
print()
for name in ['E 효능명사끝','I 성분끝','V1 관형형']:
    for k in keys:
        if flips[(name,k)]: print(name,k,flips[(name,k)])
