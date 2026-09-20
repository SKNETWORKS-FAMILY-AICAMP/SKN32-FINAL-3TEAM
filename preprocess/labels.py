"""preprocess/labels.py — **사람이 붙인 라벨을 읽는 유일한 자리** (D-99 · D-172).

  uv run python -m preprocess.labels          # 무엇이 들어오는지 본다

──────────────────────────────────────────────────────────────
🔴 **왜 생겼나 — 붙인 라벨이 아무 곳에도 닿지 않았다** (2026-09-17 실측).

    data/derived/labels/오한빈.jsonl   248행 (유형 163 · 범위밖 85)
    preprocess/split.py 의 입력        ftc_layer1_phrases · mfds_casebook_labels · mfds_hf_labels

**셋 어디에도 labels/ 가 없다.** golden.jsonl 6,626행의 provenance 도
`ftc_decisions_body 5,233 · mfds_hf_ingredient_board 1,080 · mfds_casebook 313` 이라
해설서가 **0행**이다. 즉 사람이 이틀 붙인 것이 파이프라인에 **들어갈 문이 없었다.**
「남은것」 문서의 ①「평가셋 6종이 비었다」가 바로 이 자리다.

──────────────────────────────────────────────────────────────
🚨 **여기가 라벨을 읽는 유일한 자리다** (D-99).

`scripts/label_merge.py` 가 같은 읽기를 이미 갖고 있었다. 두 번째로 쓰게 됐으므로
합친다 — 키 만들기·라벨 꺼내기·파일 읽기는 이 모듈이 정본이고 `label_merge` 는 이것을 쓴다.

──────────────────────────────────────────────────────────────
🔴 **「범위 밖」 85행은 음성 표본으로 쓰지 않는다** (fail-closed · D-72).

붙이는 사람이 「범위밖」으로 찍은 것은 **「별표1 여덟 유형 어디에도 안 들어간다」**이지
**「적법하다」가 아니다.** 해설서는 심의에서 **삭제 판정**을 받은 문구를 모은 것이라
광고물 단위로는 문제가 있었던 문장이다 (D-240 초안 · D-237).

⛔ 음성으로 넣으면 Precision 이 **낙관적으로** 나온다 — 「위반이 아닌 것을 위반이라 했다」로
   세는데 실제로는 위반이었을 수 있다. 수치가 한 번 나가면 되돌리기 어렵다.
★ 그래서 세기만 하고 넣지 않는다. 넣을지는 판정이다 (⬜ D-59 「범위 밖」 자리와 함께).
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib

DIR = pathlib.Path("data/derived/labels")
OUT_OF_SCOPE = "범위밖"

#: 같은 문구를 가리키는 키. 🚨 `문구` 만으로는 안 된다 — 다른 표에 같은 문구가 있을 수 있다.
KEY_FIELDS = ("원천", "원천라벨", "문구", "글", "쪽", "호")
HUMAN = ("확정유형", "붙인이", "붙인날")


def files() -> list[pathlib.Path]:
    """`labels/*.jsonl` 을 이름 순으로. 🚨 **순서를 고정한다** — 지문이 흔들리면 안 된다."""
    return sorted(DIR.glob("*.jsonl")) if DIR.exists() else []


def key(r: dict) -> str:
    return "\x1f".join(" ".join(str(r.get(f, "")).split()) for f in KEY_FIELDS)


def label(r: dict) -> str | None:
    """붙인 라벨을 문자열 하나로. 🚨 **안 채운 행은 None** — 빈칸은 판단이 아니다."""
    v = r.get("확정유형")
    if not v:
        return None
    return "|".join(sorted(v)) if isinstance(v, list) else str(v)


def load(paths: list[pathlib.Path]) -> dict[str, dict[str, str]]:
    """파일별로 {키: 라벨}. 빈칸은 없는 것으로 본다."""
    got: dict[str, dict[str, str]] = {}
    for p in paths:
        d: dict[str, str] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            lab = label(json.loads(line))
            if lab:
                d[key(json.loads(line))] = lab
        got[p.name] = d
    return got


def person(file_name: str, r: dict) -> str:
    """누가 붙였나 — 🔄 2026-09-20 **레코드의 `붙인이`** 가 정한다(없으면 파일 이름).

    ⛔ 종전에는 **파일 = 사람**이었다. 같은 사람이 시트 둘을 가져오면 파일이 둘이 되어
       한 사람의 두 판단이 「두 사람의 합의」로 셀 수 있었다. 이름이 사람이다.
    """
    return str(r.get("붙인이") or "").strip() or file_name.split("__", 1)[0].removesuffix(".jsonl")


#: 🆕 판정 레코드의 표시 — 갈린 행을 **판정자가 정한 것**. 합의보다 앞선다(아래 `consensus`)
DECIDED = "판정"


def _rows() -> list[tuple[str, dict]]:
    got: list[tuple[str, dict]] = []
    for p in files():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                got.append((p.name, json.loads(line)))
    return got


def by_person(paths: list[pathlib.Path] | None = None) -> dict[str, dict[str, str]]:
    """사람별 {키: 라벨} — 일치도(κ)를 재는 단위. 🚨 판정 레코드는 **사람의 독립 판단이 아니라** 뺀다."""
    got: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for p in paths if paths is not None else files():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            lab = label(r)
            if lab and not r.get(DECIDED):
                got[person(p.name, r)][key(r)] = lab
    return dict(got)


def consensus() -> tuple[dict[str, dict], dict[str, int]]:
    """{키: 레코드} — **2인 이상이 붙였으면 일치한 것만** 남긴다.

    🚨 갈린 것을 다수결로 정하지 않는다. 라벨이 갈렸다는 것은 **문구가 애매하다**는
       사실이고, 그 사실을 다수결로 지우면 평가셋이 조용히 쉬워진다 (D-172).
       갈린 것은 세어서 낸다 — 붙인 사람들이 다시 본다.
    """
    # 🔄 2026-09-20 — ① 사람은 **`붙인이`** 로 센다(한 사람의 두 파일이 둘로 세지 않게)
    #                 ② **판정 레코드가 앞선다** — 갈린 행을 판정자(팀장)가 본 것이다. 다수결이 아니다
    by: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    decided: dict[str, dict] = {}
    for fname, r in _rows():
        if not label(r):
            continue
        if r.get(DECIDED):
            decided[key(r)] = r
            continue
        by[key(r)][person(fname, r)] = r  # 같은 사람이 두 번 붙였으면 나중 것
    got: dict[str, dict] = {}
    stat: collections.Counter = collections.Counter()
    for k, r in decided.items():
        got[k] = r
        stat["판정"] += 1
    for k, people in by.items():
        if k in decided:
            continue
        labs = {label(r) for r in people.values()}
        if len(labs) > 1:
            stat["갈림"] += 1
            continue
        stat["합의" if len(people) > 1 else "1인"] += 1
        got[k] = next(iter(people.values()))
    return got, dict(stat)


def out_of_scope() -> int:
    """「범위 밖」으로 찍힌 행 수. 🔴 **세기만 한다** — 모듈 머리말의 이유 참조."""
    return sum(1 for _, r in _rows() if (r.get("판단") or "").strip() == OUT_OF_SCOPE)


def docs() -> list[dict]:
    """분할이 받는 꼴 — `split.ftc_docs()` 와 같은 모양.

    🚨 문구 **하나가 한 문서**다. 해설서 문구는 서로 독립이라 문서 단위 분할을 걸 것이
       없고, 걸 필요도 없다 — 한 문구가 양쪽에 설 수 없게 id 가 문구에서 나온다.
    """
    got: list[dict] = []
    picked, _ = consensus()
    for k, r in sorted(picked.items()):
        text = str(r.get("문구") or "").strip()
        labs = sorted(r.get("확정유형") or [])
        if not text or not labs:
            continue
        fp = hashlib.sha256(k.encode("utf-8")).hexdigest()[:12]
        got.append(
            {
                "doc_id": f"guide:{fp}",
                "원천": str(r.get("원천") or "mfds_special_use_guide"),
                "유형": labs,
                "문구": [text],
                "단위": "문장",
            }
        )
    return got


def main() -> int:
    fs = files()
    if not fs:
        print(f"🔴 {DIR} 에 라벨 파일이 없다 — 아직 아무도 붙이지 않았다 (D-110)")
        return 1
    picked, stat = consensus()
    d = docs()
    print(f"라벨 파일 {len(fs)}개 — {', '.join(p.name for p in fs)}")
    print(f"  전체 행 {len(_rows()):,} · 유형 붙은 것 {len(picked):,} · 상태 {stat}")
    print(f"  🔴 「{OUT_OF_SCOPE}」 {out_of_scope()}행 — **넣지 않는다** (머리말 참조)")
    by: collections.Counter = collections.Counter(t for x in d for t in x["유형"])
    print(f"\n  분할로 나가는 문서 {len(d):,}개 · 유형별 —")
    for t, n in by.most_common():
        print(
            f"    {n:>4}  {t}   {'✅' if n >= 30 else '🔴 30 미만 — 단독으로는 측정 불가 (D-40)'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
