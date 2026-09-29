"""scripts/guide_statute_round.py — 해설서 위반문구에 **조문 인용과 조건**을 붙이는 한 판 (2026-09-24 · D-285).

  uv run python -m scripts.guide_statute_round input  --out build/labels/guide_statute__입력.tsv
  uv run python -m scripts.guide_statute_round merge  --r1 <판독1.tsv> --r2 <판독2.tsv> [--rr1 <재판독1.tsv> --rr2 <재판독2.tsv>]
  uv run python -m scripts.guide_statute_round rebuild   # 판독 원자료만으로 채택·시트 (🆕 09-25 · TSV 없는 기기에서도)
  uv run python -m scripts.guide_statute_round import-decisions --csv <채운 팀장판정표.csv>   # 🆕 09-25 (D-285 개정 4) → rebuild

🚨 `-m` 으로 돌린다 — 스크립트로 돌리면 `scripts/collect.py` 가 `collect` 패키지를 가린다.

★ 흐름 (지시서 `docs/ohb/라벨링_지시서_2026-09-24_해설서_조문·조건.md` §5 · §6)
  1 input   1,834행을 판독 입력으로 낸다 — `지문` · 문구 · 원천 묶음 · 제품유형
  2 (판독)  독립 판독 둘이 각자 TSV 를 낸다 — 서로의 결과를 보지 않는다
  3 merge   둘이 **같으면** 채택(`판독` = `독립판독_합의`) · 다르면 사람 2인 시트로
            🔄 09-25 (D-285 개정 2) — 기대 응답이 같은 갈림(D↔M · 호만 안 겹침)은 규칙으로 채택 · 시트는 기대 응답이 갈리는 행
  4 (사람)  2인이 각자 시트를 채운다 → 팀장 판정표 · 경계 묶음은 팀장이 묶음 단위로 판정(지시서 §6)
            🔄 09-25 (D-285 개정 4) — `build/labels/guide_statute__팀장판정표.csv`(두 판독 나란히 · 빈 판정 칸)를 사람이 채우고
            `import-decisions` 가 `decisions.jsonl`(원천 · 판정자는 사람이 적는다)로 옮긴다 → `rebuild` 가 판독을 덮는다(`팀장판정`)
  5 평가    대기(시트 · 거래 조건)가 0 이 되면 `preprocess.split.guide_docs()` 가 채택본을 낸다 — 그 전에는 빈 목록

🔄 `scripts/label_round.py` 머리말의 「참고 답은 라벨이 아니다」는 **8유형 라운드**의 규칙이다.
   해설서 **조문 인용**은 D-285 가 독립 판독 둘의 합의를 채택한다 — 행마다 `판독` 칸으로 사람 판정과 가른다.

🔄 2026-09-24 밤 (D-285 개정 · D-288)
  · 조건 M 은 둘 다 M 이면 같다 — 근거는 두 판독의 호 집합이 같을 때만 남기고 아니면 빈 목록
  · `--rr1/--rr2` — 지시서 개정 뒤 **다시 읽은 행**(유형 9 의 3호·4.라 행)이 첫 판독을 **통째로** 갈아 끼운다. 원자료에 `판` 으로 남는다
  · 3.나 는 원천 제품유형 9 에서만 — 다른 유형에 적힌 판독은 채택하지 않고 시트로 (D-288)
  · 🔴 산출물은 `data/derived/labels/guide_statute/` — `readings.jsonl` 은 「원천」(다시 돌려도 같은 판독이 아니다) ·
    🔄 09-25 `adopted.jsonl` 은 「생성물」(`rebuild` 가 원자료에서 다시 낸다 · D-285 개정 3). `labels/*.jsonl` 을 읽는
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
import base64
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

from collect import registry, statute  # noqa: E402

READINGS = ROOT / "data" / "derived" / "labels" / "guide_statute" / "readings.jsonl"
ADOPTED = ROOT / "data" / "derived" / "labels" / "guide_statute" / "adopted.jsonl"
SHEET = ROOT / "build" / "labels" / "guide_statute__판정시트.csv"
#: 🆕 2026-09-25 (D-285 개정 4) — **팀장 판정**. 사람이 채운 CSV 를 `import-decisions` 가 옮긴다 — 부류 「원천」(사람의 판정 · `labels/`)
DECISIONS = ROOT / "data" / "derived" / "labels" / "guide_statute" / "decisions.jsonl"
#: 팀장 판정표 — 두 판독을 나란히 싣는다(지시서 §6 「팀장 판정표」). ⛔ 2인 시트(`SHEET`)는 판독을 싣지 않는다 — 둘은 다른 표다
TEAM_SHEET = ROOT / "build" / "labels" / "guide_statute__팀장판정표.csv"
TEAM_COLS = (
    "지문",
    "문구",
    "제품유형",
    "원천라벨",
    "대기사유",
    "판독1",
    "판독2",
    "주근거",
    "부근거",
    "조건",
    "제외목",
    "원천결손",
    "메모",
    "판정자",
)
#: 🆕 2026-09-25 (D-272 개정) — **사항이 거래 조건인 문구**는 합의만으로 채택하지 않는다. 식품표시광고법 제8조① 은
#: 시행령 제2조의 사항(명칭 · 성분 · 품질 …)에 관하여 걸리는데 가격 · 할인 · 환불은 그 목록에 없다 → 인용을 팀장이 정한다.
#: 🚨 [임의] 낱말 근사다(사실원장 09-25 ⑮ · 채택 12행) — 「특가」 · 「1+1」 · 「매출」 은 넣지 않았다(판정 전 범위를 넓히지 않는다)
TRADE = re.compile(r"가격|할인|환불|\d[\d,]*\s*원")

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
    """행 지문 — 표 · 원천 묶음 · 문구. 🚨 같은 문구가 한 제품의 다른 표(환자용 세부 품목)에 또 나온다 → 표까지 넣는다.

    🔄 2026-09-25 — **base32 소문자**(a–z · 2–7) 12자. 16진이던 때 `gs:ab0175558118` 의 숫자 꼬리가
       반출 검사의 휴대전화 꼴(`01[016789]…`)로 잡혔다. base32 에는 0 · 1 · 8 · 9 가 없어 휴대전화 ·
       주민등록번호 꼴이 **구조적으로 생기지 않는다** — 검사를 느슨하게 하지 않는다 (`scripts/derived_manifest.py`
       머리말 「재현율 쪽」 · D-133 ⑤). 옛 지문 → 새 지문은 같은 sha256 의 표기만 바꾼 것이다.
    """
    raw = f"{r['표']}|{r['원천라벨']}|{r['문구']}"
    return (
        "gs:" + base64.b32encode(hashlib.sha256(raw.encode("utf-8")).digest()).decode()[:12].lower()
    )


#: 지문 꼴 — 게이트가 대조한다 (`tests/test_guide_statute_round.py`)
KEY_RE = re.compile(r"^gs:[a-z2-7]{12}$")


def rows() -> list[dict]:
    """해설서 위반문구 전량 — `preprocess.mfds_guide` 추출 · 마스킹을 지난 사본 (D-159)."""
    from preprocess import mfds_guide as mg  # noqa: PLC0415

    if not mg.policy_or_stop():
        raise SystemExit(1)
    got, _ = mg.masked([r for r in mg.extract(mg._hwp()) if r["종류"] == "위반문구"])
    out = [{**r, "지문": key_of(r)} for r in got]
    # 🔴 변경금지(ND) 게이트 — 판독 시트도 파생 데이터셋이다 — ND 소스의 행이 들어오면 여기서 멈춘다 (2026-09-25 · `registry.assert_derivable`)
    registry.assert_derivable(out, who="guide_statute_round.rows")
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


def read(path: pathlib.Path, parse=None) -> dict[str, dict]:
    """판독 TSV → 지문별 레코드. `parse` 는 원천의 한 줄 해석기(기본 해설서 `parse_line` · 화장품 `cq_parse_line`).

    🆕 2026-09-30 (D-285 개정 5 · D-99) — 화장품 판독 TSV 는 머리줄(`지문\t…`)이 있다 — 첫 칸이 `지문` 인 줄은 건너뛴다.
    """
    parse = parse or parse_line
    got: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.split("\t", 1)[0].strip().lstrip("\ufeff") == "지문":
            continue
        r = parse(line)
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
    """판독 TSV 둘 → **판독 원자료**(`readings.jsonl` · 원천)를 쓰고 채택·시트를 계산한다."""
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
    _whole(src, a, b)
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
    return {"재판독": len(redo), **decide(src, a, b, load_decisions(src))}


def rebuild() -> dict:
    """🆕 2026-09-25 (D-285 개정 3) — **판독 원자료만으로** 채택·시트를 다시 계산한다.

    ★ 채택본은 「판독 원자료 + 채택 규칙」의 계산 결과다 — 규칙을 고칠 때마다 원천 손실 경보가 울리지 않게
       `data/derived/labels/guide_statute/adopted.jsonl` 을 **생성물**로 둔다(`scripts/derived_manifest.py` `KIND_RULES`).
       판독 TSV(판독자의 작업 파일)가 없는 기기에서도 이 명령으로 같은 채택본이 나온다.
    🔴 원자료가 없거나 원천 행과 어긋나면 멈춘다 — 빈 채택본을 쓰지 않는다 (D-220).
    """
    if not READINGS.exists():
        raise SystemExit(
            f"🔴 {READINGS} 가 없다 — 판독 원자료(원천)는 명령으로 다시 안 나온다. 공유 저장소에서 받는다"
        )
    src = {r["지문"]: r for r in rows()}
    a: dict[str, dict] = {}
    b: dict[str, dict] = {}
    redo = 0
    for line in READINGS.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        k = rec["지문"]
        if k in a:
            raise ValueError(f"판독 원자료에 지문이 두 번 — {k}")
        a[k], b[k] = rec["판독1"], rec["판독2"]
        redo += rec.get("판") == "재판독"
    _whole(src, a, b)
    return {"재판독": redo, **decide(src, a, b, load_decisions(src))}


def _whole(src: dict, a: dict, b: dict) -> None:
    """🔴 전량이 아니면 합치지 않는다 — 빠진 행이 「채택 안 됨」으로 조용히 사라지지 않게 (D-220)."""
    for name, got in (("판독1", a), ("판독2", b)):
        miss, extra = set(src) - set(got), set(got) - set(src)
        if miss or extra:
            raise ValueError(
                f"{name}: 빠진 행 {len(miss)} · 모르는 행 {len(extra)} — 전량이 아니면 합치지 않는다"
            )


def decide(src: dict, a: dict, b: dict, dec: dict[str, dict] | None = None) -> dict:
    """두 판독 → 채택본(`adopted.jsonl` · 생성물) · 판정 시트. `merge` 와 `rebuild` 가 **같은 함수**를 쓴다 (D-99).

    🔄 2026-09-25 (D-285 개정 4) — `dec`(팀장 판정 · `decisions.jsonl`)가 있는 행은 **판정이 판독을 덮는다**(`판독` = `팀장판정`).
       판정이 없는 행은 합의 규칙대로 · 거래 조건 사항은 합의여도 대기(D-272 개정).
    """
    dec = dec or {}
    adopted, sheet, why = [], [], collections.Counter()
    for k, s in src.items():
        head = {
            "지문": k,
            "표": s["표"],
            "제품유형": s["제품유형"],
            "원천라벨": s["원천라벨"],
            "문구": s["문구"],
            "원천": s["원천"],
        }
        if k in dec:
            d = dec[k]["판정"]
            got = {
                "조건": d["조건"],
                "근거": d["근거"],
                "근거_후보": [],
                "제외목": d["제외목"],
                "원천결손": d["원천결손"],
                "조건_이견": [],
            }
            adopted.append(
                {
                    **head,
                    **got,
                    "표시요건": disclosure_of(s["문구"], d, d, d["제외목"])
                    if d["조건"] in "ABC"
                    else [],
                    "labels": statute.types_of(d["근거"]),
                    "판독": "팀장판정",
                }
            )
            continue
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
        if got is not None and TRADE.search(s["문구"]):
            got, reason = None, "거래조건 사항 (D-272 개정) — 인용을 팀장이 정한다"
        if got is None:
            why[reason.split(" ")[0]] += 1
            sheet.append(
                {**head, "_우선": _priority(a[k], b[k]), "_이유": reason, "_a": a[k], "_b": b[k]}
            )
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
    order = sorted(sheet, key=lambda h: h["_우선"])
    cols = ["지문", "문구", "묶음", "제품유형", "근거", "조건", "제외목", "원천결손", "메모"]
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for h in order:
            w.writerow([h["지문"], h["문구"], h["원천라벨"], h["제품유형"], "", "", "", "", ""])
    with TEAM_SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(TEAM_COLS)
        for h in order:
            w.writerow(
                [
                    h["지문"],
                    h["문구"],
                    h["제품유형"],
                    h["원천라벨"],
                    h["_이유"],
                    _brief(h["_a"]),
                    _brief(h["_b"]),
                ]
                + [""] * 7
            )
    return {
        "전체": len(src),
        "채택": len(adopted),
        "채택_조건": dict(collections.Counter(r["조건"] for r in adopted)),
        "채택_판독": dict(collections.Counter(r["판독"] for r in adopted)),
        "채택_근거후보": sum(1 for r in adopted if r["근거_후보"]),
        "채택_조건이견": dict(
            collections.Counter("·".join(r["조건_이견"]) for r in adopted if r["조건_이견"])
        ),
        "시트": len(sheet),
        "시트_이유": dict(why),
    }


def _brief(r: dict) -> str:
    """판정표에 싣는 판독 한 줄 — 조건 · 근거(호.목) · 제외목 · 원천결손 · 메모."""
    cites = [
        f"{h}{'.' + m if m else ''}"
        for _law, _jo, _hang, h, m in (statute.parse(c) for c in r["근거"])
    ]
    parts = [r["조건"], ",".join(cites) or "-"]
    if r["제외목"]:
        parts.append("제외 " + ",".join(r["제외목"]))
    if r["원천결손"]:
        parts.append("원천결손")
    if r["메모"] not in ("", "-"):
        parts.append(r["메모"])
    return " · ".join(parts)


def load_decisions(src: dict | None = None, path: pathlib.Path | None = None) -> dict[str, dict]:
    """팀장 판정(원천). 없으면 빈 것. 🔴 모르는 지문이 있으면 멈춘다 — 조용히 버리지 않는다 (D-220).

    `path` 기본은 해설서 `DECISIONS` · 화장품은 `CQ_DECISIONS` (D-99 — 읽는 함수는 하나).
    """
    path = path or DECISIONS
    if not path.exists():
        return {}
    got: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            got[r["지문"]] = r
    if src is not None and set(got) - set(src):
        raise ValueError(f"팀장 판정에 모르는 지문 {len(set(got) - set(src))} — 원천이 바뀌었나")
    return got


def check_decision(rec: dict, kind: str) -> list[str]:
    """판정 한 행의 문제 — 합의 채택과 **같은 게이트**를 사람 판정에도 건다 (D-238 · D-288 · 지시서 §1)."""
    bad = list(rec["문제"])
    if rec["조건"] in ("C", "A", "B") and not rec["근거"]:
        bad.append(f"조건 {rec['조건']} 인데 근거가 없다")
    if rec["조건"] == "D" and rec["근거"]:
        bad.append("조건 D 는 근거가 빈다")
    if "3.나" in rec["제외목"] and not kind.startswith(NA_TYPES):
        bad.append("3.나 는 제품유형 9 만 (D-288)")
    if any(statute.parse(c)[3:5] in FORMULA_MOK for c in rec["근거"]):
        bad.append("조제유류 목(5.바·5.사) — 원천 제품유형은 조제유류가 아니다")
    return bad


def import_decisions(path: pathlib.Path) -> dict:
    """사람이 채운 팀장 판정표 CSV → `decisions.jsonl`. 🔴 `판정자` 는 사람이 적는다 — 비면 그 행을 받지 않는다.

    ★ 칸의 꼴은 판독 TSV 와 같다(`parse_line` 을 그대로 쓴다 · D-99) — 주근거 `5.다` · `3` · `법8-9` / 조건 C·A·B·M·D /
      제외목 `3.라,1.가.1` / 원천결손 Y·N. 조건이 빈 행은 아직 판정하지 않은 행이라 건너뛴다.
    🔴 한 행이라도 문제가 있으면 **아무것도 쓰지 않는다** — 반쯤 들어간 판정은 되돌리기 어렵다 (D-220).
    """
    kinds = {}
    for x in ADOPTED.read_text(encoding="utf-8").splitlines() if ADOPTED.exists() else []:
        r = json.loads(x)
        kinds[r["지문"]] = r["제품유형"]

    def to_line(k: str, row: dict) -> str | None:
        if not (row.get("조건") or "").strip():
            return None
        return "\t".join(
            [
                k,
                (row.get("주근거") or "-").strip() or "-",
                (row.get("부근거") or "-").strip() or "-",
                row["조건"].strip(),
                (row.get("제외목") or "-").strip() or "-",
                (row.get("원천결손") or "N").strip() or "N",
                (row.get("메모") or "").strip(),
            ]
        )

    return _import_sheet(
        path,
        readings=READINGS,
        decisions=DECISIONS,
        to_line=to_line,
        parse=parse_line,
        check=lambda rec, k, row: check_decision(rec, kinds.get(k) or row.get("제품유형") or ""),
    )


def _import_sheet(
    path: pathlib.Path,
    *,
    readings: pathlib.Path,
    decisions: pathlib.Path,
    to_line,
    parse,
    check,
) -> dict:
    """🆕 2026-09-30 (D-285 개정 5 · D-99) — 팀장 판정표 CSV → 판정 원천. **해설서와 화장품이 같은 함수**를 쓴다.

    `to_line(지문, 행)` 은 판정표 한 행을 그 원천의 판독 TSV 한 줄로 바꾼다 — 판정하지 않은 행이면 None(건너뜀).
    `check(판독, 지문, 행)` 은 합의 채택과 같은 게이트를 사람 판정에 건다.
    🔴 한 행이라도 문제가 있으면 **아무것도 쓰지 않는다** (D-220) · 판정자가 비면 받지 않는다(사람이 적는 칸).
    """
    src = {
        json.loads(x)["지문"]
        for x in readings.read_text(encoding="utf-8").splitlines()
        if x.strip()
    }
    got, bad, skipped = {}, [], 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        for no, row in enumerate(csv.DictReader(f), 2):
            k = (row.get("지문") or "").strip()
            line = to_line(k, row)
            if line is None:
                skipped += 1
                continue
            if k not in src:
                bad.append(f"{no}행 모르는 지문 {k!r}")
                continue
            who = (row.get("판정자") or "").strip()
            if not who:
                bad.append(f"{no}행 {k} 판정자가 비었다 — 사람이 적는 칸이다")
                continue
            rec = parse(line)
            probs = check(rec, k, row)
            if probs:
                bad.append(f"{no}행 {k} — " + " / ".join(probs))
                continue
            rec.pop("문제")
            got[k] = {"지문": k, "판정": rec, "판정자": who}
    if bad:
        raise SystemExit(
            "🔴 팀장 판정표에 문제가 있다 — **아무것도 쓰지 않았다**\n  " + "\n  ".join(bad[:30])
        )
    old = load_decisions(path=decisions)
    replaced = sorted(set(old) & set(got))
    merged = {**old, **got}
    decisions.parent.mkdir(parents=True, exist_ok=True)
    with decisions.open("w", encoding="utf-8", newline="\n") as f:
        for k in sorted(merged):
            f.write(json.dumps(merged[k], ensure_ascii=False) + "\n")
    return {
        "받음": len(got),
        "바꿈": len(replaced),
        "건너뜀(조건 빈 행)": skipped,  # 화장품은 대상·조건이 둘 다 빈 행
        "판정 합계": len(merged),
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


# ══ 문구 판 — 화장품 질의응답집 · 공정위 보도자료 (2026-09-30 · D-285 개정 5 · D-99) ══════════════════
#
# ★ 해설서 판과 **같은 함수**를 쓴다(D-99 · 화장품 지시서 §7 「사본을 만들지 않는다」) — `read` · `_whole` · `agree`(보수 합성 ·
#   D↔M → M · 호만 안 겹침 → 후보) · `load_decisions` · `_import_sheet`. 원천이 둘(화장품 `cq` · 보도자료 `fp`)이라
#   원천마다 다른 것은 `Round` 한 벌에 모았다 — 나머지 함수는 원천을 모른다. 원천만의 것은 아래 넷이다.
#     ① 판독 한 줄의 꼴 — `지문 \t 대상 \t 주근거 \t 부근거 \t 별표5목 \t 조건 \t 제외목 \t 메모` (원천결손 칸이 없다)
#        근거 코드 · 제외목 값 · 별표5목 표가 원천마다 다르다(`Round.cite_of` · `exceptions` · `mok_ho`)
#     ② `대상` — 둘 다 N 이면 평가에서 뺀다(채택본에 `대상: N` 으로 남긴다 · 대기 아님) · 하나만 N 이면 시트 (지시서 §5)
#     ③ 조건 `L`(적법) — **합성하지 않는다**: 둘 다 L 일 때만 채택 · L ↔ 그 밖은 전부 시트 (지시서 §5 · 기대 응답이 정반대)
#     ④ `별표5목` — 둘이 같을 때만 남긴다 · 한 판독 안에서 목 ↔ 주근거가 §1-1 표와 어긋나면 그 판독은 문제(시트로) · 화장품만
# 🚨 해설서 쪽 규칙(3.나 유형 · 조제유류 목 · 거래 조건 · 표시요건 부류)은 **식품 [별표 1] 규칙**이라 여기 걸지 않는다.
#    화장품 표시요건은 판독 `메모` 에만 있다 — ⬜ 부류 규칙은 화장품 지침 [별표 2] 로 따로 정할 때 (지금은 싣지 않는다).
#
# 🔴 **단위(지문 ↔ 문구) 표는 판독 원자료가 들고 있다.** 두 원천 다 원천 대조를 건다 — 원천이 바뀌어 문구가 사라지면 멈춘다 (D-220).
#    · 화장품 — 09-25 시험 판독 때 단위를 뽑은 스크립트가 저장소에 없고 지문 규칙도 되살리지 못했다(2026-09-30 실측).
#      ⛔ 그래서 지문을 다시 계산하지 않는다. 단위마다 그 문항의 `인용표현` 에 문구가 그대로 있어야 한다(`cq_units`).
#    · 보도자료 — 지문은 `fp_key_of`(사건 · 마스킹 전 문구의 sha256) · 문구는 **마스킹된** 사건 본문에 공백만 다르게 있어야
#      한다(`fp_units`). 원천 레코드는 `preprocess.ftc_press_old` 가 낸다.

import dataclasses  # noqa: E402
from collections.abc import Callable  # noqa: E402

CQ_SOURCE = "mfds_cosmetic_ad_qa"
CQ_QA = ROOT / "data" / "derived" / "mfds_cosmetic_ad_qa.jsonl"
CQ_DIR = ROOT / "data" / "derived" / "labels" / "cosmetic_qa"
#: 판독 원자료 — 「원천」(다시 돌려도 같은 판독이 아니다) · 단위 표(문항 · 자리 · 문구)를 함께 싣는다
CQ_READINGS = CQ_DIR / "readings.jsonl"
#: 채택본 — 「생성물」(`cq-rebuild` 가 원자료 + 판정에서 다시 낸다)
CQ_ADOPTED = CQ_DIR / "adopted.jsonl"
#: 팀장 판정 · 합의 감사 — 「원천」(사람이 적는다)
CQ_DECISIONS = CQ_DIR / "decisions.jsonl"
CQ_AUDIT = CQ_DIR / "audit.jsonl"
#: 🚨 `build/labels/cosmetic_qa/팀장판정표.csv`(09-25 · 사람이 채우는 중일 수 있다)를 **덮지 않는다** — 계산된 시트는 다른 이름
CQ_TEAM_SHEET = ROOT / "build" / "labels" / "cosmetic_qa__팀장판정표.csv"
CQ_KEY_RE = re.compile(r"^cq:[a-z2-7]{12}$")
#: 지시서 §2 — L(조건 없이 적법)을 더한다
CQ_CONDITIONS = (*CONDITIONS, "L")
#: 지시서 §3-3 — 이 문구를 적법하게 만들 수 있는 예외. 🔴 `근거` 에 오지 않는다 (D-238)
CQ_EXCEPTIONS = frozenset(
    ("기능성심사", "실증", "보습일시", "색조연출", "문헌인용", "천연유기농안내서")
)
#: 지시서 §1-1 — 시행규칙 [별표 5] 제2호의 목 → 화장품법 제13조제1항 호. 🔶 다~카 → 4 는 해석이다(팀장 확인 대상)
CQ_MOK_HO = {"가": 1, "나": 2, **{m: 4 for m in "다라마바사아자차카"}}

#: 🆕 2026-09-30 (동결 전 판정 ⑤-1·3 (나)) — 공정위 보도자료 1997~2007 · 지시서 `라벨링_지시서_2026-09-30_공정위보도자료_…`
FP_SOURCE = "ftc_press"
FP_CASES = ROOT / "data" / "derived" / "ftc_press_old.jsonl"
FP_DIR = ROOT / "data" / "derived" / "labels" / "ftc_press_old"
FP_READINGS = FP_DIR / "readings.jsonl"
FP_ADOPTED = FP_DIR / "adopted.jsonl"
FP_DECISIONS = FP_DIR / "decisions.jsonl"
FP_AUDIT = FP_DIR / "audit.jsonl"
FP_TEAM_SHEET = ROOT / "build" / "labels" / "ftc_press_old__팀장판정표.csv"
FP_KEY_RE = re.compile(r"^fp:[a-z2-7]{12}$")
#: 지시서 §1 — `실증`(표시광고법 제5조)만
FP_EXCEPTIONS = frozenset(("실증",))

TEAM_TAIL = (
    "대기사유",
    "판독1",
    "판독2",
    "대상",
    "주근거",
    "부근거",
    "별표5목",
    "조건",
    "제외목",
    "메모",
    "판정자",
)


def cq_cite_of(code: str) -> str:
    """화장품 판독 코드 → 인용. `1` · `2` · `4` = 화장품법 §13① 호 · `공1`~`공4` = 표시광고법 §3① 호.

    🔴 `3`(천연·유기농 오인)은 2025-01-31 **삭제**된 호다 — 적으면 멈춘다(지시서 §1-1). 모르는 꼴도 멈춘다 (D-220).
    """
    code = code.strip()
    if code in CQ_EXCEPTIONS:
        raise ValueError(f"예외(제외목)는 근거가 아니다: {code!r}")
    if code == "3":
        raise ValueError(
            "화장품법 제13조제1항제3호는 2025-01-31 삭제됐다 — 천연·유기농은 4호 (지시서 §1-1)"
        )
    if code in ("1", "2", "4"):
        return statute.cite(*statute.COSM, int(code))
    return fp_cite_of(code)


def fp_cite_of(code: str) -> str:
    """보도자료 판독 코드 → 인용. `공1`~`공4` = 표시광고법 §3① 호만 (지시서 §1). 모르는 꼴은 멈춘다 (D-220)."""
    m = re.fullmatch(r"공([1-4])", code.strip())
    if not m:
        raise ValueError(f"근거 코드 꼴이 아니다: {code!r}")
    return statute.fair(int(m.group(1)))


def fp_key_of(case: str, phrase: str) -> str:
    """보도자료 문구의 지문 — 사건 번호 · 공백을 하나로 접은 **마스킹 전** 문구. base32 소문자 12자(`key_of` 와 같은 이유)."""
    raw = f"{case}|" + re.sub(r"\s+", " ", phrase).strip()
    return (
        "fp:" + base64.b32encode(hashlib.sha256(raw.encode("utf-8")).digest()).decode()[:12].lower()
    )


@dataclasses.dataclass(frozen=True)
class Round:
    """원천 하나의 문구 판 설정. 🚨 경로는 **모듈 전역 이름**으로 든다(`{prefix}_READINGS` …) — 게이트가 임시 폴더로 갈아 끼운다."""

    prefix: str
    cmd: str
    cite_of: Callable[[str], str]
    exceptions: frozenset[str]
    mok_ho: dict[str, int]
    #: 단위 표에서 채택본 · 판정표로 옮겨 싣는 칸(지문 · 문구 · 원천 말고)
    head: tuple[str, ...]
    #: 판정표에 싣는 칸(지문 · 문구 말고) — 정렬도 이 순서
    sheet_head: tuple[str, ...]
    units: Callable[[list[dict]], dict[str, dict]]

    def path(self, name: str) -> pathlib.Path:
        return globals()[f"{self.prefix}_{name}"]


def _parse(R: Round, line: str) -> dict:
    """문구 판 판독 TSV 한 줄 → 레코드. 해설서 `parse_line` 과 같은 칸 이름을 쓴다(`agree` 가 그대로 읽는다 · D-99)."""
    p = line.rstrip("\n").split("\t")
    if len(p) < 7:
        raise ValueError(f"칸이 모자란다({len(p)}): {line[:80]!r}")
    p += [""] * (8 - len(p))
    key, target, prim, sec, mok, cond, exc, memo = (x.strip() for x in p[:8])
    rec = {
        "지문": key,
        "대상": target,
        "조건": cond,
        "근거": [],
        "별표5목": "",
        "제외목": [],
        "원천결손": False,  # 이 판독에는 이 칸이 없다 — `agree` 가 읽으므로 거짓으로 둔다
        "메모": memo,
        "문제": [],
    }
    if target == "N":
        # 대상 아님 — 뒤 칸은 `-` 여야 한다 (지시서 §1). 🚨 적힌 것이 있으면 판독 문제로 시트에 보낸다
        rest = [x for x in (prim, sec, mok, cond, exc) if x not in ("", "-")]
        if rest:
            rec["문제"].append(f"대상 N 인데 칸이 적혔다 {rest}")
        rec["조건"] = ""
        return rec
    if target != "Y":
        rec["문제"].append(f"대상 {target!r}")
        return rec
    if cond not in CQ_CONDITIONS:
        rec["문제"].append(f"조건 {cond!r}")
    for c in (prim, sec):
        if c in ("", "-"):
            continue
        if c.startswith("기타:"):
            rec["문제"].append(f"인용 꼴 밖 {c}")
            continue
        if c in R.exceptions:
            rec["문제"].append(f"예외(제외목)는 근거가 아니다: {c!r}")
            continue
        try:
            rec["근거"].append(R.cite_of(c))
        except ValueError as e:
            rec["문제"].append(str(e))
    if mok not in ("", "-"):
        if mok not in R.mok_ho:
            rec["문제"].append(f"모르는 별표5목 {mok!r}")
        elif prim != str(R.mok_ho[mok]):
            # 지시서 §1-1 · §5 — 목과 주근거가 표와 어긋나면 합의여도 시트
            rec["문제"].append(f"별표5목 {mok} 는 {R.mok_ho[mok]}호인데 주근거가 {prim!r}")
        else:
            rec["별표5목"] = mok
    for e in (x.strip() for x in exc.split(",")):
        if e in ("", "-"):
            continue
        if e in R.exceptions:
            rec["제외목"].append(e)
        else:
            rec["문제"].append(f"모르는 제외목 {e!r}")
    if cond in ("D", "L") and rec["근거"]:
        rec["문제"].append(f"조건 {cond} 는 근거가 빈다")
    return rec


def _agree(R: Round, a: dict, b: dict) -> tuple[dict | None, str]:
    """두 판독이 같은가 (지시서 §5). 해설서 `agree` 앞에 대상 · L 을 걸고, 뒤에 별표5목을 붙인다."""
    if a["문제"] or b["문제"]:
        return None, "판독 문제 — " + " / ".join(a["문제"] + b["문제"])
    if a["대상"] != b["대상"]:
        return None, f"대상 {a['대상']}≠{b['대상']}"
    if a["대상"] == "N":
        return {"대상": "N"}, ""
    if "L" in (a["조건"], b["조건"]):
        if a["조건"] != b["조건"]:
            return None, f"조건 {a['조건']}≠{b['조건']} — L(적법)은 합성하지 않는다"
        return {
            "대상": "Y",
            "조건": "L",
            "근거": [],
            "근거_후보": [],
            "별표5목": "",
            "제외목": [],
            "원천결손": False,
            "조건_이견": [],
        }, ""
    got, why = agree(a, b)
    if got is None:
        return None, why
    mok = a["별표5목"] if a["별표5목"] == b["별표5목"] else ""
    # 목은 그 호가 채택 근거에 남았을 때만 싣는다 — M 으로 근거가 비었거나 후보로 갈렸으면 뗀다
    if mok and statute.cite(*statute.COSM, R.mok_ho[mok]) not in {
        statute.ho_key(c) for c in got["근거"]
    }:
        mok = ""
    return {"대상": "Y", **got, "별표5목": mok}, ""


def _units_fail(what: str, bad: list[str]) -> None:
    if bad:
        raise SystemExit(
            f"🔴 {what} 단위 표가 원천과 어긋난다 {len(bad)} — 쓰지 않는다\n  "
            + "\n  ".join(bad[:10])
        )


def _key_ok(re_: re.Pattern, k: str, seen: dict, bad: list[str]) -> bool:
    if not re_.match(k):
        bad.append(f"지문 꼴 {k!r}")
        return False
    if k in seen:
        bad.append(f"지문이 두 번 {k}")
        return False
    return True


def cq_units(units: list[dict]) -> dict[str, dict]:
    """단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 단위의 문구가 그 문항의 `인용표현` 에 그대로 있어야 한다 (머리 주석)."""
    if not CQ_QA.exists():
        raise SystemExit(
            f"🔴 {CQ_QA} 가 없다 — 먼저: uv run python -m preprocess.mfds_cosmetic_qa --dump"
        )
    qa = {}
    for x in CQ_QA.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if r.get("분야") == "화장품":
                qa[int(r["문항"])] = r
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(CQ_KEY_RE, k, src, bad):
            continue
        q = qa.get(int(u["문항"]))
        if q is None or u["문구"] not in q["인용표현"]:
            bad.append(f"{k} Q{u['문항']} 원천 인용표현에 없는 문구 {u['문구'][:30]!r}")
            continue
        src[k] = {
            "지문": k,
            "문항": int(u["문항"]),
            "자리": u["자리"],
            "문구": u["문구"],
            "원천": CQ_SOURCE,
        }
    _units_fail("화장품", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.cq_units")
    return src


_WS = re.compile(r"\s+")


def fp_units(units: list[dict]) -> dict[str, dict]:
    """보도자료 단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 문구가 그 사건의 **마스킹된** 본문에 공백만 다르게 있어야 한다.

    🔴 **마스킹된 문구만 받는다** (`마스킹: true` · D-72). 문구 마스킹은 원문을 읽는 추출기가 **본문 안에서** 건다
       (`python -m preprocess.ftc_press_old --dump --units <단위.json>` → `data/derived/ftc_press_old_units.jsonl`).
       ⛔ 여기서 문구만 따로 마스킹했더니 본문에서는 지워진 상호가 문구에 남았다(34657 · 2026-09-30 실측) — `scripts/` 는
          원문을 못 읽으므로(D-116) 문맥 마스킹을 여기서 할 수 없다.
    """
    if not FP_CASES.exists():
        raise SystemExit(
            f"🔴 {FP_CASES} 가 없다 — 먼저: uv run python -m preprocess.ftc_press_old --dump"
        )
    cases = {}
    for x in FP_CASES.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            cases[r["사건"]] = _WS.sub("", r["본문"])
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(FP_KEY_RE, k, src, bad):
            continue
        if u.get("마스킹") is not True:
            bad.append(
                f"{k} 마스킹 전 문구다 — `preprocess.ftc_press_old --dump --units` 가 낸 파일을 넘긴다"
            )
            continue
        body = cases.get(str(u["사건"]))
        if body is None or _WS.sub("", u["문구"]) not in body:
            bad.append(f"{k} 사건 {u['사건']} 본문에 없는 문구 {u['문구'][:30]!r}")
            continue
        src[k] = {
            "지문": k,
            "사건": str(u["사건"]),
            "원천판단": u["원천판단"],
            "문구": u["문구"],
            "마스킹": True,
            "원천": FP_SOURCE,
        }
    _units_fail("보도자료", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.fp_units")
    return src


CQ = Round(
    prefix="CQ",
    cmd="cq",
    cite_of=cq_cite_of,
    exceptions=CQ_EXCEPTIONS,
    mok_ho=CQ_MOK_HO,
    head=("문항", "자리"),
    sheet_head=("문항",),
    units=lambda us: cq_units(us),
)
FP = Round(
    prefix="FP",
    cmd="fp",
    cite_of=fp_cite_of,
    exceptions=FP_EXCEPTIONS,
    mok_ho={},
    head=("사건", "원천판단", "마스킹"),
    sheet_head=("사건", "원천판단"),
    units=lambda us: fp_units(us),
)


def _merge(R: Round, units: pathlib.Path, r1: pathlib.Path, r2: pathlib.Path) -> dict:
    """단위 표(JSON 목록) + 판독 TSV 둘 → **판독 원자료**(원천)를 쓰고 채택·시트를 계산한다."""
    txt = units.read_text(encoding="utf-8")
    # 단위 표는 JSON 목록(화장품 `단위.json`) 또는 JSON Lines(보도자료 — 추출기가 낸 `ftc_press_old_units.jsonl`)
    got = (
        [json.loads(x) for x in txt.splitlines() if x.strip()]
        if units.suffix == ".jsonl"
        else json.loads(txt)
    )
    src = R.units(got)
    parse = lambda line: _parse(R, line)  # noqa: E731
    a, b = read(r1, parse), read(r2, parse)
    _whole(src, a, b)
    out = R.path("READINGS")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for k, s in src.items():
            rec = {"지문": k, **{h: s[h] for h in R.head}, "문구": s["문구"]}
            f.write(json.dumps({**rec, "판독1": a[k], "판독2": b[k]}, ensure_ascii=False) + "\n")
    return _decide(R, src, a, b, load_decisions(src, R.path("DECISIONS")))


def _rebuild(R: Round) -> dict:
    """판독 원자료만으로 채택·시트를 다시 계산한다 — 해설서 `rebuild` 와 같은 자리 (D-285 개정 3)."""
    p = R.path("READINGS")
    if not p.exists():
        raise SystemExit(
            f"🔴 {p} 가 없다 — 판독 원자료(원천)는 명령으로 다시 안 나온다. 공유 저장소에서 받는다"
        )
    recs = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    src = R.units(recs)
    a = {r["지문"]: r["판독1"] for r in recs}
    b = {r["지문"]: r["판독2"] for r in recs}
    _whole(src, a, b)
    return _decide(R, src, a, b, load_decisions(src, R.path("DECISIONS")))


def _decide(R: Round, src: dict, a: dict, b: dict, dec: dict[str, dict] | None = None) -> dict:
    """두 판독 → 채택본(생성물) · 팀장 판정표. 🔴 대상 N 행도 채택본에 남긴다(`대상: N`) — 대기와 가르려고.

    팀장 판정(`dec`)이 있는 행은 판정이 판독을 덮는다(`판독` = `팀장판정`) — 해설서 `decide` 와 같다.
    """
    dec = dec or {}
    adopted, sheet, why = [], [], collections.Counter()
    for k, s in src.items():
        head = {"지문": k, **{h: s[h] for h in R.head}, "문구": s["문구"], "원천": s["원천"]}
        if k in dec:
            d = dec[k]["판정"]
            got = {"대상": d["대상"]}
            if d["대상"] == "Y":
                got |= {
                    "조건": d["조건"],
                    "근거": d["근거"],
                    "근거_후보": [],
                    "별표5목": d["별표5목"],
                    "제외목": d["제외목"],
                    "원천결손": False,
                    "조건_이견": [],
                }
            how = "팀장판정"
        else:
            got, reason = _agree(R, a[k], b[k])
            if got is None:
                why[reason.split(" ")[0]] += 1
                sheet.append({**head, "_이유": reason, "_a": a[k], "_b": b[k]})
                continue
            how = "독립판독_합의"
        row = {**head, **got, "판독": how}
        if got["대상"] == "Y":
            row["labels"] = statute.types_of(got["근거"])
        adopted.append(row)
    out = R.path("ADOPTED")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in adopted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    team = R.path("TEAM_SHEET")
    team.parent.mkdir(parents=True, exist_ok=True)
    with team.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(("지문", *R.sheet_head, "문구", *TEAM_TAIL))
        for h in sorted(sheet, key=lambda h: (*(h[x] for x in R.sheet_head), h["지문"])):
            w.writerow(
                [h["지문"], *(h[x] for x in R.sheet_head), h["문구"], h["_이유"]]
                + [_brief_line(h["_a"]), _brief_line(h["_b"])]
                + [""] * 8
            )
    ys = [r for r in adopted if r["대상"] == "Y"]
    return {
        "전체": len(src),
        "채택": len(adopted),
        "채택_대상아님(N)": len(adopted) - len(ys),
        "채택_조건": dict(collections.Counter(r["조건"] for r in ys)),
        "채택_판독": dict(collections.Counter(r["판독"] for r in adopted)),
        "채택_근거후보": sum(1 for r in ys if r["근거_후보"]),
        "채택_조건이견": dict(
            collections.Counter("·".join(r["조건_이견"]) for r in ys if r["조건_이견"])
        ),
        "시트": len(sheet),
        "시트_이유": dict(why),
    }


def _brief_line(r: dict) -> str:
    """판정표에 싣는 판독 한 줄 — 대상 · 조건 · 호 · 목 · 제외목 · 메모."""
    if r["대상"] == "N":
        return "N" + (f" — {r['메모']}" if r["메모"] not in ("", "-") else "")
    cites = [
        ("공" if law == statute.FAIR[0] else "") + str(h)
        for law, _jo, _hang, h, _m in (statute.parse(c) for c in r["근거"])
    ]
    parts = [r["대상"], r["조건"], ",".join(cites) or "-", r["별표5목"] or "-"]
    if r["제외목"]:
        parts.append("제외 " + ",".join(r["제외목"]))
    if r["문제"]:
        parts.append("문제 " + " / ".join(r["문제"]))
    if r["메모"] not in ("", "-"):
        parts.append(r["메모"])
    return " · ".join(parts)


def _to_line(k: str, row: dict) -> str | None:
    """팀장 판정표(또는 감사표) 한 행 → 판독 TSV 한 줄. 대상 · 조건이 둘 다 비면 판정 안 한 행(None)."""
    target = (row.get("대상") or "").strip()
    cond = (row.get("조건") or "").strip()
    if not (target or cond):
        return None
    cell = lambda c: (row.get(c) or "-").strip() or "-"  # noqa: E731
    return "\t".join(
        [
            k,
            target,
            cell("주근거"),
            cell("부근거"),
            cell("별표5목"),
            cond or "-",
            cell("제외목"),
            (row.get("메모") or "").strip(),
        ]
    )


def _check_decision(rec: dict) -> list[str]:
    """문구 판 판정 한 행의 문제 — 판독 해석기가 잡은 것 + C·A·B 인데 근거가 없는 것."""
    bad = list(rec["문제"])
    if rec["대상"] == "Y" and rec["조건"] in ("C", "A", "B") and not rec["근거"]:
        bad.append(f"조건 {rec['조건']} 인데 근거가 없다")
    return bad


def _import(R: Round, path: pathlib.Path) -> dict:
    """사람이 채운 팀장 판정표 CSV → 판정(원천). 해설서와 같은 함수(`_import_sheet`)다 (D-99).

    ★ 읽는 칸은 지문 · 대상 · 주근거 · 부근거 · 별표5목 · 조건 · 제외목 · 메모 · 판정자다 — 다른 칸(검토의견 등)은 보지 않는다.
    """
    return _import_sheet(
        path,
        readings=R.path("READINGS"),
        decisions=R.path("DECISIONS"),
        to_line=_to_line,
        parse=lambda line: _parse(R, line),
        check=lambda rec, k, row: _check_decision(rec),
    )


def cq_same(x: dict, y: dict) -> bool:
    """감사 대조 — 기대 응답을 정하는 셋이 같은가: 대상 · 조건 · 호 집합 (지시서 §5 「같다」에서 목을 뺀 것)."""
    if x["대상"] != y["대상"]:
        return False
    if x["대상"] == "N":
        return True
    hx = {statute.ho_key(c) for c in x["근거"]}
    hy = {statute.ho_key(c) for c in y["근거"]}
    return x["조건"] == y["조건"] and hx == hy


def _audit(R: Round, path: pathlib.Path) -> dict:
    """합의 감사(지시서 §6 · D-285 개정 5) — 판독을 **보지 않고** 붙인 감사표 → 감사(원천) · 합의 정확도.

    🔴 감사 행은 **합의로 채택된 행**이어야 한다(팀장 판정 행 · 시트 행을 감사하면 그 수는 합의 정확도가 아니다).
    🔴 판정자가 빈 행 · 판독 문제가 있는 행이 하나라도 있으면 아무것도 쓰지 않는다 (D-220).
    ⬜ 정확도가 몇 이하면 전체를 다시 볼지는 정하지 않았다 — 수만 낸다(판정은 팀장).
    """
    ad = R.path("ADOPTED")
    took = {}
    for x in ad.read_text(encoding="utf-8").splitlines() if ad.exists() else []:
        r = json.loads(x)
        took[r["지문"]] = r
    got, bad = [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for no, row in enumerate(csv.DictReader(f), 2):
            k = (row.get("지문") or "").strip()
            line = _to_line(k, row)
            if line is None:
                continue
            who = (row.get("판정자") or "").strip()
            if not who:
                bad.append(f"{no}행 {k} 판정자가 비었다")
                continue
            r = took.get(k)
            if r is None or r["판독"] != "독립판독_합의":
                bad.append(f"{no}행 {k} 합의 채택 행이 아니다({r and r['판독']})")
                continue
            rec = _parse(R, line)
            if rec["문제"]:
                bad.append(f"{no}행 {k} — " + " / ".join(rec["문제"]))
                continue
            rec.pop("문제")
            base = {"대상": r["대상"], "조건": r.get("조건", ""), "근거": r.get("근거") or []}
            got.append({"지문": k, "감사": rec, "판정자": who, "일치": cq_same(rec, base)})
    if bad:
        raise SystemExit(
            "🔴 감사표에 문제가 있다 — **아무것도 쓰지 않았다**\n  " + "\n  ".join(bad[:30])
        )
    out = R.path("AUDIT")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(got, key=lambda r: r["지문"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hit = sum(r["일치"] for r in got)
    return {
        "감사": len(got),
        "일치": hit,
        "합의정확도": f"{hit / len(got):.1%}" if got else None,
        "불일치": [r["지문"] for r in got if not r["일치"]],
    }


# ── 원천별 이름 — 게이트 · 명령이 부르는 자리 (본체는 위 `_*` 하나 · D-99) ──────────────────────────────────
def cq_parse_line(line: str) -> dict:
    return _parse(CQ, line)


def cq_agree(a: dict, b: dict) -> tuple[dict | None, str]:
    return _agree(CQ, a, b)


def cq_merge(units: pathlib.Path, r1: pathlib.Path, r2: pathlib.Path) -> dict:
    return _merge(CQ, units, r1, r2)


def cq_rebuild() -> dict:
    return _rebuild(CQ)


def cq_decide(src: dict, a: dict, b: dict, dec: dict[str, dict] | None = None) -> dict:
    return _decide(CQ, src, a, b, dec)


def cq_import_decisions(path: pathlib.Path) -> dict:
    return _import(CQ, path)


def cq_audit(path: pathlib.Path) -> dict:
    return _audit(CQ, path)


def fp_parse_line(line: str) -> dict:
    return _parse(FP, line)


def fp_merge(units: pathlib.Path, r1: pathlib.Path, r2: pathlib.Path) -> dict:
    return _merge(FP, units, r1, r2)


def fp_rebuild() -> dict:
    return _rebuild(FP)


def fp_import_decisions(path: pathlib.Path) -> dict:
    return _import(FP, path)


def fp_audit(path: pathlib.Path) -> dict:
    return _audit(FP, path)


ROUNDS = {"cq": (CQ, "화장품"), "fp": (FP, "공정위 보도자료 1997~2007")}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="해설서 · 화장품 · 공정위 보도자료 조문·조건 판 (D-285)"
    )
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
    sub.add_parser("rebuild", help="판독 원자료만으로 채택·시트를 다시 계산한다 (생성물)")
    p_d = sub.add_parser(
        "import-decisions", help="사람이 채운 팀장 판정표 CSV → decisions.jsonl (그다음 rebuild)"
    )
    p_d.add_argument("--csv", type=pathlib.Path, required=True)
    # 🆕 2026-09-30 (D-285 개정 5) — 문구 판(화장품 `cq-*` · 보도자료 `fp-*`). 같은 채택 함수 · 산출물은 원천마다 `data/derived/labels/<판>/`
    for tag, (_R, name) in ROUNDS.items():
        pm = sub.add_parser(
            f"{tag}-merge",
            help=f"{name} — 단위 표 + 판독 TSV 둘 → 판독 원자료 · 채택 · 팀장 판정표",
        )
        pm.add_argument("--units", type=pathlib.Path, required=True, help="단위 표 JSON")
        pm.add_argument("--r1", type=pathlib.Path, required=True)
        pm.add_argument("--r2", type=pathlib.Path, required=True)
        sub.add_parser(
            f"{tag}-rebuild", help=f"{name} — 판독 원자료 + 팀장 판정으로 채택·시트를 다시 계산한다"
        )
        pd = sub.add_parser(
            f"{tag}-import-decisions", help=f"{name} — 채운 팀장 판정표 CSV → decisions.jsonl"
        )
        pd.add_argument("--csv", type=pathlib.Path, required=True)
        pa = sub.add_parser(
            f"{tag}-audit", help=f"{name} — 채운 합의 감사표 CSV → audit.jsonl · 합의 정확도"
        )
        pa.add_argument("--csv", type=pathlib.Path, required=True)
    a = ap.parse_args()
    tag = a.cmd.split("-", 1)[0]
    if tag in ROUNDS:
        return _round_main(ROUNDS[tag][0], a.cmd.split("-", 1)[1], a)
    if a.cmd == "input":
        print(f"판독 입력 {write_input(a.out):,}행 → {a.out}")
        return 0
    if a.cmd == "import-decisions":
        print(json.dumps(import_decisions(a.csv), ensure_ascii=False, indent=1))
        print(
            f"팀장 판정 → {DECISIONS}\n다음 — uv run python -m scripts.guide_statute_round rebuild"
        )
        return 0
    got = rebuild() if a.cmd == "rebuild" else merge(a.r1, a.r2, a.rr1, a.rr2)
    print(json.dumps(got, ensure_ascii=False, indent=1))
    print(
        f"채택 → {ADOPTED}\n판정 시트(사람 2인) → {SHEET}\n팀장 판정표(두 판독 나란히) → {TEAM_SHEET}\n두 판독 원자료 → {READINGS}"
    )
    return 0


def _round_main(R: Round, verb: str, a) -> int:
    if verb == "import-decisions":
        print(json.dumps(_import(R, a.csv), ensure_ascii=False, indent=1))
        print(
            f"팀장 판정 → {R.path('DECISIONS')}\n다음 — uv run python -m scripts.guide_statute_round {R.cmd}-rebuild"
        )
        return 0
    if verb == "audit":
        print(json.dumps(_audit(R, a.csv), ensure_ascii=False, indent=1))
        print(f"감사 → {R.path('AUDIT')}")
        return 0
    got = _rebuild(R) if verb == "rebuild" else _merge(R, a.units, a.r1, a.r2)
    print(json.dumps(got, ensure_ascii=False, indent=1))
    print(
        f"채택 → {R.path('ADOPTED')}\n팀장 판정표(두 판독 나란히) → {R.path('TEAM_SHEET')}\n두 판독 원자료 → {R.path('READINGS')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
