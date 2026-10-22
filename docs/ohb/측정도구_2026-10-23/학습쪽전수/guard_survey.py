"""학습 쪽 전수 — 주장 가드가 무엇을 막는가 (탐색 · 판정 아님 · dev/데이터 밖은 보지 않는다)."""
import csv, collections, json, random, re, sys
sys.path.insert(0, '.')
from app import claimscope as cs
from preprocess import devsplit, encoder_resplit as rsp

G = [json.loads(l) for l in open('data/derived/golden/golden.jsonl', encoding='utf-8') if l.strip()]
dev = set(devsplit.dev_ids(G))
plan = rsp.plan(G)
def design(r):
    if r['id'] in dev: return False
    if r.get('split') == 'train': return True
    return plan.get(r['id']) == rsp.TRAIN
gold = [r for r in G if design(r) and r.get('unit') == '문장']
def gcls(r):
    c = r.get('조건')
    return '위반' if c in ('A','B','C') else '적법' if c in ('D','L') else '모호' if c == 'M' else '조건없음'

rows = [{'src': 'golden', 'cls': gcls(r), 'text': r['text'], 'style': '', 'prov': r.get('provenance')} for r in gold]

N = list(csv.DictReader(open('build/legit/ksr_review900_20261011.csv', encoding='utf-8-sig')))
L = [r for r in N if r['판독(사람)'].strip() == '적법' and not r['애매표시'].strip()]
hold = set()
for c in ['화장품', '식품', '건기식']:
    kinds = sorted({r['제품종류'] for r in L if r['품목'] == c})
    hold |= {(c, k) for k in random.Random(42).sample(kinds, 5)}
n_design = [r for r in N if (r['품목'], r['제품종류']) not in hold]
for r in n_design:
    k = r['판독(사람)'].strip()
    rows.append({'src': 'n900', 'cls': '적법' if k.startswith('적법') else '조건부', 'text': r['text'], 'style': r['문체'], 'prov': k})

V1 = re.compile(r'(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$')
def why(t):
    t = (t or '').strip()
    if not t: return '빈글자'
    if cs.is_caution(t): return '주의'
    if cs.is_veto(t): return '거부'
    if cs.PREDICATE.search(t): return '참·서술어'
    if cs.AD_CUE.search(t): return '참·표지'
    return '막힘·관형형끝' if V1.search(t) else '막힘·명사끝'
def tail(t):
    t = re.sub(r'[\s.!?~·,]+$', '', (t or '').strip())
    m = re.search(r'([가-힣A-Za-z0-9%]+)$', t)
    w = m.group(1) if m else t[-2:]
    return w[-2:] if len(w) >= 2 else w

out = collections.defaultdict(collections.Counter)
tails = collections.defaultdict(collections.Counter)
style = collections.defaultdict(collections.Counter)
ex = collections.defaultdict(list)
for r in rows:
    k = (r['src'], r['cls']); w = why(r['text'])
    out[k][w] += 1; out[k]['_n'] += 1
    if w.startswith('막힘'):
        tails[k][tail(r['text'])] += 1
        if len(ex[(k, w)]) < 6: ex[(k, w)].append(r['text'][:50])
    if r['src'] == 'n900': style[(r['cls'], r['style'])][w] += 1

print('설계 묶음 — golden', len(gold), '(dev', len(dev), '제외)', '· n900', len(n_design), '(떼어 둔 제품', len(hold), '종 제외)')
cols = ['참·서술어', '참·표지', '막힘·관형형끝', '막힘·명사끝', '주의', '거부']
print('묶음 | 행 | ' + ' | '.join(cols))
for k in sorted(out):
    c = out[k]; n = c['_n']
    print(f"{k[0]}·{k[1]} | {n} | " + ' | '.join(f"{c[x]} ({c[x]/n:.0%})" for x in cols))
print('\n# 정상카피 900 문체별 (설계 쪽)')
for k in sorted(style):
    c = style[k]; n = sum(c.values())
    print(f"{k[0]}·{k[1]} | {n} | " + ' | '.join(f"{c[x]}" for x in cols))
print('\n# 막힌 문장의 끝 두 글자 상위')
for k in sorted(tails):
    print(k, tails[k].most_common(25))
print('\n# 예')
for (k, w), v in sorted(ex.items()):
    print(k, w, v)
