#!/usr/bin/env python3
"""build_matrix.py — 판정 매트릭스 빌드 (D-90).

  python scripts/build_matrix.py            # 두 산출물을 다시 만든다
  python scripts/build_matrix.py --check    # 어긋났는지만 본다 (쓰지 않는다)

입력 (손으로 고치는 것)
    docs/03_데이터/_matrix/data.js      판정 73건 — 등급·제약·비용·가치·용도·근거
    docs/03_데이터/_matrix/shell.html   화면 골격

출력 (생성물 — 직접 고치지 않는다)
    docs/03_데이터/판정매트릭스.html      사람이 보는 한눈보기
    docs/03_데이터/_matrix/sources.json  scripts/gen_registry.py 의 입력

🚨 왜 스크립트인가 — 이 자리만 「README 의 명령을 복사해 붙이는」 방식이었다.
   레지스트리·근거·검토표는 전부 스크립트인데 여기만 손이었고, 실제로 두 가지가 났다.
     ① sources.json 만 갱신하고 HTML 을 안 만들어 둘이 갈리는 상태
     ② JSON.stringify 가 개행으로 끝나지 않아 커밋마다 end-of-file-fixer 훅이 걸림
   D-90 이 「손으로 양쪽을 고치면 반드시 갈린다」고 한 그 자리다.

🚨 node 를 쓰지 않는다 — 5인 전원 윈도우이고 환경 동일성은 파이썬 3.11.9 하나로
   못 박혀 있다 (D-87). 매트릭스를 다시 만들려고 node 를 깔게 만들지 않는다.
   대신 data.js 의 객체 리터럴을 여기서 직접 읽는다 (아래 _JsLiteral).

이어서 반드시:
    python scripts/gen_registry.py && uv run pytest -m gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs/03_데이터/_matrix"
DATA_JS = MATRIX / "data.js"
SHELL = MATRIX / "shell.html"
OUT_JSON = MATRIX / "sources.json"
OUT_HTML = ROOT / "docs/03_데이터/판정매트릭스.html"

PLACEHOLDER = "/*__DATA__*/"

# data.js 상단의 상수. 값이 바뀌면 여기도 바꾼다 (data.js 5행과 한 쌍이다).
CONSTANTS = {"OK": "ok", "CD": "cond", "NO": "no", "UN": "unknown"}


class _JsLiteral:
    """data.js 의 `const SOURCES = [...]` 를 읽는 최소 파서.

    JS 전체를 해석하지 않는다 — 이 파일이 실제로 쓰는 형태만 받는다:
      객체 `{key: value}` (키는 따옴표 없음) · 배열 · 작은/큰따옴표 문자열 ·
      true/false/null · 위 CONSTANTS 의 식별자 · `//` 줄 주석.
    그 밖의 문법을 만나면 **조용히 넘기지 않고 위치를 찍어 실패한다** —
    판정 데이터가 소리 없이 빠지는 것이 가장 나쁘다.
    """

    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0

    # ── 위치 유틸
    def _fail(self, msg: str):
        line = self.s.count("\n", 0, self.i) + 1
        col = self.i - (self.s.rfind("\n", 0, self.i) + 1)
        near = self.s[self.i : self.i + 40].replace("\n", "\\n")
        return SyntaxError(f"data.js {line}행 {col}열: {msg} — 근처 {near!r}")

    def _skip(self) -> None:
        """공백과 `//` 줄 주석을 건너뛴다."""
        while self.i < len(self.s):
            c = self.s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif self.s.startswith("//", self.i):
                nl = self.s.find("\n", self.i)
                self.i = len(self.s) if nl == -1 else nl + 1
            else:
                return

    # ── 값
    def value(self):
        self._skip()
        if self.i >= len(self.s):
            raise self._fail("값이 있어야 하는 자리에서 파일이 끝났다")
        c = self.s[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "'\"":
            return self.string()
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if self.s.startswith(lit, self.i):
                self.i += len(lit)
                return val
        for name, val in CONSTANTS.items():
            if self.s.startswith(name, self.i) and not self.s[self.i + len(name)].isalnum():
                self.i += len(name)
                return val
        raise self._fail("모르는 값 형태다 (문자열·객체·배열·true/false/null·상수만 쓴다)")

    def string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        out: list[str] = []
        while True:
            if self.i >= len(self.s):
                raise self._fail("문자열이 닫히지 않았다")
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                self.i += 2
            elif c == quote:
                self.i += 1
                return "".join(out)
            else:
                out.append(c)
                self.i += 1

    def key(self) -> str:
        self._skip()
        if self.s[self.i] in "'\"":
            return self.string()
        start = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "_$"):
            self.i += 1
        if start == self.i:
            raise self._fail("키가 없다")
        return self.s[start : self.i]

    def obj(self) -> dict:
        self.i += 1  # {
        out: dict = {}
        while True:
            self._skip()
            if self.s[self.i] == "}":
                self.i += 1
                return out
            k = self.key()
            self._skip()
            if self.s[self.i] != ":":
                raise self._fail(f"키 {k!r} 뒤에 ':' 가 없다")
            self.i += 1
            out[k] = self.value()
            self._skip()
            if self.s[self.i] == ",":
                self.i += 1

    def arr(self) -> list:
        self.i += 1  # [
        out: list = []
        while True:
            self._skip()
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.value())
            self._skip()
            if self.s[self.i] == ",":
                self.i += 1


def read_sources(text: str) -> list[dict]:
    marker = "const SOURCES"
    at = text.find(marker)
    if at == -1:
        raise SystemExit("data.js 에 `const SOURCES` 가 없다")
    at = text.index("[", at)
    p = _JsLiteral(text)
    p.i = at
    rows = p.arr()
    if not rows:
        raise SystemExit("SOURCES 가 비어 있다 — 파싱이 잘못됐다")
    ids = [r.get("id") for r in rows]
    if not all(ids):
        raise SystemExit(
            f"id 가 없는 엔트리가 있다: {[i for i, r in enumerate(rows) if not r.get('id')]}"
        )
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"🚨 id 가 중복된다: {sorted(dup)}")
    return rows


def render(rows: list[dict], data_js: str, shell: str) -> tuple[str, str]:
    # 🚨 끝 개행 — 없으면 커밋마다 end-of-file-fixer 훅이 파일을 고치고 커밋이 멈춘다.
    js = json.dumps(rows, ensure_ascii=False, indent=1) + "\n"
    if PLACEHOLDER not in shell:
        raise SystemExit(f"shell.html 에 {PLACEHOLDER} 자리표시자가 없다")
    html = shell.replace(PLACEHOLDER, data_js)
    return js, html


def main() -> int:
    ap = argparse.ArgumentParser(description="판정 매트릭스 빌드 (D-90)")
    ap.add_argument(
        "--check", action="store_true", help="쓰지 않고 어긋났는지만 본다 (어긋나면 종료코드 1)"
    )
    args = ap.parse_args()

    data_js = DATA_JS.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    try:
        rows = read_sources(data_js)
    except SyntaxError as e:
        # 파싱 실패는 사용자 오타이지 버그가 아니다 — 스택 대신 위치를 준다.
        print(f"🚨 {e}", file=sys.stderr)
        return 1
    js, html = render(rows, data_js, shell)

    targets = [(OUT_JSON, js), (OUT_HTML, html)]

    if args.check:
        stale = [
            p for p, want in targets if not p.exists() or p.read_text(encoding="utf-8") != want
        ]
        if stale:
            print("🚨 매트릭스 산출물이 원본과 어긋난다:")
            for p in stale:
                print("   ", p.relative_to(ROOT))
            print("   → python scripts/build_matrix.py")
            return 1
        print(f"매트릭스 최신 — 판정 {len(rows)}건")
        return 0

    for p, want in targets:
        p.write_text(want, encoding="utf-8")
    print(f"판정 {len(rows)}건 →")
    for p, _ in targets:
        print(f"   {p.relative_to(ROOT)}")
    print("🚨 이어서: python scripts/gen_registry.py && uv run pytest -m gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
