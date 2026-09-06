"""`preprocess.mask` — [P3] 앵커 마스킹 (2026-09-06).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 셋이다.

  ① 앵커의 **모든 표기 변형**이 지워진다 — 긴 것부터 지워야 조각이 안 남는다
  ② **짧은 앵커는 안 지운다** — 「대한」을 전역 치환하면 「대한민국」이 [업체] 가 된다
  ③ 🚨 **판정 대상은 살아남는다** — 제품명·태그·수치. 지우면 1층 라벨이 사라진다

③이 이 모듈에서 가장 위험한 자리다. 마스킹은 **너무 많이 지워도** 실패인데,
그쪽 실패는 조용하다 — 개인정보가 남는 것과 달리 아무도 놀라지 않는다.
"""

from __future__ import annotations

import pytest

from preprocess.mask import MASK_CEO, MASK_ORG, mask, residue, strip_legal, variants


@pytest.mark.parametrize(
    ("raw", "bare"),
    [
        ("㈜비에스비푸드", "비에스비푸드"),
        ("주식회사 비에스비푸드", "비에스비푸드"),
        ("넥스큐브코퍼레이션㈜", "넥스큐브코퍼레이션"),
        ("넥스큐브코퍼레이션 주식회사", "넥스큐브코퍼레이션"),
        ("(주)담술", "담술"),
        ("농업회사법인 대한종합농산주식회사", "대한종합농산"),
        ("영원한 친구", "영원한 친구"),
    ],
)
def test_strip_legal(raw: str, bare: str) -> None:
    """실측된 상호들이다. 🚨 지어낸 예를 섞지 않는다."""
    assert strip_legal(raw) == bare


def test_variants_are_longest_first() -> None:
    """🚨 긴 것부터여야 한다.

    짧은 것을 먼저 지우면 `주식회사 [업체]` 가 남고, 남은 `주식회사` 가 다음 문서에서
    또 걸린다. 원문이 무엇이었는지도 알 수 없게 된다.
    """
    vs = variants("비에스비푸드")
    assert vs == sorted(vs, key=len, reverse=True)
    assert vs[-1] == "비에스비푸드"


# ─────────────────────────────────────────────────────────────
#  ① 모든 변형이 지워진다
# ─────────────────────────────────────────────────────────────

FTC_FORMS = [
    "피심인 주식회사 비에스비푸드는 …",
    "㈜비에스비푸드의 가맹사업법 위반",
    "비에스비푸드 주식회사가 제출한 자료",
    "비에스비푸드는 가맹본부에 해당한다",
    "(주)비에스비푸드 및 그 임직원",
]


@pytest.mark.parametrize("text", FTC_FORMS)
def test_every_form_is_masked(text: str) -> None:
    out = mask(text, "비에스비푸드")
    assert "비에스비푸드" not in out
    assert MASK_ORG in out


def test_no_leftover_fragment() -> None:
    """🚨 `주식회사 [업체]` 처럼 법인격만 남지 않는다 — 긴 변형이 통째로 지워진다."""
    assert mask("주식회사 비에스비푸드는", "비에스비푸드") == f"{MASK_ORG}는"


def test_residue_is_the_self_check(raw=None) -> None:
    """④ 검증 — 이 방법의 값. 남으면 실패이고 **몇 번인지 셀 수 있다.**"""
    text = "비에스비푸드와 비에스비푸드가"
    assert residue(text, "비에스비푸드") == 2
    assert residue(mask(text, "비에스비푸드"), "비에스비푸드") == 0


# ─────────────────────────────────────────────────────────────
#  ② 짧은 앵커는 안 지운다
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bare", ["순", "부영", "파란", "대상", "두산"])
def test_short_anchor_bare_form_survives(bare: str) -> None:
    """⬜ 실측 — 짧은 상호가 `mfds_sanctions` 346건(6.4%) · `ftc` 324건(3.9%).

    🚨 「**대상** 제품」·「검사 **대상**」·「**부영**양화」가 [업체] 가 되는 쪽이 더 나쁘다.
       맨 이름은 남기고 `--survey` 가 몇 번 남았는지 센다.
    """
    text = f"{bare}이라는 말이 든 문장"
    assert mask(text, bare) == text


@pytest.mark.parametrize("bare", ["대상", "두산"])
def test_short_anchor_with_legal_form_is_masked(bare: str) -> None:
    """🚨 짧아도 **법인격이 붙었으면 지운다** — 거기서는 상호인 것이 확실하다.

    ⛔ 첫 판은 짧은 앵커를 통째로 건너뛰었다. 그러면 `residue()` 도 0 이 나와
       **자기 채점이 꺼진다** — 「검사 안 함」이 「이상 없음」으로 보인다.
    """
    out = mask(f"㈜{bare}와 주식회사 {bare}가 검사 {bare}이다", bare)
    assert f"㈜{bare}" not in out
    assert f"주식회사 {bare}" not in out
    assert f"검사 {bare}" in out, "일반 명사 쪽은 살아야 한다"


def test_short_anchor_residue_is_counted() -> None:
    """🚨 못 지운 것을 **세지도 않는 것**이 제일 나쁘다.

    짧은 앵커의 잔여는 오탐이 섞인 수다 — 「검사 대상」의 「대상」도 세어진다.
    그래서 `survey()` 가 긴 앵커와 따로 보고한다. 여기서 확인하는 것은 **0 이 아니라는 것**.
    """
    masked = mask("㈜대상의 검사 대상 제품", "대상")
    assert masked == "[업체]의 검사 대상 제품"
    assert residue(masked, "대상") == 1  # 「검사 대상」의 것 하나 — 오탐이지만 **세어진다**


# ─────────────────────────────────────────────────────────────
#  ③ 🚨 판정 대상은 살아남는다 — 여기가 제일 위험하다
# ─────────────────────────────────────────────────────────────

#: 실측 — `mfds_sanctions` 오션유닛1 (처분일 20260902)
VIOLATION = (
    "건강기능식품으로 인식할 우려가 있는 표시 또는 광고"
    "[(제품명 중) 혈압케어 혈액 순환 정맥류 혈관, "
    "(관련태그) #혈압영양제 #항산화제 #고혈압 #저혈압 #건강기능식품]"
)


def test_product_name_and_tags_survive() -> None:
    """🚨 **이 제품명이 곧 위법 광고다.**

    처분 사유가 「제품명란과 태그에 기능성을 연상시키는 문구를 썼다」이므로,
    `[상표]` 로 가리면 **1층 라벨의 증거가 통째로 사라진다.**
    사양 [P3] 의 「상표 → [상표]」를 좁힌 근거가 이 문장이다.
    """
    out = mask(VIOLATION, "오션유닛1")
    for keep in ("혈압케어", "정맥류", "#혈압영양제", "#고혈압", "건강기능식품"):
        assert keep in out, f"{keep!r} 가 사라졌다 — 판정 대상이다"


def test_numbers_survive() -> None:
    """사양 1-4 — 수치는 판정 대상이다. 🚨 `000` 규칙이 숫자를 먹지 않는지 본다."""
    text = "영업정지 15일, 과징금 1,000만 원, 순도 100% 보장"
    out = mask(text, "오션유닛1")
    assert "15일" in out and "1,000만" in out and "100%" in out
    assert MASK_CEO not in out


# ─────────────────────────────────────────────────────────────
#  대표자명 — 가리는 것이 아니라 통일하는 것
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("redacted", ["대표이사 000", "대표이사 고ㅇㅇ", "변호사 조ㅇㅇ"])
def test_redacted_names_are_unified(redacted: str) -> None:
    """🚨 원천이 **이미 가려서** 준다. 표기가 둘이라 그대로 두면 같은 것이 두 토큰이 된다.

    실측 — `ftc/19353` 은 `000`, `ftc/19321` 은 `고ㅇㅇ`.
    """
    assert MASK_CEO in mask(redacted, "")


# ─────────────────────────────────────────────────────────────
#  🔴 원천이 늘 가려 주지는 않는다 — 직함 뒤 실명
# ─────────────────────────────────────────────────────────────

#: 실측 — `ftc` 결정요지에서 그대로 나온 문자열이다 (2026-09-06).
UNREDACTED = [
    ("주식회사 경기고속 광주시 송정동 222 대표이사 허명회", "허명회"),
    ("주식회사 덕화스포츠 서울 서대문구 연희동 81-32 대표이사 김창범", "김창범"),
    ("위 피심인의 대리인 서진법률사무소 담당변호사 진종백, 김철수", "진종백"),
]


@pytest.mark.parametrize(("text", "name"), UNREDACTED)
def test_unredacted_person_names_are_masked(text: str, name: str) -> None:
    """⛔ 가림 표기가 **47.6%** 에만 있었다. 나머지는 안 가려진 것이었다.

    🚨 숫자를 봤는데 뜻을 잘못 읽었다 — 「원천이 처리해 놓았다」로.
       회사명은 학습에 남으면 곤란한 정도지만 **개인 실명은 종류가 다르다** (D-17).
    """
    out = mask(text, "경기고속")
    assert name not in out
    assert MASK_CEO in out


def test_title_survives_the_name() -> None:
    """🚨 직함은 남긴다 — 지운 자국을 남겨야 다음 사람이 「여기 이름이 있었나」를 본다."""
    out = mask("대표이사 김창범", "")
    assert out == f"대표이사 {MASK_CEO}"


def test_name_list_is_masked_as_one() -> None:
    """「담당변호사 진종백, 김철수」처럼 이름이 나열된다 — 첫 하나만 지우면 안 된다."""
    out = mask("담당변호사 진종백, 김철수, 최영수", "")
    assert "김철수" not in out and "최영수" not in out


def test_judgment_vocabulary_after_a_title_survives() -> None:
    """🚨 성씨 목록을 쓰는 이유.

    직함만 보고 뒤 2~4자를 지우면 「대표자 **표시광고**」에서 **판정 어휘가 사라진다.**
    성씨는 열린 추측이 아니라 **닫힌 집합**이라 근거가 된다.
    """
    text = "대표자 표시광고에 관한 사항"
    assert mask(text, "") == text


def test_ordinary_text_is_untouched() -> None:
    """양성 대조 — 마스킹이 멀쩡한 문장을 건드리면 그 실패는 **조용하다.**"""
    text = "체지방 감소에 도움을 줄 수 있음"
    assert mask(text, "오션유닛1") == text
