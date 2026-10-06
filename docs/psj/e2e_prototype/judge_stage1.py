"""
판정 로직 1단계 — **신호 모음** (🔄 2026-10-06 main `ebb3f10` 맞춤판 · 박수진)

문장 하나에서 두 가지 재료를 모은다. 🔴 이 단계는 판정하지 않는다 — 판정은 2단계(`judge_stage2.py`)가 낸다.

  ① 금지 표현 사전   banned_terms.jsonl · `app/dictmatch.py`   → `DictScan`(단독판정 적중 `hits` · 자격 없는 적중 `weak`)
  ② 판정 인코더      KcBERT 확정 8종 + 편입 대기 1칸 · 유형별 τ  → 후보(τ 이상) · 여유 구간 · 사항 판별

🔄 2026-10-06 — 판정 그래프(main `ebb3f10`)에 맞춰 다시 짰다
  · 사전 적중은 **그래프와 같은 모양**(`app.graph.DictHit` · `DictScan`)으로 낸다. 단독판정 자격이 있는 항목은 `hits`,
    없는 항목(적법중첩 · 모호 · 비주장문맥)은 전부 `weak` 다 — DB 의 `exact_match` 와 같은 가름이다(D-311 · `scripts/load_db.dict_row`).
  · 그래서 종전의 신호 종류(approved_phrase · overlap · dict_weak)는 없앴다. 전제에 따라 갈리는 것은 2단계가
    `app/premise.py` 의 표로 낸다(D-319) — 승인 문구 정규식으로 따로 가르지 않는다.
  · 인코더는 **9칸**이다(D-321) — 확정 8종 + 편입 대기 `기능성화장품_오인`. 편입 대기 칸은 τ 가 1 초과라 후보로도 여유 구간으로도 내지 않는다.

계약 · 결정과 맞춘 것
  · 사전 매칭은 `app/dictmatch.py` 한 곳이다 — 정규화 · 부분문자열 규칙 · 원문 좌표가 판정 그래프와 같다 (D-99 · D-117).
  · 사전 · 모델 파일이 없으면 **멈춘다** (D-220). 빈 사전 · 대체 τ 로 진행하지 않는다.
  · 인코더 τ 는 모델 폴더의 `label_scheme.json`(dev 실측 · D-131)만 쓴다.
  · 「적법」이라는 말을 쓰지 않는다 (D-130). 신호가 없다는 것은 「신호 없음」일 뿐이다.

⬜ 팀장 판정 대기 (이 파일이 정하지 않는 것 — `[임의]` 값)
  · `QUIET_MARGIN` · `TRADE_CUE` · `CLAIM_CUE` · `NOTCLAIM_CUE` — 판정 파라미터 단일 출처(`app/settings.py` PARAMS · D-209)로 옮길지.
  · 사항 판별을 낱말로 할지 분류기로 할지 (D-272 개정 ⬜) · 「판정 대상 아님」을 누가 가리는지 (D-275 ⚠️ 재검 대기).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from app import dictmatch as dm  # noqa: E402 — 매칭 규칙은 한 곳 (D-117)
from app import graph as g  # noqa: E402 — 적중의 모양은 판정 그래프의 것을 쓴다 (D-99)
from app.contracts import Violation  # noqa: E402
from app.encoder import EncoderUnavailable, load_label_scheme  # noqa: E402 — 라벨 계약은 앱 로더의 것

BANNED_TERMS_PATH = os.path.join(REPO, "data", "derived", "banned_terms.jsonl")

#: `[임의]` 여유 구간 — 후보가 하나도 없어도 어느 유형의 확률이 τ × QUIET_MARGIN 이상이면 「조용하지 않다」로 보고 보류로 둔다.
#: τ 바로 아래의 문장이 「확정 · 위반 없음」으로 새지 않게 하는 장치다.
#: 🚨 0.5 는 09-30 의 6칸 모델(2차 골든)로 dev 에서 훑어 고른 값이다 — **3차 모델(9칸)로는 다시 훑지 않았다.**
#:    `run_judge_dist.py --margin-sweep` 으로 dev 에서 다시 본다. test 를 보고 고르지 않는다 (D-175).
QUIET_MARGIN = 0.5

# ══════════════════════════════════════════════════════════════════════
#  사항 판별 — 판정이 아니라 **인코더 점수를 어디에 쓸지** 가르는 표지 (`[임의]` 낱말 · 팀장 판정 대기)
# ══════════════════════════════════════════════════════════════════════
#: 근거 — D-272 개정 ② 「가격 · 할인율 · 비교 가격 · 환불 · 배송 등 거래 조건 … → 표시광고법이 주 근거」
#:        · 조건 ① 「사항이 거래 조건이면 표시광고법 노드로 반드시 보낸다」 → **not_claim 으로 내보내지 않는다**
#: `[임의]` 낱말 목록은 결정 문언의 예시에서 시작했다 · test 문장을 보고 늘리지 않는다(D-175)
TRADE_CUE = re.compile(
    r"가격|할인|정가|판매가|최저가|특가|세일|쿠폰|적립금|포인트\s*적립|환불|반품|교환|배송|도착|출고|경품|사은품|증정|"
    r"\d[\d,]*\s*원|만\s*원|1\+1|2\+1|협찬|광고비|대가를|유료\s*광고")
#: 주장 표지 — 효능 · 건강 목적 · 입증 필요 주장이 있으면 판정 대상이다 (D-286 ③)
CLAIM_CUE = re.compile(
    r"건강|효과|효능|개선|도움|예방|치료|완치|낫|완화|회복|면역|질환|질병|증상|환자|당뇨|혈압|혈당|콜레스테롤|비만|다이어트|체중|체지방|"
    r"피로|활력|기능성|성장|발달|두뇌|기억|수면|스트레스|관절|뼈|소화|변비|해독|디톡스|항산화|노화|피부|미용|의약|약효|"
    r"최초|최고|유일|1위|No\.?\s*1|넘버원|인증|특허|수상|입증|검증|임상|안심|안전|부작용|걱정\s*(없|끝)|무해|100\s*%|천연|무첨가|프리미엄|완벽|보장")
#: 판정 대상 아님 표지 — 섭취 대상만 · 사업자 정보 · 의무 표기 (D-275 계약 주석 · D-286 ③)
NOTCLAIM_CUE = re.compile(
    r"보관|소비기한|유통기한|제조일|내용량|원재료|원산지|영양\s*정보|열량|kcal|나트륨|분리배출|포장재질|"
    r"제조원|판매원|유통전문판매원|수입원|고객센터|소비자\s*상담|품목보고번호|식품유형|제조국|"
    r"섭취\s*(방법|량)|1일\s*\d+\s*회|\d+\s*회\s*\d+\s*(정|포|캡슐|g|ml|mL)|"
    r"(드세요|드십시오|섭취하십시오|섭취하세요|드시면 됩니다|드셔도\s*(좋아요|좋습니다|됩니다))\s*[.!]?$|"
    r"CFU|/\s*일\b|"
    r"주의\s*(하세요|하십시오|바랍니다|하시기 바랍니다)?\s*[.!]?$|과다\s*섭취|섭취에\s*주의|"
    r"분(들)?(께|에게)?\s*(추천|권)|(에게|께)\s*(알맞은|적합한|좋은)\s*(제품|구성)|(을|를)\s*위한\s*(제품|구성)|분\s*$")


def sentence_subject(text: str) -> tuple[str, Optional[re.Match]]:
    """주장 · 거래조건 · 혼합 · 판정대상아님. 🚨 판정이 아니다 — 2단계가 인코더 신호를 어떻게 쓸지만 바꾼다."""
    claim = CLAIM_CUE.search(text)
    trade = TRADE_CUE.search(text)
    if trade and claim:
        return "혼합", trade          # 사항마다 근거를 단다(D-272 개정 ③) — 인코더 신호는 그대로 쓴다
    if trade:
        return "거래조건", trade
    if not claim and NOTCLAIM_CUE.search(text):
        return "판정대상아님", None
    return "주장", None


MODEL_DIR_CANDIDATES = ("copylane-encoder-kcbert-final",)


# ══════════════════════════════════════════════════════════════════════
#  사전 — 파일(`banned_terms.jsonl`)을 DB 사전(`dict_entry`)과 **같은 규칙**으로 읽는다
# ══════════════════════════════════════════════════════════════════════
class DictBook:
    """banned_terms.jsonl → 단독판정 항목(`exact`) · 자격 없는 항목(`weak`).

    `scripts/load_db.dict_row` 와 같은 변환이다 — 근거(`근거`)가 인용 · 유형이 하나일 때만 `violation_type` · `단독판정` 이 자격(D-155 · D-178).
    판정 그래프는 DB 에서 `exact_match` 로 둘을 가른다(`graph.SQL_DICT` · `SQL_DICT_WEAK`). 여기는 같은 원천 파일을 읽는다.
    """

    def __init__(self, path: str = BANNED_TERMS_PATH) -> None:
        if not os.path.exists(path):
            raise SystemExit(f"🔴 금지 표현 사전이 없다: {path}\n"
                             "  `launcher.py data-setup` 으로 받는다. 빈 사전으로 진행하지 않는다 (D-220)")
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        if not rows:
            raise SystemExit(f"🔴 금지 표현 사전이 비었다: {path} (D-220)")
        self.path = path
        self.meta: dict[str, dict] = {r["term"]: r for r in rows}
        self.exact: list[dm.Entry] = []
        self.weak: list[dm.Entry] = []
        for r in rows:
            kinds = r.get("유형") or []
            e = dm.Entry(term=r["term"], violation_type=kinds[0] if len(kinds) == 1 else None,
                         basis=tuple(r.get("근거") or ()))
            (self.exact if r.get("단독판정") else self.weak).append(e)
        self.entries = self.exact + self.weak

    @staticmethod
    def _hits(text: str, entries: list[dm.Entry]) -> tuple[g.DictHit, ...]:
        # `graph.match_dict` 의 `_hits` 와 같다 — 항목 · 인용 · 원문 좌표
        return tuple(g.DictHit(term=m.entry.term, violation_type=m.entry.violation_type, basis=m.entry.basis, span=m.span)
                     for m in dm.find(text, entries))

    def scan(self, text: str, sid: str = "s0") -> g.DictScan:
        """문장 하나의 사전 훑기 — 그래프의 `DictScan` 그대로. `ran=True` 다(훑었다 · D-220)."""
        return g.DictScan(sent_id=sid, ran=True, hits=self._hits(text, self.exact), weak=self._hits(text, self.weak))


def load_banned_terms(path: str = BANNED_TERMS_PATH) -> DictBook:
    return DictBook(path)


# ══════════════════════════════════════════════════════════════════════
#  인코더
# ══════════════════════════════════════════════════════════════════════
def unzip_model(path: str) -> str:
    """모델 zip → **저장소 밖** `~/copylane_local/models/<zip 이름>/` 에 한 번만 푼다(이미 풀려 있으면 그대로 쓴다). 폴더면 그대로 돌려준다."""
    if not path.lower().endswith(".zip"):
        return path
    if not os.path.exists(path):
        raise SystemExit(f"🔴 모델 zip 이 없다: {path}")
    dest = os.path.join(os.path.expanduser("~"), "copylane_local", "models", os.path.splitext(os.path.basename(path))[0])
    if not os.path.exists(os.path.join(dest, "model.safetensors")):
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                base = os.path.basename(member)      # 폴더 구조는 버린다 — 파일 이름만 쓴다
                if base:
                    with z.open(member) as src, open(os.path.join(dest, base), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        print(f"[INFO] 모델 zip 을 풀었다(저장소 밖): {dest}")
    return dest


def resolve_model_dir(cli_arg: Optional[str] = None) -> str:
    """모델 폴더: --model > 환경변수 COPYLANE_MODEL_DIR > 이 폴더의 copylane-encoder-kcbert-final. zip 을 주면 저장소 밖에 풀어 쓴다.

    🚨 모델 폴더는 저장소에 커밋하지 않는다(.gitignore · 대용량) — 저장소 밖에 두고 --model 로 가리키는 것을 권한다.
    🚨 이 폴더의 `copylane-encoder-kcbert-final` 은 **2차(6칸) 모델**일 수 있다 — 3차 모델은 --model 로 가리킨다.
    """
    for cand in (cli_arg, os.environ.get("COPYLANE_MODEL_DIR")):
        if cand:
            cand = unzip_model(cand)
            path = cand if os.path.isabs(cand) else os.path.abspath(cand)
            if not os.path.exists(os.path.join(path, "label_scheme.json")):
                raise SystemExit(f"🔴 모델 폴더에 label_scheme.json 이 없다: {path}")
            return path
    for name in MODEL_DIR_CANDIDATES:
        path = os.path.join(HERE, name)
        if os.path.exists(os.path.join(path, "label_scheme.json")):
            return path
    raise SystemExit(f"🔴 모델 폴더가 없다 — --model 로 지정하거나 COPYLANE_MODEL_DIR 을 둔다 (후보: {MODEL_DIR_CANDIDATES})")


def load_scheme(model_dir: str) -> tuple[list[str], dict[str, float], dict]:
    """(label_list, thresholds, 원본 scheme) — **가중치는 읽지 않는다.** 라벨 계약은 앱 로더(`app.encoder.load_label_scheme`)로 확인한다.

    🔴 계약과 어긋나면 멈춘다 (D-220) — 계약에 없는 유형 · τ 빠짐 · `config.json` 의 칸 순서 불일치.
    """
    try:
        scheme = load_label_scheme(Path(model_dir))
    except EncoderUnavailable as e:
        raise SystemExit(f"🔴 {e} (D-54 · D-131 · D-220)") from e
    labels = [v.value for v in scheme.labels]
    thresholds = {v.value: t for v, t in scheme.thresholds.items()}
    cfg_path = os.path.join(model_dir, "config.json")
    if os.path.exists(cfg_path):          # 저장된 확률만 쓸 때는 config.json 이 없을 수 있다 — 있으면 대조한다
        with open(cfg_path, encoding="utf-8") as f:
            id2label = json.load(f).get("id2label") or {}
        if [id2label.get(str(i)) for i in range(len(labels))] != labels:
            raise SystemExit("🔴 config.json id2label 순서가 label_list 와 다르다 — 확률이 다른 유형에 붙는다 (D-220)")
    with open(os.path.join(model_dir, "label_scheme.json"), encoding="utf-8") as f:
        raw = json.load(f)
    return labels, thresholds, raw


def active_labels(thresholds: dict[str, float]) -> list[str]:
    """후보를 낼 수 있는 유형 — τ 가 1 이하인 것. 편입 대기 칸(τ 1.01 · D-321)은 빠진다."""
    return [label for label, t in thresholds.items() if 0 < t <= 1]


def load_encoder(model_dir: str):
    """(tokenizer, model, label_list, thresholds). 🔴 계약과 어긋나면 멈춘다 (D-220)."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    labels, thresholds, raw = load_scheme(model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    print(f"[INFO] 모델: {model_dir} · 실험: {raw.get('experiment', '?')} · golden {str(raw.get('golden_sha256', ''))[:8]}")
    print(f"[INFO] τ(dev 실측): {thresholds}")
    return tokenizer, model, labels, thresholds


def predict_label_probs(text: str, tokenizer, model, label_list: list[str]) -> dict[str, float]:
    return predict_label_probs_batch([text], tokenizer, model, label_list)[0]


def predict_label_probs_batch(texts: list[str], tokenizer, model, label_list: list[str],
                              batch_size: int = 32) -> list[dict[str, float]]:
    """동적 패딩 배치 — 문장마다 독립 계산이라 한 문장씩 넣은 결과와 같다. 학습과 같이 128 토큰에서 자른다."""
    import torch
    out = []
    for i in range(0, len(texts), batch_size):
        inputs = tokenizer(texts[i:i + batch_size], truncation=True, max_length=128, padding=True, return_tensors="pt")
        with torch.no_grad():
            probs = torch.sigmoid(model(**inputs).logits).numpy()
        out.extend({label: float(p) for label, p in zip(label_list, row)} for row in probs)
    return out


# ══════════════════════════════════════════════════════════════════════
#  1단계 — 신호 모음 (판정하지 않는다)
# ══════════════════════════════════════════════════════════════════════
def encoder_signal(text: str, label_probs: dict[str, float], thresholds: dict[str, float],
                   margin: float = QUIET_MARGIN) -> dict:
    """인코더가 낸 것 — 후보(τ 이상) · 여유 구간 · 사항 판별.

      candidates   확률 >= τ 인 유형 (D-131 「유형 후보 + 확신」). 편입 대기 칸은 내지 않는다
      near         후보가 없을 때, 확률이 τ × margin 이상으로 τ 에 가장 가까운 유형 하나 (없으면 None)
      quiet        후보도 여유 구간도 없다 — 인코더가 조용하다
      subject      주장 · 거래조건 · 혼합 · 판정대상아님
      active       이 모델이 후보를 낼 수 있는 유형 (τ ≤ 1) — 2단계가 「합의를 물을 수 있는 유형인가」를 이것으로 본다
    """
    act = active_labels(thresholds)
    unknown = set(act) - {v.value for v in Violation}
    if unknown:
        raise SystemExit(f"🔴 계약에 없는 유형이 τ 표에 있다: {unknown} (D-54)")
    cands = sorted(label for label in act if label_probs.get(label, 0.0) >= thresholds[label])
    near = None
    if not cands and margin < 1.0:
        ratio = {label: label_probs.get(label, 0.0) / thresholds[label] for label in act}
        top = max(ratio, key=ratio.get) if ratio else None
        if top is not None and ratio[top] >= margin:
            near = top
    subject, trade_m = sentence_subject(text)
    return {"candidates": cands, "near": near, "quiet": not cands and near is None,
            "subject": subject, "trade_term": trade_m.group(0) if trade_m else None, "active": sorted(act),
            "probs": {k: round(float(v), 4) for k, v in label_probs.items()}}


def stage1_signals(text: str, label_probs: dict[str, float], book: DictBook, thresholds: dict[str, float],
                   margin: float = QUIET_MARGIN) -> dict:
    """문장 하나의 신호 — `scan`(사전 · 그래프의 `DictScan`) · `enc`(인코더 · `encoder_signal`). 판정하지 않는다."""
    scan = book.scan(text)
    enc = encoder_signal(text, label_probs, thresholds, margin)
    return {"text": text, "scan": scan, "enc": enc, "subject": enc["subject"],
            "matched_terms_all": sorted({h.term for h in scan.hits} | {h.term for h in scan.weak})}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="1단계 신호 확인 — 판정은 judge_stage2.py")
    ap.add_argument("--model", default=None)
    ap.add_argument("texts", nargs="*")
    a = ap.parse_args()
    tok, mdl, labels, th = load_encoder(resolve_model_dir(a.model))
    book = load_banned_terms()
    print(f"[INFO] 사전 {len(book.entries)}건 (단독판정 {len(book.exact)} · 자격 없음 {len(book.weak)})\n")
    for t in a.texts or ["이 제품을 드시면 당뇨가 완치됩니다", "직사광선을 피해 서늘한 곳에 보관하십시오"]:
        s1 = stage1_signals(t, predict_label_probs(t, tok, mdl, labels), book, th)
        print(json.dumps({"text": t, "hits": [(h.term, list(h.basis)) for h in s1["scan"].hits],
                          "weak": [(h.term, list(h.basis)) for h in s1["scan"].weak], "enc": s1["enc"]}, ensure_ascii=False, indent=2))
