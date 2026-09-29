"""app/auth.py — `governor` 로그인 (D-66 · D-213 · 보안점검 P1-5 · P1-7 · P1-8).

★ **인증은 판정이 아니었다** — D-66(2026-08-19)이 이미 정했다:
  세션 쿠키(`HttpOnly` · `SameSite=Lax`) · **온프레미스는 계정 주입**(가입 화면 없음) ·
  역할은 **`governor` 하나** · 진입점별로 요구 수준을 다르게 (A 는 가입 없음).
  🚨 여기서 하는 것은 **그 결정의 구현**이고, D-66 이 안 정한 셋만 새로 정했다 (D-213) —
  해시 알고리즘 · 계정 주입 경로 · 접속기록의 자리.

🔴 **해시는 Argon2id** — OWASP Password Storage Cheat Sheet 의 preferred, 파라미터
   **m=19456(19 MiB) · t=2 · p=1**.
   ⛔ scrypt(표준 라이브러리)를 한때 추천했다가 **뒤집었다.** 이유 둘 —
      ① OWASP 는 scrypt 를 *"Argon2id 를 **못 쓸 때**"* 로 규정하는데 우리는 못 쓰는 게
        아니다 — `argon2-cffi-bindings` 가 **abi3 휠**(win_amd64 · manylinux)을 낸다.
        컴파일러가 필요 없다. **비용을 치르기 싫은 것과 못 쓰는 것은 다르다.**
      ② scrypt 최소 권고는 **64~128 MiB/로그인**이고 Argon2id 는 **19 MiB** 다.
        우리는 **P2-11(자원 고갈)을 이미 열어 뒀고** 배포는 추론과 16 GiB 를 나눠 쓴다 —
        무거운 쪽이 곧 **공격자에게 주는 증폭기**다. 표준 라이브러리라는 이점이 여기서 뒤집힌다.

🚨 **해시만으로는 안 된다.** 19 MiB 함수를 여는 것은 DoS 지렛대를 만드는 일이라
   **시도 제한이 같은 파일에** 있어야 한다 (P2-11). 아래 `_Throttle`.

⬜ **접속기록 1년 보관(고시 제8조)은 아직 테이블이 아니다** — 배포 전이 마감이고, 지금
   1년 보관할 곳이 로컬 DB 뿐이라 뜻이 없다. **로그인·로그아웃·인증 실패 세 사건을 로거로**
   남긴다. 테이블로 옮길 때 자리가 이미 있다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.settings import settings

_log = logging.getLogger("copylane.auth")

#: OWASP Password Storage Cheat Sheet — Argon2id preferred (2026-09 확인).
#: 🚨 값을 바꾸면 **기존 해시는 그대로 두고** 다음 로그인에서 재해시된다 (`needs_rehash`).
ARGON2_MEMORY_KIB = 19456  # 19 MiB
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1

#: 🔴 저장 형식은 **PHC 문자열** — `$argon2id$v=19$m=19456,t=2,p=1$…`
#:    ★ 알고리즘과 파라미터가 **값 안에** 있다. 나중에 올릴 때 판별이 필요 없다.
PHC_PREFIX = "$argon2id$"

#: 세션 수명. 🚨 짧게 둔다 — 관리자 콘솔은 오래 열어 둘 자리가 아니다.
SESSION_TTL_SEC = 8 * 3600
SESSION_COOKIE = "copylane_session"
CSRF_COOKIE = "copylane_csrf"
CSRF_FIELD = "csrf_token"

#: 🚨 시도 제한 (P2-11). 19 MiB × 동시 요청이 곧 자원 고갈이다.
MAX_ATTEMPTS = 5
LOCKOUT_SEC = 300


class AuthUnavailable(RuntimeError):
    """`argon2-cffi` 가 없다. 🚨 **조용히 약한 해시로 떨어지지 않는다** (D-220)."""


def _hasher():  # noqa: ANN202 — argon2 타입은 지연 import 라 여기서 못 적는다
    try:
        from argon2 import PasswordHasher  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover — lock 이 보장한다
        raise AuthUnavailable(
            "argon2-cffi 가 없다 — 비밀번호를 저장할 수 없다.\n"
            "  🚨 약한 해시로 떨어지지 않는다 (고시 제7조 · 보안점검 P1-7).\n"
            "  고치는 법 — uv lock && uv sync"
        ) from e

    return PasswordHasher(
        memory_cost=ARGON2_MEMORY_KIB, time_cost=ARGON2_TIME_COST, parallelism=ARGON2_PARALLELISM
    )


def hash_password(password: str) -> str:
    """PHC 문자열을 낸다. 🚨 **평문은 어디에도 안 남긴다** — 로그에도 예외에도."""
    return _hasher().hash(password)


def verify_password(stored: str, password: str) -> bool:
    """맞는가. ⛔ 틀린 이유를 나누지 않는다 — 없는 계정과 틀린 비번은 **같은 답**이다."""
    from argon2.exceptions import VerificationError, VerifyMismatchError  # noqa: PLC0415

    try:
        return bool(_hasher().verify(stored, password))
    except (VerifyMismatchError, VerificationError):
        return False


#: 없는 계정에도 해시를 한 번 돌리기 위한 값 — 처음 쓸 때 만든다(무작위 비밀번호의 해시 · 누구의 것도 아니다).
_DUMMY_HASH: str | None = None


def verify_account(stored: str | None, password: str) -> bool:
    """계정이 없어도 **같은 시간**이 걸리게 확인한다. 🆕 2026-09-21 (전수 재검토).

    ⛔ 없는 계정은 Argon2 를 건너뛰어 **4 ms**, 있는 계정의 틀린 비밀번호는 **40 ms** 였다(실측) — 답은 같아도
       걸린 시간이 계정의 존재를 알렸다. 로그인 docstring 의 「없는 계정과 틀린 비밀번호를 같은 답으로」(P1-5)가
       시간 축에서 깨져 있었다.
    """
    global _DUMMY_HASH
    if stored is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_hex(16))
        verify_password(_DUMMY_HASH, password)
        return False
    return verify_password(stored, password)


def needs_rehash(stored: str) -> bool:
    """파라미터가 낡았나. 🚨 **로그인 성공 시점에 조용히 올린다** — 사용자는 모른다."""
    return bool(_hasher().check_needs_rehash(stored))


# ══════════════════════════════════════════════════════════════════════
#  시도 제한 — 해시를 여는 것이 곧 지렛대를 만드는 것이다 (P2-11)
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _Throttle:
    """⛔ **프로세스 안에서만 센다.** `uvicorn --workers>1` 이 되면 워커마다 따로 센다 —
    그때는 DB 나 Redis 로 옮겨야 한다. 지금은 단일 프로세스라 이걸로 충분하고,
    **충분하지 않게 되는 조건을 여기 적어 둔다** (D-192).
    """

    fails: dict[str, list[float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            hits = [t for t in self.fails.get(key, []) if now - t < LOCKOUT_SEC]
            self.fails[key] = hits
            return len(hits) >= MAX_ATTEMPTS

    def fail(self, key: str) -> None:
        with self.lock:
            self.fails.setdefault(key, []).append(time.monotonic())

    def clear(self, key: str) -> None:
        with self.lock:
            self.fails.pop(key, None)


throttle = _Throttle()


# ══════════════════════════════════════════════════════════════════════
#  세션 — 서명 쿠키 하나. 🚨 새 의존성을 안 쓴다
# ══════════════════════════════════════════════════════════════════════

#: ⛔ Starlette 의 `SessionMiddleware` 는 `itsdangerous` 를 요구한다 — **또 하나의 의존성**이다.
#:    필요한 것(서명·만료)은 `hmac`+`secrets` 로 전부 된다.
_runtime_secret = secrets.token_urlsafe(32)


def _secret() -> bytes:
    """서명 키. 🚨 환경에 없으면 **프로세스마다 새로 만든다** — 재시작하면 로그아웃된다.

    ⛔ 기본 키를 코드에 박지 않는다. 박는 순간 **그 키가 모두의 키**가 된다.
    """
    return (settings().session_secret or _runtime_secret).encode("utf-8")


def _sign(payload: str) -> str:
    mac = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


#: 🆕 D-260 6-3 (가) — **일반 사용자 세션은 쿠키가 따로다.** 서명·만료 함수는 같이 쓴다(D-99).
#:    ★ 값에 접두어 `u:` 를 붙인다 — 관리자 쿠키 자리에 사용자 값을 옮겨 넣어도 `read_session` 이 거절한다.
#:    ⛔ 쿠키 하나에 역할 칸을 두는 안(나)은 기각 — 역할 칸을 읽는 곳 하나가 빠지면 사용자 세션이 관리자 문을 연다.
USER_SESSION_COOKIE = "copylane_user"
USER_PREFIX = "u:"


def _issue(subject: str) -> str:
    payload = f"{subject}.{int(time.time()) + SESSION_TTL_SEC}"
    return f"{payload}.{_sign(payload)}"


def _read(cookie: str | None) -> str | None:
    """서명·만료를 본 뒤 주체 문자열. 틀리거나 만료면 `None`. ⛔ **왜 틀렸는지 안 알려 준다.**"""
    if not cookie or cookie.count(".") != 2:
        return None
    subject, exp, sig = cookie.split(".")
    if not hmac.compare_digest(sig, _sign(f"{subject}.{exp}")):
        return None
    try:
        if int(exp) < int(time.time()):
            return None
    except ValueError:
        return None
    return subject


def issue_session(initials: str) -> str:
    """`<이니셜>.<만료>.<서명>`. 🚨 상태를 서버에 안 둔다 — 재시작이 곧 전원 로그아웃이다."""
    if initials.startswith(USER_PREFIX):
        raise ValueError("관리자 이니셜이 사용자 접두어로 시작한다 — 두 세션이 섞인다 (D-260 6-3)")
    return _issue(initials)


def read_session(cookie: str | None) -> str | None:
    """관리자 쿠키에서 이니셜. 틀리거나 만료면 `None`.

    🔴 **사용자 세션 값은 거절한다** (D-260 6-3) — 서명이 맞아도 `u:` 로 시작하면 관리자가 아니다.
    """
    subject = _read(cookie)
    if subject is None or subject.startswith(USER_PREFIX):
        return None
    return subject


def issue_user_session(user_id: uuid.UUID) -> str:
    """`u:<uuid>.<만료>.<서명>` — `USER_SESSION_COOKIE` 에 담는다."""
    return _issue(f"{USER_PREFIX}{user_id}")


def read_user_session(cookie: str | None) -> uuid.UUID | None:
    """사용자 쿠키에서 계정 id. 🚨 접두어가 없으면(= 관리자 값) `None` — 반대 방향도 섞이지 않는다."""
    subject = _read(cookie)
    if subject is None or not subject.startswith(USER_PREFIX):
        return None
    try:
        return uuid.UUID(subject[len(USER_PREFIX) :])
    except ValueError:
        return None


def new_csrf() -> str:
    """CSRF 토큰. 🚨 **주 방어는 `SameSite=Lax`** 다 — 최신 브라우저는 교차 사이트 POST 에
    쿠키를 안 붙인다. 이 토큰은 **이중 방어**이고, 그 사실을 여기 적어 둔다.
    """
    return secrets.token_urlsafe(24)


def csrf_ok(cookie: str | None, form_value: str | None) -> bool:
    """이중 제출 대조. ⛔ 둘 중 하나라도 비면 실패다 (D-220 — 없음이 통과가 되지 않는다)."""
    return bool(cookie) and bool(form_value) and hmac.compare_digest(cookie, form_value or "")


# ══════════════════════════════════════════════════════════════════════
#  접속기록 — ⬜ 테이블은 배포 전. 지금은 로거 (고시 제8조 · P1-8)
# ══════════════════════════════════════════════════════════════════════


def audit(event: str, initials: str | None, ok: bool) -> None:
    """로그인·로그아웃·인증 실패. 🚨 **문구가 아니라 접속 사실**이다 — P1-4 와 충돌하지 않는다.

    ⬜ 1년 보관은 테이블로 옮길 때 선다. 여기서는 **자리를 만든다** —
       옮길 때 부르는 쪽을 안 고치게 (D-99).
    """
    _log.info("audit event=%s actor=%s ok=%s", event, initials or "-", ok)
