"""공정위 의결서 주문의 처분 · 대표자 마스킹 · 겹침 열쇠 · 봉인 고정 (2026-09-30 · 검토 §1 · 집행 5건).

🔴 무엇을 막나
   ① 원천이 「위반되지 아니한다」라 한 문구가 위반 양성으로 들어가는 것 (D-237 · 16081 · 16095 · 18143)
   ② 뒷광고(경제적 이해관계 미공개) 사건의 상품명이 평가에 들어가는 것 (D-255 ③ · 봉인 24행)
   ③ 머리 아래 행위 항목(「다음과 같이 … 아니 된다. 1. … 2. …」)의 유형을 잃는 것 · 날짜를 항목으로 자르는 것
   ④ 피심정보내용의 대표자 실명이 광고 문구 안에 남는 것 (D-258 · 9859) · 띄어 쓴 상호가 남는 것
   ⑤ 원천이 붙인 항목 번호 머리 때문에 같은 적법 문장이 학습 · 평가 양쪽에 남는 것 (D-292)
   ⑥ 입력이 한 문서 바뀌면 봉인이 통째로 다시 뽑히는 것 (D-254)
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from preprocess import ftc_extract as fe
from preprocess import golden, mask, split
from preprocess.text import sep_norm


def _types(order: str) -> list[str]:
    return [t["label"] for t in fe.types_in(sep_norm(fe.violation_text(fe.clauses(order))))]


@pytest.mark.gate
def test_무혐의_주문의_문구는_적법이고_유형이_없다() -> None:
    order = (
        "[업체]의 부당한 광고행위에 대한 건 관련 피심인의 행위는 표시ㆍ광고의 공정화에 관한 법률 "
        "제3조 제1항에 위반되지 아니한다.\n\n\n1. 심사보고서상 혐의 내용\n\n가. 피심인의 행위\n"
        "피심인은 “모델별로 최대 210만 원까지 지원하는 특별한 가격혜택” 등의 내용을 게시하였다.\n"
        "다. 이 사건 광고는 거짓ㆍ과장의 광고로서 부당한 광고에 해당한다."
    )
    cls = fe.clauses(order)
    assert fe.doc_disposition(cls) == "적법"
    by = fe.place(fe.phrases_in(order), cls)
    assert by["적법"] == ["모델별로 최대 210만 원까지 지원하는 특별한 가격혜택"] and not by["위반"]
    assert _types(order) == []  # 🔴 심사보고서의 「거짓ㆍ과장」을 세지 않는다


@pytest.mark.gate
def test_일부_조항만_무혐의면_그_조항의_문구만_적법이다() -> None:
    order = (
        "1. 피심인은 다음과 같이 기만적으로 광고하는 행위를 다시 하여서는 아니된다.\n\n"
        "가. 적립 혜택에 대해 제한사항을 기재하지 않는 것과 같이 기만적으로 광고하는 행위\n\n"
        "2. 피심인이 가입자 수에 대해 '벌써 800만의 경쟁력’이라고 광고한 행위는 표시ㆍ광고의 공정화에 관한 "
        "법률 제3조 제1항 제1호 및 제2호에 위반되지 아니한다."
    )
    cls = fe.clauses(order)
    by = fe.place(fe.phrases_in(order), cls)
    assert by["적법"] == ["벌써 800만의 경쟁력"] and not by["위반"]
    assert _types(order) == ["소비자_기만"]


@pytest.mark.gate
def test_위반에_해당하지_아니한다_꼴도_적법_항목이다() -> None:
    """🔴 16739 — 「… 광고한 행위는 법 위반에 해당하지 아니한다」를 못 읽어 무혐의 문구가 위반 양성이 됐다 (D-237 · 원장 10-03 ⑫)."""
    order = (
        "1. 피심인은 객관적인 근거 없이 “한 번 충전으로 천 킬로미터”라고 광고하는 행위를 다시 하여서는 아니 된다.\n\n"
        "2. 피심인은 다음 각 호에 따라 과징금을 국고에 납부하여야 한다.\n\n"
        "3. 피심인이 주행보조 프로그램에 대해 “첨단 편의기술 기본 탑재” 등의 문구를 사용하여 광고한 행위는 "
        "법 위반에 해당하지 아니한다."
    )
    cls = fe.clauses(order)
    assert [k for k, _ in cls] == ["위반", "기타", "적법"]
    by = fe.place(fe.phrases_in(order), cls)
    assert by["위반"] == ["한 번 충전으로 천 킬로미터"]
    assert by["적법"] == ["첨단 편의기술 기본 탑재"]


@pytest.mark.gate
def test_뒷광고_사건은_범위_밖이다() -> None:
    order = (
        "1. 피심인은 블로그 운영자들에게 자신의 의료서비스 '▩▩▩▩▩’에 관한 광고를 게시해 줄 것을 요청하고 "
        "경제적 대가를 지급하였음에도 경제적 이해관계를 공개하지 않고 은폐 또는 누락하는 방법으로 "
        "기만적인 광고행위를 다시 하여서는 아니 된다.\n\n2. 피심인은 다음 각 호에 따라 과징금을 국고에 납부하여야 한다.\n\n"
        "가. 과징금액: 94,000,000원"
    )
    cls = fe.clauses(order)
    assert fe.doc_disposition(cls) == "뒷광고"
    assert _types(order) == []
    assert fe.place(["▩▩▩▩▩"], cls)["버림"] == ["▩▩▩▩▩"]


@pytest.mark.gate
def test_머리_아래_행위_항목은_머리를_따르고_뒷광고_항목만_빠진다() -> None:
    order = (
        "1. 피심인은 블로그 등에 후기 형식의 광고를 게시하면서 다음과 같이 부당한 광고행위를 다시 하여서는 아니 된다.\n"
        "가. 게시자들이 경험한 사실이 없음에도 실제 경험을 바탕으로 작성한 것처럼 표현하는 거짓ㆍ과장의 광고행위\n"
        "나. 광고대행업자에게 경제적 대가를 지급하였음에도 경제적 이해관계를 공개하지 않고 은폐하는 기만적인 광고행위\n"
        "2. 피심인의 행위 중 필러 유지기간 관련 부분은 표시ㆍ광고의 공정화에 관한 법률 제3조 제1항 제1호에 위반되지 아니 한다."
    )
    assert [k for k, _ in fe.clauses(order)] == ["위반", "위반", "뒷광고", "적법"]
    assert _types(order) == ["거짓_과장"]  # 🔴 소비자_기만 은 뒷광고 항목에서 왔다 (D-255 ③)


@pytest.mark.gate
def test_날짜와_위_1의_는_항목으로_자르지_않는다() -> None:
    order = (
        "4. 피심인이 2022. 4. 19. 인터넷 신문을 통해 “EQE에 탑재되는 배터리 셀은 CATL이 공급한다.” 등의 내용으로 "
        "광고한 행위는 표시ㆍ광고의 공정화에 관한 법률 제3조 제1항에 위반되지 아니한다.\n"
        "5. 위 1.의 행위를 하여 시정명령을 받았다는 사실을 공표하여야 한다."
    )
    units = fe.clauses(order)
    assert len(units) == 2 and units[0][0] == "적법"
    assert fe.place(["EQE에 탑재되는 배터리 셀은 CATL이 공급한다."], units)["적법"]


@pytest.mark.gate
def test_과징금_명령만_부수이고_납부액_서술은_아니다() -> None:
    order = (
        "1. 피심인은 다음 각호와 같은 부당한 광고를 다시 하여서는 아니된다.\n"
        "가. 협회비 납부액 순위가 1위임에도 대한민국 유가공협회 1위라고만 광고함으로써 기만적인 광고 행위\n"
        "2. 피심인은 다음 각 호에 따라 과징금을 국고에 납부하여야 한다."
    )
    assert [k for k, _ in fe.clauses(order)] == ["위반", "위반", "기타"]
    assert _types(order) == ["소비자_기만"]


def _root(info: str, name: str = "(주)신기한비누의 부당한 광고행위에 대한 건") -> ET.Element:
    r = ET.Element("FtcService")
    ET.SubElement(r, "사건명").text = name
    p = ET.SubElement(r, "피심정보")
    ET.SubElement(p, "피심정보내용").text = info
    ET.SubElement(r, "주문").text = ""
    ET.SubElement(r, "이유").text = ""
    return r


@pytest.mark.gate
def test_대표자_실명과_띄어_쓴_상호가_광고_문구에서_가려진다() -> None:
    """🔴 봉인 평가 9859 실측 — 「…김석호의 신기한 비누」가 그대로 나갔다 (D-258 집행)."""
    r = _root("주식회사 신기한비누\n서울시 강남구 신사동 528번지\n대표이사 김석호\n")
    _, bare = mask.anchor_ftc(r)
    assert bare.ceos == ("김석호",)
    got = mask.apply_policy("'씻으면 날씬해지는 김석호의 신기한 비누’", bare, "ftc")
    assert "김석호" not in got and "신기한 비누" not in got
    assert mask.MASK_CEO in got and mask.MASK_ORG in got


@pytest.mark.gate
def test_가려진_대표자와_성씨_아닌_말은_이름으로_받지_않는다() -> None:
    r = _root("주식회사 하늘하늘\n서울 송파구\n대표이사 ○○○, 이○○\n대표 서울\n")
    _, bare = mask.anchor_ftc(r)
    assert bare.ceos == ()


@pytest.mark.gate
def test_겹침_열쇠는_항목_번호_머리를_뗀다() -> None:
    assert golden.overlap_key("2) 피부보습에 도움을 줄 수 있음") == golden.overlap_key(
        "피부 보습에 도움을 줄 수 있음"
    )
    assert golden.overlap_key("1.5배 빠른") != golden.overlap_key("5배 빠른")


@pytest.mark.gate
def test_이전_판의_봉인을_지키고_빠진_것만_빠진다(monkeypatch) -> None:
    """🔴 뒷광고 문서가 빠져도 나머지 봉인은 그대로다 · 무혐의로 바뀐 봉인 문서는 적법 문구로 남는다."""

    def doc(i: str, t: list[str], ph: list[str], ok: list[str] = ()) -> dict:  # type: ignore[assignment]
        return {
            "doc_id": f"ftc:{i}",
            "원천": "ftc_decisions_body",
            "근거": [],
            "유형": t,
            "문구": ph,
            "문구_이유": [],
            "문구_적법": list(ok),
            "문구_이유_적법": [],
            "단위": "문장",
        }

    ftc = [doc(str(i), ["거짓_과장"], [f"문구{i}"]) for i in range(10)]
    ftc.append(doc("95", [], [], ["적법 문구"]))  # 이전 판에서 봉인 · 지금은 무혐의
    monkeypatch.setattr(split, "ftc_docs", lambda: ftc)
    # 🔄 2026-10-02 — 수정문구 판(`guide_fix_docs`)도 막는다 — 막지 않으면 기기의 실제 채택본(대기 0)이 평가로 섞인다
    for name in (
        "casebook_docs",
        "guide_docs",
        "cosmetic_docs",
        "ftc_press_docs",
        "guide_fix_docs",
        "caution_docs",
    ):
        monkeypatch.setattr(split, name, lambda: [])
    monkeypatch.setattr(split, "approved_docs", lambda: [])
    monkeypatch.setattr(split, "fingerprint", lambda: {})
    monkeypatch.setattr(split, "pending_guide", lambda: {})
    monkeypatch.setattr(split, "EVAL_TARGET", 3)
    prev = {"ftc:7", "ftc:8", "ftc:95", "ftc:gone"}
    m = split.plan(prev_sealed=prev)
    sealed = {k for k, v in m["assign"].items() if v == split.SEALED}
    assert {"ftc:7", "ftc:8", "ftc:95"} <= sealed, "🔴 이전 봉인이 다시 뽑혔다"
    assert len(sealed - {"ftc:95"}) == 3, "모자란 유형만 채운다"
    assert m["negatives"]["test_sentence_ftc적법"] == 1
    assert "ftc:gone" not in m["assign"]
    assert json.dumps(m, ensure_ascii=False)  # 직렬화된다


@pytest.mark.gate
@pytest.mark.parametrize(
    ("name", "text", "gone"),
    [
        (
            "(사)한국진주양식협회의 부당한 표시행위에 대한 건",
            "피심인 사단법인 한국진주양식협회는",
            "한국진주양식협회",
        ),
        (
            "학교법인 경동대학교의 부당한 광고행위에 대한 건",
            "피심인이 운영하는 경동대학교의 신입생",
            "경동대학교",
        ),
        (
            "케이제이아이대부금융(유)[구 케이제이아이파이낸스인터내셔널(유)]의 부당한 광고행위 관련 과징금 재산정의 건",
            "케이제이아이파이낸스인터내셔널이 광고하였다",
            "케이제이아이파이낸스인터내셔널",
        ),
    ],
)
def test_비영리_법인격과_옛_이름도_앵커다(name: str, text: str, gone: str) -> None:
    """🔴 전수 탐침(8,272 문서) 실측 — 법인격이 앵커에 붙은 채 남아 본문의 맨 이름이 새었다(6611 · 8361 · 8405 · 8009)."""
    _, bare = mask.anchor_ftc(_root("", name))
    got = mask.apply_policy(text, bare, "ftc")
    assert gone not in got and mask.MASK_ORG in got
