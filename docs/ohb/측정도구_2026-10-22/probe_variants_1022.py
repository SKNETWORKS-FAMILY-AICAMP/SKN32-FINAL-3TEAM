"""탐색 — 같은 주장의 표현 변형이 판정 그래프의 어느 단계에서 갈리는가 (2026-10-22 · 클론 A · 미커밋 · 판정에 넣지 않음).

문구마다 · 제품 정보마다(품목 모름 · 고른 전제) 단계별로 찍는다:
  사전 적중(단독판정 자격 · 자격 없음) → 칸(`graph.entry_cell`) → 확정 막기 가드(`claimscope.confirm_block`) → 주장 가드(`claimscope.claim_guard`)
  → 인코더 확률 · 문턱(기록 판정의 품목 입력) → 판정 · 보류 종류 · 위험도.
🚨 문구는 인자로만 받는다(없으면 기본 변형) · 봉인 평가셋을 읽지 않는다.

쓰는 법  uv run python build/probe_variants_1022.py                       # 기본: 면역력 변형
         uv run python build/probe_variants_1022.py "문구1" "문구2" ...
"""

from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import claimscope  # noqa: E402
from app import encoder as enc  # noqa: E402
from app import graph as g  # noqa: E402
from app import premise as pm  # noqa: E402
from app.contracts import Premise, ProductContext  # noqa: E402
from scripts import eval_graph as eg  # noqa: E402

DEFAULT = [
    "면역력강화에 도움을 주는",
    "면역력 강화에 도움을 줍니다",
    "면역력 쑥쑥",
    "면역력 쑥쑥!",
    "면역력이 쑥쑥 올라가요",
    "면역력 UP",
    "우리 아이 면역력 쑥쑥 튼튼",
]
PRODUCTS = [("품목 모름", ProductContext()), ("식품", pm.product_of(Premise.식품)),
            ("건기식_비인정", pm.product_of(Premise.건기식_비인정)), ("건기식_인정", pm.product_of(Premise.건기식_인정))]


def main() -> int:
    texts = sys.argv[1:] or DEFAULT
    print("판 표지", eg.use_encoder(None))
    scheme = enc.encoder_at(enc.configured_dir()).scheme
    from app.db import pg_connect  # noqa: PLC0415

    review = g.build_review()
    with pg_connect() as conn, conn.cursor() as cur:
        print("사전", eg.check_dict(cur))
        cfg = {"configurable": {"conn": cur}}
        for t in texts:
            print(f"\n■ 「{t}」 · 주장 가드 {claimscope.claim_guard(t)} · 거부 가드 {claimscope.is_veto(t)} · 주의 문구 {claimscope.is_caution(t)}")
            for name, prod in PRODUCTS:
                st = eg._checked(review.invoke({"text": t, "product": prod}, config=cfg))
                scans = {x.sent_id: x for x in st.get("dict_scans", [])}
                cin = g._encoder_inputs(prod.category)[0]
                encs = g._encodings_for(st, cin)
                thr = {getattr(k, "value", k): v for k, v in scheme.thresholds_for(None if cin == g.ANY_INPUT else cin).items()}
                for s in st.get("sentences", []):
                    sc = scans.get(s.sent_id)
                    hits = [f"{h.term}:{h.violation_type}" + (f"(막힘:{claimscope.confirm_block(s.text, h.span)})" if claimscope.confirm_block(s.text, h.span) else "") for h in (sc.hits if sc else ())]
                    weak = [f"{h.term}:{h.violation_type}" for h in (sc.weak if sc else ())]
                    e = encs.get(s.sent_id)
                    top = sorted(((p / thr[k], k, p, thr[k]) for k, p in (e.scores if e else ()) if k in thr and 0 < thr[k] <= 1), reverse=True)[:3]
                    tops = " · ".join(f"{k} {p:.3f}/{th:.3f}" for _, k, p, th in top)
                    print(f"   [{name:12}] 판정 {s.verdict.value:9} 보류종류 {s.hold_kind.value if s.hold_kind else '-':16} 사유 {s.infeasibility.value if s.infeasibility else '-'} · 위반 {[v.value for v in s.violations]} · 하한 사전 {getattr(s.risk.floor,'value',None)} 인코더 {getattr(s.risk.encoder,'value',None)} 최종 {getattr(s.risk.final,'value',None)}")
                    print(f"   {'':14} 사전 자격 {hits} · 자격 없음 {weak} · 인코더 근거 {sorted({b.violation.value for b in s.risk.encoder_basis})} · 후보 {[c.violation.value for c in s.encoder_candidates]}")
                    print(f"   {'':14} 인코더(입력 {cin}) 확률/문턱 상위: {tops}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
