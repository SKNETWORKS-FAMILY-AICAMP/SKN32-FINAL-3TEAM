"""판정 경로의 외부 호출 0 — 집행계약 doctor 16 · D-77 L4 · D-78 · 🆕 2026-10-15 (D-344 ⑦).

★ 「판정 경로」 = `app/graph.py` 에서 import 로 닿는 **우리 모듈**(`app` · `collect` · `preprocess`)이다.
   그 모듈들이 네트워크 클라이언트나 화면 쪽 라우터(`app.routers` — 카피 생성 GPT · sLLM 호출이 산다)를 **직접** import 하면 실패한다.
   🚨 카피 생성의 GPT 호출(D-332)은 판정 경로 밖이다 — 그래서 `app.routers` 가 경계다. 판정 코어는 라우터를 부르지 않는다.
⛔ 라이브러리 안쪽까지는 따라가지 않는다 — `sentence_transformers` 가 안에서 `requests` 를 끌어온다. 그 라이브러리가 **요청을
   내지 않게** 하는 것은 `local_files_only` 다(아래 둘째 시험). LangSmith 추적은 `app.graph._require_tracing_off` 가 막는다.
🔴 경계 예외는 한 곳이다 — `collect.http`. `.env` 를 읽는 `collect.env` 가 import 만 하고(`app/settings.py` 지연 import) 판정 경로는
   그 함수를 부르지 않는다. 다른 판정 모듈이 `collect.http` 를 import 하면 실패한다.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRST_PARTY = ("app", "collect", "preprocess")
START = "app.graph"
#: 판정 경로 모듈이 직접 import 하면 안 되는 것 — 네트워크 클라이언트 · 소켓 · 화면 쪽 라우터
FORBIDDEN = (
    "openai",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "urllib.request",
    "http.client",
    "socket",
    "app.routers",
)
#: 경계 예외 — 모듈 → 그것을 import 해도 되는 유일한 모듈
BOUNDARY = {"collect.http": "collect.env"}


def _path(mod: str) -> pathlib.Path | None:
    p = ROOT / (mod.replace(".", "/") + ".py")
    if p.exists():
        return p
    p = ROOT / mod.replace(".", "/") / "__init__.py"
    return p if p.exists() else None


def _imports(p: pathlib.Path) -> set[str]:
    """함수 안의 지연 import 까지 — `ast.walk` 가 모듈 전체를 돈다. 상대 import 는 쓰지 않는 저장소다."""
    out: set[str] = set()
    for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module)
            out.update(f"{n.module}.{a.name}" for a in n.names)
    return out


def _closure() -> dict[str, set[str]]:
    """판정 경로 모듈 → 그 모듈의 import. 경계 예외는 들어가지 않는다."""
    seen: dict[str, set[str]] = {}
    todo = [START]
    while todo:
        m = todo.pop()
        if m in seen or m in BOUNDARY:
            continue
        p = _path(m)
        if p is None:
            continue
        seen[m] = _imports(p)
        todo += [i for i in seen[m] if i.split(".")[0] in FIRST_PARTY and _path(i)]
    return seen


def _hits(name: str) -> bool:
    return any(name == f or name.startswith(f + ".") for f in FORBIDDEN)


def test_판정_경로_모듈은_네트워크_클라이언트와_라우터를_import_하지_않는다() -> None:
    graph = _closure()
    assert len(graph) > 5, (
        f"판정 경로 모듈을 못 찾았다 — {sorted(graph)}"
    )  # 빈 집합이 통과로 세지지 않게 (D-220)
    bad = sorted((m, i) for m, deps in graph.items() for i in deps if _hits(i))
    assert not bad, (
        f"판정 경로가 외부 호출 층을 import 한다 — {bad}\n"
        "   판정 경로의 외부 네트워크 요청은 0 이다(D-77 L4 · 집행계약 doctor 16). 생성 쪽 호출은 app.routers 에 둔다(D-332)"
    )


def test_경계_예외는_한_모듈만_import_한다() -> None:
    graph = _closure()
    for mod, only in BOUNDARY.items():
        users = sorted(
            m
            for m, deps in graph.items()
            if mod in deps or any(d.startswith(mod + ".") for d in deps)
        )
        assert users == [only], f"{mod} 를 import 하는 판정 모듈 — {users} (허용은 {only} 하나)"


def test_판정_경로의_검색_임베딩은_캐시에서만_올린다(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import retrieve as rt
    from app.settings import ALLOWED_MODELS

    got: dict = {}

    class Fake:
        def __init__(self, model_id: str, **kw: object) -> None:
            got.update(kw, model_id=model_id)

        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 1.0] for _ in texts]

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=Fake)
    )
    model_id = sorted(ALLOWED_MODELS)[0]
    monkeypatch.setattr(rt, "_model_cache", {})
    assert rt.encode(model_id, "면역력") == [0.0, 1.0]
    assert got.get("local_files_only") is True, got
    assert got.get("trust_remote_code") is False, got


def test_내려받기는_적재_도구만_한다() -> None:
    """`scripts/embed.py` 는 모델을 받는 자리다 — 기본 인자에는 `local_files_only` 가 없다."""
    from app.settings import ALLOWED_MODELS, load_kwargs

    model_id = sorted(ALLOWED_MODELS)[0]
    assert "local_files_only" not in load_kwargs(model_id)
    assert load_kwargs(model_id, local_only=True)["local_files_only"] is True


def test_진단은_검색_임베딩_캐시가_없으면_노랑이고_내려받지_않는다(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import huggingface_hub

    from scripts import doctor

    asked: list[tuple[str, str]] = []

    def fake(repo: str, name: str, **_k: object) -> None:
        asked.append((repo, name))

    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", fake)
    assert doctor._check_embed_cache() == 0  # 노랑 — 앱은 어휘 검색으로 돈다
    out = capsys.readouterr().out
    assert "🟡 검색 임베딩" in out and "embed --check" in out
    assert {n for _r, n in asked} == set(doctor.EMBED_CACHE_FILES)
