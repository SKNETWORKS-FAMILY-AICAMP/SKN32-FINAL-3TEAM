"""preprocess/split.py — 골든셋 분할 [P12] · 🚨 **출처 분리** (D-15 · D-40).

  uv run python -m preprocess.split --dry-run   # 무엇이 어디로 가는지만 본다
  uv run python -m preprocess.split --write     # split_manifest.json 을 쓴다
  uv run python -m preprocess.split --write --allow-shrink   # 🚨 봉인이 줄어드는 것을 **보고** 받아들일 때만

──────────────────────────────────────────────────────────────
★ **라벨의 출처는 셋이고, 이 파일은 ① 만 다룬다** (2026-09-09)

    ① 조문   감독기관이 법으로 붙였다 — 사례집(D-158) · 공정위 의결서
    ② 구성   규칙이 곧 라벨 — 결함 주입 [P10]. 🚨 test 에 넣지 않는다
    ③ 판단   사람 또는 모델 — 뭉친 라벨을 가르는 자리에만

🔴 **평가셋은 ① 로만 만든다.** 시험지를 시험 대상이 만들면 안 된다.

──────────────────────────────────────────────────────────────
🚨 **왜 `ftc` 를 갈라야 하는가**

레지스트리에서 `ftc_decisions_body` 는 `U1: allow` 라 **학습 원천**이고,
`mfds_casebook`·`mfds_press` 는 `U1: deny` 다.

🔄 **그 `deny` 를 「평가 전용」으로 읽지 않는다 (D-155).** 용도 축(U1~U4)에 **「평가」가
   없어서** 평가 전용 원천이 `U1: deny` 로 표기된 것이고, 그 표기가 실제로 사람을
   여러 번 속였다 — D-155 가 *「실제로 나를 한 번 속였다」* 고 적어 두었다.
🚨 **사례집은 D-155 로 성격이 바뀌었다 — 평가 홀드아웃이 아니라 「금지 표현 사전」이다.**
   아래 실측이 그 근거이고, `plan()` 의 `train = … + term` 이 그 판정을 집행한다.

그런데 평가 전용 원천만으로는 축이 안 선다 — 실측 (2026-09-09) —

                          casebook(낱말)   ftc(문장)
    질병_예방치료_표방            41            0
    의약품_오인                 38            0
    건강기능식품_오인             32            0
    거짓_과장                   32          168
    소비자_기만                   0           40   ← ftc 에만 있다
    후기_체험기_기만               0            0   🔴
    부당_비교광고                 0            2   🔴
    비방광고                     0            1   🔴

**`소비자_기만` 은 `ftc` 없이는 0 이다.** 그래서 `ftc` 의 일부를 **문서 단위로 봉인**해
학습에서 빼고 평가로 돌린다. 무작위 분할이 아니라 `seq`(의결서 번호) 단위다 —
같은 의결서의 문구가 train 과 eval 에 섞이면 F1 이 부풀려진다 ([P12] 규칙 1).

⛔ **같은 기관이라는 한계는 남는다.** `ftc` 평가 슬라이스는 학습과 **같은 원천**이라
「다른 기관에서도 되는가」를 재지 못한다. 그래서 산출에 `same_source: true` 를 박고
**두 지표를 나란히 보고한다** — 감추는 것이 아니라 적는 것이 이 설계의 값이다.

🚨 **30 미만 유형은 `unmeasurable` 에 적는다** (D-40). 「측정 불가」를 말할 수 있게
만드는 것은 슬라이드가 아니라 이 JSON 한 줄이다.

──────────────────────────────────────────────────────────────
🔄 **2026-09-09 저녁 — 네 자리를 고쳤다.** 물질화 직전 검토에서 나왔다.

  ① 🔴 **낱말과 문장을 한 시험지에 넣지 않는다.**
     사례집 인용표현은 중앙 **4자**, `ftc` 문구는 중앙 **12자**다. 한 숫자로 보고하면
     **두 과제를 평균한 수**가 된다.
     ⛔ 그래서 D-171 의 「5/8 이 섰다」는 **단위를 섞은 수였다** — 문장 단위로는 2/8 이다.
        D-155·D-172 가 경고한 바로 그 혼동을 그 D 를 쓰면서 다시 밟았다.

     🔴 **그리고 사례집은 시험지가 아니라 사전이다** (D-155). 낱말 시험지를 따로
        만들려고 사례집을 갈라 봤는데, **어느 쪽으로 갈라도 한쪽이 D-40 을 못 넘긴다** —

            질병 41 → 사전 20 / 평가 21      의약품 38 → 19 / 19
            건기식 32 → 16 / 16              거짓과장 32 → 16 / 16

        데이터의 한계다. **D-155 가 이미 「사례집 = 금지 표현 사전」으로 정했으므로
        그 결정을 따른다** — 사례집은 `train`(사전) 쪽이고, 낱말 시험지는 만들지 않는다.
        🚨 그 결과 **8종 중 6종이 어느 단위로도 평가 데이터가 없다.** 이것이
           열린 항목 A 의 실제 크기이고, 오늘 그것이 작아진 것이 아니라 **정확해졌다.**

  ② 🔴 **다중 라벨 문서는 평가에 넣지 않는다.**
     의결서가 제1호·제2호를 함께 걸면, 인용된 문구 각각이 **어느 호인지는 안 적혀 있다.**
     문서 라벨을 문구에 전파하면 그 잡음이 시험지에 들어간다 (실측 44문서 · 문구 103개).
     학습에서는 견디지만 평가에서는 못 견딘다 — **잡음은 train 으로 보낸다.**

  ③ 🔴 **적법(음성) 표본을 평가에 넣는다.**
     종전 시험지는 전부 위반이었다 — **「전부 위반」이라 답해도 Recall 100%** 다.
     2층 승인 문구 일부를 봉인해 음성으로 쓴다. 없으면 Precision 이 정의되지 않는다.
     🔄 2026-09-30 (판정 J1 (가)) — 승인 문구는 **조건 A 의 3호 양성**으로 옮겼다(「인정 제품」 전제에서만 적법 · D-263 ①).
        평가 음성은 이제 조건 L 문구(결정문 무혐의 · 보도자료 · 화장품 · 판독 뒤 해설서 수정문구)다 — 그때까지 특이도는 「음성 부족」.

  ④ 🔴 **분할이 사전·주입보다 먼저다.**
     종전 순서(사전 → 주입 → 분할)에서는 사전이 **평가 문구로 만들어졌다** —
     실측: 봉인된 평가 문구 118개 중 **118개가 사전에 그대로** 있었다.
     그 사전으로 매칭기를 재면 외운 것을 맞힌다. 이제 사전과 주입이 이 파일을 읽는다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import random
import re

from app.settings import PARAMS
from collect import statute

FTC_PHRASES = pathlib.Path("data/derived/ftc_layer1_phrases.json")
CASEBOOK = pathlib.Path("data/derived/mfds_casebook_labels.jsonl")
HF = pathlib.Path("data/derived/mfds_hf_labels.jsonl")
#: 🆕 2026-09-30 (판정 J1 (가-2′) · 원장 09-30 ⑫) — 개별인정형 원료 대장 I-0050(`mfds_hf_individual` · 정본 축 · D-185).
#:    섭취 주의사항(인정 조건문)만 읽는다. 🚨 I-0040(`mfds_hf_ingredient` · 업체 신고 · 관측 축)이 아니다 — 그쪽은 `hf_display_claims.jsonl`
HF_API = pathlib.Path("data/derived/hf_api_labels.jsonl")
OUT = pathlib.Path("data/derived/golden/split_manifest.json")
SPLIT_NAME = OUT.as_posix()

#: 🚨 유형별 평가 목표. D-40 의 30 이 **하한**이고, 신뢰구간을 감안해 40 을 목표로 둔다.
#:    40건에서 Recall 0.85 면 95% CI 가 ±11%p 다 (기획문서 6-3) — 30 은 아슬아슬하다.
EVAL_TARGET = 40
MIN_MEASURABLE = PARAMS.min_measurable  # D-40

#: 승인 문구 평가 봉인 수. 🔄 2026-09-30 (판정 J1 (가) · (가-2′)) — **음성이 아니다.** 조건 A(지위에 달림)의 3호 양성이다.
#:    ⛔ 종전에는 「음성(적법) 표본 목표」였다 — 승인 문구를 「인정받은 제품」 전제로 적법에 두었는데, 게이트는 가장 보수적인
#:       전제(인정 없음)로 잰다(D-263 ①) · 해설서 판독은 같은 꼴(「…에 도움을 주는」)을 3호 C · A 로 읽었다(원장 09-30 ⑫).
#:    ★ 이름을 안 바꾼 것은 봉인 추첨(`rnd_neg`)이 이 수에 매여 있어서다 — 60 이 그대로여야 시험지가 그대로다.
#:    🚨 평가 음성은 이제 **조건 L 행**이다(결정문 무혐의 · 보도자료 · 화장품 · 판독 뒤 해설서 수정문구) — `plan()` 의 `negatives`.
NEG_TARGET = 60


def _jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        raise FileNotFoundError(f"{p} 가 없다 — 먼저 그 원천의 추출기를 돌린다")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


#: 🔴 분할이 읽는 입력 전부. 이 셋이 1바이트라도 다르면 뒤의 수가 전부 달라진다.
#: 🔄 2026-09-24 (D-283) — **사람이 붙인 8유형 라벨(`labels/*.jsonl`)은 더 이상 입력이 아니다.**
#:    ⛔ 09-17 부터 넷째 입력이었다(D-243). 그 라벨은 라벨링 지시서의 자체 8유형으로 붙인 것이라 조문 근거가 없고
#:       (지시서 6·7번이 법 제8조①6·7호와 반대 · 5호의 목 11개가 한 줄) 사람끼리 일치가 α 0.32 였다.
#:    ★ 평가 라벨은 조문이 붙이거나(D-171 ①) 조문 원문을 기준으로 사람이 붙인다 — 해설서 행의 호는 아직 없다(D-283 ⬜).
INPUTS = (FTC_PHRASES, CASEBOOK, HF, HF_API)  # 🆕 09-30 HF_API — 인정 조건문(판정 J1 (가-2′))


def inputs() -> tuple[pathlib.Path, ...]:
    """🔄 2026-09-25 (D-285 개정 4) — 해설서 채택본은 **평가에 들어갈 때만** 입력이다(`guide_state()` 의 대기 0).

    ★ 대기 중에는 분할이 채택본을 안 보므로 지문에 넣지 않는다 — 넣으면 분할 결과는 그대로인데 봉인 파일이 바뀐다.
    🚨 대기가 0 이 되는 순간 입력이 늘어 `verify_inputs` 가 멈춘다 → 분할을 다시 쓴다(한 번). 그것이 전환이다.
    """
    st = guide_state()
    got = INPUTS + ((GUIDE_ADOPTED,) if st and not st["대기"] else ())
    # 🆕 2026-09-30 (D-285 개정 5) — 화장품 질의응답집도 같은 규칙이다(대기 0 일 때만 입력)
    cq = cosmetic_state()
    got += (COSMETIC_ADOPTED,) if cq and not cq["대기"] else ()
    # 🆕 2026-09-30 (동결 전 판정 ⑤-1·3 (나)) — 공정위 보도자료 1997~2007 도 같은 규칙
    fp = ftc_press_state()
    return got + ((FTC_PRESS_ADOPTED,) if fp and not fp["대기"] else ())


def fingerprint() -> dict[str, dict]:
    """입력 파일들의 **지문**. 🚨 재현의 근거는 seed 가 아니라 이것이다 (D-176).

    ⛔ 실측 사고 (2026-09-10). 클론 B 는 「주입 902 · 골든셋 1,910」을 원장에 적었는데
       같은 커밋·같은 seed 로 이 기기에서 돌리면 **908 · 1,915** 가 나왔다.
       원인은 코드도 seed 도 아니고 **`mfds_hf_labels.jsonl` 의 승인문구가 178 vs 177**,
       문구 **한 건** 차이였다. 그 한 건이 `V0 118→117` 로 전파돼 7 배로 벌어진다.
       🚨 `data/**` 는 커밋되지 않으므로(D-19) **입력은 git 이 못 지킨다.**
    ★ 그래서 산출물이 자기 입력의 sha256 을 들고 다니고, 뒤 단계가 대조한다.
      「같은 커밋이면 같은 결과」는 이 프로젝트에서 참이 아니다.
    """
    got: dict[str, dict] = {}
    for f in inputs():
        b = f.read_bytes() if f.exists() else b""
        got[f.as_posix()] = {
            "sha256": hashlib.sha256(b).hexdigest() if b else None,
            "bytes": len(b),
        }
    return got


def verify_inputs(manifest: dict, *, who: str) -> None:
    """분할이 본 입력과 **지금 입력**이 같은지 대조한다. 다르면 멈춘다 (D-176 · D-72).

    🚨 fail-closed 다. 「다르면 경고하고 계속」은 조용히 갈린 산출물을 만드는 길이고,
       그 갈림은 **지표로는 안 보인다** — 실측에서 177/178 두 배치의 P·R·F1 이
       소수점 셋째 자리까지 같았다.
    """
    want = manifest.get("inputs")
    if not want:
        raise SystemExit(
            f"🔴 {SPLIT_NAME} 에 `inputs` 지문이 없다 — 낡은 분할이다.\n"
            "  먼저: uv run python -m preprocess.split --write"
        )
    now = fingerprint()
    bad = [k for k, v in want.items() if now.get(k, {}).get("sha256") != v.get("sha256")]
    # 🔄 2026-09-21 (전수 재검토 I12) — ⛔ 분할이 본 파일만 대조해, 분할 **뒤에 새로 생긴** 라벨 파일은 통과했다.
    #    새 파일이 판정 레코드를 들고 오면 봉인된 test 문서의 라벨이 **id 는 그대로인 채** 바뀌었다(실측 재현).
    #    ★ 지금 입력에 있는데 분할이 못 본 것(내용이 있는 것)도 다름이다.
    bad += sorted(k for k, v in now.items() if k not in want and v.get("sha256"))
    if bad:
        lines = "\n".join(
            f"    {k}\n      분할이 본 것 {want.get(k, {}).get('sha256')!s:.12}… ({want.get(k, {}).get('bytes', 0):,} B)"
            f"\n      지금 있는 것 {now.get(k, {}).get('sha256')!s:.12}…"
            f" ({now.get(k, {}).get('bytes', 0):,} B)"
            for k in bad
        )
        raise SystemExit(
            f"🔴 **{who} 의 입력이 분할이 본 것과 다르다** — {len(bad)}개 (D-176)\n"
            f"{lines}\n"
            "  🚨 이대로 진행하면 분할과 어긋난 산출물이 나오고, **지표로는 안 보인다.**\n"
            "  → 분할을 다시 돌린다: uv run python launcher.py golden --write"
        )


def ftc_docs() -> list[dict]:
    """공정위 의결서 — **문서 하나가 한 줄**. 조문에서 읽은 유형이 붙어 있다."""
    if not FTC_PHRASES.exists():
        raise FileNotFoundError(
            f"{FTC_PHRASES} 가 없다 —\n  먼저: uv run python -m preprocess.ftc_extract --stage --dump"
        )
    got = []
    for r in json.loads(FTC_PHRASES.read_text(encoding="utf-8")):
        # 🆕 2026-09-24 (D-282) — **근거 조문이 정본이다.** 유형은 인용에서 계산하고, 추출기가 적은 유형과 대조한다.
        #    ⛔ 종전에는 유형만 넘기고 `article` 을 여기서 버렸다 — 골든셋 6,741행 중 조문 칸이 있는 행이 0 이었다.
        units = r.get("유형") or []
        basis = sorted({statute.cite(*statute.FAIR, ho_of(u["article"])) for u in units})
        labels = statute.types_of(basis)
        if labels != sorted({u["label"] for u in units}):
            raise SystemExit(
                f"🔴 ftc:{r['seq']} — 추출기의 유형 {sorted({u['label'] for u in units})} 과 "
                f"조문에서 계산한 유형 {labels} 이 다르다 (D-282 · D-99). `ftc_extract.TYPES` 를 본다."
            )
        # 🔄 **2026-09-17 — 「이유」 문구를 들고 나온다** (D-232 (A) · D-234).
        #    ⛔ 종전 조건은 `not r.get("문구")` 라 **주문에 문구가 없으면 문서를 통째로 버렸다.**
        #       그래서 이유만 있는 **502건이 train 에도 못 들어갔다** — 회수를 켜도 여기서 막혔다.
        #    🔴 **둘을 따로 들고 나간다.** 봉인(평가)은 주문 문구만 보고, 학습에만 이유가 들어간다
        #       — 평가 라벨은 조문이나 사람이 붙여야 한다 (D-172).
        order = [str(x) for x in (r.get("문구") or [])]
        reason = [str(x) for x in (r.get("문구_이유") or [])]
        # 🆕 2026-09-30 (D-237) — 원천이 **위반 아님**이라 한 문구. 유형이 없는 문서(16095 · 무혐의 주문)도 이것으로 선다
        order_ok = [str(x) for x in (r.get("문구_적법") or [])]
        reason_ok = [str(x) for x in (r.get("문구_이유_적법") or [])]
        if not (labels and (order or reason)) and not (order_ok or reason_ok):
            continue
        got.append(
            {
                "doc_id": f"ftc:{r['seq']}",
                "원천": "ftc_decisions_body",
                "근거": basis,
                "유형": labels,
                "문구": order if labels else [],
                "문구_이유": reason if labels else [],  # 🆕 학습 전용 — 봉인 대상이 아니다
                "문구_적법": order_ok,  # 🆕 조건 L — `golden` 이 적법 행으로 낸다
                "문구_이유_적법": reason_ok,
                "단위": "문장",
            }
        )
    return got


def casebook_docs() -> list[dict]:
    """사례집 — 🔄 **「금지 표현 사전」이다 (D-155).**

    ⛔ 종전 이 줄은 *「`U1: deny` 라 통째로 평가다」* 였다. **D-155 가 성격을 바꾸기 전
       서술**이고, 같은 파일 `plan()` 의 `train = … + term` 과 정반대를 말하고 있었다 — 한 파일이
       두 말을 하면 읽는 사람은 머리말을 믿는다.
    🔴 **낱말**(서로 다른 문구 237 · 평균 5.3자)이라 문장 시험지와 섞지 않는다.
    """
    got = []
    for i, r in enumerate(_jsonl(CASEBOOK)):
        # 🔄 2026-09-24 (D-282) — 원천이 적은 **호와 [별표 1] 목**으로 인용을 만들고 유형은 거기서 계산한다.
        #    ⛔ 종전에는 추출기의 `확정유형` 을 읽었고, 5호는 「뭉친 호」라 비어 있어 **5호 사례 25건(인용 36문구)이 통째로 빠졌다**(D-158).
        #    ★ 5호는 호 단위로 `소비자_기만` 이고, 원천이 「5-다」(체험기) 목을 적었으면 `후기_체험기_기만` 이다 (D-282 · D-255 ① 개정).
        basis = casebook_basis(r)
        labels = statute.types_of(basis)
        if not labels or not r.get("인용표현"):
            continue
        # 🆕 2026-09-30 (판정 J4) — 광고 표현이 아닌 인용은 뺀다(원천은 그대로 · 빼는 이유는 `casebook_not_ad`)
        quotes = [str(x) for x in r["인용표현"] if not casebook_not_ad(str(x), r)]
        if not quotes:
            continue
        got.append(
            {
                "doc_id": f"casebook:{r.get('쪽')}:{i}",
                "원천": "mfds_casebook",
                "근거": basis,
                "유형": labels,
                "문구": quotes,
                "단위": "낱말",
            }
        )
    return got


#: 「‘글루타치온’의 효능·효과 표방」 — 인용이 **원료 이름**이다. 위반은 원료 효능을 제품 효능처럼 쓴 것이지 이름이 아니다
_CASEBOOK_INGREDIENT = re.compile(
    r"^[‘'][^’']+[’'](?:\s*,\s*[‘'][^’']+[’'])*\s*의\s*효능·효과\s*표방"
)


def casebook_not_ad(quote: str, rec: dict) -> str | None:
    """사례집 인용이 **광고 표현이 아닌** 이유. 광고 표현이면 `None` (2026-09-30 · 판정 J4 · 원장 09-30 ⑦).

    ★ 원천의 문장 꼴로만 가린다 — 이름 모양으로 추측하지 않는다.
      · 원료명 — 「‘X’의 효능·효과 표방」(45 · 46쪽 12개)
      · 체험기 주제어 — 글에 「체험기」가 있고 인용이 네 글자 이하(「다이어트」 「코로나」 · 47 · 48쪽 9개)
      · 사진 설명 — 「… 전·후 사진」
      · 한 글자 의약품 어휘 — 「집중력 높이는 ‘약’」의 「약」(2호). 🚨 1호 「암」은 남긴다 — 원천이 질병명으로 적었다
    🚨 `[임의]` 규칙이다 — 판독 없이 원천 꼴로 가른 것이라, 사례집 판이 바뀌면 다시 본다.
    """
    text = rec.get("글") or rec.get("문구") or ""
    core = quote.replace(" ", "")
    if re.search(r"사진|이미지", quote):
        return "사진 설명"
    # 🔄 09-30 (원장 ⑭) — 「특허출원원료」는 원료 이름이 아니라 **특허 주장**이다(D-228 「특허 ≠ 실증」) — 원료명으로 빼지 않는다
    if _CASEBOOK_INGREDIENT.search(text) and not re.search(r"특허|인증|수상|임상", quote):
        return "원료명"
    if "체험기" in text and len(core) <= 4:
        return "체험기 주제어"
    if len(core) < 2 and rec.get("호") in (2, [2]):
        return "한 글자 의약품 어휘"
    return None


def ho_of(article: str) -> int:
    """「제3조제1항제2호」 → 2. 🔴 못 읽으면 멈춘다 — 조용히 버리지 않는다 (D-220)."""
    import re  # noqa: PLC0415

    m = re.search(r"제(\d+)호", article)
    if not m:
        raise SystemExit(f"🔴 조문 호를 못 읽는다: {article!r}")
    return int(m.group(1))


def casebook_basis(r: dict) -> list[str]:
    """사례집 행 → 식품표시광고법 §8① 인용 목록. 🆕 2026-09-24 (D-282).

    ★ 원천이 적은 것만 옮긴다 — `호`(정수 또는 목록)와 `별표목`(「5-다」 꼴).
       목은 **같은 호의 목이 하나뿐일 때만** 붙인다. 둘 이상이면 어느 문구가 어느 목인지 원천이 안 적었다 — 호까지만.
    """
    ho = r.get("호")
    hos = ho if isinstance(ho, list) else ([ho] if ho else [])
    moks: dict[int, list[str]] = collections.defaultdict(list)
    for x in r.get("별표목") or []:
        a, _, b = str(x).partition("-")
        if a.isdigit() and b:
            moks[int(a)].append(b)
    got = set()
    for h in hos:
        m = moks.get(int(h)) or []
        got.add(statute.food(int(h), m[0] if len(set(m)) == 1 else None))
    return sorted(got)


#: 🆕 2026-09-25 (D-285 개정 4) — 해설서 조문·조건 판의 산출물. 🚨 경로의 정본은 `scripts/guide_statute_round.py`
#:    `READINGS` · `ADOPTED` 다 — 바꾸면 양쪽을 같이 (D-99). `preprocess` 가 `scripts` 를 부르지 않으려고 여기 한 번 더 적는다
GUIDE_READINGS = pathlib.Path("data/derived/labels/guide_statute/readings.jsonl")
GUIDE_ADOPTED = pathlib.Path("data/derived/labels/guide_statute/adopted.jsonl")


def guide_state() -> dict[str, int] | None:
    """해설서 행의 상태 — `{"전체", "채택", "대기"}`. 판독 원자료가 없으면 `None`(이 기기는 모른다 · 0 이 아니다).

    🔴 대기 = 원자료에 있는데 채택본에 없는 행(판정 시트 · 거래 조건 사항). 채택본에 원자료에 없는 행이 있으면 멈춘다.
    """
    return _round_state(GUIDE_READINGS, GUIDE_ADOPTED, "rebuild")


def _round_state(readings: pathlib.Path, adopted: pathlib.Path, cmd: str) -> dict[str, int] | None:
    """🆕 2026-09-30 (D-99) — 판독 판 하나의 상태. 해설서 · 화장품이 같은 함수를 쓴다(대기 규칙이 둘로 갈리지 않게)."""
    if not readings.exists():
        return None
    if not adopted.exists():
        raise FileNotFoundError(
            f"{adopted} 가 없다 — 먼저: uv run python -m scripts.guide_statute_round {cmd}"
        )
    every = {r["지문"] for r in _jsonl(readings)}
    took = {r["지문"] for r in _jsonl(adopted)}
    if took - every:
        raise ValueError(
            f"{adopted.parent.name} 채택본에 원자료에 없는 행 {len(took - every)} — 채택본이 낡았다 ({cmd})"
        )
    return {"전체": len(every), "채택": len(took), "대기": len(every - took)}


#: 🆕 2026-09-30 (D-285 개정 5) — 화장품 질의응답집 조문·조건 판의 산출물. 🚨 경로의 정본은
#:    `scripts/guide_statute_round.py` `CQ_READINGS` · `CQ_ADOPTED` 다 — 바꾸면 양쪽을 같이 (D-99 · 위 GUIDE_* 와 같은 이유)
COSMETIC_READINGS = pathlib.Path("data/derived/labels/cosmetic_qa/readings.jsonl")
COSMETIC_ADOPTED = pathlib.Path("data/derived/labels/cosmetic_qa/adopted.jsonl")


def cosmetic_state() -> dict[str, int] | None:
    """화장품 질의응답집 행의 상태 — 해설서와 같은 규칙. 🔴 `대상 N` 행은 채택본에 있으므로 대기가 아니다."""
    return _round_state(COSMETIC_READINGS, COSMETIC_ADOPTED, "cq-rebuild")


def cosmetic_docs() -> list[dict]:
    """화장품 질의응답집의 평가 라벨 — **대기가 0 일 때만** 낸다(해설서 `guide_docs` 와 같은 규칙 · D-285 개정 5).

    ★ 전량 평가다(2026-09-30 팀장 판정 ⑤-4 (나) — 2025 판은 평가 전용 · 학습은 2012 · FAQ 2020). 그래서 문항 단위 분할
      (지시서 §7)은 저절로 지켜진다 — 한 문항의 문구가 학습 · 평가로 갈리지 않는다.
    🔴 `대상 N`(광고 표현이 아님) 행은 평가에 안 넣는다 — 수는 `cosmetic_state()` 와 채택본이 들고 있다.
    🔴 조건 `L` 행은 유형이 비고 **적법**이다(`golden.is_negative`) · M · D 는 적법이 아니다(해설서와 같다).
    """
    return _round_docs(cosmetic_state(), COSMETIC_ADOPTED, "mfds_cosmetic_ad_qa")


#: 🆕 2026-09-30 (동결 전 판정 ⑤-1·3 (나)) — 공정위 보도자료 1997~2007 문구 판. 🚨 경로의 정본은
#:    `scripts/guide_statute_round.py` `FP_READINGS` · `FP_ADOPTED` 다 — 바꾸면 양쪽을 같이 (D-99)
FTC_PRESS_READINGS = pathlib.Path("data/derived/labels/ftc_press_old/readings.jsonl")
#: 🆕 분할 입력이 될 수 있는 `labels/` 아래 판 — 조문·조건 판(독립 판독 · 팀장 판정)만. 사람 8유형 라벨은 아니다 (D-283)
ROUND_LABEL_DIRS = ("labels/guide_statute/", "labels/cosmetic_qa/", "labels/ftc_press_old/")
FTC_PRESS_ADOPTED = pathlib.Path("data/derived/labels/ftc_press_old/adopted.jsonl")


def ftc_press_state() -> dict[str, int] | None:
    """보도자료 문구 판의 상태 — 해설서 · 화장품과 같은 규칙."""
    return _round_state(FTC_PRESS_READINGS, FTC_PRESS_ADOPTED, "fp-rebuild")


def ftc_press_docs() -> list[dict]:
    """공정위 보도자료 1997~2007 의 평가 라벨 — 전량 평가 · **대기가 0 일 때만**(화장품과 같다).

    ★ 결정문(`ftc_decisions_body`)의 비교 · 비방 사건은 2008 년 이후만 있다 — 이 범위는 학습과 사건이 겹치지 않는다
      (원장 09-30 ④). 문구가 학습과 겹치면 `golden` 의 문구 단위 거름이 평가 쪽을 뺀다.
    """
    return _round_docs(ftc_press_state(), FTC_PRESS_ADOPTED, "ftc_press")


def _round_docs(st: dict[str, int] | None, adopted: pathlib.Path, source: str) -> list[dict]:
    """문구 판 채택본 → 분할 문서(행 하나 = 문서 하나). 🔴 대기가 남으면 빈 목록 · 대상 N 은 뺀다 (D-99 — 두 판이 같은 함수)."""
    if not st or st["대기"]:
        return []
    return [
        {
            "doc_id": r["지문"],
            "원천": source,
            "유형": r["labels"],
            "근거": r["근거"],
            "근거_후보": r["근거_후보"],
            "조건": r["조건"],
            "판독": r["판독"],
            "원천결손": r["원천결손"],
            "별표5목": r["별표5목"],
            "문구": [r["문구"]],
            "단위": "문장",
        }
        for r in _jsonl(adopted)
        if r["대상"] == "Y"
    ]


def guide_docs() -> list[dict]:
    """해설서 행의 평가 라벨 — 🔄 2026-09-25 (D-285 개정 4) **대기가 0 일 때만** 채택본에서 낸다.

    ⛔ 09-17(D-243)부터 여기로 **사람이 붙인 8유형 라벨**이 들어왔고 D-283 이 뺐다 — 조문 근거가 없었다.
    ★ 지금 원천은 해설서 조문·조건 판(D-285)이다 — 독립 판독 둘의 합의 · 팀장 판정. 행마다 `조건` 이 있다.
    🔴 **대기 행이 하나라도 있으면 빈 목록이다** — 가장 어려운 행(판정 시트)이 빠진 평가셋을 만들지 않고,
       평가셋이 두 번 바뀌지 않게 한다(D-285 「판정 시트가 끝난 뒤」). 기다리는 수는 `guide_state()` 가 낸다.
    🔴 **`유형` 이 빈 행이 적법이라는 뜻이 아니다** — `조건` M · D 행과 `근거_후보` 행은 유형이 비어 있다.
       읽는 쪽(`golden` · `eval_rule` · `load_db`)이 `조건` 을 먼저 본다 (지시서 §7 선행 게이트).
    """
    st = guide_state()
    if not st or st["대기"]:
        return []
    return [
        {
            "doc_id": r["지문"],
            "원천": "mfds_special_use_guide",
            "유형": r["labels"],
            "근거": r["근거"],
            "근거_후보": r["근거_후보"],
            "조건": r["조건"],
            "판독": r["판독"],
            "원천결손": r["원천결손"],
            "문구": [r["문구"]],
            "단위": "문장",
        }
        for r in _jsonl(GUIDE_ADOPTED)
    ]


GUIDE = pathlib.Path("data/derived/mfds_guide_labels.jsonl")


def pending_guide() -> dict[str, int]:
    """호가 정해지길 기다리는 해설서 **위반문구** 수 — 원천 3분류별. 🚨 없는 파일은 0 이 아니라 None 으로 보인다."""
    if not GUIDE.exists():
        return {}
    st = guide_state()
    if st and not st["대기"]:
        return {}  # 🔄 D-285 개정 4 — 전환된 뒤에는 기다리는 행이 없다 (대기 중에는 종전 값 그대로 — 봉인 파일이 안 바뀐다)
    c: collections.Counter = collections.Counter()
    for r in _jsonl(GUIDE):
        if r.get("종류") == "위반문구":
            c[str(r.get("원천라벨"))] += 1
    return dict(c)


#: 🆕 2026-09-30 (판정 J1 (가)) — 승인 문구의 조건 · 근거. 식품표시광고법 제8조제1항제3호(건강기능식품이 아닌 것을 건강기능식품으로 인식)
#:    ★ 조건 A — 인정받은 건강기능식품이거나 일반식품 기능성 표시 요건(고시 「부당한 표시 또는 광고로 보지 아니하는 식품등의
#:      기능성 표시 또는 광고에 관한 규정」 제4조①2호 · 제5조)을 채우면 적법이고, 아니면 위반이다. 기록은 보수 전제(D-263 ①)
#:    🚨 판독 없이 규칙으로 붙인다 — 465 전부 개별인정원료 · 461 이 「…에 도움을 줄 수 있음」(원장 09-30 ⑫)
APPROVED_BASIS = (statute.food(3),)
APPROVED_READING = "규칙_승인문구_A"


def approved_docs() -> list[dict]:
    """2층 **승인** 문구. 🔄 2026-09-30 (판정 J1 (가)) — **조건 A 의 3호 양성**이다(종전: 음성).

    ⛔ 종전 docstring 은 「음성 표본 · 위반이 아니라 적법이다」였다 — 「인정받은 제품」 전제에서만 참이다(D-156 ③ 전제 정정).
    """
    import re

    got, seen = [], set()
    for i, r in enumerate(_jsonl(HF)):
        raw = str(r.get("기능성내용") or "")
        raw = re.sub(r"\s*\(\s*'?\d{2,4}\s*년\s*\d{1,2}\s*월\s*인정\s*\)\s*", "", raw)
        for j, line in enumerate(re.split(r"[\n]+", raw)):
            s = line.strip(" -·\t")
            if len(s) < 6 or s in seen:
                continue
            seen.add(s)
            got.append(
                {
                    "doc_id": f"hf:{i}:{j}",
                    "원천": "mfds_hf_ingredient_board",
                    "근거": list(APPROVED_BASIS),
                    "유형": statute.types_of(list(APPROVED_BASIS)),
                    "문구": [s],
                    "단위": "문장",
                    "조건": "A",
                    "근거_후보": [],
                    "판독": APPROVED_READING,
                    "원천결손": False,
                }
            )
    return got


#: 인정 조건문을 문장으로 자르는 곳 — 줄바꿈 · 「…다.」 · 「…것,」 뒤. 원천이 한 칸에 여러 문장을 적는다
_CAUTION_SPLIT = re.compile(r"[\n]|(?<=다\.)\s+|(?<=것)\s*[,.]\s*")
#: 문장 앞뒤에서 떼는 것 — 번호 · 괄호 · 따옴표
_CAUTION_STRIP = ' -·①②③④⑤⑥()0123456789.“”"\t'
#: 인정 조건문이 되려면 이만큼은 돼야 한다 `[임의]` — 「주의」 한 낱말 같은 조각을 뺀다
_CAUTION_MIN = 8


def caution_docs() -> list[dict]:
    """🆕 2026-09-30 (판정 J1 (가-2′) · 원장 09-30 ⑫) — 인정 원료의 **섭취 주의사항**. 조건 D(주장 없음) 학습 행이다.

    ★ 왜 — 승인 문구가 조건 A(3호 양성)로 가면 학습에 위반 라벨이 없는 행이 거의 안 남는다(결정문 무혐의 문구 약 16).
      모델이 「전부 위법」으로 무너지지 않게, **주장이 없는 문장**을 라벨 없는 행으로 준다.
    ★ 왜 D 인가(L 이 아니라) — 해설서 채택 판독이 같은 꼴(「섭취에 주의하시기 바랍니다」 · 「섭취를 중단하십시오」)을
      D 로 읽었다(D-286 ③ · 원장 09-30 ⑫). 주장이 없으니 위반도 적법도 아니고 **판정 대상이 아니다.**
    🚨 평가에 넣지 않는다 — 전량 train. D 는 채점에서 빠지고(`eval_rule.scored`) 음성으로도 세지 않는다(`golden.is_negative`).
    🚨 `[임의]` 규칙이다 — 판독 없이 원천 칸으로 붙였다. 약 · 질환 낱말이 든 문장(231)도 D 로 둔 것은 D-286 ③ 을
       경고문까지 넓힌 해석이다 → 팀장 블라인드 감사 30 (판정 J6).
    ⛔ 광고 꼴 적법 문구가 아니다 — 광고 문구의 특이도는 이것으로 못 가르친다(「음성 부족」 · 판정 J1).
    """
    got: dict[str, dict] = {}
    for path, col, want in (
        (HF, "섭취주의사항", "mfds_hf_ingredient_board"),
        (HF_API, "IFTKN_ATNT_MATR_CN", "mfds_hf_individual"),
    ):
        for r in _jsonl(path):
            # 🔴 원천은 행이 적은 값을 쓴다 — 코드가 이름을 붙이지 않는다(09-30 · 첫 판이 I-0050 을 I-0040 이름으로 붙였다)
            src = r.get("원천") or want
            if src != want:
                raise SystemExit(
                    f"🔴 {path} 의 원천이 {src!r} 다 — {want!r} 를 기대했다 (D-185 · D-220)"
                )
            for piece in _CAUTION_SPLIT.split(str(r.get(col) or "")):
                s = piece.strip(_CAUTION_STRIP)
                if len(s) < _CAUTION_MIN:
                    continue
                key = hashlib.sha256(re.sub(r"\s", "", s).encode("utf-8")).hexdigest()[:12]
                if key in got:  # 두 원천에 같은 문장 — 먼저 읽은 원천(게시판)을 남긴다
                    continue
                got[key] = {
                    "doc_id": f"hfcau:{key}",  # 🚨 줄 번호가 아니라 글자로 — 원천이 한 줄 늘어도 id 가 안 밀린다
                    "원천": src,
                    "근거": [],
                    "유형": [],
                    "문구": [s],
                    "단위": "문장",
                    "조건": "D",
                    "근거_후보": [],
                    "판독": "규칙_인정조건문_D",
                    "원천결손": False,
                }
    return [got[k] for k in sorted(got)]


def _prev_sealed() -> set[str]:
    """이전 판에서 봉인된 문서 id. 이전 판이 없으면 빈 집합(첫 판 · 종전과 같은 추첨)."""
    prev = _previous()
    return {k for k, v in ((prev or {}).get("assign") or {}).items() if v == SEALED}


def plan(seed: int = 20260909, prev_sealed: set[str] | None = None) -> dict:
    """🚨 **희소한 유형부터 채운다.** 흔한 유형이 먼저 가져가면 희소한 것이 못 선다.

    🆕 2026-09-30 — `prev_sealed` 가 주어지면(없으면 이전 판 파일에서 읽는다) 그 봉인을 먼저 지킨다.
    """
    if prev_sealed is None:
        prev_sealed = _prev_sealed()
    ftc = ftc_docs()
    # 🔴 ② 다중 라벨 문서는 평가에서 뺀다 — 문구가 어느 호인지 안 적혀 있다
    single = [d for d in ftc if len(d["유형"]) == 1]
    multi = [d for d in ftc if len(d["유형"]) > 1]
    # 🆕 2026-09-30 (D-237) — 유형이 없고 **적법 문구만** 있는 문서(무혐의 주문 · 16081 · 16089 · 16095)
    lawful = [d for d in ftc if not d["유형"]]

    # 🔄 **봉인 후보는 「주문 문구가 있는 문서」뿐이다** (2026-09-17 · D-234).
    #    🚨 이유 문구는 **문서 라벨을 내려 붙인 것**이고 전수 채택률이 39.7% 다 —
    #       평가에 쓰면 자를 자기가 만든 잡음으로 삼는 꼴이다 (D-172).
    #    ★ 이 한 줄이 「평가셋 구성 규칙은 안 바꾼다」를 집행한다.
    sealable = [d for d in single if d["문구"]]

    have = collections.Counter(d["유형"][0] for d in sealable)
    order = sorted(have, key=lambda x: have[x])
    need = {t: min(have[t], EVAL_TARGET) for t in have}

    # 🚨 **축마다 Random 을 따로 만든다** (2026-09-10 · D-176).
    #    ⛔ 종전에는 인스턴스 하나를 두 shuffle 에 공유했다. `random.shuffle(n)` 이 소모하는
    #       워드 수가 n 의 구간마다 달라, ftc 코퍼스 크기가 **고원을 넘으면**
    #       봉인 음성 60개 중 **21~26개(35~43%)가 조용히 교체된다** (실측).
    #       고원 안(예 208~213)에서는 0개라 몇 건 늘려 보는 것으로는 안 드러난다.
    #    ★ 축을 나누면 pool 을 21개까지 흔들어도 봉인 60개가 고정된다 (실측 확인).
    rnd_pool = random.Random(seed)
    rnd_neg = random.Random(seed)
    pool = sorted(sealable, key=lambda d: d["doc_id"])
    rnd_pool.shuffle(pool)

    sealed: dict[str, dict] = {}
    got: collections.Counter = collections.Counter()
    # 🆕 2026-09-30 — 🔴 **이전 판의 봉인을 먼저 지킨다** (D-254 「시험지는 고정이 약속이다」).
    #    ⛔ 종전에는 매번 섞어 다시 뽑았다 — 추첨이 **후보 목록 전체의 섞인 순서**에 달려, 후보가 한 문서만 바뀌어도
    #       봉인이 갈릴 수 있다. 뒷광고 문서를 빼고(D-255 ③) 무혐의 문구를 적법으로 옮기면(D-237) 후보가 바뀐다.
    #       🚨 얼마나 갈렸을지는 재지 않았다 — 갈리지 않게 막았다.
    #    ★ 이전 판에서 봉인된 문서가 **지금도 설 수 있으면**(단일 유형 · 위반 문구 있음, 또는 적법 문구 있음) 그대로 둔다.
    #      빠지는 것만 빠지고(`sealed_lost` 가 멈춘다 · `--allow-shrink`), 모자란 유형만 아래에서 채운다.
    for d in sorted(single + lawful, key=lambda x: x["doc_id"]):
        if d["doc_id"] in prev_sealed and (d["문구"] or d["문구_적법"]):
            sealed[d["doc_id"]] = d
            if d["문구"]:
                got[d["유형"][0]] += 1
    for t in order:
        for d in pool:
            if d["doc_id"] in sealed or d["유형"][0] != t or got[t] >= need[t]:
                continue
            sealed[d["doc_id"]] = d
            got[t] += 1

    # 🔴 ③ 음성 표본 — 승인 문구 일부를 봉인한다
    approved = approved_docs()
    rnd_neg.shuffle(approved)
    neg_eval = approved[:NEG_TARGET]
    neg_train = approved[NEG_TARGET:]

    # 🔴 사례집은 **사전 쪽**이다 (D-155) — 낱말 시험지를 만들지 않는다. 위 ① 참조.
    term = casebook_docs()
    # 🔴 **train 은 `single` 전체에서 봉인분만 뺀다** — `pool`(봉인 후보)이 아니다.
    #    ⛔ `pool` 로 두면 「이유만 있는 문서」가 train 에서도 빠진다. 그것이 회수분이다.
    # 🆕 2026-09-30 (판정 J1 (가-2′)) — 인정 조건문(조건 D)은 전량 학습이다
    caution = caution_docs()
    train = (
        [d for d in single + lawful if d["doc_id"] not in sealed]
        + multi
        + neg_train
        + term
        + caution
    )
    # 🆕 **사람이 붙인 해설서 라벨은 전량 평가다** (2026-09-17 · D-172 · guide_docs 참조).
    #    🚨 `sealed`(ftc 봉인)와 **따로 센다** — 한 수에 두 원천을 평균하지 않는다 (D-160).
    guide = guide_docs()
    # 🆕 2026-09-30 (D-285 개정 5 · 팀장 판정 ⑤-4 (나)) — 화장품 질의응답집 2025 는 전량 평가다. 해설서와 따로 센다 (D-160)
    cosmetic = cosmetic_docs()
    # 🆕 2026-09-30 (⑤-1·3 (나)) — 공정위 보도자료 1997~2007 도 전량 평가다. 따로 센다 (D-160)
    press = ftc_press_docs()
    sent = list(sealed.values()) + guide + cosmetic + press + neg_eval

    def lawful_units(rows: list[dict]) -> int:
        """🆕 2026-09-30 (판정 J1) — **조건 L 문구 수**(적법 · 음성). 결정문 적법 문구 + 조건 L 행의 문구."""
        return sum(
            len(d.get("문구_적법") or []) + (len(d["문구"]) if d.get("조건") == "L" else 0)
            for d in rows
        )

    def tally(rows: list[dict]) -> dict[str, int]:
        c: collections.Counter = collections.Counter()
        for d in rows:
            for t in d["유형"]:
                c[t] += 1
        return dict(sorted(c.items(), key=lambda x: -x[1]))

    def phrases(rows: list[dict]) -> int:
        return sum(len(d["문구"]) + len(d.get("문구_적법") or []) for d in rows)

    def phrases_reason(rows: list[dict]) -> int:
        """🆕 이유 문구 — **주문과 섞어 세지 않는다** (D-172 · 한 숫자가 두 과제를 평균한다)."""
        return sum(len(d.get("문구_이유") or []) for d in rows)

    def tally_ho(rows: list[dict]) -> dict[str, int]:
        """🆕 D-282 — **호 단위** 셈. D-40 의 30 은 이 단위에 건다 (유형 셈은 표시용 파생값).

        🔄 2026-09-30 — 🔴 **조건 M · D · L 행은 세지 않는다.** 그 행은 호로 채점되지 않는다(`eval_rule.scored` · L 은 적법).
           ⛔ 세면 보류(M) 행의 근거가 D-40 의 30 을 채운 것처럼 보인다 — 보도자료 3호가 채점 28 인데 31 ✅ 로 찍혔다(작업공간 실측).
        """
        c: collections.Counter = collections.Counter()
        for d in rows:
            if d.get("조건") in ("M", "D", "L"):
                continue
            for k in {statute.ho_key(x) for x in d.get("근거") or []}:
                c[k] += 1
        return dict(sorted(c.items()))

    sent_pos = tally(sent)
    term_pos = tally(term)
    sent_ho = tally_ho(sent)
    AXIS = (
        "질병_예방치료_표방",
        "의약품_오인",
        "건강기능식품_오인",
        "거짓_과장",
        "소비자_기만",
        "후기_체험기_기만",
        "부당_비교광고",
        "비방광고",
    )
    return {
        "seed": seed,
        # 🔴 **재현의 근거는 seed 가 아니라 이것이다** (D-176). 위 fingerprint() 참조.
        "inputs": fingerprint(),
        "승인문구_종수": len(approved),
        "eval_target": EVAL_TARGET,
        "neg_target": NEG_TARGET,
        "min_measurable": MIN_MEASURABLE,
        "split_key": "doc_id",
        "note": (
            "평가셋은 조문 라벨 원천으로만 만든다. 🔴 낱말(test_term)과 문장(test_sentence)을 "
            "섞지 않는다 — 한 숫자로 보고하면 두 과제를 평균한 수가 된다. "
            "ftc 슬라이스는 학습과 같은 기관이라 원천 편향을 재지 못한다 (same_source)."
        ),
        # 🆕 D-282 — 정본 셈. 키는 `collect.statute.cite` 꼴(법ID:제N조제N항제N호)
        "counts_by_citation": {
            "train": tally_ho(train),
            "test_sentence": sent_ho,
        },
        "unmeasurable_by_citation": {
            "test_sentence": sorted(k for k, v in sent_ho.items() if v < MIN_MEASURABLE),
        },
        # 🆕 D-283 — 호가 안 정해져 평가에 못 넣은 해설서 위반문구 (원천 3분류별)
        "pending_guide": pending_guide(),
        "sizes": {
            "train": {"문서": len(train), "문구": phrases(train)},
            "test_sentence": {"문서": len(sent), "문구": phrases(sent)},
            # 🆕 원천별로 따로 센다 — 한 수에 두 원천을 평균하지 않는다 (D-160)
            "test_sentence_ftc봉인": {"문서": len(sealed), "문구": phrases(list(sealed.values()))},
            "test_sentence_해설서": {"문서": len(guide), "문구": phrases(guide)},
            "test_sentence_화장품질의응답": {"문서": len(cosmetic), "문구": phrases(cosmetic)},
            "test_sentence_공정위보도자료": {"문서": len(press), "문구": phrases(press)},
            "사전(사례집)": {"문서": len(term), "문구": phrases(term)},
        },
        "counts": {
            "train": tally(train),
            "test_sentence": sent_pos,
            # 🆕 유형별로도 원천을 가른다 — 어느 유형이 사람 라벨로 섰는지 보이게
            "test_sentence_ftc봉인": tally(list(sealed.values())),
            "test_sentence_해설서": tally(guide),
            "test_sentence_화장품질의응답": tally(cosmetic),
            "test_sentence_공정위보도자료": tally(press),
            "사전(사례집)": term_pos,
        },
        # 🔄 2026-09-30 (판정 J1 (가) · (가-2′)) — 음성은 **조건 L 문구**다. 승인 문구는 조건 A 양성으로 옮겼다.
        #    ⛔ 종전 `test_sentence` · `train` 은 승인 문구 문서 수(60 · 118)였다
        "negatives": {
            "test_sentence": lawful_units(sent),
            "train": lawful_units(train),
            "train_주장없음_D": sum(len(d["문구"]) for d in caution),
            "test_sentence_승인문구A": len(neg_eval),
            # 🆕 2026-09-30 (D-237) — 결정문의 적법 문구(조건 L). 승인 문구와 **따로** 센다 (D-160)
            "test_sentence_ftc적법": sum(len(d.get("문구_적법") or []) for d in sealed.values()),
        },
        "unit": {"test_sentence": "문장"},
        "unmeasurable": {
            # 🔄 2026-09-30 — AXIS(식품 · 공정위 8유형) 밖의 유형도 센다. ⛔ 화장품 판이 들어오며 `기능성화장품_오인` 13 이
            #    측정 불가인데 목록에 없었다(기기 게이트 `test_측정_불가를_숨기지_않는다` 실측) — 축 목록만 보면 새 유형이 숨는다
            "test_sentence": sorted(
                t for t in set(AXIS) | set(sent_pos) if sent_pos.get(t, 0) < MIN_MEASURABLE
            ),
        },
        # 🔴 어느 단위로도 평가 데이터가 없는 유형 — 열린 항목 A 의 실제 크기다
        "no_eval_at_all": sorted(t for t in AXIS if sent_pos.get(t, 0) == 0),
        "source_sets": {
            "train": [
                "ftc_decisions_body(비봉인·다중라벨)",
                "mfds_hf_ingredient_board(비봉인 · 조건 A)",
                "mfds_hf_ingredient_board · mfds_hf_individual 섭취 주의사항(조건 D)",
                "주입본[P10]",
            ],
            "test_sentence": [
                "ftc_decisions_body(봉인)",
                "mfds_hf_ingredient_board(봉인·조건 A 3호 — 09-30 판정 J1 · 종전 음성)",
                # 🔄 D-283 — 해설서는 호가 정해질 때까지 없다 (`pending_guide`)
            ],
        },
        "same_source": ["ftc_decisions_body"],
        "excluded_from_eval": {
            "다중라벨_문서": len(multi),
            "이유": "의결서가 두 호를 함께 걸면 인용 문구가 어느 호인지 적혀 있지 않다",
            # 🔄 D-283 — 사람 8유형 라벨(범위밖 포함)은 평가 입력이 아니다. 해설서는 `pending_guide` 로 센다.
            "해설서_이유": (
                "원천 3분류는 위반임을 말하지만(D-237) 호를 말하지 않는다 — 현행 조문으로 읽으면 묶음 밖으로 가는 문구가 있다. "
                "호를 조문 원문 기준으로 붙이기 전까지 평가에 넣지 않는다 (D-283)"
            ),
        },
        "assign": {
            **{d["doc_id"]: "train" for d in train},
            **{d["doc_id"]: "test_sentence" for d in sent},
        },
    }


#: 봉인 평가셋의 배정값. `plan()` 의 `assign` 이 이 이름으로 적는다.
SEALED = "test_sentence"


def sealed_lost(old: dict, new: dict) -> list[str]:
    """이전 판에서 봉인됐는데 **새 판에서 봉인이 아닌** id — 사라졌거나 train 으로 넘어간 것.

    🔴 **봉인 평가셋은 줄면 안 된다** (2026-09-20 · D-254 · 감사 §2 golden).
       ⛔ 종전 `--write` 는 옛 `split_manifest.json` 과 비교하지 않고 덮었다. 입력 한 줄이 빠지면
          봉인 문서가 조용히 빠지고, 옛 판과 새 판의 지표가 **다른 시험지로 잰 수**가 된다.
       🚨 수만 세지 않고 **id 를 본다** — 하나 빠지고 하나 들어오면 수는 같아도 시험지가 바뀐다.
       ★ **더해지는 것은 막지 않는다** — 사람 라벨이 늘면 봉인이 는다.
    """
    before = {k for k, v in (old.get("assign") or {}).items() if v == SEALED}
    after = {k for k, v in (new.get("assign") or {}).items() if v == SEALED}
    return sorted(before - after)


def _previous() -> dict | None:
    """이전 판 분할. **없으면 `None`** — 첫 판이다. ⛔ 깨진 JSON 은 삼키지 않는다 (D-220)."""
    if not OUT.exists():
        return None
    return json.loads(OUT.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="골든셋 분할 [P12] — 출처 분리 · 단위 분리")
    ap.add_argument("--write", action="store_true", help=f"{OUT} 로 쓴다")
    ap.add_argument("--seed", type=int, default=20260909, help="재현 조건 (D-54)")
    ap.add_argument(
        "--allow-shrink",
        action="store_true",
        help="🚨 봉인 평가셋에서 빠지는 id 가 있어도 쓴다 — 이유를 안 뒤에만",
    )
    a = ap.parse_args()

    m = plan(a.seed)
    s = m["sizes"]
    print(f"분할 seed={m['seed']} · 키={m['split_key']} · 평가 목표 유형당 {m['eval_target']}")
    print(
        f"  train {s['train']['문서']}문서/{s['train']['문구']}문구 · "
        f"test_sentence {s['test_sentence']['문서']}/{s['test_sentence']['문구']}"
    )
    print(
        f"  🔴 음성(적법 · 조건 L 문구) — 평가 {m['negatives']['test_sentence']} · 학습 {m['negatives']['train']}"
        f"  · 학습 주장 없음(D · 인정 조건문) {m['negatives'].get('train_주장없음_D', '—')}"
        f"  · 평가 승인 문구(A · 3호) {m['negatives'].get('test_sentence_승인문구A', '—')}"
    )
    print(
        f"  🔴 평가에서 뺀 다중 라벨 문서 {m['excluded_from_eval']['다중라벨_문서']} — "
        "문구가 어느 호인지 안 적혀 있다"
    )

    for name in ("test_sentence",):
        print(f"\n  ── {name} ({m['unit'][name]} 단위) ──")
        c = m["counts"][name]
        for t, n in sorted(c.items(), key=lambda x: -x[1]):
            print(f"    {t:22} {n:>4}   {'✅' if n >= MIN_MEASURABLE else '🔴 측정 불가'}")
        if m["unmeasurable"][name]:
            print(f"    🔴 측정 불가 — {m['unmeasurable'][name]}")

    # 🆕 D-282 — 정본 셈(호 단위). D-40 의 30 은 여기에 건다
    print("\n  ── test_sentence · 호 단위 (정본 · D-282) ──")
    for k, n in m["counts_by_citation"]["test_sentence"].items():
        t = statute.type_of(k) or "(유형 없음)"
        print(f"    {k:26} {t:14} {n:>4}   {'✅' if n >= MIN_MEASURABLE else '🔴 측정 불가'}")
    st = guide_state()
    if st:
        print(
            f"\n  해설서 조문·조건 판 — 전체 {st['전체']:,} · 채택 {st['채택']:,} · **대기 {st['대기']:,}**"
            + (
                "  → 대기가 0 이 되면 평가에 들어간다 (D-285 개정 4)"
                if st["대기"]
                else "  → 평가에 들어갔다"
            )
        )
    cq = cosmetic_state()
    if cq:
        print(
            f"  화장품 질의응답집 조문·조건 판 — 전체 {cq['전체']:,} · 채택 {cq['채택']:,}(대상 N 포함) · **대기 {cq['대기']:,}**"
            + (
                "  → 대기가 0 이 되면 평가에 들어간다 (D-285 개정 5)"
                if cq["대기"]
                else f"  → 평가에 들어갔다 ({m['sizes'].get('test_sentence_화장품질의응답', {}).get('문구', '?')}문구)"
            )
        )
    fp = ftc_press_state()
    if fp:
        print(
            f"  공정위 보도자료 1997~2007 조문·조건 판 — 전체 {fp['전체']:,} · 채택 {fp['채택']:,} · **대기 {fp['대기']:,}**"
            + (
                "  → 대기가 0 이 되면 평가에 들어간다"
                if fp["대기"]
                else f"  → 평가에 들어갔다 ({m['sizes'].get('test_sentence_공정위보도자료', {}).get('문구', '?')}문구)"
            )
        )
    if m["pending_guide"]:
        tot = sum(m["pending_guide"].values())
        print(
            f"\n  ⬜ **호를 기다리는 해설서 위반문구 {tot:,}행** (원천 3분류별 · D-283) — 평가에 안 넣었다"
        )
        for k, n in m["pending_guide"].items():
            print(f"     {n:>5}  {k}")

    print(f"\n  🔴 **어느 단위로도 평가 데이터가 없는 유형 {len(m['no_eval_at_all'])}종**")
    print(f"     {m['no_eval_at_all']}")
    print(
        "     🚨 이것이 **열린 항목 A 의 실제 크기**다. 사례집은 시험지가 아니라 사전이다 (D-155)."
    )
    print(f"  ★ 사전 쪽으로 간 사례집 — {m['sizes']['사전(사례집)']['문서']}문서")
    print("  🚨 ftc 슬라이스는 학습과 같은 기관이다 — 원천 편향은 못 잰다 (same_source).")

    # 🔴 **봉인이 줄면 멈춘다** (2026-09-20 · D-254) — 쓰기 전에, 미리보기에서도 보인다.
    #    🚨 비율 문턱이 없다 — 봉인은 **한 건이라도** 빠지면 멈춘다. 시험지는 고정이 약속이다.
    prev = _previous()
    lost = sealed_lost(prev, m) if prev is not None else []
    if lost:
        n_old = sum(1 for v in (prev or {}).get("assign", {}).values() if v == SEALED)
        n_new = sum(1 for v in m["assign"].values() if v == SEALED)
        print(f"\n  🔴 봉인 평가셋에서 빠지는 id {len(lost)}개 — 봉인 {n_old} → {n_new}")
        for k in lost[:10]:
            print(f"     {k}")
        if len(lost) > 10:
            print(f"     … 외 {len(lost) - 10}개")
        print("     🚨 이대로 쓰면 이전 판과 **다른 시험지**로 잰 지표가 된다.")
        print("     먼저 입력이 왜 바뀌었는지 본다 (라벨 파일 · 추출 판 · seed).")
        print("     빠지는 것이 맞다고 판단했으면:")
        print("       uv run python -m preprocess.split --write --allow-shrink")
        if a.write and not a.allow_shrink:
            print("     ⛔ 쓰지 않았다 — 이전 판이 그대로 남아 있다.")
            return 1

    if a.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        # 🔴 **개행으로 끝낸다.** 안 그러면 커밋마다 `end-of-file-fixer` 훅이 이 파일을 고친다
        #    (2026-09-17 실측 — 원장에 커밋되기 시작하면서 드러났다).
        #    ⛔ `_matrix/README.md` 가 같은 사고를 이미 적어 두었다: *"JSON.stringify 가 개행으로
        #       끝나지 않아 커밋마다 end-of-file-fixer 훅이 걸렸다."* 같은 실수를 다른 생성기에서 했다.
        OUT.write_text(
            json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"\n  → {OUT}")
        print("  🚨 **사전과 주입은 이 파일을 읽어 train 만 쓴다** — 안 그러면 누수다.")
    else:
        print(f"\n  ⬜ 쓰지 않았다 — `--write` 를 붙이면 {OUT} 에 고정된다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
