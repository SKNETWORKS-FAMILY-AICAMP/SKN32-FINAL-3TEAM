"""scripts/experiment.py — 실험의 **분배 단위에 형식을 준다** (2026-09-12 밤 · D-94).

  uv run python -m scripts.experiment --check experiments/ksr_01.yaml

⛔ **무엇이 있었나** — D-94 가 *"넘기는 것은 `(모델, 하이퍼파라미터 조합)` 하나. 팀장이
   고정하는 것은 데이터 split · 시드 · 평가 스크립트 · 기록 포맷"* 이라 정했는데,
   **그 「하나」에 형식이 없었다.** 형식이 없으면 D-94 가 기각한 (b)로 되돌아간다 —

   > 트랙째 넘기면 각자 **다른 split · 다른 시드 · 다른 평가 스크립트**로 돌아온다.
   > 숫자는 다섯 개 나오는데 **비교가 불가능하다.** 그러면 실험이 아니라 다섯 개의 일화가 된다.

★ **그래서 파일을 두 층으로 가른다.**

    experiments/harness.<트랙>.yaml   팀장이 고정한다 — split · 시드 · 평가 지표 · 무변화 3회
    experiments/<이니셜>_<번호>.yaml   팀원이 채우는 **유일한 파일** — 모델과 하이퍼파라미터

  🔴 **harness 는 트랙마다 하나**다 (2026-09-12 밤 배정 개정). 인코더(T2)와 sLLM(T5)은
     split 도 평가 지표도 다르다 — 한 파일로 두면 「같은 조건」이 트랙을 건너 거짓이 된다.

  🔴 **팀원 설정은 harness 키를 덮지 못한다.** 주석이 아니라 검증기가 막는다 (D-117).
     그것이 이 모듈의 존재 이유다 — 「같은 조건」이 사람의 성실성이 아니라 코드가 된다.

🚨 **환경은 여기서 다루지 않는다.** MLflow Projects 는 `conda.yaml` 로 환경을 핀하는데
   우리는 `.python-version` + `uv.lock` + 이미지 태그가 이미 그 일을 한다 (D-87).
   둘을 다 두면 두 벌이 된다 (D-99) — **가져오는 것은 「타입과 기본값이 붙은 파라미터」뿐**이다.

⬜ **필드 목록은 아직 판정 대상이다** (병렬작업 계약 §8 ④) — 무엇을 팀원에게 **열고**
   무엇을 잠글지가 곧 D-94 의 「설정 하나」의 정의다. 여기 있는 것은 **모양**이고,
   `params` 의 허용 키는 팀장이 `harness.<트랙>.yaml` 에서 정한다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"

#: 🔴 **실험 분배 대상 트랙 셋.** 정본은 **기획서 8-5** 다 — 여기 뜻을 다시 적지 않는다 (D-54).
#:      T2 인코더 · T3 ML·리랭킹 · T5 생성·배달(sLLM LoRA)
#: ⛔ **T1·T4 는 실험이 아니다.** T1 은 데이터·거버넌스, T4 는 그래프·RAG 로 하이퍼파라미터를
#:    나눠 돌리는 종류가 아니다 — 넣으면 「설정 하나」의 뜻이 흐려진다 (D-94).
#: 🚨 2026-09-12 밤 정정 — 처음에 `T2`·`T3` 둘만 열었는데 **sLLM LoRA 는 T5 다**(기획서 8-5).
#:    트랙 번호를 기억에서 쓴 것이고, 배정이 들어오자마자 틀린 것이 드러났다 (D-100).
TRACKS = ("T2", "T3", "T5")


def harness_file(track: str) -> Path:
    """트랙별 harness. 🔴 **하나가 아니라 트랙마다 하나**다 (2026-09-12 밤).

    ⛔ 인코더(T2)와 sLLM(T5)은 **split 도 평가 지표도 다르다.** 한 파일로 두면
       「같은 조건」이 트랙을 건너 거짓이 된다 — D-94 가 막으려던 바로 그것이다.
    """
    return EXPERIMENTS / f"harness.{track}.yaml"


#: 🔴 **팀원이 못 바꾸는 키.** D-94 가 「팀장이 고정하는 것」이라 적은 넷이다.
#:    ⛔ 이 이름이 팀원 설정의 `params` 에 나타나면 거부한다 — 덮어쓰기가 아니라 **거부**다.
#:       조용히 무시하면 팀원은 자기가 준 값으로 돈 줄 안다 (D-220 fail-closed).
LOCKED = ("split_id", "seed", "eval_metric", "noise_runs")


class Harness(BaseModel):
    """팀장이 고정하는 것. 🚨 **이 파일이 없으면 실험을 시작하지 않는다.**

    ⛔ 기본값을 여기 박아 두지 않는다 — 안 정한 것을 정한 것처럼 만든다.
       D-94 의 마감이 **2W 말**이고, 늦으면 팀원 4명이 대기한다. 대기가 보이는 편이 낫다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 데이터 split 의 식별자. 🚨 지문이지 이름이 아니다 — 같은 이름 다른 내용이면 못 잡는다 (D-176)
    split_id: str = Field(min_length=1)
    seed: int
    #: 평가 지표 이름. 유형별 P/R/F1 중 무엇을 볼 것인가 (D-77 L1 ⑥)
    eval_metric: str = Field(min_length=1)
    #: 🚨 **무변화 3회** — 설정을 나눠 주기 **전에** 팀장이 돌려 폭을 잰다 (D-190).
    #:    ⛔ 폭을 모르면 다섯 개의 수를 못 읽는다. 1 이면 D-190 을 안 지키는 것이다
    noise_runs: int = Field(ge=3)
    #: 팀원이 `params` 에 쓸 수 있는 키. 🔴 **여기 없는 키는 거부한다** — 열고 잠그는 자리다
    allowed_params: list[str] = Field(min_length=1)


class ExperimentConfig(BaseModel):
    """팀원이 채우는 **유일한 파일**. 🚨 `extra="forbid"` — 모르는 키는 조용히 넘기지 않는다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 이니셜. 🚨 팀 명단을 여기 두 벌로 적지 않는다 — `docs/<이니셜>/` 이 이미 명단이다 (D-99)
    owner: str = Field(min_length=2, max_length=8)
    #: 🚨 실험 분배 대상 트랙만. 목록은 `TRACKS`, 뜻은 **기획서 8-5** 가 정본이다
    track: str

    #: 실험 이름 — MLflow run 이름이 된다. 같은 사람이 여럿 돌리면 번호로 가른다
    run: str = Field(min_length=1)
    #: HuggingFace 모델 id. 🚨 `revision` 을 같이 적는다 — 태그는 움직인다 (기획서 8-4 #9)
    base_model: str = Field(min_length=1)
    revision: str | None = None
    params: dict[str, int | float | str | bool] = Field(default_factory=dict)
    note: str = ""

    @field_validator("track")
    @classmethod
    def _track_is_an_experiment_track(cls, v: str) -> str:
        if v not in TRACKS:
            raise ValueError(
                f"track {v!r} 은 실험 분배 대상이 아니다 — {list(TRACKS)}\n"
                "  🚨 T1(데이터·거버넌스)·T4(그래프·RAG)는 하이퍼파라미터를 나눠 돌리는 종류가"
                " 아니다. 트랙의 뜻은 기획서 8-5 가 정본이다"
            )
        return v

    @field_validator("owner")
    @classmethod
    def _owner_is_a_team_member(cls, v: str) -> str:
        """🔴 `docs/<이니셜>/` 이 있어야 한다 — **명단을 코드에 두 벌로 적지 않는다** (D-99)."""
        if not (ROOT / "docs" / v).is_dir():
            known = sorted(p.name for p in (ROOT / "docs").iterdir() if p.is_dir())
            raise ValueError(
                f"owner {v!r} 의 문서 폴더가 없다 — `docs/{v}/`.\n"
                f"  🚨 이니셜은 브랜치명·문서 폴더명과 **같은 철자**다 (사실원장 「팀」).\n"
                f"  지금 있는 폴더: {known}"
            )
        return v

    @model_validator(mode="after")
    def _no_locked_keys(self) -> ExperimentConfig:
        """🔴 팀장이 고정한 것을 팀원 설정이 **덮지 못한다** (D-94 의 핵심)."""
        bad = sorted(set(self.params) & set(LOCKED))
        if bad:
            raise ValueError(
                f"팀장이 고정한 값은 설정에 적지 않는다 — {bad}\n"
                "  🚨 split·시드·평가·무변화 횟수가 사람마다 다르면 **다섯 개의 일화**가 된다 (D-94).\n"
                "  바꿔야 할 이유가 있으면 `experiments/harness.<트랙>.yaml` 을 팀장이 고친다"
            )
        return self


def load_harness(track: str, path: Path | None = None) -> Harness:
    """트랙의 harness. 🚨 없으면 **멈춘다** — 「없음」이 기본값으로 집계되지 않게 (D-220)."""
    path = path or harness_file(track)
    if not path.exists():
        raise SystemExit(
            f"🔴 {track} harness 가 없다 — {path}\n"
            "  D-94: split · 시드 · 평가 지표 · 기록 포맷은 **팀장이 고정한다.**\n"
            "  🚨 마감은 2W 말이다. 늦으면 담당자가 그대로 대기한다.\n"
            "  ⬜ 값은 아직 판정 대상이다 — 지어내지 않는다 (병렬작업 계약 §8 ④)"
        )
    return Harness(**yaml.safe_load(path.read_text(encoding="utf-8")))


def load_config(path: Path, harness: Harness) -> ExperimentConfig:
    """팀원 설정 하나. 🚨 harness 가 **연 키만** 쓸 수 있다."""
    cfg = ExperimentConfig(**yaml.safe_load(path.read_text(encoding="utf-8")))
    unknown = sorted(set(cfg.params) - set(harness.allowed_params))
    if unknown:
        raise ValueError(
            f"harness 가 안 연 하이퍼파라미터다 — {unknown}\n"
            f"  열린 것: {sorted(harness.allowed_params)}\n"
            "  🚨 여는 것은 팀장 판정이다 — `experiments/harness.<트랙>.yaml` 의 `allowed_params`"
        )
    return cfg


def mlflow_params(cfg: ExperimentConfig, harness: Harness) -> dict[str, Any]:
    """MLflow 에 그대로 올릴 params. 🚨 **고정분과 설정분을 한 표에 같이 올린다** (D-94).

    ⛔ 고정분을 안 올리면 나중에 표를 보고 「같은 조건이었나」를 물을 수 없다 —
       기록이 비교 가능해지는 것은 **분모가 같이 적혀 있을 때**다 (D-178).
    """
    return {
        "owner": cfg.owner,
        "track": cfg.track,
        "base_model": cfg.base_model,
        "revision": cfg.revision or "",
        **{f"hp.{k}": v for k, v in sorted(cfg.params.items())},
        **{f"fixed.{k}": getattr(harness, k) for k in LOCKED},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="실험 설정 검사 — 돌리기 전에 형식을 본다")
    ap.add_argument("--check", required=True, help="experiments/<이니셜>_<번호>.yaml")
    args = ap.parse_args()

    raw = yaml.safe_load(Path(args.check).read_text(encoding="utf-8")) or {}
    track = str(raw.get("track", ""))
    if track not in TRACKS:
        print(
            f"🔴 track 이 없거나 실험 트랙이 아니다 — {track!r} (열린 것: {list(TRACKS)})",
            file=sys.stderr,
        )
        return 1
    harness = load_harness(track)
    try:
        cfg = load_config(Path(args.check), harness)
    except Exception as e:  # noqa: BLE001 — 사람이 읽을 메시지로 바꿔 낸다 (D-51)
        print(f"🔴 설정이 계약을 안 지킨다 — {args.check}\n{e}", file=sys.stderr)
        return 1

    print(f"  ✅ {cfg.owner} · {cfg.track} · {cfg.run} — {cfg.base_model}")
    print(f"  📄 harness {harness_file(cfg.track).name}")
    print(f"  🔒 고정 {', '.join(f'{k}={getattr(harness, k)}' for k in LOCKED)}")
    print(f"  🎛  설정 {cfg.params or '(없음 — 기본값으로 돈다)'}")
    print("  🚨 MLflow params 로 올라갈 것 —")
    for k, v in mlflow_params(cfg, harness).items():
        print(f"       {k} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
