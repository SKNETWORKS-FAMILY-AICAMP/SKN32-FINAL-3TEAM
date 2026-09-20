"""라벨 시트 ↔ 엑셀(CSV) — 🚨 **사람은 번호만 채운다** (2026-09-10).

  uv run python scripts/label_sheet.py export data/derived/mfds_guide_labelsheet.jsonl --who 권소라
  uv run python scripts/label_sheet.py import build/labels/권소라__mfds_guide_labelsheet.csv --sheet <시트>
  (여러 사람에게 한 번에 나눠 주기 · 검증 행 · 판정은 `scripts/label_round.py`)

──────────────────────────────────────────────────────────────
⛔ 종전에는 **JSONL 을 손으로 고치게** 했다. 다섯 사람이 각자 편집기로 열어
   `"확정유형": ["질병_예방치료_표방"]` 을 타이핑한다 — 다음이 전부 실제로 나는 사고다.

     · 대괄호·따옴표를 빠뜨려 그 줄이 **JSON 이 아니게** 된다
     · 유형 이름을 한 글자 틀린다 (`질병_예방치료표방`) — 조용히 다른 라벨이 된다
     · `문구` 칸을 건드려 **키가 어긋난다** — 취합에서 짝이 안 맞는다

★ 그래서 **채우는 칸을 하나로 줄인다.** `유형번호` 에 1~8 만 적는다.
  번호는 **판정 순서 그대로**다 — 지시서 §3 을 위에서부터 읽다가 걸린 번호를 적으면 된다.

🚨 **의존성을 늘리지 않는다.** openpyxl 을 넣으면 팀 다섯이 전부 re-lock 을 겪는다
   (`pyproject.toml` 주석이 경고하는 자리다). CSV 를 **UTF-8 BOM** 으로 쓰면
   Windows 엑셀이 그대로 연다.

🔴 **되돌릴 때 문구를 대조한다.** `문구` 열을 고치면 가져오기가 **멈춘다** —
   키가 어긋난 라벨은 취합에서 짝을 못 찾고 조용히 사라지기 때문이다 (D-160).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "build" / "labels"  # 🚨 data/ 가 아니다 — 작업용 사본은 커밋 축 밖이다

#: 🔴 **번호 = 지시서 §3 의 판정 순서.** 두 곳이 갈리면 사람이 딴 라벨을 적는다 (D-99).
#:    ⛔ 순서를 바꾸려면 지시서와 **같은 커밋에서** 바꾼다.
TYPES: tuple[str, ...] = (
    "질병_예방치료_표방",  # 1
    "의약품_오인",  # 2
    "건강기능식품_오인",  # 3
    "후기_체험기_기만",  # 4
    "소비자_기만",  # 5
    "부당_비교광고",  # 6
    "비방광고",  # 7
    "거짓_과장",  # 8
)
#: 🔄 2026-09-20 (팀장 — *「팀원들이 시트를 작성하기 편하게」*) — 채우는 칸은 여전히 **`유형번호` 하나**다.
#:    · `참고` 원천이 뭐라고 분류했나(심의 분류 · 제품 · 근거 조문) — 판단을 돕는다
#:    · `보기` 후보를 **번호와 함께** 보여 준다 — 번호표를 옆에 펴 둘 필요가 없다
#:    · `메모` 자유 — 왜 그 번호인지, 헷갈린 점 (판정 때 읽는다)
#:    · `0` = 범위밖 (여덟 유형 어디에도 자리가 없다). 빈칸 = 모르겠다
#:    ⛔ `붙인날` 칸을 뺐다 — 가져올 때 채운다. 사람이 채울 칸을 늘리지 않는다
HEADER = ["행", "문구", "참고", "보기", "유형번호", "메모", "붙인이", "지문"]
#: 가져올 때 반드시 있어야 하는 칸 — 🚨 옛 판 CSV(`후보유형`·`붙인날` 칸)도 읽는다
REQUIRED = ("행", "문구", "유형번호", "붙인이", "지문")
#: `유형번호` 에 이것을 적으면 「범위밖」 — 옛 판의 `판단` 칸과 같은 뜻
OUT_OF_SCOPE_NO = "0"

#: 🔴 **「범위 밖」은 빈칸이 아니다** (2026-09-17). 종전에는 `유형번호` 가 비면 그 행을 **버렸다** —
#:    「판단이 안 선다(빈칸)」와 「별표1 여덟 유형에 자리가 없다」가 **같은 취급**을 받았다.
#:    둘은 다른 정보이고, 뒤엣것은 **유형 체계에 구멍이 있다는 관측**이라 버리면 안 된다 (D-160).
#: 🚨 `판단` 열은 **선택**이다 — 없으면 종전과 똑같이 돈다.
OUT_OF_SCOPE = "범위밖"


def _text(r: dict) -> str:
    """시트마다 문구 칸 이름이 다르다 — guide 는 `문구`, casebook 은 `글`."""
    for f in ("문구", "글"):
        v = r.get(f)
        if v:
            return str(v)
    return ""


def _fp(text: str) -> str:
    """문구 지문 — 되돌릴 때 **다른 칸을 고쳤는지** 본다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _rows(sheet: pathlib.Path) -> list[dict]:
    if not sheet.exists():
        raise SystemExit(
            f"🔴 {sheet} 가 없다.\n"
            "  먼저 시트를 뽑는다 — 지시서 §0:\n"
            "    uv run python launcher.py extract mfds_special_use_guide --sheet 90 --min-len 20"
        )
    return [json.loads(x) for x in sheet.read_text(encoding="utf-8").splitlines() if x.strip()]


def pick(part: str | None, n: int) -> list[int]:
    """`1-40,93-144` → 1부터 세는 행 번호들. 🚨 **구간을 여럿 받는다** (2026-09-10).

    ⛔ 하나만 받으면 「전원이 겹쳐 붙이는 공통 블록 + 각자 고유 구간」을 못 만든다.
       그래서 12건씩만 겹치게 됐는데, **κ 를 12건에서 재는 것**은 이 프로젝트 자기 기준
       (D-40 · 30건 미만 측정 불가)에 안 맞는다. 겹치기도 30 이상이어야 뜻이 있다.
    """
    if not part:
        return list(range(1, n + 1))
    got: list[int] = []
    for seg in part.split(","):
        seg = seg.strip()
        if not seg:
            continue
        a, _, b = seg.partition("-")
        lo, hi = int(a), int(b or a)
        if not (1 <= lo <= hi <= n):
            raise SystemExit(f"🔴 구간 {seg!r} 이 시트 범위(1~{n}) 밖이다")
        got += [i for i in range(lo, hi + 1) if i not in got]
    return sorted(got)


#: 번호표의 한 줄 설명 — 🔗 정본은 `docs/ohb/라벨링_지시서_2026-09-10.md` §3 (예시는 그대로 옮겼다 · 바꾸면 양쪽)
TYPE_HINTS: dict[str, str] = {
    "질병_예방치료_표방": "질병 이름·증상이 나온다 — 「변비에 효과」「당뇨 예방」「배앓이」",
    "의약품_오인": "의약품처럼 말한다 — 「치료제」「처방」「특효」「~약」",
    "건강기능식품_오인": "일반식품이 기능성을 말한다 — 「면역력 강화」「체지방 감소」",
    "후기_체험기_기만": "후기·체험기 형식 — 「저도 먹어 봤는데」「3개월 만에」",
    "소비자_기만": "숨기거나 오인하게 배치 — 불리한 사실 누락 · 조건을 작게",
    "부당_비교광고": "근거 없이 경쟁사와 비교 — 「타사보다 2배」",
    "비방광고": "경쟁사를 깎아내린다 — 「시중 제품은 효과 없다」",
    "거짓_과장": "위 어디도 아닌데 부풀렸다 — 「100%」「국내 최초」「유일한」 🔴 마지막에 본다",
}


def choices(r: dict) -> str:
    """`보기` 칸 — 후보 유형을 **번호와 함께**. 후보가 없으면 전체."""
    cands = [t for t in (r.get("후보유형") or []) if t in TYPES]
    if not cands:
        return "1~8 전체 (번호표 참고)"
    body = " · ".join(f"{TYPES.index(t) + 1} {t}" for t in cands)
    return f"{body}  (다른 번호도 됩니다 · 0=범위밖)"


def note(r: dict) -> str:
    """`참고` 칸 — 원천이 뭐라고 했나. 🚨 판단을 돕는 것이지 정답이 아니다."""
    got = [str(r.get(k)) for k in ("참고", "원천라벨", "제품유형") if r.get(k)]
    return " · ".join(got)[:160]


def export(
    sheet: pathlib.Path,
    who: str,
    part: str | None,
    *,
    idx: list[int] | None = None,
    quiet: bool = False,
) -> pathlib.Path:
    rows = _rows(sheet)
    idx = idx if idx is not None else pick(part, len(rows))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{who}__{sheet.stem}.csv"
    # 🚨 BOM 을 붙인다 — 없으면 Windows 엑셀이 한글을 깨서 연다.
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i in idx:
            r = rows[i - 1]
            t = _text(r)
            w.writerow([i, t, note(r), choices(r), "", "", who, _fp(t)])
    guide = write_guide()
    if quiet:
        return out
    print(f"  → {out.relative_to(ROOT)}  ({len(idx)}행)")
    print(f"  → {guide.relative_to(ROOT)}  (번호표 · 채우는 법)")
    print(
        "\n  채우는 칸은 **`유형번호` 하나**다. 1~8, 둘이면 `1,5`, 범위밖은 `0`, 모르겠으면 비운다."
    )
    print("  🚨 `문구`·`지문` 열은 건드리지 않는다 — 고치면 가져오기가 멈춘다.")
    return out


def write_guide() -> pathlib.Path:
    """팀원이 옆에 펴 둘 **한 장** — 번호표 + 채우는 법. `build/labels/` 에만 쓴다(커밋 밖)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "유형번호표.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "유형", "이럴 때 (위에서부터 보다가 걸리면 멈춘다)"])
        for n, t in enumerate(TYPES, 1):
            w.writerow([n, t, TYPE_HINTS[t]])
        w.writerow([0, "범위밖", "여덟 유형 어디에도 자리가 없다"])
        w.writerow(
            ["(비움)", "모르겠다", "🚨 빈칸은 실패가 아니라 판단이다 — 억지로 채우지 않는다"]
        )
        w.writerow([])
        w.writerow(
            ["채우는 법", "", "`유형번호` 칸만 채운다. 둘이면 1,5 처럼 쉼표로. `메모` 는 자유"]
        )
        w.writerow(
            [
                "하지 말 것",
                "",
                "`문구`·`지문` 수정 · 행 삭제 · 다른 사람과 상의해 맞추기(독립으로 붙여야 한다)",
            ]
        )
        w.writerow(["다 했으면", "", "파일 이름을 바꾸지 말고 그대로 팀장에게 보낸다"])
    return p


def load_csv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        got = list(csv.DictReader(f))
    if not got or set(REQUIRED) - set(got[0]):
        raise SystemExit(f"🔴 {path} 의 머리글이 다르다 — export 로 만든 파일이어야 한다")
    return got


def parse_no(raw: str, line: int) -> list[str]:
    """`1,5` → 라벨 둘. 🚨 못 읽는 값은 **멈춘다** — 조용히 버리면 그 사람의 판단이 사라진다."""
    got = []
    for tok in str(raw).replace(" ", "").split(","):
        if not tok:
            continue
        if not tok.isdigit() or not 1 <= int(tok) <= len(TYPES):
            raise SystemExit(
                f"🔴 {line}행의 유형번호 {tok!r} 을 못 읽는다 — 1~{len(TYPES)} 만 쓴다.\n"
                "  모르겠으면 **비워 둔다.** 빈칸은 실패가 아니라 판단이다."
            )
        lab = TYPES[int(tok) - 1]
        if lab not in got:
            got.append(lab)
    return got


def import_(csv_path: pathlib.Path, sheet: pathlib.Path, day: str) -> int:
    rows = _rows(sheet)
    filled = load_csv(csv_path)
    tampered, out_rows, n = [], [], 0
    gold_seen: list[tuple[int, list[str], list[str]]] = []
    for rec in filled:
        i = int(rec["행"])
        base = dict(rows[i - 1])
        # 🔴 **세 개를 맞춘다** — 시트의 문구 · CSV 의 문구 · 지문 (2026-09-10 정정).
        #    ⛔ 처음에 시트↔지문만 봤다. 그러면 사람이 CSV 의 `문구` 칸을 고쳐도
        #       지문이 그대로라 **그냥 통과한다** — 정확히 막으려던 것을 못 막았다.
        #       반대 대조로 잡았다: 문구를 고쳐 넣었는데 4건이 그대로 들어갔다.
        if not (_fp(_text(base)) == rec["지문"] == _fp(rec["문구"])):
            tampered.append(i)
            continue
        raw_no = (rec.get("유형번호") or "").strip()
        scope = (rec.get("판단") or "").strip()
        if raw_no == OUT_OF_SCOPE_NO:
            raw_no, scope = "", OUT_OF_SCOPE
        labs = parse_no(raw_no, i)
        # 🆕 검증 행 — 정답을 아는 문구를 섞어 둔 것이다. **라벨로 쓰지 않고** 맞혔는지만 센다
        if base.get("검증정답") is not None:
            gold_seen.append((i, sorted(labs), sorted(base["검증정답"])))
            continue
        if scope == OUT_OF_SCOPE:
            if labs:
                raise SystemExit(f"🔴 {i}행이 「범위밖」인데 유형번호가 있다 — 둘 중 하나만 적는다")
            base["판단"] = OUT_OF_SCOPE
        elif not labs:
            continue  # 빈칸 — 판단이 없는 것이다. 버린 것이 아니다
        base.pop("재검_제외", None)  # 판 짜기용 칸 — 라벨에는 안 남긴다
        base["확정유형"] = labs
        base["붙인이"] = (rec.get("붙인이") or "").strip()
        base["붙인날"] = (rec.get("붙인날") or "").strip() or day or _today()
        if (rec.get("메모") or "").strip():
            base["메모"] = rec["메모"].strip()
        if not base["붙인이"]:
            raise SystemExit(f"🔴 {i}행에 `붙인이` 가 없다 — 누가 붙였는지가 라벨의 일부다 (D-66)")
        out_rows.append(base)
        n += 1
    if tampered:
        raise SystemExit(
            f"🔴 `문구` 열이 바뀐 행 {len(tampered)}개 — {tampered[:8]}\n"
            "  🚨 문구가 키다. 고치면 취합에서 짝을 못 찾고 **조용히 사라진다** (D-160).\n"
            "  → 그 행을 원래대로 되돌리거나, export 를 다시 받아 채운다."
        )
    who = (filled[0].get("붙인이") or "이름없음").strip()
    # 🔄 2026-09-20 — 파일 이름에 **시트 이름**을 붙인다. ⛔ 종전 `<이름>.jsonl` 은 같은 사람이 둘째 시트를
    #    가져오면 **첫 시트 라벨을 덮어썼다.** 사람 구분은 파일이 아니라 레코드의 `붙인이` 가 한다 (labels.py)
    out = ROOT / "data" / "derived" / "labels" / f"{who}__{sheet.stem}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    scoped = sum(1 for r in out_rows if r.get("판단") == OUT_OF_SCOPE)
    print(
        f"  → {out.relative_to(ROOT)}  ({n}건 · 그중 범위밖 {scoped}건 · 빈칸 {len(filled) - n}건)"
    )
    print("  🚨 빈칸은 **안 들어갔다.** 버린 것이 아니라 판단이 없는 것이다.")
    if gold_seen:
        hit = sum(1 for _, got, ans in gold_seen if got == ans)
        blank = sum(1 for _, got, _ in gold_seen if not got)
        print(
            f"\n  🔎 검증 행 {len(gold_seen)}개 — 맞힘 {hit} · 비움 {blank} · 다름 {len(gold_seen) - hit - blank}"
            f"  (정답률 {hit / len(gold_seen):.0%})"
        )
        print("     ★ 검증 행은 **라벨로 들어가지 않는다.** 정답은 기관이 이미 판단한 문구다")
        print("     🚨 사람 평가가 아니라 **지시서가 통하는지** 보는 수다 — 낮으면 지시서를 고친다")
    print("\n  취합 — uv run python scripts/label_merge.py data/derived/labels/*.jsonl")
    # 🔄 2026-09-20 (D-249) — 라벨은 git 에 올리지 않는다(공개 저장소 · 인용 원문). 정본이 저장소에 올린다.
    print(
        "  🚨 git 에 커밋하지 않는다 (D-249). 정본(클론 B)에서 import 한 뒤 —\n"
        "     launcher.py derived-manifest --write → 원장 커밋 · push → launcher.py data-publish\n"
        "     팀원은 채운 CSV 를 팀장에게 넘긴다 (정본만 올린다 · D-226)"
    )
    return 0


def _today() -> str:
    import datetime as dt  # noqa: PLC0415

    return dt.date.today().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="라벨 시트 ↔ 엑셀(CSV) — 사람은 번호만 채운다")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="시트 → 채울 CSV")
    e.add_argument("sheet", type=pathlib.Path)
    e.add_argument("--who", required=True, help="붙이는 사람 이름 — 파일명이 된다")
    e.add_argument("--part", help="맡은 구간 — 여럿 가능 (예: 1-40,93-144)")
    i = sub.add_parser("import", help="채운 CSV → data/derived/labels/<이름>.jsonl")
    i.add_argument("csv", type=pathlib.Path)
    i.add_argument("--sheet", type=pathlib.Path, required=True, help="export 에 쓴 원본 시트")
    i.add_argument("--day", default="", help="붙인날 기본값 (비면 CSV 값을 쓴다)")
    a = ap.parse_args()
    if a.cmd == "export":
        export(a.sheet, a.who, a.part)
        return 0
    # 🆕 2026-09-20 — 라벨(원천)은 **정본만** 쓴다 (D-226 · D-249). 팀원은 채운 CSV 를 팀장에게 넘긴다.
    #    🚨 `python scripts/label_sheet.py` 로 불리면 sys.path[0] 이 `scripts/` 다 — 레포 루트를 앞에 둔다
    #       (`derived_manifest.py` 가 같은 이유로 같은 일을 한다 · 런처가 이 경로로 부른다)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts import derived_manifest as dm  # noqa: PLC0415

    why = dm.not_canonical("labelsheet import")
    if why:
        print(why, file=sys.stderr)
        return 1
    return import_(a.csv, a.sheet, a.day)


if __name__ == "__main__":
    sys.exit(main())
