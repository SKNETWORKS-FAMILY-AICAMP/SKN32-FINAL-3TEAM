"""`collect.law_api` — 중앙부처 1차 해석(`mfdsCgmExpc`) 갈래 (2026-09-18).

🚨 **네트워크를 쓰지 않는다.** `_call` · `registry.require` · `store.save_raw` 를 갈아 끼운다.
   응답 모양은 2026-09-18 API 탐침 실측(사용자 실행 · 일련번호 458622)을 줄여 옮긴 것이다.

지키는 것 — `INTERP_TARGETS` 주석의 셋.

   ① 게이트와 원장이 **자기 소스 id**(`mfds_cgm_expc`)로 간다 — `law_go_kr` 서명을 빌리지 않는다
   ② 사건명 필터를 걸지 않고 **전량**을 받는다 — 제목에 광고가 없는 광고 판정이 있다
   ③ 🔴 **키 값이 raw 에 들어가지 않는다** — 목록 응답은 저장하지 않고, 본문에 키가 섞이면 저장하지 않는다

🚨 게이트(`gate`)가 아니다 — 수집기 단위 테스트다 (D-89). 파생물을 안 읽어 어느 기기에서든 돈다.
"""

from __future__ import annotations

import pytest

from collect import COLLECTORS
from collect import law_api as L

KEY = "SECRETOC"

#: 목록 — 🚨 서버가 `법령해석상세링크` 에 OC 를 되돌려준다 (실측). 두 건.
LIST = (
    '<?xml version="1.0" encoding="UTF-8"?><CgmExpc><target>mfdsCgmExpc</target>'
    "<totalCnt>2</totalCnt><page>1</page><resultCode>00</resultCode>"
    '<cgmExpc id="1"><법령해석일련번호>458622</법령해석일련번호>'
    "<안건명><![CDATA[필링젤은 기초화장품인가 · 항균 표시 가능한가]]></안건명>"
    "<해석기관명>식품의약품안전처</해석기관명><해석일자>2024.12.12</해석일자>"
    f"<법령해석상세링크>/DRF/lawService.do?OC={KEY}&amp;target=mfdsCgmExpc&amp;ID=458622"
    "</법령해석상세링크></cgmExpc>"
    '<cgmExpc id="2"><법령해석일련번호>411074</법령해석일련번호>'
    "<안건명><![CDATA[강아지용 물병 수입신고 대상인가요]]></안건명>"
    f"<법령해석상세링크>/DRF/lawService.do?OC={KEY}&amp;target=mfdsCgmExpc&amp;ID=411074"
    "</법령해석상세링크></cgmExpc></CgmExpc>"
).encode()


def _body(
    case_id: str, answer: str = "「항균」 표현은 인체세정용 제품에 한하여 …", extra: str = ""
) -> bytes:
    """본문 — 🚨 실측에서 본문에는 OC 가 **없다.** `extra` 로 섞는 경우를 만든다."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?><CgmExpcService>'
        f"<법령해석일련번호>{case_id}</법령해석일련번호>"
        "<안건명><![CDATA[질의]]></안건명><해석일자>20241212</해석일자>"
        "<해석기관명>식품의약품안전처</해석기관명>"
        "<질의요지><![CDATA[질의]]></질의요지>"
        f"<회답><![CDATA[{answer}]]></회답><이유><![CDATA[]]></이유>"
        f"<관련법령><![CDATA[「화장품법」 제2조]]></관련법령>{extra}"
        "</CgmExpcService>"
    ).encode()


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> dict:
    """가짜 원천. `bodies` 를 바꿔 끼워 경우를 만든다."""
    w: dict = {"required": [], "saved": [], "calls": [], "bodies": {}}

    def fake_call(base: str, oc: str, **params: str) -> bytes:
        w["calls"].append((base, params))
        if base == L.BASE_SEARCH:
            return LIST
        return w["bodies"].get(params["ID"], _body(params["ID"]))

    monkeypatch.setattr(L, "_call", fake_call)
    monkeypatch.setattr(L.env, "get", lambda name: KEY)
    monkeypatch.setattr(L.registry, "require", lambda sid, use: w["required"].append((sid, use)))
    monkeypatch.setattr(
        L.store,
        "save_raw",
        lambda sid, family, filename, payload, *, url: (
            w["saved"].append((sid, family, filename, payload, url)) or filename
        ),
    )
    return w


def test_게이트는_자기_소스_id_로_지난다(world: dict) -> None:
    """① — `law_go_kr` 의 서명으로 1차 해석을 받으면 등재를 나눈 뜻이 없어진다 (D-90)."""
    L.collect_cases("mfdsCgmExpc")
    assert world["required"] == [("mfds_cgm_expc", "U1")]


def test_원문은_소스_폴더에_본문만_저장한다(world: dict) -> None:
    """① · ③ — `data/raw/law/` 에 섞지 않는다(D-245). 목록 응답은 한 번도 저장되지 않는다."""
    saved, failed = L.collect_cases("mfdsCgmExpc")
    assert (saved, failed) == (2, 0)
    assert {s[0] for s in world["saved"]} == {"mfds_cgm_expc"}
    assert {s[1] for s in world["saved"]} == {"mfds_cgm_expc"}, "원문 폴더가 소스 id 가 아니다"
    assert all(b"<CgmExpcService>" in s[3] for s in world["saved"]), "목록 응답이 저장됐다"


def test_사건명_필터를_걸지_않고_전량을_받는다(world: dict) -> None:
    """② — 「강아지용 물병」은 판례용 어휘로는 탈락이지만 1차 해석에서는 받는다 (거르기는 preprocess)."""
    assert not L._in_domain("강아지용 물병 수입신고 대상인가요"), "전제: 판례 필터라면 탈락한다"
    L.collect_cases("mfdsCgmExpc")
    got = {s[2] for s in world["saved"]}
    assert got == {"mfdsCgmExpc_458622.xml", "mfdsCgmExpc_411074.xml"}


def test_질의로_좁히지_않는다(world: dict) -> None:
    """② — 검색은 빈 질의 한 번(사건명 검색)뿐이다. 본문 검색 · 질의 목록을 돌지 않는다."""
    L.collect_cases("mfdsCgmExpc")
    searches = [p for b, p in world["calls"] if b == L.BASE_SEARCH]
    assert searches and all(p["query"] == "" for p in searches)
    assert all(p["search"] == L.SEARCH_NAME for p in searches)


def test_키가_섞인_본문은_저장하지_않는다(world: dict) -> None:
    """③ 🔴 — 형식이 바뀌어 본문에 키가 들어오는 날, raw 에 박히기 전에 멈춘다 (D-220).

    🚨 반대 대조 — 위 테스트들에서 멀쩡한 본문은 저장됐다. 여기서 **한 건만** 막혀야 한다.
    """
    world["bodies"]["458622"] = _body("458622", extra=f"<링크>?OC={KEY}</링크>")
    saved, failed = L.collect_cases("mfdsCgmExpc")
    assert (saved, failed) == (1, 1)
    assert all(KEY.encode() not in s[3] for s in world["saved"])


def test_회답이_빈_해석은_성공으로_세지_않는다(world: dict) -> None:
    """내용 없는 응답이 「새로 저장」으로 집계되지 않는다 (D-220)."""
    world["bodies"]["411074"] = _body("411074", answer="")
    saved, failed = L.collect_cases("mfdsCgmExpc")
    assert (saved, failed) == (1, 1)


def test_짧은_회답도_크기로_떨어지지_않는다(world: dict) -> None:
    """🚨 `MIN_BODY`(1 KB)를 1차 해석에 걸면 짧은 회답이 실패가 된다 — 크기가 아니라 필드로 가른다."""
    short = _body("458622", answer="가능합니다.")
    assert len(short) < L.MIN_BODY, "전제: 이 응답은 1 KB 아래다"
    world["bodies"]["458622"] = short
    saved, failed = L.collect_cases("mfdsCgmExpc")
    assert (saved, failed) == (2, 0)


def test_런처_표가_1차_해석을_법제처_수집기의_target_으로_보낸다() -> None:
    """런처는 표를 읽는다 (D-179). `target` 값은 표가 든다 — 런처가 추정하지 않는다."""
    module, shape = COLLECTORS["mfds_cgm_expc"]
    assert module == "collect.law_api"
    assert shape.partition("=")[2] in L.INTERP_TARGETS
    assert L.INTERP_TARGETS[shape.partition("=")[2]] == "mfds_cgm_expc"
    assert COLLECTORS["law_go_kr"][1] == "target", "법령 경로가 바뀌면 안 된다"


def test_런처_collect_가_target_과_옵션을_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """`launcher.py collect <소스> --dry-run --limit N` 이 수집기 인자로 그대로 간다.

    🚨 반대 대조 — 법령(`law_go_kr`)은 여전히 `--target law` 다.
    """
    import typer

    import launcher

    got: list[tuple[str, ...]] = []
    monkeypatch.setattr(launcher, "run", lambda *a: got.append(a) or 0)
    with pytest.raises(typer.Exit):
        launcher.collect("mfds_cgm_expc", use=None, pages=0, limit=20, dry_run=True)
    with pytest.raises(typer.Exit):
        launcher.collect("law_go_kr", use=None, pages=0, limit=0, dry_run=False)
    head = ("uv", "run", "python", "-m", "collect.law_api", "--target")
    assert got[0] == (*head, "mfdsCgmExpc", "--dry-run", "--limit", "20")
    assert got[1] == (*head, "law")
