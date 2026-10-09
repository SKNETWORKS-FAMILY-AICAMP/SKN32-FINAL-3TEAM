"""실험 — 판정 인코더 v10 의 학습셋에 「적법 광고 문장」을 음성으로 더해 다시 학습한다 (2026-10-08 · ksr).

    uv run python docs/ksr/llm_copy/train_encoder_legit.py --probe      # 몇 스텝만 돌려 속도를 본다
    uv run python docs/ksr/llm_copy/train_encoder_legit.py              # 학습 → models/ 에 저장

무엇을 보려는가 — 평범한 판매 문구를 학습 음성에 넣으면 생성 문구의 과탐(10-08 실행 86%)이 얼마나 주는가.
인코더 학습은 박수진 · 소성민 담당이다. 이 파일은 **비교용 실험**이고 결과 모델은 채택 후보가 아니다.

설정은 박수진 v10 노트북(`origin/psj` · `copylane_encoder_finetune_v10_공통dev_합성_이유구역_20261007.ipynb`)의
기준 실행(합성O · 이유O)을 그대로 옮겼다 — dev 분리 · 학습 행 고르기 · 손실(focal + pos_weight) · 문턱 고르기.
다른 점은 셋이다: ① 학습 음성에 합성 정상 카피를 더한다 ② 시드 하나(42) ③ `datasets` · `Trainer` 없이 직접 돈다
(이 기기 `.venv` 에 없고 `uv.lock` 은 팀장 단독이다 · D-87). CPU 라 수치가 GPU 판과 조금 다를 수 있다.

🚨 test 행은 읽자마자 버린다 — 이 실험은 train(→ train · dev)만 본다 (D-175).
🚨 sLLM 학습 자료(`docs/lse/`)는 넣지 않는다 — 인코더 자료와 겹치면 안 된다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import pathlib
import random
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import torch
from sklearn.metrics import average_precision_score, f1_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "data/derived/golden/golden.jsonl"
LEGIT = ROOT / "docs/ksr/LLM_카피생성_정상카피_900_판독용_ksr_2026-10-06.csv"
#: 🆕 2026-10-08 — 사실 낱말(인증 · 수치 · 원산지)에 위반 요소를 더한 짝 문장. `--pairs` 는 **위반 100줄만** 양성으로 읽는다.
#:    같은 파일의 적법(사실 전제) 200줄은 `--facts` 를 줄 때만 음성으로 넣는다 — 🚨 골든셋이 같은 꼴을 조건 B · 거짓_과장으로
#:    둔다(라벨 규칙 판정 대기). `--facts` 판은 그 판정에 쓸 숫자를 보려는 것이다
PAIRS = ROOT / "docs/ksr/LLM_카피생성_사실진술_짝_300_판독용_ksr_2026-10-08.csv"
#: 🔴 2026-10-10 (D-325 결정 1 · 2) — 학습 음성으로 쓰는 것은 **사람이 검수한 행만**이다. 검수 전(판독 칸이 빈) 행 ·
#:    애매 표시 행은 학습 · 채점 어디에도 쓰지 않는다. 종전에는 900행을 판독 칸을 보지 않고 전부 넣었다(D-325 판정 전의 실험).
#:    `[임의]` 사람 판독 칸에서 「써도 된다」로 읽는 값 — 검수 기준의 낱말은 D-325 ⬜ 로 아직 정해지지 않았다. 정해지면 여기만 고친다
HUMAN_COL = "판독(사람)"
HUMAN_LEGIT = frozenset({"적법"})
V10_DIR = ROOT / "models" / "copylane-encoder-kcbert-v10-합성O-이유O"
OUT_DIR = ROOT / "models" / "copylane-encoder-kcbert-v10-ksr실험-적법900"

# ── v10 노트북과 같은 값 — 견주려면 바꾸지 않는다
MODEL_NAME = "beomi/kcbert-base"
SEED, MAX_EPOCHS, PATIENCE = 42, 6, 2
BATCH, LR, WARMUP, WEIGHT_DECAY, MAX_LEN = 32, 2e-5, 0.1, 0.01, 128
FOCAL_GAMMA, POS_WEIGHT_CAP = 1.5, 5
DEV_FRAC, DEV_SEED, TH_OFF = 0.15, 42, 1.01
DEV_EXPECT = (749, "4ebfcb231da703b5")  # 골든 529c970556d7 의 v11 dev (줄 수 · 지문)
TRAIN_EXPECT = 3964

SEL = [
    "질병_예방치료_표방",
    "건강기능식품_오인",
    "의약품_오인",
    "거짓_과장",
    "소비자_기만",
    "후기_체험기_기만",
]
CONF8 = [*SEL, "부당_비교광고", "비방광고"]
WAITING = ["기능성화장품_오인"]
LABEL_LIST = CONF8 + WAITING
LABEL2ID = {name: i for i, name in enumerate(LABEL_LIST)}
TH_GRID = np.arange(0.1, 0.9001, 0.025)


def norm_text(s: str) -> str:
    return " ".join(s.split())


def group_key(rid: str) -> str:
    return rid.split(":", 2)[2] if rid.startswith("inj:") else rid.split("#")[0]


def normalize(r: dict) -> dict:
    cond, labels = r.get("조건"), list(r.get("labels") or [])
    return {
        "id": r["id"],
        "group": group_key(r["id"]),
        "text": r["text"],
        "labels": labels,
        "target": []
        if cond in ("M", "D", "L")
        else labels,  # M · D · L 은 양성이 아니다 (D-296 개정 2)
        "split": r["split"],
        "provenance": r.get("provenance"),
        "origin": r.get("origin"),
        "zone": r.get("구역"),
        "cond": cond,
        "unit": r.get("unit"),
    }


def is_reason(r: dict) -> bool:
    return r["provenance"] == "ftc_decisions_body" and r["zone"] == "이유"


def dev_eligible(r: dict) -> bool:
    return r["unit"] == "문장" and r["origin"] != "injected"


def split_dev(train_all: list[dict]) -> tuple[list[dict], set[str]]:
    """v11 과 같은 dev — 원천별 묶음 15% + 6종 보충 · 시드 42. 노트북 코드를 그대로 옮겼다."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in train_all:
        groups[r["group"]].append(r)
    prov_groups: dict[str, list[str]] = defaultdict(list)
    for g in sorted(groups):
        elig = [r for r in groups[g] if dev_eligible(r)]
        if elig:
            prov_groups[Counter(r["provenance"] for r in elig).most_common(1)[0][0]].append(g)
    rng = random.Random(DEV_SEED)
    dev_groups: set[str] = set()
    for prov in sorted(prov_groups, key=lambda p: (p is None, p)):
        gs = prov_groups[prov][:]
        rng.shuffle(gs)
        dev_groups.update(gs[: max(1, math.ceil(DEV_FRAC * len(gs)))])

    def conf_pos(rows: list[dict], label: str) -> int:
        return sum(1 for r in rows if dev_eligible(r) and label in r["target"])

    rest = [g for g in sorted(groups) if g not in dev_groups]
    rng.shuffle(rest)
    for label in SEL:
        want = min(10, math.ceil(DEV_FRAC * conf_pos(train_all, label)))
        have = sum(conf_pos(groups[g], label) for g in dev_groups)
        for g in rest:
            if have >= want:
                break
            k = conf_pos(groups[g], label)
            if k and g not in dev_groups:
                dev_groups.add(g)
                have += k
    dev_rows = [r for g in sorted(dev_groups) for r in groups[g] if dev_eligible(r)]
    return dev_rows, dev_groups


def build_train(train_all: list[dict], dev_rows: list[dict], dev_groups: set[str]) -> list[dict]:
    dev_texts = {norm_text(r["text"]) for r in dev_rows}
    pool = [
        r
        for r in train_all
        if r["group"] not in dev_groups and norm_text(r["text"]) not in dev_texts
    ]
    pool = [r for r in pool if r["cond"] != "M"]
    pool = [r for r in pool if not (r["cond"] in ("C", "A", "B") and not r["labels"])]
    pool = [r for r in pool if r["unit"] != "낱말"]
    merged: dict[tuple, dict] = {}
    for r in pool:  # 같은 문구 병합 — 라벨 합집합
        k = (norm_text(r["text"]), is_reason(r))
        if k in merged:
            merged[k]["target"] = sorted(set(merged[k]["target"]) | set(r["target"]))
        else:
            merged[k] = dict(r, target=list(r["target"]))
    return list(merged.values())


def multihot(labels: list[str]) -> np.ndarray:
    v = np.zeros(len(LABEL_LIST), dtype=np.float32)
    for name in labels:
        v[LABEL2ID[name]] = 1.0
    return v


def macro_prauc(y: np.ndarray, p: np.ndarray, n: int = len(SEL)) -> float:
    v = [
        float(average_precision_score(y[:, i], p[:, i]))
        for i in range(n)
        if 0 < y[:, i].sum() < len(y)
    ]
    return float(np.mean(v)) if v else float("nan")


def pick_thresholds(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    th = {}
    for i, name in enumerate(CONF8):
        if y[:, i].sum() < 10:
            th[name] = 0.5
            continue
        fs = [f1_score(y[:, i], p[:, i] >= t, zero_division=0) for t in TH_GRID]
        th[name] = float(round(TH_GRID[int(np.argmax(fs))], 3))
    th[WAITING[0]] = TH_OFF
    return th


def predict(model, tok, texts: list[str], bs: int = 64) -> np.ndarray:  # noqa: ANN001
    model.eval()
    out = []
    for s in range(0, len(texts), bs):
        enc = tok(
            texts[s : s + bs],
            truncation=True,
            max_length=MAX_LEN,
            padding=True,
            return_tensors="pt",
        )
        enc = enc.to(next(model.parameters()).device)
        with torch.inference_mode():
            out.append(torch.sigmoid(model(**enc).logits.float()).cpu().numpy())
    return np.concatenate(out)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="12 스텝만 돌려 속도를 본다")
    ap.add_argument(
        "--no-legit",
        action="store_true",
        help="적법 문장을 더하지 않는다 — 이 기기에서 v10 을 다시 만든 기준선",
    )
    ap.add_argument(
        "--pairs",
        action="store_true",
        help="짝 위반 100줄을 양성으로 더한다 (조건부 줄은 수정안 문구로 바뀐다)",
    )
    ap.add_argument(
        "--facts",
        action="store_true",
        help="짝의 사실 문장 200줄(인증 · 수치 · 원산지)도 음성으로 더한다 — `--pairs` 와 함께",
    )
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help="시드 — v10 은 42 · 43 · 44 를 돌려 가장 좋은 것을 골랐다",
    )
    args = ap.parse_args()
    torch.set_num_threads(args.threads)

    sha = hashlib.sha256(GOLDEN.read_bytes()).hexdigest()
    rows = [normalize(json.loads(line)) for line in GOLDEN.open(encoding="utf-8") if line.strip()]
    train_all = [r for r in rows if r["split"] == "train"]
    print(f"골든 {len(rows):,}행 · sha {sha[:12]} · train {len(train_all):,}")
    del rows  # 🔴 여기서부터 test 행은 메모리에도 없다

    dev_rows, dev_groups = split_dev(train_all)
    dev_sha = hashlib.sha256("|".join(sorted(r["id"] for r in dev_rows)).encode()).hexdigest()[:16]
    train_rows = build_train(train_all, dev_rows, dev_groups)
    same = (len(dev_rows), dev_sha) == DEV_EXPECT and len(train_rows) == TRAIN_EXPECT
    print(
        f"dev {len(dev_rows)}줄 · 지문 {dev_sha} · 학습 {len(train_rows):,}행 — "
        + (
            "✅ v10 노트북과 같다"
            if same
            else f"🔴 v10 과 다르다(기대 dev {DEV_EXPECT} · 학습 {TRAIN_EXPECT})"
        )
    )
    if not same and not args.probe:
        return 1

    if args.facts and not args.pairs:
        ap.error("--facts 는 --pairs 와 함께 준다")
    if args.pairs:
        # 🔴 짝 문장의 정답은 `판독(보조)` · `위반유형(보조)` — 모델이 붙인 라벨이다. 모델이 붙인 정답으로 학습하지 않는다
        #    (D-325 결정 1). 사람 판독 칸이 선 뒤에 이 길을 다시 연다. ⛔ 파일(`PAIRS`)도 저장소에 없다 — 없으면 여기서 멈춘다
        raise SystemExit(
            "🔴 --pairs 는 닫혀 있다 — 짝 문장의 정답이 모델 보조 판독이다 (D-325 결정 1). "
            + ("" if PAIRS.exists() else f"파일도 없다: {PAIRS.name}")
        )
    legit, pairs, facts = [], [], []
    if not args.no_legit:
        dev_texts = {norm_text(r["text"]) for r in dev_rows}
        seen = {norm_text(r["text"]) for r in train_rows}
        with LEGIT.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if HUMAN_COL not in (reader.fieldnames or []):
                raise SystemExit(f"🔴 {LEGIT.name} 에 「{HUMAN_COL}」 칸이 없다 — 검수 여부를 알 수 없다 (D-325)")
            skipped: Counter[str] = Counter()
            for row in reader:
                human = (row[HUMAN_COL] or "").strip()
                if not human:
                    skipped["검수 전"] += 1
                    continue
                if (row.get("애매표시") or "").strip():
                    skipped["애매 표시"] += 1
                    continue
                if human not in HUMAN_LEGIT:
                    skipped[f"판독 「{human}」"] += 1
                    continue
                # 🆕 조건부로 읽힌 줄은 원문 대신 수정안을 쓴다 (`--pairs` 일 때만 — 종전 실행과 견줄 수 있게)
                text = (row.get("수정안(보조)") or row["text"]) if args.pairs else row["text"]
                t = norm_text(text)
                if t not in dev_texts and t not in seen:
                    seen.add(t)
                    legit.append({"id": f"ksr-legit:{row['id']}", "text": text, "target": []})
        print(
            f"더한 적법 문장 {len(legit)}행 (합성 정상 카피 · 사람 검수 · 음성) · 뺀 것 {dict(skipped)}"
        )
        if not legit:
            # 없음이 「기준선과 같은 학습」으로 조용히 넘어가지 않게 한다 (D-220) — 기준선은 `--no-legit` 로 따로 돈다
            raise SystemExit(
                "🔴 사람이 검수한 적법 행이 0 이다 — 학습하지 않는다 (D-325 결정 2). "
                f"「{HUMAN_COL}」 칸을 채운 뒤 다시 돌린다"
            )
        if args.pairs:
            with PAIRS.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    t = norm_text(row["text"])
                    if t in dev_texts or t in seen:
                        continue
                    if row["판독(보조)"] == "위반":
                        seen.add(t)
                        pairs.append(
                            {
                                "id": f"ksr-pair:{row['id']}",
                                "text": row["text"],
                                "target": row["위반유형(보조)"].split(),
                            }
                        )
                    elif args.facts:
                        seen.add(t)
                        facts.append(
                            {"id": f"ksr-fact:{row['id']}", "text": row["text"], "target": []}
                        )
            print(
                f"더한 짝 위반 문장 {len(pairs)}행 (양성) · 유형 "
                + str(dict(Counter(n for r in pairs for n in r["target"])))
            )
            if facts:
                print(f"더한 사실 문장 {len(facts)}행 (인증 · 수치 · 원산지 · 음성)")
    train = train_rows + legit + pairs + facts
    y_train = np.stack([multihot(r["target"]) for r in train])
    pos = y_train.sum(0)
    pw = np.clip(np.sqrt((len(y_train) - pos) / np.clip(pos, 1e-6, None)), 1, POS_WEIGHT_CAP)
    print(
        f"학습 {len(train):,}행 · 음성 {int((y_train.sum(1) == 0).sum()):,} · pos_weight "
        + str({name: round(float(pw[i]), 2) for i, name in enumerate(LABEL_LIST)})
    )

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=len(LABEL_LIST),
        problem_type="multi_label_classification",
        id2label=dict(enumerate(LABEL_LIST)),
        label2id=LABEL2ID,
    )
    no_decay = ("bias", "LayerNorm.weight")
    params = [
        {
            "params": [p for n, p in model.named_parameters() if not any(k in n for k in no_decay)],
            "weight_decay": WEIGHT_DECAY,
        },
        {
            "params": [p for n, p in model.named_parameters() if any(k in n for k in no_decay)],
            "weight_decay": 0.0,
        },
    ]
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # GPU 가 있으면 쓴다(코랩)
    model.to(dev)
    print("장치:", torch.cuda.get_device_name(0) if dev.type == "cuda" else "CPU")
    opt = torch.optim.AdamW(params, lr=LR)
    steps_per_epoch = math.ceil(len(train) / BATCH)
    total = steps_per_epoch * MAX_EPOCHS
    sched = get_linear_schedule_with_warmup(opt, int(WARMUP * total), total)
    pw_t = torch.tensor(pw, dtype=torch.float32, device=dev)
    y_dev = np.stack([multihot(r["target"]) for r in dev_rows]).astype(int)
    dev_texts_list = [r["text"] for r in dev_rows]
    enc_all = tok([r["text"] for r in train], truncation=True, max_length=MAX_LEN)
    y_t = torch.tensor(y_train)

    best, best_state, bad, t0, step = -1.0, None, 0, time.time(), 0
    gen = torch.Generator().manual_seed(args.seed)
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        order = torch.randperm(len(train), generator=gen).tolist()
        for s in range(0, len(order), BATCH):
            idx = order[s : s + BATCH]
            batch = tok.pad(
                {
                    "input_ids": [enc_all["input_ids"][i] for i in idx],
                    "attention_mask": [enc_all["attention_mask"][i] for i in idx],
                },
                return_tensors="pt",
            ).to(dev)
            labels = y_t[idx].to(dev)
            logits = model(**batch).logits.float()
            bce = torch.nn.functional.binary_cross_entropy_with_logits(
                logits, labels, reduction="none"
            )
            p = torch.sigmoid(logits)
            p_t = p * labels + (1 - p) * (1 - labels)
            loss = ((pw_t * labels + (1 - labels)) * (1 - p_t) ** FOCAL_GAMMA * bce).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            step += 1
            if step % 20 == 0 or (args.probe and step % 4 == 0):
                el = time.time() - t0
                print(
                    f"  에폭 {epoch} · 스텝 {step}/{total} · 손실 {loss.item():.4f} · {el / step:.1f}초/스텝 · 남은 시간 약 {(total - step) * el / step / 60:.0f}분"
                )
            if args.probe and step >= 12:
                return 0
        p_dev = predict(model, tok, dev_texts_list)
        score = macro_prauc(y_dev, p_dev)
        print(
            f"에폭 {epoch} 끝 — dev 6종 macro PR-AUC {score:.4f} · 지난 시간 {(time.time() - t0) / 60:.0f}분"
        )
        if score > best:
            best, bad = score, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_epoch, best_p = epoch, p_dev
        else:
            bad += 1
            if bad >= PATIENCE:
                print("개선이 없어 멈춘다")
                break

    model.load_state_dict(best_state)
    th = pick_thresholds(y_dev, best_p)
    out = OUT_DIR.with_name(OUT_DIR.name.replace("적법900", "기준선")) if args.no_legit else OUT_DIR
    if pairs:
        out = out.with_name(f"{out.name}-짝100" + ("-사실200" if facts else ""))
    if args.seed != SEED:
        out = out.with_name(f"{out.name}-s{args.seed}")
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    v10 = json.loads((V10_DIR / "label_scheme.json").read_text("utf-8"))
    scheme = {
        "label_list": LABEL_LIST,
        "label_thresholds": th,
        "confirmed_labels": CONF8,
        "waiting_labels": WAITING,
        "backbone": MODEL_NAME,
        "notebook": "ksr 실험 — v10 기준 실행의 설정에 적법 문장을 음성으로 더했다 (채택 후보 아님)",
        "experiment": out.name,
        "seed": args.seed,
        "best_epoch": best_epoch,
        "golden_sha256": sha,
        "train_rows": len(train),
        "train_legit_rows": len(legit),
        "train_pair_rows": len(pairs),
        "train_fact_rows": len(facts),
        "dev_rows": len(dev_rows),
        "dev_sha": dev_sha,
        "dev_macro_prauc6": best,
        "v10_dev_macro_prauc6_seed42": v10.get("dev_macro_prauc6_by_seed", {}).get("42"),
        "v10_thresholds": v10["label_thresholds"],
        "threshold_note": "dev F1 최대 · 격자 0.1~0.9(0.025) · dev 양성 10건 미만이면 0.5 — v10 과 같은 규칙. dev 에는 적법 광고 문장이 없다",
        "final_test": False,
        "test_note": "이 실험은 test 를 채점하지 않는다 (D-175)",
    }
    (out / "label_scheme.json").write_text(
        json.dumps(scheme, ensure_ascii=False, indent=2), "utf-8"
    )
    np.save(out / "dev_probs.npy", best_p)
    print(
        f"저장 — {out} · 가장 좋은 에폭 {best_epoch} · dev PR-AUC {best:.4f} (v10 시드 42: {scheme['v10_dev_macro_prauc6_seed42']})"
    )
    print("문턱:", th)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
