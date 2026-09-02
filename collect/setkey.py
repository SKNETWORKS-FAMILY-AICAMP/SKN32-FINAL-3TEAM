"""API 키를 화면에 띄우지 않고 `.env` 에 넣는다 (D-51 · D-78 ③).

🚨 키가 흔적을 남기는 경로가 **셋**이다. 하나만 막으면 나머지로 샌다 (2026-09-02).
   ① 화면    — 눈으로 보고, 캡처하고, 대화창에 붙여 넣는다. **실제로 그랬다.**
   ② 셸 기록 — `... --key 13b6...` 는 PowerShell 의 `ConsoleHost_history.txt` 에
                남는다. 터미널을 닫아도 남고, 지운 줄 알아도 남아 있다.
   ③ 편집기  — 값을 `.env.example` 에 채우면 그 파일은 **커밋 대상**이다.
                `.env` 만 gitignore 에 있으니 **한 글자 차이가 유출**이 된다.

   셋을 한 번에 막는 길은 하나뿐이다 — 값이 **인자로도 화면으로도 지나가지 않게** 한다.
   그래서 값은 getpass 로만 받고, 확인은 원문 대신 **지문**으로 낸다.

       O  uv run python launcher.py setkey FOODSAFETY_KEY   입력이 화면에 안 뜬다
       X  편집기로 .env 열어 붙여넣기                        옆자리에서 보인다
       X  setkey FOODSAFETY_KEY 13b6...                     이 모듈이 거부한다

키 이름의 단일 출처는 `collect/env.py` 의 KEYS 다 (`.env.example` 과 짝).
여기서 이름을 새로 만들지 않는다 — 만들면 읽는 곳이 두 곳이 된다.
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import os
import re
import sys
from pathlib import Path

from collect import env

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


class SetKeyError(RuntimeError):
    """넣을 수 없다. 무엇이 막았고 어떻게 푸는지까지 낸다 (D-51)."""


# 🚨 .env 에 두지 않기로 한 것 (D-78 ③). 이름만 봐도 거부한다.
#    AWS 자격증명은 서버의 IAM 역할·시크릿으로 다룬다 — 이 파일 형태가 로컬 개발용이라
#    유출 경로가 다르다. 「일단 로컬에서만」 이 그대로 배포로 따라간다.
FORBIDDEN_PREFIX = ("AWS_", "AMAZON_")

# `.gitignore` 가 .env 를 덮는 표기들. 하나라도 있으면 통과.
IGNORE_FORMS = {".env", "/.env", ".env*", "*.env", "**/.env"}


def fingerprint(value: str) -> str:
    """확인용 지문 — 값을 드러내지 않으면서 「제대로 들어갔나」에 답한다.

    🚨 앞뒤 네 글자를 보여 주는 흔한 방식을 **쓰지 않는다.** 이 프로젝트에서 사고가 난
       경로가 「화면의 문자열을 대화창에 붙여넣기」였다. 확인용으로 내는 것은
       **붙여 넣어도 안전해야** 한다. 지문은 같은 키인지 대조는 되고 복원은 안 된다.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _assert_env_ignored() -> None:
    """🚨 쓰기 **전에** .gitignore 를 본다. 순서가 뒤집히면 검사가 무의미하다.

    누가 .gitignore 를 정리하다 .env 줄을 지웠는데 이 명령이 그대로 키를 쓰면,
    다음 `git add -A` 가 키를 스테이징한다. 커밋 훅(gitleaks)이 마지막 그물이지
    첫 그물이 아니다.
    """
    text = ""
    with contextlib.suppress(OSError):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {ln.strip() for ln in text.splitlines()}
    if not (IGNORE_FORMS & lines):
        raise SetKeyError(
            "🚨 .gitignore 가 .env 를 덮고 있지 않다 — 키를 쓰면 커밋될 수 있다.\n"
            "  고치기  .gitignore 첫 줄에 `.env` 를 넣고 다시 실행한다"
        )


def _check_name(name: str) -> None:
    if any(name.startswith(p) for p in FORBIDDEN_PREFIX):
        raise SetKeyError(
            f"🚨 {name} 은 .env 에 두지 않는다 (D-78 ③).\n"
            "  이유  AWS 는 제3자 제공 계정이고, 자격증명은 서버의 IAM 역할·시크릿으로\n"
            "        다룬다. 로컬 .env 는 유출 경로가 다르다"
        )
    if name not in env.KEYS:
        known = "\n".join(f"    {k}" for k in env.KEYS)
        raise SetKeyError(
            f"{name} 은 아는 키가 아니다.\n"
            f"  아는 이름 ({len(env.KEYS)}개)\n{known}\n"
            "  🚨 여기서 새 이름을 만들지 않는다 — .env.example 과 collect/env.py 의\n"
            "     KEYS 에 먼저 등재한다. 이름의 출처가 둘이 되면 읽는 곳이 갈린다"
        )


def _clean(name: str, raw: str) -> str:
    """붙여넣기 사고를 걸러 낸다 — 값을 **되비추지 않고**."""
    value = raw.strip()
    # 「FOODSAFETY_KEY=13b6...」 통째로 붙여넣는 경우
    if value.upper().startswith(f"{name}="):
        value = value[len(name) + 1 :].strip()
    # 편집기에서 따온 따옴표
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    if not value:
        raise SetKeyError("빈 값이다 — 아무것도 쓰지 않았다.")
    if "\n" in value or "\r" in value:
        raise SetKeyError("값에 줄바꿈이 있다 — 여러 줄을 붙여 넣은 것 같다.")
    return value


def put(name: str, value: str) -> str:
    """`.env` 의 **그 한 줄만** 바꾼다. 나머지 줄·주석·순서는 건드리지 않는다.

    돌려주는 것은 값이 아니라 지문이다 — 부르는 쪽이 실수로 값을 출력할 수 없게.
    """
    _assert_env_ignored()

    if not ENV_PATH.exists():
        ENV_PATH.write_bytes(EXAMPLE_PATH.read_bytes())

    lines = _read().splitlines()
    pat = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    hits = [i for i, ln in enumerate(lines) if pat.match(ln)]

    # 🚨 중복 줄이 있으면 고쳐 주지 않고 멈춘다. dotenv 는 **뒤에 오는 줄**이 이기는데,
    #    앞줄만 조용히 바꾸면 값을 넣고도 안 들어간 것처럼 보인다 — 가장 찾기 어려운 종류다.
    if len(hits) > 1:
        raise SetKeyError(
            f"🚨 .env 에 {name} 줄이 {len(hits)}개 있다 (줄 {[i + 1 for i in hits]}).\n"
            "  dotenv 는 뒤에 오는 줄이 이긴다 — 앞줄만 바꾸면 넣고도 안 들어간다.\n"
            "  고치기  .env 를 열어 중복 줄을 지우고 다시 실행한다"
        )

    if hits:
        lines[hits[0]] = f"{name}={value}"
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{name}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    # POSIX 에서만 뜻이 있다. Windows 에서는 무해한 무동작이다.
    with contextlib.suppress(OSError):
        os.chmod(ENV_PATH, 0o600)

    return fingerprint(value)


def prompt(name: str) -> str:
    """화면에 뜨지 않게 받는다. 지문을 돌려준다."""
    _check_name(name)
    purpose, where = env.KEYS[name]

    print(f"\n  {name}")
    print(f"    쓰임  {purpose}")
    print(f"    발급  {where}\n")

    raw = getpass.getpass("  값 붙여넣기 (화면에 표시되지 않습니다) > ")
    return put(name, _clean(name, raw))


def status() -> list[tuple[str, str, int]]:
    """어떤 키가 채워졌는지 — **값을 화면에 올리지 않고** 본다.

    🚨 지금까지 확인 수단이 `.env` 를 편집기로 여는 것뿐이었다. 확인하려고 열면
       화면에 뜬다 — 확인 행위 자체가 유출 경로였다. 그 자리를 이 함수가 대신한다.
    """
    out = []
    for name in env.KEYS:
        value = env.get(name, required=False)
        out.append((name, fingerprint(value) if value else "", len(value)))
    return out


def _read() -> str:
    """🚨 `utf-8-sig` 로 읽는다 — Windows 편집기가 붙인 BOM 을 여기서 벗긴다.

    벗기지 않으면 첫 줄 키 이름 앞에 U+FEFF 가 붙어, 값이 있는데 없다고 나온다.
    쓰는 쪽(`put`·`repair`)은 BOM 을 다시 붙이지 않으므로 한 번 고치면 재발하지 않는다.
    """
    return ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""


_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=(.*)$")


def parse(text: str) -> dict[str, str]:
    """값만 뽑는다. 주석·순서는 보지 않는다 — 고칠 때 **잃지 않기 위한** 목록이다."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _ASSIGN.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()  # 뒤에 오는 줄이 이긴다 (dotenv 와 같게)
    return out


def repair() -> list[str]:
    """`.env` 의 주석을 `.env.example` 에서 되살린다 — **값은 그대로 둔다**.

    🚨 손으로 만든 `.env` 에는 발급 안내가 없다. 그런데 `setup` 은 `.env` 가 있으면
       건너뛰므로, 한 번 손으로 만들면 안내가 **영영 안 들어온다**. 팀원은 키를 어디서
       받는지 모른 채 빈 줄만 본다 — 그래서 옆 사람에게 키를 물어보고, 그 순간
       메신저에 키가 남는다. 주석이 뭉개진 것은 미용 문제가 아니라 **유출 경로**다.

    안전장치 둘.
      ① 백업 파일을 **만들지 않는다.** `.env.bak` 에도 키가 그대로 들어 있는데 이름이
         달라 `.gitignore` 를 빠져나간다 — 고치려다 새는 전형적인 경로다.
      ② 대신 쓴 뒤에 **다시 읽어 대조한다.** 값이 하나라도 달라졌으면 원문으로 되돌린다.
    """
    _assert_env_ignored()
    before_bytes = ENV_PATH.read_bytes() if ENV_PATH.exists() else b""
    before = _read()
    values = parse(before)
    example = EXAMPLE_PATH.read_text(encoding="utf-8-sig")

    out: list[str] = []
    placed: set[str] = set()
    for line in example.splitlines():
        m = _ASSIGN.match(line)
        if m and m.group(1) in values:  # 예제의 자리에 내 값을 놓는다
            name = m.group(1)
            out.append(f"{name}={values[name]}")
            placed.add(name)
            continue
        # 예제가 `# OPENAI_API_KEY=` 처럼 주석 처리해 둔 키 — 값이 있으면 주석 아래 살린다
        m2 = _ASSIGN.match(line.lstrip("# ").rstrip())
        if m2 and m2.group(1) in values and m2.group(1) not in placed:
            out.append(line)
            out.append(f"{m2.group(1)}={values[m2.group(1)]}")
            placed.add(m2.group(1))
            continue
        out.append(line)

    # 예제에 자리가 없는 키 — 지우지 않는다. 모르는 것을 버리는 것이 가장 나쁘다.
    orphans = [k for k in values if k not in placed]
    if orphans:
        out += [
            "",
            "# ─────────────────────────────────────────────────────────────",
            "#  🚨 .env.example 에 자리가 없는 키 — 고칠 때 잃지 않으려고 여기 모았다.",
            "#     이름의 단일 출처는 .env.example + collect/env.py 의 KEYS 다.",
            "#     쓰는 키라면 그 둘에 등재하고, 안 쓰는 키라면 이 줄들을 지운다.",
            "# ─────────────────────────────────────────────────────────────",
        ]
        out += [f"{k}={values[k]}" for k in orphans]

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    with contextlib.suppress(OSError):
        os.chmod(ENV_PATH, 0o600)

    # ② 대조 — 값이 하나라도 달라졌으면 되돌린다
    after = parse(_read())
    lost = {k: v for k, v in values.items() if after.get(k) != v}
    if lost:
        ENV_PATH.write_text(before, encoding="utf-8", newline="\n")
        raise SetKeyError(
            f"🚨 값이 보존되지 않아 되돌렸다 — {sorted(lost)}. .env 는 고치기 전 그대로다."
        )

    changed = []
    if before_bytes[:3] == b"\xef\xbb\xbf":
        changed.append("BOM 제거 — dotenv 가 첫 줄 키 이름에 U+FEFF 를 붙이던 것")
    if b"\r\n" in before_bytes:
        changed.append("줄끝 LF 통일")
    if len(out) > len(before.splitlines()):
        changed.append(f"발급 안내 주석 복원 ({len(before.splitlines())} → {len(out)}줄)")
    if orphans:
        changed.append(f"예제에 자리 없는 키 {len(orphans)}개 보존 — {sorted(orphans)}")
    return changed or ["바뀐 것 없음"]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--repair"]:
        try:
            for line in repair():
                print(f"  [OK] {line}")
        except SetKeyError as exc:
            print(f"\n{exc}\n", file=sys.stderr)
            return 1
        print("       🚨 값은 화면에 올리지 않았다. 확인은 `launcher.py keys` 의 지문으로 한다.\n")
        return 0

    if not argv:
        rows = status()
        print("\n  키 현황 — 값은 표시하지 않는다. 지문만 대조한다.\n")
        width = max(len(n) for n, _, _ in rows)
        for name, fp, size in rows:
            mark = "채움" if fp else "  — "
            tail = f"{size:>3}자 · 지문 {fp}" if fp else "비어 있음"
            print(f"    {mark}  {name.ljust(width)}   {tail}")
        print("\n  채우기  uv run python launcher.py setkey <이름>\n")
        return 0

    # 🚨 값을 인자로 받지 않는다. 받는 순간 셸 기록에 남고 이 모듈의 존재 이유가 사라진다.
    if len(argv) > 1:
        print(
            "🚨 값을 인자로 주지 않는다 — PowerShell 기록 파일에 그대로 남는다.\n"
            "   이름만 주면 화면에 뜨지 않게 물어본다:\n"
            f"     uv run python launcher.py setkey {argv[0]}",
            file=sys.stderr,
        )
        return 2

    try:
        fp = prompt(argv[0])
    except SetKeyError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\n  취소했다 — .env 는 그대로다.\n", file=sys.stderr)
        return 130

    print(f"\n  [OK] .env 에 넣었다 — 지문 {fp}")
    print("       🚨 지문은 붙여 넣어도 안전하다. 값 자체는 어디에도 옮기지 않는다.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
