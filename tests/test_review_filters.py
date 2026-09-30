"""골든셋 이유 거름 · 사례집 비광고 인용 (2026-09-30 · 판정 J3 (가) · J4 · J5 (가) · 원장 09-30 ⑦).

🔴 무엇을 막나
   ① 법 조문 · 절차 말(「제3조」 「피심인」 「과징금」)이 이유 문구로 학습에 들어가는 것 (J3 ㅂ)
   ② 원천이 가린 기호만 남은 문구(「▩▩▩▩」)가 들어가는 것 (J3 ㅅ)
   ③ 넷 이상 문서에 되풀이되는 정의 · 용어가 광고 문구처럼 들어가는 것 (J3 ㅇ)
   ④ 사례집의 원료명 · 체험기 주제어 · 사진 설명이 위반 문구로 들어가는 것 (J4)
   ⑤ 주입 규칙의 라벨 · 근거가 판정과 어긋나는 것 (J5)
"""

from __future__ import annotations

import pytest

from preprocess import golden, split


@pytest.mark.gate
@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("표시ㆍ광고의 공정화에 관한 법률 제3조 제1항", "ㅂ"),
        ("피심인은 이 사건 광고를 게재하였다", "ㅂ"),
        ("▩▩▩▩ ○○", "ㅅ"),
        ("<각주>3</각주>", "태그뿐"),
    ],
)
def test_이유_문구_중_법조문_절차_가림기호는_버린다(text: str, why: str) -> None:
    assert golden.reason_keep(text)[1] == why


@pytest.mark.gate
def test_광고_문구는_이유_거름을_지난다() -> None:
    assert golden.reason_keep("국내 판매 1위 공기청정기")[1] is None


@pytest.mark.gate
def test_넷_이상_문서에_되풀이되는_문구만_ㅇ으로_버린다() -> None:
    def d(i: int, ph: str) -> dict:
        return {"doc_id": f"ftc:{i}", "문구_이유": [ph]}

    docs = [d(i, "1) 일반 소비자의 인식") for i in range(4)] + [
        d(i, "가족 사건 카피") for i in range(10, 13)
    ]
    rep = golden.reason_repeats(docs)
    assert golden.reason_keep("일반 소비자의 인식", rep)[1] == "ㅇ"
    assert (
        golden.reason_keep("가족 사건 카피", rep)[1] is None
    )  # 🔴 셋은 남긴다(7023 · 7025 · 7029)


@pytest.mark.gate
@pytest.mark.parametrize(
    ("quote", "rec", "why"),
    [
        ("글루타치온", {"글": "‘글루타치온’, ‘타우린’의 효능·효과 표방", "호": 5}, "원료명"),
        ("코로나", {"글": "코로나 체험기 게시", "호": 5}, "체험기 주제어"),
        ("20대 [대표]님 체형 전·후 사진", {"글": "", "호": 5}, "사진 설명"),
        ("약", {"글": "집중력 높이는 ‘약’", "호": 2}, "한 글자 의약품 어휘"),
    ],
)
def test_사례집_비광고_인용은_뺀다(quote: str, rec: dict, why: str) -> None:
    assert split.casebook_not_ad(quote, rec) == why


@pytest.mark.gate
@pytest.mark.parametrize(
    ("quote", "rec"),
    [
        ("암", {"글": "암 예방", "호": 1}),  # 🔴 1호 질병명은 남긴다
        (
            "특허출원원료",
            {"글": "‘특허출원원료’의 효능·효과 표방", "호": 5},
        ),  # 🔴 원료명이 아니라 특허 주장
        ("면역력 증진에 탁월", {"글": "체험기 형식으로 면역력 증진에 탁월", "호": 5}),
    ],
)
def test_사례집_광고_표현은_남긴다(quote: str, rec: dict) -> None:
    assert split.casebook_not_ad(quote, rec) is None


@pytest.mark.gate
def test_주입_완치는_1호_단정은_3호_비교비방은_식품법이다() -> None:
    """🔴 판정 J5 (가) — 규칙이 곧 라벨이라 규칙표가 틀리면 주입 전량이 조용히 틀린다 (D-74)."""
    import random

    from collect import statute
    from preprocess import inject

    rules = {r[0]: r for r in inject.RULES}
    assert rules["T1"][2:] == ("건강기능식품_오인", "식품표시광고법 제8조제1항제3호")
    assert rules["T5c"][2] == "질병_예방치료_표방"
    assert rules["T7a"][3] == "식품표시광고법 제8조제1항제7호"
    assert rules["T7b"][3] == "식품표시광고법 제8조제1항제6호"
    for rid, _d, label, basis in inject.RULES:
        assert statute.types_of([statute.from_korean(basis)]) == [label], rid
    seen = set()
    for seed in range(40):
        for r in inject.transform("긴장완화에 도움을 줄 수 있음", random.Random(seed), ["비만"]):
            if r["rule_id"] in ("T5", "T5c"):
                word = r["문구"].split(" ")[0]
                assert (r["rule_id"] == "T5c") == (word == "완치"), r["문구"]
                seen.add(r["rule_id"])
    assert seen == {"T5", "T5c"}


# ── 판정 J1 (가) · (가-2′) — 승인 문구는 조건 A 3호 · 인정 조건문은 조건 D · V0 없음 ────────────


def _jsonl(p, rows) -> None:
    import json

    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )


@pytest.mark.gate
def test_승인_문구는_조건_A_3호_양성이고_음성이_아니다(tmp_path, monkeypatch) -> None:
    """🔴 「인정 제품」 전제로 적법에 두면 기록 판정이 보수 전제를 벗어난다 (D-263 ① · 원장 09-30 ⑫)."""
    from collect import statute

    hf = tmp_path / "hf.jsonl"
    _jsonl(hf, [{"기능성내용": "스트레스로 인한 긴장완화에 도움을 줄 수 있음"}])
    monkeypatch.setattr(split, "HF", hf)
    (d,) = split.approved_docs()
    assert d["조건"] == "A" and d["유형"] == ["건강기능식품_오인"]
    assert d["근거"] == [statute.food(3)]
    row = {"labels": d["유형"], "조건": d["조건"]}
    assert golden.is_positive(row) and not golden.is_negative(row)


@pytest.mark.gate
def test_인정_조건문은_조건_D_로_두_원천을_합치고_id_는_글자로_선다(tmp_path, monkeypatch) -> None:
    """🔴 주장이 없는 문장은 D 다(D-286 ③) — 음성(L)으로도 양성으로도 세지 않는다."""
    hf, api = tmp_path / "hf.jsonl", tmp_path / "api.jsonl"
    _jsonl(hf, [{"섭취주의사항": "① 임산부, 수유부는 섭취에 주의\n② 주의"}])
    _jsonl(
        api,
        [{"IFTKN_ATNT_MATR_CN": "임산부, 수유부는 섭취에 주의\n알레르기 체질은 섭취에 주의할 것"}],
    )
    monkeypatch.setattr(split, "HF", hf)
    monkeypatch.setattr(split, "HF_API", api)
    docs = split.caution_docs()
    texts = sorted(d["문구"][0] for d in docs)
    assert texts == ["알레르기 체질은 섭취에 주의할 것", "임산부, 수유부는 섭취에 주의"]
    by = {d["문구"][0]: d for d in docs}
    assert (
        by["임산부, 수유부는 섭취에 주의"]["원천"] == "mfds_hf_ingredient_board"
    )  # 겹치면 게시판이 남는다
    assert (
        by["알레르기 체질은 섭취에 주의할 것"]["원천"] == "mfds_hf_individual"
    )  # I-0050 정본 축 (D-185)
    for d in docs:
        row = {"labels": d["유형"], "조건": d["조건"]}
        assert d["조건"] == "D" and not golden.is_positive(row) and not golden.is_negative(row)
    # 원천 줄이 앞에 늘어도 id 가 안 밀린다
    _jsonl(
        hf,
        [
            {"섭취주의사항": "뜨거운 물과 섭취하지 말 것"},
            {"섭취주의사항": "임산부, 수유부는 섭취에 주의"},
        ],
    )
    again = {d["문구"][0]: d["doc_id"] for d in split.caution_docs()}
    assert again["임산부, 수유부는 섭취에 주의"] == by["임산부, 수유부는 섭취에 주의"]["doc_id"]


@pytest.mark.gate
def test_주입은_원본_V0_를_내지_않는다(tmp_path, monkeypatch) -> None:
    """🔴 V0 는 승인 문구 행과 같은 글자였다(97 × 2) — 규약 3 개정 (판정 J1 (가-2′))."""
    import json

    from preprocess import inject

    hf = tmp_path / "hf.jsonl"
    _jsonl(hf, [{"기능성내용": "긴장완화에 도움을 줄 수 있음"}])
    sp = tmp_path / "split.json"
    sp.write_text(json.dumps({"assign": {"hf:0:0": "train"}}), encoding="utf-8")
    monkeypatch.setattr(inject, "HF", hf)
    monkeypatch.setattr(inject, "SPLIT", sp)
    monkeypatch.setattr(inject.split_mod, "verify_inputs", lambda m, who: None)
    monkeypatch.setattr(
        inject,
        "split_approved",
        lambda: [{"doc_id": "hf:0:0", "문구": ["긴장완화에 도움을 줄 수 있음"]}],
    )
    monkeypatch.setattr(inject, "disease_terms", lambda: [])
    rows, _ = inject.build()
    assert rows and all(r["rule_id"] != "V0" and r["라벨"] for r in rows)


@pytest.mark.gate
def test_사전도_사례집_비광고_인용을_뺀다() -> None:
    """🔴 분할과 사전이 같은 함수를 쓴다 (D-99 · 판정 J4) — 원료명이 5호 단독판정 항목이 되면 안 된다."""
    import inspect

    from preprocess import dictionary

    assert "casebook_not_ad(" in inspect.getsource(dictionary.build)


@pytest.mark.gate
def test_인정_조건문_원천이_관측_축이면_멈춘다(tmp_path, monkeypatch) -> None:
    """🔴 I-0040(업체 신고 · 관측 축)을 인정 조건문으로 읽지 않는다 — 코드가 원천 이름을 붙이지 않는다 (D-185 · D-220)."""
    hf, api = tmp_path / "hf.jsonl", tmp_path / "api.jsonl"
    _jsonl(hf, [{"섭취주의사항": ""}])
    _jsonl(api, [{"원천": "mfds_hf_ingredient", "IFTKN_ATNT_MATR_CN": "임산부는 섭취에 주의할 것"}])
    monkeypatch.setattr(split, "HF", hf)
    monkeypatch.setattr(split, "HF_API", api)
    with pytest.raises(SystemExit, match="mfds_hf_individual"):
        split.caution_docs()
