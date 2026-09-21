"""공정위 추천·보증 사건 계측 (D-255 ⬜ · `preprocess/endorse_scan.py`).

🚨 여기서 막는 것 — ① 대가 표시 누락(범위 밖)과 체험 없는 후기를 한 갈래로 세는 것
   ② 도표 캡션·고시 이름·약칭을 「광고 문구 후보」로 세는 것 ③ 그물 밖 사건을 세는 것
"""

from __future__ import annotations

import pytest

from preprocess import endorse_scan as es

pytestmark = pytest.mark.gate

NOHIDE = "피심인은 인플루언서에게 대가를 지급하였음에도 경제적 이해관계를 공개하지 않고 은폐하는 방법으로"
FAKE = "인플루언서가 상품을 실제로 사용해 본 사실이 없음에도 경험적 사실에 부합하는 것처럼"


def test_주문이_무엇을_적었나로_갈래를_가른다() -> None:
    assert es.classify({"주문": NOHIDE, "이유": ""})["갈래"] == ["미표시"]
    assert es.classify({"주문": FAKE, "이유": ""})["갈래"] == ["거짓후기"]
    assert es.classify({"주문": NOHIDE + " " + FAKE, "이유": ""})["갈래"] == ["미표시", "거짓후기"]


def test_그물_밖은_세지_않는다() -> None:
    assert es.classify({"주문": "입찰 담합을 하여서는 아니 된다", "이유": ""}) is None


def test_캡션과_고시명은_문구후보가_아니다() -> None:
    why = (
        "<img src='/LSW/flDownload.do?flSeq=1' alt='이유 2번째 이미지'> "
        "'추천ㆍ보증 등에 관한 표시ㆍ광고 심사지침' 에 따르면 "
        "'이 사건 게시물' 은 "
        "'남자윤곽수술 2개월차 후기예요' 라고 적었다"
    )
    assert es.ad_quotes(why) == ["남자윤곽수술 2개월차 후기예요"]


def test_마스킹_정책_키가_있다() -> None:
    """⛔ 첫 판은 원천 id 로 정책을 찾아 `--candidates` 가 멈췄다 — 정책 키는 원문 폴더(계열)다."""
    from preprocess.mask import POLICY

    assert es.MASK_KEY in POLICY


def test_후보_파일은_피심인의_상호와_실명을_가린다(tmp_path) -> None:
    """🔴 2026-09-21 (D-248) — 인용을 뽑은 뒤 `apply_policy(q, "", …)` 로 가리던 때 **앵커가 없어**
    피심인 상호·개인 실명이 `build/endorse_candidates.jsonl` 에 그대로 실렸다 (이름은 가짜).

    ★ 반대 대조 — 앵커 없이 가리면(종전 방식) 이름이 남는다는 것도 같이 본다.
    """
    import json
    import xml.etree.ElementTree as ET

    from preprocess.mask import apply_policy

    root = ET.Element("PrecService")
    ET.SubElement(root, "사건명").text = "김가나의 부당한 표시ㆍ광고행위에 대한 건"
    ET.SubElement(root, "피심정보내용").text = "1. 김가나(******-*******) 서울 **"
    why = "피심인은 '김가나가 직접 3개월 먹어보고 확실히 느꼈어요' 라는 후기를 게시하였다"
    ET.SubElement(root, "이유").text = why
    p = tmp_path / "1.xml"
    ET.ElementTree(root).write(p, encoding="utf-8")

    out = tmp_path / "c.jsonl"
    assert es.candidates([(p, {"이유": why, "사건번호": "x"}, {"갈래": ["거짓후기"]})], out) == 1
    got = json.loads(out.read_text(encoding="utf-8"))["문구"]
    assert got and all("김가나" not in q for q in got), got
    assert any("[대표]" in q for q in got), got
    # 반대 대조 — 종전 방식(앵커 없이 인용 한 개씩)은 실명을 못 가린다
    assert any("김가나" in apply_policy(q, "", es.MASK_KEY) for q in es.ad_quotes(why))
