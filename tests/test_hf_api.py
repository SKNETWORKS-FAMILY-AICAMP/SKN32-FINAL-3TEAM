"""`preprocess.hf_api` — **축이 둘이라는 것**을 코드가 계속 기억하는가 (D-185).

🚨 이 파일이 막는 것은 「버그」가 아니라 **범주 오류**다. 2026-09-11 이전에는
   I-0040(업체 신고 현황)의 **표시 문구**를 I-0050(원료 대장)의 **인정 문구**와 같은
   파일에 「층: 2층 적법라벨 · 지위: 인정」으로 담았다. 둘 다 문자열이라 아무 데서도
   안 터졌고, 그래서 **테스트가 없으면 되돌아간다.**

⬜ 거버넌스 게이트 표시(`gate`)는 ①②③ 에만 붙인다 — 그 셋이 깨지면 적법/위법이
   뒤집히기 때문이다. 나머지는 정규화의 품질 문제라 붙이지 않는다 (D-89).
"""

from __future__ import annotations

import pathlib

import pytest

from preprocess import hf_api as H

OFF = (
    "(국문) 노화로 인해 저하된 인지기능 개선에 도움을 줄 수 있음\n· 기억력 개선에 도움을 줄 수 있음"
)


# ── ① 축이 섞이지 않는다 ────────────────────────────────────────────
@pytest.mark.gate
def test_관측_축은_적법라벨_파일로_가지_않는다() -> None:
    """🔴 산출 파일 이름이 축마다 다르다. 한 파일에 담으면 되돌아간 것이다."""
    assert H.OUT_OFFICIAL != H.OUT_OBSERVED
    assert H.OFFICIAL != H.OBSERVED


@pytest.mark.gate
def test_관측_행에는_지위가_붙지_않는다() -> None:
    """🚨 「지위: 인정」은 **인정 사실**이다. 업체가 그렇게 표시했다는 것과 다르다."""
    row = H.judge(
        {"인정번호_정규화": "9999-1", "원료명_정규화": "없는원료", "FNCLTY_CN": "무엇에 도움을 줌"},
        {},
    )
    assert "지위" not in row
    assert row["대조"] == "짝없음"


# ── ② 원료가 다르면 짝짓지 않는다 ──────────────────────────────────
@pytest.mark.gate
def test_번호가_같아도_원료가_다르면_짝짓지_않는다() -> None:
    """⛔ 실측 — 2007-10 은 I-0040 이 `글루코사민`, I-0050 이 `콩발효추출물` 이다.

    인정번호 단독으로 조인하면 **엉뚱한 원료의 문구가 근거로 붙는다.** 그리고 그때
    붙은 문구는 「정본과 다르다」가 아니라 **애초에 다른 물건**이다 (D-170).
    """
    idx = {
        "2007-10": [
            {
                "원료키": H.mtral_key("콩발효추출물(기능성원료인정제2007-10호)"),
                "문구": "당의 흡수를 억제하여 식후혈당을 건강하게 유지하는데 도움을 줄 수 있음",
                "원천": H.OFFICIAL,
            }
        ]
    }
    row = H.judge(
        {
            "인정번호_정규화": "2007-10",
            "원료명_정규화": H.mtral_key("글루코사민"),
            "FNCLTY_CN": "관절 및 연골 건강에 도움",
        },
        idx,
    )
    assert row["대조"] == "짝없음_원료불일치"
    assert row["번호충돌"] is True
    assert row["정본_문구"] is None


def test_원료명_꼬리는_짝짓기를_막지_않는다() -> None:
    """I-0050 은 원료명에 인정번호를 달아 적는다 — 떼지 않으면 **모든 짝이 불일치**다."""
    assert H.mtral_same(H.mtral_key("천마추출물"), H.mtral_key("천마추출물(제2024-19호)"))
    assert H.mtral_same(
        H.mtral_key("차조기등복합추출물"),
        H.mtral_key("차조기등복합추출물(기능성원료인정New제2007-13호)"),
    )


def test_그리스문자는_같은_원료다() -> None:
    """🚨 NFKC 가 안 바꾼다 — `β-glucan` 과 `b-glucan` 이 갈렸다 (2010-32)."""
    assert H.mtral_same(
        H.mtral_key("보리 베타글루칸 추출물(Barley β-glucan Extract)"),
        H.mtral_key("보리 베타글루칸 추출물(Barley b-glucan Extract)"),
    )


# ── ③ 인정 범위가 좁아진 것을 「같음」으로 세지 않는다 ─────────────
@pytest.mark.gate
def test_대상_한정이_빠지면_좁음이다() -> None:
    """🔴 2024-19 — 「**노화로 인해 저하된**」이 빠지고 항목 하나가 통째로 사라졌다.

    이것을 「같음」으로 세면 **인정 범위를 넘은 문구가 적법 근거가 된다.**
    """
    assert H.compare("인지기능 개선에 도움을 줌", OFF) == "좁음"
    assert H.assertive_gap("인지기능 개선에 도움을 줌", OFF) is True


def test_단정형은_범위와_다른_축이다() -> None:
    """⛔ 섞으면 둘 다 안 보인다 — 2024-19 는 좁으면서 **동시에** 단정형이다."""
    same_scope = "높은 혈중 콜레스테롤 수치 개선에 도움이 됩니다."
    official = "(국문) 높은 혈중 콜레스테롤 수치 개선에 도움을 줄 수 있음"
    assert H.compare(same_scope, official) == "같음"  # 범위는 같고
    assert H.assertive_gap(same_scope, official) is True  # 어미만 단정이다


def test_기전_한정이_빠지면_좁음이다() -> None:
    """2013-35 — 정본은 「**인터루킨 4 감소를 통한** 면역조절」이다."""
    assert (
        H.compare(
            "면역조절에 도움을 줄 수 있음(생리활성기능 2등급)",
            "(국문) 인터루킨 4 감소를 통한 면역조절에 도움을 줄 수 있음",
        )
        == "좁음"
    )


# ── 정규화가 헛 차이를 만들지 않는다 ───────────────────────────────
@pytest.mark.parametrize(
    ("observed", "official"),
    [
        (
            "체지방 감소에 도움을 줄 수 있습니다.",
            "(국문) 체지방 감소에 도움을 줄 수 있음 (영문) May",
        ),
        ("“관절건강에 도움이 될 수 있음(기타기능II)”", "(국문) 관절 건강에 도움을 줄 수 있음"),
        ("간 건강에 도움을 줄 수 있습니다.", "(국문) 간건강에 도움을 줄 수 있음"),
        (
            "1) 항산화에 도움을 줄 수 있음 2) 위점막을 보호하여 위건강에 도움을 줄 수 있음",
            "(국문) 항산화에 도움을 줄 수 있음(생리활성기능 2등급), "
            "위점막을 보호하여 위건강에 도움을 줄 수 있음",
        ),
    ],
)
def test_어미와_등급과_항목번호는_차이가_아니다(observed: str, official: str) -> None:
    """I-0040 은 표시체(`~있습니다`), I-0050 은 고시체(`~있음`)다 — 맞추지 않으면 43%만 같다."""
    assert H.compare(observed, official) == "같음"


def test_ㅂ니다도_개조식으로_낮춘다() -> None:
    """⛔ `습니다→음` 만 두었더니 「도움을 **줍**니다」(2004-2)가 「다름」으로 샜다."""
    assert H.claim_core("충치발생위험감소에 도움을 줍니다") == H.claim_core(
        "충치발생위험감소에 도움을 줌"
    )


def test_빈값과_대시는_문구없음이다() -> None:
    """🚨 I-0040 의 137행은 문구가 없다 — 「다름」으로 세면 경계 사례가 부풀어 오른다."""
    assert H.compare("", "(국문) 뼈 건강에 도움을 줄 수 있음") == "문구없음"
    assert H.compare("-", "(국문) 뼈 건강에 도움을 줄 수 있음") == "문구없음"


# ── ④ 적재기가 축을 다시 섞지 않는다 ───────────────────────────────
@pytest.mark.gate
def test_적재기가_관측_축을_product_fact_에_넣지_않는다() -> None:
    """🔴 `PRODUCT_FACT_SOURCES` 에 한 줄만 되붙이면 오늘 판정이 통째로 되돌아간다.

    ⛔ 2026-09-11 전수 검토에서 드러난 구멍이다 — 이 파일이 스스로 「테스트가 없으면
       되돌아간다」고 적어 놓고 **적재기 쪽에는 그 테스트를 안 붙였다.**
    🚨 `product_fact` 는 「**인정받은** 기능성 문구」이고 D-59 자격형 판정의 근거다.
       표시 문구가 거기 들어가면 **우리가 잡으려는 위반이 적법 근거가 된다.**
    """
    from scripts.load_db import PRODUCT_FACT_SOURCES

    assert H.OFFICIAL in PRODUCT_FACT_SOURCES, "정본 축이 빠지면 2층이 통째로 빈다"
    assert H.OBSERVED not in PRODUCT_FACT_SOURCES, (
        f"{H.OBSERVED} 는 업체 신고 현황이다 — 인정 사실이 아니므로 product_fact 에 오지 않는다 (D-185)"
    )


@pytest.mark.gate
def test_두_산출물이_같은_파일로_쓰이지_않는다(tmp_path: pathlib.Path, monkeypatch) -> None:
    """🚨 상수만 비교하면 **쓰는 쪽**이 한 파일에 둘 다 써도 통과한다.

    ⛔ 전수 검토가 지적한 그대로다 — `test_축이_섞이지_않는다` 는 이름 두 개만 봤다.
       여기서는 `_write()` 를 실제로 태워 **파일이 둘로 갈리는지**를 본다.
    """
    monkeypatch.setattr(H.store, "derived_dir", lambda _: tmp_path)
    monkeypatch.setattr(H.store, "stamp", lambda row, _src: row)
    a = H._write(H.OUT_OFFICIAL, [{"원천": H.OFFICIAL, "지위": "인정"}])
    b = H._write(H.OUT_OBSERVED, [{"원천": H.OBSERVED, "대조": "같음"}])
    assert a != b, "두 축이 같은 파일로 갔다 — D-185 이전으로 되돌아간 것이다"
    assert "지위" not in b.read_text(encoding="utf-8")
