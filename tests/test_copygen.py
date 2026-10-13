"""카피 생성 엔진(`app/routers/copygen`) — GPT 생성 → 코드 필터 → 인코더 판정 · 🆕 2026-10-13 (ksr).

🚨 **여기서는 밖을 부르지 않는다** — 생성 모델 · 인코더를 대역으로 갈아 끼워 흐름과 화면만 본다. 문구 품질은 재지 않는다.
   켜는 스위치는 `tests/conftest.py` 가 꺼 둔다(`COPYLANE_COPYGEN=off`). 문구 · 제품 이름은 여기서 지어낸 것이다 (D-175).
"""

from __future__ import annotations

import io
import urllib.error
from collections import Counter

import pytest

from app.routers import copygen
from app.routers.copygen import filters, judge, llm, pipeline
from app.routers.copygen.branches import BRANCHES, PLACEHOLDER

FIXED = "지어낸 인정 문구에 도움을 줄 수 있음"


class _FakeLLM:
    """라운드마다 정해 둔 후보를 낸다. 받은 프롬프트 재료를 적어 둔다."""

    model = "fake"

    def __init__(self, rounds: list[list[tuple[str, str]]]) -> None:
        self.rounds = rounds
        self.usage: Counter[str] = Counter()
        self.calls: list[dict] = []

    def generate(self, inputs, branch, n, kept, rejected):  # noqa: ANN001, ANN201
        self.calls.append(
            {
                "prompt": llm.user_prompt(inputs, branch, n, kept, rejected),
                "kept": list(kept),
                "rejected": dict(rejected),
            }
        )
        i = len(self.calls) - 1
        return [
            {"angle": a, "text": t} for a, t in (self.rounds[i] if i < len(self.rounds) else [])
        ]


class _FakeJudge:
    """글자에 「걸림」이 있으면 탈락 — 인코더 자리의 대역."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def judge(self, text, branch):  # noqa: ANN001, ANN201
        self.seen.append(text)
        return judge.Judged("걸림" not in text, "대역", "")


GOOD = [
    ("사용 장면", "아침 식탁에 올리는 지어낸 곡물바 한 조각"),
    ("감각", "고소한 향이 먼저 닿는 바삭한 한입이에요"),
    ("대상", "출근길 가방에 넣어 두는 간식으로 좋아요"),
    ("제품 사실", "낱개로 포장해 들고 다니기 편한 곡물바"),
]


def _inputs(**over) -> filters.Inputs:  # noqa: ANN003
    base = {"name": "지어낸 곡물바", "kind": "곡물바", "features": ["고소하고 바삭한 식감"]}
    return filters.Inputs.from_dict({**base, **over})


# ── 흐름 ─────────────────────────────────────────────────────────────


def test_필터와_판정을_지난_후보에서_서로_다른_셋을_고른다() -> None:
    gen = _FakeLLM(
        [
            [
                *GOOD,
                ("감각", "업계 1위의 바삭함을 담은 곡물바"),  # 비교 · 최상급
                ("제품 사실", "식이섬유 12g 을 담은 곡물바 한 조각"),  # 입력에 없는 수치
                ("감각", "면역을 채워 주는 고소한 곡물바 한입"),  # 분기 금지어
                ("사용 장면", "걸림 낱말이 든 지어낸 곡물바 문구예요"),  # 판정 탈락
            ]
        ]
    )
    j = _FakeJudge()
    res = pipeline.run(_inputs(), BRANCHES["food_no"], gen, j)
    assert res.status == "ok"
    assert len(res.picked) == pipeline.WANT
    assert len(res.rounds) == 1  # 셋이 모이면 더 부르지 않는다
    assert res.reasons() == Counter(superlative=1, number=1, forbidden=1, judge=1)
    # 코드 필터에서 떨어진 것은 판정기에 가지 않는다 — 판정 호출을 아낀다
    assert len(j.seen) == len(GOOD) + 1


def test_셋을_못_채우면_탐색_실패다_기준을_낮추지_않는다() -> None:
    gen = _FakeLLM([[GOOD[0], ("감각", "걸림 낱말이 든 지어낸 곡물바 문구예요")], [GOOD[1]], []])
    res = pipeline.run(_inputs(), BRANCHES["food_no"], gen, _FakeJudge())
    assert res.status == "search_failed"
    assert [k.text for k in res.picked] == [GOOD[0][1], GOOD[1][1]]
    assert len(res.rounds) == pipeline.MAX_ROUNDS


def test_다음_라운드_프롬프트에는_탈락_사유와_건수만_간다() -> None:
    """🚨 탈락 문구 원문은 넘기지 않는다 — 걸린 표현이 예시가 되어 되돌아오지 않게 (설계 요약 §5-3)."""
    bad = "면역을 채워 주는 고소한 곡물바 한입"
    gen = _FakeLLM([[GOOD[0], ("감각", bad)], [GOOD[1], GOOD[2]]])
    pipeline.run(_inputs(), BRANCHES["food_no"], gen, _FakeJudge())
    second = gen.calls[1]
    assert second["rejected"] == {"forbidden": 1}
    assert bad not in second["prompt"]
    assert GOOD[0][1] in second["prompt"]  # 뽑힌 것은 겹치지 않게 알려 준다


def test_고정_문구는_모델에_보내지_않고_코드가_끼운다() -> None:
    gen = _FakeLLM(
        [
            [
                ("사용 장면", f"점심 먹고 물과 함께 삼켜요, {PLACEHOLDER}"),
                ("감각", f"{PLACEHOLDER} — 작은 정제라 삼키기 편해요"),
                ("제품 사실", f"가방에 넣어 다니는 휴대용 통. {PLACEHOLDER}"),
                ("대상", f"목넘김이 편한 {PLACEHOLDER}"),  # 이음새 — 꾸미는 말 바로 뒤
                ("감각", "자리표시자를 빼먹은 지어낸 문구예요"),  # 고정 문구 자리 없음
            ]
        ]
    )
    j = _FakeJudge()
    res = pipeline.run(
        _inputs(name="지어낸 정제", kind="정제", features=["작은 정제"], fixed=FIXED),
        BRANCHES["hf_yes"],
        gen,
        j,
    )
    assert FIXED not in gen.calls[0]["prompt"]
    assert all(FIXED in k.text and PLACEHOLDER not in k.text for k in res.picked)
    assert res.reasons() == Counter(seam=1, fixed=1)
    # 판정은 고정 문구를 뺀 글자로 한다 — 인정 문구 자체가 후보로 걸리지 않게
    assert all(FIXED not in t and PLACEHOLDER not in t for t in j.seen)


# ── 판정 · 생성 모델의 가장자리 ───────────────────────────────────────


def test_인코더_후보가_서거나_뒤가_잘리면_탈락이다(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from app import encoder as enc  # noqa: PLC0415
    from app.contracts import Violation  # noqa: PLC0415

    labels = list(Violation)
    cand = enc.EncoderCandidate(labels[0], 0.8, 0.5)
    # 문턱이 유형마다 다르다 — 확률은 둘째가 높아도 문턱에 더 가까운 것은 첫째다. 1 을 넘는 문턱(대기 라벨)은 거리에서 뺀다
    scheme = SimpleNamespace(thresholds={labels[0]: 0.3, labels[1]: 0.8, labels[2]: 1.01})
    scores = {labels[0]: 0.15, labels[1]: 0.2, labels[2]: 0.9}
    preds = {
        "깨끗": enc.EncoderPrediction(scores=scores, candidates=()),
        "후보": enc.EncoderPrediction(scores={}, candidates=(cand,)),
        "잘림": enc.EncoderPrediction(scores={}, candidates=(), truncated=True),
    }
    monkeypatch.setattr(enc, "configured_dir", lambda: Path("지어낸-모델-폴더"))
    monkeypatch.setattr(
        enc, "encoder_at", lambda _d: SimpleNamespace(predict=preds.__getitem__, scheme=scheme)
    )
    j = judge.EncoderJudge()
    clean = j.judge("깨끗", BRANCHES["food_no"])
    assert clean.passed is True
    assert (clean.closeness, clean.top, clean.top_prob, clean.top_threshold) == (
        0.5,
        labels[0].value,
        0.15,
        0.3,
    )
    assert j.judge("후보", BRANCHES["food_no"]).passed is False
    assert j.judge("잘림", BRANCHES["food_no"]).passed is False  # 못 본 것을 통과로 세지 않는다


def test_인코더가_없으면_생성하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import encoder as enc  # noqa: PLC0415

    monkeypatch.setattr(enc, "configured_dir", lambda: None)
    with pytest.raises(copygen.CopyGenOff):
        judge.EncoderJudge()


def test_스위치를_켜지_않으면_키가_있어도_꺼짐이다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "has_key", lambda: True)
    monkeypatch.setenv(copygen.ENV_SWITCH, "")
    assert copygen.off_reason() is not None
    with pytest.raises(copygen.CopyGenOff):
        copygen.generate("food_no", {"name": "지어낸 곡물바"})


def test_생성_모델_오류는_응답_본문을_싣지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """🚨 오류 응답에는 보낸 프롬프트가 되돌아올 수 있다 — 상태 코드만 남긴다. 키도 메시지에 없다."""
    monkeypatch.setattr(llm, "_api_key", lambda: "지어낸-키-값")

    def boom(req, timeout=None):  # noqa: ANN001, ANN202, ARG001
        raise urllib.error.HTTPError(
            llm.URL, 429, "Too Many", None, io.BytesIO("되돌아온 프롬프트".encode())
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    with pytest.raises(copygen.CopyGenError) as e:
        llm.OpenAIChat("지어낸-모델").generate(_inputs(), BRANCHES["food_no"], 5, [], Counter())
    assert "429" in str(e.value)
    assert "되돌아온 프롬프트" not in str(e.value)
    assert "지어낸-키-값" not in str(e.value)


def test_깨진_응답은_빈_후보다() -> None:
    assert llm.parse("JSON 이 아니다") == []
    assert llm.parse('{"candidates": [{"angle": "감각", "text": " 문구 "}, {"text": ""}, 3]}') == [
        {"angle": "감각", "text": "문구"}
    ]


# ── 표 맞춤 ──────────────────────────────────────────────────────────


def test_엔진의_분기표는_화면_분기와_시험_코드의_표와_같다() -> None:
    """표가 셋이다 — 화면(`_GEN_BRANCHES`) · 엔진(`copygen.branches`) · 시험 코드(`docs/ksr/llm_copy`). 갈리면 여기서 걸린다."""
    import importlib.util  # noqa: PLC0415
    import pathlib  # noqa: PLC0415
    import sys  # noqa: PLC0415

    from app import premise as pm  # noqa: PLC0415
    from app.routers.user import _GEN_BRANCHES  # noqa: PLC0415

    assert set(_GEN_BRANCHES) == set(BRANCHES)
    for key, b in _GEN_BRANCHES.items():
        assert b["label"] == BRANCHES[key].label, key
        assert pm.PREMISE_CATEGORY[b["premise"]].value == BRANCHES[key].category, key
        assert (b.get("needs") == "fixed") == BRANCHES[key].needs_fixed, key

    path = pathlib.Path(__file__).resolve().parents[1] / "docs/ksr/llm_copy/branches.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("_ksr_branches_copygen", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        for key, b in BRANCHES.items():
            src = mod.BRANCHES[key]
            for f in ("label", "category", "allowed", "rules", "forbidden", "good", "bad"):
                assert getattr(b, f) == getattr(src, f), (key, f)
    finally:
        del sys.modules[spec.name]


# ── 화면 ─────────────────────────────────────────────────────────────


def _post(**data: str):  # noqa: ANN202
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    base = {"category": "food", "cert": "no", "age": "30", "sex": "f", "name": "지어낸 곡물바"}
    return TestClient(app).post("/u/generate", data={**base, **data})


def _wire(monkeypatch: pytest.MonkeyPatch, gen: _FakeLLM) -> None:
    monkeypatch.setattr(copygen, "off_reason", lambda: None)
    monkeypatch.setattr(copygen._llm, "make", lambda: gen)
    monkeypatch.setattr(copygen, "EncoderJudge", _FakeJudge)


def test_화면은_엔진이_꺼져_있으면_까닭을_적고_후보를_그리지_않는다() -> None:
    body = _post().text
    assert "카피 생성 엔진을 켜 두지 않았어요" in body
    assert "가짜 결과를 만들지 않아요" in body
    assert "AI 광고 생성 →" not in body
    assert "OpenAI" not in body  # 꺼진 환경에서는 「밖으로 보낸다」를 적지 않는다


def test_화면은_만든_후보를_그리고_광고_생성으로_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = "걸림 낱말이 든 지어낸 곡물바 문구예요"
    gen = _FakeLLM([[*GOOD, ("감각", bad)]])
    _wire(monkeypatch, gen)
    body = _post(features="고소하고 바삭한 식감", target="지어낸 직장인").text
    assert "후보 3개" in body
    assert body.count("AI 광고 생성 →") == 3
    assert 'name="prompt" value="' + GOOD[0][1] + '"' in body
    assert ">위반 후보 못 찾음</span>" in body
    assert "사람 확인 전" not in body
    assert "판정엔진 미통과 1건" in body
    assert bad not in body  # 탈락 문구 원문은 그리지 않는다
    assert "OpenAI" in body  # 켜진 환경에서는 무엇이 밖으로 나가는지 적는다
    # 고른 나이대 · 성별과 적은 대상이 프롬프트의 「대상」으로 간다
    assert "대상: 30대 여성 · 지어낸 직장인" in gen.calls[0]["prompt"]


def test_화면은_탐색_실패를_후보_수와_함께_적는다(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, _FakeLLM([[GOOD[0]]]))
    body = _post().text
    assert "탐색 실패 — 3개 중 1개를 찾았어요" in body
    assert body.count("AI 광고 생성 →") == 1
    assert "기준을 낮추거나 억지로 채우지 않아요" in body


def test_화면은_호출_실패의_까닭을_그리지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(_FakeLLM):
        def generate(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
            raise copygen.CopyGenError("HTTP 500 지어낸 속사정")

    _wire(monkeypatch, Boom([]))
    body = _post().text
    assert "문구를 만들다 실패했어요" in body
    assert "지어낸 속사정" not in body
    assert "AI 광고 생성 →" not in body


def test_화면은_입력이_틀리면_엔진을_부르지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    gen = _FakeLLM([GOOD])
    _wire(monkeypatch, gen)
    body = _post(category="hf", cert="yes").text  # 인정 문구가 비었다
    assert "원문 그대로 적어 주세요" in body
    assert gen.calls == []


# ── 광고 생성으로 넘기기 — 분기와 인정 · 심사 문구가 같이 간다 (2026-10-13) ─────────


def _compose_judge_spy(monkeypatch: pytest.MonkeyPatch, how: str = "unsure") -> list[tuple]:
    """광고 생성의 판정 호출을 적어 둔다 — (판정에 들어간 글자, 품목)."""
    from types import SimpleNamespace  # noqa: PLC0415

    from app.contracts import SentenceJudgment  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    extra = {
        "unsure": {"verdict": "hold", "hold_reason": "low_conf"},
        "ng": {"verdict": "unjudged"},
    }[how]
    seen: list[tuple] = []

    def fake(text: str, product=None):  # noqa: ANN001, ANN202
        seen.append((text, product))
        s = SentenceJudgment.model_validate({"sent_id": "s0", "text": text, **extra})
        return "ok", SimpleNamespace(sentences=[s])

    monkeypatch.setattr(user_router, "_core_judge", fake)
    return seen


def test_화면의_후보_카드는_분기와_인정_문구를_들고_넘어간다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen = _FakeLLM(
        [
            [
                ("사용 장면", f"점심 먹고 물과 함께 삼켜요, {PLACEHOLDER}"),
                ("감각", f"{PLACEHOLDER} — 작은 정제라 삼키기 편해요"),
                ("제품 사실", f"가방에 넣어 다니는 휴대용 통. {PLACEHOLDER}"),
            ]
        ]
    )
    _wire(monkeypatch, gen)
    body = _post(category="hf", cert="yes", name="지어낸 정제", fixed=FIXED).text
    assert body.count('name="branch" value="hf_yes"') == 3
    # 후보 카드 셋 + 「더 탐색하기」 폼 하나
    assert body.count(f'name="fixed" value="{FIXED}"') == 4
    # 이미 보여 준 문구는 자리표시자가 든 글자로 들고 다닌다 — 인정 문구를 여러 벌 싣지 않는다
    assert body.count('name="shown" value="') == 3
    assert f'name="shown" value="점심 먹고 물과 함께 삼켜요, {PLACEHOLDER}"' in body


def test_광고_생성은_넘어온_품목으로_판정하고_인정_문구는_뺀다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.contracts import Category  # noqa: PLC0415

    seen = _compose_judge_spy(monkeypatch)
    text = f"점심 먹고 물과 함께 삼켜요, {FIXED}"
    c = TestClient(app)
    first = c.post(
        "/u/compose", data={"carry": "1", "prompt": text, "branch": "hf_yes", "fixed": FIXED}
    ).text
    assert 'name="branch" value="hf_yes"' in first
    assert "이용자가 적은 값이고 확인되지 않았어요" in first
    body = c.post(
        "/u/compose",
        data={"ad_format": "배너", "prompt": text, "branch": "hf_yes", "fixed": FIXED},
    ).text
    judged, product = seen[-1]
    assert judged == "점심 먹고 물과 함께 삼켜요,"
    assert (product.category, product.has_recognized_function) == (Category.건기식, True)
    m = re.search(r'id="de-data">(.*?)</script>', body, re.DOTALL)
    draft = json.loads(m.group(1))
    # 인정 문구가 든 문구는 통째로 얹는다 — 편집기의 칸 판정도 같은 분기 · 같은 인정 문구로 돈다
    assert draft["copy"] == [{"text": text, "unsure": True}]
    assert (draft["branch"], draft["fixed"]) == ("hf_yes", FIXED)

    r = c.post("/u/compose/judge", json={"text": text, "branch": "hf_yes", "fixed": FIXED})
    assert r.json()["state"] == "unsure"
    assert seen[-1][0] == "점심 먹고 물과 함께 삼켜요,"


def test_인정_문구가_필요_없는_분기에서는_인정_문구를_빼지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⛔ 아무 문구나 「인정 문구」라며 판정에서 빼지 못한다 — 인정 분기가 아니면 전부 판정한다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415
    from app.contracts import Category  # noqa: PLC0415

    seen = _compose_judge_spy(monkeypatch)
    text = f"고소한 곡물바 한 조각, {FIXED}"
    c = TestClient(app)
    for branch in ("food_no", "없는분기", ""):
        c.post(
            "/u/compose",
            data={"ad_format": "배너", "prompt": text, "branch": branch, "fixed": FIXED},
        )
        assert seen[-1][0] == text, branch
    assert seen[0][1].category is Category.식품  # 품목은 넘긴다
    assert seen[1][1] is None and seen[2][1] is None  # 모르는 분기 · 직접 입력은 품목 없이
    # 인정 문구를 고쳐 쓴 문구도 전부 판정한다 — 글자 그대로일 때만 뺀다
    c.post(
        "/u/compose",
        data={
            "ad_format": "배너",
            "prompt": "삼켜요, 확실한 도움",
            "branch": "hf_yes",
            "fixed": FIXED,
        },
    )
    assert seen[-1][0] == "삼켜요, 확실한 도움"


# ── 보수 · 균형 · 공격 (2026-10-13) ─────────────────────────────────────


def _kept(text: str, angle: str, closeness: float) -> pipeline.Kept:
    return pipeline.Kept(text, angle, 0, "대역", "", closeness, "거짓_과장", closeness / 2, 0.5)


def test_셋은_문턱에서_먼_것_가운데_가까운_것이고_각도가_겹치지_않는다() -> None:
    kept = [
        _kept("아침 식탁에 올리는 지어낸 곡물바 한 조각", "사용 장면", 0.10),
        _kept("아침 식탁에 올려 두는 지어낸 곡물바 한 조각", "사용 장면", 0.15),
        _kept("고소한 향이 먼저 닿는 바삭한 한입이에요", "감각", 0.40),
        _kept("아침 식탁에서 먹는 지어낸 곡물바 한 조각이에요", "사용 장면", 0.45),
        _kept("출근길 가방에 넣어 두는 간식으로 좋아요", "대상", 0.80),
        _kept("아침 식탁에 올리는 곡물바 한 조각을 지어냈어요", "사용 장면", 0.90),
    ]
    picked = pipeline.pick(list(reversed(kept)))  # 들어온 순서에 기대지 않는다
    assert [k.tier for k in picked] == list(pipeline.TIERS)
    assert [k.closeness for k in picked] == [0.10, 0.40, 0.80]
    assert len({k.angle for k in picked}) == 3
    # 고르지 않은 것에는 이름이 없다
    assert sum(1 for k in kept if k.tier) == 3


def test_구간에_다른_각도가_없으면_구간을_지키고_닮은_정도를_양보한다() -> None:
    kept = [
        _kept("아침 식탁에 올리는 지어낸 곡물바 한 조각", "사용 장면", 0.10),
        _kept("고소한 향이 먼저 닿는 바삭한 한입이에요", "사용 장면", 0.50),
        _kept("출근길 가방에 넣어 두는 간식으로 좋아요", "사용 장면", 0.90),
    ]
    picked = pipeline.pick(kept)
    assert [k.closeness for k in picked] == [0.10, 0.50, 0.90]
    assert [k.tier for k in picked] == list(pipeline.TIERS)


def test_셋을_못_채우면_이름을_붙이지_않는다() -> None:
    picked = pipeline.pick([_kept("문구 하나", "감각", 0.7), _kept("문구 둘", "대상", 0.2)])
    assert [k.closeness for k in picked] == [0.2, 0.7]
    assert [k.tier for k in picked] == ["", ""]


def test_화면은_셋의_이름을_적고_문턱_수치는_카드에_적지_않는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Scored(_FakeJudge):
        scores = iter((0.2, 0.5, 0.9, 0.6))

        def judge(self, text, branch):  # noqa: ANN001, ANN201
            c = next(self.scores)
            return judge.Judged(True, "대역", "", c, "거짓_과장", c / 2, 0.5)

    gen = _FakeLLM([GOOD])
    monkeypatch.setattr(copygen, "off_reason", lambda: None)
    monkeypatch.setattr(copygen._llm, "make", lambda: gen)
    monkeypatch.setattr(copygen, "EncoderJudge", Scored)
    body = _post(features="고소하고 바삭한 식감").text
    for name in pipeline.TIERS:
        assert f"<h3>{name}</h3>" in body
    # 문턱 수치는 카드에 적지 않는다 — 이용자가 읽을 수 없는 값이다 (10-13 권소라)
    assert "문턱의 20%" not in body and "/ 문턱 0.5" not in body
    assert "통과한 후보 4개가 안전 ↔ 주의 어디쯤인지 보기" in body
    assert "문턱" not in body  # 이용자 화면에 「문턱」이라는 말을 쓰지 않는다
    assert "소구력은 재지 않아요" in body


# ── 더 탐색하기 · 생성 중 표시 (2026-10-13) ─────────────────────────────


def test_둘째_라운드부터도_인정_문구는_모델에_가지_않는다() -> None:
    """🔴 「이미 뽑힌 문구」로 되돌려 보내는 글자는 인정 문구를 끼우기 전의 것이다 — 종전에는 끼운 뒤의 글자가 나갔다."""
    gen = _FakeLLM(
        [
            [("사용 장면", f"점심 먹고 물과 함께 삼켜요, {PLACEHOLDER}")],
            [("감각", f"{PLACEHOLDER} — 작은 정제라 삼키기 편해요")],
            [("제품 사실", f"가방에 넣어 다니는 휴대용 통. {PLACEHOLDER}")],
        ]
    )
    res = pipeline.run(
        _inputs(name="지어낸 정제", kind="정제", features=["작은 정제"], fixed=FIXED),
        BRANCHES["hf_yes"],
        gen,
        _FakeJudge(),
    )
    assert len(res.picked) == 3
    assert all(FIXED in k.text and FIXED not in k.raw for k in res.picked)
    for call in gen.calls:
        assert FIXED not in call["prompt"]
    assert f"점심 먹고 물과 함께 삼켜요, {PLACEHOLDER}" in gen.calls[1]["prompt"]


def test_더_탐색하기는_보여_준_문구를_빼고_만든다(monkeypatch: pytest.MonkeyPatch) -> None:
    shown = [t for _, t in GOOD[:3]]
    fresh = [
        ("사용 장면", "주말 나들이 도시락 옆에 하나 넣어 가요"),
        ("감각", "씹을수록 구수한 곡물 향이 올라와요"),
        ("제품 사실", "서랍에 두고 꺼내 먹기 좋은 낱개 포장"),
    ]
    # 첫 후보는 이미 보여 준 것과 거의 같다 — 중복으로 떨어져야 한다
    gen = _FakeLLM([[("사용 장면", shown[0] + "."), *fresh]])
    _wire(monkeypatch, gen)
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    data = [
        ("category", "food"),
        ("cert", "no"),
        ("age", "all"),
        ("sex", "all"),
        ("name", "지어낸 곡물바"),
        ("more", "1"),
        *(("shown", t) for t in shown),
    ]
    from urllib.parse import urlencode  # noqa: PLC0415

    body = (
        TestClient(app)
        .post(
            "/u/generate",
            content=urlencode(data),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        .text
    )
    assert "더 탐색 1번째" in body
    for t in shown:
        assert f"<p>{t}</p>" not in body  # 보여 준 것을 다시 내지 않는다
        assert t in gen.calls[0]["prompt"]  # 모델에는 「이미 뽑힌 문구」로 알려 준다
    for _, t in fresh:
        assert f"<p>{t}</p>" in body
    assert "보관분 · 이전 후보와 거의 같음 1건" in body
    # 다음 폼은 여섯을 들고 간다 · 다음은 2번째
    assert body.count('name="shown" value="') == 6
    assert 'name="more" value="2"' in body
    assert "다른 문구 더 탐색하기 (2/3)" in body


def test_더_탐색하기는_세_번까지다(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, _FakeLLM([GOOD]))
    first = _post().text
    assert "다른 문구 더 탐색하기 (1/3)" in first
    _wire(monkeypatch, _FakeLLM([GOOD]))
    last = _post(more="3").text
    assert "더 탐색 3번째" in last
    assert "다른 문구 더 탐색하기" not in last
    assert "더 탐색하기는 3번까지예요" in last
    for bad in ("4", "0", "많이"):
        assert _post(more=bad).status_code == 422, bad


def test_생성_폼은_생성_중_표시를_갖고_있다() -> None:
    """가운뎃점 넷 + 「문구 생성 중입니다」 — 처음에는 숨겨 두고 `user_wait.js` 가 제출 때 보인다."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.api import app  # noqa: PLC0415

    c = TestClient(app)
    body = c.get("/u/generate").text
    assert 'id="gen-form" method="post" action="/u/generate" data-wait-form' in body
    assert (
        '<p class="gn-wait" data-wait hidden role="status"><i>·</i><i>·</i><i>·</i><i>·</i> 문구 생성 중입니다</p>'
        in body
    )
    assert '<script src="/static/user_wait.js" defer></script>' in body
    assert c.get("/static/user_wait.js").status_code == 200
