"""인코더 재분할 — 봉인 평가셋의 해설서 행 일부를 **인코더 학습 · dev 로 옮긴다** (🆕 2026-10-15 · D-347).

왜 여기 있나
  · 해설서(식약처 특수용도식품 표시 · 광고 해설서)의 위반 문구 판(`gs:`)과 수정 문구 판(`gf:`)은 전량 봉인 평가셋에
    들어가 있다(D-285 개정 4 · 판정 J1 (b)). 학습 쪽 해설서(`ge:` 근거 판)의 정상(D) 행은 17 개뿐이라 인코더는 해설서의
    「주장 아닌 줄」 · 허용 문구를 거의 배우지 못했다(봉인 404 / 학습 17 · 2026-10-15 클론 A 구성 집계).
  · 🔴 **골든 분할(`split` 칸)과 사전은 바꾸지 않는다** — 사전은 학습 분할 전체로 만들고(`preprocess/dictionary.py`
    `train_only`) dev 는 학습 분할에서 무작위로 뗀다(`preprocess/devsplit.py`). 골든을 바꾸면 둘 다 바뀐다(D-347 (나-1) 기각).
    여기서 옮긴 행은 **인코더 학습 입력과 인코더 dev 에만** 들어가고, 봉인 평가셋은 그만큼 줄어든다.

규칙 (D-347 · 측정 전에 고정 · 점수를 보지 않고 정했다)
  · 대상 — 봉인 평가셋(`split == "test_sentence"`) 중 id 가 `gs:` · `gf:` 로 시작하는 행. 그 밖의 봉인 행은 그대로 봉인
  · 묶음 — 행 id 의 `#` 앞. 묶음의 글자를 이어 **정규화**(공백 · 기호 · 밑줄을 뺀다)한 것이 열쇠 — 띄어쓰기 · 기호만 다른
    같은 문구는 같은 쪽으로 간다(해설서 위반 문구 판에 그런 묶음 26 · 60 행)
  · 배정 — `sha256("v1|" + 열쇠) % 10` → 0 ~ 4 학습 · 5 ~ 6 dev · 7 ~ 9 봉인 (5 : 2 : 3 · `[임의]`)
  · 예외 — 옮긴 뒤 봉인에서 측정 가능(D-40 의 30)에서 측정 불가로 떨어지는 유형이 생기면, **그 유형 라벨이 붙은 묶음은
    봉인에 남긴다**(라벨 수만 본다 · 점수를 보지 않는다 · D-175). 남긴 뒤 다시 세어 안정될 때까지 되풀이한다
  · 유형 수는 조건 A · B · C 행의 라벨로 센다(채점 대상 · D-321)
  · 🔄 2026-10-15 보강(누수 점검 뒤 · 점수를 보지 않았다) — 아래 둘은 **한 덩이**로 묶어 같은 칸에 넣는다(덩이의 열쇠는 묶음 열쇠 중
    가장 작은 것). ① 수정 문구(`gf:`)와 그 원래 문구(`gs:`) — 판독 채택본 `guide_fix` 의 `원래문구` 로 잇는다(봉인에 4 짝 · 그중
    3 짝이 학습과 봉인에 갈렸다) ② 정규화 글자의 3 글자 조각 자카드 ≥ 0.8 인 근접 중복 `[임의]`
    ③ 옮기지 않는 봉인 행(공정위 보도자료 · 화장품 질의응답 등)과 같거나 근접한 덩이는 **봉인에 남긴다**(2 ~ 7 자 짧은
    문구 3 행이 다른 원천의 봉인 행과 같은 글자였다)

🚨 학습기 · 평가 도구 · 판정기 B 가 **이 모듈 하나**를 부른다(D-99) — 같은 골든이면 같은 행이 나온다. 지문(`sha`)은
   devsplit 과 같은 함수다. 모델 폴더 `label_scheme.json` 에 옮긴 학습 · dev 지문을 싣는다(D-347 결정 4).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

from preprocess import devsplit

#: 판 이름 — 해시의 머리. 바꾸면 다른 배정이 나온다(새 판으로 기록한다)
VERSION = "v1"
#: 옮길 대상 판의 id 머리 (해설서 위반 문구 판 · 수정 문구 판)
PREFIXES = ("gs:", "gf:")
#: 학습 : dev : 봉인 — 10 칸 중 몇 칸 `[임의]` (D-347)
SHARES = (5, 2, 3)
#: 측정 가능 하한 (D-40 · `[관행]`)
MIN_POS = 30
#: 유형을 세는 조건 — 채점 대상 (D-321)
SCORED = ("A", "B", "C")

#: 근접 중복으로 묶는 문자 3-gram 자카드 하한 `[임의]` (D-347 보강)
NEAR = 0.8
#: 수정 문구 → 원래 문구 연결의 원천 — 판독 채택본 (`preprocess/split.py` `GUIDE_FIX_ADOPTED` 와 같은 파일 · D-99)
GUIDE_FIX = pathlib.Path("data/derived/labels/guide_fix/adopted.jsonl")

_NONWORD = re.compile(r"[\s\W_]+")

TRAIN, DEV, SEALED = "train", "dev", "sealed"


def norm(text: str) -> str:
    """공백 · 기호 · 밑줄을 뺀 글자 — 같은 문구 판별용."""
    return _NONWORD.sub("", text or "")


def _group(rid: str) -> str:
    return rid.split("#")[0]


def _slot(key: str) -> str:
    h = int(hashlib.sha256(f"{VERSION}|{key}".encode()).hexdigest(), 16) % sum(SHARES)
    a, b, _ = SHARES
    return TRAIN if h < a else (DEV if h < a + b else SEALED)


def _types(rows: Iterable[dict]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        if r.get("조건") in SCORED:
            c.update(set(r.get("labels") or []))
    return c


def fix_links(path: pathlib.Path = GUIDE_FIX) -> list[tuple[str, str]]:
    """(수정 문구 묶음 id, 원래 문구의 정규화 글자). 🔴 파일이 없으면 멈춘다 — 「연결 없음」으로 세지 않는다 (D-220)."""
    if not path.exists():
        raise SystemExit(
            f"🔴 {path} 가 없다 — 수정 문구와 원래 문구를 같은 칸에 묶지 못한다 (D-347) · 사본은 `data-sync`"
        )
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if r.get("원래문구"):
                out.append((r["지문"], norm(r["원래문구"])))
    return out


def _grams(s: str) -> frozenset[str]:
    return frozenset(s[i : i + 3] for i in range(max(1, len(s) - 2)))


def plan(golden: Iterable[dict], links: Iterable[tuple[str, str]] | None = None) -> dict[str, str]:
    """봉인 평가셋 행 id → `train` · `dev` · `sealed`. 🔴 학습 분할 행은 넣지 않는다(이 모듈이 다루지 않는다).

    `links` 를 안 주면 봉인에 수정 문구 묶음이 있을 때 `fix_links()` 를 읽는다.
    """
    sealed = [r for r in golden if r.get("split") == "test_sentence"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in sealed:
        groups[_group(r["id"])].append(r)
    #: 묶음 열쇠 — 묶음의 문장을 id 순으로 이어 정규화
    key = {
        g: norm("".join(r.get("text", "") for r in sorted(rs, key=lambda x: x["id"])))
        for g, rs in groups.items()
    }
    movable = sorted(g for g in groups if g.startswith(PREFIXES))
    if links is None:
        links = fix_links() if any(g.startswith("gf:") for g in movable) else []
    #: 덩이 — 같은 글자 · 수정 ↔ 원래 · 근접 중복을 잇는다(합집합 찾기)
    parent = {g: g for g in movable}

    def find(g: str) -> str:
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g

    def join(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_key: dict[str, str] = {}
    for g in movable:
        if key[g] in by_key:
            join(g, by_key[key[g]])
        else:
            by_key[key[g]] = g
    gs_by_key = {key[g]: g for g in movable if g.startswith("gs:")}
    for gf, orig in links:
        if gf in parent and orig in gs_by_key:
            join(gf, gs_by_key[orig])
    grams = {g: _grams(key[g]) for g in movable}
    index: dict[str, set[str]] = defaultdict(set)
    for g in movable:
        for x in grams[g]:
            index[x].add(g)
    for g in movable:
        seen: Counter = Counter()
        for x in grams[g]:
            for h in index[x]:
                if h > g:
                    seen[h] += 1
        for h, n in seen.items():
            if n / len(grams[g] | grams[h]) >= NEAR:
                join(g, h)
    comp: dict[str, list[str]] = defaultdict(list)
    for g in movable:
        comp[find(g)].append(g)
    slot = {g: SEALED for g in groups}
    for members in comp.values():
        s = _slot(min(key[g] for g in members))
        for g in members:
            slot[g] = s
    #: ③ 옮기지 않는 봉인 행(다른 원천)과 같거나 근접한 덩이는 봉인에 남긴다 — 옮기면 같은 글자가 학습과 봉인에 갈린다.
    #:    🔴 **문장 단위**로 본다 — 여러 문장짜리 묶음 안의 한 문장이 해설서 문구와 같을 수 있다(묶음 글자로는 안 잡힌다)
    fixed_idx: dict[str, set[str]] = defaultdict(set)
    fixed: dict[str, frozenset[str]] = {}
    for g, rows in groups.items():
        if g in parent:
            continue
        for r in rows:
            fixed[r["id"]] = gg = _grams(norm(r.get("text", "")))
            for x in gg:
                fixed_idx[x].add(r["id"])
    for members in comp.values():
        hit = False
        for g in members:
            for r in groups[g]:
                mine = _grams(norm(r.get("text", "")))
                seen = Counter(h for x in mine for h in fixed_idx[x])
                if any(n / len(mine | fixed[h]) >= NEAR for h, n in seen.items()):
                    hit = True
                    break
            if hit:
                break
        if hit:
            for m in members:
                slot[m] = SEALED
    before = _types(sealed)
    keep: set[str] = set()
    while True:
        after = _types(r for g, rs in groups.items() if slot[g] == SEALED for r in rs)
        drop = {t for t, n in before.items() if n >= MIN_POS and after.get(t, 0) < MIN_POS} - keep
        if not drop:
            break
        keep |= drop
        for members in comp.values():
            if slot[members[0]] != SEALED and any(
                r.get("조건") in SCORED and drop & set(r.get("labels") or [])
                for g in members
                for r in groups[g]
            ):
                for g in members:
                    slot[g] = SEALED
    return {r["id"]: slot[_group(r["id"])] for r in sealed}


def ids(golden: Iterable[dict], which: str) -> list[str]:
    """그 칸의 행 id (골든 순서)."""
    rows = list(golden)
    p = plan(rows)
    return [r["id"] for r in rows if p.get(r["id"]) == which]


def sealed_rows(golden: Iterable[dict]) -> list[dict]:
    """**봉인 평가셋** — 봉인 행 중 인코더 학습 · dev 로 옮기지 않은 것 (D-347). 평가 도구 · 판정기 B 가 이것만 읽는다(D-99)."""
    rows = list(golden)
    p = plan(rows)
    return [r for r in rows if p.get(r["id"]) == SEALED]


def guide_dev_rows(golden: Iterable[dict]) -> list[dict]:
    """인코더 dev 에 더할 해설서 행 — devsplit 의 dev 와 합쳐 「확장 dev」가 된다 (D-347)."""
    rows = list(golden)
    p = plan(rows)
    return [r for r in rows if p.get(r["id"]) == DEV]


def stamp(golden: Iterable[dict]) -> dict[str, object]:
    """판 표지 — 칸마다 행 수 · 지문. 모델 폴더 · 원장에 적는다."""
    rows = list(golden)
    p = plan(rows)
    out: dict[str, object] = {"resplit": VERSION}
    for w in (TRAIN, DEV, SEALED):
        got = [r["id"] for r in rows if p.get(r["id"]) == w]
        out[f"{w}_rows"] = len(got)
        out[f"{w}_sha"] = devsplit.sha(got)
    return out


def main(argv: list[str] | None = None) -> int:
    """칸마다 행 수 · 지문 · 유형 수를 보인다. `--write <폴더>` 면 칸마다 id 목록(`resplit_v1_<칸>.txt`)을 쓴다."""
    import argparse  # noqa: PLC0415
    import json  # noqa: PLC0415
    import pathlib  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--golden", type=pathlib.Path, default=pathlib.Path("data/derived/golden/golden.jsonl")
    )
    ap.add_argument("--write", type=pathlib.Path, help="id 목록을 쓸 폴더 (글자는 쓰지 않는다)")
    a = ap.parse_args(argv)
    if not a.golden.exists():
        raise SystemExit(f"🔴 {a.golden} 가 없다 — 빈 목록으로 0 을 내지 않는다 (D-220)")
    rows = [json.loads(x) for x in a.golden.read_text(encoding="utf-8").splitlines() if x.strip()]
    p = plan(rows)
    print(f"재분할 {VERSION} · 골든 {len(rows)} 행 · 봉인 평가셋 {len(p)} 행")
    for k, v in stamp(rows).items():
        print(f"  {k} {v}")
    for w in (TRAIN, DEV, SEALED):
        rs = [r for r in rows if p.get(r["id"]) == w]
        dl = sum(1 for r in rs if r.get("조건") in ("D", "L"))
        print(f"  {w:6s} 정상(D·L) {dl:4d} · 유형 {dict(sorted(_types(rs).items()))}")
    if a.write:
        a.write.mkdir(parents=True, exist_ok=True)
        for w in (TRAIN, DEV, SEALED):
            (a.write / f"resplit_{VERSION}_{w}.txt").write_text(
                "".join(r["id"] + "\n" for r in rows if p.get(r["id"]) == w),
                encoding="utf-8",
                newline="\n",
            )
        print(f"  ✍ {a.write} 에 id 목록 셋")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
