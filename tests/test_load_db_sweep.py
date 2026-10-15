"""`scripts/load_db.py` — 사전 거두기 · 수집 원장 계약 (2026-09-20 · D-254 · 감사 §2 load).

⛔ `load_dict` 만 옛 행을 안 지웠다 — 사전에서 뺀 금지 표현이 DB 에 영구히 남는다.
⛔ `load_manifest` 는 원장이 없으면 0 을 내고, 모르는 원천 행을 조용히 건너뛰었다.
🔴 DB 없이 돈다 — 가짜 커서.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from scripts import load_db


class _Cur:
    def __init__(self, terms: list[str]) -> None:
        self.terms = terms
        self.calls: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.calls.append((sql, params))

    def fetchall(self) -> list[tuple[str]]:
        return [(t,) for t in self.terms]

    def deletes(self) -> list[tuple[str, object]]:
        return [c for c in self.calls if c[0].startswith("DELETE")]


def _dict_file(tmp: pathlib.Path, terms: list[str]) -> None:
    (tmp / "banned_terms.jsonl").write_text(
        "".join(
            json.dumps({"term": t, "유형": ["거짓_과장"]}, ensure_ascii=False) + "\n" for t in terms
        ),
        encoding="utf-8",
    )


@pytest.fixture
def derived(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setattr(load_db, "DERIVED", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", False)
    return tmp_path


@pytest.mark.gate
def test_사전에서_빠진_용어를_거둔다(derived: pathlib.Path) -> None:
    _dict_file(derived, ["완치", "특효"])
    cur = _Cur(["완치", "특효", "만병통치"])
    load_db.load_dict(cur, dry=False)
    dels = cur.deletes()
    assert len(dels) == 1
    assert dels[0][1][2] == ["만병통치"]
    # 🚨 이 적재기가 넣는 칸 안에서만 거둔다
    assert dels[0][1][:2] == (load_db.DICT_FRAGMENT, load_db.DICT_KIND)


@pytest.mark.gate
def test_빈_사전이면_거두지_않고_멈춘다(derived: pathlib.Path) -> None:
    _dict_file(derived, [])
    cur = _Cur(["완치"])
    with pytest.raises(SystemExit):
        load_db.load_dict(cur, dry=False)
    assert not cur.deletes()


def test_allow_missing_으로_파일이_없으면_거두지_않고_넘어간다(
    derived: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_db, "ALLOW_MISSING", True)
    cur = _Cur(["완치"])
    assert load_db.load_dict(cur, dry=False) == (0, 0)
    assert not cur.deletes()


def test_dry_run_은_거두지_않는다(derived: pathlib.Path) -> None:
    _dict_file(derived, ["완치"])
    assert load_db.load_dict(_Cur([]), dry=True) == (1, 1)


@pytest.mark.gate
def test_수집_원장이_없으면_멈춘다(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", False)
    with pytest.raises(SystemExit):
        load_db.load_manifest(_Cur([]), dry=True)


def test_수집_원장이_없어도_allow_missing_이면_0(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "ALLOW_MISSING", True)
    assert load_db.load_manifest(_Cur([]), dry=True) == 0


def test_모르는_원천_행은_세서_찍는다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.jsonl").write_text(
        "".join(
            json.dumps({"source_id": s, "sha256": f"{i}"}) + "\n"
            for i, s in enumerate(["알던것", "모르는것", "모르는것"])
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "_sources", lambda: {"알던것": {}})
    assert load_db.load_manifest(_Cur([]), dry=True) == 1
    out = capsys.readouterr().out
    assert "모르는것 2" in out


def test_source_에_못_들어간_원천의_원장_줄은_넣지_않고_센다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 2026-09-26 — 레지스트리에는 있지만 CHECK 로 건너뛴 원천(`mfds_cosmetic_sanction`)의 줄이 FK 로 적재를 멈췄다."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.jsonl").write_text(
        "".join(
            json.dumps({"source_id": s, "sha256": f"{i}"}) + "\n"
            for i, s in enumerate(["들어간것", "건너뛴것", "건너뛴것"])
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(load_db, "ROOT", tmp_path)
    monkeypatch.setattr(load_db, "_sources", lambda: {"들어간것": {}, "건너뛴것": {}})
    cur = _Cur(["들어간것"])  # DB `source` 에 있는 것
    assert load_db.load_manifest(cur, dry=False) == 1
    inserted = [p for sql, p in cur.calls if sql.startswith("INSERT INTO collect_manifest")]
    assert [p[0] for p in inserted] == ["들어간것"]
    assert "건너뛴것 2" in capsys.readouterr().out


# ── 2026-10-15 전수 점검 — 소스 갱신 칸 · 빈 입력 가드 ─────────────────────────────────


@pytest.mark.gate
def test_소스는_넣는_칸을_모두_갱신한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 재현(임시 PG16) — 5 칸만 갱신해 판정자를 바꾸면 옛 판정자 + 새 검토자가 섞이고, 둘이 같아지면
    `ck_source_four_eyes` 에 걸려 적재가 멈췄다. 넣는 칸(source_id 밖)은 모두 `DO UPDATE` 에 있어야 한다."""
    import re  # noqa: PLC0415

    monkeypatch.setattr(
        load_db,
        "_sources",
        lambda: {
            "zz": {"decided_by": "B", "reviewed_by": "C", "attribution": "출처", "grade": "G3"}
        },
    )
    cur = _Cur([])
    load_db.load_sources(cur, dry=False)
    sql = next(s for s, _ in cur.calls if "INSERT INTO source " in s)
    cols = re.search(r"INSERT INTO source \(([^)]*)\)", sql).group(1)
    inserted = {c.strip() for c in cols.split(",")} - {"source_id"}
    updated = set(re.findall(r"(\w+)=EXCLUDED\.\1", sql))
    assert inserted <= updated, f"갱신 안 되는 칸: {sorted(inserted - updated)}"


@pytest.mark.gate
def test_별표_폴더가_비면_멈춘다(derived: pathlib.Path) -> None:
    """🔴 폴더는 있는데 내용 있는 별표 파일이 0 이면 별표 없이 성공을 냈다(뒤에 embed FK 오류로 터짐)."""
    (derived / "law_article.jsonl").write_text(
        json.dumps({"파일": "법_000001_x.xml", "법령": "법"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (derived / "law_norm").mkdir()
    (derived / "law_norm" / "빈.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="별표 파일이 하나도 없다"):
        load_db.load_documents(_Cur([]), dry=True)


@pytest.mark.gate
def test_인정_문구가_0_행이면_멈춘다(derived: pathlib.Path) -> None:
    """🔴 파일은 있는데 쓸 수 있는 행이 0 이면 0 행을 넣고 성공으로 냈다 (D-220)."""
    (derived / "hf_api_labels.jsonl").write_text(
        json.dumps({"원천": "mfds_hf_individual", "PRIMARY_FNCLTY": "", "RAWMTRL_NM": ""}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="0 이다"):
        load_db.load_product_fact(_Cur([]), dry=True)


@pytest.mark.gate
def test_제재표_원천에_행이_없으면_표를_거두지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 행이 0 이면 `NOT (rule_key = ANY('{}'))` 가 표 전체를 지웠다 — 빈 선언으로는 거두지 않는다 (D-220)."""
    from scripts import sanction_rule as sr  # noqa: PLC0415

    monkeypatch.setattr(sr, "load_rules", lambda: {"rows": []})
    monkeypatch.setattr(sr, "lint", lambda spec: [])
    monkeypatch.setattr(sr, "signature", lambda spec: None)
    monkeypatch.setattr(sr, "plan_sha", lambda spec: "0" * 12)
    cur = _Cur([])
    with pytest.raises(SystemExit, match="행이 없다"):
        load_db.load_sanction_rule(cur, dry=False)
    assert not cur.deletes()
