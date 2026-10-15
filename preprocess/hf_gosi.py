"""preprocess/hf_gosi.py — 건강기능식품 **고시형** 기능성 문구 (「건강기능식품의 기준 및 규격」 · 2026-10-14 ksr).

  uv run python -m preprocess.hf_gosi --verify     # 세기만 한다
  uv run python -m preprocess.hf_gosi --dump       # → data/derived/hf_gosi_claims.jsonl

★ 왜 — 카피 생성의 인정 문구(`fixed`)를 공식 문구와 대조하려면 고시형 원료의 문구가 있어야 한다.
  개별인정형은 I-0050 · 게시판(`hf_api_labels` · `mfds_hf_labels`)에 있지만 **고시형은 없었다** —
  게시판의 「기능성 원료」 · 「영양성분」 글은 본문 없이 소비자 리포트 PDF 만 붙어 있고, 그 PDF 는
  「판매 목적의 표시·광고에 사용할 수 없음」이라 쓰지 않는다(레지스트리 `mfds_hf_ingredient_board`).
★ 원천 — 법제처 API 가 준 고시 응답(`admrul_34650_*.xml`)의 `첨부파일링크` 「고시전문」 ZIP.
  본문 XML 에는 조문만 있고 원료별 기준은 이 첨부(HWPX)에 있다. 고시라 저작권법 제7조 자유이용(`law_go_kr`).
  원본은 `collect.ingest register law_go_kr` 로 `data/raw/law/admrul_34650_<날짜>_attach.zip` 에 둔다.

🚨 HWPX 는 ZIP 안의 XML 이다 — 표준 라이브러리로 읽는다. 압축은 **메모리에서만** 푼다(디스크 경로로 풀지 않는다).
🚨 글자는 `<hp:t>` 의 `itertext()` 로 모은다 — `.text` 만 읽으면 안에 낀 태그 뒤 글자가 빠져 표 칸이 비었다(실측).
★ 행 단위는 **원료 × 문구 하나**다. 「면역력 증진･피로개선…에 도움을 줄 수 있음」은 문구 여럿을 한 줄에 묶은
  고시 표기라 「…에 도움을 줄 수 있음」 꼴만 가운뎃점으로 나눈다. 「산화･환원 효소의 활성에 필요」처럼
  가운뎃점이 낱말 안에 있는 것은 나누지 않는다. 원문은 `기능성내용_원문` 에 그대로 남긴다(D-117 · 매칭은 정규화문, 보관은 원문).
★ 개정 고시가 시행일을 달고 같은 원료 안에 함께 실린 경우가 있다(2-49 키토산 · 2027-01-01 시행) — `시행` 으로 가른다.
🟡 2-48 영지버섯 자실체 추출물은 2027-01-01 부터 **삭제**된다(제2026-43호) — 지금은 현행 문구로 둔다.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

from collect import store

SOURCE_ID = "law_go_kr"
OUT = "hf_gosi_claims.jsonl"
GOSI = "건강기능식품의 기준 및 규격"

#: 원료 제목 — 「2-2홍삼」 · 「1-15 칼슘」. 목차 줄(「2-2 홍삼 104」)은 끝이 쪽수라 제외한다
HEAD = re.compile(r"^(\d{1,2}-\d{1,3})\s*([^\d(\s].{0,80}?)$")
FN = re.compile(r"^\(1\)\s*기능성\s*내용\s*[:：]?\s*(.*)$")
STOP = re.compile(r"^\(2\)|^\d\)\s|^\d{1,2}-\d{1,3}")
ITEM = re.compile(r"\((?:[가-하])\)\s*")
#: 문구 뒤에 붙는 제한 — 「(키토산에 한함)」 · 「[1) (2) (다)의 제조방법에 한함]」 · 「※…」
COND = re.compile(r"\s*(\[[^\]]*한함\]|\([^()]*한함\)|※.*)$")
DOT = "･·‧․"
SPLIT_TAIL = "에 도움을 줄 수 있음"
EFFECTIVE = re.compile(r"시행일\((\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\)")
NOTICE_NO = re.compile(r"고시전문\((제\d{4}-\d+호),\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\.?\)")


def _raw_zip() -> tuple[str, bytes]:
    hits = sorted((store.RAW / "law").glob("admrul_34650_*_attach.zip"))
    if not hits:
        raise SystemExit(
            "🚨 고시전문 ZIP 이 없다 — `collect.ingest register law_go_kr <폴더>` 로 먼저 올린다"
        )
    p = hits[-1]
    return p.name, p.read_bytes()


def _lines(blob: bytes) -> tuple[list[str], str, str]:
    """「제1~제3」 HWPX 의 문단 글자들 · 고시번호 · 고시일."""
    outer = zipfile.ZipFile(io.BytesIO(blob))
    no = day = ""
    part = None
    for info in outer.infolist():
        name = info.filename.encode("cp437").decode("cp949", "replace")
        if m := NOTICE_NO.search(name):
            no, day = m.group(1), f"{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
        if "제1~제3" in name:
            part = info
    if part is None:
        raise SystemExit("🚨 ZIP 안에 「제1~제3」 HWPX 가 없다 — 고시전문 구성이 바뀌었다")
    hz = zipfile.ZipFile(io.BytesIO(outer.read(part)))
    lines: list[str] = []
    for sec in sorted(n for n in hz.namelist() if re.match(r"Contents/section\d+\.xml$", n)):
        for p in ET.fromstring(hz.read(sec)).iter():
            if p.tag.endswith("}p"):
                t = "".join("".join(x.itertext()) for x in p.iter() if x.tag.endswith("}t"))
                if t.strip():
                    lines.append(t.strip())
    return lines, no, day


def _claims(text: str) -> list[tuple[str, str]]:
    """원문 → [(문구, 제한)]. 항목 (가)(나)로 가르고, 「…에 도움을 줄 수 있음」 묶음은 가운뎃점으로 가른다."""
    out: list[tuple[str, str]] = []
    # 🚨 제한 대괄호 안에도 「(나)」가 있다(「[1) (3) (나) (ㄴ)에 한함]」) — 항목으로 가르기 전에 덮어 둔다
    held: list[str] = []

    def _hold(m: re.Match) -> str:
        held.append(m.group(0))
        return f"\x00{len(held) - 1}\x00"

    masked = re.sub(r"\[[^\]]*\]", _hold, text)
    for item in (s.strip() for s in ITEM.split(masked)):
        item = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], item)
        if not item:
            continue
        cond = ""
        if m := COND.search(item):
            cond, item = m.group(1).strip(), item[: m.start()].strip()
        if item.endswith(SPLIT_TAIL) and any(d in item for d in DOT):
            head = item[: -len(SPLIT_TAIL)]
            for piece in re.split(f"\\s*[{DOT}]\\s*", head):
                if piece.strip():
                    out.append((piece.strip() + SPLIT_TAIL, cond))
        else:
            out.append((item, cond))
    return out


def collect_rows() -> list[dict]:
    raw_name, blob = _raw_zip()
    lines, no, day = _lines(blob)
    rows: list[dict] = []
    cur: tuple[str, str] | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if (m := HEAD.match(line)) and not line.endswith("참조"):
            cur = (m.group(1), m.group(2).strip())
        if (f := FN.match(line)) and cur:
            parts = [f.group(1)] if f.group(1) else []
            j = i + 1
            while j < len(lines) and not STOP.match(lines[j]):
                parts.append(lines[j])
                j += 1
            original = " ".join(parts).strip()
            # 개정 상자가 **기능성 내용을 고친 것**일 때만 그 시행일을 단다 — 규격 · 제조기준 개정 상자가
            # 바로 앞에 있어도(2-47 알로에 겔 · 요오드 전분 반응) 문구는 현행이다
            back = [ln for ln in lines[max(0, i - 3) : i] if "기능성 내용" in ln]
            eff = EFFECTIVE.search(back[-1]) if back else None
            when = (
                f"{eff.group(1)}-{int(eff.group(2)):02d}-{int(eff.group(3)):02d}" if eff else "현행"
            )
            for claim, cond in _claims(original):
                rows.append(
                    {
                        "원천": SOURCE_ID,
                        "원본": raw_name,
                        "고시": GOSI,
                        "고시번호": no,
                        "고시일": day,
                        "구분": "영양성분" if cur[0].startswith("1-") else "기능성 원료",
                        "번호": cur[0],
                        "원료명": cur[1],
                        "기능성문구": claim,
                        "제한": cond,
                        "시행": when,
                        "기능성내용_원문": original,
                        "층": "2층 적법라벨",
                        "지위": "고시",
                    }
                )
            i = j
            continue
        i += 1
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="건강기능식품 고시형 기능성 문구 → hf_gosi_claims.jsonl"
    )
    ap.add_argument("--dump", action="store_true", help=f"data/derived/{OUT} 로 쓴다")
    ap.add_argument("--verify", action="store_true", help="세기만 한다")
    args = ap.parse_args()

    rows = collect_rows()
    items = {(r["번호"], r["시행"]) for r in rows}
    kinds = {
        k: len({r["번호"] for r in rows if r["구분"] == k}) for k in ("영양성분", "기능성 원료")
    }
    print(f"  고시 {rows[0]['고시번호'] if rows else '?'} ({rows[0]['고시일'] if rows else '?'})")
    print(
        f"  원료 {len({r['번호'] for r in rows})} (영양성분 {kinds['영양성분']} · 기능성 원료 {kinds['기능성 원료']})"
        f" · 원료×시행 {len(items)} · 문구 {len(rows)}"
    )
    later = sorted({(r["번호"], r["시행"]) for r in rows if r["시행"] != "현행"})
    if later:
        print(f"  🟡 시행일이 따로 있는 개정 문구 — {later}")
    empty = [r["번호"] for r in rows if not r["기능성문구"]]
    if empty or not rows:
        print(f"  🚨 빈 문구 {empty}", file=sys.stderr)
        return 1
    if args.verify or not args.dump:
        return 0
    out = store.derived_dir(".") / OUT
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(store.stamp(r, SOURCE_ID), ensure_ascii=False) + "\n")
    print(f"  💾 {len(rows)}행 → {out.relative_to(store.ROOT) if hasattr(store, 'ROOT') else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
