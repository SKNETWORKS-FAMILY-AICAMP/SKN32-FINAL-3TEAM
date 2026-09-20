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
