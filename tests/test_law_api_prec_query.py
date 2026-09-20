"""`collect.law_api` — 판례 질의 확장과 마약 사범 제외 (2026-09-18).

🚨 **네트워크를 쓰지 않는다.** `_in_domain` 은 사건명 문자열만 본다.
   사건명은 2026-09-18 시뮬레이션 출력(사용자 실행)에서 옮겼다. 마약 사범 사건명은
   출력에 번호 없이 계열로만 보였으므로 **계열 대표형**이다 — 실측 원문 그대로가 아니다.

지키는 것 —
   ① 「의약품관리법」 계열 마약 사범은 업종어(`의약품`)가 박혀 있어도 빠진다
   ② 「마약류」·「대마」가 사건명에 있어도 **건기식·화장품 사건은 남는다** (시뮬레이션의 오탈락 3건)
   ③ 새 질의 둘이 `QUERIES` 에 있다 — 후보 중 순증 0 인 것은 없다

🚨 게이트(`gate`)가 아니다 — 수집기 단위 테스트다 (D-89). 파생물을 안 읽어 어느 기기에서든 돈다.
"""

from __future__ import annotations

import pytest

from collect import law_api as L

#: 계열 대표형 — `의약품` 이 박혀 ② 업종어로 통과하던 마약 사범. 마지막은 원문 오타.
DRUG_CRIMES = (
    "향정신성의약품관리법위반",
    "습관성의약품관리법위반",
    "향정산성의약품관리법위반",
    "향정신성의약품관리법위반·대마관리법위반",
)

#: 시뮬레이션에서 「마약류」·「대마관리법」 을 넣었을 때 떨어진 **우리 사건** (번호는 판례일련번호).
KEEP = {
    "170437": "사기·마약류관리에 관한 법률 위반(향정)·약사법 위반·정신보건법 위반·"
    "건강기능식품에 관한 법률 위반",
    "170362": "사기·마약류관리에 관한 법률 위반(향정)·의료법 위반·정신보건법 위반·"
    "건강기능식품에 관한 법률 위반",
    "606509": "표준통관예정보고발급거부처분취소[칸나비디올(CBD)을 원료로 한 화장품이 "
    "「마약류 관리에 관한",
}

OLD_STRONG = tuple(w for w in L.EXCLUDE_STRONG if w != "의약품관리법")


@pytest.mark.parametrize("name", DRUG_CRIMES)
def test_의약품관리법_계열_마약_사범은_빠진다(name: str) -> None:
    """① — 업종어를 이기는 칸이어야 빠진다. `EXCLUDE_WORDS`(약한 칸)였다면 통과했다."""
    assert not L._in_domain(name)


@pytest.mark.parametrize("name", DRUG_CRIMES)
def test_반대대조_이전_제외어로는_마약_사범이_통과했다(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🚨 반대 대조 — 위 테스트가 제외어 덕분에 통과한다는 것을 보인다."""
    monkeypatch.setattr(L, "EXCLUDE_STRONG", OLD_STRONG)
    assert L._in_domain(name), "전제: 제외어 없이는 `의약품` 업종어로 통과한다"


@pytest.mark.parametrize("case_id", sorted(KEEP))
def test_마약류가_섞인_건기식_화장품_사건은_남는다(case_id: str) -> None:
    """② — 「마약류」·「대마관리법」 을 넣으면 이 셋이 떨어진다 (2026-09-06 「가처분」과 같은 과잉 제외)."""
    assert L._in_domain(KEEP[case_id])


@pytest.mark.parametrize("case_id", sorted(KEEP))
def test_반대대조_마약류를_넣으면_우리_사건이_떨어진다(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🚨 반대 대조 — ② 가 우연히 통과하는 것이 아님을 보인다. 넣지 않은 이유가 이것이다."""
    monkeypatch.setattr(L, "EXCLUDE_STRONG", (*L.EXCLUDE_STRONG, "마약류", "대마관리법"))
    assert not L._in_domain(KEEP[case_id])


def test_새_질의가_있고_순증_0_후보는_없다() -> None:
    """③ — 순증 0 으로 잰 후보가 다시 들어오면 검색만 늘고 더하는 것이 없다 (2026-09-06 교훈)."""
    assert {"의약품으로 오인", "질병의 치료"} <= set(L.QUERIES)
    zero = {
        "광고문구",
        "광고 문구",
        "과대광고",
        "허위광고",
        "기만적인 광고",
        "의약품으로 혼동",
        "암 치료",
        "질병의 예방",
        "효능",
        "부당광고",
    }
    assert not zero & set(L.QUERIES)
