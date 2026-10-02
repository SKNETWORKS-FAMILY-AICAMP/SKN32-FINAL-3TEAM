"""🔴 **평가셋이 판정 규칙을 고르지 못하게** — D-175 (2026-09-10).

⛔ 실측 사고. `dictionary.approved_terms()` 가 HF **전량**을 읽어, 봉인된 음성 평가
   60행이 「어떤 사전 항목을 `단독판정` 에서 뺄지」를 정하고 있었다.

       봉인 포함(종전)  단독판정 411종 → 적법 60행 오탐 **0행 (0.0%)**
       봉인 제외(지금)  단독판정 413종 → 적법 60행 오탐 **3행 (5.0%)**

   갈린 항목은 정확히 둘이다 —
       「항산화」        ⊂  「인체의 항산화능 증진에 도움을 줄 수 있음」
       「키성장에도움」   ⊂  「어린이 키성장에 도움을 줄 수 있음」

🚨 **D-174 의 문언은 지켜지고 있었다.** 이 둘은 사전의 `term` 이 아니라 `신뢰도` 칸에만
   영향을 준다. 사전 종수(536)가 안 변해서 아무도 못 봤다. **문언은 지키고 취지가 뚫린 자리다.**

★ 이 게이트는 **산출물 없이도 돈다.** tmp 로 입력을 지어 함수를 직접 부른다.
  ⛔ 산출물이 있을 때만 도는 검사는 「아무도 안 해도 아무것도 실패하지 않는」 검사다 (D-146) —
     실제로 2026-09-10 아침까지 `test_split.py` 의 누수 검사가 그렇게 skip 되고 있었다.
"""

from __future__ import annotations

import inspect
import json
import pathlib

import pytest

from preprocess import dictionary, split

pytestmark = pytest.mark.gate

#: 실제 사고를 낸 두 문장 + 대조군 하나. 🚨 값을 바꾸지 않는다 — 재현 사례다.
_ROWS = [
    {"기능성내용": "항산화에 도움을 줄 수 있음"},
    {"기능성내용": "어린이 키성장에 도움을 줄 수 있음"},
    {"기능성내용": "체지방 감소에 도움을 줄 수 있음"},
]


@pytest.fixture
def hf(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    p = tmp_path / "mfds_hf_labels.jsonl"
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in _ROWS) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(split, "HF", p)
    return split.approved_docs()


def test_승인문구는_train_만_읽는다(hf: list[dict]) -> None:
    """🔴 봉인된 적법 문장이 사전 설계에 들어오면 안 된다."""
    assert len(hf) == 3, "표본이 바뀌었다 — 이 게이트의 전제가 깨진다"
    train = {hf[0]["doc_id"], hf[1]["doc_id"]}
    sealed = hf[2]["문구"][0]

    got = dictionary.approved_terms(train)

    assert sealed not in got, (
        f"🚨 봉인된 평가 문구 「{sealed}」가 사전 설계에 들어왔다.\n"
        "   이 코퍼스가 `적법중첩`/`단독판정` 을 정한다 — 시험지가 채점 규칙을 고르게 된다 (D-175)."
    )
    assert len(got) == 2


def test_승인문구가_전량으로_되돌아가지_않았다() -> None:
    """⛔ 인자가 사라지면 **전량으로 되돌아간 것**이다. 그것이 원래 사고의 모양이다."""
    params = list(inspect.signature(dictionary.approved_terms).parameters)
    assert params == ["train"], (
        f"`approved_terms{tuple(params)}` — `train` 인자가 없어졌다.\n"
        "   전량을 읽으면 봉인된 음성 평가가 판정 규칙을 고른다 (D-175)."
    )


def test_반대_대조_봉인을_풀면_결과가_달라진다(hf: list[dict]) -> None:
    """🚨 **실패할 수 없는 단언이 아님을 스스로 보인다** (D-170).

    위 게이트가 진짜로 무언가를 막고 있는지 확인한다 — 전량과 train 이 같은 답을 내면
    이 검사는 아무것도 안 지키고 있는 것이다.
    """
    everything = {d["doc_id"] for d in hf}
    train = {hf[0]["doc_id"], hf[1]["doc_id"]}
    assert dictionary.approved_terms(everything) != dictionary.approved_terms(train), (
        "전량과 train 이 같은 답을 낸다 — 이 게이트는 실패할 수 없다 (D-170)."
    )


# ══════════════════════════════════════════════════════════════════════
#  🆕 2026-10-02 (D-311) — 정본 섭취 주의사항도 **train 만** 단독판정 심사의 재료다
# ══════════════════════════════════════════════════════════════════════

_CAUTION = [
    {"doc_id": "hfcau:a", "문구": ["고혈압 치료제 등 복용 시 전문가와 상담할 것"]},
    {"doc_id": "hfcau:b", "문구": ["당뇨병의 치료 및 예방에 사용될 수 없음"]},
]


@pytest.fixture
def caution(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    monkeypatch.setattr(split, "caution_docs", lambda: _CAUTION)
    return _CAUTION


def test_주의사항은_train_만_읽는다(caution: list[dict]) -> None:
    """🔴 봉인 문장이 「어느 항목을 단독판정에서 뺄지」를 정하면 안 된다 — 09-10 사고와 같은 자리 (D-175)."""
    got = dictionary.caution_terms({"hfcau:a"})
    assert got == ["고혈압 치료제 등 복용 시 전문가와 상담할 것"]
    assert dictionary.caution_terms({"hfcau:a", "hfcau:b"}) != got, (
        "전량과 train 이 같은 답을 낸다 — 이 게이트는 실패할 수 없다 (D-170)."
    )


def test_주의사항이_전량으로_되돌아가지_않았다() -> None:
    params = list(inspect.signature(dictionary.caution_terms).parameters)
    assert params == ["train"], f"`caution_terms{tuple(params)}` — `train` 인자가 없어졌다 (D-175)."


def test_주의사항에_나오는_단일_항목은_단독판정을_잃는다() -> None:
    """★ D-311 — 주장 아닌 정본 문장에 그대로 나오면 `비주장문맥`. 🔴 이름은 `적법중첩` 과 다르다(시제품이 다르게 읽는다)."""
    c = dictionary.confidence
    assert c([], ["질병_예방치료_표방"], ["고혈압치료제등복용시…"]) == "비주장문맥"
    assert c([], ["질병_예방치료_표방"], []) == "단일"
    # 순서 — 적법중첩 > 모호 > 비주장문맥
    assert c(["…도움을줄수있음"], ["건강기능식품_오인"], ["…"]) == "적법중첩"
    assert c([], ["거짓_과장", "소비자_기만"], ["…"]) == "모호"


def test_단독판정은_단일_뿐이다() -> None:
    """🔴 `build` 가 `단독판정 = (신뢰도 == 단일)` 로 쓴다 — 새 신뢰도 값이 생겨도 자격이 새지 않게 (D-311)."""
    src = inspect.getsource(dictionary.build)
    assert '"단독판정": conf == "단일"' in src
