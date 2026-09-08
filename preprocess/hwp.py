"""preprocess/hwp.py — HWP 5.x 본문에서 **표를 셀 구조 그대로** 읽는다 (D-150).

  uv run python -m preprocess.hwp <파일.hwp> --probe        # 구조만 본다
  uv run python -m preprocess.hwp <파일.hwp> --table 3      # 표 하나를 찍어 본다

★ **왜 직접 읽는가 — 값이 표에 있기 때문이다.**

  `mfds_special_use_guide`(특수용도식품 표시·광고 해설서)의 값은 본문이 아니라 **표**다 —
  10개 제품유형 × 4블록(삭제 문구 / 수정 문구 / 근거자료 제출 문구 / 삭제 이미지).
  🚨 사이트의 뷰어 변환본(`convertDocViewer.do` xhtml)은 텍스트는 주지만
     **셀이 줄로 흩어져 「유형 │ 내용」 대응이 무너진다**(D-138 실측). 그러면 라벨이 안 선다.
  hwp5txt 류의 「텍스트만 뽑기」도 같은 이유로 못 쓴다.

──────────────────────────────────────────────────────────────
🚨 **읽기 전용이다.** 원본을 고치지 않고, 여기서 저장도 하지 않는다 (규약 2).

🚨 **셀 주소는 LIST_HEADER 의 offset 8 이다** (2026-09-08 실물 확인).
   6·8·10 을 다 찍어 보고 골랐다 — 6 은 「열=256」, 10 은 「행병합=42247」이 나온다.
   문서만 보고 6 을 골랐으면 **조용히 틀린 표**가 나왔을 것이다.

🔴 **두 가지를 대조한다 — 구조와 글자.**

   ① **구조** — `HWPTAG_TABLE` 이 행 수·열 수·행별 셀 수를 들고 있다 (아래).
   ② **글자** — hwp 는 저작 도구가 만든 평문 미리보기 `PrvText` 스트림을 들고 있다.
      **우리가 만들지 않은 독립 렌더링**이라, 우리 추출과 맞대면 제어문자 규칙이 맞는지 알 수 있다.
      `--verify` 가 그것을 한다. 실측(해설서) — **17/17 일치**.
      🚨 `PrvText` 는 **표 경계에 `<` `>` 를 넣는다.** 그건 미리보기의 표기이지 문서의 글자가 아니라
         빼고 맞댄다. 안 빼면 4건이 어긋나 보이는데 **전부 그 자리**다.

🔴 **표의 선언과 실제를 대조한다.** `HWPTAG_TABLE` 이 행 수·열 수·**행별 셀 수**를 들고 있다.
   우리가 모은 셀이 그것과 다르면 **멈춘다.** 파싱이 어긋난 채로 라벨을 만들면
   그 오류는 데이터에 박혀 되돌릴 수 없다 — 조용한 실패의 자리다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field

import olefile

#: BodyText 레코드 태그 (HWPTAG_BEGIN = 0x10).
PARA_HEADER, PARA_TEXT, CTRL_HEADER, LIST_HEADER, TABLE = 66, 67, 71, 72, 77

#: 🚨 PARA_TEXT 의 제어문자. **8 wchar(16바이트)를 먹는 것**과 1 wchar 인 것이 갈린다.
#:    이걸 틀리면 뒤 글자가 통째로 밀려 **읽히기는 하는데 내용이 어긋난다.**
_INLINE = frozenset({4, 5, 6, 7, 8, 9, 19, 20})
_EXTENDED = frozenset({1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23})


@dataclass
class Cell:
    row: int
    col: int
    rowspan: int
    colspan: int
    paras: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(p for p in self.paras if p.strip())


@dataclass
class Table:
    rows: int
    cols: int
    row_cells: tuple[int, ...]  # 행별 셀 수 — 원천이 선언한 값
    cells: list[Cell] = field(default_factory=list)

    def check(self) -> str:
        """선언과 실제가 맞는가. 🚨 어긋나면 사유를, 맞으면 빈 문자열을."""
        got = tuple(sum(1 for c in self.cells if c.row == r) for r in range(self.rows))
        if got != self.row_cells:
            return f"행별 셀 수가 선언과 다르다 — 선언 {self.row_cells} · 실제 {got}"
        return ""

    def grid(self) -> list[list[str]]:
        """행 × 열 텍스트. 🚨 병합은 펴지 않는다 — 원본 구조를 바꾸지 않는다."""
        g = [[""] * self.cols for _ in range(self.rows)]
        for c in self.cells:
            if c.row < self.rows and c.col < self.cols:
                g[c.row][c.col] = c.text
        return g


def sections(path: pathlib.Path) -> list[bytes]:
    """BodyText 섹션들. 🚨 압축 여부는 FileHeader 의 flags bit 0 이 정한다."""
    ole = olefile.OleFileIO(str(path))
    head = ole.openstream("FileHeader").read()
    if head[:17] != b"HWP Document File":
        raise ValueError(f"HWP 5.x 가 아니다 — 서명 {head[:17]!r}")
    (flags,) = struct.unpack("<I", head[36:40])
    if flags & 2:
        raise ValueError("암호가 걸린 문서다 — 여기서 풀지 않는다")
    names = sorted("/".join(s) for s in ole.listdir() if s and s[0] == "BodyText")
    out = []
    for n in names:
        raw = ole.openstream(n).read()
        out.append(zlib.decompress(raw, -15) if flags & 1 else raw)
    return out


def records(buf: bytes) -> Iterator[tuple[int, int, bytes]]:
    """(태그, 수준, 자료). 🚨 크기가 0xFFF 면 **다음 4바이트가 진짜 크기**다."""
    i = 0
    while i + 4 <= len(buf):
        (h,) = struct.unpack_from("<I", buf, i)
        i += 4
        tag, lvl, size = h & 0x3FF, (h >> 10) & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            (size,) = struct.unpack_from("<I", buf, i)
            i += 4
        yield tag, lvl, buf[i : i + size]
        i += size


def para_text(data: bytes) -> str:
    """PARA_TEXT 를 글자로. 🚨 제어문자가 먹는 길이를 지켜야 뒤 글자가 안 밀린다."""
    out: list[str] = []
    n = len(data) // 2
    i = 0
    while i < n:
        (ch,) = struct.unpack_from("<H", data, i * 2)
        if ch in _INLINE or ch in _EXTENDED:
            out.append("\t" if ch == 9 else "")
            i += 8
            continue
        if ch in (10, 13):
            out.append("\n")
        elif ch >= 32:
            out.append(chr(ch))
        i += 1
    return "".join(out)


def tables_with_lead(path: pathlib.Path, lead: int = 6) -> list[tuple[Table, list[str]]]:
    """표와 **그 앞의 본문 문단들**. 🚨 셀 안의 문단은 LIST_HEADER 와 **같은 수준**에 온다.

    ★ 앞 문단이 표의 **정체**를 말한다 — 해설서는 표 바로 위에
      「심의시 '삭제'판정을 받은 문구」처럼 블록 이름을 본문으로 적는다.
      표만 보면 「부당한 표시ㆍ광고 유형 │ 내용」이 여러 블록에 똑같이 나와 구분이 안 된다.
    """
    found: list[tuple[Table, list[str]]] = []
    for buf in sections(path):
        cur: Table | None = None
        base = -1
        cell: Cell | None = None
        recent: list[str] = []
        lead_of: list[str] = []
        for tag, lvl, data in records(buf):
            if cur is None and tag == PARA_TEXT and lvl <= 1:
                t = " ".join(para_text(data).split())
                if t:
                    recent.append(t)
                    del recent[:-lead]
            if cur is not None and lvl <= base:
                found.append((cur, lead_of))
                cur, cell = None, None
            if tag == CTRL_HEADER and len(data) >= 4 and data[3::-1] == b"tbl ":
                base = lvl
                cur = Table(0, 0, ())
                cell = None
                lead_of = list(recent)
            elif cur is not None and tag == TABLE:
                _, rows, cols = struct.unpack_from("<IHH", data, 0)
                cur.rows, cur.cols = rows, cols
                # 속성4 + 행수2 + 열수2 + 셀간격2 + 안쪽여백 4×2 = 18
                cur.row_cells = struct.unpack_from(f"<{rows}H", data, 18)
            elif cur is not None and tag == LIST_HEADER and len(data) >= 16:
                col, row, colspan, rowspan = struct.unpack_from("<HHHH", data, 8)
                cell = Cell(row=row, col=col, rowspan=rowspan, colspan=colspan)
                cur.cells.append(cell)
            elif cur is not None and cell is not None and tag == PARA_TEXT:
                cell.paras.append(para_text(data))
        if cur is not None:
            found.append((cur, lead_of))
    return found


def tables(path: pathlib.Path) -> list[Table]:
    """문서의 모든 표."""
    return [t for t, _ in tables_with_lead(path)]


def verify(path: pathlib.Path) -> int:
    """🔴 **우리가 만들지 않은 렌더링과 맞댄다.**

    hwp 는 저작 도구가 만든 평문 미리보기(`PrvText`)를 들고 있다. 표 구조는 `Table.check()` 가
    원천의 선언과 대조하지만 **셀 안의 글자**는 그것으로 검증되지 않는다 —
    제어문자가 먹는 길이(8 wchar)를 틀리면 **읽히기는 하는데 내용이 밀린다.**
    미리보기와 맞대면 그 실패가 드러난다.

    🚨 `PrvText` 는 표 경계에 `<` `>` 를 넣는다 — 미리보기의 표기이지 문서의 글자가 아니다.
    """
    import re  # noqa: PLC0415

    ole = olefile.OleFileIO(str(path))
    if "PrvText" not in {"/".join(x) for x in ole.listdir()}:
        print("🚨 PrvText 가 없다 — 이 검사를 할 수 없다. 못 하는 것을 못 한다고 적는다")
        return 1
    prv = ole.openstream("PrvText").read().decode("utf-16-le", errors="replace")
    body = "".join(
        para_text(d) for buf in sections(path) for tag, _, d in records(buf) if tag == PARA_TEXT
    )
    sq = re.compile(r"\s+")
    b = sq.sub("", body)
    pv = sq.sub("", prv).replace("<", "").replace(">", "")
    frags = [pv[i : i + 30] for i in range(0, max(len(pv) - 30, 1), 40)]
    miss = [f for f in frags if f and f not in b]
    print(f"미리보기 {len(pv):,}자 · 본문 {len(b):,}자 (공백 제거)")
    print(f"  조각 {len(frags)}개 중 본문에 그대로 있는 것 **{len(frags) - len(miss)}**")
    if miss:
        print(f"  🔴 어긋난 조각 {len(miss)}개 — **제어문자 규칙을 의심한다**")
        for f in miss[:5]:
            k = next((j for j in range(1, len(f) + 1) if f[:j] not in b), len(f) + 1) - 1
            print(f"     맞는 데까지: {f[:k]!r}  →  다음: {f[k : k + 6]!r}")
        return 1
    print("★ 전부 일치한다 — 제어문자가 먹는 길이가 맞다")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="HWP 5.x 표 읽기 (읽기 전용)")
    ap.add_argument("path")
    ap.add_argument("--probe", action="store_true", help="표 목록과 검증 결과만")
    ap.add_argument("--table", type=int, default=None, help="표 하나를 찍는다 (0부터)")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="🔴 저작 도구의 미리보기(PrvText)와 글자를 맞댄다 — 제어문자 규칙 검증",
    )
    a = ap.parse_args()

    p = pathlib.Path(a.path)
    if not p.exists():
        print(f"🚨 {p} 가 없다", file=sys.stderr)
        return 1
    if a.verify:
        return verify(p)
    ts = tables(p)
    bad = [(i, t.check()) for i, t in enumerate(ts) if t.check()]
    print(f"표 {len(ts)}개 · 셀 {sum(len(t.cells) for t in ts):,}개")
    if bad:
        print(f"🔴 선언과 어긋난 표 {len(bad)}개 — **파싱이 틀렸다는 뜻이다**")
        for i, why in bad[:5]:
            print(f"   표 {i}: {why}")
        return 1
    print("★ 모든 표가 원천의 선언(행 수 · 행별 셀 수)과 일치한다")

    if a.table is not None:
        t = ts[a.table]
        print(f"\n── 표 {a.table} · {t.rows}행 × {t.cols}열")
        for r, line in enumerate(t.grid()):
            cells = " │ ".join((c or "").replace("\n", " ⏎ ")[:38] for c in line)
            print(f"  {r:>3} │ {cells}")
    elif a.probe:
        print("\n  크기별 상위 10 —")
        for i, t in sorted(enumerate(ts), key=lambda x: -len(x[1].cells))[:10]:
            head = (t.grid()[0][0] if t.rows else "")[:44].replace("\n", " ")
            print(f"   표 {i:>3}  {t.rows:>3}행 × {t.cols:>2}열  첫 셀: {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
