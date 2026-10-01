"""판정 로직 1·2단계 규칙 테스트 — 설계결정을 코드로 고정한다 (박수진 · 2026-10-01)

  uv run pytest docs/psj/e2e_prototype/test_judge_rules.py -q

🔴 인코더 모델 없이 돈다 — 인코더 점수는 테스트가 직접 넣는다(가짜 점수). 3차 재학습 · τ 변경 뒤에도 그대로 쓴다.
🔴 금지 표현 사전(banned_terms.jsonl)이 필요한 테스트는 사전이 없으면 건너뛴다 — `launcher.py data-setup` 으로 받는다.
🚨 문장은 이 파일에서 지어낸 예문이다 — 평가셋(test_sentence) 문장을 옮겨 오지 않는다 (D-175 · D-249).

낱말 목록(TRADE_CUE · CLAIM_CUE · NOTCLAIM_CUE)을 고쳐도 아래 규칙이 깨지면 안 된다.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..")))

import judge_stage1 as s1  # noqa: E402
import judge_stage2 as s2  # noqa: E402
from app.contracts import Category  # noqa: E402

TH = {
    "질병_예방치료_표방": 0.325,
    "건강기능식품_오인": 0.275,
    "의약품_오인": 0.525,
    "거짓_과장": 0.65,
    "소비자_기만": 0.275,
    "후기_체험기_기만": 0.45,
}
HF = "건강기능식품_오인"
PASS = ("confirmed",)


def probs(**over):
    """모든 유형 0.01 — 넣은 유형만 바꾼다."""
    p = {k: 0.01 for k in TH}
    p.update(over)
    return p


def near(label):
    """τ × margin 이상 · τ 미만 — 경계 근처 신호만 나는 점수."""
    return (TH[label] * s1.QUIET_MARGIN + TH[label]) / 2


def above(label):
    """τ 이상 — 인코더가 울린 점수."""
    return min(0.99, TH[label] + 0.2)


@pytest.fixture(scope="module")
def book():
    if not os.path.exists(s1.BANNED_TERMS_PATH):
        pytest.skip("banned_terms.jsonl 없음 — data-setup 으로 받는다")
    return s1.load_banned_terms()


def run(text, p, book, category=None, recognized=None):
    a = s1.stage1_signals(text, p, book, TH)
    return a, s2.stage2_judge(a, category=category, recognized=recognized)


def kinds(a):
    return {x["kind"] for x in a["signals"]}


# ── 사항 판별 (낱말 단계) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, want",
    [
        ("전 상품 무료배송, 주문 다음 날 도착", "거래조건"),
        ("5만원 이상 구매 시 사은품 증정", "거래조건"),
        ("1일 2회, 1회 1포를 물과 함께 드세요", "판정대상아님"),
        ("서늘하고 건조한 곳에 보관하세요", "판정대상아님"),
        ("야근이 잦은 분께 추천합니다", "판정대상아님"),
        ("개봉 후에는 냉장 보관하시고 뜨거우니 드실 때 주의하세요", "판정대상아님"),
        ("면역력 강화에 도움을 줍니다", "주장"),
        ("부작용 걱정 없이 드셔도 좋아요", "주장"),  # D-286 ⑥ — 안전 주장이 붙으면 D 가 아니다
        ("관절 건강에 알맞은 구성", "주장"),  # 대상 + 효능 → 주장
        ("혈당 걱정 끝! 지금 30% 할인", "혼합"),
    ],
)
def test_사항_판별(text, want):
    assert s1.sentence_subject(text)[0] == want


# ── D-272 개정 — 거래 조건은 판정 대상 아님이 아니다 ─────────────────────


def test_거래조건은_not_claim_으로_나가지_않는다(book):
    a, r = run("전 상품 무료배송, 주문 다음 날 도착", probs(거짓_과장=0.9, 소비자_기만=0.9), book)
    assert a["subject"] == "거래조건"
    assert a["not_claim"] is False and r["not_claim"] is False
    assert r["verdict"] == "hold" and "거래조건" in r["hold_types"]
    assert "model" not in kinds(a)  # 인코더 점수를 판정 근거로 쓰지 않는다


def test_거래조건은_신호가_없어도_통과가_아니다(book):
    _, r = run("5만원 이상 구매 시 사은품 증정", probs(), book)
    assert r["verdict"] == "hold"


# ── D-275 · D-286 ③ — 판정 대상 아님 ──────────────────────────────────


def test_주장_없는_문구_경계_신호만이면_판정_대상_아님(book):
    a, r = run("서늘하고 건조한 곳에 보관하세요", probs(거짓_과장=near("거짓_과장")), book)
    assert a["not_claim"] is True and a["signals"] == []
    assert r["verdict"] == "confirmed" and r["violations"] == [] and r["not_claim"] is True


# ── D-127 — 코드가 인코더를 덮지 않는다 ─────────────────────────────────


def test_τ_넘긴_인코더_신호는_판정_대상_아님으로_덮지_않는다(book):
    a, r = run("서늘하고 건조한 곳에 보관하세요", probs(거짓_과장=above("거짓_과장")), book)
    assert a["subject"] == "판정대상아님"
    assert a["not_claim"] is False
    assert r["verdict"] == "hold"


def test_주장_문장의_경계_신호는_보류(book):
    a, r = run("한 끼로 든든한 하루를 시작하세요", probs(거짓_과장=near("거짓_과장")), book)
    assert "near_threshold" in kinds(a)
    assert r["verdict"] == "hold"


def test_신호가_전혀_없으면_확정_위반_없음(book):
    a, r = run("한 끼로 든든한 하루를 시작하세요", probs(), book)
    assert a["signals"] == [] and a["not_claim"] is False
    assert r["verdict"] == "confirmed" and r["violations"] == []


def test_사전만으로는_확정하지_않는다(book):
    _, r = run("이 제품을 드시면 당뇨가 완치됩니다", probs(), book)
    assert r["dict_backed"]
    assert r["verdict"] == "hold" and r["violations"] == []


def test_사전과_인코더가_합의하면_확정(book):
    _, r = run("이 제품을 드시면 당뇨가 완치됩니다", probs(질병_예방치료_표방=above("질병_예방치료_표방")), book)
    assert r["verdict"] == "confirmed" and "질병_예방치료_표방" in r["violations"]
    assert r["basis"]  # D-224 — 확정에는 근거 조문


def test_인코더_단독은_확정하지_않는다(book):
    _, r = run("한 끼로 든든한 하루를 시작하세요", probs(거짓_과장=above("거짓_과장")), book)
    assert r["verdict"] in ("hold", "no_basis") and r["violations"] == []


# ── D-229 · D-263 · D-276 — 전제 ─────────────────────────────────────


def test_건기식_전제에서는_건기식_오인을_확정하지_않는다(book):
    _, r = run("매일 한 포로 면역 기능을 챙기세요", probs(**{HF: above(HF)}), book, category=Category.건기식)
    for p, br in r["branches"].items():
        assert HF not in br["violations"], p
    assert HF not in r["violations"]


def test_품목_모름이고_전제별로_갈리면_보류_cat_unknown(book):
    _, r = run("이 제품은 기억력 개선에 도움을 줄 수 있습니다", probs(), book)
    assert r["verdict"] == "hold" and r["hold_reason"] == "cat_unknown"
    assert r["branches"]["건기식_인정"]["verdict"] == "confirmed"
    assert r["conservative_premise"] == "식품"


def test_건기식인데_인정_여부를_모르면_premise_unknown(book):
    _, r = run("이 제품은 기억력 개선에 도움을 줄 수 있습니다", probs(), book, category=Category.건기식)
    assert r["hold_reason"] == "premise_unknown"
    assert r["conservative_premise"] == "건기식_비인정"


def test_사업자_선택은_기록되는_판정을_바꾸지_않는다(book):
    _, r = run("이 제품은 기억력 개선에 도움을 줄 수 있습니다", probs(), book)
    sel = s2.apply_selection(r, "건기식_인정", detected=None)
    assert sel["verdict"] == r["verdict"] == "hold"
    ps = sel["premise_selection"]
    assert ps["applied"] and ps["pass_badge"] is False
    assert ps["notice"] == s2.NOTICE_USER_SELECTED


def test_전용법_미수록은_신호가_없어도_law_uncovered(book):
    _, r = run("한 끼로 든든한 하루를 시작하세요", probs(), book, category=Category.전용법_미수록)
    assert r["verdict"] == "hold" and r["hold_reason"] == "law_uncovered"


# ── 10-01 팀장 채점 기준 — run_judge_dist 버킷 ───────────────────────────


def test_채점_버킷():
    import run_judge_dist as rd

    def b(**k):
        return rd.bucket({"id": "t", "text": k.pop("text", "보관하세요"), **k})

    assert b(조건="L") == "neg"
    assert b() == "neg"
    assert b(조건="C") == b(조건="A") == b(조건="B") == "pending"
    assert b(labels=["거짓_과장"]) == "scored"
    assert b(조건="M", labels=["거짓_과장"]) == "M"  # M 은 채점 안 함
    assert b(조건="D", labels=["거짓_과장"]) == "D"  # D 는 별도 지표
    assert b(조건="D", text="무료배송 이벤트") == "D_거래"
    with pytest.raises(SystemExit):
        b(조건="L", labels=["거짓_과장"])  # L(적법)에 위반 라벨 — 데이터 어긋남
    assert rd.TEAM["scored"] == rd.TEAM["pending"] == "양성"
