"""data_status.py — 데이터 현황판을 **생성한다** (D-54 · D-90).

  uv run python -m scripts.data_status            # 화면에 낸다
  uv run python -m scripts.data_status --write    # docs/03_데이터/데이터현황판.md

왜 생성물인가 — 「무엇을 쓰기로 했고 무엇을 안 쓰기로 했나」를 손으로 적으면 **반드시 갈린다.**
2026-09-03 판 현황판이 그렇게 낡았다. 여기서 세는 값은 전부 레지스트리·원장·파일에서 읽는다.

🚨 **DB 는 보지 않는다.** 도커가 없는 기기에서도 돌아야 하고, DB 현황은 `launcher.py load`
   와 `/health` 가 낸다. 축이 다르면 파일도 다르다 (D-89).

🚨 **이 현황판은 「팀 축」이다 — 이 기기에 파일이 있는지는 보지 않는다.**
   수집 원장(`data/manifest.jsonl`)은 **git 으로 공유**되지만 원문은 `.gitignore` 라
   기기마다 다르다(D-19). 두 축을 한 표에 섞으면 「A 기기에서는 받았는데 B 기기에는 없다」가
   「안 받았다」로 읽힌다 — 팀장이 2026-09-09 에 정확히 그것으로 헷갈렸다.

   팀 축   `launcher.py status`     ← 이 파일. 원장 기준. **두 기기가 같은 답을 낸다**
   기기 축 `launcher.py inventory`  ← preprocess/inventory.py. 이 기기의 실물 + 원장과의 차이

🚨 그리고 `scripts/` 는 원문 디렉터리를 읽지 않는다 (D-92 — 소비 경로는 등급 디렉터리와
   derived 만 읽는다). 게이트가 그것을 잡았고, 잡힌 덕분에 축이 갈렸다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"


def _registry() -> dict:
    return yaml.safe_load((ROOT / "data_sources.yaml").read_text(encoding="utf-8"))


def _manifest() -> collections.Counter:
    c: collections.Counter = collections.Counter()
    p = ROOT / "data" / "manifest.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    c[json.loads(line).get("source_id", "")] += 1
                except json.JSONDecodeError:
                    continue
    return c


def _decisions_by_source(keys: set[str]) -> dict[str, list[str]]:
    """원장 본문에서 **소스 이름이 나오는 결정**을 모은다 (2026-09-14).

    🚨 **「이 소스를 다룬 결정」이지 「이 소스를 판정한 결정」이 아니다.**
       `dmap` 과 같은 성격이다 — *「세는 것은 인용이지 준수가 아니다」*.

    ★ **실측 (표본 28건 · `mfds_press` 19 + `mfds_casebook` 9)** — 판정 **19** · 단순 언급 **9**
      → **정밀도 68%**. 언급 9건의 성격은 재료 나열·비유·계기·파일명이다.

    ⛔ **노이즈 필터를 만들어 재 봤더니 손해였다.** 명령줄(`launcher.py …`)과
       파일경로(`preprocess/<id>.py`)를 걸렀더니 정밀도는 74%→71% · 56%→57% 로 **안 오르고**
       판정을 셋 놓쳤다 — **D-136**(`launcher.py probe mfds_press` = robots 확인 판정) ·
       **D-167**(`preprocess/mfds_press.py 를 만든다` = 결정문 본문) · **D-158**(같은 꼴).
       🚨 **파일명·명령줄에 이름이 나오는 것이 오히려 판정의 표시였다.** 그래서 거르지 않는다.

    ⬜ **여기서 안 보는 것** (D-188) — 이름이 안 나오는 결정. 소스를 다루면서 이름을
       안 적은 결정은 0건으로 보인다. `dmap` 의 「D 번호를 안 적었다」 갈래와 같은 자리다.
    """
    from scripts.decision_map import load_ledger  # noqa: PLC0415 — 원장 파서를 두 벌 두지 않는다
    from scripts.extract_rationale import ALIAS  # noqa: PLC0415 — id ↔ 키의 정본 (D-100)

    decisions, _ = load_ledger()
    hit: dict[str, list[str]] = {}
    for key in sorted(keys):
        names = {key, *ALIAS.get(key, [])}
        names = {n for n in names if len(n) > 4}  # 🚨 짧은 이름은 아무 데나 걸린다
        found = [d for d, v in decisions.items() if any(n in v.get("body", "") for n in names)]
        if found:
            hit[key] = sorted(found, key=lambda x: int(x[2:]))
    return hit


def build() -> str:
    reg = _registry()
    src = {k: v for k, v in reg["sources"].items() if isinstance(v, dict)}
    man = _manifest()
    out: list[str] = []
    w = out.append

    w("# 데이터 현황판 — 무엇을 쓰기로 했고 무엇을 안 쓰기로 했나")
    w("")
    w("> 🚨 **생성물이다. 손으로 고치지 않는다** — `python -m scripts.data_status --write`.")
    w("> 값은 `data_sources.yaml`(레지스트리) · `data/manifest.jsonl`(수집 원장) ·")
    w("> `data/derived`(파생물)에서 읽는다. 손으로 적으면 갈린다 (D-54 · D-90).")
    w("> 🚨 DB 적재 현황은 여기가 아니라 `launcher.py load` 와 `/health` 가 낸다 (D-89).")
    w("")

    by_status: dict[str, list[str]] = collections.defaultdict(list)
    for k, v in src.items():
        by_status[v.get("status", "?")].append(k)
    na = [x for x in (reg.get("not_adopted") or []) if isinstance(x, dict)]
    blocked = [x for x in (reg["sources"].get("blocked") or []) if isinstance(x, dict)]

    w("## 한눈에")
    w("")
    w("| 갈래 | 건 | 뜻 |")
    w("|---|:-:|---|")
    w(f"| ✅ **쓴다** (`collect`) | {len(by_status['collect'])} | 거버넌스를 지나 수집 대상 |")
    w(
        f"| ✋ **수기만** (`manual`) | {len(by_status['manual'])} | 자동 접근이 약관 위반 — 사람이 본다 |"
    )
    w(
        f"| ⏸ **보류** (`hold`) | {len(by_status['hold'])} | 판정이 안 끝났다 — **지금은 안 받는다** |"
    )
    w(f"| ❌ **안 쓴다** (`not_adopted`) | {len(na)} | 조건·도메인·대체재 때문에 내렸다 |")
    w(f"| ⛔ **배제** (`blocked`) | {len(blocked)} | G1 — 탐침도 하지 않는다 |")
    w("")

    w("## ✅ 쓴다 — 수집 상태")
    w("")
    w("| 소스 | 층 | 등급 | 가치 | 원장 | `collected_at` | |")
    w("|---|---|:-:|:-:|--:|---|---|")
    done, todo = [], []
    for k in sorted(by_status["collect"]):
        v = src[k]
        n_man = man.get(k, 0)
        got = bool(n_man)
        (done if got else todo).append(k)
        # 🚨 원장에 없는데 `collected_at` 이 있으면 어긋난 것이다 — 사람이 적는 칸이라 그렇다
        gap = (
            " 🔴 원장에 없는데 collected_at 이 있다"
            if (not n_man and v.get("collected_at"))
            else ""
        )
        w(
            f"| {'✅' if got else '⬜'} `{k}` | {v.get('layer', '')} | {v.get('grade')} "
            f"| {v.get('value')} | {n_man or '—'} | {v.get('collected_at') or '—'} |{gap} |"
        )
    w("")
    w(f"**원장에 오른 것 {len(done)} · 아직 안 받은 것 {len(todo)}**")
    w("")
    w(
        "🚨 「원장에 있다」는 **팀 누군가가 받았다**는 뜻이지 **이 기기에 있다**는 뜻이 아니다. "
        "이 기기의 실물은 `launcher.py inventory` 가 낸다."
    )
    w("")

    w("### 층별 — 판정 파이프라인이 서 있는가")
    w("")
    w("| 층 | 원장에 오름 | 안 받음 |")
    w("|---|--:|---|")
    layers: dict[str, list[list[str]]] = collections.defaultdict(lambda: [[], []])
    for k in by_status["collect"]:
        lay = (src[k].get("layer") or "?").split("·")[0].strip()
        layers[lay][0 if k in done else 1].append(k)
    for lay in sorted(layers):
        got, miss = layers[lay]
        w(f"| {lay} | {len(got)} | {', '.join(f'`{m}`' for m in sorted(miss)) or '—'} |")
    w("")

    groups = (
        ("⏸ 보류 — 판정이 안 끝났다", by_status["hold"], "note"),
        ("✋ 수기만 — 자동 접근이 약관 위반", by_status["manual"], "caution"),
    )
    for title, keys, why in groups:
        w(f"## {title} ({len(keys)})")
        w("")
        w("| 소스 | 등급 | 사유 |")
        w("|---|:-:|---|")
        for k in sorted(keys):
            v = src[k]
            reason = str(v.get(why) or v.get("caution") or v.get("note") or "")[:110]
            w(f"| `{k}` | {v.get('grade')} | {reason} |")
        w("")

    w(f"## ❌ 안 쓰기로 한 것 ({len(na)})")
    w("")
    w("🚨 **가치가 없어서가 아니다.** 조건이 우리와 안 맞거나 더 나은 대체재가 있어서다 (D-110).")
    w("")
    w("| 소스 | 등급 | 사유 |")
    w("|---|:-:|---|")
    for x in na:
        reason = str(x.get("reason"))[:150]
        w(f"| `{x.get('key')}` {x.get('name', '')} | {x.get('grade')} | {reason} |")
    w("")

    w(f"## ⛔ 배제 ({len(blocked)}) — G1")
    w("")
    w("🚨 **받아서 지우는 것과 받지 않는 것은 다르다.** 탐침도 하지 않는다.")
    w("")
    w("| 대상 | 사유 |")
    w("|---|---|")
    for x in blocked:
        w(f"| {x.get('name')} | {str(x.get('reason'))[:130]} |")
    w("")

    w("## 📜 판정 이력 — 이 소스를 다룬 결정")
    w("")
    w("> 🚨 **「다룬」이지 「판정한」이 아니다.** 원장 본문에 이름이 나온 결정을 전부 냅니다 —")
    w("> 실측 표본 28건에서 **판정 19 · 단순 언급 9(정밀도 68%)** 였습니다. 거르지 않는 이유는")
    w("> `scripts/data_status.py` 의 `_decisions_by_source()` docstring 에 적혀 있습니다.")
    w(
        "> ⛔ **매트릭스(`data.js`)가 인용한 D 와 다릅니다.** 매트릭스는 「등재 시점의 판정」을 들고,"
    )
    w("> 그 뒤에 바뀐 판정은 원장에만 쌓입니다 — 그 차이를 보이게 하는 것이 이 절의 목적입니다.")
    w("")
    hit = _decisions_by_source(set(src) | {str(x.get("key")) for x in na if x.get("key")})
    w("| 소스 | 건 | 이 소스를 다룬 결정 |")
    w("|---|--:|---|")
    for k in sorted(hit, key=lambda x: (-len(hit[x]), x)):
        w(f"| `{k}` | {len(hit[k])} | {' · '.join(hit[k])} |")
    w("")
    none = sorted((set(src) | {str(x.get("key")) for x in na if x.get("key")}) - set(hit))
    w(
        f"🔴 **원장에 이름이 한 번도 안 나온 소스 {len(none)}건** — 결함이 아니라 "
        "**「아직 어떤 결정도 이 소스를 다루지 않았다」**는 사실입니다."
    )
    w("")
    w(f"> {' · '.join('`' + k + '`' for k in none)}")
    w("")

    w("## 파생물 — 원문이 무엇이 됐나")
    w("")
    w("| 산출물 | 크기 |")
    w("|---|--:|")
    if DERIVED.exists():
        for p in sorted(DERIVED.rglob("*.jsonl")) + sorted(DERIVED.rglob("*.json")):
            # 🔴 **`as_posix()` 가 없으면 윈도우에서 `data\\derived\\…` 로 나온다** (2026-09-14 실측).
            #    같은 명령이 기기마다 다른 생성물을 내면 diff 가 매번 뜨고, 그러면 아무도 안 본다
            #    (D-19 — `data/` 는 기기마다 다르지만 **이 표는 파일 목록이라 같아야 한다**).
            w(f"| `{p.relative_to(ROOT).as_posix()}` | {p.stat().st_size:,} B |")
    # 🚨 끝의 빈 줄을 턴다 — 안 그러면 `end-of-file-fixer` 가 **돌릴 때마다** 파일을 고쳐
    #    커밋이 중단된다(2026-09-09 실제로 걸렸다). 생성기가 훅과 싸우면 둘 중 하나를 끄게 된다.
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="데이터 현황판 생성")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    text = build()
    if args.write:
        out = ROOT / "docs" / "03_데이터" / "데이터현황판.md"
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"💾 {out.relative_to(ROOT)} ({len(text):,}자)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
