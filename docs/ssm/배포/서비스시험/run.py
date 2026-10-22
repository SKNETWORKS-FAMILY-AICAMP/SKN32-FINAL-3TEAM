#!/usr/bin/env python3
"""run.py — CopyLane 서비스 시험 한 번에 (2026-10-22 · 소성민).

명령 하나로 시험 전체를 돌리고 로그 · CSV · 결과보고서를 남긴다. 화면 캡처는 하지 않는다.

쓰는 법 (내 PC · 저장소 루트에서)
    uv run python docs/ssm/배포/서비스시험/run.py                       # 기본 — https://copylane.site
    uv run python docs/ssm/배포/서비스시험/run.py --with-llm            # 고쳐 쓰기(sLLM)까지
    uv run python docs/ssm/배포/서비스시험/run.py --no-login            # 계정 없이 (로그인 시험은 건너뜀)
    uv run python docs/ssm/배포/서비스시험/run.py --base http://127.0.0.1:8000   # 로컬 서버로
    uv run python docs/ssm/배포/서비스시험/run.py --only 검수            # 파일 이름 · 시험 이름 일부로 골라 돌리기

시험 계정
    실행하면 이메일 · 비밀번호를 묻는다(비밀번호는 화면에 안 보인다). 묻지 않게 하려면 같은 폴더에
    `svc.env` 를 만든다(틀: `svc.env.example` · git 에 안 올라간다). 환경변수 CL_TEST_EMAIL · CL_TEST_PASSWORD 도 된다.

결과
    docs/ssm/배포/서비스시험/결과/<MMDD_HHMM>/
        서비스시험_로그.log · 서비스시험_결과.csv · 서비스시험_원자료.json · 서비스시험_보고서.md

종료 코드 — 0: 실패 없음 · 1: 실패 있음 · 그 밖: 실행 자체가 안 됨
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def load_env_file(path: pathlib.Path) -> None:
    """`KEY=VALUE` 줄만 읽는다. 이미 있는 환경변수는 덮지 않는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser(description="CopyLane 서비스 시험 — 실행 · 로그 · 보고서")
    ap.add_argument("--base", default=None, help="시험할 주소 (기본 https://copylane.site)")
    ap.add_argument("--with-llm", action="store_true", help="지적 문장 고쳐 쓰기(sLLM)까지 시험한다 (수십 초 더 걸림)")
    ap.add_argument("--admin-open", action="store_true", help="관리자 허용 IP 에서 실행 — 관리자 화면 접근을 시험한다")
    ap.add_argument("--no-login", action="store_true", help="계정을 묻지 않는다 — 로그인 시험은 건너뛴다")
    ap.add_argument("--only", default="", help="이 글자가 들어간 시험만 (pytest -k)")
    ap.add_argument("--timeout", type=float, default=180, help="요청 하나 대기 상한(초) · 기본 180")
    ap.add_argument("--out", default=None, help="결과 폴더 (기본 서비스시험/결과/<MMDD_HHMM>)")
    args = ap.parse_args()

    try:
        import pytest
        import requests  # noqa: F401
    except ImportError as e:
        print(f"[멈춤] {e.name} 가 없다. 저장소 루트에서 `uv sync` 뒤 `uv run python …` 으로 실행한다.")
        print("       (uv 를 안 쓰면: pip install pytest requests)")
        return 3

    load_env_file(HERE / "svc.env")

    base = (args.base or os.environ.get("SVC_BASE") or "https://copylane.site").rstrip("/")
    os.environ["SVC_BASE"] = base
    os.environ["SVC_TIMEOUT"] = str(args.timeout)
    os.environ["SVC_WITH_LLM"] = "1" if args.with_llm else "0"
    os.environ["SVC_ADMIN_OPEN"] = "1" if args.admin_open else "0"
    out = pathlib.Path(args.out) if args.out else HERE / "결과" / dt.datetime.now().strftime("%m%d_%H%M")
    os.environ["SVC_OUT"] = str(out)

    print("=" * 70)
    print(" CopyLane 서비스 시험")
    print(f"   대상    : {base}")
    print(f"   고쳐 쓰기: {'포함' if args.with_llm else '제외 (--with-llm)'}")
    print(f"   결과    : {out}")
    print("=" * 70)

    if args.no_login:
        os.environ["CL_TEST_EMAIL"] = ""
        os.environ["CL_TEST_PASSWORD"] = ""
    elif not (os.environ.get("CL_TEST_EMAIL") and os.environ.get("CL_TEST_PASSWORD")):
        if sys.stdin.isatty():
            print(" 시험 계정(일반 회원)을 넣는다. 비우고 Enter 면 로그인 시험은 건너뛴다.")
            email = input("   이메일: ").strip()
            pw = getpass.getpass("   비밀번호(안 보임): ") if email else ""
            os.environ["CL_TEST_EMAIL"] = email
            os.environ["CL_TEST_PASSWORD"] = pw
        else:
            print(" 시험 계정이 없다 — 로그인 시험은 건너뛴다.")
    if args.admin_open and not (os.environ.get("CL_ADMIN_EMAIL") and os.environ.get("CL_ADMIN_PASSWORD")):
        if sys.stdin.isatty():
            email = input("   관리자 아이디(예: abc@admin.copylane · 비우면 건너뜀): ").strip()
            pw = getpass.getpass("   관리자 비밀번호(안 보임): ") if email else ""
            os.environ["CL_ADMIN_EMAIL"] = email
            os.environ["CL_ADMIN_PASSWORD"] = pw
    print()

    pytest_args = ["-c", str(HERE / "pytest.ini"), "--rootdir", str(HERE), str(HERE)]
    if args.only:
        pytest_args += ["-k", args.only]
    code = pytest.main(pytest_args)
    return 0 if code == 0 else (1 if code == 1 else int(code))


if __name__ == "__main__":
    sys.exit(main())
