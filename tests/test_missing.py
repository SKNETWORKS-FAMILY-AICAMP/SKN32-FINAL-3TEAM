"""원장에 있고 디스크에 없는 것을 **왜 없는지**로 가른다 (D-253 · `collect/missing.py`).

팀장 — *「doctor 은 제 기능을 충분히 하고 있나?」* (2026-09-20). 실측 53개 중 36개가 종전 세 갈래 어디에도 없었다.
★ 전부 임시 폴더다 — 진짜 `data/` 와 `.env` 는 안 본다.
🚨 여기서 막는 것 —
   ① 수집기가 안 받기로 한 것을 「재수집하면 닫힌다」로 안내하는 것 (서식 34개)
   ② 옮긴 흔적을 결손으로 세는 것 — 그리고 **크기가 다른 옛 파일**을 옮긴 곳으로 믿는 것
   ③ 기기 칸이 있는데도 「다른 기기 것인지 모른다」고 하는 것 · 이 기기가 받은 것이 사라져도 조용한 것
   ④ 별칭을 모르는 기기가 「다른 기기 것」이라고 단정하는 것
"""

from __future__ import annotations

import pathlib

import pytest

from collect import law_annex, missing

pytestmark = pytest.mark.gate

G3 = lambda _sid: "G3"  # noqa: E731


def _put(root: pathlib.Path, rel: str, size: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)


def _row(
    path: str, sha: str = "s", size: int = 5000, sid: str = "src", device: str | None = None
) -> dict:
    r = {"source_id": sid, "path": path, "sha256": sha, "bytes": size}
    if device is not None:
        r["device"] = device
    return r


def test_같은_내용이_다른_경로에_있으면_옮겨짐이다(tmp_path) -> None:
    _put(tmp_path, "data/raw/law/law_1.xml", 145625)
    rows = [
        _row("data\\raw\\law\\law_1__c20260917.xml", "a64e", 145625, "law_go_kr"),
        _row("data\\raw\\law\\law_1.xml", "a64e", 145625, "law_go_kr"),
    ]
    got = missing.classify(rows, root=tmp_path, me="clone-b", grade_of=G3, rules={})
    assert got == {"data/raw/law/law_1__c20260917.xml": ("moved", "data/raw/law/law_1.xml")}


def test_크기가_다른_옛_파일은_옮긴_곳으로_믿지_않는다(tmp_path) -> None:
    """원장은 `page_7.json` 에 새 sha 를 적었지만 디스크의 `page_7.json` 은 옛 판이다(09-14 실측 모양)."""
    _put(tmp_path, "data/raw/hf/page_7.json", 50083)  # 옛 판 크기
    rows = [
        _row("data/raw/hf/page_7__c20260909.json", "new", 50023),
        _row("data/raw/hf/page_7.json", "old", 50083),
        _row("data/raw/hf/page_7.json", "new", 50023),
    ]
    got = missing.classify(rows, root=tmp_path, me="clone-b", grade_of=G3, rules={})
    assert got["data/raw/hf/page_7__c20260909.json"][0] != "moved"


def test_수집기가_안_받는다고_선언한_것은_정책_제외다(tmp_path) -> None:
    rows = [_row("data\\raw\\law\\annex\\008741_form_0001_00.json", sid="law_go_kr")]
    got = missing.classify(rows, root=tmp_path, me="clone-b", grade_of=G3, rules=missing.declared())
    assert got["data/raw/law/annex/008741_form_0001_00.json"][0] == "excluded"


def test_서식_선언은_별표를_삼키지_않는다() -> None:
    import fnmatch

    pats = [p for p, _ in law_annex.NOT_KEPT]
    assert any(fnmatch.fnmatchcase("law/annex/008741_form_0006_02.json", p) for p in pats)
    assert not any(fnmatch.fnmatchcase("law/annex/008741_annex_0001_00.json", p) for p in pats)


def test_g2_는_지우는_것이_규칙이다(tmp_path) -> None:
    rows = [_row("data/raw/g2src/a.json", sid="g2src")]
    got = missing.classify(rows, root=tmp_path, me="x", grade_of=lambda s: "G2", rules={})
    assert got["data/raw/g2src/a.json"][0] == "g2"


def test_오류_판을_치우고_정상_판이_있으면_치움이다(tmp_path) -> None:
    _put(tmp_path, "data/raw/hf/page_0001.json", 56342)
    rows = [
        _row("data/raw/hf/page_0001__c20260908.json", "err", 146),
        _row("data/raw/hf/page_0001.json", "ok", 56342),
    ]
    got = missing.classify(rows, root=tmp_path, me="x", grade_of=G3, rules={})
    assert got["data/raw/hf/page_0001__c20260908.json"][0] == "cleared"


def test_기기_칸이_있으면_다른_기기와_유실을_가른다(tmp_path) -> None:
    rows = [
        _row("data/raw/s/theirs.json", "t", device="collector-1"),
        _row("data/raw/s/mine.json", "m", device="clone-b"),
    ]
    got = missing.classify(rows, root=tmp_path, me="clone-b", grade_of=G3, rules={})
    assert got["data/raw/s/theirs.json"][0] == "other"
    assert got["data/raw/s/mine.json"][0] == "lost", "🔴 이 기기가 받은 것이 사라졌는데 조용하다"
    assert missing.needs_eyes(got) == 1


def test_별칭을_모르면_다른_기기_것이라_단정하지_않는다(tmp_path) -> None:
    rows = [_row("data/raw/s/a.json", device="collector-1")]
    got = missing.classify(rows, root=tmp_path, me=None, grade_of=G3, rules={})
    assert got["data/raw/s/a.json"][0] == "legacy"


def test_기기_칸_이전_줄은_못_가른다고_말한다(tmp_path) -> None:
    rows = [
        _row("data/raw/law/decc_1.xml", sid="law_go_kr"),
        _row("data/raw/law/admrul_1.xml", sid="law_go_kr"),
    ]
    got = missing.classify(rows, root=tmp_path, me="clone-b", grade_of=G3, rules={})
    assert got["data/raw/law/decc_1.xml"][0] == "query"
    assert got["data/raw/law/admrul_1.xml"][0] == "legacy"


def test_있는_파일은_돌려주지_않는다(tmp_path) -> None:
    _put(tmp_path, "data/raw/s/a.json", 10)
    assert (
        missing.classify([_row("data/raw/s/a.json")], root=tmp_path, me="x", grade_of=G3, rules={})
        == {}
    )


def test_이유_표의_순서와_정상_여부() -> None:
    """🚨 순서가 가르는 순서다 — `moved` 가 맨 앞, 🔴 는 `lost` 하나."""
    assert list(missing.REASONS)[0] == "moved"
    assert [k for k, v in missing.REASONS.items() if v[0] == "🔴"] == ["lost"]


# ══════════════════════════════════════════════════════════
# 🆕 2026-09-21 — 경보 수준 한 곳 · 역할을 본다
# ══════════════════════════════════════════════════════════
def test_경보_수준은_역할을_본다() -> None:
    """🔴 사본은 원문을 쓰지 않는다(D-226) — 원장으로 못 가르는 것(`legacy`·`query`)은 사본에서 볼 것이 아니다.
    ★ `lost` 는 어느 역할에서도 🔴 · 정본·역할 없음은 종전 그대로 🟡."""
    for who in ("canonical", "replica", None):
        assert missing.level("lost", who) == "red"
        for normal in ("moved", "excluded", "g2", "cleared", "other"):
            assert missing.level(normal, who) == "ok"
    for reason in ("legacy", "query"):
        assert missing.level(reason, "replica") == "ok"
        assert missing.level(reason, "canonical") == "eyes"
        assert missing.level(reason, None) == "eyes"  # CI · 역할 모름 — 접는 쪽으로 틀리지 않는다


def _legacy_rows() -> list[dict]:
    """진짜 저장소에 **없는** 경로 — 기기 칸 없음(legacy) 하나 · 질의 기반(query) 하나."""
    return [
        _row("data/raw/mfds_sanctions/zz_pytest_absent.json", sid="mfds_sanctions"),
        _row("data/raw/law/decc_zz_pytest_absent.xml", sid="law_go_kr"),
    ]


def test_doctor_는_사본에서_원문_결손을_접고_수집을_권하지_않는다(capsys) -> None:
    """🔴 2026-09-21 사용자 실행(클론 A) — 「사람이 볼 것 5,545개」와 「이 기기에서 쓸 원천이면 다시 받는다」.
    ★ 반대 대조 — 정본에서는 같은 줄이 🟡 로 펴지고 안내가 나온다."""
    from scripts import doctor

    rows = _legacy_rows()
    assert doctor._report_missing(rows, len(rows), who="replica") == 0
    out = capsys.readouterr().out
    assert "사람이 볼 것 **0개**" in out and "사본은 원문을 쓰지 않는다" in out, out
    assert "다시 받는다" not in out, out
    assert doctor._report_missing(rows, len(rows), who="canonical") == 0
    out = capsys.readouterr().out
    assert "사람이 볼 것 **2개**" in out and "다시 받는다" in out, out


def _inventory_world(tmp_path, monkeypatch, role: str | None) -> None:
    import json

    from preprocess import inventory

    (tmp_path / "data").mkdir()
    (tmp_path / "data_sources.yaml").write_text(
        "sources:\n  mfds_sanctions: {status: collect, grade: G3}\n", encoding="utf-8"
    )
    ledger = tmp_path / "data" / "manifest.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in _legacy_rows()[:1]) + "\n", encoding="utf-8")
    monkeypatch.setattr(inventory, "ROOT", tmp_path)
    monkeypatch.setattr(inventory, "RAW", tmp_path / "data" / "raw")
    monkeypatch.setattr(inventory, "MANIFEST", ledger)
    monkeypatch.setattr(missing, "role", lambda: role)


def test_inventory_는_사본에서_다시_받으라고_하지_않는다(tmp_path, monkeypatch, capsys) -> None:
    """🔴 종전 — 하나도 없는 소스를 이유를 안 보고 🔴 「이 기기에서 쓰려면 다시 받는다」로 찍었다."""
    from preprocess import inventory

    _inventory_world(tmp_path, monkeypatch, "replica")
    assert inventory.main() == 0
    out = capsys.readouterr().out
    body = out.splitlines()[1:]  # 첫 줄은 열 이름(「🔴없음」)이다
    assert not [x for x in body if "🔴" in x], out
    assert "다시 받는다" not in out, out
    assert "사본은 원문을 쓰지 않는다" in out, out


def test_inventory_와_doctor_는_같은_결손에_같은_색을_낸다(tmp_path, monkeypatch, capsys) -> None:
    """🔴 D-253 맥락 4 — 같은 결손을 inventory 는 🔴, doctor 는 🟡 로 찍었다. 정본에서 둘 다 🟡 여야 한다."""
    from preprocess import inventory
    from scripts import doctor

    _inventory_world(tmp_path, monkeypatch, "canonical")
    inventory.main()
    inv = capsys.readouterr().out
    doctor._report_missing(_legacy_rows()[:1], 1, who="canonical")
    doc = capsys.readouterr().out
    line = next(x for x in inv.splitlines() if x.strip().startswith("mfds_sanctions"))
    assert "🟡" in line and "🔴" not in line, line
    assert doc.lstrip().startswith("🟡"), doc


def test_경보_수준을_정하는_자리는_한_곳이다() -> None:
    """🚨 두 도구가 `REASONS[...][1]` 로 색을 따로 정하면 다시 갈린다 (D-99)."""
    import inspect

    from preprocess import inventory
    from scripts import doctor

    for mod in (inventory, doctor):
        src = inspect.getsource(mod)
        assert "missing.level(" in src or "missing_mod.level" in src or "levels(" in src, mod
        assert "REASONS[r][1]" not in src, f"🔴 {mod.__name__} 가 수준을 따로 정한다"
