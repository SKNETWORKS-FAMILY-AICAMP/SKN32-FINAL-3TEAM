"""카드 17 채택 판의 label_scheme 을 D-324 문턱으로 다시 쓴다 (박수진 · 2026-10-12)

카드 17 노트북이 저장한 모델 zip 의 `label_scheme.json` 문턱은 **F1 최대**다(노트북의 미리보기 규칙).
채택 판의 문턱은 D-324 — `card17_adopt.py` 가 고른 값과 **같은 계산**으로 다시 쓴다. 가중치 · 토크나이저 · 다른 칸은 그대로다.

  uv run python docs\\psj\\e2e_prototype\\make_card17_scheme.py ^
      --src  <카드 17 모델 zip (영문 이름으로 받은 card17_model.zip 도 된다)> ^
      --dir  <행별 확률 폴더 (Downloads\\copylane_v10 · card17_csv.zip 을 푼 곳)> ^
      --out-dir <저장소 밖 폴더>

  · 문턱 = card17_adopt.d324_thresholds — 목표 = 기준선 재현 3 시드 유형별 재현율 평균 · 측정 가능 유형은 목표 이상인 가장 높은 문턱
           · dev 양성 30 미만 세 유형은 그 판의 F1 최대 (D-324 ⬜ · 임시 · label_scheme 에 표시)
  · zip 의 시드가 배포 시드(6종 PR-AUC 최고 · D-324 결정 3)와 다르면 멈춘다
  · 내는 것 — label_scheme.json · 그것만 바꿔 끼운 모델 zip · 가중치 지문 · 확인표(건수만)

🔴 dev 전용 (D-175) · 출력은 저장소 밖 (D-249) — 이 저장소 안이면 멈춘다.
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


def read_scheme(src):
    with zipfile.ZipFile(src) as z:
        name = next((n for n in z.namelist() if os.path.basename(n) == "label_scheme.json"), None)
        if name is None:
            raise SystemExit(f"🔴 zip 안에 label_scheme.json 이 없다: {src}")
        return json.loads(z.read(name)), z.namelist()


def sha12_in_zip(zpath):
    with zipfile.ZipFile(zpath) as z:
        name = next((n for n in z.namelist() if os.path.basename(n) == "model.safetensors"), None)
        if name is None:
            return None
        h = hashlib.sha256()
        with z.open(name) as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()[:12]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--golden", default=sd.GOLDEN)
    a = ap.parse_args(argv)
    out_dir = os.path.abspath(a.out_dir)
    repo = os.path.normcase(os.path.abspath(sd.REPO))
    try:
        in_repo = os.path.normcase(os.path.commonpath([out_dir, os.path.abspath(sd.REPO)])) == repo
    except ValueError:
        in_repo = False
    if in_repo:
        raise SystemExit(f"🔴 --out-dir 가 저장소 안이다 — 모델 · 문턱 파일은 저장소 밖에 둔다 (D-249): {out_dir}")
    try:
        raw, names = read_scheme(a.src)
    except zipfile.BadZipFile:
        raise SystemExit(f"🔴 zip 이 깨졌다 — 덜 받은 파일일 수 있다 (크기 {os.path.getsize(a.src):,} 바이트): {a.src}")

    dev, gsha, mark = sd.load_dev(a.golden)
    if raw.get("experiment") != ca.CAND or raw.get("seed") not in ca.SEEDS:
        raise SystemExit(f"🔴 카드 17 채택 판 후보의 zip 이 아니다 — experiment {raw.get('experiment')} · seed {raw.get('seed')}")
    if raw.get("golden_sha256") != gsha:
        raise SystemExit(f"🔴 학습한 골든과 지금 골든이 다르다 — {str(raw.get('golden_sha256'))[:12]} 대 {gsha[:12]}")
    if list(raw.get("label_list", [])) != sd.LABELS:
        raise SystemExit(f"🔴 칸 순서가 규약과 다르다: {raw.get('label_list')}")

    # card17_adopt 와 같은 계산
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    npos = {x: sum(r[i] for r in Y) for i, x in enumerate(sd.CONF8)}
    f = lambda tag, s: os.path.join(a.dir, f"{tag}_seed{s}_dev행별확률.csv")
    PB = {s: sd.read_probs(f(ca.BASE, s), dev) for s in ca.SEEDS}
    PC = {s: sd.read_probs(f(ca.CAND, s), dev) for s in ca.SEEDS}
    rec = {s: {x: ca.recall(Y, PB[s], i, sd.pick_thresholds(Y, PB[s])[x]) for i, x in enumerate(sd.CONF8) if npos[x]} for s in ca.SEEDS}
    target = {x: statistics.mean(rec[s][x] for s in ca.SEEDS) for x in rec[ca.SEEDS[0]]}
    pr = {s: sd.evaluate(dev, PC[s], sd.pick_thresholds(Y, PC[s]))["prauc6"] for s in ca.SEEDS}
    best = max(ca.SEEDS, key=lambda s: pr[s])
    seed = raw["seed"]
    if seed != best:
        raise SystemExit(f"🔴 zip 의 시드 {seed} 가 배포 시드(6종 PR-AUC 최고) {best} 와 다르다 (D-324 결정 3)")
    th, src = ca.d324_thresholds(Y, PC[seed], target)
    e_old, e_new = sd.evaluate(dev, PC[seed], {x: float(raw["label_thresholds"][x]) for x in sd.CONF8}), sd.evaluate(dev, PC[seed], th)
    syn = os.path.join(a.dir, f"{ca.CAND}_seed{seed}_합성정상_행별확률.csv")
    s_old = ca.syn_counts(syn, {x: float(raw["label_thresholds"][x]) for x in sd.CONF8}).get("합성정상dev", {})
    s_new = ca.syn_counts(syn, th).get("합성정상dev", {})

    print(f"golden {gsha[:12]} · 공통 dev {len(dev)}행 (지문 {mark}) · 채택 판 = {ca.CAND} 시드 {seed} (6종 PR-AUC {pr[seed]:.4f} · 배포 시드)")
    print("| 지표 | 원래 문턱 (F1 최대) | 새 문턱 (D-324) |\n|---|---:|---:|")
    print(f"| 위반 탐지 (/{e_new['scored']}) | {e_old['det']} | {e_new['det']} |")
    print(f"| 정답 유형 적중 | {e_old['hit']} | {e_new['hit']} |")
    print(f"| 음성(D · L) 오판정 (/{e_new['neg'][1]}) | {e_old['neg'][0]} | {e_new['neg'][0]} |")
    print(f"| 검수 적법 정상 문구 — 후보 · 조용 (/{s_new.get('n', 0)}) | {s_old.get('flag')} · {s_old.get('quiet')} | {s_new.get('flag')} · {s_new.get('quiet')} |")
    print("\n| 유형 | dev 양성 | 목표 재현율 | 원래 → 새 문턱 | 고른 방법 |\n|---|---:|---:|---|---|")
    for x in sd.CONF8:
        print(f"| {x} | {npos[x]} | {target[x] * 100:.1f}% | {float(raw['label_thresholds'][x]):g} → {th[x]:g} | {src[x]} |")

    new = dict(raw)
    new["label_thresholds"] = {x: (th[x] if x in th else float(raw["label_thresholds"][x])) for x in raw["label_list"]}
    new["thresholds_f1max_original"] = raw["label_thresholds"]
    new["threshold_rule"] = "D-324"
    new["threshold_targets"] = {x: round(target[x], 6) for x in sd.CONF8}
    new["threshold_source"] = {x: src[x] for x in sd.CONF8}
    new["threshold_note"] = ("D-324 — 유형마다 「dev 재현율이 목표 이상인 가장 높은 문턱」 · 목표 = 기준선 재현(카드17-Baseline재현) 시드 48 · 49 · 50 의 "
                             "유형별 재현율 평균 · 격자 0.1~0.9(0.025). dev 양성 30 미만(후기 · 부당 비교 · 비방)은 측정 불가(D-324 결정 2) — "
                             "이 판의 F1 최대를 임시로 둔다(⬜ 팀장 판정 전). 편입 대기 칸은 1.01. 적용은 확률 >= threshold.")
    new["adoption"] = {"card": "카드 17", "verdict": "채택 판 (dev · 관문 B · G1 · G3 + 목표)", "deploy_seed": seed,
                       "made_by": "make_card17_scheme.py", "dev_mark": mark,
                       "note": "test 미채점 — 봉인 평가는 D-322 A 회차에 기준선(v10)과 같이 (D-175)"}
    new.setdefault("max_len", 128)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "label_scheme.json"), "w", encoding="utf-8", newline="\n") as fo:
        json.dump(new, fo, ensure_ascii=False, indent=2)
    out_zip = os.path.join(out_dir, f"{ca.CAND}_seed{seed}_D324.zip")
    with zipfile.ZipFile(a.src) as zi, zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zi.infolist():
            if os.path.basename(info.filename) == "label_scheme.json":
                zo.writestr(info.filename, json.dumps(new, ensure_ascii=False, indent=2))
            else:
                with zi.open(info) as fi, zo.open(info.filename, "w", force_zip64=True) as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)
    print(f"\n[INFO] 새 문턱: {os.path.join(out_dir, 'label_scheme.json')}")
    print(f"[INFO] 넘길 모델 zip: {out_zip}")
    print(f"[INFO] 가중치 지문 (model.safetensors sha256 앞 12자 · D-178): {sha12_in_zip(out_zip)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
