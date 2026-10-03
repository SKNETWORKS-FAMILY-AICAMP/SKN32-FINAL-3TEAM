"""2021 사례집 라벨 시트 — 쪽 전사에서 규칙으로 뽑은 행 (2026-10-03 다시 씀 · 원장 10-03 ④)."""

from __future__ import annotations

import pytest

from scripts import casebook2021_sheet as sheet


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    if not sheet.PAGES.exists():
        pytest.skip("쪽 전사가 이 기기에 없다 — git 이 나르지 않는다(D-249) · 기기 축이다 (D-19)")
    got = sheet.rows()
    sheet.verify(got)
    return got


@pytest.mark.gate
def test_행은_화면_하나_요약_문장_하나다(rows: list[dict]) -> None:
    """🔴 광고사례는 화면 하나가 한 행이다 — 표시 조각으로 쪼개지 않는다 (팀장 판정 2026-10-03 (나))."""
    ads = [r for r in rows if r["블록"] == "광고사례"]
    assert len(ads) == sheet.EXPECTED["광고사례"]
    keys = [(r["쪽"], r["칸"]) for r in ads]
    assert len(set(keys)) == len(keys), "같은 쪽 · 칸이 두 행이다"
    assert all(r["화면글"] or r["식약처설명"] for r in ads)
    assert all(r["글"] and not r["화면글"] for r in rows if r["블록"] != "광고사례")


@pytest.mark.gate
def test_원본의_오타를_고치지_않는다(rows: list[dict]) -> None:
    """🔴 인쇄가 「관절언골」 · 「치내」 · 「수먼부족」이다 — 맞는 낱말로 고쳐 적으면 빨강."""
    text = "\n".join(r["글"] + r["대분류"] for r in rows)
    for typo, fixed in (
        ("관절언골", "관절연골 염증"),
        ("‘치내’", "‘치매’에 효능"),
        ("수먼부족", "‘수면부족’"),
    ):
        assert typo in text, typo
        assert fixed not in text, fixed


@pytest.mark.gate
def test_심의가_지운_글자는_적법글에_없다(rows: list[dict]) -> None:
    """🔴 53쪽 자율심의 칸 — 취소선이 그어진 줄이 적법 문구로 나가면 빨강 (팀장 판정 2026-10-03)."""
    ok = [r for r in rows if r["층"] == sheet.LAYER_2]
    assert len(ok) == sheet.EXPECTED[sheet.LAYER_2]
    edited = [r for r in ok if r["심의삭제"]]
    assert {r["쪽"] for r in edited} == {53}, "취소선이 있는 쪽이 달라졌다"
    assert sum(len(r["심의삭제"]) for r in edited) >= 4  # 취소선 네 곳 + 교정 네모
    for r in ok:
        assert not r["후보유형"], "적법 층에 유형이 붙었다"
        joined = "\n".join(r["적법글"])
        assert "⟦" not in joined
    for r in edited:
        fixed = [
            x for x in r["화면글"] if any(k in x["표시"] for k in (sheet.STRUCK, *sheet.MARKS))
        ]
        assert fixed and len(r["적법글"]) == len(r["화면글"]) - len(fixed), (r["쪽"], r["칸"])
        gone = {x["글"].replace("⟦", "").replace("⟧", "") for x in fixed}
        assert not gone & set(r["적법글"]), (r["쪽"], r["칸"])


@pytest.mark.gate
def test_쪽_전사는_git_이_나르지_않는다() -> None:
    """🔴 광고주 문구가 든 쪽 전사는 `data/` 아래에만 산다 — 공개 저장소에 올리지 않는다 (D-249 ⑥)."""
    assert sheet.PAGES.as_posix().startswith("data/derived/labels/")
    src = (sheet.ROOT / "scripts" / "casebook2021_sheet.py").read_text(encoding="utf-8")
    assert "⟦불" not in src and "#" + "다이어트" not in src  # 문구를 코드에 적지 않는다
    assert not (sheet.ROOT / "scripts" / "casebook2021_pages.json").exists(), (
        "쪽 전사가 scripts/ 에 있다"
    )


@pytest.mark.gate
def test_인용_상한은_조각마다_건다(rows: list[dict]) -> None:
    """🔴 표시 조각 · 화면 글 한 줄이 `PARAMS.quote_max_chars` 를 넘지 않는다 (D-249 ③)."""
    cap = sheet.PARAMS.quote_max_chars
    assert all(len(s) <= cap for r in rows for s in r["표시문구"])
    assert all(len(x["글"]) <= cap for r in rows for x in r["화면글"])
    assert all(r["길이"] == max((len(s) for s in r["표시문구"]), default=0) for r in rows)


@pytest.mark.gate
def test_사람_칸은_비어_있다(rows: list[dict]) -> None:
    """🔴 확정유형 · 붙인이 · 붙인날은 사람이 채운다 (D-66)."""
    assert not any(r["확정유형"] or r["붙인이"] or r["붙인날"] for r in rows)
    assert {r["원천"] for r in rows} == {sheet.SOURCE_ID}


def test_유형은_원천이_적은_호에서만_온다(rows: list[dict]) -> None:
    for r in rows:
        if r["근거법"] == sheet.D_AK:
            assert not r["후보유형"], "약사법 행에 식품 유형이 붙었다"
        if r["근거법"] == sheet.F and r["블록"] == "위반사례":
            assert r["후보유형"] == sheet.TYPE[r["호"]]


def test_겹친_표시는_바깥_것_하나다() -> None:
    assert sheet.spans("a ⟦b ⟦c⟧ d⟧ e ⟦f⟧") == ["b c d", "f"]
    with pytest.raises(sheet.SheetError):
        sheet.spans("⟦열고 안 닫음")
    with pytest.raises(sheet.SheetError):
        sheet.spans("닫기만⟧")


def test_보도일은_요약_문장_끝_괄호에서만_읽는다() -> None:
    assert sheet._dates("○ … 광고 (2021.9.9. 보도)") == "2021.09.09"
    assert sheet._dates("○ … 광고 (2021.9.29., 2021.10.22. 보도)") == "2021.09.29, 2021.10.22"
    assert sheet._dates("- … 판매 (2021. 1. 27 보도)") == "2021.01.27"
    assert sheet._dates("○ 보도일이 없는 문장 (참고)") == ""


def test_인용표현은_식약처가_따옴표나_세모로_든_것만이다() -> None:
    got = sheet.quoted(
        "○ ‘당뇨 간식’, ‘암 예방’ 등 광고",
        ["* (사례) 빵류에 “당뇨간식”, 등 표시", "* (사례) △불면증 △불면증을 완화하며"],
    )
    assert got == ["당뇨 간식", "암 예방", "당뇨간식", "불면증", "불면증을 완화하며"]
    # 따옴표도 △ 도 없는 나열은 쪼개지 않는다
    assert sheet.quoted("- 제품명 표시", ["* (사례) 365잠솔솔, 굿잠 감태추출물 등"]) == []


@pytest.mark.gate
def test_모든_글이_마스킹_정책을_지난다(rows: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 정책이 없으면 한 행도 내지 않고 멈춘다 (D-72) · 우리 쪽 가림 수가 줄면 이름이 되살아난 것이다 (D-17)."""
    from preprocess import mask

    assert sheet.SOURCE_ID in mask.POLICY
    blob = sheet.PAGES.read_text(encoding="utf-8")
    assert {k: blob.count(k) for k in sheet.EXPECTED_REDACTED} == sheet.EXPECTED_REDACTED
    monkeypatch.setattr(
        mask, "POLICY", {k: v for k, v in mask.POLICY.items() if k != sheet.SOURCE_ID}
    )
    with pytest.raises(mask.MaskPolicyError):
        sheet.rows()
