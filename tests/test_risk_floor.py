"""위험도 하한 — 적재(`load_sanction_rule`) · 조회(`app/sanction.py`) · 배선(`assess_risk`) (🆕 2026-10-02 · W5 · D-305 · D-309 · D-310 · D-09).

지키는 것
  ① 서명한 표와 판정이 **같은 규칙**을 쓴다 — 원천(yaml)과 DB 뷰가 같은 함수(`floor_rows`)에 같은 열쇠의 행을 넘긴다 (D-99)
  ② 하한을 **모르면 적지 않는다** — 제재표가 비었거나 맞는 행이 없으면 위험도 없이 보류다 (D-220 · D-72)
  ③ 서명 없는 판 · 무효 서명은 하한이 되지 않는다 (D-309 · 0013)
  ④ 종착이 재료 없이 증명서 · 지시를 찍지 않는다 — 계약이 응답을 거부하기 전에 보류로 내린다
"""

from __future__ import annotations

import copy

import pytest

from app import sanction
from app.contracts import (
    Category,
    Certificate,
    EvidenceArticle,
    Infeasibility,
    Outcome,
    ProductContext,
    Risk,
    RiskAssessment,
    SentenceJudgment,
    Span,
    SubstBranch,
    Verdict,
    Violation,
)
from app.graph import (
    LAW_OF_NODE,
    NODES,
    REVIEW_TERMINALS,
    DictHit,
    DictScan,
    LawResult,
    assess_risk,
    floor_of_sentence,
    guidance_ready,
    judge,
    load_sanction_rows,
    to_response,
    upsert_sentences,
)
from scripts import load_db
from scripts import sanction_rule as sr

pytestmark = pytest.mark.gate

FOOD1 = "013094:제8조제1항제1호"
FOOD4 = "013094:제8조제1항제4호"
FOOD4_MA = "013094:제8조제1항제4호|마목"
FOOD5_DA = "013094:제8조제1항제5호|다목"
FAIR1 = "002011:제3조제1항제1호"


def _rows() -> list[dict]:
    """서명된 원천의 행 — 판정 그래프가 DB 뷰에서 받는 것과 **같은 열쇠**다."""
    spec = sr.load_rules()
    assert sr.signature(spec) is not None, "원천이 서명 전이다 — 이 게이트의 전제가 깨진다"
    return sr.rule_rows(spec)


class _Cur:
    """`v_risk_lookup` 대역 — `SQL_RISK` 의 칸 순서로 행을 낸다. 질의 수를 센다."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows, self.calls = rows, 0

    def execute(self, sql: str, params: object = None) -> None:
        assert "v_risk_lookup" in sql, (
            "🚨 하한은 뷰로만 읽는다 — 서명 없는 행이 보이면 안 된다 (0013)"
        )
        self.calls += 1

    def fetchall(self) -> list[tuple]:
        return [
            (r["id"], r["law_id"], r["type"], r["kind"], r.get("annex1"), r.get("cover"), r["quote"], r.get("fact"))
            for r in self.rows
        ]  # fmt: skip


def _hit(*basis: str, term: str = "낱말") -> DictHit:
    return DictHit(term=term, violation_type=None, basis=basis, span=(0, 2))


def _state(by_law: dict[str, list[DictHit]], category: Category | None = Category.식품) -> dict:
    """문장 하나 · 법별 적중. `judge` 를 실제로 돌려 문장을 만든다 — 판정과 위험도가 같은 적중을 읽는다."""
    laws = tuple(by_law)
    st = {
        "text": "낱말이 든 문장입니다.",
        "sents": ["낱말이 든 문장입니다."],
        "product": ProductContext(category=category),
        "laws": laws,
        "dict_scans": [
            DictScan(sent_id="s0", ran=True, hits=tuple(h for hs in by_law.values() for h in hs))
        ],
        "law_results": [
            LawResult(law=law, sent_ids=("s0",), dict_hits=(("s0", tuple(hits)),))
            for law, hits in by_law.items()
        ],
    }
    st["sentences"] = judge(st)["sentences"]
    return st


def _risk(st: dict, rows: list[dict] | None = None) -> RiskAssessment:
    cur = _Cur(_rows() if rows is None else rows)
    out = assess_risk(st, {"configurable": {"conn": cur}})
    sents = upsert_sentences(st["sentences"], out.get("sentences", []))
    return sents[0].risk


# ── ① 리듀서 ─────────────────────────────────────────────────────────


def test_같은_문장은_바꿔_끼우고_새_문장은_뒤에_붙는다() -> None:
    a = SentenceJudgment(sent_id="s0", text="가", verdict=Verdict.unjudged)
    b = SentenceJudgment(sent_id="s1", text="나", verdict=Verdict.unjudged)
    a2 = SentenceJudgment(
        sent_id="s0", text="가", verdict=Verdict.confirmed, risk=RiskAssessment(floor=Risk.R0, final=Risk.R0)
    )  # fmt: skip
    c = SentenceJudgment(sent_id="s2", text="다", verdict=Verdict.unjudged)
    out = upsert_sentences([a, b], [a2, c])
    assert [s.sent_id for s in out] == ["s0", "s1", "s2"], "🚨 순서가 바뀌거나 문장이 두 줄이 됐다"
    assert out[0] is a2 and out[1] is b


# ── ② 하한 조회 ───────────────────────────────────────────────────────


def test_법_축마다_처분_원천이_있다() -> None:
    """🔴 판정 그래프의 법 축 이름 ↔ 제재표의 법 ID 표가 원천과 어긋나면 그 법은 **늘 하한 없음**이 된다 (D-99)."""
    spec = sr.load_rules()
    src_ids = {spec["sources"][r["src"]]["law_id"] for r in spec["rows"]}
    assert set(sanction.SANCTION_LAW) == set(LAW_OF_NODE.values())
    assert set(sanction.SANCTION_LAW.values()) == src_ids, "🚨 처분 원천 법 ID 가 원천과 다르다"


def test_한_전제_안에서_두_법이_걸리면_높은_쪽이다() -> None:
    """D-272 — 식품 1호(R2)와 표시광고법(R1)이 같이 걸리면 R2."""
    by = {"식품표시광고법": (_hit(FOOD1),), "표시광고법": (_hit(FAIR1),)}
    f = floor_of_sentence(_rows(), by)
    assert f.floor is Risk.R2 and f.ceiling is None


def test_넓은_목은_하한이_아니라_가능_상한으로_온다() -> None:
    """D-310 개정 2 (다) — 4.마 는 목이 별표7 행보다 넓다. 하한 R1 · 상한 R2 · 근거 줄."""
    f = floor_of_sentence(_rows(), {"식품표시광고법": (_hit(FOOD4_MA),)})
    assert (f.floor, f.ceiling) == (Risk.R1, Risk.R2)
    assert "4.마" in (f.ceiling_note or "")
    full = floor_of_sentence(_rows(), {"식품표시광고법": (_hit(FOOD5_DA),)})
    assert (full.floor, full.ceiling) == (Risk.R2, None), "5.다 는 전부 덮는 행이다 — 하한이 R2"


def test_행이_없는_유형은_하한을_모른다() -> None:
    """🔴 아는 것만으로 max 를 내지 않는다 — 모르는 처분이 더 무거울 수 있다 (D-220)."""
    rows = [r for r in _rows() if r["law_id"] != "002011"]
    by = {"식품표시광고법": (_hit(FOOD1),), "표시광고법": (_hit(FAIR1),)}
    assert floor_of_sentence(rows, by).floor is None
    assert floor_of_sentence([], by).floor is None, "제재표가 비면 하한이 없다"


# ── ③ 배선 ───────────────────────────────────────────────────────────


def test_확정_위반에_하한과_가능_상한이_붙는다() -> None:
    st = _state({"law_food": [_hit(FOOD4_MA)], "law_ftc": []})
    assert st["sentences"][0].verdict is Verdict.confirmed and st["sentences"][0].risk.final is None
    r = _risk(st)
    assert (r.floor, r.final, r.ceiling) == (Risk.R1, Risk.R1, Risk.R2)
    assert r.encoder is None and r.evidence_span is None, "인코더가 없다 — 최종 = 하한 (D-131)"


def test_제재표가_비면_위험도를_적지_않는다() -> None:
    st = _state({"law_food": [_hit(FOOD1)], "law_ftc": []})
    assert _risk(st, rows=[]).final is None
    from app.graph import route_review  # noqa: PLC0415

    assert route_review(st) == "hold", "🚨 위험도 없는 확정 위반이 종착으로 갔다 (D-220)"


def test_품목_미확정은_아직_적지_않는다() -> None:
    """🚨 D-229 ⑥ 판정 대기 — 전제마다 하한이 달라 기준이 필요하다. 판정이 내려오면 이 게이트를 고친다 (D-192)."""
    st = _state({"law_food": [_hit(FOOD1)], "law_ftc": []}, category=None)
    cur = _Cur(_rows())
    assert assess_risk(st, {"configurable": {"conn": cur}}).get("sentences") is None
    assert cur.calls == 0


def test_보류뿐이면_제재표를_읽지_않는다() -> None:
    st = _state({"law_food": [], "law_ftc": []})
    assert st["sentences"][0].verdict is Verdict.hold
    cur = _Cur(_rows())
    assert assess_risk(st, {"configurable": {"conn": cur}}).get("sentences") is None
    assert cur.calls == 0, "🚨 적을 문장이 없는데 질의를 했다"
    assert assess_risk(st).get("sentences") is None, "커서가 없어도 돈다 — 아무것도 적지 않는다"


def test_위반_없는_확정은_R0_이다() -> None:
    ok = SentenceJudgment(sent_id="s0", text="가", verdict=Verdict.confirmed)
    st = {"sentences": [ok], "product": ProductContext(category=Category.식품), "law_results": []}
    cur = _Cur(_rows())
    out = assess_risk(st, {"configurable": {"conn": cur}})
    assert out["sentences"][0].risk == RiskAssessment(floor=Risk.R0, final=Risk.R0)
    assert cur.calls == 0, "위반이 없으면 제재표가 필요 없다"


def test_노드가_config_를_받는_모양이다() -> None:
    """LangGraph 는 시그니처를 보고 `config` 를 넘긴다 — 주석이 붙으면 커서가 조용히 None 이 된다 (2026-09-14 실측)."""
    import inspect  # noqa: PLC0415

    p = inspect.signature(NODES["assess_risk"]).parameters
    assert "config" in p and p["config"].annotation is inspect.Parameter.empty


# ── ④ 종착 ───────────────────────────────────────────────────────────


def _viol(infeas: Infeasibility, **kw: object) -> SentenceJudgment:
    return SentenceJudgment(
        sent_id="s0",
        text="낱말이 든 문장",
        verdict=Verdict.confirmed,
        violations=[Violation.거짓_과장],
        infeasibility=infeas,
        evidence=[EvidenceArticle(law_id="013094", article="제8조", item="제1항제4호")],
        risk=RiskAssessment(floor=Risk.R1, final=Risk.R1),
        **kw,
    )


def test_증명서가_없으면_증명서_종착이_보류로_내린다() -> None:
    st = {"sentences": [_viol(Infeasibility.C)]}
    st.update(REVIEW_TERMINALS["certificate"](st))
    assert st["outcome"] is Outcome.hold
    assert to_response(st).outcome is Outcome.hold, "계약이 응답을 받는다"
    st["certificate"] = Certificate(reason=Infeasibility.C, explanation="사유")
    assert REVIEW_TERMINALS["certificate"](st)["outcome"] is Outcome.certificate
    st["outcome"] = Outcome.certificate
    assert to_response(st).certificate is not None


def test_실증_분기가_없으면_지시_종착이_보류로_내린다() -> None:
    thin = _viol(Infeasibility.B)
    assert not guidance_ready([thin])
    assert REVIEW_TERMINALS["guidance"]({"sentences": [thin]})["outcome"] is Outcome.hold
    full = _viol(
        Infeasibility.B,
        spans=[Span(start=0, end=2)],
        substantiation=SubstBranch(
            substantiated_max=Risk.R0, accepted_evidence=["시험 결과"], criteria="기준"
        ),
    )
    assert guidance_ready([full])
    assert REVIEW_TERMINALS["guidance"]({"sentences": [full]})["outcome"] is Outcome.guidance


# ── ⑤ 적재 ───────────────────────────────────────────────────────────


def test_적재_행은_원천을_그대로_옮긴다() -> None:
    spec = sr.load_rules()
    sig, sha = sr.signature(spec), sr.plan_sha(spec)
    by = {r["id"]: dict(zip(load_db.SANCTION_COLS, load_db.sanction_row(spec, r, sig, sha), strict=True)) for r in spec["rows"]}  # fmt: skip
    a = by["food.b1.4ma"]
    assert (a["law_id"], a["annex_no"], a["fragment_id"]) == ("013475", "0007", "law_go_kr:annex")
    assert (a["annex1"], a["cover"], a["risk_level"]) == (["4.마"], "일부", "R2")
    assert (a["verified_by"], a["reviewed_by"]) == sig and a["plan_sha"] == sha
    assert by["food.b1.4sa"]["annex1"] == [], "목 칸이 빈 행은 빈 배열이다"
    assert by["food.b1.1"]["annex1"] is None, (
        "목으로 갈리지 않는 행은 NULL 이다 — 빈 배열과 합치지 않는다"
    )
    assert by["fair.1"]["fragment_id"] == "law_go_kr:article" and by["fair.1"]["annex_no"] is None
    unsigned = load_db.sanction_row(spec, spec["rows"][0], None, sha)
    cols = dict(zip(load_db.SANCTION_COLS, unsigned, strict=True))
    assert cols["verified_by"] is None and cols["reviewed_by"] is None, (
        "서명 전 판은 뷰에 안 보인다"
    )


def test_무효_서명은_싣지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 판이 바뀐 뒤 남은 서명을 「서명 없음」으로 낮춰 싣지 않는다 — 멈춘다 (D-309)."""
    spec = copy.deepcopy(sr.load_rules())
    spec["rows"][0]["first"] += " "
    monkeypatch.setattr(sr, "load_rules", lambda *a, **k: spec)
    with pytest.raises(SystemExit, match="검사를 못 지났다"):
        load_db.load_sanction_rule(None, True)


def test_적재는_넣는_칸을_전부_갱신한다() -> None:
    import inspect  # noqa: PLC0415

    src = inspect.getsource(load_db.load_sanction_rule)
    assert 'for c in SANCTION_COLS if c != "rule_key"' in src, "🚨 upsert 가 일부 칸만 고친다"
    assert "DELETE FROM sanction_rule" in src, "🚨 원천에서 빠진 행을 거두지 않는다 (D-187)"


def test_DB_에_실은_표와_원천이_같은_하한을_낸다() -> None:
    """★ 서명한 표와 판정이 같은가 — DB 뷰에서 읽은 행과 yaml 행으로 **모든 (유형 · 법 · 목)** 의 하한을 견준다.

    DB 가 없거나 제재표를 안 실은 기기에서는 건너뛴다(기기 축 · D-19). 실었으면 반드시 같아야 한다.
    """
    psycopg = pytest.importorskip("psycopg")
    from app.settings import dsn  # noqa: PLC0415

    try:
        conn = psycopg.connect(dsn(), connect_timeout=2)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 에 못 붙었다 — {type(e).__name__}")
    with conn, conn.cursor() as cur:
        try:
            got = load_sanction_rows(cur)
        except psycopg.Error as e:
            pytest.skip(f"뷰를 못 읽었다(마이그레이션 전) — {type(e).__name__}")
    if not got:
        pytest.skip("제재표가 비었다 — `launcher.py load` 뒤에 본다")
    want = _rows()
    assert sorted(r["id"] for r in got) == sorted(r["id"] for r in want), (
        "🚨 실린 행이 원천과 다르다"
    )
    cites = [
        [],
        [FOOD4_MA],
        [FOOD5_DA],
        ["013094:제8조제1항제5호|차목"],
        ["013094:제8조제1항제7호|나목"],
    ]
    for law_id in sorted(set(sanction.SANCTION_LAW.values())):
        for v in Violation:
            for c in cites:
                a = sanction.floor_rows(got, v.value, law_id, c)
                b = sanction.floor_rows(want, v.value, law_id, c)
                assert a == b, f"🚨 {v.value} · {law_id} · {c} — DB {a} ≠ 원천 {b}"


def test_위험도가_붙은_보류는_하한_없음으로_세지_않는다() -> None:
    """평가 도구 — 위험도가 붙었는데 종착이 보류면 까닭이 다르다(증명서 · 지시의 문안이 없다). 한 칸에 섞지 않는다 (D-160)."""
    from scripts import eval_graph as eg  # noqa: PLC0415

    rows = [{"text": "가", "labels": ["거짓_과장"], "근거": [FAIR1]}] * 2
    with_risk = {"sentences": [_viol(Infeasibility.B)], "outcome": Outcome.hold}
    no_risk = {
        "sentences": [_viol(Infeasibility.B).model_copy(update={"risk": RiskAssessment()})],
        "outcome": Outcome.hold,
    }
    s = eg.summarize(rows, [eg.predict(with_risk), eg.predict(no_risk)])
    assert s["hold_reasons"] == {"종착재료없음(문안)": 1, "하한없음(W5)": 1}


# ── ⑥ 주된 광고법을 안 본 품목 (D-271 ④ · D-277 개정) ───────────────────────


@pytest.mark.parametrize("category", [Category.일반상품, Category.전용법_미수록])
def test_안_본_법이_있는_품목은_걸린_것_없는_문장이_보류다(category: Category) -> None:
    """표시광고법으로 걸린 것이 없을 뿐 그 품목의 법은 보지 않았다 — 확정 R0 이 아니라 `law_uncovered` 보류다."""
    from app.contracts import HoldReason  # noqa: PLC0415
    from app.graph import route_review  # noqa: PLC0415

    clean = SentenceJudgment(sent_id="s0", text="가", verdict=Verdict.confirmed)
    not_claim = SentenceJudgment(
        sent_id="s1", text="나", verdict=Verdict.confirmed, not_claim=True,
        risk=RiskAssessment(floor=Risk.R0, final=Risk.R0),
    )  # fmt: skip
    st = {"sentences": [clean, not_claim], "product": ProductContext(category=category)}
    out = assess_risk(st)  # 🚨 커서가 없어도 한다 — 제재표가 필요 없는 판단이다
    st["sentences"] = upsert_sentences(st["sentences"], out["sentences"])
    s0, s1 = st["sentences"]
    assert (s0.verdict, s0.hold_reason) == (Verdict.hold, HoldReason.law_uncovered)
    assert s1.verdict is Verdict.confirmed and s1.not_claim, "판정 대상 아님은 그대로다 (D-275)"
    assert route_review(st) == "hold"
    # 판정 대상 아님 문장뿐이어도 통과는 아니다 — 종착이 막는다(계약과 같은 규칙)
    only = {"sentences": [not_claim], "product": ProductContext(category=category)}
    assert route_review(only) == "hold"
    only["outcome"] = Outcome.hold
    r = to_response(only)
    assert r.not_reviewed and r.category is category
    assert r.category_source.value == "user_selected"


def test_응답이_품목과_출처를_싣는다() -> None:
    ok = SentenceJudgment(
        sent_id="s0", text="가", verdict=Verdict.confirmed, risk=RiskAssessment(floor=Risk.R0, final=Risk.R0)
    )  # fmt: skip
    r = to_response({"sentences": [ok], "outcome": Outcome.passed, "product": ProductContext(category=Category.식품)})  # fmt: skip
    assert (r.category, r.category_source.value, r.not_reviewed) == (
        Category.식품,
        "user_selected",
        [],
    )
    none = to_response({"sentences": [ok], "outcome": Outcome.passed, "product": ProductContext()})
    assert none.category is None and none.category_source is None
