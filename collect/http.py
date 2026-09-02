"""HTTP 수집 — 재시도·간격 (수집기 공통 규약 5).

🚨 상대는 공공기관 서버다. 간격 없이 두드리면 우리가 막히는 것으로 끝나지 않고,
   레지스트리에 적어 둔 「공식 API 이용」이라는 근거 자체가 흔들린다.

표준 라이브러리만 쓴다 — 수집기는 팀원 누구의 기기에서도 돌아야 한다.
🚨 그래서 이 모듈은 `collect.env` 를 **import 하지 않는다.** 키를 알아야 가릴 수 있는데,
   그 방향으로 의존을 만들면 순환이 된다. 반대로 뒤집었다 — `env.get()` 이 읽은 값을
   `register_secret()` 으로 **여기에 등록**한다 (D-111 확장).
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "CopyLane/0.1 (SKN Final Project; research use)"

MIN_INTERVAL = 0.5  # 규약 5 — 최소 간격
MAX_RETRY = 3  # 규약 5 — 재시도 3회
BACKOFF = 2.0  # 지수 백오프 계수

_last_call = 0.0


class FetchError(RuntimeError):
    """재시도를 다 쓰고도 실패했다."""


# ─────────────────────────────────────────────────────────────
#  키 가리기 (D-111 확장 · 2026-09-02)
# ─────────────────────────────────────────────────────────────
#  🚨 D-111 이 센 경로는 셋이었다 — 화면 입력 · 셸 기록 · 키 이름.
#     **넷째가 있었다: 오류 메시지.** 그리고 성질이 다르다 —
#     앞의 셋은 사람이 실수해야 새지만, 이것은 **코드가 정상 동작할 때** 샌다.
#
#  2026-09-02 실제 사고 — cosmetic 2건이 403 으로 실패했고 `FetchError` 가
#  요청 URL 을 통째로 찍어 `serviceKey` 값이 터미널·스크롤백·대화 기록에 남았다.
#  키를 재발급했다.
#
#  🚨 더 나쁜 자리는 `probe.py` 다. 거기서 `FetchError` 메시지는
#     `실측_<날짜>.md` 와 `build/probe_results.json` 으로 들어가고 **커밋된다.**
#     터미널은 닫으면 사라지지만 커밋은 남는다. 그래서 고치는 자리가 여기다 —
#     예외를 만드는 **한 곳**을 막으면 그것을 받아쓰는 모든 곳이 함께 막힌다.

MASK = "<가림>"

#: 값이 키인 쿼리 파라미터 이름. 🚨 소문자로 비교한다 (serviceKey · ServiceKey · SERVICEKEY)
SECRET_PARAMS = frozenset(
    {
        "servicekey",
        "service_key",
        "key",
        "apikey",
        "api_key",
        "oc",  # 법제처
        "authkey",
        "auth_key",
        "accesskey",
        "access_key",
        "token",
        "secret",
        "password",
    }
)

_QUERY_RE = re.compile(r"(?i)([?&])(" + "|".join(sorted(SECRET_PARAMS)) + r")=([^&#]*)")

#: 🚨 키가 **경로**에 있는 규약 — 식품안전나라 `/api/{keyId}/{serviceId}/{fmt}/{s}/{e}`.
#:  쿼리만 가리는 마스킹은 이쪽을 못 막는다. 길이 8 이상만 잡으므로
#:  `/api/sample/…`(6자) 과 `/api/I-0040/…`(6자) 은 걸리지 않는다.
_PATH_KEY_RE = re.compile(r"(?i)(/api/)([A-Za-z0-9%+._-]{8,})(/)")

_SECRETS: dict[str, str] = {}  # 값의 각 표기형 → 키 이름


def _forms(value: str) -> list[str]:
    """같은 값이 URL 안에서 취할 수 있는 표기형들.

    🚨 원문 그대로만 찾으면 못 잡는다 — `urlencode` 를 거치면서 `+/=` 가
       `%2B%2F%3D` 로 바뀐다. 2026-09-02 에는 **이중 인코딩**(`%252F`)까지 나왔다.
    """
    quoted = urllib.parse.quote(value, safe="")
    forms = [value, quoted, urllib.parse.quote(quoted, safe=""), urllib.parse.quote_plus(value)]
    return [f for f in dict.fromkeys(forms) if f]


def register_secret(name: str, value: str) -> None:
    """키 값을 「가릴 것」으로 등록한다. `env.get()` 이 읽을 때마다 부른다.

    🚨 값으로 가리는 것이 이름으로 가리는 것보다 강하다 — 쿼리든 경로든,
       인코딩이 어떻든, 파라미터 이름을 우리가 모르든 잡힌다.
    🚨 짧은 값은 등록하지 않는다. URL 의 정상적인 부분을 지워 오류 메시지를
       읽을 수 없게 만드는 쪽이 더 해롭다.
    """
    value = (value or "").strip()
    if len(value) < 8:
        return
    for form in _forms(value):
        _SECRETS[form] = name


def redact(url: str) -> str:
    """URL 에서 키를 가린다. **밖으로 나가는 모든 URL 문자열이 여기를 지난다.**

    세 겹이다. 하나가 놓쳐도 다음이 잡는다.

      ① 값   — 등록된 키 값(과 그 인코딩 변형)을 `<키이름>` 으로 바꾼다
      ② 이름 — `serviceKey=` · `OC=` 같은 쿼리 파라미터의 값을 가린다
      ③ 경로 — `/api/{키}/…` 규약의 두 번째 세그먼트를 가린다

    ①이 가장 정확하지만 `env` 를 거치지 않고 손으로 만든 URL 은 못 잡는다.
    ②③이 그 그물이다.
    """
    out = url
    for form, name in _SECRETS.items():
        if form in out:
            out = out.replace(form, f"<{name}>")
    out = _QUERY_RE.sub(_mask_param, out)
    return _PATH_KEY_RE.sub(_mask_segment, out)


def _already_masked(value: str) -> bool:
    """①이 이미 가린 자리는 건드리지 않는다 — `<DATA_GO_KR_KEY>` 가 `<가림>` 보다 낫다.

    어느 키가 샐 뻔했는지가 오류 메시지에 남아야 **그 키를 재발급**할 수 있다.
    """
    return value.startswith("<") and value.endswith(">")


def _mask_param(m: re.Match[str]) -> str:
    sep, name, value = m.group(1), m.group(2), m.group(3)
    return f"{sep}{name}={value if _already_masked(value) else MASK}"


def _mask_segment(m: re.Match[str]) -> str:
    head, seg, tail = m.group(1), m.group(2), m.group(3)
    return f"{head}{seg if _already_masked(seg) else MASK}{tail}"


def _hint(url: str, error: Exception) -> str:
    """자주 밟는 실패에 한 줄 힌트를 붙인다. 🚨 URL 을 다시 찍지 않는다."""
    code = getattr(error, "code", None)
    if code in (401, 403) and "%25" in url:
        return (
            "\n  🚨 키가 **이중 인코딩**돼 있다 (`%25` 는 `%` 의 인코딩이다).\n"
            "     data.go.kr 은 인증키를 Encoding 용·Decoding 용 둘로 준다 — "
            "`.env` 에는 **Decoding 키**를 넣는다.\n"
            "     (2026-09-02 에 이 실패로 한 시간을 썼다)"
        )
    if code in (401, 403):
        return "\n  ⓘ 401·403 은 키보다 **활용신청**이 먼저다 — 데이터셋별로 따로 낸다."
    return ""


def encode(url: str) -> str:
    """🚨 URL 에 ASCII 밖 문자가 있으면 퍼센트 인코딩한다.

    `urllib.request` 는 ASCII 만 받아 `UnicodeEncodeError` 로 죽는다 —
    **잡히지 않고 죽는다.** `FetchError` 가 아니라 재시도 루프 밖에서 터지므로
    한 소스가 전체를 멈춘다.

    2026-09-02 탐침 1회전에서 나스미디어 2건(`/정기보고서/…`)이 이렇게 터졌다.
    🚨 **탐침이 아니라 수집기의 버그다** — `collect/http.py` 는 둘의 공용이고,
    같은 URL 로 수집기를 돌렸어도 똑같이 죽었다. 국내 기관 사이트에 한글 경로는 흔하다.
    """
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            p.scheme,
            p.netloc.encode("idna").decode("ascii") if not p.netloc.isascii() else p.netloc,
            urllib.parse.quote(p.path, safe="/%"),
            urllib.parse.quote(p.query, safe="=&?/%"),
            urllib.parse.quote(p.fragment, safe="/%"),
        )
    )


def fetch(url: str, *, timeout: int = 30) -> bytes:
    """간격을 지키며 받아온다. 실패하면 지수 백오프로 재시도한다."""
    global _last_call

    url = encode(url)

    last_error: Exception | None = None
    for attempt in range(MAX_RETRY):
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                _last_call = time.monotonic()
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            _last_call = time.monotonic()
            last_error = e
            if attempt < MAX_RETRY - 1:
                time.sleep(MIN_INTERVAL * (BACKOFF**attempt))

    # 🚨 `url` 을 그대로 넣지 않는다. 이 한 줄이 2026-09-02 에 키를 흘렸다.
    raise FetchError(
        f"{redact(url)} — {MAX_RETRY}회 시도 실패: {last_error}"
        f"{_hint(url, last_error) if last_error else ''}"
    )
