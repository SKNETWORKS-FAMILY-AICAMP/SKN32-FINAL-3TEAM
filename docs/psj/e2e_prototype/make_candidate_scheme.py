"""채택 후보 모델의 문턱을 「유형별 목표 재현율」로 다시 쓴다 (박수진 · 2026-10-08)

카드 14 의 채택 후보 = 카드 9 설정 모델(선택 시드 46) + 유형별 목표 재현율 문턱.
학습 노트북이 모델 zip 에 넣은 label_scheme.json 의 문턱은 **F1 최대**다 — 그대로 쓰면 위반 탐지가 v10 보다 낮다.
이 스크립트는 문턱만 바꿔 넘길 판을 만든다. 가중치 · 토크나이저 · 다른 칸은 손대지 않는다.

  uv run python docs\\psj\\e2e_prototype\\make_candidate_scheme.py ^
      --src  <카드 14 모델 zip (Drive copylane_v10_card14/copylane-encoder-kcbert-v10-카드9-정상음성.zip)> ^
      --dir  <행별 확률 폴더 (Downloads\\copylane_v10)> ^
      --out-dir <저장소 밖 폴더>

  · 목표 재현율 = 유형마다 **v10(선택 시드 42 · 자기 F1 최대 문턱)의 dev 재현율** — 팀장이 목표 값을 정하기 전의 임시값이다
  · 문턱 = 후보 모델(시드 46)의 dev 재현율이 그 목표 이상인 가장 높은 문턱 (격자 0.1 ~ 0.9 · 0.025 · 카드 13 · 14 와 같은 방식)
           dev 양성 10 미만 유형은 0.5 · 편입 대기 칸은 원래 값(1.01 · 꺼 둠) 그대로
  · 내는 것 — label_scheme.json (문턱만 바뀐 것) · --src 가 모델 zip 이면 label_scheme 만 바꿔 끼운 새 모델 zip
             · 화면에 건수만 적은 확인표 (v10 대 후보 · 위반 탐지 · 음성 오판정 · 정상 합성 문구 후보)
  · --self-test — v10 을 자기 자신에 맞춰 v10 의 수가 그대로 나오는지 본다 (계산 확인용 · 파일을 쓰지 않는다)

🔴 dev 전용 (D-175). test 는 읽지 않는다 — 넘긴 판은 「test 미채점 후보」다 (final_test 는 false 그대로).
🔴 출력은 저장소 밖에 둔다 — 모델 zip(약 420MB)은 커밋하지 않는다 (D-249). --out-dir 가 저장소 안이면 멈춘다.
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import zipfile

import score_encoder_dev as sd

CAND_TAG = "copylane-encoder-kcbert-v10-카드9-정상음성"
V10_TAG = "copylane-encoder-kcbert-v10-합성O-이유O"
SEED = 46                      # 카드 14 의 선택 시드 (6종 PR-AUC 가 가장 높은 시드 · 규약 4절)
MAX_LEN = 128                  # 학습 노트북의 MAX_LEN — 로더가 이 칸을 읽는다 (app/encoder.py)
RULE = "target_recall_v10"


def matched(Y, P, target):
    """유형마다 재현율이 target 이상인 가장 높은 문턱. 격자 끝(0.1)에서도 못 미치면 0.1 과 함께 알린다."""
    th, short = {}, []
    for i, x in enumerate(sd.CONF8):
        y = [r[i] for r in Y]
        n = sum(y)
        if n < 10:
            th[x] = 0.5
            continue
        best = None
        for t in sd.TH_GRID:
            tp = sum(1 for k in range(len(Y)) if y[k] and P[k][i] >= t)
            if tp / n >= target[x] - 1e-12:
                best = t
        if best is None:
            best = sd.TH_GRID[0]
            short.append(x)
        th[x] = best
    return th, short


def read_raw_scheme(src):
    """폴더 · zip · json 에서 label_scheme.json 원문(dict)을 읽는다."""
    if os.path.isdir(src):
        src = os.path.join(src, "label_scheme.json")
    if src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            name = next((n for n in z.namelist() if os.path.basename(n) == "label_scheme.json"), None)
            if name is None:
                raise SystemExit(f"🔴 zip 안에 label_scheme.json 이 없다: {src}")
            return json.loads(z.read(name)), z.namelist()
    with open(src, encoding="utf-8") as f:
        return json.load(f), []


def syn_flags(path, th):
    """정상 합성 문구 — 측정용 285행에서 후보가 선 행 · 조용한 행(모든 유형이 문턱의 절반 미만)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["갈래"] == "합성정상dev"]
    cand = sum(any(float(r[f"p_{x}"]) >= th[x] for x in sd.CONF8) for r in rows)
    quiet = sum(all(float(r[f"p_{x}"]) < th[x] * 0.5 for x in sd.CONF8) for r in rows)
    return cand, quiet, len(rows)


def safetensors_sha12(zpath):
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
    ap.add_argument("--src", help="카드 14 모델 zip · 모델 폴더 · label_scheme.json")
    ap.add_argument("--dir", required=True, help="행별 확률 CSV 폴더 (v10 · 카드 9 설정 시드 46)")
    ap.add_argument("--v10-scheme", default=None, help="v10 의 문턱 (기본: <dir>/" + V10_TAG + "_scheme.zip)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--golden", default=sd.GOLDEN)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    dev, gsha, mark = sd.load_dev(a.golden)
    Y = [[1 if x in r["target"] else 0 for x in sd.LABELS] for r in dev]
    v10_scheme = a.v10_scheme or os.path.join(a.dir, f"{V10_TAG}_scheme.zip")
    th10, _ = sd.read_scheme(v10_scheme)
    P10 = sd.read_probs(os.path.join(a.dir, f"{V10_TAG}_dev행별확률.csv"), dev)
    e10 = sd.evaluate(dev, P10, th10)
    target = {x: e10["types"][x]["tp"] / e10["types"][x]["n"] for x in sd.CONF8 if e10["types"][x]["n"]}

    if a.self_test:
        th, short = matched(Y, P10, target)
        e = sd.evaluate(dev, P10, th)
        print(f"[self-test] v10 을 자기 자신에 맞춤 — 위반 탐지 {e10['det']} → {e['det']} · 음성 오판정 {e10['neg'][0]} → {e['neg'][0]}")
        print("  문턱 (v10 → 맞춘 값):", " · ".join(f"{x} {th10[x]:g}→{th[x]:g}" for x in sd.CONF8))
        print("  재현율이 같아야 한다:", all(e["types"][x]["tp"] == e10["types"][x]["tp"] for x in sd.CONF8), "· 못 맞춘 유형:", short or "없음")
        return 0
    if not a.src or not a.out_dir:
        raise SystemExit("🔴 --src 와 --out-dir 가 필요하다 (--self-test 가 아니면)")
    out_dir = os.path.abspath(a.out_dir)
    # 이 저장소(sd.REPO) 안인지만 본다 — sd.inside_repo 는 위쪽 어디든 .git 이 있으면 참이라 홈 폴더가 git 이면 늘 멈춘다
    repo = os.path.normcase(os.path.abspath(sd.REPO))
    try:
        in_repo = os.path.normcase(os.path.commonpath([out_dir, os.path.abspath(sd.REPO)])) == repo
    except ValueError:                                  # 드라이브가 다르면 저장소 밖이다
        in_repo = False
    if in_repo:
        raise SystemExit(f"🔴 --out-dir 가 저장소 안이다 — 모델 · 문턱 파일은 저장소 밖에 둔다 (D-249): {out_dir}")

    raw, names = read_raw_scheme(a.src)
    # 🔴 넘길 판이 맞는지 — 카드 9 설정 · 시드 46 · 카드 14 노트북 · 칸 순서
    if raw.get("experiment") != CAND_TAG or raw.get("seed") != SEED or "card14" not in str(raw.get("notebook", "")):
        raise SystemExit(f"🔴 카드 14 의 선택 시드 판이 아니다 — experiment {raw.get('experiment')} · seed {raw.get('seed')} · "
                         f"notebook {raw.get('notebook')} (기대 {CAND_TAG} · {SEED} · v10-card14)")
    if list(raw.get("label_list", [])) != sd.LABELS:
        raise SystemExit(f"🔴 칸 순서가 규약과 다르다: {raw.get('label_list')}")
    if raw.get("golden_sha256") != gsha:
        raise SystemExit(f"🔴 학습한 골든과 지금 골든이 다르다 — {str(raw.get('golden_sha256'))[:12]} 대 {gsha[:12]}")

    Pc = sd.read_probs(os.path.join(a.dir, f"{CAND_TAG}_seed{SEED}_dev행별확률.csv"), dev)
    th_old = {x: float(raw["label_thresholds"][x]) for x in sd.CONF8}
    th, short = matched(Y, Pc, target)
    if short:
        raise SystemExit(f"🔴 격자 끝(0.1)에서도 v10 재현율에 못 미치는 유형이 있다: {short} — 넘기지 않는다")
    e_old, e_new = sd.evaluate(dev, Pc, th_old), sd.evaluate(dev, Pc, th)
    syn_path = os.path.join(a.dir, f"{CAND_TAG}_seed{SEED}_합성정상_행별확률.csv")
    s_old, s_new = syn_flags(syn_path, th_old), syn_flags(syn_path, th)

    # ── 확인표 (건수만)
    print(f"golden {gsha[:12]} · 공통 dev {len(dev)}행 (지문 {mark}) · 후보 = {CAND_TAG} 시드 {SEED}")
    print("| 지표 | v10 (F1 최대) | 후보 · 원래 문턱 (F1 최대) | 후보 · 새 문턱 (v10 재현율 맞춤) |")
    print("|---|---:|---:|---:|")
    print(f"| 위반 탐지 (/{e10['scored']}) | {e10['det']} | {e_old['det']} | {e_new['det']} |")
    print(f"| 정답 유형 적중 | {e10['hit']} | {e_old['hit']} | {e_new['hit']} |")
    print(f"| 음성(D · L) 오판정 (/{e10['neg'][1]}) | {e10['neg'][0]} | {e_old['neg'][0]} | {e_new['neg'][0]} |")
    print(f"| 정상 합성 문구 — 후보 · 조용 (/{s_new[2]}) | — | {s_old[0]} · {s_old[1]} | {s_new[0]} · {s_new[1]} |")
    print("\n| 유형 | dev 양성 | 목표 재현율 (v10) | 후보 재현율 | 원래 문턱 → 새 문턱 |")
    print("|---|---:|---:|---:|---|")
    for x in sd.CONF8:
        n = e10["types"][x]["n"]
        print(f"| {x} | {n} | {target[x] * 100:.1f}% | {e_new['types'][x]['tp'] / n * 100:.1f}% | {th_old[x]:g} → {th[x]:g} |")

    # ── 새 label_scheme — 문턱 칸만 바꾸고 바꾼 까닭을 적는다
    new = dict(raw)
    new["label_thresholds"] = {x: (th[x] if x in th else float(raw["label_thresholds"][x])) for x in raw["label_list"]}
    new["thresholds_f1max_original"] = raw["label_thresholds"]
    new["threshold_rule"] = RULE
    new["threshold_targets"] = {x: round(target[x], 6) for x in sd.CONF8}
    new["threshold_note"] = (f"유형별 목표 재현율 — 유형마다 v10({V10_TAG} · 선택 시드 42 · F1 최대 문턱)의 공통 dev 재현율 이상인 가장 높은 문턱 "
                             "· 격자 0.1~0.9(0.025) · dev 양성 10건 미만이면 0.5 · 편입 대기 칸은 원래 값. 적용은 확률 >= threshold. "
                             "목표 재현율 값은 팀장 판정 전의 임시값이다 (실험 기록 카드 13 · 14)")
    new["threshold_source"] = {"golden_sha256": gsha, "dev_mark": mark, "v10_probs": f"{V10_TAG}_dev행별확률.csv",
                               "candidate_probs": f"{CAND_TAG}_seed{SEED}_dev행별확률.csv", "made_by": "make_candidate_scheme.py"}
    new["candidate_note"] = "카드 14 채택 후보 — test 미채점 (D-175) · 팀장 판정 셋(문턱 규칙 · 골든 밖 재료 · 관문 지표) 대기"
    new.setdefault("max_len", MAX_LEN)

    os.makedirs(out_dir, exist_ok=True)
    js = os.path.join(out_dir, "label_scheme.json")
    with open(js, "w", encoding="utf-8", newline="\n") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
    print(f"\n[INFO] 새 문턱: {js}")

    if a.src.lower().endswith(".zip") and any(os.path.basename(n) == "model.safetensors" for n in names):
        out_zip = os.path.join(out_dir, f"{CAND_TAG}_seed{SEED}_목표재현율.zip")
        with zipfile.ZipFile(a.src) as zi, zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zo:
            for info in zi.infolist():
                if os.path.basename(info.filename) == "label_scheme.json":
                    zo.writestr(info.filename, json.dumps(new, ensure_ascii=False, indent=2))
                else:
                    with zi.open(info) as fi, zo.open(info.filename, "w", force_zip64=True) as fo:
                        shutil.copyfileobj(fi, fo, 1 << 20)
        print(f"[INFO] 넘길 모델 zip: {out_zip}")
        print(f"[INFO] 가중치 지문 (model.safetensors sha256 앞 12자 · D-178): {safetensors_sha12(out_zip)}")
    else:
        print("[INFO] --src 가 모델 zip 이 아니다 — label_scheme.json 만 냈다. 모델 폴더의 같은 파일을 이것으로 바꾼다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
