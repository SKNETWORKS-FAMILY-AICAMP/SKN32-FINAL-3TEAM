"""probe_guard_b1022.py — 주장 가드 판 비교 (클론 B 재작성 · 2026-10-22). 🚨 git 무시 · 탐색 · 게이트 아님 · 판정 아님.

클론 A 의 `probe_guard_1022.py` 를 받지 못해 다시 만들었다(같은 바이트가 아니다). 같은 측정인지는 V0 을 클론 A 표(인계 10-22 클론A §0-5)와
대조해 확인한다.

★ 분해 — `graph.encoder_cap` 은 가드가 거짓이면 빠질 뿐이고 근거(`_encoder_basis`)는 가드와 무관하다. 그래서
     「판 X 에서 문장에 인코더 하한이 선다」 = guard_X(문장) ∧ 「가드를 늘 참으로 둔 판(V7)에서 그 문장에 하한이 섰다」.
   V7 을 한 번 돌리면 어떤 가드 후보든 계산으로 센다(`calc`). V0 실측과 V0 계산이 행마다 같은지로 분해를 검증한다.
   🚨 확정은 근사다 — 인코더 판정 확정(`encoder_judged`) 문장만 가드로 거른다(τ · 칸 · 품목 규칙은 V7 실행의 결과를 그대로 쓴다).

쓰는 법 (저장소 뿌리 · PowerShell):
  uv run python build/probe_guard_b1022.py run --guard V0 --set dev --out build/eval/pg_B1022_dev_V0.json
  uv run python build/probe_guard_b1022.py run --guard V7 --set dev --out build/eval/pg_B1022_dev_V7.json
  uv run python build/probe_guard_b1022.py calc build/eval/pg_B1022_dev_V0.json build/eval/pg_B1022_dev_V7.json

묶음 (--set):
  dev          확장 dev · 조건부(`eval_graph --dev --guide-dev --conditional` 과 같은 행 · 같은 제품 정보)
  gpt213       권소라 검수판 GPT 353(`c5c78314d1732a25`) 의 판독(사람)=적법 ∧ 애매 없음 213 · 품목 입력
               (분기 「건기식 꼴 · 인증 아니오(일반식품)」 은 식품 전제 — 클론 A 인계 §4 와 같게)
  m171         정상 카피 900(`f3bfec9079e05c36`) 의 측정용 171 — 분할 규칙으로 다시 뽑음(품목마다 제품종류 가나다순 →
               `random.Random(42).sample(·, 5)`) · 🚨 id 목록 지문 `f633835161e5f3ef` 미재현 — 같은 집합인지 미확인
  caution      `hf_display_claims.jsonl` 주의사항 칸 → `sentsplit.split` → 앞 번호 · 기호 뗌 → 4 자 이상 · 중복 제거 ·
               건기식_비인정 전제 · 🚨 원장 10-14(A) ⑥ 의 444 와 행 수가 다를 수 있다(절차 세부 미확인 · 행 수를 찍는다)
  n900x        정상 카피 900 의 떼어 둔 15 제품(인코더 학습 밖) 중 측정용 171 밖의 행(적법(사실 전제) · 조건부 · 애매 적법)
  gptfact      GPT 353 의 판독(사람)=적법(사실 전제) ∧ 애매 없음
  fnclty       `hf_display_claims.jsonl` 인정 기능성 내용(`FNCLTY_CN`) → 문장 · 건기식_인정 전제 — 명사구 효능 주장의 적법 쪽 시험
  *_unk        같은 묶음 · 품목 모름(빈 제품 정보)

🆕 (라) 실측 — `run --guard R` (하한 자리만 넓은 가드) → `check V0.json V7.json R.json` (실측 ↔ 계산 · 확정이 V0 보다 늘었나)
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import claimscope as cs  # noqa: E402
from app import premise as pm  # noqa: E402
from app.contracts import Category, Premise, ProductContext, Verdict, encoder_judged  # noqa: E402
from scripts import eval_graph as eg  # noqa: E402

GPT = (Path("build/legit/ksr_gpt353_20261013.csv"), "c5c78314d1732a25")
N900 = (Path("build/legit/ksr_review900_20261011.csv"), "f3bfec9079e05c36")
HF = Path("data/derived/hf_display_claims.jsonl")
LEAD = re.compile(r"^\s*(\(?\d+\)?[.)]?|[①-⑳]|[-·•*※○●▶►]|[가-하][.)])\s*")

_V0 = cs.claim_guard


def base(t: str) -> bool:
    """가드의 앞 두 조건 — 빈 글자 아님 ∧ 주의 · 상담 아님 ∧ 거부 가드에 안 걸림 (V7 = 이것만)."""
    t = (t or "").strip()
    return bool(t) and not cs.is_caution(t) and not cs.is_veto(t)


# ── 가드 후보 ── 🚨 정규식 · 낱말 목록은 [임의] 다(판정 경로에 들어가면 보고에 올린다)
#: 관형형 끝 — 인계 10-22 클론A §1 #1 의 V1 정규식
V1 = re.compile(r"(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$")
#: 효능 명사 끝 — 학습 쪽 전수(10-22 클론 B · 학습 골든 위반 행 중 가드가 막은 문장의 끝 낱말 상위)에서 뽑은 12 낱말
EFD = re.compile(r"(도움|예방|완화|강화|억제|증가|증진|감소|향상|보습|조절|건강)\s*[.!?~]*\s*$")
#: 효능 명사 끝 — 위에 사람이 넓힌 낱말을 더함(자료 밖)
EFX = re.compile(
    r"(도움|예방|완화|개선|강화|억제|증가|증진|감소|향상|보습|조절|건강|해소|회복|치료|완치|효과|효능|촉진|방지|유지|관리|케어|진정"
    r"|미백|탄력|재생|활력|면역|해독|디톡스|다이어트|감량|숙면|쾌변|쑥쑥|팡팡|튼튼|든든|매끈|촉촉|쫀쫀)\s*[.!?~]*\s*$"
)


#: 주장 낱말 — 학습 쪽 전수(10-22 클론 B · 막힌 위반에 나오고 막힌 적법에 0 번인 낱말에서 사건 고유어를 뺀 일반 낱말) · [임의] 섞인 [측정]
#:    ⚠️ 알려진 새는 자리 — 「가득」(맛 묘사 「입안 가득」) · 「전문」(「유통전문판매원」) · 검증 묶음을 보고 고치지 않았다
CUE_WORDS = (
    "예방 강화 증가 향상 감소 최소화 도움 촉진 차단 항산화 항균 회복 해소 치료 면역력 혈액순환 배출 "
    "무첨가 무첨 NO No free FREE 프리 무농약 유기농 친환경 천연 GMO 방부제 항생제 트랜스지방 칼로리 "
    "전문 대표 프리미엄 연구소 연구 개발 획득 돌파 전문의 피부과 FDA 시험 안전한 안전성 안심 풍부한 듬뿍 가득 ZERO zero"
).split()
CUE = re.compile("|".join(sorted(map(re.escape, CUE_WORDS), key=len, reverse=True)))
NUMX = re.compile(r"\d+(\.\d+)?\s*(배|회|위)")


def wide(t: str) -> bool:
    """(라) 의 하한 가드 — 지금 가드 ∨ (주의 · 거부 밖 ∧ (주장 낱말 ∨ N배 · N회 · N위 ∨ 관형형 끝))."""
    return _V0(t) or (base(t) and bool(CUE.search(t) or NUMX.search(t) or V1.search(t.strip())))


_VN: set[str] | None = None


def _vn_words() -> set[str]:
    """(ㄴ) 동작 · 상태 명사 — 「X하 · X되 · X시키 …」가 코퍼스(법령 청크 + 학습 쪽 골든 · 900 학습 쪽)에 2 회 이상 낱말 머리로 나오는 X.
    🚨 dev · 봉인 · 데이터 밖 묶음은 쓰지 않는다. [측정] (코퍼스) · 「2 회」 는 [임의]."""
    global _VN
    if _VN is not None:
        return _VN
    from preprocess import devsplit  # noqa: PLC0415
    from preprocess import encoder_resplit as rsp  # noqa: PLC0415

    g = [json.loads(x) for x in Path("data/derived/golden/golden.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    dev = set(devsplit.dev_ids(g))
    plan = rsp.plan(g)
    corpus = [r["text"] for r in g if r["id"] not in dev and (r.get("split") == "train" or plan.get(r["id"]) == rsp.TRAIN)]
    corpus += [json.loads(x)["text"] for x in Path("data/derived/chunks.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rs = _csv(N900)
    lawful = _lawful(rs)
    hold = set()
    for c in ("화장품", "식품", "건기식"):
        kinds = sorted({r["제품종류"] for r in lawful if r["품목"] == c})
        hold |= {(c, k) for k in random.Random(42).sample(kinds, 5)}
    corpus += [r["text"] for r in rs if (r["품목"], r["제품종류"]) not in hold]
    suf = r"(하|되|시키|해|돼|했|됐|한|된|할|될|함|됨|하여|되어)"
    cnt: collections.Counter[str] = collections.Counter()
    for t in corpus:
        for m in re.finditer(r"(?<![가-힣])([가-힣]{2,4})" + suf, t):
            cnt[m.group(1)] += 1
    _VN = {w for w, c in cnt.items() if c >= 2}
    return _VN


def vn_end(t: str) -> bool:
    t = re.sub(r"[\s.!?~·,'\"”’)\]]+$", "", (t or "").strip())
    m = re.search(r"([가-힣]+)$", t)
    if not m:
        return False
    w = m.group(1)
    vn = _vn_words()
    return any(w[-n:] in vn for n in range(min(4, len(w)), 1, -1))


#: R2 의 하한 가드 후보 — 지금 가드 ∨ (주의 · 거부 밖 ∧ 그 판의 조건)
WIDE = {
    "V1": lambda t: _V0(t) or (base(t) and bool(V1.search(t.strip()))),
    "L": lambda t: wide(t),
    "VN": lambda t: _V0(t) or (base(t) and (vn_end(t) or bool(V1.search(t.strip())))),
}


def _end(rx: re.Pattern[str]):
    return lambda s: _V0(s["text"]) or (base(s["text"]) and bool(rx.search(s["text"].strip())))


def _v5s(s: dict) -> bool:
    """🚨 V5s 근사 — 보류 문장의 사전 후보 유형(자격 없는 적중) 중 하나 = 인코더 1 위 유형(직접 후보). `demoted` · 「단일」 신뢰도 ·
    확정 막기 가드 제외는 결과에 실리지 않아 가르지 못한다(클론 A 의 V5s 보다 넓을 수 있다)."""
    top = s.get("enc_top")
    return bool(top) and top in set(s.get("hold_dict") or ())


GUARDS = {
    "V0": lambda s: _V0(s["text"]),
    "V7": lambda s: base(s["text"]),
    "V1": _end(V1),
    "Ed": _end(EFD),
    "E": _end(EFX),
    "Ed+V1": lambda s: _end(EFD)(s) or _end(V1)(s),
    "V8≈(V1+V5s근사)": lambda s: _end(V1)(s) or (base(s["text"]) and _v5s(s)),
    "L정리+V1": lambda s: wide(s["text"]),
}
#: 하한 가드 · 확정 가드가 다른 판 — (라) = 하한은 넓게 · 확정은 지금 가드
SPLIT = {"(라) 하한 L정리+V1 · 확정 V0": (lambda s: wide(s["text"]), GUARDS["V0"])}


# ── 묶음 ──
def _csv(src: tuple[Path, str]) -> list[dict]:
    p, want = src
    b = p.read_bytes()
    got = hashlib.sha256(b).hexdigest()[:16]
    if got != want:
        raise SystemExit(f"🔴 {p} 지문이 다르다 — {got} ≠ {want}")
    return list(csv.DictReader(b.decode("utf-8-sig").splitlines()))


def _lawful(rs: list[dict]) -> list[dict]:
    return [r for r in rs if r["판독(사람)"].strip() == "적법" and not (r["애매표시"] or "").strip()]


def load(name: str) -> tuple[list[dict], dict]:
    """→ (행 [{id, text, gold, labels, product}], 표지)."""
    unk = name.endswith("_unk")
    key = name.removesuffix("_unk")
    if key == "dev":
        if unk:
            raise SystemExit("🔴 dev 는 조건부만 — 클론 A 표가 조건부다")
        every = eg.load_rows(dev=True, guide_dev=True)
        mark = eg.check_dev(every, None)
        out = []
        for r in eg.conditional_rows(every):
            c = r.get("조건") or ""
            gold = "위반" if c in ("A", "B", "C") else "적법" if c in ("D", "L") else "모호" if c == "M" else "조건없음"
            out.append(
                {"id": r["id"], "text": r["text"], "gold": gold, "labels": list(r.get("labels") or []),
                 "product": eg.product_of(r, True)}
            )
        return out, {"dev": mark}
    if key == "gpt213":
        rs = _lawful(_csv(GPT))
        if len(rs) != 213:
            raise SystemExit(f"🔴 GPT 적법 · 애매 없음이 {len(rs)} 행 — 213 이어야 한다")

        def prod(r: dict) -> ProductContext:
            if unk:
                return ProductContext()
            if "(일반식품)" in r["분기"]:
                return pm.product_of(Premise.식품)
            return ProductContext(category=Category(r["품목"]))

        return [{"id": r["id"], "text": r["text"], "gold": "적법", "labels": [], "product": prod(r)} for r in rs], {}
    if key == "m171":
        lawful = _lawful(_csv(N900))
        hold: set[tuple[str, str]] = set()
        for c in ("화장품", "식품", "건기식"):
            kinds = sorted({r["제품종류"] for r in lawful if r["품목"] == c})
            hold |= {(c, k) for k in random.Random(42).sample(kinds, 5)}
        rs = [r for r in lawful if (r["품목"], r["제품종류"]) in hold]
        n = collections.Counter(r["품목"] for r in rs)
        if len(rs) != 171 or n != {"화장품": 59, "식품": 58, "건기식": 54}:
            raise SystemExit(f"🔴 측정용이 171(59 · 58 · 54) 이 아니다 — {dict(n)}")
        ids = "\n".join(sorted(r["id"] for r in rs)) + "\n"
        return (
            [{"id": r["id"], "text": r["text"], "gold": "적법", "labels": [],
              "product": ProductContext() if unk else ProductContext(category=Category(r["품목"]))} for r in rs],
            {"m171_ids_sha": hashlib.sha256(ids.encode()).hexdigest()[:16], "m171_note": "지문 f633835161e5f3ef 미재현 · 같은 집합 미확인"},
        )
    if key in ("n900x", "gptfact"):
        if key == "gptfact":
            rs = [r for r in _csv(GPT) if r["판독(사람)"].strip() == "적법(사실 전제)" and not (r["애매표시"] or "").strip()]

            def prod(r: dict) -> ProductContext:
                if unk:
                    return ProductContext()
                if "(일반식품)" in r["분기"]:
                    return pm.product_of(Premise.식품)
                return ProductContext(category=Category(r["품목"]))
        else:
            allr = _csv(N900)
            lawful = _lawful(allr)
            hold = set()
            for c in ("화장품", "식품", "건기식"):
                kinds = sorted({r["제품종류"] for r in lawful if r["품목"] == c})
                hold |= {(c, k) for k in random.Random(42).sample(kinds, 5)}
            m171 = {r["id"] for r in lawful if (r["품목"], r["제품종류"]) in hold}
            #: 떼어 둔 15 제품(인코더 학습 밖) 중 측정용 171 밖의 행 — 적법(사실 전제) · 조건부 · 애매 표시 적법
            rs = [r for r in allr if (r["품목"], r["제품종류"]) in hold and r["id"] not in m171]

            def prod(r: dict) -> ProductContext:
                return ProductContext() if unk else ProductContext(category=Category(r["품목"]))
        return [{"id": r["id"], "text": r["text"], "gold": r["판독(사람)"].strip() + ("·애매" if (r["애매표시"] or "").strip() else ""),
                 "labels": [], "product": prod(r)} for r in rs], {}
    if key == "fnclty":
        from app import sentsplit  # noqa: PLC0415

        seen: set[str] = set()
        out = []
        for x in HF.read_text(encoding="utf-8").splitlines():
            if not x.strip():
                continue
            v = json.loads(x).get("FNCLTY_CN")
            if not v:
                continue
            for t in sentsplit.split(v):
                t = LEAD.sub("", t).strip()
                if len(t) >= 4 and t not in seen:
                    seen.add(t)
                    out.append(t)
        #: 인정받은 기능성 내용 — 건기식_인정 전제에서 적법인 효능 주장(명사구 포함). 🚨 주석 · 단서 줄(「따라서 반드시 …」)도 섞인다
        prod = ProductContext() if unk else pm.product_of(Premise.건기식_인정)
        rows = [{"id": f"fnclty:{i}", "text": t, "gold": "적법(인정)", "labels": [], "product": prod} for i, t in enumerate(out)]
        return rows, {"hf_sha": hashlib.sha256(HF.read_bytes()).hexdigest()[:12], "fnclty_rows": len(rows)}
    if key == "caution":
        from app import sentsplit  # noqa: PLC0415

        seen: set[str] = set()
        out = []
        for x in HF.read_text(encoding="utf-8").splitlines():
            if not x.strip():
                continue
            v = json.loads(x).get("IFTKN_ATNT_MATR_CN")
            if not v:
                continue
            for t in sentsplit.split(v):
                t = LEAD.sub("", t).strip()
                if len(t) >= 4 and t not in seen:
                    seen.add(t)
                    out.append(t)
        prod = ProductContext() if unk else pm.product_of(Premise.건기식_비인정)
        rows = [{"id": f"caution:{i}", "text": t, "gold": "적법", "labels": [], "product": prod} for i, t in enumerate(out)]
        return rows, {"hf_sha": hashlib.sha256(HF.read_bytes()).hexdigest()[:12], "caution_rows": len(rows), "원장_10-14A⑥": 444}
    raise SystemExit(f"🔴 모르는 묶음 {name}")


# ── 실행 ──
def _patch_r(wide_fn=None, *, gate_absolute: bool = False) -> None:
    """(라) 를 실행 중에 흉내 낸다 — **하한 자리(`_with_encoder_risk`) 안에서만** 넓은 가드, 나머지 `encoder_cap` 자리는 지금 가드.

    🚨 확정 경로가 `encoder_cap` 을 다시 보지 않고 하한의 근거(`encoder_basis`)만 읽으면 여기서 확정이 는다 —
       그것이 이 실행이 찾으려는 것이다(분리 구현 때 막아야 할 자리). 스레드마다 표지를 따로 둔다(그래프가 노드를 병렬로 돌릴 수 있다).
    """
    import threading  # noqa: PLC0415

    from app import graph as g  # noqa: PLC0415

    tl = threading.local()
    cap0 = g.encoder_cap
    orig = g._with_encoder_risk  # noqa: SLF001
    fn = wide_fn or wide

    def cap(text: str):
        if getattr(tl, "on", False):
            return g.ENCODER_RECORD_MAX if fn(text) else None
        return cap0(text)

    def with_risk(j, premise, rows):
        tl.on = True
        try:
            return orig(j, premise, rows)
        finally:
            tl.on = False

    g.encoder_cap = cap
    g._with_encoder_risk = with_risk  # noqa: SLF001
    if gate_absolute:
        #: 🆕 R2 — 답 없는 확정 · 품목 선택 필요의 한 관문(`_absolute_types` · graph.py 3632 「여기 한 곳에서 거른다」)에 **지금 가드**를 건다.
        #:    넓힌 하한은 표시 · 질문(사실 확인 · 실증 · 인정 기능성)까지만 열고, 답 없는 확정은 지금처럼 막는다.
        abs0 = g._absolute_types  # noqa: SLF001

        def absolute(s):
            return abs0(s) if _V0(s.text) else set()

        g._absolute_types = absolute  # noqa: SLF001


def _sents(state: dict) -> list[dict]:
    out = []
    for s in state.get("sentences", []):
        direct = [c for c in s.encoder_candidates if c.moved_from is None]
        top = max(direct, key=lambda c: c.confidence).violation.value if direct else None
        out.append(
            {
                "text": s.text,
                "floor": s.risk.encoder is not None,
                "verdict": s.verdict.value,
                "enc_judged": encoder_judged(s),
                "conf_types": sorted(v.value for v in s.violations) if s.verdict is Verdict.confirmed else [],
                "hold_dict": sorted(v.value for v in s.violations) if s.verdict is Verdict.hold else [],
                "enc_top": top,
                #: 🆕 (다) 확인 — 보류의 종류(`hold_kind` · 답 대기 = 질문이 섰다) · 선 질문(사실 확인 종류 · 실증)
                "hold_kind": None if s.hold_kind is None else s.hold_kind.value,
                "fact_q": None if s.fact_check is None else s.fact_check.kind.value,
                "subst_q": s.substantiation is not None,
                "risk_final": None if s.risk.final is None else s.risk.final.value,
            }
        )
    return out


def run(a: argparse.Namespace) -> int:
    rows, mark = load(a.set)
    if a.guard == "V7":
        cs.claim_guard = base  # 🚨 `graph.encoder_cap` 이 `claimscope.claim_guard` 를 모듈 속성으로 부른다 — 이 실행 동안만
    if a.guard == "R":
        _patch_r()
    if a.guard == "R2":
        if not a.wide:
            raise SystemExit("🔴 R2 는 --wide V1|L|VN 이 있어야 한다")
        _patch_r(WIDE[a.wide], gate_absolute=True)
    stamp = {"set": a.set, "guard": a.guard + (f":{a.wide}" if a.guard == "R2" else ""), "rows": len(rows), **mark}
    stamp |= eg.use_encoder(None)
    if not stamp.get("encoder"):
        raise SystemExit("🔴 인코더가 꺼져 있다 — 잠금 채택 판을 켠다(COPYLANE_MODEL_DIR)")
    from app import graph as g  # noqa: PLC0415
    from app.db import pg_connect  # noqa: PLC0415

    review = g.build_review()
    preds = []
    t0 = time.perf_counter()
    with pg_connect() as conn, conn.cursor() as cur:
        stamp |= eg.check_dict(cur)
        cfg = {"configurable": {"conn": cur}}
        for k, r in enumerate(rows, 1):
            st = eg._checked(review.invoke({"text": r["text"], "product": r["product"]}, config=cfg))  # noqa: SLF001
            p = eg.predict(st)
            preds.append(
                {"id": r["id"], "gold": r["gold"], "labels": r["labels"], "class": p["class"], "types": p["types"],
                 "enc_risk": p.get("enc_risk"), "contract_error": st.get("_contract_error"), "sents": _sents(st)}
            )
            if k % 100 == 0:
                print(f"  … {k} / {len(rows)} · {time.perf_counter() - t0:.0f}초", file=sys.stderr)
    stamp |= {"judged_by": g.JUDGED_BY, "secs": round(time.perf_counter() - t0)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"stamp": stamp, "rows": preds}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"→ {a.out} · {len(preds)} 행 · {stamp['secs']}초 · 계약 위반 {sum(bool(p['contract_error']) for p in preds)}")
    print("  표지 " + " · ".join(f"{k} {v}" for k, v in stamp.items() if k not in ("set", "guard")))
    return 0


# ── 계산 ──
def _row(p: dict, guard, cguard=None) -> tuple[bool, bool, bool]:
    """(하한, 확정 위반, 확정 유형 맞음) — V7 실행 행에 가드 후보를 씌운 값. `cguard` 가 있으면 확정은 그 가드로."""
    cguard = cguard or guard
    floor = any(s["floor"] and guard(s) for s in p["sents"])
    types: set[str] = set()
    for s in p["sents"]:
        if s["conf_types"] and (not s["enc_judged"] or cguard(s)):
            types |= set(s["conf_types"])
    return floor, bool(types), bool(types & set(p["labels"]))


def _wil(k: int, n: int) -> str:
    w = eg.wilson(k, n)
    return f"{w[1]:.1%}" if w else "-"


def calc(a: argparse.Namespace) -> int:
    d0, d7 = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (a.v0, a.v7))
    s0, s7 = d0["stamp"], d7["stamp"]
    if (s0["guard"], s7["guard"]) != ("V0", "V7") or s0["set"] != s7["set"]:
        raise SystemExit(f"🔴 짝이 아니다 — {s0['set']}/{s0['guard']} · {s7['set']}/{s7['guard']}")
    for k in ("encoder", "dict_sha", "judged_by", "rows"):
        if s0.get(k) != s7.get(k):
            raise SystemExit(f"🔴 두 실행의 {k} 가 다르다 — {s0.get(k)} ≠ {s7.get(k)}")
    r0 = {p["id"]: p for p in d0["rows"]}
    r7 = d7["rows"]
    print(f"묶음 {s0['set']} · {len(r7)} 행 · 판 {s0.get('encoder')} · 사전 {s0.get('dict_sha')} · judged_by {s0.get('judged_by')}")
    for k in ("caution_rows", "m171_ids_sha", "m171_note", "hf_sha"):
        if k in s0:
            print(f"  {k} {s0[k]}")
    # ① 분해 검증 — V0 실측 = V0 계산
    bad = collections.Counter()
    ex = []
    for p in r7:
        q = r0[p["id"]]
        real = (bool(q["enc_risk"]), q["class"] == "확정위반", bool(set(q["types"]) & set(q["labels"])))
        calc_ = _row(p, GUARDS["V0"])
        for name, x, y in zip(("하한", "확정", "유형맞음"), real, calc_, strict=True):
            if x != y:
                bad[name] += 1
                if len(ex) < 8:
                    ex.append((p["id"], name, x, y))
    print(f"\n① 분해 검증 (V0 실측 ↔ V0 계산 · 다른 행) — 하한 {bad['하한']} · 확정 {bad['확정']} · 유형맞음 {bad['유형맞음']}")
    if ex:
        print("   예: " + " · ".join(f"{i} {n} 실측 {x}/계산 {y}" for i, n, x, y in ex))
    # ② 판별 표
    order = ("위반", "적법", "모호", "조건없음")
    golds = [g for g in order if any(p["gold"] == g for p in r7)] + sorted({p["gold"] for p in r7} - set(order))
    lk = "적법" if any(p["gold"] == "적법" for p in r7) else golds[0]
    n = collections.Counter(p["gold"] for p in r7)
    print("\n② 판별 (하한 붙은 행 / 확정 위반 행(유형 맞음)) — 분모 " + " · ".join(f"{g} {n[g]}" for g in golds))
    print("   판 | " + " | ".join(f"{g} 하한" for g in golds) + " | " + " | ".join(f"{g} 확정" for g in golds) + f" | {lk} 하한 95%상한 | {lk} 확정 95%상한")
    v0 = {p["id"]: _row(p, GUARDS["V0"]) for p in r7}
    allg = {k: (v, None) for k, v in GUARDS.items()} | SPLIT
    for name, (guard, cg) in allg.items():
        fl = collections.Counter()
        cf = collections.Counter()
        ty = collections.Counter()
        for p in r7:
            f, c, t = _row(p, guard, cg)
            fl[p["gold"]] += f
            cf[p["gold"]] += c
            ty[p["gold"]] += t
        print(
            f"   {name} | " + " | ".join(str(fl[g]) for g in golds) + " | "
            + " | ".join(f"{cf[g]}({ty[g]})" if g == "위반" else str(cf[g]) for g in golds)
            + f" | {_wil(fl[lk], n[lk])} | {_wil(cf[lk], n[lk])}"
        )
    # ③ V0 에서 바뀐 적법 행
    print("\n③ V0 대비 하한 · 확정이 새로 붙은 적법 행 (판마다 6 개까지)")
    for name, (guard, cg) in allg.items():
        if name in ("V0", "V7"):
            continue
        got = []
        for p in r7:
            if p["gold"] == "위반" or p["gold"] == "모호" or p["gold"] == "조건없음":
                continue
            f, c, _ = _row(p, guard, cg)
            f0, c0, _ = v0[p["id"]]
            if (f and not f0) or (c and not c0):
                got.append(("하한" if f and not f0 else "") + ("확정" if c and not c0 else "") + " " + " / ".join(s["text"][:40] for s in p["sents"]))
        print(f"   {name} — {len(got)} 행" + ("".join(f"\n     · {x}" for x in got[:6])))
    return 0


def check(a: argparse.Namespace) -> int:
    """(라) 실측(R 실행) ↔ (라) 계산(V7 + 가드 분리). 확정이 계산보다 많으면 지금 가드로 막히지 않는 확정 경로가 있다."""
    d0, d7, dr = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (a.v0, a.v7, a.r))
    if [d["stamp"]["guard"] for d in (d0, d7, dr)] != ["V0", "V7", "R"] or len({d["stamp"]["set"] for d in (d0, d7, dr)}) != 1:
        raise SystemExit("🔴 V0 · V7 · R 짝이 아니다")
    r0 = {p["id"]: p for p in d0["rows"]}
    rr = {p["id"]: p for p in dr["rows"]}
    fg, cg = SPLIT["(라) 하한 L정리+V1 · 확정 V0"]
    diff = collections.Counter()
    ex = []
    tab = collections.defaultdict(collections.Counter)
    for p in d7["rows"]:
        q, o = rr[p["id"]], r0[p["id"]]
        pf, pc, _ = _row(p, fg, cg)
        real = (bool(q["enc_risk"]), q["class"] == "확정위반")
        tab[p["gold"]]["n"] += 1
        tab[p["gold"]]["하한 실측"] += real[0]
        tab[p["gold"]]["확정 실측"] += real[1]
        tab[p["gold"]]["확정 V0"] += o["class"] == "확정위반"
        tab[p["gold"]]["조건부 실측"] += q["class"] == "조건부위반"
        tab[p["gold"]]["조건부 V0"] += o["class"] == "조건부위반"
        for k, x, y in (("하한", real[0], pf), ("확정", real[1], pc)):
            if x != y:
                diff[f"{k} 실측 {'참' if x else '거짓'} · 계산 {'참' if y else '거짓'}"] += 1
                if len(ex) < 10:
                    ex.append(f"{p['id']} {k} 실측 {x} 계산 {y} | " + " / ".join(s["text"][:35] for s in q["sents"]))
    print(f"묶음 {d7['stamp']['set']} · (라) 실측 ↔ 계산 — 다른 행 {dict(diff) or 0} · 계약 위반(R) {sum(bool(q['contract_error']) for q in rr.values())}")
    for e in ex:
        print("   · " + e)
    for g, c in tab.items():
        print(f"   {g} {c['n']} — 하한 {c['하한 실측']} · 확정 {c['확정 실측']}(V0 {c['확정 V0']}) · 조건부위반 {c['조건부 실측']}(V0 {c['조건부 V0']})")
    return 0


def holds(a: argparse.Namespace) -> int:
    """(다) 확인 — 인코더 하한이 붙은 문장이 **질문과 함께** 서는가. 묶음마다 보류 종류 · 질문 종류별 문장 수."""
    for path in a.files:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        st = d["stamp"]
        c = collections.Counter()
        q = collections.Counter()
        ex = collections.defaultdict(list)
        n_rows = collections.Counter(p["gold"] for p in d["rows"])
        f_rows = collections.Counter()
        for p in d["rows"]:
            hit = False
            for s in p["sents"]:
                if not s["floor"]:
                    continue
                hit = True
                k = s.get("hold_kind") or f"(보류 아님 · {s['verdict']})"
                c[(p["gold"], k)] += 1
                q[(p["gold"], s.get("fact_q") or ("실증" if s.get("subst_q") else "질문 없음"))] += 1
                if len(ex[(p["gold"], k)]) < 3:
                    ex[(p["gold"], k)].append(s["text"][:40])
            f_rows[p["gold"]] += hit
        print(f"\n## {st['set']} · {st['guard']} — 하한 붙은 행 " + " · ".join(f"{g} {f_rows[g]}/{n_rows[g]}" for g in n_rows))
        print("   하한 붙은 문장의 보류 종류: " + " · ".join(f"{g}·{k} {v}" for (g, k), v in sorted(c.items())))
        print("   하한 붙은 문장의 질문: " + " · ".join(f"{g}·{k} {v}" for (g, k), v in sorted(q.items())))
        for (g, k), v in sorted(ex.items()):
            print(f"     예 {g}·{k}: " + " / ".join(v))
    return 0


def table(a: argparse.Namespace) -> int:
    """(ㄷ) 판정(10-23) 의 두 지표 — 판마다 · 정답 칸마다:
    (ㄴ) 관문 = 하한이 붙었는데 **질문도 선택도 없는**(`hold_kind` = 확인 못 함) 문장이 있는 행 · (ㄱ) 보고 = 하한이 붙은 행 전부 · 확정 위반 행(유형 맞음)."""
    for path in a.files:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        st = d["stamp"]
        if not any("hold_kind" in s for p in d["rows"] for s in p["sents"]):
            print(f"🔴 {path} — 보류 종류 칸이 없다(옛 판 결과) · 다시 돌린다")
            continue
        n = collections.Counter()
        fl = collections.Counter()
        al = collections.Counter()
        cf = collections.Counter()
        ty = collections.Counter()
        for p in d["rows"]:
            g = p["gold"]
            n[g] += 1
            fl[g] += any(s["floor"] for s in p["sents"])
            al[g] += any(s["floor"] and s.get("hold_kind") == "unconfirmed" for s in p["sents"])
            cf[g] += p["class"] == "확정위반"
            ty[g] += bool(set(p["types"]) & set(p["labels"]))
        cells = []
        for g in sorted(n, key=lambda x: ("위반", "적법", "모호").index(x) if x in ("위반", "적법", "모호") else 9):
            if g in ("위반", "모호", "조건없음"):
                cells.append(f"{g} {n[g]}: 하한 {fl[g]} · 확정 {cf[g]}" + (f"({ty[g]})" if g == "위반" else ""))
            else:
                cells.append(f"{g} {n[g]}: (ㄴ)홀로 {al[g]} [{_wil(al[g], n[g])}] · (ㄱ)전부 {fl[g]} [{_wil(fl[g], n[g])}] · 확정 {cf[g]} [{_wil(cf[g], n[g])}]")
        print(f"{st['set']:12s} {st['guard']:6s} | " + " | ".join(cells) + f" | 계약 위반 {sum(bool(p['contract_error']) for p in d['rows'])}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--guard", choices=("V0", "V7", "R", "R2"), required=True)
    r.add_argument("--wide", choices=tuple(WIDE), help="R2 의 하한 가드")
    r.add_argument("--set", required=True)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("calc")
    c.add_argument("v0")
    c.add_argument("v7")
    k = sub.add_parser("check")
    k.add_argument("v0")
    k.add_argument("v7")
    k.add_argument("r")
    h = sub.add_parser("holds")
    h.add_argument("files", nargs="+")
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    a = ap.parse_args()
    return {"run": run, "calc": calc, "check": check, "holds": holds, "table": table}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
