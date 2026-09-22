"""app/settings.py — 설정과 **판정 파라미터**를 두는 한 곳 (D-99 · 병렬작업 계약 §1 #4).

⛔ **무엇이 있었나 ①** — `dsn()` 이 **네 벌**이었다 (2026-09-12 밤).

    app/api.py:51 · scripts/load_db.py:63 · scripts/embed.py:172 · scripts/search_probe.py:51

  네 곳 모두 `os.environ.get("DATABASE_URL") or "postgresql://…"` 를 그대로 적고 있었다.
  🔴 **그리고 네 곳 다 `.env` 를 안 읽고 있었다** — `.env` 에 값을 적어도 조용히 기본값으로
  떨어졌다. `collect/env.py` 자신이 *"`.env` 가 장식이었다"* 라고 적어 둔 사고의 재발이다.

⛔ **무엇이 있었나 ② — 그 수정이 새 구멍을 냈다** (2026-09-12 밤 · 발견 당일).
  검증기를 `("postgresql://", "postgres://")` 로만 열어 뒀는데, `.env.example` 이
  **「기본값 · 그대로 두면 됩니다」**라고 적어 둔 값은 `postgresql+psycopg://…` 였다.

      "postgresql+psycopg://…".startswith(("postgresql://", "postgres://"))  →  False

  🚨 **문서대로 복사한 사람은 반드시 밟는다.** 그리고 소비자가 둘이라 값도 두 형태다 —
  **alembic(SQLAlchemy)은 `+psycopg` 를 요구하고, psycopg 직결은 그것을 못 읽는다.**
  ★ 그래서 여기서 **한 값을 받아 두 형태로 낸다** — `dsn()` / `sqlalchemy_url()`.

⛔ **무엇이 있었나 ③ — 파라미터가 코드 여기저기 박혀 있었다.**
  `512` 넷 · `30` 다섯(하나는 이름 없는 생리터럴) · `2`(재생성 K) 셋 · `20`(K-익명) 둘 ·
  범주 어휘 다섯. 하나를 바꾸면 나머지가 조용히 안 따라온다 (D-99).
  ★ 여기 모으되 **뜻이 다른 값은 합치지 않는다** — 같은 수라고 한 이름으로 묶으면
    D-200 이 갈라 둔 축을 되붙인다.

🚨 **판정 파라미터는 환경변수로 열지 않는다** (D-205). 설계·탐색은 자유롭되 **결정은 실측과
   검증으로** 남아야 하는데, `.env` 로 바꾸면 **바뀐 사실이 아무 데도 안 남는다.**
   탐색은 도구의 인자로 한다 — `search_probe --pool`, `experiment` 의 `params`.
   환경으로 여는 것은 **접속 문자열과 운영 값**뿐이다.

🚨 **`pydantic-settings` 는 아직 안 쓴다.** 새 의존성이라 `uv.lock` 이 바뀌고 lock 은 팀장
   단독이며 충돌이 팀 전체로 번진다 (D-87). 필요한 것(한 곳·타입·검증)은 `BaseModel` 로 된다.
"""

from __future__ import annotations

import functools
import os
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ══════════════════════════════════════════════════════════════════════
#  1. 접속 — 한 값을 받아 두 형태로 낸다
# ══════════════════════════════════════════════════════════════════════

#: 🚨 `docker-compose.yml` 의 기본 사용자·비밀번호와 같아야 한다. 값이 갈리면
#:    「내 기기에서는 붙는데」가 난다. 이 문자열이 **저장소에서 유일**해야 하는 이유다.
#: ⛔ 진짜 비밀번호를 여기 적지 않는다 — 로컬 개발 기본값이고 `127.0.0.1` 에만 열려 있다.
DEFAULT_DATABASE_URL = "postgresql://copylane:copylane@localhost:5432/copylane"

#: SQLAlchemy(alembic·ORM)가 요구하는 드라이버. psycopg 직결은 이것을 **못 읽는다.**
SQLALCHEMY_DRIVER = "psycopg"

#: 🆕 2026-09-22 — DB 에 **붙을 때 기다리는 최대 초**. `[임의]` — 로컬 도커(`127.0.0.1`)라 붙을 수 있으면 곧바로 붙는다.
#:    ⛔ 이 값이 없으면 psycopg 는 응답 없는 주소를 **끝없이** 기다린다 — 화면·도구가 멈춘 것처럼 보인다.
#:    🔗 쓰는 곳 — `app/db.py`(화면의 ORM 엔진) · `scripts/db_reset.py`(지우기 전 콘솔 계정 명단). 둘이 따로 3 을 적던 것을 여기로 모았다 (D-99).
#:    ⬜ `scripts/doctor.py` 의 DB 검사는 5초를 따로 적는다 — 진단은 조금 더 기다린다. 합치지 않았다.
DB_CONNECT_TIMEOUT_S = 3

#: `postgresql://` · `postgres://` · `postgresql+psycopg://` 를 다 받는다.
#: ⛔ 아무 드라이버나 받지는 않는다 — `+asyncpg` 를 적으면 psycopg 경로가 죽는다.
_SCHEME = re.compile(rf"^postgres(?:ql)?(?:\+{SQLALCHEMY_DRIVER})?://")


# ══════════════════════════════════════════════════════════════════════
#  2. 판정·검색 파라미터 — 코드에 흩지 않는다
# ══════════════════════════════════════════════════════════════════════


class Params(BaseModel):
    """판정·검색·적재 파라미터 한 벌. 🚨 **얼려 둔다** — 돌던 중에 바뀌면 못 재현한다.

    🔴 **출처 태그가 없는 값을 여기 두지 않는다** — `[측정]`/`[문헌]`/`[관행]`/`[임의]`/`[설계]`.
       `[설계]`·`[임의]` 는 **바꾸는 조건**을 같이 적는다 (D-201 → D-205).
    ⛔ **같은 수라고 한 칸에 합치지 않는다.** `citation_token_max` 와 `rerank_token_max` 는
       지금 둘 다 512 지만 **재는 축이 다르다** (D-200 · D-202).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── 검색 ──────────────────────────────────────────────────────────
    #: `[설계]` 기획서 5-6 「후보 50」. **바꾸는 조건** — 골든셋 30건(D-40) + 응답시간 실측(D-77).
    #: 🚨 탐색은 `search_probe --pool` 로 한다. 여기 값을 바꾸는 것은 **결정**이다 (D-205).
    pool: int = Field(50, ge=1)
    #: `[설계]` 기획서 5-6 「상위 5」. `pool` 과 같은 조건에서 함께 연다.
    top_k: int = Field(5, ge=1)
    #: `[문헌]` RRF (Cormack et al., SIGIR 2009). 🚨 **가중치가 아니다** — 순위 완만도다.
    rrf_k: int = Field(60, ge=1)
    #: `[관행]` 조사를 깎고 남는 어간의 최소 길이. 1글자는 아무 데나 걸린다.
    min_stem: int = Field(2, ge=1)

    # ── 청크·토큰 (축이 둘이다) ────────────────────────────────────────
    #: `[설계]` **인용 단위**의 토큰 상한 — `chunk.token_count`. `db/schema.sql` 의
    #: `ck_chunk_tokens` 와 같아야 한다. 게이트가 대조한다.
    citation_token_max: int = Field(512, ge=1)
    #: `[설계]` **리랭커 입력**의 토큰 상한 — `chunk.input_token_count`.
    #: ⬜ **리랭커 미선정**이라 잠정으로 인용 상한과 같은 값을 쓴다. 모델이 정해지면 바뀐다.
    rerank_token_max: int = Field(512, ge=1)
    #: `[임의]` 512 의 보수적 글자 환산. ⬜ **폐기 예정** — 실제 토크나이저로 재면 사라진다.
    chunk_max_chars: int = Field(700, ge=1)

    # ── 판정 ──────────────────────────────────────────────────────────
    #: `[설계]` 재생성 라운드 K (D-126 · 총 라운드 K+1). **바꾸는 조건** — CPU 생성 1건 실측
    #: (기획서 8-4 #5). ⛔ 계약(`contracts.py`)과 DB(`models.py`)가 **같은 수**를 들어야 한다.
    max_attempt: int = Field(2, ge=0)
    #: `[설계]` 진입점 B 의 후보 수 N (D-34).
    candidate_n: int = Field(3, ge=1)

    # ── 표본·통계 ─────────────────────────────────────────────────────
    #: `[문헌]` D-40 — 이 수 미만은 「측정 불가」다. 성공률로 읽지 않는다.
    min_measurable: int = Field(30, ge=1)
    #: `[측정]` D-249 — 인용 광고 문구의 **보관 상한**(글자). 넘는 행은 **버린다 · 자르지 않는다**.
    #: 근거: ftc 「이유」 인용 최대 119자(2026-09-20 클론 B) — 문장 하나가 들어가는 길이. 팀장 판정.
    #: 🚨 D-133 의 40 은 이 값으로 개정됐다 — 40 이면 `부당_비교광고` 평가 표본이 35 → 27 로 D-40 밑이다.
    #: **바꾸는 조건** — 올릴 때 이유를 결정기록에 남긴다(D-133 이 정한 규칙 그대로).
    quote_max_chars: int = Field(120, ge=1)
    #: `[설계]` 세그먼트 K-익명 하한. `db/schema.sql` 의 `ck_segment_k_anon` 과 같아야 한다.
    #: **바꾸는 조건** — 스키마 주석이 「W1 확정 후 조정」이라 적어 뒀다.
    k_anon_min: int = Field(20, ge=1)

    # ── 입구 상한 (보안) ──────────────────────────────────────────────
    #: `[설계]` 한 요청이 담을 수 있는 글자 수. `contracts.py` 의 `max_length` 와 같은 수다.
    #: 🚨 **없으면 무제한이다** — 요청마다 새 커넥션 + 전 코어 인코딩 (보안점검 P2-11).
    max_text_len: int = Field(2000, ge=1)
    #: `[설계]` `limit` 의 천장. 없으면 `?limit=1000000` 이 조문 전문을 긁어 간다.
    max_limit: int = Field(50, ge=1)

    # ── 적재 ──────────────────────────────────────────────────────────
    #: `[관행]` 임베딩 배치. 기기 메모리에 따라 다르다 — 판정에 안 걸린다.
    embed_batch: int = Field(32, ge=1)
    #: `[설계]` 임베딩 모델. 🚨 **읽을 때는 DB 의 `model_id` 가 정본이다**(`retrieve.py`).
    #: 이 값은 **쓸 때** 쓴다. `embed_revision` 과 짝으로만 의미가 있다.
    embed_model_id: str = Field("nlpai-lab/KURE-v1", min_length=1)
    #: ⬜ **비어 있다 — 태그는 움직인다** (기획서 8-4 #9 · 보안점검 P0-3).
    #: `experiment.py` 가 팀원에게 `revision` 을 요구하면서 본체가 안 지키고 있었다.
    embed_revision: str = Field("", description="HF 커밋 SHA 40자. 비면 태그를 따라간다")
    #: `[설계]` 임베딩 차원. `db/schema.sql` 의 `vector(1024)` 와 같아야 한다.
    embed_dim: int = Field(1024, ge=1)


#: 🔴 **로드해도 되는 모델의 화이트리스트** (2026-09-12 밤 · 보안점검 P0-3 · D-212).
#: ⛔ **무엇이 있었나** — `retrieve.py` 가 *"모델 이름을 상수로 들지 않는다 · DB 가 정본이다"*
#:    라 적고 `SELECT DISTINCT model_id FROM chunk_embedding` 의 결과를 그대로
#:    `SentenceTransformer(...)` 에 넘겼다. 재현성 근거로는 옳지만, **그 순간 DB 문자열이
#:    코드 로딩 경로에 닿는다** — `chunk_embedding` 에 한 행을 넣을 수 있는 사람이
#:    임의 HF 저장소를 로드시킬 수 있고, `.safetensors` 가 없으면 `.bin`(pickle)이 풀린다.
#: ★ **DB 가 정본이라는 전제는 지킨다** — 어느 모델로 만든 벡터인지는 여전히 DB 가 말한다.
#:    여기서 더하는 것은 **「그 이름을 실제로 로드해도 되는가」** 하나다. 두 물음은 다르다.
#: 🚨 **새 모델을 쓰는 것은 코드 변경이다.** 그것이 맞다 — 모델 로드는 신뢰 결정이다.
ALLOWED_MODELS: frozenset[str] = frozenset({"nlpai-lab/KURE-v1"})

#: 🔴 **판정 파라미터의 단일 출처.** 코드 어디서도 이 값을 다시 적지 않는다 (D-99).
#:    게이트 `test_판정_파라미터를_코드에_다시_적지_않는다` 가 그것을 본다 (D-117).
PARAMS = Params()

#: 🚨 **범주 어휘의 정본은 `app/contracts.py` 의 `Category` 다** — 여기 다시 적지 않는다.
#:    기본값만 둔다. `retrieve`·`api` 가 `str` 로 받고 있어 오타가 조용히 0건이 됐다.
DEFAULT_CATEGORY = "일반"


# ══════════════════════════════════════════════════════════════════════
#  3. 에디션 — **관리자 화면이 어디에 서는가** (D-213 · 배포계획 §1)
# ══════════════════════════════════════════════════════════════════════

#: 🔴 **배포 그림에 제품 관리자 화면의 자리가 없었다** (2026-09-12 밤 검토).
#:    그림은 `api:8000`(Caddy 뒤 · 공개)과 `admin:8001 SQLAdmin`(127.0.0.1 · SSH 터널) 둘뿐인데,
#:    ssm·psj 가 만드는 **제품 관리자 화면**은 어느 쪽도 아니었다. `api:8000` 안에 두면
#:    배포하는 순간 **등급 판정 근거와 2인 확인 서명(사람 이름)이 공개 표면에 선다** —
#:    D-76·P2-10 이 「로컬에서 한다」로 미뤄 둔 그것이다. **읽기 전용이어도 같다.**
#: ★ 배포계획이 이미 *"에디션 = compose 프로파일"* 을 채택해 뒀다 (D-79 개정분 ②).
#:    그 손잡이를 그대로 쓴다 — **클라우드에서는 관리자 라우터를 아예 안 붙인다.**
#: 🚨 **「비로컬이면 503」은 폐기했다** — Caddy 뒤에서는 `request.client.host` 가 프록시다.
#:    `X-Forwarded-For` 를 믿으면 위조 가능하고, 안 믿으면 항상 503 이다.
#:    **판단을 네트워크 위상에 걸면 안 된다** — 에디션은 우리가 아는 사실이다.
EDITIONS = ("local", "demo", "onprem", "cloud")

#: 🔴 관리자 화면을 **붙이지 않는** 에디션. 라우트가 없으면 404 다 — 「막았다」의 가장 확실한 형태.
ADMIN_CLOSED_EDITIONS = frozenset({"cloud"})


# ══════════════════════════════════════════════════════════════════════
#  4. 환경에서 읽는 것 — 접속과 운영뿐
# ══════════════════════════════════════════════════════════════════════


class Settings(BaseModel):
    """환경에서 읽은 설정 한 벌. 🚨 **얼려 둔다.**"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_url: str = Field(min_length=1)

    #: 🔴 어느 판으로 떴는가 (D-213). 기본은 `local` — **개발 기기가 클라우드로 오인되지 않게.**
    #:    ⛔ 반대로 두면(기본 cloud) 개발자가 관리자 화면을 못 보고 원인을 못 찾는다.
    #:       위험한 쪽이 **기본값이 아니라 명시**여야 한다.
    edition: str = Field("local")

    #: 🚨 세션 쿠키 서명 키. 비어 있으면 **프로세스마다 새로 만든다** — 재시작하면 로그아웃된다.
    #:    ⛔ 그것이 맞다. 기본 키를 코드에 박으면 그 키가 곧 모두의 키가 된다.
    session_secret: str = Field("")

    @field_validator("edition")
    @classmethod
    def _known_edition(cls, v: str) -> str:
        if v not in EDITIONS:
            raise ValueError(
                f"COPYLANE_EDITION 이 {v!r} 이다 — 아는 것은 {list(EDITIONS)}.\n"
                "  🚨 오타는 조용히 `local` 로 떨어지면 안 된다 (D-220) — 클라우드에서 "
                "관리자 화면이 열린 채로 뜬다"
            )
        return v

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, v: str) -> str:
        """🔴 **PostgreSQL 이다. MySQL 이 아니다** (D-95).

        ⛔ 팀 5인의 이전 프로젝트가 MySQL 기반이라 `mysql://` 를 적을 수 있다. 그러면
           psycopg 가 훨씬 뒤에서 알아보기 어려운 오류로 죽는다 — **여기서 이름을 대고 막는다**
           (D-51 — 오류는 고치는 법을 보여준다).
        🚨 **`postgresql+psycopg://` 도 받는다** — `.env.example` 이 그 형태를 기본값으로
           적어 뒀고, alembic 이 그것을 요구한다. 형태 변환은 `dsn()`·`sqlalchemy_url()` 이 한다.
        """
        if not _SCHEME.match(v):
            scheme = v.split("://")[0] if "://" in v else v[:20]
            raise ValueError(
                f"DATABASE_URL 이 postgres 가 아니다 — {scheme}://…\n"
                "  🚨 저장 계층은 PostgreSQL + pgvector 다 (D-95 · D-41). MySQL 은 벡터를 "
                "별도 인프라로 빼야 하고 삭제가 2단계가 된다.\n"
                f"  받는 형태 — postgresql:// · postgres:// · postgresql+{SQLALCHEMY_DRIVER}://\n"
                "  고치는 법 — .env 의 DATABASE_URL 을 그중 하나로. 기본값은 "
                ".env.example 그대로 쓰면 된다"
            )
        return v


@functools.cache
def settings() -> Settings:
    """설정 한 벌. 🚨 **프로세스당 한 번만 읽는다** — 중간에 바뀌지 않는다.

    ⛔ `.env` 를 읽는 것은 `collect/env.py` 다. 여기서 `load_dotenv` 를 부르지 않는다 (D-99).
    🚨 **지연 import 다.** `collect.env` 는 `collect.http`(수집기의 HTTP 층)를 끌고 온다 —
       모듈 최상단에서 부르면 **판정 API 프로세스가 수집 계층을 통째로 import** 한다.
    """
    from collect import env as _env  # noqa: PLC0415 — 위 주석 참조

    _env.load()
    return Settings(
        database_url=os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL,
        edition=os.environ.get("COPYLANE_EDITION") or "local",
        session_secret=os.environ.get("COPYLANE_SESSION_SECRET") or "",
    )


def admin_is_mounted() -> bool:
    """관리자 화면을 붙이는가 (D-213).

    🚨 **붙이지 않으면 라우트 자체가 없다** — 404 다. 인증 실패(401)와 다른 답이고,
       그것이 맞다. **없는 것과 막힌 것은 다르다.**
    """
    return settings().edition not in ADMIN_CLOSED_EDITIONS


def dsn() -> str:
    """**psycopg 직결용** 접속 문자열 — 드라이버 접미사를 뗀다.

    🚨 **저장소에서 이 함수는 하나뿐이라야 한다** — 게이트
    `test_dsn_정의가_저장소에_하나뿐이다` 가 본다 (D-117).
    ⛔ `postgresql+psycopg://` 를 psycopg 에 그대로 주면 붙지 않는다. `.env.example` 이
       그 형태를 기본값으로 적어 두었으므로 **여기서 벗긴다.**
    """
    return settings().database_url.replace(f"+{SQLALCHEMY_DRIVER}://", "://", 1)


def sqlalchemy_url() -> str:
    """**SQLAlchemy(alembic·ORM)용** 접속 문자열 — 드라이버 접미사를 붙인다.

    ⛔ 접미사가 없으면 SQLAlchemy 가 기본 드라이버(psycopg2)를 찾고, 우리는 그것을 안 깐다.
    """
    url = settings().database_url
    if f"+{SQLALCHEMY_DRIVER}://" in url:
        return url
    # 🔄 2026-09-21 (전수 재검토) — ⛔ 검증이 받아 주는 `postgres://` 가 `postgres+psycopg://` 가 되어 SQLAlchemy 가
    #    `NoSuchModuleError … postgres.psycopg` 로 죽었다(방언 이름은 `postgresql` 이다). 앞머리를 먼저 맞춘다.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url.replace("://", f"+{SQLALCHEMY_DRIVER}://", 1)


def load_kwargs(model_id: str) -> dict[str, object]:
    """`SentenceTransformer(model_id, **load_kwargs(model_id))` 에 줄 인자 (P0-3).

    🔴 **화이트리스트 밖이면 여기서 막는다** — 로드 시점이 아니라 **인자를 만드는 자리**에서.
    ⛔ `trust_remote_code=False` 는 기본값이지만 **명시한다.** 기본값에 기대면 라이브러리가
       바꿀 때 조용히 열린다.
    🚨 `revision` 이 비어 있으면 **태그를 따라간다** — 태그는 움직인다 (기획서 8-4 #9).
       ⬜ SHA 를 아직 안 박았다. 값이 서면 이 함수는 안 바뀐다.
    """
    if model_id not in ALLOWED_MODELS:
        raise ValueError(
            f"허용 목록에 없는 모델이다 — {model_id!r}\n"
            "  🚨 모델 이름이 DB 에서 왔다면, 그 행을 넣을 수 있는 사람이 임의 저장소를 "
            "로드시킬 수 있다는 뜻이다 (보안점검 P0-3).\n"
            f"  허용: {sorted(ALLOWED_MODELS)}\n"
            "  고치는 법 — 새 모델을 쓰려면 app/settings.py 의 ALLOWED_MODELS 에 더한다. "
            "**코드 변경이 맞다** — 모델 로드는 신뢰 결정이다"
        )
    kw: dict[str, object] = {"trust_remote_code": False}
    # ⛔ `use_safetensors` 를 모르는 판이 있어 조용히 무시될 수 있다 — 그래서 **model_kwargs**
    #    로도 같이 넘긴다. 둘 중 하나는 닿는다 (`.bin` pickle 역직렬화 차단).
    kw["model_kwargs"] = {"use_safetensors": True}
    if PARAMS.embed_revision:
        kw["revision"] = PARAMS.embed_revision
    return kw
