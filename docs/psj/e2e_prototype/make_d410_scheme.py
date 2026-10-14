"""D4-10 배포 폴더 만들기 — label_scheme.json 을 D-324 문턱 두 벌로 다시 쓴다 (박수진 · 2026-10-14)

D4-10 노트북의 모델 zip(label_scheme.experiment.json · F1 최대 미리 보기)을 풀어, 배포 시드 48 의 D-324 문턱
(입력별 두 벌 · card17_adopt.d324_thresholds · 목표 = 카드 17 기준선 재현 평균)으로 label_scheme.json 을 새로 쓴다.
하위 폴더 없는 폴더 하나 + 그 폴더를 묶은 zip 을 낸다(D-333 새 이름 폴더).

  uv run python docs\\psj\\e2e_prototype\\make_d410_scheme.py --dir <D4-00 CSV> --d10-dir <D4-10 CSV> --model-zip <D4-10 모델 zip> --out <저장소 밖 폴더>

  · 칸 — label_thresholds = (나) 「모름」 문턱(기록 판정 · 옛 로더가 읽어도 안전한 쪽) · label_thresholds_by_cat = (가) 품목 앎 문턱
          (칸 이름은 팀장 판정 대기 · D-336 결정 4) · input_format = 문장쌍 · max_len 136
  · 측정 불가 세 유형(후기 · 부당 비교 · 비방)은 이 판의 F1 최대 임시값 — 팀장 판정 대기(카드 17 값 0.6 · 0.6 · 0.3 으로 바꿀 수 있다 · `--card17-three`)
  · 가중치 sha256 이 c9c230918a95… 가 아니면 멈춘다
🔴 모델 폴더 · zip 은 저장소에 두지 않는다(git 무시 · D-249).
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

NAME = "copylane-encoder-kcbert-D4-10-품목입력사실전제"
TAG = "copylane-encoder-kcbert-D4-10-품목입력사실전제"
SEED = 48
W_SHA = "c9c230918a9503a678a8628303c87caa50d0eae5ba717bd31204340a46bf4042"
THREE = ["후기_체험기_기만", "부당_비교광고", "비방광고"]
CARD17_THREE = {"후기_체험기_기만": 0.6, "부당_비교광고": 0.6, "비방광고": 0.3}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--d10-dir", required=True)
    ap.add_argument("--model-zip", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--card17-three", action="store_true", help="세 유형 문턱을 카드 17 값으로 (팀장 판정이 (ㄴ) 이면)")
    a = ap.parse_args()

    dev, gsha, mark = sd.load_dev(sd.GOLDEN)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(y[i] for y in Y) for i, x in enumerate(sd.CONF8)}
    PB = {s: sd.read_probs(os.path.join(a.dir, f"{ca.BASE}_seed{s}_dev행별확률.csv"), dev) for s in ca.SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in ca.SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in ca.SEEDS) for x in rec[ca.SEEDS[0]]}
    by_seed, src = {"품목": {}, "모름": {}}, None
    for mode in by_seed:
        for s in ca.SEEDS:
            P = sd.read_probs(os.path.join(a.d10_dir, f"{TAG}_{mode}_seed{s}_dev행별확률.csv"), dev)
            th, src = ca.d324_thresholds(Y, P, target)
            th["기능성화장품_오인"] = 1.01
            by_seed[mode][str(s)] = th
    th_unknown, th_cat = dict(by_seed["모름"][str(SEED)]), dict(by_seed["품목"][str(SEED)])
    if a.card17_three:
        th_unknown.update(CARD17_THREE)
        th_cat.update(CARD17_THREE)

    out = os.path.join(a.out, NAME)
    if os.path.exists(out):
        raise SystemExit(f"🔴 이미 있다 — {out}")
    os.makedirs(out)
    with zipfile.ZipFile(a.model_zip) as z:
        exp = json.loads(z.read("label_scheme.experiment.json"))
        for n in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
            with z.open(n) as src_f, open(os.path.join(out, n), "wb") as dst:
                shutil.copyfileobj(src_f, dst)
    if sha(os.path.join(out, "model.safetensors")) != W_SHA:
        raise SystemExit("🔴 가중치 sha256 이 c9c230918a95… 가 아니다")
    cfg = json.load(open(os.path.join(out, "config.json"), encoding="utf-8"))
    assert [cfg["id2label"][str(i)] for i in range(len(sd.LABELS))] == sd.LABELS, "config 라벨 순서가 다르다"

    keep = ("label_list", "confirmed_labels", "waiting_labels", "legacy_confirmed_labels", "backbone", "golden_sha256", "golden_rows",
            "train_rows", "train_by_cat", "train_label_pos", "dev_sha", "dev_rows", "score_view", "target_rule",
            "synthetic_lawful_rows", "synthetic_lawful_sha256", "synthetic_lawful_reviews", "synthetic_lawful_fact_rows", "input_format",
            "dev_macro_prauc6_by_seed", "best_epoch")
    scheme = {k: exp[k] for k in keep if k in exp}
    scheme.update({
        "label_thresholds": th_unknown,
        "label_thresholds_by_cat": th_cat,
        "label_thresholds_note": "label_thresholds = 「모름」 입력(기록 판정 · 품목 미확정) · label_thresholds_by_cat = 품목 입력(분기 · 재검수) — 가중치 하나 문턱 두 벌(D-336 결정 4 · 칸 이름은 팀장 판정 대기)",
        "input_format": {**exp["input_format"], "values": ["식품", "건기식", "화장품"], "unknown": "모름",
                         "premise_to_input": {"식품": "식품", "건기식_인정": "건기식", "건기식_비인정": "건기식", "화장품": "화장품", "일반상품": "모름"}},
        "max_len": 136,
        "waiting_note": "편입 대기(D-321) — 칸은 두되 문턱 1.01 로 꺼 둔다",
        "selection_note": "회차는 (가) 품목 입력의 6종 dev macro PR-AUC 로 · 배포 시드는 (가) 6종 PR-AUC 최고(D-324 결정 3)",
        "experiment": TAG, "notebook": "D4-10 (박수진 · 품목 입력 + 검수 「적법(사실 전제)」 음성 — D-336 · D-331 결정 7)",
        "baseline": "D4-00 = copylane-encoder-kcbert-v10-카드17-검수정상음성 (시드 49 · 80348d88c0e9)",
        "seed": SEED, "weights_sha256": W_SHA,
        "threshold_rule": "D-324",
        "threshold_note": "D-324 — 유형 · 입력마다 「dev 재현율이 목표 이상인 가장 높은 문턱」 · 목표 = 카드 17 기준선 재현 시드 48 · 49 · 50 평균 · 격자 0.1~0.9(0.025). "
                          "dev 양성 30 미만(후기 · 부당 비교 · 비방)은 측정 불가(D-324 결정 2) — "
                          + ("카드 17 값(0.6 · 0.6 · 0.3 · D-331 결정 6)을 두 벌에 쓴다" if a.card17_three else "이 판의 F1 최대를 임시로 둔다(팀장 판정 대기)")
                          + ". 편입 대기 칸은 1.01. 적용은 확률 >= threshold.",
        "threshold_targets": {k: round(v, 6) for k, v in target.items() if k in sd.CONF8},
        "threshold_source": {x: ("카드 17 값 (측정 불가 · D-331 결정 6)" if a.card17_three and x in THREE else s) for x, s in src.items()},
        "thresholds_by_seed": by_seed,
        "adoption": {"card": "D4-10", "verdict": "dev 관문 · 한도 · 목표 통과 · 팀장 채택(10-14 · 사용자 전달)", "deploy_seed": SEED,
                     "made_by": "make_d410_scheme.py", "dev_mark": mark,
                     "sealed": "봉인 평가 한 회차(인코더 단독 · 10-14 · D4-T) — 판정 그래프 회차는 D-336 집행 뒤"},
        "final_test": True,
        "test_note": "봉인 평가셋은 10-14 한 회차(인코더 단독 · v10 · D4-00 과 같은 채점) — 이 수로 판 · 문턱을 고르지 않았다(D-175)",
        "experiment_only": False,
        "loader_note": "🔴 품목 입력(문장쌍) 판이다 — 앱 로더가 input_format 을 읽기 전(D-336 집행 전)에는 문장만 넣으면 잘못 돈다. 모델 잠금(D-333)에 올리기 전에는 앱이 올리지 않는다",
    })
    with open(os.path.join(out, "label_scheme.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(scheme, f, ensure_ascii=False, indent=1)
    zpath = out + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for n in sorted(os.listdir(out)):
            z.write(os.path.join(out, n), n)
    print("[OK]", out)
    for n in sorted(os.listdir(out)):
        print(f"  {n}  {sha(os.path.join(out, n))[:16]}  {os.path.getsize(os.path.join(out, n)):,}")
    print(f"  zip {os.path.basename(zpath)}  {sha(zpath)[:16]}  {os.path.getsize(zpath):,}")
    print("  label_thresholds (모름):", th_unknown)
    print("  label_thresholds_by_cat (품목):", th_cat)


if __name__ == "__main__":
    main()
