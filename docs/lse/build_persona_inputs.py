"""2단계(페르소나 말투) 학습 입력 고르기 — 누수 없이 (2026-10-01, 팀장 조건: 데이터 누수 금지).

입력 = 이미 적법한 문장 = 식약처 기능성 원료 **고시 문구**(`hf_display_claims.jsonl`, 재배포 가능).
정답(페르소나별 다듬은 문장)은 `persona_targets.jsonl` 에 따로 쓴다 — 이 스크립트는 입력과 분할만 만든다.

누수 방지 (어기면 멈춘다):
  ① 판정 인코더 데이터(`golden.jsonl`)와 **정확히 같거나 부분으로 들어간** 문구는 학습 · 평가 모두에서 뺀다.
  ② 학습 · 평가는 **기능 주제**(눈 · 피부 · 혈당 …) 단위로 나눈다 — 평가 주제는 학습에 통째로 없다.
     (첫 판은 문장 핵심 단위로 나눴더니 「스트레스 긴장 완화」 같은 사실상 같은 문장이 양쪽에 섰다.)
  ③ 평가에는 학습에 없는 페르소나 2개를 쓴다.
  ④ 재배포 불가 원천(공정위 · 사례집 · 해설서)은 쓰지 않는다.

실행: .venv/Scripts/python.exe docs/lse/build_persona_inputs.py
"""

from __future__ import annotations

import collections
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "lse" / "persona_inputs.jsonl"
SEED = 20261001
#: 평가 전용 주제 — 학습에 이 주제 문장은 하나도 없다
EVAL_TOPICS = ("피부", "기억인지", "수면긴장", "항산화")
TOPICS = [
    ("눈", ["눈", "황반"]), ("피부", ["피부"]), ("체지방", ["체지방"]), ("혈당", ["혈당", "당의 흡수"]),
    ("혈압", ["혈압"]), ("콜레스테롤", ["콜레스테롤"]), ("간", ["간 ", "간을", "간건강"]),
    ("관절뼈", ["관절", "연골", "뼈", "칼슘"]), ("기억인지", ["기억", "인지"]),
    ("장", ["장내", "배변", "장 건강", "유산균"]), ("면역", ["면역", "신체방어", "저항능력"]),
    ("수면긴장", ["수면", "스트레스", "긴장"]), ("운동피로", ["운동", "근력", "피로"]),
    ("갱년기", ["갱년기"]), ("전립선", ["전립선"]), ("항산화", ["항산화", "산화"]),
    ("혈행", ["혈소판", "혈액"]), ("위", ["위 불편"]),
]

# 🚨 D-27 — 고민 · 증상(pain point) 축 없음. 인구통계 · 라이프스타일 · 목표만. 취약계층(아동 · 환자) 대상 없음.
PERSONAS = {
    "p1": "30대 직장인 — 바쁜 일상 속 간편한 관리",
    "p2": "50대 — 가족과 함께하는 꾸준한 건강 습관",
    "p3": "20대 — 운동·자기관리 루틴을 즐기는 사람",
    "p4": "40대 맞벌이 부부 — 효율적으로 챙기는 생활",
    "p5": "60대 액티브 시니어 — 여행과 취미를 즐기는 일상",
    "p6": "20대 대학생 — 가성비와 트렌드에 민감",
    # 평가 전용 — 학습에서 보지 못한 페르소나
    "q1": "30대 프리랜서 — 재택근무하며 자기 페이스대로 사는 사람",
    "q2": "40대 등산·캠핑 동호인 — 주말마다 야외 활동",
}
TRAIN_PERSONAS = ["p1", "p2", "p3", "p4", "p5", "p6"]


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "")


def split_claims(raw: str) -> list[str]:
    out = []
    for part in re.split(r"\n|(?<=음)\s*[,/]\s*|(?<=다)\s*[,/]\s*|\s(?=\d\)\s)", raw or ""):
        s = re.sub(r"^\s*(\(국문\)|\d+\)|[①-⑩])\s*", "", part).strip(" “”\"'")
        s = re.sub(r"\((기타기능|생리활성기능|질병발생위험감소기능)[^)]*\)", "", s).strip(" “”\"'.")
        if 10 <= len(s) <= 70 and "도움" in s:
            out.append(s)
    return out


def clean(s: str) -> str:
    """영문 병기 · 등급 · 인정 연월 · 번호 머리를 뗀다."""
    s = re.sub(r"\(영문\).*$", "", s)
    s = re.sub(r"\((기타|생리활성|질병)[^)]*\)|\('\d+년[^)]*\)|\([^)]*등급\)", "", s)
    s = re.sub(r"^[\s①-⑩\d\)\.]+", "", s)
    s = s.replace("?", "·")
    # 끝에 특수 공백(NBSP 등)이 붙은 원문이 있다 — str.strip(" ") 로는 안 떨어진다
    return re.sub(r"^[\s“”\"'.,]+|[\s“”\"'.,]+$", "", s)


def topic(s: str) -> str:
    for name, keys in TOPICS:
        if any(k in s for k in keys):
            return name
    return "기타"


def main() -> None:
    hf = [json.loads(line) for line in (ROOT / "data/derived/hf_display_claims.jsonl").open(encoding="utf-8")]
    assert all(r.get("redistributable") is not False for r in hf), "재배포 불가 행이 섞였다"
    golden = [norm(json.loads(line)["text"]) for line in (ROOT / "data/derived/golden/golden.jsonl").open(encoding="utf-8")]
    gset = set(golden)
    gblob = "\n".join(golden)

    uniq: dict[str, str] = {}
    for r in hf:
        for raw in split_claims(r.get("정본_문구") or r.get("FNCLTY_CN")):
            c = clean(raw)
            # 머리가 잘린 조각(「유지시켜 주어…」) · 괄호 단서문은 문장이 아니다
            if (len(c) < 10 or not re.match(r"^[가-힣A-Za-z]", c) or c.startswith(("유지시켜", "동물시험"))
                    or c.endswith("있으나")):  # 단서가 잘린 문장 — 「~있으나」 뒤 조건이 없다
                continue
            # ① 정리 전 · 후 어느 쪽이든 golden 과 같거나 부분으로 들어가면 뺀다
            if any(k in gset or k in gblob for k in (norm(c), norm(raw))):
                continue
            uniq.setdefault(norm(c), c)
    print(f"golden 겹침 · 조각 제외 후 고유 문구 {len(uniq)}")

    by_topic: dict[str, list[str]] = collections.defaultdict(list)
    for c in uniq.values():
        by_topic[topic(c)].append(c)
    train_rows = [(t, c) for t, cs in sorted(by_topic.items()) if t not in EVAL_TOPICS for c in cs]
    eval_rows = [(t, c) for t, cs in sorted(by_topic.items()) if t in EVAL_TOPICS for c in cs]
    # ② 주제 겹침 0
    assert not {t for t, _ in eval_rows} & {t for t, _ in train_rows}
    rng = random.Random(SEED)

    rows = []
    for i, (k, s) in enumerate(train_rows):
        for p in rng.sample(TRAIN_PERSONAS, 3):
            rows.append({"id": f"t{i:03d}-{p}", "split": "train", "group": k, "input": s,
                         "persona": p, "persona_label": PERSONAS[p], "source": "hf_display_claims"})
    for i, (k, s) in enumerate(eval_rows):
        # ③ 평가 — 학습에 없는 페르소나 2 + 학습 페르소나 1
        for p in ["q1", "q2", rng.choice(TRAIN_PERSONAS)]:
            rows.append({"id": f"e{i:03d}-{p}", "split": "eval", "group": k, "input": s,
                         "persona": p, "persona_label": PERSONAS[p], "source": "hf_display_claims"})

    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n = collections.Counter(r["split"] for r in rows)
    print(f"문장 학습 {len(train_rows)} · 평가 {len(eval_rows)} → 쌍 {dict(n)} · {OUT.name}")


if __name__ == "__main__":
    main()
