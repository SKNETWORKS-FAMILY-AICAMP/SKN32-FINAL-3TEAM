"""preprocess/pdf_lines.py — PDF 문단의 **줄넘김을 되살린다** (2026-10-03).

한글 PDF 는 칸 너비에서 글자 단위로 줄을 바꾼다 — 「화장\\n품」 · 「거칠\\n어진」처럼 낱말 한가운데서도 넘는다.
줄을 빈칸으로 이으면 「화장 품」이 되고, 그 글에서 뜬 인용 문구도 깨진다.

★ **문단 글(양쪽 맞춤)에서는 글자 좌표로 가를 수 있다** `[측정]` 2026-10-03 · 클론 B 원문 · 작업공간
  · 줄이 **빈칸에서** 넘으면 PDF 에 그 빈칸 글자가 줄 끝에 남는다. 낱말 안에서 넘으면 없다.
  · 빈칸 글자가 없어도 **짧은 줄**(오른쪽 끝에 못 미친 줄)은 문단의 끝이다 — 붙이지 않는다.
  · 대조 — 문서 안에서 「붙여 쓴 꼴만 나오는 쌍」 · 「띄어 쓴 꼴만 나오는 쌍」을 정답으로 삼아 쟀다:
      2020 질문집  1,152 쌍 중 어긋남 17 (1.5%) · 2012 질의응답집  742 쌍 중 어긋남 10 (1.3%)
    어긋난 것의 다수는 원문이 두 꼴을 섞어 쓴 자리다(「표시·/기재」).
  🚨 **표 칸에는 안 통한다** — 「화장품 표시·광고 관리 지침」의 표는 줄 끝 빈칸 글자가 없다(양쪽 다 칸 끝에서 끝난다).
     그 문서는 줄넘김을 읽고 적은 표(`mfds_cosmetic_guideline.JOINS`)로 잇는다. 여기 규칙을 표에 쓰지 않는다.

★ 규칙 — 줄 끝에서 다음 줄과 **붙이는** 조건(`Line.glue`)
  ① 줄 끝에 빈칸 글자가 없다  ② 줄이 쪽의 오른쪽 끝에 닿았다(`_REACH` 글자 너비 안)
  ③ 문장 부호(. ? ! , ; :)로 끝나지 않는다  ④ 문서 안에서 띄어 쓴 꼴만 나오는 쌍이 아니다(`_veto`)
  그리고 이을 때 — 다음 줄이 새 항목의 머리(글머리표 · 「가.」 · 「1.」 · 「(예」)면 붙이지 않는다(`join`).
  그 밖은 전부 빈칸이다 — **모르면 띄운다**(빈칸으로 잇던 종전 동작과 같다).
  🚨 남는 틀림 — 줄 끝 빈칸 글자가 빠졌는데 문서 안에 같은 쌍이 또 없는 자리(「다른/제조업체에」).
     붙인 자리 가운데 문서 안에서 확인 안 되는 것 279(2020) 을 읽어 보니 틀린 것은 1~2% 다. 문구는 판독에서 원문과 대조한다.
"""

from __future__ import annotations

import collections
import pathlib
import re

#: 줄이 오른쪽 끝에 닿았다고 보는 거리 — 글자 크기의 배수. 두 바이트 글자 하나가 못 들어가 넘은 줄은
#: 끝에서 한 글자 너비 안쪽에서 끝난다 `[측정]` 2026-10-03 (1.0 ~ 2.0 사이에서 대조 결과가 같다)
_REACH = 1.4
_SENTENCE_END = (".", "?", "!", ",", ";", ":")
#: 새 항목의 머리 — 글머리표 · 목록 번호 · 「(예」. 이런 줄은 앞 줄에 붙이지 않는다
_ITEM_HEAD = re.compile(r"^(?:[¡\-·․*※○□●•☞▶]|(?:[가-하]|\d{1,2})\.(?:\s|$)|\(예)")
_EDGE = re.compile(r"^[\W_]+|[\W_]+$")


class Line(str):
    """줄 하나 — `glue` 가 참이면 다음 줄과 빈칸 없이 붙는다."""

    __slots__ = ("glue",)
    glue: bool

    def __new__(cls, text: str, glue: bool = False) -> Line:
        obj = super().__new__(cls, text)
        obj.glue = glue
        return obj


def as_lines(page: str | list[str]) -> list[Line]:
    """쪽 → 줄 목록. 🚨 글(str)로 받으면 좌표가 없다 — 전부 빈칸으로 잇는다(합성 글 · 테스트)."""
    if isinstance(page, str):
        return [Line(s) for s in (" ".join(x.split()) for x in page.split("\n")) if s]
    return [s if isinstance(s, Line) else Line(s) for s in page if s]


def join(lines: list[str], clean=None) -> str:
    """줄을 잇는다 — `glue` 인 줄은 붙이고 그 밖은 빈칸. `clean` 은 줄마다 먼저 거는 손질(글머리표 떼기 따위)."""
    out = ""
    glue = False
    for s in lines:
        text = " ".join((clean(s) if clean else str(s)).split())
        if not text:
            continue
        if out and not (glue and not _ITEM_HEAD.match(s)):
            out += " "
        out += text
        glue = bool(getattr(s, "glue", False))
    return out


def _edge(w: str) -> str:
    return _EDGE.sub("", w)


def _page_lines(pg) -> list[dict]:
    """pdfplumber 쪽 → `[{text, sp(줄 끝 빈칸 글자), x1, size}, …]`."""
    spaces = [c for c in pg.chars if not c["text"].strip()]
    out: list[dict] = []
    for ln in pg.extract_text_lines(return_chars=True):
        chars = [c for c in ln["chars"] if c["text"].strip()]
        text = " ".join(ln["text"].split())
        if not chars or not text:
            continue
        last = max(chars, key=lambda c: c["x1"])
        mid = (last["top"] + last["bottom"]) / 2
        sp = any(s["x0"] >= last["x1"] - 0.5 and s["top"] <= mid <= s["bottom"] for s in spaces)  # noqa: PLR2004
        size = collections.Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
        out.append({"text": text, "sp": sp, "x1": last["x1"], "size": size})
    return out


def _veto(doc: list[list[dict]]) -> set[tuple[str, str]]:
    """문서 안에서 **띄어 쓴 꼴만** 나오는 (앞 토막, 뒤 토막) — 줄 끝 빈칸 글자가 빠진 자리를 잡는다.

    줄 안쪽의 토막만 센다 — 줄의 첫 · 끝 토막은 잘린 것일 수 있다.
    """
    inner: collections.Counter = collections.Counter()
    pairs: collections.Counter = collections.Counter()
    for pg in doc:
        for ln in pg:
            t = ln["text"].split()
            inner.update(_edge(w) for w in t[1:-1])
            pairs.update((_edge(a), _edge(b)) for a, b in zip(t, t[1:], strict=False))
    return {p for p in pairs if not inner[p[0] + p[1]]}


def document(path: pathlib.Path) -> tuple[list[list[Line]], dict]:
    """PDF → (쪽별 줄 목록, 계측 `{줄넘김, 붙임, 띄움_빈칸, 띄움_짧은줄, 띄움_부호, 띄움_쌍}`)."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError("pdfplumber 가 없다 — 고치는 법:  uv sync") from e

    with pdfplumber.open(path) as d:
        doc = [_page_lines(pg) for pg in d.pages]
    veto = _veto(doc)
    stat: collections.Counter = collections.Counter()
    out: list[list[Line]] = []
    for pg in doc:
        right = max((ln["x1"] for ln in pg), default=0.0)
        lines: list[Line] = []
        for i, ln in enumerate(pg):
            nxt = pg[i + 1]["text"] if i + 1 < len(pg) else None
            why = _why_space(ln, nxt, right, veto)
            if nxt is not None:
                stat["줄넘김"] += 1
                stat[why or "붙임"] += 1
            lines.append(Line(ln["text"], glue=nxt is not None and why is None))
        out.append(lines)
    return out, dict(stat)


def _why_space(ln: dict, nxt: str | None, right: float, veto: set[tuple[str, str]]) -> str | None:
    """이 줄 뒤가 빈칸인 까닭 — 없으면(None) 붙인다."""
    if nxt is None:
        return "쪽_끝"
    if ln["sp"]:
        return "띄움_빈칸"
    if ln["x1"] < right - _REACH * ln["size"]:
        return "띄움_짧은줄"
    if ln["text"].endswith(_SENTENCE_END):
        return "띄움_부호"
    if (_edge(ln["text"].split()[-1]), _edge(nxt.split()[0])) in veto:
        return "띄움_쌍"
    return None
