"""preprocess/mfds_hf.py — 건기식 원료별 정보 HTML → **2층 적법라벨** (D-156).

  uv run python -m preprocess.mfds_hf                 # 센다
  uv run python -m preprocess.mfds_hf --dump          # 🔴 마스킹 정책이 있어야 한다
  uv run python -m preprocess.mfds_hf --verify        # 원천의 선언과 대조만 한다

원천: `mfds_hf_ingredient_board` (식품안전나라 「건강기능식품 원료별 정보」)

🚨 **폴더 이름과 원천 id 가 다르다** — `data/raw/mfds_hf_board/` 인데 원천은
   `mfds_hf_ingredient_board` 다. 마스킹 정책은 **원천 id** 로 찾는다. 폴더 이름을
   그대로 넘기면 `apply_policy` 가 「정책 없음」으로 멈춘다(그건 다행이다 — D-72).
   조용히 통과하는 이름이 하나라도 생기면 그때가 진짜 사고다.

──────────────────────────────────────────────────────────────
★ **네 분류 중 하나만 문구를 가지고 있다**

    개별인정원료   465건  ← ○ 키 : 값 본문. **이 모듈이 뽑는 것.**
    사용불가 원료   93건  ┐
    기능성 원료     69건  ├ 본문이 「기준 및 규격 2-1 인삼」 같은 **고시 가리킴**뿐이다.
    영양성분        28건  ┘ 기능성 문구는 첨부 고시에 있고 본문에는 없다.
                   ───
                   655건 (원천 선언 total_cnt 와 같다)

  🚨 190건을 「추출 실패」로 세지 않는다 — 원천에 **없는** 것이다. 그렇다고 조용히
     버리지도 않는다: `--verify` 가 분류별로 세어 보여 준다. 없는 것과 못 뽑은 것을
     같은 0 으로 적으면 다음 사람이 못 고친다.

──────────────────────────────────────────────────────────────
🔴 **인정번호와 기능성내용은 마스킹을 지나도 한 글자도 안 바뀐다** (D-156)

  2층 판정은 「표현 + 제품 지위」의 함수다. 「체지방 감소에 도움을 줄 수 있음」이
  적법한 이유는 **그 원료가 그 기능성으로 인정받았기 때문**이고, 그 사실을 가리키는
  것이 인정번호다. 인정번호가 지워지면 라벨이 성립하지 않는다 — 적법하다는 근거가
  사라진 「적법」 딱지만 남는다.

  ⛔ 나는 2026-09-08 에 이걸 **한 번 재고 넘어갈 뻔했다** (「484 중 0 · 432 중 0」).
     한 번 잰 것은 다음에 규칙이 움직이면 조용히 깨진다. 그래서 `--dump` 마다 잰다.
     🚨 어긋나면 **멈춘다.** 경고만 찍고 내보내면 아무도 안 본다.

  ★ 「지금은 0 이니까 검사도 0 이다」가 아니다. 검사는 **0 이 아니게 되는 날**을 위해 있다.

──────────────────────────────────────────────────────────────
🚨 **업체명은 마스킹하는 것이 아니라 애초에 안 담는다**

  레지스트리 `fragment_note` 가 그렇게 정했다. 마스킹은 **못 담긴 것이 새어 나올 때**를
  위한 두 번째 그물이지 첫 번째 방어가 아니다. 465건 중 업체 필드가 있는 것을 세어
  보여 주되(`--verify`), 산출물에는 넣지 않는다.

  ★ 영문 블록(`※ English version ※` 아래)도 담지 않는다 — 거기 `Company or institution`
    이 있고, 우리 마스킹은 한국어 규칙이라 영문 상호를 못 잡는다. **못 잡는 그물 뒤에
    두느니 안 담는다.**

🚨 **첨부 「소비자 리포트」 PDF 는 이 모듈이 아예 읽지 않는다** — 원천이 1쪽에
   「판매 목적의 표시·광고 또는 홍보 수단으로 사용할 수 없음」이라 적어 두었고,
   우리 제품은 광고 문구를 **생성**한다. 레지스트리 `fragment_note` 참조.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import html as _html
import json
import pathlib
import re
import sys

SOURCE_ID = "mfds_hf_ingredient_board"
RAW_DIR = pathlib.Path("data/raw/mfds_hf_board")  # 🚨 폴더 이름 ≠ 원천 id
OUT = pathlib.Path("data/derived/mfds_hf_labels.jsonl")

#: ○ 키 : 값 본문을 가진 유일한 분류. 나머지 셋은 고시를 가리킬 뿐이다.
CATEGORY = "개별인정원료"

#: 취하는 것 — 레지스트리 `fragment_note` 가 정한 목록 그대로다.
KEEP = ("원료명", "인정번호", "기능성내용", "일일섭취량", "섭취주의사항")

#: 🚨 **취하지 않는 것.** 마스킹으로 지우는 게 아니라 담지 않는다.
DROP = ("업체",)

#: 🔴 마스킹을 지나도 **한 글자도 바뀌면 안 되는** 필드 (D-156).
INTACT = ("인정번호", "기능성내용")

#: 🚨 마스킹을 거는 자리. **제목은 여기 없다 — 아예 안 담기 때문이다.**
MASKED = KEEP

#: 원천이 같은 것을 여러 이름으로 부른다 — 실측한 표기를 한 이름으로 모은다.
#: 🚨 목록에 없는 키가 나오면 `--verify` 가 이름을 찍는다. 조용히 버리지 않는다.
KEY_ALIAS = {
    "원료명": "원료명",
    "원재료": "원료명",
    "신청원료명": "원료명",
    "인정번호": "인정번호",
    "기능성내용": "기능성내용",
    "기능성 내용": "기능성내용",
    "일일섭취량": "일일섭취량",
    "섭취주의사항": "섭취주의사항",
    "섭취시주의사항": "섭취주의사항",
    "섭취 시 주의사항": "섭취주의사항",
    "섭취 주의사항": "섭취주의사항",
    "섭취시 주의사항": "섭취주의사항",
    "업체": "업체",
    "업체명": "업체",
    "기타사항": "기타사항",
    "섭취방법": "섭취방법",
}

_POST = '<div class="post" id="_post">'
_ATTACH = "<!--첨부파일"
_TITLE = re.compile(r'<h4 class="view_title">\s*(.*?)\s*</h4>', re.S)
_EN = "English version"
#: 재수집 스냅숏. 본문이 같은지 **확인하고** 지나간다 — 그냥 거르면 원천 변경을 놓친다.
_SNAP = re.compile(r"__c\d{8}$")


def _n(s: str) -> str:
    return " ".join(s.split())


def body_lines(raw: str) -> list[str]:
    """게시물 본문을 줄로. 🚨 `<br>` 이 줄이다 — 원천이 표가 아니라 줄바꿈으로 적었다."""
    i = raw.index(_POST)
    j = raw.index(_ATTACH, i)
    b = raw[i + len(_POST) : j]
    b = re.sub(r"<!--.*?-->", " ", b, flags=re.S)  # 🚨 안 지우면 `-->` 가 값에 붙는다
    b = re.sub(r"<br\s*/?>", "\n", b, flags=re.I)
    b = re.sub(r"</p>|</div>|</tr>|</li>", "\n", b, flags=re.I)
    b = re.sub(r"<[^>]+>", " ", b)
    b = _html.unescape(b).replace("​", "")
    return [x for x in (_n(ln) for ln in b.split("\n")) if x]


def explode(lines: list[str]) -> list[str]:
    """한 줄에 여러 「○ 키」가 붙어 온 것을 편다.

    ⛔ 원천은 대부분 한 줄에 하나씩 적지만 **66건이 두 개를 붙여 놓았다** —
       「○ 원료명 : 감잎주정추출분말 ○ 인정번호 : 제2022-18호」.
    🔴 안 펴면 두 가지가 동시에 조용히 망가진다:
         ① 인정번호가 **없는 것**이 된다 (D-156 이 지키라는 바로 그 필드다)
         ② 「○ 기능성내용 : … ○ 일일섭취량 : …」에서 **일일섭취량이 기능성내용 안에 섞인다**
       ②가 더 나쁘다 — 필드가 비지 않아 계수로도 안 잡힌다. 값이 길어질 뿐이다.

    🚨 아무 `○` 에서나 자르지 않는다 — 값 안에도 `○` 가 올 수 있다(가림 표기 「김○○」).
       **뒤따르는 말이 우리가 아는 키일 때만** 자른다.
    """
    out: list[str] = []
    for ln in lines:
        head, *rest = ln.split("○")
        buf = head
        for seg in rest:
            key_raw = seg.split(":")[0].split("：")[0]
            if _n(key_raw) in KEY_ALIAS:
                if buf.strip():
                    out.append(buf.strip())
                buf = "○" + seg
            else:
                buf += "○" + seg
        if buf.strip():
            out.append(buf.strip())
    return out


def fields(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    """국문 블록의 「○ 키 : 값」. 반환 = (필드, 모르는 키들).

    🚨 값이 다음 줄로 이어진다 — 「○ 기능성내용 :」 뒤에 `- …` 여러 줄이 오는 형태가
       실제로 있다. 이어지는 줄을 안 붙이면 **기능성 문구가 통째로 사라진다.**
       ★ 그래도 티가 안 난다: 필드는 있고 값만 짧아진다. 그래서 `--verify` 가 길이를 센다.
    """
    got: dict[str, list[str]] = {}
    unknown: list[str] = []
    cur: str | None = None
    for ln in explode(lines):
        if _EN in ln:  # ※ English version ※ — 여기부터는 담지 않는다
            break
        if ln.startswith("※"):
            cur = None
            continue
        if ln.startswith("○"):
            # 🚨 정규식으로 「키 : 값」을 잡지 않는다. 비탐욕 수량자에 콜론을 선택으로 두면
            #    「○ 기능성내용 : …」의 키를 **'기' 한 글자**로 끊는다 — 2026-09-08 실측.
            #    ⛔ 그래도 예외가 안 난다: 필드 465건이 전부 「모르는 키」로 빠지고 끝난다.
            #    ★ `--verify` 의 「모르는 키」 계수가 그 자리에서 잡았다. 세는 쪽이 있어서다.
            rest = ln[1:].strip()
            key_raw, sep, val = rest.partition(":")
            if not sep:
                key_raw, sep, val = rest.partition("：")
            if not sep:  # 「○ 기능성내용」처럼 콜론 없이 오고 값이 다음 줄인 형태
                key_raw, val = rest, ""
            key = KEY_ALIAS.get(_n(key_raw))
            if key is None:
                unknown.append(_n(key_raw))
                cur = None
                continue
            got.setdefault(key, [])
            if val.strip():
                got[key].append(val.strip())
            cur = key
        elif cur:
            got[cur].append(ln)
    return {k: "\n".join(v).strip() for k, v in got.items() if v}, unknown


def index() -> dict[str, dict]:
    """게시물 번호 → 목록 행. 🚨 목록이 **분류와 제목의 유일한 출처**다 — 본문엔 없다."""
    idx: dict[str, dict] = {}
    total: set[int] = set()
    for p in sorted(RAW_DIR.glob("hf_board_index_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("total_cnt"):
            total.add(int(d["total_cnt"]))
        for r in d.get("list") or []:
            idx.setdefault(str(r["ntctxt_no"]), r)
    if not idx:
        raise FileNotFoundError(
            f"{RAW_DIR} 에 목록 json 이 없다 —\n  먼저: uv run python -m collect.mfds_hf_board"
        )
    if len(total) != 1:
        raise ValueError(f"목록마다 선언한 전체 건수가 다르다 — {sorted(total)}")
    declared = total.pop()
    if len(idx) != declared:
        raise ValueError(
            f"원천이 {declared} 건이라 했는데 목록에 {len(idx)} 건이다.\n"
            "  🚨 offset 페이징에서 정렬 키가 유일하지 않으면 중복+누락이 함께 난다.\n"
            "     수가 맞아도 중복과 누락이 상쇄됐을 수 있으니 번호까지 본다."
        )
    return idx


def posts() -> dict[str, pathlib.Path]:
    """게시물 번호 → 파일. 재수집 스냅숏은 **본문 대조 후** 접는다."""
    base: dict[str, pathlib.Path] = {}
    snaps: list[tuple[str, pathlib.Path]] = []
    for p in sorted(RAW_DIR.glob("hf_board_*.html")):
        stem = p.stem.removeprefix("hf_board_")
        if _SNAP.search(stem):
            snaps.append((_SNAP.sub("", stem), p))
        else:
            base[stem] = p
    for no, p in snaps:
        b = base.get(no)
        if b is None:  # 스냅숏만 있으면 그게 원본이다
            base[no] = p
            continue
        if body_lines(b.read_text(encoding="utf-8", errors="replace")) != body_lines(
            p.read_text(encoding="utf-8", errors="replace")
        ):
            raise ValueError(
                f"게시물 {no} 의 재수집본 본문이 처음 것과 다르다 — {p.name}\n"
                "  🚨 원천이 바뀐 것이다. 어느 쪽을 쓸지는 사람이 정한다 (D-143)."
            )
    return base


def extract() -> tuple[list[dict], dict]:
    """레코드들과 계측. 🚨 마스킹은 여기서 하지 않는다 — 부르는 쪽이 정책을 지고 건다."""
    idx, files = index(), posts()
    miss = sorted(set(idx) - set(files))
    extra = sorted(set(files) - set(idx))
    if miss or extra:
        raise ValueError(
            f"목록과 파일이 어긋난다 — 파일 없는 목록 {len(miss)}건 {miss[:5]} ·"
            f" 목록 없는 파일 {len(extra)}건 {extra[:5]}"
        )

    rows: list[dict] = []
    stat: dict = {
        "분류": collections.Counter(),
        "필드": collections.Counter(),
        "버린필드": collections.Counter(),
        "모르는키": collections.Counter(),
        "본문없음": [],
        "영문블록": 0,
        "제목인정번호": 0,
    }
    for no, p in sorted(files.items()):
        meta = idx[no]
        cat = _n(meta.get("ctgrynm") or "?")
        stat["분류"][cat] += 1
        if cat != CATEGORY:
            continue  # 고시를 가리킬 뿐 — 없는 것이지 못 뽑은 것이 아니다
        lines = body_lines(p.read_text(encoding="utf-8", errors="replace"))
        stat["영문블록"] += any(_EN in ln for ln in lines)
        got, unknown = fields(lines)
        for u in unknown:
            stat["모르는키"][u] += 1
        for k in DROP:
            if got.get(k):
                stat["버린필드"][k] += 1
        # 🔴 **제목은 담지 않는다.**
        #  ⛔ 처음엔 담고 마스킹만 걸었다. 465건 중 434건이 가려졌고 **31건이 남았다** —
        #     「주식회사 성 동」(원천이 이름 안에 띄어쓰기를 넣었다)·「주식회사애니닥터헬스케어」
        #     (법인격 뒤에 공백이 없다). 우리 규칙이 못 잡는 모양이다.
        #  🚨 업체 필드는 안 담기로 해 놓고 **제목이라는 다른 문으로** 같은 이름이 들어오고
        #     있었다. 필드 이름으로 막으면 필드 이름이 아닌 자리로 샌다.
        #  ★ 그래서 가리는 대신 **버린다.** 제목에서 쓸모 있는 것은 인정번호뿐이고
        #     (여러 호가 통합된 원료는 제목에만 다 적혀 있다) 그건 패턴으로 떠낼 수 있다.
        title = _n(meta.get("titl") or "")
        stat["제목인정번호"] += len(_RECOG.findall(title))
        rec = {
            "게시물": no,
            "분류": cat,
            "작성일": _n(meta.get("cret_dtm") or "")[:10],
            "원천": SOURCE_ID,
            "층": "2층 적법라벨",
            "지위": "기능성 원료로 인정받음",
        }
        for k in KEEP:
            v = got.get(k, "")
            rec[k] = v
            if v:
                stat["필드"][k] += 1
        if not any(rec[k] for k in KEEP):
            stat["본문없음"].append(no)
            continue
        rec["기능성문구"] = split_claims(rec["기능성내용"])
        # 🚨 제목에만 적힌 통합 인정번호까지 모은다 — 이름은 빼고 번호만 떠낸다.
        rec["인정번호_전체"] = list(
            dict.fromkeys(_RECOG.findall(rec["인정번호"]) + _RECOG.findall(title))
        )
        rows.append(rec)
    return rows, stat


_BULLET = re.compile(r"^[-–·ㆍ]\s*")


def split_claims(text: str) -> list[str]:
    """기능성내용 → 문구 목록. 🚨 **원문은 `기능성내용` 에 그대로 남는다** (D-156 검사 대상)."""
    out = []
    for ln in text.split("\n"):
        s = _BULLET.sub("", ln).strip().strip("“”\"'")
        if s:
            out.append(s)
    return out


#: 「제2009-83호」 꼴. 🚨 인정번호는 **자기 필드 밖에도 산다** — 실측: 섭취주의사항 안에
#: 「기존에 인정받은 제2009-83호(깻잎추출물, (주)휴메딕스)와 동일한 원료임」.
#: 그 줄에서 업체명은 지워야 하고 인정번호는 남아야 한다. 같은 줄에서 갈린다.
_RECOG = re.compile(r"제?\s*\d{4}\s*-\s*\d+\s*호")


def intact_report(before: list[dict], after: list[dict]) -> list[str]:
    """🔴 D-156 상시 검사 — 마스킹이 근거를 건드렸는가.

    두 가지를 본다:
      ① `INTACT` 필드는 **한 글자도** 안 바뀐다.
      ② 어느 필드든 **인정번호 꼴이 사라지지 않는다.**

    ⛔ ①만 보면 놓친다 — 인정번호는 자기 필드 밖에도 있기 때문이다.
       「세는 쪽과 하는 쪽이 어긋난 자리」가 정확히 이런 모양이다.
    """
    bad = []
    for a, b in zip(before, after, strict=True):
        for k in INTACT:
            if a[k] != b[k]:
                bad.append(f"게시물 {a['게시물']} · {k}\n    전: {a[k]!r}\n    후: {b[k]!r}")
        for k in MASKED:
            lost = len(_RECOG.findall(a[k])) - len(_RECOG.findall(b[k]))
            if lost:
                bad.append(
                    f"게시물 {a['게시물']} · {k} — 인정번호 {lost}개가 사라졌다\n"
                    f"    전: {a[k]!r}\n    후: {b[k]!r}"
                )
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="건기식 원료별 정보 → 2층 적법라벨 (D-156)")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다 (마스킹 정책 필요)")
    ap.add_argument("--verify", action="store_true", help="원천 선언과 대조만 한다")
    a = ap.parse_args()

    rows, stat = extract()
    print(f"레코드 {len(rows):,}  ({CATEGORY} 만 본문이 있다)")
    print("\n  분류별 게시물 — 🚨 아래 셋은 **없는 것**이지 못 뽑은 것이 아니다")
    for k, v in stat["분류"].most_common():
        mark = "★" if k == CATEGORY else " ·"
        note = "" if k == CATEGORY else "  (본문은 고시 가리킴뿐)"
        print(f"    {mark} {v:>5}  {k}{note}")

    if a.verify:
        print("\n  필드별 채워진 수 — 🚨 비어 있는 것이 있으면 파싱이 아니라 원천을 먼저 본다")
        for k in KEEP:
            n = stat["필드"][k]
            print(f"    {'🚨' if n < len(rows) else '★'} {n:>5} / {len(rows)}  {k}")
        print(
            f"\n  담지 않은 것 — 업체 필드 {stat['버린필드']['업체']}건 ·"
            f" 영문 블록 {stat['영문블록']}건 · 제목 {len(rows)}건"
        )
        print("     🚨 마스킹으로 지운 게 아니라 **애초에 안 담았다** (레지스트리 fragment_note).")
        print(f"     ★ 제목에서는 인정번호 {stat['제목인정번호']}개만 떠냈다 — 상호는 안 가져온다.")
        print("       ⛔ 담고 마스킹만 걸었을 때 465건 중 31건에 상호가 남았다(2026-09-08 실측).")
        if stat["모르는키"]:
            print(f"\n  🔴 KEY_ALIAS 에 없는 키 {len(stat['모르는키'])}종 — 조용히 버려졌다:")
            for k, v in stat["모르는키"].most_common(20):
                print(f"      {v:>4}  {k!r}")
        if stat["본문없음"]:
            print(
                f"\n  🔴 {CATEGORY} 인데 필드가 하나도 없는 게시물 {len(stat['본문없음'])}건:"
                f" {stat['본문없음'][:10]}"
            )

    if a.dump:
        from preprocess.mask import apply_policy  # noqa: PLC0415

        log: list[dict] = []
        after = []
        changed = collections.Counter()
        for r in rows:
            rec = dict(r)
            for k in MASKED:
                if rec[k]:
                    m = apply_policy(rec[k], "", SOURCE_ID, log)
                    if m != rec[k]:
                        changed[k] += 1
                    rec[k] = m
            rec["기능성문구"] = split_claims(rec["기능성내용"])
            after.append(rec)

        bad = intact_report(rows, after)
        if bad:
            print(
                f"\n🔴 D-156 위반 — 마스킹이 {INTACT} 를 건드렸다. **내보내지 않는다.**\n"
                "   2층 판정은 「표현 + 제품 지위」의 함수다. 인정번호가 지워지면\n"
                "   적법하다는 **근거가 사라진 「적법」 딱지**만 남는다.\n"
                + "\n".join(f"  · {b}" for b in bad[:10]),
                file=sys.stderr,
            )
            return 1

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8") as fh:
            for rec in after:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n  🔴 마스킹 — 바뀐 필드 {dict(changed) or '없음'} · 치환 {len(log)}건")
        print(
            f"  ★ D-156 상시 검사 통과 — {INTACT} 훼손 0 "
            f"(인정번호 {stat['필드']['인정번호']} · 기능성내용 {stat['필드']['기능성내용']} 중)"
        )
        print(
            "     🚨 「지금 0 이니 검사도 필요 없다」가 아니다 — 0 이 아니게 되는 날을 위해 있다."
        )
        print(f"  → {OUT}  ({len(after):,}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
