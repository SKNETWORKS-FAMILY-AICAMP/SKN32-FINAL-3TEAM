"""preprocess/hwp3.py — 한글 3.0(`HWP Document File V3.00`) 본문 글자를 읽는다 (2026-09-30).

★ **왜 직접 읽는가** — `ftc_press` 2001~2004 첨부 12 개가 한글 3.0 이다. LibreOffice 변환은 **본문을 거의 다 잃었다**
   (글상자 · 표 밖의 머리 몇 줄만 남음 — 34743 샘표 사건에서 광고 문구가 한 줄도 안 나왔다 · 2026-09-30 실측).
   이 파일은 본문 글자를 **조합형(Johab) 2 바이트 코드**로 들고 있어서, 압축을 풀고 16 비트 단위로 훑으면 문단 글자가 나온다
   (같은 사건에서 「뭘 보고 고르세요? 비싼만큼 특별합니다」 · 「국산 태양초라야 제 맛이 납니다」가 나왔다).

🚨 **정식 파서가 아니다 — 훑기다.** 문단 머리 · 글꼴 표 · 표 구조를 해석하지 않고 16 비트 값을 그대로 글자로 바꾼다.
   · 이진 머리의 값이 우연히 한글 코드 범위에 들어 **짧은 가짜 음절 조각**(「몔뭉」 「잆딬」)이 섞인다 → `_junk` 가 거른다(넓게).
   · 한자 · 일부 기호는 조합형 사용자 영역이라 풀리지 않거나 다른 글자로 나온다 → 버린다.
   · 그림으로 든 글 · 일부 사건(34811 · 35185)의 본문은 여기서도 안 나온다 — **없는 것이 아니라 못 읽은 것**이다(D-188).
   ★ 그래서 이 글은 **문구가 원천에 있는지 대조하는 바닥**으로만 쓴다(`guide_statute_round.fp_units`) — 문구를 여기서 뽑지 않는다.
🚨 **읽기 전용** — 원본을 고치지 않는다.
"""

from __future__ import annotations

import pathlib
import re
import struct
import zlib

SIGNATURE = b"HWP Document File V3.00"
#: 파일 머리 — 서명 30 · 문서 정보 128 · 문서 요약 1,008 바이트 (한글 3.0 파일 구조)
_SIG_LEN, _INFO_LEN, _SUMMARY_LEN = 30, 128, 1008
_HANGUL = re.compile(r"[가-힣]")


def is_hwp3(path: pathlib.Path) -> bool:
    return path.read_bytes()[: len(SIGNATURE)] == SIGNATURE


def body(path: pathlib.Path) -> bytes:
    """압축을 푼 본문 바이트. 🔴 서명이 다르면 멈춘다 — 다른 형식을 조용히 훑지 않는다 (D-220)."""
    b = path.read_bytes()
    if b[: len(SIGNATURE)] != SIGNATURE:
        raise ValueError(f"{path.name}: 한글 3.0 파일이 아니다")
    info = b[_SIG_LEN : _SIG_LEN + _INFO_LEN]
    compressed = info[124]
    extra = struct.unpack_from("<H", info, 126)[0]  # 정보 블록 길이
    rest = b[_SIG_LEN + _INFO_LEN + _SUMMARY_LEN + extra :]
    return zlib.decompressobj(-15).decompress(rest) if compressed else rest


def char_of(code: int) -> str:
    """16 비트 값 하나 → 글자. 0x8000 이상은 조합형 2 바이트 · 인쇄 가능한 ASCII · 문단 끝(13)만 살린다. 나머지는 끊는 자리(`\\x00`)."""
    if code >= 0x8000:
        try:
            return bytes([code >> 8, code & 0xFF]).decode("johab")
        except UnicodeDecodeError:
            return "\x00"
    if 32 <= code < 127:
        return chr(code)
    return "\n" if code == 13 else "\x00"


def _junk(seg: str) -> bool:
    """이진 값이 우연히 만든 조각인가. 🚨 [임의] 넓게 거른다 — 짧고 공백 · 숫자 · 문장부호가 없는 한글 덩어리."""
    if len(_HANGUL.findall(seg)) < 2:
        return True
    return len(seg) <= 4 and not re.search(r"[\s\d.,!?%()]", seg)


def text(path: pathlib.Path) -> str:
    """본문 글자 — 끊는 자리마다 줄을 나누고 조각을 거른다."""
    buf = body(path)
    raw = "".join(char_of(struct.unpack_from("<H", buf, i)[0]) for i in range(0, len(buf) - 1, 2))
    segs = (s.strip() for s in re.split(r"[\n\x00]+", raw))
    return "\n".join(s for s in segs if s and not _junk(s))
