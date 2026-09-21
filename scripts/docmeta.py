"""docmeta.py — 문서가 스스로 말하는 버전을 읽는다.

🚨 버전은 **문서 머리말 한 곳**에 있다. 파일명에는 없다 (2026-09-01 팀장 결정).
   파일명에 붙이면 갱신할 때 두 곳을 손대야 하고, 실제로 어긋났다 —
   `수집전처리_기획_v1.2.md` 의 내용이 v1.3 이었다. 두 벌이 된 사실은 갈라진다 (D-99).

🚨 그래서 **읽는 방법도 한 곳**에 둔다. sync_project 와 build_pdf 가 각자 정규식을
   들고 있으면 그 둘이 또 갈라진다.

버전이 없는 문서가 있다 — 사실원장·설계결정기록·산출물현황·검토표·판정매트릭스처럼
**계속 고쳐지는 원장**이다. 이들에게는 버전이 아니라 **커밋 해시가 판(版)이다.**
없는 것을 없다고 말하는 것이 맞다. 억지로 v1.0 을 붙이지 않는다.
"""

from __future__ import annotations

import re

# 버전이 적히는 자리는 둘뿐이다 — H1 제목, 또는 문서 정보 표의 「문서」 행.
# 🚨 본문 산문(「v1.0 -> v1.1 로 올린다」 같은 설명)을 주워오지 않으려고 자리를 좁힌다.
_VER = re.compile(r"\bv(\d+\.\d+)\b")


def version_of(text: str) -> str | None:
    """머리말에서 버전을 읽는다. 없으면 None — 그것도 정보다."""
    for line in text.splitlines()[:30]:
        s = line.strip()
        if not (s.startswith("# ") or (s.startswith("|") and "문서" in s)):
            continue
        m = _VER.search(s)
        if m:
            return f"v{m.group(1)}"
    return None


def versioned_stem(stem: str, text: str) -> str:
    """발행물 파일명 — 여기서는 버전을 **붙인다.**

    🚨 원본과 발행물은 다르다. 원본은 계속 고쳐지므로 경로가 고정돼야 하고,
       발행물(PDF)은 **그 시점에서 얼어붙은 것**이라 이름이 바뀔 일이 없다.
       「PDF 발행이 버전을 고정하는 사건」이라는 개정 규칙은 여기에 살아 있다.
    """
    ver = version_of(text)
    return f"{stem}_{ver}" if ver else stem


def refuse_args(prog: str) -> None:
    """🆕 2026-09-21 (전수 재검토) — **인자를 받지 않는 생성 스크립트**가 인자를 받으면 멈춘다.

    ⛔ `gen_registry.py`·`extract_rationale.py`·`review_sheet.py` 는 argv 를 안 봤다 — `--help`·`--check` 를 줘도
       **생성물을 다시 썼다**(검토 중 실제로 그랬다 · 바이트가 같아 다행이었다). 확인하려던 명령이 쓰기가 됐다.
    ★ 셋이 같은 규칙이라 여기 하나 (D-99) — 🚨 `gen_registry.py` 만 옮겨 적었다(모듈 수준 스크립트 · 테스트가 한 파일만 복사한다). 고치면 둘 다.
       대조 모드(`--check`)는 아직 없다 — 생기면 여기가 아니라 그 스크립트에 둔다.
    """
    import sys  # noqa: PLC0415

    if len(sys.argv) > 1:
        raise SystemExit(
            f"🔴 {prog} 는 인자를 받지 않는다 — 받은 것: {sys.argv[1:]}. 아무것도 쓰지 않았다.\n"
            "  돌리면 생성물을 **다시 쓴다.** 대조만 하려면 `launcher.py check` (게이트)를 쓴다"
        )
