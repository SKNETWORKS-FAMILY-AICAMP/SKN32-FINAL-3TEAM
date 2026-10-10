"""판정 로직 1·2단계 규칙 테스트 — 설계결정을 코드로 고정한다 (🔄 2026-10-06 main `ebb3f10` 맞춤판 · 박수진)

  uv run pytest docs/psj/e2e_prototype/test_judge_rules.py -q

🔴 인코더 모델 · DB · 받은 사전 없이 돈다 — 인코더 점수는 테스트가 직접 넣고, 사전은 이 파일이 만든 **작은 사전**이다.
   그래서 사전 판(506종)이 바뀌어도 · 인코더를 다시 학습해도 같은 결과다.
🚨 문장 · 낱말은 이 파일에서 지어낸 것이다 — 평가셋(test_sentence) 문장을 옮겨 오지 않는다 (D-175 · D-249).

무엇을 고정하나
  · 규칙 판정은 판정 그래프의 함수가 낸다(`app/graph.py`) — 여기서는 **인코더 층**과 품목 미확정 처리만 본다.
  · 인코더만으로는 확정하지 않는다 (D-224 · D-131) · 사전 확정은 인코더 합의가 있을 때만 (D-127)
  · 통과(확정 · 위반 없음)는 사전도 인코더도 조용할 때만 (D-273) · 품목 미확정 · 주된 광고법을 안 본 품목에는 통과가 없다 (D-319 ② · D-314)
  · 전제가 유형을 바꾸는 자리 (D-319 ④′) · 편입 대기 칸은 후보로 내지 않는다 (D-321)
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..")))

import judge_stage1 as s1  # noqa: E402
import judge_stage2 as s2  # noqa: E402
from app import premise as pm  # noqa: E402
from app.contracts import Category, Verdict  # noqa: E402
from collect import statute  # noqa: E402

FOOD, FAIR, COSM = (statute.STATUTE_ID[k] for k in ("식품표시광고법", "표시광고법", "화장품법"))
WAIT = "기능성화장품_오인"
HF = "건강기능식품_오인"
TH = {"질병_예방치료_표방": 0.35, "건강기능식품_오인": 0.45, "의약품_오인": 0.45, "거짓_과장": 0.375, "소비자_기만": 0.475,
      "후기_체험기_기만": 0.325, "부당_비교광고": 0.9, "비방광고": 0.8, WAIT: 1.01}

#: 지어낸 낱말 — 실제 광고 낱말이 아니다. (낱말, 인용, 유형, 단독판정)
TERMS = [
    ("가나표지", f"{FAIR}:제3조제1항제1호", "거짓_과장", True),            # 표시광고법 — 모든 전제의 법 묶음에 든다
    ("다라표지", f"{FOOD}:제8조제1항제1호", "질병_예방치료_표방", True),    # 식품표시광고법 — 식품 전제에서만 선다
    ("마바표지", f"{FOOD}:제8조제1항제3호", HF, True),                      # 3호 — 건강기능식품 전제에서는 서지 않는다
    ("사아표지", f"{COSM}:제13조제1항제2호", WAIT, True),                   # 인코더가 내지 않는 유형
    ("자차표지", f"{FOOD}:제8조제1항제1호", "질병_예방치료_표방", False),   # 단독판정 자격 없음 (D-311)
]
PLAIN = "오늘도 좋은 하루"           # 표지 없음 · 사항 「주장」
NOTCLAIM = "직사광선을 피해 서늘한 곳에 두십시오 보관"
TRADE = "전 상품 무료 배송"


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    path = tmp_path_factory.mktemp("dict") / "banned_terms.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for term, cite, kind, solo in TERMS:
            f.write(json.dumps({"term": term, "원문": [term], "유형": [kind], "근거": [cite], "단독판정": solo}, ensure_ascii=False) + "\n")
    return s1.load_banned_terms(str(path))


def probs(**over):
    """모든 유형 0.01 — 넣은 유형만 바꾼다."""
    return {**{k: 0.01 for k in TH}, **over}


def above(label):
    return min(0.99, TH[label] + 0.05)


def near(label):
    return TH[label] * (s1.QUIET_MARGIN + 1) / 2      # τ × margin 이상 · τ 미만


def run(book, text, category=None, agree=True, **p):
    return s2.stage2_judge(s1.stage1_signals(text, probs(**p), book, TH), category=category, agree=agree)


# ── 1단계 ──────────────────────────────────────────────────────────────
def test_사전은_자격으로_갈린다(book):
    assert len(book.exact) == 4 and len(book.weak) == 1
    scan = book.scan("가나표지 그리고 자차표지")
    assert scan.ran and [h.term for h in scan.hits] == ["가나표지"] and [h.term for h in scan.weak] == ["자차표지"]


def test_편입_대기_칸은_후보도_여유구간도_아니다():
    enc = s1.encoder_signal(PLAIN, probs(**{WAIT: 0.99}), TH)
    assert enc["candidates"] == [] and enc["near"] is None and enc["quiet"] and WAIT not in enc["active"]


def test_후보와_여유구간():
    enc = s1.encoder_signal(PLAIN, probs(거짓_과장=above("거짓_과장")), TH)
    assert enc["candidates"] == ["거짓_과장"] and not enc["quiet"]
    enc = s1.encoder_signal(PLAIN, probs(거짓_과장=near("거짓_과장")), TH)
    assert enc["candidates"] == [] and enc["near"] == "거짓_과장" and not enc["quiet"]


def test_사항_판별():
    assert s1.sentence_subject(PLAIN)[0] == "주장"
    assert s1.sentence_subject(NOTCLAIM)[0] == "판정대상아님"
    assert s1.sentence_subject(TRADE)[0] == "거래조건"


# ── 사전 확정 × 인코더 합의 (D-127) ────────────────────────────────────
def test_모든_전제에서_같은_위반이면_품목을_몰라도_확정(book):
    r = run(book, "가나표지 문장", 거짓_과장=above("거짓_과장"))
    assert r["verdict"] == "confirmed" and r["violations"] == ["거짓_과장"]
    assert set(r["branches"]) == {p.value for p in pm.PREMISES_OF[None]}      # 품목 미확정이면 분기는 언제나 (D-229 ⑥)
    assert r["outcome"] == "hold"                                             # 위험도 하한을 못 읽는다(DB 없음) → 종착은 보류


def test_전제에_따라_갈리면_보류와_분기(book):
    r = run(book, "다라표지 문장", 질병_예방치료_표방=above("질병_예방치료_표방"))
    assert (r["verdict"], r["hold_reason"]) == ("hold", "cat_unknown") and r["hold_types"] == ["질병_예방치료_표방"]
    assert r["branches"]["식품"]["violations"] == ["질병_예방치료_표방"]
    assert r["branches"]["화장품"]["verdict"] == "hold" and r["branches"]["일반상품"]["verdict"] == "hold"
    assert r["branches"]["건기식_인정"]["verdict"] == "hold"                  # 목을 모르는 질병 표방 — 이 전제에서는 판정하지 못한다


def test_품목을_알면_확정(book):
    r = run(book, "다라표지 문장", Category.식품, 질병_예방치료_표방=above("질병_예방치료_표방"))
    assert r["verdict"] == "confirmed" and r["violations"] == ["질병_예방치료_표방"] and r["branches"] == {}


def test_인코더가_합의하지_않으면_보류_유형은_남긴다(book):
    r = run(book, "가나표지 문장", Category.화장품)
    assert (r["verdict"], r["hold_reason"]) == ("hold", "low_conf") and r["hold_types"] == ["거짓_과장"]
    assert r["rule"]["verdict"] == "confirmed"                                # 규칙만으로는 확정이었다
    r = run(book, "가나표지 문장", Category.화장품, agree=False)              # 그래프의 지금 규칙 (D-269)
    assert r["verdict"] == "confirmed" and r["violations"] == ["거짓_과장"]


def test_합의_문턱을_따로_두면_후보를_넓혀도_확정은_그대로다(book):
    """카드 8 — 후보 문턱만 절반으로 낮춘다. 합의 문턱을 따로 주지 않으면 합의도 같이 느슨해진다."""
    low = {k: (v * 0.5 if v <= 1 else v) for k, v in TH.items()}
    p = probs(거짓_과장=TH["거짓_과장"] * 0.7)                                # 낮춘 후보 문턱 이상 · 원래 문턱 미만
    judge = lambda **kw: s2.stage2_judge(s1.stage1_signals("가나표지 문장", p, book, low, margin=1.0, **kw), category=Category.화장품)
    r = judge()                                                              # 문턱 하나 — 합의가 되어 확정
    assert r["verdict"] == "confirmed" and r["violations"] == ["거짓_과장"]
    r = judge(agree_thresholds=TH)                                           # 합의는 원래 문턱 — 보류 · 유형은 남는다
    assert (r["verdict"], r["hold_reason"]) == ("hold", "low_conf") and r["hold_types"] == ["거짓_과장"]
    assert r["enc_candidates"] == ["거짓_과장"]                              # 후보는 낮춘 문턱으로 선다
    r = s2.stage2_judge(s1.stage1_signals(PLAIN, p, book, low, margin=1.0, agree_thresholds=TH), category=Category.화장품)
    assert r["verdict"] == "hold" and r["hold_types"] == ["거짓_과장"]        # 사전이 조용한 문장 — 후보가 붙은 보류 (합의와 무관)


def test_다른_유형에_울린_것은_합의가_아니다(book):
    r = run(book, "가나표지 문장", Category.화장품, 의약품_오인=above("의약품_오인"))
    assert r["verdict"] == "hold" and r["hold_types"] == ["거짓_과장"]


def test_인코더가_내지_않는_유형은_사전이_선다(book):
    r = run(book, "사아표지 문장", Category.화장품)
    assert r["verdict"] == "confirmed" and r["violations"] == [WAIT]


# ── 인코더만 (D-224 · D-131) ───────────────────────────────────────────
@pytest.mark.parametrize("category", [None, Category.식품, Category.건기식, Category.화장품, Category.일반상품, Category.전용법_미수록])
def test_인코더만으로는_확정하지_않는다(book, category):
    r = run(book, PLAIN, category, **{k: 0.99 for k in TH})
    assert r["verdict"] == "hold" and r["violations"] == [] and r["hold_types"]
    assert all(b["violations"] == [] for b in r["branches"].values())


def test_인코더_후보는_보류의_유형_후보(book):
    r = run(book, PLAIN, Category.식품, 소비자_기만=above("소비자_기만"))
    assert (r["verdict"], r["hold_reason"], r["hold_types"]) == ("hold", "low_conf", ["소비자_기만"])


def test_여유_구간은_보류(book):
    r = run(book, PLAIN, Category.식품, 거짓_과장=near("거짓_과장"))
    assert (r["verdict"], r["hold_reason"], r["hold_types"]) == ("hold", "low_conf", [])


def test_자격_없는_적중은_인코더가_조용해도_보류(book):
    r = run(book, "자차표지 문장", Category.식품)
    assert (r["verdict"], r["hold_reason"]) == ("hold", "low_conf") and r["hold_types"] == ["질병_예방치료_표방"]


def test_거래_조건은_보류이고_후보는_표시광고법_유형만(book):
    r = run(book, TRADE, Category.식품, 질병_예방치료_표방=above("질병_예방치료_표방"))
    assert (r["verdict"], r["hold_reason"], r["hold_types"]) == ("hold", "low_conf", []) and not r["not_claim"]
    r = run(book, TRADE, Category.식품, 거짓_과장=above("거짓_과장"), 의약품_오인=above("의약품_오인"))
    assert (r["verdict"], r["hold_reason"], r["hold_types"]) == ("hold", "low_conf", ["거짓_과장"])
    r = run(book, TRADE, Category.식품)                                       # 인코더가 조용해도 통과로 내지 않는다 (D-272 개정 ①)
    assert r["verdict"] == "hold" and not r["pass"]


# ── 통과 (D-273 · D-314 · D-319 ②) ─────────────────────────────────────
def test_사전도_인코더도_조용하면_확정_위반없음(book):
    r = run(book, PLAIN, Category.식품)
    assert r["verdict"] == "confirmed" and r["violations"] == [] and r["pass"] and r["outcome"] == "pass"
    assert r["rule"]["verdict"] == "hold"                                     # 규칙만으로는 보류였다 (D-269)


def test_품목을_모르면_통과가_없다(book):
    r = run(book, PLAIN)
    assert (r["verdict"], r["hold_reason"]) == ("hold", "cat_unknown") and r["outcome"] == "hold"
    assert r["branches"]["식품"]["pass"] and r["branches"]["일반상품"]["hold_reason"] == "law_uncovered"


@pytest.mark.parametrize("category", [Category.일반상품, Category.전용법_미수록])
def test_주된_광고법을_안_본_품목은_통과가_없다(book, category):
    r = run(book, PLAIN, category)
    assert (r["verdict"], r["hold_reason"]) == ("hold", "law_uncovered") and r["outcome"] == "hold"


def test_판정_대상_아님(book):
    r = run(book, NOTCLAIM, Category.식품)
    assert r["verdict"] == "confirmed" and r["not_claim"] and r["outcome"] == "pass"
    r = run(book, NOTCLAIM, Category.일반상품)                                # 주장이 없는 문장은 법을 안 봤어도 확정이다 (D-314)
    assert r["verdict"] == "confirmed" and r["not_claim"] and r["outcome"] == "hold"
    r = run(book, NOTCLAIM)                                                   # 문장은 확정 · 종착은 통과가 아니다 (D-319 ②)
    assert r["verdict"] == "confirmed" and r["not_claim"] and r["outcome"] == "hold"
    r = run(book, NOTCLAIM, Category.식품, 거짓_과장=above("거짓_과장"))      # 인코더가 울리면 판정 대상이다
    assert r["verdict"] == "hold" and not r["not_claim"]


# ── 전제가 유형을 바꾸는 자리 (D-319 ④′) ───────────────────────────────
def test_건강기능식품에서는_3호_후보가_서지_않는다(book):
    r = run(book, PLAIN, Category.건기식, **{HF: above(HF)})
    assert r["verdict"] == "hold" and r["hold_types"] == ["거짓_과장"]        # 비인정 전제의 [별표 1] 4.나
    assert r["branches"]["건기식_인정"]["hold_types"] == [] and r["branches"]["건기식_인정"]["verdict"] == "hold"
    assert r["branches"]["건기식_비인정"]["hold_types"] == ["거짓_과장"]
    r = run(book, PLAIN, Category.식품, **{HF: above(HF)})
    assert r["hold_types"] == [HF] and r["branches"]["일반식품_기능성"]["hold_types"] == []


def test_건강기능식품의_3호_적중은_전제에_따라_갈린다(book):
    r = run(book, "마바표지 문장", Category.건기식, **{HF: above(HF)})
    assert (r["verdict"], r["hold_reason"]) == ("hold", "premise_unknown") and r["hold_types"] == ["거짓_과장"]
    assert r["branches"]["건기식_비인정"]["violations"] == ["거짓_과장"]      # 3호 → 4호 나목 · 인코더의 3호 후보도 같이 옮긴다
    assert r["branches"]["건기식_인정"]["verdict"] == "hold"


# ── 팀장 평가 도구와 같은 자 ────────────────────────────────────────────
def test_평가_도구에_그대로_들어간다(book):
    eg = pytest.importorskip("scripts.eval_graph")
    rows = [{"id": "x:1", "text": "가나표지 문장", "labels": ["거짓_과장"], "조건": "B", "근거": [f"{FAIR}:제3조제1항제1호"], "split": "dev"},
            {"id": "x:2", "text": PLAIN, "labels": ["소비자_기만"], "조건": "B", "근거": [f"{FAIR}:제3조제1항제2호"], "split": "dev"},
            {"id": "x:3", "text": "오늘은 맑은 날", "labels": [], "조건": "L", "근거": [], "split": "dev"}]
    ps = [probs(거짓_과장=above("거짓_과장")), probs(소비자_기만=above("소비자_기만")), probs()]
    preds = [eg.predict(s2.stage2_judge(s1.stage1_signals(r["text"], p, book, TH), category=Category.화장품)["state"])
             for r, p in zip(rows, ps)]
    assert [p["class"] for p in preds] == ["확정위반", "보류", "확정무위반"]
    assert preds[0]["types"] == ["거짓_과장"] and preds[1]["candidates"] == ["소비자_기만"]
    s = eg.summarize(rows, preds)
    assert s["detect"] == {"positive": 2, "confirmed": 1, "detected": 2}
    assert s["lawful"]["주장"] == (1, 0)


def test_문장_판정은_계약을_지난다(book):
    r = run(book, "다라표지 문장", 질병_예방치료_표방=above("질병_예방치료_표방"))
    st = r["state"]
    assert st["sentences"][0].verdict is Verdict.hold and len(st["branches"]) == 6
    assert all(b.criteria for b in st["branches"])


# ── 분포 스크립트 ───────────────────────────────────────────────────────
def test_버킷은_확정_8종_기준이다():
    rd = pytest.importorskip("run_judge_dist")
    row = lambda cond, labels, rid="g:1#1", text=PLAIN: {"id": rid, "text": text, "조건": cond, "labels": labels}
    assert rd.bucket(row("B", ["비방광고"])) == "scored"                     # 새 2종도 채점 (D-321)
    assert rd.bucket(row("B", ["부당_비교광고", WAIT])) == "scored"
    assert rd.bucket(row("A", [WAIT])) == "대기"                             # 편입 대기만 달린 행
    assert rd.bucket(row("C", [])) == "pending"                              # 유형 없는 위반
    assert rd.bucket(row("M", ["거짓_과장"])) == "M"
    assert rd.bucket(row("L", [])) == "neg"
    assert rd.bucket(row("D", [], rid="gf:1#1")) == "D"                      # 적법 문장(주장 없음) — 원천이 승인한 형태만 (D-301)
    assert rd.bucket(row("D", [])) == "D_기타"
    assert rd.bucket(row("D", [], text=TRADE)) == "D_거래"
    with pytest.raises(SystemExit):
        rd.bucket(row("L", ["거짓_과장"]))


def test_test_는_final_없이는_멈춘다(tmp_path):
    rd = pytest.importorskip("run_judge_dist")
    with pytest.raises(SystemExit):
        rd.main(["--split", "test", "--out-dir", str(tmp_path)])
