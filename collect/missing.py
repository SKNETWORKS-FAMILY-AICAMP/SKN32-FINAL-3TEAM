"""collect/missing.py — 원장에 있는데 **이 기기 디스크에 없는** 원문을 「왜 없는지」로 가른다 (D-253).

  doctor --data 와 inventory 가 같이 쓴다 — 같은 결손을 두 도구가 다르게 부르지 않게 (D-99).
  🔄 2026-09-21 — **경보 수준(`level`)도 여기서 정한다.** 사본은 `legacy`·`query` 를 접는다 (아래 `REPLICA_FOLDS`).

팀장 — *「doctor 은 제 기능을 충분히 하고 있나?」* (2026-09-20). ⛔ 종전 doctor 는 없는 이유를 셋(ㄱ G2 · ㄴ 다른 클론 ·
ㄷ 질의 필터)으로만 나눴다. 실측(클론 B · 2026-09-20) `law_go_kr` 36개는 **셋 다 아니었다** —
  ① 34개는 법령 **서식** — 수집기가 기본으로 안 받게 바뀐 것(`collect/law_annex.py` · D-220). doctor 는
     「재수집하면 닫힌다」고 안내했다 — **다시 받아도 안 돌아오고, 돌아오면 안 된다.**
  ② 2개는 09-18 `law_002015` 를 옮기던 **자리의 흔적** — 같은 내용이 원래 이름으로 디스크에 있다.
  그리고 D-250 에서 원장에 **기기 칸**이 생겼는데 doctor 는 「다른 클론 것과 유실은 원장으로 못 가른다」고 말하고 있었다.
★ 결손 53개 중 사람이 볼 것이 몇 개인지 **도구가 말하지 못했다** — 사람(클로드)이 원장과 폴더를 맞대서야 갈렸다.

**가르는 순서** — 앞에서 걸린 것이 이긴다. **정상**은 사람이 볼 필요가 없고, 🔴 는 이 기기에서 답할 수 있는 결손이다.

  | 이유       | 정상 | 무엇                                                                   |
  |------------|:----:|------------------------------------------------------------------------|
  | `moved`    |  ✅  | 같은 sha·**같은 이름**(판 표시 뗀)의 기록이 **디스크의 다른 경로**에 있고 크기가 같다 |
  | `excluded` |  ✅  | 수집기가 **기본으로 안 받는다**고 선언한 경로 (`NOT_KEPT`)              |
  | `g2`       |  ✅  | G2 — 사실을 뽑은 뒤 원문을 지우는 것이 규칙 (D-92)                      |
  | `cleared`  |  ✅  | 크기가 급감한 판(오류 응답)이고, 같은 이름의 정상 판이 디스크에 있다 (D-147) |
  | `other`    |  ✅  | 기록한 기기가 **전부 이 기기가 아니다** (D-250 기기 칸)                 |
  | `lost`     |  🔴  | **이 기기가 받았다**고 원장에 적혔는데 없다 — 유실이거나 손으로 지웠다   |
  | `query`    |  🟡  | 질의 기반 원천(prec·decc) — 필터가 뺀 것일 수 있다. `--dry-run` 대조 (D-153) |
  | `legacy`   |  🟡  | 기기 칸 이전 기록 — 다른 기기 것인지 유실인지 원장으로 못 가른다          |

🚨 `moved` 는 **해시를 다시 재지 않는다** — 원장의 sha 와 디스크 **크기**만 맞댄다. 크기가 같은데 내용이 조용히
   바뀐 파일까지 「옮겨짐」으로 볼 수 있다. 그 축은 `doctor --data --hash` 가 잰다 (D-177).
🚨 `excluded` 는 **선언된 것만** 정상이다. 수집기가 안 받게 바꾸고 선언을 빠뜨리면 `legacy`·`lost` 로 떨어진다 —
   떨어지는 쪽이 안전하다 (D-220). 선언은 수집기 옆에 둔다 — 안 받는 이유를 아는 곳이 거기다.
⛔ 이 모듈은 파일을 **열지 않는다** — 있는지와 크기만 본다.
"""

from __future__ import annotations

import collections
import fnmatch
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: 이유 → (표시, 정상인가, 한 줄 설명). 🚨 순서가 **가르는 순서**다.
REASONS: dict[str, tuple[str, bool, str]] = {
    "moved": (
        "✅",
        True,
        "같은 이름·같은 내용이 디스크의 다른 경로에 있다 (옮기거나 판을 채택한 흔적)",
    ),
    "excluded": ("✅", True, "수집기가 기본으로 안 받는다고 선언한 것 — 재수집해도 안 돌아온다"),
    "g2": ("✅", True, "G2 — 사실을 뽑은 뒤 원문을 지우는 것이 규칙이다 (D-92)"),
    "cleared": ("✅", True, "오류 응답 판을 치웠고 같은 이름의 정상 판이 있다 (D-147)"),
    "other": ("✅", True, "다른 기기가 받은 것 — 이 기기에 없는 것이 정상이다 (D-19 · D-250)"),
    "lost": ("🔴", False, "**이 기기가 받았다**고 원장에 적혔는데 없다 — 유실이거나 손으로 지웠다"),
    "query": (
        "🟡",
        False,
        "질의 기반 원천 — 필터가 뺀 것일 수 있다. `--dry-run` 질의별 실측과 맞댄다 (D-153)",
    ),
    "legacy": ("🟡", False, "기기 칸 이전 기록 — 다른 기기 것인지 유실인지 원장으로 못 가른다"),
}

#: 크기 급감의 기준 — 🔄 `scripts/doctor.py` 의 급감 판별과 **같은 수**를 쓴다 (D-209 · 그쪽이 이것을 읽는다).
#: `[임의]` — 1,000 B 이상에서 20% 미만으로 줄면 오류 본문의 모양으로 본다(09-08 실측 51,636 → 146 B · D-147).
COLLAPSE_MIN_BYTES = 1000
COLLAPSE_RATIO = 0.2

#: 질의 기반 원천의 파일 이름 앞자리 — 필터를 바꾸면 목록에서 빠진다 (D-153)
QUERY_PREFIXES = ("prec_", "decc_")


def _norm(p: str) -> str:
    """원장 경로의 구분자를 `/` 로 — 윈도우에서 쓴 줄을 어디서나 같게 읽는다."""
    return p.replace("\\", "/")


def _rel_raw(p: str) -> str:
    """`data/raw/law/annex/x.json` → `law/annex/x.json` (선언 패턴이 보는 모양)."""
    parts = PurePosixPath(_norm(p)).parts
    return "/".join(parts[2:]) if len(parts) > 2 and parts[1] == "raw" else _norm(p)


def _stem(p: str) -> str:
    """판 표시를 걷은 이름 — `page_0001__c20260908.json` → `data/raw/x/page_0001.json`."""
    from collect.store import EDITION_MARK  # noqa: PLC0415 — 판 표시의 정본 (D-99)

    q = PurePosixPath(_norm(p))
    return str(q.with_name(q.stem.split(EDITION_MARK, 1)[0] + q.suffix))


def _name_key(p: str) -> str:
    """판 표시를 걷은 **파일 이름만** — 폴더는 안 본다. `moved` 가 「같은 것을 옮겼다」를 가를 때 쓴다 (코드 리뷰 #5)."""
    return PurePosixPath(_stem(p)).name


def declared() -> dict[str, tuple[tuple[str, str], ...]]:
    """수집기가 **기본으로 안 받는다**고 선언한 경로 — `{source_id: ((glob, 이유), …)}`.

    🚨 선언은 수집기 모듈에 둔다(`NOT_KEPT`). 여기는 모으기만 한다. 새 수집기가 무엇을 안 받게 되면
       그 모듈에 `NOT_KEPT` 를 두고 아래 표에 한 줄 더한다 — 빠뜨리면 `legacy`·`lost` 로 떨어진다(안전한 쪽).
    """
    from collect import law_annex  # noqa: PLC0415 — 수집기를 부를 때만 무겁다

    return {law_annex.SOURCE_ID: law_annex.NOT_KEPT}


def _grade(source_id: str) -> str:
    from collect import registry  # noqa: PLC0415

    try:
        return str(registry.spec(source_id).get("grade", "?"))
    except Exception:  # noqa: BLE001 — 미등록은 doctor 가 따로 🔴 로 센다
        return "?"


def _me() -> str | None:
    """이 기기의 별칭. 🚨 없으면 None — 진단은 별칭이 없어도 돈다(수집만 막힌다 · D-250)."""
    from collect import store  # noqa: PLC0415

    try:
        return store.device_id()
    except Exception:  # noqa: BLE001 — StoreError(별칭 없음) · .env 없음 모두 「모른다」
        return None


def classify(
    rows: Iterable[dict[str, Any]],
    *,
    root: Path = ROOT,
    me: str | None = ...,  # type: ignore[assignment]
    grade_of: Callable[[str], str] | None = None,
    rules: dict[str, tuple[tuple[str, str], ...]] | None = None,
) -> dict[str, tuple[str, str]]:
    """원장 행 → **디스크에 없는 path** 마다 `(이유, 덧붙임)`. 있는 path 는 안 돌려준다.

    `me`·`grade_of`·`rules` 는 테스트가 바꾼다. 기본은 이 기기의 `.env`·레지스트리·수집기 선언이다.
    """
    if me is ...:
        me = _me()
    grade_of = grade_of or _grade
    rules = declared() if rules is None else rules

    by_path: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        if r.get("path"):
            by_path[_norm(r["path"])].append(r)

    exists_cache: dict[str, int | None] = {}

    def size_on_disk(p: str) -> int | None:
        if p not in exists_cache:
            f = root / p
            exists_cache[p] = f.stat().st_size if f.is_file() else None
        return exists_cache[p]

    missing = [p for p in by_path if size_on_disk(p) is None]
    if not missing:
        return {}

    # sha → 그 sha 를 기록한 (path, bytes) — `moved` 를 가른다
    by_sha: dict[str, list[tuple[str, int, str]]] = collections.defaultdict(list)
    for p, rs in by_path.items():
        for r in rs:
            if r.get("sha256"):
                by_sha[r["sha256"]].append(
                    (p, int(r.get("bytes") or 0), str(r.get("source_id") or ""))
                )
    # 판을 걷은 이름 → 그 이름을 쓰는 path 들 — `cleared` 를 가른다
    by_stem: dict[str, list[str]] = collections.defaultdict(list)
    for p in by_path:
        by_stem[_stem(p)].append(p)

    out: dict[str, tuple[str, str]] = {}
    for p in missing:
        rs = by_path[p]
        sid = str(rs[0].get("source_id") or "")

        # ① moved — 같은 sha 의 기록이 다른 경로에 있고, 그 파일의 크기가 그 기록과 같고, **같은 이름**이다
        #    🔄 2026-09-21 (소성민 코드 리뷰 #5) — ⛔ 종전에는 이름을 안 봤다. 바이트만 같은 **별개 파일**
        #       (같은 첨부가 두 게시물에 붙은 것 · 같은 빈 페이지)이 있으면 없는 경로를 「옮겨짐」으로 봤고,
        #       `raw_inbox` 가 그것을 정리된 것(`SETTLED`)으로 여겨 팀원 원문이 `raw-import` 에서 **조용히 빠졌다.**
        #       doctor 도 ✅ 로 보고했다. ★ 실제로 알려진 옮김은 둘 — 판 채택(`x__c날짜` → `x` · D-246)과
        #       폴더 옮김(D-245 `law_go_kr/` → `law/`)이고, 둘 다 **판 표시를 뗀 파일 이름이 같다.**
        #    🔄 같은 날 (전수 재검토 I9) — **같은 원천**도 요구한다. ⛔ 이름만 보면 `page_0001.json` 같은 흔한 이름이
        #       **다른 원천끼리** 바이트가 같을 때 옮겨짐이 됐다(실측 재현: mfds_sanctions ↔ mfds_hf_individual).
        name = _name_key(p)
        where = next(
            (
                q
                for r in rs
                for q, b, s in by_sha.get(str(r.get("sha256") or ""), ())
                if q != p and s == sid and _name_key(q) == name and size_on_disk(q) == b
            ),
            None,
        )
        if where:
            out[p] = ("moved", where)
            continue

        # ② excluded — 수집기 선언
        rel = _rel_raw(p)
        hit = next((why for pat, why in rules.get(sid, ()) if fnmatch.fnmatchcase(rel, pat)), None)
        if hit:
            out[p] = ("excluded", hit)
            continue

        # ③ g2
        if grade_of(sid).startswith("G2"):
            out[p] = ("g2", "")
            continue

        # ④ cleared — 이 path 의 기록이 전부 작고, 같은 이름의 다른 판이 디스크에 크게 있다
        mine = max(int(r.get("bytes") or 0) for r in rs)
        sib = [size_on_disk(q) or 0 for q in by_stem[_stem(p)] if q != p]
        big = max(sib, default=0)
        if big >= COLLAPSE_MIN_BYTES and mine < big * COLLAPSE_RATIO:
            out[p] = ("cleared", f"{mine:,} B · 정상 판 {big:,} B")
            continue

        # ⑤ 기기 칸 — 누가 받았나
        devices = {str(r.get("device") or "") for r in rs}
        if "" not in devices:
            if me and me in devices:
                out[p] = ("lost", f"기록 기기 {sorted(devices)}")
            elif me:
                out[p] = ("other", ", ".join(sorted(devices)))
            else:
                # 이 기기 별칭을 모르면 「다른 기기 것」이라고 말할 수 없다 — 모른다고 둔다
                out[p] = ("legacy", f"이 기기 별칭 없음 · 기록 기기 {sorted(devices)}")
            continue

        # ⑥ 질의 기반 — 가설일 뿐이다
        if PurePosixPath(p).name.startswith(QUERY_PREFIXES):
            out[p] = ("query", "")
            continue

        out[p] = ("legacy", "")
    return out


def tally(got: dict[str, tuple[str, str]]) -> collections.Counter[str]:
    return collections.Counter(reason for reason, _ in got.values())


# ══════════════════════════════════════════════════════════
# 🆕 2026-09-21 — 경보 수준은 **여기 한 곳**에서 정한다 · 역할을 본다
# ══════════════════════════════════════════════════════════
#: 사본(replica)에서는 볼 것이 아닌 이유. 🚨 사본은 원문으로 파생물을 만들지 않는다 — 받은 파생물로만 돈다 (D-226).
#:    ⛔ 종전에는 역할을 안 봐서, 클론 A 에서 「사람이 볼 것 5,545개」(legacy 5,266 · query 279)가 찍히고
#:       `inventory` 는 같은 줄을 🔴 로 세며 「이 기기에서 쓰려면 다시 받는다」고 안내했다(2026-09-21 사용자 실행).
#:       사본이 수집하면 원문이 두 기기로 갈라진다 — 안내가 D-226 과 정면으로 어긋났다.
#:    ★ `lost` 는 접지 않는다 — **이 기기가 받았다**고 적힌 것이 없으면 역할과 무관하게 유실이다.
#:    ★ 정본(canonical)·역할 없음(CI)은 종전 그대로 — 거기서는 이 목록이 진짜 볼 것이다.
REPLICA_FOLDS: frozenset[str] = frozenset({"legacy", "query"})

#: 수준 → 표시. 🔴 는 종료코드에 든다 · 🟡 는 사람이 본다 · ✅ 는 한 줄로 접는다.
LEVEL_MARK: dict[str, str] = {"red": "🔴", "eyes": "🟡", "ok": "✅"}


def mirror_hint() -> str:
    """사본 안내 끝줄 — 🆕 2026-09-21 (D-256) 읽을 원문이 필요하면 어디서 받는지. doctor·inventory 가 같이 쓴다 (D-99).

    🔄 같은 날 정정 — ⛔ 처음에 「사본은 원문을 쓰지 않는다」고 적었다. D-226 이 막는 것은 **원문으로 파생물을 만드는 것**이지
       원문을 읽는 것이 아니다. 팀장 기기는 원문 거울로 받아 **읽고 미리보기**를 한다 (D-256).
    """
    from collect import env  # noqa: PLC0415

    if env.setting("RAW_MIRROR"):
        return "        ★ 읽을 원문이 필요하면 — uv run python launcher.py raw-mirror-sync (정본 원문 거울 · D-256)"
    return "        ★ 읽을 원문이 필요하면 — 팀장 기기는 원문 거울을 붙인다 (`data-setup` · D-256). 팀원 기기는 받지 않는다"


def role() -> str | None:
    """이 기기 역할 — `derived_manifest.role()` 한 곳에서 읽는다 (D-99).

    🚨 모르는 값(`canonnical`)이면 `role()` 이 멈추는데, **진단은 멈추지 않는다** — 역할 없음(더 많이 보이는 쪽)으로
       돌고, 역할 오타는 `doctor --env` 가 🔴 로 따로 센다. 접는 쪽으로 틀리지 않는다 (D-220).
    """
    from scripts import derived_manifest as dm  # noqa: PLC0415 — 역할의 정본

    try:
        return dm.role()
    except SystemExit:
        return None


def level(reason: str, who: str | None) -> str:
    """이유 하나의 경보 수준 — `"red"` · `"eyes"` · `"ok"`. 🔴 doctor 와 inventory 가 **이 함수만** 읽는다.

    ⛔ 종전에는 수준을 두 도구가 따로 정했다 — 같은 `legacy` 줄을 doctor 는 🟡, inventory 는 🔴 로 찍었다.
       D-253 맥락 4 가 고칠 이유로 든 그 불일치가, 분류만 한 벌이 되고 **색은 두 벌**로 남아 있었다.
    """
    if reason == "lost":
        return "red"
    if REASONS[reason][1]:
        return "ok"
    if who == "replica" and reason in REPLICA_FOLDS:
        return "ok"
    return "eyes"


def levels(got: dict[str, tuple[str, str]], who: str | None) -> collections.Counter[str]:
    """`classify` 결과 → 수준별 개수 (`red`·`eyes`·`ok`)."""
    return collections.Counter(level(reason, who) for reason, _ in got.values())


def needs_eyes(got: dict[str, tuple[str, str]], who: str | None = None) -> int:
    """사람이 볼 것 — 🟡·🔴 인 것의 개수. `who` 를 주면 역할대로 접는다."""
    return sum(1 for reason, _ in got.values() if level(reason, who) != "ok")
