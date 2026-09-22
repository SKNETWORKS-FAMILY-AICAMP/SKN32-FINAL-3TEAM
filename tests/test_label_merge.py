"""🔴 **라벨 취합** — 사람 시간이 들어간 자리라 되돌리는 비용이 가장 크다 (D-66 · D-170).

⛔ 2026-09-10 실측으로 찾은 구멍 둘.

  ① `--merge` 의 합의 판정이 `len({라벨들}) == 1` 뿐이었다. **한 파일에만 있는 키도
     집합 크기가 1 이라 통과한다** — 겹치지 않은 라벨이 전부 「두 사람이 합의한 것」으로
     산출에 들어갔다. 2인 확인이 이 프로젝트의 뼈대인데(D-15 · D-66) 그 자리가 비어 있었다.

  ② `pe == 1` 일 때 κ 를 **1.0(완전 합의)** 으로 냈다. 그건 두 사람이 전부 **같은 한
     라벨만** 찍었다는 뜻이고 정보량이 0 이다. 1.0 으로 보고하면 **가장 정보 없는
     라벨링이 가장 좋아 보인다.** 같은 함수 docstring 이 반대편 착시(일치 85%인데
     κ=0.000)는 경고해 놓고 이쪽 극단은 열어 뒀다.

🚨 지시서가 이미 5인에게 나갔다면 이 둘은 **사람이 붙인 라벨의 신뢰도를 직접 바꾼다.**
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from scripts.label_merge import kappa, load

pytestmark = pytest.mark.gate


def _sheet(p: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    return p


def _row(text: str, label: str | None) -> dict:
    r = {"원천": "ftc", "원천라벨": "x", "문구": text, "글": "", "쪽": "", "호": ""}
    if label:
        r |= {"확정유형": [label], "붙인이": "누구", "붙인날": "2026-09-10"}
    return r


def test_한_사람만_채운_항목은_합의가_아니다(tmp_path: pathlib.Path) -> None:
    """🔴 두 사람이 **겹쳐서** 채운 것만 합의다."""
    a = _sheet(
        tmp_path / "a.jsonl", [_row("겹친다", "거짓_과장"), _row("나만 채웠다", "소비자_기만")]
    )
    b = _sheet(tmp_path / "b.jsonl", [_row("겹친다", "거짓_과장"), _row("나만 채웠다", None)])

    data = load([a, b])
    allk = {k for d in data.values() for k in d}

    solo = [k for k in allk if sum(1 for d in data.values() if k in d) == 1]
    old = {k for k in allk if len({d[k] for d in data.values() if k in d}) == 1}
    new = {
        k
        for k in allk
        if sum(1 for d in data.values() if k in d) >= 2
        and len({d[k] for d in data.values() if k in d}) == 1
    }

    assert len(solo) == 1, "한 사람만 채운 항목이 하나 있어야 표본이 성립한다"
    assert len(old) == 2, "⛔ 종전 조건은 한 사람만 채운 것까지 합의로 셌다"
    assert len(new) == 1, "🚨 2인 이상이 채운 것만 합의다 (D-66)"
    assert solo[0] not in new


def test_모두_같은_라벨만_찍으면_κ_는_정의되지_않는다() -> None:
    """🔴 `pe == 1` — 우연히 맞을 확률이 1 이면 뺄 것이 전부다. 1.0 이 아니다."""
    a = {"1": "거짓_과장", "2": "거짓_과장", "3": "거짓_과장"}
    b = dict(a)

    k, n, agree = kappa(a, b)

    assert n == 3 and agree == 3
    assert math.isnan(k), (
        "🚨 전원이 같은 한 라벨만 찍었는데 κ 가 수로 나왔다 — "
        "가장 정보 없는 라벨링이 가장 좋아 보인다."
    )


def test_반대_대조_라벨이_섞이면_κ_가_수로_나온다() -> None:
    """🚨 위 게이트가 **아무 때나 nan 을 내는 것이 아님**을 보인다 (D-170)."""
    a = {"1": "거짓_과장", "2": "소비자_기만", "3": "거짓_과장", "4": "소비자_기만"}
    b = {"1": "거짓_과장", "2": "소비자_기만", "3": "소비자_기만", "4": "소비자_기만"}

    k, n, _ = kappa(a, b)

    assert n == 4
    assert not math.isnan(k) and -1.0 <= k <= 1.0


def test_일치율이_높아도_κ_는_0_일_수_있다() -> None:
    """★ docstring 이 적어 둔 실측 극단을 코드로 못박는다 — 일치 85%인데 κ=0.000."""
    a = {str(i): "거짓_과장" for i in range(60)}
    b = {str(i): ("거짓_과장" if i < 51 else "소비자_기만") for i in range(60)}

    k, n, agree = kappa(a, b)

    assert (n, agree) == (60, 51)
    assert math.isnan(k) or k <= 0.0, f"한쪽이 늘 같은 답이면 합의가 아니다 — κ={k}"


def test_KEY_FIELDS_에_사례집_문구_필드가_있다() -> None:
    """🔴 casebook 시트의 문구 필드는 `글` 이다 — 키에서 빠지면 행이 서로 안 맞는다.

    ⛔ 라벨링 지시서 §4 의 예시 JSON 은 `문구`/`후보유형`(guide 시트)인데,
       §1·§5 가 「먼저 하라」고 지정한 것은 casebook 시트다. 두 시트의 필드가 다르다.
    """
    from scripts.label_merge import KEY_FIELDS  # noqa: PLC0415

    assert "글" in KEY_FIELDS and "문구" in KEY_FIELDS


# 🆕 2026-09-21 (전수 재검토 I10)
def _line(person: str, text: str, types: list[str] | None, scope: str = "") -> str:
    import json as _j

    r = {"원천": "g", "원천라벨": "", "문구": text, "글": "", "쪽": "", "호": "", "붙인이": person}
    if types:
        r["확정유형"] = types
    if scope:
        r["판단"] = scope
    return _j.dumps(r, ensure_ascii=False)


def test_합의는_첫_파일에_없어도_쓴다(tmp_path, monkeypatch) -> None:
    """⛔ 합의 목록은 모두에게서 모으고 **첫 파일의 줄만** 써서, 첫 파일에 없는 합의가 빠졌다."""
    import sys

    from scripts import label_merge

    a = tmp_path / "A__s1.jsonl"
    a.write_text(_line("A", "다른 문구", ["거짓_과장"]) + "\n", encoding="utf-8")
    b = tmp_path / "B__s2.jsonl"
    b.write_text(_line("B", "y1", ["의약품_오인"]) + "\n", encoding="utf-8")
    c = tmp_path / "C__s2.jsonl"
    c.write_text(_line("C", "y1", ["의약품_오인"]) + "\n", encoding="utf-8")
    out = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", ["label_merge", str(a), str(b), str(c), "--merge", str(out)])
    assert label_merge.main() == 0
    got = [x for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(got) == 1 and "y1" in got[0], got


def test_범위밖과_유형이_갈리면_갈림이다(tmp_path, monkeypatch) -> None:
    """⛔ 범위밖 행은 `확정유형` 이 비어 「한 사람만 채움」으로 세였고, `consensus` 가 그 1인 라벨을 분할로 냈다."""
    from preprocess import labels

    d = tmp_path / "labels"
    d.mkdir()
    (d / "A.jsonl").write_text(_line("A", "y3", None, "범위밖") + "\n", encoding="utf-8")
    (d / "B.jsonl").write_text(_line("B", "y3", ["의약품_오인"]) + "\n", encoding="utf-8")
    monkeypatch.setattr(labels, "DIR", d)
    picked, stat = labels.consensus()
    assert stat.get("갈림") == 1 and not picked, (picked, stat)
    assert labels.docs() == []
