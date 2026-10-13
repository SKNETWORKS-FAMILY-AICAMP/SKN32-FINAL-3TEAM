"""모델 잠금 — 앱은 잠금(`models.lock.json`)의 채택 · 되돌림 판만 올린다 (🆕 2026-10-13 · D-333).

⛔ 카드 17 의 F1 최대 판과 채택 판은 가중치가 같고 문턱 파일만 달랐다 — 가중치 지문으로는 가를 수 없었고,
   판을 바꾼 사실이 기기 환경 변수에만 있었다(D-205 의 구멍). 이 파일이 그 둘을 지킨다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import encoder as enc
from app import model_lock as ml
from scripts import model_lock as cli

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[1]


def _folder(base: Path, name: str, scheme: str = '{"a": 1}', extra: dict | None = None) -> Path:
    d = base / name
    d.mkdir()
    (d / "config.json").write_text("{}", encoding="utf-8")
    (d / "label_scheme.json").write_text(scheme, encoding="utf-8")
    (d / "model.safetensors").write_bytes(b"\x00" * 64)
    for k, v in (extra or {}).items():
        (d / k).write_text(v, encoding="utf-8")
    return d


def _registry(tmp_path: Path) -> Path:
    p = tmp_path / "registry.yaml"
    p.write_text(
        "models:\n"
        "  kcbert_base:\n    use: {U1: allow, U2: deny, U3: deny, U4: allow}\n"
        "  closed_base:\n    use: {U1: allow, U2: deny, U3: deny, U4: deny}\n",
        encoding="utf-8",
    )
    return p


# ── 저장소의 잠금 ───────────────────────────────────────────────


def test_잠금_파일이_형식대로다() -> None:
    data = ml.load()
    assert ml.validate(data) == []
    assert set(data["roles"]) <= set(ml.ROLES)


def test_잠금의_베이스는_레지스트리에_있고_배포_용도가_열려_있다() -> None:
    """D-23 — 모델 가중치도 G-게이트 대상이다. 파인튜닝 판은 베이스의 라이선스 · 배포 용도에 묶인다."""
    data = ml.load()
    bad = {
        name: why
        for name, b in data["bundles"].items()
        if (why := cli.registry_problem(b["base"])) is not None
    }
    assert not bad, f"🔴 레지스트리와 안 맞는 잠금의 판: {bad}"


def test_화면은_인코더_표지_글자를_직접_적지_않는다() -> None:
    """표지가 `+enc:` → `+encb:` 로 바뀌면서 화면만 조용히 「사용 안 함」이 될 자리였다 — 필터(`encoder_ran`)로 본다 (D-99)."""
    for p in (ROOT / "app" / "templates").rglob("*.html"):
        assert "+enc" not in p.read_text(encoding="utf-8"), (
            f"🔴 {p.name} 이 표지 글자를 직접 적는다"
        )


# ── 판 지문 · 대조 ──────────────────────────────────────────────


def test_문턱_파일만_달라도_판_지문이_다르고_드라이브_부산물은_뺀다(tmp_path: Path) -> None:
    a = _folder(tmp_path, "a", '{"t": 0.5}')
    b = _folder(tmp_path, "b", '{"t": 0.65}')
    c = _folder(tmp_path, "c", '{"t": 0.5}', extra={"desktop.ini": "[.ShellClassInfo]"})
    fa, fb, fc = ml.scan(a)[0], ml.scan(b)[0], ml.scan(c)[0]
    assert fa["model.safetensors"] == fb["model.safetensors"]  # 가중치는 같다
    assert ml.bundle_sha(fa) != ml.bundle_sha(fb)  # 판은 다르다
    assert ml.bundle_sha(fa) == ml.bundle_sha(fc)  # desktop.ini 는 판의 일부가 아니다


def _lock(tmp_path: Path) -> tuple[dict, Path, Path]:
    adopted = _folder(tmp_path, "adopted", '{"t": 0.65}')
    old = _folder(tmp_path, "old", '{"t": 0.5}')
    data = cli.empty()
    data["bundles"]["adopted"] = ml.entry(adopted, "encoder", "kcbert_base", "D-331")
    data["bundles"]["old"] = ml.entry(old, "encoder", "kcbert_base", "D-331")
    data["roles"]["encoder"] = {"adopted": "adopted", "rollback": ["old"]}
    assert ml.validate(data) == []
    return data, adopted, old


def test_내용으로_판을_가른다_이름은_보지_않는다(tmp_path: Path) -> None:
    data, adopted, old = _lock(tmp_path)
    renamed = tmp_path / "다른-이름"
    adopted.rename(renamed)
    assert ml.match(renamed, "encoder", data).status == ml.ADOPTED
    assert ml.match(old, "encoder", data).status == ml.ROLLBACK


def test_하위_폴더나_다른_문턱이면_잠금_밖이다(tmp_path: Path) -> None:
    """오늘 사고의 자리 — 공유 폴더가 바로 아래와 `seed49/` 에 문턱 파일을 둘 두고 있었다."""
    data, adopted, _ = _lock(tmp_path)
    (adopted / "seed49").mkdir()
    m = ml.match(adopted, "encoder", data)
    assert m.status == ml.OUTSIDE and "하위 폴더" in m.why
    f1 = _folder(tmp_path, "f1max", '{"t": 0.525}')
    m = ml.match(f1, "encoder", data)
    assert m.status == ml.OUTSIDE and "label_scheme.json" in m.why


def test_이름_크기_대조는_해시_없이_어긋남을_낸다(tmp_path: Path) -> None:
    data, adopted, _ = _lock(tmp_path)
    assert ml.quick(adopted, "adopted", data) == ""
    (adopted / "tokenizer.json").write_text("{}", encoding="utf-8")
    assert "더 있는 파일" in ml.quick(adopted, "adopted", data)


# ── 앱의 문 ─────────────────────────────────────────────────────


@pytest.fixture
def app_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data, adopted, old = _lock(tmp_path)
    monkeypatch.setattr(ml, "load", lambda path=None: data)
    monkeypatch.setattr(enc, "_UNLOCKED_OK", False)
    enc.lock_match.cache_clear()
    enc.bundle_mark.cache_clear()
    yield data, adopted, old
    enc.lock_match.cache_clear()
    enc.bundle_mark.cache_clear()


def test_앱은_잠금_밖_판을_올리지_않는다(app_lock, tmp_path: Path) -> None:
    _, adopted, old = app_lock
    assert enc.checked_dir(adopted).status == ml.ADOPTED
    assert enc.checked_dir(old).status == ml.ROLLBACK  # 되돌림은 설정 하나다 (D-331)
    stray = _folder(tmp_path, "stray", '{"t": 0.3}')
    with pytest.raises(enc.EncoderUnavailable, match="잠금"):
        enc.checked_dir(stray)


def test_도구는_잠금_밖도_올리되_앱의_기본은_닫혀_있다(app_lock, tmp_path: Path) -> None:
    stray = _folder(tmp_path, "stray", '{"t": 0.3}')
    enc.permit_unlocked()
    assert enc.checked_dir(stray).status == ml.OUTSIDE


def test_응답_표지는_판_지문이고_옛_표지는_인코더로_세지_않는다(app_lock) -> None:
    _, adopted, _ = app_lock
    mark = enc.bundle_mark(adopted)
    assert mark == ml.bundle_sha(ml.scan(adopted)[0]) and len(mark) == 12
    assert enc.ran(f"rule-0.3.0-dict{enc.JUDGED_BY_MARK}{mark}")
    assert not enc.ran("rule-0.3.0-dict+enc:abcdef123456")  # 가중치 지문 — 판을 가르지 못한다
    assert not enc.ran(None)


def test_잠금을_못_읽으면_판을_모른다로_멈춘다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path=None):  # noqa: ANN001, ANN202
        raise ml.LockError("잠금 파일이 없다")

    monkeypatch.setattr(ml, "load", broken)
    enc.lock_match.cache_clear()
    d = _folder(tmp_path, "x")
    with pytest.raises(enc.EncoderUnavailable):
        enc.checked_dir(d)
    enc.bundle_mark.cache_clear()
    assert enc.bundle_mark(d) == "지문없음"
    enc.lock_match.cache_clear()
    enc.bundle_mark.cache_clear()


def test_설정값이_판_이름이면_models_아래를_본다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "판A").mkdir()
    monkeypatch.setattr(ml, "MODELS", tmp_path)
    monkeypatch.setenv(enc.ENV_MODEL_DIR, "판A")
    assert enc.configured_dir() == tmp_path / "판A"
    monkeypatch.setenv(enc.ENV_MODEL_DIR, "")
    assert enc.configured_dir() is None


# ── 잠금 쓰기 ───────────────────────────────────────────────────


def test_채택하면_옛_채택은_되돌림으로_가고_같은_이름의_다른_내용은_거절한다(
    tmp_path: Path,
) -> None:
    reg, lock = _registry(tmp_path), tmp_path / "models.lock.json"
    v10 = _folder(tmp_path, "v10", '{"t": 0.5}')
    c17 = _folder(tmp_path, "c17", '{"t": 0.65}')
    cli.add(
        v10,
        role="encoder",
        as_="adopted",
        base="kcbert_base",
        decision="D-331",
        path=lock,
        registry=reg,
    )
    cli.add(
        c17,
        role="encoder",
        as_="adopted",
        base="kcbert_base",
        decision="D-331",
        path=lock,
        registry=reg,
    )
    data = json.loads(lock.read_text(encoding="utf-8"))
    assert data["roles"]["encoder"] == {"adopted": "c17", "rollback": ["v10"]}
    (c17 / "label_scheme.json").write_text('{"t": 0.7}', encoding="utf-8")
    with pytest.raises(ml.LockError, match="고치지 않는다"):
        cli.add(
            c17,
            role="encoder",
            as_="adopted",
            base="kcbert_base",
            decision="D-331",
            path=lock,
            registry=reg,
        )


def test_레지스트리_밖이거나_배포가_닫힌_베이스는_올리지_않는다(tmp_path: Path) -> None:
    reg, lock = _registry(tmp_path), tmp_path / "models.lock.json"
    d = _folder(tmp_path, "d")
    for base in ("없는_베이스", "closed_base"):
        with pytest.raises(ml.LockError):
            cli.add(
                d,
                role="encoder",
                as_="adopted",
                base=base,
                decision="D-331",
                path=lock,
                registry=reg,
            )
    assert not lock.exists()


def test_근거_D_번호가_없으면_쓰지_않는다(tmp_path: Path) -> None:
    reg, lock = _registry(tmp_path), tmp_path / "models.lock.json"
    d = _folder(tmp_path, "d")
    with pytest.raises(ml.LockError, match="D 번호"):
        cli.add(
            d,
            role="encoder",
            as_="adopted",
            base="kcbert_base",
            decision="채택",
            path=lock,
            registry=reg,
        )


def test_하위_폴더가_있는_폴더는_판으로_올리지_않는다(tmp_path: Path) -> None:
    reg, lock = _registry(tmp_path), tmp_path / "models.lock.json"
    d = _folder(tmp_path, "d")
    (d / "seed49").mkdir()
    with pytest.raises(ml.LockError, match="하위 폴더"):
        cli.add(
            d,
            role="encoder",
            as_="adopted",
            base="kcbert_base",
            decision="D-331",
            path=lock,
            registry=reg,
        )


# ── 설정 ────────────────────────────────────────────────────────


def test_모델_판과_생성_스위치는_런처_설정이고_키가_아니다() -> None:
    from collect import env

    names = {
        "COPYLANE_MODEL_DIR",
        "COPYLANE_COPYGEN",
        "COPYLANE_COPYGEN_MODEL",
        "COPYLANE_SLLM_URL",
    }
    assert names <= set(env.SETTINGS)
    assert not names & set(env.KEYS)
