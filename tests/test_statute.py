"""조문 인용이 라벨의 정본이다 — 유형은 인용에서 계산한다 (D-282 · D-237 집행 · D-283).

🔴 무엇을 막나
   ① 호 → 유형 대응이 여러 벌로 갈리는 것 (D-99) — 종전 네 벌이 5호·8호에서 서로 달랐다
   ② 유형과 조문이 따로 움직이는 것 — 골든셋 라벨이 근거 조문에서 계산된 값과 다르면 빨강
   ③ 조문 근거가 없는 사람 8유형 라벨이 평가로 새는 것 (D-283)
   ④ 대응표가 조문 본문과 어긋나는 것 — 식품 6호는 비방, 7호는 부당 비교다
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re

import pytest

from app.contracts import Violation
from collect import statute

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAW_ARTICLE = ROOT / "data" / "derived" / "law_article.jsonl"
GOLDEN = ROOT / "data" / "derived" / "golden" / "golden.jsonl"


# ── 인용 꼴 ────────────────────────────────────────────────────────────────


def test_인용_꼴은_만들고_읽으면_같다() -> None:
    c = statute.food(5, "다")
    assert c == "013094:제8조제1항제5호|다목"
    assert statute.parse(c) == ("013094", 8, 1, 5, "다")
    assert statute.ho_key(c) == "013094:제8조제1항제5호"
    assert statute.fair(3) == "002011:제3조제1항제3호"


def test_꼴이_아닌_인용은_멈춘다() -> None:
    with pytest.raises(ValueError):
        statute.parse("식품표시광고법 제8조제1항제4호")
    with pytest.raises(ValueError):
        statute.parse("013094:제8조제1항")


def test_한국어_근거를_인용으로_읽는다() -> None:
    assert statute.from_korean("식품표시광고법 제8조제1항제4호") == statute.food(4)
    assert statute.from_korean("표시광고법 제3조제1항제3호") == statute.fair(3)
    assert statute.from_korean(
        "식품표시광고법 제8조제1항제5호(시행령 [별표 1] 제5호다목)"
    ) == statute.food(5, "다")


def test_다른_호의_목이나_모르는_법은_멈춘다() -> None:
    """🔴 조용히 떼지 않는다 (D-220)."""
    with pytest.raises(ValueError):
        statute.from_korean("식품표시광고법 제8조제1항제4호(시행령 [별표 1] 제5호다목)")
    with pytest.raises(ValueError):
        statute.from_korean("약사법 제68조제1항제1호")


# ── 대응표 ────────────────────────────────────────────────────────────────


@pytest.mark.gate
def test_파생_유형은_계약_열거형_안에_있다() -> None:
    """🔴 대응표가 계약(`Violation`)에 없는 이름을 내면 적재(`violation_t`)에서 터진다."""
    names = {v.value for v in Violation}
    bad = [(c, t) for c, t in statute.table() if t not in names]
    assert not bad, f"계약에 없는 파생 유형: {bad}"


@pytest.mark.gate
def test_모르는_조문은_유형이_없다() -> None:
    """🔴 기본 유형으로 떨어지지 않는다 (D-220) — 식품 8~10호 · 화장품 13①4 는 None."""
    for h in (8, 9, 10):
        assert statute.type_of(statute.food(h)) is None
    assert statute.type_of(statute.cite(*statute.COSM, 4)) is None
    assert statute.types_of([statute.food(8), statute.food(4)]) == ["거짓_과장"]
    assert statute.untyped([statute.food(8), statute.food(4)]) == [statute.food(8)]


@pytest.mark.gate
def test_체험기는_5호_다목의_파생이다() -> None:
    """🔄 D-255 ① 개정 (D-282) — 후기는 형식 라벨이 아니라 [별표 1] 5호 다목이다. 목이 없으면 5호 = 기만."""
    assert statute.type_of(statute.food(5, "다")) == "후기_체험기_기만"
    assert statute.type_of(statute.food(5)) == "소비자_기만"
    assert statute.type_of(statute.food(5, "나")) == "소비자_기만"


#: 조문 본문에 반드시 있어야 할 낱말 — 대응표가 본문과 어긋나면 빨강 [문헌]
_BODY_WORDS: dict[tuple[str, int, int, int], str] = {
    (*statute.FOOD, 1): "질병",
    (*statute.FOOD, 2): "의약품",
    (*statute.FOOD, 3): "건강기능식품",
    (*statute.FOOD, 4): "거짓",
    (*statute.FOOD, 5): "기만",
    (*statute.FOOD, 6): "비방",
    (*statute.FOOD, 7): "비교",
    (*statute.FAIR, 1): "거짓",
    (*statute.FAIR, 2): "기만",
    (*statute.FAIR, 3): "비교",
    (*statute.FAIR, 4): "비방",
    (*statute.COSM, 1): "의약품",
    (*statute.COSM, 2): "기능성화장품",
}
_FILE_OF = {"013094": "law_013094", "002011": "law_002011", "002015": "law_002015"}


def test_대응표는_조문_본문과_맞는다() -> None:
    """🔴 식품 6호가 비방 · 7호가 부당 비교다 — 사람 라벨 시트 번호와 반대였다 (D-283).

    코퍼스(`law_article.jsonl`)가 없는 기기에서는 건너뛴다 — 🚨 「안 본 것」이지 통과가 아니다 (D-188).
    """
    if not LAW_ARTICLE.exists():
        pytest.skip(f"{LAW_ARTICLE} 가 없다 — 조문 본문 대조를 **하지 못했다**")
    body: dict[tuple[str, int, int, int], str] = {}
    for line in LAW_ARTICLE.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        for law, pre in _FILE_OF.items():
            if not str(r.get("파일", "")).startswith(pre):
                continue
            m = re.match(r"^(\d+)\.", str(r.get("본문", "")))
            if m and str(r.get("항", "")).startswith("①"):
                body[(law, int(r["조"]), 1, int(m.group(1)))] = r["본문"]
    for k, word in _BODY_WORDS.items():
        assert k in body, f"조문 {k} 본문을 코퍼스에서 못 찾았다"
        assert word in body[k], f"{k} 본문에 「{word}」가 없다 — 대응표를 본다: {body[k]}"
        assert statute.type_of(statute.cite(*k)) is not None


# ── 사본은 정본과 같다 (D-99) ───────────────────────────────────────────


@pytest.mark.gate
def test_호_유형_사본은_정본과_같다() -> None:
    """🔴 추출기·스캐너·시트 도구에 남은 대응은 `collect.statute` 와 같아야 한다 (D-99)."""
    from preprocess import ftc_extract, guide_label, inject, interp_scan, mfds_casebook

    for h in range(1, 8):
        want = statute.type_of(statute.food(h))
        assert interp_scan.HO_TYPE[str(h)] == want
        assert guide_label.TYPE_OF[str(h)] == want
        assert mfds_casebook.HO_TYPES[h][0] == want
    assert mfds_casebook.HO_TYPES[5] == ("소비자_기만", "후기_체험기_기만")

    for _word, label, article in ftc_extract.TYPES:
        ho = int(re.search(r"제(\d+)호", article).group(1))
        assert statute.type_of(statute.fair(ho)) == label, (article, label)

    for rid, _desc, label, basis in inject.RULES:
        assert statute.types_of([statute.from_korean(basis)]) == [label], (rid, basis, label)

    # 2021 사례집 시트 — 함수 안 표라 소스로 대조한다
    from scripts import casebook2021_sheet

    src = inspect.getsource(casebook2021_sheet)
    for h in range(1, 8):
        want = statute.type_of(statute.food(h))
        assert re.search(rf"\b{h}: \[\"{want}\"\]", src), f"casebook2021_sheet TYPE {h} ≠ {want}"


# ── 사람 8유형 라벨은 평가 입력이 아니다 (D-283) ─────────────────────────


@pytest.mark.gate
def test_사람_8유형_라벨은_분할의_입력이_아니다() -> None:
    """🔴 지시서 8유형으로 붙인 라벨은 조문 근거가 없다 — 분할·평가로 들어오면 빨강 (D-283).

    ⛔ 09-17(D-243)부터 넷째 입력이었다. 해설서 호가 조문 원문 기준으로 붙으면 `guide_docs()` 가 그것을 낸다.
    """
    from preprocess import split

    # 🔄 2026-09-25 (D-285 개정 4) — 해설서 **조문·조건 판**(`labels/guide_statute/`)은 대기가 0 이 되면 입력이 된다.
    #    그 밖의 `labels/`(사람 8유형)는 여전히 입력이 아니다
    assert not any(
        "/labels/" in p.as_posix() and "/labels/guide_statute/" not in p.as_posix()
        for p in split.inputs()
    )
    assert all("조건" in d and "판독" in d for d in split.guide_docs())
    import ast

    tree = ast.parse(inspect.getsource(split))
    imported = {
        (n.module or "") + ":" + ",".join(a.name for a in n.names)
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
    }
    assert not any("labels" in x.split(":")[1] and x.startswith("preprocess") for x in imported), (
        f"split 이 사람 라벨 저장소를 들여온다 — {sorted(imported)}"
    )


@pytest.mark.gate
def test_골든셋_라벨은_근거_조문에서_계산된다() -> None:
    """🔴 모든 행의 `labels` = `types_of(근거)` · 위반 행에는 근거가 있다 (D-282)."""
    from scripts import derived_manifest as dm

    dm.gate_guard(GOLDEN)
    rows = [json.loads(x) for x in GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert all("근거" in r for r in rows), "`근거` 칸이 없는 행 — 낡은 골든셋이다"
    bad = [
        r["id"]
        for r in rows
        if sorted(r["labels"]) != statute.types_of(r["근거"]) or (r["labels"] and not r["근거"])
    ]
    assert not bad, f"라벨과 근거가 어긋난 행 {len(bad)}개 — 예 {bad[:5]}"
