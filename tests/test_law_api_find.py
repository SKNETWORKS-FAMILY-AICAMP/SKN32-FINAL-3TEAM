"""`--find` 는 후보를 **전부** 내고 이미 가진 ID 를 표시한다 (2026-09-25 · C1).

🔴 막는 것 — 1번 후보가 이미 `TARGETS` 에 있는 ID 일 때(09-05 37971 · 09-25 69549) 그것을 새것인 양 옮기는 것.
🚨 **네트워크를 쓰지 않는다.** `_call` · `registry.require` · `env.get` 을 갈아 끼운다.
"""

from __future__ import annotations

import pytest

from collect import law_api as L

pytestmark = pytest.mark.gate

#: 09-25 실측 모양 — 「식품등의 표시기준」 검색의 1번 후보가 이미 가진 69549 였다
LIST = """<?xml version="1.0" encoding="UTF-8"?>
<AdmRulSearch><totalCnt>2</totalCnt>
<admrul><행정규칙ID>69549</행정규칙ID><행정규칙명>식품등의 부당한 표시 또는 광고의 내용 기준</행정규칙명><시행일자>20251204</시행일자></admrul>
<admrul><행정규칙ID>99999</행정규칙ID><행정규칙명>식품등의 표시기준</행정규칙명><시행일자>20260101</시행일자></admrul>
</AdmRulSearch>""".encode()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    def fake_call(base: str, oc: str, **params: str) -> bytes:
        calls.append(params)
        return LIST

    monkeypatch.setattr(L, "_call", fake_call)
    monkeypatch.setattr(L.env, "get", lambda name: "k")
    monkeypatch.setattr(L.registry, "require", lambda sid, use: None)
    monkeypatch.setattr(L, "PENDING", [("admrul", "식품등의 표시기준", "S1-02")])
    return calls


def test_후보는_서버_순서대로_전부_나온다(fake: list) -> None:
    got = L.candidates("k", "admrul", "식품등의 표시기준")
    assert [i for i, _, _ in got] == ["69549", "99999"]
    # search() 는 여전히 첫 후보 — 그래서 사람 확인에 쓰지 않는다
    assert L.search("k", "admrul", "식품등의 표시기준")[0] == "69549"


def test_find_는_이미_가진_ID_와_이름_일치를_표시한다(
    fake: list, capsys: pytest.CaptureFixture[str]
) -> None:
    L.find_pending()
    out = capsys.readouterr().out
    line_have = next(ln for ln in out.splitlines() if '"69549"' in ln)
    line_new = next(ln for ln in out.splitlines() if '"99999"' in ln)
    assert "이미 TARGETS" in line_have
    assert "이름 일치" in line_new and "이미 TARGETS" not in line_new
    assert "후보 2건 · 이름 완전일치 1건" in out
