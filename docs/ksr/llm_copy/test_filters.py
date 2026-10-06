"""코드 필터 · 흐름 시험 — `uv run pytest docs/ksr/llm_copy -q` (저장소 기본 시험 경로 밖이다)."""

from __future__ import annotations

import pathlib
import sys
from collections import Counter

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pipeline  # noqa: E402
from branches import BRANCHES, PLACEHOLDER  # noqa: E402
from filters import Inputs, check, render  # noqa: E402
from judge import Judged, NoJudge  # noqa: E402
from llm import FakeLLM, parse, user_prompt  # noqa: E402

CREAM = Inputs(
    name="촉촉 수분크림", kind="크림", features=("끈적임 없이 산뜻",), ingredients=("히알루론산",)
)
COS = BRANCHES["cos_no"]


# 설계 요약 §4 의 예시 표 그대로
@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("끈적임 없이 산뜻하게 스며드는 촉촉 수분크림", None),
        ("히알루론산 5% 함유, 72시간 보습", "number"),
        ("세라마이드가 피부 장벽을 채워 줍니다", "ingredient"),
        ("피부과 테스트를 마친 순한 크림", "cert"),
        ("지친 피부를 재생시키는 수분크림", "forbidden"),
        ("업계 최고의 수분크림을 만나 보세요", "superlative"),
        ("수분크림", "format"),
    ],
)
def test_설계_예시(text: str, reason: str | None) -> None:
    got = check(text, CREAM, COS, [])
    assert (got[0] if got else None) == reason


def test_입력에_있는_것은_지어낸_것이_아니다() -> None:
    tofu = Inputs(
        name="바른손 두부", kind="두부", features=("국산 콩 100%",), certs=("HACCP 인증 시설 제조",)
    )
    assert (
        check("HACCP 인증 시설에서 만든 국산 콩 100% 두부", tofu, BRANCHES["food_yes"], []) is None
    )
    assert (
        check("HACCP 인증 시설에서 만든 국산 콩 두부", CREAM, BRANCHES["food_no"], [])[0] == "cert"
    )


def test_거의_같은_문구는_한_번만() -> None:
    first = "끈적임 없이 산뜻하게 스며드는 촉촉 수분크림"
    assert (
        check("끈적임 없이 산뜻하게 스며드는 촉촉한 수분크림", CREAM, COS, [first])[0]
        == "duplicate"
    )


def test_고정_문구는_코드가_끼운다() -> None:
    hf = BRANCHES["hf_yes"]
    inp = Inputs(name="데일리바이옴", kind="캡슐", fixed="장 건강에 도움을 줄 수 있음")
    assert check("출근 전 한 캡슐로 챙기는 습관", inp, hf, [])[0] == "fixed"
    ok = f"출근 전 한 캡슐, {PLACEHOLDER}"
    assert check(ok, inp, hf, []) is None
    assert render(ok, inp) == "출근 전 한 캡슐, 장 건강에 도움을 줄 수 있음"
    assert check(f"{PLACEHOLDER} 변비 해소까지", inp, hf, [])[0] == "forbidden"


def test_탈락_문구_원문은_프롬프트에_안_들어간다() -> None:
    prompt = user_prompt(CREAM, COS, 20, ["보관한 문구"], Counter(number=6, forbidden=2))
    assert "입력에 없는 수치 6건" in prompt
    assert "보관한 문구" in prompt
    assert "72시간" not in prompt


def test_응답_파싱() -> None:
    assert parse('{"candidates":[{"angle":"감각","text":" 산뜻한 크림 "},{"text":""},"x"]}') == [
        {"angle": "감각", "text": "산뜻한 크림"}
    ]
    assert parse("JSON 아님") == []


def test_흐름_세_개를_채우면_멈춘다() -> None:
    res = pipeline.run(CREAM, COS, FakeLLM(), NoJudge())
    assert res.status == "ok"
    assert len(res.picked) == 3
    assert len(res.rounds) == 1
    assert {d["reason"] for d in res.dropped} >= {
        "number",
        "ingredient",
        "cert",
        "superlative",
        "forbidden",
    }


def test_흐름_못_채우면_탐색_실패() -> None:
    class Reject(NoJudge):
        def judge(self, text, branch):  # noqa: ANN001, ANN201
            return Judged(False, "hold", "unjudged")

    res = pipeline.run(CREAM, COS, FakeLLM(), Reject())
    assert res.status == "search_failed"
    assert len(res.rounds) == pipeline.MAX_ROUNDS
    assert res.picked == []
    more = pipeline.run(CREAM, COS, FakeLLM(), NoJudge(), carry=res)
    assert len(more.rounds) > pipeline.MAX_ROUNDS


def test_예시를_그대로_돌려주면_탈락() -> None:
    class Echo(FakeLLM):
        def generate(self, inputs, branch, n, kept, rejected):  # noqa: ANN001, ANN201
            return [{"angle": "감각", "text": t} for t in branch.good]

    res = pipeline.run(CREAM, COS, Echo(), NoJudge(), rounds=1)
    assert res.kept == []
    assert {d["reason"] for d in res.dropped} == {"duplicate"}


def test_예시는_시험_입력과_다른_제품이다() -> None:
    import json

    cases = json.loads((pathlib.Path(__file__).parent / "cases.json").read_text("utf-8"))
    for c in cases:
        b = BRANCHES[c["branch"]]
        for g in b.good + tuple(t for t, _ in b.bad):
            for key in ("name", "kind"):
                if c["inputs"].get(key):
                    assert c["inputs"][key] not in g, (c["id"], g)


def test_부분_글자_오탐() -> None:
    # 「감기는 샴푸 거품」의 「감기」는 질병이 아니다
    assert check("뻑뻑함 없이 부드럽게 감기는 샴푸 거품", CREAM, COS, []) is None
    got = check("감기를 예방하는 따뜻한 유자차 한 잔", CREAM, BRANCHES["food_no"], [])
    assert got[0] == "forbidden"


def test_모델을_섞으면_후보마다_모델이_남는다() -> None:
    from llm import MixLLM

    class One(FakeLLM):
        def __init__(self, name: str, texts: list[str]) -> None:
            super().__init__()
            self.model, self.texts = name, texts

        def generate(self, inputs, branch, n, kept, rejected):  # noqa: ANN001, ANN201
            assert n == 10
            return [{"angle": "감각", "text": t} for t in self.texts]

    a = One("a", ["세안 후 가볍게 바르는 산뜻한 크림", "자기 전 듬뿍 발라도 가벼운 마무리"])
    b = One("b", ["메이크업 전에도 밀리지 않는 가벼움", "손끝에 닿는 순간 느껴지는 수분감"])
    res = pipeline.run(CREAM, COS, MixLLM([a, b]), NoJudge(), rounds=1)
    assert [k.model for k in res.kept] == ["a", "b", "a", "b"]
    assert {k.model for k in res.picked} == {"a", "b"}


def test_분기_대상_문구만으로도_돈다() -> None:
    inp = Inputs.from_dict(
        {"target": "야근이 잦은 30대 직장인", "phrase": "끈적임 없이 산뜻한 수분크림"}
    )
    prompt = user_prompt(inp, COS, 20, [], Counter())
    assert "제품명:" not in prompt
    assert "이용자가 적은 문구: 끈적임 없이 산뜻한 수분크림" in prompt
    assert "원료 이야기" not in prompt
    assert "사용 장면 · 감각 · 대상 3가지" in prompt
    assert check("야근 후에도 끈적임 없이 산뜻하게 바르는 수분크림", inp, COS, []) is None
    assert pipeline.run(inp, COS, FakeLLM(), NoJudge()).status == "ok"
    with pytest.raises(ValueError, match="하나는 있어야"):
        Inputs.from_dict({"target": "직장인"})
