"""계약 표면 스냅샷 — **계약이 조용히 바뀌면 잡는다** (2026-09-12 밤 · D-124 · 병렬작업 계약 §6).

⛔ **무엇이 있었나** — `app/contracts.py` 를 고치면 **아무 데도 안 튀었다.** 팀원 4인이
   그 모양을 보고 화면·BFF 를 붙이고 있는데, 필드를 지우거나 필수를 선택으로 바꿔도
   `pytest` 는 초록이고 **화면은 런타임에 깨진다.**
   🚨 D-124 가 *"계약을 잘못 고정하면 4명이 함께 고치게 된다"* 라 적은 그 자리다.

★ **그래서 표면을 커밋해 두고 대조한다.** 계약 변경이 「조용한 수정」이 아니라
  **스냅샷을 같이 고치는 커밋**이 되고, 그 커밋이 리뷰 대상이 된다.

🚨 **`openapi.json` 을 통째로 스냅샷하지 않는다.** 그 파일은 FastAPI·pydantic 판이 올라가면
   우리가 아무것도 안 고쳐도 바뀐다 — **버전 잡음이 계약 변경으로 읽히면 게이트가 죽는다.**
   여기서 뜨는 것은 우리가 정한 것뿐이다: **enum 값 · 모델의 필드 이름과 타입과 필수 여부 ·
   라우트 경로와 메서드.**

고치는 법 — 계약을 의도적으로 바꿨으면 스냅샷을 다시 쓰고 **같은 커밋에** 올린다.

    COPYLANE_WRITE_SURFACE=1 uv run pytest tests/test_contract_surface.py -q
"""

from __future__ import annotations

import enum
import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app import contracts

SNAPSHOT = Path(__file__).resolve().parent / "contract_surface.json"


def _type_name(t: Any) -> str:
    """타입을 **판 버전에 안 흔들리는 문자열**로. 🚨 `repr` 을 그대로 쓰지 않는다."""
    if t is None:
        return "None"
    if isinstance(t, type):
        return f"{t.__module__}.{t.__qualname__}"
    return str(t).replace("<class '", "").replace("'>", "")


def surface() -> dict[str, Any]:
    """지금 코드가 내는 계약 표면. 🚨 **목록을 손으로 적지 않는다** — 모듈을 훑는다 (D-99)."""
    enums: dict[str, list[str]] = {}
    models: dict[str, dict[str, str]] = {}
    for name in dir(contracts):
        obj = getattr(contracts, name)
        if not isinstance(obj, type):
            continue
        if issubclass(obj, enum.Enum) and obj.__module__ == contracts.__name__:
            enums[name] = sorted(m.value for m in obj)
        elif (
            issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == contracts.__name__
        ):
            models[name] = {
                f: f"{'req' if info.is_required() else 'opt'} {_type_name(info.annotation)}"
                for f, info in sorted(obj.model_fields.items())
            }

    from app.api import app  # noqa: PLC0415 — fastapi 는 이 검사에서만 든다

    # 🚨 FastAPI 가 스스로 붙이는 문서 라우트는 **뺀다.** 우리가 안 고쳐도 판이 올라가면
    #    바뀔 수 있는 자리라, 넣어 두면 **버전 잡음이 계약 변경으로 읽힌다** — 게이트가 죽는다.
    _BUILTIN = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
    routes = sorted(
        [r.path, sorted(m for m in r.methods if m != "HEAD")]
        for r in app.routes
        if getattr(r, "methods", None) and r.path not in _BUILTIN
    )
    return {"enums": enums, "models": models, "routes": routes}


def _dump(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@pytest.mark.gate
def test_계약_표면이_스냅샷과_같다() -> None:
    """🔴 다르면 **계약이 바뀐 것**이다 — 스냅샷을 같은 커밋에 올린다.

    ⛔ 여기서 실패했다고 스냅샷만 갱신하고 넘어가지 않는다. 4명이 그 모양에 붙어 있다 —
       **무엇이 바뀌었는지가 리뷰 대상**이다 (D-124).
    """
    now = surface()
    if os.environ.get("COPYLANE_WRITE_SURFACE"):
        SNAPSHOT.write_text(_dump(now), encoding="utf-8")
        pytest.skip("🚨 스냅샷을 다시 썼다 — 변경 내용을 확인하고 같은 커밋에 올린다")

    assert SNAPSHOT.exists(), (
        f"🔴 계약 표면 스냅샷이 없다 — {SNAPSHOT.name}\n"
        "   만드는 법: COPYLANE_WRITE_SURFACE=1 uv run pytest tests/test_contract_surface.py -q"
    )
    want = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    # 🚨 어디가 달라졌는지를 **이름으로** 낸다 — 통째 diff 는 사람이 못 읽는다 (D-51)
    diffs: list[str] = []
    for kind in ("enums", "models"):
        for name in sorted(set(want[kind]) | set(now[kind])):
            a, b = want[kind].get(name), now[kind].get(name)
            if a != b:
                diffs.append(f"  {kind}.{name}\n    스냅샷 {a}\n    지금   {b}")
    if want["routes"] != now["routes"]:
        diffs.append(f"  routes\n    스냅샷 {want['routes']}\n    지금   {now['routes']}")

    assert not diffs, (
        "🔴 계약 표면이 스냅샷과 다르다 — 화면·BFF 넷이 이 모양에 붙어 있다 (D-124).\n"
        + "\n".join(diffs)
        + "\n  의도한 변경이면: COPYLANE_WRITE_SURFACE=1 uv run pytest "
        "tests/test_contract_surface.py -q  → 스냅샷을 **같은 커밋에** 올린다"
    )


@pytest.mark.gate
def test_이_게이트가_실제로_변경을_잡는다() -> None:
    """🚨 **통과만 하는 게이트는 게이트가 아니다** — 집행계약이 세 번 적은 문장이다.

    D-203 이 「게이트가 잡는다는 것을 음성 픽스처로 잰다」를 규칙으로 올렸다. 여기서 잰다 —
    필드를 지우고, 필수를 선택으로 바꾸고, enum 값을 더한 셋을 **실제로 떨어뜨려 본다.**
    """
    base = surface()

    def differs(mutated: dict[str, Any]) -> bool:
        return _dump(mutated) != _dump(base)

    import copy  # noqa: PLC0415

    # ① 필드를 지운다
    m = copy.deepcopy(base)
    name, fields = next(iter(m["models"].items()))
    fields.pop(next(iter(fields)))
    assert differs(m), "🔴 필드 삭제를 못 잡는다"

    # ② 필수를 선택으로 바꾼다
    m = copy.deepcopy(base)
    for fields in m["models"].values():
        for f, v in fields.items():
            if v.startswith("req "):
                fields[f] = v.replace("req ", "opt ", 1)
                break
        else:
            continue
        break
    assert differs(m), "🔴 필수→선택 변경을 못 잡는다"

    # ③ enum 값을 더한다 — 화면이 모르는 값을 받는 자리다
    m = copy.deepcopy(base)
    next(iter(m["enums"].values())).append("새값")
    assert differs(m), "🔴 enum 값 추가를 못 잡는다"

    # ④ 라우트를 더한다
    m = copy.deepcopy(base)
    m["routes"].append(["/새경로", ["POST"]])
    assert differs(m), "🔴 라우트 추가를 못 잡는다"
