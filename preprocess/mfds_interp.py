"""preprocess/mfds_interp.py — 식약처 1차 법령해석(XML) → **표시·광고 질의회신 레코드** (2026-10-03).

  uv run python -m preprocess.mfds_interp            # 센다
  uv run python -m preprocess.mfds_interp --verify   # 받은 것과 대조한다(일련번호 · 빈 칸 · 그물 수)
  uv run python -m preprocess.mfds_interp --dump     # 🔴 마스킹 정책이 있어야 한다

원천: `mfds_cgm_expc` (법제처 「중앙부처 1차 해석」 — 식품의약품안전처 · 해석 하나에 XML 하나)

──────────────────────────────────────────────────────────────
★ **레코드 = 해석 하나** — 안건명 · 질의 · 답변 · 관련법령

  5,129 건의 대부분은 수입신고 · 품목허가 · 시험법 같은 절차 질의다. **표시·광고 판단의 그물**에 걸린 것만 싣는다.
  그물(`in_scope`) = ① 식품 · 화장품의 **표시·광고 규범**을 글 어디서든 드는 해석(`ARTICLES`)
                   ∪ ② 질의 · 안건명에 「광고」가 있고 품목이 식품 · 화장품(또는 관련법령이 빈) 해석.
  실측(2026-10-03 · 클론 B 원문 · 작업공간) — 해석 5,129 → 그물 **427**: 식품 240 · 화장품 187.
    조항 — 식품표시광고법 제8조 187 · 화장품법 제13조 170 · 화장품 실증 규정 82 · 화장품 지침 80 ·
           식품 부당광고 고시 52 · 식품위생법 제13조(구법) 10 · 조항 없이 질의에 「광고」만 17.
    질의에 「광고」가 있는 해석 126 · 같은 질의가 두 번 실린 것 19(`같은_질의`) · 기준시점 없음 83.
  🚨 `preprocess/interp_scan.py` 의 그물(`AD_ARTICLES`)은 **관련법령 칸만** 본다 — 계측용이다(식품 제8조 168).
     여기는 글 전체를 본다(187): 답변이 조문을 드는데 관련법령 칸이 빈 해석이 있다. 두 그물은 묻는 것이 달라 합치지 않았다.
  🚨 **그물은 판정이 아니다** — 식품 제8조가 걸린 해석의 다수는 제품명 · 원재료 **표시 기준** 질의다
     (「제품명에 '오곡'을 쓰면 함량을 적나」). 광고 문구의 가부를 답한 해석인지는 판독 판이 가른다.
     기계가 줄 수 있는 것만 싣는다 — `광고질의`(질의에 「광고」) · `인용표현`(질의 · 답변의 따옴표 안 문구).

★ **라벨을 만들지 않는다** — 회답은 「민원 답변」이다(`판정지위: 질의회신` · D-240). 스스로 「이후 개정 법규 · 사실관계에
  따라 달리 적용될 수 있다」고 적는다. 호까지 적은 해석은 6 건뿐이라 `관련법령` 은 원문 그대로 옮긴다.
  · `기준시점` — 답변의 「YYYY년 M월 현재」가 먼저, 없으면 해석일자. 둘 다 없으면 None(옛 질의회신).
  · `구법` — 식품위생법 제13조(허위표시 금지 · 2019-03 식품표시광고법으로 옮겨 감)를 드는 해석. 조문 번호를 지금 번호로 읽지 않는다.
  · `답변_출처` — 「(답변 출처) 2023년 자주하는 질문집 :」 꼴이 있으면 옮긴다. 책자에서 옮겨 실은 해석이다.

★ **겹침** (2026-10-03 · 작업공간) — 화장품법 제13조 해석 170 가운데 질의가 2025 질문집에 그대로 있는 것 3 ·
  2020 질문집 0 · 2021 질의응답집 0. 화장품 쪽은 거의 다 새 글이다(2024-12 등록분 147).

★ **담지 않는 것** (D-159) — 그물 밖 해석 · 질의기관 · 등록일시 같은 관리 칸. 전화번호는 `[전화]` 로 바꾼다
  (답변 속 협회 · 기관 대표 전화 — 마스킹 축에 전화가 없다).

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed · `preprocess.mask.apply_policy` · 정책 org · person).
  ★ **사람 축은 좁게 건다** (`mask.PERSON_STRICT` · 2026-10-03) — 넓은 규칙은 이 원천에서 치환 280 이 전부 오탐이었다
     (제품명 예시의 빈칸 「흑마늘○○」 · 숫자 자리 「000밀리그램」). 좁은 규칙은 직함 · 호칭 · 조사가 곁에 있을 때만 바꾼다 — 치환 0.
  🔴 **사람 축 치환이 한 건이라도 생기면 멈춘다** (`check_person`) — 이 원천은 0 이 정상이다. 새로 받은 해석에서 걸리면
     실제 이름이거나 새 오탐이다. 사람이 보고 정한다: 이름이면 그대로 두고 `PERSON_SEEN` 에 일련번호를 적는다 ·
     보통 낱말이면 `mask._S_NOT_NAME` 에 넣는다. 조용히 지나가지 않는다 (D-220).
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

from collect import store
from preprocess.interp_scan import QUOTE_FAMILIES_AD, _fields
from preprocess.mfds_cosmetic_qa_2012 import _PHONE, MASK_PHONE
from preprocess.text import quoted

SOURCE_ID = "mfds_cgm_expc"
OUT = pathlib.Path("data/derived/mfds_cgm_expc_ad.jsonl")

#: 표시·광고 규범의 그물 — (이름, 품목, 정규식). 글 전체(안건명 · 질의 · 답변 · 이유 · 관련법령)에서 찾는다.
#: 🚨 계측 모듈의 `interp_scan.AD_ARTICLES` 는 관련법령 칸만 본다 — 서로 다른 물음이다(머리말)
ARTICLES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "식품표시광고법 제8조",
        "식품",
        re.compile(r"표시\s*[ㆍ·‧･]?\s*광고에\s*관한\s*법률[」｣]?.{0,25}제\s*8\s*조"),
    ),
    ("화장품법 제13조", "화장품", re.compile(r"화장품법[」｣]?.{0,25}제\s*13\s*조")),
    ("식품위생법 제13조(구법)", "식품", re.compile(r"식품위생법[」｣]?.{0,25}제\s*13\s*조")),
    (
        "화장품 지침",
        "화장품",
        re.compile(r"화장품\s*표시\s*[ㆍ·‧･.]?\s*광고\s*관리\s*(?:지침|가이드라인)"),
    ),
    ("화장품 실증 규정", "화장품", re.compile(r"화장품\s*표시\s*[ㆍ·‧･.]?\s*광고\s*실증")),
    (
        "식품 부당광고 고시",
        "식품",
        re.compile(
            r"부당한\s*표시\s*또는\s*광고로\s*보지\s*아니하는|부당한\s*표시\s*또는\s*광고의\s*내용\s*기준"
        ),
    ),
)
OLD_LAW = "식품위생법 제13조(구법)"
#: 관련법령이 이것만 들면 범위 밖이다(의료기기 · 의약품 광고는 이 서비스의 품목이 아니다)
_OUT_OF_SCOPE = re.compile(r"의료기기|약사법|의약외품|마약|체외진단|위생용품|인체조직|첨단재생")
_FOOD = re.compile(r"식품|축산물|건강기능")
#: 답변의 기준 시점 — 「2025년 11월 현재」
_AS_OF = re.compile(r"(20\d{2})년\s*(\d{1,2})월\s*현재")
#: 책자에서 옮겨 실은 해석 — 「(답변 출처) 2023년 자주하는 질문집 :」
_FROM = re.compile(r"\(\s*답변\s*출처\s*\)\s*([^:：\n]{2,60})")
_RULE = re.compile(r"-{5,}")

REGIME = {"판정지위": "질의회신"}
#: 그물 수의 하한 `[측정]` 2026-10-03 — 받은 것이 줄면(수집이 덜 됐으면) 검증이 멈춘다. 늘어나는 것은 정상이다
EXPECTED_MIN = 427
EXPECTED_TOTAL_MIN = 5129


def _n(s: str) -> str:
    return " ".join(s.split())


def _whole(f: dict[str, str]) -> str:
    return " ".join(f.get(k, "") for k in ("안건명", "질의요지", "회답", "이유", "관련법령"))


def articles(f: dict[str, str]) -> list[str]:
    text = _whole(f)
    return [name for name, _, pat in ARTICLES if pat.search(text)]


def item_of(f: dict[str, str], arts: list[str]) -> str:
    """품목 — 화장품 · 식품 · 범위밖 · 모름. 🚨 광고 규범이 걸렸으면 그 규범의 품목이 먼저다."""
    kinds = {kind for name, kind, _ in ARTICLES if name in arts}
    if len(kinds) == 1:
        return next(iter(kinds))
    law = f.get("관련법령", "")
    if "화장품" in law:
        return "화장품"
    if _FOOD.search(law):
        return "식품"
    if _OUT_OF_SCOPE.search(law):
        return "범위밖"
    text = _whole(f)
    if not law and _OUT_OF_SCOPE.search(f.get("안건명", "") + f.get("질의요지", "")):
        return "범위밖"
    if not law and "화장품법" in text:
        return "화장품"
    if not law and "식품" in text:
        return "식품"
    return "모름" if not law or kinds else "범위밖"


def in_scope(f: dict[str, str]) -> bool:
    arts = articles(f)
    if arts:
        return True
    asked = "광고" in f.get("안건명", "") + f.get("질의요지", "")
    return asked and item_of(f, arts) != "범위밖"


def _clean(text: str, stat: collections.Counter) -> str:
    out, n = _PHONE.subn(MASK_PHONE, _n(_RULE.sub(" ", text)))
    stat["전화"] += n
    return out


def record(f: dict[str, str], stat: collections.Counter) -> dict:
    arts = articles(f)
    answer = _clean(f.get("회답", ""), stat)
    reason = _clean(f.get("이유", ""), stat)
    day = f.get("해석일자", "")
    m = _AS_OF.search(answer)
    as_of = (
        f"{m.group(1)}-{int(m.group(2)):02d}"
        if m
        else f"{day[:4]}-{day[4:6]}"
        if len(day) >= 6
        else None  # noqa: PLR2004
    )
    src = _FROM.search(answer)
    rec = {
        "id": f.get("법령해석일련번호", ""),
        "품목": item_of(f, arts),
        "조항": arts,
        "구법": OLD_LAW in arts,
        "광고질의": "광고" in f.get("안건명", "") + f.get("질의요지", ""),
        "안건명": _clean(f.get("안건명", ""), stat),
        "질의": _clean(f.get("질의요지", ""), stat),
        "답변": answer,
        "이유": reason or None,
        "관련법령": _n(f.get("관련법령", "")),
        "해석일자": f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 else None,  # noqa: PLR2004
        "기준시점": as_of,
        "답변_출처": _n(src.group(1)) if src else None,
        "원천": SOURCE_ID,
        **REGIME,
    }
    rec["인용표현"] = quotes(rec)
    return rec


def quotes(rec: dict) -> list[str]:
    """질의 · 답변의 따옴표 안 문구 — 라벨 판의 후보. 🔴 낫표는 법령명이라 세지 않는다(`interp_scan` 과 같다)."""
    text = f"{rec.get('질의', '')}\n{rec.get('답변', '')}"
    return list(dict.fromkeys(quoted(text, min_len=2, max_len=120, families=QUOTE_FAMILIES_AD)))


def fields() -> list[dict[str, str]]:
    raw = store.family_path(SOURCE_ID)
    files = store.current_files(raw, "*.xml")
    if not files:
        raise FileNotFoundError(
            f"{raw} 에 *.xml 이 없다 —\n  먼저: uv run python launcher.py collect {SOURCE_ID}"
        )
    return [_fields(p) for p in files]


def raw_of(source: str) -> pathlib.Path:
    """원문 폴더 — 표(`store.FAMILY_OF`)에서 꺼낸다 (D-254)."""
    return store.family_path(source)


def parse(all_fields: list[dict[str, str]]) -> tuple[list[dict], dict]:
    """해석 전부 → (그물에 걸린 레코드, 계측). 🚨 마스킹은 여기서 하지 않는다 — 전화번호만 바꾼다."""
    stat: collections.Counter = collections.Counter()
    stat["해석"] = len(all_fields)
    rows = [record(f, stat) for f in all_fields if in_scope(f)]
    # 같은 질의가 두 번 실렸다 — 뒤의 것(해석일자 · 일련번호가 늦은 것)을 남기고 앞의 것에 그 id 를 적는다
    keep: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["해석일자"] or "", int(r["id"] or 0))):
        keep[re.sub(r"\W", "", r["질의"])] = r
    for r in rows:
        last = keep[re.sub(r"\W", "", r["질의"])]
        r["같은_질의"] = None if last is r or not r["질의"] else last["id"]
    stat["같은_질의"] = sum(1 for r in rows if r["같은_질의"])
    stat["빈_질의"] = sum(1 for r in rows if not r["질의"])
    stat["빈_답변"] = sum(1 for r in rows if not r["답변"])
    return rows, dict(stat)


def verify(all_fields: list[dict[str, str]]) -> list[str]:
    """🔴 받은 것과 대조한다 — 일련번호가 있고 겹치지 않나 · 답변이 비지 않았나 · 그물 수가 줄지 않았나."""
    rows, stat = parse(all_fields)
    bad: list[str] = []
    ids = [r["id"] for r in rows]
    if any(not i for i in ids):
        bad.append("일련번호가 빈 해석이 있다")
    if len(set(ids)) != len(ids):
        bad.append("일련번호가 겹친다")
    if stat["빈_답변"]:
        bad.append(f"답변이 빈 해석 {stat['빈_답변']}")
    if any(r["품목"] == "범위밖" and not r["조항"] for r in rows):
        bad.append("범위 밖 품목이 그물에 들었다")
    return bad


def check_received(stat: dict, n: int) -> list[str]:
    """🔴 받은 양 대조 — 실제 원문에만 건다(합성 글에는 걸지 않는다). 줄었으면 수집이 덜 된 것이다."""
    bad: list[str] = []
    if stat["해석"] < EXPECTED_TOTAL_MIN:
        bad.append(f"해석 {stat['해석']:,} — 잰 판은 {EXPECTED_TOTAL_MIN:,} 이었다(수집이 덜 됐다)")
    if n < EXPECTED_MIN:
        bad.append(f"그물 {n} — 잰 판은 {EXPECTED_MIN} 이었다")
    return bad


#: 사람이 보고 「실제 이름이 맞다」고 확인한 해석의 일련번호 — 여기 있으면 `check_person` 이 멈추지 않는다.
#: 🚨 지금은 비어 있다(원천 전체에 사람 이름 0 · 2026-10-03). 채우는 것은 사람이다
PERSON_SEEN: frozenset[str] = frozenset()
_PERSON_RULES = ("엄격·", "가려진이름", "직함+이름", "부분가림", "이름+직함")


#: 마스킹을 거는 자리 — 🚨 인용표현은 마스킹된 본문에서 다시 뜬다
MASK_FIELDS = ("안건명", "질의", "답변", "이유")


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter, list[dict]]:
    """마스킹을 건 사본과 계측. **산출물로 나가는 모든 길이 여기를 지난다.** 치환 기록에 해석 id 를 단다."""
    from preprocess.mask import apply_policy  # noqa: PLC0415

    log: list[dict] = []
    changed: collections.Counter = collections.Counter()
    out: list[dict] = []
    for r in rows:
        rec = dict(r)
        for f in MASK_FIELDS:
            if rec.get(f):
                before = len(log)
                m = apply_policy(rec[f], "", SOURCE_ID, log)
                for entry in log[before:]:
                    entry["id"], entry["칸"] = r["id"], f
                if m != rec[f]:
                    changed[f] += 1
                rec[f] = m
        rec["인용표현"] = quotes(rec)
        out.append(rec)
    return out, changed, log


def check_person(log: list[dict]) -> list[str]:
    """🔴 사람 축 치환이 생겼나 — 확인된 해석(`PERSON_SEEN`) 밖에서 한 건이라도 있으면 멈춘다."""
    hits = collections.Counter(
        (e["id"], e["칸"], e["규칙"])
        for e in log
        if e["규칙"].startswith(_PERSON_RULES) and e.get("id") not in PERSON_SEEN
    )
    return [
        f"사람 축 치환 — 해석 {i} 의 {f} · {rule} {n}곳. 실제 이름인지 본다(머리말)"
        for (i, f, rule), n in sorted(hits.items())
    ]


def _report(rows: list[dict], stat: dict) -> None:
    count = collections.Counter
    print(f"해석 {stat['해석']:,} → 표시·광고 그물 {len(rows):,}")
    for k, v in count(r["품목"] for r in rows).most_common():
        print(f"    {v:>4}  {k}")
    print("\n  조항 (그물이다 — 판정이 아니다)")
    for k, v in count(a for r in rows for a in r["조항"]).most_common():
        print(f"    · {v:>4}  {k}")
    print(f"    · {sum(1 for r in rows if not r['조항']):>4}  조항 없이 질의에 「광고」만")
    asked = [r for r in rows if r["광고질의"]]
    print(
        f"\n  질의에 「광고」가 있는 해석 {len(asked)} · 인용표현 {sum(len(r['인용표현']) for r in rows):,}건"
        f"(그중 광고 질의 {sum(len(r['인용표현']) for r in asked):,}건)"
    )
    print(
        f"  기준시점 없음 {sum(1 for r in rows if not r['기준시점'])} · 구법 {sum(1 for r in rows if r['구법'])}"
        f" · 책자에서 옮긴 것 {sum(1 for r in rows if r['답변_출처'])} · 같은 질의 {stat['같은_질의']}"
        f" · 전화번호 {stat.get('전화', 0)}곳을 {MASK_PHONE} 로 바꿨다"
    )
    for k in ("빈_질의", "빈_답변"):
        if stat[k]:
            print(f"  🚨 {k} {stat[k]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="식약처 1차 법령해석 → 표시·광고 질의회신 레코드")
    ap.add_argument("--verify", action="store_true", help="받은 것과 대조한다")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    a = ap.parse_args()

    got = fields()
    rows, stat = parse(got)
    out, changed, log = masked(rows)
    bad = verify(got) + check_received(stat, len(rows)) + check_person(log)
    if a.verify:
        if bad:
            print("🔴 받은 것과 어긋난다 — 파싱 결과를 믿지 않는다:", file=sys.stderr)
            for b in bad:
                print(f"  · {b}", file=sys.stderr)
            return 1
        print("★ 대조 통과 — 일련번호 · 답변 · 그물 수가 잰 판 이상이다 · 사람 축 치환 0")
    _report(rows, stat)

    if a.dump:
        if bad:  # 🔴 대조가 깨진 파싱은 파생물로 내보내지 않는다 (D-72)
            print(f"\n🔴 대조 실패 {len(bad)}건 — 쓰지 않았다. `--verify` 로 본다", file=sys.stderr)
            return 1
        lost = sum(len(x["인용표현"]) for x in rows) - sum(len(x["인용표현"]) for x in out)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'} · 치환 {len(log)}건")
        print(f"  {'🚨' if lost else '★'} 마스킹으로 사라진 인용표현 {lost}건")
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
