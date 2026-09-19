"""collect — 수집기 공통 모듈.

🚨 수집기는 여기를 거치지 않고 파일을 쓰지 않는다.
   규약(수집리스트 v1.2 「수집기 공통 규약」)을 문서가 아니라 코드로 들고 있는 곳이다.

  1. registry.require(source_id, use)  로 시작한다        → registry.py
  2. 원본은 data/raw/ 에 무손상 저장 · 덮어쓰기 금지        → store.py
  3. manifest.jsonl 에 1행 append                          → store.py
  4. sha256 동일하면 스킵                                   → store.py
  5. sleep 0.5 이상 + 재시도 3회 (지수 백오프)              → http.py
  6. 크롤링형은 robots_checked_at 기록 후에만 실행          → registry.py
  7. 모든 산출 행에 provenance + redistributable            → store.py
"""

# 🚨 **여기서 아무것도 import 하지 않는다** (D-109).
#    `collect/probe.py` 는 저장을 하지 않는 경로인데, 이 파일이 `store` 를 끌어오면
#    **탐침 프로세스에 저장 코드가 로드된다.** 「안 부른다」는 약속과 「부를 수 없다」는
#    구조는 다르고, 게이트 23 이 검사하는 것은 뒤쪽이다.
#    쓰는 쪽이 `from collect import registry, store` 처럼 필요한 것만 집어 간다 —
#    실제로 재수출을 쓰는 곳은 한 군데도 없었다.

#: 🔴 **소스 → 수집기.** 런처는 이 표를 읽는다 — 껍데기가 판정을 들지 않는다 (D-99 · D-179).
#:
#:    ⛔ 2026-09-10 까지 `launcher.py collect` 는 소스와 무관하게 `collect.openapi` 한 곳으로만
#:       보냈다. `status: collect` 31건 중 실제로 받아지는 것은 **7건**뿐이었다.
#:       `mfds_online_guideline`(자료실 PDF 다운로드)이 그 자리에서 터졌고, 오류 문구가
#:       *"포털 상세기능에서 요청주소를 확인해 적는다"* 라 안내해 — 따라 하면 **오픈API 가 아닌
#:       게시판 URL 을 `endpoints.yaml` 에 넣게 되는** 잘못된 처방이었다 (D-51 의 반대).
#:    ★ 같은 파일의 `extract`·`scan` 은 이미 표를 읽고 없으면 「표를 본다」로 끝낸다.
#:      `collect` 만 그 패턴을 못 받았다.
#:
#: 값 — `(모듈, 소스id 를 어떻게 넘기나)`
#:    "arg"    → `python -m <모듈> <소스id> --use U1`   (여러 소스를 다루는 수집기)
#:    "none"   → `python -m <모듈>`                     (한 소스 전용)
#:    "target" → `python -m <모듈> --target law`        (법제처 API · 법령)
#:    "target=<값>" → `python -m <모듈> --target <값>`   (법제처 API · 법령 밖 target)
COLLECTORS: dict[str, tuple[str, str]] = {
    # 오픈 API — `collect/endpoints.yaml` 에 요청주소가 있다
    "mfds_hf_ingredient": ("collect.openapi", "arg"),
    "mfds_hf_individual": ("collect.openapi", "arg"),
    "mfds_sanctions": ("collect.openapi", "arg"),
    "foodsafety_penalty_std": ("collect.openapi", "arg"),
    # ⛔ 2026-09-19 미채택 — 원천이 서비스를 안 준다(ERROR-310 · 두 키). `registry_tail.yaml` not_adopted.
    #    "foodsafety_ad_monitor": ("collect.openapi", "arg"),
    "cosmetic_ingredient": ("collect.openapi", "arg"),
    "cosmetic_restricted": ("collect.openapi", "arg"),
    "ftc_decisions_api": ("collect.openapi", "arg"),
    # 게시물 첨부 — 자료실·안내서·사례집. 🚨 게시물 HTML 을 파싱하는 **스크래퍼**다
    "mfds_casebook": ("collect.mfds_board", "arg"),
    "mfds_special_use_guide": ("collect.mfds_board", "arg"),
    "mfds_online_guideline": ("collect.mfds_board", "arg"),
    # 한 소스 전용 수집기
    "mfds_press": ("collect.mfds_press", "none"),
    "mfds_hf_ingredient_board": ("collect.mfds_hf_board", "none"),
    "ftc_decisions_body": ("collect.ftc_body", "none"),
    # 법제처 — 한 모듈이 `--target` 으로 갈린다
    "law_go_kr": ("collect.law_api", "target"),
    # 🆕 2026-09-18 — 중앙부처 1차 해석(식약처). 같은 모듈 · **다른 소스 id** (등재 단위는 이용조건 · D-90).
    #    ⬜ G0 · hold — 2인 확인 전에는 `registry.require()` 가 첫 줄에서 막는다. 그것이 정상이다.
    "mfds_cgm_expc": ("collect.law_api", "target=mfdsCgmExpc"),
}

#: 🚨 **수집기가 없는 것은 없다고 적는다** — 「빠진 것」인지 「사람이 받는 것」인지 갈린다 (D-110).
#:    AI Hub·설문·통계 계열은 신청·회원가입이 필요해 **사람이 받아 `launcher.py register` 로 올린다.**
MANUAL_SOURCES = {
    "aihub_558",
    "aihub_71486",
    "aihub_71694",
    "aihub_71723",
    "aihub_review_corpus",
    "bab2min_shopping",
    "nsmc",
    "klue_dataset",
    "kobaco_mcr",
    "krei_food",
    "khff_survey",
    "kcc_media",
    "kosis",
    # 🔄 2026-09-17 — 식품안전나라 게시판(menu_no=4806)의 PDF 다. `mfds_board` 는
    #    mfds.go.kr 전용이라 이 사이트를 못 받는다 — 사람이 내려받아 register 로 올린다.
    #    🚨 그래서 SCRAPERS 를 안 지난다 = robots 검사 대상이 아니다. 우리가 HTML 을
    #       긁지 않기 때문이고, 자동 수집을 열면 그때 robots 를 재고 COLLECTORS 로 옮긴다.
    "mfds_casebook_2021",
    "mfds_production",
    "ftc_decisions",
    "self_sanction_stat",
}

#: 🔴 **게시판 HTML 을 파싱하는 수집기** — 이 모듈로 가는 소스는 robots 확인이 필요하다 (규약 6).
#:    ⛔ 종전에는 `access` **산문에 낱말이 있는지**로 판단했다 (`{크롤링, 게시판, 스크래핑}`).
#:       그래서 「자료실 PDF 다운로드」·「보도자료 웹 공개」·「웹 서비스」가 낱말표에 없어
#:       **HTML 을 실제로 긁는 소스 6건이 robots 검사를 통째로 지나갔다.**
#:       `mfds_board.py` 는 게시물 HTML 을 파싱하는 명백한 스크래퍼인데 한 번도 안 걸렸다.
#:    ★ 산문이 아니라 **어느 수집기가 그 소스를 다루는가**로 판단한다 (D-167 · D-89 · D-179).
SCRAPERS = {"collect.mfds_board", "collect.mfds_press", "collect.mfds_hf_board"}


def is_scraper(source_id: str) -> bool:
    """이 소스를 다루는 수집기가 HTML 을 긁는가."""
    spec = COLLECTORS.get(source_id)
    return bool(spec) and spec[0] in SCRAPERS
