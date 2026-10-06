"""해설서 수정문구 판(GF) · 결정문 봉인 문구 판(FS) (2026-09-30 · 판정 J1 (b) · J2).

🔴 무엇을 막나
   ① 해설서 수정쌍에 없는 행(고쳐 쓴 문구 · 표가 다른 행)이 수정문구 판에 채택되는 것 (D-220)
   ② 식품 규칙(3.나 유형 · 조제유류 목 · 거래 조건)이 수정문구 판에서만 빠지는 것 — 위반문구 판과 같은 함수 (D-99)
   ③ 판정 대기가 남았는데 수정문구가 평가에 들어가는 것 · 대상 N 이 평가에 들어가는 것
     🔄 2026-10-01 (D-299 · D-301) — 수정문구는 **조건 D 행만** 평가에 든다(적법 문장 · 주장 없음). C · A · B · M · L 은 안 든다
   ④ 결정문 봉인 문구에 판독이 L(적법)을 붙이거나 원천 호를 바꾸는데 합의로 채택되는 것 (D-237)
   ⑤ 봉인 문구 판이 끝났는데 골든에 대상 N 문구가 남거나 · 판에 없는 봉인 문구가 조건 없이 섞이는 것
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import statute
from preprocess import golden, split
from scripts import guide_statute_round as g

HEAD = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _paths(monkeypatch, prefix: str, d: pathlib.Path) -> None:
    for name, fn in (
        ("READINGS", "readings.jsonl"),
        ("ADOPTED", "adopted.jsonl"),
        ("DECISIONS", "decisions.jsonl"),
        ("AUDIT", "audit.jsonl"),
        ("TEAM_SHEET", "team.csv"),
    ):
        monkeypatch.setattr(g, f"{prefix}_{name}", d / fn)


@pytest.fixture
def gf(tmp_path, monkeypatch):
    d = tmp_path / "gf"
    _paths(monkeypatch, "GF", d)
    guide = tmp_path / "guide.jsonl"
    base = {"블록": "수정", "원천": "mfds_special_use_guide", "종류": "수정쌍"}
    _jsonl(
        guide,
        [
            {
                **base,
                "표": 37,
                "제품유형": "2. 성장기용 조제식",
                "문구": "MCT 풍부",
                "수정문구": "MCT 함유",
            },
            {
                **base,
                "표": 78,
                "제품유형": "9. 체중조절용 조제식품",
                "문구": "진짜 초코맛",
                "수정문구": "초코맛",
            },
            {
                **base,
                "표": 78,
                "제품유형": "9. 체중조절용 조제식품",
                "문구": "Various Flavor",
                "수정문구": "*한글 표기",
            },
            {"표": 37, "종류": "위반문구", "문구": "모유수준", "원천": "mfds_special_use_guide"},
        ],
    )
    monkeypatch.setattr(g, "GF_GUIDE", guide)
    monkeypatch.setattr(split, "GUIDE_FIX_READINGS", d / "readings.jsonl")
    monkeypatch.setattr(split, "GUIDE_FIX_ADOPTED", d / "adopted.jsonl")
    return tmp_path, d


def _units(tmp: pathlib.Path) -> pathlib.Path:
    up = tmp / "units.json"
    up.write_text(json.dumps(g.gf_rows(), ensure_ascii=False), encoding="utf-8")
    return up


@pytest.mark.gate
def test_수정문구_단위는_수정쌍만이고_원천과_다르면_멈춘다(gf) -> None:
    tmp, _ = gf
    rows = g.gf_rows()
    assert [r["문구"] for r in rows] == [
        "MCT 함유",
        "초코맛",
        "*한글 표기",
    ]  # 위반문구 행은 안 든다
    assert all(g.GF_KEY_RE.match(r["지문"]) for r in rows)
    bad = [{**rows[0], "문구": "MCT 풍부함유"}]
    with pytest.raises(SystemExit):
        g.gf_units(bad)


@pytest.mark.gate
def test_수정문구_판은_식품_호를_받고_L_과_대상_N_을_받는다() -> None:
    assert g.gf_parse_line("gf:x\tY\t5.다\t-\t-\tC\t-\t")["근거"] == [statute.food(5, "다")]
    assert g.gf_parse_line("gf:x\tY\t-\t-\t-\tL\t-\tL 근거: …")["조건"] == "L"
    assert g.gf_parse_line("gf:x\tN\t-\t-\t-\t-\t-\t편집 메모")["문제"] == []
    assert g.gf_parse_line("gf:x\tY\t공3\t-\t-\tC\t-\t")["문제"]  # 표시광고법 코드는 식품 판에 없다
    assert g.gf_parse_line("gf:x\tY\t1.가.1\t-\t-\tA\t-\t")[
        "문제"
    ]  # 적용 제외는 근거가 아니다 (D-238)


@pytest.mark.gate
def test_수정문구_판도_식품_규칙으로_시트에_보낸다(gf) -> None:
    tmp, _ = gf
    k1, k2, k3 = (r["지문"] for r in g.gf_rows())
    r1 = tmp / "r1.tsv"
    r2 = tmp / "r2.tsv"
    # k1: 유형 2 에 3.나 → 합의여도 시트 (D-288) · k2: 둘 다 D → 채택 · k3: 둘 다 N → 채택(평가 밖)
    r1.write_text(
        HEAD + f"{k1}\tY\t3\t-\t-\tA\t3.나\t\n{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n",
        encoding="utf-8",
    )
    r2.write_text(
        HEAD + f"{k1}\tY\t3\t-\t-\tA\t3.나\t\n{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n",
        encoding="utf-8",
    )
    got = g.gf_merge(_units(tmp), r1, r2)
    assert got["시트"] == 1 and got["시트_이유"] == {"3.나": 1}
    assert got["채택"] == 2 and got["채택_대상아님(N)"] == 1
    # ⚠ 위반문구 판(`decide`)과 같은 함수다 — 한쪽만 고쳐지지 않게
    s = {"제품유형": "2. 성장기용 조제식", "문구": "x"}
    rec = {"제외목": ["3.나"]}
    assert g.food_guard(s, rec, {"제외목": []}, {}) == "3.나 유형 밖 (D-288)"
    assert g.food_guard({**s, "제품유형": "9. 체중조절용"}, rec, rec, {}) is None


@pytest.mark.gate
def test_수정문구는_대기가_0_일_때만_조건_D_행만_평가에_든다(gf) -> None:
    """🔄 2026-10-01 (판정 K1 (나) · D-299 · D-301) — 종전에는 채택 Y 전량이 평가에 들었다(판정 J1 (b))."""
    tmp, _ = gf
    k1, k2, k3 = (r["지문"] for r in g.gf_rows())
    r1 = tmp / "r1.tsv"
    r2 = tmp / "r2.tsv"
    r1.write_text(
        HEAD + f"{k1}\tY\t-\t-\t-\tL\t-\t\n{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n",
        encoding="utf-8",
    )
    r2.write_text(
        HEAD + f"{k1}\tY\t4\t-\t-\tA\t-\t\n{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n",
        encoding="utf-8",
    )
    got = g.gf_merge(_units(tmp), r1, r2)
    assert got["시트"] == 1  # L ↔ A 는 합성하지 않는다
    assert split.guide_fix_state()["대기"] == 1
    assert split.guide_fix_docs() == []  # 🔴 대기가 남으면 빈 목록
    for cond in ("L", "A", "B", "C", "M"):
        # 🔴 대기 0 이어도 D 가 아닌 수정문구는 들지 않는다 — 원천이 승인한 문구를 모델이 위반 · 적법으로 읽은 것이다 (D-237)
        same = (
            HEAD
            + f"{k1}\tY\t{'4' if cond in 'ABC' else '-'}\t-\t-\t{cond}\t-\t\n"
            + f"{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n"
        )
        r1.write_text(same, encoding="utf-8")
        r2.write_text(same, encoding="utf-8")
        g.gf_merge(_units(tmp), r1, r2)
        assert split.guide_fix_state()["대기"] == 0
        docs = split.guide_fix_docs()
        assert [d["doc_id"] for d in docs] == [k2], cond  # N 도 빠진다
    d = docs[0]
    assert d["조건"] == "D" and d["유형"] == [] and d["원천"] == "mfds_special_use_guide"
    assert not golden.is_negative({"labels": d["유형"], "조건": d["조건"]})  # D 는 L 이 아니다
    assert golden.lawful_kind({"id": f"{k2}#0", "labels": [], "조건": "D"}) == "주장없음"
    assert "labels/guide_fix/" in split.ROUND_LABEL_DIRS


@pytest.mark.gate
def test_적법_문장은_원천이_선언했거나_원천이_승인한_주장없음뿐이다() -> None:
    """🆕 2026-10-01 (D-301) — 「위반이라 하지 않았다」는 「적법이라 확인했다」가 아니다."""
    lk = golden.lawful_kind
    assert lk({"id": "ftc:1#a0", "labels": [], "조건": "L"}) == "주장"  # 원천 무혐의
    assert (
        lk({"id": "gf:abcdefghijkl#0", "labels": [], "조건": "D"}) == "주장없음"
    )  # 원천 승인 · 주장 없음
    # ⛔ 해설서 위반문구의 D — 원천이 삭제를 지시했다
    assert lk({"id": "guide:1#0", "labels": [], "조건": "D"}) is None
    assert (
        lk({"id": "gf:abcdefghijkl#0", "labels": [], "조건": "M"}) is None
    )  # 문장만으로 안 정해진다
    assert lk({"id": "x#0", "labels": [], "조건": "A"}) is None
    assert lk({"id": "ftc:1#0", "labels": ["거짓_과장"]}) is None


@pytest.mark.gate
def test_적법_문장_오탐률은_내역과_합계를_따로_낸다() -> None:
    from scripts import eval_rule

    rows = [
        {"id": "ftc:1#a0", "text": "울림", "labels": [], "조건": "L"},
        {"id": "ftc:2#a0", "text": "조용", "labels": [], "조건": "L"},
        {"id": "gf:abcdefghijkl#0", "text": "울림", "labels": [], "조건": "D"},
        {"id": "guide:1#0", "text": "울림", "labels": [], "조건": "D"},  # 세지 않는다
        {"id": "ftc:3#0", "text": "울림", "labels": ["거짓_과장"]},  # 위반 — 세지 않는다
    ]
    got = eval_rule.lawful_report(rows, lambda t: t == "울림")
    assert got == {"주장": (2, 1), "주장없음": (1, 1), "합계": (3, 2)}


# ── 결정문 봉인 문구 ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def fs(tmp_path, monkeypatch):
    d = tmp_path / "fs"
    _paths(monkeypatch, "FS", d)
    man = tmp_path / "split_manifest.json"
    man.write_text(
        json.dumps({"assign": {"ftc:1": split.SEALED, "ftc:2": "train"}}), encoding="utf-8"
    )
    monkeypatch.setattr(g, "FS_MANIFEST", man)
    # 🔄 2026-10-05 (D-312) — 학습 문구 판을 막는다 — 막지 않으면 기기의 실제 채택본이 이 모의 학습 문서에 걸려 멈춘다
    monkeypatch.setattr(split, "ftc_train_marks", lambda: None)
    # 🔄 2026-10-05 — 이유 구역 판도 같은 이유로 막는다(기기의 실제 채택본이 모의 이유 문구에 걸려 멈춘다)
    monkeypatch.setattr(split, "ftc_reason_marks", lambda: None)
    basis = [statute.fair(1)]
    docs = [
        {
            "doc_id": "ftc:1",
            "원천": "ftc_decisions_body",
            "근거": basis,
            "유형": statute.types_of(basis),
            "문구": ["업계 최초 5G", "GiGA LTE", "공기청정 제품"],
            "문구_이유": [],
            "문구_적법": [],
            "문구_이유_적법": [],
            "단위": "문장",
        },
        {
            "doc_id": "ftc:2",
            "원천": "ftc_decisions_body",
            "근거": basis,
            "유형": statute.types_of(basis),
            "문구": ["학습 문구"],
            "문구_이유": [],
            "문구_적법": [],
            "문구_이유_적법": [],
            "단위": "문장",
        },
    ]
    monkeypatch.setattr(split, "ftc_docs", lambda: docs)
    monkeypatch.setattr(split, "FTC_SEALED_READINGS", d / "readings.jsonl")
    monkeypatch.setattr(split, "FTC_SEALED_ADOPTED", d / "adopted.jsonl")
    return tmp_path, man, docs


def _fs_merge(tmp: pathlib.Path, lines1: list[str], lines2: list[str]) -> dict:
    up = tmp / "fs_units.json"
    up.write_text(json.dumps(g.fs_rows(), ensure_ascii=False), encoding="utf-8")
    r1, r2 = tmp / "f1.tsv", tmp / "f2.tsv"
    r1.write_text(HEAD + "\n".join(lines1) + "\n", encoding="utf-8")
    r2.write_text(HEAD + "\n".join(lines2) + "\n", encoding="utf-8")
    return g._merge(g.FS, up, r1, r2)


@pytest.mark.gate
def test_봉인_문구는_봉인_문서만이고_L_과_원천_밖_호는_팀장에게(fs) -> None:
    tmp, _, _ = fs
    rows = g.fs_rows()
    assert [r["문구"] for r in rows] == [
        "업계 최초 5G",
        "GiGA LTE",
        "공기청정 제품",
    ]  # 학습 문서는 안 든다
    k1, k2, k3 = (r["지문"] for r in rows)
    assert k1 == split.sealed_key("ftc:1", "업계 최초 5G")  # 골든과 같은 지문 함수 (D-99)
    got = _fs_merge(
        tmp,
        [
            f"{k1}\tY\t공3\t-\t-\tB\t실증\t",
            f"{k2}\tY\t-\t-\t-\tL\t-\t",
            f"{k3}\tN\t-\t-\t-\t-\t-\t",
        ],
        [
            f"{k1}\tY\t공3\t-\t-\tB\t실증\t",
            f"{k2}\tY\t-\t-\t-\tL\t-\t",
            f"{k3}\tN\t-\t-\t-\t-\t-\t",
        ],
    )
    assert got["시트"] == 2  # 원천은 공1 인데 공3 · 원천이 위반이라 한 문구에 L
    assert got["채택"] == 1 and got["채택_대상아님(N)"] == 1
    with pytest.raises(SystemExit):  # 봉인 문구 일부만 든 단위 표는 받지 않는다
        g.fs_units(rows[:2])


@pytest.mark.gate
def test_봉인_판이_끝나면_골든이_대상_N_을_빼고_조건을_붙인다(fs, tmp_path, monkeypatch) -> None:
    tmp, man, docs = fs
    k1, k2, k3 = (r["지문"] for r in g.fs_rows())
    same = [
        f"{k1}\tY\t공1\t-\t-\tB\t실증\t",
        f"{k2}\tY\t-\t-\t-\tM\t-\t이름만",
        f"{k3}\tN\t-\t-\t-\t-\t-\t",
    ]
    _fs_merge(tmp, same, same)
    assert split.ftc_sealed_state()["대기"] == 0
    inj = tmp_path / "inj.jsonl"
    inj.write_text("", encoding="utf-8")
    monkeypatch.setattr(golden, "SPLIT", man)
    monkeypatch.setattr(golden, "INJECTED", inj)
    monkeypatch.setattr(golden.split_mod, "verify_inputs", lambda m, who: None)
    monkeypatch.setattr(golden, "ftc_docs", lambda: docs)
    for name in ("approved_docs", "casebook_docs", "guide_docs", "caution_docs", "guide_fix_docs"):
        monkeypatch.setattr(golden, name, lambda: [])
    monkeypatch.setattr(golden, "lineage", lambda prov, origin: ("f", True))
    rows, stat = golden.build()
    sealed = {r["text"]: r for r in rows if r["split"] == split.SEALED}
    assert set(sealed) == {"업계 최초 5G", "GiGA LTE"}  # 🔴 대상 N 은 빠진다
    assert sealed["GiGA LTE"]["조건"] == "M" and sealed["업계 최초 5G"]["조건"] == "B"
    assert sealed["업계 최초 5G"]["근거"] == [statute.fair(1)]  # 호는 원천 그대로
    assert stat["봉인_대상아님(N)"] == 1
    train = [r for r in rows if r["split"] == "train"]
    assert train and "조건" not in train[0]  # 학습 문서는 판이 건드리지 않는다
    # 🔴 판에 없는 봉인 문구가 생기면(봉인이 바뀌었다) 조건 없이 내지 않고 멈춘다
    docs[0]["문구"].append("새 문구")
    with pytest.raises(SystemExit):
        golden.build()


@pytest.mark.gate
def test_봉인_문구가_조건_D_면_근거와_유형을_싣지_않는다(fs, tmp_path, monkeypatch) -> None:
    """🆕 2026-10-02 — 조건 D 는 판정 대상이 아니다. 의결서 호를 남기면 `check_basis` 가 골든을 멈춘다(B 기기 · 4 행)."""
    tmp, man, docs = fs
    k1, k2, k3 = (r["지문"] for r in g.fs_rows())
    same = [
        f"{k1}\tY\t공1\t-\t-\tB\t실증\t",
        f"{k2}\tY\t-\t-\t-\tD\t-\t표시사항",
        f"{k3}\tN\t-\t-\t-\t-\t-\t",
    ]
    _fs_merge(tmp, same, same)
    inj = tmp_path / "inj.jsonl"
    inj.write_text("", encoding="utf-8")
    monkeypatch.setattr(golden, "SPLIT", man)
    monkeypatch.setattr(golden, "INJECTED", inj)
    monkeypatch.setattr(golden.split_mod, "verify_inputs", lambda m, who: None)
    monkeypatch.setattr(golden, "ftc_docs", lambda: docs)
    for name in ("approved_docs", "casebook_docs", "guide_docs", "caution_docs", "guide_fix_docs"):
        monkeypatch.setattr(golden, name, lambda: [])
    monkeypatch.setattr(golden, "lineage", lambda prov, origin: ("f", True))
    rows, _ = golden.build()
    d = next(r for r in rows if r["text"] == "GiGA LTE")
    assert (d["조건"], d["근거"], d["labels"]) == ("D", [], [])
    assert not golden.is_positive(d) and not golden.is_negative(d)
    golden.check_basis(rows)  # 🔴 멈추지 않는다


@pytest.mark.gate
def test_골든_호_셈은_채점_행만_센다() -> None:
    """🆕 2026-10-02 — 유형이 남은 M 행 · D · L 은 호 셈(D-40)에 안 든다 — `split.tally_ho` 와 같은 규칙 (D-99)."""
    c = [statute.fair(2)]
    base = {"labels": statute.types_of(c), "근거": c}
    rows = [
        {**base, "조건": "B"},
        {**base, "조건": "M"},
        {**base},
        {"labels": [], "근거": [], "조건": "D"},
    ]
    assert golden.ho_counts(rows) == {statute.ho_key(c[0]): 2}


@pytest.mark.gate
def test_골든_호_셈은_서로_다른_글자로도_센다() -> None:
    """🆕 2026-10-04 (판정 묶음 ⑫) — 평가의 하한 30 은 같은 호 · 같은 글자를 한 번만 센 수에 건다.

    ⛔ 행으로만 세어 공정위 2호가 채점 행 25 로 보였는데 서로 다른 글자는 16 이었다(원장 10-03 ㊵).
    """
    c2, c3 = [statute.fair(2)], [statute.fair(3)]

    def row(c: list[str], text: str, **kw: str) -> dict:
        return {"labels": statute.types_of(c), "근거": c, "text": text, **kw}

    rows = [
        row(c2, "국내 최초 인증", 조건="B"),
        row(c2, "국내  최초 인증", 조건="C"),  # 공백만 다르다 — 같은 글자
        row(c2, "1) 국내 최초 인증"),  # 항목 번호 머리만 다르다 — 같은 글자(`overlap_key`)
        row(c2, "업계 1위", 조건="B"),
        row(c3, "국내 최초 인증", 조건="B"),  # 호가 다르면 따로 센다
        row(c2, "국내 최초 인증", 조건="M"),  # 채점 행이 아니다
    ]
    k2, k3 = statute.ho_key(c2[0]), statute.ho_key(c3[0])
    assert golden.ho_counts(rows) == {k2: 4, k3: 1}
    assert golden.ho_counts(rows, distinct=True) == {k2: 2, k3: 1}


# ── 블라인드 감사표 (판정 J6) ────────────────────────────────────────────────────────────


@pytest.mark.gate
def test_감사표는_판독을_싣지_않고_같은_seed_면_같은_표본이며_앞_감사를_덮지_않는다(gf) -> None:
    import csv

    tmp, _ = gf
    k1, k2, k3 = (r["지문"] for r in g.gf_rows())
    same = (
        HEAD
        + f"{k1}\tY\t4\t-\t-\tA\t-\t판독 메모\n{k2}\tY\t-\t-\t-\tD\t-\t\n{k3}\tN\t-\t-\t-\t-\t-\t\n"
    )
    r1 = tmp / "r1.tsv"
    r1.write_text(same, encoding="utf-8")
    g.gf_merge(_units(tmp), r1, r1)
    out = tmp / "sheet.csv"
    got = g.audit_sheet(g.GF, out, n=2, seed=7)
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert got["표본"] == 2 and len(rows) == 2
    assert all(not r[c] for r in rows for c in g.AUDIT_TAIL)  # 🔴 판독 값 · 판정자는 비어 있다
    assert "판독 메모" not in out.read_text(encoding="utf-8-sig")
    assert g.audit_pick([k1, k2, k3], 2, 7) == [r["지문"] for r in rows]  # 재현 (D-54)
    for r in rows:
        r.update({"대상": "Y", "조건": "D", "판정자": "팀장"})
    filled = tmp / "filled.csv"
    with filled.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    g.GF_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    g.GF_AUDIT.write_text('{"지문": "앞 감사"}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="덮지 않는다"):
        g._audit(g.GF, filled)
    assert g.GF_AUDIT.read_text(encoding="utf-8") == '{"지문": "앞 감사"}\n'
    got = g._audit(g.GF, filled, tmp / "audit__팀장.jsonl")
    assert got["감사"] == 2


# ── 2026-10-05 (D-312) 결정문 학습 문구 판 → 골든 학습 행 ──
def _train_golden(fs, tmp_path, monkeypatch, marks: dict | None):
    _tmp, man, docs = fs
    inj = tmp_path / "inj.jsonl"
    inj.write_text("", encoding="utf-8")
    monkeypatch.setattr(golden, "SPLIT", man)
    monkeypatch.setattr(golden, "INJECTED", inj)
    monkeypatch.setattr(golden.split_mod, "verify_inputs", lambda m, who: None)
    monkeypatch.setattr(golden, "ftc_docs", lambda: docs)
    for name in ("approved_docs", "casebook_docs", "guide_docs", "caution_docs", "guide_fix_docs"):
        monkeypatch.setattr(golden, name, lambda: [])
    monkeypatch.setattr(golden, "lineage", lambda prov, origin: ("f", True))
    monkeypatch.setattr(split, "ftc_sealed_marks", lambda: None)
    monkeypatch.setattr(split, "ftc_train_marks", lambda: marks)
    return docs


def _mark(doc: str, text: str, cond: str | None, target: str = "Y") -> tuple[str, dict]:
    k = split.train_key(doc, text)
    return k, {"지문": k, "대상": target, "조건": cond, "판독": "독립판독_합의"}


@pytest.mark.gate
def test_학습_판이_끝나면_골든_학습_행이_대상_N_을_빼고_조건을_붙인다(
    fs, tmp_path, monkeypatch
) -> None:
    """🔴 D-312 — 대상 이름 · 시장 용어가 위반 라벨로 학습에 남지 않는다. 봉인 문서의 행은 이 판이 건드리지 않는다."""
    docs = _train_golden(fs, tmp_path, monkeypatch, None)
    docs[1]["문구"] = ["실증 문구", "이름만", "시장 용어", "거래조건", "원천 무혐의"]
    marks = dict(
        [
            _mark("ftc:2", "실증 문구", "B"),
            _mark("ftc:2", "이름만", "M"),
            _mark("ftc:2", "시장 용어", None, "N"),
            _mark("ftc:2", "거래조건", "D"),
            _mark("ftc:2", "원천 무혐의", "L"),
        ]
    )
    monkeypatch.setattr(split, "ftc_train_marks", lambda: marks)
    rows, stat = golden.build()
    train = {r["text"]: r for r in rows if r["split"] == "train"}
    assert set(train) == {"실증 문구", "이름만", "거래조건", "원천 무혐의"}  # 🔴 대상 N 은 빠진다
    assert stat["학습_대상아님(N)"] == 1 and stat["학습_조건_M"] == 1
    assert train["실증 문구"]["조건"] == "B" and train["실증 문구"]["근거"] == [statute.fair(1)]
    assert (
        train["이름만"]["조건"] == "M" and train["이름만"]["labels"]
    )  # 호 · 유형은 원천 그대로 (봉인 판과 같다)
    for text in ("거래조건", "원천 무혐의"):  # D · L 은 근거 · 유형이 빈다 (`ck_golden_cond_empty`)
        assert (train[text]["근거"], train[text]["labels"]) == ([], [])
    assert golden.is_negative(train["원천 무혐의"]) and not golden.is_negative(train["거래조건"])
    sealed = [r for r in rows if r["split"] == split.SEALED]
    assert sealed and all("조건" not in r for r in sealed)  # 봉인 판이 없으면 봉인 행은 종전대로
    golden.check_basis(rows)


@pytest.mark.gate
def test_학습_주문_문구가_판에_없으면_조건_없이_내지_않고_멈춘다(fs, tmp_path, monkeypatch) -> None:
    """🔴 분할이 바뀌어 학습 문서가 달라지면 판을 다시 맞춘다 — 판정 없는 행이 섞이지 않는다 (D-220)."""
    _train_golden(fs, tmp_path, monkeypatch, {})
    with pytest.raises(SystemExit, match="학습 주문 문구가 판독 판에 없다"):
        golden.build()


@pytest.mark.gate
def test_학습_판의_대기가_남으면_골든은_종전대로다(tmp_path, monkeypatch) -> None:
    """대기가 0 일 때만 든다 — 채택본이 반만 선 판으로 학습 행을 바꾸지 않는다."""
    monkeypatch.setattr(split, "FTC_TRAIN_READINGS", tmp_path / "r.jsonl")
    monkeypatch.setattr(split, "FTC_TRAIN_ADOPTED", tmp_path / "a.jsonl")
    assert split.ftc_train_marks() is None  # 판이 없다
    (tmp_path / "r.jsonl").write_text('{"지문": "ft:a"}\n{"지문": "ft:b"}\n', encoding="utf-8")
    (tmp_path / "a.jsonl").write_text(
        '{"지문": "ft:a", "대상": "Y", "조건": "B"}\n', encoding="utf-8"
    )
    assert split.ftc_train_state()["대기"] == 1 and split.ftc_train_marks() is None
    assert split.FTC_TRAIN_ADOPTED not in split.inputs()


# ── 2026-10-05 결정문 이유 구역 문구 판 → 골든 학습 이유 행 (원장 10-03 ㊿-28) ──
def _rmark(
    doc: str, text: str, cond: str | None, basis: list[str] | None = None
) -> tuple[str, dict]:
    k = split.reason_key(doc, text)
    return k, {
        "지문": k,
        "대상": "N" if cond is None else "Y",
        "조건": cond,
        "근거": basis or [],
        "판독": "독립판독_합의",
    }


def _reason_golden(fs, tmp_path, monkeypatch, texts: list[str]):
    docs = _train_golden(fs, tmp_path, monkeypatch, None)
    two = [statute.fair(1), statute.fair(2)]
    docs[1] |= {"근거": two, "유형": statute.types_of(two), "문구": [], "문구_이유": texts}
    return two


@pytest.mark.gate
def test_이유_판이_끝나면_골든_이유_행이_대상_N_을_빼고_호를_좁힌다(
    fs, tmp_path, monkeypatch
) -> None:
    """🔴 이유 문구는 문서의 호를 내려 붙인 것이다 — 증거 이름 · 약칭이 위반 양성으로 남지 않고, 위반 행의 호는 판독이 고른 것이다."""
    texts = [
        "거짓 문구 하나",
        "이름만 있는 것",
        "증거 문서 이름",
        "가격 고지 문구",
        "원천 무혐의 문구",
    ]
    two = _reason_golden(fs, tmp_path, monkeypatch, texts)
    marks = dict(
        [
            _rmark("ftc:2", texts[0], "B", [statute.fair(1)]),
            _rmark("ftc:2", texts[1], "M", [statute.fair(1)]),
            _rmark("ftc:2", texts[2], None),
            _rmark("ftc:2", texts[3], "D"),
            _rmark("ftc:2", texts[4], "L"),
        ]
    )
    monkeypatch.setattr(split, "ftc_reason_marks", lambda: marks)
    rows, stat = golden.build()
    got = {r["text"]: r for r in rows if r.get("구역") == "이유"}
    assert set(got) == set(texts) - {texts[2]}  # 🔴 대상 N 은 빠진다
    assert stat["이유_대상아님(N)"] == 1 and stat["이유_조건_B"] == 1
    assert got[texts[0]]["근거"] == [statute.fair(1)]  # 🔴 문서의 두 호가 아니라 판독이 고른 호
    assert got[texts[0]]["labels"] == statute.types_of([statute.fair(1)])
    assert got[texts[1]]["조건"] == "M" and got[texts[1]]["근거"] == two  # M 은 문서의 호를 든 채
    for t in (texts[3], texts[4]):
        assert (got[t]["근거"], got[t]["labels"]) == ([], [])
    sealed = [r for r in rows if r["split"] == split.SEALED]
    assert sealed and all("조건" not in r for r in sealed)  # 평가 행은 이 판을 모른다
    golden.check_basis(rows)


@pytest.mark.gate
def test_이유_문구가_판에_없거나_호가_원천_밖이면_멈춘다(fs, tmp_path, monkeypatch) -> None:
    """🔴 판정 없는 양성이 섞이지 않는다 · 호는 의결서가 정한다 (D-220 · D-237)."""
    texts = ["거짓 문구 하나"]
    _reason_golden(fs, tmp_path, monkeypatch, texts)
    monkeypatch.setattr(split, "ftc_reason_marks", lambda: {})
    with pytest.raises(SystemExit, match="이유 문구가 판독 판에 없다"):
        golden.build()
    out = dict([_rmark("ftc:2", texts[0], "B", [statute.fair(4)])])
    monkeypatch.setattr(split, "ftc_reason_marks", lambda: out)
    with pytest.raises(SystemExit, match="원천.*밖"):
        golden.build()


@pytest.mark.gate
def test_이유_판의_대기가_남으면_골든은_종전대로다(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(split, "FTC_REASON_READINGS", tmp_path / "r.jsonl")
    monkeypatch.setattr(split, "FTC_REASON_ADOPTED", tmp_path / "a.jsonl")
    assert split.ftc_reason_marks() is None  # 판이 없다
    (tmp_path / "r.jsonl").write_text('{"지문": "fr:a"}\n{"지문": "fr:b"}\n', encoding="utf-8")
    (tmp_path / "a.jsonl").write_text('{"지문": "fr:a", "대상": "N"}\n', encoding="utf-8")
    assert split.ftc_reason_state()["대기"] == 1 and split.ftc_reason_marks() is None
    assert split.FTC_REASON_ADOPTED not in split.inputs()


@pytest.mark.gate
def test_이유_판의_지문과_경로는_분할과_판이_같은_것을_본다() -> None:
    """D-99 — 지문 함수 · 산출물 경로가 두 모듈에서 갈리면 골든이 판을 못 찾는다."""
    k = split.reason_key("ftc:1", "문구")
    assert (
        g.FR_KEY_RE.match(k)
        and k.split(":", 1)[1] == split.sealed_key("ftc:1", "문구").split(":", 1)[1]
    )
    assert g.FR_READINGS == g.ROOT / split.FTC_REASON_READINGS
    assert g.FR_ADOPTED == g.ROOT / split.FTC_REASON_ADOPTED
    assert "labels/ftc_reason/" in split.ROUND_LABEL_DIRS


def test_판독의_부근거_칸은_쉼표로_여럿을_받는다() -> None:
    """세 호가 걸린 결정문 — 주근거 하나 + 부근거 둘. 한 호만 적는 종전 줄은 그대로 읽힌다."""
    rec = g._parse(g.FR, "fr:aaaaaaaaaaaa\tY\t공4\t공1,공3\t-\tB\t실증\t메모")
    assert not rec["문제"] and rec["근거"] == [statute.fair(4), statute.fair(1), statute.fair(3)]
    one = g._parse(g.FR, "fr:aaaaaaaaaaaa\tY\t공1\t-\t-\tB\t실증\t")
    assert not one["문제"] and one["근거"] == [statute.fair(1)]
    bad = g._parse(g.FR, "fr:aaaaaaaaaaaa\tY\t공1\t공2,엉뚱\t-\tB\t실증\t")
    assert bad["문제"]  # 모르는 꼴은 문제로 남는다(조용히 버리지 않는다)


# ── 2026-10-05 표시광고법 사건만 분할에 든다 (원장 10-03 ㊿-27) ──
def _phrases(tmp_path, monkeypatch, recs: list[dict]) -> None:
    p = tmp_path / "phrases.json"
    p.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(split, "FTC_PHRASES", p)


def _rec(seq: str, law: str | None) -> dict:
    r = {
        "seq": seq,
        "문구": ["문구 하나"],
        "문구_이유": [],
        "유형": [{"label": "거짓_과장", "article": "제3조제1항제1호"}],
    }
    return r if law is None else r | {"적용법": law}


@pytest.mark.gate
def test_표시광고법_사건이_아니면_분할에_들지_않는다(tmp_path, monkeypatch) -> None:
    """🔴 전자상거래법 사건이 표시광고법 호를 달고 학습에 들어가 있었다(46 문서 · 골든 488 행)."""
    from preprocess import ftc_triage as tr

    _phrases(
        tmp_path,
        monkeypatch,
        [
            _rec("1", tr.LAW_AD),
            _rec("2", "전자상거래법"),
            _rec("3", tr.LAW_AD_UNNAMED),
            _rec("4", "공정거래법"),
        ],
    )
    assert [d["doc_id"] for d in split.ftc_docs()] == ["ftc:1", "ftc:3"]


@pytest.mark.gate
def test_적용법을_못_읽었거나_칸이_없으면_멈춘다(tmp_path, monkeypatch) -> None:
    """🔴 조용히 넣지도 빼지도 않는다 (D-220)."""
    from preprocess import ftc_triage as tr

    _phrases(tmp_path, monkeypatch, [_rec("1", None)])
    with pytest.raises(SystemExit, match="적용법"):
        split.ftc_docs()
    _phrases(tmp_path, monkeypatch, [_rec("1", tr.LAW_UNKNOWN)])
    with pytest.raises(SystemExit, match="적용된 법을 못 읽었다"):
        split.ftc_docs()


def test_적용법은_표시광고법이_적혔으면_표시광고법이다() -> None:
    from preprocess import ftc_triage as tr

    law = lambda t: tr.case_law("", t, "", "")  # noqa: E731
    assert law("표시·광고의 공정화에 관한 법률 제3조") == tr.LAW_AD
    assert law("전자상거래 등에서의 소비자보호에 관한 법률 제21조 및 표시광고법 제3조") == tr.LAW_AD
    assert law("전자상거래 등에서의 소비자보호에 관한 법률 제21조제1항제1호") == "전자상거래법"
    assert law("독점규제 및 공정거래에 관한 법률 제23조") == "공정거래법"
    assert law("법 제3조 제1항 제1호에 해당") == tr.LAW_AD_UNNAMED
    assert law("주문 없음") == tr.LAW_UNKNOWN
    assert {tr.LAW_AD, tr.LAW_AD_UNNAMED} == tr.AD_LAWS
