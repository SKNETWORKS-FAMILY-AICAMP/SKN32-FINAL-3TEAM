"""preprocess/mfds_guide.py — 해설서 표 → **1층 라벨 + 준법 정답 쌍** (D-151).

  uv run python -m preprocess.mfds_guide                 # 센다
  uv run python -m preprocess.mfds_guide --dump          # 🔴 마스킹 정책이 있어야 한다
  uv run python -m preprocess.mfds_guide --sheet 50      # 사람이 붙일 검증셋을 만든다

원천: `mfds_special_use_guide` (특수용도식품 표시·광고 해설서 · 2017 · 사전심의)

──────────────────────────────────────────────────────────────
★ **왜 「후보 유형」인가 — 모른다는 것을 데이터로 적는다** (D-151 · ⓓ)

  해설서의 **3분류가 우리 6종을 뭉친다.**

      해설서 ①「질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동」
              → 질병_예방치료_표방 / 의약품_오인 / 건강기능식품_오인  **셋 중 무엇인지 모른다**
      해설서 ②「거짓ㆍ과장ㆍ기만」
              → 거짓_과장 / 소비자_기만 / 후기_체험기_기만            **셋 중 무엇인지 모른다**
      해설서 ③「부당한 비교ㆍ비방」
              → 부당_비교광고 / 비방광고

  🚨 ②에 `후기_체험기_기만` 을 넣는 근거 — 해설서가 「엄마들의 경험담을 직접 확인하세요!」를
     ②로 분류한다(D-139 실측). 즉 뭉친 것이 아니라 **경계 자체가 다르다.**

  🔴 **뭉친 것을 하나로 확정하면 홀드아웃이 거짓말을 한다.** 569건을 한 라벨로 쓰면
     모델이 「의약품 오인」을 「건기식 오인」이라 답해도 맞은 것으로 채점된다 (D-40).
     그래서 `확정유형` 은 비우고 `후보유형` 에 적는다 — **없는 확신을 만들지 않는다.**

  ★ 후보 집합만으로도 지금 쓸 수 있다 — 「위반이다/아니다」 이진 판정과 생성 가드레일.
    6종 학습은 `확정유형` 이 있는 것만 쓴다(`ftc` 627문구가 그쪽이다).

🔴 **마스킹 없이는 파생을 내보내지 않는다** (D-72 fail-closed).
   이 원천에는 아직 `masking:` 선언이 없다. 세는 것은 되고, `--dump` 는 거부한다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import re
import sys

from preprocess.hwp import Table, tables_with_lead
from preprocess.text import sheet_lengths

SOURCE_ID = "mfds_special_use_guide"
RAW_DIR = pathlib.Path("data/raw") / SOURCE_ID
OUT = pathlib.Path("data/derived/mfds_guide_labels.jsonl")
SHEET = pathlib.Path("data/derived/mfds_guide_labelsheet.jsonl")

#: 제도 시점 — D-138. **레코드마다 남긴다.** 현행은 자율심의(식품표시광고법 §10)다.
REGIME = {"심의제도": "사전심의(식품위생법 제12조의3)", "연도": 2017}

#: 해설서 3분류 → 우리 유형. 🚨 **확정이 아니라 후보다** (D-151 ⓓ).
CANDIDATES: dict[str, list[str]] = {
    "질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동": [
        "질병_예방치료_표방",
        "의약품_오인",
        "건강기능식품_오인",
    ],
    "거짓ㆍ과장ㆍ기만": ["거짓_과장", "소비자_기만", "후기_체험기_기만"],
    "부당한 비교ㆍ비방": ["부당_비교광고", "비방광고"],
}

#: 표 **앞의 본문 문단**이 블록을 말한다. 표 머리글만 보면 여러 블록이 똑같이 생겼다.
BLOCKS = (
    ("삭제", r"'삭제'\s*판정"),
    ("수정", r"'수정'\s*판정"),
    ("근거자료", r"근거자료\s*제출"),
    ("삭제이미지", r"'삭제'\s*판정을 받은 이미지|판정을 받은 이미지"),
    ("키워드", r"key\s*-?\s*word"),
)


def _n(s: str) -> str:
    return " ".join(s.split())


def block_of(lead: list[str]) -> str:
    """앞 문단들에서 블록 이름. 🚨 **가장 가까운 것**이 이긴다 — 앞엣것이 남아 있다."""
    for line in reversed(lead):
        for name, pat in BLOCKS:
            if re.search(pat, line):
                return name
    return "미상"


def _label_fill(t: Table) -> dict[int, str]:
    """행 병합된 유형 셀을 행마다 편다. 🚨 유형은 **첫 행에만** 있다."""
    fill: dict[int, str] = {}
    for c in t.cells:
        if c.col == 0 and c.text.strip():
            for r in range(c.row, c.row + max(c.rowspan, 1)):
                fill[r] = _n(c.text)
    return fill


def extract(path: pathlib.Path) -> list[dict]:
    """레코드들. 🚨 마스킹은 여기서 하지 않는다 — 부르는 쪽이 정책을 지고 건다."""
    rows: list[dict] = []
    # 🚨 앞 문단 창을 **12** 로 둔다. 6 이면 표 51 이 놓친다 —
    #    그 표 앞에는 제품유형 목록(「신장질환자용식품」…)이 여섯 줄 넘게 깔려 있어
    #    블록 이름(「심의시 '삭제'판정을 받은 문구」)이 창 밖으로 밀린다.
    # ★ 창을 넓히는 것은 안전하다 — `block_of` 가 **가장 가까운 것**을 고르기 때문이다.
    #   ⛔ 대신 「머리글이 부당한 표시면 삭제로 본다」로 메우려다 말았다. 그것은 추정이고,
    #      추정한 블록은 틀려도 티가 안 난다. 근거는 문서 안에 있어야 한다.
    for idx, (t, lead) in enumerate(tables_with_lead(path, lead=12)):
        why = t.check()
        if why:
            raise ValueError(f"표 {idx} 가 원천의 선언과 어긋난다 — {why}")
        g = t.grid()
        if not g or not g[0]:
            continue
        head = " │ ".join(_n(x) for x in g[0])
        blk = block_of(lead)
        base = {"표": idx, "블록": blk, "원천": SOURCE_ID, **REGIME}

        if head.startswith("부당한 표시") and "key" not in head:
            fill = _label_fill(t)
            cur = ""
            for r in range(1, t.rows):
                cur = fill.get(r, cur)
                val = _n(g[r][1]) if len(g[r]) > 1 else ""
                if not val:
                    continue
                rows.append(
                    {
                        **base,
                        "종류": "위반문구",
                        "원천라벨": cur,
                        "문구": val,
                        "확정유형": [],  # 🔴 비운다 — 사람이 붙인다 (D-151 ⓒ)
                        "후보유형": CANDIDATES.get(cur, []),
                    }
                )
        elif head.startswith("표시(안)"):
            for r in range(1, t.rows):
                a = _n(g[r][0])
                b = _n(g[r][1]) if len(g[r]) > 1 else ""
                if a and b:
                    rows.append({**base, "종류": "수정쌍", "문구": a, "수정문구": b})
        elif "key" in head:
            for r in range(1, t.rows):
                a, b = _n(g[r][0]), _n(g[r][1]) if len(g[r]) > 1 else ""
                if b:
                    rows.append({**base, "종류": "키워드", "원천라벨": a, "문구": b})
        elif head.startswith("표시 내용"):
            for r in range(1, t.rows):
                a = _n(g[r][0])
                if a:
                    rows.append({**base, "종류": "표시내용", "문구": a})
    return rows


#: 마스킹을 거는 자리. 🚨 `원천라벨` 까지 건다 — 라벨 문자열에도 원천의 표기가 들어온다.
MASK_FIELDS = ("문구", "수정문구", "원천라벨")


def masked(rows: list[dict]) -> tuple[list[dict], collections.Counter]:
    """마스킹을 건 사본과 계측. **산출물로 나가는 모든 길이 여기를 지난다.**

    🔴 `--sheet` 도 여기를 지난다 (2026-09-08 · D-159).
       ⛔ 그 전에는 `--dump` 만 지났다. 검증셋은 사람이 읽는 파일이라 무심코 원문을 썼는데,
          `data/derived/` 에 떨어지는 순간 다른 파생물과 똑같이 D-17 대상이다.
       🚨 그런데도 **깨끗해 보였다** — 이 원천의 상호는 3,037문구 중 2건뿐이라
          150건 표본에 안 걸렸다. **오늘 깨끗한 것은 표본 운이지 규칙이 아니다.**

    🚨 앵커가 없는 원천이라 `bare` 는 빈 문자열이다 — 앵커 치환은 건너뛴다.
    ★ 해설서는 `person` 이 꺼져 있다: 원천이 **사람이 아닌 것**을 같은 기호로 가려서
      그 축이 판정 대상 문구를 먹는다 (D-157 · 실측 오탐 11 · 진짜 0).
    """
    from preprocess.mask import apply_policy  # noqa: PLC0415

    changed: collections.Counter = collections.Counter()
    out: list[dict] = []
    for r in rows:
        rec = dict(r)
        for f in MASK_FIELDS:
            if rec.get(f):
                m = apply_policy(rec[f], "", SOURCE_ID)
                if m != rec[f]:
                    changed[f] += 1
                rec[f] = m
        out.append(rec)
    return out, changed


def policy_or_stop() -> bool:
    """🔴 정책이 없으면 **아무것도 내보내지 않는다** (D-72 fail-closed). 시트도 포함이다."""
    from preprocess.mask import POLICY  # noqa: PLC0415

    if SOURCE_ID in POLICY:
        return True
    print(
        f"\n🔴 {SOURCE_ID!r} 의 마스킹 정책이 없다 — **내보내지 않는다** (D-72 fail-closed).\n"
        "   실측(2026-09-08 · 문구 3,037): 원천이 이미 가려서 준다 —\n"
        "     가림표기(oo·㈜**) 238건 · 법인격 2건(둘 다 이미 가려짐) ·\n"
        "     대표자명 0 · 주소 0 · URL 0 · 🚨 전화번호 1건(033-332-4000)\n"
        "   🚨 「가려져 있으니 불필요」로 가지 않는다 — **원천의 정책이지 우리의 보장이 아니다.**\n"
        "   고치는 법 — ① data_sources.yaml 의 masking: 기입 ② 2인 확인 ③ mask.POLICY 반영",
        file=sys.stderr,
    )
    return False


def _hwp() -> pathlib.Path:
    got = sorted(RAW_DIR.glob("*.hwp"))
    if not got:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 hwp 가 없다 —\n"
            "  먼저: uv run python -m collect.mfds_board mfds_special_use_guide --use U1"
        )
    return got[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="해설서 표 → 1층 라벨 (D-151)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    ap.add_argument("--sheet", type=int, default=0, help="유형별 N건씩 검증셋을 만든다 (ⓒ)")
    ap.add_argument("--seed", type=int, default=20260908, help="표본 추출 seed — 재현 조건 (D-54)")
    ap.add_argument(
        "--min-len",
        type=int,
        default=0,
        dest="min_len",
        help="문구 길이 하한 — 낱말을 빼고 문장만 뽑는다 (0 = 안 건다)",
    )
    a = ap.parse_args()

    rows = extract(_hwp())
    kinds = {}
    for r in rows:
        kinds.setdefault(r["종류"], []).append(r)
    print(f"레코드 {len(rows):,}")
    for k, v in sorted(kinds.items(), key=lambda x: -len(x[1])):
        print(f"  {k:8} {len(v):>6,}")
    viol = kinds.get("위반문구", [])
    print("\n  위반문구 — 원천라벨별 · 🚨 확정유형은 비어 있다 (D-151 ⓓ)")
    by: dict[str, int] = {}
    for r in viol:
        by[r["원천라벨"]] = by.get(r["원천라벨"], 0) + 1
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        cand = CANDIDATES.get(k)
        mark = "★" if v >= 30 else "🚨"
        print(f"    {mark} {v:>5}  {k[:44]:46} 후보 {cand if cand else '🔴 매핑 없음'}")
    unmapped = [k for k in by if k not in CANDIDATES]
    if unmapped:
        print(
            f"    🔴 매핑이 없는 원천라벨 {len(unmapped)}종 — CANDIDATES 를 채워야 한다: {unmapped}"
        )

    if a.sheet:
        if not policy_or_stop():
            return 1
        # 🔴 검증셋도 마스킹을 지난다 (D-159). 표본 **선택**은 마스킹 전과 같다 —
        #    마스킹은 순서도 개수도 안 바꾸므로 seed 가 같으면 같은 행이 뽑힌다 (D-54).
        safe, sheet_changed = masked(viol)
        rnd = random.Random(a.seed)
        pick: list[dict] = []
        for k in sorted(by):
            pool = [r for r in safe if r["원천라벨"] == k]
            if a.min_len:
                pool = [r for r in pool if len(_n(r.get("문구", ""))) >= a.min_len]
            pick += rnd.sample(pool, min(a.sheet, len(pool)))
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        with SHEET.open("w", encoding="utf-8") as f:
            for r in pick:
                f.write(json.dumps({**r, "붙인이": "", "붙인날": ""}, ensure_ascii=False) + "\n")
        print(f"\n  ⓒ 검증셋 {len(pick):,}건 → {SHEET}  (seed={a.seed} · 길이하한 {a.min_len})")
        sheet_lengths(pick, "문구", a.min_len)
        print(
            f"     🔴 마스킹을 지났다 — 위반문구 전체에서 바뀐 필드 {dict(sheet_changed) or '없음'}"
        )
        print("     🚨 표본에 안 걸렸다고 안전한 것이 아니다 — **표본 운이지 규칙이 아니다.**")
        print(
            "     🚨 `확정유형` 은 **사람이** 채운다 — 추출기가 채우면 홀드아웃이 자기 채점이 된다."
        )

    if a.dump:
        if not policy_or_stop():
            return 1
        out, changed = masked(rows)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as fh:
            for rec in out:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'}")
        print("     🚨 0 이라고 안 건 것이 아니다 — 정책이 꺼져 있으면 애초에 안 돈다.")
        print(f"  → {OUT}  ({len(out):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
