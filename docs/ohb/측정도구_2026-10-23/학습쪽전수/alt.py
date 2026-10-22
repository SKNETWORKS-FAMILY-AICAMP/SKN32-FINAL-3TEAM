import json,re,sys,collections
sys.path.insert(0,'.')
from app import claimscope as cs
from scripts_wil import wil
def base(t): t=t.strip(); return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)
#: 거부 가드 보강 후보 (dev 적법 38 을 보고 만든 꼴 — dev 는 고른 자리다)
XV_PRICE = re.compile(r'\d[\d,]*\s*(만|억|천)\s*원')
XV_TARGET = re.compile(r'(분|분들)\s*[.!?~]*\s*$')
XV_INFO = re.compile(r'(제조원|판매원|유통전문판매원|제조사|판매처)\s*[:：]?')
def short(t): t=t.strip(); return (' ' not in t) and len(t)<=3
V1 = re.compile(r'(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$')
EFD = re.compile(r'(도움|예방|완화|강화|억제|증가|증진|감소|향상|보습|조절|건강)\s*[.!?~]*\s*$')
def xveto(t, short_on=True):
    t=t.strip()
    return bool(XV_PRICE.search(t) or XV_TARGET.search(t) or XV_INFO.search(t) or (short_on and short(t)))
G={
 'V0': lambda t: cs.claim_guard(t),
 'V1': lambda t: cs.claim_guard(t) or (base(t) and bool(V1.search(t.strip()))),
 'V7': base,
 'V7+X': lambda t: base(t) and not xveto(t),
 'V7+X(짧은낱말 뺌)': lambda t: base(t) and not xveto(t,False),
 'V0∨(V7+X 중 4자↑)': lambda t: cs.claim_guard(t) or (base(t) and not xveto(t) and len(t.strip())>=4),
}
def rowcalc(p,guard):
    floor=any(s['floor'] and guard(s['text']) for s in p['sents'])
    ty=set()
    for s in p['sents']:
        if s['conf_types'] and (not s['enc_judged'] or guard(s['text'])): ty|=set(s['conf_types'])
    return floor,bool(ty),bool(ty&set(p['labels']))
for name in ['dev','gpt213','caution','cautionunk','m171']:
    rows=json.load(open(f'build/eval/pg_B1022_{name}_V7.json',encoding='utf-8'))['rows']
    n=collections.Counter(p['gold'] for p in rows)
    print(f'\n### {name} 분모',dict(n))
    for gn,g in G.items():
        fl=collections.Counter();cf=collections.Counter();ty=collections.Counter()
        for p in rows:
            f,c,t=rowcalc(p,g); fl[p['gold']]+=f; cf[p['gold']]+=c; ty[p['gold']]+=t
        if name=='dev':
            print(f"  {gn:18s} 하한 위반 {fl['위반']} 적법 {fl['적법']} 모호 {fl['모호']} | 확정 위반 {cf['위반']}({ty['위반']}) 적법 {cf['적법']} 모호 {cf['모호']} | 적법 하한 상한 {wil(fl['적법'],n['적법'])} 확정 상한 {wil(cf['적법'],n['적법'])}")
        else:
            print(f"  {gn:18s} 적법 하한 {fl['적법']} ({wil(fl['적법'],n['적법'])}) 확정 {cf['적법']} ({wil(cf['적법'],n['적법'])})")

print('\n\n======== 주장 낱말 넓히기 ========')
auto=json.load(open('/tmp/lexcand.json'))
CUR = ['예방','강화','증가','향상','감소','최소화','도움','촉진','차단','항산화','항균','회복','해소','치료','면역력','혈액순환','배출',
       '무첨가','무첨','NO','No','free','FREE','프리','무농약','유기농','친환경','천연','GMO','방부제','항생제','트랜스지방','칼로리',
       '전문','대표','프리미엄','연구소','연구','개발','획득','돌파','전문의','피부과','FDA','시험','안전한','안전성','안심','풍부한','듬뿍','가득','ZERO','zero']
def lexre(ws): return re.compile('|'.join(sorted(map(re.escape,ws),key=len,reverse=True)))
LA=lexre(auto); LC=lexre(CUR); NUMX=re.compile(r'\d+(\.\d+)?\s*(배|회|위)')
H={
 'V0':lambda t: cs.claim_guard(t),
 'L자동(학습쪽 b=0 전부)':lambda t: cs.claim_guard(t) or (base(t) and bool(LA.search(t))),
 'L정리(일반 낱말만)':lambda t: cs.claim_guard(t) or (base(t) and bool(LC.search(t) or NUMX.search(t))),
 'L정리+V1':lambda t: cs.claim_guard(t) or (base(t) and bool(LC.search(t) or NUMX.search(t) or V1.search(t.strip()))),
}
print('자동 목록',len(auto),'낱말')
def rowcalc2(p,gfloor,gconf):
    floor=any(s['floor'] and gfloor(s['text']) for s in p['sents'])
    ty=set()
    for s in p['sents']:
        if s['conf_types'] and (not s['enc_judged'] or gconf(s['text'])): ty|=set(s['conf_types'])
    return floor,bool(ty),bool(ty&set(p['labels']))
import itertools
for name in ['dev','gpt213','caution','cautionunk','m171']:
    rows=json.load(open(f'build/eval/pg_B1022_{name}_V7.json',encoding='utf-8'))['rows']
    n=collections.Counter(p['gold'] for p in rows)
    print(f'\n### {name}')
    for (hn,h),split in itertools.product(H.items(),(False,True)):
        if hn=='V0' and split: continue
        gc = H['V0'] if split else h
        fl=collections.Counter();cf=collections.Counter();ty=collections.Counter()
        for p in rows:
            f,c,t=rowcalc2(p,h,gc); fl[p['gold']]+=f; cf[p['gold']]+=c; ty[p['gold']]+=t
        lab=hn+(' [확정은 V0]' if split else '')
        if name=='dev':
            print(f"  {lab:34s} 하한 위반 {fl['위반']} 적법 {fl['적법']} 모호 {fl['모호']} | 확정 {cf['위반']}({ty['위반']}) 적법 {cf['적법']} | 상한 하한 {wil(fl['적법'],n['적법'])} 확정 {wil(cf['적법'],n['적법'])}")
        else:
            print(f"  {lab:34s} 적법 하한 {fl['적법']} ({wil(fl['적법'],n['적법'])}) 확정 {cf['적법']}")
