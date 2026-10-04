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
import random
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
#: 🆕 2026-10-01 (판정 J6 · D-220) — 블라인드 감사 두 표의 **들여온 결과**(원천 · 사람 판정). 앞 감사를 덮지 않는다
GS_AUDIT_TEAM = ROOT / "data" / "derived" / "labels" / "guide_statute" / "audit__팀장.jsonl"
CAUTION_AUDIT_TEAM = ROOT / "data" / "derived" / "labels" / "caution" / "audit__팀장.jsonl"
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


def food_guard(s: dict, a: dict, b: dict, got: dict) -> str | None:
    """합의여도 **시트로 보내는** 식품 규칙 — 해설서 위반문구(`decide`)와 수정문구 판(`GF`)이 같은 함수를 쓴다 (D-99).

    ① 3.나 가 원천 제품유형 9 밖에 적혔다 (D-288) ② 조제유류 목(5.바·5.사)이 근거·후보에 남았다 ③ 사항이 거래 조건이다 (D-272 개정).
    대상 N · 조건 L 행은 근거가 없으므로 ② 는 걸리지 않는다 — ① · ③ 은 판독 · 문구로 건다.
    """
    if not s["제품유형"].startswith(NA_TYPES) and ("3.나" in a["제외목"] + b["제외목"]):
        return "3.나 유형 밖 (D-288)"
    cites = (got.get("근거") or []) + [x for cand in got.get("근거_후보") or [] for x in cand]
    if any(statute.parse(c)[3:5] in FORMULA_MOK for c in cites):
        # 후보도 본다 — 한쪽 후보가 조제유류 목이면 그 후보를 정답으로 둘 수 없다
        return "조제유류 목 (5.바·5.사) — 원천 제품유형은 조제유류가 아니다"
    if TRADE.search(s["문구"]):
        return "거래조건 사항 (D-272 개정) — 인용을 팀장이 정한다"
    return None


def _food_hold(s: dict, a: dict, b: dict, got: dict) -> tuple[dict | None, str]:
    why = food_guard(s, a, b, got)
    return (None, why) if why else (got, "")


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
        if got is not None:
            got, reason = _food_hold(s, a[k], b[k], got)
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
    #: 🆕 2026-09-30 (판정 J1 (b)) — 합의여도 시트로 보내는 원천 규칙(없으면 None). 식품 수정문구 판은 `food_guard`
    guard: Callable[[dict, dict, dict, dict], str | None] | None = None

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


# ── 🆕 2026-10-04 옛 화장품 질의응답(2012 · FAQ 2020) 판 — 판정 묶음 ① (`판정기록_2026-10-04_판독판_판정묶음.md`) ──
#: 지시서는 화장품 2025 판과 같다(`라벨링_지시서_2026-09-25_질의응답집_화장품_조문·조건.md`) — 근거 코드 · 제외목 · 별표5목 표도 같다.
#:    다른 것은 원천 둘 · 문항 표기 · 원천 대조뿐이다(판독자가 부호 없이 뽑은 문구가 있다 — 원장 10-03 ㉒).
#:    🚨 2012 판은 2010 화장품법 기준이다 — 원천의 조문 번호를 지금 번호로 읽지 않는다(추출기 머리말). 판독은 현행 조문으로 붙였다.
CO_QA = {
    "mfds_cosmetic_ad_qa_2012": ROOT / "data" / "derived" / "mfds_cosmetic_ad_qa_2012.jsonl",
    "mfds_cosmetic_faq_2020": ROOT / "data" / "derived" / "mfds_cosmetic_faq_2020.jsonl",
}
CO_DIR = ROOT / "data" / "derived" / "labels" / "cosmetic_qa_old"
CO_READINGS = CO_DIR / "readings.jsonl"
CO_ADOPTED = CO_DIR / "adopted.jsonl"
CO_DECISIONS = CO_DIR / "decisions.jsonl"
CO_AUDIT = CO_DIR / "audit.jsonl"
CO_TEAM_SHEET = ROOT / "build" / "labels" / "cosmetic_qa_old__팀장판정표.csv"
#: 지문 머리 — `ca:` 2012 판 · `cf:` FAQ 2020. 🚨 지문은 판독 때 만든 것을 그대로 쓴다(다시 계산하지 않는다 — 화장품 2025 판과 같은 이유)
CO_KEY_RE = re.compile(r"^c[af]:[a-z2-7]{12}$")
CO_KEY_SOURCE = {"ca": "mfds_cosmetic_ad_qa_2012", "cf": "mfds_cosmetic_faq_2020"}
#: 문구를 찾는 칸 — 인용표현에 없으면 이 칸들의 글에서 찾는다(공백만 다르게)
CO_TEXT_FIELDS = ("제목", "소제목", "질의", "답변")


def co_question(source: str, rec: dict) -> str | None:
    """원천 레코드 → 단위 표의 문항 표기. 2012 판 「장 번호-문항」(화장품 편만) · FAQ 2020 「Q번호」. 범위 밖이면 None."""
    if source == "mfds_cosmetic_faq_2020":
        return f"Q{int(rec['문항'])}"
    if rec.get("편") != "화장품":
        return None  # 의약외품 편은 이 판의 범위 밖이다 (D-192)
    m = re.match(r"(\d+)\.", str(rec.get("장") or ""))
    return f"{m.group(1)}-{int(rec['문항'])}" if m else None


def co_units(units: list[dict]) -> dict[str, dict]:
    """옛 화장품 단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 문구가 그 문항의 `인용표현` 에 있거나 문항 글에 공백만 다르게 있어야 한다.

    ★ 문항 글에서도 찾는 까닭 — 이 원천은 인용부호 없이 적은 광고 표현이 많아 판독자가 문구를 직접 뽑았다(325 중 144 · 원장 10-03 ㊿-6).
    🔴 지문 머리와 `원천` 이 어긋나면 멈춘다 — 두 원천의 문항 표기가 달라 섞이면 다른 문항에 붙는다 (D-220).
    """
    qa: dict[tuple[str, str], dict] = {}
    for source, path in CO_QA.items():
        if not path.exists():
            raise SystemExit(
                f"🔴 {path} 가 없다 — 먼저: uv run python -m preprocess."
                f"{'mfds_cosmetic_qa_2012' if source.endswith('2012') else 'mfds_cosmetic_faq_2020'} --dump"
            )
        for x in path.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                q = co_question(source, r)
                if q is not None:
                    qa[(source, q)] = r
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(CO_KEY_RE, k, src, bad):
            continue
        # 원천은 **지문 머리**가 정한다 — 판독 원자료(`readings.jsonl`)는 `원천` 칸을 싣지 않는다(`rebuild` 가 그것만 읽는다).
        #    단위 표가 `원천` 을 적어 왔으면 머리와 같은지 본다
        source = CO_KEY_SOURCE[k[:2]]
        if u.get("원천") not in (None, source):
            bad.append(f"{k} 지문 머리와 원천이 어긋난다 {u.get('원천')!r}")
            continue
        q = qa.get((source, str(u["문항"])))
        if q is None:
            bad.append(f"{k} {source} 에 없는 문항 {u['문항']!r}")
            continue
        body = _WS.sub("", " ".join(str(q.get(f) or "") for f in CO_TEXT_FIELDS))
        if u["문구"] not in (q.get("인용표현") or []) and _WS.sub("", u["문구"]) not in body:
            bad.append(f"{k} {u['문항']} 원천에 없는 문구 {u['문구'][:30]!r}")
            continue
        src[k] = {
            "지문": k,
            "문항": str(u["문항"]),
            "자리": u["자리"],
            "문구": u["문구"],
            "원천": source,
        }
    _units_fail("옛 화장품 질의응답", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.co_units")
    return src


CO = Round(
    prefix="CO",
    cmd="co",
    cite_of=cq_cite_of,
    exceptions=CQ_EXCEPTIONS,
    mok_ho=CQ_MOK_HO,
    head=("문항", "자리"),
    sheet_head=("문항",),
    units=lambda us: co_units(us),
)


# ── 🆕 2026-10-04 사례집 2021 판 — 지시서 `라벨링_지시서_2026-10-03_사례집2021_조문·조건.md` · 판정 묶음 ① ──
#: 식약처 「부당한 표시 또는 광고 사례집」 2021 판의 **광고 화면**(쪽 · 칸 하나가 단위). 원천이 위반이라 든 화면이다(D-237).
#:    🚨 법이 둘이다 — 식품(식품표시광고법 제8조 · [별표 1] 목)과 화장품(화장품법 제13조 · [별표 5] 목). 근거 코드가 겹쳐
#:       (`1` 이 식품 1호이기도 화장품 1호이기도 하다) **판을 둘로 가른다** — 단위의 `법` 칸이 어느 판인지 정한다.
#:    🔴 원천 레코드는 `scripts/casebook2021_sheet.py --dump` 가 낸다(쪽 전사 → 마스킹 → 행).
CB_SOURCE = "mfds_casebook_2021"
CB_SHEET = ROOT / "data" / "derived" / "casebook2021_labelsheet.jsonl"
CB_KEY_RE = re.compile(r"^cb:[a-z2-7]{12}$")
#: 단위의 문구는 화면 글의 줄을 이 글자로 이어 붙인 것이다(판독 입력을 만들 때의 꼴)
CB_JOIN = " / "
#: 원천 대조에서 보지 않는 글자 — 공백과 **표시 자국**(⟦ ⟧ · 전사가 형광 · 색글자 자리를 감싼다)
_CB_SKIP = re.compile(r"[\s⟦⟧]+")
#: 화면의 글이 든 칸 — 표시 문구 · 화면 글 · 식약처 설명 · 심의 삭제 · 본문 글
CB_TEXT_FIELDS = ("문구", "표시문구", "화면글", "식약처설명", "글", "사례", "참고", "소제목")

CBF_DIR = ROOT / "data" / "derived" / "labels" / "casebook_2021_food"
CBF_READINGS = CBF_DIR / "readings.jsonl"
CBF_ADOPTED = CBF_DIR / "adopted.jsonl"
CBF_DECISIONS = CBF_DIR / "decisions.jsonl"
CBF_AUDIT = CBF_DIR / "audit.jsonl"
CBF_TEAM_SHEET = ROOT / "build" / "labels" / "casebook_2021_food__팀장판정표.csv"
CBC_DIR = ROOT / "data" / "derived" / "labels" / "casebook_2021_cosmetic"
CBC_READINGS = CBC_DIR / "readings.jsonl"
CBC_ADOPTED = CBC_DIR / "adopted.jsonl"
CBC_DECISIONS = CBC_DIR / "decisions.jsonl"
CBC_AUDIT = CBC_DIR / "audit.jsonl"
CBC_TEAM_SHEET = ROOT / "build" / "labels" / "casebook_2021_cosmetic__팀장판정표.csv"


def _cb_text(v: object) -> str:
    """원천 행의 한 칸 → 글(목록 · `{글, 표시}` 꼴을 편다)."""
    if isinstance(v, dict):
        return " ".join(_cb_text(x) for x in v.values())
    if isinstance(v, list):
        return " ".join(_cb_text(x) for x in v)
    return v if isinstance(v, str) else ""


def cb_units(units: list[dict], law: str) -> dict[str, dict]:
    """사례집 2021 단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 단위의 `행` 이 가리키는 원천 행과 쪽 · 칸이 같고,
    문구의 줄마다 그 행의 글에 있어야 한다(공백 · 표시 자국만 다르게).

    ★ 줄 단위로 보는 까닭 — 표시 문구가 없는 화면은 화면 글을 이어 붙여 단위 문구로 삼았다(114 중 21 · 원장 10-03 ㊿-8).
    🔴 `법` 이 이 판의 것이 아닌 단위가 섞이면 멈춘다 — 식품 코드로 화장품 화면을 읽게 된다 (D-220).
    """
    if not CB_SHEET.exists():
        raise SystemExit(
            f"🔴 {CB_SHEET} 가 없다 — 먼저: uv run python scripts/casebook2021_sheet.py --dump"
        )
    rows = [json.loads(x) for x in CB_SHEET.read_text(encoding="utf-8").splitlines() if x.strip()]
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(CB_KEY_RE, k, src, bad):
            continue
        if u.get("법") != law:
            bad.append(f"{k} 법 {u.get('법')!r} — 이 판은 {law} 다")
            continue
        no = int(u["행"])
        r = rows[no - 1] if 1 <= no <= len(rows) else None
        if r is None or (str(r["쪽"]), str(r["칸"])) != (str(u["쪽"]), str(u["칸"])):
            bad.append(f"{k} 행 {no} 의 쪽 · 칸이 원천과 다르다")
            continue
        body = _CB_SKIP.sub("", " ".join(_cb_text(r.get(f)) for f in CB_TEXT_FIELDS))
        lines = [x for x in u["문구"].split(CB_JOIN) if x.strip()]
        miss = [x for x in lines if _CB_SKIP.sub("", x) not in body]
        if miss or not lines:
            bad.append(f"{k} {u['쪽']}쪽 원천에 없는 줄 {len(miss)} — {(miss or [''])[0][:30]!r}")
            continue
        src[k] = {
            "지문": k,
            "행": no,
            "쪽": str(u["쪽"]),
            "칸": str(u["칸"]),
            "법": law,
            "원천호": str(u["원천호"]),
            "문구": u["문구"],
            "원천": CB_SOURCE,
        }
    _units_fail(f"사례집 2021({law})", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.cb_units")
    return src


_CB_HEAD = ("행", "쪽", "칸", "법", "원천호")
CBF = Round(
    prefix="CBF",
    cmd="cbf",
    cite_of=cite_of,
    exceptions=EXCEPTIONS,
    mok_ho={},
    head=_CB_HEAD,
    sheet_head=("쪽", "원천호"),
    units=lambda us: cb_units(us, "식품"),
)
CBC = Round(
    prefix="CBC",
    cmd="cbc",
    cite_of=cq_cite_of,
    exceptions=CQ_EXCEPTIONS,
    mok_ho=CQ_MOK_HO,
    head=_CB_HEAD,
    sheet_head=("쪽", "원천호"),
    units=lambda us: cb_units(us, "화장품"),
)


# ── 🆕 2026-10-05 대구청 사례(2013) 판 — 지시서 `라벨링_지시서_2026-10-03_대구청사례_조문·조건.md` ──
#: 대구지방식약청 「식품 등 허위과대광고 사례」의 **확정 문구**(사람이 원본에 대 확정한 전사 · 한 행이 단위)다.
#:    🔴 원천 레코드는 `scripts/daegu2013_sheet.py --dump` 가 낸다(전사 → 마스킹 → 행).
#:    🚨 전사에서 「제외」로 적힌 행(적법 쪽 추정 · 글자 미확정 · 기구)은 단위가 될 수 없다 — 오면 멈춘다.
DG_SOURCE = "mfds_daegu_ad_cases_2013"
DG_ROWS = ROOT / "data" / "derived" / "mfds_daegu_ad_cases_2013.jsonl"
DG_KEY_RE = re.compile(r"^dg:[a-z2-7]{12}$")
DG_DIR = ROOT / "data" / "derived" / "labels" / "daegu_2013"
DG_READINGS = DG_DIR / "readings.jsonl"
DG_ADOPTED = DG_DIR / "adopted.jsonl"
DG_DECISIONS = DG_DIR / "decisions.jsonl"
DG_AUDIT = DG_DIR / "audit.jsonl"
DG_TEAM_SHEET = ROOT / "build" / "labels" / "daegu_2013__팀장판정표.csv"
_DG_SAME = ("쪽", "묶음", "품목", "문구")


def dg_units(units: list[dict]) -> dict[str, dict]:
    """대구청 단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 단위의 번호가 가리키는 파생물 행과 쪽 · 묶음 · 품목 · 문구가 같아야 한다."""
    if not DG_ROWS.exists():
        raise SystemExit(
            f"🔴 {DG_ROWS} 가 없다 — 먼저: uv run python scripts/daegu2013_sheet.py --dump"
        )
    have = {}
    for x in DG_ROWS.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            have[int(r["번호"])] = r
    src: dict[str, dict] = {}
    bad: list[str] = []
    nos: set[int] = set()
    for u in units:
        k = u["지문"]
        if not _key_ok(DG_KEY_RE, k, src, bad):
            continue
        no = int(u["번호"])
        h = have.get(no)
        if h is None or any(str(u.get(f)) != str(h[f]) for f in _DG_SAME):
            bad.append(f"{k} {no} 번 — 파생물의 행과 다르다")
            continue
        if h.get("제외"):
            bad.append(f"{k} {no} 번은 전사에서 제외한 행이다 — {str(h['제외'])[:30]}")
            continue
        if no in nos:
            bad.append(f"{k} {no} 번이 두 단위에 든다")
            continue
        nos.add(no)
        src[k] = {
            "지문": k,
            "번호": no,
            "쪽": int(h["쪽"]),
            "묶음": h["묶음"],
            "품목": h["품목"],
            "문구": h["문구"],
            "원천": DG_SOURCE,
        }
    _units_fail("대구청 사례", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.dg_units")
    return src


DG = Round(
    prefix="DG",
    cmd="dg",
    cite_of=cite_of,
    exceptions=EXCEPTIONS,
    mok_ho={},
    head=("번호", "쪽", "묶음", "품목"),
    sheet_head=("번호", "쪽", "품목"),
    units=dg_units,
)


# ── 🆕 2026-10-04 1차 법령해석(식약처 질의회신) 판 — 판독 지시 `build/labels/interp_ad/판독_지시_*.md` · 원장 10-03 ㉚ ──
#: 식약처 1차 해석 중 광고 표현 해석(`python -m preprocess.mfds_interp --dump` · 289 해석)의 **문구**가 단위다.
#:    🚨 법이 둘이다(식품 · 화장품) — 근거 코드가 겹쳐 사례집 2021 처럼 **판을 둘로 가른다**. 단위의 `품목` 과 지문 머리가 판을 정한다.
IP_SOURCE = "mfds_cgm_expc"
IP_QA = ROOT / "data" / "derived" / "mfds_cgm_expc_ad.jsonl"
#: 문구를 찾는 칸 — 인용표현에 없으면 이 칸들의 글에서 찾는다(공백만 다르게 · 옛 화장품 판과 같은 이유)
IP_TEXT_FIELDS = ("안건명", "질의", "답변", "이유")
IP_HEAD = {"식품": "if", "화장품": "ic"}
IPF_DIR = ROOT / "data" / "derived" / "labels" / "interp_ad_food"
IPF_READINGS = IPF_DIR / "readings.jsonl"
IPF_ADOPTED = IPF_DIR / "adopted.jsonl"
IPF_DECISIONS = IPF_DIR / "decisions.jsonl"
IPF_AUDIT = IPF_DIR / "audit.jsonl"
IPF_TEAM_SHEET = ROOT / "build" / "labels" / "interp_ad_food__팀장판정표.csv"
IPC_DIR = ROOT / "data" / "derived" / "labels" / "interp_ad_cosmetic"
IPC_READINGS = IPC_DIR / "readings.jsonl"
IPC_ADOPTED = IPC_DIR / "adopted.jsonl"
IPC_DECISIONS = IPC_DIR / "decisions.jsonl"
IPC_AUDIT = IPC_DIR / "audit.jsonl"
IPC_TEAM_SHEET = ROOT / "build" / "labels" / "interp_ad_cosmetic__팀장판정표.csv"


def ip_units(units: list[dict], item: str) -> dict[str, dict]:
    """1차 해석 단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 문항이 파생물에 있고 품목이 같고, 문구가 그 해석의
    `인용표현` 에 있거나 해석 글에 공백만 다르게 있어야 한다.

    🔴 품목이 이 판의 것이 아닌 단위 · 지문 머리가 품목과 어긋난 단위가 오면 멈춘다 — 다른 법의 코드로 읽게 된다 (D-220).
    """
    if not IP_QA.exists():
        raise SystemExit(
            f"🔴 {IP_QA} 가 없다 — 먼저: uv run python -m preprocess.mfds_interp --dump"
        )
    qa = {}
    for x in IP_QA.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            qa[str(r["id"])] = r
    key_re = re.compile(rf"^{IP_HEAD[item]}:[a-z2-7]{{12}}$")
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(key_re, k, src, bad):
            continue
        q = qa.get(str(u["문항"]))
        if q is None:
            bad.append(f"{k} 파생물에 없는 해석 {u['문항']!r}")
            continue
        if u.get("품목") != item or q.get("품목") != item:
            bad.append(f"{k} 품목 {u.get('품목')!r} · 원천 {q.get('품목')!r} — 이 판은 {item} 다")
            continue
        body = _WS.sub("", " ".join(str(q.get(f) or "") for f in IP_TEXT_FIELDS))
        if u["문구"] not in (q.get("인용표현") or []) and _WS.sub("", u["문구"]) not in body:
            bad.append(f"{k} {u['문항']} 원천에 없는 문구 {u['문구'][:30]!r}")
            continue
        src[k] = {
            "지문": k,
            "품목": item,
            "문항": str(u["문항"]),
            "자리": u["자리"],
            "문구": u["문구"],
            "원천": IP_SOURCE,
        }
    _units_fail(f"1차 해석({item})", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.ip_units")
    return src


_IP_HEAD = ("품목", "문항", "자리")
IPF = Round(
    prefix="IPF",
    cmd="ipf",
    cite_of=cite_of,
    exceptions=EXCEPTIONS,
    mok_ho={},
    head=_IP_HEAD,
    sheet_head=("문항",),
    units=lambda us: ip_units(us, "식품"),
)
IPC = Round(
    prefix="IPC",
    cmd="ipc",
    cite_of=cq_cite_of,
    exceptions=CQ_EXCEPTIONS,
    mok_ho=CQ_MOK_HO,
    head=_IP_HEAD,
    sheet_head=("문항",),
    units=lambda us: ip_units(us, "화장품"),
)


# ── 🆕 2026-10-04 판별 매뉴얼(2015) 판 — 지시서 `라벨링_지시서_2026-10-03_판별매뉴얼_조문·조건.md` ──
#: 식약처 「허위·과대광고 판별 매뉴얼」의 위반 사례 문구를 자른 **조각**(`preprocess.mfds_ad_manual.pieces`)이 단위다.
#:    🔴 원천 레코드는 `python -m preprocess.mfds_ad_manual --dump` 가 낸다(사람 가림 + 마스킹 정책 · 2인 확인 2026-10-04).
#:    🚨 식약처 서술만 든 조각(자른 까닭이 그것이다 · 지시서 ⑭-4)은 판독하지 않았다 — 단위 표에 없다(2 · 원장 10-03 ㊿-10).
#:       그래서 단위 표는 조각의 **부분집합**이어도 된다. 조각에 없는 단위가 오면 멈춘다.
MN_SOURCE = "mfds_ad_judge_manual_2015"
MN_CASES = ROOT / "data" / "derived" / "mfds_ad_judge_manual_2015.jsonl"
MN_KEY_RE = re.compile(r"^mn:[a-z2-7]{12}$")
MN_DIR = ROOT / "data" / "derived" / "labels" / "ad_manual_2015"
MN_READINGS = MN_DIR / "readings.jsonl"
MN_ADOPTED = MN_DIR / "adopted.jsonl"
MN_DECISIONS = MN_DIR / "decisions.jsonl"
MN_AUDIT = MN_DIR / "audit.jsonl"
MN_TEAM_SHEET = ROOT / "build" / "labels" / "ad_manual_2015__팀장판정표.csv"
_MN_SAME = ("구역", "쪽", "면", "조각", "조각수", "문구")


def mn_pieces() -> dict[str, dict]:
    """판별 매뉴얼 파생물 → 지문별 조각. 🔴 자리표와 문구가 어긋나면 `pieces` 가 멈춘다 (D-220)."""
    from preprocess import mfds_ad_manual  # noqa: PLC0415 — 추출기는 이 판을 돌릴 때만 든다

    if not MN_CASES.exists():
        raise SystemExit(
            f"🔴 {MN_CASES} 가 없다 — 먼저: uv run python -m preprocess.mfds_ad_manual --dump"
        )
    rows = [json.loads(x) for x in MN_CASES.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {p["지문"]: p for p in mfds_ad_manual.pieces(rows)}


def mn_units(units: list[dict]) -> dict[str, dict]:
    """단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 지문 · 구역 · 쪽 · 면 · 조각 · 문구가 파생물의 조각과 같아야 한다."""
    have = mn_pieces()
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(MN_KEY_RE, k, src, bad):
            continue
        h = have.get(k)
        if h is None or any(u.get(f) != h[f] for f in _MN_SAME):
            bad.append(
                f"{k} {u.get('쪽')}{u.get('면')} 조각 {u.get('조각')} — 파생물의 조각과 다르다"
            )
            continue
        src[k] = {**h, "원천": MN_SOURCE}
    _units_fail("판별 매뉴얼", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.mn_units")
    return src


MN = Round(
    prefix="MN",
    cmd="mn",
    cite_of=cite_of,
    exceptions=EXCEPTIONS,
    mok_ho={},
    head=("구역", "쪽", "면", "조각", "조각수"),
    sheet_head=("구역", "쪽", "조각"),
    units=mn_units,
)


# ── 🆕 2026-09-30 (판정 J1 (b)) 해설서 **수정문구** 판 — 지시서 `라벨링_지시서_2026-09-30_해설서_수정문구_조문·조건.md` ──
#: 해설서 「표시(안) → 수정」 표의 오른쪽 칸(`preprocess/mfds_guide.py` 의 `수정쌍`). 🚨 위반문구 1,834 와 **다른 행**이다 —
#:    원래 문구(왼쪽 칸)는 위반문구 표에 없다(0/245 · 작업공간 실측). 이 판은 **수정문구**만 읽는다
GF_SOURCE = "mfds_special_use_guide"
GF_GUIDE = ROOT / "data" / "derived" / "mfds_guide_labels.jsonl"
GF_DIR = ROOT / "data" / "derived" / "labels" / "guide_fix"
GF_READINGS = GF_DIR / "readings.jsonl"
GF_ADOPTED = GF_DIR / "adopted.jsonl"
GF_DECISIONS = GF_DIR / "decisions.jsonl"
GF_AUDIT = GF_DIR / "audit.jsonl"
GF_TEAM_SHEET = ROOT / "build" / "labels" / "guide_fix__팀장판정표.csv"
#: 🚨 머리 `gf:` 를 `preprocess/golden.py` `LAWFUL_NOCLAIM_PREFIX` 가 읽는다(적법 문장 · 주장 없음 · D-301) — 바꾸면 양쪽을 같이 (D-99)
GF_KEY_RE = re.compile(r"^gf:[a-z2-7]{12}$")


def gf_key_of(table: int, orig: str, fix: str) -> str:
    """수정문구의 지문 — 표 · 원래 문구 · 수정문구. 🚨 같은 수정문구(「~ 환자」)가 여러 표 · 여러 원래 문구에 나온다 → 셋을 다 넣는다."""
    raw = f"{table}|{orig}|{fix}"
    return (
        "gf:" + base64.b32encode(hashlib.sha256(raw.encode("utf-8")).digest()).decode()[:12].lower()
    )


def _gf_source() -> dict[str, dict]:
    """해설서 파생물(마스킹을 지난 `--dump` 사본 · D-159)의 수정쌍 → 지문별 행. 같은 셋이 두 번이면 한 번만(수를 센다)."""
    if not GF_GUIDE.exists():
        raise SystemExit(
            f"🔴 {GF_GUIDE} 가 없다 — 먼저: uv run python -m preprocess.mfds_guide --dump"
        )
    got: dict[str, dict] = {}
    for x in GF_GUIDE.read_text(encoding="utf-8").splitlines():
        if not x.strip():
            continue
        r = json.loads(x)
        if r.get("종류") != "수정쌍":
            continue
        k = gf_key_of(r["표"], r["문구"], r["수정문구"])
        got.setdefault(
            k,
            {
                "지문": k,
                "표": r["표"],
                "제품유형": r["제품유형"],
                "원래문구": r["문구"],
                "문구": r["수정문구"],
                "원천": r["원천"],
            },
        )
    return got


def gf_rows() -> list[dict]:
    """판독 단위 — 수정쌍 전량(지문 중복 제거). `gf-input` 이 `단위.json` 으로 낸다."""
    rows = list(_gf_source().values())
    registry.assert_derivable(rows, who="guide_statute_round.gf_rows")
    return rows


def gf_units(units: list[dict]) -> dict[str, dict]:
    """단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 지문 · 표 · 원래 문구 · 수정문구가 해설서 파생물의 수정쌍과 같아야 한다."""
    have = _gf_source()
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(GF_KEY_RE, k, src, bad):
            continue
        h = have.get(k)
        if h is None or any(u.get(f) != h[f] for f in ("표", "원래문구", "문구")):
            bad.append(f"{k} 표 {u.get('표')} 해설서 수정쌍에 없는 행 {str(u.get('문구'))[:30]!r}")
            continue
        if h["원천"] != GF_SOURCE:
            bad.append(f"{k} 원천 {h['원천']!r} ≠ {GF_SOURCE}")
            continue
        src[k] = h
    _units_fail("해설서 수정문구", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.gf_units")
    return src


GF = Round(
    prefix="GF",
    cmd="gf",
    cite_of=cite_of,
    exceptions=EXCEPTIONS,
    mok_ho={},
    head=("표", "제품유형", "원래문구"),
    sheet_head=("표", "제품유형"),
    units=lambda us: gf_units(us),
    guard=food_guard,
)

# ── 🆕 2026-09-30 (판정 J2) 결정문 **봉인 문구** 판 — 지시서 `라벨링_지시서_2026-09-30_결정문봉인문구_대상·조건.md` ──
#: 봉인 평가셋(`split_manifest` 의 `test_sentence`)에 든 결정문 **주문 문구**. 원천(의결서)이 위반이라 했다(D-237) —
#:    판독은 **호를 새로 붙이지 않고** ① 광고 문구인가(대상) ② 문장만으로 판정되는가(조건)만 붙인다
FS_SOURCE = "ftc_decisions_body"
FS_MANIFEST = ROOT / "data" / "derived" / "golden" / "split_manifest.json"
FS_DIR = ROOT / "data" / "derived" / "labels" / "ftc_sealed"
FS_READINGS = FS_DIR / "readings.jsonl"
FS_ADOPTED = FS_DIR / "adopted.jsonl"
FS_DECISIONS = FS_DIR / "decisions.jsonl"
FS_AUDIT = FS_DIR / "audit.jsonl"
FS_TEAM_SHEET = ROOT / "build" / "labels" / "ftc_sealed__팀장판정표.csv"
FS_KEY_RE = re.compile(r"^fs:[a-z2-7]{12}$")


def _fs_source() -> dict[str, dict]:
    """봉인 문서의 주문 문구 → 지문별 행. 🔴 분할 기록이 없으면 멈춘다 · 한 문서에 같은 문구가 두 번이면 멈춘다 (D-220)."""
    from preprocess import split as sp  # noqa: PLC0415

    if not FS_MANIFEST.exists():
        raise SystemExit(f"🔴 {FS_MANIFEST} 가 없다 — 봉인이 무엇인지 모른다")
    assign = json.loads(FS_MANIFEST.read_text(encoding="utf-8"))["assign"]
    got: dict[str, dict] = {}
    for d in sp.ftc_docs():
        if assign.get(d["doc_id"]) != sp.SEALED:
            continue
        for text in d["문구"]:
            k = sp.sealed_key(d["doc_id"], text)
            if k in got:
                raise SystemExit(f"🔴 {d['doc_id']} 에 같은 주문 문구가 두 번 — {text[:30]!r}")
            got[k] = {
                "지문": k,
                "doc_id": d["doc_id"],
                "근거_원천": d["근거"],
                "문구": text,
                "원천": d["원천"],
            }
    return got


def fs_rows() -> list[dict]:
    rows = list(_fs_source().values())
    registry.assert_derivable(rows, who="guide_statute_round.fs_rows")
    return rows


def fs_units(units: list[dict]) -> dict[str, dict]:
    """단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 지금 봉인된 문서의 주문 문구와 같아야 한다(봉인이 바뀌었으면 멈춘다)."""
    have = _fs_source()
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(FS_KEY_RE, k, src, bad):
            continue
        h = have.get(k)
        if h is None or u.get("doc_id") != h["doc_id"] or u.get("문구") != h["문구"]:
            bad.append(f"{k} {u.get('doc_id')} 봉인 주문 문구에 없다 {str(u.get('문구'))[:30]!r}")
            continue
        src[k] = h
    miss = set(have) - set(src)
    if miss:
        bad.append(f"봉인 주문 문구 중 단위 표에 없는 것 {len(miss)} — 전량이 아니면 합치지 않는다")
    _units_fail("결정문 봉인 문구", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.fs_units")
    return src


def fs_guard(s: dict, a: dict, b: dict, got: dict) -> str | None:
    """합의여도 팀장에게 — ① 조건 L(원천은 위반이다 · D-237) ② C·A·B 인데 판독의 호가 **원천의 호 밖**이거나 비었다(호는 원천이 정한다).

    🔄 2026-10-03 — 「원천 호와 같다」에서 「원천 호 **안**이다」로 고쳤다. 지시서 §0 은 「두 호가 걸린 문서면 문구에 맞는 호
    하나 또는 둘」이라 적는데, 종전 가드는 두 호 문서에서 하나만 고른 합의를 전부 팀장에게 보냈다(학습 판 368 중 20).
    봉인 판은 문서마다 호가 하나라 결과가 같다(119 행 · 채택이 그대로임을 게이트가 본다).
    """
    if got["대상"] != "Y":
        return None
    if got["조건"] == "L":
        return "조건 L — 원천(의결서)은 위반이라 했다 (D-237)"
    if got["조건"] in ("C", "A", "B"):
        mine = {statute.ho_key(c) for c in got.get("근거") or []}
        if not mine or not mine <= {statute.ho_key(c) for c in s["근거_원천"]}:
            return "원천 호 밖 — 호는 의결서가 정한다"
    return None


FS = Round(
    prefix="FS",
    cmd="fs",
    cite_of=fp_cite_of,
    exceptions=FP_EXCEPTIONS,
    mok_ho={},
    head=("doc_id", "근거_원천"),
    sheet_head=("doc_id",),
    units=lambda us: fs_units(us),
    guard=fs_guard,
)


def fs_input(out_dir: pathlib.Path) -> dict:
    """판독 재료 — `단위.json` · `입력.md`(문서 id · 원천 호 · 문구)."""
    rows = fs_rows()
    out_dir.mkdir(parents=True, exist_ok=True)
    units = [{h: r[h] for h in ("지문", "doc_id", "문구")} for r in rows]
    (out_dir / "단위.json").write_text(
        json.dumps(units, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    ho = lambda r: ",".join(f"공{statute.parse(c)[3]}" for c in r["근거_원천"])  # noqa: E731
    lines = ["# 판독 입력 — 결정문 봉인 문구", "", "지문 | 문서 | 원천 호 | **문구**", ""]
    lines += [f"{r['지문']} | {r['doc_id']} | {ho(r)} | **{r['문구']}**" for r in rows]
    (out_dir / "입력.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"단위": len(units), "문서": len({r["doc_id"] for r in rows})}


# ── 🆕 2026-10-03 (D-312) 결정문 **학습 문구** 판 — 지시서 `라벨링_지시서_2026-10-02_결정문학습문구_대상·조건.md` ──
#: 분할이 `train` 으로 배정한 결정문의 **주문 문구**. 봉인 판(FS)과 같은 정의 · 같은 채택 함수 · 같은 가드를 쓴다 (D-99).
#:    다른 곳은 둘이다 — ① 입력(봉인 아닌 문서) ② 판독자에게 **인용부호 앞뒤 글**을 함께 보인다(대상 이름인지 광고 내용인지 가르는 재료 · 지시서 §1 ④)
FT_SOURCE = "ftc_decisions_body"
FT_STAGE = ROOT / "data" / "derived" / "ftc_stage.jsonl"
FT_DIR = ROOT / "data" / "derived" / "labels" / "ftc_train"
FT_READINGS = FT_DIR / "readings.jsonl"
FT_ADOPTED = FT_DIR / "adopted.jsonl"
FT_DECISIONS = FT_DIR / "decisions.jsonl"
FT_AUDIT = FT_DIR / "audit.jsonl"
FT_TEAM_SHEET = ROOT / "build" / "labels" / "ftc_train__팀장판정표.csv"
FT_KEY_RE = re.compile(r"^ft:[a-z2-7]{12}$")
#: 인용부호 앞뒤로 보이는 글자 수 `[임의]` — 지시서 §1 ④ 가 30 으로 적었다. 판정 경로가 아니라 판독자가 읽는 재료다
FT_CONTEXT = 30
#: 학습 쪽 분할 값 — `preprocess.split` 의 배정 값. 🚨 「봉인이 아닌 것」으로 고르지 않는다(배정이 없는 문서가 섞인다 · D-220)
FT_SPLIT = "train"


def ft_key(doc_id: str, text: str) -> str:
    """학습 문구의 지문 — 봉인 판과 같은 해시(`split.sealed_key`)에 머리만 `ft:` (D-99)."""
    from preprocess import split as sp  # noqa: PLC0415

    return "ft:" + sp.sealed_key(doc_id, text).split(":", 1)[1]


def ft_context(order: str, text: str, width: int = FT_CONTEXT) -> str:
    """주문에서 문구가 인용된 자리의 앞뒤 글 — `… 앞 ⟦문구⟧ 뒤 …`. 🔴 주문에 없으면 멈춘다(지어내지 않는다 · D-220).

    같은 문구가 주문에 여러 번 나오면 **첫 자리**를 보인다. 줄바꿈은 공백으로 접는다.
    """
    i = order.find(text)
    if i < 0:
        raise ValueError(f"주문에 없는 문구 — {text[:30]!r}")
    fold = lambda x: re.sub(r"\s+", " ", x)  # noqa: E731
    head = fold(order[max(i - width, 0) : i])
    tail = fold(order[i + len(text) : i + len(text) + width])
    return f"{'… ' if i > width else ''}{head}⟦{text}⟧{tail}{' …' if i + len(text) + width < len(order) else ''}"


def _ft_orders() -> dict[str, str]:
    """문서 id → 마스킹을 지난 주문. 🔴 파생물이 없으면 멈춘다."""
    if not FT_STAGE.exists():
        raise SystemExit(
            f"🔴 {FT_STAGE} 가 없다 — 먼저: uv run python -m preprocess.ftc_extract --stage --dump"
        )
    got: dict[str, str] = {}
    for line in FT_STAGE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            got[f"ftc:{r['seq']}"] = str(r.get("주문_마스킹") or "")
    return got


def _ft_source() -> dict[str, dict]:
    """학습 문서의 주문 문구 → 지문별 행. 🔴 분할 기록 · 주문이 없거나 문구가 주문에 없으면 멈춘다 (D-220)."""
    from preprocess import split as sp  # noqa: PLC0415

    if not FS_MANIFEST.exists():
        raise SystemExit(f"🔴 {FS_MANIFEST} 가 없다 — 어느 문서가 학습 쪽인지 모른다")
    assign = json.loads(FS_MANIFEST.read_text(encoding="utf-8"))["assign"]
    orders = _ft_orders()
    got: dict[str, dict] = {}
    for d in sp.ftc_docs():
        if assign.get(d["doc_id"]) != FT_SPLIT:
            continue
        for text in d["문구"]:
            k = ft_key(d["doc_id"], text)
            if k in got:
                raise SystemExit(f"🔴 {d['doc_id']} 에 같은 주문 문구가 두 번 — {text[:30]!r}")
            if d["doc_id"] not in orders:
                raise SystemExit(f"🔴 {d['doc_id']} 의 주문이 {FT_STAGE} 에 없다")
            try:
                around = ft_context(orders[d["doc_id"]], text)
            except ValueError as e:
                raise SystemExit(f"🔴 {d['doc_id']} — {e}") from e
            got[k] = {
                "지문": k,
                "doc_id": d["doc_id"],
                "근거_원천": d["근거"],
                "문구": text,
                "앞뒤": around,
                "원천": d["원천"],
            }
    return got


def ft_rows() -> list[dict]:
    rows = list(_ft_source().values())
    registry.assert_derivable(rows, who="guide_statute_round.ft_rows")
    return rows


def ft_units(units: list[dict]) -> dict[str, dict]:
    """단위 표 → 지문별 원천 행. 🔴 **원천 대조** — 지금 학습 쪽 문서의 주문 문구와 같아야 한다(분할이 바뀌었으면 멈춘다)."""
    have = _ft_source()
    src: dict[str, dict] = {}
    bad: list[str] = []
    for u in units:
        k = u["지문"]
        if not _key_ok(FT_KEY_RE, k, src, bad):
            continue
        h = have.get(k)
        if h is None or u.get("doc_id") != h["doc_id"] or u.get("문구") != h["문구"]:
            bad.append(f"{k} {u.get('doc_id')} 학습 주문 문구에 없다 {str(u.get('문구'))[:30]!r}")
            continue
        src[k] = h
    miss = set(have) - set(src)
    if miss:
        bad.append(f"학습 주문 문구 중 단위 표에 없는 것 {len(miss)} — 전량이 아니면 합치지 않는다")
    _units_fail("결정문 학습 문구", bad)
    registry.assert_derivable(list(src.values()), who="guide_statute_round.ft_units")
    return src


FT = Round(
    prefix="FT",
    cmd="ft",
    cite_of=fp_cite_of,
    exceptions=FP_EXCEPTIONS,
    mok_ho={},
    head=("doc_id", "근거_원천"),
    sheet_head=("doc_id",),
    units=lambda us: ft_units(us),
    guard=fs_guard,  # 봉인 판과 **같은 함수** — 조건 L · 원천 호와 다른 호는 합의여도 팀장에게 (D-99)
)


def ft_input(out_dir: pathlib.Path) -> dict:
    """판독 재료 — `단위.json` · `입력.md`(문서 id · 원천 호 · 앞뒤 글 · 문구)."""
    rows = ft_rows()
    out_dir.mkdir(parents=True, exist_ok=True)
    units = [{h: r[h] for h in ("지문", "doc_id", "문구")} for r in rows]
    (out_dir / "단위.json").write_text(
        json.dumps(units, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    ho = lambda r: ",".join(f"공{statute.parse(c)[3]}" for c in r["근거_원천"])  # noqa: E731
    lines = [
        "# 판독 입력 — 결정문 학습 문구",
        "",
        "지문 | 문서 | 원천 호 | 주문에서 인용된 자리(⟦ ⟧ 가 문구) | **문구**",
        "",
    ]
    lines += [
        f"{r['지문']} | {r['doc_id']} | {ho(r)} | {r['앞뒤']} | **{r['문구']}**" for r in rows
    ]
    (out_dir / "입력.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"단위": len(units), "문서": len({r["doc_id"] for r in rows})}


#: 식품 판독에 주는 기준 원문 — 현행 조문 · [별표] · 고시(지시서 §4). 🔴 하나라도 없으면 멈춘다(빈 묶음을 주지 않는다 · D-220)
LAW_ARTICLE = ROOT / "data" / "derived" / "law_article.jsonl"
LAW_NORM = ROOT / "data" / "derived" / "law_norm"
FOOD_ARTICLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("식품 등의 표시ㆍ광고에 관한 법률", ("7", "8", "9")),
    ("식품 등의 표시ㆍ광고에 관한 법률 시행령", ("2", "3")),
    ("식품등의 부당한 표시 또는 광고의 내용 기준", ("2",)),
    (
        "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
        ("2", "3", "4", "5", "6"),
    ),
)
FOOD_ANNEXES = ("013453_0001", "69549_0001", "75449_0001", "75449_0002")


def food_criteria() -> str:
    """🆕 2026-09-30 — 식품 판독의 기준 원문 묶음(마크다운). 종전에는 판독 때마다 손으로 모았다(화장품 지시서 §4 「스크립트는 아직 없다」)."""
    miss = [
        str(p)
        for p in (LAW_ARTICLE, *(LAW_NORM / f"{a}.jsonl" for a in FOOD_ANNEXES))
        if not p.exists()
    ]
    if miss:
        raise SystemExit("🔴 기준 원문이 없다 — 묶음을 내지 않는다\n  " + "\n  ".join(miss))
    arts = [
        json.loads(x) for x in LAW_ARTICLE.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    out = ["# 기준 원문 — 식품 (현행 · 코퍼스에서 뽑음)", ""]
    for law, jos in FOOD_ARTICLES:
        got = [r for r in arts if r["법령"] == law and r["조"] in jos and not r["가지"]]
        if {r["조"] for r in got} != set(jos):
            raise SystemExit(
                f"🔴 {law} 제{','.join(jos)}조 중 코퍼스에 없는 조 — 묶음을 내지 않는다"
            )
        out += [f"## {law}", ""]
        out += [
            r["본문"] for r in sorted(got, key=lambda r: jos.index(r["조"]))
        ]  # 파일 순서 유지(안정 정렬)
        out.append("")
    for a in FOOD_ANNEXES:
        rs = [
            json.loads(x)
            for x in (LAW_NORM / f"{a}.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()
        ]
        out += [f"## [별표] {rs[0]['annex_title']} ({a})", ""]
        for r in rs:
            out.append("  " * max(int(r.get("level") or 0) - 1, 0) + f"{r['path']} {r['text']}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def gf_input(out_dir: pathlib.Path) -> dict:
    """판독 재료 셋 — `단위.json`(병합이 읽는다) · `입력.md`(판독자가 읽는다 · 원래 문구를 함께) · `기준원문.md`."""
    rows = gf_rows()
    out_dir.mkdir(parents=True, exist_ok=True)
    units = [{h: r[h] for h in ("지문", "표", "제품유형", "원래문구", "문구")} for r in rows]
    (out_dir / "단위.json").write_text(
        json.dumps(units, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# 판독 입력 — 해설서 수정문구",
        "",
        "지문 | 제품유형 | 원래 문구(심의에서 고치라 한 것) | **수정문구(판독 대상)**",
        "",
    ]
    lines += [f"{u['지문']} | {u['제품유형']} | {u['원래문구']} | **{u['문구']}**" for u in units]
    (out_dir / "입력.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "기준원문.md").write_text(food_criteria(), encoding="utf-8", newline="\n")
    return {"단위": len(units), "제품유형": dict(collections.Counter(u["제품유형"] for u in units))}


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
            if got is not None and R.guard is not None:
                hold = R.guard(s, a[k], b[k], got)
                if hold:
                    got, reason = None, hold
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


def _audit(R: Round, path: pathlib.Path, out: pathlib.Path | None = None) -> dict:
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
    if out is None:
        out = R.path("AUDIT")
        if out.exists():
            # 🆕 2026-09-30 (판정 J6) — 앞 감사(예: 화장품 모델 감사 · 원장 09-30)를 **덮지 않는다** — 감사는 원천이다
            raise SystemExit(
                f"🔴 {out} 가 이미 있다 — 덮지 않는다. 새 감사는 --out 으로 다른 이름에(예: audit__팀장.jsonl)"
            )
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


#: 🆕 2026-09-30 (판정 J6) — 블라인드 감사표의 칸. 🔴 판독 · 채택 값을 싣지 않는다(보고 붙이면 그쪽으로 끌린다 · 지시서 §6)
AUDIT_TAIL = ("대상", "주근거", "부근거", "별표5목", "조건", "제외목", "메모", "판정자")
AUDIT_SEED = 20260930


def audit_pick(keys: list[str], n: int, seed: int) -> list[str]:
    """정렬한 지문에서 seed 로 n 개 — 같은 seed · 같은 채택본이면 같은 표본이다 (D-54)."""
    keys = sorted(keys)
    return sorted(random.Random(seed).sample(keys, min(n, len(keys))))


def _cell(v) -> str:
    return ",".join(map(str, v)) if isinstance(v, list) else str(v)


def audit_sheet(
    R: Round, out: pathlib.Path, n: int = 30, seed: int = AUDIT_SEED, keys: list[str] | None = None
) -> dict:
    """합의 채택 행에서 무작위 n 을 뽑아 **판독을 가린** 감사표를 쓴다 → 팀장이 채워 `{cmd}-audit --csv … --out …`.

    `keys` 를 주면 그 행으로(앞 감사와 같은 표본을 사람이 다시 볼 때 · 화장품 모델 감사 30). 🔴 합의 채택 행이 아니면 멈춘다.
    """
    ad = R.path("ADOPTED")
    if not ad.exists():
        raise SystemExit(f"🔴 {ad} 가 없다 — 먼저 {R.cmd}-rebuild")
    took = {}
    for x in ad.read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if r["판독"] == "독립판독_합의":
                took[r["지문"]] = r
    pick = sorted(keys) if keys is not None else audit_pick(list(took), n, seed)
    bad = [k for k in pick if k not in took]
    if bad:
        raise SystemExit(f"🔴 합의 채택 행이 아닌 지문 {len(bad)} — 예 {bad[:3]}")
    shown = [h for h in R.head if h not in ("마스킹",)]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(("지문", *shown, "문구", *AUDIT_TAIL))
        for k in pick:
            r = took[k]
            w.writerow(
                [k, *(_cell(r.get(h, "")) for h in shown), r["문구"]] + [""] * len(AUDIT_TAIL)
            )
    return {"판": R.cmd, "합의채택": len(took), "표본": len(pick), "seed": None if keys else seed}


def guide_audit_sheet(out: pathlib.Path, n: int = 30, seed: int = AUDIT_SEED) -> dict:
    """해설서 위반문구 판(`gs`) 블라인드 감사표 — 칸은 이 판의 판독 꼴(근거 · 조건 · 제외목 · 원천결손).

    🔄 2026-10-01 — 채운 표는 `audit-import --csv …` 가 읽는다(`guide_audit` · 이 판은 `Round` 가 아니라 따로 둔다).
    """
    took = {}
    for x in ADOPTED.read_text(encoding="utf-8").splitlines() if ADOPTED.exists() else []:
        r = json.loads(x)
        if r["판독"] == "독립판독_합의":
            took[r["지문"]] = r
    if not took:
        raise SystemExit(f"🔴 {ADOPTED} 에 합의 채택 행이 없다 — 먼저 rebuild")
    pick = audit_pick(list(took), n, seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            (
                "지문",
                "표",
                "제품유형",
                "문구",
                "주근거",
                "부근거",
                "조건",
                "제외목",
                "원천결손",
                "메모",
                "판정자",
            )
        )
        for k in pick:
            r = took[k]
            w.writerow([k, r["표"], r["제품유형"], r["문구"]] + [""] * 7)
    return {"판": "gs", "합의채택": len(took), "표본": len(pick), "seed": seed}


def caution_audit_sheet(out: pathlib.Path, n: int = 30, seed: int = AUDIT_SEED) -> dict:
    """인정 조건문(섭취 주의사항 · 조건 D · 판정 J1 (가-2′)) 블라인드 감사표 — 규칙이 붙인 D 를 사람이 본다.

    칸 — 조건(C·A·B·M·D·L) · 메모 · 판정자. 🔴 규칙의 값(D)을 싣지 않는다. 🔄 2026-10-01 — 읽는 명령 `caution-audit-import`.
    """
    from preprocess import split as sp  # noqa: PLC0415

    docs = {d["doc_id"]: d for d in sp.caution_docs()}
    if not docs:
        raise SystemExit("🔴 인정 조건문이 0 — 원천(mfds_hf_labels · hf_api_labels)을 본다")
    pick = audit_pick(list(docs), n, seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(("지문", "원천", "문구", "조건", "메모", "판정자"))
        for k in pick:
            d = docs[k]
            w.writerow([k, d["원천"], d["문구"][0], "", "", ""])
    return {"판": "인정조건문", "전체": len(docs), "표본": len(pick), "seed": seed}


def _canonical_only(what: str) -> None:
    """🔴 들여오기는 **정본에서만** — 사본이 `labels/`(원천)에 쓰면 정본과 갈라지고 공유 저장소로 못 간다 (D-226)."""
    from scripts import derived_manifest as dm  # noqa: PLC0415

    why = dm.not_canonical(what)
    if why:
        raise SystemExit(why)


def _write_audit(got: list[dict], bad: list[str], out: pathlib.Path) -> dict:
    """감사 결과를 쓴다 — `_audit` 과 같은 규칙: 문제 행이 하나라도 있으면 아무것도 안 쓴다 · 있는 파일은 덮지 않는다 (D-220)."""
    if bad:
        raise SystemExit(
            "🔴 감사표에 문제가 있다 — **아무것도 쓰지 않았다**\n  " + "\n  ".join(bad[:30])
        )
    if not got:
        raise SystemExit("🔴 판정자가 적힌 행이 0 — 쓸 것이 없다 (빈 표를 들여오지 않는다)")
    if out.exists():
        raise SystemExit(f"🔴 {out} 가 이미 있다 — 덮지 않는다. 새 감사는 --out 으로 다른 이름에")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(got, key=lambda r: r["지문"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hit = sum(r["일치"] for r in got)
    return {
        "감사": len(got),
        "일치": hit,
        "정확도": f"{hit / len(got):.1%}",
        "불일치": [r["지문"] for r in got if not r["일치"]],
        "→": str(out),
    }


def gs_same(x: dict, y: dict) -> bool:
    """해설서 위반문구 판 감사 대조 — **기대 응답을 정하는 것**이 같은가: 조건 · (C·A·B 면) 호 집합.

    채택 행이 `근거_후보`(호만 갈린 두 판독 · D-285 개정 2)면 **어느 후보와 같아도** 일치다 — 채택 규칙이 「어느 쪽을 인용해도 정답」이다.
    목은 보지 않는다(`cq_same` 과 같은 기준).
    """
    if x["조건"] != y["조건"]:
        return False
    if x["조건"] in ("M", "D"):
        return True
    hx = {statute.ho_key(c) for c in x["근거"]}
    cands = [y.get("근거") or []] + [c for c in (y.get("근거_후보") or []) if c]
    return any(hx == {statute.ho_key(c) for c in cand} for cand in cands if cand)


def guide_audit(path: pathlib.Path, out: pathlib.Path = GS_AUDIT_TEAM) -> dict:
    """🆕 2026-10-01 — 채운 해설서 위반문구 감사표(`audit-sheet`) → 감사(원천) · 합의 정확도. ⬜ 이었던 「읽는 명령」.

    🔴 조건이 빈 행은 판정 안 한 행(건너뜀) · 판정자가 비면 받지 않는다 · 합의 채택 행이 아니면 멈춘다.
    원천결손 칸이 비면 N 으로 읽는다(표시가 없다 = 결손 아님) — 그 밖의 칸은 판독 해석기(`parse_line`)가 그대로 검사한다.
    """
    _canonical_only("audit-import")
    took = {}
    for x in ADOPTED.read_text(encoding="utf-8").splitlines() if ADOPTED.exists() else []:
        if x.strip():
            r = json.loads(x)
            if r["판독"] == "독립판독_합의":
                took[r["지문"]] = r
    got, bad = [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for no, row in enumerate(csv.DictReader(f), 2):
            k = (row.get("지문") or "").strip()
            cond = (row.get("조건") or "").strip()
            if not cond:
                continue
            who = (row.get("판정자") or "").strip()
            if not who:
                bad.append(f"{no}행 {k} 판정자가 비었다 — 사람이 적는 칸이다")
                continue
            if k not in took:
                bad.append(f"{no}행 {k} 합의 채택 행이 아니다")
                continue
            c1, c2, ex = ((row.get(c) or "").strip() or "-" for c in ("주근거", "부근거", "제외목"))
            gap = (row.get("원천결손") or "").strip() or "N"
            line = "\t".join([k, c1, c2, cond, ex, gap, (row.get("메모") or "").strip()])
            rec = parse_line(line)
            if rec["문제"]:
                bad.append(f"{no}행 {k} — " + " / ".join(rec["문제"]))
                continue
            rec.pop("문제")
            got.append({"지문": k, "감사": rec, "판정자": who, "일치": gs_same(rec, took[k])})
    return _write_audit(got, bad, out)


#: 인정 조건문 감사가 받는 조건 — 규칙이 붙인 값은 D 하나다(판정 J1 (가-2′)). L 은 「주장 있는 적법」(D-301)
CAUTION_CONDITIONS = ("C", "A", "B", "M", "D", "L")


def caution_audit(path: pathlib.Path, out: pathlib.Path = CAUTION_AUDIT_TEAM) -> dict:
    """🆕 2026-10-01 — 채운 인정 조건문 감사표(`caution-audit-sheet`) → 감사(원천) · 규칙(D) 정확도. ⬜ 이었던 「읽는 명령」.

    일치 = 사람이 D 를 적었다. 🔴 지문이 지금의 인정 조건문(`split.caution_docs`)에 없으면 멈춘다 — 원천이 바뀐 뒤의 표다.
    """
    _canonical_only("caution-audit-import")
    from preprocess import split as sp  # noqa: PLC0415

    docs = {d["doc_id"] for d in sp.caution_docs()}
    got, bad = [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for no, row in enumerate(csv.DictReader(f), 2):
            k = (row.get("지문") or "").strip()
            cond = (row.get("조건") or "").strip()
            if not cond:
                continue
            who = (row.get("판정자") or "").strip()
            if not who:
                bad.append(f"{no}행 {k} 판정자가 비었다 — 사람이 적는 칸이다")
                continue
            if k not in docs:
                bad.append(f"{no}행 {k} 지금의 인정 조건문에 없다")
                continue
            if cond not in CAUTION_CONDITIONS:
                bad.append(f"{no}행 {k} 조건 {cond!r}")
                continue
            rec = {"조건": cond, "메모": (row.get("메모") or "").strip()}
            got.append({"지문": k, "감사": rec, "판정자": who, "일치": cond == "D"})
    return _write_audit(got, bad, out)


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


def gf_parse_line(line: str) -> dict:
    return _parse(GF, line)


def gf_merge(units: pathlib.Path, r1: pathlib.Path, r2: pathlib.Path) -> dict:
    return _merge(GF, units, r1, r2)


def gf_rebuild() -> dict:
    return _rebuild(GF)


ROUNDS = {
    "cq": (CQ, "화장품"),
    "co": (CO, "화장품 질의응답 2012 · 2020"),
    "cbf": (CBF, "사례집 2021 · 식품"),
    "cbc": (CBC, "사례집 2021 · 화장품"),
    "dg": (DG, "대구청 사례 2013"),
    "mn": (MN, "판별 매뉴얼 2015"),
    "ipf": (IPF, "1차 법령해석 · 식품"),
    "ipc": (IPC, "1차 법령해석 · 화장품"),
    "fp": (FP, "공정위 보도자료 1997~2007"),
    "gf": (GF, "해설서 수정문구"),
    "fs": (FS, "결정문 봉인 문구"),
    "ft": (FT, "결정문 학습 문구"),
}


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
        pa.add_argument(
            "--out", type=pathlib.Path, help="감사 원자료를 쓸 곳(기본 audit.jsonl · 있으면 멈춘다)"
        )
        ps = sub.add_parser(
            f"{tag}-audit-sheet", help=f"{name} — 합의 채택 무작위 n 블라인드 감사표 CSV"
        )
        ps.add_argument("--out", type=pathlib.Path, required=True)
        ps.add_argument("--n", type=int, default=30)
        ps.add_argument("--seed", type=int, default=AUDIT_SEED)
        ps.add_argument(
            "--keys-from",
            type=pathlib.Path,
            dest="keys_from",
            help="이 감사 jsonl 과 같은 표본으로",
        )
    p_gi = sub.add_parser("gf-input", help="해설서 수정문구 — 단위.json · 입력.md · 기준원문.md")
    p_gi.add_argument("--out", type=pathlib.Path, default=ROOT / "build" / "labels" / "guide_fix")
    for name, hlp in (
        ("audit-sheet", "해설서 위반문구 판"),
        ("caution-audit-sheet", "인정 조건문"),
    ):
        pz = sub.add_parser(name, help=f"{hlp} — 블라인드 감사표 CSV (판정 J6)")
        pz.add_argument("--out", type=pathlib.Path, required=True)
        pz.add_argument("--n", type=int, default=30)
        pz.add_argument("--seed", type=int, default=AUDIT_SEED)
    for name, hlp in (
        ("audit-import", "해설서 위반문구 판"),
        ("caution-audit-import", "인정 조건문"),
    ):
        pi = sub.add_parser(
            name, help=f"{hlp} — 채운 블라인드 감사표 CSV → 감사(원천) · 정확도 (정본)"
        )
        pi.add_argument("--csv", type=pathlib.Path, required=True)
        pi.add_argument("--out", type=pathlib.Path)
    p_fi = sub.add_parser("fs-input", help="결정문 봉인 문구 — 단위.json · 입력.md")
    p_fi.add_argument("--out", type=pathlib.Path, default=ROOT / "build" / "labels" / "ftc_sealed")
    p_ti = sub.add_parser("ft-input", help="결정문 학습 문구 — 단위.json · 입력.md(앞뒤 글 포함)")
    p_ti.add_argument("--out", type=pathlib.Path, default=ROOT / "build" / "labels" / "ftc_train")
    a = ap.parse_args()
    if a.cmd in ("audit-sheet", "caution-audit-sheet"):
        fn = guide_audit_sheet if a.cmd == "audit-sheet" else caution_audit_sheet
        print(json.dumps(fn(a.out, a.n, a.seed), ensure_ascii=False, indent=1))
        print(f"감사표 → {a.out} (판정자 칸은 사람이 채운다)")
        return 0
    if a.cmd in ("audit-import", "caution-audit-import"):
        fn = guide_audit if a.cmd == "audit-import" else caution_audit
        res = fn(a.csv, a.out) if a.out else fn(a.csv)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "fs-input":
        print(json.dumps(fs_input(a.out), ensure_ascii=False, indent=1))
        print(f"판독 재료 → {a.out}")
        return 0
    if a.cmd == "ft-input":
        print(json.dumps(ft_input(a.out), ensure_ascii=False, indent=1))
        print(f"판독 재료 → {a.out}")
        return 0
    if a.cmd == "gf-input":
        print(json.dumps(gf_input(a.out), ensure_ascii=False, indent=1))
        print(f"판독 재료 → {a.out}")
        return 0
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
        print(json.dumps(_audit(R, a.csv, a.out), ensure_ascii=False, indent=1))
        print(f"감사 → {a.out or R.path('AUDIT')}")
        return 0
    if verb == "audit-sheet":
        keys = None
        if a.keys_from:
            keys = [
                json.loads(x)["지문"]
                for x in a.keys_from.read_text(encoding="utf-8").splitlines()
                if x.strip()
            ]
        print(json.dumps(audit_sheet(R, a.out, a.n, a.seed, keys), ensure_ascii=False, indent=1))
        print(f"감사표 → {a.out} (판독 값은 싣지 않았다 · 판정자 칸은 사람이 채운다)")
        return 0
    got = _rebuild(R) if verb == "rebuild" else _merge(R, a.units, a.r1, a.r2)
    print(json.dumps(got, ensure_ascii=False, indent=1))
    print(
        f"채택 → {R.path('ADOPTED')}\n팀장 판정표(두 판독 나란히) → {R.path('TEAM_SHEET')}\n두 판독 원자료 → {R.path('READINGS')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
