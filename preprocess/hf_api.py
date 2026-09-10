"""preprocess/hf_api.py — 건기식 **API 2종** → 2층 적법라벨 (D-156).

  uv run python -m preprocess.hf_api --verify     # 세고 대조만 한다
  uv run python -m preprocess.hf_api --dump       # 🔴 마스킹 정책이 있어야 한다

원천 둘 —
  `mfds_hf_ingredient`  I-0040 기능성 원료인정 현황   873행 (`FNCLTY_CN`)
  `mfds_hf_individual`  I-0050 개별인정형 정보        547행 (`PRIMARY_FNCLTY`)

왜 있는가 — 둘 다 **받아 두고 읽는 코드가 없었다**(2026-09-09 확인). 2층 적법라벨은
골든셋의 적법 표본 118건을 지탱하는 자리인데, 인정받은 문구 수천 건이 놀고 있었다.

🚨 **셋이 겹친다 — 인정번호로 합친다** (레지스트리 caution 이 예고한 자리).
   ⛔ 처음에 **원문 그대로** 비교해 「교집합 0」을 얻었다. 표기가 다를 뿐이었다 —
      API 는 `2019-20`, 게시판은 `제2019-20호(2019.08.13)`. **D-117 그대로다:
      매칭은 정규화문, 보관은 원문.** 정규화 뒤 실측(2026-09-09) —

        ingredient 768 · individual 444 · board(mfds_hf) 465   고유 인정번호
        ing∩ind 433 · ing∩board 457 · ind∩board 400
        합집합 **781** — board 가 이미 465 를 덮으므로 **새로 얻는 것은 316**

   🚨 그래서 「1,420건이 놀고 있다」는 말은 틀렸다. 중복을 빼면 316 이다.
      **정본을 무엇으로 할지는 판정 사항이라 여기서 고르지 않는다** — 행마다
      `sources` 에 어느 원천이 그 인정번호를 가졌는지 적어 두고 넘긴다 (D-153).

🔴 **인정번호와 기능성문구는 마스킹을 지나도 한 글자도 안 바뀌어야 한다** (D-156).
   `mfds_hf.py` 와 같은 이유다 — 인정번호가 지워지면 「적법하다는 근거」가 사라진
   「적법」 딱지만 남는다. `--dump` 마다 재고, 어긋나면 **멈춘다.**
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

from collect import store
from preprocess import mask

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# 🚨 담는 필드만 적는다. 여기 없는 열은 **아예 안 담는다** (D-159) —
#    BSSH_NM(업체명) · ADDR(주소) · INDUTY_NM(업종) 이 그것이다.
KEEP: dict[str, tuple[str, ...]] = {
    "mfds_hf_ingredient": (
        "HF_FNCLTY_MTRAL_RCOGN_NO",
        "FNCLTY_CN",
        "APLC_RAWMTRL_NM",
        "DAY_INTK_CN",
        "IFTKN_ATNT_MATR_CN",
        "PRMS_DT",
    ),
    "mfds_hf_individual": (
        "HF_FNCLTY_MTRAL_RCOGN_NO",
        "PRIMARY_FNCLTY",
        "RAWMTRL_NM",
        "DAY_INTK_LOWLIMIT",
        "DAY_INTK_HIGHLIMIT",
        "WT_UNIT",
        "IFTKN_ATNT_MATR_CN",
    ),
}
PHRASE = {"mfds_hf_ingredient": "FNCLTY_CN", "mfds_hf_individual": "PRIMARY_FNCLTY"}
RCOGN = "HF_FNCLTY_MTRAL_RCOGN_NO"
DIRS = {"mfds_hf_ingredient": "mfds_hf_ingredient", "mfds_hf_individual": "mfds_hf_individual"}

_KEY = re.compile(r"(\d{4})\s*-\s*(\d+)")


def rcogn_key(value: object) -> str | None:
    """인정번호의 **정규화문**. 보관은 원문으로 한다 (D-117)."""
    m = _KEY.search(str(value or ""))
    return f"{m.group(1)}-{int(m.group(2))}" if m else None


def _records(directory: str) -> list[dict]:
    """응답 JSON 안의 레코드 배열을 꺼낸다. 껍데기 이름이 서비스마다 다르다."""

    def dig(x: object) -> list[dict] | None:
        if isinstance(x, dict):
            for v in x.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
                found = dig(v)
                if found is not None:
                    return found
        return None

    d = RAW / directory
    # 🔴 **디렉터리가 없어도 glob 은 예외를 안 낸다** — 빈 이터레이터를 준다 (2026-09-10).
    #    ⛔ 그래서 원문을 안 받았거나 폴더 이름이 바뀌면 「0행」을 찍고 **성공으로 끝났다.**
    #       원장에는 수가 적혀 있는데 산출물만 조용히 비는, D-149 와 같은 모양이다.
    if not d.exists():
        raise SystemExit(
            f"🔴 {d} 가 없다 — 이 원천의 원문을 이 기기에서 아직 안 받았다.\n"
            f"  먼저: uv run python launcher.py collect {directory} --use U1\n"
            "  🚨 「0행」을 성공으로 찍지 않는다 (D-72)."
        )
    files = store.current_files(d, "*.json")
    if not files:
        raise SystemExit(f"🔴 {d} 에 json 이 한 개도 없다 — 수집이 비었다.")
    out: list[dict] = []
    for p in files:
        got = dig(json.loads(p.read_text(encoding="utf-8")))
        if got:
            out += got
    if not out:
        raise SystemExit(
            f"🔴 {d} 의 파일 {len(files)}개를 읽었는데 **레코드가 0** 이다.\n"
            "  🚨 응답 껍데기가 바뀌어 `dig()` 가 엉뚱한 배열을 집었을 수 있다 — 파일을 열어 본다."
        )
    return out


def board_keys() -> set[str]:
    """`mfds_hf.py` 가 이미 뽑아 놓은 게시판 465건의 인정번호."""
    p = ROOT / "data" / "derived" / "mfds_hf_labels.jsonl"
    if not p.exists():
        return set()
    keys = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            k = rcogn_key(json.loads(line).get("인정번호"))
            if k:
                keys.add(k)
    return keys


def collect_rows(source: str) -> list[dict]:
    rows = []
    for r in _records(DIRS[source]):
        key = rcogn_key(r.get(RCOGN))
        rows.append(
            {
                "원천": source,
                "인정번호": (r.get(RCOGN) or "").strip(),  # 🚨 원문 보관
                "인정번호_정규화": key,
                **{f: (r.get(f) or "").strip() for f in KEEP[source] if f != RCOGN},
            }
        )
    return rows


def _check_intact(rows: list[dict], source: str) -> None:
    """마스킹이 인정번호·기능성문구를 건드리면 **멈춘다** (D-156)."""
    field = PHRASE[source]
    hurt = []
    for r in rows:
        for f in ("인정번호", field):
            before = r.get(f, "")
            if before and mask.apply_policy(before, "", source) != before:
                hurt.append((f, before[:40]))
    if hurt:
        print(
            f"🚨 마스킹이 {source} 의 판정 재료를 건드렸다 — {len(hurt)}건 (D-156)", file=sys.stderr
        )
        for f, v in hurt[:5]:
            print(f"   {f}: {v!r}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="건기식 API 2종 → 2층 적법라벨")
    ap.add_argument("--dump", action="store_true", help="data/derived/hf_api_labels.jsonl 로 쓴다")
    ap.add_argument("--verify", action="store_true", help="세고 대조만 한다")
    args = ap.parse_args()

    all_rows: list[dict] = []
    keys: dict[str, set[str]] = {}
    for source in KEEP:
        rows = collect_rows(source)
        keys[source] = {r["인정번호_정규화"] for r in rows if r["인정번호_정규화"]}
        phrase = sum(1 for r in rows if r.get(PHRASE[source]))
        print(
            f"  {source:22} 행 {len(rows):>4} · 고유 인정번호 {len(keys[source]):>4} · 문구 {phrase:>4}"
        )
        all_rows += rows

    bk = board_keys()
    ing, ind = keys["mfds_hf_ingredient"], keys["mfds_hf_individual"]
    union = ing | ind | bk
    print(f"\n  게시판(mfds_hf) 고유 인정번호 {len(bk)}")
    print(f"  ing∩ind {len(ing & ind)} · ing∩board {len(ing & bk)} · ind∩board {len(ind & bk)}")
    print(
        f"  합집합 {len(union)} — 게시판이 덮는 {len(bk)} 를 빼면 **새로 얻는 것 {len(union - bk)}**"
    )

    if args.verify:
        return 0

    for source in KEEP:
        _check_intact([r for r in all_rows if r["원천"] == source], source)
    print("  ✅ 인정번호·기능성문구 훼손 0 (D-156)")

    if args.dump:
        out = store.derived_dir(".") / "hf_api_labels.jsonl"
        seen: dict[str, list[str]] = {}
        for r in all_rows:
            k = r["인정번호_정규화"]
            if k:
                seen.setdefault(k, []).append(r["원천"])
        with out.open("w", encoding="utf-8") as f:
            for r in all_rows:
                k = r["인정번호_정규화"]
                r["층"] = "2층 적법라벨"
                r["지위"] = "인정"
                # 🚨 정본을 고르지 않는다 — 어느 원천이 이 인정번호를 가졌는지만 적는다
                r["sources"] = sorted(set(seen.get(k, []) + (["board"] if k in bk else [])))
                f.write(json.dumps(store.stamp(r, r["원천"]), ensure_ascii=False) + "\n")
        print(f"  💾 {len(all_rows)}행 → {out.relative_to(ROOT)}")
        print("  🚨 정본은 고르지 않았다 — `sources` 가 겹침을 그대로 들고 있다 (D-153).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
