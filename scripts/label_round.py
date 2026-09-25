"""scripts/label_round.py — 라벨 **한 판(round)** 을 짜고, 갈린 것을 판정한다 (2026-09-20).

  uv run python scripts/label_round.py plan round2 --who 권소라,소성민,박수진,이서은
  uv run python scripts/label_round.py compare --sheet data/derived/label_rounds/round2_labelsheet.jsonl build/labels/*__round2_labelsheet.csv
  uv run python scripts/label_round.py decide build/labels/판정__round2_labelsheet.csv --sheet data/derived/label_rounds/round2_labelsheet.jsonl

팀장 — *「2차 라벨 시트 구성을 사람이 직접 하는 건 정확도가 떨어질 것 같은데」* →
*「이 흐름으로 시트를 설계하되 기존 시트도 이 방법대로 다시 하는 건 어때? 그리고 팀원들이 시트를 작성하기 편하게」*.

★ **흐름** — 사람이 틀리는 것을 없앨 수는 없다. **틀린 것이 드러나게** 짠다.

  1 plan     한 판을 짠다 — 기관이 묶어 둔 분류 안에서 고르게(보기 2~3개) · 일부는 **전원이 겹쳐** 붙인다(κ) ·
             정답을 아는 **검증 행**을 섞는다(사람마다 정답률) · **기존 시트를 다른 사람이 다시** 붙인다(재검)
  2 (사람)   CSV 의 `유형번호` 한 칸만 채운다 → 팀장에게 보낸다
  3 import   `label_sheet.py import` — 검증 행은 라벨로 안 들어가고 정답률만 낸다
  4 compare  사람끼리 갈린 행 + (있으면) 참고 답과 다른 행 → 판정표 한 장
  5 decide   판정자가 `최종번호` 를 채운 판정표를 들인다 → **판정 레코드**(합의보다 앞선다 · `labels.consensus`)

🚨 **참고 답(`--ref`)은 라벨이 아니다** — LLM 이 붙인 CSV 를 넣어도 `labels/` 에 안 들어가고 판정표에 칸으로만 선다.
   모델이 붙인 정답으로 모델을 채점하면 틀린 것이 겹쳐 성능이 부풀기 때문이다.
🚨 **정본에서만 쓴다**(시트·라벨은 파생물의 원천·표본 · D-226 · D-249). 팀원 기기에서는 CSV 를 채워 보내기만 한다.
🔴 **다수결을 하지 않는다**— 갈린 행은 판정자가 보고 정한다. 판정자 이름이 레코드에 남는다.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collect import registry  # noqa: E402
from preprocess import labels as store  # noqa: E402
from scripts import label_sheet as ls  # noqa: E402

DERIVED = ROOT / "data" / "derived"
#: 판마다의 시트 — 🚨 경로를 **한 폴더**로 둔다. 파생물 원장이 「누가 만들었나」를 이 폴더 이름으로 찾는다
#:    (`derived_manifest.match_writers` · 이름이 판마다 달라 파일명 상수로는 못 찾는다). 부류는 `_labelsheet` = 표본
ROUNDS = ROOT / "data" / "derived" / "label_rounds"
GUIDE = DERIVED / "mfds_guide_labels.jsonl"
DECC = DERIVED / "decc_phrases.jsonl"
GOLDEN = DERIVED / "golden" / "golden.jsonl"
#: 재검할 기존 시트 — 이미 붙인 사람 **말고** 다른 사람에게 간다
RECHECK = (DERIVED / "mfds_guide_labelsheet.jsonl",)

#: 해설서의 뭉친 분류 → 이번 판에서 얼마나 담나. `None` = 남은 것 전부.
#: 🚨 **평가 4유형 부족분**(2026-09-20 `golden` 실측 · 비방 12 · 의약품 8 · 질병 6 · 후기 1)을 채우는 쪽으로 기운다.
#: `[임의]` 150 — 질병 묶음 437(10자 이상) 중 단서 있는 것을 앞에 두고 자른 크기. 사람 품과 기대치(의약품 ~44 · 질병 ~22)의 절충
GUIDE_CLASSES: dict[str, int | None] = {
    "질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동": 150,
    "부당한 비교ㆍ비방": None,
}
#: 「거짓ㆍ과장ㆍ기만」 묶음에서는 **후기 단서가 있는 것만** — 나머지는 이미 평가가 충분하다
REVIEW_CUE = re.compile(r"후기|체험|경험담|먹어\s*보|써\s*보|리뷰|소감|했더니")
#: 질병 묶음 안에서 **앞에 둘** 것 — 판정이 아니라 순서다
DISEASE_CUE = re.compile(r"치료|예방|질환|질병|증상|병|약|처방|특효|완치|개선")
#: `[임의]` 10자 — 사례집 낱말(평균 5.3자)이 문장 평가를 못 버틴 자리(D-155). 첫 시트(20자)보다 낮춘 이유는
#: 20자 이상 「비교ㆍ비방」이 첫 시트에서 거의 다 쓰였기 때문(남은 것 10~19자 약 40)
MIN_LEN = 10


#: 원천 칸이 없는 입력의 원천 — 🚨 `decc_phrases.jsonl` 은 행에 원천을 적지 않는다(재결례는 법제처 OPEN API · `law_go_kr`).
_SOURCE_OF = {"decc_phrases.jsonl": "law_go_kr"}


def _jl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        raise SystemExit(f"🔴 {p.relative_to(ROOT)} 가 없다 — 정본에서 파생물을 먼저 만든다 (D-72)")
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    # 🔴 변경금지(ND) 게이트 — 라벨 시트도 파생 데이터셋이다 (2026-09-25 · `registry.assert_derivable`)
    registry.assert_derivable(rows, who=f"label_round:{p.name}", default=_SOURCE_OF.get(p.name))
    return rows


def _cap() -> int:
    from app.settings import PARAMS  # noqa: PLC0415 — 보관 상한의 정본 (D-249)

    return PARAMS.quote_max_chars


def _seen_keys() -> set[str]:
    """이미 어느 시트·라벨에 든 문구 — 새 판에 다시 넣지 않는다(재검은 따로 넣는다)."""
    got = {store.key(r) for _, r in store._rows()}  # noqa: SLF001
    for sheet in [*DERIVED.glob("*_labelsheet.jsonl"), *ROUNDS.glob("*_labelsheet.jsonl")]:
        got |= {store.key(r) for r in ls._rows(sheet)}  # noqa: SLF001
    return got


def pool_guide(seen: set[str], rng: random.Random) -> list[dict]:
    cap = _cap()
    rows = [
        r
        for r in _jl(GUIDE)
        if r.get("종류") == "위반문구"
        and MIN_LEN <= len(str(r.get("문구") or "")) <= cap
        and store.key(r) not in seen
    ]
    out: list[dict] = []
    for cls, limit in GUIDE_CLASSES.items():
        got = [r for r in rows if r.get("원천라벨") == cls]
        rng.shuffle(got)
        got.sort(
            key=lambda r: not DISEASE_CUE.search(str(r["문구"]))
        )  # 단서 있는 것이 앞 (안정 정렬)
        out += got if limit is None else got[:limit]
    out += [
        r
        for r in rows
        if r.get("원천라벨") == "거짓ㆍ과장ㆍ기만" and REVIEW_CUE.search(str(r["문구"]))
    ]
    for r in out:
        r["참고"] = f"식약처 심의 지적 · {r.get('심의제도', '')}"
    return out


def pool_decc(seen: set[str]) -> list[dict]:
    """행정심판에서 처분이 유지된 사건의 광고 문구 — 기관 판단이 있다. 유형은 사람이 고른다."""
    cap = _cap()
    out = []
    for r in _jl(DECC) if DECC.exists() else []:
        text = str(r.get("문구") or "")
        rec = {
            "원천": "law_go_kr",
            "원천라벨": f"행정심판 {r.get('사건번호', '')}",
            "문구": text,
            "후보유형": [],
            "참고": f"행정심판 · {str(r.get('주문', ''))[:16]} · 근거 {r.get('근거조문', '')}"[
                :150
            ],
        }
        if MIN_LEN <= len(text) <= cap and store.key(rec) not in seen:
            out.append(rec)
    return out


def pool_recheck() -> list[dict]:
    """기존 시트 중 **누가 이미 붙인** 행 — 그 사람 말고 다른 사람이 가려서(블라인드) 다시 붙인다."""
    who_by_key: dict[str, set[str]] = collections.defaultdict(set)
    for fname, r in store._rows():  # noqa: SLF001
        if store.label(r) or (r.get("판단") or "").strip() == store.OUT_OF_SCOPE:
            who_by_key[store.key(r)].add(store.person(fname, r))
    out = []
    for sheet in RECHECK:
        if not sheet.exists():
            continue
        for r in ls._rows(sheet):  # noqa: SLF001
            k = store.key(r)
            if k in who_by_key:
                rec = {f: v for f, v in r.items() if f not in store.HUMAN and f != "판단"}
                rec["재검_제외"] = sorted(who_by_key[k])
                # 🚨 「재검」이라고 적지 않는다 — 앞사람이 있었다는 것만으로 판단이 기운다(블라인드)
                rec["참고"] = f"식약처 심의 지적 · {r.get('심의제도', '')}"
                out.append(rec)
    return out


def pool_gold(n: int, rng: random.Random) -> list[dict]:
    """정답을 아는 문구 — 공정위 의결서 **주문**이 한 유형만 단 것. 사람마다 정답률을 잰다(라벨로 안 쓴다)."""
    rows = [
        r
        for r in _jl(GOLDEN)
        if r.get("provenance") == "ftc_decisions_body"
        and r.get("split") == "test_sentence"
        and len(r.get("labels") or []) == 1
        and MIN_LEN <= len(str(r.get("text") or "")) <= _cap()
    ]
    rng.shuffle(rows)
    # 🚨 `참고` 는 사실대로 적는다(공정위 의결) — 검증 행이라는 것만 안 드러낸다. 보기는 전체(1~8)
    return [
        {
            "원천": "검증",
            "원천라벨": "공정위 의결 · 주문",
            "문구": r["text"],
            "후보유형": [],
            "검증정답": r["labels"],
        }
        for r in rows[:n]
    ]


def assign(
    rows: list[dict], who: list[str], overlap: float, rng: random.Random
) -> dict[str, list[int]]:
    """행 번호(1부터) → 사람. 새 행의 `overlap` 은 **전원**, 나머지·재검은 한 사람씩, 검증 행은 전원."""
    fresh = [i for i, r in enumerate(rows, 1) if "재검_제외" not in r and "검증정답" not in r]
    rech = [i for i, r in enumerate(rows, 1) if "재검_제외" in r]
    gold = [i for i, r in enumerate(rows, 1) if "검증정답" in r]
    rng.shuffle(fresh)
    n_shared = round(len(fresh) * overlap)
    shared, rest = fresh[:n_shared], fresh[n_shared:]
    got: dict[str, list[int]] = {w: list(shared) + list(gold) for w in who}
    load = dict.fromkeys(who, 0)
    for i in rest:
        w = min(who, key=lambda x: load[x])
        got[w].append(i)
        load[w] += 1
    for i in rech:
        ok = [w for w in who if w not in rows[i - 1]["재검_제외"]]
        if not ok:
            raise SystemExit(
                f"🔴 {i}행을 다시 붙일 사람이 없다 — 이미 붙인 사람만 있다: {rows[i - 1]['재검_제외']}"
            )
        w = min(ok, key=lambda x: load[x])
        got[w].append(i)
        load[w] += 1
    return {w: sorted(v) for w, v in got.items()}


def _first_by_key(rows: list[dict]) -> list[int]:
    """행 번호(1부터) → 같은 키의 **첫 행** 번호. 🆕 2026-09-24.

    🔴 라벨은 **키**(`labels.key` — 원천 · 원천라벨 · 문구 …)로 쌓인다. 시트에 키가 같은 행이 둘이면
       사람에게는 두 행이지만 라벨 저장소에는 **한 자리**다. 2차 시트(round2)에 이런 쌍이 셋 있었다
       (해설서 표 47·48 의 같은 문구 · 같은 행정심판 사건 · 같은 검증 문구) —
       ⛔ `compare` 는 앞 행의 라벨을 뒤 행에 **한 번 더** 붙여 판정표에 같은 문구를 두 번 올렸고,
       ⛔ `decide` 는 두 판정을 다 써서 `consensus` 가 **나중 것으로 조용히 덮었다**.
    ★ 같은 키는 첫 행 하나로 모은다 — 키에 `표` 가 없는 것은 설계다(같은 문구는 같은 라벨).
    """
    first: dict[str, int] = {}
    return [first.setdefault(store.key(r), i) for i, r in enumerate(rows, 1)]


def _dedup_keys(rows: list[dict]) -> tuple[list[dict], int]:
    """🆕 2026-09-24 — 판을 짤 때 **같은 키의 행을 한 번만** 담는다(`_first_by_key` 참조)."""
    seen: set[str] = set()
    kept = []
    for r in rows:
        k = store.key(r)
        if k in seen:
            continue
        seen.add(k)
        kept.append(r)
    return kept, len(rows) - len(kept)


def plan(name: str, who: list[str], overlap: float, gold: int, seed: int) -> int:
    from scripts import derived_manifest as dm  # noqa: PLC0415

    why = dm.not_canonical("label_round plan")
    if why:
        print(why, file=sys.stderr)
        return 1
    if len(who) < 2:
        print("🔴 두 사람 이상이 필요하다 — 겹쳐 붙여야 일치도(κ)가 나온다", file=sys.stderr)
        return 1
    sheet = ROUNDS / f"{name}_labelsheet.jsonl"
    if sheet.exists():
        print(
            f"🔴 {sheet.relative_to(ROOT)} 가 이미 있다 — **다시 뽑지 않는다**(표본이 갈린다 · 지시서 보충 §1).\n"
            "   새 판이면 다른 이름을 준다",
            file=sys.stderr,
        )
        return 1
    rng = random.Random(seed)
    seen = _seen_keys()
    parts = {
        "해설서(새)": pool_guide(seen, rng),
        "행정심판": pool_decc(seen),
        "재검(기존 시트)": pool_recheck(),
        "검증": pool_gold(gold, rng),
    }
    rows, n_dup = _dedup_keys([r for v in parts.values() for r in v])
    rng.shuffle(rows)  # 🚨 섞는다 — 검증 행이 끝에 몰리면 행 번호로 드러난다
    table = assign(rows, who, overlap, rng)

    sheet.parent.mkdir(parents=True, exist_ok=True)
    with sheet.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"시트 {sheet.relative_to(ROOT)} — {len(rows)}행 (seed {seed})")
    for k, v in parts.items():
        print(f"    {k:<14} {len(v):>4}")
    if n_dup:
        print(
            f"    🟡 같은 키(원천·원천라벨·문구)라 한 번만 담은 행 {n_dup}개 — 라벨은 키로 쌓인다"
        )
    print(f"\n배정 — 전원 겹침 {round(overlap * 100)}% · 검증 {gold}행은 전원(라벨로 안 들어간다)")
    for w, idx in table.items():
        out = ls.export(sheet, w, None, idx=idx, quiet=True)
        print(f"    {w:<8} {len(idx):>4}행  → {out.relative_to(ROOT)}")
    print(f"    번호표   → {(ls.OUT_DIR / '유형번호표.csv').relative_to(ROOT)} (함께 보낸다)")
    print(
        "\n  🚨 행정심판 행을 평가셋에 넣으려면 골든셋 계보표(`preprocess/lineage.py`)에 한 줄이 필요하다 —\n"
        "     없으면 `golden --write` 가 「모르는 계보」로 멈춘다(정상 · 재배포 불가로 둘지 판정)\n"
        "\n  다음 — 각자 CSV 를 채워 팀장에게 보낸다(파일 이름 그대로) → 정본에서\n"
        f"    uv run python launcher.py labelsheet import build/labels/<이름>__{sheet.stem}.csv --sheet {sheet.relative_to(ROOT)}\n"
        f"    uv run python scripts/label_round.py compare --sheet {sheet.relative_to(ROOT)} build/labels/*__{sheet.stem}.csv\n"
        "  🚨 시트는 표본이다 — `derived-manifest --write` → 원장 커밋 → `data-publish` (D-249 · git 에 안 올린다)"
    )
    return 0


def _norm(raw: str) -> str:
    raw = (raw or "").replace(" ", "").replace(";", ",")
    if raw == ls.OUT_OF_SCOPE_NO:
        return "0"
    return ",".join(sorted({x for x in raw.split(",") if x}))


#: 🔄 2026-09-22 (D-262) — 「합의 유형」·「갈린 유형」 칸. 판정자는 **갈린 유형만** 보고 `최종번호` 에 전체를 적는다.
PANEL = [
    "행", "문구", "참고", "보기", "사람들 답", "합의 유형", "갈린 유형", "참고 답", "최종번호", "메모", "판정자", "지문",
]  # fmt: skip


def _names(nums: frozenset[str]) -> str:
    return " · ".join(
        "0 범위밖" if n == "0" else f"{n} {ls.TYPES[int(n) - 1]}" for n in sorted(nums, key=int)
    )


def compare(sheet: pathlib.Path, csvs: list[pathlib.Path], refs: list[pathlib.Path]) -> int:
    """갈린 행 → 판정표 한 장. 🚨 **세기만 한다** — 라벨을 쓰지 않는다."""
    rows = ls._rows(sheet)  # noqa: SLF001
    canon = _first_by_key(rows)  # 🆕 2026-09-24 — 같은 키의 행은 첫 행으로 모은다
    dup_rows = sum(1 for i, c in enumerate(canon, 1) if c != i)
    clash: list[str] = []
    ans: dict[int, dict[str, str]] = collections.defaultdict(dict)
    ref: dict[int, dict[str, str]] = collections.defaultdict(dict)
    for group, paths in ((ans, csvs), (ref, refs)):
        for p in paths:
            for rec in ls.load_csv(p):
                i = int(rec["행"])
                if not ls.row_matches(rows[i - 1], rec)[0]:
                    raise SystemExit(
                        f"🔴 {p.name} {i}행의 `문구` 가 바뀌었다 — 되돌린 뒤 다시 한다"
                    )
                v = _norm(rec.get("유형번호") or "")
                if v:
                    i, who = canon[i - 1], (rec.get("붙인이") or p.stem).strip()
                    if group[i].get(who, v) != v:
                        # 🔴 한 사람이 같은 문구(두 행)에 다른 답을 냈다 — 어느 쪽인지 고르지 않는다 (D-220)
                        clash.append(f"{i}행 {who}: {group[i][who]} ↔ {v}")
                        v = ",".join(sorted(set(group[i][who].split(",")) | set(v.split(","))))
                    group[i][who] = v
    # 🔴 **이미 들어온 라벨도 답이다** — 재검 행은 앞사람의 답이 CSV 가 아니라 `labels/` 에 있다.
    #    ⛔ CSV 만 보면 「오한빈 1 · 권소라 2」가 갈린 줄을 모르고 지나간다(테스트로 잡았다)
    #    🔄 2026-09-24 — 같은 키면 **첫** 행이다. ⛔ 종전 dict 는 마지막 행을 골라 앞 행의 답을 뒤 행에 한 번 더 붙였다
    by_key: dict[str, int] = {}
    for i, r in enumerate(rows, 1):
        by_key.setdefault(store.key(r), i)
    for fname, r in store._rows():  # noqa: SLF001
        i = by_key.get(store.key(r))
        if i is None or r.get(store.DECIDED):
            continue
        who = store.person(fname, r)
        if who in ans[i]:
            continue  # 같은 사람의 CSV 가 먼저다
        if (r.get("판단") or "").strip() == store.OUT_OF_SCOPE:
            ans[i][who] = "0"
        elif r.get("확정유형"):
            ans[i][who] = ",".join(
                sorted(str(ls.TYPES.index(t) + 1) for t in r["확정유형"] if t in ls.TYPES)
            )
    split, solo, partial = [], 0, 0
    rel_of: dict[int, tuple[str, frozenset[str], frozenset[str]]] = {}
    for i in sorted(ans):
        if "검증정답" in rows[i - 1]:
            continue
        sets = [frozenset(v.split(",")) for v in ans[i].values()]
        refs_i = set(ref.get(i, {}).values())
        if len(ans[i]) < 2:
            solo += 1
        rel_of[i] = store.agreement(sets, "0")
        rel = rel_of[i][0]
        partial += rel == store.PARTIAL
        # 🔄 D-262 — 부분합의도 판정표로 간다(갈린 유형만 정하면 된다). 참고 답과 다르면 여전히 싣는다
        if (len(ans[i]) >= 2 and rel != store.AGREED) or (
            refs_i and ans[i] and refs_i != set(ans[i].values())
        ):
            split.append(i)
    out = ls.OUT_DIR / f"판정__{sheet.stem}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(PANEL)
        for i in split:
            r = rows[i - 1]
            t = ls._text(r)  # noqa: SLF001
            show = " · ".join(f"{k}:{v}" for k, v in sorted(ans[i].items()))
            show_ref = " · ".join(f"{k}:{v}" for k, v in sorted(ref.get(i, {}).items()))
            _, agreed, contested = rel_of.get(i, ("", frozenset(), frozenset()))
            w.writerow(
                [i, t, ls.note(r), ls.choices(r), show, _names(agreed), _names(contested), show_ref,
                 "", "", "", ls.csv_fp(t)]
            )  # fmt: skip
    both = [i for i in ans if len(ans[i]) >= 2 and "검증정답" not in rows[i - 1]]
    agree = sum(1 for i in both if rel_of[i][0] == store.AGREED)
    print(
        f"답이 있는 행 {len(ans)} · 두 사람 이상 {len(both)} "
        f"(합의 {agree} · 부분합의 {partial} · 갈림 {len(both) - agree - partial}) · 한 사람만 {solo}"
    )
    print(
        "  ★ 부분합의 = 공유한 유형은 합의, 일부 유형만 갈림 (D-262) — 판정표의 「갈린 유형」만 본다"
    )
    print(f"  → {out.relative_to(ROOT)}  갈린 행 {len(split)}개 — 판정자가 `최종번호` 를 채운다")
    if dup_rows:
        print(
            f"  🟡 시트에 같은 키의 행 {dup_rows}개 — 첫 행으로 모아 셌다(판정표에는 한 번만 오른다)"
        )
    if clash:
        print(
            f"  🔴 같은 문구에 한 사람이 다른 답 {len(clash)}건 — 두 답을 합쳐 갈림으로 올렸다: {clash[:5]}"
        )
    print("  🚨 다수결로 채우지 않는다. 헷갈리면 0(범위밖)이나 빈칸도 판정이다")
    print("  일치도(κ) — uv run python scripts/label_merge.py data/derived/labels/*.jsonl")
    return 0


def decide(panel: pathlib.Path, sheet: pathlib.Path, day: str) -> int:
    """판정표 → `labels/_판정__<시트>.jsonl`. 판정 레코드는 **합의보다 앞선다**(labels.consensus)."""
    from scripts import derived_manifest as dm  # noqa: PLC0415

    why = dm.not_canonical("label_round decide")
    if why:
        print(why, file=sys.stderr)
        return 1
    rows = ls._rows(sheet)  # noqa: SLF001
    with panel.open(encoding="utf-8-sig", newline="") as f:
        got = list(csv.DictReader(f))
    out_rows = []
    decided_at: dict[str, tuple[int, str]] = {}
    for rec in got:
        i = int(rec["행"])
        base = dict(rows[i - 1])
        if not ls.row_matches(base, rec)[0]:
            raise SystemExit(f"🔴 판정표 {i}행의 `문구` 가 바뀌었다 — 되돌린 뒤 다시 한다")
        raw = (rec.get("최종번호") or "").strip()
        if not raw:
            continue  # 판정하지 않은 행 — 보류다
        # 🆕 2026-09-24 — 같은 키(같은 문구)의 판정이 둘이면 `consensus` 가 나중 것으로 **조용히** 덮는다.
        #    다르면 멈추고, 같으면 한 번만 쓴다 (D-220 · `_first_by_key`)
        k = store.key(base)
        if k in decided_at:
            j, prev = decided_at[k]
            if _norm(prev) != _norm(raw):
                raise SystemExit(
                    f"🔴 판정표 {j}행과 {i}행은 같은 문구인데 `최종번호` 가 다르다({prev} ↔ {raw}) — 하나로 맞춘다"
                )
            continue
        decided_at[k] = (i, raw)
        judge = (rec.get("판정자") or "").strip()
        if not judge:
            raise SystemExit(f"🔴 판정표 {i}행에 `판정자` 가 없다 — 누가 정했는지가 판정의 일부다")
        for k in ("재검_제외", "참고"):
            base.pop(k, None)
        if raw == ls.OUT_OF_SCOPE_NO:
            base["판단"] = store.OUT_OF_SCOPE
        else:
            base["확정유형"] = ls.parse_no(raw, i)
        base.update(
            {store.DECIDED: store.DECIDED, "붙인이": judge, "붙인날": day or ls._today()}  # noqa: SLF001
        )
        if (rec.get("메모") or "").strip():
            base["메모"] = rec["메모"].strip()
        out_rows.append(base)
    out = DERIVED / "labels" / f"_판정__{sheet.stem}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  → {out.relative_to(ROOT)}  판정 {len(out_rows)}행 (빈 칸은 보류)")
    print(
        "  다음 — golden --write 로 평가셋에 반영 → derived-manifest --write → 원장 커밋 → data-publish"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="라벨 한 판 — 짜기 · 갈린 것 모으기 · 판정 들이기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="시트를 짜고 사람마다 CSV 를 만든다 (정본)")
    p.add_argument("name", help="판 이름 — 시트가 data/derived/<이름>_labelsheet.jsonl 이 된다")
    p.add_argument("--who", required=True, help="붙일 사람들 — 쉼표로 (두 명 이상)")
    p.add_argument("--overlap", type=float, default=0.3, help="`[관행]` 전원이 겹쳐 붙일 비율")
    p.add_argument("--gold", type=int, default=20, help="`[임의]` 사람마다 섞을 검증 행 수")
    p.add_argument("--seed", type=int, default=20260920)
    c = sub.add_parser("compare", help="채운 CSV 들 → 갈린 행 판정표")
    c.add_argument("csvs", nargs="+", type=pathlib.Path)
    c.add_argument("--sheet", type=pathlib.Path, required=True)
    c.add_argument(
        "--ref",
        action="append",
        type=pathlib.Path,
        default=[],
        help="참고 답 CSV (LLM 등 · 라벨 아님)",
    )
    d = sub.add_parser("decide", help="판정표 → 판정 레코드 (정본)")
    d.add_argument("panel", type=pathlib.Path)
    d.add_argument("--sheet", type=pathlib.Path, required=True)
    d.add_argument("--day", default="")
    a = ap.parse_args()
    if a.cmd == "plan":
        return plan(
            a.name, [w.strip() for w in a.who.split(",") if w.strip()], a.overlap, a.gold, a.seed
        )
    if a.cmd == "compare":
        return compare(a.sheet, a.csvs, a.ref)
    return decide(a.panel, a.sheet, a.day)


if __name__ == "__main__":
    sys.exit(main())
