"""`launcher` 메뉴 — **보이는 줄과 눌리는 줄이 같은가** (D-162).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

⛔ 2026-09-08 에 키 두 개가 겹쳐 있었다. `g` 가 「받은 파일 등록」과 「Phase 게이트 판정」에,
   `c` 가 「오픈API 수집」과 「커밋 전 점검」에. 조회가 `next(...)` 라 앞엣것만 걸리고,
   **메뉴에는 네 줄이 다 보이는데 두 줄은 눌러도 다른 것이 돌았다.**
🚨 그런데 에러가 안 났다 — `g` 는 `register` 가 인자 없이 돌아 그럴듯한 메시지를 냈다.
   「게이트 판정이 안 돌았다」는 말은 어디에도 없었다.

⛔ 2026-09-11 · 이 파일이 **한 번 더 같은 실수를 했다.** 구분줄 표식을 `"-"` 라고
   **여기에 직접 적어** 두었는데, 런처가 그것을 `GROUP = "#"`(그룹 제목 줄)로 바꿨다.
   표식의 주인은 `launcher` 다 — **글자를 베끼지 않고 모듈에서 읽는다** (D-99).
"""

from __future__ import annotations

import collections
import importlib.util

import launcher
from preprocess import EXTRACTORS, SCANNERS


def test_menu_keys_are_unique() -> None:
    """🔴 겹치면 하나는 **영영 안 눌린다.** 메뉴에는 보이는 채로."""
    keys = [k for k, _, _ in launcher.MENU if k != launcher.GROUP]
    dup = [k for k, n in collections.Counter(keys).items() if n > 1]
    assert not dup, f"겹친 키 {dup} — 하나는 안 눌린다"


def test_every_menu_row_resolves_to_what_it_says() -> None:
    """메뉴가 든 함수와 **런처가 실제로 찾아 주는** 함수가 같아야 한다.

    🚨 2026-09-11 정정 — 종전에는 `next(...)` 로 「앞엣것」을 찾았다. 런처는 이제
       `{k: fn for ...}` 딕셔너리로 찾으므로 **겹치면 뒤엣것이 이긴다.** 방향이 반대다.
       중복이 없으면 결과는 같지만, **검사한다고 적은 것과 실제가 달랐다.**
    """
    by_num = {k: fn for k, _, fn in launcher.MENU if k != launcher.GROUP}
    for key, label, fn in launcher.MENU:
        if key == launcher.GROUP or fn is None:
            continue
        assert by_num[key] is fn, f"[{key}] {label} 은 눌러도 다른 것이 돈다"


def test_extract_and_scan_are_on_the_menu() -> None:
    """🚨 전처리 단계가 통째로 메뉴에 없었다 — 런처가 파이프라인의 한 칸을 안 덮었다."""
    fns = {fn for _, _, fn in launcher.MENU if fn is not None}
    assert launcher.extract in fns
    assert launcher.scan in fns


def test_tables_point_at_modules_that_exist() -> None:
    """🚨 표에 오타가 나면 런처는 「모듈이 없다」가 아니라 **엉뚱한 실행 실패**를 낸다."""
    for src, mod in {**EXTRACTORS, **SCANNERS}.items():
        assert importlib.util.find_spec(mod) is not None, f"{src} → {mod} 가 없다"


def test_tables_name_real_sources() -> None:
    """🔴 원천 id 는 레지스트리가 원본이다 — 런처 표가 두 번째 원본이 되면 안 된다 (D-99)."""
    from collect import registry  # noqa: PLC0415

    for src in {*EXTRACTORS, *SCANNERS}:
        if src.endswith("_pdf"):  # 🚨 첨부 PDF 는 원천 id 가 아니라 저장 자리다
            continue
        assert registry.spec(src), f"{src} 가 레지스트리에 없다"
