"""preprocess/normalize.py — [P2] 비파괴 정규화 층 · `NormalizedText` 계약
(전처리 사양 1-2 · 1-3 · D-84 ① · 2026-09-06).

🚨 `preprocess/text.py` 가 이 자리를 **비워 두고** 이렇게 적어 놓았다 —

    「지금 있는 것은 나열 구분자 하나뿐이고, **비파괴 계약(`NormalizedText`)은 아직
     없다.** 오프셋 맵이 필요한 순간(주장 스팬 BIO · 하이라이트 UI)이 오면
     사양 1-3 의 계약을 여기에 세운다」

그 자리가 여기다. `text.py` 의 `sep_norm()` 은 **파괴적**이라 원문 좌표를 잃는다.
이 모듈은 잃지 않는다 — 그것이 존재 이유의 전부다.

──────────────────────────────────────────────────────────────
왜 좌표를 지켜야 하나 (사양 1-2)

  ① 원문 오프셋이 깨지면 → 하이라이트 UI · 주장 스팬 BIO 라벨이 전부 어긋난다
  ② 회피 표기 자체가 신호다 → 정규화로 지우면 「작성자가 위법성을 인지했다」는
     정보를 함께 잃는다

★ **매칭은 `norm` 에서 하고, 보고는 `offset_map` 으로 `raw` 좌표로 되돌린다.**
  이 한 줄이 이 모듈의 사용법 전부다.

──────────────────────────────────────────────────────────────
🚨 `raw` 는 「원문」이지 「서버가 준 바이트」가 아니다

  사양 0장의 순서는 **[P3] 마스킹 → [P2] 정규화**다. 마스킹이 뒤에 오면 오프셋 맵이
  전부 어긋나기 때문이다 (D-17). 그러므로 여기 들어오는 `raw` 는 **이미 마스킹된
  문서**이고, `offset_map` 이 가리키는 좌표계도 그것이다.
  🚨 `data/raw/` 의 원본 바이트와 혼동하지 마라 — 이름이 같을 뿐 다른 것이다 (D-92).

──────────────────────────────────────────────────────────────
🚨 지금 구현한 것과 안 한 것 — 사양 1-4 의 N1~N7

  ✅ N1 FULLWIDTH   유니코드 NFKC        (한계는 아래 「글자 단위 NFKC」 참조)
  ✅ N2 ZWSP        제어문자·zero-width 제거
  ✅ N5 REPEAT      3회 이상 → 2회
  ✅ N6 SPACE       연속 공백 → 1칸
  ⬜ N3 JAMO_SPLIT  자모 분리 복원
  ⬜ N4 SEP_INSERT  구분자 삽입 제거
  ⬜ N7 HANJA       한자 → 한글 음차

  🚨 **안 한 셋은 게을러서가 아니라 [P6] 사전이 없어서다.**
     사양 1-4 가 「N4 는 **사전 어휘의 문자 사이에서만** 적용한다 — 전역 치환이 아니다」
     라고 못 박았고, 1-5 의 각주가 「`비타민 C` 의 공백까지 지우면 정상 표현이 깨진다」
     고 그 이유를 든다. N3·N7 도 같다 (미해결 #1 · #2).
     `text.py` 의 `LEX` 10개로 흉내 낼 수는 있지만, 그 자리에 **하한을 전량인 척**
     넣어 두면 사전이 선 뒤에도 아무도 다시 안 본다.
     ⬜ 로 비워 두고 사전과 함께 채운다.

──────────────────────────────────────────────────────────────
🚨 `evasion_flags` 에 N5·N6 을 넣지 않는다 — 사양의 두 문장이 부딪히는 자리다

  1-3 은 `evasion_flags` 를 「적용된 정규화 규칙 ID」로 정의하고,
  1-5 는 그것을 **위험도 인코더의 입력 피처이자 가산 근거**로 쓴다고 한다.

  둘을 그대로 따르면 **연속 공백을 한 칸으로 줄였다는 이유로 위험도가 올라간다.**
  「대박!!!!!」은 회피가 아니라 강조이고, 공백 정리는 거의 모든 문서에서 일어난다.
  전부 켜지는 피처는 피처가 아니다.

  ★ 그래서 **적용된 규칙 전부**(`applied_rules`)와 **회피 신호**(`evasion_flags`)를
    나눠 담는다. 계약의 필드 이름은 그대로 두고, 뜻을 좁혔다.
  🚨 이건 **사양을 고친 것**이다. 팀장 확인 대상이고, 확인 전까지 이 주석이 근거다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: N2 — 지워야 할 보이지 않는 문자.
#:    zero-width space/non-joiner/joiner · LRM/RLM · BOM · word-joiner ·
#:    그리고 **soft hyphen** (U+00AD) — 화면에 안 보이는데 낱말을 가른다.
_INVISIBLE = re.compile(r"[​-‏⁠­﻿]")

#: N5 — 같은 글자가 3번 이상 이어지면 2번으로 줄인다.
#: 🚨 숫자는 건드리지 않는다 (사양 1-4 「대소문자·숫자는 건드리지 않는다」).
#:    「2000년」의 `00` 이나 「1111-2222」 같은 번호가 망가진다.
#: 🚨 **공백도 뺀다.** 안 빼면 「비타민␣␣␣C」의 공백 셋이 N5 에 먼저 걸려
#:    `applied_rules` 에 `REPEAT` 가 찍힌다 — 반복 **강조**가 아니라 띄어쓰기인데.
#:    결과 문자열은 N6 이 어차피 같게 만들지만, **어느 규칙이 발동했는가가 피처**라
#:    (사양 1-5) 이름이 틀리면 근거 문장이 틀린다. 공백은 N6 의 일이다.
#:    ⛔ 첫 판이 이랬고 smoke 에서 잡혔다.
_REPEAT_EXEMPT = frozenset("0123456789 \t\n\r\v\f\xa0　")

#: N6 — 연속 공백. 🚨 줄바꿈을 공백으로 바꾸지 않는다 —
#:    [P4] 문장 분할이 「광고 텍스트는 마침표가 없다. **줄바꿈**·이모지·해시태그를
#:    경계로 쓴다」고 되어 있다. 여기서 줄바꿈을 지우면 그 경계를 미리 없애는 것이다.
_SPACE_RUN = re.compile(r"[ \t  -   　]+")

#: 🚨 회피 신호로 **세는** 규칙만 여기 둔다. 위 docstring 의 마지막 절이 이유다.
_EVASION_RULES = frozenset({"FULLWIDTH", "ZWSP", "JAMO_SPLIT", "SEP_INSERT", "HANJA"})


@dataclass(frozen=True)
class NormalizedText:
    """사양 1-3 의 계약. **필드 이름을 바꾸지 않는다** — 수집기·학습·평가가 다 이 이름을 쓴다.

    🚨 `frozen=True` 는 **리스트 안까지 얼리지 않는다.** `offset_map.append(...)` 는
       그대로 통한다. 계약이 `list` 로 되어 있어 그대로 두었고, 대신 여기 적는다 —
       **받은 쪽은 읽기만 한다.** 고칠 일이 있으면 새로 만든다.
    """

    raw: str
    """원문. 표시·오프셋의 **기준**이다. 🚨 이미 [P3] 마스킹을 거친 문서다."""

    norm: str
    """정규화문. **매칭의 기준**이다. 사람에게 보여주지 않는다."""

    offset_map: list[int]
    """`norm[i]` 를 만든 `raw` 의 시작 오프셋. `len(offset_map) == len(norm)` 이 불변식이다."""

    evasion_flags: list[str] = field(default_factory=list)
    """회피 표기 신호로 **읽어도 되는** 규칙만. 위험도 가산 근거로 쓰인다 (사양 1-5)."""

    applied_rules: list[str] = field(default_factory=list)
    """실제로 발동한 규칙 전부. 🚨 진단용이다 — 위험도에 넣지 마라."""

    def to_raw(self, start: int, end: int) -> tuple[int, int]:
        """`norm` 의 반열린 구간 `[start, end)` 를 `raw` 좌표로 되돌린다.

        🚨 **보고는 언제나 이것을 거친다.** `norm` 좌표를 그대로 UI 나 라벨에 넘기면
           사용자가 보는 글자와 다른 자리가 칠해진다.

        🚨 끝 좌표는 `offset_map[end-1] + 1` 이 아니다 — 한 `raw` 글자가 여러 `norm`
           글자로 늘어날 수 있어(`⑴` → `(1)`) 그렇게 하면 구간이 잘린다.
           **다음 글자의 시작**을 쓰고, 끝이면 `len(raw)` 를 쓴다.
        """
        if not 0 <= start <= end <= len(self.norm):
            raise ValueError(f"구간이 norm 범위 밖이다: [{start}, {end}) · len={len(self.norm)}")
        if start == end:
            at = self.offset_map[start] if start < len(self.norm) else len(self.raw)
            return (at, at)
        first = self.offset_map[start]
        last = self.offset_map[end - 1]
        # 같은 raw 글자에서 나온 norm 글자들을 모두 지나친 뒤가 구간의 끝이다.
        stop = end
        while stop < len(self.norm) and self.offset_map[stop] == last:
            stop += 1
        after = self.offset_map[stop] if stop < len(self.norm) else len(self.raw)
        return (first, after)


def has_decomposed_hangul(text: str) -> bool:
    """NFD 로 분해된 한글(`ᄒ`+`ᅡ`+`ᆫ`)이 있는가 — **글자 단위 NFKC 가 못 합치는 것**이다.

    🚨 이것을 함수로 둔 이유 — 우리 원천에 이런 문자열이 **있는지 없는지 아직 모른다.**
       모르는 것을 「없다」로 두고 넘어가면 나중에 조용히 틀린다. 세어 보고 정한다.
       (`scripts/doctor.py --data` 처럼 재는 자리를 만들어 두는 것과 같은 뜻이다.)

    ⛔ 첫 판은 두 번째 범위를 `A960`~`D7FF` 한 덩어리로 썼다가 **한글 완성형
       (`AC00`~`D7A3`)을 통째로 삼켰다** — 「한」이 분해 자모로 판정됐다.
       확장 A(`A960`~`A97F`)와 확장 B(`D7B0`~`D7FF`)는 **완성형을 사이에 두고
       떨어져 있다.** 유니코드 블록은 이름이 이어진다고 코드포인트가 이어지지 않는다.
       🚨 오늘 세 번째 같은 실수다 — `가처분`⊂`허가처분`, `mfds_press`⊂`mfds_press_pdf`,
          그리고 이것. **범위·부분문자열은 눈으로 확인하기 전엔 믿지 않는다.**
    """
    return any(
        "ᄀ" <= ch <= "ᇿ"  # 한글 자모
        or "ꥠ" <= ch <= "꥿"  # 확장 A
        or "ힰ" <= ch <= "퟿"  # 확장 B
        for ch in text
    )


def normalize(raw: str) -> NormalizedText:
    """[P2] 정규화. **원문 좌표를 잃지 않는다.**

    적용 순서 —
      ① N2 보이지 않는 문자 제거   ← 먼저 지워야 뒤 규칙이 낱말을 온전히 본다
      ② N1 NFKC                   ← 전각 공백이 여기서 반각이 되므로 N6 보다 앞
      ③ N5 반복 축약
      ④ N6 공백 정리

    🚨 **글자 단위 NFKC 다.** 문자열 전체에 `unicodedata.normalize` 를 걸면 글자 수가
       어떻게 변하는지 추적할 수 없어 `offset_map` 을 만들 방법이 없다. 대신 결합이
       필요한 경우(분해된 한글 자모)를 못 합친다 — `has_decomposed_hangul()` 로
       **재고 나서** 다룬다. 한계를 코드가 아니라 주석에만 적어 두면 잊힌다.
    """
    chars: list[str] = list(raw)
    offsets: list[int] = list(range(len(raw)))
    fired: set[str] = set()

    # ── ① N2 — 보이지 않는 문자 ──────────────────────────
    kept = [(c, o) for c, o in zip(chars, offsets, strict=True) if not _INVISIBLE.match(c)]
    if len(kept) != len(chars):
        fired.add("ZWSP")
    chars = [c for c, _ in kept]
    offsets = [o for _, o in kept]

    # ── ② N1 — NFKC (글자 단위) ─────────────────────────
    out_c: list[str] = []
    out_o: list[int] = []
    for c, o in zip(chars, offsets, strict=True):
        folded = unicodedata.normalize("NFKC", c)
        if folded != c:
            fired.add("FULLWIDTH")
        for fc in folded:  # 🚨 한 글자가 여럿이 될 수 있다 — `⑴` → `(1)`
            out_c.append(fc)
            out_o.append(o)
    chars, offsets = out_c, out_o

    # ── ③ N5 — 반복 축약 ────────────────────────────────
    out_c, out_o = [], []
    run = 0
    for c, o in zip(chars, offsets, strict=True):
        run = run + 1 if out_c and c == out_c[-1] else 1
        if run >= 3 and c not in _REPEAT_EXEMPT:
            fired.add("REPEAT")
            continue  # 3번째부터는 버린다 (2번은 남는다)
        out_c.append(c)
        out_o.append(o)
    chars, offsets = out_c, out_o

    # ── ④ N6 — 공백 정리 ────────────────────────────────
    out_c, out_o = [], []
    for c, o in zip(chars, offsets, strict=True):
        if _SPACE_RUN.match(c):
            if out_c and _SPACE_RUN.match(out_c[-1]):
                fired.add("SPACE")
                continue  # 이어지는 공백은 버린다
            if c != " ":
                fired.add("SPACE")
            out_c.append(" ")  # 어떤 공백이든 보통 공백 하나로
            out_o.append(o)
            continue
        out_c.append(c)
        out_o.append(o)

    order = ("ZWSP", "FULLWIDTH", "REPEAT", "SPACE")
    applied = [r for r in order if r in fired]
    return NormalizedText(
        raw=raw,
        norm="".join(out_c),
        offset_map=out_o,
        evasion_flags=[r for r in applied if r in _EVASION_RULES],
        applied_rules=applied,
    )
