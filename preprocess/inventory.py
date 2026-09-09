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

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "manifest.jsonl"

# 폴더 이름이 소스 id 와 다른 것들 — 수집기가 계열로 묶어 저장한다
ALIAS = {
    "mfds_hf_ingredient_board": "mfds_hf_board",
    "ftc_decisions_body": "ftc",
    "ftc_decisions_api": "ftc",
    "ftc_decisions": "ftc",
    "law_go_kr": "law",
}


def ledger() -> collections.Counter:
    c: collections.Counter = collections.Counter()
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    c[json.loads(line).get("source_id", "")] += 1
                except json.JSONDecodeError:
                    continue
    return c


def on_disk(source_id: str) -> int:
    """파일 수만 센다. 🚨 **열지 않는다.**

    ⛔ `rglob("*")` + `is_file()` 로 짰다가 **2분을 넘겨 죽었다**(2026-09-09).
       `data/raw` 가 384MB 이고 마운트된 파일시스템이라 파일마다 `stat` 이 붙는다.
       같은 날 `.venv` 팽창으로 게이트가 3분이 된 것과 **같은 부류**다 —
       걷는 비용을 안 재고 편한 API 를 썼다. `os.walk` 는 이름만 받아 온다.
    """
    d = RAW / ALIAS.get(source_id, source_id)
    if not d.exists():
        d = RAW / source_id
    if not d.exists():
        return 0
    return sum(len(files) for _, _, files in os.walk(d))


def main() -> int:
    import yaml  # noqa: PLC0415 — 레지스트리를 읽는 유일한 자리다

    src = yaml.safe_load((ROOT / "data_sources.yaml").read_text(encoding="utf-8"))["sources"]
    src = {k: v for k, v in src.items() if isinstance(v, dict) and v.get("status") == "collect"}
    led = ledger()

    # 한 폴더를 여러 소스가 쓰는지 먼저 센다
    shared: collections.Counter = collections.Counter(ALIAS.get(k, k) for k in src)

    both, only_ledger, only_disk, neither = [], [], [], []
    print(f"{'소스':28}{'원장(팀)':>10}{'이 기기':>10}")
    for k in sorted(src):
        n_led, n_disk = led.get(k, 0), on_disk(k)
        aliased = shared[ALIAS.get(k, k)] > 1 and not n_led
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
        if n_led and not n_disk:
            mark = "  🔴 **다른 기기에서 받았다 — 이 기기엔 없다**"
        elif n_disk and not n_led:
            # 🚨 **계열을 공유하는 소스는 오탐이다** (2026-09-09 실측).
            #    `ftc_decisions`·`ftc_decisions_api`·`ftc_decisions_body` 가 한 폴더(`ftc`)를
            #    쓰므로, 본문 수집기가 채운 파일이 나머지 둘에도 잡힌다.
            #    오탐으로 시작한 검사는 곧 꺼진다 — 이름을 붙여 구분한다 (D-167).
            mark = (
                "  ⤷ 계열 공유 폴더"
                if shared[ALIAS.get(k, k)] > 1
                else "  🔴 원장에 없는데 파일이 있다 — 원장을 확인한다"
            )
        print(f"  {k:26}{n_led or '—':>10}{n_disk or '—':>10}{mark}")

    print()
    print(
        f"  둘 다 있음 {len(both)} · 원장만 {len(only_ledger)} · 파일만 {len(only_disk)} "
        f"· 둘 다 없음 {len(neither)}"
    )
    if only_ledger:
        print("\n🔴 **다른 기기에서 받은 것 — 이 기기에서 쓰려면 다시 받는다**")
        for k in only_ledger:
            print(f"   {k}")
        print("   🚨 원장은 git 으로 공유되지만 원문은 `.gitignore` 다 (D-19).")
        print("      「원장에 있다」는 「이 기기에 있다」가 아니다.")
    if only_disk:
        print("\n🔴 **원장에 없는데 파일이 있다** — 규약 3 이 지켜지지 않았거나 원장이 밀렸다")
        for k in only_disk:
            print(f"   {k}")
    if not only_ledger and not only_disk:
        print("  ✅ 원장과 이 기기가 일치한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
