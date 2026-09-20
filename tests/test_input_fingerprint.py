"""🔴 **입력 지문** — 같은 커밋·같은 seed 로도 결과가 갈린다 (D-176 · 2026-09-10).

⛔ 실측 사고. 클론 B 는 원장에 「주입 902 · 골든셋 1,910」을 적었는데, **같은 커밋에서
   같은 seed(20260909)로** 다른 기기가 돌리면 **908 · 1,915** 가 나왔다.

       원인은 코드도 seed 도 아니었다 — `mfds_hf_labels.jsonl` 의 승인문구가
       **178 vs 177**, 문구 **한 건** 차이였다. `V0 = 승인문구 − 60` 이라
       그 한 건이 `118→117` 로 전파되고, 주입이 `V0 + 7×변형` 이라 7 배로 벌어진다.

🚨 그리고 **지표로는 안 보인다.** 두 배치의 P·R·F1 이 소수점 셋째 자리까지 같았다.
   「지표가 맞으니 같은 배치」라고 읽으면 틀린다.

★ `data/**` 는 커밋되지 않으므로(D-19) **입력은 git 이 못 지킨다.** 산출물이 자기 입력의
  sha256 을 들고 다니고 뒤 단계가 대조하는 것이, 이 사고를 잡는 유일한 자리다.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from preprocess import labels as label_store
from preprocess import split
from scripts import derived_manifest as dm

pytestmark = pytest.mark.gate


@pytest.fixture
def inputs(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> list[pathlib.Path]:
    files = []
    for name in ("a.json", "b.jsonl", "c.jsonl"):
        f = tmp_path / name
        f.write_text(f"내용-{name}", encoding="utf-8")
        files.append(f)
    monkeypatch.setattr(split, "INPUTS", tuple(files))
    # 🔄 2026-09-17 — 라벨 파일이 넷째 입력이 됐다(`split.inputs()`). 이 단위 테스트는
    #    **실제 `data/derived/labels/` 를 보면 안 된다** — 붙인 사람이 늘 때마다 흔들린다.
    #    그래서 라벨 디렉터리도 빈 tmp 로 돌린다 (밀폐).
    monkeypatch.setattr(label_store, "DIR", tmp_path / "labels-없음")
    return files


def test_지문이_같으면_지나간다(inputs: list[pathlib.Path]) -> None:
    split.verify_inputs({"inputs": split.fingerprint()}, who="테스트")


def test_입력이_한_바이트만_달라도_멈춘다(inputs: list[pathlib.Path]) -> None:
    """🚨 **한 건 차이가 902 와 908 을 갈랐다.** 경고가 아니라 정지여야 한다 (D-72)."""
    m = {"inputs": split.fingerprint()}
    inputs[2].write_text("내용-c.jsonl 에 한 줄 더", encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        split.verify_inputs(m, who="테스트")

    assert inputs[2].as_posix() in str(e.value), "어느 파일이 갈렸는지 이름으로 내야 한다"
    assert "D-176" in str(e.value)


def test_지문이_없는_낡은_분할은_멈춘다(inputs: list[pathlib.Path]) -> None:
    """⛔ 「없으면 그냥 통과」는 조용히 옛 상태로 돌아가는 길이다."""
    with pytest.raises(SystemExit):
        split.verify_inputs({"assign": {}}, who="테스트")


def test_분할_산출물이_지문을_들고_있다() -> None:
    """🔴 산출물에 지문이 없으면 뒤 단계가 대조할 것이 없다."""
    if not split.OUT.exists():
        pytest.skip(
            "🔴 분할 산출물이 없어 **확인하지 못했다** — uv run python launcher.py golden --write"
        )
    m = json.loads(split.OUT.read_text(encoding="utf-8"))
    assert "inputs" in m, f"{split.OUT} 에 `inputs` 지문이 없다 — 분할을 다시 돌린다 (D-176)"
    # 🔄 2026-09-17 — `INPUTS`(고정 셋) 이 아니라 `inputs()`(고정 + 라벨 파일) 과 댄다.
    #    ⛔ 고정 셋과 대면 라벨이 늘 때마다 여기서 걸린다 — 라벨은 **의도된 넷째 입력**이다.
    #    ★ 그렇다고 헐거워지지 않는다: 이제 **「라벨 파일이 늘었는데 분할을 다시 안 돌렸다」**
    #      를 잡는다. 저장된 지문과 지금 입력 목록이 다르면 그 분할은 낡은 것이다 (D-176).
    #    🔄 2026-09-20 (D-249) — 라벨은 이제 **git 에 없다**(공유 저장소가 옮긴다). CI · 받기 전 사본에는
    #       라벨 파일이 없어 `inputs()` 가 짧다 → 종전 등식은 **CI 에서 원리적으로 실패**했다(실측 · b4bc3d4).
    #    ★ 둘로 가른다 — ① 이 기기에 있는 라벨이 분할에 없다 = 낡은 분할(어디서든 🔴)
    #                     ② 분할에 있는 입력이 이 기기에 없다 = **대조를 못 한 것**(정본이면 🔴 · 아니면 skip)
    #    ⛔ ②를 조용히 통과시키지 않는다 — 없음을 성공으로 세지 않는다 (D-72).
    saved = set(m["inputs"])
    here = {f.as_posix() for f in split.inputs()}
    assert not (here - saved), (
        f"분할 산출물의 지문에 없는 입력이 있다 {sorted(here - saved)} — 라벨을 붙인 뒤 "
        "uv run python launcher.py golden --write 를 안 돌렸을 수 있다"
    )
    assert all(v["sha256"] for v in m["inputs"].values()), "입력이 비어 있다"
    assert "승인문구_종수" in m, "902 vs 908 을 가른 수다 — 산출물에 적어 둔다"
    absent = sorted(saved - here)
    if absent:
        assert dm.role() != "canonical", f"정본에 분할 입력이 없다 {absent} — 라벨을 잃었다 (D-249)"
        pytest.skip(
            f"🔴 분할 입력 {len(absent)}개가 이 기기에 없어 **전체 대조는 못 했다** — {absent[:3]}. "
            "라벨은 공유 저장소가 옮긴다 (D-249 · `launcher.py data-sync`)"
        )


def _fake_split(
    tmp: pathlib.Path, mp: pytest.MonkeyPatch, saved: list[str], here: list[str]
) -> None:
    out = tmp / "split_manifest.json"
    out.write_text(
        json.dumps(
            {"inputs": {k: {"sha256": "x", "bytes": 1} for k in saved}, "승인문구_종수": 1},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mp.setattr(split, "OUT", out)
    mp.setattr(split, "inputs", lambda: tuple(pathlib.PurePosixPath(x) for x in here))


FIXED = ["data/derived/a.json"]
LABEL = "data/derived/labels/누군가.jsonl"


def test_라벨이_git_에_없는_기기는_대조를_못_했다고_남긴다(tmp_path, monkeypatch) -> None:
    """🔴 CI 실측 (b4bc3d4) — 라벨이 공유 저장소로 옮겨 가(D-249) CI 에는 없다. 등식은 원리적으로 실패했다.

    ⛔ 그렇다고 통과로 세지 않는다 — **skip** 으로 「못 했다」를 남기고, 정본이면 🔴.
    """
    _fake_split(tmp_path, monkeypatch, FIXED + [LABEL], FIXED)
    monkeypatch.setenv("DATA_ROLE", "")
    with pytest.raises(pytest.skip.Exception):
        test_분할_산출물이_지문을_들고_있다()
    monkeypatch.setenv("DATA_ROLE", "canonical")
    with pytest.raises(AssertionError, match="라벨을 잃었다"):
        test_분할_산출물이_지문을_들고_있다()


def test_라벨이_늘었는데_분할을_안_돌리면_어디서든_멈춘다(tmp_path, monkeypatch) -> None:
    _fake_split(tmp_path, monkeypatch, FIXED, FIXED + [LABEL])
    monkeypatch.setenv("DATA_ROLE", "")
    with pytest.raises(AssertionError, match="golden --write"):
        test_분할_산출물이_지문을_들고_있다()


def test_반대_대조_shuffle_축이_분리돼_있다() -> None:
    """🚨 pool 크기가 봉인 음성을 흔들지 못해야 한다 (D-176).

    ⛔ 종전에는 `random.Random` 하나를 두 shuffle 에 공유했다. 고원을 넘으면
       봉인 60개 중 21~26개가 조용히 교체됐다 — **고원 안에서는 0개라 안 드러난다.**
    ★ 소스를 읽지 않고 **동작으로** 묻는다 (D-170).
    """
    import random

    def seal(pool_n: int, *, shared: bool) -> list[int]:
        rp = random.Random(20260909)
        rn = rp if shared else random.Random(20260909)
        pool = list(range(pool_n))
        rp.shuffle(pool)
        approved = list(range(300))
        rn.shuffle(approved)
        return approved[:60]

    base = seal(211, shared=False)
    assert all(seal(n, shared=False) == base for n in (190, 203, 214, 232)), (
        "축을 나눴는데도 pool 크기가 봉인을 흔든다 — 구현이 바뀌었다"
    )
    assert any(seal(n, shared=True) != seal(211, shared=True) for n in (190, 203, 232)), (
        "공유했을 때조차 안 흔들린다면 이 검사는 실패할 수 없다 (D-170)"
    )
