"""인정 · 고시 문구 대조 — `app/claim_match.py` · `user._fixed_match_notes` (🆕 2026-10-14 ksr · D-341 결정 4).

★ 파생물(`data/derived/*.jsonl`)은 git 에 없다 — 테스트는 작은 목록을 임시 폴더에 만들어 쓴다.
"""

from __future__ import annotations

import json

import pytest

from app import claim_match as cm


def _write(d, name: str, rows: list[dict]) -> None:
    (d / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), "utf-8")


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    _write(
        tmp_path,
        "hf_gosi_claims.jsonl",
        [
            {
                "번호": "2-10",
                "원료명": "대두이소플라본",
                "기능성문구": "뼈 건강에 도움을 줄 수 있음",
                "시행": "현행",
            },
            {
                "번호": "2-2",
                "원료명": "홍삼",
                "기능성문구": "면역력 증진에 도움을 줄 수 있음",
                "시행": "현행",
            },
            {
                "번호": "2-2",
                "원료명": "홍삼",
                "기능성문구": "피로개선에 도움을 줄 수 있음",
                "시행": "현행",
            },
            {
                "번호": "1-15",
                "원료명": "칼슘",
                "기능성문구": "골다공증 발생 위험 감소에 도움을 줌",
                "시행": "현행",
            },
            {
                "번호": "2-49",
                "원료명": "키토산",
                "기능성문구": "식후 혈당상승 억제에 도움을 줄 수 있음",
                "시행": "2027-01-01",
            },
        ],
    )
    _write(
        tmp_path,
        "hf_api_labels.jsonl",
        [
            {
                "인정번호": "2024-19",
                "RAWMTRL_NM": "인지원료",
                "PRIMARY_FNCLTY": "(국문) · 노화로 인해 저하된 인지기능 개선에 도움을 줄 수 있음\n· 기억력 개선에 도움을 줄 수 있음(기타기능Ⅱ)\n(영문) · May help",
            }
        ],
    )
    _write(
        tmp_path,
        "mfds_hf_labels.jsonl",
        [
            {
                "인정번호": "제2015-1호",
                "원료명": "기관원료",
                "기능성문구": ["기관·기관지 상태(기침·가래 등) 개선에 도움을 줄 수 있음"],
            }
        ],
    )
    monkeypatch.setattr(cm, "DERIVED", tmp_path)
    cm.clear_cache()
    yield tmp_path
    cm.clear_cache()


def test_목록은_정본만_펼쳐_담고_시행_전_문구는_뺀다(catalog) -> None:
    texts = {o.text for o in cm.catalog()}
    assert "노화로 인해 저하된 인지기능 개선에 도움을 줄 수 있음" in texts  # 글머리 「·」를 갈랐다
    assert "기억력 개선에 도움을 줄 수 있음" in texts  # 꼬리표 「(기타기능Ⅱ)」를 뗐다
    assert (
        "기관·기관지 상태(기침·가래 등) 개선에 도움을 줄 수 있음" in texts
    )  # 낱말 안 가운뎃점은 안 가른다
    assert not any(t.startswith("기관에") for t in texts)
    assert not any("식후 혈당상승" in t for t in texts)  # 2027-01-01 시행 문구


@pytest.mark.parametrize(
    "text",
    [
        "뼈 건강에 도움을 줄 수 있음",
        "뼈건강에 도움을 줄 수 있습니다.",
        "“뼈 건강에 도움을 줄 수 있음”(기타기능Ⅱ)",
        "면역력 증진･피로개선에 도움을 줄 수 있음",  # 고시 묶음 표기
        "1) 면역력 증진에 도움을 줄 수 있음 2) 피로개선에 도움을 줄 수 있음",
        "골다공증 발생 위험 감소에 도움을 줌",  # 공식 문구가 원래 단정형
        "기관·기관지 상태(기침·가래 등) 개선에 도움을 줄 수 있음",
    ],
)
def test_공식_문구는_같음(catalog, text: str) -> None:
    assert cm.match(text, "건기식").state == "same"


@pytest.mark.parametrize(
    ("text", "official", "why"),
    [
        ("뼈 건강에 도움을 줌", "뼈 건강에 도움을 줄 수 있음", "assertive"),
        ("면역력 증진에 확실히 도움을 줍니다", "면역력 증진에 도움을 줄 수 있음", "emphasis"),
        (
            "인지기능 개선에 도움을 줄 수 있음",
            "노화로 인해 저하된 인지기능 개선에 도움을 줄 수 있음",
            "narrowed",
        ),
        ("면역력 증진 및 암 예방에 도움을 줄 수 있음", "면역력 증진에 도움을 줄 수 있음", "added"),
    ],
)
def test_바꾼_문구는_비슷함과_다른_점(catalog, text: str, official: str, why: str) -> None:
    r = cm.match(text, "건기식")
    assert r.state == "near"
    p = r.pieces[0]
    assert p.official.text == official
    assert why in p.why


def test_무관한_문구는_없음(catalog) -> None:
    r = cm.match("바삭한 식감의 그래놀라", "건기식")
    assert r.state == "none"
    assert r.pieces[0].shown == "바삭한 식감의 그래놀라"


def test_화장품은_목록이_없어_대조_못_함(catalog) -> None:
    r = cm.match("피부의 미백에 도움을 준다", "화장품")
    assert (r.state, r.reason) == ("unchecked", "no_list")


def test_목록_파일이_없으면_대조_못_함이지_없음이_아니다(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cm, "DERIVED", tmp_path / "없는곳")
    cm.clear_cache()
    try:
        r = cm.match("뼈 건강에 도움을 줄 수 있음", "건기식")
        assert (r.state, r.reason) == ("unchecked", "no_data")
    finally:
        cm.clear_cache()


def test_화면_안내는_분기마다_한_함수다(catalog) -> None:
    from app import reasons
    from app.routers import user as user_router

    same = user_router._fixed_match_notes("뼈 건강에 도움을 줄 수 있음", "hf_yes")
    assert [n["level"] for n in same] == ["match_same"]
    assert "대두이소플라본" in same[0]["text"]
    assert "확인하지 않았어요" in same[0]["text"]  # 제품의 인정 여부는 모른다고 적는다

    near = user_router._fixed_match_notes("뼈 건강에 도움을 줌", "hf_yes")
    assert [n["level"] for n in near] == ["match_near"]
    assert reasons.MATCH_WHY["assertive"] in near[0]["text"]
    assert "「뼈 건강에 도움을 줄 수 있음」" in near[0]["text"]

    none = user_router._fixed_match_notes("바삭한 그래놀라", "hf_yes")
    assert [n["level"] for n in none] == ["match_none"]

    cos = user_router._fixed_match_notes("피부의 미백에 도움을 준다", "cos_yes")
    assert cos == [{"level": "match_unchecked", "text": reasons.MATCH_NO_LIST}]

    # 고정 문구가 없는 분기 · 빈 문구는 안내가 없다
    assert user_router._fixed_match_notes("뼈 건강에 도움을 줄 수 있음", "food_no") == []
    assert user_router._fixed_match_notes("", "hf_yes") == []


def test_같은_문구의_원료를_모두_보이고_원재료가_다르면_알린다(catalog) -> None:
    # 「뼈 건강에 도움을 줄 수 있음」을 가진 원료가 둘이 되게 한 줄 더한다
    _write(
        catalog,
        "mfds_hf_labels.jsonl",
        [
            {
                "인정번호": "제2015-1호",
                "원료명": "기관원료",
                "기능성문구": ["기관·기관지 상태(기침·가래 등) 개선에 도움을 줄 수 있음"],
            },
            {
                "인정번호": "제2010-9호",
                "원료명": "뼈원료(제2010-9호)",
                "기능성문구": ["뼈 건강에 도움을 줄 수 있음"],
            },
        ],
    )
    cm.clear_cache()
    from app import reasons
    from app.routers import user as user_router

    n = cm.norm("뼈 건강에 도움을 줄 수 있음")
    assert [o.name for o in cm.owners()[n]] == [
        "대두이소플라본",
        "뼈원료",
    ]  # 고시형 먼저 · 괄호 꼬리 뗌

    same = user_router._fixed_match_notes(
        "뼈 건강에 도움을 줄 수 있음", "hf_yes", ["대두 추출물", "대두이소플라본"]
    )
    assert [x["level"] for x in same] == ["match_same"]
    assert "대두이소플라본(고시형 2-10) · 뼈원료(개별인정형 제2010-9호)" in same[0]["text"]

    other = user_router._fixed_match_notes("뼈 건강에 도움을 줄 수 있음", "hf_yes", ["칼슘"])
    assert [x["level"] for x in other] == ["match_other"]
    assert other[0]["text"].startswith(reasons.MATCH_OTHER.split("{")[0])
    assert "(칼슘)" in other[0]["text"]

    # 원재료를 안 적었으면 모른다 — 같음으로 그린다
    assert cm.fits(n, []) is None
    assert [
        x["level"]
        for x in user_router._fixed_match_notes("뼈 건강에 도움을 줄 수 있음", "hf_yes", [])
    ] == ["match_same"]


def test_카피_생성과_광고_생성_화면에_대조_안내가_붙는다(catalog, monkeypatch) -> None:
    """🔴 원재료 칸이 대조까지 닿는지 — 10-14 실제로 연결이 빠져 「다른 원료」 안내가 안 떴다."""
    from fastapi.testclient import TestClient

    from app.api import app
    from app.routers import copygen
    from app.routers import user as user_router

    monkeypatch.setattr(user_router, "_gen_gate", lambda *_a: None)
    monkeypatch.setattr(
        user_router, "_fixed_notes", lambda *_a: []
    )  # 따로 판정한 경고는 test_copygen 이 잰다
    monkeypatch.setattr(copygen, "off_reason", lambda: "테스트 — 엔진 끔")
    c = TestClient(app)
    base = {"category": "hf", "cert": "yes", "age": "all", "sex": "all", "name": "칼슘 정"}

    r = c.post(
        "/u/generate", data={**base, "ingredients": "칼슘", "fixed": "뼈 건강에 도움을 줄 수 있음"}
    )
    assert r.status_code == 200
    assert "gn-fixed-match_other" in r.text and "(칼슘)" in r.text

    r = c.post(
        "/u/generate",
        data={**base, "ingredients": "대두이소플라본", "fixed": "뼈 건강에 도움을 줌"},
    )
    assert "gn-fixed-match_near" in r.text and "「뼈 건강에 도움을 줄 수 있음」" in r.text

    monkeypatch.setattr(user_router, "_core_judge", lambda *_a, **_k: ("pending", None))
    r = c.post(
        "/u/compose",
        data={
            "ad_format": "상세페이지",
            "prompt": "하루 한 알. 뼈 건강에 도움을 줌",
            "branch": "hf_yes",
            "fixed": "뼈 건강에 도움을 줌",
        },
    )
    assert r.status_code == 200
    assert "cp-fixed-match_near" in r.text
