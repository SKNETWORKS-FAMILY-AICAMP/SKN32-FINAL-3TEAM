"""화면에 나가는 근거 · 위험도 · 고쳐 쓰기 표시 — 판정을 바꾸지 않는 표시 결함 넷 (🆕 2026-10-08 · 소유자 팀장).

🔴 무엇을 막나
   ① 보류 문장 옆 초록 「위험도 R0」 — R0 은 「특이사항 없음」(D-280)이라 보류 옆에 서면 통과로 읽힌다
   ② 목 붙은 사전 근거가 평가 도구의 호 셈에서 조용히 빠지는 것 — 그래프의 꼴과 되읽는 꼴이 두 벌이었다 (D-99)
   ③ 인용 자격(`U3_cite`)이 열린 법령 조문인데도 `quote` 가 늘 비는 것 (D-224 ④)
   ④ 고쳐 쓰기 서버를 두지 않은 환경에서 누를 수 없는 버튼과 「잠시 뒤 다시」라는 거짓 안내
⛔ 이 파일이 보장하지 못하는 것 — 실제 DB 에서 `citable` 이 참으로 오는지(질의문만 본다) · 판정 결과의 수.
"""

from __future__ import annotations

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
    ],
)
def test_인용_자격이_열린_청크만_조문_글을_싣는다(kw: dict, want: str | None) -> None:
    a = g._evidence_article(_hit(**kw))  # noqa: SLF001
    assert a is not None
    assert a.quote == want


@pytest.mark.parametrize("sql", [rt.SQL_VECTOR, rt.SQL_LITERAL, rt.SQL_LEXICAL])
def test_모든_질의가_인용_자격을_읽는다(sql: str) -> None:
    assert "'U3_cite'" in sql
    assert "citable" in rt._NAMES  # noqa: SLF001


# ── ④ 고쳐 쓰기를 꺼 둔 환경 ─────────────────────────────────────────────


def test_꺼_둔_환경에서는_서버를_부르지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sllm_client, "ENABLED", False)
    assert sllm_client.rewrite("문구", ["거짓_과장"]) == ("off", None)


def test_꺼_둔_환경에서는_버튼_대신_안내를_그린다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sllm_client, "ENABLED", False)
    html = TestClient(app).get("/u/preview/02_hold_low_conf").text
    assert 'action="/u/review/rewrite"' not in html
    assert "이 환경에서는 문장 고쳐 쓰기를 제공하지 않아요" in html


def test_켜_둔_환경에서는_버튼이_있다(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ 로컬 · 시연의 동작은 바뀌지 않는다 — 기본값(`COPYLANE_SLLM_URL` 없음)이 켜짐이다."""
    monkeypatch.setattr(sllm_client, "ENABLED", True)
    html = TestClient(app).get("/u/preview/02_hold_low_conf").text
    assert 'action="/u/review/rewrite"' in html
