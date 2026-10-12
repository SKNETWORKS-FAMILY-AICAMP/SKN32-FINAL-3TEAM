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
def test_불가_사유가_없는_유형은_확정하지_않는다() -> None:
    """🔄 2026-10-01 (D-308 ⑨) — 표에 없는 유형은 보류다(D-273). 남은 하나는 뒷광고 — D-255 범위 밖이라 일부러 뺐다."""
    assert set(Violation) - set(INFEASIBILITY_OF) == {Violation.추천_보증_뒷광고}
    # 인용이 유형을 못 주면(식품 9호) 사전 칸의 유형을 쓴다 — 뒷광고는 인용으로 갈 호가 없다(D-255 범위 밖)
    h = DictHit("체험", "추천_보증_뒷광고", ("013094:제8조제1항제9호",), (0, 2))
    s = _one(_state("체험 후기", [h]))
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf
    assert s.violations == [Violation.추천_보증_뒷광고]


@pytest.mark.gate
@pytest.mark.parametrize(
    ("cite", "vt", "want"),
    [
        ("013094:제8조제1항제5호|다목", "후기_체험기_기만", Infeasibility.C),
        ("002015:제13조제1항제2호", "기능성화장품_오인", Infeasibility.A),
    ],
)
def test_후기는_절대형_기능성화장품은_자격형이다(cite: str, vt: str, want: Infeasibility) -> None:
    """🆕 2026-10-01 (D-308 ⑨)."""
    s = _one(_state("체험 후기", [DictHit("체험", None, (cite,), (0, 2))]))
    assert s.verdict is Verdict.confirmed and s.violations == [Violation(vt)]
    assert s.infeasibility is want


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

    rows = [
        {"id": "a", "text": "가", "품목": "화장품", "전제": "화장품"},
        {"id": "b", "text": "나", "품목": None, "전제": None},
        {
            "id": "h",
            "text": "다",
            "품목": "건기식",
            "전제": None,
        },  # 품목만 안다 — 인정 여부는 모른다
    ]
    assert [r["id"] for r in eg.conditional_rows(rows)] == ["a", "h"]
    assert eg.product_of(rows[0], True).category is Category.화장품
    assert eg.product_of(rows[2], True).category is Category.건기식
    assert eg.product_of(rows[0], False) == ProductContext()
    with pytest.raises(SystemExit, match="품목"):
        eg.conditional_rows([{"id": "c"}])
    # 🆕 2026-10-10 — `전제` 칸이 없는 판(재동결 전)에서도 멈춘다 — 품목만으로 조용히 돌지 않는다
    with pytest.raises(SystemExit, match="전제"):
        eg.conditional_rows([{"id": "c", "품목": "식품"}])
    seen = []
    eg.run(
        rows[:1],
        lambda t, p: seen.append(p) or {"sentences": [], "outcome": None},
        0,
        conditional=True,
    )
    assert seen[0].category is Category.화장품


# ── 🆕 2026-10-02 (D-311) — 단독판정 자격 없는 적중은 보류 문장의 유형 후보다 ────────────────


@pytest.mark.gate
def test_자격_없는_적중은_확정하지_않고_보류에_유형_후보로_싣는다() -> None:
    """★ D-311 · D-273 ④ — 강등된 질병 이름(「당뇨」)은 확정의 재료가 아니다. 그러나 **사전 침묵과 같은 보류**가 되면 안 된다."""
    weak = DictHit("당뇨", "질병_예방치료_표방", (FOOD,), (0, 2))
    st = _state("당뇨에 좋은 차", [])
    st["dict_scans"] = [DictScan(sent_id="s0", ran=True, weak=(weak,))]
    st["law_results"] = [
        LawResult(law="law_food", sent_ids=("s0",), weak_hits=(("s0", (weak,)),)),
        LawResult(law="law_ftc", sent_ids=("s0",)),
    ]
    (s,) = judge(st)["sentences"]
    assert s.verdict is Verdict.hold and s.hold_reason is HoldReason.low_conf
    assert s.violations == [Violation.질병_예방치료_표방], (
        "🚨 유형 후보가 사라지면 사전 침묵과 구별이 안 된다"
    )
    assert ("013094", "제8조", "제1항제1호") in {(a.law_id, a.article, a.item) for a in s.evidence}
    st["sentences"] = [s]
    assert route_review(st) == "hold", "🔴 자격 없는 적중으로 확정 · 통과가 나면 안 된다"


@pytest.mark.gate
def test_자격_없는_적중도_보낸_법의_인용만_남는다() -> None:
    """🔴 법별 노드의 거름은 단독판정 적중과 **같다**(`_mine` · D-99) — 화장품 전제에서 식품 인용 후보가 붙지 않는다."""
    from app.graph import _mine

    weak = DictHit("당뇨", "질병_예방치료_표방", (FOOD,), (0, 2))
    assert _mine((weak,), "화장품법") == ()
    assert _mine((weak,), "식품표시광고법") == (weak,)


@pytest.mark.gate
def test_그래프_평가는_탐지_재현율을_확정_재현율과_나란히_낸다() -> None:
    """🆕 D-311 · 판정 10-02 보고 규칙 — 보류 유형 후보는 **예측이 아니다**(유형 P/R · selective risk 에 안 든다). 탐지 칸에만."""
    from scripts import eval_graph as eg

    rows = [
        {
            "id": "a",
            "text": "가",
            "labels": ["질병_예방치료_표방"],
            "근거": [FOOD],
            "split": "test_sentence",
        },
        {
            "id": "b",
            "text": "나",
            "labels": ["질병_예방치료_표방"],
            "근거": [FOOD],
            "split": "test_sentence",
        },
    ]
    preds = [
        {"outcome": "hold", "verdicts": ["hold"], "hold_reasons": ["low_conf"], "types": [],
         "candidates": ["질병_예방치료_표방"], "ho": [], "class": "보류", "committed": False, "n_sents": 1},
        {"outcome": "hold", "verdicts": ["hold"], "hold_reasons": ["low_conf"], "types": [],
         "candidates": [], "ho": [], "class": "보류", "committed": False, "n_sents": 1},
    ]  # fmt: skip
    s = eg.summarize(rows, preds)
    assert s["detect"] == {"positive": 2, "confirmed": 0, "detected": 1}
    assert s["types"]["질병_예방치료_표방"] == (2, 0, 0), "🚨 후보가 예측으로 세어졌다 (D-127)"
    assert s["committed"] == 0


def test_불가_사유_진단은_축이_다른_짝을_어긋남으로_세지_않는다() -> None:
    """🆕 2026-10-06 — 예측 사유(A/B/C)와 라벨 조건의 대조. 라벨의 A 는 지위 · 조성 전부라 예측 B 와는 축이 다르다(D-308 4′)."""
    from scripts import eval_graph as eg

    def row(cond: str | None, *labels: str) -> dict:
        return {
            "text": "문장",
            "조건": cond,
            "labels": list(labels),
            "근거": [],
            "split": "test_sentence",
        }

    rows = [
        row("C", "질병_예방치료_표방"),
        row("A", "거짓_과장"),
        row("C", "건강기능식품_오인"),
        row("C", "거짓_과장"),
        row("M", "거짓_과장"),
        row("B", "거짓_과장"),
        row(None, "거짓_과장"),
    ]
    preds = [{"infeasibility": x} for x in ("C", "B", "A", "B", "B", None, "B")]
    q = eg.reason_report(rows, preds)
    assert q == {"n": 4, "exact": 1, "axis_gap": 1, "wrong": 2, "wrong_hf": 1}, q
    assert eg.reason_report([row("C", "거짓_과장")], [{}])["n"] == 0, (
        "🚨 사유 없는 예측을 셌다 — 없음을 일치로도 어긋남으로도 세지 않는다 (D-220)"
    )


def test_보수_기록은_분기_보류에_실린_유형을_기록으로_센다() -> None:
    """🆕 2026-10-06 (D-263 ① · D-319 ①) — 확정 ∪ 전제를 몰라 멈춘 문장의 유형. 자격 없는 적중의 후보(`candidates`)는 세지 않는다."""
    from scripts import eval_graph as eg

    def row(cond: str, *labels: str) -> dict:
        return {
            "text": "문장",
            "조건": cond,
            "labels": list(labels),
            "근거": [],
            "split": "test_sentence",
        }

    rows = [
        row("C", "질병_예방치료_표방"),
        row("B", "거짓_과장"),
        row("B", "거짓_과장"),
        row("D"),
        row("C", "의약품_오인"),
    ]
    preds = [
        {"types": [], "premise_held": ["질병_예방치료_표방"], "candidates": ["질병_예방치료_표방"]},
        {"types": ["소비자_기만"], "premise_held": []},
        {"types": [], "premise_held": [], "candidates": ["거짓_과장"]},
        {"types": ["거짓_과장"], "premise_held": []},
        {"types": []},
    ]
    w = eg.recorded_report(rows, preds)
    assert w == {"rows": 2, "wrong": 1, "positive": 4, "hit": 1}, w


def test_조건부_평가는_승인_문구_규칙_행을_전제로만_넘긴다() -> None:
    """그 행의 `품목` 은 원천이고 라벨은 「일반식품이 쓰면」이라는 전제다. 품목을 제품 정보로 넘기면 전제가 어긋난다.

    🔄 2026-10-10 — 종전에는 뺐다. 골든 `전제`(식품)가 생겨 그 전제로 든다. `전제` 가 빈 승인 문구 행은 여전히 뺀다.
    """
    from app.contracts import Category
    from preprocess.split import APPROVED_READING
    from scripts import eval_graph as eg

    rows = [
        {"품목": "건기식", "판독": APPROVED_READING, "전제": "식품"},
        {"품목": "건기식", "판독": APPROVED_READING, "전제": None},
        {"품목": "건기식", "판독": "독립판독_합의", "전제": None},
        {"품목": None, "판독": None, "전제": None},
        {"품목": "식품", "전제": "식품"},
    ]
    got = eg.conditional_rows(rows)
    assert got == [rows[0], rows[2], rows[4]]
    assert eg.product_of(rows[0], True).category is Category.식품, (
        "원천(건기식)이 아니라 전제(식품)다"
    )


# ── 2026-10-08 평가 규칙 집행 (D-321 · D-40 · D-175) ─────────────────────────────────────────────
def test_유형_없는_위반_행과_편입_대기_유형만_붙은_행은_채점_밖이다() -> None:
    """★ D-321 — 「유형이 없어 학습 · 채점에서 빠진다」(평가 131) · 편입 대기 유형은 게이트 · 발표 지표에 넣지 않는다."""
    from scripts.eval_rule import scored, truth_types, untyped_violation  # noqa: PLC0415

    untyped = {"조건": "C", "labels": [], "근거": ["002015:제13조제1항제4호"]}
    pending = {"조건": "A", "labels": ["기능성화장품_오인"], "근거": ["002015:제13조제1항제2호"]}
    mixed = {
        "조건": "B",
        "labels": ["거짓_과장", "기능성화장품_오인"],
        "근거": ["002011:제3조제1항제1호"],
    }
    lawful = {"조건": "L", "labels": [], "근거": []}
    cand = {"조건": "B", "labels": [], "근거": [], "근거_후보": [["002011:제3조제1항제1호"]]}
    assert untyped_violation(untyped) and not scored(untyped)
    assert untyped_violation(pending) and not scored(pending)
    assert scored(mixed) and truth_types(mixed, set()) == {"거짓_과장"}, (
        "편입 대기 유형은 정답에서 빠진다"
    )
    assert scored(lawful), "적법 행은 그대로 채점한다"
    assert scored(cand), "근거 후보만 있는 행은 후보가 정답이다 — 빼지 않는다"


def test_6종_8종_표와_신뢰구간() -> None:
    """★ D-321 결정 4 — 두 표 · D-40 — 30 미만은 macro 에서 빠지고 · 신뢰구간은 n=0 이면 없다."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    t = {
        "거짓_과장": (40, 20, 5),
        "비방광고": (35, 7, 0),
        "후기_체험기_기만": (10, 5, 0),
    }
    m = eg.macro_table(t)
    assert m["8종"]["measurable"] == ["거짓_과장", "비방광고"]
    assert m["6종"]["measurable"] == ["거짓_과장"], "6종 표에는 이번 편입 둘이 없다"
    assert "후기_체험기_기만" in m["8종"]["unmeasurable"]
    lo, hi = eg.wilson(20, 40)
    assert lo < 0.5 < hi
    assert eg.wilson(0, 0) is None


def test_봉인_실행은_기록하고_횟수를_센다(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """★ D-175 — 봉인 평가셋 실행을 기록한다. 도구가 세지 않으면 「한 번」이 지켜졌는지 알 수 없다."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    monkeypatch.setattr(eg, "SEALED_LOG", tmp_path / "sealed.jsonl")
    assert eg.log_sealed_run({"golden_sha": "x"}) == 1
    assert eg.log_sealed_run({"golden_sha": "x"}) == 2
