"""판 채택과 **원문 폴더 이름** (2026-09-18 · D-143 · D-99).

⛔ 실측 사고. `ingest.cmd_register()` 가 `store.raw_dir(source_id)` 를 불러
   `law_go_kr` 파일을 **`data/raw/law_go_kr/`** 에 넣었다. 추출기는 `data/raw/law/` 를 보므로
   **화장품법 334노드가 코퍼스에서 조용히 사라졌다** — `law_article` 2,207 → 1,873.
   아무것도 실패하지 않았다. 게이트 337개가 전부 초록이었다.

   원인은 둘이다 —
     ① 소스 id ≠ 원문 폴더 이름인 소스가 **넷**인데 `register` 가 그것을 몰랐다
     ② 같은 매핑이 `preprocess/inventory.ALIAS` 에 따로 있었고 `collect` 는 안 썼다 (D-99)

🔴 그리고 그 사고가 드러낸 더 큰 빈칸 — **판을 채택하는 명령이 없었다.**
   `collect` 가 판을 만들고(규약 2) `current_files` 가 멈추는데(D-143) 그 다음이 없어서,
   사람이 손으로 옮기다가 원장이 깨졌다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import ingest, store

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.gate
def test_원문_폴더_매핑이_한_곳에만_있다() -> None:
    """🔴 D-99 — 같은 표가 두 곳에 있으면 갈린다. 실제로 갈려서 사고가 났다."""
    from preprocess import inventory

    assert inventory.ALIAS is store.FAMILY_OF, (
        "preprocess/inventory.ALIAS 가 collect/store.FAMILY_OF 와 다른 객체다 — "
        "표가 두 벌이면 한쪽만 갱신된다 (D-99)"
    )


@pytest.mark.gate
def test_register_는_계열_폴더에_넣는다() -> None:
    """🔴 소스 id 가 아니라 **원문 폴더**다. 이 검사가 없어서 334노드가 사라졌다.

    🚨 코드가 `raw_dir_of` 를 쓰는지 본다 — 폴더를 실제로 만들지 않고 이름만 확인한다.
    """
    src = pathlib.Path(ingest.__file__).read_text(encoding="utf-8")
    assert "raw_dir_of(source_id)" in src, (
        "cmd_register 가 raw_dir_of(소스id) 를 쓰지 않는다 — "
        "소스 id 로 폴더를 만들면 폴더 이름이 다른 넷에서 추출기가 못 읽는다"
    )
    assert "store.raw_dir(source_id)" not in src, (
        "cmd_register 가 아직 raw_dir(소스id) 를 쓴다 — 2026-09-18 사고의 그 줄이다"
    )
    # 표에 있는 넷은 실제로 id 와 폴더가 다르다 — 표가 비면 이 검사가 무의미해진다
    diff = [k for k, v in store.FAMILY_OF.items() if v[0] != k]
    assert len(diff) >= 4, f"폴더 이름이 소스 id 와 다른 소스가 넷 미만이다: {diff}"


@pytest.mark.gate
def test_채택하는_명령이_있다() -> None:
    """🚨 `collect`(만든다) · `current_files`(멈춘다) 다음 칸이 비어 있었다 (D-143)."""
    import launcher

    names = {i.name or launcher.cli_name(i.callback) for i in launcher.app.registered_commands}
    assert "adopt" in names, "판을 채택하는 명령이 없다 — 사람이 손으로 옮기면 원장이 깨진다"
    assert hasattr(ingest, "cmd_adopt")


def test_채택이_원장에_새_행을_붙인다(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 **게이트가 아니다** — 원장·원문을 건드리므로 tmp 로 돌린다 (D-89 와 같은 자리).

    이것이 채택의 핵심이다. 이름만 바꾸면 원본 경로의 바이트가 그 경로에 기록된 어느
    sha 와도 달라 `doctor --hash` 가 🔴 훼손으로 찍는다.
    """
    raw = tmp_path / "data" / "raw" / "가짜계열"
    raw.mkdir(parents=True)
    ledger = tmp_path / "data" / "manifest.jsonl"
    monkeypatch.setattr(store, "RAW", tmp_path / "data" / "raw")
    monkeypatch.setattr(store, "MANIFEST", ledger, raising=False)
    monkeypatch.setattr(store, "FAMILY_OF", {"가짜소스": ("가짜계열",)})
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest.registry, "spec", lambda sid: {"url": "http://example/x"})

    (raw / "doc_1.xml").write_text("종전", encoding="utf-8", newline="\n")
    (raw / f"doc_1{store.EDITION_MARK}20260918.xml").write_text(
        "새판", encoding="utf-8", newline="\n"
    )

    assert ingest.cmd_adopt("가짜소스", "doc_1") == 0
    assert (raw / "doc_1.xml").read_text(encoding="utf-8") == "새판", "판이 원본 자리로 안 올라갔다"
    assert not list(raw.glob(f"*{store.EDITION_MARK}*")), "판 파일이 남아 있다"

    rows = [json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows, "원장에 행이 안 붙었다 — doctor 가 훼손으로 본다"
    assert rows[-1]["path"].endswith("doc_1.xml"), rows[-1]
    assert rows[-1]["source_id"] == "가짜소스"


def test_판이_둘이면_멈춘다(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 어느 판을 쓸지는 사람이 정한다 (D-143). 자동으로 최신을 고르지 않는다."""
    raw = tmp_path / "data" / "raw" / "가짜계열"
    raw.mkdir(parents=True)
    monkeypatch.setattr(store, "RAW", tmp_path / "data" / "raw")
    monkeypatch.setattr(store, "FAMILY_OF", {"가짜소스": ("가짜계열",)})
    monkeypatch.setattr(ingest.registry, "spec", lambda sid: {"url": ""})
    for day in ("20260917", "20260918"):
        (raw / f"doc_1{store.EDITION_MARK}{day}.xml").write_text(
            day, encoding="utf-8", newline="\n"
        )
    assert ingest.cmd_adopt("가짜소스", "doc_1") == 1
