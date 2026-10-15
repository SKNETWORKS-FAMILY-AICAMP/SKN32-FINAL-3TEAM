"""인코더 재분할 — 봉인 평가셋의 해설서 행 일부를 인코더 학습 · dev 로 옮긴다 (🆕 2026-10-15 · D-347 · `preprocess/encoder_resplit.py`).

지키는 것
  ① 옮기는 것은 봉인 행 중 해설서 판(`gs:` · `gf:`)뿐이다 — 다른 봉인 행 · 학습 분할 행은 그대로다
  ② 정규화한 글자가 같은 묶음은 같은 쪽으로 간다 — 띄어쓰기만 다른 같은 문구가 학습과 봉인에 갈리지 않는다
  ③ 옮긴 뒤 봉인에서 측정 가능(30)에서 불가로 떨어지는 유형의 묶음은 봉인에 남는다 — 라벨 수만 본다
  ④ 같은 입력이면 같은 배정이다(해시 · 시드 없음) — 지문이 그것을 잡는다
  ⑤ 평가 도구의 봉인 평가셋 · 판정기 B 의 시험지는 옮긴 행을 읽지 않는다 — 정의는 한 곳(D-99)
  ⑥ 확장 dev 대조 — 재분할 전 판은 해설서 dev 를 학습에서 보지 않았다(봉인 몫) · 재분할 판은 지문이 같아야 한다
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from preprocess import devsplit as ds
from preprocess import encoder_resplit as rs

pytestmark = pytest.mark.gate


#: 진짜 함수 — 아래 자동 고정물이 바꾸기 전에 잡아 둔다(파일 없음 멈춤을 잰다)
_REAL_FIX_LINKS = rs.fix_links


@pytest.fixture(autouse=True)
def _no_fix_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """합성 골든에는 판독 채택본이 없다 — 연결 없음으로 둔다."""
    monkeypatch.setattr(rs, "fix_links", lambda *a, **k: [])


def _row(
    rid: str, text: str, *, split: str = "test_sentence", labels=("거짓_과장",), cond: str = "C"
) -> dict:
    return {"id": rid, "text": text, "split": split, "labels": list(labels), "조건": cond}


def _golden() -> list[dict]:
    rows = [_row(f"gs:{i:03d}#0", f"해설서 위반 문구 {i}") for i in range(200)]
    rows += [_row(f"gf:{i:03d}#0", f"해설서 수정 문구 {i}", labels=(), cond="D") for i in range(40)]
    rows += [_row(f"ftc:{i:03d}#0", f"보도자료 문구 {i}") for i in range(30)]
    rows += [_row(f"tr:{i:03d}#0", f"학습 문구 {i}", split="train") for i in range(20)]
    return rows


def test_옮기는_것은_봉인의_해설서_판뿐이다() -> None:
    g = _golden()
    p = rs.plan(g)
    assert set(p) == {
        r["id"] for r in g if r["split"] == "test_sentence"
    }  # 학습 분할 행은 다루지 않는다
    assert all(p[r["id"]] == rs.SEALED for r in g if r["id"].startswith("ftc:"))
    moved = {i for i, w in p.items() if w != rs.SEALED}
    assert moved and all(i.startswith(rs.PREFIXES) for i in moved)
    assert {w for w in p.values()} == {rs.TRAIN, rs.DEV, rs.SEALED}


def test_정규화한_글자가_같으면_같은_쪽이다() -> None:
    g = [_row(f"gs:{i:03d}#0", "체중 감량 효과!" if i % 2 else "체중감량효과") for i in range(20)]
    assert len(set(rs.plan(g).values())) == 1


def test_수정_문구와_원래_문구는_같은_칸이다() -> None:
    def word(i: int, salt: str) -> str:  # 서로 닮지 않은 글자(근접 중복으로 묶이지 않게)
        return hashlib.sha256(f"{salt}{i}".encode()).hexdigest()[:16]

    #: 유형 없이(조건 D) — 측정 불가 예외가 끼지 않게
    g = [_row(f"gs:{i:03d}#0", word(i, "원"), labels=(), cond="D") for i in range(60)]
    g += [_row(f"gf:{i:03d}#0", word(i, "수"), labels=(), cond="D") for i in range(60)]
    links = [(f"gf:{i:03d}", rs.norm(word(i, "원"))) for i in range(60)]
    p = rs.plan(g, links)
    assert all(p[f"gf:{i:03d}#0"] == p[f"gs:{i:03d}#0"] for i in range(60))
    assert len({p[f"gs:{i:03d}#0"] for i in range(60)}) > 1  # 짝끼리는 같고 짝 사이는 갈린다


def test_근접_중복은_같은_칸이다() -> None:
    base = "이 제품은 체지방 감소에 탁월한 효과가 있는 다이어트 식품입니다"
    g = [_row(f"gs:{i:03d}#0", base + ("요" if i % 2 else "")) for i in range(20)]
    assert len(set(rs.plan(g, []).values())) == 1


def test_채택본이_없으면_멈춘다(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="원래 문구"):
        _REAL_FIX_LINKS(tmp_path / "없음.jsonl")


def test_다른_원천의_봉인_행과_같은_글자면_봉인에_남는다() -> None:
    def word(i: int) -> str:
        return hashlib.sha256(f"w{i}".encode()).hexdigest()[:16]

    g = [_row(f"gs:{i:03d}#0", word(i), labels=(), cond="D") for i in range(100)]
    g += [_row(f"ftc:{i:03d}#0", word(i), labels=(), cond="D") for i in range(0, 100, 2)]
    p = rs.plan(g, [])
    assert all(p[f"gs:{i:03d}#0"] == rs.SEALED for i in range(0, 100, 2))
    assert any(p[f"gs:{i:03d}#0"] != rs.SEALED for i in range(1, 100, 2))


def test_측정_불가로_떨어지는_유형은_봉인에_남는다() -> None:
    #: 후기 30 묶음이 모두 해설서 판 — 그냥 나누면 봉인 후기가 30 아래로 떨어진다
    g = [_row(f"gs:h{i:03d}#0", f"후기 문구 {i}", labels=("후기_체험기_기만",)) for i in range(30)]
    g += [_row(f"gs:x{i:03d}#0", f"과장 문구 {i}") for i in range(300)]
    p = rs.plan(g)
    assert all(p[r["id"]] == rs.SEALED for r in g if "후기_체험기_기만" in r["labels"])
    sealed = [r for r in g if p[r["id"]] == rs.SEALED]
    assert sum("후기_체험기_기만" in r["labels"] for r in sealed) == 30
    #: 원래 30 미만인 유형은 지키지 않는다(측정 가능에서 떨어지는 것만 막는다)
    g2 = [_row(f"gs:h{i:03d}#0", f"후기 문구 {i}", labels=("후기_체험기_기만",)) for i in range(10)]
    assert any(w != rs.SEALED for w in rs.plan(g2).values())


def test_같은_입력이면_같은_배정이다() -> None:
    a, b = rs.stamp(_golden()), rs.stamp(list(reversed(_golden())))
    assert a["train_rows"] == b["train_rows"] and a["dev_rows"] == b["dev_rows"]
    assert rs.stamp(_golden()) == rs.stamp(_golden())


def test_봉인_평가셋은_옮긴_행을_읽지_않는다(tmp_path: Path) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    g = _golden()
    path = tmp_path / "golden.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in g), encoding="utf-8")
    sealed = eg.load_rows(path)
    want = {r["id"] for r in rs.sealed_rows(g)}
    assert {r["id"] for r in sealed} == want
    assert len(want) < sum(r["split"] == "test_sentence" for r in g)


def test_판정기_B_도_같은_봉인_정의를_쓴다() -> None:
    src = Path("scripts/eval_rule.py").read_text(encoding="utf-8")
    assert "encoder_resplit.sealed_rows(" in src
    assert 'json.loads(x)["split"] == "test_sentence"' not in src


def _scheme(tmp_path: Path, **kw) -> Path:
    (tmp_path / "label_scheme.json").write_text(json.dumps(kw), encoding="utf-8")
    return tmp_path


def test_확장_dev_대조(tmp_path: Path) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    base = [{"id": f"doc{i}#0"} for i in range(5)]
    guide = [{"id": f"gs:{i:03d}#0"} for i in range(3)]
    bsha, gsha = ds.sha(r["id"] for r in base), ds.sha(r["id"] for r in guide)
    #: 재분할 전 판 — base 만 대조하고 해설서 dev 는 봉인 몫으로 적는다
    old = _scheme(tmp_path, dev_sha=bsha, dev_rows=5)
    got = eg.check_dev(base + guide, old)
    assert got["dev_rows"] == 5 and got["guide_dev_rows"] == 3 and "봉인 몫" in got["dev_check"]
    #: 재분할 판 — 지문이 같아야 한다
    _scheme(tmp_path, dev_sha=bsha, dev_rows=5, resplit=rs.VERSION, resplit_dev_sha=gsha)
    assert eg.check_dev(base + guide, tmp_path)["dev_check"] == "일치(재분할 판)"
    _scheme(tmp_path, dev_sha=bsha, dev_rows=5, resplit=rs.VERSION, resplit_dev_sha="0" * 16)
    with pytest.raises(SystemExit, match="해설서 dev"):
        eg.check_dev(base + guide, tmp_path)
    _scheme(tmp_path, dev_sha=bsha, dev_rows=5, resplit="v0", resplit_dev_sha=gsha)
    with pytest.raises(SystemExit, match="재분할"):
        eg.check_dev(base + guide, tmp_path)


def test_guide_dev_는_dev_와_함께만() -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    with pytest.raises(SystemExit, match="--dev 와 함께만"):
        eg.main(["--sealed", "--guide-dev", "--stub"])


GOLDEN = Path("data/derived/golden/golden.jsonl")
#: 골든 `f6ccc5a7de44` 에서 낸 재분할 v1 (2026-10-15 · 클론 A 실행 · D-347) — 바뀌면 학습 · dev · 봉인 수가 모두 달라진다
FROZEN_V1 = (
    "f6ccc5a7de44",
    950,
    "e8f5d6d27e7a5cea",
    398,
    "cc2d8b7e42d57266",
    1141,
    "74e37657d39ec325",
)


@pytest.mark.skipif(not GOLDEN.exists(), reason="골든 사본이 없는 기기")
def test_골든_사본이_있으면_재분할_v1_지문이_같다() -> None:
    import hashlib  # noqa: PLC0415

    raw = GOLDEN.read_bytes()
    if hashlib.sha256(raw).hexdigest()[:12] != FROZEN_V1[0]:
        pytest.skip("다른 골든 판 — 지문을 비교할 판이 아니다")
    s = rs.stamp(json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip())
    got = (
        s["train_rows"],
        s["train_sha"],
        s["dev_rows"],
        s["dev_sha"],
        s["sealed_rows"],
        s["sealed_sha"],
    )
    assert got == FROZEN_V1[1:]
