"""D4-04 보충 ② Q3 — 판정 인코더 CPU 추론 시간 (박수진 · 2026-10-14 · 진단 · D-336 확인 요청)

문장 하나에 인코더를 한 번 돌리는 시간(배치 1 · CPU)을 dev 문장으로 잰다. 품목 입력은 문장쌍(품목 · 문장 · 길이 136)이고
문장 입력은 문장만(길이 128)이다 — 가중치 구조가 같아 D4-00 가중치로 두 입력을 다 잰다(품목 입력 판의 시간과 같은 계산량).

  uv run python docs\\psj\\e2e_prototype\\encoder_cpu_timing.py --model-dir <D4-00 모델 폴더(zip 을 푼 곳)>
      --n 200 (기본) · --threads 0 (기본 = torch 기본값) · --warmup 10

  · 출력 — 입력별 중앙값 · 평균 · 90 백분위(ms) · 문장 길이(토큰) 중앙값 · 분기 4 번을 돌릴 때의 문장당 추정(중앙값 × 4 — 품목 넷을 한 배치로 묶으면 더 짧다)
  · 묶음 시간도 같이 적는다 — 같은 문장의 품목 4 개를 한 배치(4 × 1)로 돌린 중앙값
🔴 dev 문장만 쓴다 (D-175). 문장은 출력하지 않는다.
"""
import argparse
import os
import statistics
import time

import score_encoder_dev as sd


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args(argv)

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    if a.threads:
        torch.set_num_threads(a.threads)
    tok = AutoTokenizer.from_pretrained(a.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(a.model_dir).eval()
    dev, gsha, mark = sd.load_dev(a.golden)
    texts = [r["text"] for r in dev][: a.n]
    cats = ["식품", "건기식", "화장품", "모름"]
    print(f"[INFO] golden {gsha[:12]} · dev {mark} · 문장 {len(texts)} · torch {torch.__version__} · threads {torch.get_num_threads()} · CPU")

    def run(enc):
        t0 = time.perf_counter()
        with torch.no_grad():
            model(**enc)
        return (time.perf_counter() - t0) * 1000

    res, lens = {"문장 입력 (128)": [], "품목 입력 (136)": [], "품목 넷 한 배치 (4 × 136)": []}, []
    for i, t in enumerate(texts):
        e1 = tok(t, truncation=True, max_length=128, return_tensors="pt")
        e2 = tok("식품", t, truncation="only_second", max_length=136, return_tensors="pt")
        e4 = tok(cats, [t] * 4, truncation="only_second", max_length=136, padding=True, return_tensors="pt")
        if i < a.warmup:
            run(e1), run(e2), run(e4)
            continue
        lens.append(int(e1["input_ids"].shape[1]))
        res["문장 입력 (128)"].append(run(e1))
        res["품목 입력 (136)"].append(run(e2))
        res["품목 넷 한 배치 (4 × 136)"].append(run(e4))
    q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
    print(f"\n문장 길이(토큰) 중앙값 {statistics.median(lens)} · 최대 {max(lens)} · 잰 문장 {len(lens)}")
    print("| 입력 | 중앙값 ms | 평균 ms | 90% ms |")
    print("|---|---:|---:|---:|")
    for k, v in res.items():
        print(f"| {k} | {statistics.median(v):.1f} | {statistics.mean(v):.1f} | {q(v, 0.9):.1f} |")
    m2, m4 = statistics.median(res["품목 입력 (136)"]), statistics.median(res["품목 넷 한 배치 (4 × 136)"])
    print(f"\n문장당 분기 4 번 — 따로 돌리면 약 {m2 * 4:.0f} ms · 한 배치로 묶으면 약 {m4:.0f} ms (+ 기록 판정 「모름」 한 번 {m2:.0f} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
