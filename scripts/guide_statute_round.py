"""scripts/guide_statute_round.py — 해설서 위반문구에 **조문 인용과 조건**을 붙이는 한 판 (2026-09-24 · D-285).

  uv run python -m scripts.guide_statute_round input  --out build/labels/guide_statute__입력.tsv
  uv run python -m scripts.guide_statute_round merge  --r1 <판독1.tsv> --r2 <판독2.tsv> [--rr1 <재판독1.tsv> --rr2 <재판독2.tsv>]

🚨 `-m` 으로 돌린다 — 스크립트로 돌리면 `scripts/collect.py` 가 `collect` 패키지를 가린다.

★ 흐름 (지시서 `docs/ohb/라벨링_지시서_2026-09-24_해설서_조문·조건.md` §5 · §6)
  1 input   1,834행을 판독 입력으로 낸다 — `지문` · 문구 · 원천 묶음 · 제품유형
  2 (판독)  독립 판독 둘이 각자 TSV 를 낸다 — 서로의 결과를 보지 않는다
  3 merge   둘이 **같으면** 채택(`판독` = `독립판독_합의`) · 다르면 사람 2인 시트로
            🔄 09-25 (D-285 개정 2) — 기대 응답이 같은 갈림(D↔M · 호만 안 겹침)은 규칙으로 채택 · 시트는 기대 응답이 갈리는 행
  4 (사람)  2인이 각자 시트를 채운다 → 팀장 판정표 ⬜ (다음 판) · 경계 묶음은 팀장이 묶음 단위로 판정(지시서 §6)

🔄 `scripts/label_round.py` 머리말의 「참고 답은 라벨이 아니다」는 **8유형 라운드**의 규칙이다.
   해설서 **조문 인용**은 D-285 가 독립 판독 둘의 합의를 채택한다 — 행마다 `판독` 칸으로 사람 판정과 가른다.

🔄 2026-09-24 밤 (D-285 개정 · D-288)
  · 조건 M 은 둘 다 M 이면 같다 — 근거는 두 판독의 호 집합이 같을 때만 남기고 아니면 빈 목록
  · `--rr1/--rr2` — 지시서 개정 뒤 **다시 읽은 행**(유형 9 의 3호·4.라 행)이 첫 판독을 **통째로** 갈아 끼운다. 원자료에 `판` 으로 남는다
  · 3.나 는 원천 제품유형 9 에서만 — 다른 유형에 적힌 판독은 채택하지 않고 시트로 (D-288)
  · 🔴 산출물은 `data/derived/labels/guide_statute/` — 부류 「원천」(다시 돌려도 같은 판독이 아니다). `labels/*.jsonl` 을 읽는
    `preprocess.labels` 는 하위 폴더를 안 읽는다

판독 TSV 한 줄 — `지문 \\t 주근거 \\t 부근거 \\t 조건 \\t 제외목 \\t 원천결손 \\t 메모`
  주근거·부근거  [별표 1] 코드 `5.다` · `3` · `4.라` / 법 제8조①9·10호는 `법8-9` · `법8-10` / 없으면 `-` /
                 그 밖(시행규칙 [별표 6] 등)은 `기타:<원문>` — 🔴 억지로 가까운 호에 넣지 않는다 (지시서 §1)
  조건          C · A · B · M · D
  제외목        `3.라,1.가.1` 처럼 쉼표 · 없으면 `-`
  원천결손      Y · N
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collect import statute  # noqa: E402

READINGS = ROOT / "data" / "derived" / "labels" / "guide_statute" / "readings.jsonl"
ADOPTED = ROOT / "data" / "derived" / "labels" / "guide_statute" / "adopted.jsonl"
SHEET = ROOT / "build" / "labels" / "guide_statute__판정시트.csv"

CONDITIONS = ("C", "A", "B", "M", "D")
#: [별표 1] 적용 제외 — 지시서 §1 표와 같은 목록. 🔴 `근거` 에 오면 안 된다 (D-238)
EXCEPTIONS = frozenset(
    (
        "1.가.1",
        "1.가.2",
        "1.라.1",
        "1.라.2",
        "3.가",
        "3.나",
        "3.다",
        "3.라",
        "5.가단서",
        "5.라단서",
        "7.나단서",
    )
)
_CODE = re.compile(r"^([1-8])(?:\.([가-힣]))?$")
_LAW = {"법8-9": 9, "법8-10": 10}


def key_of(r: dict) -> str:
    """행 지문 — 표 · 원천 묶음 · 문구. 🚨 같은 문구가 한 제품의 다른 표(환자용 세부 품목)에 또 나온다 → 표까지 넣는다."""
    raw = f"{r['표']}|{r['원천라벨']}|{r['문구']}"
    return "gs:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def rows() -> list[dict]:
    """해설서 위반문구 전량 — `preprocess.mfds_guide` 추출 · 마스킹을 지난 사본 (D-159)."""
    from preprocess import mfds_guide as mg  # noqa: PLC0415

    if not mg.policy_or_stop():
        raise SystemExit(1)
    got, _ = mg.masked([r for r in mg.extract(mg._hwp()) if r["종류"] == "위반문구"])
    out = [{**r, "지문": key_of(r)} for r in got]
    dup = [k for k, v in collections.Counter(r["지문"] for r in out).items() if v > 1]
    if dup:
        raise ValueError(f"지문이 겹친다 {len(dup)} — 예 {dup[:3]}")
    return out


def cite_of(code: str) -> str:
    """판독 코드 → 인용. 🔴 모르는 꼴은 멈춘다 — 조용히 버리지 않는다 (D-220). 적용 제외 목이 오면 멈춘다 (D-238)."""
    code = code.strip()
    if code in EXCEPTIONS:
        raise ValueError(f"적용 제외 목은 근거가 아니다: {code!r}")
    if code in _LAW:
        return statute.food(_LAW[code])
    m = _CODE.match(code)
    if not m:
        raise ValueError(f"근거 코드 꼴이 아니다: {code!r}")
    return statute.food(int(m.group(1)), m.group(2))


def parse_line(line: str) -> dict:
    """판독 TSV 한 줄 → 레코드. `문제` 에 걸린 것을 모은다 — 걸린 행은 채택하지 않는다."""
    p = line.rstrip("\n").split("\t")
    if len(p) < 6:
        raise ValueError(f"칸이 모자란다({len(p)}): {line[:80]!r}")
    p += [""] * (7 - len(p))
    key, prim, sec, cond, exc, gap, memo = (x.strip() for x in p[:7])
    rec = {
        "지문": key,
        "조건": cond,
        "근거": [],
        "제외목": [],
        "원천결손": gap == "Y",
        "메모": memo,
        "문제": [],
    }
    if cond not in CONDITIONS:
        rec["문제"].append(f"조건 {cond!r}")
    for c in (prim, sec):
        if c in ("", "-"):
            continue
        if c.startswith("기타:"):
            rec["문제"].append(f"인용 꼴 밖 {c}")
            continue
        try:
            rec["근거"].append(cite_of(c))
        except ValueError as e:
            rec["문제"].append(str(e))
    for e in (x.strip() for x in exc.split(",")):
        if e in ("", "-"):
            continue
        if e in EXCEPTIONS:
            rec["제외목"].append(e)
        else:
            rec["문제"].append(f"모르는 제외목 {e!r}")
    if gap not in ("Y", "N"):
        rec["문제"].append(f"원천결손 {gap!r}")
    return rec


def read(path: pathlib.Path) -> dict[str, dict]:
    got: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = parse_line(line)
        if r["지문"] in got:
            raise ValueError(f"{path.name}: 지문이 두 번 — {r['지문']}")
        got[r["지문"]] = r
    return got


def agree(a: dict, b: dict) -> tuple[dict | None, str]:
    """두 판독이 **같은가** (지시서 §5 · D-285). 같으면 (채택값, "") · 다르면 (None, 이유).

    🔄 D-285 개정 2 (09-25) — 기대 응답이 같은 갈림은 규칙으로 닫는다: D↔M → M · 호만 안 겹침 → `근거_후보`.
    시트에 남는 것은 **기대 응답이 갈리는 것**(위반 ↔ 보류·대상 아님)과 판독 문제 · 원천결손 · A↔B 다.
    """
    if a["문제"] or b["문제"]:
        return None, "판독 문제 — " + " / ".join(a["문제"] + b["문제"])
    if {a["조건"], b["조건"]} == {"D", "M"}:
        # 🔄 2026-09-25 (D-285 개정 2) — **D↔M 은 M 으로 보수 합성**. 둘 다 위반이 아니고, M(low_conf)은 통과로
        #    새지 않는다 · D(판정 대상 아님)는 새는 쪽이다 (D-273). 원천결손은 **둘 다** 적었을 때만 — M 이 한쪽이면
        #    평가에 남긴다(빼는 쪽이 보수적이지 않다)
        return {
            "조건": "M",
            "근거": [],
            "근거_후보": [],
            "제외목": [],
            "원천결손": a["원천결손"] and b["원천결손"],
            "조건_이견": ["D", "M"],
        }, ""
    gap = a["원천결손"] or b["원천결손"]
    if gap and not (a["조건"] == b["조건"] == "D"):
        return (
            None,
            "원천결손",
        )  # 🔄 09-24 밤 — 둘 다 D 면 채택(아래) · 갈리면 시트 (지시서 §5 · ④′)
    cond, dissent = a["조건"], []
    if a["조건"] != b["조건"]:
        # 🔄 2026-09-25 (D-285 개정) — **보수 합성**: C 와 A·B 가 갈리면 더 엄격한 C 로 · 이견을 남긴다.
        #    제외목은 교집합(③)이고 기록되는 판정은 가장 보수적인 전제다(D-263 ①) — 같은 논리다.
        #    A↔B 는 엄격함의 순서가 없어 시트로 · 기대 응답이 갈리는 쌍(M·D)은 시트로.
        if {a["조건"], b["조건"]} not in ({"A", "C"}, {"B", "C"}):
            return None, f"조건 {a['조건']}≠{b['조건']}"
        cond, dissent = "C", sorted((a["조건"], b["조건"]))
    base = {
        "조건": cond,
        # 합성된 C 는 예외 경로가 없다는 뜻이라 제외목을 싣지 않는다 — 이견은 `조건_이견` 과 원자료에 남는다
        "제외목": [] if dissent else sorted(set(a["제외목"]) & set(b["제외목"])),
        "원천결손": gap,
        "조건_이견": dissent,
        "근거_후보": [],
    }
    if cond == "D":
        return {**base, "근거": [], "제외목": []}, ""
    ha = {statute.ho_key(c): statute.parse(c)[4] for c in a["근거"]}
    hb = {statute.ho_key(c): statute.parse(c)[4] for c in b["근거"]}
    if cond == "M" and (not ha or not hb or set(ha) != set(hb)):
        return {**base, "근거": []}, ""  # 🔄 D-285 개정 — M 은 호를 추측으로 채우지 않는다
    if not ha or not hb:
        return None, f"조건 {cond} 인데 근거가 없다"
    common = set(ha) & set(hb)
    if not common:
        # 🔄 2026-09-25 (D-285 개정 2) — 조건(C·A·B)은 같고 호만 안 겹치면 **조건은 채택 · 근거는 후보 둘**.
        #    기대 응답(위반)이 같다 · 합집합은 「둘 다 걸린다」는 뜻이라 쓰지 않는다 — **어느 쪽을 인용해도 정답**.
        #    🔴 `근거` 가 비고 `labels` 도 빈다 → 조건 칸 없이 골든에 들어가면 적법으로 센다 (지시서 §7 선행 게이트)
        return {**base, "근거": [], "근거_후보": [sorted(a["근거"]), sorted(b["근거"])]}, ""
    cites = []
    cites = []
    for h in sorted(common):  # 🔄 09-24 밤 — 겹치면 둘 다 적은 호만 남긴다 (목과 같은 원리)
        law, jo, hang, ho, _ = statute.parse(h)
        mok = ha[h] if ha[h] == hb[h] else None
        cites.append(statute.cite(law, jo, hang, ho, mok))
    return {**base, "근거": cites}, ""


#: 🆕 2026-09-25 (D-289) — **표시요건**: 같은 광고 안에 밝혀야 적법해지는 것. 조문이 무엇을 밝히라는지 정한다 →
#: 부류별 규칙으로 붙인다(판독 메모 「표시요건」 + 문구 부류). 🚨 부류를 못 가리면 「미분류」로 **보이게** 남긴다 (D-220)
DISCLOSURE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"1위|1등|No\.? ?1|넘버원|순위", ("조사대상", "조사기관", "조사기간")),  # 고시 69549 4.나
    (
        r"논문|연구|학회|임상|저널|인체시험|인체적용|발표",
        ("연구자", "문헌명", "발표 연월일"),
    ),  # [별표 1] 5.가 단서
    (
        r"성적서|검사|검증된|불검출|검출되지|기준에 적합",
        ("시험·검사성적서 전문",),
    ),  # 고시 69549 3.아
    (r"100 ?%", ("첨가물 명칭 괄호 병기",)),  # 고시 69549 3.카
)


#: 3.나(기능성 고시)는 **법이 표시를 함께 요구한다** — 고시 75449 제6조(기능성 원재료·함량·1일 섭취기준량 ·
#: 「본 제품은 건강기능식품이 아닙니다」). 판독 메모와 무관하게 붙는다 (A + 표시 · D-289 표 4번)
FUNC_DISCLOSURE = ("기능성 고시 제6조 필수 표시",)


def disclosure_of(text: str, a: dict, b: dict, exc: list[str] | None = None) -> list[str]:
    """두 판독 중 하나라도 메모에 「표시요건」을 적었으면 문구 부류로 무엇을 밝혀야 하는지 붙인다.

    합집합이다 — 밝혀야 할 것을 빠뜨리면 분기가 「입증하면 된다」로 틀리게 안내한다(D-289 맥락 3).
    """
    if exc and "3.나" in exc:
        return list(FUNC_DISCLOSURE)
    if "표시요건" not in a["메모"] + b["메모"]:
        return []
    for rx, need in DISCLOSURE:
        if re.search(rx, text):
            return list(need)
    return ["미분류"]


#: 3.나(기능성 고시)를 적을 수 있는 원천 제품유형 — 지시서 §3 ⑦ · D-288. 고시 제3조② 가 나머지를 뺀다
NA_TYPES = ("9.",)
#: 주어가 **조제유류**인 목 — [별표 1] 5호 바목·사목. 해설서의 영아용·성장기용 **조제식**은 원천 정의가
#: 「… 다만, 조제유류는 제외」다 → 이 목을 그대로 채택하지 않고 시트로 (호 5 는 사람이 본다 · D-220)
FORMULA_MOK = {(5, "바"), (5, "사")}


def merge(
    r1: pathlib.Path,
    r2: pathlib.Path,
    rr1: pathlib.Path | None = None,
    rr2: pathlib.Path | None = None,
) -> dict:
    src = {r["지문"]: r for r in rows()}
    a, b = read(r1), read(r2)
    redo: set[str] = set()
    if rr1 or rr2:
        if not (rr1 and rr2):
            raise ValueError("재판독은 둘이 함께 온다 — 한쪽만 갈아 끼우면 독립 판독이 아니다")
        x, y = read(rr1), read(rr2)
        if set(x) != set(y):
            raise ValueError("두 재판독의 행이 다르다")
        if set(x) - set(src):
            raise ValueError(f"재판독에 모르는 행 {len(set(x) - set(src))}")
        a.update(x)
        b.update(y)
        redo = set(x)
    for name, got in (("판독1", a), ("판독2", b)):
        miss, extra = set(src) - set(got), set(got) - set(src)
        if miss or extra:
            raise ValueError(
                f"{name}: 빠진 행 {len(miss)} · 모르는 행 {len(extra)} — 전량이 아니면 합치지 않는다"
            )
    adopted, sheet, why = [], [], collections.Counter()
    READINGS.parent.mkdir(parents=True, exist_ok=True)
    with READINGS.open("w", encoding="utf-8", newline="\n") as f:
        for k in src:
            rec = {
                "지문": k,
                "판": "재판독" if k in redo else "첫판독",
                "판독1": a[k],
                "판독2": b[k],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for k, s in src.items():
        got, reason = agree(a[k], b[k])
        if (
            got is not None
            and not s["제품유형"].startswith(NA_TYPES)
            and ("3.나" in a[k]["제외목"] + b[k]["제외목"])
        ):
            got, reason = None, "3.나 유형 밖 (D-288)"
        if got is not None and any(
            statute.parse(c)[3:5] in FORMULA_MOK
            for c in got["근거"] + [x for cand in got["근거_후보"] for x in cand]
        ):  # 후보도 본다 — 한쪽 후보가 조제유류 목이면 그 후보를 정답으로 둘 수 없다
            got, reason = None, "조제유류 목 (5.바·5.사) — 원천 제품유형은 조제유류가 아니다"
        head = {
            "지문": k,
            "표": s["표"],
            "제품유형": s["제품유형"],
            "원천라벨": s["원천라벨"],
            "문구": s["문구"],
            "원천": s["원천"],
        }
        if got is None:
            why[reason.split(" ")[0]] += 1
            sheet.append({**head, "_우선": _priority(a[k], b[k])})
            continue
        adopted.append(
            {
                **head,
                **got,
                "표시요건": disclosure_of(s["문구"], a[k], b[k], got["제외목"])
                if got["조건"] in "ABC"
                else [],
                "labels": statute.types_of(got["근거"]),
                "판독": "독립판독_합의",
            }
        )
    with ADOPTED.open("w", encoding="utf-8", newline="\n") as f:
        for r in adopted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    cols = ["지문", "문구", "묶음", "제품유형", "근거", "조건", "제외목", "원천결손", "메모"]
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for h in sorted(sheet, key=lambda h: h["_우선"]):
            w.writerow([h["지문"], h["문구"], h["원천라벨"], h["제품유형"], "", "", "", "", ""])
    return {
        "전체": len(src),
        "재판독": len(redo),
        "채택": len(adopted),
        "채택_조건": dict(collections.Counter(r["조건"] for r in adopted)),
        "채택_근거후보": sum(1 for r in adopted if r["근거_후보"]),
        "채택_조건이견": dict(
            collections.Counter("·".join(r["조건_이견"]) for r in adopted if r["조건_이견"])
        ),
        "시트": len(sheet),
        "시트_이유": dict(why),
    }


#: 평가가 기대하는 응답 — 지시서 §2. 시트 정렬에만 쓴다
_EXPECT = {"C": "위반", "A": "위반", "B": "위반", "M": "보류", "D": "대상아님"}


def _priority(a: dict, b: dict) -> int:
    """시트 순서 — 기대 응답이 갈린 행이 먼저(평가 정답이 바뀐다) · 그다음 호 · 나머지."""
    if _EXPECT.get(a["조건"]) != _EXPECT.get(b["조건"]):
        return 0
    return 1 if a["조건"] == b["조건"] else 2


def write_input(out: pathlib.Path) -> int:
    """판독 입력 — 지문 · 문구 · 원천 묶음 · 제품유형. 🚨 다른 판독 결과는 싣지 않는다."""
    out.parent.mkdir(parents=True, exist_ok=True)
    rs = rows()
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in rs:
            f.write(f"{r['지문']}\t{r['문구']}\t{r['원천라벨']}\t{r['제품유형']}\n")
    return len(rs)


def main() -> int:
    ap = argparse.ArgumentParser(description="해설서 위반문구 조문·조건 판 (D-285)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_in = sub.add_parser("input")
    p_in.add_argument(
        "--out", type=pathlib.Path, default=ROOT / "build" / "labels" / "guide_statute__입력.tsv"
    )
    p_m = sub.add_parser("merge")
    p_m.add_argument("--r1", type=pathlib.Path, required=True)
    p_m.add_argument("--r2", type=pathlib.Path, required=True)
    p_m.add_argument("--rr1", type=pathlib.Path)
    p_m.add_argument("--rr2", type=pathlib.Path)
    a = ap.parse_args()
    if a.cmd == "input":
        print(f"판독 입력 {write_input(a.out):,}행 → {a.out}")
        return 0
    got = merge(a.r1, a.r2, a.rr1, a.rr2)
    print(json.dumps(got, ensure_ascii=False, indent=1))
    print(f"채택 → {ADOPTED}\n판정 시트(사람 2인) → {SHEET}\n두 판독 원자료 → {READINGS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
