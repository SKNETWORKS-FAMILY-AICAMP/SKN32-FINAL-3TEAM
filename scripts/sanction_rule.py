#!/usr/bin/env python3
"""sanction_rule.py — **위험도 하한 원천(`scripts/sanction_review.yaml`)을 원문과 대조하고 검토표를 낸다** (🆕 2026-10-01 · W5 · D-305 · D-308).

  uv run python -m scripts.sanction_rule check            # 원문 대조 · 검토표(build/labels/sanction_rule__검토표.csv)

★ 왜 원문 대조인가 — 별표는 병합 셀 괘선 표다. 파서(`collect/law_annex.py`)는 하위 목을 한 행에 뭉쳐(4)호 가)~거)) **목별 1차 처분을
  잃는다**(2026-10-01 실측 · 파싱 행의 처분이 첫 하위 목 것). 그래서 행은 사람이 읽을 원천(yaml)에 두고, 이 검사가 **원문 괘선 표의
  첫 칸(위반행위)과 1차 칸**에서 인용을 찾아 맞는지 본다. 못 찾으면 멈춘다 — 서명은 원문과 같은 글자 위에서만 한다 (D-149 · D-220).
★ 위험도는 처분 **종류**로만 정한다 — `KIND_RISK` 한 곳 (D-227 · D-99). yaml 에 위험도를 적지 않는다.
🚨 서명은 사람만 — 이 스크립트는 **읽기만** 한다. 🔄 2026-10-01 (D-309) **판 단위 서명** — yaml 의 `signoff` 하나에 판 sha(`plan_sha`)와
   두 이름. sha 가 지금 판과 다르면 **서명 무효**(check 가 멈춘다 · 적재기는 싣지 않는다) · 두 이름이 같으면 멈춘다(D-66 · `ck_sanction_four_eyes`).
   적재기는 유효한 판 서명을 행마다 `verified_by` · `reviewed_by` 로 옮긴다(`signature`) — 스키마 · 뷰는 그대로다.
⛔ 적재(`load_db.load_sanction_rule`) · `assess_risk` 배선은 서명 뒤 작업이다 — 여기서 하지 않는다 (D-305).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.contracts import FactKind, Risk, Violation  # noqa: E402

RULES = ROOT / "scripts" / "sanction_review.yaml"
SHEET = ROOT / "build" / "labels" / "sanction_rule__검토표.csv"

#: 처분 종류 → 위험도 (D-227 「종류로 가른다」 · 출처 `[문헌]` 각 법의 처분 사다리 — 초안 09-16 §1 · 09-12 §3-2).
#: 🚨 정지에 **갈음하는 과징금**도 R2 다(식품 제19조 · 화장품 제28조) — 금액은 쓰지 않는다(D-182).
KIND_RISK: dict[str, Risk] = {
    "시정명령": Risk.R1,
    "시정조치": Risk.R1,  # 표시광고법 제7조 — 정지 · 취소 사다리가 없다
    "영업정지": Risk.R2,
    "품목제조정지": Risk.R2,
    "품목류제조정지": Risk.R2,
    "광고업무정지": Risk.R2,
    "판매업무정지": Risk.R2,
    "영업허가등록취소": Risk.R3,
    "영업소폐쇄": Risk.R3,
}

#: D-255 — 범위 밖 유형은 하한 행을 두지 않는다(넣으면 「하한이 있다」가 확정처럼 읽힌다)
OUT_OF_SCOPE = {Violation.추천_보증_뒷광고}

#: 괘선 표 첫 칸의 목 머리 — 하위 목(1) · 가) · (1))과 최상위 목(가.)
_MARK = re.compile(r"^\s*(\d+\)|[가-힣]\)|\(\d+\)|[가-힣]\.)")
_TOP = re.compile(r"^\s*[가-힣]\.")
_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    """대조용 — 공백을 다 지운다(괘선 표는 칸 폭에서 줄이 끊긴다)."""
    return _WS.sub("", s or "")


def bands(content: str) -> list[dict[str, Any]]:
    """괘선 표 → 행(목) 묶음. 첫 칸이 목 머리로 시작하면 새 행이다. `c1` = 첫 칸 이어붙임 · `first` = 1차 칸(넷째 칸).

    🚨 1차 칸 위치는 두 별표(식품 7 · 화장품 7)에서 같다 — 머리줄 「1차 위반」이 넷째 칸이다(2026-10-01 실측).
    """
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for no, line in enumerate(content.split("\n")):
        if "│" not in line:
            continue
        cells = line.split("│")
        c1 = cells[1] if len(cells) > 1 else ""
        if c1.strip() and _MARK.match(c1):
            if cur:
                out.append(cur)
            cur = {"line": no, "c1": "", "first": ""}
        if cur is None:
            continue
        cur["c1"] += c1.strip()
        if len(cells) > 3:
            cur["first"] += cells[3].strip()
    if cur:
        out.append(cur)
    return out


def find_band(
    bs: list[dict[str, Any]], block: str, nth: int, mok: str, quote: str
) -> dict[str, Any] | str:
    """블록(최상위 목 · `nth` 번째) 안에서 목 머리 `mok` 로 시작하고 `quote` 를 담은 행. 못 찾으면 이유(문자열)."""
    heads = [i for i, b in enumerate(bs) if norm(b["c1"]).startswith(norm(block))]
    if len(heads) < nth:
        return f"블록 {block!r} 의 {nth} 번째를 못 찾았다(찾은 수 {len(heads)})"
    start = heads[nth - 1]
    end = next((j for j in range(start + 1, len(bs)) if _TOP.match(bs[j]["c1"])), len(bs))
    got = [
        b
        for b in bs[start + 1 : end]
        if norm(b["c1"]).startswith(norm(mok)) and norm(quote) in norm(b["c1"])
    ]
    if len(got) != 1:
        return f"블록 안에서 목 {mok!r} · 인용 {quote[:20]!r} 행이 {len(got)} 개다(하나여야 한다)"
    return got[0]


def article_text(rows: list[dict], law: str, article: str, hang: str) -> str:
    """조문 코퍼스에서 (법령 · 조 · 항)의 본문을 이어 붙인다. 가지 조(제7조의2 등)는 뺀다."""
    return "".join(
        r.get("본문", "")
        for r in rows
        if r.get("법령") == law
        and str(r.get("조")) == article
        and not r.get("가지")
        and r.get("항", "") == hang
    )


_GANADA = "가나다라마바사아자차카타파하"


def mok_segment(content: str, mok: str, section: str = "2.화장품표시ㆍ광고시준수사항") -> str:
    """별표5 제2호의 한 목(`가` · `나` …) 본문(공백 제거). 다음 목 머리(`나.` …)까지 — 목 안 문장의 「다.」로 끊지 않는다."""
    t = norm(content)
    i = t.find(norm(section))
    if i < 0:
        return ""
    t = t[i:]
    a = t.find(f"{mok}.")
    if a < 0:
        return ""
    nxt = _GANADA[_GANADA.index(mok) + 1] if mok in _GANADA[:-1] else None
    b = t.find(f"{nxt}.", a + 2) if nxt else -1
    return t[a : b if b > 0 else len(t)]


def load_rules(path: pathlib.Path = RULES) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def lint(spec: dict[str, Any]) -> list[str]:
    """원문 없이 보는 것 — 유형 · 종류 · 사실 칸 · id 중복 · 범위 밖 · 서명 2인. **게이트가 이것을 돌린다.**"""
    bad: list[str] = []
    seen: set[str] = set()
    for r in spec.get("rows") or []:
        rid = r.get("id", "?")
        if rid in seen:
            bad.append(f"{rid} id 가 두 번")
        seen.add(rid)
        if r.get("src") not in (spec.get("sources") or {}):
            bad.append(f"{rid} 모르는 원천 {r.get('src')!r}")
        try:
            vt = Violation(r.get("type"))
        except ValueError:
            bad.append(f"{rid} 모르는 유형 {r.get('type')!r}")
            continue
        if vt in OUT_OF_SCOPE:
            bad.append(f"{rid} 범위 밖 유형 {vt.value} (D-255)")
        if r.get("kind") not in KIND_RISK:
            bad.append(f"{rid} 모르는 처분 종류 {r.get('kind')!r} — KIND_RISK 에 없다")
        if r.get("fact") is not None:
            try:
                FactKind(r["fact"])
            except ValueError:
                bad.append(f"{rid} 모르는 사실 칸 {r['fact']!r}")
        for f in ("quote", "first"):
            if not r.get(f):
                bad.append(f"{rid} {f} 가 비었다 — 원문 대조를 못 한다")
        if "verified_by" in r or "reviewed_by" in r:
            bad.append(f"{rid} 행에 서명 칸이 있다 — 서명 자리는 `signoff` 하나다 (D-309)")
    for p in spec.get("penal") or []:
        for t in p.get("types") or []:
            try:
                Violation(t)
            except ValueError:
                bad.append(f"{p.get('id')} 모르는 유형 {t!r}")
    so = spec.get("signoff") or {}
    v, rv = (str(so.get(k) or "").strip() for k in ("verified_by", "reviewed_by"))
    if v and rv and v == rv:
        bad.append("signoff 검증자와 확인자가 같다 (D-66 · ck_sanction_four_eyes)")
    if (v or rv) and so.get("sha") and so["sha"] != plan_sha(spec):
        bad.append(
            f"signoff 서명이 무효다 — 서명한 판 {so['sha']} ≠ 지금 판 {plan_sha(spec)} (판이 바뀌었다 · 사람이 지우고 다시 서명 · D-309)"
        )
    if (v or rv) and not so.get("sha"):
        bad.append("signoff 에 이름은 있는데 판 sha 가 없다 — 무엇에 서명했는지 모른다 (D-309)")
    return bad


def plan_sha(spec: dict[str, Any]) -> str:
    """판 sha — 원천 · 행 · 형벌의 내용(서명 칸 제외). 🔴 한 글자라도 바뀌면 달라진다 — 서명은 이 값에 묶인다 (D-309)."""
    body = {k: spec.get(k) for k in ("sources", "rows", "penal")}
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def signature(spec: dict[str, Any]) -> tuple[str, str] | None:
    """유효한 판 서명 `(verified_by, reviewed_by)` — 둘 다 있고 · 서로 다르고 · sha 가 지금 판과 같을 때만. 그 밖에는 None(서명 없음과 같다)."""
    so = spec.get("signoff") or {}
    v, rv = (str(so.get(k) or "").strip() for k in ("verified_by", "reviewed_by"))
    if v and rv and v != rv and so.get("sha") == plan_sha(spec):
        return v, rv
    return None


def verify(spec: dict[str, Any], root: pathlib.Path = ROOT) -> list[str]:
    """원문 대조 — 행마다 인용 · 1차 처분(· 별표5 목 인용)을 원문에서 찾는다. 🔴 원문 파일이 없으면 멈춘다(대조 없이 통과 금지 · D-220)."""
    src = spec["sources"]
    bad: list[str] = []
    cache: dict[str, Any] = {}

    def content(key: str) -> Any:
        if key not in cache:
            p = root / src[key]["path"]
            if not p.exists():
                raise SystemExit(
                    f"🔴 원문이 이 기기에 없다 — {p} (정본 · 원문이 있는 기기에서 돈다 · D-220)"
                )
            if p.suffix == ".jsonl":
                cache[key] = [
                    json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()
                ]
            else:
                cache[key] = json.loads(p.read_text(encoding="utf-8"))["content"]
        return cache[key]

    bands_of: dict[str, list[dict[str, Any]]] = {}
    for r in spec.get("rows") or []:
        rid, key = r["id"], r["src"]
        if key == "fair":
            text = norm(
                article_text(content(key), src[key]["law"], r["article"], r.get("hang", ""))
            )
            for f in ("quote", "first"):
                if norm(r[f]) not in text:
                    bad.append(f"{rid} 조문에 {f} {r[f][:24]!r} 가 없다")
            continue
        if key not in bands_of:
            bands_of[key] = bands(content(key))
        b = find_band(bands_of[key], r["block"], int(r.get("nth", 1)), r["mok"], r["quote"])
        if isinstance(b, str):
            bad.append(f"{rid} {b}")
            continue
        if norm(r["first"]) not in norm(b["first"]):
            bad.append(f"{rid} 1차 칸에 {r['first']!r} 가 없다 — 원문 {b['first'][:40]!r}")
        if norm(r["kind"]) not in norm(r["first"]).replace("ㆍ", "").replace("·", ""):
            bad.append(f"{rid} 처분 종류 {r['kind']!r} 가 1차 인용 {r['first']!r} 에 없다")
        if r.get("rule"):
            seg = mok_segment(content("cosm_rule"), r["rule"]["mok"])
            if norm(r["rule"]["quote"]) not in seg:
                bad.append(
                    f"{rid} 별표5 {r['rule']['mok']}목에 {r['rule']['quote'][:20]!r} 가 없다"
                )
    for p in spec.get("penal") or []:
        text = norm(article_text(content("fair"), p["law"], p["article"], p.get("hang", "")))
        if p.get("also"):
            text += norm(
                "".join(
                    x.get("본문", "")
                    for x in content("fair")
                    if x.get("법령") == p["law"]
                    and str(x.get("조")) == p["article"]
                    and not x.get("가지")
                )
            )
        for f in ("quote", "also"):
            if p.get(f) and norm(p[f]) not in text:
                bad.append(f"{p['id']} 조문에 {f} {p[f][:24]!r} 가 없다")
    return bad


SHEET_COLS = (
    "id", "법", "별표", "업종", "목", "위반(원문 인용)", "1차 처분(원문)", "처분 종류", "위험도",
    "유형", "사실 확인", "폐기", "비고", "verified_by", "reviewed_by", "상태",
)  # fmt: skip


def sheet_rows(spec: dict[str, Any]) -> list[list[str]]:
    src = spec["sources"]
    sig = signature(spec)
    out = []
    for r in spec.get("rows") or []:
        s = src[r["src"]]
        signed = sig is not None
        out.append(
            [
                r["id"],
                s["law_id"],
                s.get("annex_no") or f"제{r.get('article')}조",
                r.get("industry", ""),
                r.get("mok", "") + (f" · 별표5 2.{r['rule']['mok']}" if r.get("rule") else ""),
                r["quote"],
                r["first"],
                r["kind"],
                KIND_RISK[r["kind"]].value,
                r["type"],
                r.get("fact") or "",
                "폐기" if r.get("disposal") else "",
                r.get("note", ""),
                sig[0] if sig else "",
                sig[1] if sig else "",
                "서명됨(하한으로 쓴다)" if signed else "서명 전(안 쓴다)",
            ]
        )
    return out


def write_sheet(spec: dict[str, Any], out: pathlib.Path = SHEET) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(SHEET_COLS)
        rows = sheet_rows(spec)
        w.writerows(rows)
    return len(rows)


def floor_by_type(spec: dict[str, Any], signed_only: bool = True) -> dict[str, dict[str, str]]:
    """유형 × 법 → 하한(같은 법 안에서 max · D-227 「업종은 언제나 max」). 검토 요약용 — 판정 경로는 DB 뷰가 한다."""
    order = list(Risk)
    out: dict[str, dict[str, str]] = {}
    if signed_only and signature(spec) is None:
        return out
    for r in spec.get("rows") or []:
        law = spec["sources"][r["src"]]["law_id"]
        cur = out.setdefault(r["type"], {}).get(law)
        risk = KIND_RISK[r["kind"]]
        if cur is None or order.index(risk) > order.index(Risk(cur)):
            out[r["type"]][law] = risk.value
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="원문 대조 · 검토표")
    p.add_argument(
        "--root", type=pathlib.Path, default=ROOT, help="원문을 찾을 저장소 뿌리(기본 이 저장소)"
    )
    a = ap.parse_args(argv)
    spec = load_rules()
    bad = lint(spec) + verify(spec, a.root)
    if bad:
        print("🔴 원천이 원문과 맞지 않는다 — 서명하지 않는다\n  " + "\n  ".join(bad))
        return 1
    n = write_sheet(spec)
    sig = signature(spec)
    print(
        f"✅ 원문 대조 통과 — 행 {n} · 형벌 조항 {len(spec.get('penal') or [])} · 판 sha {plan_sha(spec)} · "
        + (
            f"서명됨({sig[0]} · {sig[1]})"
            if sig
            else "서명 전 — `signoff` 에 이 판 sha 와 두 이름을 적는다(D-309)"
        )
    )
    print(f"   검토표 → {SHEET.relative_to(ROOT)}")
    print("   유형 × 법 하한(서명 무시 · 미리보기):")
    for t, by in sorted(floor_by_type(spec, signed_only=False).items()):
        print(f"     {t:<14} " + " · ".join(f"{k} {v}" for k, v in sorted(by.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
