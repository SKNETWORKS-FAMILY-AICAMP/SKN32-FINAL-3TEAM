"""광고 문구 → 문장 (전처리 사양 [P4] · 판정 그래프 `split` 노드).

★ 광고 텍스트는 마침표가 없다 — **줄바꿈 · 이모지 · 해시태그**를 경계로 쓴다 ([P4] · `docs/03_데이터/전처리_사양.md`).
   마침표 · 물음표 · 느낌표 뒤의 공백도 경계다(평문 문장).
🔴 **문장은 원문의 부분 문자열이다** — 글자를 바꾸지 않고 앞뒤 공백만 뗀다. 그래서 `offsets()` 가 원문 좌표를
   되찾을 수 있다 — 뺄 구간(D-278)은 **원문** 위에 그려진다. ⛔ 정규화문을 나누면 좌표가 어긋난다 (D-84 ①).
🚨 경계 규칙은 `[관행]` 이다 — 분할 정확도는 D-77 L1-1 이 재야 하는데 **분할 정답 셋이 아직 없다**(미측정).
   ⛔ `preprocess/chunk.py` 의 `_SENT` 는 조문용(마침표 기준)이라 쓰지 않는다 — 광고 문구와 경계가 다르다.
⛔ 형태소 분석기(kss 등)를 들이지 않는다 — 새 의존성이고, 광고 문구는 문법 문장이 아니다.
"""

from __future__ import annotations

import re

#: 이모지 — 그림 문자 블록 · 기호 블록 · 딩뱃 · 변형 선택자 · 결합자 `[관행]`.
#: 🚨 `re` 는 `\p{Extended_Pictographic}` 을 모른다 — 블록 범위로 근사한다(한글 · 한자 · 기호 ㆍ·※ 는 안 걸린다).
_EMOJI = "\U0001f000-\U0001faff☀-➿⬀-⯿️‍"

#: 경계 — ① 줄바꿈 ② 종결 부호 묶음 뒤 공백 ③ 이모지 묶음 뒤 공백 ④ 해시태그 앞 공백.
#: 🔴 숫자 사이 마침표(「3.5g」)는 뒤에 공백이 없어 경계가 아니다.
_BOUNDARY = re.compile(
    r"\r?\n+"
    r"|(?<=[.!?。！？…])\s+"
    rf"|(?<=[{_EMOJI}])\s+"
    r"|\s+(?=#\S)"
)


def split(text: str) -> list[str]:
    """원문 → 문장 목록. 빈 조각은 버린다 · **하나도 안 남으면 원문 하나**(공백만 떼고)다.

    🚨 빈 목록을 내지 않는다 — 문장이 0 이면 판정할 것이 없다고 읽혀 `hold` 로도 안 가는 길이 생긴다 (D-220).
    """
    parts = [p.strip() for p in _BOUNDARY.split(text)]
    parts = [p for p in parts if p]
    return parts or [text.strip() or text]


def offsets(text: str, sents: list[str]) -> list[int]:
    """문장마다 원문 시작 좌표. 앞 문장 끝에서부터 차례로 찾는다 — 같은 문장이 두 번 나와도 자리가 안 겹친다.

    🔴 못 찾으면 멈춘다 — 문장이 원문의 부분 문자열이 아니면 좌표가 거짓이 된다(D-224 의 좌표 판).
    """
    out: list[int] = []
    at = 0
    for s in sents:
        i = text.find(s, at)
        if i < 0:
            raise ValueError(f"문장이 원문에 없다 — 분할이 글자를 바꿨다: {s[:30]!r}")
        out.append(i)
        at = i + len(s)
    return out
