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

from app.dictmatch import norm as _norm
from collect import registry, statute

CASEBOOK = pathlib.Path("data/derived/mfds_casebook_labels.jsonl")
SPLIT = pathlib.Path("data/derived/golden/split_manifest.json")
FTC = pathlib.Path("data/derived/ftc_layer1_phrases.json")
HF = pathlib.Path("data/derived/mfds_hf_labels.jsonl")
OUT = pathlib.Path("data/derived/banned_terms.jsonl")

#: 🔄 2026-09-24 (D-282) — 근거는 `collect.statute.cite` 꼴의 **조문 인용**이고 유형은 거기서 계산한다.
#:    🚨 사례집은 **식품표시광고법**이고 의결서는 **표시광고법**이다 — 같은 이름의 유형이라도 근거 법이 다르다.
#:    ⛔ 종전에는 한국어 근거 문자열(「식품표시광고법 제8조제1항제{호}호」)을 여기서 따로 만들었고, 유형과 근거를 **각각**
#:       집합으로 합쳐 어느 근거가 어느 유형인지 짝이 사라졌다. 이제 `짝` 칸이 그 짝을 든다.

#: 🔴 이보다 짧으면 사전에 넣지 않는다. 2자 낱말은 아무 문장에나 걸린다 —
#:    실측에서 「변비」·「당뇨」는 유용했지만 1자 조각은 전부 오탐이었다.
MIN_TERM = 2


#: 🔄 2026-09-28 — 정규화는 `app/dictmatch.py` 한 곳이다 (D-99). ⛔ 종전에는 여기와 `scripts/eval_rule.py` 에 같은 글자로 있었다.
#:    `preprocess.golden` 이 이 이름으로 부르므로 이름을 남긴다.
norm = _norm


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


def caution_terms(train: set[str]) -> list[str]:
    """정본 축 **섭취 주의사항** — 주장이 아닌 문장. 🆕 2026-10-02 (D-311 · D-156 확장).

    ★ 왜 — 단독판정 심사(`단독판정`)가 승인 문장 하나와만 대조했다. 그래서 규제기관이 쓴 주의사항
      (「고혈압 치료제 등 복용 시 전문가와 상담할 것」 · 「당뇨병의 치료 및 예방에 사용될 수 없음」)에 든
      질병 · 약 이름이 단독으로 위반을 확정했다(원장 10-02 ⑤ — 학습 D 반반 교차 50 → 5 · 골든 밖 관측 축 18/274 → 2).
    🔴 **`train` 만 본다** — `approved_terms` 와 같은 이유다(09-10 사고 · `tests/test_dictionary_leak.py`).
       지금은 주의사항이 전량 train 이지만, 분할이 바뀌는 날 봉인 문장이 사전 설계를 고르지 않게 인자로 받는다.
    🔴 **정본 축만** — `split.caution_docs()`(I-0050 개별인정 · 게시판)를 그대로 쓴다 (D-99 · D-185).
       ⛔ I-0040 업체 신고(`hf_display_claims.jsonl` · 관측 축)는 재료가 아니다 — 표시 문구가 섞인 관측값이고
          봉인 승인 문장을 품은 문단이 85 개였다(원장 10-02 ⑤). 그쪽은 **시험**에만 쓴다.
    """
    from preprocess.split import caution_docs  # noqa: PLC0415 — 모듈 최상단이면 순환 import

    return [q for d in caution_docs() if d["doc_id"] in train for q in d["문구"]]


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


def _add(entries: dict, n: str, raw: str, basis: list[str], src: str) -> None:
    """🔄 D-282 — 근거(조문 인용)만 받는다. 유형은 인용에서 계산하고 **(유형, 근거) 짝**을 남긴다."""
    e = entries.setdefault(
        n, {"term": n, "원문": [], "유형": set(), "근거": set(), "짝": set(), "출처": set()}
    )
    e["원문"].append(raw)
    for c in basis:
        t = statute.type_of(c)
        e["근거"].add(c)
        if t:
            e["유형"].add(t)
            e["짝"].add((t, c))
    e["출처"].add(src)


def confidence(overlap: list[str], types: list[str], nonclaim: list[str]) -> str:
    """항목 하나의 `신뢰도` — **단독판정은 `단일` 뿐이다**. 🆕 2026-10-02 (D-311).

    🔴 값은 하나다 — 적법중첩(지위에 따라 적법 · D-156) > 모호(여러 유형 · D-155) > 비주장문맥(주장 아닌 자리에 쓰인다) > 단일.
    ⛔ 비주장문맥을 「적법중첩」 이름에 담지 않는다 — 박수진 시제품 1단계가 적법중첩을 `overlap`(품목 전제 분기)으로 읽어
       식품 전제에서 위반으로 돌린다(원장 10-02 ⑤). 주의사항의 질병 이름은 지위 문제가 아니다.
    """
    if overlap:
        return "적법중첩"
    if len(types) > 1:
        return "모호"
    return "비주장문맥" if nonclaim else "단일"


def build() -> tuple[list[dict], dict]:
    """사전 항목들과 계측. 🚨 **항목은 조문이 고른다 — 여기서 판단하지 않는다.**

    🔴 **`train` 문서만 본다.** 평가로 봉인된 문구가 들어가면 매칭기가 외운 것을 맞힌다.
    """
    from preprocess.split import (  # noqa: PLC0415 — 모듈 최상단이면 순환 import
        casebook_basis,
        casebook_not_ad,
        ho_of,
    )

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
        # 🔄 D-282 — 분할과 **같은 함수**로 인용을 만든다(D-99). 5호는 이제 들어온다(호 단위 `소비자_기만` · 다목 `후기`).
        basis = casebook_basis(r)
        if not statute.types_of(basis):
            continue
        for q in r.get("인용표현") or []:
            # 🆕 2026-09-30 (판정 J4) — 분할과 **같은 함수**로 광고 표현이 아닌 인용을 뺀다(D-99).
            #    ⛔ 빼지 않으면 원료명(「글루타치온」)이 5호 단독판정 항목이 된다
            if casebook_not_ad(str(q), r):
                stat["사례집_비광고"] = stat.get("사례집_비광고", 0) + 1
                continue
            n = norm(q)
            if len(n) < MIN_TERM:
                continue
            _add(entries, n, str(q), basis, "mfds_casebook")
            stat["사례집"] += 1

    for r in json.loads(FTC.read_text(encoding="utf-8")):
        units = r.get("유형") or []
        if not units:
            continue
        did = f"ftc:{r['seq']}"
        if did not in train:
            stat["봉인제외" if did in assign else "미배정"] += 1
            continue
        basis = sorted({statute.fair(ho_of(u["article"])) for u in units})
        for q in r.get("문구") or []:
            n = norm(q)
            if len(n) < MIN_TERM:
                continue
            _add(entries, n, str(q), basis, "ftc_decisions_body")
            stat["의결서"] += 1

    # 🔴 D-156 — 승인 문장에 그대로 들어 있는 항목을 표시한다
    #    🔄 2026-09-30 (판정 J1) — 승인 문구는 이제 조건 A(지위에 달림)다. `적법중첩` 은 「지위에 따라 적법일 수 있는 문장 안의 항목」으로
    #       읽는다 — 단독으로 위반을 내지 않는 동작은 그대로 맞다(분기는 전제가 가른다 · D-263)
    approved = [norm(x) for x in approved_terms(train)]
    # 🆕 2026-10-02 (D-311) — 주장이 아닌 정본 문장(섭취 주의사항)에 그대로 나오는 항목도 단독으로 확정하지 못한다
    caution = [norm(x) for x in caution_terms(train)]
    rows: list[dict] = []
    for n, e in sorted(entries.items()):
        types = sorted(e["유형"])
        overlap = [a for a in approved if n in a]
        nonclaim = [c for c in caution if n in c]
        if len(types) > 1:
            stat["충돌"][tuple(types)] += 1
        conf = confidence(overlap, types, nonclaim)
        rows.append(
            {
                "term": n,
                "원문": sorted(set(e["원문"]))[:5],
                "유형": types,
                "근거": sorted(e["근거"]),
                # 🆕 D-282 — 어느 근거가 어느 유형인지. 판정기 B 의 호 단위 채점이 읽는다
                "짝": sorted([t, c] for t, c in e["짝"]),
                "출처": sorted(e["출처"]),
                # 🚨 신뢰도는 「얼마나 확실한가」가 아니라 **「단독으로 써도 되는가」**다.
                "신뢰도": conf,
                "적법예시": sorted({a for a in overlap})[:2],
                # 🆕 D-311 — 단독판정을 잃은 근거 문장(사람이 본다 · 판정 재료가 아니다)
                "비주장예시": sorted(set(nonclaim))[:2] if conf == "비주장문맥" else [],
                # 🔴 단독 판정 자격 — 정확매칭만 「위험도 하한」이 된다 (수집전처리_기획 4-9)
                # 🔄 2026-10-02 (D-311) — 비주장문맥도 자격이 없다
                "단독판정": conf == "단일",
            }
        )
    return rows, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="[P6] 금지 표현 사전 (D-155 · D-156)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    a = ap.parse_args()

    rows, stat = build()
    print(f"사전 항목 **{len(rows):,}종** (정규화 기준 · D-117)")
    print(
        f"  들어온 인용 — 사례집 {stat['사례집']}회 · 의결서 {stat['의결서']}회"
        f" · 사례집 비광고 인용 뺌 {stat.get('사례집_비광고', 0)} (판정 J4)"
    )
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

    nc = [r for r in rows if r["신뢰도"] == "비주장문맥"]
    print(
        f"\n  🆕 **비주장문맥 {len(nc)}종** — 정본 섭취 주의사항(train)에 그대로 나온다 · 단독으로 확정하지 않는다 (D-311)"
    )
    # 🔴 목록을 늘 찍는다 — 분할 · 주의사항 원천이 바뀌면 이 목록이 **조용히** 바뀐다. 원장에 판마다 적는다 (D-149)
    print("     " + " · ".join(r["term"] for r in nc))

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

    # 🔴 변경금지(ND) 게이트 — 파생 데이터셋에 ND 소스의 행이 들어오면 여기서 멈춘다 (2026-09-25 · `registry.assert_derivable`)
    registry.assert_derivable(rows, who="preprocess.dictionary")
    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n  → {OUT}  ({len(rows):,}줄)")
    else:
        print(f"\n  ⬜ 쓰지 않았다 — `--dump` 를 붙이면 {OUT} 에 쓴다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
