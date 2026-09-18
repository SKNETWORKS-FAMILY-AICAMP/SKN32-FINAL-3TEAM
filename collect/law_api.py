"""collect/law_api.py — 법제처 OPEN API 수집기 (S1-01 · S1-02 · D-92).

  uv run python -m collect.law_api --target law      # 법률 3 + 시행령·시행규칙 4
  uv run python -m collect.law_api --target admrul   # 고시 3종
  uv run python -m collect.law_api --target prec     # 판례 — 질의로 모아 본문 수집
  uv run python -m collect.law_api --target decc     # 행정심판 재결례
  uv run python -m collect.law_api --target mfdsCgmExpc   # 중앙부처 1차 해석 — 식약처 (소스 mfds_cgm_expc)
  uv run python -m collect.law_api --dry-run         # 저장하지 않고 무엇을 받을지만

🚨 첫 줄이 registry.require() 다 (수집기 공통 규약 1). 게이트를 우회하는 경로를 만들지 않는다.
   원본은 data/raw/law/ 에 무손상 저장하고 덮어쓰지 않는다 (규약 2 · D-92).

산출: data/raw/law/{target}_{id}_{eff}.xml  + data/manifest.jsonl 1행
"""

from __future__ import annotations

import argparse
import html.entities
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

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
        # ── 건강기능식품 1 (2026-09-05 확보) ───────────────────
        #  🚨 새 소스가 아니다 — `law_go_kr` 의 covers 가 이미 약속하고 있던 둘 중 하나다.
        #     아래 PENDING 주석에 확인 경위를 남겼다.
        #  🚨 시행일이 두 곳에서 다르다 — 검색 목록은 20250103, 본문 조회는 20240724.
        #     **본문 쪽을 적는다.** 우리가 실제로 받아 저장하는 것이 본문이기 때문이다.
        #     검색 목록의 날짜를 믿고 적으면 원장의 수치가 저장물과 어긋난다 (D-54).
        ("009353", "건강기능식품에 관한 법률", "S1-01"),  # 시행일 20240724 (본문 실측)
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
        # ── 건강기능식품 고시 1 (2026-09-05 확보) ──────────────
        #  🚨 위 37971(「기능성 원료 및 기준·규격 **인정에 관한 규정**」)과 다른 문서다.
        #     이름이 닮았지만 37971 은 원료를 **인정하는 절차**이고, 이것은 기준·규격 **본문**이다.
        ("34650", "건강기능식품의 기준 및 규격", "S1-02"),  # 시행일 20260611 (검색·본문 일치)
    ],
}

# ⬜ 미확보 — 스모크에서 ID 를 못 받은 것. 확인 후 위 표로 옮긴다.
#  ✅ 2026-09-02 해소 — 두 건 모두 검색으로 ID 를 확인해 TARGETS 로 옮겼다.
#     같은 검색에서 식품표시광고법 시행령(013453)·화장품법 시행령(005668)도 확보했다.
#  🚨 `·`(U+00B7)와 `ㆍ`(U+318D)는 검색에 영향이 없다 — 둘 다 같은 1건을 낸다.
#     법령명 원문은 `ㆍ` 쪽이라 TARGETS 의 표기를 원문에 맞췄다.
#: 🚨 **`covers` 에 적혀 있는데 실제로는 안 받고 있던 둘** (2026-09-04 발견).
#:    `law_go_kr` 의 covers 가 「건강기능식품의 기준 및 규격 고시」를 이미 약속하고 있었는데
#:    TARGETS 에는 없었다 — **목록과 실물이 어긋난 자리**다. 서명은 이미 이 범위를 덮는다.
#:    🚨 검색은 **후보를 내는 도구**이고, ID 는 사람이 확인해 TARGETS 에 박는다 (C1).
#:
#: ✅ 2026-09-05 해소 — 둘 다 TARGETS 로 옮겼다 (법률 `009353` · 고시 `34650`).
#:    🚨 **그 C1 이 실제로 막았다.** `search()` 는 `display=3` 을 받아 `hits[0]` 만
#:       돌려준다. 「건강기능식품의 기준 및 규격」은 후보 13건 중 **5번째**였고,
#:       1번으로 온 것은 **이미 TARGETS 에 있던 37971**(「…인정에 관한 규정」)이었다.
#:       자동 기입 설계였다면 갖고 있는 것을 새것인 양 중복 등재했을 것이다.
#:    🚨 그리고 이 검색은 `collect/http.py` 인코딩 버그를 고친 **뒤에야** 의미가 있었다 —
#:       그 전에는 공백이 든 법령명이 통째로 무시돼 목록 맨 앞(「10ㆍ27법난」)이 왔다.
PENDING: list[tuple[str, str, str]] = []

#: 🚨 검색 응답과 본문 응답의 **필드 이름이 다르다** (2026-09-06 실측).
#:    prec  검색 `판례일련번호`          → 본문 `판례정보일련번호`
#:    decc  검색 `행정심판재결례일련번호`  → 본문 `행정심판례일련번호`
#:    넷을 다 적어 둔다. 하나만 적으면 검색이나 본문 중 한쪽에서 조용히 빈 문자열이 된다.
ID_FIELDS = (
    "법령ID",
    "행정규칙ID",
    "법령일련번호",
    "행정규칙일련번호",
    "판례일련번호",
    "판례정보일련번호",
    "행정심판재결례일련번호",
    "행정심판례일련번호",
    # 🆕 2026-09-18 — 중앙부처 1차 해석. 검색·본문 둘 다 이 이름이다 (탐침 실측 · 458622).
    "법령해석일련번호",
)

#: 🚨 본문 조회의 **ID 파라미터 이름이 target 마다 다르다** (2026-09-02 실측).
#:
#:   law    → ID=<법령ID>            예) ID=002011
#:   admrul → LID=<행정규칙ID>       예) LID=69549
#:
#: `admrul` 에 `ID=69549` 를 보내면 「일치하는 행정규칙이 없습니다」가 온다 —
#: 그 자리의 `ID` 는 **행정규칙일련번호**(2100000269428)를 뜻하기 때문이다.
#: 일련번호는 개정마다 바뀌므로 쓰지 않는다. `LID` 는 행정규칙ID 라 **개정을 건너 안정**하고,
#: `law` 의 법령ID 와 같은 성질이다(항상 최신 시행본을 준다).
#: 🚨 `prec`·`decc` 는 둘 다 `ID` 다 — `admrul` 의 `LID` 는 예외였다 (2026-09-06 실측).
#:    `decc` 에 `LID` 를 보내면 144바이트 「일치하는 행정심판례가 없습니다」가 온다.
ID_PARAM = {"law": "ID", "admrul": "LID", "prec": "ID", "decc": "ID", "mfdsCgmExpc": "ID"}
NAME_FIELDS = ("법령명한글", "행정규칙명", "사건명", "안건명")

#: 🚨 `decc` 의 `처분일자` 는 **비어 있는 경우가 많다.** `_text()` 가 빈 값을 건너뛰므로
#:    `의결일자` 로 넘어간다 — 순서가 곧 우선순위다.
EFF_FIELDS = ("시행일자", "발령일자", "선고일자", "처분일자", "의결일자", "해석일자")

# ─────────────────────────────────────────────────────────────
#  판례 · 재결례 — 검색으로 모으는 갈래 (2026-09-06 신설)
# ─────────────────────────────────────────────────────────────
#  🚨 **C1 을 그대로 쓸 수 없는 자리다.** 법령은 소수·고정이라 「ID 는 사람이 박는다」가
#     성립하지만, 판례·재결례는 **집합**이고 시간이 지나면 늘어난다. 2,769건을 사람이
#     박을 수도 없고, 박아 봐야 다음 달에 어긋난다.
#
#     그래서 **사람이 박는 것을 ID 에서 질의로 옮긴다.** 재현성의 근거가
#     「ID + 시행일」에서 **「질의 + 수집일 + 그때의 실측 건수」**로 바뀐다.
#     🚨 그 실측을 남기지 않으면 재현성이 없다 — `collect_cases()` 가 표를 찍는 이유다.
#
#  🚨 **질의에 `·`(U+00B7)를 넣지 마라** (2026-09-06 실측).
#     서버가 `&middot;` 로 되받고 사건명·본문 **어느 쪽에서도 0건**이 온다.
#     예외도 오류도 아닌 0건이라 눈으로 안 잡힌다.
#         「식품등의 표시·광고에 관한 법률」 → 0건
#         「식품등의 표시광고에 관한 법률」 → 5건
#
#  🚨 **도메인 선별은 여기서 하지 않는다** — 그것은 `preprocess/` 의 일이다.
#     raw 는 등급 혼재를 전제로 무손상 보관하는 자리다 (D-92).
#     다만 **명백한 무관을 받기 전에 빼는 것**은 선별이 아니라 수집 대상 결정이고,
#     그것은 아래 `CASE_NAME_KEYWORDS` 가 한다. 이유는 거기 적었다 —
#     본문 검색이 토큰 AND 라 그대로 두면 5건 중 4건이 무관한 문서다.
#  🔴 **질의로 좁히기 전에 전량 규모를 먼저 잰다** (2026-09-06 확정 · 팀장).
#     `ftc_decisions_body` 를 「표시광고」로 받아 1,087건이었는데, 토큰 AND 라
#     **「표시」가 안 나오는 광고 사건 664건이 처음부터 범위 밖**이었다. 그리고 그 사실이
#     **4일간 드러나지 않았다** — 안 받아본 것 중에 무엇이 있는지는 볼 방법이 없기 때문이다.
#     ① 질의 없는 전체 건수를 먼저 잰다(호출 한 번) ② 감당 가능하면 전량을 받고 선별은
#     `preprocess/` 가 한다(D-92) ③ 불가능하면 좁히되 **무엇을 놓치는지 함께 적는다.**
#     🚨 `prec`·`decc` 는 아직 전량 규모를 재지 않았다 — 다음 사람이 할 일이다.
#
#  ⬜ 2026-09-06 에 뺀 질의 — **다시 넣지 마라.**
#     「식품등의 표시광고」 : 순증 0. `decc` 69건·`prec` 7건이 **전부 「표시광고」에 포함**된다.
#       본문 검색이 토큰 AND 라 더 긴 질의는 짧은 질의의 부분집합이 될 수밖에 없다.
#       매 실행마다 검색 4회를 쓰면서 아무것도 더하지 않았다.
#       🚨 이유를 여기 적어 두는 것이 뺀 것보다 중요하다 — 안 적으면 다음 사람이
#          「식품 쪽 질의가 없네」 하고 다시 넣는다.
#
#  ⬜ 2026-09-06 에 **넣지 않기로 한** 질의 — 「광고」 단독. 실측하고 뺐다.
#       decc | 현재 120 | 「광고」단독 85 | 순증 **0**
#       prec | 현재  92 | 「광고」단독 102 | 순증 **29**
#     🚨 순증 29건을 눈으로 전부 봤다. **29건 모두 무관**이었다 —
#        「광고선전비의 손금산입 적정 여부」 · 「…광고선전비가 접대비에 해당하는지」 ·
#        「실제로 광고용역을 제공받지 않은 자로부터 발급받은 전자세금계산서…」 ·
#        「사죄광고」 · 「광고료」 · 「현상광고보수」.
#     🚨 순증이 0 이 아니라고 넣는 것이 아니다. **순증이 무엇인지 보고 정한다.**
#        단어 하나짜리 질의는 토큰 AND 에서 사실상 필터가 없는 것과 같아서,
#        세무·민사의 '광고'(광고비·광고료)가 통째로 딸려 온다.
QUERIES: tuple[str, ...] = (
    "표시광고",
    "부당한 광고",
    "건강기능식품",
    "화장품법",
)

#: 검색으로 모으는 target. 본문 조회 파라미터는 `ID_PARAM` 이 진다.
CASE_TARGETS = ("prec", "decc")

#: 🆕 2026-09-18 — **중앙부처 1차 해석** (target → 소스 id). 판례·재결례와 같은 「목록 → 본문」
#:    두 단계라 `collect_cases()` 를 같이 쓰지만 **셋이 다르다** (API 탐침 실측 · 사용자 실행).
#:
#:    ① **소스 id 가 다르다.** 법령은 비보호저작물(저작권법 제7조)이라 `law_go_kr` 하나로 묶었는데
#:       1차 해석은 **부처의 업무상 저작물**이라 이용조건이 달라 따로 등재했다 (D-90 · 등재 단위는 이용조건).
#:       게이트(`registry.require`)도 원장 기록(`mark_collected`)도 그 id 로 간다.
#:    ② **사건명 필터(`_in_domain`)를 걸지 않고 전량을 받는다.** 목록에 【분류】가 없어 받기 전에
#:       가를 수단이 없고, 「항균」 해석(458622)처럼 **제목에 광고가 없는 광고 판정**이 있다.
#:       거르기는 `preprocess/` 가 `회답` · `관련법령` 으로 한다 (D-92 · 규칙은 판정 대기).
#:    ③ 🔴 **목록 응답을 저장하지 않는다 — 원래도 안 한다.** 목록의 `법령해석상세링크` 에
#:       **서버가 OC 키 값을 그대로 넣어 돌려준다**(본문엔 없다). 그래서 본문 저장 직전에
#:       키 값이 섞였는지 한 번 더 보고, 섞였으면 **저장하지 않고 실패로 센다** (D-220).
#:
#:    🚨 원문 폴더는 소스 id 그대로(`data/raw/mfds_cgm_expc/`)다 — `store.FAMILY_OF` 에 없으면
#:       그렇게 된다. `data/raw/law/` 에 섞지 않는다 — 법령 추출기가 그 폴더를 훑는다 (D-245).
#:    ⬜ 이 소스는 **G0 · hold** 다. 2인 확인 전에는 첫 줄의 게이트가 막는다 — 그것이 정상이다.
INTERP_TARGETS: dict[str, str] = {"mfdsCgmExpc": "mfds_cgm_expc"}

#: 목록 응답에서 한 건을 담는 요소 이름. `prec`·`decc` 는 target 과 같은데
#: 1차 해석은 `<cgmExpc>` 다 (2026-09-18 실측). 표에 없으면 target 을 그대로 쓴다.
ITEM_TAG: dict[str, str] = {"mfdsCgmExpc": "cgmExpc"}

#: 1차 해석 본문이 성공이라고 볼 최소 조건 — **회답이 비지 않았다.** 🚨 `MIN_BODY`(1,000 B)를
#:    쓰지 않는다 — 짧은 회답은 1 KB 아래일 수 있고, 크기로 가르면 멀쩡한 해석을 실패로 센다.
#:    대신 자식 요소 검사(`_reject_reason`) + 이 필드로 가른다.
INTERP_REQUIRED = "회답"

#: 🚨 `search=2` 가 **본문 검색**이다. 기본값(`1`)은 사건명 검색인데, 사건명은
#:    「식품등의표시·광고에관한법률위반」처럼 **법률명 나열**이라 서술 표현이 안 걸린다.
#:    「부당한 광고」가 사건명 0건 / 본문 987건인 것이 그 차이다.
SEARCH_BODY = "2"
SEARCH_NAME = "1"

#: 한 장에 받을 검색 결과 수. 100 이 상한이다.
SEARCH_ROWS = 100

#: 🚨 **본문 검색은 구(句)가 아니라 토큰 AND 다** (2026-09-06 실측). 이것이 이 필터가
#:    있는 이유다.
#:
#:      「표시광고」로 잡힌 재결례 5건의 본문에 **문자열 「표시광고」는 0회**였다.
#:      「표시」1회·「광고」1회처럼 두 흔한 단어가 각각 나온 무관한 문서들이었다
#:      (개발제한구역 행위신고 · LED전자현수막 계약해지 …).
#:      `decc` 는 「광고」 521건 중 496건이 「부당한 광고」로 잡힌다 — 거의 안 걸러진다.
#:
#:    그대로 받으면 653건 중 약 500건이 무관한 문서다. 18분을 쓰고 공공기관 서버를
#:    5,500번 두드리는 일이 되는데, 규약 5 가 「우리가 막히는 것으로 끝나지 않고
#:    『공식 API 이용』이라는 근거 자체가 흔들린다」고 적어 둔 자리다.
#:    **효율이 아니라 거버넌스 문제로 다룬다.**
#:
#: 🚨 이것은 **도메인 선별이 아니라 수집 대상 결정**이다 — `preprocess/ftc_triage.py` 가
#:    1,087건을 다 **받은 뒤** 고른 것과 성격이 다르다. 받기 전에 정해야 서버 부담이 준다.
#:    선별의 정밀한 판단은 여전히 `preprocess/` 의 일이고, 여기서는 **명백한 무관만** 뺀다.
#:
#: 🚨 그리고 이것이 「사람이 박는 것」의 세 번째 자리다 — ID(법령) → 질의(판례) → 이 어휘.
#:    2026-09-06 실측: `decc` 653건 → 147건 통과. 탈락 표본에 우리 도메인은 없었다.
CASE_NAME_KEYWORDS: tuple[str, ...] = ("광고", "표시", "식품", "화장품", "의약품")

#: 🚨 업종이 사건명에 박혀 있으면 **무조건 받는다.** 아래 제외 어휘보다 세다.
#:    「식품위생법 위반업소 행정처분 및 **불법옥외광고물** 자진철거 계고처분」 같은
#:    사건이 실재한다 — 제외가 포함을 이기면 이런 것이 오탈락한다.
INDUSTRY_WORDS: tuple[str, ...] = ("식품", "화장품", "의약품")

#: 🚨 **옥외광고물 사건을 뺀다** (2026-09-06, 사건명 92종을 눈으로 훑고 정함).
#:    간판·현수막의 **설치** 규제이지 광고 **문구의 내용** 규제가 아니다.
#:    92종 중 22종이 이 계열이었다 —
#:      옥외광고물등관리법위반 이행강제금 · 불법광고물 강제제거 · 옥외광고심의위원회 …
#:      「광고물등표시금지지역장소의상업광고표시허용심의취소」처럼 `표시`·`광고`를
#:      둘 다 담아 기존 어휘를 그대로 통과하던 것들이다.
#:
#: 🚨 「상업광고」를 따로 적은 이유 — 「상업광고표시철거이행청구」는 `광고물`·`옥외광고`
#:    어느 쪽에도 안 걸린다. **어휘 하나로 계열을 덮었다고 믿지 않는다.**
#:
#: 🚨 여기에 **동음어와 민사 보전처분도 넣는다** (2026-09-06 2차). 아래 `EXCLUDE_STRONG`
#:    에 넣었다가 내렸다 — 그쪽은 업종어를 이기는 칸이라 「식품등의 **표시변경** 명령」
#:    같은 우리 사건이 조용히 사라진다. **업종어가 이겨야 맞는 제외**는 여기다.
#:      의사표시 : 「뇌물공여**의사표시**·여신전문금융업법위반」
#:      표시변경 : 「건축물**표시변경**신청수리불가처분취소」(부동산 표시)
#:      금지가처분 : 「광고**금지가처분**」(민사 보전)
EXCLUDE_WORDS: tuple[str, ...] = (
    "광고물",
    "옥외광고",
    "상업광고",
    "의사표시",
    "표시변경",
    "금지가처분",
)

#: 🚨 **세무·민사 계열을 뺀다** (2026-09-06, 이미 받은 `prec` 92건의 사건명 58종을 훑고 정함).
#:
#: 🚨 왜 뒤늦게 생겼나 — 위 어휘 전부를 `decc`(행정심판재결례) **하나만 보고** 정한 뒤
#:    `prec`(판례)에 그대로 썼다. 재결례는 행정심판이라 세무·민사가 거의 없다.
#:    판례는 **같은 코퍼스에 세무·민사가 함께 있다.** 오염원이 다르다.
#:    ⛔ 오늘 §7 4번(전제가 바뀐 줄 모르고 옛 예외를 남겨 둠)과 **같은 자리**다 —
#:       **도메인이 다르면 어휘도 다르다.** 어휘를 옮길 때는 옮긴 곳에서 다시 잰다.
#:
#: 🚨 이 목록은 `INDUSTRY_WORDS` **보다 세다.** 옥외광고물과 판정 순서가 반대다.
#:      「**화장품** 외판원이 **부가가치세**법상의 사업자인지 여부」
#:    업종어가 박혀 있어도 광고 문구와는 무관한 세금 다툼이다.
#:    옥외광고물은 업종이 걸리면 진짜인 경우가 있었지만(식품위생법 위반 + 불법광고물 계고),
#:    세무는 업종이 걸려도 **관측된 전부가** 세금 사건이었다. 그래서 순서를 다르게 준다.
#:
#: 🚨 잡히는 것 (관측된 사건명) —
#:    세무 : 광고선전비가 접대비인지 · 광고대행수수료가 필요경비인지 · 광고매체대행사의
#:           매입세금계산서 · 유류비 등 매입세액 · 신문사 광고수입금액 누락과 법인세 탈루
#:    민사 : 「광고료」 · 「사죄광고」 · 「현상광고보수(금)」 · 「광고금지가처분」
#:    동음어: 「건축물**표시**변경신청수리불가처분취소」(부동산 표시)
#:            「뇌물공여의사**표시**·여신전문금융업법위반」(의사표시)
#:
#: ⛔ **`가처분` 을 넣었다가 뺐다** (2026-09-06, `--audit` 이 잡았다). 한국어 복합어에서
#:    잘린 자리가 우연히 다른 단어가 된다 —
#:      「의약품제조품목제조**허가처분**취소청구」    ← 허**가처분**
#:      「의약품제조품목허가조건**부가처분**취소청구」 ← 조건**부가처분**
#:    `의약품` 이 박혀 있는데도 이 칸이 업종어를 이기는 바람에 **둘 다 오탈락**했다.
#:    🚨 교훈은 둘이다 —
#:       ① 두 글자가 넘어도 **부분문자열은 단어가 아니다.** 넣기 전에 그 글자가 어떤
#:          복합어 안에 들어 있는지 본다 (허가·인가·부가·불허가 …).
#:       ② **센 칸일수록 좁게 적는다.** 여기는 업종어를 이기는 자리라 오탈락이
#:          구제되지 않는다. 위 어휘는 전부 실제 사건명에서 왔다 — 관측 없이 넣지 마라.
#:    지금은 `금지가처분` 으로 좁혀 `EXCLUDE_WORDS`(약한 칸)에 있다.
#:
#: ⬜ **안 잡히는 것을 함께 적는다** — 「특수관계자의 광고용역을 무상·저가수행하였는지
#:    여부 등」은 부당행위계산부인(세무)인데 위 어휘에 하나도 안 걸린다.
#:    「특수관계」를 넣으면 공정거래법 부당지원 사건까지 같이 빠진다 — 그쪽은 우리 것이다.
#:    🚨 그래서 **일부러 남겼다.** 애매하면 받는다(아래 docstring). 다음 사람이
#:       「왜 이게 남아 있지」 하고 어휘를 넓히다가 진짜를 떨구는 일을 막으려고 적는다.
EXCLUDE_STRONG: tuple[str, ...] = (
    # ── 세무 — 광고비를 「비용」으로 다투는 사건 ──
    "법인세",
    "소득세",
    "부가가치세",
    "세금계산서",
    "매입세액",
    "필요경비",
    "접대비",
    "손금",
    "익금",
    "광고선전비",
    "광고수입",
    # ── 민사 — 광고를 「계약·불법행위」로 다투는 사건 ──
    "현상광고",
    "사죄광고",
    "광고료",
)


def _in_domain(case_name: str) -> bool:
    """사건명이 우리 도메인인가. 🚨 사건명은 검색 응답에 이미 있어 **공짜**다.

    🚨 여기서 하는 것은 **명백한 무관 제외**이지 도메인 선별이 아니다.
       「식품위생법 위반 영업정지」가 광고 때문인지 위생 때문인지는 **본문을 봐야** 알고,
       그 판단은 `preprocess/` 의 일이다. 애매한 것은 받는다.

    🚨 **판정 순서가 곧 규칙이다** (D-118 ③). 위에서부터 —
       ① `EXCLUDE_STRONG` : 세무·민사. 업종어를 **이긴다.**
       ② `INDUSTRY_WORDS` : 업종이 박혀 있으면 받는다. ③ 을 **이긴다.**
       ③ `EXCLUDE_WORDS`  : 옥외광고물·동음어·민사 보전.
       ④ `CASE_NAME_KEYWORDS` : 나머지는 기본 어휘로 본다.
       ①과 ③은 둘 다 「제외」인데 ②를 사이에 두고 **강도가 다르다.** 한 통에 합치면
       화장품 세무 사건이 들어오거나(합쳐서 약하게) 식품+옥외광고물 사건이
       빠진다(합쳐서 세게). 두 관측이 서로 반대라 통을 나눈 것이지 취향이 아니다.

    🚨 **①에 넣는 문턱이 ③보다 높다.** ① 은 오탈락이 구제되지 않는 자리다.
       「업종어가 박힌 사건인데도 무관했다」를 **실제로 본 것**만 ① 에 넣는다.
       그렇지 않으면 ③ 이다 — 판단이 서지 않으면 ③ 으로 간다.
    """
    if any(word in case_name for word in EXCLUDE_STRONG):
        return False
    if any(word in case_name for word in INDUSTRY_WORDS):
        return True
    if any(word in case_name for word in EXCLUDE_WORDS):
        return False
    return any(word in case_name for word in CASE_NAME_KEYWORDS)


#: 🚨 원천이 **「비어 있음」을 문자열로 표현**한다 (2026-09-06 실측).
#:    `ftc` ID=18691·18701·18717·18719 네 건이 이렇게 왔다 —
#:
#:      <문서유형>null</문서유형><사건번호>null</사건번호><사건명><![CDATA[null]]></사건명>
#:
#: 🚨 **`"null"` 은 참인 문자열이다.** `if not (got and eff)` 검사를 그대로 통과하고,
#:    파일명·원장에 `null` 이 그대로 들어간다. 그 네 건은 352 B 였고 `MIN_BODY` **그물**이
#:    잡았다 — **1,000 B 만 넘었으면 사건명이 `null` 인 파일이 저장됐다.**
#:    크기와 무관한 문제이므로 그물에 맡기지 않고 값을 읽는 자리에서 막는다.
#:
#: 🚨 `"-"` 는 넣지 않는다 — 실제 값으로 쓰는 원천이 있다(`decc` 의 `처분종료일`).
#:    「빈 값의 표기」와 「짧은 값」을 섞지 않는다.
_EMPTY_MARKERS = frozenset({"null", "none", "nil"})


def _text(node: ET.Element, *names: str) -> str:
    """이름 목록을 순서대로 보고 **처음 만나는 실제 값**을 돌려준다.

    🚨 빈 값 표기(`null` 등)는 없는 것으로 보고 **다음 이름으로 넘어간다.**
       원천마다 필드 이름이 다른 상황(D-118)에서 한 이름이 `null` 이라고 멈추면
       뒤에 있는 진짜 값을 놓친다.
    """
    for n in names:
        el = node.find(n)
        if el is not None and el.text:
            value = el.text.strip()
            if value and value.lower() not in _EMPTY_MARKERS:
                return value
    return ""


def _call(base: str, oc: str, **params: str) -> bytes:
    params["OC"] = oc
    params.setdefault("type", "XML")
    url = f"{base}?{urllib.parse.urlencode(params, encoding='utf-8')}"
    return http.fetch(url)


#: 🚨 법제처는 **XML 을 자칭하면서 HTML 엔티티를 섞어 보낸다** (2026-09-06 실측).
#:
#:     <키워드>식품등의 표시&middot;광고에 관한 법률</키워드>
#:
#:    XML 이 정의하는 엔티티는 `&amp; &lt; &gt; &quot; &apos;` 다섯뿐이다.
#:    `&middot;` 에서 파서가 죽고 `_parse` 가 `None` 을 돌려준다 —
#:    **질의에 `·` 가 들어 있기만 하면** 그렇게 된다.
#:
#: 🚨 그 자리를 `search()` 가 「OC 가 승인되지 않았거나 값이 틀렸다」로 단정했다.
#:    바로 앞뒤 질의가 성공하는데도 그랬다. 키를 재발급하며 시간을 쓰는 실패다.
#:    형태가 `collect/http.py` 의 인코딩 버그와 같다 — 서버가 규격을 자칭하면서
#:    규격 밖 문자를 섞고, 우리 쪽은 예외도 0건도 아닌 그럴듯한 다른 결과를 받는다.
_HTML_ENTITY_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]{1,31});")

#: XML 이 스스로 정의하는 다섯. 이것들은 건드리지 않는다.
_XML_ENTITIES = frozenset({"amp", "lt", "gt", "quot", "apos"})


def _xmlify_entities(text: str) -> str:
    """HTML 이름 엔티티를 수치 참조로 바꾼다. **모르는 이름은 그대로 둔다.**

    🚨 추측해서 값을 지어내지 않는다 — 모르는 엔티티는 그대로 두어 파싱이
       실패하게 만든다. 조용히 잘못된 글자를 넣는 것보다 실패가 낫다.
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name in _XML_ENTITIES:
            return m.group(0)
        code = html.entities.name2codepoint.get(name)
        return f"&#{code};" if code else m.group(0)

    return _HTML_ENTITY_RE.sub(repl, text)


def _parse(body: bytes) -> ET.Element | None:
    """XML 이면 root, 아니면 None. 🚨 인증 실패 시 HTML 이 온다.

    🚨 **정규화는 파싱 직전에만 한다.** `body` 는 손대지 않고 그대로 돌아가
       `store.save_raw()` 로 간다 — `data/raw/` 에는 서버가 준 원문이 남는다
       (D-117 「매칭은 정규화문, 보관은 원문」).

    🚨 정상 응답은 첫 시도에서 끝난다. 정규화는 **실패했을 때만** 한 번 더 시도한다 —
       모든 응답을 정규화하면 언젠가 정규화가 원문을 조용히 바꾸는 날이 온다.
    """
    text = body.decode("utf-8", "replace")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        pass

    normalized = _xmlify_entities(text)
    if normalized == text:
        return None
    try:
        return ET.fromstring(normalized)
    except ET.ParseError:
        return None


def _parse_failure(body: bytes) -> str:
    """XML 로 못 읽은 응답의 사유. 🚨 **원인을 단정하지 않는다.**

    2026-09-06 이전에는 이 자리가 「OC 가 승인되지 않았거나 값이 틀렸다」 하나였다.
    깨진 XML 과 인증 실패가 같은 문장으로 처리돼, 키가 멀쩡한데도 키를 의심하게 만들었다.
    **HTML 이 온 경우에만** OC 를 언급하고, 그때도 단정하지 않는다.

    🚨 응답 전문을 쏟지 않고 한 줄로 자른다 — `probe.py` 의 오류 메시지는
       `실측_<날짜>.md` 와 `build/probe_results.json` 으로 들어가 **커밋된다** (D-111).
    """
    head = body[:400].lstrip()
    if head[:9].lower() == b"<!doctype" or head[:5].lower() == b"<html":
        return (
            "HTML 이 왔다 — OC 가 승인되지 않았거나 값이 틀렸을 수 있다 (scripts/law_api_smoke.py)"
        )
    snippet = " ".join(body[:200].decode("utf-8", "replace").split())
    return f"XML 로 읽히지 않는다 — 응답 앞부분: {snippet}"


def search(oc: str, target: str, query: str) -> tuple[str, str, str] | None:
    """검색해서 (ID, 이름, 시행일) 을 돌려준다. 못 찾으면 None."""
    body = _call(BASE_SEARCH, oc, target=target, query=query, display="3")
    root = _parse(body)
    if root is None:
        # 🚨 target·query 를 같이 찍는다. 이 실패는 **질의 하나 때문에** 나기도 한다 —
        #    앞뒤 질의가 성공하는 상황에서 「OC 가 틀렸다」만 보면 키부터 의심하게 된다.
        raise SystemExit(
            f"🚨 검색 응답을 읽지 못했다 (target={target} query={query!r})\n"
            f"   {_parse_failure(body)}"
        )
    hits = root.findall(".//law") + root.findall(".//admrul")
    if not hits:
        return None
    first = hits[0]
    return _text(first, *ID_FIELDS), _text(first, *NAME_FIELDS) or query, _text(first, *EFF_FIELDS)


def _reject_reason(root: ET.Element | None, body: bytes, *, min_body: int = MIN_BODY) -> str:
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
        # 🚨 2026-09-06 이전에는 이 자리도 OC 를 단정했다. `_parse_failure` 로 넘긴다.
        return _parse_failure(body)
    if len(root) == 0:
        return f"본문이 없다 — 서버 응답: {(root.text or root.tag).strip()[:80]}"
    if len(body) < min_body:
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


def _search_hits(oc: str, target: str, query: str, *, section: str) -> list[tuple[str, str]]:
    """질의 하나가 내는 (ID, 사건명) 전부. 순서는 **서버가 준 그대로** 둔다 (D-118 ①).

    `section` 은 `SEARCH_NAME`(사건명) 또는 `SEARCH_BODY`(본문).

    🚨 한 장이 깨져도 멈추지 않는다. 그 장만 사유를 찍고 넘어간다 —
       한 장 때문에 수십 분짜리 수집이 통째로 죽는 것이 더 비싸다 (D-118 ④).
       다만 **몇 건을 못 받았는지는 숨기지 않는다.** 아래에서 총계와 대조한다.
    """
    body = _call(BASE_SEARCH, oc, target=target, query=query, display="1", search=section)
    root = _parse(body)
    if root is None:
        raise SystemExit(
            f"🚨 검색 응답을 읽지 못했다 (target={target} query={query!r})\n   {_parse_failure(body)}"
        )
    total = int(root.findtext("totalCnt") or 0)

    ids: list[tuple[str, str]] = []
    for page in range(1, -(-total // SEARCH_ROWS) + 1):
        page_body = _call(
            BASE_SEARCH,
            oc,
            target=target,
            query=query,
            display=str(SEARCH_ROWS),
            search=section,
            page=str(page),
        )
        page_root = _parse(page_body)
        if page_root is None:
            print(f"     ⚠ {query} {page}장 — {_parse_failure(page_body)}")
            continue
        ids += [
            (i, _text(e, "사건명", "안건명"))
            for e in page_root.iter(ITEM_TAG.get(target, target))
            if (i := _text(e, *ID_FIELDS))
        ]

    if len(ids) != total:
        # 🚨 조용히 줄어드는 것을 막는다. 서버가 말한 수와 손에 든 수가 다르면 그대로 찍는다.
        print(f"     ⚠ {query} — 서버 총계 {total:,} · 실제 수신 {len(ids):,}")
    return ids


def collect_cases(
    target: str, *, dry_run: bool = False, limit: int | None = None, all_cases: bool = False
) -> tuple[int, int]:
    """판례·재결례를 질의로 모아 본문을 받는다. 돌려주는 값은 (새로 저장, 실패).

    🚨 두 단계다 — ① 질의별로 수집 대상을 정하고 ② 그 ID 로 본문을 받는다.
       ①의 실측표가 **재현성의 근거**이므로 화면에만 두지 말고 사실원장에 옮긴다 (D-54).

    ① 의 규칙 — **사건명 검색과 본문 검색을 합친 뒤 `_in_domain()` 을 한 번 건다.**

    🚨 처음에는 「사건명 검색 결과는 정밀하니 필터 없이 전부 받는다」로 짰다가 고쳤다
       (2026-09-06). **사건명 검색도 토큰 AND 다.** 「표시광고」 질의에
       「광고물등**표시**금지지역장소의상업**광고**표시허용심의취소」가 걸려 들어왔고,
       필터를 건너뛰는 경로라 그대로 수집 대상이 됐다.
       🚨 전제가 무너졌으면 그 위에 세운 예외도 같이 걷어낸다 — 예외를 남겨 두면
          필터를 고쳐도 그 경로로 계속 샌다.
    """
    # ── 규약 1 — 게이트가 첫 줄이다 ──────────────────────────
    # 🚨 1차 해석은 **자기 소스 id 로** 게이트를 지난다 — `law_go_kr` 의 서명을 빌려 쓰지 않는다.
    source = INTERP_TARGETS.get(target, SOURCE_ID)
    interp = target in INTERP_TARGETS
    registry.require(source, use="U1")
    oc = env.get("LAW_OC_KEY")
    family = store.families(source)[0] if interp else FAMILY

    seen: set[str] = set()
    order: list[str] = []
    rows: list[tuple[str, int, int, int, int]] = []
    # 🔴 2026-09-17 — 전량 규모를 쟀다 (규칙 ①). `decc` 35,213 중 `_in_domain` 을
    #    지나는 것이 **392**(1.1%) 였고, 본문 272건이 약 2.3분이다.
    #    ★ 그래서 **규칙 ② 이 성립한다** — 질의로 좁히지 않고 전량을 받고
    #    선별은 `preprocess/` 가 한다 (D-92). 4.9시간이라는 전제는 사건명을
    #    공짜로 받을 수 있다는 사실(`_in_domain` docstring)로 깨졌다.
    #
    # 🚨 질의 경로를 지우지 않는다 — `prec` 은 아직 전량 규모를 안 쟀다.
    # 🚨 빈 질의는 사건명·본문 검색이 **같은 전량**을 준다. 두 번 부르면
    #    페이징 353장을 두 번 도는 것이라 서버만 더 두드린다 (규약 5).
    # 🚨 1차 해석은 **늘 전량**이다 — `INTERP_TARGETS` ②. 질의로 좁히면 제목에 광고가 없는
    #    광고 판정을 놓친다.
    whole = all_cases or interp
    queries = ("",) if whole else QUERIES
    for query in queries:
        by_name = _search_hits(oc, target, query, section=SEARCH_NAME)
        by_body = [] if whole else _search_hits(oc, target, query, section=SEARCH_BODY)
        # 🚨 예외 없이 한 번에 건다. 두 경로 중 하나만 거르면 다른 쪽으로 샌다.
        #    1차 해석만 거르지 않는다 — 사건명 어휘는 판례용이고 여기엔 맞지 않는다 (②).
        kept = by_name + by_body if interp else [h for h in by_name + by_body if _in_domain(h[1])]

        fresh = 0
        for case_id, _name in kept:
            if case_id not in seen:
                seen.add(case_id)
                order.append(case_id)
                fresh += 1
        rows.append((query, len(by_name), len(by_body), len({i for i, _ in kept}), fresh))

    print(f"\n  질의별 실측 ({target}) — 🚨 사실원장에 옮긴다 (D-54)")
    print(f"    {'질의':<18} {'사건명':>7} {'본문':>7} {'→필터':>7} {'순증':>7}")
    for query, n_name, n_body, n_kept, fresh_n in rows:
        query = query or "(전량)"  # 🚨 빈 문자열은 표에서 안 보인다
        # 🚨 「순증」이 0 이면 그 질의는 다른 질의의 부분집합이다. 빼도 되는지 사람이 판단한다.
        print(f"    {query:<18} {n_name:>7,} {n_body:>7,} {n_kept:>7,} {fresh_n:>7,}")
    print(f"    {'합집합':<18} {'':>7} {'':>7} {'':>7} {len(order):>7,}")

    todo = order[:limit] if limit else order
    if limit:
        print(f"  ⚠ --limit {limit} — 합집합 {len(order):,}건 중 앞 {len(todo):,}건만 받는다\n")

    saved = failed = 0
    missing: list[str] = []
    for n, case_id in enumerate(todo, 1):
        body = _call(BASE_SERVICE, oc, target=target, ID=case_id)
        root = _parse(body)

        # 🚨 **「본문 미제공」과 「실패」를 가른다** (2026-09-06).
        #    XML 로 읽히는데 자식이 0개면 조회 실패 봉투다 — `<Law>일치하는 판례가
        #    없습니다.</Law>`. 그 ID 는 **서버 자신의 검색 인덱스**가 준 것이므로
        #    우리가 고칠 것이 없고, 재실행해도 같은 결과가 나온다.
        #    prec 92건 중 8건이 이랬다 (decc 120건은 0건).
        #    🚨 문구로 판별하지 않는다 — **자식 요소의 유무**로 가른다. 메시지가 바뀌어도
        #       판별이 유지된다 (`_reject_reason` 의 원칙과 같다).
        #    🚨 `LID` 로 우회되지 않는다 — 네 건 전부 1,940바이트 상수 응답이었고,
        #       정상 동작하는 622249 조차 그랬다. `prec` 에 `LID` 는 무효한 파라미터다.
        if root is not None and len(root) == 0:
            missing.append(case_id)
            continue

        reason = _reject_reason(root, body, min_body=0 if interp else MIN_BODY)
        if not reason and interp:
            # 🔴 ③ — 키 값이 응답에 섞였으면 **저장하지 않는다.** 실측으로는 본문에 없지만
            #    서버가 목록에는 넣어 보낸다. 형식이 바뀌는 날 raw 에 키가 박히는 것을 여기서 막는다.
            if oc and oc.encode() in body:
                reason = (
                    "🔴 응답에 OC 키 값이 들어 있다 — 저장하지 않는다 (목록의 상세링크와 같은 반사)"
                )
            elif not _text(root, INTERP_REQUIRED):
                reason = f"`{INTERP_REQUIRED}` 이 비었다 — 내용 없는 해석을 성공으로 세지 않는다"
        if reason:
            print(f"  ❌ [{n}/{len(todo)}] {target} ID={case_id} — {reason}")
            failed += 1
            continue

        name = _text(root, *NAME_FIELDS)
        eff = _text(root, *EFF_FIELDS)
        # 🚨 **사건명만 필수다.** 일자가 아예 없는 record 가 실재한다 (2026-09-06 실측) —
        #    `decc` ID=268809 은 `처분일자`·`의결일자` 가 둘 다 비고 다른 날짜 필드도 없다.
        #    그런데 사건명·주문·청구취지·이유는 온전하다. **일자 하나로 문서를 버리지 않는다.**
        #    응답 구조가 바뀐 것을 잡는 역할은 사건명이 진다.
        if not name:
            print(
                f"  ❌ [{n}/{len(todo)}] {target} ID={case_id} — 사건명을 못 읽었다. "
                "응답 구조를 확인하라"
            )
            failed += 1
            continue

        if dry_run:
            if n <= 5 or n % 200 == 0:
                print(f"  ✅ [{n}/{len(todo)}] {eff or '일자없음':<8}  {name[:52]}")
            continue

        # 🚨 파일명에 일자를 넣지 않는다 — **법령과 다르다.**
        #    법령은 개정마다 새 시행본이 나와 `{id}_{시행일}` 로 판을 구분해야 하지만,
        #    판례·재결례는 **확정된 사건 기록이라 판이 하나뿐이다.**
        #    규약 2(덮어쓰지 않는다)는 `save_raw()` 의 sha256 검사가 이미 지킨다.
        #    🚨 처음에는 법령 관례를 근거 확인 없이 복사했고, 일자 없는 record 6건이
        #       저장을 거부당하면서 드러났다 — **관례는 그 근거가 적용될 때만 옮긴다.**
        filename = f"{target}_{case_id}.xml"
        path = store.save_raw(
            source,
            family,
            filename,
            body,
            url=f"{BASE_SERVICE}?target={target}&ID={case_id}",
        )
        if path is not None:
            saved += 1
        # 🚨 2,769건을 전건 출력하면 실패가 묻힌다. 진행은 25건마다, 실패는 전부 찍는다.
        #    이어받기는 `store.save_raw()` 가 디스크를 보고 판단하므로 재실행이 안전하다.
        if n % 25 == 0 or n == len(todo):
            print(
                f"     … {n:,}/{len(todo):,}  (새로 저장 {saved:,} · 실패 {failed:,}"
                f"{f' · 본문 미제공 {len(missing):,}' if missing else ''})"
            )

    if missing:
        # 🚨 화면에만 두지 않는다. **재현성의 일부다** — 다음 사람이 같은 질의로 돌렸을 때
        #    합집합과 저장 건수가 다른 이유가 여기 있고, 그것을 모르면 「누락」으로 읽는다.
        print(
            f"\n  ⚠ 본문 미제공 {len(missing)}건 — 검색 인덱스에는 있으나 본문 조회가 빈 봉투를 준다.\n"
            "     🚨 우리 잘못이 아니고 재실행해도 같다. 사실원장에 ID 를 남긴다 (D-54)."
        )
        for i in range(0, len(missing), 10):
            print("       " + " ".join(missing[i : i + 10]))

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


#: 🚨 필터를 **통과했지만** 눈으로 한 번 더 볼 사건명의 표지 (`--audit` 전용).
#:    어휘에 없는 세무·회계 말이다. 통과한 것 중 여기 걸리는 것을 따로 찍어,
#:    「제외 어휘가 아직 못 잡는 계열」을 사람이 보게 한다.
#:    🚨 이걸 제외 어휘에 넣지 마라 — 「용역」·「비용」은 우리 사건명에도 흔하다.
#:       보는 눈과 거르는 손을 같은 목록으로 쓰면, 보려고 넣은 단어가 조용히 지운다.
AUDIT_WATCH: tuple[str, ...] = ("조세", "세무", "과세", "경비", "비용", "수수료", "용역")


def audit_saved(target: str) -> int:
    """이미 받아 둔 원문에 **현재 필터를 다시 걸어 본다.** 반환값은 탈락 건수다.

    🚨 네트워크를 쓰지 않는다. `data/raw/law/` 만 읽는다 — 어휘를 고칠 때마다
       공공기관 서버를 다시 두드리지 않으려고 이렇게 짰다 (규약 5).

    🚨 게이트(`registry.require`)를 부르지 않는다 — **수집이 아니기 때문이다.**
       규약 1 은 원천에 접근하는 자리의 규칙이고, 여기는 우리 디스크만 본다.

    🚨 왜 필요한가 — 어휘는 **나중에 바뀐다.** 그때 이미 받아 둔 파일은 옛 어휘로
       걸러진 것이라 새 기준과 어긋난 채 남는다. 어긋난 것을 **사람이 보고 지우게**
       하려고 목록으로 찍는다. 🚨 이 함수는 **아무것도 지우지 않는다** — D-19·규약 2 가
       걸린 자리라 삭제는 사람이 파일명을 보고 한다.
    """
    raw_dir = Path("data") / "raw" / FAMILY
    paths = sorted(raw_dir.glob(f"{target}_*.xml"))
    print(f"\n  이미 받아 둔 {target} — {len(paths):,}건 ({raw_dir.as_posix()}/)")
    if not paths:
        print("  🚨 파일이 없다. 경로나 target 을 확인해라.")
        return 0

    dropped: list[tuple[str, str]] = []
    watched: list[tuple[str, str]] = []
    for path in paths:
        root = _parse(path.read_bytes())
        if root is None:
            # 🚨 읽히지 않는 파일도 탈락으로 센다 — 「검사하지 못한 것」을 통과로 두지 않는다.
            dropped.append((path.name, "🚨 파싱 실패 — 파일을 직접 봐라"))
            continue
        name = _text(root, *NAME_FIELDS)
        if not _in_domain(name):
            dropped.append((path.name, name or "🚨 사건명 없음"))
        elif any(word in name for word in AUDIT_WATCH):
            watched.append((path.name, name))

    print(f"\n  ❌ 현재 필터에 탈락 — {len(dropped):,}건")
    print("     🚨 이 파일들은 옛 어휘로 받은 것이다. 지울지는 사람이 정한다.")
    for filename, name in dropped:
        print(f"       {filename}  {name}")

    print(f"\n  ⬜ 통과했지만 눈으로 볼 것 — {len(watched):,}건 (표지: {' · '.join(AUDIT_WATCH)})")
    print("     🚨 탈락이 아니다. 「어휘가 아직 못 잡는 계열」을 사람이 보라고 찍는다.")
    for filename, name in watched:
        print(f"       {filename}  {name}")
    return len(dropped)


def main() -> int:
    ap = argparse.ArgumentParser(description="법제처 OPEN API 수집기 (S1-01 · S1-02)")
    ap.add_argument(
        "--target", choices=sorted((*TARGETS, *CASE_TARGETS, *INTERP_TARGETS)), default="law"
    )
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 조회만")
    ap.add_argument("--find", action="store_true", help="미확보 항목의 ID 를 검색만 한다")
    # 🚨 사건명 필터 뒤에도 수백 건이고 0.5초 간격이라 여러 분이 걸린다.
    #    첫 실행은 --limit 로 소량을 먼저 보고 나서 전량을 받는다.
    ap.add_argument("--limit", type=int, help="prec·decc 전용 — 앞 N 건만 받는다")
    # 🚨 네트워크를 쓰지 않는다. 어휘를 고친 뒤 **이미 받아 둔 것**에 다시 걸어 본다.
    ap.add_argument("--audit", action="store_true", help="받아 둔 원문에 현재 필터를 다시 건다")
    # 🚨 질의 없이 전량을 받는다. 사건명 필터(`_in_domain`)만 걸린다 —
    #    사람이 박는 것이 질의에서 **어휘 하나로** 줄어드는 자리다.
    ap.add_argument(
        "--all",
        action="store_true",
        help="prec·decc 전용 — 질의 없이 전량을 받아 사건명 필터만 건다",
    )
    args = ap.parse_args()

    try:
        if args.audit:
            dropped = audit_saved(args.target)
            # 🚨 탈락이 있어도 **0 으로 끝낸다.** 이것은 검사가 아니라 사람에게 보이는
            #    목록이다. 종료코드 1 로 만들면 pre-commit·CI 가 이걸 실패로 읽는다.
            print(f"\n(audit — 아무것도 지우지 않았다 · 탈락 {dropped:,}건)")
            return 0
        if args.find:
            find_pending()
            return 0
        if args.target in CASE_TARGETS or args.target in INTERP_TARGETS:
            saved, failed = collect_cases(
                args.target, dry_run=args.dry_run, limit=args.limit, all_cases=args.all
            )
        else:
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
        # 🚨 받은 소스의 원장에 찍는다 — 1차 해석을 `law_go_kr` 에 찍으면 서명과 기록이 갈린다.
        registry.mark_collected(INTERP_TARGETS.get(args.target, SOURCE_ID))
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
