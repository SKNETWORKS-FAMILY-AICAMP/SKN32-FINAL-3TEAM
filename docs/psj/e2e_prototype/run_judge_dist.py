"""판정 로직(1·2단계) 분포 — 🔄 2026-10-06 main `ebb3f10` 맞춤판 (박수진)

인코더를 판정 로직에 **붙였을 때** 무엇이 달라지는지 잰다. 같은 행을 「규칙만」과 「규칙 + 인코더」로 두 번 판정해 나란히 낸다.

  # ① 저장해 둔 행별 확률로 (모델을 다시 돌리지 않는다 · 권장)
  uv run python docs\\psj\\e2e_prototype\\run_judge_dist.py --model <모델 zip 또는 폴더> --probs-csv <…_dev행별확률.csv>
  # ② 모델을 직접 돌려서 (zip 이면 저장소 밖 ~/copylane_local/models 에 한 번 풀어 쓴다)
  uv run python docs\\psj\\e2e_prototype\\run_judge_dist.py --model <모델 zip 또는 폴더>
  # ③ 최종 1회 (봉인 평가셋)
  uv run python docs\\psj\\e2e_prototype\\run_judge_dist.py --model <…> --probs-csv <…_행별확률.csv> --split test --final

🔄 2026-10-06 — 바뀐 것
  · 판정은 판정 그래프의 함수 + 인코더 층이다(`judge_stage2.py`). 여기는 행을 고르고 세기만 한다.
  · **확정 8종**(D-321) 기준 버킷 — 새 2종(`부당_비교광고` · `비방광고`)은 채점 행이다. 편입 대기(`기능성화장품_오인`)만 달린 행은 `대기`.
  · `--probs-csv` — 노트북이 저장한 행별 확률(id · p_<유형>)을 골든과 id 로 붙인다. 문턱은 `--model` 의 `label_scheme.json` 것이다.
  · `--conditional` — 골든 `품목` 을 제품 정보로 넘긴다(품목을 아는 행만 · D-306). 기본은 품목 미확정(무조건부).
  · 팀장 평가 도구(`scripts/eval_graph.py`)의 `predict` · `summarize` · `report` 로 같은 표를 낸다 — 규칙 판정기 기준선과 **같은 자**다.
    🚨 이 스크립트에는 조문 검색 · 위험도 하한이 없다(DB 없음). 그래서 종착은 대부분 보류이고 호 단위 수는 사전 인용에서만 나온다.

🔴 D-175 — 평가로 봉인된 것(test_sentence)은 **판정 규칙의 설계 재료로 쓰지 않는다.**
   · 규칙 · 여유 구간(`QUIET_MARGIN`) · 합의 여부(`--dict-stands`)를 고르는 것은 **dev** 다.
   · `--split test` 는 `--final` 없이는 멈춘다. 설정을 정한 뒤 **한 번** 잰다 — 그 결과로 규칙을 다시 고치지 않는다.
🔴 D-249 ⑥ — 결과 파일은 **저장소 밖**에 쓰고(기본 ~/copylane_local/eval/) 문장 원문은 넣지 않는다. `--with-text` 는 저장소 밖일 때만.
🔴 D-269 — 보류율을 **사유별로** 함께 보고한다.
🔴 D-272 개정 — 거래 조건(가격 · 할인 · 환불 · 배송) D 행은 `판정 대상 아님`을 기대하지 않는다 → 버킷 `D_거래` 로 따로 센다.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import tempfile
import zipfile
from collections import Counter, defaultdict

from judge_stage1 import (QUIET_MARGIN, REPO, BANNED_TERMS_PATH, load_banned_terms, load_encoder, load_scheme,
                          predict_label_probs_batch, resolve_model_dir, stage1_signals)
from judge_stage2 import stage2_judge
from app import graph as g
from app.contracts import Category
from scripts import eval_graph as _eg  # 🆕 10-10 — 제품 정보는 평가 도구의 한 곳에서 (`product_of`)
from preprocess.golden import lawful_kind  # 적법 문장 판별은 한 곳 (D-301 · D-99)

GOLDEN = os.path.join(REPO, "data", "derived", "golden", "golden.jsonl")
OUT_DIR = os.path.join(os.path.expanduser("~"), "copylane_local", "eval")
#: 기존 6종 — dev 를 떼는 층화 기준이다(인코더 노트북 v8 ~ v8.2 섹션 4 와 같다 · 8종으로 넓히지 않았다)
CONFIRMED6 = ["질병_예방치료_표방", "건강기능식품_오인", "의약품_오인", "거짓_과장", "소비자_기만", "후기_체험기_기만"]
CONFIRMED8 = CONFIRMED6 + ["부당_비교광고", "비방광고"]  # D-321
WAITING = {"기능성화장품_오인"}  # 편입 대기 (D-321)
DEV_FRAC, DEV_SEED = 0.15, 42  # 인코더 노트북 섹션 4 와 같은 값 — 바꾸면 둘 다 바꾼다
#: 거래 조건 문장 표지 (D-272 개정) — 버킷을 가르는 데만 쓴다
TRADE = re.compile(r"가격|할인|적립|쿠폰|무료\s*배송|배송|환불|반품|교환|\d+\s*원|만원|1\+1|2\+1|특가|최저가")
EXPECT = {"scored": "위반 · 보류(정답 유형)", "pending": "위반 · 보류", "대기": "참고 — 편입 대기 유형만 (D-321)",
          "M": "보류 (채점 안 함)", "D": "판정 대상 아님 (적법 · 주장 없음 · D-301)", "D_기타": "참고 — 적법 확인 아님 (D-301)",
          "D_거래": "보류 (표시광고법 대상)", "neg": "통과 (조건 L)"}
ORDER = ["scored", "pending", "대기", "M", "D", "D_기타", "D_거래", "neg"]
#: `hold:품목만` — 사전도 인코더도 조용한데 **품목을 몰라서** 보류인 문장(D-319 ②). 품목을 알면 통과가 되는 자리다
STATES = ["confirmed:위반", "no_basis", "hold", "hold:품목만", "confirmed:신호없음", "판정대상아님"]
PASS_STATES = ("confirmed:신호없음", "판정대상아님")
QUIET_STATES = PASS_STATES + ("hold:품목만",)


def bucket(r):
    """팀장 채점 기준(10-01) — C·A·B = 양성 · L = 음성 · D = 별도 지표 · M = 채점 안 함. 유형은 확정 8종(D-321).

    조건이 M · D 면 라벨보다 먼저 가른다(채점 밖). L 인데 라벨이 붙어 있으면 데이터가 어긋난 것이라 멈춘다.
    조건 D 는 둘이다(D-301) — 원천이 **승인한 형태**(`gf:`)만 「주장 없는 적법 문장」(`D`)이고, 그 밖은 적법이라 확인된 적이 없어 `D_기타`(참고)다.
    """
    cond, labels = r.get("조건"), r.get("labels") or []
    if cond == "M":
        return "M"
    if cond == "D":
        if TRADE.search(r["text"]):
            return "D_거래"
        return "D" if lawful_kind({**r, "labels": labels}) == "주장없음" else "D_기타"
    if cond == "L":
        if labels:
            raise SystemExit(f"🔴 조건 L(적법)인데 라벨이 있다 — {r['id']} · {labels}")
        return "neg"
    if any(x in CONFIRMED8 for x in labels):
        return "scored"
    if labels:
        return "대기"
    return "pending" if cond in ("C", "B", "A") else "neg"


def wilson(k, n, z=1.96):
    """D-40 — 비율의 95% 구간. n=0 이면 (nan, nan)."""
    if not n:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(k, n):
    return f"{k:5d}/{n:<5d} {k / n:6.1%} [{wilson(k, n)[0]:.1%}~{wilson(k, n)[1]:.1%}]" if n else "    —"


def state_of(v):
    """판정 하나(`judge_stage2._view` 모양) → 표의 칸."""
    if v["verdict"] != "confirmed":
        return "hold:품목만" if v.get("pass_blocked") else v["verdict"]
    return "confirmed:위반" if v["violations"] else ("판정대상아님" if v.get("not_claim") else "confirmed:신호없음")


def group_key(r):
    rid = r["id"]
    return rid.split(":", 2)[2] if rid.startswith("inj:") else rid.split("#")[0]


def train_role(r):
    """인코더 노트북 v8 `train_role` 과 같다 (D-296 개정 2) — M = 뺀다 · D · L = 음성 · C·A·B · 조건 없음 = 유형이 양성."""
    c = r.get("조건")
    if c == "M":
        return "drop_M"
    if c in ("D", "L"):
        return "neg"
    if r.get("labels"):
        return "pos"
    return "pos_untyped" if c in ("C", "A", "B") else "neg"


def dev_rows(golden):
    """인코더 노트북 **v8 ~ v8.2** 섹션 4 와 같은 묶음 단위 층화 dev — 같은 골든이면 **같은 행**이 나온다.

    · 모집단 = train 에서 조건 M 을 뺀 전부 · dev 채점 행 = 이유 구역 · 낱말 행 · 유형 없는 C·A·B 를 뺀 문장 (D-234)
    · 층화는 기존 6종으로 한다(8종으로 넓히지 않았다 — 2차와 dev 를 잇는다)
    🔴 노트북의 DEV_FRAC · DEV_SEED · 규칙을 바꾸면 여기도 같이 바꾼다. `--probs-csv` 를 주면 CSV 의 id 와 대조해 알린다.
    🚨 v8.3 · v9 (dev 를 실제 문구만으로 다시 뗀 판)의 dev 와는 **다른 행**이다 — 그 모델은 `--probs-csv` 로 잰다.
    """
    use = []
    for r in golden:
        if r["split"] != "train":
            continue
        role = train_role(r)
        if role != "drop_M":
            use.append({**r, "role": role, "labels": list(r.get("labels") or []) if role == "pos" else []})
    devable = lambda r: (not (r.get("provenance") == "ftc_decisions_body" and r.get("구역") == "이유")
                         and r.get("unit") != "낱말" and r["role"] != "pos_untyped")
    groups = defaultdict(list)
    for r in use:
        groups[group_key(r)].append(r)
    gkeys = sorted(groups)
    random.Random(DEV_SEED).shuffle(gkeys)
    lab = lambda r: [x for x in r["labels"] if x in CONFIRMED6]
    pos_total = Counter(x for r in use if devable(r) for x in lab(r))
    target = {x: max(1, math.ceil(DEV_FRAC * pos_total[x])) for x in CONFIRMED6}
    neg_groups = {k for k in gkeys if any(devable(r) and not r["labels"] for r in groups[k])}
    neg_target = math.ceil(DEV_FRAC * len(neg_groups))
    got, neg_got, dev = Counter(), 0, set()
    for k in gkeys:
        labs = Counter(x for r in groups[k] if devable(r) for x in lab(r))
        is_neg = k in neg_groups and not labs
        if any(got[x] < target[x] for x in labs) or (is_neg and neg_got < neg_target):
            dev.add(k)
            got.update(labs)
            neg_got += is_neg
    return [r for k in dev for r in groups[k] if devable(r)]


def scheme_dir(path):
    """`--probs-csv` 때의 모델 자리 — 폴더 또는 **zip**. zip 이면 `label_scheme.json` · `config.json` 만 임시 폴더에 꺼낸다(가중치는 안 읽는다)."""
    if not path or not path.lower().endswith(".zip"):
        return resolve_model_dir(path)
    if not os.path.exists(path):
        raise SystemExit(f"🔴 모델 zip 이 없다: {path}")
    out = tempfile.mkdtemp(prefix="copylane_scheme_")
    with zipfile.ZipFile(path) as z:
        names = {os.path.basename(n): n for n in z.namelist() if os.path.basename(n) in ("label_scheme.json", "config.json")}
        if "label_scheme.json" not in names:
            raise SystemExit(f"🔴 zip 안에 label_scheme.json 이 없다: {path}")
        for base, member in names.items():
            with open(os.path.join(out, base), "wb") as f:
                f.write(z.read(member))
    return out


def read_probs_csv(path, labels):
    """노트북이 저장한 행별 확률 — `id` · `p_<유형>`. 🔴 유형 칸이 하나라도 빠지면 멈춘다 (D-220)."""
    if not os.path.exists(path):
        raise SystemExit(f"🔴 행별 확률 파일이 없다: {path}")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"🔴 행별 확률 파일이 비었다: {path}")
    missing = [x for x in ["id"] + [f"p_{x}" for x in labels] if x not in rows[0]]
    if missing:
        raise SystemExit(f"🔴 행별 확률 파일에 칸이 없다: {missing} — 이 모델(`--model`)이 낸 파일이 맞는지 본다")
    return [r["id"] for r in rows], {r["id"]: {x: float(r[f"p_{x}"]) for x in labels} for r in rows}


def extra_holdout(path, frac=0.2):
    """인코더 노트북 v7.4 섹션 4 와 같은 규칙으로 뗀 추가 파일 홀드아웃 — family 별 · id 순 · DEV_SEED 셔플 · 앞 frac."""
    if not os.path.exists(path):
        raise SystemExit(f"🔴 홀드아웃 파일이 없다: {path}")
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(x) for x in f if x.strip()]
    fam = defaultdict(list)
    for r in rows:
        fam[r.get("family", "-")].append(r)
    rng, hold = random.Random(DEV_SEED), []
    for _, rs in sorted(fam.items()):
        rs = sorted(rs, key=lambda r: r["id"])
        rng.shuffle(rs)
        hold += rs[:int(round(frac * len(rs)))]
    stem = os.path.splitext(os.path.basename(path))[0].replace("proto_", "")
    for r in hold:
        r.setdefault("labels", [])
        r["bucket"] = f"hold:{stem}"
    return hold, stem


def eval_file(path):
    """검증 전용 파일(실제 포장 문구 등)을 **전부** 버킷 `eval:<이름>` 으로 싣는다. 학습에 쓰지 않은 문장이어야 한다.

    .txt — 한 줄에 한 문장 · `[종류] 문장` · `#` 줄 무시 · `# 제품 …` 줄은 다음 줄들의 제품 묶음 표시
    .jsonl — {id, text, family?, product?} · 라벨이 없으면 D(주장 없는 문구)로 본다
    """
    if not os.path.exists(path):
        raise SystemExit(f"🔴 검증 파일이 없다: {path}")
    stem = os.path.splitext(os.path.basename(path))[0]
    rows, product = [], "-"
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(x) for x in f if x.strip()]
    else:
        with open(path, encoding="utf-8-sig") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line.startswith("#"):
                    m = re.match(r"^#\s*제품\s*(.+)$", line)
                    if m:
                        product = m.group(1).strip()
                    continue
                if not line:
                    continue
                m = re.match(r"^\[([^\]]+)\]\s*(.+)$", line)
                rows.append({"id": f"{stem}:{i + 1}", "text": (m.group(2) if m else line).strip(),
                             "family": m.group(1).strip() if m else "-", "product": product})
    seen, out = set(), []
    for r in rows:
        if r["text"] in seen:
            continue
        seen.add(r["text"])
        r.setdefault("labels", [])
        r.setdefault("조건", "D")
        r["bucket"] = f"eval:{stem}"
        out.append(r)
    return out, stem


def team_summary(dist, title):
    """팀장 기준 요약 — 위반은 「확정 · 근거없음 · 보류」로 나가고 통과는 「신호없음 · 판정대상아님」이다."""
    agg = defaultdict(Counter)
    for b, c in dist.items():
        agg[{"scored": "양성", "pending": "양성", "neg": "음성"}.get(b, b)].update(c)
    passed = lambda c: sum(c[s] for s in PASS_STATES)
    held = lambda c: c["hold"] + c["no_basis"] + c["hold:품목만"]
    quiet = lambda c: f"(품목만 알면 통과 {c['hold:품목만']})" if c["hold:품목만"] else ""
    print(f"\n[{title} · C·A·B 양성 · L 음성 · D 별도 · M 채점 안 함 · 적법 문장은 L 과 D(gf:) 둘뿐 — D-301]")
    c = agg["양성"]
    n = sum(c.values())
    if n:
        print(f"  양성 (C·A·B)              위반 확정    {pct(c['confirmed:위반'], n)}")
        print(f"                            보류         {pct(held(c), n)}")
        print(f"                            놓침(통과)   {pct(passed(c), n)}   ← 낮을수록 좋다 {quiet(c)}")
    c = agg["음성"]
    n = sum(c.values())
    if n:
        print(f"  음성 (L)                  오판정(확정) {pct(c['confirmed:위반'], n)}   ← 낮을수록 좋다")
        print(f"                            통과         {pct(passed(c), n)}   ← 높을수록 좋다 {quiet(c)}")
    c = agg["D"]
    n = sum(c.values())
    if n:
        print(f"  D (적법 · 주장 없음)      통과         {pct(passed(c), n)}   ← 높을수록 좋다 (그중 판정대상아님 {c['판정대상아님']}) {quiet(c)}")
        print(f"                            오판정(확정) {pct(c['confirmed:위반'], n)}   ← 낮을수록 좋다")
    c = agg["D_기타"]
    n = sum(c.values())
    if n:
        print(f"  D_기타 (참고 · 적법 아님)  통과         {pct(passed(c), n)} {quiet(c)}")
        print(f"                            위반 확정    {pct(c['confirmed:위반'], n)}   ← 오답으로 세지 않는다 (D-301)")
    c = agg["D_거래"]
    n = sum(c.values())
    if n:
        print(f"  D_거래 (참고 · D-272 개정) 판정대상아님 {pct(c['판정대상아님'], n)}   ← 0 이어야 한다(not_claim 금지)")
    c = agg["M"]
    n = sum(c.values())
    if n:
        print(f"  M (참고 · 채점 안 함)      보류         {pct(held(c), n)}")


def headline(s):
    """평가 도구 요약(`eval_graph.summarize`)에서 한 줄 — 탐지 · 확정 재현율 · 적법 문장 · coverage."""
    d, law = s["detect"], s["lawful"]
    pos = d["positive"]
    sr = s["selective_risk"]
    return (f"탐지 재현율 {d['detected']}/{pos} {d['detected'] / pos:.1%}" if pos else "탐지 재현율 —") + \
           (f" · 확정 재현율 {d['confirmed']}/{pos} {d['confirmed'] / pos:.1%}" if pos else "") + \
           f" · 적법 문장에 위반 확정 {law['주장'][1]}/{law['주장'][0]} (주장) · {law['주장없음'][1]}/{law['주장없음'][0]} (주장 없음)" + \
           f" · coverage {s['coverage']:.1%} · selective risk {'-' if sr is None else f'{sr:.1%}'}" + \
           f" · 행 {s['class']}"


def type_table(rows, cand_rows, active):
    """유형별 인코더 후보 — **이 실행의 모든 행** 기준(위반 · M · D · L 을 다 분모에 넣는다). 판정 로직과 무관하게 인코더 후보만 본다.

    정밀도 = 후보가 선 행 중 그 유형이 정답인 비율. 결과보고서의 「유형 있는 위반 행 안」 정밀도와 다르다 — 여기는 적법 문장에 선 것도 틀린 것으로 센다.
    「어느 유형의 후보를 믿을 수 있나」를 dev 로 보는 표다. 🔴 test 에서는 진단으로만 읽고 이 표로 규칙 · 문턱을 고르지 않는다 (D-175).
    """
    keep = [(r, c) for r, c in zip(rows, cand_rows) if not r["bucket"].startswith(("hold:", "eval:"))]
    out = {}
    print(f"\n유형별 인코더 후보 — 이 실행의 모든 행 기준 (n={len(keep)}) · 판정 로직과 무관")
    print(f"  {'유형':12s} {'정답':>5s} {'후보':>5s} {'맞음':>5s} {'정밀도':>6s} {'재현율':>6s}   잘못 선 곳 — 다른 유형 위반 · 유형 없는 위반 · M · D(적법) · D_기타 · L")
    for t in active:
        right = lambda r: r["bucket"] == "scored" and t in (r.get("labels") or [])
        gold = sum(1 for r, _ in keep if right(r))
        fire = [(r, c) for r, c in keep if t in c]
        tp = sum(1 for r, _ in fire if right(r))
        w = Counter(r["bucket"] for r, _ in fire if not right(r))
        fmt = lambda k, n: f"{k / n:6.3f}" if n else "     —"
        mark = "  측정 불가(정답 30 미만 · D-40)" if gold < 30 else ""
        print(f"  {t[:12]:12s} {gold:5d} {len(fire):5d} {tp:5d} {fmt(tp, len(fire))} {fmt(tp, gold)}   "
              f"{w['scored']:4d} · {w['pending']:3d} · {w['M']:3d} · {w['D']:3d} · {w['D_기타']:3d} · {w['neg']:2d}{mark}")
        out[t] = {"gold": gold, "fired": len(fire), "tp": tp, "wrong_by_bucket": dict(w)}
    solo = Counter()
    for r, c in keep:
        if len(c) == 1:
            solo[(r["bucket"], c[0])] += 1
    top = Counter()
    for (b, t), v in solo.items():
        top[t] += v
    if top:
        t0 = top.most_common(1)[0][0]
        n_by = Counter(r["bucket"] for r, _ in keep)
        print(f"  후보가 「{t0}」 하나뿐인 행 — " + " · ".join(f"{b} {solo[(b, t0)]}/{n_by[b]}" for b in ("scored", "pending", "M", "D", "D_기타", "neg") if n_by[b]))
    return out


def timing(rows, tok, mdl, labels, book, th, cat_of, agree, margin, n):
    """추론 시간 — 문장 하나씩(배치 1) · 배치 16 · 판정 로직(1 · 2단계). 이 기기의 CPU 로 잰 값이다.

    🚨 배포 기기의 수가 아니다 — 판정 목표(p95 3초 · D-77)와 견줄 때는 배포 환경에서 다시 잰다. 여기 수는 「대략 어느 자릿수인가」를 보는 것이다.
    """
    import time

    import torch
    texts = [r["text"] for r in rows]
    lens = [len(tok(t)["input_ids"]) for t in texts]          # 특수 토큰 포함 · 학습은 128 에서 자른다
    lens_sorted = sorted(lens)
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
    print(f"\n[문장 길이 · 토큰] {len(texts)}행 — 중앙값 {q(lens_sorted, 0.5)} · p95 {q(lens_sorted, 0.95)} · 최대 {lens_sorted[-1]} · "
          f"128 초과 {sum(x > 128 for x in lens)}행 ({sum(x > 128 for x in lens) / len(lens):.1%}) — 넘는 부분은 잘려 인코더가 보지 못한다")
    sample = random.Random(0).sample(range(len(rows)), min(n, len(rows)))
    for i in sample[:3]:                                        # 예열
        predict_label_probs_batch([texts[i]], tok, mdl, labels)
    one, probs = [], {}
    for i in sample:
        t0 = time.perf_counter()
        probs[i] = predict_label_probs_batch([texts[i]], tok, mdl, labels)[0]
        one.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter()
    predict_label_probs_batch([texts[i] for i in sample], tok, mdl, labels, batch_size=16)
    batch_ms = (time.perf_counter() - t0) * 1000 / len(sample)
    judge = []
    for i in sample:
        t0 = time.perf_counter()
        stage2_judge(stage1_signals(texts[i], probs[i], book, th, margin=margin), category=cat_of(rows[i]), agree=agree)
        judge.append((time.perf_counter() - t0) * 1000)
    row = lambda name, xs: print(f"  {name:34s} 평균 {sum(xs) / len(xs):7.1f} ms · 중앙값 {q(sorted(xs), 0.5):7.1f} · p95 {q(sorted(xs), 0.95):7.1f} · 최대 {max(xs):7.1f}")
    print(f"\n[추론 시간] 표본 {len(sample)}문장 · CPU · torch 스레드 {torch.get_num_threads()}")
    row("인코더 — 문장 하나씩 (배치 1)", one)
    print(f"  {'인코더 — 배치 16 (문장당)':34s} 평균 {batch_ms:7.1f} ms")
    row("판정 로직 — 1 · 2단계 (인코더 제외)", judge)
    print("  🚨 이 기기의 CPU 로 잰 값이다 — 배포 환경에서 다시 잰다. 문서 한 건은 문장 수만큼 인코더가 돈다")
    print("     배치는 가장 긴 문장에 맞춰 채우므로(패딩) 짧은 문장이 많으면 CPU 에서는 하나씩 돌리는 것보다 빠르지 않을 수 있다")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="모델 폴더 또는 zip. zip 은 저장소 밖(~/copylane_local/models)에 풀어 쓴다 · `--probs-csv` 를 주면 label_scheme.json 만 읽는다")
    ap.add_argument("--probs-csv", default=None, help="노트북이 저장한 행별 확률 CSV (id · p_<유형>) — 모델을 돌리지 않고 이 확률로 판정한다")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--banned", default=BANNED_TERMS_PATH)
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--final", action="store_true", help="test 최종 측정 1회 — 결과로 규칙을 다시 고치지 않는다 (D-175)")
    ap.add_argument("--category", default=None, choices=[c.value for c in Category], help="모든 행을 이 품목으로 (기본: 품목 미확정)")
    ap.add_argument("--conditional", action="store_true", help="조건부 — 골든 `품목` 을 제품 정보로 (품목을 아는 행만 · D-306)")
    ap.add_argument("--dict-stands", action="store_true", help="사전 확정에 인코더 합의를 요구하지 않는다 (그래프의 지금 규칙 · D-269)")
    ap.add_argument("--exclude-injected", action="store_true", help="주입 행(id 가 inj: 로 시작)을 뺀다 — 실제 문구만")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--margin", type=float, default=QUIET_MARGIN, help="여유 구간 (τ 배수 · 1.0 이면 끔)")
    ap.add_argument("--margin-sweep", default=None, help="예: 1.0,0.8,0.6,0.5,0.4 — 여유 구간별 통과 비율만 출력하고 끝낸다 (dev 만)")
    ap.add_argument("--holdout", action="append", default=[], help="추가 파일 홀드아웃 버킷 — 모델을 직접 돌릴 때만")
    ap.add_argument("--eval-file", action="append", default=[], help="검증 전용 파일 전부를 버킷 eval:<이름> 으로 — 모델을 직접 돌릴 때만")
    ap.add_argument("--with-text", action="store_true", help="문장 원문 포함 — 저장소 밖 경로일 때만 (D-249 ⑥)")
    ap.add_argument("--timing", type=int, default=0, metavar="N", help="추론 시간 — N 문장을 뽑아 인코더 · 판정 로직의 문장당 시간과 토큰 길이를 재고 끝낸다 (dev · 모델 직접 실행만)")
    a = ap.parse_args(argv)

    if a.split == "test" and not a.final:
        raise SystemExit("🔴 test_sentence 는 규칙 설계에 쓰지 않는다 (D-175). 최종 측정 1회면 --final 을 붙인다.")
    if a.split == "test" and a.margin_sweep:
        raise SystemExit("🔴 여유 구간은 dev 에서만 고른다 (D-175) — test 에서는 훑지 않는다.")
    if a.conditional and a.category:
        raise SystemExit("🔴 --conditional 과 --category 는 같이 쓰지 않는다 — 품목을 골든에서 읽거나 하나로 고정하거나.")
    if a.timing and (a.probs_csv or a.split == "test"):
        raise SystemExit("🔴 --timing 은 dev 에서 모델을 직접 돌릴 때만 쓴다 — `--probs-csv` · `--split test` 와 같이 쓰지 않는다.")
    if a.probs_csv and (a.holdout or a.eval_file):
        raise SystemExit("🔴 --holdout · --eval-file 은 저장된 확률이 없다 — `--probs-csv` 없이 모델을 직접 돌릴 때만 쓴다.")
    out_dir = os.path.abspath(a.out_dir)
    if os.path.commonpath([out_dir, REPO]) == REPO:
        raise SystemExit(f"🔴 결과를 저장소 안에 쓰지 않는다 (D-249 ⑥): {out_dir}")
    if not os.path.exists(a.golden):
        raise SystemExit(f"🔴 골든이 없다: {a.golden} — `launcher.py data-setup` 으로 받는다 (D-220)")

    with open(a.golden, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    golden = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]

    # ── 모델(문턱) · 확률
    if a.probs_csv:
        model_dir = scheme_dir(a.model)
        labels, th, scheme = load_scheme(model_dir)
        tok = mdl = None
    else:
        model_dir = resolve_model_dir(a.model)
        tok, mdl, labels, th = load_encoder(model_dir)
        with open(os.path.join(model_dir, "label_scheme.json"), encoding="utf-8") as f:
            scheme = json.load(f)
    if scheme.get("golden_sha256") and scheme["golden_sha256"] != sha:
        raise SystemExit(f"🔴 이 모델은 다른 골든으로 학습했다 — 모델 {scheme['golden_sha256'][:12]} · 지금 {sha[:12]}\n"
                         "  dev 행이 달라진다(모델이 학습한 행을 dev 라고 재게 된다). 같은 판 골든으로 맞춘다 (D-220)")

    # ── 행
    if a.probs_csv:
        ids, prob_of = read_probs_csv(a.probs_csv, labels)
        by_id = {r["id"]: r for r in golden}
        lost = [i for i in ids if i not in by_id]
        if lost:
            raise SystemExit(f"🔴 행별 확률의 id {len(lost)}개가 골든에 없다 (예: {lost[:3]}) — 골든 판이 다르다 (D-220)")
        # 같은 id 가 둘 이상이면(주입 행에 있을 수 있다) 어느 문장의 확률인지 id 로는 못 가린다 — 그 행은 뺀다. 봉인 평가셋이면 멈춘다
        all_ids = set(ids)
        n_gold, n_csv = Counter(r["id"] for r in golden), Counter(ids)
        vague = {i for i in n_csv if n_csv[i] > 1 or n_gold[i] > 1}
        if vague:
            n_drop = sum(n_csv[i] for i in vague)
            if any(by_id[i]["split"] == "test_sentence" for i in vague):
                raise SystemExit(f"🔴 평가셋에 같은 id 가 둘 이상이다({len(vague)}종) — 확률을 문장에 붙일 수 없다 (D-220)")
            print(f"[INFO] 같은 id 가 둘 이상인 행 {n_drop}개(id {len(vague)}종 · 주입 {sum(i.startswith('inj:') for i in vague)}종)는 "
                  "확률을 문장에 붙일 수 없어 뺐다")
            ids = [i for i in ids if i not in vague]
        rows = [dict(by_id[i]) for i in ids]
        is_test = [r["split"] == "test_sentence" for r in rows]
        if any(is_test) and a.split != "test":
            raise SystemExit("🔴 이 파일은 봉인 평가셋(test_sentence) 행이다 — `--split test --final` 로만 잰다 (D-175)")
        if a.split == "test" and not all(is_test):
            raise SystemExit("🔴 --split test 인데 평가셋이 아닌 행이 있다 — dev 확률 파일이면 `--split dev` 다")
        if a.split == "dev":
            mine = {r["id"] for r in dev_rows(golden)}
            note = "같은 행이다" if mine == all_ids else (f"🟡 다른 행이다(겹침 {len(mine & all_ids)} · 이 파일에만 {len(all_ids - mine)} · "
                                                       f"규칙에만 {len(mine - all_ids)}) — 파일의 행을 쓴다")
            print(f"[INFO] 행별 확률 {len(ids)}행 · 이 스크립트의 dev 규칙(v8 ~ v8.2)과 {note}")
    else:
        rows = dev_rows(golden) if a.split == "dev" else [dict(r) for r in golden if r["split"] == "test_sentence"]
        if a.split == "dev":
            by_id = {r["id"]: r for r in golden}
            rows = [dict(by_id[r["id"]]) for r in rows]        # 버킷은 골든의 조건 · 라벨로 가른다(dev 복사본은 D · L 의 유형을 지웠다)
        prob_of = None
    if a.exclude_injected:
        n0 = len(rows)
        rows = [r for r in rows if not r["id"].startswith("inj:")]
        print(f"[INFO] 주입 행 {n0 - len(rows)}개를 뺐다 — 실제 문구 {len(rows)}행")
    if a.conditional:
        from scripts.eval_graph import conditional_rows
        n0 = len(rows)
        rows = conditional_rows(rows)
        print(f"[INFO] 조건부 — 품목을 아는 행 {len(rows)}/{n0} (승인 문구 규칙 행 제외 · 평가 도구와 같은 거름)")
    for r in rows:
        r.setdefault("labels", [])
        r["bucket"] = bucket(r)
    order, expect = list(ORDER), dict(EXPECT)
    for hp in a.holdout:
        hold, stem = extra_holdout(hp)
        rows += hold
        order.append(f"hold:{stem}")
        expect[f"hold:{stem}"] = "위반 · 보류(정답 유형)" if any(r.get("labels") for r in hold) else "통과 (D형)"
        print(f"[INFO] 홀드아웃 {stem}: {len(hold)}행")
    for ep in a.eval_file:
        ev, stem = eval_file(ep)
        rows += ev
        order.append(f"eval:{stem}")
        expect[f"eval:{stem}"] = "판정 대상 아님 (검증 · 학습 안 함)"
        print(f"[INFO] 검증 {stem}: {len(ev)}행 · 종류 {len(Counter(r.get('family', '-') for r in ev))}")
    if not rows:
        raise SystemExit("🔴 잴 행이 없다 (D-220)")

    book = load_banned_terms(a.banned)
    with open(a.banned, "rb") as f:
        dict_sha = hashlib.sha256(f.read()).hexdigest()
    agree = not a.dict_stands
    cat_of = (lambda r: _eg.product_of(r, True).category) if a.conditional else (lambda r: Category(a.category) if a.category else None)
    if a.timing:
        print(f"[INFO] golden {sha[:12]} · {a.split} {len(rows)}행 · 모델 {scheme.get('experiment', '?')}")
        timing(rows, tok, mdl, labels, book, th, cat_of, agree, a.margin, a.timing)
        return 0
    probs = [prob_of[r["id"]] for r in rows] if prob_of else predict_label_probs_batch([r["text"] for r in rows], tok, mdl, labels)
    cat_note = "골든 품목(조건부)" if a.conditional else (a.category or "모름(무조건부)")
    print(f"[INFO] golden {sha[:12]} · 사전 {dict_sha[:12]} ({len(book.exact)} 단독판정 · {len(book.weak)} 자격 없음) · {a.split} {len(rows)}행 · 품목 {cat_note}"
          + ("  🔴 최종 측정 — 이 결과로 규칙을 고치지 않는다" if a.final else ""))
    print(f"[INFO] 모델 {scheme.get('experiment', '?')} · 확률 {'저장된 파일' if prob_of else '직접 계산'} · "
          f"여유 구간 {a.margin} · 사전 확정에 인코더 합의 {'요구' if agree else '요구 안 함(--dict-stands)'} · 규칙 {g.JUDGED_BY}")
    print("[INFO] τ: " + " · ".join(f"{k} {v:g}" for k, v in th.items()))

    if a.margin_sweep:
        ms = [float(x) for x in a.margin_sweep.split(",")]
        shown = [b for b in order if any(r["bucket"] == b for r in rows)]
        print("\n[여유 구간 sweep · dev] 사전도 인코더도 조용한 문장의 비율 (통과 + 판정대상아님 + 품목만 알면 통과) — 양성 버킷은 낮을수록 · D · neg 는 높을수록 좋다")
        print(f"{'margin':>7s}  " + "  ".join(f"{b:>18s}" for b in shown))
        for m in ms:
            c = defaultdict(Counter)
            for r, lp in zip(rows, probs):
                s2 = stage2_judge(stage1_signals(r["text"], lp, book, th, margin=m), category=cat_of(r), agree=agree)
                c[r["bucket"]][state_of(s2) in QUIET_STATES] += 1
            print(f"{m:7.2f}  " + "  ".join(f"{c[b][True]:4d}/{sum(c[b].values()):4d} ({c[b][True] / max(sum(c[b].values()), 1):6.1%})".rjust(18) for b in shown))
        print("  🚨 여기서 고른 값은 `judge_stage1.QUIET_MARGIN` 에 적고, test 는 그 값으로 한 번만 잰다 (D-175)")
        return 0

    # ── 판정 — 같은 행을 「규칙만」과 「규칙 + 인코더」로
    dist, dist0 = defaultdict(Counter), defaultdict(Counter)
    reasons, subj, moved, whys = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), Counter()
    prem = defaultdict(lambda: defaultdict(Counter))
    famdist = defaultdict(lambda: defaultdict(Counter))
    states, states0, out, cand_rows = [], [], [], []
    for r, lp in zip(rows, probs):
        s1 = stage1_signals(r["text"], lp, book, th, margin=a.margin)
        cat = cat_of(r)
        s2 = stage2_judge(s1, category=cat, agree=agree)
        s0 = stage2_judge(s1, category=cat, agree=agree, encoder=False)
        b, st, st0 = r["bucket"], state_of(s2), state_of(s0)
        states.append(s2["state"])
        states0.append(s0["state"])
        dist[b][st] += 1
        dist0[b][st0] += 1
        moved[b][(st0, st)] += 1
        whys[s2["why"]] += 1
        cand_rows.append(list(s2["enc_candidates"]))
        subj[b][s2["subject"]] += 1
        if s2["hold_reason"]:
            reasons[b][s2["hold_reason"]] += 1
        if b.startswith("eval:"):
            famdist[b][r.get("family", "-")][st] += 1
        for p, br in s2["branches"].items():
            prem[p][b]["위반 확정" if br["violations"] else ("통과" if br["pass"] else "보류")] += 1
        row = {"bucket": b, "id": r["id"], "조건": r.get("조건") or "", "labels": "|".join(r.get("labels") or []),
               "품목": cat.value if cat else "", "verdict": s2["verdict"], "hold_reason": s2["hold_reason"] or "",
               "violations": "|".join(s2["violations"]), "no_basis": "|".join(s2["no_basis_types"]), "hold_types": "|".join(s2["hold_types"]),
               "not_claim": int(s2["not_claim"]), "outcome": s2["outcome"], "rule_only": st0, "why": s2["why"],
               "dict_hits": len(s2["dict_terms"]), "dict_weak": len(s2["weak_terms"]), "subject": s2["subject"],
               "enc_candidates": "|".join(s2["enc_candidates"]), "enc_near": s2["enc_near"] or "",
               **{f"p_{x}": round(lp[x], 4) for x in labels}}
        if a.with_text:
            row["text"] = r["text"]
        out.append(row)

    for title, d in ((f"규칙만 (인코더 없음 · {g.JUDGED_BY})", dist0), ("규칙 + 인코더", dist)):
        print(f"\n[기록되는 판정 — {title} · 품목 {cat_note}]")
        print(f"{'버킷':8s} {'n':>5s}  " + "  ".join(f"{s:>16s}" for s in STATES) + "   기대")
        for b in order:
            n = sum(d[b].values())
            if n:
                print(f"{b:8s} {n:5d}  " + "  ".join(f"{d[b][s]:6d}({d[b][s] / n:6.1%})".rjust(16) for s in STATES) + f"   {expect[b]}")
    team_summary(dist0, "규칙만")
    team_summary(dist, "규칙 + 인코더")

    print("\n인코더 층이 바꾼 것 (규칙만 → 규칙 + 인코더 · 행 수)")
    for b in order:
        ch = [(k, v) for k, v in moved[b].most_common() if k[0] != k[1]]
        if moved[b]:
            same = sum(v for k, v in moved[b].items() if k[0] == k[1])
            print(f"  {b:8s} 그대로 {same:5d}" + "".join(f" · {x} → {y} {v}" for (x, y), v in ch))
    print("\n인코더 층의 까닭별 (기록되는 판정 기준)")
    for k, v in whys.most_common():
        print(f"  {v:5d}  {k}")
    types = type_table(rows, cand_rows, [x for x in labels if 0 < th[x] <= 1])
    print("\n사항 판별 (주장 · 거래조건 · 혼합 · 판정대상아님)")
    for b in order:
        if subj[b]:
            print(f"  {b:12s} " + " · ".join(f"{k} {v}" for k, v in subj[b].most_common()))
    for b, fd in famdist.items():
        print(f"\n검증 {b} — 종류별 (판정대상아님 · 통과 · 보류 · 위반 확정)")
        for fam, c in sorted(fd.items(), key=lambda kv: -sum(kv[1].values())):
            print(f"  {fam:14s} n={sum(c.values()):3d}  판정대상아님 {c['판정대상아님']:3d} · 통과 {c['confirmed:신호없음']:3d} · "
                  f"보류 {c['hold'] + c['no_basis'] + c['hold:품목만']:3d} · 위반 {c['confirmed:위반']:3d}")
    print("\n보류 사유별 (D-269 · 규칙 + 인코더)")
    for b in order:
        if reasons[b]:
            print(f"  {b:8s} " + " · ".join(f"{k} {v}" for k, v in reasons[b].most_common()))
    if prem:
        print("\n전제별 결과 (분기 — 기록되는 판정이 아니다 · D-263)")
        for p, d in prem.items():
            print(f"  [{p}] " + " | ".join(f"{b}: " + ", ".join(f"{k} {v}" for k, v in d[b].items()) for b in order if d[b]))

    # ── 팀장 평가 도구와 같은 자 (`scripts/eval_graph.py`) — 골든 행만
    summary = {}
    idx = [i for i, r in enumerate(rows) if not r["bucket"].startswith(("hold:", "eval:"))]
    if idx:
        from scripts import eval_graph as eg
        grows = [rows[i] for i in idx]
        for name, sts in (("규칙만", states0), ("규칙+인코더", states)):
            summary[name] = eg.summarize(grows, [eg.predict(sts[i]) for i in idx])
        print("\n" + "═" * 100)
        print(f"팀장 평가 도구(`scripts/eval_graph.py`)와 같은 자 — {a.split} · 품목 {cat_note}")
        print(f"  규칙만         {headline(summary['규칙만'])}")
        print(f"  규칙 + 인코더  {headline(summary['규칙+인코더'])}")
        print("  · 탐지 = 확정 유형 ∪ 보류 문장의 유형 후보가 정답과 겹친다 (D-311 · 탐지는 판정이 아니다) · 확정 = 확정 문장의 위반만 (D-127)")
        print("  · 🚨 이 스크립트에는 조문 검색 · 위험도 하한이 없다 — 팀장 기준선(DB 로 돈 그래프)과 「규칙만」 줄이 조금 다를 수 있다")
        print("═" * 100 + "\n[규칙 + 인코더 — 평가 도구의 표]")
        eg.report(summary["규칙+인코더"], a.conditional)
        if a.split != "test":
            print("  (위 마지막 줄은 평가 도구의 고정 문구다 — 이번 실행은 dev 다)")

    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"judge_dist_{a.split}_{'cond' if a.conditional else (a.category or 'uncond')}_{stamp}"
    path = os.path.join(out_dir, tag + ".csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    meta = {"split": a.split, "final": a.final, "rows": len(rows), "golden_sha256": sha, "banned_terms_sha256": dict_sha,
            "model_experiment": scheme.get("experiment"), "thresholds": th, "probs": "csv" if prob_of else "model",
            "probs_csv": os.path.basename(a.probs_csv) if a.probs_csv else None, "margin": a.margin, "agree_required": agree,
            "category": cat_note, "exclude_injected": a.exclude_injected, "judged_by": g.JUDGED_BY, "at": stamp,
            "dist": {"규칙만": {b: dict(c) for b, c in dist0.items()}, "규칙+인코더": {b: dict(c) for b, c in dist.items()}},
            "hold_reasons": {b: dict(c) for b, c in reasons.items()}, "why": dict(whys), "encoder_types": types, "summary": summary}
    with open(os.path.join(out_dir, tag + ".json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n[INFO] 행별 결과(저장소 밖): {path}" + ("" if a.with_text else " · 문장 원문 없음(id 로 대조)"))
    print(f"[INFO] 요약: {os.path.join(out_dir, tag + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
