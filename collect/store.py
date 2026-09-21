"""원본 저장과 수집 원장 (수집기 공통 규약 2·3·4·7 · D-92).

🚨 경로를 손으로 쓰지 않는다. 위치가 곧 게이트인데 사람이 위치를 고르면
   게이트가 사람 손에 달린다 (D-19).

배치 (D-92)
    data/raw/<계열>/          무손상 원본 · 등급 혼재 · 🚨 소비 금지
    data/derived/             파생물
    data/g3 · g2_facts · …    판정이 끝난 산출물
    data/manifest.jsonl       수집 원장 — 내용 없음. 유일하게 커밋되는 것
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from collect import registry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
DERIVED = DATA / "derived"
MANIFEST = DATA / "manifest.jsonl"


class StoreError(RuntimeError):
    """저장을 거부한 이유."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


#: 판을 가르는 표. 🚨 `__c` 두 글자다 — 한 글자면 원천의 이름과 부딪힌다.
#:    법령 파일이 이미 `law_002011_20250121.xml` 처럼 밑줄 하나를 쓰고 있어서,
#:    `_c...` 로 두면 원천이 준 이름의 일부인지 우리가 붙인 것인지 구분이 안 된다.
EDITION_MARK = "__c"


def edition_name(filename: str, day: str) -> str:
    """`page_0001.json` · `20260906` → `page_0001__c20260906.json`.

    🚨 이미 판 표시가 붙은 이름에 또 붙이지 않는다 — `__c20260906__c20260907` 이 되면
       원래 이름이 무엇이었는지 사람이 못 읽는다. 날짜만 갈아 끼운다.
    """
    p = Path(filename)
    stem = p.stem.split(EDITION_MARK, 1)[0]
    return f"{stem}{EDITION_MARK}{day}{p.suffix}"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


#: 🔴 **응답에 호출마다 바뀌는 값이 박혀 있는 원천** — 「같은가?」를 물을 때만 지운다.
#:
#:  🚨 **저장은 원문 그대로다** (D-92 무손상). 여기서 지우는 것은 판정용 사본이고
#:     디스크에도 원장에도 안 남는다. 이건 이 프로젝트에 **세 번째로 나오는 모양**이다 —
#:     D-117(매칭은 정규화문 · 보관은 원문) · D-152(분류는 정규화문 · 저장은 원문),
#:     그리고 여기 **동일성 판정은 정규화문 · 저장은 원문**.
#:
#:  ⛔ 2026-09-09 실측 — `mfds_press` 105 파일 **전부**가 원장에 「내용 갈림」으로 떴다.
#:     `jsessionid=` 64자 토큰이 파일마다 정확히 2개, 길이가 고정이라
#:     **바이트 수는 같고 해시만 달랐다.** D-149(offset 밀림)가 아니다 — 그건 크기가 변한다.
#:     이 상태로는 **규약 4(동일하면 스킵)가 영원히 안 걸린다.** 돌릴 때마다 105개가
#:     새 판으로 깔린다.
#:
#:  🚨 등록되지 않은 원천은 원문 해시를 그대로 쓴다 — 모르는 원천을 느슨하게 판정하지
#:     않는다. 빠뜨리면 판이 쌓일 뿐 데이터를 잃지는 않는다 (안전한 쪽으로 틀린다).
#:
#:  ⬜ **열린 것** — 세션 토큰이 `data/raw/mfds_press/` 에 210개 들어 있다.
#:     D-159(담지 않기가 가리기보다 앞선다)의 대상이지만 D-92(원본 무손상)와 부딪힌다.
#:     여기서 정하지 않는다 — 팀장 판정 사항으로 남긴다.
VOLATILE: dict[str, tuple[tuple[str, re.Pattern[bytes]], ...]] = {
    "mfds_press": (("jsessionid", re.compile(rb"jsessionid=[A-Za-z0-9]+")),),
    # 🔴 2026-09-10 실측 — 게시판 목록 5개가 재수집에서 「달라졌다」고 나왔는데,
    #    갈린 것은 **조회수 12건과 목록 순번 42건**뿐이었다. 게시물 번호는 0건 차이다.
    #    ⛔ 이대로 두면 볼 때마다 판이 생기고, 그 판이 「원천이 바뀌었다」로 읽힌다.
    #    🚨 `"no":` 는 `"ntctxt_no":` 와 안 겹친다 — 앞이 `"` 인지 `_` 인지로 갈린다.
    "mfds_hf_ingredient_board": (
        ("inqry_cnt", re.compile(rb'"inqry_cnt"\s*:\s*"?\d+"?')),
        ("no", re.compile(rb'"no"\s*:\s*"?\d+"?')),
    ),
}

#: 🚨 위 정규식과 **같은 뜻**을 필드 이름으로도 둔다 — 읽는 쪽은 파싱된 dict 를 본다.
#:    ⛔ 두 벌이지만 축이 다르다(바이트 vs 필드). 한쪽만 고치면 갈리므로 여기 나란히 둔다 (D-99).
VOLATILE_FIELDS: dict[str, tuple[str, ...]] = {
    "mfds_hf_ingredient_board": ("inqry_cnt", "no"),
}


def _strip_volatile(source_id: str, payload: bytes) -> bytes:
    """호출마다 바뀌는 값을 뺀 바이트. **판정에만 쓴다 — 저장하지 않는다.**"""
    for _name, pat in VOLATILE.get(source_id, ()):
        payload = pat.sub(b"", payload)
    return payload


def identity_sha256(source_id: str, payload: bytes) -> str:
    """「같은 응답인가」를 묻는 해시 (규약 4).

    🚨 원장의 `sha256` 과 **다른 것**이다. 원장의 것은 「이 파일의 내용」이고
       이것은 「원천이 같은 것을 줬는가」다. 둘이 갈릴 때만 원장에 `identity_sha256`
       칸이 생긴다 — 없으면 둘이 같다는 뜻이다.
    """
    return sha256(_strip_volatile(source_id, payload))


def fold_editions(paths: Iterable[Path]) -> tuple[dict[str, Path], list[tuple[str, Path]]]:
    """파일 목록을 **원본 map** 과 **판 목록**으로 가른다. 🚨 정책은 안 정한다 — 가르기만 한다.

    반환 — `({원본이름: 경로}, [(원본이름, 판 경로), …])`
    """
    base: dict[str, Path] = {}
    eds: list[tuple[Path]] = []
    for p in sorted(paths):
        stem = p.stem
        if EDITION_MARK in stem:
            eds.append((stem.split(EDITION_MARK, 1)[0], p))
        else:
            base[stem] = p
    return base, eds


def current_files(
    directory: Path, pattern: str = "*", *, allow_editions: bool = False
) -> list[Path]:
    """읽는 쪽의 **판 규칙** (2026-09-10 · D-177).

    ⛔ `save_raw` 는 「원본은 그대로 둔다(규약 2 · D-92)」만 정하고 **읽는 쪽 규칙이 없었다.**
       그래서 `data/raw/*` 를 `glob("*.xml")` 하는 추출기 16곳이 **원본과 판을 함께 읽었다.**
       실측 사고 — `preprocess/mfds_hf.py:209` `index()` 가 `hf_board_index_*__c20260907.json`
       5개를 함께 읽고 `setdefault` 로 **새 판의 행을 조용히 버리고** 있었다.

    ★ 규칙 — **원본을 읽는다.** 원본이 없고 판만 있으면 그 판이 원본이다 (D-92).
    🚨 그리고 판이 있으면 **기본값은 멈추는 것**이다. 판이 생겼다는 것은 원천이 달라졌다는
       뜻이고, **어느 것을 쓸지는 사람이 정한다** (D-143). 「최신을 쓴다」를 기본으로 두면
       2인 확인을 지난 적 없는 바이트가 조용히 판정 근거가 된다.
       ★ 이미 스스로 대조 규칙을 가진 호출자(`mfds_hf.posts()`)만 `allow_editions=True` 로
         받아 자기 정책을 적용한다.
    """
    if not directory.exists():
        return []
    base, eds = fold_editions(directory.glob(pattern))
    for stem, p in eds:
        base.setdefault(stem, p)  # 원본이 없으면 판이 원본이다
    if eds and not allow_editions:
        names = ", ".join(sorted(p.name for _, p in eds)[:5])
        raise SystemExit(
            f"🔴 {directory} 에 판(`{EDITION_MARK}`)이 {len(eds)}개 있는데 읽는 규칙이 없다.\n"
            f"   {names}{' …' if len(eds) > 5 else ''}\n"
            "  🚨 판이 생겼다는 것은 **원천이 달라졌다**는 뜻이다 — 어느 것을 쓸지는 사람이 정한다 (D-143).\n"
            "  → 원본을 그대로 쓸 것이면 이 호출에 allow_editions=True 를 주고 대조 규칙을 적는다."
        )
    return [base[k] for k in sorted(base)]


#: 🔴 **소스 id ≠ 원문 폴더 이름.** 수집기마다 `FAMILY` 를 들고 있어서 흩어져 있었다.
#:    ⛔ 2026-09-18 사고 — `ingest.cmd_register()` 가 `raw_dir(source_id)` 를 불러
#:       `law_go_kr` 파일을 **`data/raw/law_go_kr/`** 에 넣었다. 추출기는 `data/raw/law/` 를
#:       보므로 화장품법 334노드가 코퍼스에서 **조용히 사라졌다** (law_article 2,207 → 1,873).
#:    ★ 그래서 매핑을 **원문 경로를 정하는 이 모듈**이 든다. `preprocess/inventory.py` 가
#:      같은 표를 갖고 있었는데(D-99), 그쪽이 이것을 쓴다.
FAMILY_OF: dict[str, tuple[str, ...]] = {
    "mfds_hf_ingredient_board": ("mfds_hf_board",),
    "ftc_decisions_body": ("ftc",),
    "ftc_decisions_api": ("ftc",),
    "ftc_decisions": ("ftc",),
    "law_go_kr": ("law",),
    "mfds_press": ("mfds_press", "mfds_press_pdf"),
}


def families(source_id: str) -> tuple[str, ...]:
    """이 소스의 원문 폴더 이름들. 표에 없으면 소스 id 그대로다."""
    return FAMILY_OF.get(source_id, (source_id,))


def raw_dir_of(source_id: str) -> Path:
    """소스가 **글을 쓰는** 원문 폴더. 🚨 여럿이면 첫 번째가 정본이다 (mfds_press 의 pdf 는 부속)."""
    return raw_dir(families(source_id)[0])


def family_path(source_id: str, family: str | None = None) -> Path:
    """소스의 원문 폴더 **경로만** — 만들지 않는다. 🆕 2026-09-20 (D-254) 추출기가 읽는 자리다.

    ⛔ 추출기마다 `data/raw/law` · `data/raw/mfds_press_pdf` 를 **따로 박아** 두었다 — 표(`FAMILY_OF`)와
       추출기가 갈려도 아무도 몰랐다(09-18 `law_go_kr` 334노드 소실과 같은 모양 · 감사 §1-7).
    ★ 폴더 이름을 이 표에서만 꺼낸다 (D-99). `family` 를 주면 **그 소스의 계열이어야 한다** — 아니면 멈춘다 (D-220).
    🚨 `raw_dir` 과 달리 mkdir 하지 않는다 — 추출기는 import 할 때 부르고, 「없다」를 스스로 알려야 한다.
    """
    fams = families(source_id)
    name = fams[0] if family is None else family
    if name not in fams:
        raise StoreError(
            f"{family!r} 는 {source_id!r} 의 원문 폴더가 아니다 — store.FAMILY_OF 는 {fams} 다.\n"
            "  추출기와 수집기가 다른 폴더를 보면 데이터가 **조용히** 빠진다 (2026-09-18). 표를 고쳐라."
        )
    return RAW / name


def raw_dir(family: str) -> Path:
    """data/raw/<계열>/ — 없으면 만든다.

    계열은 수집리스트 v1.2 의 표기를 따른다 (law · mfds · ftc · kcia …).
    """
    d = RAW / family
    d.mkdir(parents=True, exist_ok=True)
    return d


def derived_dir(name: str) -> Path:
    d = DERIVED / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def already_have(path: Path) -> bool:
    """수집기가 **부르기 전에** 건너뛸지 — 디스크에 있거나, 원장에 **다른 기기**가 받은 기록이 있다.

    🆕 2026-09-21 (전수 재검토) — ⛔ 수집기 넷(`mfds_hf_board`·`mfds_press`·`ftc_body`·`mfds_board`)이 디스크만 봤다.
       D-250 뒤로 팀원 기기는 원장은 있고 원문은 없다 — 그래서 정본이 받은 것을 **다시 불렀고**, 조회수처럼 부를 때마다
       바뀌는 값이 든 원천(`hf_board_*.html`)은 `save_raw` 가 새 판으로 깔았다(실측 재현: 1건 → 새 판 + `mark_collected`).
    ★ **이 기기가 받은** 기록만 있고 디스크에 없으면 건너뛰지 않는다 — 그것은 유실이고 다시 받아 되살린다(`restore`).
       기기 칸 없는 옛 행(`legacy`)은 정본의 과거분이다(D-250 결정 4) — 정본이 아니면 건너뛴다.
    """
    if path.exists():
        return True
    rows = ledger_editions(path)
    if not rows:
        return False
    try:
        me = device_id()
    except StoreError:
        return True  # 별칭을 모르면(`--dry-run` 은 별칭 검사를 안 거친다) 누구 것인지 모른다 — 부르지 않는 쪽
    return any(str(r.get("device") or "") != me for r in rows)


def _same_elsewhere(
    path: Path, ident: str, file_ident: Callable[[Path], str], *, source_id: str
) -> tuple[str, Path, str | None] | None:
    """`path` 의 이름과 그 판들(`__c날짜`) 중 **같은 것**(판정용 해시)이 있으면 그 판정 — 없으면 None.

    순서 — ① 디스크에 있으면 `skip`(원장 행이 없으면 `ledger`) ② 원장에만 있고 **이 기기가 받은 것**이면 `restore`
    ③ 원장에만 있고 다른 기기(또는 기기 칸 없는 옛 행)의 것이면 `skip`.
    🚨 `path` 자신은 부르는 쪽이 이미 봤어도 다시 본다 — 비교가 한 곳에 있어야 두 갈래가 안 갈린다 (D-99).
    """
    stem = path.stem.split(EDITION_MARK, 1)[0]
    siblings = sorted(
        path.parent.glob(f"{glob.escape(stem)}{EDITION_MARK}*{glob.escape(path.suffix)}")
    )
    for q in ([path] if path.exists() else []) + siblings:
        if q.is_file() and file_ident(q) == ident:
            return ("skip" if ledger_row(q) is not None else "ledger"), q, None
    same = [r for r in ledger_editions(path) if _ident_of(r) == ident]
    if not same:
        return None
    # 🆕 2026-09-21 (소성민 코드 리뷰 #3) — ⛔ 종전에는 원장에 같은 것이 있으면 **누가 받았든** `skip` 이었다.
    #    그래서 이 기기가 받은 원문을 잃으면(D-245 334노드 같은 사고) 다시 수집해도 조용히 건너뛰고 파일은 계속 없었다 —
    #    doctor 의 `lost` 안내(「이 기기에서 다시 받는다」)와 모순이었다.
    #    ★ `lost` 와 **같은 조건** (`collect/missing.py` ⑤ · D-253) — 기기 칸이 **이 기기**일 때만 되살린다.
    #    🚨 G2 는 되살리지 않는다 — 사실을 뽑은 뒤 원문을 **일부러** 지우는 것이 규칙이고(D-17), doctor 도 `g2` 를
    #       정상으로 가른다. 되살리면 평소 수집 한 번에 지운 원문이 전부 돌아온다.
    me = device_id()
    mine = [r for r in same if str(r.get("device") or "") == me]
    if not mine or registry.is_g2(source_id):
        return "skip", path, None  # 규약 4 가 기기를 넘어 선다 — 다른 기기가 같은 것을 이미 받았다
    # 🔄 2026-09-21 (전수 재검토 I7) — **원본 이름을 먼저, 그다음 가장 늦은 행.** ⛔ 종전 `mine[-1]` 은 색인의
    #    처음 넣은 순서라, `adopt` 로 치운 옛 판 경로를 되살렸다(실측 재현).
    #    🚨 되살릴 자리에 **다른 바이트가 이미 있으면** 그 자리는 안 쓴다 — 덮어쓰지 않는다(규약 2).
    #       위 디스크 대조가 같은 것을 못 찾았으니 그 파일은 원장과 다르다 — 새 판 규칙으로 넘긴다(None).
    free = [r for r in mine if not (ROOT / _norm(str(r["path"]))).exists()]
    if not free:
        return None
    base = _norm(_rel(path.with_name(stem + path.suffix)))
    pick = next((r for r in free if _norm(str(r["path"])) == base), None) or max(
        free, key=lambda r: str(r.get("fetched_at") or "")
    )
    return "restore", ROOT / _norm(str(pick["path"])), None


def plan_raw(
    family: str,
    filename: str,
    ident: str,
    file_ident: Callable[[Path], str],
    *,
    source_id: str,
) -> tuple[str, Path, str | None]:
    """원문 한 개를 **어디에 둘지** 정한다 — `save_raw` 와 `ingest register` 가 같이 쓴다 (D-99 · D-254).

    반환 — `(판정, 경로, supersedes)`
        "write"  — 이 경로에 새로 쓴다 (🚨 이름이 넘긴 것과 다를 수 있다 — 새 판 `__c날짜`)
        "skip"   — 같은 것이 이미 있다 (디스크든 원장이든 · 규약 4)
        "ledger" — 디스크에 **같은 바이트**가 있는데 그 경로의 원장 행이 없다 — 쓰지 않고 행만 보탤 자리
        "restore" — 🆕 **이 기기가 받았다고** 원장에 적힌 같은 것이 디스크에 없다 — 그 경로에 **다시 쓴다**
                    (원장 행은 이미 있다 · 바이트가 행과 다를 때만 보탠다 — 부르는 쪽이 `restore_needs_row` 로 본다)
    `file_ident` — 디스크 파일의 판정용 해시를 내는 함수 (수집기는 바이트 · register 는 스트리밍).
    `source_id` — G2 인지 본다(`restore` 를 안 낸다 · 아래).

    ⛔ 2026-09-20 전까지 이 판정이 `save_raw` 에만 있었고 `register` 는 디스크만 봤다 —
       원장(다른 기기)에 있는 것을 다시 넣고, 원장에 없는 같은 파일을 조용히 건너뛰었다 (감사 §2 register).
    """
    path = raw_dir(family) / filename
    supersedes: str | None = None

    # 🆕 2026-09-20 (D-250) — **이 기기에 파일이 없어도 원장(git)이 안다.** 팀원 PC 에는 클론 B 의 원문이 없다.
    #    ⛔ 디스크만 보면 B 에 이미 있는 것을 **다시 받고**, 같은 경로·다른 바이트가 생겨 합칠 때 갈린다.
    #    ★ 원장의 그 경로 행과 판정용 해시가 같으면 받지 않는다 · 다르면 새 판 이름으로 둔다 — 디스크 규칙과 같다.
    # 🔄 2026-09-21 (전수 재검토 I6·I7) — **같은 것이 이미 어딘가에 있는가**를 먼저 한 곳에서 묻는다.
    #    ⛔ 종전에는 두 갈래가 따로 물었다 — 원장 갈래는 옛 판까지 봤고, 디스크 갈래는 **오늘 판만** 봤다.
    #       그래서 한 번 내용이 바뀐 원천은 수집할 때마다 날짜만 다른 **같은 판**이 또 생겼고(실측 재현:
    #       `__c0907`·`__c0908`·`__c0909` 가 바이트 동일), 원본이 되살아난 뒤에는 옛 판을 되살리지 않고 새 판을 썼다.
    found = _same_elsewhere(path, ident, file_ident, source_id=source_id)
    if found is not None:
        return found

    if not path.exists():
        known = ledger_row(path)
        if known is not None:
            versioned = path.with_name(edition_name(filename, _today()))
            vk = ledger_row(versioned)
            if vk is not None and _ident_of(vk) == ident:
                return "skip", versioned, None
            if vk is not None or versioned.exists():
                raise StoreError(
                    f"{versioned.name} 가 원장에 이미 있고 **또 내용이 다르다** — 하루에 두 번 갈렸다.\n"
                    "  자동으로 판을 더 만들지 않는다 (위 규칙과 같다)."
                )
            supersedes = _rel(path)
            print(
                f"  🔴 새 판 — {filename} 이(가) 원장(다른 기기)에 있고 내용이 다르다.\n"
                f"     {versioned.name} 으로 저장한다. 합칠 때 정본에서 `adopt` 로 판을 고른다 (D-246)."
            )
            path = versioned

    if path.exists():
        if file_ident(path) == ident:
            # 규약 4 — 동일하면 스킵. 원장 행이 없으면 부르는 쪽이 정한다 ("ledger")
            return ("skip" if ledger_row(path) is not None else "ledger"), path, None

        versioned = path.with_name(edition_name(filename, _today()))
        if versioned.exists():
            if file_ident(versioned) == ident:
                # 오늘 판을 이미 받았다
                return ("skip" if ledger_row(versioned) is not None else "ledger"), versioned, None
            raise StoreError(
                f"{versioned} 가 이미 있고 **또 내용이 다르다**.\n"
                "  🚨 하루에 두 번 갈렸다 — 원천이 바뀐 것이 아니라 **응답이 호출마다\n"
                "     다를** 수 있다 (레코드 순서 비결정 · 응답에 유동 필드 …).\n"
                "  자동으로 판을 더 만들지 않는다 — 돌릴 때마다 파일이 불어난다.\n"
                "  두 판을 비교해 무엇이 다른지 보고, 원천의 성질을 원장에 적어라."
            )

        supersedes = _rel(path)
        # 🚨 라이브러리에서 화면에 찍는 것이 깔끔하지 않다는 건 안다. 그런데 이 한 줄이
        #    없으면 파일 이름이 조용히 바뀐다 — 안 보이는 것보다 안 깔끔한 편이 낫다.
        print(
            f"  🔴 새 판 — {filename} 이(가) 이미 있고 내용이 다르다.\n"
            f"     {versioned.name} 으로 저장한다. 원본은 그대로 둔다 (규약 2).\n"
            f"     🚨 원천이 같은 이름으로 다른 것을 준다는 뜻이다 — 원장에 적어라 (D-54)."
        )
        path = versioned

    return "write", path, supersedes


def save_raw(
    source_id: str,
    family: str,
    filename: str,
    payload: bytes,
    *,
    url: str,
    rows: int | None = None,
) -> Path | None:
    """원본을 무손상 저장하고 원장에 1행 남긴다.

    돌려주는 값:
        Path  — 새로 저장했다 (🚨 **이름이 넘긴 것과 다를 수 있다** — 아래 「새 판」)
        None  — sha256 이 같아 스킵했다 (규약 4)

    🚨 **덮어쓰지 않는다** (규약 2). 전처리는 언제든 재실행 가능해야 하고, 그 전제가
       원본 불변이다. 이건 안 바뀌었다 — 아래도 덮어쓰지 않는다.

    ── 🔴 같은 이름, 다른 내용 → **새 판으로 저장한다** (2026-09-06 · 팀장 결정) ──

    예전에는 여기서 `StoreError` 로 멈추고 「새 파일명으로 저장하라」고 사람에게 시켰다.
    2026-09-06 전수조사에서 그 자리가 **셋** 나왔고 셋 다 원인이 같았다 —

        law_002011_20250121.xml             −5 B   시행일 그대로, 본문 정정
        mfds_sanctions/page_0001.json     +179 B   시계열 — 처분이 추가됨
        mfds_hf_individual/page_0001.json   ±0 B   길이 그대로, 값 정정

    🚨 **파일명이 「원천의 어느 시점인가」를 담지 않는다.** `{ID}_{시행일}` 은 「시행일이
       같으면 같은 판」을, `page_{N}` 은 「N번째 장은 늘 같다」를 전제하는데 둘 다 깨졌다.
       원천이 살아 있는 한 이 자리는 계속 늘고, 그때마다 팀원의 수집이 멈춘다.

    ★ 그래서 **`StoreError` 메시지가 사람에게 시키던 일을 그대로 자동화한다** —
      `page_0001.json` → `page_0001__c20260906.json` (`c` = collected).
      규약 2(덮어쓰지 않음)도 규약 4(동일하면 스킵)도 그대로 산다.

    🚨 **하루에 두 번 갈리면 그때는 멈춘다.** 그건 원천이 바뀐 것이 아니라 **응답이
       호출마다 다른 것**이고(레코드 순서 비결정 등), 자동으로 판을 만들면 돌릴 때마다
       파일이 불어난다. 자동화의 유일한 위험이 그것이라 거기에 사람 검문소를 남겼다.
       (`mfds_hf_individual` 은 재호출로 안정성을 확인했다 — 2026-09-06.)

    🚨 새 판을 만들 때는 **반드시 화면에 남긴다.** 조용히 다른 이름으로 저장하는 것이
       이 설계의 값이자 위험이다. 부르는 쪽은 자기가 넘긴 `filename` 을 찍으므로
       여기서 안 찍으면 아무도 모른다.
    """
    device_id()  # 🆕 D-250 — 별칭이 없으면 **쓰기 전에** 멈춘다
    digest = sha256(payload)
    # 🔴 「같은가?」는 **판정용 해시**로 묻는다 (`VOLATILE`). 원문은 그대로 저장한다.
    ident = identity_sha256(source_id, payload)
    verdict, path, supersedes = plan_raw(
        family,
        filename,
        ident,
        lambda q: identity_sha256(source_id, q.read_bytes()),
        source_id=source_id,
    )
    if verdict == "restore":
        # 🆕 2026-09-21 (코드 리뷰 #3) — 이 기기가 받았다고 적혔는데 없던 원문. **그 경로에 다시 쓴다**(덮을 것이 없다).
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        print(f"  🔄 되살림 — {path.name} (원장에 이 기기가 받았다고 적혔는데 디스크에 없었다)")
        if restore_needs_row(path, digest):
            manifest_append(
                source_id=source_id,
                url=url,
                sha256=digest,
                bytes_=len(payload),
                rows=rows,
                path=str(path.relative_to(ROOT)),
                supersedes=None,
                identity=None if ident == digest else ident,
            )
        return path
    if verdict != "write":
        # 규약 4 — 동일하면 스킵. 🚨 "ledger"(디스크엔 같은 것이 있는데 원장 행이 없다)도 여기선 스킵이다 —
        #    수집기의 종전 동작 그대로다. 행을 보태는 것은 `ingest register` 만 한다 (D-254).
        return None

    path.write_bytes(payload)
    manifest_append(
        source_id=source_id,
        url=url,
        sha256=digest,
        bytes_=len(payload),
        rows=rows,
        path=str(path.relative_to(ROOT)),
        supersedes=supersedes,
        identity=None if ident == digest else ident,
    )
    return path


def manifest_append(
    *,
    source_id: str,
    url: str,
    sha256: str,
    bytes_: int,
    rows: int | None = None,
    path: str | None = None,
    supersedes: str | None = None,
    identity: str | None = None,
) -> None:
    """원장에 1행 append (규약 3).

    🚨 게이트 18 이 이 파일을 읽는다 — source_id 가 레지스트리에 있고 G1 이 아닐 것.
       원장이 곧 「raw 에 무엇이 들어왔는가」의 유일한 증언이다.

    🚨 `supersedes` — 이 행이 **어느 파일의 새 판인가** (2026-09-06 신설).
       파일명만으로도 짐작은 되지만, 짐작과 기록은 다르다. 판이 여럿 쌓인 뒤에
       「이게 무엇의 다음 판인가」를 이름 규칙으로 되짚게 만들지 않는다.
       옛 행에는 이 칸이 없다 — 없으면 `None` 이고, 그것은 「새 판이 아니다」는 뜻이다.

    🚨 `identity_sha256` — **동일성 판정에 쓴 해시** (2026-09-09 신설 · `store.VOLATILE`).
       원문 해시와 **다를 때만** 칸이 생긴다. 칸이 있다는 것은 「이 원천은 응답에
       호출마다 바뀌는 값이 박혀 있어서, 원문 해시로는 같은지 물을 수 없다」는 뜻이다.
       ⛔ 이 칸을 「내용 해시」로 읽지 마라 — 판정용이라 **원문을 재현하지 못한다.**
    """
    registry.spec(source_id)  # 미등록이면 여기서 거부된다
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source_id": source_id,
        "fetched_at": _now(),
        "url": url,
        "sha256": sha256,
        "bytes": bytes_,
        "rows": rows,
        "path": path,
    }
    # 🚨 새 판일 때만 칸을 만든다 — 안 그러면 기존 1만 행과 새 행의 모양이 달라지고,
    #    `null` 만 든 칸이 10,000줄 붙는다. 없는 것과 비어 있는 것은 다르다.
    if supersedes:
        row["supersedes"] = supersedes
    if identity:
        row["identity_sha256"] = identity
    # 🆕 2026-09-20 (D-250) — **어느 기기가 받았나.** 팀원도 수집한다. 새 행에만 붙인다(옛 행은 「기록 없음」).
    row["device"] = device_id()
    # 🔴 `newline="\n"` — 2026-09-19 실측: 이 줄이 없어 Windows 에서 원장 **5,148줄이 CRLF** 로 붙었다
    #    (그날 수집한 mfds_cgm_expc 5,129 · ftc_decisions_body 19 전부). 게이트가 `Path.open("a")` 의
    #    모드를 못 읽어 지나쳤다 — 검사기도 같이 고쳤다 (D-241).
    with MANIFEST.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _index_add(row)


# ══════════════════════════════════════════════════════════
# 🆕 원장을 읽는 쪽 — 기기를 넘는 규칙 (2026-09-20 · D-250)
# ══════════════════════════════════════════════════════════
#: `[임의]` 다른 기기가 이 기간 안에 같은 소스를 받았으면 수집 전에 **경고**한다(런처 `collect --force`).
#:    **바꾸는 조건** — 원천 갱신 주기를 재서 소스별로 나눌 필요가 보이면. 주 단위면 공정위 결정문
#:    (가장 자주 바뀌는 쪽)도 충분하다고 봤다. 막는 것이 아니라 알린다 — 겹쳐도 sha 대조로 섞이지 않는다.
OVERLAP_DAYS = 7


#: 기기 별칭의 모양 — 🚨 원장은 **공개 저장소**에 올라간다. 공백·한글을 받지 않는다(실명·「○○ 노트북」 꼴을 거른다).
#:    실명 금지·중복 금지는 **팀 회의로 정한다**(팀장 판정 2026-09-20) — 코드는 모양만 본다.
DEVICE_RE = re.compile(r"[A-Za-z0-9._-]{1,32}")
#: 정본이 별칭 없이 수집하면 원장에 적는 이름. 🚨 팀원 별칭으로 쓰지 않는다 (`setup` 이 막는다)
CANONICAL_DEVICE = "canonical"


def device_problem(v: str, role: str | None) -> str | None:
    """별칭 `v` 가 못 쓰는 이유 한 줄, 쓸 수 있으면 `None` — **판정의 정본은 여기 한 곳**이다 (D-99).

    🆕 2026-09-21 — ⛔ 종전에는 `canonical` 예약어를 `data_store.setup` 만 막았다. `.env` 에 손으로
       `DATA_DEVICE=canonical` 을 적은 팀원 기기는 `device_id()` 가 그대로 받아 원장에 `canonical` 로 적었고,
       `raw_inbox` 는 그 행을 「정본에 이미 있다」로 보고 **raw-publish 에서 건너뛴다**(받은 원문이 정본에 안 간다).
       `doctor` 도 모양만 봤다. 세 곳(`device_id` · `data_store.setup` · `doctor`)이 이 함수를 부른다.
    """
    if not DEVICE_RE.fullmatch(v):
        return "모양이 틀렸다 — 영문·숫자·`._-` 32자 이내 (예: collector-1)"
    if v == CANONICAL_DEVICE and role != "canonical":
        return f"`{CANONICAL_DEVICE}` 는 정본 예약어다 — 정본(DATA_ROLE=canonical) 밖에서는 못 쓴다"
    return None


def device_id() -> str:
    """이 기기의 별칭 — `.env` 의 `DATA_DEVICE`. 비었으면 정본만 `canonical`, 나머지는 **멈춘다**.

    🔄 2026-09-20 (D-250 개정 · 팀장 판정) — ⛔ 종전에는 비면 **호스트 이름의 해시 8자**를 적었다.
       되돌릴 수는 없어도 **대입**은 된다(`DESKTOP-` + 7자 ≈ 780억 가지 · GPU 수 시간) — 공개 원장에
       PC 이름을 적는 것과 같았다. 무작위 별칭은 `.env` 를 새로 만들면 바뀐다. 그래서 **팀원이 정한다.**
    🚨 쓰기 **전에** 부른다(`save_raw` 첫 줄 · `ingest`) — 파일만 놓이고 원장 행이 안 남는 일을 막는다 (D-72).
    """
    from collect import env  # noqa: PLC0415 — `.env` 를 여는 곳은 한 곳이다 (D-99)

    v = env.setting("DATA_DEVICE")
    role = env.setting("DATA_ROLE")
    if v:
        why = device_problem(v, role)
        if why:
            raise StoreError(
                f"DATA_DEVICE {why}. 아무것도 저장하지 않았다.\n"
                "  🚨 원장은 공개 저장소에 올라간다 — 실명을 쓰지 않는다.\n"
                "  고치기: uv run python launcher.py data-setup --device <별칭>"
            )
        return v
    if role == "canonical":
        return CANONICAL_DEVICE
    raise StoreError(
        "기기 별칭(DATA_DEVICE)이 비어 있다 — 누가 받았는지 원장에 못 적는다. 아무것도 저장하지 않았다.\n"
        "  별칭은 팀 회의에서 겹치지 않게 정한다 (실명 금지 · 예: collector-1).\n"
        "  넣기: uv run python launcher.py data-setup --device <별칭>"
    )


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _norm(p: str) -> str:
    """원장의 경로는 기기마다 `\\`·`/` 가 섞여 있다 — 비교는 `/` 로 한다."""
    return p.replace("\\", "/")


#: (원장 경로, (크기, 수정 시각)) → 경로별 마지막 행. 🚨 수집 한 번에 수천 번 부르므로 한 번만 읽는다.
#:    크기만 보면 `git pull` 이 같은 길이로 바꾼 원장을 못 알아챈다 — 수정 시각도 본다.
_INDEX: tuple[str, tuple[int, int], dict[str, dict[str, Any]]] | None = None


def _stamp() -> tuple[int, int]:
    if not MANIFEST.exists():
        return (-1, -1)
    st = MANIFEST.stat()
    return (st.st_size, st.st_mtime_ns)


def _index() -> dict[str, dict[str, Any]]:
    global _INDEX
    size = _stamp()
    if _INDEX is None or _INDEX[0] != str(MANIFEST) or _INDEX[1] != size:
        idx: dict[str, dict[str, Any]] = {}
        if MANIFEST.exists():
            for line in MANIFEST.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r.get("path"):
                        idx[_norm(str(r["path"]))] = r
        _INDEX = (str(MANIFEST), size, idx)
    return _INDEX[2]


def _index_add(row: dict[str, Any]) -> None:
    """방금 붙인 행을 색인에도 넣는다 — 다시 읽지 않게."""
    global _INDEX
    if _INDEX is not None and _INDEX[0] == str(MANIFEST) and row.get("path"):
        _INDEX[2][_norm(str(row["path"]))] = row
        _INDEX = (_INDEX[0], _stamp(), _INDEX[2])


def ledger_row(path: Path) -> dict[str, Any] | None:
    """원장에 적힌 이 경로의 **마지막** 행. 없으면 None."""
    return _index().get(_norm(_rel(path)))


def ledger_editions(path: Path) -> list[dict[str, Any]]:
    """원장에 적힌 이 이름과 **그 판들**(`__c날짜`)의 마지막 행 — 판이 여럿이면 옛 판과 같을 수도 있다."""
    rel = _norm(_rel(path))
    parent, _, name = rel.rpartition("/")
    p = Path(name)
    stem = p.stem.split(EDITION_MARK, 1)[0]
    head = f"{parent}/{stem}" if parent else stem
    return [
        r
        for k, r in _index().items()
        if k == rel or (k.startswith(head + EDITION_MARK) and k.endswith(p.suffix))
    ]


def _ident_of(row: dict[str, Any]) -> str:
    return str(row.get("identity_sha256") or row.get("sha256"))


def restore_needs_row(path: Path, digest: str) -> bool:
    """`plan_raw` 가 `restore` 를 낸 뒤 — 되살린 파일의 바이트가 그 경로의 원장 행과 **다르면** 행을 보탠다.

    🚨 판정용 해시(`VOLATILE`)만 같고 바이트는 다를 수 있다 — 그대로 두면 원장 sha 가 실제 파일과 안 맞아
       `doctor --hash` 가 훼손으로 찍는다. 같으면 보태지 않는다 — 같은 행을 두 번 적지 않는다.
       🔗 `save_raw` · `ingest.cmd_register` 가 같이 쓴다 (D-99).
    """
    row = ledger_row(path)
    return row is None or str(row.get("sha256")) != digest


def recent_by_others(
    source_id: str, days: int = OVERLAP_DAYS, now: datetime | None = None
) -> dict[str, str]:
    """다른 기기가 `days` 안에 이 소스를 받은 기록 — `{기기: 마지막 시각}`.

    🚨 기기 칸이 없는 옛 행(09-20 이전)은 **정본이 받은 것**이다 — 그때는 정본만 수집했다 (D-226).
       그래서 정본 기기에서는 건너뛰고, 다른 기기에서는 「정본(기기 칸 이전)」으로 알린다.
    """
    from collect import env  # noqa: PLC0415

    me = device_id()
    canonical = env.setting("DATA_ROLE") == "canonical"
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    out: dict[str, str] = {}
    if not MANIFEST.exists():
        return out
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("source_id") != source_id:
            continue
        who = str(r.get("device") or "")
        if who == me or (not who and canonical):
            continue
        who = who or "정본(기기 칸 이전)"
        try:
            at = datetime.fromisoformat(str(r.get("fetched_at")))
        except ValueError:
            continue
        if at.tzinfo is None:  # 옛 행 — UTC 로 적었다 (`_now`)
            at = at.replace(tzinfo=UTC)
        if at >= cutoff:
            out[who] = max(out.get(who, ""), str(r["fetched_at"]))
    return out


def stamp(row: dict[str, Any], source_id: str) -> dict[str, Any]:
    """산출 행에 provenance · redistributable 을 박는다 (규약 7 · D-71).

    🚨 나중에 못 한다. 섞인 뒤에는 어느 줄이 어디서 왔는지 알 수 없고,
       redistributable=false 가 한 줄이라도 섞이면 그 골든셋 전체를 공개할 수 없다.
       그래서 상속값을 **행에 복사**한다 — 소스 등급이 나중에 바뀌어도 조인의 답이 흔들리지 않게.
    """
    row["provenance"] = source_id
    row["redistributable"] = registry.redistributable(source_id)
    return row


def drop_raw_for_g2(source_id: str, family: str, filename: str, *, facts_path: Path) -> None:
    """G2 소스의 원본을 삭제한다 (D-17 · D-92).

    🚨 「G2 = 추출된 사실만 · 원문 없음」과 「원본 무손상 저장」은 정면으로 부딪친다.
       화해는 이것이다 — 사실을 뽑은 뒤 원본을 지우고 manifest 의 sha256 만 남긴다.
       재실행은 보관본이 아니라 **재수집**으로 한다.

    사실 파일이 실제로 만들어진 뒤에만 지운다. 순서가 뒤집히면 둘 다 잃는다.
    """
    if not registry.is_g2(source_id):
        raise StoreError(f"{source_id!r} 는 G2 가 아니다. 이 경로를 쓰지 않는다.")
    if not facts_path.exists() or facts_path.stat().st_size == 0:
        raise StoreError(f"{facts_path} 가 비어 있다. 사실을 뽑기 전에 원본을 지우면 둘 다 잃는다.")
    target = RAW / family / filename
    if target.exists():
        target.unlink()
