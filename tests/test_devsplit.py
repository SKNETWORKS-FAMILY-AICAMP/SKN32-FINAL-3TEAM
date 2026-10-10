"""dev(검증 묶음) 분리 — 인코더 학습 노트북과 같은 행을 저장소에서 낸다 (🆕 2026-10-07 · `preprocess/devsplit.py`).

지키는 것
  ① dev 는 **학습 분할의 문장 행**에서만 나온다 — 평가 행 · 합성 행 · 낱말 행이 들지 않는다
  ② 같은 묶음(문서)의 문장이 dev 와 학습으로 갈리지 않는다 — 갈리면 학습이 dev 의 이웃 문장을 본다
  ③ 같은 입력이면 같은 행이다(시드 고정) — 지문이 그것을 잡는다
  ④ 평가 도구는 모델 폴더의 dev 지문과 **다르면 멈춘다** — 그 모델은 이 행을 학습에서 봤다 (D-175 · D-220)
     지문이 없으면 일치로 세지 않는다 — 「미확인」으로 적는다
  ⑤ 골든 사본이 있는 기기 — 재동결 10-05 판의 dev 가 노트북(v11 · v10)과 같은 749행 · 같은 지문이다
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from preprocess import devsplit as ds

pytestmark = pytest.mark.gate

GOLDEN = Path("data/derived/golden/golden.jsonl")
#: 재동결 10-05 판(골든 `529c970556d7`)에서 노트북이 낸 dev — 소성민 v11 · 박수진 v10 의 `label_scheme.json` `dev_rows` · `dev_sha`
FROZEN_1005 = ("529c970556d7", 749, "4ebfcb231da703b5")
#: 🆕 2026-10-10 재동결 — `전제` 칸만 더한 판. 문구 · 라벨 · 분할 · 행 순서는 10-05 판과 같다(행별 지문 대조 · 달라진 행 0 /
#:    8,383 · 클론 B). dev 를 고르는 함수는 새 칸을 읽지 않으므로 dev 는 같은 749 행이어야 한다 — 이 줄이 그것을 지킨다
FROZEN_1010 = ("9fe079465d88", 749, "4ebfcb231da703b5")
#: 🆕 2026-10-10 2 차 재동결 — 사례집 2021 식품편의 `품목` 을 소제목에서 읽은 판(봉인 10 행의 품목 · 전제만 바뀌었다 ·
#:    원장 10-10 ⑩). 바뀐 행은 전부 평가 쪽이라 dev 는 같은 749 행이어야 한다
FROZEN_1010B = ("f6ccc5a7de44", 749, "4ebfcb231da703b5")


def _row(rid: str, *, split: str = "train", unit: str = "문장", origin: str = "real", **kw) -> dict:
    return {
        "id": rid,
        "split": split,
        "unit": unit,
        "origin": origin,
        "text": rid,
        "labels": kw.get("labels", ["거짓_과장"]),
        "provenance": kw.get("provenance", "src_a"),
        "조건": kw.get("cond", "C"),
    }


def _golden() -> list[dict]:
    rows = []
    for d in range(40):  # 문서 40개 · 문서마다 문장 3
        rows += [
            _row(f"doc{d:02d}#{k}", provenance="src_a" if d % 2 else "src_b") for k in range(3)
        ]
    rows += [_row(f"t{d}#0", split="test_sentence") for d in range(10)]
    rows += [_row(f"inj:T1:hf:{d}:0", origin="injected") for d in range(10)]
    rows += [_row(f"w{d}#0", unit="낱말") for d in range(10)]
    return rows


def test_dev_는_학습_분할의_문장_행에서만_나온다() -> None:
    ids = ds.dev_ids(_golden())
    assert ids and all(i.startswith("doc") for i in ids)


def test_같은_묶음의_문장이_갈리지_않는다() -> None:
    ids = set(ds.dev_ids(_golden()))
    docs = {i.split("#")[0] for i in ids}
    assert ids == {f"{d}#{k}" for d in docs for k in range(3)}


def test_같은_입력이면_같은_행이다() -> None:
    a, b = ds.dev_ids(_golden()), ds.dev_ids(_golden())
    assert a == b and ds.sha(a) == ds.sha(reversed(a))  # 지문은 순서와 무관하다


def test_조건_M_D_L_은_양성으로_세지_않는다() -> None:
    """양성이 모자라면 묶음을 더 넣는다 — M · D · L 의 라벨은 그 셈에 들지 않는다 (D-296 개정 2)."""
    base = [_row(f"doc{d:02d}#0", labels=[], cond="D") for d in range(40)]
    pos = [_row(f"pos{d}#0", labels=["의약품_오인"], cond="C") for d in range(3)]
    fake = [_row(f"m{d}#0", labels=["의약품_오인"], cond="M") for d in range(30)]
    ids = ds.dev_ids(base + pos + fake)
    assert any(i.startswith("pos") for i in ids)  # 진짜 양성이 dev 에 들어온다


def _scheme(tmp_path: Path, **kw) -> Path:
    (tmp_path / "label_scheme.json").write_text(json.dumps(kw), encoding="utf-8")
    return tmp_path


def test_모델의_dev_지문과_다르면_멈춘다(tmp_path: Path) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    rows = [{"id": i} for i in ds.dev_ids(_golden())]
    good = _scheme(tmp_path, dev_sha=ds.sha(r["id"] for r in rows), dev_rows=len(rows))
    assert eg.check_dev(rows, good)["dev_check"] == "일치"
    _scheme(tmp_path, dev_sha="0" * 16, dev_rows=len(rows))
    with pytest.raises(SystemExit, match="학습에서 봤다"):
        eg.check_dev(rows, tmp_path)
    _scheme(tmp_path, dev_sha=ds.sha(r["id"] for r in rows), dev_rows=len(rows) + 1)
    with pytest.raises(SystemExit, match="다르다"):
        eg.check_dev(rows, tmp_path)


def test_지문이_없으면_일치로_세지_않는다(tmp_path: Path) -> None:
    from scripts import eval_graph as eg  # noqa: PLC0415

    rows = [{"id": "a#0"}]
    assert "미확인" in eg.check_dev(rows, _scheme(tmp_path, label_list=[]))["dev_check"]
    assert "dev_check" not in eg.check_dev(rows, None)  # 인코더 없이 — 대조할 모델이 없다
    with pytest.raises(SystemExit, match="읽지 못했다"):
        eg.check_dev(rows, tmp_path / "없는_폴더")


def test_재동결_1005_판의_dev_는_노트북과_같다() -> None:
    """🚨 이 줄이 깨지면 `devsplit` 이 노트북과 갈렸다 — 그 dev 로 잰 수는 모델이 학습에서 본 행을 포함한다."""
    if not GOLDEN.exists():
        pytest.skip("골든 사본이 없는 기기 — data-sync 뒤에 돈다")
    raw = GOLDEN.read_bytes()
    frozen = {f[0]: f[1:] for f in (FROZEN_1005, FROZEN_1010, FROZEN_1010B)}
    sha12 = hashlib.sha256(raw).hexdigest()[:12]
    if sha12 not in frozen:
        pytest.skip("골든이 아는 동결 판이 아니다 — 새 판의 dev 지문은 새 모델 폴더가 든다")
    n, want = frozen[sha12]
    ids = ds.dev_ids(json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip())
    assert (len(ids), ds.sha(ids)) == (n, want)
