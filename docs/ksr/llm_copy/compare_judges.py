"""판정 방식 비교 — 같은 문구에 ① 코드 필터 + 사전 ② 인코더 ③ LLM 판정의 신호를 모은다 (2026-10-08).

    uv run python docs/ksr/llm_copy/compare_judges.py --log build/llm_copy/<실행 로그>.json

모으는 것(문구마다) — 코드 필터에 걸렸나 · 사전 판정에 걸렸나 · 인코더 유형별 확률 · LLM 판정(모델별).
조합(① + ② 등)은 여기서 정하지 않는다 — 신호만 `build/llm_copy/compare_signals_*.json` 에 남기고 표는 따로 낸다.

문구 묶음
  V  직접 쓴 위반 문구 30 + 대조 5 (10-06 재실행 결과 §3-2 · 실제 광고 아님)
  N  실행 로그에서 판정까지 간 문구(보관 + 판정 탈락) — 고정 문구를 뺀 글자로 판정한다(생성 흐름과 같다)
  S  합성 정상 카피 900 (10-06) — 입력 정보가 없어 코드 필터는 돌리지 않는다

🚨 `OPENAI_API_KEY` 는 평가 · 비교 전용이다 (D-78 ②). 이 파일은 실험이고 `app/` 경로에 넣지 않는다.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime
import io
import json
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import llm as llm_mod  # noqa: E402
from branches import BRANCHES, PLACEHOLDER  # noqa: E402
from filters import Inputs, check  # noqa: E402
from judge import ENCODER_DIR, GraphJudge  # noqa: E402

SYNTH = ROOT / "docs/ksr/LLM_카피생성_정상카피_900_판독용_ksr_2026-10-06.csv"
#: 코드 필터 사유 중 **내용**을 본 것 — 자리 · 길이 · 중복은 위반 판정이 아니다
CONTENT_REASONS = {"superlative", "number", "cert", "ingredient", "forbidden"}

#: (분기, 시험 입력, 노린 것, 문구) — 10-06 재실행 결과 §3-2 의 35개 그대로. 「대조」는 위반이 아니다
VIOLATIONS = [
    ("food_no", "food_no_1", "대조", "우유에 바로 부어 먹는 바삭한 아침곡간 그래놀라"),
    ("food_no", "food_no_1", "건기식 오인", "면역력을 높여 주는 아침곡간 그래놀라"),
    ("food_no", "food_no_1", "질병", "매일 한 그릇으로 당뇨를 예방하는 그래놀라"),
    ("food_no", "food_no_1", "질병", "변비를 치료해 주는 통귀리 그래놀라"),
    ("food_no", "food_no_1", "의약품 오인", "혈압약 대신 먹는 그래놀라"),
    ("food_no", "food_no_1", "체중", "먹기만 해도 살이 빠지는 다이어트 그래놀라"),
    ("food_no", "food_no_1", "최상급", "국내 최고, 판매 1위 그래놀라"),
    ("food_no", "food_no_1", "부당 비교", "타사 그래놀라보다 영양이 두 배 많은 아침곡간"),
    ("food_no", "food_no_1", "비방", "다른 회사 그래놀라는 설탕 덩어리, 아침곡간만 믿으세요"),
    ("food_no", "food_no_1", "거짓·과장", "부작용 없이 100% 효과를 보장하는 그래놀라"),
    ("hf_no", "hf_no_1", "건기식 오인", "피로 회복에 좋은 매일한포 석류즙"),
    ("hf_no", "hf_no_1", "건기식 오인", "갱년기 여성 건강에 도움을 주는 석류즙"),
    ("hf_no", "hf_no_1", "질병", "항암 효과가 있는 석류즙"),
    (
        "hf_yes",
        "hf_yes_1",
        "대조",
        "유산균 증식 및 유해균 억제·배변활동 원활·장 건강에 도움을 줄 수 있음",
    ),
    ("hf_yes", "hf_yes_1", "대조", "하루 한 캡슐, 작은 캡슐 데일리바이옴"),
    ("hf_yes", "hf_yes_1", "인정 범위 초과", "하루 한 캡슐로 면역력까지 높여 주는 데일리바이옴"),
    ("hf_yes", "hf_yes_1", "질병", "과민성 대장 증후군을 치료하는 데일리바이옴"),
    ("hf_yes", "hf_yes_1", "질병", "장염과 대장암을 예방하는 프로바이오틱스"),
    ("hf_yes", "hf_yes_1", "체중", "뱃살이 빠지는 다이어트 유산균 데일리바이옴"),
    ("hf_yes", "hf_yes_1", "최상급", "세계 최고 유산균, 국내 판매 1위 데일리바이옴"),
    ("hf_yes", "hf_yes_1", "부당 비교", "타사 유산균보다 열 배 더 살아서 가는 데일리바이옴"),
    ("cos_no", "cos_no_1", "대조", "끈적임 없이 산뜻하게 발리는 촉촉 수분크림"),
    ("cos_no", "cos_no_1", "의약품 오인", "지친 피부를 재생시키는 촉촉 수분크림"),
    ("cos_no", "cos_no_1", "의약품 오인", "여드름을 치료하는 수분크림"),
    ("cos_no", "cos_no_1", "의약품 오인", "아토피 피부염을 완화하는 수분크림"),
    ("cos_no", "cos_no_1", "기능성 오인", "주름을 개선해 주는 촉촉 수분크림"),
    ("cos_no", "cos_no_1", "기능성 오인", "바르기만 해도 미백 효과가 나타나는 수분크림"),
    ("cos_no", "cos_no_1", "의약품 오인", "피부 세포를 되살려 흉터를 없애는 크림"),
    ("cos_no", "cos_no_1", "최상급", "국내 최고, 판매 1위 수분크림"),
    ("cos_no", "cos_no_1", "부당 비교", "타사 수분크림보다 보습력이 세 배 높은 촉촉 수분크림"),
    ("cos_no", "cos_no_1", "비방", "다른 브랜드 크림은 화학 성분 범벅, 촉촉 수분크림만 안전합니다"),
    ("cos_no", "cos_no_1", "거짓·과장", "부작용 전혀 없이 누구나 100% 효과를 보는 수분크림"),
    ("cos_yes", "cos_yes_1", "대조", "피부 미백에 도움을 준다"),
    ("cos_yes", "cos_yes_1", "심사 범위 초과", "기미와 잡티를 완전히 없애 주는 브라이트 세럼"),
    ("cos_yes", "cos_yes_1", "심사 범위 초과", "주름 개선까지 한 번에, 브라이트 세럼"),
]

JUDGE_SYSTEM = """너는 한국의 광고 표시 심사를 돕는 검토자다. 광고 문구 후보가 법 위반 소지가 있는지 한 줄씩 본다.

기준
- 식품 · 건강기능식품 (식품 등의 표시·광고에 관한 법률 제8조): 질병의 예방 · 치료 효능으로 인식될 우려 / 의약품으로 인식될 우려 /
  건강기능식품이 아닌 것이 신체 기능 · 건강 효과를 말해 건강기능식품으로 인식될 우려 / 거짓 · 과장 / 소비자 기만 / 다른 업체 · 제품 비방 / 부당 비교.
- 화장품 (화장품법 제13조): 의약품으로 잘못 인식할 우려(치료 · 재생 · 질환) / 기능성화장품이 아닌데 기능성(미백 · 주름 개선 · 자외선 차단)으로
  인식할 우려 / 사실과 다르거나 소비자가 잘못 인식할 우려 / 비교 · 비방.
- 공통: 근거 없는 최상급 · 1위 · 100% 보장 · 부작용 없음 / 제품 정보에 없는 수치 · 인증 · 시험 사실.

원칙
- 제품 정보에 적힌 것은 사실로 본다. 맛 · 식감 · 제형 · 사용감 · 사용 장면 · 대상 · 원료 이름을 말하는 것은 위반이 아니다.
- 인정 · 심사 문구가 주어지면 그 문구를 글자 그대로 쓴 것은 허용이다. 그 범위를 넓히거나 다른 효능을 더하면 위반이다.
- 위반 소지가 분명할 때만 violation 을 true 로 한다. 막연한 느낌으로 true 를 주지 않는다.
- awkward 는 위반과 별개다 — 문장이 깨졌거나 낱말이 틀려 그대로 쓰기 어려울 때만 true.

JSON 으로만 답한다: {"results": [{"id": 번호, "violation": true|false, "type": "유형 한 낱말 또는 빈 문자열", "awkward": true|false, "reason": "한 줄"}]}
모든 번호에 답한다."""


def judge_prompt(branch_key: str, inputs: dict, texts: list[tuple[int, str]]) -> str:
    b = BRANCHES[branch_key]
    info = " · ".join(
        f"{k}: {', '.join(v) if isinstance(v, list) else v}"
        for k, v in inputs.items()
        if k != "fixed"
    )
    parts = [
        f"[분기] {b.label} (판정 품목: {b.category})",
        f"[제품 정보] {info or '(적은 것 없음)'}",
    ]
    if inputs.get("fixed"):
        parts.append(f"[인정 · 심사 문구] {inputs['fixed']}")
    parts.append("[문구]\n" + "\n".join(f"{i}. {t}" for i, t in texts))
    return "\n".join(parts)


def call_llm(model: str, key: str, user: str) -> tuple[dict[int, dict], dict]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(  # noqa: S310 — 주소는 상수다
        llm_mod.URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as res:  # noqa: S310
            data = json.load(res)
    except (urllib.error.URLError, TimeoutError) as e:
        return {}, {"error": str(e)[:200]}
    try:
        items = json.loads(data["choices"][0]["message"]["content"]).get("results", [])
    except (json.JSONDecodeError, AttributeError, KeyError):
        items = []
    out = {}
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), int):
            out[it["id"]] = {
                "violation": bool(it.get("violation")),
                "type": str(it.get("type") or ""),
                "awkward": bool(it.get("awkward")),
                "reason": str(it.get("reason") or "")[:200],
            }
    return out, data.get("usage", {})


def llm_judge(model: str, items: list[dict], batch: int, workers: int) -> dict:
    """묶음(같은 분기 · 같은 제품)별로 나눠 부른다. 빠진 번호는 한 번 더 묻는다."""
    key = llm_mod._api_key()  # noqa: SLF001
    groups: dict[tuple, list[dict]] = {}
    for it in items:
        groups.setdefault((it["branch"], json.dumps(it["inputs"], ensure_ascii=False)), []).append(
            it
        )
    jobs = []
    for (branch, inp), its in groups.items():
        for i in range(0, len(its), batch):
            jobs.append((branch, json.loads(inp), its[i : i + batch]))
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "errors": 0}

    def run(job: tuple) -> None:
        branch, inp, its = job
        todo = its
        for _ in range(2):
            got, u = call_llm(
                model, key, judge_prompt(branch, inp, [(x["id"], x["full"]) for x in todo])
            )
            usage["calls"] += 1
            usage["errors"] += 1 if "error" in u else 0
            for k in ("prompt_tokens", "completion_tokens"):
                usage[k] += u.get(k, 0)
            for x in todo:
                if x["id"] in got:
                    x.setdefault("llm", {})[model] = got[x["id"]]
            todo = [x for x in todo if model not in x.get("llm", {})]
            if not todo:
                break

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        list(ex.map(run, jobs))
    return usage


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--log", required=True, help="run.py 실행 로그 — 판정까지 간 문구를 여기서 읽는다"
    )
    ap.add_argument("--models", default="gpt-5.6-luna,gpt-6-luna", help="LLM 판정 모델(쉼표)")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-synth", action="store_true", help="합성 900개는 건너뛴다")
    args = ap.parse_args()

    cases = {c["id"]: c for c in json.loads((HERE / "cases.json").read_text("utf-8"))}
    items: list[dict] = []

    def add(group: str, branch: str, inputs: dict, full: str, **extra: object) -> None:
        judged = (
            full.replace(inputs["fixed"], " ").strip()
            if inputs.get("fixed") and group == "N"
            else full
        )
        items.append(
            {
                "id": len(items) + 1,
                "group": group,
                "branch": branch,
                "inputs": inputs,
                "full": full,
                "judged": judged,
                **extra,
            }
        )

    for branch, case, aim, text in VIOLATIONS:
        add("V", branch, cases[case]["inputs"], text, case=case, aim=aim, violation=aim != "대조")
    for r in json.loads(pathlib.Path(args.log).read_text("utf-8")):
        inp = cases[r["case"]]["inputs"]
        for k in r["kept"]:
            add("N", r["branch"], inp, k["text"], case=r["case"], run="kept")
        for x in r["dropped"]:
            if x["reason"] == "judge":
                add("N", r["branch"], inp, x["text"], case=r["case"], run="judge")
    if not args.no_synth:
        kinds = {
            "식품": "food_no",
            "건강기능식품": "hf_yes",
            "건기식": "hf_yes",
            "화장품": "cos_no",
        }
        with SYNTH.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                add(
                    "S",
                    kinds.get(row["품목"], "food_no"),
                    {"name": row["제품명"], "kind": row["제품종류"]},
                    row["text"],
                    sid=row["id"],
                    dict_10_06=row["사전엔진_유형"],
                    ambiguous=row["애매표시"],
                )
    print(
        f"문구 — V {sum(i['group'] == 'V' for i in items)} · N {sum(i['group'] == 'N' for i in items)} · "
        f"S {sum(i['group'] == 'S' for i in items)}"
    )

    # ① 코드 필터 — 입력 정보가 있는 V 만 새로 돌린다. N 은 필터를 지나온 문구다(걸린 것 0)
    for it in items:
        if it["group"] == "V":
            b = BRANCHES[it["branch"]]
            raw = f"{it['full']} {PLACEHOLDER}" if b.needs_fixed else it["full"]
            hit = check(raw, Inputs.from_dict(it["inputs"]), b, [])
            it["filter"] = list(hit) if hit and hit[0] in CONTENT_REASONS else None
        elif it["group"] == "N":
            it["filter"] = None

    # ① 사전 판정 — V 만. N 은 실행 로그에서 사전 탈락이 0 이었고, S 는 10-06 에 잰 칸을 쓴다
    gj = GraphJudge(reject_only=True)
    for it in items:
        if it["group"] == "V":
            j = gj.judge(it["judged"], BRANCHES[it["branch"]])
            it["dict"] = None if j.passed else j.detail
        elif it["group"] == "N":
            it["dict"] = None
        else:
            it["dict"] = it["dict_10_06"] or None
    gj.close()
    print("사전 판정 끝")

    # ② 인코더 — 유형별 확률을 전부 남긴다(문턱은 표를 낼 때 건다)
    from app.encoder import JudgeEncoder  # noqa: PLC0415

    enc = JudgeEncoder(ENCODER_DIR)
    for it in items:
        it["enc"] = {k.value: round(v, 4) for k, v in enc.predict(it["judged"]).scores.items()}
    thresholds = {k.value: v for k, v in enc.scheme.thresholds.items()}
    print("인코더 끝")

    # ③ LLM 판정 — 고정 문구를 끼운 모습 그대로 보여 준다(인정 · 심사 문구를 같이 알려 준다)
    usage = {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        usage[model] = llm_judge(model, items, args.batch, args.workers)
        missing = sum(model not in it.get("llm", {}) for it in items)
        print(f"LLM {model} 끝 — {usage[model]} · 답 없는 문구 {missing}")

    out = (
        ROOT
        / "build"
        / "llm_copy"
        / f"compare_signals_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "log": str(args.log),
                "encoder": ENCODER_DIR.name,
                "thresholds": thresholds,
                "usage": usage,
                "items": items,
            },
            ensure_ascii=False,
            indent=1,
        ),
        "utf-8",
    )
    print(f"신호 — {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
