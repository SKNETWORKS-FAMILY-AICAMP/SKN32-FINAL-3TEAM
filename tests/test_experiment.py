"""실험 분배 단위 — **팀장이 고정한 것을 팀원이 못 바꾸는가** (2026-09-12 밤 · D-94).

D-94 가 (b)「트랙째 위임」을 기각한 이유가 *"각자 다른 split · 다른 시드 · 다른 평가
스크립트로 돌아온다 … 실험이 아니라 다섯 개의 일화가 된다"* 였다.
🚨 그 기각이 **문서에만** 있으면 지켜지지 않는다 (D-117). 여기서 검사로 만든다.

⬜ **필드 목록 자체는 판정 대상이다** — 무엇을 열고 무엇을 잠글지는 팀장이 정한다
   (병렬작업 계약 §8 ④). 이 파일이 보는 것은 **잠근 것이 실제로 잠기는가**다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts import experiment as ex

_OK = {
    "owner": "ohb",
    "track": "T2",
    "run": "kcbert-base-lr2e5",
    "base_model": "beomi/kcbert-base",
    "params": {"lr": 2e-5, "epochs": 3},
}
_HARNESS = ex.Harness(
    split_id="sha256:0000",
    seed=42,
    eval_metric="macro_f1",
    noise_runs=3,
    allowed_params=["lr", "epochs"],
)


@pytest.mark.gate
@pytest.mark.parametrize("locked", ex.LOCKED)
def test_고정값을_팀원_설정이_못_덮는다(locked: str) -> None:
    """🔴 **D-94 의 핵심.** 조용히 무시하면 팀원은 자기 값으로 돈 줄 안다 — 거부한다 (D-72)."""
    with pytest.raises(ValidationError) as e:
        ex.ExperimentConfig(**{**_OK, "params": {**_OK["params"], locked: 1}})
    assert "D-94" in str(e.value)


@pytest.mark.gate
def test_모르는_키를_조용히_넘기지_않는다() -> None:
    """⛔ `extra="forbid"` — 오타 난 키가 무시되면 **안 먹은 설정으로 돌고도 초록**이다."""
    with pytest.raises(ValidationError):
        ex.ExperimentConfig(**{**_OK, "lr": 2e-5})  # params 밖에 적은 오타


@pytest.mark.gate
def test_harness_가_안_연_하이퍼파라미터는_거부한다() -> None:
    """🚨 여는 것은 팀장 판정이다 — 팀원이 새 손잡이를 만들지 못한다."""
    cfg_ok = ex.ExperimentConfig(**_OK)
    assert cfg_ok.params  # 열린 둘은 통과한다

    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "x.yaml"
        p.write_text(
            "owner: ohb\ntrack: T2\nrun: r\nbase_model: m\nparams:\n  warmup: 100\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="harness 가 안 연"):
            ex.load_config(p, _HARNESS)


@pytest.mark.gate
def test_팀_명단을_코드에_두_벌로_두지_않는다() -> None:
    """🔴 `owner` 는 `docs/<이니셜>/` 이 있어야 통과한다 — 명단의 정본은 디스크다 (D-99).

    ⛔ 이니셜 목록을 코드에 적으면 사실원장 「팀」 표와 두 벌이 되고, 사람이 바뀌면 갈린다.
    """
    with pytest.raises(ValidationError) as e:
        ex.ExperimentConfig(**{**_OK, "owner": "zzz"})
    assert "docs/zzz" in str(e.value)


@pytest.mark.gate
def test_무변화_3회_미만을_harness_가_거부한다() -> None:
    """🚨 D-190 — 아무것도 안 바꾸고 세 번 돌린 폭보다 작은 변화는 개선이 아니다.

    ⛔ `noise_runs: 1` 을 허용하면 D-190 이 절차로만 남는다.
    """
    with pytest.raises(ValidationError):
        ex.Harness(
            split_id="s", seed=1, eval_metric="macro_f1", noise_runs=1, allowed_params=["lr"]
        )


@pytest.mark.gate
def test_기록에_고정분이_같이_올라간다() -> None:
    """⛔ 고정분이 안 올라가면 나중에 표를 보고 **「같은 조건이었나」를 물을 수 없다** (D-178)."""
    params = ex.mlflow_params(ex.ExperimentConfig(**_OK), _HARNESS)
    for k in ex.LOCKED:
        assert f"fixed.{k}" in params, f"🔴 고정분 {k} 가 기록에 안 올라간다"
    assert params["hp.lr"] == 2e-5
    assert params["owner"] == "ohb"


def test_harness_가_없으면_멈춘다(tmp_path) -> None:  # noqa: ANN001 — pytest 픽스처
    """🚨 게이트가 아니다 — `experiments/harness.yaml` 은 아직 없는 것이 정상이다.

    ⬜ **팀장이 2W 말까지 채운다** (D-94). 없을 때 조용히 기본값으로 도는 것만 막는다.
    """
    with pytest.raises(SystemExit, match="harness 가 없다"):
        ex.load_harness(tmp_path / "없다.yaml")
