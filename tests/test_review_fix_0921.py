"""2026-09-21 전수 재검토 고침 — 기존 테스트가 못 잡던 결함 중 규칙 파일 옆에 둘 자리가 없는 것.

🚨 **게이트가 아니다** — 파일은 tmp 로, 명령은 기록기로 돈다. 네트워크·postgres 없음.
   마스킹(C1·C2)은 `test_mask.py` · `test_derived_manifest.py`, 원문 저장(I6·I7)은 `test_raw_inbox.py`,
   `moved`(I9)는 `test_missing.py` 에 있다.
"""

from __future__ import annotations

import pathlib

import pytest


# ── I8 — `--limit` 으로 일부만 받아도 「수집함」으로 찍던 것 ─────────────────────
@pytest.mark.parametrize(
    ("saved", "partial", "want"), [(3, True, False), (0, False, False), (3, False, True)]
)
def test_수집_완료는_다_받았고_새로_저장했을_때만_찍는다(monkeypatch, saved, partial, want) -> None:
    from collect import registry

    marked: list[str] = []
    monkeypatch.setattr(registry, "mark_collected", marked.append)
    assert registry.mark_if_complete("x", saved=saved, partial=partial) is want
    assert marked == (["x"] if want else [])


def test_수집기는_완료_표시를_한_곳에서_정한다() -> None:
    """🚨 D-99 — 규칙이 수집기마다 손으로 쓰여 한 곳만 `--limit` 을 막았다. 수집기가 `mark_collected` 를 직접 부르지 않는다.
    ⛔ 예외 — `ingest.cmd_register`(사람이 받아 온 것 · `--limit` 이 없다 · 게이트가 그 호출을 요구한다)."""
    root = pathlib.Path(__file__).resolve().parents[1] / "collect"
    direct = [
        f.name
        for f in root.glob("*.py")
        if f.name not in {"registry.py", "ingest.py", "probe.py"}
        and "registry.mark_collected(" in f.read_text(encoding="utf-8")
    ]
    assert not direct, f"🔴 완료 표시를 직접 찍는다 — `registry.mark_if_complete` 로: {direct}"


def test_collected_at_을_바꿀_때_다음_줄을_먹지_않는다(tmp_path, monkeypatch) -> None:
    """🔴 ⛔ `collected_at:\\s*\\S+` 는 값이 비면 줄을 넘어 `reviewed_by` 를 먹었다."""
    from collect import registry

    ledger = tmp_path / "review.yaml"
    ledger.write_text("\nsrc:\n  collected_at:\n  reviewed_by: kim\n\n", encoding="utf-8")
    monkeypatch.setattr(registry, "LEDGER", ledger)
    monkeypatch.setattr(registry, "spec", lambda sid: {})
    monkeypatch.setattr(registry.subprocess, "run", lambda *a, **k: None)
    registry.mark_collected("src")
    text = ledger.read_text(encoding="utf-8")
    assert "reviewed_by: kim" in text, text


# ── load_db — 빈 입력을 성공으로 적재 · 레지스트리에 있는 소스를 「없는 소스」로 지움 ─────────
def test_적재는_빈_입력을_성공으로_치지_않는다(tmp_path, monkeypatch) -> None:
    """🔴 ⛔ 있기만 보고 0바이트 파일을 받아 `documents 0 · golden 0` 이 「정상 완료」로 찍혔다."""
    from scripts import load_db as ld

    d = tmp_path / "derived"
    (d / "golden").mkdir(parents=True)
    for n in ("law_article.jsonl", "golden/golden.jsonl"):
        (d / n).write_bytes(b"")
    monkeypatch.setattr(ld, "DERIVED", d)
    monkeypatch.setattr(ld, "ALLOW_MISSING", False)
    with pytest.raises(SystemExit, match="비었다"):
        ld.load_documents(None, True)
    with pytest.raises(SystemExit, match="비었다"):
        ld.load_golden(None, True)


class _Cur:
    def __init__(self, db: list[str]) -> None:
        self.db, self.deleted, self._r = db, [], None

    def execute(self, sql: str, p=None) -> None:  # noqa: ANN001
        if sql.startswith("SELECT source_id FROM source"):
            self._r = [(x,) for x in self.db]
        elif "count(*) FROM fragment" in sql:
            self._r = (0, 0, 0)
        elif sql.startswith("DELETE"):
            self.deleted.append(p[0])

    def fetchall(self):  # noqa: ANN201
        return self._r

    def fetchone(self):  # noqa: ANN201
        return self._r


def test_레지스트리에_있는_소스는_2인_확인_전이어도_거두지_않는다(monkeypatch) -> None:
    """⛔ `- sent` 라 2인 확인 미완으로 건너뛴 소스까지 지우고 「레지스트리에 없는 소스」라 적었다."""
    from scripts import load_db as ld

    srcs = {
        "a": {"decided_by": "x", "reviewed_by": "y", "attribution": "A", "grade": "G3"},
        "b": {"decided_by": "x", "reviewed_by": None, "attribution": "B", "grade": "G3"},
    }
    monkeypatch.setattr(ld, "_sources", lambda: srcs)
    c = _Cur(["a", "b", "ghost"])
    _ok, skipped, swept, _kept = ld.load_sources(c, False)
    assert swept == ["ghost"] and c.deleted == ["ghost"], (swept, c.deleted)
    assert any(s.startswith("b ") for s in skipped)


# ── doctor — `--env --data` 가 데이터를 건너뛰고 0 · 깨진 원장 줄을 🔴 로 찍고도 0 ──────────
def test_doctor_env_와_data_를_같이_주면_둘_다_본다(monkeypatch) -> None:
    import sys

    from scripts import doctor

    called: list[int] = []
    monkeypatch.setattr(doctor, "check_env", lambda: 0)
    monkeypatch.setattr(doctor, "check_data", lambda **k: called.append(1) or 5)
    monkeypatch.setattr(sys, "argv", ["doctor", "--env", "--data"])
    assert doctor.main() == 1 and called, "🔴 데이터 검사를 건너뛰었다"


def test_doctor_는_깨진_원장_줄을_실패로_센다(tmp_path, monkeypatch) -> None:
    import sys

    from scripts import doctor

    m = tmp_path / "manifest.jsonl"
    m.write_text("{broken\n", encoding="utf-8")
    monkeypatch.setattr(doctor, "MANIFEST", m)
    monkeypatch.setattr(doctor, "RAW", tmp_path / "raw")
    monkeypatch.setattr(sys, "argv", ["doctor", "--data"])
    assert doctor.main() == 1


# ── I12 — 분할 뒤 새 라벨 파일 · 낡은 주입본 ────────────────────────────────
def test_분할_뒤에_새로_생긴_입력도_다름이다(monkeypatch) -> None:
    """⛔ 분할이 본 파일만 대조해 새 라벨 파일은 통과했고, 봉인 문서의 라벨이 id 는 그대로인 채 바뀌었다."""
    from preprocess import split

    monkeypatch.setattr(
        split,
        "fingerprint",
        lambda: {"a.jsonl": {"sha256": "1", "bytes": 1}, "new.jsonl": {"sha256": "2", "bytes": 1}},
    )
    with pytest.raises(SystemExit, match="new.jsonl"):
        split.verify_inputs({"inputs": {"a.jsonl": {"sha256": "1", "bytes": 1}}}, who="t")
    # 반대 대조 — 새로 생겼어도 비어 있으면(없는 입력) 다름이 아니다
    monkeypatch.setattr(
        split,
        "fingerprint",
        lambda: {"a.jsonl": {"sha256": "1", "bytes": 1}, "new.jsonl": {"sha256": None, "bytes": 0}},
    )
    split.verify_inputs({"inputs": {"a.jsonl": {"sha256": "1", "bytes": 1}}}, who="t")


def test_주입본의_원본이_train_이_아니면_물질화하지_않는다(tmp_path, monkeypatch) -> None:
    """🔴 ⛔ 분할을 다시 쓴 뒤 주입을 안 돌리면 **봉인 문서에서 만든 변형**이 train 에 들어갔다 — 누수."""
    import json

    from preprocess import golden

    sp = tmp_path / "split_manifest.json"
    sp.write_text(json.dumps({"assign": {"hf:0": "test_sentence"}, "inputs": {}}), encoding="utf-8")
    inj = tmp_path / "injected.jsonl"
    inj.write_text(
        json.dumps(
            {
                "rule_id": "V0",
                "src": "hf:0",
                "문구": "x",
                "라벨": ["거짓_과장"],
                "origin": "injected",
                "provenance": "p",
                "redistributable": True,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(golden, "SPLIT", sp)
    monkeypatch.setattr(golden, "INJECTED", inj)
    monkeypatch.setattr(golden.split_mod, "verify_inputs", lambda m, who: None)
    for name in ("ftc_docs", "casebook_docs", "approved_docs", "guide_docs"):
        monkeypatch.setattr(golden, name, lambda: [])
    with pytest.raises(SystemExit, match="train 이 아니다"):
        golden.build()


# ── I11 (팀장 판정 (나)) — 적법 평가 문장과 겹치는 학습 행은 학습에서 뺀다 ─────────────
def test_적법_평가_문장과_겹치는_학습_행은_학습에서_뺀다(tmp_path, monkeypatch) -> None:
    """⛔ 거름이 라벨 있는 평가 행에만 걸려 적법 문장이 양쪽에 남았다 — Precision 이 부풀었다.
    ★ 평가는 그대로(모자란 쪽을 안 깎는다) · 학습을 깎는다 · 띄어쓰기만 다른 것도 같은 문장이다."""
    import json

    from preprocess import golden

    sp = tmp_path / "split_manifest.json"
    sp.write_text(
        json.dumps(
            {"assign": {"n:1": "test_sentence", "n:2": "train", "n:3": "train"}, "inputs": {}}
        ),
        encoding="utf-8",
    )
    inj = tmp_path / "injected.jsonl"
    inj.write_text("", encoding="utf-8")
    docs = [
        {"doc_id": "n:1", "문구": ["피부 보습에 도움"], "유형": [], "단위": "문장", "원천": "g"},
        {"doc_id": "n:2", "문구": ["피부보습에 도움"], "유형": [], "단위": "문장", "원천": "g"},
        {"doc_id": "n:3", "문구": ["다른 문장"], "유형": [], "단위": "문장", "원천": "g"},
    ]
    monkeypatch.setattr(golden, "SPLIT", sp)
    monkeypatch.setattr(golden, "INJECTED", inj)
    monkeypatch.setattr(golden.split_mod, "verify_inputs", lambda m, who: None)
    monkeypatch.setattr(golden, "approved_docs", lambda: docs)
    for name in ("ftc_docs", "casebook_docs", "guide_docs"):
        monkeypatch.setattr(golden, name, lambda: [])
    monkeypatch.setattr(golden, "lineage", lambda prov, origin: ("f", True))
    rows, stat = golden.build()
    ids = {r["id"] for r in rows}
    assert "n:1#0" in ids, "평가 문장은 그대로다"
    assert "n:2#0" not in ids, "🔴 평가 적법 문장과 같은 학습 행이 남았다"
    assert "n:3#0" in ids and stat["음성겹침_학습제외"] == 1


# ── G2 — 삭제 경로 없이 받으면 원문이 영구히 남던 것 (D-92 · 팀장 판정 (나)) ──────────────
def _spec(grade: str) -> dict:
    return {
        "grade": grade,
        "use": {"U1": "allow"},
        "reviewed_by": "kim",
        "status": "active",
        "access": "",
    }


def test_G2_는_삭제_경로가_없으면_require_에서_막힌다(monkeypatch) -> None:
    from collect import registry

    monkeypatch.setattr(registry, "spec", lambda sid: _spec("G2"))
    monkeypatch.setattr(registry, "G2_DROP_WIRED", ())
    with pytest.raises(registry.RegistryError, match="D-92"):
        registry.require("g2_src", use="U1")


def test_G3_는_G2_문에_걸리지_않는다(monkeypatch) -> None:
    from collect import registry

    monkeypatch.setattr(registry, "spec", lambda sid: _spec("G3"))
    assert registry.require("g3_src", use="U1")["grade"] == "G3"


def test_G2_문은_호출부가_적히면_열린다(monkeypatch) -> None:
    from collect import registry

    monkeypatch.setattr(registry, "spec", lambda sid: _spec("G2"))
    monkeypatch.setattr(registry, "G2_DROP_WIRED", ("preprocess.g2_extract:run",))
    assert registry.require("g2_src", use="U1")["grade"] == "G2"


# ── 앱 가벼운 항목 (전수 재검토) — 비활성 계정 세션 · 벡터 오류 문장 · dict 로그 · 본문 상한 ────────
def test_비활성_계정의_세션은_관리자_화면을_못_연다(monkeypatch) -> None:
    """🔴 ⛔ `disabled_at` 을 로그인에서만 봐서, 막은 계정의 쿠키가 만료(8시간)까지 관리자 화면을 열었다."""
    from fastapi.testclient import TestClient

    from app import auth
    from app.api import app
    from app.routers import admin

    monkeypatch.setattr(auth, "_secret", lambda: b"t" * 32)
    monkeypatch.setattr(admin, "account_active", lambda initials: False)
    c = TestClient(app)
    c.cookies.set(auth.SESSION_COOKIE, auth.issue_session("ohb"))
    r = c.get("/admin/", follow_redirects=False)
    assert r.status_code == 303 and r.headers.get("location") == "/login", r.status_code


def test_벡터_검색_불가_사유는_고정_문장만_응답에_싣는다(monkeypatch) -> None:
    from app import retrieve as rt

    def boom(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise rt.EncoderUnavailable(
            "모델 '/home/secret/weights' 을 로드하지 못했다 — https://x/y?token=abc"
        )

    monkeypatch.setattr(rt, "by_vector", boom)
    monkeypatch.setattr(rt, "by_lexical", lambda *a, **k: [])
    _hits, state = rt.search(None, "면역력 강화")
    assert state.vector.startswith("EncoderUnavailable: ")
    assert "secret" not in state.vector and "token" not in state.vector, state.vector


@pytest.mark.parametrize(
    "line",
    [
        '{"q": "면역력, 암을 예방"}',
        "{'text': '면역력, 암을 예방'}",
        'payload={"prompt":"면역력, 암을 예방"}',
    ],
)
def test_dict_모양_로그의_문구도_가린다(line: str) -> None:
    """🔴 ⛔ 열쇠 뒤가 따옴표라 `[=:]` 가 바로 안 붙어 dict·JSON 모양은 통째로 지나갔다."""
    from app.logging_conf import redact

    assert "암을" not in redact(line), redact(line)


def test_로그_인자가_dict_여도_가린다() -> None:
    import logging

    from app.logging_conf import RedactFilter

    r = logging.LogRecord(
        "x", logging.INFO, "f", 1, "req %s n=%d", ({"q": "면역력 암 예방"}, 3), None
    )
    RedactFilter().filter(r)
    msg = r.getMessage()
    assert "면역력" not in msg and msg.endswith("n=3"), msg


def test_본문_상한은_다_읽기_전에_거부한다() -> None:
    """🔴 ⛔ `await request.body()` 로 전부 읽은 뒤 길이를 쟀다. 선언 길이가 넘으면 읽지 않는다."""
    from fastapi.testclient import TestClient

    from app.api import app

    r = TestClient(app).post(
        "/login",
        content=b"a=" + b"x" * 5000,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 413, r.status_code
