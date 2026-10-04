"""판별 매뉴얼(2015) 추출기 — 반쪽 읽기 · 다섯 칸 · 목차 대조 · 사람 가림 (2026-10-03).

🚨 원문 PDF 는 저장소에 없다(CI) — 실제 문서에서 본 **모양**을 합성 글로 옮겨 대조한다. 이름은 전부 지어낸 것이다.
   실측(클론 B 원문 · 작업공간): 사례 80(식품 37 · 건강기능식품 28 · 축산물 15) · 처분 칸 65 · 목차 대조 통과 ·
   사람 가림 22 곳 · 남은 이름 후보 0 · 조각 203.
"""

from __future__ import annotations

import pytest

from preprocess import mfds_ad_manual as mm
from preprocess.mask import MASK_ADDR, MASK_CEO

TOC = "\n".join(
    [
        "개요 05",
        "위반 사례 및 적발 사례 21",
        "1. 식품 22",
        "2. 건강기능식품 64",
        "3. 축산물 94",
        "노인 대상 허위·과대광고(떴다방) 111",
        "1. 떴다방 영업 현황 및 허위·과대광고 112",
    ]
)
#: 🚨 실물처럼 표지의 띄어쓰기가 섞이고(「위반구분」 · 「위반 구분」), 문구가 줄을 넘는다
CASE_FOOD = "\n".join(
    [
        "▶ 위반구분 : 질병 치료•예방 효과 광고",
        "▶ 위반내용 : 제품이 혈액순환 등 질병에 효과가 있다고 광고",
        "▶ 광고매체 : 인터넷",
        "▶ 과대광고문구 : 피를 맑게하여 순환계에 도움이 됩니다.",
        "수면장애 등이 사라집니다.",
        "▶ 처분내용(근거) :영업정지[식품위생법 시행규칙 제8조(허위표시, 과대광고 및 과대포장의 범위)",
        "①항2호]",
        "26 MINISTRY OF FOOD AND DRUG SAFETY",
    ]
)
CASE_HF = "\n".join(
    [
        "●●● 허위•과대광고 판별 매뉴얼",
        "▶ 위반 구분 : 체험기 이용 광고",
        "▶ 위반 내용: 제품 체험 사례 이용 광고",
        "▶ 광고 매체: 신문",
        "▶ 과대광고 문구 : 1) 홍길동 (남, 63세) ... 통증이 사라졌습니다.",
        "▶ 처분내용(근거) : 영업정지[건강기능식품에 관한 법률 시행규칙 별표5 1호 나목]",
        "MINISTRY OF FOOD AND DRUG SAFETY 65",
    ]
)
#: 축산물 사례 — 처분 내용 없이 「▶ 처분 근거 :」만 있다(원천 15/15 건)
CASE_MEAT = "\n".join(
    [
        "▶ 위반 구분 : 허위 표시•광고",
        "▶ 위반 내용 : 인증을 받지 않은 제품을 인증받은 것처럼 광고",
        "▶ 광고 매체 : 인터넷",
        "▶ 과대광고 문구 : 무항생제 인증 마크 사용",
        "▶ 처분 근거 : 축산물 위생관리법 제32조 및 시행규칙 제52조 제1항 제14호 위반",
        "94 MINISTRY OF FOOD AND DRUG SAFETY",
    ]
)
HALVES = [
    (1, "L", ""),
    (2, "R", TOC),
    (14, "L", CASE_FOOD),
    (34, "R", CASE_HF),
    (48, "L", CASE_MEAT),
]


@pytest.mark.gate
def test_목차에서_사례_구역의_쪽_범위를_읽는다() -> None:
    assert mm.toc(HALVES) == {"식품": (22, 63), "건강기능식품": (64, 93), "축산물": (94, 110)}
    with pytest.raises(ValueError, match="목차"):
        mm.toc([(1, "L", "목차가 없는 글")])


@pytest.mark.gate
def test_사례는_다섯_칸으로_갈리고_구역과_쪽이_붙는다() -> None:
    rows, stat = mm.parse(HALVES)
    assert [(r["구역"], r["쪽"], r["면"]) for r in rows] == [
        ("식품", 26, "L"),
        ("건강기능식품", 65, "R"),
        ("축산물", 94, "L"),
    ]
    food = rows[0]
    assert food["위반구분"] == "질병 치료•예방 효과 광고"
    assert food["광고매체"] == "인터넷"
    # 🚨 줄을 넘은 문구가 이어지고, 바닥글은 처분 칸에 섞이지 않는다
    assert food["문구"] == "피를 맑게하여 순환계에 도움이 됩니다. 수면장애 등이 사라집니다."
    assert food["처분"] == "영업정지"
    assert food["처분근거"].endswith("①항2호") and "MINISTRY" not in food["처분근거"]
    assert rows[1]["처분근거"] == "건강기능식품에 관한 법률 시행규칙 별표5 1호 나목"
    assert all(not v for v in stat.values())


@pytest.mark.gate
def test_처분_칸이_없으면_판정지위를_지어내지_않는다() -> None:
    rows, _ = mm.parse(HALVES)
    assert rows[0]["판정지위"] == "행정처분" and rows[0]["기준시점"] == "2015-03"
    assert rows[2]["처분"] is None and rows[2]["판정지위"] is None  # D-220


@pytest.mark.gate
def test_처분_근거만_있는_사례는_근거가_문구에_섞이지_않는다() -> None:
    """🔴 축산물 사례의 「▶ 처분 근거 :」 줄 — 표지를 안 보면 근거가 광고 문구 끝에 붙는다 (실측 15/15)."""
    rows, _ = mm.parse(HALVES)
    meat = rows[2]
    assert meat["문구"] == "무항생제 인증 마크 사용"
    assert meat["처분근거"] == "축산물 위생관리법 제32조 및 시행규칙 제52조 제1항 제14호"
    assert meat["처분"] is None and meat["판정지위"] is None  # 처분 내용은 원천에 없다 (D-220)


@pytest.mark.gate
def test_겹쳐_찍힌_바닥글도_쪽_번호로_읽는다() -> None:
    assert mm.printed("글\n2222 MMIINNIISSTTRRYY OOFF FFOOOODD AANNDD DDRRUUGG SSAAFFEETTYY") == 22
    assert mm.printed("글\nMINISTRY OF FOOD AND DRUG SAFETY 2233") == 23
    # 🚨 두 자리 「22」는 겹친 2 가 아니라 22 다
    assert mm.printed("글\n22 MINISTRY OF FOOD AND DRUG SAFETY") == 22
    assert mm.printed("바닥글이 없는 쪽") is None


@pytest.mark.gate
def test_목차와_어긋나면_검증이_실패한다() -> None:
    assert mm.verify(HALVES) == []
    # 구역 밖 쪽 번호
    off = CASE_FOOD.replace("26 MINISTRY", "120 MINISTRY")
    assert any("구역_밖" in b for b in mm.verify([*HALVES[:2], (14, "L", off)]))
    # 칸이 빠진 사례 — 레코드로 내지 않고 검증이 멈춘다
    cut = CASE_FOOD.replace("▶ 광고매체 : 인터넷\n", "")
    rows, stat = mm.parse([*HALVES[:2], (14, "L", cut)])
    assert rows == [] and stat["칸_빠짐"]
    assert mm.verify([*HALVES[:2], (14, "L", cut)])
    # 한 면에 사례가 둘
    two = CASE_FOOD.replace("26 MINISTRY", CASE_MEAT.split("\n94 ")[0] + "\n26 MINISTRY")
    assert any("한_면에_여럿" in b for b in mm.verify([*HALVES[:2], (14, "L", two)]))


@pytest.mark.gate
@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("1) 홍길동 (남, 63세) ... 통증이", f"1) {MASK_CEO} (남, 60대) ... 통증이"),
        ("좋아졌다. (대구, 홍길순) 평소", f"좋아졌다. (대구, {MASK_CEO}) 평소"),
        ("생리통(홍길순,39세,어느마을) 손가락", f"생리통({MASK_CEO},30대,{MASK_ADDR}) 손가락"),
        # 🚨 PDF 가 이름 한가운데서 띈다
        ("혈액투석(홍 길순, 53세,한국서 울),", f"혈액투석({MASK_CEO}, 50대,{MASK_ADDR}),"),
        ("1) 김가짜(34세 가명/서울) 64kg", f"1) {MASK_CEO}(30대 가명/서울) 64kg"),
        ("방송, 박가짜씨. “먹으니", f"방송, {MASK_CEO}씨. “먹으니"),
        ("피부과 전문의 홍길동(간편하게", f"피부과 전문의 {MASK_CEO}(간편하게"),
        ("연구소 홍길동 박사는“버섯을", f"연구소 {MASK_CEO} 박사는“버섯을"),
        ("나을 수 있다. [N.W 워커박사]", f"나을 수 있다. [{MASK_CEO}박사]"),
    ],
)
def test_사람이_특정되는_자리를_가린다(raw: str, want: str) -> None:
    log: list[dict] = []
    assert mm.redact_people(raw, log) == want
    assert len(log) == 1 and log[0]["자리"] == MASK_CEO


@pytest.mark.gate
@pytest.mark.parametrize(
    "text",
    [
        "한의사, 교수 등을 내세워 효과가 입증",  # 직함의 나열
        "유명 의대교수를 홍보대사로",  # 「의대」는 이름이 아니다
        "효과(허위, 과장)가 있다",  # 지역이 아닌 나열
        "볶은 홍화씨 500g",  # 씨앗 — 두 글자 + 씨
        "어린이(10세 미만)에게",  # 성씨로 시작하지 않는다
        "노인들(65세 이상)에게",  # 성씨 글자로 시작하는 보통명사
    ],
)
def test_사람이_아닌_말은_건드리지_않는다(text: str) -> None:
    log: list[dict] = []
    assert mm.redact_people(text, log) == text
    assert log == []


@pytest.mark.gate
def test_남은_이름_후보는_가린_자리를_빼고_낸다() -> None:
    red = mm.redact_people("1) 홍길동 (남, 63세) 좋아졌다. 이웃 김씨도 45세에")
    got = mm.candidates(red)
    assert got and all(MASK_CEO not in c for c in got)
    assert any("45세" in c for c in got)
    assert any("김씨도" in c for c in got)  # 성씨 + 씨 + 조사 — 사람일 수 있다
    # 🔴 씨앗 이름은 후보가 아니다(기기 실행 2026-10-03 — 「볶은 홍화씨 500g」이 떴었다)
    assert mm.candidates("○○○○ 볶은 홍화씨 500g 포도씨유 해바라기씨 1kg") == []


@pytest.mark.gate
def test_마스킹_정책이_없으면_파생을_내보내지_못한다() -> None:
    """🔴 D-72 fail-closed — 2인 확인 전에는 `POLICY` 에 이 원천이 없고, `masked` 는 멈춰야 한다.

    정책이 등재되면 이 검사를 「정책대로 걸린다」로 바꾼다.
    """
    from preprocess.mask import POLICY, MaskPolicyError

    rows, _ = mm.parse(HALVES)
    if mm.SOURCE_ID in POLICY:
        out, _, _ = mm.masked(rows)
        assert MASK_CEO in out[1]["문구"]
        return
    with pytest.raises(MaskPolicyError):
        mm.masked(rows)
    # 사람 가림만 건 길은 정책 없이도 돈다(화면 확인용 · 파일로 내지 않는다)
    red, log = mm.redacted(rows)
    assert MASK_CEO in red[1]["문구"] and len(log) == 1


@pytest.mark.gate
def test_정책_마스킹이_사람_자국_뒤_괄호를_지우지_않는다() -> None:
    """🔴 `mask_paren_alias` 는 `[대표]` 뒤 괄호를 지운다 — 정책을 사람 가림보다 먼저 걸어 막는다 (원장 10-03 ㊿-10)."""
    from preprocess.mask import POLICY

    if mm.SOURCE_ID not in POLICY:
        pytest.skip("정책 등재 전 — 위 게이트가 지킨다")
    rows = [{"위반내용": "체험기 이용", "문구": "1) 가나다 (남, 63세) ... 3일째 좋아졌어요"}]
    out, _, log = mm.masked(rows)
    assert out[0]["문구"] == f"1) {MASK_CEO} (남, 60대) ... 3일째 좋아졌어요"
    assert "괄호원어" not in [x["규칙"] for x in log]
    red, _ = mm.redacted(rows)
    assert out == red  # 자리표(`pieces`)는 사람 가림만 건 글에 맞춰 굳혔다


@pytest.mark.gate
def test_보도_제목의_유명인_이름을_가린다() -> None:
    """성씨 규칙 밖의 이름(외국 이름) — 「이름 + 몸매 비결」 꼴 (원장 10-03 ⑪)."""
    log: list[dict] = []
    got = mm.redact_people("가나다 라 몸매 비결로 지목된 슈퍼푸드", log)
    assert got == f"{mm.MASK_CEO} 몸매 비결로 지목된 슈퍼푸드"
    assert [x["규칙"] for x in log] == ["유명인_이름"]


def _cut(text: str, at: tuple[int, ...]) -> dict[str, tuple[str, tuple[int, ...]]]:
    import hashlib

    return {"22L": (hashlib.sha256(text.encode()).hexdigest()[:12], at)}


@pytest.mark.gate
def test_조각은_자리표대로_잘리고_이으면_문구가_된다() -> None:
    text = "첫 문장입니다. 둘째 문장입니다."
    row = {"쪽": 22, "면": "L", "구역": "식품", "문구": text}
    got = mm.pieces([row], _cut(text, (9,)))
    assert [p["문구"] for p in got] == ["첫 문장입니다.", "둘째 문장입니다."]
    assert [p["조각"] for p in got] == [1, 2] and got[0]["조각수"] == 2
    # 지문은 글이 아니라 자리로 만든다 — 가림이 바뀌어도 같다
    assert got[0]["지문"] == mm.piece_id(22, "L", 1) and got[0]["지문"] != got[1]["지문"]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("row_text", "cut_text", "at", "why"),
    [
        ("문구가 바뀌었다.", "원래 문구였다.", (), "다르다"),
        ("짧은 문구.", "짧은 문구.", (99,), "문구 밖"),
        ("짧은 문구.", "짧은 문구.", (3, 3), "문구 밖"),
    ],
)
def test_자리표와_문구가_어긋나면_멈춘다(
    row_text: str, cut_text: str, at: tuple[int, ...], why: str
) -> None:
    """🔴 D-220 — 굳힌 자리가 다른 글자를 가리키면 조각을 내지 않는다."""
    row = {"쪽": 22, "면": "L", "구역": "식품", "문구": row_text}
    with pytest.raises(ValueError, match=why):
        mm.pieces([row], _cut(cut_text, at))


@pytest.mark.gate
def test_자리표에_없는_사례는_멈춘다() -> None:
    with pytest.raises(ValueError, match="자리표에 없는"):
        mm.pieces([{"쪽": 1, "면": "R", "구역": "식품", "문구": "글"}], {})


@pytest.mark.gate
def test_자리표는_사례_80_건_조각_203_개다() -> None:
    """자리표가 통째로 바뀌는 것을 잡는다 — 수는 원장 10-03 ⑪."""
    from preprocess.mfds_ad_manual_cuts import CUTS

    assert len(CUTS) == 80
    assert sum(len(at) + 1 for _, at in CUTS.values()) == 203
    assert all(list(at) == sorted(set(at)) and all(x > 0 for x in at) for _, at in CUTS.values())
