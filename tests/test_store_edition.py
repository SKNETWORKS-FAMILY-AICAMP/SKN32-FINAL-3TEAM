"""`collect.store.save_raw` — 같은 이름, 다른 내용 → 새 판 (2026-09-06).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

무엇이 이 동작을 만들게 했나 — 2026-09-06 전수조사에서 세 자리가 나왔고 원인이 같았다.

    law_002011_20250121.xml             −5 B   시행일 그대로, 본문 정정
    mfds_sanctions/page_0001.json     +179 B   시계열 — 처분이 추가됨
    mfds_hf_individual/page_0001.json   ±0 B   길이 그대로, 값 정정

**파일명이 「원천의 어느 시점인가」를 담지 않는다.** 예전에는 여기서 `StoreError` 로
멈추고 사람에게 새 이름을 시켰다. 이 파일이 지키는 것은 그 자동화가 **무엇을 깨지
않는가**다 —

  ① 규약 2 — **원본을 덮어쓰지 않는다.** 옛 판이 바이트 그대로 남는다
  ② 규약 4 — 내용이 같으면 여전히 스킵한다 (재실행 안전)
  ③ 규약 3 — 원장에 판이 남고, `supersedes` 가 무엇의 다음인지 말한다
  ④ 🚨 **하루에 두 번 갈리면 멈춘다** — 자동화의 유일한 위험에 남긴 사람 검문소
"""

from __future__ import annotations

import json

import pytest

from collect import store


@pytest.fixture
def raw(tmp_path, monkeypatch):
    """`data/` 를 건드리지 않는다. 🚨 진짜 raw 에 쓰는 테스트는 만들지 않는다."""
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "RAW", tmp_path / "data" / "raw")
    monkeypatch.setattr(store, "MANIFEST", tmp_path / "data" / "manifest.jsonl")
    # 레지스트리는 실물을 쓴다 — 등재된 소스만 원장에 오른다는 규칙까지 함께 지킨다.
    return tmp_path


def _rows(tmp_path) -> list[dict]:
    text = (tmp_path / "data" / "manifest.jsonl").read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def _save(payload: bytes, name: str = "page_0001.json"):
    return store.save_raw("law_go_kr", "probe_fam", name, payload, url="https://example.invalid/x")


# ─────────────────────────────────────────────────────────────
#  이름 만들기
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("page_0001.json", "page_0001__c20260906.json"),
        ("law_002011_20250121.xml", "law_002011_20250121__c20260906.xml"),
        ("noext", "noext__c20260906"),
    ],
)
def test_edition_name(filename: str, expected: str) -> None:
    assert store.edition_name(filename, "20260906") == expected


def test_edition_mark_is_not_stacked() -> None:
    """🚨 판 위에 판을 쌓지 않는다 — 날짜만 갈아 끼운다.

    `__c20260906__c20260907` 이 되면 원래 이름이 무엇이었는지 사람이 못 읽는다.
    """
    once = store.edition_name("page_0001.json", "20260906")
    assert store.edition_name(once, "20260907") == "page_0001__c20260907.json"


# ─────────────────────────────────────────────────────────────
#  🚨 본론 — 무엇을 깨지 않는가
# ─────────────────────────────────────────────────────────────


def test_identical_payload_is_skipped(raw) -> None:
    """규약 4 — 같으면 스킵. 🚨 이게 깨지면 재실행이 매번 파일을 불린다."""
    assert _save(b"same") is not None
    assert _save(b"same") is None
    assert len(_rows(raw)) == 1


def test_changed_payload_becomes_a_new_edition(raw) -> None:
    """🔴 이 수정의 본론 — 멈추지 않고 새 판으로 간다."""
    first = _save(b"old content")
    second = _save(b"new content")
    assert second is not None
    assert second != first
    assert store.EDITION_MARK in second.name


def test_the_old_edition_is_untouched(raw) -> None:
    """🚨 규약 2 — **덮어쓰지 않는다.** 이 단언이 이 기능의 전제 전부다."""
    first = _save(b"old content")
    _save(b"new content")
    assert first.exists()
    assert first.read_bytes() == b"old content"


def test_manifest_records_what_it_supersedes(raw) -> None:
    """규약 3 — 파일명으로 짐작하게 두지 않는다."""
    _save(b"old content")
    _save(b"new content")
    rows = _rows(raw)
    assert len(rows) == 2
    assert "supersedes" not in rows[0], "첫 행에는 칸이 없어야 한다 — 새 판이 아니다"
    assert rows[1]["supersedes"].endswith("page_0001.json")
    assert store.EDITION_MARK in rows[1]["path"]


def test_reruning_the_same_new_content_is_skipped(raw) -> None:
    """🚨 오늘 판을 이미 받았으면 또 만들지 않는다.

    이게 없으면 원천이 한 번 바뀐 뒤로 **돌릴 때마다** 판이 하나씩 생긴다.
    """
    _save(b"old content")
    _save(b"new content")
    assert _save(b"new content") is None
    assert len(_rows(raw)) == 2


def test_third_distinct_payload_same_day_is_refused(raw) -> None:
    """🚨 **하루에 두 번 갈리면 멈춘다** — 자동화에 남긴 사람 검문소.

    원천이 바뀐 것이 아니라 **응답이 호출마다 다른 것**일 수 있다. 그 경우
    자동으로 판을 만들면 돌릴 때마다 파일이 불어난다.
    """
    _save(b"old content")
    _save(b"new content")
    with pytest.raises(store.StoreError) as e:
        _save(b"yet another")
    assert "호출마다" in str(e.value)


def test_error_message_says_what_to_do(raw) -> None:
    """D-51 — 「무엇이 틀렸나」가 아니라 「어떻게 하나」를 적는다."""
    _save(b"old content")
    _save(b"new content")
    with pytest.raises(store.StoreError) as e:
        _save(b"yet another")
    msg = str(e.value)
    assert "비교" in msg and "원장" in msg


def test_new_edition_is_announced(raw, capsys) -> None:
    """🚨 조용히 다른 이름으로 저장하지 않는다.

    부르는 쪽은 자기가 넘긴 `filename` 을 찍는다 — 여기서 안 찍으면 아무도 모른다.
    """
    _save(b"old content")
    _save(b"new content")
    out = capsys.readouterr().out
    assert "새 판" in out
    assert store.EDITION_MARK in out


def test_unrelated_files_are_unaffected(raw) -> None:
    """양성 대조 — 이름이 다르면 아무 일도 안 일어난다."""
    a = _save(b"aaa", "page_0001.json")
    b = _save(b"bbb", "page_0002.json")
    assert a is not None and b is not None
    assert store.EDITION_MARK not in a.name
    assert store.EDITION_MARK not in b.name


# ─────────────────────────────────────────────────────────────
#  🔴 동일성 판정은 정규화문으로 · 저장은 원문으로 (2026-09-09)
#
#  ⛔ `mfds_press` 105 파일 **전부**가 원장에 「내용 갈림」으로 떴다. 원인은
#     `jsessionid=` 64자 토큰이 파일마다 2개, 길이가 고정이라 **바이트 수는 같고
#     해시만 달랐다.** 이 상태로는 규약 4 가 영원히 안 걸리고 돌릴 때마다 105개가
#     새 판으로 깔린다. D-117(매칭은 정규화문·보관은 원문)의 세 번째 적용이다.
# ─────────────────────────────────────────────────────────────

_TOKEN = "jsessionid=" + "A" * 64
_TOKEN2 = "jsessionid=" + "B" * 64


def _press(payload: bytes, name: str = "50316.html"):
    return store.save_raw("mfds_press", "probe_fam", name, payload, url="https://example.invalid/x")


def test_volatile_token_alone_does_not_make_a_new_edition(raw) -> None:
    """🔴 본론 — 세션 토큰만 다르면 **같은 응답**이다. 규약 4 가 걸려야 한다."""
    assert _press(f"<a>{_TOKEN}</a>".encode()) is not None
    assert _press(f"<a>{_TOKEN2}</a>".encode()) is None
    assert len(_rows(raw)) == 1


def test_stored_bytes_keep_the_token(raw) -> None:
    """🚨 **저장은 원문 그대로다** (D-92 무손상).

    지우는 것은 판정용 사본이고 디스크에 남지 않는다. 이 단언이 없으면
    「같은지 묻기 위해」 시작한 정규화가 슬금슬금 원본을 깎는다.
    """
    body = f"<a>{_TOKEN}</a>".encode()
    path = _press(body)
    assert path.read_bytes() == body
    assert _TOKEN.encode() in path.read_bytes()


def test_a_real_change_still_becomes_a_new_edition(raw) -> None:
    """양성 대조 — 토큰 말고 **본문**이 바뀌면 판이 서야 한다. 안 그러면 눈이 먼다."""
    _press(f"<a>{_TOKEN}</a>".encode())
    second = _press(f"<a>{_TOKEN2}</a><b>new</b>".encode())
    assert second is not None
    assert store.EDITION_MARK in second.name


def test_unregistered_source_falls_back_to_the_raw_hash(raw) -> None:
    """🚨 모르는 원천은 **느슨하게 판정하지 않는다.**

    `VOLATILE` 에 없는 원천은 원문 해시를 그대로 쓴다 — 빠뜨리면 판이 쌓일 뿐
    데이터를 잃지는 않는다. 안전한 쪽으로 틀린다.
    """
    _save(f"<a>{_TOKEN}</a>".encode())
    second = _save(f"<a>{_TOKEN2}</a>".encode())
    assert second is not None, "law_go_kr 은 VOLATILE 에 없으므로 갈려야 한다"


def test_manifest_keeps_the_original_hash_and_marks_the_judging_one(raw) -> None:
    """원장의 `sha256` 은 **파일 내용**이고 `identity_sha256` 은 **판정용**이다.

    🚨 둘이 갈릴 때만 칸이 생긴다. 칸이 있다는 것은 「이 원천은 원문 해시로는
       같은지 물을 수 없다」는 뜻이지 「내용이 이것이다」가 아니다.
    """
    body = f"<a>{_TOKEN}</a>".encode()
    _press(body)
    _save("평범한 본문".encode())
    press_row, plain_row = _rows(raw)
    assert press_row["sha256"] == store.sha256(body), "원장은 원문 해시를 증언한다"
    assert press_row["identity_sha256"] != press_row["sha256"]
    assert "identity_sha256" not in plain_row, "갈리지 않으면 칸을 만들지 않는다"
