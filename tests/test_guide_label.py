"""해설서 평가셋의 게이트 — **축이 다시 뒤집히지 않게** (D-240 초안).

⛔ 1판은 내가 쓴 앵커를 정본 축으로 삼아 1,834행 중 1,707행을 「애매」로 떨어뜨렸다.
   원천은 전부에 라벨을 갖고 있었다. **테스트가 없으면 되돌아간다.**
"""

from __future__ import annotations

import pytest

from preprocess import guide_label as G
from preprocess.mfds_guide import CANDIDATES


def _row(label: str, text: str = "문구", tab: int = 1) -> dict:
    return {"문구": text, "원천라벨": label, "표": tab, "원천": "mfds_special_use_guide"}


def test_두_표의_키가_같다():
    """`CANDIDATES`(원천 축)와 `LABEL_TO_ARTICLE8`(조문 축)이 갈리면 판정이 갈린다 (D-99)."""
    assert set(CANDIDATES) == set(G.LABEL_TO_ARTICLE8)
    G._gate_tables()  # 멈추지 않아야 한다


def test_가리키는_호가_전부_이름표에_있다():
    assert {h for hs in G.LABEL_TO_ARTICLE8.values() for h in hs} <= set(G.ARTICLE8_NAME)


def test_제8호는_아무_라벨도_안_가리킨다():
    """제8호(사행심·음란)는 식품표시광고법 제정 때 **신설**이라 해설서에 대응이 없다.

    🚨 이 단언이 깨지면 「승계됐다」는 D-240 의 근거 ㉰가 바뀐다 — 원장부터 고친다.
    """
    assert "8" not in {h for hs in G.LABEL_TO_ARTICLE8.values() for h in hs}


def test_원천라벨이_없으면_멈춘다():
    """🔴 없음을 성공으로 세지 않는다 (D-72 fail-closed)."""
    with pytest.raises(SystemExit, match="원천라벨"):
        G.build([_row("거짓ㆍ과장ㆍ기만"), {"문구": "x", "원천": "s", "표": 1}])


def test_모르는_원천라벨이면_멈춘다():
    with pytest.raises(SystemExit, match="매핑에 없는"):
        G.build([_row("새로운 분류")])


def test_확정유형은_비어서_나온다():
    """🔴 사람만 채운다 (D-66 · D-172). 기계가 채우면 홀드아웃이 거짓말을 한다 (D-40)."""
    out = G.build([_row(k) for k in G.LABEL_TO_ARTICLE8])
    assert all(r["확정유형"] == [] for r in out)


def test_판정지위가_모든_행에_붙는다():
    """🚨 없으면 다음 사람이 **확정된 위반**으로 읽는다 (D-240 · D-237)."""
    out = G.build([_row(k) for k in G.LABEL_TO_ARTICLE8])
    assert all(r["판정지위"] == "심의지적" for r in out)
    assert all(r["판정"] == "원천3분류" for r in out)


def test_후보유형_칸_이름을_바꾸지_않는다():
    """`scripts/label_sheet.py` 가 이 칸을 읽어 사람 시트를 뽑는다 (D-99)."""
    out = G.build([_row("거짓ㆍ과장ㆍ기만")])
    assert out[0]["후보유형"] == list(CANDIDATES["거짓ㆍ과장ㆍ기만"])


def test_앵커는_평가셋_행에_안_들어간다():
    """⛔ 앵커는 `--anchors` 로만 나간다 — 두 계수기를 섞지 않는다 (D-160)."""
    out = G.build([_row("거짓ㆍ과장ㆍ기만", "질병을 예방하고 치료합니다")])
    assert "제안유형" not in out[0]
    assert "근거조문" not in out[0]


def test_앵커_오탐이_실재한다():
    """🔴 「무농약」·「시간절약」이 `2.가` 에 걸린다 — 고쳤다고 착각하지 않게 못박는다 (D-191).

    이 단언이 깨지면 **앵커가 좋아진 것**이므로, 원장 09-17 밤 ③ 과 D-240 을 같이 고친다.
    """
    assert any(p == "2.가" for p, _ in G.anchor_label("무농약, 무항생제"))
    assert any(p == "2.가" for p, _ in G.anchor_label("시간절약, 돈절약"))
