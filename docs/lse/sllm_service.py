"""sLLM 1단계 서비스 — 앱에서 부를 수 있게 1단계 → 후처리 → 관문을 함수 · HTTP 로 감싼다 (2026-10-05 · 붙이기 준비).

왜 따로 띄우나:
  앱 `.venv` 는 CPU torch 다(팀 lock 보호). sLLM 은 GPU torch · transformers · peft 가 있는 `.venv-sllm` 에서 돈다.
  한 프로세스에 합치면 패키지가 부딪힌다 → **sLLM 은 별도 프로세스로 띄우고 앱은 HTTP 로 부른다**(D-47 의 서빙 분리와 같은 뜻).

무엇을 돌려주나 (`rewrite` · `POST /rewrite`):
  outcome      candidate(후보) · hold(보류 — 사람 검토) · infeasible(합법화 불가)
  rewrite      계약 `RewriteSet` 꼴 {body, mandatory_note, placement} — candidate 일 때만
  infeasible   불가 사유(위반 유형 이름) — infeasible 일 때만
  reasons      관문 · 후처리가 막은 사유 — hold 일 때
  repairs      후처리가 고친 내역(원료명 되찾음 · 공식 문구로 등)
  model        1단계 어댑터 버전
🚨 candidate 도 적법 확정이 아니다 — 판정 코어 재판정(D-119)과 사람 검수가 남는다.
🚨 이 서비스는 대체 문구를 만드는 쪽이다(진입점 B · D-265). 검수(진입점 A)는 대체 문구를 내지 않는다.

실행 (repo 루트 · GPU venv · 모델 파일은 models/ 에 — 연결 안내서 참고):
    .venv-sllm/Scripts/python.exe docs/lse/sllm_service.py --text "고혈압 낮추는 오미자청, 문경 오미자를 설탕에 100일 숙성" --types 질병_예방치료_표방
    .venv-sllm/Scripts/python.exe docs/lse/sllm_service.py --serve --port 8765
    # 다른 터미널(앱 쪽 어디서든):
    curl -X POST localhost:8765/rewrite -H "Content-Type: application/json" \
         -d '{"text": "...", "violation_types": ["질병_예방치료_표방"]}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 모델은 캐시에 있다 — 허브 호출에서 멈추지 않게(10-02 embed 멈춤과 같은 원인)
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from typing import Literal  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402

from app.settings import PARAMS  # noqa: E402 — 문구 길이 상한은 앱과 한 곳(D-99)


class RewriteReq(BaseModel):
    """`POST /rewrite` 요청 — 🚨 모듈 맨 위에 둔다(함수 안에 두면 FastAPI 가 본문이 아니라 쿼리로 읽는다)."""

    #: 🔄 10-06 (팀장 전달 §2 #4) — 종전 500 자 · 앱은 2,000 자라 넘으면 422 가 「연결하지 못했어요」로 보였다
    text: str = Field(..., min_length=1, max_length=PARAMS.max_text_len)
    violation_types: list[str] = Field(default_factory=list)
    persona: str | None = None  # 고객층 설명 — 주면 2단계(말투)까지 돈다
    rejudge: bool = False  # 판정 코어 재판정(DB 필요)
    #: 🆕 10-06 (팀장 전달 §2 #3) — 품목(`app.contracts.Category` 값 · 판정 결과의 품목 · D-319). 없으면 후처리가 문구에서 추측한다
    category: Literal["식품", "건기식", "화장품", "일반상품", "전용법_미수록"] | None = None


_MODEL = None
#: 올라간 판의 표지 — `/health` 가 그대로 돌려준다(어느 어댑터 · 어느 베이스 · 가중치 지문)
_META: dict = {}
_LOCK = threading.Lock()  # generate 는 동시에 부르지 않는다 — GPU 하나 · 요청은 줄 세운다


def load(stage1: str | None = None) -> tuple:
    """모델을 한 번만 올린다. (model, tok, 어댑터 버전)."""
    global _MODEL
    if _MODEL is None:
        import torch  # noqa: PLC0415
        from peft import PeftModel  # noqa: PLC0415
        from persona_experiment import BASE  # noqa: PLC0415
        from persona_pipeline_e2e import STAGE1_VER, STAGE2  # noqa: PLC0415
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

        import sllm_meta  # noqa: PLC0415

        ver = stage1 or STAGE1_VER
        adapter = sllm_meta.stage1_dir(ver)
        if not adapter.exists():
            raise FileNotFoundError(f"1단계 어댑터가 없다 — {adapter} (연결 안내서의 「모델 파일」을 본다)")
        # 🆕 2026-10-07 — 어댑터가 학습된 베이스와 올리려는 베이스가 다르면 **올리기 전에** 멈춘다 (D-220).
        #    다른 베이스에 얹은 어댑터는 오류 없이 엉뚱한 문장을 낸다. 판 · 베이스는 `sllm_meta` 의 환경 변수로 바꾼다
        sllm_meta.check_base(adapter, BASE)
        if STAGE2.exists():
            sllm_meta.check_base(STAGE2, BASE)
        _META.update(model=ver, base=BASE, adapter_sha=sllm_meta.adapter_sha12(adapter),
                     stage2=STAGE2.name if STAGE2.exists() else None)
        tok = AutoTokenizer.from_pretrained(BASE)
        base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
        model = PeftModel.from_pretrained(base, str(adapter), adapter_name="stage1")
        if STAGE2.exists():
            model.load_adapter(str(STAGE2), adapter_name="stage2")
        model.eval()
        _MODEL = (model, tok, ver)
    return _MODEL


def _rejudge_view(r: dict) -> dict | None:
    """재판정 결과를 이유까지 싣는다(🆕 10-05) — 한 단어(`rejected`)만으로는 왜 떨어졌는지 모른다.
    status: rejected(위반 유형이 붙음 → 후보 탈락) · no_violation(위반 없음 — 🚨 통과 보증 아님) · passed · unavailable(DB 없음)."""
    if not r.get("rejudge"):
        return None  # 재판정을 안 켰거나 후보가 아니었다
    return {
        "status": r["rejudge"],
        "core_outcome": r.get("rejudge_outcome"),  # 판정 코어 종착(hold · certificate · guidance · passed)
        "violations": r.get("rejudge_violations") or [],
        "hold_reasons": r.get("rejudge_hold_reasons") or [],  # low_conf = 인코더 없음 · 확신 부족
        "basis": r.get("rejudge_basis") or [],
        "rejected_body": r.get("rejudge_body"),  # 탈락한 후보 문장
        "note": r.get("rejudge_note"),
    }


def rewrite(text: str, violation_types: list[str] | None = None, persona: str | None = None,
            do_rejudge: bool = False, category: str | None = None) -> dict:
    """문구 하나를 고쳐 쓴다. 위반 유형은 판정 코어(검수)가 준 것을 그대로 넘긴다 — 없으면 빈 목록."""
    from persona_pipeline_e2e import run_one  # noqa: PLC0415

    model, tok, ver = load()
    t0 = time.time()
    with _LOCK:
        r = run_one(model, tok, text, list(violation_types or []), persona, do_rejudge=do_rejudge, category=category)
    out = {
        "outcome": r["outcome"],
        "rewrite": None,
        "infeasible": r.get("infeasible"),
        "reasons": r.get("gate1") or [],
        "repairs": r.get("repairs") or [],
        "note_problem": r.get("note_problem"),
        "rejudge": _rejudge_view(r),
        "model": ver,
        "latency_ms": int((time.time() - t0) * 1000),
    }
    if r.get("rejudge") == "rejected":
        out["reasons"] = [*out["reasons"], "재판정 탈락: " + " · ".join(r.get("rejudge_violations") or ["근거 없음"])]
    if r["outcome"] == "candidate" and r.get("final"):
        out["rewrite"] = {"body": r["final"], "mandatory_note": r.get("note"), "placement": None}
    return out


def serve(port: int) -> None:
    import uvicorn  # noqa: PLC0415
    from fastapi import FastAPI  # noqa: PLC0415

    _, _, loaded = load()  # 첫 요청이 느리지 않게 미리 올린다(약 30초)
    app = FastAPI(title="CopyLane sLLM 1단계", version=loaded)

    @app.get("/health")
    def health() -> dict:
        load()
        return {"ok": True, **_META}

    @app.post("/rewrite")
    def do_rewrite(req: RewriteReq) -> dict:
        return rewrite(req.text, req.violation_types, req.persona, req.rejudge, req.category)

    uvicorn.run(app, host="127.0.0.1", port=port)  # 🚨 로컬만 — 외부에 열지 않는다


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--types", default="", help="위반 유형(쉼표)")
    ap.add_argument("--category", default=None, help="품목(식품 · 건기식 · 화장품 …) — 🆕 10-06")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if args.serve:
        serve(args.port)
    elif args.text:
        types = [t.strip() for t in args.types.split(",") if t.strip()]
        print(json.dumps(rewrite(args.text, types, category=args.category), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
