"""인코더 단독으로 문장 몇 개 돌려 보기 — 판정 그래프 없이 모델 확률 · 후보만 본다 (박수진 · 2026-10-15 · 화면 확인용)

앱과 같은 코드(`app.encoder`)로 올리고 같은 문턱(`label_scheme.json`)으로 후보를 고른다. 잠금 밖 판(D4-10)도 이 도구에서만 올린다(D-333).
  uv run python docs\\psj\\e2e_prototype\\encoder_probe.py --model models\\copylane-encoder-kcbert-D4-00 --model <D4-10 폴더>
  uv run python docs\\psj\\e2e_prototype\\encoder_probe.py --model <폴더> --text "문장 하나" --text "문장 둘"
🚨 확인용이다 — 성능 수가 아니다(문장이 dev 가 아니다). 결과를 저장소에 남기지 않는다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app import encoder as enc  # noqa: E402
from app import premise as pm  # noqa: E402

SAMPLES = [
    "먹기만 해도 한 달에 10kg 빠지는 기적의 차",
    "100% 천연 원료만 사용했습니다",
    "매일 선착순 100명 한정, 지금 안 사면 다시는 이 가격 없어요",
    "식약처가 인정한 다이어트 효과",
    "면역력 강화에 탁월한 홍삼 젤리",
    "피로회복제 대신 이 음료 한 병이면 충분해요",
    "관절 통증을 줄여 주는 콜라겐 캔디",
    "당뇨 환자도 안심하고 먹으면 혈당이 내려가요",
    "꾸준히 마시면 암 예방에 도움이 됩니다",
    "실제 구매자 후기: 이거 먹고 아토피가 싹 나았어요",
    "타사 제품은 방부제 덩어리지만 우리 제품은 다릅니다",
    "시중 유산균보다 효과가 10배 뛰어납니다",
    "국내산 쌀로 지은 밥을 그대로 담았어요",
    "한 봉지에 단백질 12g이 들어 있어요",
    "냉장 보관 후 3일 안에 드세요",
]


def show(p, top=3):
    cand = " · ".join(f"{c.violation.value} {c.confidence:.2f}(≥{c.threshold:.2f})" for c in p.candidates) or "— 후보 없음"
    near = sorted(p.scores.items(), key=lambda kv: -kv[1])[:top]
    return cand, " · ".join(f"{v.value} {s:.2f}" for v, s in near)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", required=True, help="모델 폴더 (여러 번)")
    ap.add_argument("--text", action="append", help="문장 (비우면 예시 15개)")
    a = ap.parse_args(argv)
    enc.permit_unlocked()
    texts = a.text or SAMPLES
    for md in a.model:
        d = Path(md).resolve()
        m = enc.lock_match(d)
        model = enc.encoder_at(d)
        inputs = ((pm.ENCODER_UNKNOWN, *pm.ENCODER_INPUT.values()) if model.takes_category else (None,))
        print(f"\n━━ {d.name} · 잠금 {m.status}{' ' + m.name if m.name else ''} · 입력 {'품목 쌍' if model.takes_category else '문장만'}")
        for t in texts:
            print(f"\n▶ {t}")
            preds = model.predict_many(t, inputs) if model.takes_category else [model.predict(t)]
            for x, p in zip(inputs, preds, strict=True):
                cand, near = show(p)
                tag = f"[{x}] " if x else ""
                print(f"   {tag}후보: {cand}")
                print(f"   {' ' * len(tag)}상위: {near}{' · ⚠ 잘림' if p.truncated else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
