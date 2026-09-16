# 요청 — 오류 로그 저장 테이블 `app_error_log` (초안)

> **요청** 소성민 (ssm) · 2026-09-16
> **검토** 오한빈 (팀장)
> **상태** ⬜ 초안 — 승인 전. 스키마·마이그레이션은 등급 1(`db/**` · `alembic/**`)이라 **제가 고치지 않습니다.**
> **관련** 병렬작업 계약 §5 · 보안점검 P1-4 · P1-6 · P1-8 · `app/logging_conf.py`

---

## 0. 한 줄

지금 로그는 **stdout 에만** 나갑니다. 서버를 끄면 사라지고, 관리자가 화면에서 오류를 볼 길이 없습니다.
**WARNING 이상만** DB 에 쌓고, 관리자 콘솔에 **읽기 전용** `/admin/errors` 화면을 붙이려 합니다.

---

## 1. 요청 드리는 것 (판단 다섯)

| # | 요청 | 제 제안 |
|---|---|---|
| ① | `app_error_log` 테이블 추가 (아래 §2) | 런타임 층 — `alembic/versions/` + `app/models.py` (`app_account` 0012 와 같은 자리) |
| ② | **보관 기간** | ⬜ 판정 필요. 원장에 적힌 값이 없어 숫자는 비워 둡니다 (D-54) |
| ③ | `setup_logging()` 에 DB 핸들러를 붙이는 한 줄 | 핸들러 본체는 제가 새 파일로 만들고, `logging_conf.py` 수정은 팀장님께 맡기거나 허락을 받고 하겠습니다 |
| ④ | 새 라우터 등록 (`app/routers/__init__.py` · `app/api.py`) | `admin.py` 는 psj 와 같이 쓰는 파일이라 **`admin_errors.py` 로 분리** (§5 「쪼개는 것이 규칙보다 싸다」) |
| ⑤ | 클라우드 에디션에서도 저장하나 | 클라우드는 admin 라우터가 안 붙습니다(D-213). 저장만 하고 볼 화면이 없게 되니 **온프레미스만** 켜는 쪽을 제안합니다 |

---

## 2. 테이블 초안

| 컬럼 | 타입 | NULL | 설명 |
|---|---|:-:|---|
| `id` | UUID | ✗ | PK — 순차 정수 안 씀 (P1-5 와 같은 이유) |
| `occurred_at` | timestamptz | ✗ | 기본값 `now()` |
| `level` | varchar | ✗ | `CHECK (level in ('WARNING','ERROR','CRITICAL'))` |
| `logger_name` | varchar | ✗ | 예: `copylane.admin`, `uvicorn.error` |
| `message` | text | ✗ | **`RedactFilter` 를 지난 뒤의** 문자열 |
| `exc_type` | varchar | ○ | 예외 **클래스 이름만** (예: `OperationalError`) |
| `module` · `func_name` · `lineno` | varchar · varchar · int | ○ | 어디서 났는지 |

- 인덱스: `occurred_at` 내림차순 (화면이 최신순으로 읽음)
- `COMMENT ON TABLE`: *"WARNING 이상 앱 로그. 마스킹 필터를 지난 값만 들어온다 (P1-4)"*

### 🚨 일부러 **안 넣는** 것

| 안 넣는 것 | 이유 |
|---|---|
| **트레이스백 전문** (`exc_text`) | `RedactFilter` 는 `record.msg` 와 `record.args` 만 지웁니다. **트레이스백은 필터를 안 지납니다** — 보안점검 P1-4 표 첫 줄(「예외 트레이스백에 request body 가 통째로」)이 그대로 DB 에 들어갑니다. 클래스 이름과 위치만 남깁니다 |
| 요청 경로 원문 · 쿼리스트링 | 문구가 실릴 수 있는 자리 (P1-4) |
| 사용자 이니셜 · IP | 그건 **접속기록(P1-8)** 입니다. 섞으면 보관 기준이 두 개가 됩니다 |
| INFO 이하 | `auth.audit()` 가 INFO 로 나갑니다 — 받으면 접속기록이 이 표에 섞입니다 |

---

## 3. 구현 계획 (승인 후, 제 담당 파일만)

| 파일 | 내용 | 등급 |
|---|---|---|
| 🆕 `app/error_log.py` | `logging.Handler` 하위 클래스 — `emit()` 에서 INSERT | 새 파일 (ssm) |
| 🆕 `app/routers/admin_errors.py` | `GET /admin/errors` — `require_governor` + `_list_sources()` 와 같은 패턴 (DB 실패 시 `None` → 안내 문구) | 새 파일 (ssm) |
| 🆕 `app/templates/admin/errors.html` | 최신순 목록 · 레벨 필터 | 등급 2 (ssm·psj) |

핸들러에서 지킬 것 —

1. **핸들러 자신에게 `RedactFilter` 를 붙입니다.** 파이썬은 자식 로거(`copylane.admin` 등)의 레코드가 전파될 때 **부모 로거의 필터를 안 거치고 핸들러 필터만** 거칩니다. `setup_logging()` 이 root 로거에 건 필터로는 안 막힙니다.
2. **DB 저장이 실패해도 앱이 안 죽고, 그 실패를 다시 로그로 남기지 않습니다** — 무한 반복 방지(재진입 가드).
3. 오류 원인 문자열은 안 남깁니다 — 기존 코드처럼 `type(e).__name__` 만 (호스트·포트·사용자명이 들어 있음).
4. `sqlalchemy.engine` 레코드는 받지 않습니다 — 바인딩 파라미터에 문구 원문이 있습니다.

---

## 4. 확인 방법 (완료의 정의)

- 일부러 `logger.error("q=우리 제품은 면역력이 쑥쑥")` → DB 의 `message` 에 원문이 없고 `<가림 …>` 만 있다
- 예외를 일으킨 뒤 → `exc_type` 만 있고 트레이스백은 없다
- DB 를 끈 상태 → 앱이 뜨고, `/admin/errors` 는 안내 문구를 낸다
- 로그인 안 한 상태 → `/admin/errors` 가 `/login` 으로 보낸다

⬜ 게이트 테스트(`tests/**`)는 팀장 담당이라, 위 넷을 검사로 옮길지는 따로 여쭙겠습니다.
