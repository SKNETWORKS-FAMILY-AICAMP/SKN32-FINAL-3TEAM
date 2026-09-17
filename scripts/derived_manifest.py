#!/usr/bin/env python3
"""derived_manifest.py — **파생물 원장** (기기 사이 동등성 · D-19 의 짝).

  uv run python scripts/derived_manifest.py             # 표만 찍는다 (쓰지 않는다)
  uv run python scripts/derived_manifest.py --write     # data/derived_manifest.jsonl
  uv run python scripts/derived_manifest.py --check      # 원장 ↔ 디스크 대조 (종료코드)

──────────────────────────────────────────────────────────────
🚨 **왜 필요한가 — `data/manifest.jsonl` 은 raw 전용이다.**

    원장(raw)   20,395행 · sha256 전부 있음 · **git 으로 공유된다**
    원장(파생물) **없었다** — 그래서 「네가 받은 파생물이 내 것과 같은가」를 물을 수 없다

`RAW_READERS = {"collect","preprocess"}`(게이트)라 `scripts/`·`app/`·`db/` 는 전부
파생물만 읽는다. 즉 **팀원은 raw 없이 `golden` 아래 전부를 돌릴 수 있다.**
그 길을 쓰려면 파생물에도 원장이 있어야 한다 — 이 파일이 그것이다.

──────────────────────────────────────────────────────────────
🔴 **부류가 셋이다. 이것이 「무엇을 git 에 넣는가」를 정한다.**

    원천    사람의 판정이다. **어떤 명령으로도 다시 안 나온다.** 잃으면 끝이다
            → `data/derived/labels/**`
    표본    명령으로 다시 나오지만 **다시 뽑으면 그 표본이 아니다.**
            갈리면 그때까지 채운 라벨과 평가 수치가 비교 불가가 된다
            → `*_labelsheet.jsonl` · `golden/split_manifest.json`
    생성물  명령이 같은 입력에서 같은 것을 낸다. 옮기지 않아도 다시 만들 수 있다

★ **원천·표본은 git 으로, 생성물은 파일로 옮기고 원장만 git 으로** — raw 와 같은 구조다.

──────────────────────────────────────────────────────────────
🚨 **만든 명령을 손으로 적지 않는다** (D-99).

모듈이 어느 파생물에 쓰는지는 **코드에 이미 있다.** AST 로 훑어 경로 상수를 모은다 —
문자열 `"data/derived/x.jsonl"` 과 분절 `ROOT / "data" / "derived" / "x.jsonl"` 둘 다 본다
(게이트 `_path_segments` 가 같은 이유로 둘을 본다 — 분절 표기가 검사를 지나간 적이 있다).

🔴 **쓰는 곳을 못 찾은 파생물이 있으면 멈춘다** (D-72 fail-closed).
   분류 없는 파일이 조용히 묶음에 섞이면 **재배포 가부를 모르는 채로 나간다.**
"""

from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DERIVED = ROOT / "data" / "derived"
OUT = ROOT / "data" / "derived_manifest.jsonl"
SCAN_DIRS = ("preprocess", "scripts", "collect")

#: 부류 — 경로 패턴으로 판정한다. 위에서부터 먼저 맞는 것.
#: 🚨 이 셋만 손으로 적는다. 「만든 명령」은 코드에서 나온다.
KIND_RULES: tuple[tuple[str, str, str], ...] = (
    # 🔴 **원문 캐시가 `data/derived` 안에 섞여 있다** (2026-09-17 실측 · 내 층 구분 오류).
    #    `preprocess/mfds_press.py:165` 의 `CACHE` 는 「PDF 의 표들. 캐시가 PDF 보다 새로우면
    #    그것을 쓴다」다 — **마스킹 전 원문**이고, 마스킹은 그 뒤 `--dump` 경로에서
    #    `mfds_press_labels.jsonl` 에 적용된다(그 파일은 잔여 0).
    #    ⛔ 그래서 「derived 는 마스킹을 지난 층」이 **캐시에는 참이 아니다.**
    #    ★ 캐시는 raw 와 같은 자리다 — **묶음에 넣지 않는다.** raw 가 없는 기기는
    #      어차피 `extract` 를 못 돌리므로 캐시가 없어도 잃는 것이 없다.
    ("원문캐시", "mfds_press_pdf/", "마스킹 전 원문 캐시 — raw 와 같은 자리다. 묶음에서 뺀다"),
    ("원천", "labels/", "사람의 판정 — 어떤 명령으로도 다시 안 나온다"),
    ("표본", "_labelsheet.jsonl", "다시 뽑으면 그 표본이 아니다 — 라벨과 κ 가 갈린다"),
    ("표본", "golden/split_manifest.json", "다시 나누면 평가 누수 방어와 수치 비교가 무너진다"),
)
DEFAULT_KIND = "생성물"

#: 🚨 **저장소 안에 만드는 코드가 없는 파생물.** 이름과 사유를 여기 적는다.
#:    ⛔ 검사를 약하게 두지 않고 목록으로 둔다 — 게이트의 `RAW_EXCEPTIONS` 와 같은 자리.
#:    ★ 만드는 코드가 없다는 것은 **다시 만들 수 없다**는 뜻이므로 부류는 자동으로 「원천」이다.
#:      즉 이 목록에 오르는 순간 git 으로 따라가야 하는 것이 된다.
UNWRITTEN: dict[str, str] = {
    # 🔄 2026-09-17 — 비었다. `casebook2021_labelsheet.jsonl` 이 여기 있었는데
    #    전사기를 `scripts/casebook2021_sheet.py` 로 커밋해 **1차 대조로 넘어갔다**
    #    (재생성 결과가 기기 파일과 바이트 동일 · sha 999710e20ac3 · 161,601 B).
    #    ★ 이 목록이 비어 있는 것이 정상이다. 여기 이름이 늘면 「한 기기에만 사는 원천」이 늘었다는 뜻이다.
}


#: 🔴 **반출 전 검사** — 마스킹이 실제로 됐는가 (D-17 · D-78 ③).
#:    ⛔ 게이트 `test_derived_로_나가는_원문은_마스킹을_지난다` 는 스스로 적어 두었다:
#:       *"import 만 본다. 「제대로 마스킹했는가」는 이 게이트가 못 본다."*
#:       그래서 **코드를 고친 뒤에도 낡은 산출물이 그대로 남는다** — 실측 2026-09-17:
#:       `ftc_layer1_triage.json` 은 `ftc_triage.py` 가 `mask` 를 들게 고쳐진 뒤에도
#:       **09-06 판이 그대로 있어 법인 표기 6,082건**을 싣고 있었다. 아무도 읽지 않는 파일이라
#:       지표로도 안 보였다. 묶음에 넣으면 그 6,082건이 같이 나간다.
#: 🚨 **실명이 붙은 법인 표기만** 센다. 원천이 이미 `ㅇㅇㅇ`·`000` 으로 가려 준 것과,
#:    「'주식회사'는 생략한다」처럼 **낱말로 쓰인 것**은 세지 않는다 — 실측으로 확인했다:
#:    성긴 패턴은 우리 추출물에서 12건을 잡았는데 전부 그 두 꼴이었다(거짓 양성).
#:    좁힌 뒤 우리 추출물 **0건** · 낡은 `ftc_layer1_triage.json` **2,972건**으로 갈렸다.
#: ⚠️ 이것은 **거름망**이지 증명이 아니다. 법인 표기가 없는 이름(개인·상호)은 못 잡는다 —
#:    그 잔여를 재는 것은 `preprocess/mask.py --survey` 의 일이다 (D-110).
_LEAK_NAME = r"(?![ㅇ○0]+)[가-힣A-Za-z][가-힣A-Za-z0-9]{1,}"
LEAK_PAT = re.compile(rf"(?:{_LEAK_NAME}\s*(?:㈜|\(주\))|(?:주식회사|유한회사)\s*{_LEAK_NAME})")

#: 법인 표기가 **정당하게** 남는 파일. 이름과 사유를 적는다 (검사를 약하게 두지 않는다).
LEAK_ALLOW: dict[str, str] = {
    "law_decc.jsonl": "법제처 결정례 원문 — 당사자명이 관보에 공표된 판단문의 일부다 (공공저작물)",
    "law_prec.jsonl": "법제처 판례 원문 — 같은 이유",
}


def leaks() -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """(파생물 잔여, 원문캐시 잔여) — 둘은 **다른 문제**다.

    파생물에 남으면 **마스킹이 안 된 것**이고 추출기를 다시 돌려야 한다.
    캐시에 남는 것은 **정상**이다 — 마스킹 전 원문이니까. 대신 **묶음에서 뺀다.**
    🚨 한 목록에 섞으면 「고쳐야 할 것」과 「빼야 할 것」이 구별되지 않는다 (D-160).
    """
    got: list[tuple[str, int]] = []
    cache: list[tuple[str, int]] = []
    for f in sorted(DERIVED.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep" or f.suffix not in {".json", ".jsonl"}:
            continue
        rel = f.relative_to(DERIVED).as_posix()
        if rel in LEAK_ALLOW or f.name in LEAK_ALLOW:
            continue
        n = len(LEAK_PAT.findall(f.read_text(encoding="utf-8", errors="ignore")))
        if n:
            (cache if kind_of(rel)[0] == "원문캐시" else got).append((rel, n))
    return got, cache


def kind_of(rel: str) -> tuple[str, str]:
    """`data/derived` 아래 상대경로 → (부류, 이유)."""
    for name, pat, why in KIND_RULES:
        if pat in rel:
            return name, why
    return DEFAULT_KIND, "명령이 같은 입력에서 같은 것을 낸다"


#: 파생물 뿌리를 뜻하는 표시. 경로가 문자열이 아니라 **함수 호출**로 시작할 때 쓴다 —
#: `collect.store.derived_dir(".") / "law_article.jsonl"` 이 실제로 그 꼴이다.
#: ⛔ 이 표시가 없었을 때 `law_article.jsonl`·`law_prec.jsonl` 이 「쓰는 곳 없음」으로 걸렸다.
_ROOTMARK = "\x00derived\x00"
_DERIVED_CALLS = {"derived_dir"}


def _tokens(node: ast.AST) -> list[str]:
    """`x / "a" / f"b{v}"` 사슬을 조각으로 편다.

    - 문자열 상수는 그대로
    - f-string 은 **앞쪽 리터럴까지만** — 뒤는 실행 때 정해진다 (`law_{kind}.jsonl`)
    - `derived_dir(...)` 호출과 `DERIVED` 이름은 파생물 뿌리 표시로 바꾼다
    - 그 밖(변수 등)은 빈 조각 — 경로로 세지 않는다
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _tokens(node.left) + _tokens(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        head: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                head.append(v.value)
            else:
                break
        return ["".join(head)] if head else []
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name in _DERIVED_CALLS:
            return [_ROOTMARK]
        # `pathlib.Path("data/derived")` — 문자열 인자를 그대로 조각으로 쓴다.
        # ⛔ 이것이 없을 때 `mfds_press_pdf/tables/*.json` 108개가 전부 「쓰는 곳 없음」이었다.
        if name in {"Path", "PurePath"} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return [first.value]
        return []
    if isinstance(node, ast.Name | ast.Attribute):
        last = node.attr if isinstance(node, ast.Attribute) else node.id
        return [_ROOTMARK] if last == "DERIVED" else []
    return []


def _scan(path: pathlib.Path) -> tuple[set[str], set[str]]:
    """한 모듈에서 (경로 후보, 문자열 상수 전부). 주석·docstring 은 보지 않는다.

    🚨 문자열 상수를 따로 모으는 이유 — 이름이 **실행 때 정해지는** 파생물이 있다.
       `store.derived_dir(".") / f"{source}.jsonl"` (cosmetic) ·
       `store.derived_dir(".") / name` (hf_api) · `store.derived_dir(FAMILY) / "…"` (mfds_press).
       AST 로는 어느 파일인지 모르지만 **그 이름의 조각은 같은 모듈 안에 리터럴로 있다** —
       `SOURCES = {"cosmetic_ingredient": …}` · `OUT_OFFICIAL = "hf_api_labels.jsonl"`.
    ⛔ 이 2차 대조가 없을 때 실측으로 **114개**가 미분류로 걸렸다 (클론 B · 2026-09-17).
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value.value = ""
    cands: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = [p for p in _tokens(node) if p]
            if parts:
                cands.add("/".join(p.strip("/") for p in parts))
    unparsed = ast.unparse(tree)
    for m in re.finditer(r"""["']([^"'\n]*derived/[^"'\n]*)["']""", unparsed):
        cands.add(m.group(1))
    lits = {
        n.value.strip("./")
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and 0 < len(n.value) < 80
    }
    return cands, lits


def _rel(cand: str) -> str | None:
    """후보에서 `data/derived` 뒤쪽만 떼어 낸다. 아니면 None."""
    cand = cand.replace("\\", "/")
    if _ROOTMARK in cand:
        cand = cand.rsplit(_ROOTMARK, 1)[1]
        return cand.strip("/").removeprefix("./").strip("/")
    m = re.search(r"(?:^|/)data/derived/?(.*)$", cand)
    if m is None:
        return None
    return m.group(1).strip("/")


class Table:
    """경로 → 모듈. 증거가 센 것과 약한 것을 **섞지 않는다.**

    `paths`  1차 — 코드가 경로를 상수로 든다. 확실하다
    `lits`   2차 — 그 모듈이 파생물을 만지는 것은 분명하고, 파일 이름 조각이 그 안에
             리터럴로 있다. **추정**이라 `(추정)` 을 붙여 낸다 (D-110 — 센 것과 약한 것을 가른다)
             🚨 2차는 **쓰는 것과 읽는 것을 못 가른다** — `load_db` 가 읽기만 하는 파일도
                이름을 들면 걸린다. 부류 판정에는 「쓰는 코드가 있는가」만 쓰므로
                그 한계를 안고 간다. 정확한 생산자가 필요하면 1차만 본다.
    """

    def __init__(self) -> None:
        self.paths: dict[str, set[str]] = collections.defaultdict(set)
        self.lits: dict[str, set[str]] = {}


def writers() -> Table:
    t = Table()
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            if f.name in {"__init__.py", pathlib.Path(__file__).name}:
                # 🚨 자기 자신은 뺀다 — `UNWRITTEN` 에 적은 파일 이름이 리터럴이라
                #    2차 대조에서 **이 파일이 그 파생물을 주장한다.** 실제로 그렇게 나왔다.
                continue
            mod = f"{d}.{f.stem}" if d != "scripts" else f"scripts/{f.name}"
            cands, lits = _scan(f)
            rels = {r for c in cands if (r := _rel(c)) is not None}
            for rel in rels:
                if rel:
                    t.paths[rel].add(mod)
            # 🚨 2차 대조는 **파생물을 만지는 것이 이미 확인된 모듈에만** 준다.
            #    그러지 않으면 아무 모듈의 문자열이 아무 파일을 주장할 수 있다.
            if rels:
                t.lits[mod] = lits
    return t


def match_writers(rel: str, table: Table) -> set[str]:
    """1차(경로 상수) → 2차(같은 모듈 안의 리터럴 조각) 순서로 찾는다.

    🚨 이름이 동적인 파생물이 있다 — `law_norm/<법령ID>_<별표>.jsonl` ·
       `labels/<이름>.jsonl` · `f"{source}.jsonl"`. 코드에는 조각만 상수로 있다.
    """
    if rel in table.paths:
        return table.paths[rel]
    got: set[str] = set()
    for key, mods in table.paths.items():
        if not key:
            continue
        if rel.startswith(key.rstrip("/") + "/"):
            got |= mods  # 디렉터리 접두사 — `law_norm/` · `labels/`
        elif "/" not in key and "/" not in rel and rel.startswith(key):
            got |= mods  # f-string 앞쪽 리터럴 — `law_` → `law_prec.jsonl`
    if got:
        return got

    p = pathlib.PurePosixPath(rel)
    pieces = {p.name, p.stem, *p.parts[:-1]}
    return {f"{mod} (추정)" for mod, lits in table.lits.items() if pieces & lits}


def rows() -> list[dict[str, object]]:
    if not DERIVED.exists():
        raise SystemExit(f"🔴 {DERIVED} 가 없다 — 이 기기에는 파생물이 없다")
    table = writers()
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    got: list[dict[str, object]] = []
    orphan: list[str] = []
    for f in sorted(DERIVED.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        rel = f.relative_to(DERIVED).as_posix()
        mods = sorted(match_writers(rel, table))
        if not mods and rel not in UNWRITTEN:
            orphan.append(rel)
            continue
        data = f.read_bytes()
        lines = None
        if f.suffix == ".jsonl":
            lines = sum(1 for x in data.split(b"\n") if x.strip())
        if mods:
            name, why = kind_of(rel)
        else:
            # 만드는 코드가 없다 = 다시 만들 수 없다 → 원천이다
            name, why = "원천", UNWRITTEN[rel]
            mods = ["(없음 — 저장소에 만드는 코드가 없다)"]
        got.append(
            {
                "경로": f"data/derived/{rel}",
                "부류": name,
                "부류근거": why,
                "만든모듈": mods,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "행": lines,
                "기록시각": now,
            }
        )
    if orphan:
        raise SystemExit(
            "🔴 쓰는 곳을 못 찾은 파생물이 있다 — 분류 없이 묶음에 섞이면 재배포 가부를 "
            "모르는 채로 나간다 (D-72). 만드는 모듈에 경로 상수를 두거나, 손으로 만든 것이면 "
            f"`data/derived` 밖으로 옮긴다: {orphan}"
        )
    return got


def report(got: list[dict[str, object]]) -> None:
    by = collections.Counter(str(r["부류"]) for r in got)
    size = collections.Counter()
    for r in got:
        size[str(r["부류"])] += int(r["bytes"])  # type: ignore[arg-type]
    total = sum(size.values())
    print(f"파생물 {len(got)}개 · 합계 {total / 1024 / 1024:,.1f} MB")
    print(f"\n  {'부류':<8}{'개':>5}{'크기':>12}   {'비중':>7}")
    for name in ("원천", "표본", "생성물", "원문캐시"):
        if by[name]:
            pct = size[name] / total * 100 if total else 0
            print(f"  {name:<8}{by[name]:>5}{size[name] / 1024:>10,.0f} KB{pct:>7.2f}%")
    keep = [r for r in got if r["부류"] in ("원천", "표본")]
    print(f"\n  🔴 git 으로 따라가야 하는 것 {len(keep)}개 — 다시 만들 수 없거나 갈린다")
    for r in keep:
        print(f"     {r['경로']}  ({r['행'] or '-'}행)  {r['부류']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="파생물 원장 (D-19 의 짝)")
    ap.add_argument("--write", action="store_true", help=f"{OUT.name} 을 쓴다")
    ap.add_argument("--check", action="store_true", help="원장 ↔ 디스크 대조. 다르면 1")
    ap.add_argument(
        "--export-check",
        action="store_true",
        help="🔴 묶음을 내보내기 전 검사 — 마스킹 잔여가 있으면 1 (D-17 · D-78 ③)",
    )
    a = ap.parse_args()

    got = rows()

    if a.export_check:
        bad, cache = leaks()
        pack = [r for r in got if r["부류"] != "원문캐시"]
        nc = len(got) - len(pack)
        if cache:
            print(
                f"⬜ **원문캐시 {len(cache)}개에 법인 표기가 있다 — 정상이다.** 마스킹 전 원문이다."
            )
            print(f"   → 묶음에서 뺀다. 캐시 {nc}개는 raw 와 같은 자리다(부류 원문캐시).")
            print(f"   예: {cache[0][0]}  {cache[0][1]:,}건\n")
        if not bad:
            print(f"반출 가능 — 묶음 대상 {len(pack)}개에 마스킹 잔여 0 (캐시 {nc}개 제외)")
            print(f"  ⬜ 허용 목록 {len(LEAK_ALLOW)}개는 세지 않았다: {', '.join(LEAK_ALLOW)}")
            return 0
        print("🔴 **묶음 대상에 마스킹 잔여가 있다 — 이대로 묶으면 업체명이 나간다** (D-17)")
        for rel, n in bad:
            print(f"     {rel}  법인 표기 {n:,}건")
        print("\n  🚨 만든 추출기를 다시 돌린다 — 코드는 고쳐졌어도 **산출물이 낡았을 수 있다.**")
        print("     예: uv run python -m preprocess.ftc_triage --dump", file=sys.stderr)
        return 1

    if a.check:
        if not OUT.exists():
            print(f"🔴 {OUT.name} 이 없다 — 먼저 --write", file=sys.stderr)
            return 1
        old = {
            r["경로"]: r
            for r in (
                json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()
            )
        }
        new = {str(r["경로"]): r for r in got}
        added = sorted(set(new) - set(old))
        gone = sorted(set(old) - set(new))
        changed = [k for k in sorted(set(old) & set(new)) if old[k]["sha256"] != new[k]["sha256"]]
        if not (added or gone or changed):
            print(f"원장 최신 — 파생물 {len(got)}개")
            return 0
        for k in added:
            print(f"  🆕 원장에 없다        {k}")
        for k in gone:
            print(f"  ⛔ 이 기기에 없다      {k}")
        for k in changed:
            print(f"  🔄 sha256 이 다르다   {k}")
        print("\n🔴 원장이 디스크와 다르다 — 갱신하려면 --write", file=sys.stderr)
        return 1

    report(got)
    if a.write:
        OUT.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in got) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n→ {OUT.relative_to(ROOT).as_posix()}")
    else:
        print("\n🚨 쓰지 않았다 — 원장을 만들려면 --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
