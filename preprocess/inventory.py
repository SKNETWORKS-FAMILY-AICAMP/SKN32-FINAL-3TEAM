"""preprocess/inventory.py — **이 기기**에 무엇이 있나 (기기 축).

  uv run python -m preprocess.inventory

왜 따로인가 — 팀장이 2026-09-09 에 이렇게 물었다:
*"내가 기기를 두 개에서 각각 작업하는데 어떤 기기는 받고 어떤 기기는 안 받고 이런 상황
때문에 헷갈리는데"*

**축이 둘인데 표가 하나였기 때문이다.**

    팀 축   `data/manifest.jsonl`  — **git 으로 공유된다.** 두 기기가 같은 답을 낸다
    기기 축 `data/raw/**`          — **`.gitignore` 다** (D-19). 기기마다 다르다

한 표에 섞으면 「A 기기에서 받은 것」이 B 기기에서 「안 받았다」로 읽힌다.
그래서 `launcher.py status`(팀 축)와 이것(기기 축)을 나눴다.

🚨 이 모듈이 `preprocess/` 에 있는 이유 — `data/raw` 를 읽는 것은 수집·전처리만 할 수 있다
   (D-92 · `RAW_READERS`). `scripts/` 에 두었다가 게이트가 잡았고, 잡힌 덕분에 축이 갈렸다.

🚨 **파일을 열지 않는다.** 이름과 개수만 센다 — 원문을 소비하는 것이 아니다.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib

from collect import missing, store

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.jsonl"

# 폴더 이름이 소스 id 와 다른 것들 — 수집기가 계열로 묶어 저장한다.
# 🔴 **한 소스가 여러 폴더를 쓸 수 있다** (2026-09-10). ⛔ 값이 문자열 하나였을 때
#    `mfds_press` 의 첨부 PDF 107개가 `data/raw/mfds_press_pdf/` 에 따로 있는 것을
#    통째로 못 봤다 — 원장 고유 214 인데 「이 기기 107」로 찍혀 **절반만 있는 것처럼** 보였다.
#    실제로는 214/214 로 완전했다. 🚨 본문은 첨부 PDF 에만 있다 (D-118).
# 🔄 **2026-09-18 — 표를 `collect/store.py` 로 옮겼다** (D-99).
#    ⛔ 같은 매핑이 두 곳에 있었고, `collect` 쪽이 그것을 안 써서 `register` 가
#       `law_go_kr` 파일을 `data/raw/law_go_kr/` 에 넣었다 — 추출기는 `data/raw/law/` 를 본다.
#    ★ 원문 경로를 정하는 것은 `store` 의 일이므로 그쪽이 정본이고, 여기서는 그것을 쓴다.
#      이름(`ALIAS`·`folders`)은 그대로 둔다 — 바깥에 보이는 표면은 안 바꾼다.
ALIAS = store.FAMILY_OF


def folders(source_id: str) -> tuple[str, ...]:
    return store.families(source_id)


def ledger() -> dict[str, set[str]]:
    """소스별 **고유 path 집합**. 🚨 줄 수가 아니다 (D-54).

    ⛔ 종전에는 줄마다 +1 이었다. 원장은 재수집마다 줄이 붙으므로 그 수는 **부풀어 오른다** —
       실측 `mfds_press` 원장 줄 424 · 고유 path 214, `ftc_decisions_body` 16,506 vs 8,253.
       `doctor` 가 바로 위에서 「원장 줄 수를 건수로 쓰지 마라」를 찍는데
       `inventory` 의 팀 축이 그 줄 수였다.
    """
    got: dict[str, set[str]] = collections.defaultdict(set)
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            got[r.get("source_id", "")].add(r.get("path", ""))
    return got


def on_disk(source_id: str) -> int:
    """파일 수만 센다. 🚨 **열지 않는다.**

    ⛔ `rglob("*")` + `is_file()` 로 짰다가 **2분을 넘겨 죽었다**(2026-09-09).
       `data/raw` 가 384MB 이고 마운트된 파일시스템이라 파일마다 `stat` 이 붙는다.
       같은 날 `.venv` 팽창으로 게이트가 3분이 된 것과 **같은 부류**다 —
       걷는 비용을 안 재고 편한 API 를 썼다. `os.walk` 는 이름만 받아 온다.
    """
    n = 0
    for name in folders(source_id):
        d = RAW / name
        if d.exists():
            n += sum(len(files) for _, _, files in os.walk(d))
    return n


def _rows() -> list[dict]:
    """원장 행 전부 — 결손 가르기(`collect/missing.py`)가 기기 칸·sha·크기를 본다. 🚨 깨진 줄은 건너뛴다(`ledger` 와 같다)."""
    out: list[dict] = []
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def missing_paths(paths: set[str]) -> list[str]:
    """원장에 있는데 **이 기기 디스크에 없는** path. 🚨 소스 단위 0/비0 이 아니라 path 단위다.

    ⛔ 종전 분류는 「파일이 하나라도 있으면 둘 다 있음」이었다. 그래서
       `mfds_hf_ingredient` 가 **10개 중 9개가 없는데** 「둘 다 있음」으로 갔다.
    """
    return sorted(p for p in paths if p and not (ROOT / p.replace("\\", "/")).exists())


def listed(sources: dict, led: dict[str, set[str]]) -> dict[str, str]:
    """표에 올릴 소스 → 상태. `collect` 소스 **+ 원장에 행이 있는 소스 전부**(상태 무관).

    🆕 2026-09-20 (D-254 · 감사 §2 inventory) — ⛔ 종전에는 `status == collect` 만 봤다.
       `manual`(AI Hub 를 사람이 받아 register)·`hold` 소스의 원장 행이 **표에서 통째로 빠졌다** —
       받은 것이 있는데 안 보이는 것이 이 표가 막으려던 바로 그 모양이다.
    🚨 원장에만 있고 레지스트리에 없는 id 는 `미등재` 로 올린다 — 숨기지 않는다 (D-220).
    """
    out = {
        k: str(v.get("status"))
        for k, v in sources.items()
        if isinstance(v, dict) and v.get("status") == "collect"
    }
    for k, paths in led.items():
        if k and paths and k not in out:
            v = sources.get(k)
            out[k] = str(v.get("status") or "상태없음") if isinstance(v, dict) else "미등재"
    return out


def main() -> int:
    import yaml  # noqa: PLC0415 — 레지스트리를 읽는 유일한 자리다

    reg = yaml.safe_load((ROOT / "data_sources.yaml").read_text(encoding="utf-8"))["sources"]
    led = ledger()
    src = listed(reg, led)
    # 🆕 D-253 — 없는 것을 **왜 없는지**로 가른다. doctor 와 같은 함수다 (D-99 · `collect/missing.py`).
    #    ⛔ 종전에는 없는 것을 전부 🔴 「일부만 받은 것」으로 찍었다 — 같은 53개를 doctor 는 🟡 로 찍어
    #       두 도구가 같은 결손에 다른 경보를 냈다. 실측 53개 중 36개는 정책 제외·옮긴 흔적이었다.
    why = missing.classify(_rows())
    # 🆕 2026-09-21 — 경보 수준은 `missing.level()` 한 곳이 정하고 역할을 본다 (doctor 와 같은 색 · D-99).
    who = missing.role()

    # 한 폴더를 여러 소스가 쓰는지 먼저 센다
    shared: collections.Counter = collections.Counter(f for k in src for f in folders(k))

    both, only_ledger, only_disk, neither = [], [], [], []
    partial: list[tuple[str, int, int, bool]] = []
    print(f"{'소스':26}{'원장(고유)':>11}{'이 기기':>8}{'🔴없음':>8}")
    for k in sorted(src):
        paths = led.get(k, set())
        n_led, n_disk = len(paths), on_disk(k)
        gone = missing_paths(paths)
        aliased = any(shared[f] > 1 for f in folders(k)) and not n_led
        bucket = (
            both
            if (n_led and n_disk)
            else only_ledger
            if n_led
            else neither
            if (aliased or not n_disk)
            else only_disk
        )
        bucket.append(k)
        mark = ""
        if gone:
            # 🔴 **일부만 없는 것**을 종전에는 「둘 다 있음」으로 삼켰다 (2026-09-10).
            # 🔄 D-253 — 정상으로 설명되는 것은 🔴 로 안 센다. 설명 안 되는 것만 남긴다.
            # 🔄 2026-09-21 — 수준을 `missing.level()` 에서 받는다. ⛔ 종전에는 「정상이 아니면 🔴」로 여기서 따로 정해
            #    doctor(🟡)와 색이 갈렸고, **하나도 없는 소스**는 이유를 안 보고 「다른 기기에서 받았다 — 다시 받는다」로
            #    🔴 를 찍었다 — 사본(클론 A)에서 수집을 권하는 안내였다 (D-226).
            reasons = collections.Counter(
                why.get(p.replace("\\", "/"), ("legacy", ""))[0] for p in gone
            )
            lv = collections.Counter()
            for r, n in reasons.items():
                lv[missing.level(r, who)] += n
            eyes = lv["red"] + lv["eyes"]
            told = " · ".join(f"{r} {n}" for r, n in reasons.most_common())
            whole = "하나도 없다" if not n_disk else f"{len(gone)}/{n_led} 이 없다"
            if eyes:
                partial.append((k, eyes, n_led, bool(lv["red"])))
                head = missing.LEVEL_MARK["red" if lv["red"] else "eyes"]
                mark = f"  {head} **{whole}** — 볼 것 {eyes} ({told})"
            elif who == "replica" and any(r in missing.REPLICA_FOLDS for r in reasons):
                mark = f"  ✅ {whole} — 사본은 원문으로 파생물을 만들지 않는다 ({told})"
            else:
                mark = f"  ✅ {whole} — 전부 설명됨 ({told})"
        elif n_disk and not n_led:
            # 🚨 **계열을 공유하는 소스는 오탐이다** (2026-09-09 실측).
            #    `ftc_decisions`·`ftc_decisions_api`·`ftc_decisions_body` 가 한 폴더(`ftc`)를
            #    쓰므로, 본문 수집기가 채운 파일이 나머지 둘에도 잡힌다.
            #    오탐으로 시작한 검사는 곧 꺼진다 — 이름을 붙여 구분한다 (D-167).
            mark = (
                "  ⤷ 계열 공유 폴더"
                if any(shared[f] > 1 for f in folders(k))
                else "  🔴 원장에 없는데 파일이 있다 — 원장을 확인한다"
            )
        if src[k] != "collect":
            mark += f"  [{src[k]}]"  # 수집기 밖(manual·hold·미등재) — 원장에 행이 있어 올렸다
        print(f"  {k:24}{n_led or '—':>11}{n_disk or '—':>8}{len(gone) or '—':>8}{mark}")

    print()
    print(
        f"  둘 다 있음 {len(both)} · 원장만 {len(only_ledger)} · 파일만 {len(only_disk)} "
        f"· 둘 다 없음 {len(neither)}"
    )
    # 🔄 2026-09-21 — 「원장에만 있는 소스」도 이유로 가른다 — 아래 「볼 것」 목록에 함께 든다.
    #    ⛔ 종전에는 여기서 따로 🔴 「이 기기에서 쓰려면 다시 받는다」를 찍었다(이유를 안 봤다).
    if only_ledger and who == "replica":
        print(
            f"\n✅ **원장에만 있는 소스 {len(only_ledger)}개** — 사본은 원문으로 파생물을 만들지 않는다 (D-226)"
        )
        print("   🚨 이 기기에서 수집하지 않는다 — 원문은 정본 한 곳에 모인다.")
        print(
            "      「원장에 있다」는 「이 기기에 있다」가 아니다 (D-19). 볼 사람은 정본(클론 B)이다."
        )
        print(missing.mirror_hint())
    if only_disk:
        print("\n🔴 **원장에 없는데 파일이 있다** — 규약 3 이 지켜지지 않았거나 원장이 밀렸다")
        for k in only_disk:
            print(f"   {k}")
    if partial:
        head = missing.LEVEL_MARK["red" if any(r for *_, r in partial) else "eyes"]
        print(f"\n{head} **없는 것 중 설명이 안 되는 것** — 소스 단위로는 「있다」로 보일 수 있다")
        for k, g, n, red in partial:
            print(f"   {k:26} {g}/{n} 볼 것" + ("  🔴 이 기기가 받았는데 없다" if red else ""))
        print("   🚨 종전 분류는 파일이 하나라도 있으면 「둘 다 있음」이었다 (D-160).")
        print("   → 이유와 경로: uv run python launcher.py doctor   (D-253 · 같은 분류 · 같은 색)")
    if not only_disk and not partial:
        print("  ✅ 원장과 이 기기 사이에 볼 것이 없다")

    # 🚨 **세 번째 축은 여기서 안 잰다** — 「있다」는 「최신이다」가 아니다 (D-177).
    #    ⛔ 실측 — `mfds_hf_ingredient_board` 672개 중 **662개가 팀 최신판이 아닌데**
    #       이 표는 전부 「있음」으로 찍는다. 그 축은 해시를 봐야 갈린다.
    print(
        "\n⬜ **낡음은 여기서 안 본다** — 「이 기기에 있다」는 「이 기기 것이 최신이다」가 아니다."
    )
    print("   uv run python scripts/doctor.py --data --hash   ← 그 축은 여기서 잰다 (D-177)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
