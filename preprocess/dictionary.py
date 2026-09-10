"""preprocess/dictionary.py — [P6] **금지 표현 사전** (D-155 · D-156).

  uv run python -m preprocess.dictionary            # 무엇이 들어가는지 본다
  uv run python -m preprocess.dictionary --dump     # data/derived/banned_terms.jsonl

──────────────────────────────────────────────────────────────
★ **사전의 항목은 사람이 고르지 않는다 — 조문이 고른다.**

    사례집   식약처가 「제8조제1항제N호」로 묶어 준 인용표현      (D-158)
    의결서   공정위가 「제3조제1항제N호」로 판단한 광고 문구      (ftc_extract)

🚨 **항목 수는 정규화 기준으로 센다** (D-117 — 매칭은 정규화문, 보관은 원문).
   사례집 원문 250종은 정규화하면 234종이다 — 「탈모 예방」/「탈모예방」이 접힌다.
   ⛔ 250 으로 사전을 만들면 16개가 중복이다.

──────────────────────────────────────────────────────────────
🔴 **이 사전만으로 판정하면 틀린다** (D-156)

    위반 「기억력 개선」  ⊂  적법 「기억력 개선에 도움을 줄 수 있음」
    위반 「체지방 감소」  ⊂  적법 「체지방 감소에 도움을 줄 수 있음」

**차이는 완곡 표현과 그 제품이 인정을 받았는가다.** 그래서 승인 표현(2층)에 포함되는
항목에는 `적법중첩` 을 박고 **단독으로 위반 판정에 쓰지 못하게** 한다.
★ 이것이 사전을 약하게 만드는 것이 아니라 **정확히 어디까지 쓸 수 있는지**를 적는 것이다.

──────────────────────────────────────────────────────────────
🔴 **분할을 먼저 읽는다 — `train` 문서에서만 만든다** (2026-09-09 저녁).

  ⛔ 처음에 전량으로 만들었더니 **평가 문구가 그대로 사전에 들어갔다** —
     실측: 봉인된 평가 문구 118개 중 **118개**가 사전에 있었다.
     그 사전으로 매칭기를 재면 **외운 것을 맞힌다.** 지표가 아니라 착시다.
  🚨 그래서 `split_manifest.json` 이 없으면 **멈춘다.** 「없으면 전량으로」는
     조용히 누수로 돌아가는 길이다 (D-72 fail-closed).

🚨 **한 산출물이 셋에 쓰인다** — 그래서 이걸 먼저 만든다.

    ① 해설서의 뭉친 라벨을 자동으로 가른다 (D-151 · 실측 8%)
    ② **판정기 B** — 룰 기반 매칭. 인코더와 학습을 공유하지 않아 오류가 독립이다
       (기획문서 6-2 의 이질적 판정기 교차 · 상관 오류 방어)
    ③ 1차 스크리닝 — 문장 전에 어휘를 자른다
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import unicodedata

CASEBOOK = pathlib.Path("data/derived/mfds_casebook_labels.jsonl")
SPLIT = pathlib.Path("data/derived/golden/split_manifest.json")
FTC = pathlib.Path("data/derived/ftc_layer1_phrases.json")
HF = pathlib.Path("data/derived/mfds_hf_labels.jsonl")
OUT = pathlib.Path("data/derived/banned_terms.jsonl")

#: 사례집의 호 → 근거 조문. 🚨 사례집은 **식품표시광고법**이고 의결서는 **표시광고법**이다.
#:    같은 이름의 유형이라도 근거 법이 다르므로 사전에 조문을 함께 적는다.
CASEBOOK_ARTICLE = "식품표시광고법 제8조제1항제{호}호"
FTC_LAW = "표시광고법"

#: 🔴 이보다 짧으면 사전에 넣지 않는다. 2자 낱말은 아무 문장에나 걸린다 —
#:    실측에서 「변비」·「당뇨」는 유용했지만 1자 조각은 전부 오탐이었다.
MIN_TERM = 2


def norm(s: str) -> str:
    """매칭용 정규화. 🚨 **보관은 원문으로 한다** (D-117)."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(s)))


def _jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        raise FileNotFoundError(f"{p} 가 없다 — 먼저 그 원천의 추출기를 돌린다")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def approved_terms(train: set[str]) -> list[str]:
    """2층 **승인** 표현 — 인정받은 기능성 문구. 🚨 위반이 아니라 적법이다.

    🔴 **`train` 만 본다** (2026-09-10 · D-175).

      ⛔ 종전에는 HF **전량**을 읽었다. 봉인된 음성 평가 60행이 그 안에 있었고,
         그것이 **어떤 항목을 `적법중첩` 으로 낙인찍어 판정 규칙에서 뺄지**를 정했다.
         실측 — 봉인을 풀면 「적법 60행 오탐 **0.0%**」가 **5.0%(3행)** 가 된다.
         「항산화」·「키성장에도움」 2종이 봉인된 적법 문장에 걸려 빠져 있었다.
      🚨 D-174 의 문언(「봉인된 평가 문구가 사전에 **들어가면** 안 된다」)은 지켜졌었다 —
         이 2종은 사전의 `term` 이 아니라 **`신뢰도` 칸**에만 영향을 준다.
         **문언은 지키고 취지는 뚫린 자리다.** 사전 종수(536)가 안 변해서 아무도 못 봤다.
      ★ **비대칭이 원인이었다** — 위반 표현(term)만 봉인하고 적법 표현(중첩 판정 코퍼스)은
        전량으로 뒀다. 그 비대칭이 **정확히 Precision 쪽으로 유리하게** 기운다.

    ★ 문구를 여기서 다시 자르지 않는다 — `split.approved_docs()` 를 그대로 쓴다 (D-99).
      같은 규칙이 두 벌이면 한쪽만 고쳐져 조용히 갈린다.
    """
    from preprocess.split import approved_docs  # noqa: PLC0415 — 모듈 최상단이면 순환 import

    return [q for d in approved_docs() if d["doc_id"] in train for q in d["문구"]]


def assign_map() -> dict[str, str]:
    """`doc_id` → `train`/`test_sentence`. 🔴 없으면 멈춘다 — 조용히 전량으로 가지 않는다."""
    if not SPLIT.exists():
        raise FileNotFoundError(
            f"{SPLIT} 가 없다 — **분할이 먼저다** (D-171).\n"
            "  먼저: uv run python -m preprocess.split --write\n"
            "  🚨 전량으로 사전을 만들면 평가 문구가 사전에 들어가 매칭기가 외운 것을 맞힌다."
        )
    from preprocess import split as _split  # noqa: PLC0415 — 모듈 최상단이면 순환 import

    m = json.loads(SPLIT.read_text(encoding="utf-8"))
    _split.verify_inputs(m, who="사전[P6]")  # 🔴 D-176 — 분할이 본 입력과 같은가
    return dict(m["assign"])


def train_only() -> set[str]:
    """`train` 으로 배정된 `doc_id` 들."""
    return {k for k, v in assign_map().items() if v == "train"}


def _add(entries: dict, n: str, raw: str, types: set[str], arts: set[str], src: str) -> None:
    e = entries.setdefault(n, {"term": n, "원문": [], "유형": set(), "근거": set(), "출처": set()})
    e["원문"].append(raw)
    e["유형"] |= types
    e["근거"] |= arts
    e["출처"].add(src)


def build() -> tuple[list[dict], dict]:
    """사전 항목들과 계측. 🚨 **항목은 조문이 고른다 — 여기서 판단하지 않는다.**

    🔴 **`train` 문서만 본다.** 평가로 봉인된 문구가 들어가면 매칭기가 외운 것을 맞힌다.
    """
    entries: dict[str, dict] = {}
    stat: dict = {
        "사례집": 0,
        "의결서": 0,
        "충돌": collections.Counter(),
        # 🚨 둘을 **가른다** (D-160 — 무엇을 세는지 먼저 적는다).
        #    ⛔ 종전에는 한 칸이라 「봉인 133개」로 읽혔는데, 실측 봉인은 83 이고
        #       나머지 50 은 `확정유형`·`인용표현` 이 없어 **애초에 못 쓰던 행**이다.
        "봉인제외": 0,
        "미배정": 0,
    }
    assign = assign_map()
    train = {k for k, v in assign.items() if v == "train"}

    for i, r in enumerate(_jsonl(CASEBOOK)):
        # 🔴 사례집은 **사전 쪽**이라 분할에서 전량 train 이다 (D-155 · split.py:206).
        #    여기서 빠지는 것은 봉인된 것이 아니라 라벨·인용이 없어 분할에 안 오른 행이다.
        did = f"casebook:{r.get('쪽')}:{i}"
        if did not in train:
            stat["봉인제외" if did in assign else "미배정"] += 1
            continue
        types = set(r.get("확정유형") or [])
        if not types:
            continue
        ho = r.get("호")
        hos = ho if isinstance(ho, list) else ([ho] if ho else [])
        art = {CASEBOOK_ARTICLE.format(호=h) for h in hos} or {"식품표시광고법 제8조제1항"}
        for q in r.get("인용표현") or []:
            n = norm(q)
            if len(n) < MIN_TERM:
                continue
            _add(entries, n, str(q), types, art, "mfds_casebook")
            stat["사례집"] += 1

    for r in json.loads(FTC.read_text(encoding="utf-8")):
        units = r.get("유형") or []
        if not units:
            continue
        did = f"ftc:{r['seq']}"
        if did not in train:
            stat["봉인제외" if did in assign else "미배정"] += 1
            continue
        types = {u["label"] for u in units}
        arts = {f"{FTC_LAW} {u['article']}" for u in units}
        for q in r.get("문구") or []:
            n = norm(q)
            if len(n) < MIN_TERM:
                continue
            _add(entries, n, str(q), types, arts, "ftc_decisions_body")
            stat["의결서"] += 1

    # 🔴 D-156 — 승인 문장에 그대로 들어 있는 항목을 표시한다
    approved = [norm(x) for x in approved_terms(train)]
    rows: list[dict] = []
    for n, e in sorted(entries.items()):
        types = sorted(e["유형"])
        overlap = [a for a in approved if n in a]
        if len(types) > 1:
            stat["충돌"][tuple(types)] += 1
        rows.append(
            {
                "term": n,
                "원문": sorted(set(e["원문"]))[:5],
                "유형": types,
                "근거": sorted(e["근거"]),
                "출처": sorted(e["출처"]),
                # 🚨 신뢰도는 「얼마나 확실한가」가 아니라 **「단독으로 써도 되는가」**다.
                "신뢰도": ("적법중첩" if overlap else ("모호" if len(types) > 1 else "단일")),
                "적법예시": sorted({a for a in overlap})[:2],
                # 🔴 단독 판정 자격 — 정확매칭만 「위험도 하한」이 된다 (수집전처리_기획 4-9)
                "단독판정": not overlap and len(types) == 1,
            }
        )
    return rows, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="[P6] 금지 표현 사전 (D-155 · D-156)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()

    rows, stat = build()
    print(f"사전 항목 **{len(rows):,}종** (정규화 기준 · D-117)")
    print(f"  들어온 인용 — 사례집 {stat['사례집']}회 · 의결서 {stat['의결서']}회")
    print(f"  🔴 평가로 **봉인돼 제외한 문서 {stat['봉인제외']}개** — 사전이 시험지를 외우지 않게")
    if stat["미배정"]:
        print(
            f"  ⬜ 라벨·인용이 없어 **애초에 못 쓰는 문서 {stat['미배정']}개**"
            " — 봉인과 다른 것이다 (D-160)"
        )

    by = collections.Counter(t for r in rows for t in r["유형"])
    print("\n  유형별 —")
    for k, v in by.most_common():
        print(f"    {v:>4}  {k}")

    conf = collections.Counter(r["신뢰도"] for r in rows)
    print(f"\n  신뢰도 — {dict(conf)}")
    solo = sum(1 for r in rows if r["단독판정"])
    print(f"  🔴 **단독 판정 자격이 있는 것 {solo}종** ({solo * 100 // len(rows)}%)")
    print("     나머지는 문맥이 필요하다 — 사전만으로는 못 푼다 (D-156).")

    lap = [r for r in rows if r["신뢰도"] == "적법중첩"]
    if lap:
        print(f"\n  🔴 **적법중첩 {len(lap)}종** — 승인 문장에 그대로 들어 있다")
        for r in lap[:6]:
            print(f"     위반 「{r['term']}」  ⊂  적법 「{r['적법예시'][0][:44]}」")
        print("     🚨 이 항목들은 **단독으로 위반 판정에 쓰지 않는다.**")

    if stat["충돌"]:
        print(f"\n  🚨 한 낱말이 여러 유형에 붙은 것 {sum(stat['충돌'].values())}종")
        for k, v in stat["충돌"].most_common(4):
            print(f"     {v:>3}  {' / '.join(k)}")
        print("     🚨 낱말이 라벨을 감당할 만큼 크지 않다는 뜻이다 (D-155).")

    lens = sorted(len(r["term"]) for r in rows)
    print(
        f"\n  길이 — 중앙 {lens[len(lens) // 2]}자 · 10자 이상 {sum(1 for x in lens if x >= 10)}종"
    )

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n  → {OUT}  ({len(rows):,}줄)")
    else:
        print(f"\n  ⬜ 쓰지 않았다 — `--dump` 를 붙이면 {OUT} 에 쓴다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
