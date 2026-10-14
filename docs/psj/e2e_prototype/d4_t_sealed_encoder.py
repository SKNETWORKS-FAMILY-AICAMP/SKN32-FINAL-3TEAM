"""D4-T 봉인 — 봉인 평가셋(test_sentence) 한 회차 · 인코더 단독 (박수진 · 2026-10-14)

D4 실험기록 「D4-T 봉인」 에 결과 전에 적었다 — v10 배포 · D4-00 배포 · D4-10 배포 후보((가) 품목 · (나) 모름)를
같은 채점(score_encoder_dev.evaluate)으로 잰다. 합격선 없음(D-322 A · G3). 이 수로 판 · 문턱 · 규칙을 고르지 않는다(D-175).

  python d4_t_sealed_encoder.py --golden <golden.jsonl> --v10 <폴더> --d400 <폴더> --d410 <폴더> --out-dir <저장소 밖> --out-md <집계표>
🔴 한 번만 돌린다. 행별 확률(행 id 포함)은 --out-dir(저장소 밖)에만 쓴다.
"""
import argparse
import csv
import hashlib
import json
import os
import statistics

import score_encoder_dev as sd

CATS = ["식품", "건기식", "화장품"]
TH = {
    "D4-00": {"질병_예방치료_표방": 0.45, "건강기능식품_오인": 0.65, "의약품_오인": 0.65, "거짓_과장": 0.475, "소비자_기만": 0.5,
              "후기_체험기_기만": 0.6, "부당_비교광고": 0.6, "비방광고": 0.3, "기능성화장품_오인": 1.01},
    "D4-10 (가) 품목": {"질병_예방치료_표방": 0.75, "건강기능식품_오인": 0.675, "의약품_오인": 0.825, "거짓_과장": 0.475, "소비자_기만": 0.4,
                     "후기_체험기_기만": 0.3, "부당_비교광고": 0.525, "비방광고": 0.5, "기능성화장품_오인": 1.01},
    "D4-10 (나) 모름": {"질병_예방치료_표방": 0.55, "건강기능식품_오인": 0.475, "의약품_오인": 0.6, "거짓_과장": 0.525, "소비자_기만": 0.4,
                     "후기_체험기_기만": 0.65, "부당_비교광고": 0.625, "비방광고": 0.275, "기능성화장품_오인": 1.01},
}


def load_test(path):
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    rows = []
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r["split"] == "test_sentence":
                r["target"] = sd.encoder_target(r)
                r["bucket"] = sd.bucket(r)
                r["reason"] = r.get("provenance") == "ftc_decisions_body" and r.get("구역") == "이유"
                rows.append(r)
    mark = hashlib.sha256("|".join(sorted(r["id"] for r in rows)).encode()).hexdigest()[:16]
    return rows, sha, mark


def infer(mdir, rows, pair_mode=None, bs=32):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(mdir)
    m = AutoModelForSequenceClassification.from_pretrained(mdir).eval()
    labs = [m.config.id2label[i] for i in range(m.config.num_labels)]
    assert labs == sd.LABELS, f"칸 순서가 다르다 {labs}"
    out = []
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        texts = [r["text"] for r in chunk]
        if pair_mode is None:
            e = tok(texts, truncation=True, max_length=128, padding=True, return_tensors="pt")
        else:
            cats = [(r.get("품목") if r.get("품목") in CATS else "모름") if pair_mode == "품목" else "모름" for r in chunk]
            e = tok(cats, texts, truncation="only_second", max_length=136, padding=True, return_tensors="pt")
        with torch.no_grad():
            out += torch.sigmoid(m(**e).logits).tolist()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--v10", required=True)
    ap.add_argument("--d400", required=True)
    ap.add_argument("--d410", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--out-md", required=True)
    a = ap.parse_args()
    rows, gsha, mark = load_test(a.golden)
    C = sd.CONF8
    with open(os.path.join(a.v10, "label_scheme.json"), encoding="utf-8") as f:
        TH["v10"] = json.load(f)["label_thresholds"]
    runs = [("v10", a.v10, None), ("D4-00", a.d400, None), ("D4-10 (가) 품목", a.d410, "품목"), ("D4-10 (나) 모름", a.d410, "모름")]
    E, npos = {}, None
    os.makedirs(a.out_dir, exist_ok=True)
    for name, mdir, pm in runs:
        P = infer(mdir, rows, pm)
        with open(os.path.join(a.out_dir, f"sealed_{name.replace(' ', '_')}_행별확률.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "조건", "bucket"] + [f"p_{x}" for x in sd.LABELS])
            for r, p in zip(rows, P):
                w.writerow([r["id"], r.get("조건") or "", r["bucket"]] + [f"{x:.6f}" for x in p])
        th = dict(TH[name])
        e = sd.evaluate(rows, P, th)
        E[name] = e
        print(f"  {name}: 탐지 {e['det']}/{e['scored']} · 적중 {e['hit']} · 음성 {e['neg'][0]}/{e['neg'][1]} · PR-AUC6 {e['prauc6']:.4f}")
    names = [n for n, _, _ in runs]
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in rows]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(C)}
    sc = E["v10"]["scored"]
    pend = [k for k, r in enumerate(rows) if r["bucket"] == "pending"]
    md = ["# D4-T 봉인 — 봉인 평가셋 한 회차 · 인코더 단독", "",
          f"> golden `{gsha[:12]}` · test_sentence {len(rows)}행 · 행 지문 `{mark}` · 2026-10-14 · 한 번만 돌렸다 · 합격선 없음(D-322 A · G3) · "
          "이 수로 판 · 문턱 · 규칙을 고르지 않는다(D-175) · 인코더 단독(판정 그래프 회차는 D-336 집행 뒤 팀장 도구) · 건수만 적는다", "",
          "| 지표 | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names),
          "| 6종 PR-AUC | " + " | ".join(f"{E[n]['prauc6']:.4f}" for n in names) + " |",
          f"| 위반 탐지 · 유형 무관 (/{sc}) | " + " | ".join(f"{E[n]['det']} ({E[n]['det'] / sc * 100:.1f}%)" for n in names) + " |",
          f"| 정답 유형 적중 (/{sc}) | " + " | ".join(f"{E[n]['hit']} ({E[n]['hit'] / sc * 100:.1f}%)" for n in names) + " |",
          f"| 유형 오인 (/{sc}) | " + " | ".join(str(E[n]['cat_n']['F1 유형 오인']) for n in names) + " |",
          f"| 놓침 (/{sc}) | " + " | ".join(str(E[n]['cat_n']['F2 놓침']) for n in names) + " |",
          f"| 음성(D · L) 오판정 (/{E['v10']['neg'][1]}) | " + " | ".join(f"{E[n]['neg'][0]} ({E[n]['neg'][0] / E[n]['neg'][1] * 100:.1f}%)" for n in names) + " |",
          f"| 「유형 없는 위반」에 후보 (/{len(pend)}) | " + " | ".join(str(sum(1 for k in pend if E[n]['cand'][k])) for n in names) + " |",
          "", "## 유형별 재현율", "", "| 유형 | 정답 행 | " + " | ".join(names) + " |", "|---|---:|" + "---:|" * len(names)]
    for x in C:
        if npos[x]:
            md.append(f"| {x} | {npos[x]} | " + " | ".join(f"{E[n]['types'][x]['tp'] / npos[x] * 100:.1f}%" for n in names) + " |")
    md += ["", "문턱 — v10 은 그 판 label_scheme · D4-00 은 채택 판 label_scheme(D-324) · D4-10 은 배포 시드 48 의 입력별 D-324 문턱(dev 에서 고름). "
           "(가) 품목 = 골든 `품목` 칸(빈 칸은 「모름」) · (나) = 전부 「모름」.",
           "", "🔒 봉인 평가셋 수다 — 판 · 문턱 · 규칙을 이 수에 맞춰 고치지 않는다(D-175)."]
    with open(a.out_md, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
