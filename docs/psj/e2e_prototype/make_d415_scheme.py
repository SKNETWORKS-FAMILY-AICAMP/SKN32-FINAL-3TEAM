"""D4-15 배포 폴더 만들기 — label_scheme.json 을 확장 dev 의 D-324 문턱 두 벌 + 재분할 지문으로 쓴다 (박수진 · 2026-10-15 · D-347)

D4-15 노트북의 모델 zip(label_scheme.experiment.json · F1 최대 미리 보기)을 풀어, 배포 시드(D4-15 (가) 6종 PR-AUC 최고 · D-324 결정 3)의
D-324 문턱(입력별 두 벌 · 목표 = D4-15a 가 확장 dev 로 다시 잰 카드 17 기준선 재현 평균)으로 label_scheme.json 을 새로 쓴다.
하위 폴더 없는 폴더 하나 + 그 폴더를 묶은 zip 을 낸다(D-333).

  uv run python docs\\psj\\e2e_prototype\\make_d415_scheme.py --base-dir <D4-15a CSV> --dir <D4-15 CSV> --model-zip <D4-15 모델 zip> --out <저장소 밖 폴더>

  · 칸 — label_thresholds = (나) 「모름」 · label_thresholds_by_cat = (가) 품목 앎 (D-339 결정 2) · input_format 문장쌍 · max_len 136
  · 확장 dev 양성 30 미만(부당 비교 25 · 후기 14)은 그 판의 F1 최대 · 비방(56)은 목표 재현율 (팀장 10-15)
  · 재분할 지문 — resplit "v1" · resplit_train_sha/rows · resplit_dev_sha/rows (D-347 결정 4) · dev_sha 는 devsplit 것 그대로
  · zip 안 시드가 배포 시드와 다르면 멈춘다
🔴 모델 폴더 · zip 은 저장소에 두지 않는다(D-249).
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import zipfile

import card17_adopt as ca
import score_encoder_dev as sd
from d4_15_resplit import D415, RESPLIT, SEEDS, base_probs, ext_dev, targets
from d4_17_ensemble_grid import thresholds

NAME = "copylane-encoder-kcbert-D4-15-재분할학습"
FEW = "F1 최대 (확장 dev 양성 30 미만 · D-347)"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--model-zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", default=D415, help="실험 태그 (🆕 10-16 · D4-18 이면 copylane-encoder-kcbert-D4-18-적법가중2 등)")
    ap.add_argument("--delta", type=float, default=0.0, help="목표 재현율 여유 δ (🆕 10-16 · D4-16 · D-324 개정 판정 뒤에만)")
    a = ap.parse_args()

    dev, guide, gsha, mark = ext_dev(sd.GOLDEN)
    D = dev + guide
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in D]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(sd.CONF8)}
    target = targets(Y, base_probs(a.base_dir, dev, guide), npos)
    by_seed, src, pr = {"품목": {}, "모름": {}}, None, {}
    for mode in by_seed:
        for s in SEEDS:
            P = sd.read_probs(os.path.join(a.dir, f"{a.run}_{mode}_seed{s}_dev행별확률.csv"), D)
            th, src = ca.d324_thresholds(Y, P, target)
            if a.delta:
                th = thresholds(Y, P, target, ca.GRID, a.delta, False, npos)
            th["기능성화장품_오인"] = 1.01
            by_seed[mode][str(s)] = th
            if mode == "품목":
                pr[s] = sd.macro_prauc(Y, P, 6)
    seed = max(SEEDS, key=lambda s: pr[s])
    th_unknown, th_cat = dict(by_seed["모름"][str(seed)]), dict(by_seed["품목"][str(seed)])

    name = a.run if a.run != D415 else NAME
    out = os.path.join(a.out, name)
    if os.path.exists(out):
        raise SystemExit(f"🔴 이미 있다 — {out}")
    with zipfile.ZipFile(a.model_zip) as z:
        exp = json.loads(z.read("label_scheme.experiment.json"))
        if exp.get("seed") != seed:
            raise SystemExit(f"🔴 모델 zip 의 시드 {exp.get('seed')} 가 배포 시드 {seed} 와 다르다 — 노트북은 (가) F1 미리 보기 기준이 아니라 같은 6종 PR-AUC 로 골랐는지 본다")
        if (exp.get("resplit_train_sha"), exp.get("resplit_dev_sha")) != (RESPLIT["train"][1], RESPLIT["dev"][1]):
            raise SystemExit("🔴 모델 zip 의 재분할 지문이 D-347 과 다르다")
        os.makedirs(out)
        for n in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
            with z.open(n) as src_f, open(os.path.join(out, n), "wb") as dst:
                shutil.copyfileobj(src_f, dst)
    cfg = json.load(open(os.path.join(out, "config.json"), encoding="utf-8"))
    assert [cfg["id2label"][str(i)] for i in range(len(sd.LABELS))] == sd.LABELS, "config 라벨 순서가 다르다"
    w_sha = sha(os.path.join(out, "model.safetensors"))

    keep = ("label_list", "confirmed_labels", "waiting_labels", "legacy_confirmed_labels", "backbone", "golden_sha256", "golden_rows",
            "train_rows", "train_by_cat", "train_label_pos", "dev_sha", "dev_rows", "score_view", "target_rule",
            "synthetic_lawful_rows", "synthetic_lawful_sha256", "synthetic_lawful_reviews", "synthetic_lawful_fact_rows", "input_format",
            "dev_macro_prauc6_by_seed", "best_epoch",
            "resplit", "resplit_train_sha", "resplit_train_rows", "resplit_dev_sha", "resplit_dev_rows",
            "resplit_train_used_rows", "dev_rows_extended", "dev_sha_extended", "neg_weight")
    scheme = {k: exp[k] for k in keep if k in exp}
    scheme.update({
        "label_thresholds": th_unknown,
        "label_thresholds_by_cat": th_cat,
        "label_thresholds_note": "label_thresholds = 「모름」 입력(기록 판정 · 품목 미확정) · label_thresholds_by_cat = 품목 입력(분기 · 재검수) — 가중치 하나 문턱 두 벌(D-336 결정 4 · 칸 이름은 D-339 결정 2 개정으로 확정)",
        "input_format": {**exp["input_format"], "values": ["식품", "건기식", "화장품"], "unknown": "모름",
                         "premise_to_input": {"식품": "식품", "건기식_인정": "건기식", "건기식_비인정": "건기식", "화장품": "화장품", "일반상품": "모름"}},
        "max_len": 136,
        "waiting_note": "편입 대기(D-321) — 칸은 두되 문턱 1.01 로 꺼 둔다",
        "selection_note": "회차는 확장 dev 의 (가) 품목 입력 6종 macro PR-AUC 로 · 배포 시드는 (가) 6종 PR-AUC 최고(D-324 결정 3)",
        "experiment": a.run, "target_recall_delta": a.delta, "notebook": exp.get("notebook", "D4-15 (박수진 · D4-10 + 재분할 v1 학습 — D-347)"),
        "baseline": "D4-10 = copylane-encoder-kcbert-D4-10-품목입력사실전제 (채택 · ef2c12a3b90f) · 같은 확장 dev 비교 = D4-10재현-확장dev",
        "seed": seed, "weights_sha256": w_sha,
        "threshold_rule": "D-324",
        "threshold_note": f"D-324{' + δ ' + str(a.delta) if a.delta else ''} — 유형 · 입력마다 「확장 dev 재현율이 목표(+δ) 이상인 가장 높은 문턱」 · 목표 = 카드 17 기준선 재현(D4-15a · 확장 dev) 시드 48 · 49 · 50 평균 · "
                          "격자 0.1~0.9(0.025). 확장 dev 양성 30 미만(부당 비교 · 후기)은 이 판의 F1 최대 · 비방은 양성 56 이라 목표 재현율(팀장 10-15). "
                          "편입 대기 칸은 1.01. 적용은 확률 >= threshold.",
        "threshold_targets": {k: round(v, 6) for k, v in target.items() if k in sd.CONF8},
        "threshold_source": {x: (FEW if s.startswith("F1") else s) for x, s in src.items()},
        "thresholds_by_seed": by_seed,
        "adoption": {"card": name.replace("copylane-encoder-kcbert-", ""), "verdict": "팀장 대조 · 채택 측정 대기", "deploy_seed": seed, "made_by": "make_d415_scheme.py",
                     "dev_mark": mark, "target_recall_delta": a.delta, "neg_weight": exp.get("neg_weight")},
        "final_test": False,
        "test_note": "새 봉인 평가셋(1,141행 · 74e37657d39ec325)은 봉인 회차 전까지 열지 않는다 (D-347 · D-175)",
        "experiment_only": False,
        "loader_note": "품목 입력(문장쌍) 판 — 모델 잠금(D-333)에 올리기 전에는 앱이 올리지 않는다",
    })
    with open(os.path.join(out, "label_scheme.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(scheme, f, ensure_ascii=False, indent=1)
    zpath = out + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for n in sorted(os.listdir(out)):
            z.write(os.path.join(out, n), n)
    print("[OK]", out, "· 배포 시드", seed, "· (가) 6종 PR-AUC", {s: round(v, 4) for s, v in pr.items()})
    for n in sorted(os.listdir(out)):
        print(f"  {n}  {sha(os.path.join(out, n))}  {os.path.getsize(os.path.join(out, n)):,}")
    print(f"  zip {os.path.basename(zpath)}  {sha(zpath)}  {os.path.getsize(zpath):,}")
    print("  label_thresholds (모름):", th_unknown)
    print("  label_thresholds_by_cat (품목):", th_cat)


if __name__ == "__main__":
    main()
