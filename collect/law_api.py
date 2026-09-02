"""collect/law_api.py — 법제처 OPEN API 수집기 (S1-01 · S1-02 · D-92).

  uv run python -m collect.law_api --target law      # 법률 3 + 시행령·시행규칙 4
  uv run python -m collect.law_api --target admrul   # 고시 3종
  uv run python -m collect.law_api --dry-run         # 저장하지 않고 무엇을 받을지만

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.
   원본은 data/raw/law/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).

산출: data/raw/law/{target}_{id}_{eff}.xml  + data/manifest.jsonl 1행
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import xml.etree.ElementTree as ET

from collect import env, http, registry, store

SOURCE_ID = "law_go_kr"
FAMILY = "law"

#: 🚨 성공 응답의 최소 크기. 오류 봉투는 138바이트였다.
#:    자식 요소 검사가 주 방어이고 이것은 그물이다.
MIN_BODY = 1000

BASE_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
BASE_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

# 수집리스트 S1-01 · S1-02.
#  🚨 **ID 로 직접 조회한다. 이름으로 검색하지 않는다.**
#     수집전처리 기획 C1 이 재현성 근거로 「ID+시행일 고정」을 든 이유가 이것이다 —
#     이름 검색은 법령명이 개정되거나 검색 순위가 바뀌면 **다른 법령을 가져온다.**
#     실제로 스모크(2026-08-31)에서 코드의 「표시·광고」와 법령의 「표시 또는 광고」가
#     달랐는데 부분 매칭으로 우연히 통과했다. 운에 기대지 않는다.
#
#  🚨 목록을 여기서 늘리지 않는다 — 새 소스는 레지스트리에 먼저 등재하고 그다음 여기에 온다 (D-15).
#  ID 는 scripts/law_api_smoke.py 로 확인한 실측값이다 (2026-08-31).
TARGETS: dict[str, list[tuple[str, str, str]]] = {
    # (ID, 법령명, 수집리스트 항목)
    "law": [
        # ── 법률 3 ────────────────────────────────────────────
        ("002011", "표시ㆍ광고의 공정화에 관한 법률", "S1-01"),
        ("013094", "식품 등의 표시ㆍ광고에 관한 법률", "S1-01"),
        ("002015", "화장품법", "S1-01"),
        # ── 시행령·시행규칙 4 (2026-09-02 확보) ────────────────
        #  🚨 새 소스가 아니다 — `law_go_kr` 의 covers 가 이미 「3법 (+시행령·시행규칙)」과
        #     「시행령 [별표] 부당한 표시·광고의 유형 및 기준」·「행정처분 기준 [별표]」를
        #     적고 있다. 서명이 덮는 범위 안이므로 D-15 에 걸리지 않는다.
        ("005361", "표시ㆍ광고의 공정화에 관한 법률 시행령", "S1-01"),
        ("013453", "식품 등의 표시ㆍ광고에 관한 법률 시행령", "S1-01"),
        ("013475", "식품 등의 표시ㆍ광고에 관한 법률 시행규칙", "S1-01"),
        ("005668", "화장품법 시행령", "S1-01"),
        ("008741", "화장품법 시행규칙", "S1-01"),
    ],
    "admrul": [
        # ── 식약처 고시 3 ─────────────────────────────────────
        ("69549", "식품등의 부당한 표시 또는 광고의 내용 기준", "S1-02"),
        (
            "75449",
            "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
            "S1-02",
        ),
        ("37971", "건강기능식품 기능성 원료 및 기준·규격 인정에 관한 규정", "S1-04 원출처"),
        # ── 공정위 고시·지침 5 (2026-09-02 확보) ───────────────
        #  🚨 「부당한 표시·광고의 유형 및 기준」은 **시행령 [별표]가 아니라 고시**다.
        #     기획문서 3층 표가 「시행령 [별표]」로 적어 둔 것이 절반만 맞았다 —
        #     표시광고법 시행령(005361)에는 과징금·과태료 부과기준 3개뿐이고,
        #     유형기준은 ① 이 고시(34717) ② 식품표시광고법 시행령 [별표 1]
        #     「부당한 표시 또는 광고의 내용」(013453) 둘로 갈려 있다.
        ("34717", "부당한 표시·광고행위의 유형 및 기준 지정고시", "S1-02"),
        ("35032", "추천ㆍ보증 등에 관한 표시ㆍ광고 심사지침", "S1-02"),
        ("35037", "환경 관련 표시·광고에 관한 심사지침", "S1-02"),
        ("20207", "비교표시·광고에 관한 심사지침", "S1-02"),
        # 🚨 ID 자릿수가 다르다(7자리). 다른 것과 형식이 달라도 화면 그대로 적는다
        ("2052445", "인터넷 광고에 관한 심사지침", "S1-02"),
        # ── 화장품 고시 2 ─────────────────────────────────────
        #  🚨 기획문서의 「화장품 지침 3종」 중 **「화장품 표시·광고 관리 지침」은 없다** —
        #     행정규칙이 아니라 **민원인 안내서**라 법제처에 등재되지 않는다.
        #     식약처에서 따로 받아야 하고, 그것은 별도 소스 등재 대상이다 (D-15).
        ("41277", "화장품 표시·광고 실증에 관한 규정", "S1-02"),
        ("36122", "기능성화장품 심사에 관한 규정", "S1-02"),
    ],
}

# ⬜ 미확보 — 스모크에서 ID 를 못 받은 것. 확인 후 위 표로 옮긴다.
#  ✅ 2026-09-02 해소 — 두 건 모두 검색으로 ID 를 확인해 TARGETS 로 옮겼다.
#     같은 검색에서 식품표시광고법 시행령(013453)·화장품법 시행령(005668)도 확보했다.
#  🚨 `·`(U+00B7)와 `ㆍ`(U+318D)는 검색에 영향이 없다 — 둘 다 같은 1건을 낸다.
#     법령명 원문은 `ㆍ` 쪽이라 TARGETS 의 표기를 원문에 맞췄다.
PENDING: list[tuple[str, str, str]] = []

ID_FIELDS = ("법령ID", "행정규칙ID", "법령일련번호", "행정규칙일련번호")

#: 🚨 본문 조회의 **ID 파라미터 이름이 target 마다 다르다** (2026-09-02 실측).
#:
#:   law    → ID=<법령ID>            예) ID=002011
#:   admrul → LID=<행정규칙ID>       예) LID=69549
#:
#: `admrul` 에 `ID=69549` 를 보내면 「일치하는 행정규칙이 없습니다」가 온다 —
#: 그 자리의 `ID` 는 **행정규칙일련번호**(2100000269428)를 뜻하기 때문이다.
#: 일련번호는 개정마다 바뀌므로 쓰지 않는다. `LID` 는 행정규칙ID 라 **개정을 건너 안정**하고,
#: `law` 의 법령ID 와 같은 성질이다(항상 최신 시행본을 준다).
ID_PARAM = {"law": "ID", "admrul": "LID"}
NAME_FIELDS = ("법령명한글", "행정규칙명")
EFF_FIELDS = ("시행일자", "발령일자")


def _text(node: ET.Element, *names: str) -> str:
    for n in names:
        el = node.find(n)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def _call(base: str, oc: str, **params: str) -> bytes:
    params["OC"] = oc
    params.setdefault("type", "XML")
    url = f"{base}?{urllib.parse.urlencode(params, encoding='utf-8')}"
    return http.fetch(url)


def _parse(body: bytes) -> ET.Element | None:
    """XML 이면 root, 아니면 None. 🚨 인증 실패 시 HTML 이 온다."""
    try:
        return ET.fromstring(body.decode("utf-8", "replace"))
    except ET.ParseError:
        return None


def search(oc: str, target: str, query: str) -> tuple[str, str, str] | None:
    """검색해서 (ID, 이름, 시행일) 을 돌려준다. 못 찾으면 None."""
    root = _parse(_call(BASE_SEARCH, oc, target=target, query=query, display="3"))
    if root is None:
        raise SystemExit(
            "🚨 XML 이 아닌 응답이다 — OC 가 승인되지 않았거나 값이 틀렸다.\n"
            "   scripts/law_api_smoke.py 를 먼저 돌려 확인하라 (S0-01)."
        )
    hits = root.findall(".//law") + root.findall(".//admrul")
    if not hits:
        return None
    first = hits[0]
    return _text(first, *ID_FIELDS), _text(first, *NAME_FIELDS) or query, _text(first, *EFF_FIELDS)


def _reject_reason(root: ET.Element | None, body: bytes) -> str:
    """성공 응답이 아니면 사유를, 맞으면 빈 문자열을 돌려준다.

    🚨 **「XML 로 파싱된다」는 성공이 아니다.** 법제처는 조회 실패도 XML 로 돌려준다:

        <?xml version="1.0" encoding="utf-8"?>
        <Law>일치하는 행정규칙이 없습니다.  행정규칙명을 확인하여 주십시오.</Law>

    138바이트짜리 이 응답이 2026-09-02 에 **✅ 로 찍히고 저장되고 `collected_at` 까지
    기록됐다.** 파싱만 보고 통과시켰기 때문이다. 3층이 「채워졌다」고 표시된 채 비어 있었다.

    구분은 **자식 요소의 유무**로 한다. 성공 응답은 `<법령>`·`<AdmRulService>` 아래에
    기본정보·조문이 달리고, 오류 응답은 `<Law>` 하나에 텍스트만 있다. 문구로 찾지 않는다 —
    메시지가 바뀌면 다시 새기 때문이다.
    """
    if root is None:
        return "XML 이 아니다 — OC 가 승인되지 않았거나 값이 틀렸다"
    if len(root) == 0:
        return f"본문이 없다 — 서버 응답: {(root.text or root.tag).strip()[:80]}"
    if len(body) < MIN_BODY:
        return f"본문이 너무 짧다 ({len(body):,} bytes) — 조회가 실패했을 수 있다"
    return ""


def collect(target: str, *, dry_run: bool = False) -> tuple[int, int]:
    """대상 하나를 수집한다. 돌려주는 값은 (새로 저장한 건수, 실패 건수)."""
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    registry.require(SOURCE_ID, use="U1")
    oc = env.get("LAW_OC_KEY")

    id_param = ID_PARAM[target]  # 🚨 law 는 ID, admrul 은 LID
    saved = failed = 0
    for law_id, name, sid in TARGETS[target]:
        body = _call(BASE_SERVICE, oc, target=target, **{id_param: law_id})
        root = _parse(body)

        # 🚨 받은 것이 요청한 것인지 확인한다. ID 는 고정이지만 응답은 검증한다.
        reason = _reject_reason(root, body)
        if reason:
            print(f"  ❌ [{sid}] {name} ({id_param}={law_id}) — {reason}")
            failed += 1
            continue

        got = _text(root, *NAME_FIELDS) or _text(root, ".//법령명_한글", ".//행정규칙명")
        eff = _text(root, *EFF_FIELDS) or _text(root, ".//시행일자", ".//발령일자")
        # 🚨 시행일을 못 읽으면 파일명이 `unknown` 이 되어 다음 개정본과 충돌한다.
        #    이름·시행일 둘 다 못 읽으면 응답 모양이 바뀐 것이므로 저장하지 않는다.
        if not (got and eff):
            print(
                f"  ❌ [{sid}] {name} ({id_param}={law_id}) — 이름·시행일을 못 읽었다 "
                f"(이름={got or '없음'} 시행일={eff or '없음'}). 응답 구조를 확인하라"
            )
            failed += 1
            continue

        print(f"  ✅ [{sid}] {got}  {id_param}={law_id}  시행일={eff}")
        if dry_run:
            continue

        # 🚨 파일명에 시행일을 넣는다. 개정되면 새 파일이 되고 원본은 남는다 (규약 2)
        filename = f"{target}_{law_id}_{eff}.xml"
        path = store.save_raw(
            SOURCE_ID,
            FAMILY,
            filename,
            body,
            url=f"{BASE_SERVICE}?target={target}&{id_param}={law_id}",
        )
        if path is None:
            print(f"     ⏭  동일본 스킵 (sha256 일치) — {filename}")
        else:
            print(f"     💾 {path.relative_to(store.ROOT)}  ({len(body):,} bytes)")
            saved += 1

    if PENDING and target == "law":
        print("\n  ⬜ 미확보 (ID 확인 필요):")
        for _t, nm, sid in PENDING:
            print(f"     · [{sid}] {nm}")

    return saved, failed


def find_pending() -> None:
    """미확보 항목의 ID 를 검색해서 알려준다. 🚨 자동으로 TARGETS 에 넣지 않는다.

    검색은 **사람이 확인할 후보를 내는 도구**이지 수집 경로가 아니다.
    ID 는 사람이 확인하고 코드에 박는다 — 그래야 재현성이 유지된다 (C1).
    """
    registry.require(SOURCE_ID, use="U1")
    oc = env.get("LAW_OC_KEY")

    print("미확보 항목 ID 검색 — 확인 후 TARGETS 에 직접 옮기십시오\n")
    for target, query, sid in PENDING:
        hit = search(oc, target, query)
        if hit is None:
            print(f"  ❌ [{sid}] {query} — 검색어를 바꿔 재시도")
            continue
        law_id, name, eff = hit
        print(f"  ✅ [{sid}] {name}")
        print(f'        ("{law_id}", "{name}", "{sid}"),   # 시행일 {eff}')


def main() -> int:
    ap = argparse.ArgumentParser(description="법제처 OPEN API 수집기 (S1-01 · S1-02)")
    ap.add_argument("--target", choices=sorted(TARGETS), default="law")
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 조회만")
    ap.add_argument("--find", action="store_true", help="미확보 항목의 ID 를 검색만 한다")
    args = ap.parse_args()

    try:
        if args.find:
            find_pending()
            return 0
        saved, failed = collect(args.target, dry_run=args.dry_run)
    except (registry.RegistryError, env.MissingKey) as e:
        # 🚨 게이트와 키 부재는 「고치는 법」을 그대로 보여준다 (D-51)
        print(f"\n수집을 시작할 수 없다 —\n{e}\n", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n(dry-run — 저장하지 않았다){f' · 🚨 실패 {failed}건' if failed else ''}")
        return 1 if failed else 0

    print(f"\n새로 저장 {saved}건" + (f" · 🚨 실패 {failed}건" if failed else ""))
    if saved:
        registry.mark_collected(SOURCE_ID)
        print("collected_at 을 원장에 기록하고 data_sources.yaml 을 재생성했다.")
    if failed:
        # 🚨 일부 실패를 0 으로 끝내지 않는다. 2026-09-02 에 admrul 3건이 전부 오류 응답이었는데
        #    「새로 저장 3건」과 종료코드 0 이 나와, 3층이 채워진 것으로 보였다.
        print(
            "🚨 실패한 항목이 있다 — collected_at 이 찍혔더라도 **그 항목은 받지 못했다.**\n"
            "   위 사유를 먼저 해결하고 다시 돌린다.",
            file=sys.stderr,
        )
    print("🚨 이어서 반드시:  uv run pytest -m gate")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
