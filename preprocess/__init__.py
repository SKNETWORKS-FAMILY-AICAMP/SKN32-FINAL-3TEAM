"""preprocess — 전처리 층. `data/raw/` 를 읽어도 되는 **둘째** 자리다.

게이트 `test_raw_는_수집_전처리_밖에서_참조되지_않는다` 의 `RAW_READERS` 가
`{"collect", "preprocess"}` 다 — 이 디렉터리는 그 약속이 처음부터 가리키던 자리이고,
2026-09-03 에 실물이 생겼다 (D-116).

🚨 **`scripts/` 는 raw 를 읽지 않는다.** 처음에 `scripts/ftc_triage.py` 로 두었다가
   게이트에 걸렸고, 게이트가 옳았다. `scripts/` 는 레지스트리·문서·빌드를 다루는 자리라
   거기에 raw 읽기를 한 번 허용하면 **학습 스크립트가 raw 를 글롭해도 막을 수 없다**
   (D-19 · D-92 가 막으려는 것이 정확히 그것이다).

전처리 사양(`docs/03_데이터/전처리_사양.md`)의 파이프라인이 여기 들어온다.

    [P1] 파싱 → [P3] 마스킹 → [P2] 정규화 → [P4] 문장분할 → [P5] 청킹 …

🚨 [P3] 마스킹이 [P2] 정규화보다 **먼저**다. 정규화가 오프셋 맵을 만드는데
   마스킹이 뒤에 오면 그 맵이 전부 어긋난다 (사양 0장).

🚨 **여기서 아무것도 import 하지 않는다** — `collect/__init__.py` 와 같은 이유다 (D-109).
   쓰는 쪽이 필요한 것만 집어 간다.
"""

#: 원천 id → 전처리(추출) 모듈.
#:
#: 🚨 **런처가 이 표를 읽는다 — 런처에 사본을 두지 않는다** (D-99).
#:    런처는 껍데기이고 진실의 원천이 아니다. 원천이 늘면 여기만 고친다.
#: 🚨 표에 문자열만 둔다. import 는 하지 않는다 (위 주석).
EXTRACTORS: dict[str, str] = {
    "mfds_casebook": "preprocess.mfds_casebook",
    "mfds_hf_ingredient_board": "preprocess.mfds_hf",
    "mfds_special_use_guide": "preprocess.mfds_guide",
    "ftc_decisions_body": "preprocess.ftc_extract",
    "mfds_press": "preprocess.mfds_press",
}

#: 원천 id → 계측 모듈. 🔴 **라벨을 만들지 않고 세기만 한다** — 산출물이 없다.
#:    받은 것이 전부인지(D-161) · 회피 표기와 광고 문구가 실제로 실리는지(D-40) 를 묻는다.
SCANNERS: dict[str, str] = {
    "mfds_sanctions": "preprocess.sanctions_scan",
    "mfds_casebook": "preprocess.evasion_scan",
    "mfds_press_pdf": "preprocess.evasion_scan",
    # 🆕 2026-09-20 — 1차 법령해석이 평가 라벨의 원천이 되는가 (부당광고 조항 · 문구 · 호). 후보는 build/ 에만
    "mfds_cgm_expc": "preprocess.interp_scan",
}
