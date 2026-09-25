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

from collect import registry
from preprocess.mask import (
    MARK_RE,
    MASK_ADDR,
    MASK_BRAND,
    MASK_CEO,
    MASK_ORG,
    MASKS,
    POLICY,
    POLICY_WORDS,
    Ledger,
    Trace,
    apply_policy,
    mask,
    mask_address,
    mask_brand,
    mask_org_foreign,
    mask_org_slots,
    mask_person,
    residue,
    strip_legal,
    to_natural,
    variants,
)

#: 정책 키의 원천 — `preprocess.mask.POLICY` 는 이것의 사본이다.
#: ⛔ 2026-09-08 에 `POLICY` 를 2종 → 5종으로 늘리면서 **이 표를 안 늘렸다.**
#:    이 테스트는 `sorted(POLICY)` 로 파라미터를 만드는데, 그날 돌린 것은
#:    `-m` 로 추린 38건이라 새 세 개가 **한 번도 안 돌았다.** 대조기를 늘리지 않으면
#:    대조가 늘지 않는다 — 오늘 하루의 주제 그대로다.
_REGISTRY_SOURCE = {
    "ftc": "ftc_decisions_body",
    "mfds_sanctions": "mfds_sanctions",
    "mfds_special_use_guide": "mfds_special_use_guide",
    "mfds_casebook": "mfds_casebook",
    "mfds_hf_ingredient_board": "mfds_hf_ingredient_board",
    "mfds_press": "mfds_press",
    "mfds_hf_ingredient": "mfds_hf_ingredient",
    "mfds_hf_individual": "mfds_hf_individual",
    "law_go_kr": "law_go_kr",
    "mfds_cgm_expc": "mfds_cgm_expc",
    "mfds_cosmetic_ad_qa": "mfds_cosmetic_ad_qa",
}


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
    # 🔄 2026-09-21 (전수 재검토) — `000` 규칙은 `mask_person` 에 있다(D-157). 위 `mask()` 는 그 규칙을 안 부른다 —
    #    그대로 두면 이 테스트는 무엇을 넣어도 통과한다. 사람 규칙으로도 같은 것을 잰다.
    out = mask_person(text)
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
    assert MASK_CEO in mask_person(redacted)


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
    out = mask_person(text)  # 🔄 D-157 — 사람은 이 함수가 한다
    assert name not in out
    assert MASK_CEO in out


def test_title_survives_the_name() -> None:
    """🚨 직함은 남긴다 — 지운 자국을 남겨야 다음 사람이 「여기 이름이 있었나」를 본다."""
    out = mask_person("대표이사 김창범")
    assert out == f"대표이사 {MASK_CEO}"


def test_name_list_is_masked_as_one() -> None:
    """「담당변호사 진종백, 김철수」처럼 이름이 나열된다 — 첫 하나만 지우면 안 된다."""
    out = mask_person("담당변호사 진종백, 김철수, 최영수")
    assert "김철수" not in out and "최영수" not in out


def test_judgment_vocabulary_after_a_title_survives() -> None:
    """🚨 성씨 목록을 쓰는 이유.

    직함만 보고 뒤 2~4자를 지우면 「대표자 **표시광고**」에서 **판정 어휘가 사라진다.**
    성씨는 열린 추측이 아니라 **닫힌 집합**이라 근거가 된다.
    """
    text = "대표자 표시광고에 관한 사항"
    assert mask(text, "") == text
    # 🔄 2026-09-21 (전수 재검토) — ⛔ 위 줄은 사람 규칙을 안 부르는 `mask()` 라(D-157 이후) **아무것도 안 쟀다.**
    #    실제로는 「표」가 성씨가 된 뒤(D-165) 「대표자 [대표]에 관한 사항」이 나오고 있었다. 사람 규칙으로 잰다.
    assert mask_person(text) == text


def test_ordinary_text_is_untouched() -> None:
    """양성 대조 — 마스킹이 멀쩡한 문장을 건드리면 그 실패는 **조용하다.**"""
    text = "체지방 감소에 도움을 줄 수 있음"
    assert mask(text, "오션유닛1") == text


# ─────────────────────────────────────────────────────────────
#  🚨 POLICY 는 레지스트리의 사본이다 — 두 번째 원본이 아니다 (D-54)
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("target", sorted(POLICY))
def test_policy_matches_the_registry(target: str) -> None:
    """🚨 **원장이 원본이고 코드가 사본이다.** 어긋나면 여기서 깨진다.

    레지스트리의 `masking:` 은 산문이라 기계가 못 읽는다. 그래서 코드에 표를 두되,
    그 표가 **원문과 같은 말을 하는지**를 검사한다. 두 곳에 같은 판정을 두면
    한 곳만 고치게 되고, 고쳐지지 않은 쪽이 실제로 도는 쪽일 수 있다 (D-99).

    🚨 `ftc` 의 `person` 은 예외다 — `masking:` 에 「대표자명」이라는 말이 없고
       대신 「원천이 이미 가려서 준다 — **그래도 우리 쪽 마스킹을 끄지 않는다**」가 있다.
       ⛔ 2026-09-06 에 내가 정확히 그 문장이 경고한 자리에 빠졌다 (가림 47.6% 를 보고
          「원천이 처리해 놓았다」로 읽음). 그래서 그 문장 자체를 검사한다.
    """
    spec = registry.spec(_REGISTRY_SOURCE[target])
    wording = str(spec.get("masking") or "")
    assert wording, f"{target} 에 masking 문언이 없다 — 레지스트리부터 채운다"

    for key, word in POLICY_WORDS.items():
        declared = key in POLICY[target]
        if target == "ftc" and key == "person":
            assert declared, "ftc 는 대표자명을 지운다 — 원천의 정책은 우리의 보장이 아니다"
            assert "원천의 정책이지 우리의 보장이 아니다" in wording
            continue
        # 🚨 **끈 것도 문언으로 증명한다.** 어떤 문언에는 「대표자명」이라는 낱말이
        #    들어 있지만 뜻은 반대다 — 「대표자명(person)은 **끈다**」.
        #    ⛔ 낱말만 세면 「지운다」와 「끈다」를 구별하지 못한다. 그래서 축을 끈 원천은
        #       **끈다고 적힌 문장**을 확인한다. 켤 때만 근거를 요구하고 끌 때는 안 하면,
        #       실수로 꺼진 축이 조용히 통과한다.
        #    🔄 2026-09-09 — 해설서 한 원천의 특례로 적어 두었더니 `mfds_press` 가
        #       같은 자리에 오면서 특례를 또 써야 했다. **두 번째면 규칙이다** — 원천
        #       이름을 빼고 「`<축>(<key>)은 끈다` 라고 적혀 있으면 끈 것」으로 일반화했다.
        #       다음 원천은 문언만 규약대로 적으면 여기를 안 고쳐도 된다.
        #    ⛔ 2026-09-09 — 이 자리를 `if not declared and …` 로 썼다가 **또 무력하게**
        #       만들었다. 문언에 「대표자명(person)은 끈다」가 있으면 낱말 「대표자명」도
        #       들어 있으므로, `person` 을 실수로 **켜 두어도** 아래 `word in wording` 이
        #       참이 되어 통과한다. 반대 대조를 돌려 보고서야 나왔다 (D-170 을 쓴 날에
        #       D-170 을 다시 밟았다). **끈다고 적혔으면 꺼져 있어야 한다**로 고쳤다.
        if f"{word}({key})은 끈다" in wording:
            assert not declared, (
                f"{target}: 레지스트리는 「{word}({key})은 끈다」인데 POLICY 는 켜 두었다 — "
                "원장이 원본이고 코드가 사본이다 (D-54 · D-99)"
            )
            continue
        assert declared == (word in wording), (
            f"{target}: POLICY 는 {key}={declared} 인데 레지스트리 masking 문언은 "
            f"{word!r} 를 {'포함' if word in wording else '미포함'} 한다"
        )


def test_brand_is_masked_for_ftc_but_not_for_mfds() -> None:
    """🚨 **원천마다 「상표」의 뜻이 다르다.** 레지스트리가 이미 다르게 적었다.

    ftc  「자신의 영업표지 '청년피자'를」        → 브랜드다. 지운다
    mfds 「(제품명 중) 혈압케어 … 정맥류 혈관」  → **위법 광고 문구다.** 남긴다
    """
    assert "brand" in POLICY["ftc"]
    assert "brand" not in POLICY["mfds_sanctions"]
    kept = apply_policy(
        "(제품명 중) 혈압케어 혈액 순환 정맥류 혈관, (관련태그) #혈압영양제",
        "오션유닛1",
        "mfds_sanctions",
    )
    for w in ("혈압케어", "정맥류", "#혈압영양제"):
        assert w in kept, f"{w!r} 가 사라졌다 — 1층 라벨의 증거다"


def test_brand_needs_the_context_word() -> None:
    """🚨 따옴표만 보고 지우면 **인용된 위법 문구가 사라진다.**

    결정문은 위법 광고도 따옴표로 인용한다(「'바르는게 운동입니다'」) — 그게 우리가
    가장 원하는 데이터다. 그래서 앞말(영업표지·상표…)을 요구한다.
    """
    quoted = "피심인은 '바르는게 운동입니다' 라고 광고하였다"
    assert mask_brand(quoted) == quoted
    assert MASK_BRAND in mask_brand("자신의 영업표지 '청년피자'를 사용하여")


def test_address_needs_more_than_a_province_name() -> None:
    """⬜ 「서울」 하나만 있는 자리는 안 건드린다.

    실측 잔여 상위가 「서울 1,622건」이었는데, 그중 상당수가 「**서울** 지역 시장에서」
    같은 자리다. 시·도 이름만 보고 지우면 문장이 무너진다.
    """
    assert mask_address("서울 지역 시장에서") == "서울 지역 시장에서"
    assert mask_address("서울 서대문구 연희동 81-32") == MASK_ADDR


def test_org_slot_keeps_the_particle() -> None:
    """⛔ 「(주)미래이엔지**에게**」를 「[업체] 」로 만들어 조사를 먹었다.

    🚨 판정 어휘는 아니지만 **필요 이상으로 지우는 실패는 조용하다** —
       오늘 `1,000만` 을 먹은 것과 같은 종류다.
    """
    assert mask_org_slots("(주)미래이엔지에게 위탁한") == f"{MASK_ORG}에게 위탁한"


def test_org_slot_catches_third_parties() -> None:
    """🚨 앵커가 못 잡는 제3자를 **이름과 무관하게** 잡는다 (6,244종의 답).

    🚨 다만 **반쪽이다** — 법인격 없이 쓴 두 번째 언급은 못 잡는다. 그것이 이 함수를
       `residual_orgs()` 와 **한 짝으로만** 쓰는 이유다.
    """
    out = mask_org_slots("원사업자인 케이티건설 주식회사가 수급사업자인 문원건설 주식회사에")
    assert "케이티건설" not in out and "문원건설" not in out
    assert mask_org_slots("문원건설에 직접 지급하여야") == "문원건설에 직접 지급하여야"


# ══ 외국 법인격 (2026-09-08) ═══════════════════════════════════════════
#
# 🚨 이 절이 지키는 것은 **계수기가 아니라 이름이 사라졌는가**이다.
#    첫 판은 잔여 계수 11→0 을 만들고도 「오션스카이 인터넷 인포메이션 [업체]」를 남겼다.
#    그래서 여기서는 전부 **이름 문자열이 없는지**로 확인한다.


def test_foreign_org_single_word() -> None:
    """한 어절 상호 — 앞말(역할명사)은 남는다."""
    out = mask_org_foreign("1· 피심인 구글 엘엘씨는 자신이 운영하는")
    assert "구글" not in out
    assert out.startswith("1· 피심인 ") and "는 자신이" in out


def test_foreign_org_multiword() -> None:
    """🚨 **여러 어절 상호.** 한 어절만 잡으면 이름이 남는다 — 그 실패를 막는 자리."""
    out = mask_org_foreign(
        "1) 오션스카이 인터넷 인포메이션 테크놀로지 프라이빗 리미티드 : 90,000,000원"
    )
    for frag in ("오션스카이", "인터넷", "인포메이션", "테크놀로지"):
        assert frag not in out, out
    assert out.startswith("1) ") and "90,000,000원" in out  # 항목번호·금액은 산다


def test_foreign_org_english() -> None:
    out = mask_org_foreign("Imabari Shipbuilding Co Ltd 와 AT&T Inc")
    assert "Imabari" not in out and "AT&T" not in out


def test_foreign_org_keeps_english_words() -> None:
    """🔴 **광고 문구를 먹지 않는다.** 「Limited Edition」의 Limited 는 법인격이 아니다.

    ⛔ 첫 판이 이것을 「[업체] Edition 출시」로 만들었다. 마스킹이 학습 입력을 먹는
       실패는 조용하다 — 개인정보가 남는 것과 달리 아무도 놀라지 않는다.
    ★ 규칙: 법인격은 상호의 **끝**에 온다. 뒤에 영문 낱말이 더 오면 법인격이 아니다.
    """
    for s in ("Summer Limited Edition 출시", "Incredible 효과", "Corporate 이미지"):
        assert mask_org_foreign(s) == s


def test_foreign_org_form_at_tail() -> None:
    """「… Corporation Singapore Pte」는 **끝의 Pte** 에서 걸린다 — 이름 전체가 사라진다."""
    assert "Hanwha" not in mask_org_foreign("Hanwha Energy Corporation Singapore Pte 는")


def test_foreign_org_one_char_token() -> None:
    """🚨 법인격 바로 앞 어절이 **1자**인 것 — 「샤오미 테크놀로지 **코** 엘티디」.

    2자를 요구했더니 이 문장이 통째로 안 걸렸다. **누락이 과잉삭제보다 조용하다.**
    """
    out = mask_org_foreign("구글 아시아 퍼시픽 피티이 엘티디")
    assert "구글" not in out and "퍼시픽" not in out


def test_foreign_org_keeps_lead_words() -> None:
    """앞말은 되돌린다 — 「중국의」·「및」·항목번호까지 먹으면 문장이 망가진다."""
    out = mask_org_foreign("중국의 샤오미 테크놀로지 코 엘티디 등이 있으며")
    assert out.startswith("중국의 ") and out.endswith(" 등이 있으며")
    assert "샤오미" not in out


# ══ 치환 원장 (D-144 · 2026-09-08) ═════════════════════════════════════


def test_log_does_not_change_output() -> None:
    """🔴 **켜는 것이 결과를 바꾸면 계측이 아니다.** 원장은 곁에서 적기만 한다."""
    text = "원사업자인 케이티건설 주식회사가 수급사업자인 문원건설 주식회사에 위탁하였다"
    log: list[dict] = []
    assert apply_policy(text, "", "ftc", log) == apply_policy(text, "", "ftc")
    # 🔄 2026-09-08 D-165 — `원문` 은 더 이상 담지 않는다. 개수와 규칙만 남는다.
    assert log and all({"규칙", "자리"} <= set(x) for x in log)
    assert all("원문" not in x for x in log)


def test_slot_prefix_keeps_particle_after_sign() -> None:
    """🔴 **조사를 회사명으로 먹지 않는다** — 치환 원장이 잡아낸 버그 (63건).

    ⛔ 「석정건설**(주)에게**」에서 기호 뒤 캡처가 「에게」를 이름으로 잡아
       「석정건설[업체]」가 됐다. 조사가 통째로 사라지고 이름은 남았다.
    🚨 `residual_orgs` 는 `_ONLY_PARTICLE` 로 이걸 걷어내고 있었다 —
       **세는 쪽만 고쳐 두면 지우는 쪽이 조용히 틀린다.**
    """
    assert mask_org_slots("석정건설(주)에게 위탁한") == f"{MASK_ORG}에게 위탁한"
    assert mask_org_slots("㈜미래이엔지에게 위탁한") == f"{MASK_ORG}에게 위탁한"


def test_apply_policy_wires_person() -> None:
    """🔴 **배선을 잠근다** — 함수가 있어도 `apply_policy` 가 안 부르면 소용없다.

    ⛔ 2026-09-08, `mask()` 에서 사람을 떼어내며 `_REDACTED_NAME` 줄을 **통째로 날렸다.**
       결과 문자열은 854/854 같았고 산출물도 627 그대로였다 —
       **치환 원장의 개수 하나(416 → 398)만 달랐다.** 그 하나를 안 좇았으면 놓쳤을 것이고,
       놓친 것은 **가려진 이름 18건이 안 지워진 채 나가는 일**이었다.
    ★ 그래서 단위 동작만이 아니라 **`apply_policy` 를 통해서도** 확인한다.
    """
    out = apply_policy("피심인 대표이사 000 및 대표이사 김창범", "", "ftc")
    assert "000" not in out and "김창범" not in out
    assert out.count(MASK_CEO) >= 2


def test_person_axis_is_separable() -> None:
    """🚨 `POLICY` 에 축이 있으면 **끌 수 있어야** 한다 (D-157).

    해설서처럼 원천이 **사람이 아닌 것**을 같은 기호로 가리는 자료가 있다 —
    「전문oo」(업체명) · 「모유분석 000건」(숫자). 거기서는 이 축이 오탐만 낸다.
    ⛔ 예전에는 `org` 를 켜면 `person` 이 **딸려 왔다** — 선언에 축이 있는데 코드가 안 따랐다.
    """
    text = "모유분석 000건"
    assert apply_policy(text, "", "mfds_sanctions") != text  # person 이 켜진 원천
    assert mask(text, "") == text  # 🚨 `mask()` 는 이제 사람을 건드리지 않는다


# ─────────────────────────────────────────────────────────────
#  🔴 치환 원장은 **개수**를 남기고 원문은 남기지 않는다 (D-165)
# ─────────────────────────────────────────────────────────────


def test_ledger_keeps_no_source_by_default() -> None:
    """🔴 ⛔ 2026-09-08 — `ftc_stage.jsonl` 에 실명·주소 원문이 416줄 들어 있었다.

    레지스트리 `masking:` 은 「원문 미보관 (D-17)」이라고 말하고 있었다.
    ★ 그냥 `list` 를 넘겨도 안전해야 한다 — **안전한 쪽이 기본값**이다.
    """
    for log in (Ledger(), []):
        mask_person("대표이사 김홍익을 고발한다", log)
        assert log, "원장이 비었다 — 개수는 남아야 한다"
        assert all("원문" not in r for r in log), f"원문이 남았다: {log}"
        assert all(r["규칙"] and r["자리"] for r in log)


def test_trace_is_the_only_way_to_see_the_source() -> None:
    """진단은 `Trace` 로만. 🚨 이 값을 파일로 쓰는 코드를 만들지 않는다."""
    log = Trace()
    mask_person("대표이사 김홍익을 고발한다", log)
    assert any(r.get("원문") for r in log)


def test_count_alone_catches_a_broken_rule() -> None:
    """★ 원문을 빼도 검출은 된다 — 2026-09-08 에 결손을 잡은 것은 **416 → 398 이라는 수**였다."""
    a, b = Ledger(), Ledger()
    mask_person("대표이사 김홍익을 고발한다", a)
    mask_person("대표이사 김홍익을 고발한다", b)
    assert len(a) == len(b)
    mask_person("추가로 대표이사 박철수도", b)
    assert len(b) > len(a)  # 규칙이 움직이면 수가 달라진다


def test_rare_surname_is_masked() -> None:
    """⛔ 「원」이 성씨 목록에 없어 「대표이사 **원호봉**을」이 산출물에 남아 있었다."""
    assert "원호봉" not in mask_person("피심인 및 대표이사 원호봉을 각각 고발한다")
    assert "구상모" not in mask_person("대표이사 구상모")


def test_widening_surnames_does_not_eat_form_words() -> None:
    """🚨 「대표자 **성명**」의 「성」은 실제 성씨다 — 넓히면 양식 문구가 지워진다.

    ⛔ 그래서 성씨 확장과 불용어는 **같이 가야 한다.** 하나만 하면 다른 쪽이 깨진다.
    """
    assert mask_person("대표자 성명 기재") == "대표자 성명 기재"
    assert mask_person("사장 에서 물러난") == "사장 에서 물러난"


def test_particle_survives_person_masking() -> None:
    """🔴 「대표이사 원호봉**을** 각각」이 「대표이사 [대표] 각각」이 되어 조사가 사라졌다.

    `_slot_sub` 가 업체 쪽에서 이미 고친 것과 **같은 버그**가 사람 쪽에 남아 있었다 (D-166).
    실측 — 직함+이름 12,754건 중 4자 850, 그중 끝이 조사인 것 291건.
    """
    assert mask_person("대표이사 원호봉을 각각 고발한다") == "대표이사 [대표]을 각각 고발한다"
    # 🚨 3자는 이름 그대로인 경우가 압도적이라(2자 616 · 3자 11,288 · 4자 850) 떼지 않는다
    assert mask_person("대표이사 김홍익") == "대표이사 [대표]"


def test_marks_have_one_source() -> None:
    """⛔ `ftc_extract._MARK` 가 자국 꼴을 **따로** 들고 있었다 — 표기를 바꾸면 조용히 어긋난다."""
    from preprocess.ftc_extract import _MARK  # noqa: PLC0415

    assert _MARK is MARK_RE
    assert all(MARK_RE.fullmatch(m) for m in MASKS)


def test_natural_form_is_one_way_only() -> None:
    """🔴 저장은 자국으로, 내보낼 때만 `○` 로 (D-166).

    ⛔ 자국 자체를 `○` 로 바꿔 봤다가 되돌렸다 — 원천이 **숫자·URL 도** ○ 로 가려서
       (「○○○km」·「www.○○○○.com」) 계수기가 우리 자국과 구분하지 못했다.
    ★ 한 방향으로만 간다. 되돌릴 수 없으므로 **정보가 많은 쪽으로 저장한다** (D-152 와 같은 모양).
    """
    assert to_natural("피심인 [업체] 및 대표이사 [대표]을") == "피심인 ○○○○ 및 대표이사 ○○○을"
    # 🚨 원천이 가린 ○ 는 건드리지 않는다 — 우리 자국만 바꾼다
    assert to_natural("1회 충전으로 ○○○km 이상") == "1회 충전으로 ○○○km 이상"


# ══════════════════════════════════════════════════════════
# 2026-09-19 — 반출 검사 실측에서 나온 셋 (이름은 가짜로 바꿨다)
# ══════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "text",
    [
        "다이사이클로펜타다이엔/t-부틸크레솔코폴리머",  # 성분명 안의 「이사」
        "냉장보관 상태로 검사장소까지 운반된 것이",  # 「검사장」
        "산업단지 내 공사장 인부와 공장 종업원",  # 「공사장」
        "이 사건 업소의 대표자이다.",  # 서술형 — 「이」가 성씨라 「이다」를 이름으로 읽었다
        "대외 영업을 담당하는 대표자이자 대표이사로",
        "분양받은 사람들이 이사하여 살 수 있도록",
        # 🔄 2026-09-21 — 앞붙이를 더하면서 새로 열릴 수 있는 자리 (반대 대조)
        "이사회 의결을 거쳐",
        "회사의 사내 이사회에서",
        "감사 결과를 통보했다",  # 「감사」 단독은 직함으로 보지 않는다
        # 🔄 2026-09-21 (전수 재검토) — 직함 뒤 **판정·서술 어휘**(성씨로 시작) · 구분자를 열며 생긴 자리
        "대표이사 고발 조치",
        "대표이사 지시로 작성",
        "대표이사 이상의 책임",
        "대표이사(이하 '갑')",
        "전무후무한 일",
    ],
)
def test_직함_규칙이_낱말_안쪽과_서술형을_사람으로_읽지_않는다(text: str) -> None:
    """⛔ 이것들이 `[대표]` 가 되면 성분명·판정 문장이 훼손된다 (D-157 · 과잉 삭제는 조용하다)."""
    from preprocess.mask import mask_person

    assert mask_person(text) == text


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("법인의 대표자 홍길동에게 확인서를", "법인의 대표자 [대표]에게 확인서를"),
        ("피심인대표이사김철수는", "피심인대표이사[대표]는"),  # 긴 직함은 붙여 써도 잡는다
        ("회장 박영수의 지시로", "회장 [대표]의 지시로"),  # 짧은 직함도 낱말 경계면 잡는다
        # 🔄 2026-09-21 (소성민 코드 리뷰 #2) — 합성 직함. ⛔ 09-19 경계가 앞붙이까지 막아 **실명이 남았다**(회귀)
        ("부사장 김철수는", "부사장 [대표]는"),
        ("부회장 김철수", "부회장 [대표]"),
        ("사내이사 김철수가", "사내이사 [대표]가"),
        ("이사장 김철수", "이사장 [대표]"),
        ("전무이사 김철수", "전무이사 [대표]"),
        ("상무이사 박영희", "상무이사 [대표]"),
        ("명예회장 정가나", "명예회장 [대표]"),
        ("피심인사내이사김철수는", "피심인사내이사[대표]는"),  # 두 글자 앞붙이는 붙여 써도 잡는다
        # 🔄 2026-09-21 (전수 재검토 C1) — 직함이 둘 이어지면 **뒤 직함 뒤가** 이름이다.
        #    ⛔ 「변」·「전」이 성씨라 「변호사」·「전무」를 이름으로 지우고 실명을 남겼다 — 판결문·결정문의 표준 표기
        ("원고 소송대리인 변호사 홍길동 외 1인", "원고 소송대리인 변호사 [대표] 외 1인"),
        ("이사 전무 김철수", "이사 전무 [대표]"),
        # 🔄 C2 — 직함과 이름 사이의 구분자 · 「및」 목록. ⛔ 전부 그대로 나갔다
        ("대표자 : 홍길동", "대표자 : [대표]"),
        ("대표이사(홍길동)", "대표이사([대표])"),
        ("대표이사, 홍길동", "대표이사, [대표]"),
        ("대표이사 김철수 및 박영희", "대표이사 [대표]"),
    ],
)
def test_직함_규칙이_실명은_여전히_지운다(text: str, want: str) -> None:
    """🔴 좁히면서 놓치지 않는가 — 반대 대조."""
    from preprocess.mask import mask_person

    assert mask_person(text) == want


def test_사건명_머리의_짧은_앵커를_지운다() -> None:
    """🔴 2자 앵커도 **사건명 머리**면 피심인이다 — 본문의 같은 말은 안 건드린다 (D-233)."""
    from preprocess.mask import mask

    assert mask("가나의 전자상거래소비자보호법 위반행위에 대한 건", "가나").startswith("[업체]의 ")
    assert mask("본문의 대상 상품", "대상") == "본문의 대상 상품"


def test_피심인_메일만_도메인을_지운다() -> None:
    """★ 팀장 판정 (2026-09-19) — 「피심인일 때만」. 제3자 메일은 그대로 둔다."""
    from preprocess.mask import mask

    s = (
        "피심인은 자신이 운영하는 사이버몰인 '가나다몰(GANADAMALL)'을 통해 판매하였다. "
        "영상을 CSCENTER@GANADAMALL.COM 으로 발송. 경쟁사 help@othershop.io"
    )
    out = mask(s, "가나다유통")
    assert "CSCENTER@[업체]" in out
    assert "help@othershop.io" in out, "제3자 메일을 지웠다 — D-233 범위를 넘었다"
    assert mask("영상을 CSCENTER@GANADAMALL.COM 으로", "가나다유통").endswith(
        "GANADAMALL.COM 으로"
    ), "피심인 것인지 모르는데 지웠다"


@pytest.mark.parametrize(
    ("text", "bare", "want"),
    [
        # 상호 안의 「의」 — `anchor_ftc` 는 첫 「의」에서 끊는다
        ("가나의 착한갈비의 가맹사업법 위반행위에 대한 건", "가나", "[업체]의 가맹사업법"),
        # 정규화가 마침표를 가운뎃점으로 바꾼 사건명
        ("D·M·I산업의 가맹사업법 위반행위에 대한 건", "D.M.I산업", "[업체]의 가맹사업법"),
        # 법인격 토막
        ("가나다(유)의 전자상거래소비자보호법 위반행위에 대한 건", "가나다", "[업체]의 전자상거래"),
        # 「위반행위」가 아닌 사건명
        ("가나의 지정자료 허위제출행위에 대한 건", "가나", "[업체]의 지정자료"),
    ],
)
def test_사건명_머리를_통째로_지운다(text: str, bare: str, want: str) -> None:
    """🔴 2026-09-19 재생성 뒤 실측 — 머리 일부가 남던 셋 (이름은 가짜로 바꿨다)."""
    from preprocess.mask import mask

    assert mask(text, bare).startswith(want), mask(text, bare)


def test_본문의_먼_사건명_꼴까지_먹지_않는다() -> None:
    """⛔ 머리 40자 · 뒤 6어절 제한 — 없으면 이유 문단이 통째로 `[업체]` 가 된다."""
    from preprocess.mask import mask

    body = (
        "가나 제품은 소비자에게 판매되었고 여러 사정을 종합하면 이 사건은 " * 3
        + "의 위반행위에 대한 건"
    )
    assert "소비자에게" in mask(body, "가나")


def test_병합_사건명의_뒤_피심인을_지운다() -> None:
    """🔴 2026-09-19 3차 실측 — 「…에 대한 건 및 X의 …」의 X 가 남았다 (이름은 가짜)."""
    from preprocess.mask import mask

    s = "가나건설의 부당한 공동행위에 대한 건 및 다라협회의 사업자단체 금지행위에 대한 건(병합)"
    out = mask(s, "가나건설")
    assert "다라협회" not in out and out.count("[업체]") == 2, out
    # 묶음 설명은 누구도 가리키지 않는다 — 두다
    s2 = "가나건설의 부당한 공동행위에 대한 건 및 2개 종계 판매사업자의 부당한 공동행위에 대한 건"
    assert "2개 종계 판매사업자" in mask(s2, "가나건설")


def test_행위가_아닌_사건명도_머리를_지운다() -> None:
    """「X의 지주회사 설립·전환신고 … 위반에 대한 건」 (2026-09-19 실측 꼴 · 이름은 가짜)."""
    from preprocess.mask import mask

    s = "가나의 지주회사 설립·전환신고 및 신고규정 위반에 대한 건"
    assert mask(s, "가나").startswith("[업체]의 지주회사")


def test_괄호_설명을_단_개인_피심인을_모두_지운다() -> None:
    """🔴 2026-09-19 5차 실측 꼴 (이름·집단은 가짜) — 괄호 안 「의 」에서 머리를 끊어 **둘째 사람의 실명**이 남았다.

    ⛔ 고치기 전 — 「[업체]의 전 동일인) 및 을○○(…)의 …」: 괄호 설명은 토막 나고 실명은 남았다.
    ★ 괄호 설명(「기업집단 「다라」의 전 동일인」)도 사람을 **특정한다** — 머리 통째로 지운다.
    """
    from preprocess.mask import mask

    s = (
        "김가나(상호출자제한기업집단 「다라」의 전 동일인) 및 이마바(상호출자제한기업집단 「다라」의 특수관계인)"
        "의 지정자료 허위제출행위에 대한 건"
    )
    out = mask(s, "김가나(상호출자제한기업집단 「다라」")
    assert out == "[업체]의 지정자료 허위제출행위에 대한 건", out


def test_앵커가_40자를_넘는_병합_사건명도_뒤_피심인까지_지운다() -> None:
    """🔴 2026-09-19 5차 실측 꼴 (47자 앵커 · 이름은 가짜) — 머리 한도에 걸려 뒤 협회가 남았다."""
    from preprocess.mask import mask

    a = "가나다라레미콘공업협동조합 및 마바사아자차카레미콘사업협동조합 및 타파하거너더레미콘조합"
    assert len(a) > 40
    s = f"{a}의 부당한 공동행위에 대한 건 및 러머버협회의 사업자단체 금지행위에 대한 건(병합)"
    out = mask(s, a)
    assert (
        out == "[업체]의 부당한 공동행위에 대한 건 및 [업체]의 사업자단체 금지행위에 대한 건(병합)"
    ), out


def test_앵커_뒤로는_여전히_40칸까지만_먹는다() -> None:
    """⛔ 한도를 앵커 길이만큼 늘렸지만 **앵커 뒤**는 그대로 40칸 — 본문 문단을 먹지 않는다 (반대 대조)."""
    from preprocess.mask import mask

    s = "가나 " + "제품은 여러 사정을 종합하면 판매된 " * 2 + "것의 위반행위에 대한 건"
    assert "종합하면" in mask(s, "가나")


# ─────────────────────────────────────────────────────────────
#  🆕 2026-09-19 (D-248) — 개인 피심인은 `[대표]` · law_go_kr 사람 축
# ─────────────────────────────────────────────────────────────


def _ftc_root(case: str, respondent: str):
    import xml.etree.ElementTree as ET

    root = ET.Element("PrecService")
    ET.SubElement(root, "사건명").text = case
    ET.SubElement(root, "피심정보내용").text = respondent
    return root


def test_개인_피심인은_대표로_찍힌다() -> None:
    """🔴 팀장 판정 — 개인이 피심인이면 자국이 `[업체]` 가 아니라 `[대표]` 다 (이름·집단은 가짜).

    ★ 사람인지는 원천이 정한다 — 피심정보내용의 **가려진 주민등록번호**가 붙은 이름만 사람이다.
    """
    from preprocess.mask import anchor_ftc, apply_policy

    case = (
        "김가나(상호출자제한기업집단 「다라」의 전 동일인) 및 이마바(상호출자제한기업집단 「다라」의 특수관계인)"
        "의 지정자료 허위제출행위에 대한 건"
    )
    who = (
        "1. 김가나(******-*******, 상호출자제한기업집단 「다라」의 전 동일인) 서울 ** "
        "2. 이마바(******-*******, 상호출자제한기업집단 「다라」의 특수관계인) 서울 **"
    )
    _, bare = anchor_ftc(_ftc_root(case, who))
    assert bare.people == ("김가나", "이마바")
    assert apply_policy(case, bare, "ftc") == "[대표]의 지정자료 허위제출행위에 대한 건"
    # 본문의 맨몸 언급도 — 조사는 남는다
    body = "피심인 이마바는 김가나의 혈족이다."
    assert apply_policy(body, bare, "ftc") == "피심인 [대표]는 [대표]의 혈족이다."


def test_법인_피심인은_그대로_업체다() -> None:
    """반대 대조 — 주민등록번호 표지가 없으면 사람으로 보지 않는다 (추측하지 않는다)."""
    from preprocess.mask import anchor_ftc, apply_policy

    case = "주식회사 가나다의 부당한 광고행위에 대한 건"
    _, bare = anchor_ftc(_ftc_root(case, "주식회사 가나다 서울 ** 대표이사 ○○○"))
    assert bare.people == ()
    assert apply_policy(case, bare, "ftc").startswith("[업체]의 부당한 광고행위")


def test_개인_이름은_낱말_안에서_지우지_않는다() -> None:
    """🚨 두 글자 이름이 보통명사 안에서 지워지면 판정 어휘가 사라진다 (가짜 이름)."""
    from preprocess.mask import Anchor, mask

    out = mask("이수 과정을 마친 이수는 교육이수증을 받았다", Anchor("", ("이수",)))
    assert out == "[대표] 과정을 마친 [대표]는 교육이수증을 받았다", out


@pytest.mark.parametrize(
    "body",
    [
        "피심인 김가나로부터 자료를 제출받았다",  # 로(부터)
        "김가나만 이를 알고 있었다",  # 만
        "김가나까지 포함하면",  # 까지
        "김가나에게 통지하였다",  # 에게
        "김가나씨는 대표이다",  # 씨
        "김가나께서 답하였다",  # 께(서)
        "김가나라는 사람이",  # 라는
    ],
)
def test_개인_피심인_이름은_어떤_조사_앞에서도_남지_않는다(body: str) -> None:
    """🔴 2026-09-21 — 조사 목록이 세 벌이던 때 「로·만·까지·에게·씨」 앞의 실명이 **그대로 남았다.**

    ⛔ 직함이 없으니 `_TITLED_PERSON` 도, 반출 검사(개인식별)도 못 잡는 자리다. 여기서만 잡힌다.
    """
    from preprocess.mask import Anchor, mask

    out = mask(body, Anchor("", ("김가나",)))
    assert "김가나" not in out and "[대표]" in out, out


def test_지우는_쪽_조사는_세는_쪽_조사를_모두_안다() -> None:
    """🔴 D-99 — 세는 쪽(`_PARTICLE`)이 아는 조사를 지우는 쪽(`_mask_people`)이 모르면 실명이 샌다.

    반대 방향(지우는 쪽이 더 넓음)은 허용한다 — 사람 뒤에만 붙는 호칭(`씨`·`님`)이 있다.
    """
    from preprocess import mask as m

    tail = set(m._NAME_TAIL.split("|"))
    assert set(m.PARTICLES) <= tail, sorted(set(m.PARTICLES) - tail)
    for p in m.PARTICLES:
        assert m._PARTICLE.search("가나다" + p), p  # 세는 쪽도 같은 표에서 온다


def test_앵커는_문자열처럼_쓰인다() -> None:
    """`Anchor` 는 `str` 이다 — 기존 호출부(비교·포함·길이)가 그대로 돈다."""
    from preprocess.mask import Anchor

    a = Anchor("가나다", ("김가나",))
    assert a == "가나다" and "나" in a and len(a) == 3 and isinstance(a, str)


def test_law_go_kr_는_사람만_가리고_업체는_둔다() -> None:
    """🔴 2026-09-19 반출 검사 실측 꼴 (이름·상호는 가짜) — 재결례의 「법인의 대표자 손○○」.

    ★ 업체명·처분청은 공표된 판단문의 일부라 **남긴다** — 5층 반례의 값이다.
    """
    from preprocess.mask import apply_policy

    s = "2015. 8. 7. 법인의 대표자 김가나에게 확인서를 징구한 주식회사 다라마 및 ○○시장"
    out = apply_policy(s, "", "law_go_kr")
    assert "김가나" not in out and "[대표]에게" in out, out
    assert "주식회사 다라마" in out and "○○시장" in out, out


def test_판례_재결례는_텍스트_칸만_마스킹한다(tmp_path) -> None:
    """`law_case.parse` — 텍스트 칸만 `apply_policy` 를 지나고 식별 칸은 그대로다 (가짜 값)."""
    from preprocess import law_case

    xml = (
        "<PrecService><행정심판례일련번호>1</행정심판례일련번호><사건명>영업정지처분 취소청구</사건명>"
        "<처분청>가나시장</처분청><이유>법인의 대표자 김가나에게 확인서를 징구하였다</이유></PrecService>"
    )
    p = tmp_path / "decc_1.xml"
    p.write_text(xml, encoding="utf-8")
    row = law_case.parse(p, "decc")
    assert "김가나" not in row["이유"] and "[대표]" in row["이유"], row["이유"]
    assert row["처분청"] == "가나시장"


def test_ftc_정책으로_가리는_호출부는_앵커를_싣는다() -> None:
    """🔴 2026-09-21 (D-248) — `"ftc"` 정책은 앵커(`anchor_ftc` 의 알맹이)가 있어야 사건명 머리·개인 피심인
    축이 돈다. `apply_policy(x, "", "ftc")` 는 **예외 없이 그 축을 끈다** — `endorse_scan` 이 그렇게 돌았다.

    ★ 정책 키가 이름(`MASK_KEY`)으로 와도 모듈을 import 해 값을 읽는다 — 글자만 보면 못 잡는다.
    """
    import ast
    import importlib
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    bad: list[str] = []
    for path in sorted((root / "preprocess").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mod = None
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", getattr(node.func, "attr", None)) == "apply_policy"
                and len(node.args) >= 3
            ):
                continue
            bare, key = node.args[1], node.args[2]
            if not (isinstance(bare, ast.Constant) and bare.value == ""):
                continue
            if isinstance(key, ast.Constant):
                val = key.value
            elif isinstance(key, ast.Name):
                mod = mod or importlib.import_module(f"preprocess.{path.stem}")
                val = getattr(mod, key.id, None)
            else:
                val = None  # 식으로 오는 키(`policy_source(…)`)는 그 함수가 ftc 를 거부한다 (evasion_scan)
            if val == "ftc":
                bad.append(f"{path.name}:{node.lineno}")
    assert not bad, f"🔴 앵커 없이 ftc 정책으로 가린다 — 개인 피심인·사건명 축이 꺼진다: {bad}"


def test_반대_대조_앵커_없는_ftc_호출을_잡는다() -> None:
    """위 게이트가 실제로 실패할 수 있는가 — 종전 `endorse_scan` 모양을 가짜 모듈로 세워 본다 (D-170)."""
    import ast

    src = 'MASK_KEY = "ftc"\ndef f(q):\n    return apply_policy(q, "", MASK_KEY)\n'
    tree = ast.parse(src)
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "apply_policy"
    ]
    assert calls and isinstance(calls[0].args[1], ast.Constant) and calls[0].args[1].value == ""
    assert isinstance(calls[0].args[2], ast.Name) and calls[0].args[2].id == "MASK_KEY"


# ─────────────────────────────────────────────────────────────
#  🆕 2026-09-22 — 앵커가 놓친 피심인: 본문이 「피심인 X」라 부르고 피심정보내용의 이름 자리에도 X (이름은 가짜)
# ─────────────────────────────────────────────────────────────
def _ftc_full(case: str, info: str, order: str, reason: str = ""):
    import xml.etree.ElementTree as ET

    root = ET.Element("PrecService")
    for tag, text in (("사건명", case), ("피심정보내용", info), ("주문", order), ("이유", reason)):
        ET.SubElement(root, tag).text = text
    return root


def test_표지_없는_피심인도_원천이_두_번_적었으면_가린다() -> None:
    """🔴 09-22 반출 검사 실측 — 주민번호 표지 없는 개인 피심인 나열이 주문에 그대로 남았다."""
    from preprocess.mask import anchor_ftc, apply_policy

    order = "1. 피심인 안가나 및 피심인 김다라는 거짓으로 표시ㆍ광고하는 행위를 하여서는 아니된다."
    root = _ftc_full(
        "가나 외 1인의 부당한 표시ㆍ광고행위에 대한 건",
        "1. 안가나\n서울 중랑구 용마산로 1\n2. 김다라 경기 수원시",
        order,
        "피심인 김다라에게 통지하였다.",
    )
    _, bare = anchor_ftc(root)
    assert bare.named == ("안가나", "김다라")
    out = apply_policy(order, bare, "ftc")
    assert "안가나" not in out and "김다라" not in out, out
    assert out.startswith("1. 피심인 [업체] 및 피심인 [업체]는 거짓으로"), out
    assert (
        apply_policy("피심인 김다라에게 통지하였다.", bare, "ftc")
        == "피심인 [업체]에게 통지하였다."
    )


def test_이름_자리에_없는_말은_피심인으로_보지_않는다() -> None:
    """반대 대조 — 보통명사 · 주소 머리 · 정보칸 **가운데**에만 있는 말은 가리지 않는다."""
    from preprocess.mask import anchor_ftc, apply_policy

    reason = "피심인 주장에 대하여 본다. 피심인 서울 사무소와 피심인 강남 지점은"
    root = _ftc_full(
        "주식회사 가나의 부당한 광고행위에 대한 건",
        "주식회사 가나\n서울 강남 테헤란로 1\n대표이사 ○○○",
        "피심인은 …",
        reason,
    )
    _, bare = anchor_ftc(root)
    assert bare.named == ()
    assert apply_policy(reason, bare, "ftc") == reason


def test_사람_표지가_있으면_대표로_남는다() -> None:
    """주민번호 표지가 있는 이름은 `people`(`[대표]`)이 맡는다 — 이름자리 규칙이 `[업체]` 로 덮지 않는다."""
    from preprocess.mask import anchor_ftc, apply_policy

    root = _ftc_full(
        "김가나의 지정자료 허위제출행위에 대한 건",
        "1. 김가나(******-*******) 서울 **",
        "피심인 김가나는 …",
    )
    _, bare = anchor_ftc(root)
    assert bare.people == ("김가나",) and bare.named == ()
    assert apply_policy("피심인 김가나는 …", bare, "ftc") == "피심인 [대표]는 …"


# ─────────────────────────────────────────────────────────────
#  🆕 2026-09-22 — 선언이 「개인 실명」인 원천(law_go_kr)은 대표자 밖의 사람도 가린다 (이름은 가짜)
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("전전 조리실장(홍가나)은 이를", "전전 조리실장([대표])은 이를"),
        ("영업소 실장 김가나가 판매", "영업소 실장 [대표]가 판매"),
        ("○○개발 대표 조○나는", "○○개발 대표 [대표]는"),  # 부분 가림 — 두 글자가 드러났다
        ("청구인 김가○의 처는", "청구인 [대표]의 처는"),
    ],
)
def test_개인_실명_원천은_대표자_밖의_사람도_가린다(text: str, want: str) -> None:
    """🔴 09-22 반출 검사 실측 — 재결례에 「조리실장(실명)」·「대표 조○우」가 남았다. 레지스트리는 「개인 실명」이라 선언했다."""
    from preprocess.mask import apply_policy

    assert apply_policy(text, "", "law_go_kr") == want


@pytest.mark.parametrize(
    "text",
    [
        "팀장 지시로 판매하였다",  # 판정·서술 어휘
        "실장 이하 직원이",
        "부장 이상의 책임",
        "점장이나 실장이나 직원이",  # 09-22 탐침 실측 — 붙여 쓴 「이나」가 이름으로 걸렸다
        "대표 이○의 주장",  # 성만 드러난 가림 + 조사 — 특정 불가 · 조사를 먹지 않는다
        "대표 김○○는",  # 전부 가림은 원래 규칙(가려진이름)이 맡는다 — 결과만 본다
    ],
)
def test_넓은_규칙은_보통명사와_성만_남은_가림을_건드리지_않는다(text: str) -> None:
    from preprocess.mask import apply_policy

    out = apply_policy(text, "", "law_go_kr")
    assert out == text or out == text.replace("김○○", "[대표]"), out


def test_넓은_규칙은_선언한_원천에만_건다() -> None:
    """반대 대조 — 선언이 「개인 실명」인 원천(law_go_kr · 🔄 D-258 ftc)에만 건다. 사람 축을 끈 원천·다른 원천은 그대로."""
    from preprocess.mask import PERSON_ALL_NAMES, apply_policy

    assert sorted(PERSON_ALL_NAMES) == ["ftc", "law_go_kr"]
    text = "영업소 실장 김가나가 판매 · 허가나 원장"
    assert apply_policy(text, "", "mfds_sanctions") == text
    assert apply_policy(text, "", "mfds_press") == text  # 사람 축을 끈 원천 (09-09 판정)


# ─────────────────────────────────────────────────────────────
#  🆕 2026-09-22 D-258 — ftc 의 제3자 개인 · 이름이 직함 앞에 오는 꼴 (이름은 가짜)
# ─────────────────────────────────────────────────────────────
def test_광고_속_이름_직함_꼴을_가린다() -> None:
    """🔴 09-22 반출 검사 실측 — 의결서가 인용한 광고 문구 속 의사 셋이 골든셋까지 들어갔다."""
    from preprocess.mask import apply_policy

    text = "다인치과 임플란트센터 허가나 원장, 전다라 원장, 임마바 원장은"
    out = apply_policy(text, "", "ftc")
    assert out == "다인치과 임플란트센터 [대표] 원장, [대표] 원장, [대표] 원장은", out
    assert apply_policy("홍가나 교수님께 문의", "", "ftc") == "[대표] 교수님께 문의"
    assert apply_policy("영업소 실장 김가나가", "", "ftc") == "영업소 실장 [대표]가"


@pytest.mark.parametrize(
    "text",
    [
        "이러한 의사가 있었다",  # 「의사」 = 뜻 — 직함에서 뺐다
        "구매 팀장이 지시",  # 두 글자는 보지 않는다
        "한의원 원장이",  # 세 글자 보통명사 (불용어)
        "지금의 사장은",  # 셋째 글자가 조사
        "계정별 원장",  # 「계」는 성씨 목록 밖
        "소갑 제5호증 부장 진술조서",  # 09-22 ftc 탐침 — 증거 목록의 표준 꼴 (113개 문서)
        "팀장 진술서 및 실장 진술",
        "점장 신발장 정리",
        "결재 권한이 사장에게",
        "그 임원은 회장의 지시로",
    ],
)
def test_이름_직함_꼴은_보통명사를_건드리지_않는다(text: str) -> None:
    from preprocess.mask import apply_policy

    assert apply_policy(text, "", "ftc") == text


def test_이름_자리_밖의_피심인도_사람_꼴이면_가린다() -> None:
    """🔴 09-22 재측정 — 「피심인 [업체] 및 피심인 X」의 X 가 남았다. 피심정보내용에는 이름 자리 밖에 있었다(이름은 가짜)."""
    from preprocess.mask import anchor_ftc, apply_policy

    order = "1. 피심인 가나상사 및 피심인 김다은 판매하는 제품에 대하여"
    root = _ftc_full(
        "가나상사 외 1인의 부당한 광고행위에 대한 건",
        "1. 가나상사 서울 중랑구\n2. 진주상회(대표 김다) 경기 수원시",
        order,
    )
    _, bare = anchor_ftc(root)
    assert "김다" in bare.named, bare.named
    out = apply_policy(order, bare, "ftc")
    assert "김다" not in out, out


def test_이름_자리_밖의_말은_사람_꼴이_아니면_받지_않는다() -> None:
    """반대 대조 — 정보칸 가운데의 보통명사(성씨로 시작하지 않거나 불용어)는 피심인으로 보지 않는다."""
    from preprocess.mask import anchor_ftc

    root = _ftc_full(
        "주식회사 가나의 부당한 광고행위에 대한 건",
        "주식회사 가나 서울 강남 테헤란로 1 회사 대표이사 ○○○",
        "피심인 회사는 …",
        "피심인 주장에 대하여 본다.",
    )
    _, bare = anchor_ftc(root)
    assert bare.named == ()


def test_앞자리가_드러난_가림과_띄어_쓴_이름도_사람_표지다() -> None:
    """🔴 09-22 탐침(seq 7269 모양) — 「000000-0******」 가림 · 「가 나(…)」 띄어 쓴 이름. 둘째 피심인이 안 가려졌다 (이름·번호는 가짜)."""
    from preprocess.mask import anchor_ftc, apply_policy

    info = "가나다(900101-1******, 라마 대표)\n서울 중랑구 1\n김 다(910202-2******)\n경기 수원시 2"
    order = "1. 피심인 가나다 및 피심인 김다는 거짓으로"
    root = _ftc_full("가나다 외 1인의 부당한 광고행위에 대한 건", info, order)
    _, bare = anchor_ftc(root)
    assert "가나다" in bare.people and "김다" in bare.people, bare.people
    out = apply_policy(order, bare, "ftc")
    assert out == "1. 피심인 [대표] 및 피심인 [대표]는 거짓으로", out


def test_전부_숫자인_등록번호는_사람_표지가_아니다() -> None:
    """반대 대조 — 법인등록번호(전부 숫자)는 가림 표지가 아니다. 이름 앞 낱말 경계도 본다."""
    from preprocess.mask import respondent_people

    root = _ftc_full("x", "주식회사 가나(110111-1234567)\n대표 김다라(******-*******)", "x")
    assert respondent_people(root) == ("김다라",)
