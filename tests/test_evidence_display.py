"""화면에 나가는 근거 · 위험도 · 고쳐 쓰기 표시 — 판정을 바꾸지 않는 표시 결함 넷 (🆕 2026-10-08 · 소유자 팀장).

🔴 무엇을 막나
   ① 보류 문장 옆 초록 「위험도 R0」 — R0 은 「특이사항 없음」(D-280)이라 보류 옆에 서면 통과로 읽힌다
   ② 목 붙은 사전 근거가 평가 도구의 호 셈에서 조용히 빠지는 것 — 그래프의 꼴과 되읽는 꼴이 두 벌이었다 (D-99)
   ③ 인용 자격(`U3_cite`)이 열린 법령 조문인데도 `quote` 가 늘 비는 것 (D-224 ④)
   ④ 고쳐 쓰기 서버를 두지 않은 환경에서 누를 수 없는 버튼과 「잠시 뒤 다시」라는 거짓 안내
⛔ 이 파일이 보장하지 못하는 것 — 실제 DB 에서 `citable` 이 참으로 오는지(질의문만 본다) · 판정 결과의 수.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import graph as g
from app import retrieve as rt
from app.api import app
from app.contracts import SentenceJudgment, Verdict
from app.routers import sllm_client
from collect import statute
from scripts import eval_graph

# ── ① 보류 문장의 R0 칩 ─────────────────────────────────────────────────


@pytest.mark.parametrize("fixture", ["17_hold_law_uncovered", "19_hold_general_goods_uncovered"])
def test_보류_문장에는_R0_칩을_그리지_않는다(fixture: str) -> None:
    html = TestClient(app).get(f"/u/preview/{fixture}").text
    assert "위험도 R0" not in html, "🔴 보류 문장 옆에 초록 R0 — 통과로 읽힌다 (D-280)"
    assert "보류 · 등급 미정" in html


def test_확정_문장의_R0_칩은_그대로다() -> None:
    assert "위험도 R0" in TestClient(app).get("/u/preview/01_pass").text


# ── ② 근거 조문 칸의 꼴 — 만들고 되읽는 곳이 한 곳 ───────────────────────


@pytest.mark.parametrize(
    "cite", ["013094:제8조제1항제4호", "013094:제8조제1항제5호|다목", "002011:제3조제1항제1호"]
)
def test_근거_조문_칸은_인용으로_되돌아온다(cite: str) -> None:
    law, article, item = statute.article_item(cite)
    assert statute.from_article_item(law, article, item) == cite


@pytest.mark.parametrize(
    ("article", "item"),
    [("제8조제1항제4호", "4."), ("[별표 1]제5호다목", ""), ("제8조", ""), ("제8조", "제1항")],
)
def test_검색_근거는_인용으로_되읽지_않는다(article: str, item: str) -> None:
    """검색이 찾은 조문은 판정 문맥이지 위반 인용이 아니다 — 지어내지 않는다 (D-220)."""
    assert statute.from_article_item("013094", article, item) is None


def test_평가_도구가_목_붙은_사전_근거의_호를_센다() -> None:
    """🔴 종전에는 「제5호다목」을 `|다목` 꼴로 못 읽어 빠졌다."""
    ev = [g._basis_article("013094:제8조제1항제5호|다목")]  # noqa: SLF001
    s = SentenceJudgment(sent_id="s0", text="x", verdict=Verdict.confirmed, evidence=ev)
    assert eval_graph._ho(s) == {"013094:제8조제1항제5호"}  # noqa: SLF001


# ── ③ 인용 자격이 열린 조문만 글을 싣는다 ───────────────────────────────


def _hit(**kw: object) -> rt.Hit:
    d = dict.fromkeys(rt._NAMES)  # noqa: SLF001
    d.update(
        chunk_id="c1",
        law_id="013094",
        article="제8조",
        doc_type="법령",
        law="식품표시광고법",
        text="조문 글",
        exempt_of="",
        part_no=1,
        part_total=1,
        match=rt.MATCH_FUSED,
        citation="제8조제1항제1호",
        basis_citation="제8조제1항제1호",
    )
    d.update(kw)
    return rt.Hit(**d)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kw", "want"),
    [
        ({"citable": True}, "조문 글"),
        ({"citable": False}, None),
        ({"citable": None}, None),  # 질의가 칸을 안 실었다 — 자격을 지어내지 않는다
        ({"citable": True, "exempt_of": "1.가"}, None),  # 제외 목의 글은 부모 좌표의 글이 아니다
        (
            {"citable": True, "part_no": 2, "part_total": 3},
            None,
        ),  # 조각 — 「일부다」를 말할 칸이 없다 (D-224 ③)
        ({"citable": True, "part_total": None}, None),  # 재적재 전 — 전문인지 모른다 (D-220)
    ],
)
def test_인용_자격이_열린_청크만_조문_글을_싣는다(kw: dict, want: str | None) -> None:
    a = g._evidence_article(_hit(**kw))  # noqa: SLF001
    assert a is not None
    assert a.quote == want


#: 질의문이 인용 자격 칸을 싣는지 · 법별 할당 질의가 그 칸을 이름으로 부르는지는 게이트 파일
#: `tests/test_retrieve.py` 에 있다(집행계약 §1-3 에 오른 파일).


# ── ④ 고쳐 쓰기를 꺼 둔 환경 ─────────────────────────────────────────────


def test_꺼_둔_환경에서는_서버를_부르지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPYLANE_SLLM_URL", "off")
    assert sllm_client.rewrite("문구", ["거짓_과장"]) == ("off", None)


def test_꺼_둔_환경에서는_버튼_대신_안내를_그린다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPYLANE_SLLM_URL", "off")
    html = TestClient(app).get("/u/preview/02_hold_low_conf").text
    assert 'action="/u/review/rewrite"' not in html
    assert "이 환경에서는 문장 고쳐 쓰기를 제공하지 않아요" in html


def test_켜_둔_환경에서는_버튼이_있다(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ 로컬 · 시연의 동작은 바뀌지 않는다 — 변수를 안 주면 켜짐이다."""
    monkeypatch.delenv("COPYLANE_SLLM_URL", raising=False)
    html = TestClient(app).get("/u/preview/02_hold_low_conf").text
    assert 'action="/u/review/rewrite"' in html


def test_꺼짐은_부를_때_읽는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 import 시점에 읽으면 `.env` 의 `off` 가 import 순서에 따라 안 먹힌다 — 부를 때마다 읽는다."""
    monkeypatch.delenv("COPYLANE_SLLM_URL", raising=False)
    assert sllm_client.enabled()
    for v in ("off", "OFF", " off ", ""):
        monkeypatch.setenv("COPYLANE_SLLM_URL", v)
        assert not sllm_client.enabled()
    monkeypatch.setenv("COPYLANE_SLLM_URL", "http://127.0.0.1:9999/")
    assert sllm_client.enabled()
    assert sllm_client._url() == "http://127.0.0.1:9999"  # noqa: SLF001


# ── ⑤ 근거 표시 「(나)」 — 인용 근거와 참고 조문을 가른다 (🆕 2026-10-08) ──────────────────


def _row(**kw: object) -> tuple:
    d = dict.fromkeys(rt._NAMES)  # noqa: SLF001
    d.update(
        doc_type="법령", exempt_of="", part_no=1, part_total=1, citable=True, law="식품표시광고법"
    )
    d.update(kw)
    return tuple(d[n] for n in rt._NAMES)  # noqa: SLF001


class _Cur:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows, self.calls = rows, []

    def execute(self, sql: str, params: tuple) -> None:
        self.calls.append(params)

    def fetchall(self) -> list[tuple]:
        return self.rows


def test_사전_근거에_조문_원문을_붙인다() -> None:
    cur = _Cur(
        [
            _row(
                chunk_id="a1",
                law_id="013094",
                article="제8조",
                paragraph="①",
                item="1.",
                text="1. 질병",
            ),
            _row(
                chunk_id="a5",
                law_id="013094",
                article="제8조",
                paragraph="①",
                item="5.",
                text="5. 기만",
            ),
            # 쪼갠 조각 — 원문을 붙이지 않는다 (D-224 ③)
            _row(
                chunk_id="b1",
                law_id="002011",
                article="제3조",
                paragraph="①",
                item="1.",
                part_total=2,
                text="x",
            ),
        ]
    )
    cites = [
        "013094:제8조제1항제1호",
        "013094:제8조제1항제5호|다목",
        "002011:제3조제1항제1호",
        "꼴이 아님",
    ]
    got = g.basis_texts(cur, cites)
    assert set(got) == {"013094:제8조제1항제1호", "013094:제8조제1항제5호|다목"}
    a = got["013094:제8조제1항제5호|다목"]
    assert (a.article, a.item, a.chunk_id, a.quote) == ("제8조", "제1항제5호다목", "a5", "5. 기만")
    assert len(cur.calls) == 1, "커서는 한 번만 묻는다"


def test_원문_자격이_없으면_붙이지_않는다() -> None:
    cur = _Cur(
        [
            _row(
                chunk_id="a1",
                law_id="013094",
                article="제8조",
                paragraph="①",
                item="1.",
                citable=False,
                text="t",
            )
        ]
    )
    assert g.basis_texts(cur, ["013094:제8조제1항제1호"]) == {}


def test_원문이_붙은_근거는_좌표를_바꾸지_않는다() -> None:
    """평가 도구가 되읽는 꼴(`statute.from_article_item`)이 그대로다 — 원문만 더 붙는다."""
    cite = "013094:제8조제1항제1호"
    texts = {
        cite: g.EvidenceArticle(
            law_id="013094", article="제8조", item="제1항제1호", chunk_id="a1", quote="q"
        )
    }
    a = g._basis_article(cite, texts)  # noqa: SLF001
    assert a is not None and statute.from_article_item(a.law_id, a.article, a.item) == cite


def test_같은_청크는_참고_조문에_다시_싣지_않는다() -> None:
    basis = [
        g.EvidenceArticle(
            law_id="013094", article="제8조", item="제1항제1호", chunk_id="a1", quote="q"
        )
    ]
    retrieved = [
        g.EvidenceArticle(
            law_id="013094", article="제8조제1항제1호", item="1.", chunk_id="a1", quote="q"
        ),
        g.EvidenceArticle(law_id="013094", article="제1조", item="", chunk_id="z", quote="목적"),
    ]
    assert [a.chunk_id for a in g._references(retrieved, basis)] == ["z"]  # noqa: SLF001


def test_근거를_인용_근거와_참고_조문으로_가른다() -> None:
    from app.templating import evidence_parts  # noqa: PLC0415

    ev = [
        g.EvidenceArticle(law_id="013094", article="제8조", item="제1항제1호", basis=True),
        g.EvidenceArticle(law_id="013094", article="제8조", item="제1항제5호다목", basis=True),
        # 🔄 D-323 결정 2 — 칸으로 가른다. 꼴이 인용이어도 칸이 거짓이면 참고다(칸을 모르는 쪽이 만든 근거)
        g.EvidenceArticle(law_id="013094", article="제8조", item="제1항제4호"),
        g.EvidenceArticle(law_id="002011", article="제1조", item="", chunk_id="c", quote="목적"),
        g.EvidenceArticle(law_id="005361", article="제2조제1항제5호", item="5.", chunk_id="d"),
        g.EvidenceArticle(law_id="013453", article="[별표 1]제1호다목", item="본문", chunk_id="e"),
    ]
    parts = evidence_parts(ev)
    assert [e.item for e in parts["basis"]] == ["제1항제1호", "제1항제5호다목"]
    assert [e.article for e in parts["refs"]] == [
        "제8조",
        "제1조",
        "제2조제1항제5호",
        "[별표 1]제1호다목",
    ]


@pytest.mark.parametrize(
    ("fixture", "label"),
    [("05_certificate_a", "위반 근거"), ("02_hold_low_conf", "걸린 표현의 인용 조문 — 확정 아님")],
)
def test_근거_보기의_머리말은_판정에_맞춘다(fixture: str, label: str) -> None:
    html = TestClient(app).get(f"/u/preview/{fixture}").text
    assert label in html


# ── ⑥ D-323 — 인코더 후보는 따로 실린다 · 사전 근거는 칸으로 표시된다 ─────────────────


def test_사전_근거는_basis_칸이_참이다() -> None:
    a = g._basis_article("013094:제8조제1항제1호")  # noqa: SLF001
    assert a is not None and a.basis is True
    r = g._evidence_article(_hit(citable=True))  # noqa: SLF001
    assert r is not None and r.basis is False, "검색 근거는 참고 조문이다"


def test_인코더_후보_칸은_기본이_비어_있고_violations_와_따로다() -> None:
    from app.contracts import EncoderTypeCandidate, Violation  # noqa: PLC0415

    s = SentenceJudgment(sent_id="s0", text="x", verdict=Verdict.hold, hold_reason="low_conf")
    assert s.encoder_candidates == [] and s.violations == []
    s2 = s.model_copy(
        update={
            "encoder_candidates": [
                EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.7)
            ]
        }
    )
    assert s2.violations == [], "🔴 인코더 후보가 사전 근거 칸으로 새지 않는다 (D-323 결정 3)"
    with pytest.raises(ValueError):
        EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=1.5)


def test_인코더_후보만_있는_보류는_재판정에서_탈락하지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-323 결정 4 — 탈락은 사전 근거로만. 인코더 후보만 남으면 「위반 못 찾음」이다(통과 아님)."""
    from app.contracts import (  # noqa: PLC0415
        EncoderTypeCandidate,
        JudgeResponse,
        Outcome,
        Violation,
    )
    from app.routers import user as u  # noqa: PLC0415

    s = SentenceJudgment(
        sent_id="s0",
        text="x",
        verdict=Verdict.hold,
        hold_reason="low_conf",
        encoder_candidates=[EncoderTypeCandidate(violation=Violation.거짓_과장, confidence=0.9)],
    )
    base = json.loads(
        (Path(__file__).parent / "fixtures/judge/02_hold_low_conf.json").read_text(encoding="utf-8")
    )
    res = JudgeResponse.model_validate(
        {**base, "sentences": [s.model_dump(mode="json")], "outcome": Outcome.hold.value}
    )
    monkeypatch.setattr(u, "_core_judge", lambda body, product=None: ("ok", res))
    got = u._rejudge("고친 문구")  # noqa: SLF001
    assert got["status"] == "no_violation" and got["violations"] == []
