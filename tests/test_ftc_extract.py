"""`preprocess.ftc_extract` — 1층 라벨 추출의 **버리는 규칙** (2026-09-08).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 하나다 — **마스킹이 학습 입력을 먹지 않는다.**

  ⛔ 예전 `NOISE` 는 마스킹 자국이 **든** 인용을 통째로 버렸다. 실측에서 그렇게
     643 → 619 문구 · 285 → 280 문서가 사라졌고, 그중 7건이 진짜 광고 문구였다.
  ★ 버려야 할 것은 자국이 든 인용이 아니라 **자국을 걷어내면 아무것도 안 남는 인용**이다.
"""

from __future__ import annotations

from preprocess.ftc_extract import content_len, phrases_in


def test_content_len_ignores_marks() -> None:
    """자국과 그에 붙은 조사는 알맹이가 아니다."""
    assert content_len("[업체]") == 0
    assert content_len("[업체]는") == 0
    assert content_len("[업체] 오븐글라스") == len("오븐글라스")


def test_keeps_phrase_with_mark() -> None:
    """🔴 **자국이 들어갔다는 이유로 버리지 않는다.** 판정 대상이 남아 있다."""
    got = phrases_in("‘[업체] 오븐글라스’ 라고 표시·광고함으로써")
    assert got == ["[업체] 오븐글라스"]


def test_keeps_full_sentence_with_mark() -> None:
    """문서의 **유일한** 문구가 이렇게 생긴 경우가 있었다 — 버리면 근거절까지 사라진다."""
    q = "한국의 톱밥우사 구조에서는 [업체]만의 특허기술인 급이 우선 개체이동 방식 없이는 한계입니다"
    assert phrases_in(f"‘{q}’ 라고 광고하였다") == [q]


def test_drops_mark_only_quote() -> None:
    """인용이 상호뿐이던 것 — 마스킹 뒤엔 값이 없다."""
    assert phrases_in("‘[업체]’ 라고 표시하였다") == []
    assert phrases_in("‘[업체]는’ 이라고 표시하였다") == []


def test_drops_case_title() -> None:
    """사건명 인용. 예전엔 자국 규칙에 딸려 걸렸으므로 따로 막는다."""
    assert phrases_in("‘[업체]의 부당한 고객유인행위에 대한 건’ 에서") == []


def test_keeps_agency_endorsement_claim() -> None:
    """🔴 **기관 사칭형 거짓·과장 광고를 버리지 않는다.**

    ⛔ `공정거래위원회`·`위원회` 를 통째로 `NOISE` 에 넣었더니
       「… 합격자 배출수 1위, … 및 공정거래위원회 **인정**」이 사라지고 있었다.
       1층이 제일 필요로 하는 종류다. 과잉삭제 감시 지표가 잡아냈다 (D-142 (다)).
    """
    q = "독학학위제 학위취득 2016 합격자 배출수 1위, 2016년 3월 4일 국가평생교육진흥원 및 공정거래위원회 인정"
    assert phrases_in(f"‘{q}’ 라고 광고하였다") == [q]


def test_drops_agency_order_text() -> None:
    """반면 처분 문안·자료 제출 명령은 광고 문구가 아니다 — 좁게 막는다."""
    assert phrases_in("‘공정거래위원회에 회원수 근거자료 제출’ 하여야 한다") == []
    assert phrases_in("‘게재면 및 활자의 크기는 사전에 공정거래위원회와 협의를 거쳐야 한다’") == []
