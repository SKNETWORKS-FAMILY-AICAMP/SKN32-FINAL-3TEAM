"""preprocess/hf_api.py — 건기식 **API 2종**. 🚨 **축이 둘이다** (D-89 · D-185).

  uv run python -m preprocess.hf_api --verify     # 세고 대조만 한다
  uv run python -m preprocess.hf_api --dump       # 🔴 마스킹 정책이 있어야 한다

    정본 축   `mfds_hf_individual`  I-0050 개별인정형 **원료 대장**
              → `hf_api_labels.jsonl`      층 = 2층 적법라벨 · 지위 = 인정
    관측 축   `mfds_hf_ingredient`  I-0040 **업체 신고 현황**
              → `hf_display_claims.jsonl`  층 = 표시 문구 관측 · 🚨 지위를 안 붙인다

⛔ **2026-09-11 이전에는 둘을 한 파일에 「2층 적법라벨 · 지위: 인정」으로 담았다.**
   그것이 이 파일의 가장 큰 오류였다. 열이 이미 말하고 있었는데 안 봤다 (D-167) —
   I-0040 에는 `BSSH_NM`(업체) · `ADDR`(주소) · `INDUTY_NM`(업종) · `PRMS_DT`(승인일)가 있고
   원료명 열 이름이 `APLC_`(**신청**)로 시작한다. **행의 축이 업체×품목 승인**이지
   인정번호가 아니다.

🔴 **그래서 `HF_FNCLTY_MTRAL_RCOGN_NO` 는 I-0040 에서 외래키가 아니다** (2026-09-11 실측).
     773행 / 고유번호 768 — 중복 4건이 **서로 다른 원료**다
       2007-11  한국암웨이「토치대두발효추출물·식후혈당」 / 삼성물산「코엔자임Q10·항산화」
     I-0050 과 짝지은 433건 중 **34건은 원료명이 아예 다르다**
       2007-10  글루코사민 ↔ 콩발효추출물      2007-13  크레아틴 ↔ 차조기등복합추출물
   🚨 앞서 이것을 「오프셋 밀림(D-149)」으로 의심했는데 **틀렸다.** 밀린 것이 아니라
      **키가 유일하지 않은 것**이다 — 신고서에 적힌 자기신고 값이라 오타·구제도 번호가 섞인다.
   ★ 그래서 짝짓기는 **(인정번호, 원료명)** 두 축으로 한다. 원료명이 어긋나면
     **짝짓지 않고 그 사실을 적는다** (D-170).

🔴 **`FNCLTY_CN` 은 「인정 문구」가 아니라 「표시 문구」다.**
     어미가 「~도움을 줄 수 **있습니다**」(소비자 대면) — I-0050 은 고시체 「~있**음**」
     값에 「첨부파일 참조」·「◆ *OOO: … 함유된 제품명」 같은 **표시 지침**이 통째로 실린다
     773행을 정본과 맞춰 본 결과 (2026-09-11 실측) —
       같음 220 · 좁음 39 · 넓음 10 · 다름 72 · 문구없음 137 · 짝없음 276 · 원료불일치 19
     **문구가 있고 정본과 짝이 지어진 341건 중 같은 것은 220건(65%)뿐이다**
   ★ 그러므로 버릴 값이 아니라 **층을 옮길 값**이다. 인정 문구는 I-0050(444) + 게시판(465)에서
     이미 확보했고, **실제 시장에서 쓰인 표시 문구는 I-0040 에만 있다.**
     정본보다 좁거나 넓은 것이 우리가 찾던 **경계 사례**다 —
       2024-19  「인지기능 개선에 도움을 줌」  ← 정본은 「**노화로 인해 저하된** 인지기능 개선에
                도움을 줄 수 **있음**」 + 「기억력 개선…」. 대상 한정 삭제 + 가능형→단정형
       2013-35  「면역조절에…」              ← 정본은 「**인터루킨 4 감소를 통한** 면역조절에…」
       2019-5   「위 점막 보호…」            ← 정본은 「**① 관절 건강**, ② 위 점막…」

🚨 **셋이 겹친다 — 인정번호로 합친다** (레지스트리 caution 이 예고한 자리).
   ⛔ 처음에 **원문 그대로** 비교해 「교집합 0」을 얻었다. 표기가 다를 뿐이었다 —
      API 는 `2019-20`, 게시판은 `제2019-20호(2019.08.13)`. **D-117 그대로다:
      매칭은 정규화문, 보관은 원문.**
   🔴 **「합집합 781 · 새로 얻는 것 316」을 재검했다** (2026-09-11 · D-178).
      그 수는 **틀린 수가 아니라 다른 게이트 상태에서 잰 맞는 수**다 —

        [인정번호 단독 · 원료 대조 없음]   합집합 781 · 게시판 밖 **316**   ← 종전 수치, 재현됨
        [정본 축만 · I-0040 제외]         합집합 509 · 게시판 밖 **44**    ← 2층 적법라벨의 실제 크기

      ★ **「새로 얻는 것 316」이 아니라 44 다.** 나머지는 표시 문구 관측이지 인정 사실이 아니다.
      `--verify` 가 두 줄을 **함께** 찍는다 — 수 하나만 적으면 다음 사람이 또 오해한다.

🔴 **인정번호와 기능성문구는 마스킹을 지나도 한 글자도 안 바뀌어야 한다** (D-156).
   `mfds_hf.py` 와 같은 이유다 — 인정번호가 지워지면 「적법하다는 근거」가 사라진
   「적법」 딱지만 남는다. `--dump` 마다 재고, 어긋나면 **멈춘다.**

원천 행 수 (2026-09-10 정정 · D-54) —
  `mfds_hf_ingredient` 773행 · `mfds_hf_individual` 447행
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import unicodedata

from collect import store
from preprocess import mask

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

#: 🔴 **정본 축** — 원료 대장. 여기서만 「지위: 인정」이 나온다.
OFFICIAL = "mfds_hf_individual"
#: 🔴 **관측 축** — 업체 신고 현황. 「지위」를 붙이지 않는다.
OBSERVED = "mfds_hf_ingredient"

# 🚨 담는 필드만 적는다. 여기 없는 열은 **아예 안 담는다** (D-159) —
#    BSSH_NM(업체명) · ADDR(주소) · INDUTY_NM(업종) 이 그것이다.
KEEP: dict[str, tuple[str, ...]] = {
    OBSERVED: (
        "HF_FNCLTY_MTRAL_RCOGN_NO",
        "FNCLTY_CN",
        "APLC_RAWMTRL_NM",
        "DAY_INTK_CN",
        "IFTKN_ATNT_MATR_CN",
        "PRMS_DT",
    ),
    OFFICIAL: (
        "HF_FNCLTY_MTRAL_RCOGN_NO",
        "PRIMARY_FNCLTY",
        "RAWMTRL_NM",
        "DAY_INTK_LOWLIMIT",
        "DAY_INTK_HIGHLIMIT",
        "WT_UNIT",
        "IFTKN_ATNT_MATR_CN",
    ),
}
PHRASE = {OBSERVED: "FNCLTY_CN", OFFICIAL: "PRIMARY_FNCLTY"}
MTRAL = {OBSERVED: "APLC_RAWMTRL_NM", OFFICIAL: "RAWMTRL_NM"}
RCOGN = "HF_FNCLTY_MTRAL_RCOGN_NO"
DIRS = {OBSERVED: OBSERVED, OFFICIAL: OFFICIAL}

OUT_OFFICIAL = "hf_api_labels.jsonl"
OUT_OBSERVED = "hf_display_claims.jsonl"

_KEY = re.compile(r"(\d{4})\s*-\s*(\d+)")
#: 원료명에 붙는 인정번호 꼬리 — 「(기능성원료인정제2007-10호)」·「(제2024-19호)」·「New제…」
_TAIL = re.compile(r"\(\s*(?:기능성원료인정|New|new|\s)*제?\s*\d{4}\s*-\s*\d+\s*호?\s*\)")
_DROP = re.compile(r"[\s®™()（）\[\]{}·ㆍ,./\\'\"“”‘’’-]")
#: 문구 비교에서 지우는 것 — 영문 병기 · 등급 괄호 · 항목 번호
_EN = re.compile(r"\(\s*영문\s*\).*", re.S)
_GRADE = re.compile(r"\(\s*(기타기능|생리활성기능|기타)\s*[^)]*\)")
_BULLET = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩◆▪■□○●※☞]")
#: 항목 번호 — 🚨 **앞이 공백일 때만** 지운다. 종전 후보 `[가-힣]\s*[).]` 는
#:    「도움을 줍니다.」의 **「다.」를 먹었다** — 어미를 맞추기 전에 어미를 지우고 있었다.
_ITEM = re.compile(r"(?:^|\s)(?:\d+|[ㄱ-힣])\s*[).]\s*", re.M)


def rcogn_key(value: object) -> str | None:
    """인정번호의 **정규화문**. 보관은 원문으로 한다 (D-117)."""
    m = _KEY.search(str(value or ""))
    return f"{m.group(1)}-{int(m.group(2))}" if m else None


#: 원료명에 섞이는 그리스 문자. 🚨 NFKC 가 안 바꾼다 — `β-glucan` 과 `b-glucan` 이 갈렸다.
_GREEK = str.maketrans("αβγδεωΑΒΓΔΕΩ", "abgdewabgdew")


def mtral_key(value: object) -> str:
    """원료명의 **정규화문** — 짝짓기의 둘째 축 (D-185).

    🚨 인정번호 꼬리를 떼는 것이 핵심이다. I-0050 은 `콩발효추출물(기능성원료인정제2007-10호)`
       처럼 적고 I-0040 은 `글루코사민` 처럼 적는다 — 꼬리를 안 떼면 **모든 짝이 불일치**로
       보이고, 떼고 나면 **진짜 불일치만** 남는다.
    """
    s = unicodedata.normalize("NFKC", str(value or ""))
    s = _TAIL.sub("", s)
    return _DROP.sub("", s).translate(_GREEK).lower()


def mtral_same(a: str, b: str) -> bool:
    """같은 원료인가. 한쪽이 다른 쪽을 품으면 같은 것으로 본다 (표기 차이가 잦다)."""
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _plain(s: str) -> str:
    """존댓말 어미를 개조식으로 낮춘다 — 「줍니다」→「줌」·「있습니다」→「있음」.

    🚨 낱말 표가 아니라 **자모 연산**으로 한다. ⛔ 종전에 `습니다→음` 만 두었더니
       「도움을 **줍**니다」(2004-2 자일리톨)가 안 걸려 「다름」으로 샜다 —
       `줍`은 `주+ㅂ` 이고 `ㅂ니다` 는 종성 ㅂ 을 ㅁ 으로 바꾸면 개조식이 된다.
    """
    s = s.replace("습니다", "음")  # 🚨 먼저 — `있습니다` 의 `습` 은 `스+ㅂ` 이라 아래 규칙에 걸린다

    def fix(m: re.Match[str]) -> str:
        code = ord(m.group(1)) - 0xAC00
        if 0 <= code < 11172 and code % 28 == 17:  # 종성 ㅂ → ㅁ
            return chr(0xAC00 + code - 1)
        return m.group(1) + "ㅁ"

    return re.sub(r"([가-힣])니다", fix, s)


def claim_core(value: object) -> str:
    """문구의 **비교용 정규화문**. 🚨 보관은 원문으로 한다 (D-117).

    지우는 것 — 영문 병기 · 등급 괄호(`(기타기능II)`) · 항목 기호 · 공백 · 따옴표.
    맞추는 것 — 어미. I-0040 은 `~있습니다`(표시체), I-0050 은 `~있음`(고시체)이라
    이것을 안 맞추면 **43%만 일치**한다.
    """
    s = unicodedata.normalize("NFKC", str(value or ""))
    s = _EN.sub("", s).replace("(국문)", "")
    s = _GRADE.sub("", s)
    s = _ITEM.sub(" ", _BULLET.sub(" ", s))
    s = _plain(s)
    s = re.sub(r"도움이\s*될\s*수\s*있음", "도움을줄수있음", s)
    s = re.sub(r"도움이\s*됨", "도움을줌", s)
    return _DROP.sub("", s)


#: 🔴 **단정형** — 「도움을 줌」·「개선함」. 정본은 늘 가능형(「도움을 줄 수 있음」)이다.
#:    이것 자체가 하나의 위반 축이라 **범위(좁음/넓음)와 따로** 센다. 섞으면 둘 다 안 보인다 —
#:    2024-19 는 대상 한정이 빠지고(좁음) **동시에** 단정형이다.
_ASSERT = re.compile(r"도움을줌|도움이됨|개선함|증진함|완화함|예방함|치료")


def soften(core: str) -> str:
    """단정형을 가능형으로 낮춘다 — **범위만** 보고 싶을 때 쓴다."""
    return core.replace("도움을줌", "도움을줄수있음").replace("도움이됨", "도움을줄수있음")


def assertive_gap(observed: object, official: object) -> bool:
    """관측은 단정형인데 정본은 가능형인가."""
    a, b = claim_core(observed), claim_core(official)
    return bool(a and b and _ASSERT.search(a) and not _ASSERT.search(b))


#: 관측 문구 ↔ 정본 문구 대조 결과. 🚨 「좁음」이 곧 위법이라는 뜻은 아니다 — **후보**다.
VERDICTS = ("같음", "좁음", "넓음", "다름", "문구없음", "짝없음", "짝없음_원료불일치")
BORDERLINE = ("좁음", "넓음", "다름")


def compare(observed: str, official: str) -> str:
    """표시 문구가 정본 문구와 어떻게 다른가."""
    a, b = claim_core(observed), claim_core(official)
    if not a or a == "-":
        return "문구없음"
    if not b:
        return "짝없음"
    # 🚨 단정/가능의 차이를 먼저 낮춘다 — 그것은 `assertive_gap` 이 따로 센다.
    #    안 낮추면 2024-19 처럼 **범위도 어긋난 건이 「다름」에 묻힌다.**
    a, b = soften(a), soften(b)
    if a == b:
        return "같음"
    if a in b:
        return "좁음"  # 정본의 일부만 — 대상 한정·항목 누락
    if b in a:
        return "넓음"  # 정본에 없는 말이 붙음 — 표시 지침·제품명·추가 표현
    return "다름"


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


def board_rows() -> dict[str, dict[str, str]]:
    """게시판 인정공고 — **1차 사료**다. `mfds_hf.py` 가 이미 뽑아 놓았다.

    돌려주는 값 — `{인정번호_정규화: {"원료키":…, "문구":…}}`
    🚨 게시판도 정본 축이다. I-0050 에 없는 인정번호를 게시판이 덮는다.
    """
    p = ROOT / "data" / "derived" / "mfds_hf_labels.jsonl"
    if not p.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        k = rcogn_key(r.get("인정번호"))
        if not k:
            continue
        out.setdefault(
            k,
            {
                "원료키": mtral_key(r.get("원료명")),
                "문구": " ".join(r.get("기능성문구") or []) or str(r.get("기능성내용") or ""),
            },
        )
    return out


def collect_rows(source: str) -> list[dict]:
    rows = []
    for r in _records(DIRS[source]):
        rows.append(
            {
                "원천": source,
                "인정번호": (r.get(RCOGN) or "").strip(),  # 🚨 원문 보관
                "인정번호_정규화": rcogn_key(r.get(RCOGN)),
                "원료명_정규화": mtral_key(r.get(MTRAL[source])),
                **{f: (r.get(f) or "").strip() for f in KEEP[source] if f != RCOGN},
            }
        )
    return rows


def official_index(rows: list[dict], board: dict[str, dict[str, str]]) -> dict[str, list[dict]]:
    """정본 색인 — `{인정번호: [{원료키, 문구, 원천}, …]}`.

    🚨 값이 **리스트**다. 같은 인정번호에 원료가 둘일 수 있다는 것을 실측으로 알았으므로
       (I-0040 2007-11), 정본 쪽도 하나라고 가정하지 않는다.
    """
    idx: dict[str, list[dict]] = {}
    for r in rows:
        k = r["인정번호_정규화"]
        if not k:
            continue
        idx.setdefault(k, []).append(
            {"원료키": r["원료명_정규화"], "문구": r[PHRASE[OFFICIAL]], "원천": OFFICIAL}
        )
    for k, v in board.items():
        idx.setdefault(k, []).append({"원료키": v["원료키"], "문구": v["문구"], "원천": "board"})
    return idx


def judge(row: dict, idx: dict[str, list[dict]]) -> dict:
    """관측 행 하나를 정본과 맞춰 본다. 🚨 **원료가 다르면 짝짓지 않는다** (D-170)."""
    k = row["인정번호_정규화"]
    cands = idx.get(k, []) if k else []
    matched = [c for c in cands if mtral_same(row["원료명_정규화"], c["원료키"])]
    if not matched:
        row["대조"] = "짝없음_원료불일치" if cands else "짝없음"
        row["정본_원천"] = None
        row["정본_문구"] = None
        # 🚨 「번호는 같은데 원료가 다르다」는 **버릴 사실이 아니다** — 키가 못 미덥다는 증거다
        row["번호충돌"] = bool(cands)
        row["단정형"] = False
        row["경계후보"] = False
        return row
    best = min(matched, key=lambda c: VERDICTS.index(compare(row[PHRASE[OBSERVED]], c["문구"])))
    row["대조"] = compare(row[PHRASE[OBSERVED]], best["문구"])
    row["정본_원천"] = best["원천"]
    row["정본_문구"] = best["문구"]
    row["번호충돌"] = len(matched) < len(cands)
    row["단정형"] = assertive_gap(row[PHRASE[OBSERVED]], best["문구"])
    row["경계후보"] = row["대조"] in BORDERLINE or row["단정형"]
    return row


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


def _write(name: str, rows: list[dict]) -> pathlib.Path:
    out = store.derived_dir(".") / name
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(store.stamp(r, r["원천"]), ensure_ascii=False) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="건기식 API 2종 → 정본 축 · 관측 축")
    ap.add_argument("--dump", action="store_true", help=f"{OUT_OFFICIAL} · {OUT_OBSERVED} 로 쓴다")
    ap.add_argument("--verify", action="store_true", help="세고 대조만 한다")
    args = ap.parse_args()

    rows = {s: collect_rows(s) for s in (OFFICIAL, OBSERVED)}
    keys = {s: {r["인정번호_정규화"] for r in v if r["인정번호_정규화"]} for s, v in rows.items()}
    for s in (OFFICIAL, OBSERVED):
        phrase = sum(1 for r in rows[s] if r.get(PHRASE[s]))
        axis = "정본" if s == OFFICIAL else "관측"
        print(
            f"  [{axis}] {s:22} 행 {len(rows[s]):>4} · 고유번호 {len(keys[s]):>4} · 문구 {phrase:>4}"
        )

    # 🔴 **키가 유일한가를 먼저 묻는다** — 이 물음이 없어서 두 원천을 한 표로 오해했다
    for s in (OFFICIAL, OBSERVED):
        dup = len(rows[s]) - len(keys[s])
        if dup:
            print(f"  🟡 {s}: 인정번호가 행보다 {dup}개 적다 — **번호가 유일하지 않다**")

    board = board_rows()
    idx = official_index(rows[OFFICIAL], board)
    observed = [judge(dict(r), idx) for r in rows[OBSERVED]]

    tally = {v: sum(1 for r in observed if r["대조"] == v) for v in VERDICTS}
    print(f"\n  게시판(mfds_hf) 고유 인정번호 {len(board)}")
    print("  관측 축 ↔ 정본 대조 — " + " · ".join(f"{k} {v}" for k, v in tally.items() if v))
    cand = sum(1 for r in observed if r["경계후보"])
    clash = sum(1 for r in observed if r["번호충돌"])
    hard = sum(1 for r in observed if r["단정형"])
    print(f"  🔴 경계 사례 후보 {cand}건 (그중 단정형 {hard}건)")
    print(f"  🟡 번호는 같은데 원료가 달라 짝을 안 지은 것 {clash}건 — 키가 못 미덥다는 증거다")

    # 🚨 수에 **게이트 조건**을 함께 적는다 (D-178). 종전의 「합집합 781 · 새로 얻는 것 316」은
    #    인정번호 **단독**으로, 그것도 유일하지 않은 키로 센 수였다.
    ind, ing, bk = keys[OFFICIAL], keys[OBSERVED], set(board)
    print(
        f"\n  [게이트: 인정번호 단독 · 원료 대조 없음] 합집합 {len(ind | ing | bk)}"
        f" · 게시판 밖 {len((ind | ing) - bk)}"
    )
    print(
        f"  [게이트: 정본 축만 · I-0040 제외] 합집합 {len(ind | bk)}"
        f" · 게시판 밖 {len(ind - bk)}   ← 2층 적법라벨의 실제 크기"
    )

    if args.verify:
        return 0

    for s in (OFFICIAL, OBSERVED):
        _check_intact(rows[s], s)
    print("  ✅ 인정번호·기능성문구 훼손 0 (D-156)")

    if args.dump:
        official = []
        for r in rows[OFFICIAL]:
            r = dict(r)
            r["층"] = "2층 적법라벨"
            r["지위"] = "인정"
            k = r["인정번호_정규화"]
            r["sources"] = sorted({OFFICIAL} | ({"board"} if k in board else set()))
            official.append(r)
        for r in observed:
            r["층"] = "표시 문구 관측"  # 🚨 「지위: 인정」을 붙이지 않는다 (D-185)
        p1, p2 = _write(OUT_OFFICIAL, official), _write(OUT_OBSERVED, observed)
        print(f"  💾 [정본] {len(official):>4}행 → {p1.relative_to(ROOT)}")
        print(f"  💾 [관측] {len(observed):>4}행 → {p2.relative_to(ROOT)}  (경계 후보 {cand})")
        print("  🚨 관측 축에는 「지위: 인정」이 없다 — 표시 문구는 인정 사실이 아니다 (D-185).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
