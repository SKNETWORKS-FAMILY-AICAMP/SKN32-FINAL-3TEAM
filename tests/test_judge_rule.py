"""판정 노드 1판 — 인코더 전 규칙 판정 (🆕 2026-10-01 · W4 · D-269 · D-127 · D-224 · D-273) 과 문장 분할 ([P4]).

🔴 무엇을 막나
   ① 사전을 **못 훑은** 문장이 보류 · 통과로 세어지는 것 — 못 본 것은 미판정이다 (D-220 · D-63)
   ② 사전의 **침묵**이 「특이사항 없음」이 되는 것 — 인코더 전에는 보류(확신 부족)다 (D-269)
   ③ 불가 사유를 못 정한 유형이 확정되는 것 — 보류다 (D-273 결정 3 · D-72)
   ④ 인용 좌표를 못 세운 확정 — 근거 없음이다 (D-224 · D-127)
   ⑤ 위험도(하한 · W5) 없는 확정 위반이 증명서 · 지시로 가서 계약에 걸리는 것 — 보류다 (D-268 막힘)
   ⑥ 분할이 글자를 바꿔 원문 좌표가 어긋나는 것 ([P4] · D-278)
"""

from __future__ import annotations

import pytest

from app import sentsplit
from app.contracts import (
    HoldReason,
    Infeasibility,
    JudgeResponse,
    Outcome,
    Verdict,
    Violation,
)
from app.graph import (
    INFEASIBILITY_OF,
    DictHit,
    DictScan,
    LawResult,
    judge,
    route_review,
    to_response,
)

FOOD = "013094:제8조제1항제1호"
FAIR = "002011:제3조제1항제1호"


def _state(text: str, hits: list[DictHit], *, ran: bool = True, scan_hits=None) -> dict:  # noqa: ANN001
    sents = sentsplit.split(text)
    return {
        "text": text,
        "sents": sents,
        "laws": ("law_food", "law_ftc"),
        "dict_scans": [
            DictScan(
                sent_id="s0", ran=ran, hits=tuple(scan_hits if scan_hits is not None else hits)
            )
        ],
        "law_results": [
            LawResult(law="law_food", sent_ids=("s0",), dict_hits=(("s0", tuple(hits)),)),
            LawResult(law="law_ftc", sent_ids=("s0",)),
        ],
    }


def _one(state: dict):  # noqa: ANN202
    (s,) = judge(state)["sentences"]
    return s


@pytest.mark.gate
def test_사전을_못_훑었으면_미판정이다() -> None:
    s = _one(_state("암 예방에 좋습니다", [], ran=False))
    assert s.verdict is Verdict.unjudged


@pytest.mark.gate
def test_사전에_안_걸리면_보류다() -> None:
    s = _one(_state("하루 한 포", []))
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf
    assert not s.violations


@pytest.mark.gate
def test_사전_적중은_인용_조문과_함께_위반_확정이다() -> None:
    h = DictHit("암예방", "질병_예방치료_표방", (FOOD,), (0, 4))
    s = _one(_state("암 예방에 좋습니다", [h]))
    assert s.verdict is Verdict.confirmed
    assert s.violations == [Violation.질병_예방치료_표방]
    assert s.infeasibility is Infeasibility.C
    assert (s.evidence[0].law_id, s.evidence[0].article, s.evidence[0].item) == (
        "013094",
        "제8조",
        "제1항제1호",
    )
    assert [(x.start, x.end, x.label) for x in s.spans] == [(0, 4, "질병_예방치료_표방")]
    assert s.risk.final is None, "🚨 하한(W5) 없이 위험도를 지어내지 않는다 (D-09)"


@pytest.mark.gate
def test_사유가_여럿이면_더_막힌_쪽이다() -> None:
    hs = [
        DictHit("최고", "거짓_과장", (FOOD,), (0, 2)),
        DictHit("암예방", "질병_예방치료_표방", (FOOD,), (3, 7)),
    ]
    s = _one(_state("최고 암 예방", hs))
    assert s.infeasibility is Infeasibility.C


@pytest.mark.gate
@pytest.mark.parametrize(
    ("vt", "cite"),
    [
        ("후기_체험기_기만", "013094:제8조제1항제5호|다목"),
        ("기능성화장품_오인", "002015:제13조제1항제2호"),
        # 인용이 유형을 못 주면(식품 9호) 사전 칸의 유형을 쓴다 — 뒷광고는 인용으로 갈 호가 없다(D-255 범위 밖)
        ("추천_보증_뒷광고", "013094:제8조제1항제9호"),
    ],
)
def test_불가_사유를_못_정한_유형은_확정하지_않는다(vt: str, cite: str) -> None:
    """⬜ D-273 의 ⬜ 둘과 표에 없는 유형 — 판정이 내려오면 `INFEASIBILITY_OF` 에 들어온다. 비방은 D-304 로 B."""
    assert Violation(vt) not in INFEASIBILITY_OF
    s = _one(_state("체험 후기", [DictHit("체험", vt, (cite,), (0, 2))]))
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf
    assert s.violations == [Violation(vt)]


@pytest.mark.gate
def test_유형은_인용에서_계산한다() -> None:
    """🔴 D-282 — 여러 유형 항목은 사전 칸(`violation_type`)이 비어 있다(적재기). 인용이 유형을 준다."""
    h = DictHit("0원메가패스", None, ("002011:제3조제1항제1호", "002011:제3조제1항제2호"), (0, 6))
    s = _one(_state("0원 메가패스", [h]))
    assert s.verdict is Verdict.confirmed
    assert s.violations == [Violation.거짓_과장, Violation.소비자_기만]
    assert s.infeasibility is Infeasibility.B
    mok = _one(_state("체험", [DictHit("체험", None, ("013094:제8조제1항제5호|다목",), None)]))
    assert mok.violations == [Violation.후기_체험기_기만]


@pytest.mark.gate
def test_어느_법인지_못_정한_인용만_울리면_근거_없음이다() -> None:
    bad = DictHit("암예방", "질병_예방치료_표방", ("999999:제1조제1항제1호",), (0, 4))
    s = _one(_state("암 예방", [], scan_hits=[bad]))
    assert s.verdict is Verdict.no_basis and s.violations == [Violation.질병_예방치료_표방]


@pytest.mark.gate
def test_위험도_없는_확정_위반은_증명서로_못_가고_응답이_계약을_지난다() -> None:
    h = DictHit("암예방", "질병_예방치료_표방", (FOOD, FAIR), (0, 4))
    state = _state("암 예방에 좋습니다", [h])
    state["sentences"] = judge(state)["sentences"]
    assert route_review(state) == "hold"
    state["outcome"] = Outcome.hold
    r = to_response(state)
    assert isinstance(r, JudgeResponse) and r.outcome is Outcome.hold
    assert r.judged_by.startswith("rule-")


@pytest.mark.gate
@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("면역력 강화에 도움을 줍니다.", ["면역력 강화에 도움을 줍니다."]),
        ("3.5g 함유! 지금 주문", ["3.5g 함유!", "지금 주문"]),
        ("첫 줄\n\n둘째 줄", ["첫 줄", "둘째 줄"]),
        (
            "달라져요✨ 하루 한 포 #다이어트 #체지방",
            ["달라져요✨", "하루 한 포", "#다이어트", "#체지방"],
        ),
        ("   ", ["   "]),
    ],
)
def test_분할은_원문의_부분_문자열을_낸다(text: str, want: list[str]) -> None:
    got = sentsplit.split(text)
    assert got == want
    starts = sentsplit.offsets(text, got)
    assert all(text[a : a + len(s)] == s for a, s in zip(starts, got, strict=True))


@pytest.mark.gate
def test_둘째_문장의_구간은_원문_좌표다() -> None:
    text = "맛있어요\n암 예방에 좋습니다"
    hits = [DictHit("암예방", "질병_예방치료_표방", (FOOD,), (0, 4))]
    state = {
        "text": text,
        "sents": sentsplit.split(text),
        "dict_scans": [DictScan("s0", ran=True), DictScan("s1", ran=True, hits=tuple(hits))],
        "law_results": [
            LawResult(law="law_food", sent_ids=("s0", "s1"), dict_hits=(("s1", tuple(hits)),))
        ],
    }
    s0, s1 = judge(state)["sentences"]
    assert s0.verdict is Verdict.hold
    (sp,) = s1.spans
    assert text[sp.start : sp.end] == "암 예방"


# ── W1 그래프 평가 도구 (`scripts/eval_graph.py`) ─────────────────────────────


@pytest.mark.gate
def test_그래프_평가는_예측을_확정_문장에서만_세고_보류를_사유별로_낸다() -> None:
    """🆕 2026-10-01 (W1) — 보류는 예측이 아니다(D-127) · 보류율 사유별(D-269) · selective risk 는 판정을 낸 행만(D-77 L1 #8)."""
    from scripts import eval_graph as eg

    rows = [
        {
            "id": "a",
            "text": "가",
            "labels": ["거짓_과장"],
            "근거": [FAIR],
            "split": "test_sentence",
        },
        {
            "id": "b",
            "text": "나",
            "labels": ["거짓_과장"],
            "근거": [FAIR],
            "split": "test_sentence",
        },
        {"id": "c", "text": "다", "labels": [], "근거": [], "조건": "L", "split": "test_sentence"},
        {"id": "d", "text": "라", "labels": [], "근거": [], "조건": "M", "split": "test_sentence"},
    ]
    hit = DictHit("최고", None, (FAIR,), (0, 1))
    preds = []
    for r, hits, ran in (
        (rows[0], [hit], True),
        (rows[1], [], True),
        (rows[2], [hit], True),
        (rows[3], [], False),
    ):
        st = _state(r["text"], hits, ran=ran)
        st["law_results"] = [
            LawResult(law="law_ftc", sent_ids=("s0",), dict_hits=(("s0", tuple(hits)),))
        ]
        st["sentences"] = judge(st)["sentences"]
        st["outcome"] = Outcome(route_review(st))
        preds.append(eg.predict(st))
    s = eg.summarize(rows, preds)
    assert [p["class"] for p in preds] == ["확정위반", "보류", "확정위반", "미판정"]
    assert s["types"]["거짓_과장"] == (2, 1, 1)  # 정답 2 · 맞힘 1 · 적법 행에 울린 1
    assert s["hold_reasons"] == {"하한없음(W5)": 2, "low_conf": 1, "미판정": 1}
    assert s["committed"] == 2 and s["selective_risk"] == 0.5  # 판정 낸 둘 중 적법 행 하나가 틀렸다
    assert s["scored_rows"] == 3 and s["unscored_rows"] == 1  # M 은 채점 밖
    assert s["lawful"]["주장"] == (1, 1)
    assert s["by_condition"]["M"] == {"미판정": 1}


@pytest.mark.gate
def test_그래프_평가는_DB_사전이_파일과_다르면_멈춘다() -> None:
    """🆕 2026-10-01 (원장 10-01 ⑦) — 낡은 DB 사전(봉인 문서 문구가 든 판)으로 잰 수가 정본처럼 찍히지 않게 (D-220 · D-174)."""
    from app import dictmatch as dm
    from scripts import eval_graph as eg

    file_rows = [
        {"term": "암예방", "유형": ["질병_예방치료_표방"], "근거": [FOOD], "단독판정": True},
        {"term": "최고", "유형": ["거짓_과장", "소비자_기만"], "근거": [FAIR], "단독판정": True},
        {
            "term": "천연",
            "유형": ["거짓_과장"],
            "근거": [FAIR],
            "단독판정": False,
        },  # 단독판정 밖 — 대조 밖
    ]
    same = [
        dm.Entry("암예방", "질병_예방치료_표방", (FOOD,)),
        dm.Entry("최고", None, (FAIR,)),
    ]
    assert eg.dict_drift(same, file_rows) == {
        "db_only": 0,
        "file_only": 0,
        "changed": 0,
        "file": 2,
        "db": 2,
    }
    stale = [dm.Entry("암예방", "질병_예방치료_표방", (FAIR,)), dm.Entry("한상춘방짜유기")]
    d = eg.dict_drift(stale, file_rows)
    assert (d["db_only"], d["file_only"], d["changed"]) == (1, 1, 1)

    class Cur:  # `load_dict_entries` 가 읽는 꼴만
        def execute(self, *_a) -> None: ...  # noqa: ANN002

        def fetchall(self) -> list[tuple]:
            return [("한상춘방짜유기", "거짓_과장", FAIR)]

    import json
    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "banned_terms.jsonl"
        p.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in file_rows),
            encoding="utf-8",
            newline="\n",
        )
        with pytest.raises(SystemExit, match="launcher.py load"):
            eg.check_dict(Cur(), p)
        with pytest.raises(SystemExit, match="없다"):
            eg.check_dict(Cur(), pathlib.Path(td) / "none.jsonl")


@pytest.mark.gate
def test_비방은_실증형이다() -> None:
    """🆕 2026-10-01 (D-304) — 비방 = B. 기록되는 판정은 실증 못한 경우(D-263 ①) · 실증 분기 상한은 R1 이상(하한 W5 뒤)."""
    s = _one(
        _state(
            "경쟁사 제품은 효과 없음",
            [DictHit("효과없음", None, ("002011:제3조제1항제4호",), (0, 4))],
        )
    )
    assert s.verdict is Verdict.confirmed and s.violations == [Violation.비방광고]
    assert s.infeasibility is Infeasibility.B


@pytest.mark.gate
def test_골든_품목은_계약의_품목_값이고_모르면_미상이다() -> None:
    """🆕 2026-10-01 (D-306) — 원천 → 품목 표의 값이 계약 `Category` 밖이면 조건부 평가가 그 행에서 죽는다 (D-99)."""
    from app.contracts import Category
    from preprocess.golden import CATEGORY_OF_SOURCE, category_of

    assert set(CATEGORY_OF_SOURCE.values()) <= {c.value for c in Category}
    assert category_of("ftc_decisions_body") is None, (
        "결정문은 원천으로 품목을 못 정한다 — 지어내지 않는다"
    )
    assert category_of("mfds_cosmetic_ad_qa") == "화장품"


@pytest.mark.gate
def test_조건부_평가는_품목을_아는_행만_품목을_넘겨_돈다() -> None:
    """🆕 2026-10-01 (D-306) — 품목 칸이 없는 판(재동결 전)이면 멈춘다 · 무조건부로 조용히 바꾸지 않는다 (D-220)."""
    from app.contracts import Category, ProductContext
    from scripts import eval_graph as eg

    rows = [{"id": "a", "text": "가", "품목": "화장품"}, {"id": "b", "text": "나", "품목": None}]
    assert [r["id"] for r in eg.conditional_rows(rows)] == ["a"]
    assert eg.product_of(rows[0], True).category is Category.화장품
    assert eg.product_of(rows[0], False) == ProductContext()
    with pytest.raises(SystemExit, match="품목"):
        eg.conditional_rows([{"id": "c"}])
    seen = []
    eg.run(
        rows[:1],
        lambda t, p: seen.append(p) or {"sentences": [], "outcome": None},
        0,
        conditional=True,
    )
    assert seen[0].category is Category.화장품
