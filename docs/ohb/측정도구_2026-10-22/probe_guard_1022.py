"""탐색 측정 — 주장 가드 세기 · 합의 면제를 D4-20 으로 다시 재기 (2026-10-22 · 클론 A · 미커밋 · 판정에 넣지 않음).

맥락 — 「면역력 쑥쑥」 · 「면역력 UP」은 사전(면역력 · 건기식 오인)과 인코더(건기식 오인 0.91~0.97)가 같은 유형을 가리키는데
       주장 가드(`claimscope.claim_guard` · 서술어 끝 ∨ 광고 표지)에 막혀 인코더 하한 · 인코더 쪽 확정이 서지 않는다.
       D-348 결정 3 · 5 는 가드 세기를 「적법 하한 비율 Wilson 95% 상한 ≤ 10% `[임의]` 안의 가장 느슨한 판」으로 고르라 했고
       D4-20 채택 뒤 다시 고르지 않았다. 합의 면제는 D-330 보충 3 의 미결 안건이다.

방법 — `claimscope.claim_guard` 를 판마다 바꿔 끼우고 그래프를 그대로 돈다(가드를 부르는 다섯 자리 · `graph.encoder_cap` 이 모두 이 함수를 부른다).
       기준판(V0)을 전 행 돌고, 판마다 **가드 값이 기준판과 달라지는 문장이 있는 행만** 다시 돈다(나머지 행은 결과가 같다).
판 —   V0 현재 · V1 관형형 끝 추가 · V2 구어 효능 표지 추가 · V3 V1+V2
       V4 합의 면제(사전 적중 유형 = 인코더 1위 유형) · V5 합의 면제(적법중첩 항목 제외) · V6 V3+V5 · V7 서술 · 광고 표지 조건 없음(주의 · 거부만 · 상한 참고)
       🆕 V5s 합의 면제(신뢰도 「단일」 항목만 — 모호 · 판독강등 · 비주장문맥 · 적법중첩 제외 · D-341 결정 2 가 접은 원인 = 비주장문맥) · V6s V3+V5s
묶음(`--set`) — dev(확장 dev · 골든 조건으로 위반/적법/모호) · gpt213(권소라 검수판 353 의 「판독(사람) 적법」 ∧ 애매 없음 213 · 전부 적법)
       · caution(주의사항 관측 축 · `build/probe_disease_consensus.py` `axis_sentences` · 전부 표시 · 주의 문구 = 적법 취급) — 데이터 밖 확인(D-348 보충 1 결정 2 · D-340 결정 8)
🚨 합의는 기준판의 기록 문장에서 문장 글자로 미리 센다 — 같은 글자가 다른 품목 행에 있으면 한 값을 쓴다(근사).
   인코더 1위 = 기록 문장의 후보 중 확신 최대 · 옮긴 후보는 옮기기 전 유형(`moved_from`)으로 사전 유형과 맞춘다.
지표(행 단위 · 조건 A·B·C = 위반 · D·L = 적법 · M = 모호 · `scripts/eval_graph.py` `encoder_risk_report` 와 같은 분모)
   ① 인코더 하한이 붙은 행 — 적법 비율 · Wilson 95% 상한 (결정 3 예산 ≤ 10%) · 분모 = 인코더가 돈 적법 행
   ② 위반 확정 행(확정 ∧ 위반 유형 있음) — 적법 확정 행 수(결정 2 의 dev 기준 ≤ 1 · 인코더 쪽 확정에 걸린 규칙이라 참고) · 위반 확정 · 그중 골든 유형 맞음
   ③ 기준판 대비 새로 붙은 · 새로 확정된 행 — 적법 쪽은 문구를 찍는다(육안 확인용)
🚨 dev(확장) 전용 — 봉인 평가셋을 읽지 않는다(D-175). 데이터 밖(검수판 171 · 다른 생성기 적법 213) 확인은 이 측정 밖이다.

쓰는 법(저장소 루트 · 클론 A)
    uv run python build/probe_guard_1022.py            # 조건부
    uv run python build/probe_guard_1022.py --uncond   # 무조건부
    uv run python build/probe_guard_1022.py --set gpt213            # 데이터 밖 — 품목 = 검수판 「분기」 (조건부)
    uv run python build/probe_guard_1022.py --set caution           # 데이터 밖 — 품목 건기식_비인정 (조건부) · --uncond 면 품목 모름
    uv run python build/probe_guard_1022.py --set m171              # 데이터 밖 — 측정용 171 (900 원본 · id 목록 · 지문 대조 · 클론 B)
    uv run python build/probe_guard_1022.py --only V6s V8           # 판을 골라서(기준판 V0 은 늘 돈다)
출력  표준출력 표 + build/eval/probe_guard_A1022_<cond|uncond>.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import claimscope  # noqa: E402
from app import encoder as enc  # noqa: E402
from app import graph as g  # noqa: E402
from app.contracts import Category, Premise, ProductContext, Verdict  # noqa: E402
from app import premise as pm  # noqa: E402
from scripts import eval_graph as eg  # noqa: E402

BASE = claimscope.claim_guard
#: [임의] 탐색용 꼴 — 관형형 어미로 끝남(「도움을 주는」 · 「건강한」)
ADNOMINAL = re.compile(r"(는|은|운|한|인|된|진|던|할|될|줄)\s*[.!?~]*\s*$")
#: [임의] 탐색용 꼴 — 구어 효능 표지(「쑥쑥」 · 「UP」 · 「↑」)
COLLOQ = re.compile(r"(쑥쑥|팡팡|빵빵|쭉쭉|씽씽|쌩쌩|튼튼|든든|탄탄|불끈|UP|Up|↑|⬆)")
TRUST = {}
for _l in (ROOT / "data" / "derived" / "banned_terms.jsonl").read_text(encoding="utf-8").splitlines():
    if _l.strip():
        _d = json.loads(_l)
        TRUST[_d["term"]] = _d.get("신뢰도")


def _pre(t: str) -> bool:
    return bool(t) and not claimscope.is_caution(t) and not claimscope.is_veto(t)


def variants(agree_all: set[str], agree_strict: set[str], agree_single: set[str]) -> dict[str, object]:
    def v(extra):  # noqa: ANN001, ANN202
        def guard(text: str) -> bool:
            t = (text or "").strip()
            return BASE(text) or (_pre(t) and extra(t))

        return guard

    return {
        "V0 현재": BASE,
        "V1 +관형형": v(lambda t: bool(ADNOMINAL.search(t))),
        "V2 +구어표지": v(lambda t: bool(COLLOQ.search(t))),
        "V3 V1+V2": v(lambda t: bool(ADNOMINAL.search(t) or COLLOQ.search(t))),
        "V4 합의": v(lambda t: t in agree_all),
        "V5 합의(적법중첩 제외)": v(lambda t: t in agree_strict),
        "V6 V3+V5": v(lambda t: bool(ADNOMINAL.search(t) or COLLOQ.search(t)) or t in agree_strict),
        "V5s 합의(단일만)": v(lambda t: t in agree_single),
        "V6s V3+V5s": v(lambda t: bool(ADNOMINAL.search(t) or COLLOQ.search(t)) or t in agree_single),
        "V7 표지 조건 없음": v(lambda t: True),
        "V8 V1+V5s": v(lambda t: bool(ADNOMINAL.search(t)) or t in agree_single),
    }


def cls(r: dict) -> str:
    c = r.get("조건") or ""
    return "위반" if c in ("A", "B", "C") else "적법" if c in ("D", "L") else "모호" if c == "M" else "-"


def summarize(st: dict) -> dict:
    sents = list(st.get("sentences", []))
    conf = sorted({v.value for s in sents if s.verdict is Verdict.confirmed and not s.not_claim for v in s.violations})
    return {
        "encoded": bool(st.get("encodings")),
        "enc_risk": any(s.risk.encoder is not None for s in sents),
        "confirmed": conf,
        "texts": [s.text for s in sents],
    }


def agreement(st: dict) -> tuple[set[str], set[str], set[str]]:
    scans = {x.sent_id: x for x in st.get("dict_scans", [])}
    a_all, a_strict, a_single = set(), set(), set()
    for s in st.get("sentences", []):
        if s.not_claim or not s.encoder_candidates:
            continue
        top = max(s.encoder_candidates, key=lambda c: c.confidence)
        tv = (top.moved_from or top.violation).value
        sc = scans.get(s.sent_id)
        hits = [*(sc.hits if sc else ()), *(sc.weak if sc else ())]
        if any(h.violation_type == tv for h in hits):
            a_all.add(s.text.strip())
        if any(h.violation_type == tv and TRUST.get(h.term) != "적법중첩" for h in hits):
            a_strict.add(s.text.strip())
        # V5s = 칸 때문에 내려간 자격 항목(`graph.dict_scan` `_lowered`)만 — 확정 막기 가드로 내려간 적중(`claimscope.confirm_block` · 주장 아닌 자리)은 뺀다
        if any(h.violation_type == tv and TRUST.get(h.term) == "단일" and not claimscope.confirm_block(s.text, h.span) for h in hits):
            a_single.add(s.text.strip())
    return a_all, a_strict, a_single


GPT_CSV = ROOT / "build" / "card17" / "LLM카피생성_GPT정상문구353검수용_ksr_2026-10-13.csv"
#: 🆕 측정용 171(권소라 검수판 900 의 「적법」 ∧ 애매 없음 중 박수진이 뗀 id · D-331 · 원장 10-13) — 클론 A 에는 900 원본이 없다(`face3785` 에서 저장소 밖)
M171_CSV = ROOT / "docs" / "ksr" / "LLM_카피생성_정상카피_900_판독용_ksr_2026-10-06.csv"
M171_IDS = ROOT / "build" / "card17" / "card17_measure171_ids.txt"
#: 지문(sha256 앞 16 자) — 원장 10-13(A) ⑤ ⑥ · 다르면 멈춘다(D-220)
FINGERPRINT = {"gpt": "c5c78314d1732a25", "m171_csv": "f3bfec9079e05c36", "m171_ids": "f633835161e5f3ef"}


def _sha16(path: pathlib.Path) -> str:
    if not path.exists():
        raise SystemExit(f"🔴 파일이 없다 — {path} (이 기기에 그 묶음이 없으면 그 --set 은 돌리지 않는다)")
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _check(path: pathlib.Path, key: str) -> None:
    got = _sha16(path)
    if got != FINGERPRINT[key]:
        raise SystemExit(f"🔴 {path.name} 지문 {got} ≠ {FINGERPRINT[key]} — 다른 판이다. 멈춘다")
#: 검수판 「분기」 → 전제 · 🚨 「건기식 꼴 · 인증 아니오(일반식품)」은 일반식품이 건기식 말투를 쓴 행이라 식품으로 넣는다(가정)
GPT_PREMISE = {"화장품 · 인증 아니오": Premise.화장품, "식품 · 인증 예": Premise.식품, "식품 · 인증 아니오": Premise.식품,
               "건기식 꼴 · 인증 아니오(일반식품)": Premise.식품}


def load_set(name: str, cond: bool) -> list[dict]:
    """묶음 → 행 [{id, text, 조건, product}] · 🔴 정의와 행 수가 어긋나면 멈춘다(D-220)."""
    if name == "m171":
        _check(M171_CSV, "m171_csv")
        _check(M171_IDS, "m171_ids")
        want = {x.strip().removeprefix("syn:") for x in M171_IDS.read_text("utf-8").splitlines() if x.strip()}
        rows = [r for r in csv.DictReader(M171_CSV.open(encoding="utf-8-sig", newline=""))
                if r["판독(사람)"] == "적법" and r.get("애매표시", "") != "Y" and r["id"] in want]
        if len(rows) != 171:
            raise SystemExit(f"🔴 측정용 id 171 중 {len(rows)} 행만 「적법」 · 애매 없음에 있다 — 멈춘다")
        out = []
        for r in rows:
            # 🚨 「분기」가 아는 값이면 그 전제 · 모르면(또는 칸이 없으면) 품목만 — 건기식 품목만이면 고르기 대기라 확정이 서지 않는다(보고에 수를 남긴다)
            prem = GPT_PREMISE.get(r.get("분기", ""))
            prod = (pm.product_of(prem) if prem else ProductContext(category=Category(r["품목"]))) if cond else ProductContext()
            out.append({"id": r["id"], "text": r["text"], "조건": "L", "product": prod, "_premise_known": bool(prem)})
        return out
    if name == "gpt213":
        _check(GPT_CSV, "gpt")
        rows = [r for r in csv.DictReader(GPT_CSV.open(encoding="utf-8-sig", newline=""))
                if r["판독(사람)"] == "적법" and r.get("애매표시", "") != "Y"]
        if len(rows) != 213:
            raise SystemExit(f"🔴 검수판 적법 · 애매 없음이 {len(rows)} 행 — 213 이 아니다")
        return [{"id": r["id"], "text": r["text"], "조건": "L",
                 "product": pm.product_of(GPT_PREMISE[r["분기"]]) if cond else ProductContext()} for r in rows]
    if name == "caution":
        spec = importlib.util.spec_from_file_location("pdc", ROOT / "build" / "probe_disease_consensus.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        prod = pm.product_of(Premise.건기식_비인정) if cond else ProductContext()
        return [{"id": f"ax{i}", "text": t, "조건": "L", "product": prod} for i, t in enumerate(mod.axis_sentences())]
    raise SystemExit(f"🔴 모르는 묶음 {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uncond", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--set", default="dev", choices=("dev", "gpt213", "caution", "m171"))
    #: 🆕 판 이름 앞부분으로 고른다(예: --only V8) · 기준판(V0)은 늘 돈다
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    cond = not a.uncond

    if a.set == "dev":
        golden = {json.loads(x)["id"]: json.loads(x) for x in eg.GOLDEN.read_text(encoding="utf-8").splitlines() if x.strip()}
        rows = eg.load_rows(dev=True, guide_dev=True)
        stamp = {"golden_sha": eg._sha12(eg.GOLDEN), "conditional": cond, "split": "dev+guide_dev"}
        stamp |= eg.check_dev(rows, enc.configured_dir())
        rows = [r for r in eg._mode_rows(rows, cond, a.limit) if r["id"] in golden]
        for r in rows:
            r["product"] = eg.product_of(r, cond)
    else:
        rows = load_set(a.set, cond)
        rows = rows[: a.limit] if a.limit else rows
        golden = {r["id"]: {"labels": []} for r in rows}
        src = {"gpt213": GPT_CSV, "m171": M171_CSV}.get(a.set, ROOT / "data" / "derived" / "hf_display_claims.jsonl")
        stamp = {"conditional": cond, "split": a.set, "rows": len(rows), "source_sha": eg._sha12(src)}
        if a.set == "m171":
            stamp["premise_known_rows"] = sum(1 for r in rows if r["_premise_known"])
    stamp |= eg.use_encoder(None)

    from app.db import pg_connect  # noqa: PLC0415

    review = g.build_review()
    t0 = time.perf_counter()
    res: dict[str, dict[str, dict]] = {}
    with pg_connect() as conn, conn.cursor() as cur:
        stamp |= eg.check_dict(cur)
        cfg = {"configurable": {"conn": cur}}

        def run(r: dict) -> dict:
            return eg._checked(review.invoke({"text": r["text"], "product": r["product"]}, config=cfg))

        base, a_all, a_strict, a_single = {}, set(), set(), set()
        for k, r in enumerate(rows, 1):
            st = run(r)
            base[r["id"]] = summarize(st)
            x, y, z = agreement(st)
            a_all |= x
            a_strict |= y
            a_single |= z
            if k % 100 == 0:
                print(f"  기준판 … {k}/{len(rows)} · {time.perf_counter() - t0:.0f}s", flush=True)
        res["V0 현재"] = base
        res_guard: dict[str, object] = {}
        print(f"  합의 문장 글자 — 전부 {len(a_all)} · 적법중첩 제외 {len(a_strict)} · 단일만 {len(a_single)}", flush=True)

        for name, guard in variants(a_all, a_strict, a_single).items():
            if name == "V0 현재" or (a.only and not any(name.startswith(o) for o in a.only)):
                continue
            todo = [r for r in rows if any(guard(t) != BASE(t) for t in base[r["id"]]["texts"])]
            print(f"  {name} — 다시 돌 행 {len(todo)} · {time.perf_counter() - t0:.0f}s", flush=True)
            res_guard[name] = guard
            claimscope.claim_guard = guard
            try:
                out = dict(base)
                for r in todo:
                    out[r["id"]] = summarize(run(r))
            finally:
                claimscope.claim_guard = BASE
            res[name] = out

    tag = ("" if a.set == "dev" else a.set + "_") + ("cond" if cond else "uncond")
    print(f"\n== 판 표지 {json.dumps(stamp, ensure_ascii=False)}")
    print(f"== 행 {len(rows)} · {tag} · {time.perf_counter() - t0:.0f}s")
    byid = {r["id"]: r for r in rows}
    print("\n판                      | ① 인코더 하한 행 위반/적법/모호 · 적법 비율 [상한] (≤10%) | ② 확정 행 위반(유형맞음)/적법/모호 | ③ 기준 대비 새 하한 · 새 확정(위반/적법/모호)")
    report = {}
    for name, out in res.items():
        n = collections.Counter()
        for rid, p in out.items():
            c, b = cls(byid[rid]), base[rid]
            gold = set(golden[rid]["labels"])
            if p["encoded"]:
                n[f"enc_n_{c}"] += 1
                n[f"enc_{c}"] += p["enc_risk"]
            if p["confirmed"]:
                n[f"conf_{c}"] += 1
                n["conf_ok"] += c == "위반" and bool(gold & set(p["confirmed"]))
            n[f"new_enc_{c}"] += p["enc_risk"] and not b["enc_risk"]
            n[f"new_conf_{c}"] += bool(p["confirmed"]) and not b["confirmed"]
        n_law = sum(1 for rid in out if cls(byid[rid]) == "적법")
        ci_c = eg.wilson(n["conf_적법"], n_law)
        n["conf_law_upper_pct"] = round(100 * ci_c[1], 2) if ci_c else None
        gfn = res_guard.get(name) or BASE  # ⛔ 이름 `g` 금지 — 모듈 `app.graph` 를 가린다
        n["guard_flip_law_sents"] = sum(1 for rid in out if cls(byid[rid]) == "적법" for t in base[rid]["texts"] if gfn(t) != BASE(t))
        lo_hi = eg.wilson(n["enc_적법"], n["enc_n_적법"])
        up = lo_hi[1] if lo_hi else float("nan")
        rate = n["enc_적법"] / n["enc_n_적법"] if n["enc_n_적법"] else float("nan")
        print(
            f"{name:22} | {n['enc_위반']:>4}/{n['enc_적법']:>3}/{n['enc_모호']:>3} · {rate:5.1%} [{up:5.1%}] {'안' if up <= 0.10 else '넘음'}"
            f" | {n['conf_위반']:>4}({n['conf_ok']:>4})/{n['conf_적법']:>3}/{n['conf_모호']:>3}"
            f" | 하한 +{n['new_enc_위반']}/+{n['new_enc_적법']}/+{n['new_enc_모호']} · 확정 +{n['new_conf_위반']}/+{n['new_conf_적법']}/+{n['new_conf_모호']}"
            f" | 적법 확정 상한 {n['conf_law_upper_pct']}% (≤2%) · 가드가 바뀐 적법 문장 {n['guard_flip_law_sents']}"
        )
        report[name] = dict(n) | {"lawful_rate": rate, "lawful_upper": up}

    print(f"\n   (분모 — 인코더가 돈 행: 위반 {report['V0 현재'].get('enc_n_위반', 0)} · 적법 {report['V0 현재'].get('enc_n_적법', 0)} · 모호 {report['V0 현재'].get('enc_n_모호', 0)})")
    for name in ("V3 V1+V2", "V5 합의(적법중첩 제외)", "V6 V3+V5", "V6s V3+V5s", "V8 V1+V5s"):
        if name not in res:
            continue
        out = res[name]
        lw = [(rid, out[rid]) for rid in out if cls(byid[rid]) == "적법"
              and ((out[rid]["enc_risk"] and not base[rid]["enc_risk"]) or (out[rid]["confirmed"] and not base[rid]["confirmed"]))]
        print(f"\n[{name}] 새로 걸린 적법 행 {len(lw)} (최대 15)")
        for rid, p in lw[:15]:
            print(f"   {rid} · 확정 {p['confirmed']} · 하한 {p['enc_risk']} · {byid[rid]['text'][:80]}")
        vw = [(rid, out[rid]) for rid in out if cls(byid[rid]) == "위반" and out[rid]["confirmed"] and not base[rid]["confirmed"]]
        print(f"[{name}] 새로 확정된 위반 행 {len(vw)} (최대 8)")
        for rid, p in vw[:8]:
            print(f"   {rid} · 확정 {p['confirmed']} · 골든 {golden[rid]['labels']} · {byid[rid]['text'][:70]}")

    for gname in ("V6s V3+V5s", "V8 V1+V5s"):
        g6 = res_guard.get(gname)
        if not g6:
            continue
        flips = [(rid, t) for rid in res["V0 현재"] if cls(byid[rid]) == "적법" for t in base[rid]["texts"] if g6(t) != BASE(t)]
        print(f"\n[{gname}] 가드가 거짓 → 참으로 바뀐 적법 문장 {len(flips)} (하한 · 확정이 안 붙어도 · 최대 25)")
        for rid, t in flips[:25]:
            print(f"   {rid} · {t[:70]}")
    # V6s 대비 V8 이 잃은 것 — V2(구어 표지) 몫
    if "V6s V3+V5s" in res and "V8 V1+V5s" in res:
        lost = [rid for rid in res["V8 V1+V5s"] if (res["V6s V3+V5s"][rid]["enc_risk"] and not res["V8 V1+V5s"][rid]["enc_risk"])
                or (res["V6s V3+V5s"][rid]["confirmed"] and not res["V8 V1+V5s"][rid]["confirmed"])]
        print(f"\n[V6s → V8] V2 를 빼서 잃은 행 {len(lost)} (하한 또는 확정)")
        for rid in lost[:15]:
            print(f"   {rid} · {cls(byid[rid])} · V6s 확정 {res['V6s V3+V5s'][rid]['confirmed']} · {byid[rid]['text'][:70]}")

    path = ROOT / "build" / "eval" / f"probe_guard_A1022_{tag}.json"
    path.write_text(json.dumps({"stamp": stamp, "report": report, "rows": res}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n✅ {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
