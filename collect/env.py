"""환경 변수 로딩 — `.env` 를 실제로 읽는 유일한 곳.

🚨 `python-dotenv` 가 의존성에 있는데 아무도 부르지 않아 `.env` 가 **장식이었다** (2026-08-31 발견).
   키를 채워도 수집기가 못 읽는다. 여기서 한 번 읽고 전부가 이 모듈을 쓴다.

키 이름은 `.env.example` 이 단일 출처다. 스크립트마다 다른 이름을 쓰지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from collect import http

ROOT = Path(__file__).resolve().parent.parent
_loaded = False


class MissingKey(RuntimeError):
    """필요한 키가 .env 에 없다. 무엇을 어디서 받는지까지 알려준다."""


# 키 → (용도, 발급처)  — 오류 메시지가 「어떻게 고치나」를 내도록 (D-51)
KEYS = {
    # 1. 데이터 수집 (T1 · 1W~2W)
    "LAW_OC_KEY": (
        "법제처 OPEN API — 법령·고시 수집 (S1-01 · S1-02)",
        "open.law.go.kr > 마이페이지 > OPEN API 신청현황. 🚨 이메일의 @ 앞부분만 넣는다",
    ),
    "DATA_GO_KR_KEY": (
        "공공데이터포털 — 식약처 API 4종 (S1-04 · S1-05 · S2-03)",
        "data.go.kr 활용신청 (S0-05) — 즉시~1일",
    ),
    "FOODSAFETY_KEY": (
        "식품안전나라 OpenAPI — 건기식 기능성 원료 I-0040 · 개별인정형 I-0050",
        "🚨 data.go.kr 키가 아니다. 15058359 는 **API 유형이 LINK** 라 실제 호출이 "
        "openapi.foodsafetykorea.go.kr 로 가고, 인증키도 그쪽에서 따로 발급받는다. "
        "data.go.kr 활용신청 버튼이 그 사이트로 보낸다",
    ),
    "KOSIS_KEY": (
        "KOSIS 국가통계 — 6층 세그먼트",
        "kosis.kr/serviceInfo/openAPIGuide.do (S0-06) — 자동 발급",
    ),
    # 2. DB (T1 · 1W~)
    "DATABASE_URL": (
        "postgres 접속 — 🚨 PostgreSQL 이다. MySQL 이 아니다 (D-95)",
        "docker-compose 기본값 그대로 쓰면 된다. setup.bat 이 컨테이너를 띄운다",
    ),
    # 3. 학습·실험 (T2·T3 · 3W~)
    "MLFLOW_TRACKING_URI": (
        "실험 기록 — 🚨 LangSmith·W&B 는 쓰지 않는다 (D-43)",
        "기본값 file:./mlruns 그대로",
    ),
    "RUNPOD_API_KEY": (
        "학습 전용 (D-78) — 🚨 계정이 팀당 1개다. 슬롯 규칙을 먼저 정한다 (D-94)",
        "발급 담당 소성민",
    ),
    # 4. 평가·비교 (T3 · 4W~)
    "OPENAI_API_KEY": (
        "🚨 평가·비교 전용 (D-78 ②) — 판정·생성 런타임 경로 진입 금지",
        "doctor 16번이 「판정 경로의 외부 네트워크 요청 = 0」을 검사한다 (D-73)",
    ),
}


def load() -> None:
    """`.env` 를 한 번만 읽는다. 이미 설정된 환경 변수는 덮어쓰지 않는다."""
    global _loaded
    if not _loaded:
        # 🚨 encoding 을 명시한다. Windows 편집기가 .env 를 **UTF-8 BOM** 으로 저장하면
        #    dotenv 가 첫 줄 키 이름 앞에 U+FEFF 를 붙인다 — `LAW_OC_KEY` 를 넣어도
        #    `\ufeffLAW_OC_KEY` 로 들어가 못 읽는다. 값이 있는데 없다고 나오는,
        #    가장 찾기 어려운 종류의 실패다 (2026-09-02 실제 발생).
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
        _loaded = True


def get(name: str, *, required: bool = True) -> str:
    """키를 읽는다. 없으면 무엇을 어디서 받는지 알려주며 실패한다.

    🚨 읽은 값은 곧바로 `http.register_secret()` 에 등록한다 (D-111 확장).
       **키를 손에 쥐는 곳이 여기 하나뿐**이므로, 가릴 것을 알려 주는 자리도 여기다.
       등록해 두면 `FetchError` 가 URL 을 찍어도 그 값이 `<이름>` 으로 바뀐다 —
       2026-09-02 에 `serviceKey` 가 오류 메시지로 샜다.
    """
    load()
    value = (os.environ.get(name) or "").strip()
    if value:
        http.register_secret(name, value)
    if value or not required:
        return value

    purpose, where = KEYS.get(name, ("?", "?"))
    raise MissingKey(
        f"{name} 가 비어 있다 ({purpose}).\n"
        f"  발급  {where}\n"
        f"  기입  프로젝트 루트의 .env 파일 — 🚨 .env 는 커밋하지 않는다"
    )
