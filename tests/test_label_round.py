"""라벨 한 판 — 짜기 · 검증 행 · 재검 · 갈린 것 · 판정 (2026-09-20 · `scripts/label_round.py`).

팀장 — *「사람이 직접 하는 건 정확도가 떨어질 것 같은데」* → 사람이 틀리는 것이 **드러나게** 짠다.

★ 전부 **임시 폴더**다 — 가짜 파생물·가짜 라벨. 진짜 `data/` 와 `.env` 는 안 본다.
🚨 여기서 막는 것 —
   ① 이미 붙인 사람에게 재검 행이 가는 것(블라인드가 아니다)
   ② 검증 행이 라벨로 들어가는 것 · CSV 에서 검증 행이 드러나는 것
   ③ 참고 답(LLM 등)이 라벨로 들어가는 것
   ④ 한 사람의 두 파일이 「두 사람의 합의」로 세는 것
   ⑤ 판정자 없는 판정 · 판정이 갈린 행을 이기지 못하는 것
"""

from __future__ import annotations

import csv
import json
import pathlib

import pytest

from collect import env
from preprocess import labels as store
from scripts import label_round as lr
from scripts import label_sheet as ls

pytestmark = pytest.mark.gate

DISEASE = "질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동"
COMPARE = "부당한 비교ㆍ비방"


def _w(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    der = tmp_path / "data" / "derived"
    guide = [
        {
            "원천": "mfds_special_use_guide",
            "종류": "위반문구",
            "원천라벨": DISEASE,
            "문구": f"변비 치료에 효과가 있는 제품입니다 {i}번",
            "후보유형": ["질병_예방치료_표방", "의약품_오인", "건강기능식품_오인"],
        }
        for i in range(10)
    ] + [
        {
            "원천": "mfds_special_use_guide",
            "종류": "위반문구",
            "원천라벨": COMPARE,
            "문구": f"타사 제품은 효과가 전혀 없습니다 {i}번",
            "후보유형": ["부당_비교광고", "비방광고"],
        }
        for i in range(4)
    ]
    old_sheet = [
        {
            "원천": "mfds_special_use_guide",
            "원천라벨": DISEASE,
            "문구": f"기존 시트 문구입니다 {i}번",
            "확정유형": [],
            "후보유형": ["질병_예방치료_표방"],
            "붙인이": "",
            "붙인날": "",
        }
        for i in range(3)
    ]
    labeled = [dict(r, 확정유형=["질병_예방치료_표방"], 붙인이="오한빈") for r in old_sheet]
    golden = [
        {
            "text": f"국내 최초 유일한 기술로 만든 제품 {i}",
            "labels": ["거짓_과장"],
            "provenance": "ftc_decisions_body",
            "split": "test_sentence",
        }
        for i in range(5)
    ]
    _w(der / "mfds_guide_labels.jsonl", guide)
    _w(der / "mfds_guide_labelsheet.jsonl", old_sheet)
    _w(der / "labels" / "오한빈.jsonl", labeled)
    _w(der / "golden" / "golden.jsonl", golden)
    monkeypatch.setattr(lr, "DERIVED", der)
    monkeypatch.setattr(lr, "ROUNDS", der / "label_rounds")
    monkeypatch.setattr(lr, "GUIDE", der / "mfds_guide_labels.jsonl")
    monkeypatch.setattr(lr, "DECC", der / "없음.jsonl")
    monkeypatch.setattr(lr, "GOLDEN", der / "golden" / "golden.jsonl")
    monkeypatch.setattr(lr, "RECHECK", (der / "mfds_guide_labelsheet.jsonl",))
    monkeypatch.setattr(lr, "ROOT", tmp_path)
    monkeypatch.setattr(lr, "_cap", lambda: 120)
    monkeypatch.setattr(store, "DIR", der / "labels")
    monkeypatch.setattr(ls, "ROOT", tmp_path)
    monkeypatch.setattr(ls, "OUT_DIR", tmp_path / "build" / "labels")
    monkeypatch.setattr(env, "_loaded", True)
    monkeypatch.setenv("DATA_ROLE", "canonical")
    return tmp_path


def _sheet(root: pathlib.Path) -> pathlib.Path:
    return root / "data" / "derived" / "label_rounds" / "r2_labelsheet.jsonl"


def _csv_rows(p: pathlib.Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _fill(p: pathlib.Path, fn) -> None:
    rows = _csv_rows(p)
    for r in rows:
        r["유형번호"] = fn(r)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_판은_겹침_검증_재검을_나눠_담는다(world) -> None:
    assert lr.plan("r2", ["오한빈", "권소라", "소성민"], 0.5, 3, 1) == 0
    rows = ls._rows(_sheet(world))
    gold = {i for i, r in enumerate(rows, 1) if "검증정답" in r}
    rech = {i for i, r in enumerate(rows, 1) if "재검_제외" in r}
    assert len(gold) == 3 and len(rech) == 3
    got = {
        w: {int(r["행"]) for r in _csv_rows(world / "build/labels" / f"{w}__r2_labelsheet.csv")}
        for w in ("오한빈", "권소라", "소성민")
    }
    assert all(gold <= v for v in got.values()), "검증 행은 전원에게 간다"
    assert not (rech & got["오한빈"]), "🔴 이미 붙인 사람에게 재검 행이 갔다 — 블라인드가 아니다"
    assert rech <= got["권소라"] | got["소성민"]
    shared = got["오한빈"] & got["권소라"] & got["소성민"] - gold
    assert len(shared) >= 5, "새 행의 절반은 전원이 겹쳐야 한다"
    assert sorted(gold) != list(range(len(rows) - 2, len(rows) + 1)), "검증 행이 끝에 몰렸다"


def test_CSV_에서_검증_행이_드러나지_않는다(world) -> None:
    lr.plan("r2", ["권소라", "소성민"], 0.5, 3, 1)
    text = (world / "build/labels/권소라__r2_labelsheet.csv").read_text(encoding="utf-8-sig")
    assert "검증" not in text and '거짓_과장"]' not in text


def test_검증_행은_라벨로_안_들어가고_정답률만_센다(world, capsys) -> None:
    lr.plan("r2", ["권소라", "소성민"], 0.5, 3, 1)
    p = world / "build/labels/권소라__r2_labelsheet.csv"
    _fill(p, lambda r: "8")  # 검증 정답(거짓_과장=8)을 전부 맞힌다
    ls.import_(p, _sheet(world), "")
    out = capsys.readouterr().out
    assert "검증 행 3개 — 맞힘 3" in out
    got = (world / "data/derived/labels/권소라__r2_labelsheet.jsonl").read_text(encoding="utf-8")
    assert "검증정답" not in got and "국내 최초" not in got


def test_갈린_행만_판정표로_가고_참고_답은_라벨이_아니다(world) -> None:
    lr.plan("r2", ["권소라", "소성민"], 1.0, 0, 1)  # 전부 겹침
    a = world / "build/labels/권소라__r2_labelsheet.csv"
    b = world / "build/labels/소성민__r2_labelsheet.csv"
    _fill(a, lambda r: "1")
    _fill(b, lambda r: "2" if "0번" in r["문구"] else "1")
    ref = world / "build/labels/참고.csv"
    ref.write_bytes(a.read_bytes())
    _fill(ref, lambda r: "7" if "타사" in r["문구"] else "1")
    assert lr.compare(_sheet(world), [a, b], [ref]) == 0
    panel = _csv_rows(world / "build/labels/판정__r2_labelsheet.csv")
    texts = [r["문구"] for r in panel]
    assert any("0번" in t for t in texts), "사람끼리 갈린 행"
    assert any("타사" in t for t in texts), "참고 답과 다른 행"
    assert not (world / "data/derived/labels/참고__r2_labelsheet.jsonl").exists()


def test_판정은_갈린_행을_이기고_판정자가_없으면_멈춘다(world) -> None:
    lr.plan("r2", ["권소라", "소성민"], 1.0, 0, 1)
    sheet = _sheet(world)
    a = world / "build/labels/권소라__r2_labelsheet.csv"
    b = world / "build/labels/소성민__r2_labelsheet.csv"
    _fill(a, lambda r: "1")
    _fill(b, lambda r: "2")
    ls.import_(a, sheet, "")
    ls.import_(b, sheet, "")
    picked, stat = store.consensus()
    assert stat.get("갈림", 0) > 0
    lr.compare(sheet, [a, b], [])
    panel = world / "build/labels/판정__r2_labelsheet.csv"
    rows = _csv_rows(panel)
    for r in rows:
        r["최종번호"] = "2"
    with panel.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(SystemExit, match="판정자"):
        lr.decide(panel, sheet, "")
    for r in rows:
        r["판정자"] = "오한빈"
    with panel.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert lr.decide(panel, sheet, "") == 0
    picked, stat = store.consensus()
    assert stat.get("갈림", 0) == 0 and stat["판정"] == len(rows)
    assert all(r["확정유형"] == ["의약품_오인"] for r in picked.values() if r.get("판정"))


def test_한_사람의_두_파일은_한_사람이다(world) -> None:
    der = world / "data" / "derived" / "labels"
    row = {
        "원천": "x",
        "원천라벨": "y",
        "문구": "같은 문구",
        "확정유형": ["거짓_과장"],
        "붙인이": "권소라",
    }
    _w(der / "권소라__a.jsonl", [row])
    _w(der / "권소라__b.jsonl", [row])
    picked, stat = store.consensus()
    k = store.key(row)
    assert k in picked and stat.get("합의", 0) == 0, "🔴 한 사람이 두 번 붙인 것이 합의로 셌다"


def test_사본에서는_판을_짜지_않는다(world, monkeypatch) -> None:
    monkeypatch.setenv("DATA_ROLE", "replica")
    assert lr.plan("r2", ["권소라", "소성민"], 0.3, 3, 1) == 1
    assert not _sheet(world).exists()


def test_같은_이름의_판은_다시_뽑지_않는다(world) -> None:
    assert lr.plan("r2", ["권소라", "소성민"], 0.3, 3, 1) == 0
    before = _sheet(world).read_bytes()
    assert lr.plan("r2", ["권소라", "소성민"], 0.3, 3, 2) == 1
    assert _sheet(world).read_bytes() == before


# ── 🆕 2026-09-24 — 같은 키(같은 문구)의 행이 시트에 둘일 때 ─────────────────────────
#    round2 실측 — 해설서 표 47·48 의 「의인의 마음을 담아 만듭니다」 · 같은 행정심판 사건 · 같은 검증 문구가
#    두 번씩 들어가 있었다. 라벨은 키로 쌓이므로 두 행은 저장소에서 **한 자리**다.
#    ⛔ compare 가 같은 문구를 판정표에 두 번 올렸고(213 → 214), decide 는 다른 두 판정 중 나중 것을 조용히 남겼다.
def _dup_sheet(world: pathlib.Path) -> pathlib.Path:
    row = {
        "원천": "mfds_special_use_guide",
        "원천라벨": DISEASE,
        "문구": "같은 문구가 두 표에 있습니다",
        "확정유형": [],
        "후보유형": ["질병_예방치료_표방", "의약품_오인"],
    }
    other = dict(row, 문구="다른 문구입니다 하나 더")
    sheet = _sheet(world)
    _w(sheet, [dict(row, 표=47), other, dict(row, 표=48)])
    return sheet


def test_판은_같은_키의_행을_한_번만_담는다(world) -> None:
    der = world / "data" / "derived"
    guide = [
        json.loads(x)
        for x in (der / "mfds_guide_labels.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    _w(der / "mfds_guide_labels.jsonl", guide + [dict(guide[0], 표=99)])
    assert lr.plan("r2", ["권소라", "소성민"], 0.5, 3, 1) == 0
    keys = [store.key(r) for r in ls._rows(_sheet(world))]
    assert len(keys) == len(set(keys)), "🔴 같은 키의 행이 한 판에 둘 들어갔다"


def test_같은_키의_두_행은_판정표에_한_번만_오른다(world) -> None:
    sheet = _dup_sheet(world)
    paths = []
    for who, no in (("권소라", "1"), ("소성민", "2")):
        p = ls.export(sheet, who, None, idx=[1, 2, 3], quiet=True)
        _fill(p, lambda r, no=no: no if r["행"] == "1" else "")
        ls.import_(p, sheet, "")
        paths.append(p)
    assert lr.compare(sheet, paths, []) == 0
    panel = _csv_rows(world / "build/labels/판정__r2_labelsheet.csv")
    assert [r["행"] for r in panel] == ["1"], "🔴 같은 문구가 판정표에 두 번 올랐다"


def test_같은_문구에_다른_최종번호면_판정을_멈춘다(world) -> None:
    sheet = _dup_sheet(world)
    panel = world / "build/labels/판정__r2_labelsheet.csv"
    panel.parent.mkdir(parents=True, exist_ok=True)
    rows = ls._rows(sheet)

    def write(nos: tuple[str, str]) -> None:
        with panel.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=lr.PANEL)
            w.writeheader()
            for i, no in zip((1, 3), nos, strict=True):
                t = ls._text(rows[i - 1])
                w.writerow(
                    {"행": i, "문구": t, "최종번호": no, "판정자": "오한빈", "지문": ls.csv_fp(t)}
                )

    write(("1", "2"))
    with pytest.raises(SystemExit, match="같은 문구인데"):
        lr.decide(panel, sheet, "")
    write(("1", "1"))
    assert lr.decide(panel, sheet, "") == 0
    got = (world / "data/derived/labels/_판정__r2_labelsheet.jsonl").read_text(encoding="utf-8")
    assert len(got.splitlines()) == 1, "같은 판정은 한 번만 쓴다"
