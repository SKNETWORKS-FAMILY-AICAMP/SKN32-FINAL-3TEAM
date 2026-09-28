"""law_norm.py — [별표] **산문**을 규범 노드로 자른다 (3층 판단규범).

  uv run python -m preprocess.law_norm --dump
  uv run python -m preprocess.law_norm --annex 013453_0001

왜 따로인가 — `collect/law_annex.py` 는 **괘선 표**를 자른다. 그런데 표 0행인 별표가 12건이고,
그중 **3층의 본체가 둘 있다**(2026-09-09 실측) —

    013453 [별표 1] 부당한 표시 또는 광고의 내용(제3조제1항 관련)   8,161자
    008741 [별표 5] 화장품 표시ㆍ광고의 범위 및 준수사항(제22조 관련) 2,734자

앞의 것이 **우리 위법 유형 8종의 법령상 정의 그 자체**다. 표가 아니라 `1. → 가. → 1)` 계층
산문이라 표 파서로는 0행이 나온다. 같은 수집으로 4층은 채워지고 3층은 원문만 쌓여 있었다.

🚨 **줄을 이어붙이는 것은 되돌릴 수 없이 애매하다.** 원문이 고정폭으로 접혀 있는데
   패딩이 공백을 먹어서, 「단어 사이에서 접혔는가」와 「음절 사이에서 접혔는가」가
   구분되지 않는다. 실측 —

       '…등(이하 이'  + '목에서'  → 원문은 「이 목에서」   (공백 있었음)
       '…각 목의 표'  + '시 또는' → 원문은 「표시 또는」   (공백 없었음)

   폭으로도 안 갈린다. 접힘 열이 76~78 사이에서 흔들리고, 한글이 폭 2 라 마지막 칸을
   정확히 채우지 못한다. **그래서 복원하지 않는다** (D-98 「완전 복원은 하지 않는다」).

✅ **그런데 이 애매함은 매칭에 영향을 주지 않는다.** D-117 이 「매칭은 정규화문, 보관은 원문」
   이고 `norm()` 이 공백을 **전부 지운다** — 「이목에서」와 「이 목에서」가 같은 문자열이 된다.
   그래서 이 모듈은 둘 다 남긴다:
     `lines`  물리 줄 원본 — 화면에 보일 때 쓴다. 재구성하지 않는다
     `text`   공백 없이 이어붙인 것 — 매칭용. `norm()` 을 지나면 애매함이 사라진다
   🚨 `text` 를 화면에 그대로 찍으면 안 된다. 그건 복원한 척하는 것이다.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys

from collect import store
from collect.law_annex import ROW_START, parse_table

ROOT = pathlib.Path(__file__).resolve().parents[1]
# 🆕 D-254 — 폴더 이름은 store.FAMILY_OF 에서만 꺼낸다 (D-99 · 감사 §1-7)
ANNEX = store.family_path("law_go_kr") / "annex"

# 계층 — 마커의 **모양**이 깊이를 정한다. 들여쓰기로 정하지 않는다:
# 이어지는 줄의 들여쓰기가 마커 줄과 같아서 둘을 못 가른다 (실측).
#: 🚨 **`app/retrieve.py` 의 `_JO` 와 같은 값이다** (2026-09-14 · 별표 인용).
#:    ⛔ 합치지 않았다 — `app/` 이 `preprocess/` 를 import 하면 런타임이 전처리 층에 매인다.
#:       D-99 의 나머지 절반을 쓴다: **양쪽에 서로를 가리키는 주석.** 한쪽을 고치면 둘 다 고친다.
JO = "가나다라마바사아자차카타파하"
#: `level` 은 **모양의 이름표**다(깊이가 아니다) — 법령 별표 노드의 값이 바뀌지 않게 종전 번호를 그대로 둔다.
#: 🆕 2026-09-26 — 괄호 번호 `(1)` · `(가)`(6 · 7). 행정규칙(고시) 별표가 쓴다 — 36122 [별표 4] 제4호 아래
#:    `(1)~(6)` · `(1)~(7)` · `(1)~(5)` 목록 셋을 모르고 **제4호 본문에 통째로 붙였다**(1,324자 · 사실원장 ㉜).
LEVELS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, re.compile(r"^(\d{1,2})\.\s")),
    (2, re.compile(rf"^([{JO}])\.\s")),
    (3, re.compile(r"^(\d{1,2})\)\s")),
    (4, re.compile(rf"^([{JO}])\)\s")),
    (6, re.compile(r"^(\(\d{1,2}\))\s?")),
    (7, re.compile(rf"^(\([{JO}]\))\s?")),
    (5, re.compile(r"^([①-⑳])\s?")),
)
#: 표준 순서(얕은 것 → 깊은 것) — `1.` > `가.` > `1)` > `가)` > `(1)` > `(가)` > `①`. 🚨 비교는 이 순위로 한다(`level` 값이 아니다)
RANK: dict[int, int] = {lv: i for i, (lv, _) in enumerate(LEVELS)}
#: 🆕 2026-09-28 — 줄 전체가 「비고」면 그 자리부터 구역 「비고」다(사실원장 ㊴). ⛔ 종전에는 「비고」를 **다음 구역의 이름**으로만
#:    받아서, 「비고」와 첫 번호 사이의 문장(013453 [별표 1] 「제1호 및 제3호에도 불구하고 … 부당한 표시 또는 광고행위로
#:    보지 않는다」 — 적용 제외의 **뜻 전체**)이 앞 호 제8호나목 본문에 붙었다. 위법 유형에 적용 제외 문장이 섞였다.
NOTE = re.compile(r"^비\s*고$")
#: 🆕 2026-09-26 — 별표 안의 **부표** 머리글. 🚨 **줄 전체**가 「[부표 N]」일 때만 구역 경계다 —
#:    본문이 부표를 부르는 줄(「[부표 1]의 설문을 통하여」)까지 경계로 읽으면 글이 빈 구역으로 사라진다
SUBTABLE = re.compile(r"^\[부표\s*\d+\]$")

#: 🔴 「다만 … 제외한다」 — 이 단서를 든 **본문** 노드의 하위 목이 적용 제외다 (D-238).
#:    🆕 2026-09-28 (D-238 개정 (나)) — 정본을 여기로 옮겼다. 라벨 게이트(`preprocess/guide_label.py`)와
#:    청크 표시(`preprocess/chunk.py`)가 **같은 함수**를 부른다 — 두 벌이면 라벨이 막는 목과 검색이 올리는 목이 갈린다 (D-99).
#:    `[문헌]` — 별표 원문의 단서 문형. 80자 폭은 D-238 이 013453 에 걸어 잰 값이다 — 80자를 넘는 단서가 있는지는 **안 쟀다** `[임의]`.
EXC = re.compile(r"다만[,\s].{0,80}?제외한다")


def exemption_parents(nodes: list[dict]) -> dict[str, str]:
    """본문 노드 경로 → 그 노드를 적용 제외로 만든 **가장 가까운** 단서 노드의 경로. 제외 목이 아니면 키가 없다.

        013453 [별표 1]   `1.가.1` → `1.가`   (1.가 「… 다만, 다음의 어느 하나에 해당하는 경우는 제외한다」)
        013475 [별표 3]   `2.나.1` → `2`      (손자 목도 제외다 — 중간 목 2.나 는 단서가 없다)

    🔴 **하위 목이 제외인 모양만** 잡는다 (D-238 표의 앞 모양). 단서가 그 목 **안에** 있고 하위 목이 없는 것
       (013453 `5.가` · `5.라`)은 목 전체가 위반 유형이다 — 키가 안 생긴다.
    🚨 **본문 구역만** 본다. 013453 「비고」(「제1호 및 제3호에도 불구하고 … 보지 않는다」)는 구역이 이미 다르고
       인용도 「[별표 1] 비고 …」로 갈린다 — 이 함수의 몫이 아니다(부모가 둘이라 한 좌표로 못 올린다 · ⬜).
    ⛔ 손으로 표를 만들지 않는다 — 원문 글귀로 계산한다 (D-238 · D-90).
    """
    body = [d for d in nodes if d.get("section") == "본문"]
    parents = {str(d["path"]) for d in body if EXC.search((d.get("text") or "").replace("\n", ""))}
    out: dict[str, str] = {}
    for d in body:
        parts = str(d["path"]).split(".")
        for k in range(len(parts) - 1, 0, -1):
            anc = ".".join(parts[:k])
            if anc in parents:
                out[str(d["path"])] = anc
                break
    return out


# 「■ 화장품법 시행규칙 [별표 5] <개정 …>」 — 머리글
HEAD = re.compile(r"^■")
# 🆕 머리글의 **별표 번호** (2026-09-14) — 위 예시의 `5`.
#    🔴 `annex_no`(파일명 일련번호)와 **다른 값**이다. 실측으로 24건이 일치했지만
#       머리글이 없는 파일이 34건 있고 그중 하나는 산문이다 — **일치는 보장이 아니다.**
#       인용에 쓰는 것은 **원문에서 읽은 이 값**이고, 없으면 인용을 세우지 않는다 (D-224).
ANNEX_NO = re.compile(r"\[별표\s*(\d{1,3})")
# 제목의 「(제22조 관련)」 — 이 별표를 위임한 조문
ARTICLE = re.compile(r"\(([^)]*제\d+조[^)]*)\s*관련\)")


def annex_number(content: str) -> int | None:
    """머리글에서 별표 번호를 읽는다. 🔴 못 읽으면 `None` — 파일명으로 짐작하지 않는다.

    🚨 **첫 머리글 줄만 본다.** 본문에 「[별표 3]에 따른」 같은 **다른 별표를 가리키는 말**이
       있으면, 문서 전체를 훑으면 그것을 이 별표의 번호로 읽는다.
    ⛔ `annex_no`(파일명 일련번호)로 대신하지 않는다. 실측(2026-09-14) — 머리글이 있는 24건은
       전부 일치했지만 **머리글이 없는 파일이 34건**이고 그중 하나는 산문이다. 없는 것을
       「아마 같을 것」으로 채우는 것이 D-224 가 막으려는 바로 그 일이다.
    """
    for line in content.splitlines():
        if HEAD.match(line.strip()):
            m = ANNEX_NO.search(line)
            return int(m.group(1)) if m else None
    return None


def _marker(line: str) -> tuple[int, str] | None:
    s = line.strip()
    for level, pat in LEVELS:
        m = pat.match(s)
        if m:
            return level, m.group(1)
    return None


def parse(content: str, *, reverse_child: bool = False) -> list[dict]:
    """`1. → 가. → 1) → 가) → (1) → (가) → ①` 계층을 노드로 자른다. 노드는 마커 줄에서 시작한다.

    🔴 **구역을 갈라야 한다** (2026-09-09 실측). 013453 [별표 1] 은 8호까지가 위법 유형이고
       그 뒤에 「비고」가 붙어 **「부당한 표시·광고로 보지 않는다」는 적용 제외 2호**가 온다.
       번호가 1 부터 다시 시작하므로, 구역을 안 가르면 **적용 제외가 위법 유형 1·2호로 읽힌다** —
       「식품접객업 영업소의 표시·광고」가 위법 유형이 되는 것이다. D-153·D-156 의 자리다.

    🚨 구역 전환은 **낱말이 아니라 구조**로 잡는다 — 이미 1호가 나온 뒤에 다시 1호가 오면
       그 자리가 새 구역이다. 「비고」라는 낱말은 **이름을 붙이는 데만** 쓴다 (없으면 번호로 부른다).
    🆕 2026-09-26 — 줄 전체가 「[부표 N]」이면 그 자리부터 구역 `[부표 N]` 이다. 부표 머리의 글(첫 마커 앞)은
       노드 `머리` 로 남긴다 — 버리지 않는다. ⛔ 종전에는 36122 [별표 3] [부표 1](피험자 선정기준 · 설문)이
       앞 호 제11호 본문과 **하위 항목**(`11.1~11.8`)으로 붙었다(사실원장 ㉜).

    ``reverse_child`` — 🆕 2026-09-26 · **행정규칙 별표만** 켠다(`build_admrul`).
       표준 순서로 **얕은** 모양이 스택에 없는 채로 나오면 — 법령은 그 자리까지 올라가고(종전 · 013475 [별표 4]
       머리 목록 「가. 나.」 뒤의 「1.」은 형제다), 고시는 **자식으로 둔다**. 고시가 순서를 거꾸로 쓴다 —
       「(3) 최고용량 :」 아래 「1) 2)」(36122 [별표 1] 3곳) · 「① …다음 각호」 · 「② …다음 각 호와 같다」 아래
       「1.」(36122 [별표 2] 2곳) · 「나) 기체크로마토그래프법」 아래 「1)」(37098 [별표 4]). 09-26 전수 6곳 모두
       원문을 읽어 보니 자식이었다.
       🚨 뒤집은 노드는 `역순` 을 단다 — 원문 판독 없이 규칙으로 정한 자리다. 호출자가 세어 찍는다(D-200 의 어법).
    """
    nodes: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, 마커) — 바깥에서 안으로
    cur: dict | None = None
    section, section_no, seen_l1 = "본문", 1, False
    label: str | None = None  # 직전에 지나간 마커 없는 짧은 줄 — 구역 이름 후보

    for raw in content.split("\n"):
        s = raw.strip()
        if not s or HEAD.match(s):
            continue
        if SUBTABLE.match(s) or NOTE.match(s):
            section, stack, seen_l1, label = ("비고" if NOTE.match(s) else s), [], False, None
            cur = {"section": section, "level": 0, "marker": "", "path": "머리", "lines": []}
            nodes.append(cur)
            continue
        hit = _marker(raw)
        if hit is None:
            if cur is not None:
                cur["lines"].append(raw.rstrip())
            # 🚨 「고」를 거르면 안 된다 — **「비고」가 걸린다**(2026-09-09에 실제로 걸렸다).
            #    「…표시ㆍ광고」로 끝나는 줄을 거르려던 것인데 구역 이름을 먹었다.
            if len(s) <= 12 and not s.endswith((".", "다")):
                label = s
            continue
        level, mark = hit
        levels = [lv for lv, _ in stack]
        reversed_ = False
        if level in levels:  # 같은 모양 — 그 자리의 형제
            stack = stack[: levels.index(level)]
        elif stack and RANK[level] < RANK[stack[-1][0]]:
            if reverse_child:
                reversed_ = True  # 거꾸로 쓴 순서 — 자식으로 둔다
            else:
                stack = [x for x in stack if RANK[x[0]] < RANK[level]]
        if level == 1 and not stack:
            if mark == "1" and seen_l1:
                section_no += 1
                section = label or f"구역{section_no}"
                cur = None
            seen_l1 = True
            label = None
        stack.append((level, mark))
        cur = {
            "section": section,
            "level": level,
            "marker": mark,
            "path": ".".join(m for _, m in stack),
            "lines": [raw.rstrip()],
        }
        if reversed_:
            cur["역순"] = True
        nodes.append(cur)
    # 부표 머리에 글이 없으면(머리글 바로 뒤에 마커) 노드가 아니다
    return [n for n in nodes if n["lines"]]


def build(path: pathlib.Path) -> tuple[dict, list[dict]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    art = ARTICLE.search(d["title"])
    head_no = annex_number(d["content"])
    nodes = parse(d["content"])
    rows = []
    for n in nodes:
        joined = "".join(x.strip() for x in n["lines"])
        # 마커를 본문에서 뗀다 — 「1. 질병의…」의 「1. 」
        body = re.sub(r"^[\dA-Za-z①-⑳" + JO + r"]{1,2}[.)]\s*", "", joined, count=1)
        rows.append(
            store.stamp(
                {
                    "law_id": d["law_id"],
                    #: 🚨 파일명 일련번호 — **별표 번호가 아니다.** 인용에 쓰지 않는다.
                    "annex_no": d["annex_no"],
                    #: 🆕 머리글에서 **읽은** 별표 번호. `None` = 머리글이 없다 (D-224 fail-closed).
                    #:    ⛔ 읽는 쪽은 `document.annex_no` 다 — `load_db.load_documents()`.
                    "annex_no_head": head_no,
                    "section": n["section"],
                    "annex_title": d["title"],
                    "article": art.group(1).strip() if art else "",
                    "path": n["path"],
                    "level": n["level"],
                    "text": body,  # 🚨 매칭용. 화면에 그대로 찍지 않는다
                    "lines": n["lines"],  # 🚨 원문 — 화면은 이쪽을 쓴다
                    "chars": len(body),
                },
                "law_go_kr",
            )
        )
    unique_paths(rows)  # 🆕 2026-09-26 — 법령 별표도 같은 규칙(09-26 원장 12파일은 겹침 0)
    return d, rows


# ══════════════════════════════════════════════════════════
# 🆕 2026-09-26 — **행정규칙(고시 · 지침)의 [별표]** (사실원장 ㉗ · ㉚)
#
# 🔴 왜 — `collect/law_annex.py` 는 `target=law`(법령)만 부른다. 행정규칙 XML 은 `<별표단위><별표내용>` 에
#    전문을 **이미 갖고 있는데** 읽는 곳이 없었다 — 화장품 안전기준(37098)은 조문 7행뿐이고 본체
#    [별표 1] 사용할 수 없는 원료 · [별표 2] 사용상의 제한이 필요한 원료(합 약 42만 자)가 코퍼스 밖이었다.
# ★ 네트워크를 쓰지 않는다 — 받아 둔 원문(`data/raw/law/admrul_*.xml`)만 읽는다. 원문을 새로 만들지 않는다(규약 2).
# 🚨 판(시행일)은 조문과 **같은 규칙**을 쓴다 — `law_article.split_in_force` · `PENDING_ALLOWED` (D-99).
# 🚨 괘선 표를 **행 노드**로 푼다. 법령 별표는 표를 `law_annex`(4층 처분값)가 맡고 여기서 건너뛰지만,
#    행정규칙 별표의 표는 원료 · 기능성 범위 같은 **판단 기준 그 자체**라 행이 곧 규범이다.
#    ⬜ 법령 별표의 표를 같은 길로 풀지는 정하지 않았다 — 코퍼스가 바뀐다.
# ══════════════════════════════════════════════════════════

ADMRUL = store.family_path("law_go_kr")

#: 「별표」가 아닌데 싣는 것 — 🚨 이름으로 거르지 않고 사람이 본 것만 적는다. (소스 ID, 구분, 번호) → 이유
#:    ⛔ 싣지 않는 것 — 신청서 · 인정서(서식) · 도안 · 공정위 셀프 체크리스트(20246 · 35037 — 판단 기준이 아니라 점검표)
ADMRUL_EXTRA: dict[tuple[str, str, str], str] = {
    (
        "36814",
        "별지",
        "0001",
    ): "표시사항별 세부표시기준 — 제품명 · 영양강조 등 규범 본문(서식이 아니다)",
}
#: 행정규칙 별표 머리글 — 「[별표 1]」. 법령은 「■ … [별표 5]」(위 `annex_number`)
HEAD_ADMRUL = re.compile(r"^\[별표\s*(\d{1,3})\]")
#: 머리글 줄 — 번호는 안 읽는다(「[표 4]」는 원문이 별표를 「표」로 부른 것 — 「[별표 4]」로 인용하지 않는다 · D-224)
HEAD_LINE = re.compile(r"^[\[『]\s*(?:별표|표|별지)\s*\d*\s*[\]』]")
#: 🚨 **굵은 괘선을 가는 괘선으로 바꾼 뒤** 푼다 — 식약처 고시는 `┏━┯━┓ ┃ │ ┃ ┠─┼─┨ ┗━┷━┛` 를 쓴다(36814 · 37971 실측).
#:    `law_annex.parse_table` 은 가는 괘선(`┌├└ │`)만 안다 — 바꾸지 않으면 표가 통째로 0행이다.
HEAVY_TO_LIGHT = str.maketrans("━┃┏┓┗┛┣┫┳┻╋┠┨┯┷┿╂┝┥┰┸", "─│┌┐└┘├┤┬┴┼├┤┬┴┼┼├┤┬┴")
#: 🆕 2026-09-27 — **굵은 괘선 표가 있는 별표만** 바꾼다. 굵은 선 문자 가운데 `┃` 는 뺀 것으로 가른다 —
#:    37098 [별표 2] 는 가는 괘선 표 안에서 `┐ ┃ ┘` 를 **「합계량」 묶음 괄호**로 쓴다(4줄 · 09-27 전수).
#:    ⛔ 무조건 바꾸면 그 `┃` 가 세로선이 되어 칸이 하나 늘고 값이 옆 칸으로 밀린다(사실원장 ㉝).
HEAVY_BORDER = re.compile("[━┏┓┗┛┣┫┳┻╋┠┨┯┷┿╂┝┥┰┸]")
#: 괘선 문자 — 표 줄인지 가르고, 셀 값에서 지운다(칸 안에 걸린 부분 구분선 `├──┼──┤` 조각)
BOX = "─│┌┐└┘├┤┬┴┼"
#: 🆕 2026-09-27 — 값에서는 묶음 괄호 `┃` 도 지운다(위 `HEAVY_BORDER` — 바꾸지 않은 별표에만 남는다)
_BOX_RE = re.compile(f"[{BOX}┃]+")


def admrul_units(path: pathlib.Path) -> list[dict]:
    """행정규칙 XML 의 별표 단위 — 「별표」 전부 + `ADMRUL_EXTRA` 에 적힌 것. 삭제 · 빈 것은 뺀다."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    law_id = path.stem.split("_")[1]
    out = []
    for u in ET.parse(path).getroot().iter("별표단위"):

        def g(tag: str, u: ET.Element = u) -> str:
            return (u.findtext(tag) or "").strip()

        kind, no, title, content = (
            g("별표구분"),
            g("별표번호"),
            g("별표제목"),
            # 🚨 원문에 **두 번 이스케이프된 문자**가 있다(41277 「&#9656;」 — 화면에는 ▸) → 푼다.
            #    굵은 괘선 표가 있으면 가는 괘선으로 바꾼다(아래 · `HEAVY_BORDER`).
            html.unescape(u.findtext("별표내용") or ""),
        )
        if HEAVY_BORDER.search(content):
            content = content.translate(HEAVY_TO_LIGHT)
        if not content.strip() or title.startswith("삭제"):
            continue
        if kind != "별표" and (law_id, kind, no) not in ADMRUL_EXTRA:
            continue
        out.append(
            {
                "law_id": law_id,
                "kind": kind,
                "annex_no": no,
                "title": title,
                "content": content,
                "file": path.name,
            }
        )
    return out


def split_tables(content: str) -> tuple[str, list[tuple[str, list[str]]]]:
    """괘선 표를 떼어 낸다 → (표를 뺀 산문, [(표 앞 이름표, 표 줄들)]).

    이름표 — 표 바로 앞의 짧은 줄(「* 보존제 성분」). 없으면 빈 문자열.
    """
    prose: list[str] = []
    tables: list[tuple[str, list[str]]] = []
    cur: list[str] | None = None
    last = ""
    for line in content.split("\n"):
        s = line.strip()
        if s[:1] in BOX:
            if cur is None:
                cur = []
                tables.append((last, cur))
            cur.append(line)
            continue
        if s:
            cur = None
            prose.append(line)
            last = s.lstrip("*※ ").strip() if len(s) <= 30 else ""
    return "\n".join(prose), tables


#: 🆕 2026-09-27 — 칸을 가르는 선. **`│` 만이 아니다** — 칸 중간에서 시작하는 가로선(`│    ├───┼───┤`)의
#:    `├ ┼ ┤` 는 세로선 자리에 놓인다. `│` 로만 쪼개면 그 줄의 칸 수가 모자라 글이 옆 칸으로 밀린다(사실원장 ㉝).
_COL_SEP = re.compile("[│├┼┤]")
#: 칸 하나가 가로선뿐이면 그 칸의 **하위 행 경계**다
_RULE = re.compile(r"^[─┬┴\s]*─[─┬┴\s]*$")
#: 논리 행 경계 — 줄 머리가 괘선 모서리 · 교차면 행이 끝난다(`law_annex.parse_table` 과 같은 규칙)
_ROW_EDGE = "┌┬┐├┼┤└┴┘"


def _segments(line: str) -> list[str]:
    """한 줄을 칸으로 — 바깥 테두리 양쪽은 뗀다(오른쪽 테두리가 없는 줄도 있다 · 36122 [별표 3] 부표)."""
    s = line.strip()
    parts = _COL_SEP.split(s)
    if s[:1] in "│├":
        parts = parts[1:]
    if s[-1:] in "│┤" and parts:
        parts = parts[:-1]
    return parts


def _join(frags: list[str]) -> str:
    """한 칸의 물리 줄 조각을 잇는다 — **공백 없이**(`parse_table` 과 같다 · 한글은 음절 사이에서 접힌다).
    🆕 2026-09-27 — 숫자와 숫자가 맞닿으면 **띄운다.** 한 칸에 한 줄씩 적은 값 목록(36122 [별표 3] 부표 처방
    「8.00 / 2.50 / 4.00」 · 37098 CAS 여럿)이 「8.002.504.00」 이 됐다. 09-27 전수 18곳 모두 따로 적힌 값이었다 —
    숫자 하나가 두 줄로 접힌 자리는 없었다."""
    out = ""
    for f in frags:
        if out and out[-1].isdigit() and f[:1].isdigit():
            out += " "
        out += f
    return out


def parse_grid(text: str) -> list[dict]:
    """괘선 표 → 논리 행. 행마다 칸별 **하위 칸**(칸 안의 가로선으로 나뉜 조각)을 든다 (🆕 2026-09-27 · 사실원장 ㉝).

        {"subs": [[조각, …], …] 칸마다 하위 칸 목록, "irregular": bool, "fragments": 칸별 조각(화면용)}

    🔴 **왜** — 원문 표는 한 칸이 여러 줄에 걸치고 옆 칸만 가로선으로 나뉜다(한 칸 병합). `parse_table` 은 줄 머리의
       가로선만 행 경계로 알아 **하위 행이 한 행에 붙었다** — 36122 [별표 4] 염모제 성분 30개와 농도 30개가 각각 한 칸에
       공백 없이(「1.50.51.01.0…」), 37098 [별표 1] 원료 하나의 CAS 셋이 한 칸에(「55-65-276487-49-5」).
       짝(성분 ↔ 농도)을 잃으면 **틀린 수치를 인용**하게 된다.
    ★ 칸 수는 **바로 앞 경계선**에서 읽는다(`┬ ┼` 수 + 1) — 행마다 칸 수가 달라지는 표가 있다(머리글이 두 층인 표).
    🚨 칸 수가 맞지 않는 줄이 있으면 그 행은 `irregular` — 하위 칸을 가르지 않는다(호출자가 종전 방식으로 두고 표시한다).
    """
    rows: list[dict] = []
    buf: list[str] = []
    ncols: int | None = None

    def flush() -> None:
        if not buf:
            return
        n = ncols or max(len(_segments(x)) for x in buf)
        subs: list[list[list[str]]] = [[[]] for _ in range(n)]
        irregular = False
        for line in buf:
            seg = _segments(line)
            if len(seg) != n:
                irregular = True
                break
            for j, x in enumerate(seg):
                if _RULE.match(x):
                    subs[j].append([])
                elif x.strip():
                    subs[j][-1].append(x.strip())
        rows.append(
            {
                "subs": [[c for c in col if c] or [[]] for col in subs],
                "irregular": irregular,
                "raw": list(buf),
            }
        )
        buf.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        head = line.lstrip()[:1]
        if not line.strip():
            continue
        if head in _ROW_EDGE:
            flush()
            ncols = 1 + sum(line.count(c) for c in "┬┼") if head not in "└┴┘" else None
            continue
        if "│" in line:
            seg = _segments(line)
            # 구분선 없는 표의 행 경계 — 첫 칸이 항목 마커로 시작하면 새 행이다(`parse_table` 과 같다)
            if seg and ROW_START.match(seg[0].strip()):
                flush()
            buf.append(line)
    flush()
    return rows


def _row_values(row: dict) -> list[tuple[list[str], list[str], int | None]]:
    """논리 행 → [(칸 값들, 칸 화면 글, 하위 번호)]. 하위 칸 수가 한 가지면 하위 행으로 풀고 걸친 칸은 되풀이한다.

    값은 `_join`(매칭용) · 화면 글은 조각을 공백으로 잇는다(`lines` — 종전과 같다).
    🚨 하위 칸 수가 칸마다 다르면(다단 계층 표 · 36814 1회 섭취참고량) **풀지 않는다** — 하위 칸을 ` / ` 로 잇고 번호 0.
       ⛔ 공백 없이 붙이지 않는다. 짝을 지어 줄 수 없으면 짝이 없다고 보이게 둔다.
    """
    subs = row["subs"]
    counts = [len(c) for c in subs]
    multi = {c for c in counts if c > 1}

    def pick(i: int, k: int) -> list[list[str]]:
        return [c[i] if len(c) == k else c[0] for c in subs]

    if not multi:
        cells = [c[0] for c in subs]
        return [([_join(x) for x in cells], [" ".join(x) for x in cells], None)]
    if len(multi) == 1:
        k = multi.pop()
        return [
            ([_join(x) for x in pick(i, k)], [" ".join(x) for x in pick(i, k)], i + 1)
            for i in range(k)
        ]
    return [
        (
            [" / ".join(_join(x) for x in c) for c in subs],
            [" / ".join(" ".join(x) for x in c) for c in subs],
            0,
        )
    ]


def table_nodes(label: str, lines: list[str], t: int) -> list[dict]:
    """표 하나를 행 노드로 — 첫 논리 행을 머리글로, 나머지 행마다 「머리글: 값」.

    🚨 값은 조각을 **공백 없이** 잇는다(`parse_table` 과 같다 · 매칭용 · 숫자끼리만 띄운다 `_join`) — 화면은 `lines` 를 쓴다.
    🔄 2026-09-27 — `parse_grid` 로 푼다. 칸 안의 가로선으로 나뉜 **하위 행은 노드 하나씩**(경로 `표{t}.{i}.{k}`) —
       여러 줄에 걸친 칸(「구분: I」 · 원료명)은 하위 행마다 되풀이한다. 하위 행이 없는 행의 경로는 종전 그대로 `표{t}.{i}`.
       칸 수가 안 맞는 행은 종전 방식(`parse_table`)으로 두고 `표불규칙` 을 단다. 하위 칸 수가 칸마다 다르면 ` / ` 로 잇고 `표불규칙`.
    """
    grid = parse_grid("\n".join(lines))
    if not grid:
        return []
    old = parse_table("\n".join(lines))
    # 🚨 머리글은 **종전 파서로** 읽는다 — 머리글이 두 층인 표(`├──┬──┤` 로 한 칸이 여러 칸으로 갈린다 · 37971 [별표 1] ·
    #    [별표 5] · 36122 [별표 4] 표61)는 첫 줄의 칸 수보다 아래 칸이 많다. 격자로 읽으면 머리글이 모자라 **값 칸이 버려진다**(09-27 작업공간 재현)
    head = [_BOX_RE.sub("", c).replace(" ", "") for c in (old[0]["cells"] if old else [])]
    out = []
    for i, r in enumerate(grid[1:], start=1):
        if r["irregular"]:
            # 칸 수가 안 맞는다 — 종전 행(같은 경계 · 같은 순서)을 쓴다. 🚨 짝이 틀렸을 수 있다 → 표시
            legacy = old[i] if len(old) == len(grid) else None
            if legacy:
                disp = [" ".join(x for x in f) for f in legacy["fragments"]]
                variants = [(legacy["cells"], disp, 0)]
            else:
                variants = [(["".join(r["raw"])], [" ".join(r["raw"])], 0)]
        else:
            variants = _row_values(r)
        for vals, disp, sub in variants:
            vals = [_BOX_RE.sub("", v).strip() for v in vals]
            if [v.replace(" ", "") for v in vals] == head:
                continue  # 쪽이 넘어가며 다시 나온 머리글
            pairs = [
                (h or f"칸{k + 1}", v)
                for k, (h, v) in enumerate(zip(head, vals, strict=False))
                if v
            ]
            if not pairs:
                continue
            node = {
                # 🚨 이름표가 없으면 「본문」 — 경로(`표{t}.{i}`)가 표를 가른다. 인용은 서지 않는다(경로가 숫자로 시작하지 않는다)
                "section": label or "본문",
                "level": 0,
                "path": f"표{t}.{i}" if not sub else f"표{t}.{i}.{sub}",
                "text": " · ".join(f"{h}: {v}" for h, v in pairs),
                "lines": [" │ ".join(_BOX_RE.sub("", d).strip() for d in disp)],
            }
            if sub == 0:
                node["표불규칙"] = True
            out.append(node)
    return out


def build_admrul(u: dict) -> list[dict]:
    """행정규칙 별표 하나 → 노드(산문은 `parse` · 표는 `table_nodes`). 필드는 `build()` 와 같다 — 읽는 쪽이 같다."""
    from preprocess.law_article import PENDING_ALLOWED  # noqa: PLC0415 — 판 규칙의 정본 (D-99)

    first = next((x.strip() for x in u["content"].split("\n") if x.strip()), "")
    m = HEAD_ADMRUL.match(first) if u["kind"] == "별표" else None
    head_no = int(m.group(1)) if m else None
    art = ARTICLE.search(u["title"])
    prose, tables = split_tables(u["content"])
    nodes = []
    # 🚨 `parse` 는 **첫 마커 앞의 글을 버린다**(노드는 마커 줄에서 시작한다). 법령 별표는 그 자리가 머리글뿐이었지만,
    #    행정규칙 별표는 마커 없는 목록(41277 「○ … ▸ …」)이 통째로 거기 있다 — 버리면 별표 하나가 0노드다(실측).
    #    머리글 줄(「[별표 1]」 · 「[표 4]」)과 제목 줄을 뺀 나머지를 노드 `머리` 로 남긴다.
    lead = []
    for x in prose.split("\n"):
        if _marker(x):
            break
        s = x.strip()
        if s and not HEAD_LINE.match(s) and s.replace(" ", "") != u["title"].replace(" ", ""):
            lead.append(x.rstrip())
    if lead:
        nodes.append(
            {
                "section": "본문",
                "level": 0,
                "path": "머리",
                "lines": lead,
                "text": "".join(x.strip() for x in lead),
            }
        )
    for n in parse(prose, reverse_child=True):
        joined = "".join(x.strip() for x in n["lines"])
        body = re.sub(r"^[\dA-Za-z①-⑳" + JO + r"]{1,2}[.)]\s*", "", joined, count=1)
        # 🚨 괘선 윗줄이 글과 한 줄에 붙은 것(69549 「가. …유사명칭┌──┬──┐」)은 표로 안 잡힌다 — 괘선 문자만 지운다
        nodes.append(
            {**n, "text": _BOX_RE.sub("", body), "lines": [_BOX_RE.sub("", x) for x in n["lines"]]}
        )
    for t, (label, lines) in enumerate(tables, start=1):
        # 🚨 표 앞 줄이 머리글(「[별표 1]」)이나 별표 제목이면 이름표가 아니다 — 문맥에 제목이 두 번 붙는다
        if HEAD_LINE.match(label) or label.replace(" ", "") == u["title"].replace(" ", ""):
            label = ""
        nodes += table_nodes(label, lines, t)
    pend = PENDING_ALLOWED.get(u["file"])
    rows = []
    for n in nodes:
        row = {
            "law_id": u["law_id"],
            "annex_no": u["annex_no"],
            "annex_no_head": head_no,
            "section": n["section"],
            "annex_title": u["title"],
            "article": art.group(1).strip() if art else "",
            "path": n["path"],
            "level": n["level"],
            "text": n["text"],
            "lines": n["lines"],
            "chars": len(n["text"]),
            "원문파일": u["file"],
        }
        # 🆕 2026-09-26 — 거꾸로 쓴 번호를 자식으로 둔 자리(`parse(reverse_child=True)`)
        if n.get("역순"):
            row["역순"] = True
        # 🆕 2026-09-27 — 칸 짝을 확신할 수 없는 표 행(`table_nodes`)
        if n.get("표불규칙"):
            row["표불규칙"] = True
        # 🚨 시행 전 판을 싣는 파일이면 같은 글귀 규칙으로 표시한다 — 별표에는 글귀가 없을 수 있다(멈추지 않는다)
        if pend and any(k in n["text"] for k in pend["시행예정"]):
            row["시행예정"] = pend["표시"]
        rows.append(store.stamp(row, "law_go_kr"))
    unique_paths(rows)
    return rows


def unique_paths(rows: list[dict]) -> int:
    """같은 (구역, 경로)가 둘 이상이면 **전부** `~1` · `~2` … 를 붙인다. 붙인 행 수를 돌려준다.

    🔴 청크 ID 가 `{문서}#{구역}#{경로}#{조각}` 이라 겹치면 **적재에서 뒤엣것이 앞엣것을 덮는다**(조용히 사라진다).
       실측(2026-09-26) — 36122 [별표 4] 「4.①」이 셋 · 37098 [별표 2] 표마다 붙은 「※ 유의사항 1 · 2」.
       🔄 2026-09-26 오후 — 앞의 것은 **파서가 `(1)` 계층을 몰라서** 생긴 겹침이었다(고쳤다 · 사실원장 ㉜).
       지금 남는 겹침은 원문이 **같은 번호 목록을 되풀이**하는 자리다 — 36122 [별표 4] 제4호의
       `(1)~(6)` 효능 · `(1)~(7)` 용법 · `(1)~(5)` 원료가 번호 없는 소제목만 사이에 두고 한 호 아래 있다.
    🚨 첫째 것도 붙인다 — 경로가 여러 자리를 가리키면 어느 것도 그 좌표로 인용할 수 없다. `~` 가 붙은 경로는
       `app/retrieve.py` `_annex_citation` 이 모르는 꼴이라 인용이 서지 않는다(fail-closed · D-224).
    🆕 2026-09-26 오후 — **자손도 따라간다.** 부모가 `4.(1)~3` 이 되면 그 아래 `4.(1).①` 은 `4.(1)~3.①` 이다.
       ⛔ 따라가지 않으면 자손이 **없는 부모 경로**를 가리켜 문맥(`chunk._annex_context`)에서 부모가 빠지고,
          다른 목록의 같은 번호 자손과 다시 겹친다. 얕은 겹침부터 풀고 다시 센다 — 자손끼리의 겹침은 부모를 가른 뒤에 판단한다.
    """
    import collections  # noqa: PLC0415

    n = 0
    for _ in range(32):  # 깊이마다 한 바퀴 — 별표 계층은 7단을 넘지 않는다
        seen = collections.Counter((r["section"], str(r["path"])) for r in rows)
        dups = {key for key, v in seen.items() if v > 1}
        if not dups:
            return n
        depth = min(p.count(".") for _, p in dups)
        top = {key for key in dups if key[1].count(".") == depth}
        k: collections.Counter = collections.Counter()
        open_: dict[str, tuple[str, str]] = {}  # 구역 → (옛 경로, 새 경로) — 지금 자손을 받는 부모
        for r in rows:
            sec, path = r["section"], str(r["path"])
            if (sec, path) in top:
                k[(sec, path)] += 1
                r["path"] = f"{path}~{k[(sec, path)]}"
                r["경로중복"] = True
                n += 1
                open_[sec] = (path, r["path"])
            elif sec in open_ and path.startswith(open_[sec][0] + "."):
                old, new = open_[sec]
                r["path"] = new + path[len(old) :]
            else:
                open_.pop(sec, None)  # 🚨 자손은 부모 바로 뒤에 이어 온다 — 끊기면 닫는다
    raise SystemExit("🔴 unique_paths — 겹친 경로가 32바퀴 뒤에도 남았다. 원문 모양을 본다 (D-220)")


def admrul_key(u: dict) -> str:
    """파일 이름 — 별표는 법령과 같은 꼴(`{ID}_{번호}`), 그 밖(별지)은 구분을 넣는다 — 36814 별표 0001 과 별지 0001 이 겹친다."""
    return (
        f"{u['law_id']}_{u['annex_no']}"
        if u["kind"] == "별표"
        else f"{u['law_id']}_{u['kind']}{u['annex_no']}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="[별표] 산문 → 규범 노드 (3층)")
    ap.add_argument("--annex", default=None, help="예: 013453_0001 (생략하면 표 0행 전부)")
    ap.add_argument("--dump", action="store_true", help="노드를 사람이 읽게 찍는다")
    ap.add_argument("--write", action="store_true", help="data/derived/law_norm/ 에 쓴다")
    args = ap.parse_args()

    if not ANNEX.exists():
        print("별표가 없다 — collect.law_annex 를 먼저 돌린다", file=sys.stderr)
        return 1

    total = 0
    for p in store.current_files(ANNEX, "*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["table_rows"]:  # 표는 law_annex 가 맡는다
            continue
        key = f"{d['law_id']}_{d['annex_no']}"
        if args.annex and args.annex != key:
            continue
        _, rows = build(p)
        by_level = {lv: sum(1 for r in rows if r["level"] == lv) for lv in (1, 2, 3, 4, 6, 7, 5)}
        lv = " ".join(f"L{k}:{v}" for k, v in by_level.items() if v)
        # 🔴 **머리글 번호를 매번 찍는다.** 없으면 그 별표는 인용이 안 선다 —
        #    조용히 넘기면 검색에는 걸리는데 근거로는 못 가는 별표가 늘어난다 (D-199 의 어법).
        no = rows[0]["annex_no_head"] if rows else None
        tag = f"[별표 {no}]" if no else "🔴 머리글 번호 없음"
        print(f"  [{key}] {tag:14} {d['title'][:34]:36} 노드 {len(rows):>3}  {lv}")
        total += len(rows)

        if args.dump:
            for r in rows[:12]:
                print(f"       {r['path']:>10}  {r['text'][:64]}")
        if args.write and rows:
            out = store.derived_dir("law_norm") / f"{key}.jsonl"
            with out.open("w", encoding="utf-8", newline="\n") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ── 🆕 행정규칙 별표 (2026-09-26) ──
    from datetime import date  # noqa: PLC0415

    from preprocess.law_article import split_in_force  # noqa: PLC0415 — 판 규칙의 정본 (D-99)

    files, later = split_in_force(
        store.current_files(ADMRUL, "admrul_*.xml"), date.today().strftime("%Y%m%d")
    )
    for p in later:
        print(f"  🚨 시행 전 판 — 별표도 싣지 않는다: {p.name}")
    for p in files:
        for u in admrul_units(p):
            key = admrul_key(u)
            if args.annex and args.annex != key:
                continue
            rows = build_admrul(u)
            n_tab = sum(1 for r in rows if str(r["path"]).startswith("표"))
            no = rows[0]["annex_no_head"] if rows else None
            tag = (
                f"[별표 {no}]"
                if no
                else ("🔴 머리글 번호 없음" if u["kind"] == "별표" else u["kind"])
            )
            n_rev = sum(1 for r in rows if r.get("역순"))
            n_sub = len({r["section"] for r in rows if str(r["section"]).startswith("[부표")})
            extra = (f" · 부표 {n_sub}" if n_sub else "") + (
                f" · 🚨 역순 중첩 {n_rev}(자식으로 둠 — 원문 확인)" if n_rev else ""
            )
            print(
                f"  [{key}] {tag:14} {u['title'][:34]:36} 노드 {len(rows):>4}  (표 행 {n_tab}){extra}"
            )
            total += len(rows)
            if args.dump:
                for r in rows[:6]:
                    print(f"       {r['path']:>10}  {r['text'][:64]}")
            if args.write and rows:
                out = store.derived_dir("law_norm") / f"{key}.jsonl"
                with out.open("w", encoding="utf-8", newline="\n") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n노드 {total}개")
    print("🚨 `text` 는 매칭용이다 — 화면에는 `lines` 를 쓴다 (D-98 · D-117).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
