"""preprocess/mfds_press.py — 보도자료 붙임 표 → **1층 판정라벨** (D-167).

  uv run python launcher.py extract mfds_press --verify   # 표를 어떻게 갈랐는지 본다
  uv run python launcher.py extract mfds_press --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_press` (식약처 부당광고 점검 보도자료 · 첨부 PDF 107건)

──────────────────────────────────────────────────────────────
★ **받아 둔 것에서 1층 라벨이 더 나오는 마지막 자리다.**

  107개 PDF 가 이미 디스크에 있고 `evasion_scan` 이 위법 문구 77종까지 세어 두었는데,
  **라벨 추출기가 없어 파생물이 안 나오고 있었다.**

🚨 **표 머리글이 39종이다.** 원천이 회차마다 다르게 짠다 —

    연번 │ 제품 │ 주요 부당광고                                        13
    업체명 │ 제품 사진 │ 광고 내용                                      7
    연번 │ 업체명(업종) │ 소재지 │ 제품명(식품유형) │ 위반유형 │ 광고내용   3
    연번 │ 제품명(식품유형) │ 판매업체명(업종, 소재지) │ 판매금액 │ 광고 내용  3
    …

  ⛔ 머리글을 나열해 맞추지 않는다 — 다음 회차에 40번째가 나온다.
  ★ **열 이름의 뜻으로 가른다.** 「광고」가 든 열이 있으면 문구가 있는 표이고, 없으면 아니다.
    (실증대상 업체 목록·부적합 항목·담당부서 표가 그렇게 걸러진다.)

──────────────────────────────────────────────────────────────
🔴 **업체명과 소재지는 담지 않는다** (D-159 · D-166)

  표가 「판매업체명 **(업종, 소재지)**」처럼 한 셀에 셋을 담아 준다.
  ★ 그중 **업종만** 떠내고 업체명·소재지는 버린다 — 마스킹으로 가리는 것이 아니라 **안 담는다.**
  🚨 업종·식품유형을 담는 이유는 판정이 「표현 + **제품 지위**」의 함수이기 때문이다 (D-156).
     상호에서 짜내지 않는다 — 실측상 상호의 15.4% 만 업종을 암시하고 그나마 우리 축과 무관하다.

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed).
   이 원천에는 아직 `masking:` 선언이 없다. `--verify` 는 되고 `--dump` 는 거부한다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

from preprocess.text import quoted

SOURCE_ID = "mfds_press"
RAW_DIR = pathlib.Path("data/raw/mfds_press_pdf")  # 🚨 본문은 첨부 PDF 에만 있다 (D-118)
OUT = pathlib.Path("data/derived/mfds_press_labels.jsonl")

#: 열 이름 → 역할. 🚨 **머리글 전체가 아니라 열 하나씩** 본다 — 조합은 회차마다 다르다.
#:  ⛔ 순서가 있다. 「위반 내용」은 문구이고 「위반유형」은 유형이라, 유형을 먼저 본다.
#:  ⛔ 처음에 문구 키를 「광고」 한 낱말로 뒀다가 **부서명과 법률명**이 걸렸다 —
#:     「식품안전정책국 식품표시**광고**정책과」·「식품 등의 표시**광고**에 관한 법률」.
#:     담당부서 표가 통째로 문구 표로 잡혀 레코드 0 이 나왔다. **낱말이 아니라 열의 뜻**이다.
ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 🚨 「위반 내용」은 **문구가 아니라 유형 서술**이다 — 실측: 「거짓·과장된 표시·광고 등」.
    #    문구 쪽에 두면 인용이 없어 어차피 안 담기지만, **역할을 틀리게 적어 두지 않는다.**
    ("원천유형", ("위반유형", "위반 유형", "부당광고 유형", "광고 유형", "위반 내용", "위반내용")),
    (
        "문구",
        (
            "광고 내용",
            "광고내용",
            "부당광고",
            "부당 광고",
            "광고 문구",
            "광고문구",
            "표시·광고내용",
            "표시광고내용",
            "부당표시",
            "부당 표시",
            "위반 내용",
            "위반내용",
            "위반 사항",
            "위반사항",
        ),
    ),
    ("제품", ("제품", "품목", "취급제품")),
    # 🚨 식품유형이 **독립 열**로 오기도 한다 — 그때는 제품 셀 괄호에서 짜내지 않는다.
    ("식품유형", ("식품유형", "제품유형", "품목유형")),
    ("업종", ("업종",)),
    ("비고", ("비고",)),
)

#: 🔴 **담지 않는 열.** 세기만 한다 — 버린 것을 세지 않는 것이 제일 나쁘다.
#: 🚨 이 말이 머리글에 있으면 **문구 표가 아니다** — 담당부서·법률 전재 표다 (실측).
_NOT_TABLE = (
    "담당 부서",
    "담당부서",
    "책임자",
    "관한 법률",
    "보 도 자 료",
    "보도자료",
    "보 도 참 고",
)

DROP = (
    "업체",
    "업소",
    "소재지",
    "판매금액",
    "판매단가",
    "판매량",
    "점검기관",
    "사진",
    "연번",
    "연 번",
)

#: 셀 안 괄호에서 떠내는 것. 「판매업체명(업종, 소재지)」·「제품명(식품유형)」
_PAREN = re.compile(r"[（(]([^）)]{2,40})[）)]")
#: 업종은 「…업」으로 끝난다 — 소재지와 가르는 표지다.
_INDUSTRY = re.compile(r"[가-힣·\s]{2,30}업$")


def _n(s: str | None) -> str:
    return " ".join((s or "").split())


def role_of(col: str) -> str | None:
    """열 이름 하나의 역할. 🚨 못 알아본 열은 `None` — 부르는 쪽이 **센다.**"""
    c = _n(col)
    if not c:
        return None
    for role, keys in ROLES:
        if any(k in c for k in keys):
            return role
    return None


def industry_of(cell: str) -> str:
    """셀에서 **업종만** 떠낸다. 🔴 업체명·소재지는 버린다.

    「주식회사 제트샵 (건강기능식품유통 전문판매업, 강원 화천군)」 → 「건강기능식품유통 전문판매업」
    🚨 괄호 안이 「업종, 소재지」 순이라는 보장이 없다 — **「…업」으로 끝나는 조각**을 고른다.
    """
    for m in _PAREN.finditer(cell):
        for part in m.group(1).split(","):
            if _INDUSTRY.fullmatch(_n(part)):
                return _n(part)
    return ""


def kind_of(cell: str) -> str:
    """제품 셀의 괄호에서 **식품유형**. 「덱카닉정(고형차)」 → 「고형차」."""
    m = _PAREN.search(cell)
    if not m:
        return ""
    v = _n(m.group(1))
    if _INDUSTRY.fullmatch(v) or "," in v:
        return ""
    # 🚨 괄호 안이 늘 식품유형인 것은 아니다 — 「덴티오클린(Dentio clean)」처럼 **영문 제품명**이 온다.
    #    식품유형은 실측상 전부 한글이다(과·채가공품 · 기타가공품 · 고형차 …).
    return v if re.search(r"[가-힣]", v) else ""


#: 🚨 **[P1] 파싱 산출물을 캐시한다** — `evasion_scan` 과 같은 이유다. 표 추출은 107건에
#:    2분 넘게 걸리고, 그러면 열 이름 하나 고칠 때마다 2분을 낸다.
#:    **되돌리기 싼 구조가 실제로 되돌리게 한다** (D-118 ④).
CACHE = pathlib.Path("data/derived") / "mfds_press_pdf" / "tables"


def tables_of(path: pathlib.Path, *, refresh: bool = False) -> list[dict]:
    """PDF 의 표들. 캐시가 PDF 보다 새로우면 그것을 쓴다."""
    c = CACHE / f"{path.stem}.json"
    if not refresh and c.exists() and c.stat().st_mtime >= path.stat().st_mtime:
        return json.loads(c.read_text(encoding="utf-8"))
    import pdfplumber  # noqa: PLC0415

    got: list[dict] = []
    with pdfplumber.open(path) as d:
        for pno, pg in enumerate(d.pages, 1):
            for t in pg.extract_tables() or []:
                if t and len(t) >= 2 and t[0] and len(t[0]) >= 3:
                    got.append({"쪽": pno, "표": t})
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
    return got


def _pdfs() -> list[pathlib.Path]:
    got = sorted(RAW_DIR.glob("*.pdf"))
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 pdf 가 없다 —\n  먼저: uv run python -m collect.mfds_press"
        )
    return got


def _count_cols(stat: dict, head: list, roles: list, *, in_phrase_table: bool) -> None:
    """역할이 없어 **행에 안 담기는 열**을 센다.

    🔴 2026-09-09 — 여기가 비어 있었다. 원래는 「문구 열이 없는 표」에서만 셌고,
       **문구 표 안에서 역할 없이 빠지는 열은 아무도 세지 않았다** (모르는 열 6종 16회 ·
       버린 열 11종 69회). 바로 위 `DROP` 주석이 「버린 것을 세지 않는 것이 제일 나쁘다」인데
       그 일을 하고 있었다.

    🚨 **두 자리를 갈라서 센다.** 문구 없는 표의 모르는 열은 「우리가 안 쓰는 표」이고,
       문구 표 안의 모르는 열은 **판정 재료 옆에서 버려진 것**이라 무게가 다르다.
       실측으로 나온 것 — `광고 방법` 2 · `광고기간` 1 · `흑염소 함량(실제 / 표시)` 4.
       ⛔ **세기만 한다. `ROLES` 는 안 바꾼다** — 3회는 근거가 아니다 (D-40).
          늘어나는지 보고, 30 을 넘으면 그때 축을 연다.
    """
    suffix = "_문구표" if in_phrase_table else ""
    for c, r in zip(head, roles, strict=True):
        name = _n(c)
        if r is not None or not name:
            continue
        key = "버린열" if any(d_ in name for d_ in DROP) else "모르는열"
        stat[key + suffix][name[:24]] += 1


def extract(limit: int | None = None) -> tuple[list[dict], dict]:
    """레코드들과 계측. 🚨 마스킹은 여기서 하지 않는다 — 부르는 쪽이 정책을 지고 건다."""
    rows: list[dict] = []
    stat: dict = {
        "문서": 0,
        "표": 0,
        "문구열있음": 0,
        "버린열": collections.Counter(),
        "모르는열": collections.Counter(),
        # 🔴 문구 표 **안**에서 버려지는 열 — 판정 재료 옆에서 사라지는 것이라 따로 센다
        "버린열_문구표": collections.Counter(),
        "모르는열_문구표": collections.Counter(),
        "원천유형": collections.Counter(),
    }
    for p in _pdfs()[:limit]:
        stat["문서"] += 1
        for _tb in tables_of(p):
            pno, t = _tb["쪽"], _tb["표"]
            stat["표"] += 1
            cols = [role_of(c) for c in t[0]]
            # 🚨 담당부서·법률 표가 문구 표로 잡히지 않게 한 겹 더 — 실측으로 나온 형태다.
            if any(w in _n(" ".join(c or "" for c in t[0])) for w in _NOT_TABLE):
                continue
            if "문구" not in cols:
                _count_cols(stat, t[0], cols, in_phrase_table=False)
                continue
            stat["문구열있음"] += 1
            _count_cols(stat, t[0], cols, in_phrase_table=True)
            carry: dict[str, str] = {}
            for line in t[1:]:
                cell = {r: _n(c) for r, c in zip(cols, line, strict=True) if r}
                # 🚨 병합 셀은 빈 칸으로 온다 — 앞 행의 값을 잇는다.
                for k in ("제품", "업종", "원천유형"):
                    if cell.get(k):
                        carry[k] = cell[k]
                    else:
                        cell[k] = carry.get(k, "")
                qs = quoted(cell.get("문구", ""), min_len=2)
                if not qs:
                    continue
                if cell.get("원천유형"):
                    stat["원천유형"][cell["원천유형"]] += 1
                rows.append(
                    {
                        "보도자료": p.stem,
                        "쪽": pno,
                        "원천": SOURCE_ID,
                        "층": "1층 판정라벨",
                        # 🔴 업체명·소재지는 담지 않는다 (D-159)
                        "제품": re.sub(_PAREN, "", cell.get("제품", "")).strip(),
                        "식품유형": kind_of(cell.get("제품", "")),
                        "업종": industry_of(cell.get("업종", "")),
                        "원천유형": cell.get("원천유형", ""),
                        "문구": qs,
                        "비고": cell.get("비고", ""),
                    }
                )
    return rows, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="보도자료 붙임 표 → 1층 판정라벨 (D-167)")
    ap.add_argument("--verify", action="store_true", help="표를 어떻게 갈랐는지 본다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    ap.add_argument("--limit", type=int, default=None, help="앞 N개 PDF 만 (탐침)")
    a = ap.parse_args()

    rows, stat = extract(a.limit)
    qs = sum(len(r["문구"]) for r in rows)
    uniq = {q for r in rows for q in r["문구"]}
    print(f"레코드 {len(rows):,} · 문구 {qs:,}회 · **고유 {len(uniq):,}종**")
    print(
        f"  PDF {stat['문서']} · 표 {stat['표']:,} · 그중 광고 문구 열이 있는 표 {stat['문구열있음']}"
    )
    got = collections.Counter(k for r in rows for k in ("식품유형", "업종", "원천유형") if r[k])
    print(f"  함께 담은 구조 필드 — {dict(got) or '없음'}")
    print("  🔴 업체명·소재지는 담지 않는다 — 마스킹으로 가린 것이 아니라 **안 담았다** (D-159)")

    if a.verify:
        # 🔴 **문구 표 안**부터 본다 — 여기가 판정 재료 옆에서 버려지는 자리다 (2026-09-09).
        #    아래 「문구 없는 표」의 수는 우리가 안 쓰는 표라 무게가 다르다.
        print("\n  🔴 문구 표 **안**에서 행에 안 담긴 열 — 여기가 진짜 손실이다")
        print(
            f"     담지 않기로 한 것 {sum(stat['버린열_문구표'].values())}회"
            f" / {len(stat['버린열_문구표'])}종 (D-159)"
        )
        if stat["모르는열_문구표"]:
            print(
                f"     🚨 못 알아본 열 {sum(stat['모르는열_문구표'].values())}회"
                f" / {len(stat['모르는열_문구표'])}종 — **세기만 한다.**"
            )
            for k, v in stat["모르는열_문구표"].most_common(12):
                print(f"       {v:>4}  {k}")
            print("     ⛔ 30 을 넘기 전에는 `ROLES` 를 안 바꾼다 (D-40). 늘어나는지만 본다.")

        print("\n  버린 열 (담지 않기로 한 것 · 문구 없는 표)")
        for k, v in stat["버린열"].most_common(12):
            print(f"    {v:>4}  {k}")
        if stat["모르는열"]:
            print(f"\n  🚨 못 알아본 열 {len(stat['모르는열'])}종 — 🔴 **전부 문구 없는 표다**")
            print("     실측 2026-09-09 — 처분 4종(업무정지·등록취소·시정명령·과징금)은")
            print("     「업무정지│등록취소│시정명령│과징금│경고│합계」 **한 줄짜리 집계표**다.")
            print("     `ROLES` 에 넣어도 문구 레코드는 한 줄도 안 는다. **넣지 않는다.**")
            for k, v in stat["모르는열"].most_common(15):
                print(f"    {v:>4}  {k}")
        if stat["원천유형"]:
            print("\n  ★ 원천이 유형을 적어 준 행")
            for k, v in stat["원천유형"].most_common(10):
                print(f"    {v:>4}  {k[:60]}")

    if a.dump:
        from preprocess.mask import POLICY  # noqa: PLC0415

        if SOURCE_ID not in POLICY:
            print(
                f"\n🔴 {SOURCE_ID!r} 의 마스킹 정책이 없다 — **내보내지 않는다** (D-72 fail-closed).\n"
                "   🚨 이 원천은 **적발 업체명이 표에 그대로 나온다** — 우리가 안 담을 뿐이다.\n"
                "      광고 문구 안에도 상호·인물이 섞여 들어올 수 있다(「약사 남OO」 실측).\n"
                "   고치는 법 — ① data_sources.yaml 의 masking: 기입 ② 2인 확인 ③ mask.POLICY 반영",
                file=sys.stderr,
            )
            return 1
        from preprocess.mask import apply_policy  # noqa: PLC0415

        out = []
        changed = collections.Counter()
        for r in rows:
            rec = dict(r)
            for f in ("제품", "문구"):
                if f == "문구":
                    m = [apply_policy(q, "", SOURCE_ID) for q in rec[f]]
                    changed[f] += sum(x != y for x, y in zip(rec[f], m, strict=True))
                    rec[f] = m
                elif rec[f]:
                    m2 = apply_policy(rec[f], "", SOURCE_ID)
                    changed[f] += m2 != rec[f]
                    rec[f] = m2
            out.append(rec)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'}")
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
