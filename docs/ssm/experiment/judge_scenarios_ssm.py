"""실제처럼 문구를 넣어 검수 그래프 전체를 돌리는 실험 — 소성민 · 2026-10-13.

★ 하는 일 — `app.api.judge`(화면 `/u/judge` 가 부르는 **같은 코어**)에 지어낸 광고 문구를 넣고, 응답 전체를 JSON 으로 남긴다.
   실제 DB(청크 · 임베딩 · 사전 · 위험도 표) + `.env` 의 인코더(`COPYLANE_MODEL_DIR`)로 돈다.
🚨 지표가 아니다 — 문구는 이 실험을 위해 지어낸 것이고(골든 · dev · 봉인 평가셋을 읽지 않는다 · D-175), 사례별 동작을 보는 것이다.
🚨 판정을 저장하지 않는다 — `/u/judge` 가 아니라 코어를 바로 부른다.

실행 (저장소 뿌리에서):
    uv run python docs/ssm/experiment/judge_scenarios_ssm.py
결과:
    build/eval/ssm_scenarios_<날짜>.json   (git 무시 폴더)
"""

from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from collect import env as _env  # noqa: E402

_env.load()

from app.api import judge  # noqa: E402
from app.contracts import Category, JudgeRequest, ProductContext  # noqa: E402

#: (id, 묶음, 문구, 넘길 품목 · None = 첫 검수처럼 품목 없이 · `건기식+인정` = 인정 받음, 기대 · 사람이 본 예상)
CASES: list[tuple[str, str, str, str | None, str]] = [
    # A. 사전에 있을 법한 명백한 위반
    ("A1", "명백한 위반", "암 예방에 좋은 음식입니다.", None, "질병 예방 표방 — 위반"),
    ("A2", "명백한 위반", "당뇨 치료에 효과가 있는 차입니다.", None, "질병 치료 표방 — 위반"),
    ("A3", "명백한 위반", "이 제품 하나로 탈모가 해결됩니다.", None, "질병 · 의약품 오인 — 위반"),
    ("A4", "명백한 위반", "한약 성분으로 몸속 독소를 해독합니다.", "식품", "의약품 오인 — 위반"),
    ("A5", "명백한 위반", "먹기만 하면 체지방이 100% 빠집니다.", "식품", "거짓 · 과장 — 위반"),
    # B. 사전에 없을 법한 위반 표현
    ("B1", "사전 밖 위반", "암을 완쾌해주는 음식", None, "질병 치료 표방 — 위반(권소라 재현)"),
    ("B2", "사전 밖 위반", "관절염이 씻은 듯이 낫습니다.", None, "질병 치료 표방 — 위반"),
    ("B3", "사전 밖 위반", "혈압약 대신 드셔도 됩니다.", "식품", "의약품 대체 — 위반"),
    ("B4", "사전 밖 위반", "일주일 만에 10kg 감량을 보장합니다.", "식품", "거짓 · 과장 — 위반"),
    # C. 조건 · 전제에 따라 갈리는 문구
    ("C1", "조건부", "붓기 관리에 좋은 원료를 담았습니다.", None, "기능성 표방 — 전제에 따라"),
    ("C2", "조건부", "면역력 강화에 도움을 줄 수 있습니다.", None, "인정 기능성이면 가능"),
    ("C3", "조건부", "면역력 강화에 도움을 줄 수 있습니다.", "건기식", "인정 여부로 갈림"),
    ("C4", "조건부", "특허받은 원료로 만들었습니다.", "식품", "사실이면 가능 — 실증"),
    ("C5", "조건부", "면역력 강화에 도움을 줄 수 있습니다.", "건기식+인정", "인정 기능성 — 가능"),
    # D. 화장품
    (
        "D1",
        "화장품",
        "주름 개선에 도움을 주는 기능성 화장품입니다.",
        "화장품",
        "기능성 심사 받았으면 가능",
    ),
    ("D2", "화장품", "아토피 피부를 치료하는 크림", "화장품", "의약품 오인 — 위반"),
    ("D3", "화장품", "손상된 피부 세포를 재생시킵니다.", "화장품", "의약품 오인 — 위반"),
    (
        "D4",
        "화장품",
        "순한 약산성 클렌저로 촉촉하게 세안하세요.",
        "화장품",
        "정상 — 오탐 확인(「한 약」)",
    ),
    # E. 비교 · 비방 · 후기
    (
        "E1",
        "비교·비방·후기",
        "타사 제품보다 흡수율이 2배 높습니다.",
        "식품",
        "부당 비교 — 실증 필요",
    ),
    ("E2", "비교·비방·후기", "경쟁사 제품은 유해 성분 덩어리입니다.", "식품", "비방 — 위반"),
    (
        "E3",
        "비교·비방·후기",
        "구매 고객 100%가 효과를 봤다고 후기를 남겼습니다.",
        "식품",
        "후기 기만 — 위반",
    ),
    # F. 정상 문구 (위반 없음 기대)
    ("F1", "정상", "바삭한 식감과 고소한 맛이 일품입니다.", "식품", "정상"),
    ("F2", "정상", "아침 식사 대용으로 간편하게 즐기세요.", "식품", "정상"),
    ("F3", "정상", "국내산 원료로 정성껏 만들었습니다.", "식품", "정상(원산지 사실이면)"),
    ("F4", "정상", "편안한 약속을 드립니다.", None, "정상 — 오탐 확인(「한약」)"),
    ("F5", "정상", "냉장 보관 후 개봉 즉시 드세요.", "식품", "정상 — 보관 안내"),
    # G. 실제 광고처럼 여러 문장
    (
        "G1",
        "여러 문장",
        "매일 아침 한 포로 시작하는 건강 습관! 장 건강에 도움을 주는 유산균 100억 마리. "
        "변비로 고생하던 분들도 3일 만에 효과를 봤어요. 의사들이 추천하는 바로 그 제품!",
        None,
        "기능성 · 후기 · 전문가 추천 — 섞임",
    ),
    (
        "G2",
        "여러 문장",
        "제주 유기농 녹차로 만든 깔끔한 맛. 하루 두 잔으로 상쾌한 오후를 보내세요. "
        "카페인이 적어 저녁에도 부담 없어요.",
        "식품",
        "대부분 정상 — 「카페인이 적어」 확인",
    ),
]


def _cat(name: str | None) -> ProductContext | None:
    """품목 이름 · `건기식+인정` 은 기능성 인정을 받았다고 넘긴다(인정번호는 넣지 않는다)."""
    if name is None:
        return None
    if name == "건기식+인정":
        return ProductContext(category=Category.건기식, has_recognized_function=True)
    return ProductContext(category=Category(name))


def _sentence(s) -> dict:  # noqa: ANN001
    return {
        "text": s.text,
        "verdict": s.verdict.value,
        "hold_reason": s.hold_reason.value if s.hold_reason else None,
        "violations": [v.value for v in s.violations],
        "infeasibility": s.infeasibility.value if s.infeasibility else None,
        "risk_floor": s.risk.floor.value if s.risk.floor else None,
        "risk_final": s.risk.final.value if s.risk.final else None,
        "not_claim": s.not_claim,
        "basis": [f"{e.law_id} {e.article} {e.item}".strip() for e in s.evidence if e.basis],
        "refs": [
            f"{e.doc_title or e.law_id} {e.article} {e.item}".strip()
            for e in s.evidence
            if not e.basis
        ][:5],
        "encoder": [
            {
                "v": c.violation.value,
                "p": round(c.confidence, 3),
                "moved_from": c.moved_from.value if c.moved_from else None,
            }
            for c in s.encoder_candidates
        ],
    }


def run() -> Path:
    out: dict = {
        "made_at": datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(),
        "cases": [],
    }
    print(f"사례 {len(CASES)}건 — 첫 호출은 인코더 · 임베딩 로드로 느리다")
    for cid, group, text, cat, expect in CASES:
        req = JudgeRequest(text=text) if cat is None else JudgeRequest(text=text, product=_cat(cat))
        t0 = time.perf_counter()
        try:
            res = judge(req)
            err = None
        except Exception as e:  # noqa: BLE001 — 실패한 사례도 기록하고 다음으로 간다
            res, err = None, f"{type(e).__name__}: {getattr(e, 'detail', '')}"
        ms = round((time.perf_counter() - t0) * 1000)
        row: dict = {
            "id": cid,
            "group": group,
            "text": text,
            "category_in": cat,
            "expect": expect,
            "ms": ms,
            "error": err,
        }
        if res is not None:
            row.update(
                outcome=res.outcome.value,
                category=res.category.value if res.category else None,
                category_source=res.category_source.value if res.category_source else None,
                judged_by=res.judged_by,
                law_version=res.law_version,
                not_reviewed=res.not_reviewed,
                sentences=[_sentence(s) for s in res.sentences],
                branches=[
                    {
                        "premise": b.premise.value,
                        "outcome": b.outcome.value,
                        "sentences": [_sentence(s) for s in b.sentences],
                    }
                    for b in res.branches
                ],
                certificate=(
                    {
                        "reason": res.certificate.reason.value,
                        "explanation": res.certificate.explanation,
                    }
                    if res.certificate
                    else None
                ),
                timings=[{"node": t.node, "ms": round(t.ms, 1)} for t in res.timings],
            )
        out["cases"].append(row)
        print(
            f"{cid:3} {ms:6d}ms  {row.get('outcome', 'ERROR'):11}  "
            f"{','.join(sorted({v for s in row.get('sentences', []) for v in s['violations']})) or '-':30}  {text[:30]}"
        )
    dest = ROOT / "build" / "eval" / f"ssm_scenarios_{datetime.now():%Y%m%d_%H%M}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장 — {dest.relative_to(ROOT)}")
    return dest


if __name__ == "__main__":
    run()
