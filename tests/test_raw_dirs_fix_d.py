"""추출기가 읽는 원문 폴더 ⊂ `store.families(원천)` (2026-09-20 · D-254 · 감사 §1-7).

⛔ 2026-09-18 — `register law_go_kr` 가 `data/raw/law_go_kr/` 에 넣었고 추출기는 `data/raw/law/` 를 봤다.
   화장품법 334노드가 조용히 사라졌는데 게이트 337개가 전부 초록이었다 — **대조하는 게이트가 없었다.**
★ 추출기의 폴더 상수를 **실제로 불러** 표와 대조한다. 폴더를 만들지 않는다 (`store.family_path`).

🚨 목록은 손으로 적는다 — 추출기가 늘면 여기에 한 줄 보탠다. 빠진 추출기는
   `test_EXTRACTORS_의_추출기가_목록에_있다` 가 잡는다.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

from collect import store

#: (모듈, 폴더를 내는 이름, 원천 id). 이름이 `()` 로 끝나면 원천 id 를 받는 함수다.
READERS: list[tuple[str, str, str]] = [
    ("preprocess.law_article", "LAW", "law_go_kr"),
    ("preprocess.law_norm", "ANNEX", "law_go_kr"),
    ("preprocess.law_case", "LAW", "law_go_kr"),
    ("preprocess.mfds_hf", "RAW_DIR", "mfds_hf_ingredient_board"),
    ("preprocess.mfds_press", "RAW_DIR", "mfds_press"),
    ("preprocess.ftc_extract", "RAW", "ftc_decisions_body"),
    ("preprocess.sanctions_scan", "raw_of()", "mfds_sanctions"),
    # 🚨 아래는 아직 상수를 손으로 적는다(이번 고침 범위 밖) — 그래도 **값이** 표와 맞는지는 본다
    ("preprocess.mfds_casebook", "RAW_DIR", "mfds_casebook"),
    ("preprocess.mfds_guide", "RAW_DIR", "mfds_special_use_guide"),
    ("preprocess.ftc_triage", "RAW", "ftc_decisions_body"),
    ("preprocess.mfds_cosmetic_qa", "RAW_DIR", "mfds_cosmetic_ad_qa"),
]


def _dir_of(mod: str, name: str, source: str) -> pathlib.Path:
    m = importlib.import_module(mod)
    v = getattr(m, name[:-2])(source) if name.endswith("()") else getattr(m, name)
    p = pathlib.Path(v)
    return p if p.is_absolute() else store.ROOT / p  # 상대 경로는 저장소 뿌리에서 도는 것이 전제다


@pytest.mark.gate
@pytest.mark.parametrize(("mod", "name", "source"), READERS)
def test_추출기_원문_폴더가_원천의_계열_안에_있다(mod: str, name: str, source: str) -> None:
    d = _dir_of(mod, name, source)
    rel = d.resolve().relative_to(store.RAW.resolve())
    assert rel.parts[0] in store.families(source), (
        f"{mod}.{name} 이(가) 원문 폴더 {rel.as_posix()} 를 읽는데 {source} 의 계열은 "
        f"{store.families(source)} 다 — 수집기·register 가 다른 폴더에 쓰면 **조용히** 빠진다 (2026-09-18)"
    )


@pytest.mark.gate
def test_EXTRACTORS_의_추출기가_목록에_있다() -> None:
    """🚨 추출기가 늘었는데 위 목록에 안 오르면 대조가 비는 것이다 (D-220 — 모르는 것은 실패)."""
    from preprocess import EXTRACTORS

    listed = {m for m, _, _ in READERS}
    missing = sorted(set(EXTRACTORS.values()) - listed)
    assert not missing, f"원문 폴더 대조 목록(READERS)에 없는 추출기: {missing}"


@pytest.mark.gate
def test_family_path_는_남의_계열을_거부한다() -> None:
    with pytest.raises(store.StoreError):
        store.family_path("law_go_kr", "law_go_kr")
    assert store.family_path("mfds_press", "mfds_press_pdf").name == "mfds_press_pdf"


@pytest.mark.gate
def test_openapi_수집은_계열_폴더에_쓴다() -> None:
    """🟡 `collect ftc_decisions_api` 가 표(`ftc`)와 다른 `ftc_decisions_api/` 에 썼다 (감사 §1-7)."""
    src = pathlib.Path(importlib.import_module("collect.openapi").__file__).read_text(
        encoding="utf-8"
    )
    assert "store.family_path(source_id)" in src
    assert "source_id,\n            source_id," not in src, "save_raw 에 소스 id 를 폴더로 넘긴다"


@pytest.mark.gate
def test_보도자료_수집기는_폴더_이름을_표에서_꺼낸다() -> None:
    """🆕 2026-09-21 — 수집기 쪽도 같은 대조다. ⛔ `collect/mfds_press.py` 가 `"mfds_press"` 와
    `f"{FAMILY}_pdf"` 를 따로 박았고, 옛 격리 폴더를 `store.raw_dir()` 로 불러 **돌 때마다 만들었다**.
    """
    m = importlib.import_module("collect.mfds_press")
    assert store.families("mfds_press") == (m.FAMILY, m.PDF_FAMILY)
    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    assert 'raw_dir(f"{FAMILY}_' not in src, "계열 이름을 문자열로 조립해 폴더를 만든다"
    assert 'FAMILY = "' not in src, "계열 이름을 손으로 적었다 — store.FAMILY_OF 를 쓴다"
