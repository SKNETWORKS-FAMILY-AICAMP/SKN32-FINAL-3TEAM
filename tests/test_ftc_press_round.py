"""공정위 보도자료 1997~2007 문구 판 — 사건 레코드 → 판독 → 채택 → 평가 (2026-09-30 · 동결 전 판정 ⑤-1·3 (나)).

🔴 무엇을 막나
   ① 마스킹 정책 없이 · 또는 문구만 따로 마스킹해(문맥의 상호가 남는다) 보도자료 문구가 판독 원자료로 가는 것 (D-72)
   ② 원천 본문에 없는 문구(뽑은 이가 고쳐 쓴 것 · 원천이 바뀐 것)가 채택되는 것 (D-220)
   ③ 화장품 코드(1 · 2 · 4 · 별표5목)가 보도자료 판독에 섞이는 것
   ④ 판정 대기가 남았는데 평가에 들어가는 것 · 대상 N 이 평가에 들어가는 것
   ⑤ 화장품 판과 채택 규칙이 갈리는 것 — 같은 `_agree` 를 쓴다 (D-99)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from collect import statute
from preprocess import ftc_press_old, hwp3, mask, split
from scripts import guide_statute_round as g

HEAD = "지문\t대상\t주근거\t부근거\t별표5목\t조건\t제외목\t메모\n"


def _jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def fp(tmp_path, monkeypatch):
    d = tmp_path / "fp"
    for name, fn in (
        ("FP_READINGS", "readings.jsonl"),
        ("FP_ADOPTED", "adopted.jsonl"),
        ("FP_DECISIONS", "decisions.jsonl"),
        ("FP_AUDIT", "audit.jsonl"),
        ("FP_TEAM_SHEET", "team.csv"),
    ):
        monkeypatch.setattr(g, name, d / fn)
    cases = tmp_path / "cases.jsonl"
    _jsonl(
        cases,
        [
            {"사건": "1", "본문": "듀라셀은 2배,\n 3배 최고 5배 오래갑니다 라고 광고"},
            {"사건": "2", "본문": "경쟁사는 부도덕한 기업이라고 광고"},
        ],
    )
    monkeypatch.setattr(g, "FP_CASES", cases)
    monkeypatch.setattr(split, "FTC_PRESS_READINGS", d / "readings.jsonl")
    monkeypatch.setattr(split, "FTC_PRESS_ADOPTED", d / "adopted.jsonl")
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    k1 = g.fp_key_of("1", "듀라셀은 2배, 3배 최고 5배 오래갑니다")
    k2 = g.fp_key_of("2", "부도덕한 기업")
    units = [
        {
            "지문": k1,
            "사건": "1",
            "문구": "듀라셀은 2배, 3배 최고 5배 오래갑니다",
            "원천판단": "부당한 비교광고",
            "마스킹": True,
        },
        {"지문": k2, "사건": "2", "문구": "부도덕한 기업", "원천판단": "비방광고", "마스킹": True},
    ]
    up = tmp_path / "units.json"
    up.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    r1 = tmp_path / "r1.tsv"
    r1.write_text(
        HEAD + f"{k1}\tY\t공3\t-\t-\tC\t-\t\n{k2}\tY\t공4\t-\t-\tC\t-\t\n", encoding="utf-8"
    )
    r2 = tmp_path / "r2.tsv"
    r2.write_text(
        HEAD + f"{k1}\tY\t공3\t-\t-\tB\t실증\t\n{k2}\tY\t공4\t-\t-\tL\t-\t\n", encoding="utf-8"
    )
    return up, r1, r2, k1, k2


@pytest.mark.gate
def test_보도자료_판독은_표시광고법_호만_받는다() -> None:
    assert g.fp_parse_line("fp:x\tY\t공3\t공4\t-\tC\t-\t")["근거"] == [
        statute.fair(3),
        statute.fair(4),
    ]
    assert g.fp_parse_line("fp:x\tY\t1\t-\t-\tC\t-\t")["문제"]  # 화장품법 코드
    assert g.fp_parse_line("fp:x\tY\t공3\t-\t가\tC\t-\t")["문제"]  # 별표5목은 화장품 칸
    assert g.fp_parse_line("fp:x\tY\t공3\t-\t-\tB\t기능성심사\t")["문제"]  # 화장품 제외목


@pytest.mark.gate
def test_지문은_사건과_공백을_접은_문구로_정해진다() -> None:
    assert g.fp_key_of("1", "가 나\n 다") == g.fp_key_of("1", "가 나 다")
    assert g.fp_key_of("1", "가 나 다") != g.fp_key_of("2", "가 나 다")
    assert g.FP_KEY_RE.match(g.fp_key_of("1", "문구"))


@pytest.mark.gate
def test_마스킹_전_문구는_받지_않는다(fp) -> None:
    *_, k1, _k2 = fp
    u = {"지문": k1, "사건": "1", "문구": "듀라셀은 2배, 3배 최고 5배 오래갑니다", "원천판단": "x"}
    with pytest.raises(SystemExit, match="마스킹 전 문구"):
        g.fp_units([u])


@pytest.mark.gate
def test_문구는_본문_안에서_마스킹된다(monkeypatch) -> None:
    """🔴 문구만 따로 걸면 문서가 밝힌 상호가 문구에 남는다(34657 실측) — 본문 안에서 걸어 꺼낸다."""
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = "(주)대한항공은 광고에서\n동경 여행은 따져 볼수록 대한항공이 더욱 편리합니다\n라는 제목"
    phrase = "동경 여행은 따져 볼수록 대한항공이 더욱 편리합니다"
    assert "대한항공" in mask.apply_policy(phrase, "", "ftc_press", [])  # 따로 걸면 남는다
    got, bad = ftc_press_old.mask_units(
        [{"사건": "9", "본문": body}], [{"지문": "fp:x", "사건": "9", "문구": phrase}]
    )
    assert not bad and "대한항공" not in got[0]["문구"] and got[0]["마스킹"] is True
    assert got[0]["문구"] in mask.apply_policy(body, "", "ftc_press", [])
    _, bad = ftc_press_old.mask_units(
        [{"사건": "9", "본문": body}], [{"지문": "fp:y", "사건": "9", "문구": "없는 문구"}]
    )
    assert bad


@pytest.mark.gate
def test_뒷붙이_약칭으로_적은_상호의_맨몸_언급도_지운다(monkeypatch) -> None:
    """🔴 「○○(주)의 부당한 광고행위」 꼴 — 자리 치환은 「○○(주)」만 지우고 문구 속 맨몸 「○○는」을 남겼다.

    실측 2026-10-04(원장 10-03 ㊸) — 정책 초안을 걸었을 때 문구 119 중 19 에 문서가 밝힌 상호가 남았다.
    """
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = "가나다맥주(주)의 부당한 광고행위에 대한 시정명령\n가나다맥주는 100% 국내자본기업\n이라고 광고"
    phrase = "가나다맥주는 100% 국내자본기업"
    assert "가나다맥주" in mask.apply_policy(body, "", "ftc_press", [])  # 정책만으로는 남는다
    got, bad = ftc_press_old.mask_units(
        [{"사건": "9", "본문": body}], [{"지문": "fp:x", "사건": "9", "문구": phrase}]
    )
    assert not bad and got[0]["문구"] == "[업체]는 100% 국내자본기업"
    assert (
        "가나다맥주"
        not in ftc_press_old.masked([{"사건": "9", "제목": "가나다맥주 건", "본문": body}])[0][0][
            "제목"
        ]
    )


@pytest.mark.gate
def test_원천판단_칸과_줄넘김으로_갈린_이름도_지운다(monkeypatch) -> None:
    """🔴 문구 말고 글이 든 칸(`원천판단`)이 그대로 파생물에 실렸다(실측 10 / 119) · 괘선 칸은 낱말 안에서 줄이 바뀐다."""
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = "한국라마바(주)에 대해 비방한 광고\n이 성분을 써 온 라마 바사는 물의를 빚자\n라는 문구 · 라마바(주)가 받은 상"
    got, bad = ftc_press_old.mask_units(
        [{"사건": "9", "본문": body}],
        [
            {
                "지문": "fp:x",
                "사건": "9",
                "문구": "이 성분을 써 온 라마 바사는 물의를 빚자",
                "원천판단": "라마바사를 비방한 광고",
            }
        ],
    )
    assert not bad
    assert "라마" not in got[0]["문구"] and "라마바" not in got[0]["원천판단"]


@pytest.mark.gate
def test_앞말은_상호로_잡지_않는다() -> None:
    """「공정위는 (주)○○」 · 「피심인과 (주)○○」의 앞말을 상호로 읽으면 본문의 그 낱말이 전부 지워진다."""
    names = ftc_press_old.doc_names(
        "공정거래위원회는 (주)가나다와 경쟁사업자인 (주)라마바산업에 대해"
    )
    assert "공정거래위원회는" not in names and "경쟁사업자인" not in names
    assert "라마바산업" in names


@pytest.mark.gate
def test_뒷붙이_법인격_뒤의_말은_상호가_아니다(monkeypatch) -> None:
    """🔴 「○○(주)의 부당한 광고행위」에서 「부당한」이 상호로 들어 그 낱말이 `[업체]` 가 됐다(원장 10-03 ㊽ · 2 사건)."""
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = (
        "가나다맥주(주)의 부당한 광고행위\n부당한 광고행위에 대한 시정명령 · 가나다맥주는 광고에서"
    )
    assert not [n for n in ftc_press_old.doc_names(body) if "부당한" in n]
    out, _, _ = ftc_press_old.masked([{"사건": "9", "제목": "건", "본문": body}])
    assert out[0]["본문"].count("부당한") == 2 and "가나다맥주" not in out[0]["본문"]
    # 풀어 쓴 법인격이나 띄어 쓴 앞붙이로도 나오는 말은 상호로 둔다
    assert "라마바" in ftc_press_old.doc_names("가나다(주)라마바 · 라마바 주식회사는")


@pytest.mark.gate
@pytest.mark.parametrize(
    ("text", "gone"),
    [
        ("가나다(주)(대표 홍길동)에 대해", "홍길동"),
        ("가나다(주)[대표이사 성춘향]의 광고", "성춘향"),
        ("가나다(주)[代表\uf9e4事 洪吉童]\n이 자사의", "洪吉童"),
        ("피심인: 가나다(주)(대표이사 성춘향\n피심인 일반현황", "성춘향"),
    ],
)
def test_괄호_속_대표자_이름을_지운다(text: str, gone: str) -> None:
    """🔴 「(대표 ○○○)」 · 한자 직함 · 성씨 목록 밖 이름이 본문에 남았다(실측 4 사건 · 원장 10-03 ㊾)."""
    got = ftc_press_old.mask_paren_ceo(text)
    assert gone not in got and "[대표]" in got


def test_괄호_대표_규칙은_보통_말을_건드리지_않는다() -> None:
    for text in ("(대표 상품은 다음과 같다)", "자사의 대표 제품인 가나다", "(대표적인 예)"):
        assert ftc_press_old.mask_paren_ceo(text) == text


@pytest.mark.gate
def test_괘선으로_갈린_상호를_통째로_지운다(monkeypatch) -> None:
    """🔴 「가나 │⏎│ 다건설(주)」 — 자리 치환이 뒷조각만 지워 앞조각이 남았다(실측 3 · 원장 10-03 ㊾)."""
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = "가나다건설(주)의 부당한 광고\n│ 경쟁사업자인 가나   │\n│ 다건설(주)가 시공한 │"
    out, _, log = ftc_press_old.masked([{"사건": "9", "제목": "건", "본문": body}])
    assert "가나" not in out[0]["본문"] and "다건설" not in out[0]["본문"]
    assert any(e.get("규칙") == "갈린상호" for e in log)


@pytest.mark.gate
def test_사건별_이름_목록의_표기를_지우고_남으면_멈춘다(monkeypatch) -> None:
    """🔴 약칭 · 상호와 같은 글자의 상표는 규칙으로 못 잡는다 — 사람이 확인한 목록으로 지운다(검토요청 §3-6 (ㅁ′))."""
    monkeypatch.setitem(mask.POLICY, "ftc_press", mask.POLICY["ftc"])
    body = "가나다맥주(주)의 부당한 광고행위\n오직 가나만이 국내자본\n연락처 : 02) 123-4567(홍보실)"
    rows = [{"사건": "9", "제목": "가나 광고 건", "본문": body}]
    unit = {
        "지문": "fp:x",
        "사건": "9",
        "문구": "오직 가나만이 국내자본",
        "원천판단": "가나의 광고",
    }
    listed = {"9": [("02) 123-4567(홍보실)", "연락처"), ("가나", "회사")]}
    assert "가나만이" in ftc_press_old.masked(rows)[0][0]["본문"]  # 목록 없이는 남는다
    out, _, log = ftc_press_old.masked(rows, listed)
    assert "가나" not in out[0]["본문"] + out[0]["제목"] and "123-4567" not in out[0]["본문"]
    assert not ftc_press_old.records_left(out, listed)
    assert sum(e.get("규칙") == "이름목록" for e in log) >= 3
    got, bad = ftc_press_old.mask_units(rows, [unit], listed)
    assert (
        not bad
        and got[0]["문구"] == "오직 [업체]만이 국내자본"
        and "가나" not in got[0]["원천판단"]
    )
    # 다른 사건의 목록은 걸리지 않는다
    assert "가나만이" in ftc_press_old.masked(rows, {"8": [("가나", "회사")]})[0][0]["본문"]
    # 남은 것을 세는 쪽이 지우는 쪽과 같은 꼴을 본다(줄넘김으로 갈린 표기)
    assert ftc_press_old.listed_left("가 \n나의 광고", [("가나", "회사")]) == 1


@pytest.mark.gate
def test_이름_목록은_지문과_다르면_멈춘다(tmp_path, monkeypatch) -> None:
    """🔴 목록은 저장소 밖(실명)이고 저장소에는 수와 지문만 있다 — 없거나 다르면 파생을 쓰지 않는다 (D-220)."""
    csv_path = tmp_path / "이름목록.csv"
    lock_path = tmp_path / "lock.json"
    head = "사건,표기,갈래,처리,메모\n"
    csv_path.write_text(
        head + "9,가나,회사,지움,\n9,가나 우유,회사,뺌,상표\n", encoding="utf-8-sig"
    )
    monkeypatch.setattr(ftc_press_old, "NAMES", csv_path)
    monkeypatch.setattr(ftc_press_old, "NAMES_LOCK", lock_path)
    with pytest.raises(SystemExit, match="지문이 저장소에"):
        ftc_press_old.load_names()
    listed = ftc_press_old.read_names(csv_path)
    assert listed == {"9": [("가나", "회사")]}  # 「뺌」은 싣지 않는다
    lock = ftc_press_old.names_lock(listed)
    assert "가나" not in json.dumps(lock, ensure_ascii=False) and lock["9"]["수"] == 1
    lock_path.write_text(json.dumps({"사건": lock}, ensure_ascii=False), encoding="utf-8")
    assert ftc_press_old.load_names() == listed
    csv_path.write_text(head + "9,가나다,회사,지움,\n", encoding="utf-8-sig")
    with pytest.raises(SystemExit, match="지문과 다르다"):
        ftc_press_old.load_names()
    csv_path.unlink()
    with pytest.raises(SystemExit, match="가 없다"):
        ftc_press_old.load_names()
    for bad in ("9,가,회사,지움,\n", "9,가나,상표,지움,\n"):
        csv_path.write_text(head + bad, encoding="utf-8-sig")
        with pytest.raises(ValueError, match="행"):
            ftc_press_old.read_names(csv_path)


@pytest.mark.gate
def test_저장소의_이름_목록_지문은_표기를_싣지_않는다() -> None:
    lock = json.loads(ftc_press_old.NAMES_LOCK.read_text(encoding="utf-8"))["사건"]
    assert lock and all(set(v) == {"수", "지문"} and len(v["지문"]) == 12 for v in lock.values())


@pytest.mark.gate
def test_마스킹_정책이_없으면_멈춘다() -> None:
    assert "ftc_press" not in mask.POLICY or pytest.skip(
        "정책이 등재됐다 — 이 게이트는 등재 전 판을 지킨다"
    )
    with pytest.raises(mask.MaskPolicyError):
        ftc_press_old.mask_units(
            [{"사건": "9", "본문": "광고 문구"}],
            [{"지문": "fp:x", "사건": "9", "문구": "광고 문구"}],
        )


@pytest.mark.gate
def test_괘선_표는_칸마다_이어_붙인다() -> None:
    table = (
        "┌───┬──────┐\n"
        "│허위 │·어떠한 조건에서도 │\n"
        "│·과장│ 환경 │\n"
        "│ │ 호르몬이 검출되지 │\n"
        "├───┼──────┤\n"
        "│비방 │·왜 아기에게 │\n"
        "└───┴──────┘"
    )
    cells = ftc_press_old.box_cells(table)
    assert "·어떠한 조건에서도 환경 호르몬이 검출되지" in cells
    assert "허위 ·과장" in cells and "·왜 아기에게" in cells


@pytest.mark.gate
def test_한글3_조합형_글자와_잡음_조각() -> None:
    assert hwp3.char_of(0x8861) == "가"  # 조합형 「가」
    assert hwp3.char_of(ord("A")) == "A" and hwp3.char_of(13) == "\n" and hwp3.char_of(5) == "\x00"
    assert hwp3._junk("몔뭉") and hwp3._junk("잆딬몔뭉")  # 이진 값이 만든 짧은 덩어리
    assert not hwp3._junk("국산 태양초 100%") and not hwp3._junk("헛똑똑이 엄마는 되지 않겠다!")


@pytest.mark.gate
def test_원천_본문에_없는_문구면_멈춘다(fp, tmp_path) -> None:
    *_, k1, _k2 = fp
    with pytest.raises(SystemExit, match="원천과 어긋난다"):
        g.fp_units([{"지문": k1, "사건": "1", "문구": "고쳐 쓴 문구", "원천판단": "x"}])


@pytest.mark.gate
def test_채택은_화장품과_같은_규칙이고_다시_계산해도_같다(fp) -> None:
    up, r1, r2, k1, _k2 = fp
    got = g.fp_merge(up, r1, r2)
    first = g.FP_ADOPTED.read_bytes()
    assert got["채택"] == 1 and got["시트"] == 1  # C↔B → C · C↔L 은 시트
    assert g.fp_rebuild() == got and g.FP_ADOPTED.read_bytes() == first
    row = json.loads(first.decode().splitlines()[0])
    assert row["지문"] == k1 and row["조건"] == "C" and row["근거"] == [statute.fair(3)]
    assert row["사건"] == "1" and row["원천판단"] == "부당한 비교광고"


@pytest.mark.gate
def test_대기가_남으면_평가에_없다(fp) -> None:
    up, r1, r2, *_ = fp
    g.fp_merge(up, r1, r2)
    assert split.ftc_press_state() == {"전체": 2, "채택": 1, "대기": 1}
    assert split.ftc_press_docs() == []
    assert split.FTC_PRESS_ADOPTED not in split.inputs()
