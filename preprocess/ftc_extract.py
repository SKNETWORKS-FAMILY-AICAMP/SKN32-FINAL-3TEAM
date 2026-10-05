"""preprocess/ftc_extract.py — 공정위 결정문 「주문」에서 **1층 라벨 삼요소**를 뽑는다.

  uv run python -m preprocess.ftc_extract              # 세기만 한다
  uv run python -m preprocess.ftc_extract --dump       # data/derived/ftc_layer1_phrases.json

수집이 아니라 **읽기만 한다** — `data/raw/ftc/*.xml` 을 건드리지 않는다 (`preprocess/` 에 있는 이유).

──────────────────────────────────────────────────────────────
★ 왜 「주문」인가 — 한 문장에 입력·라벨·근거가 다 있다 (2026-09-07 실측)

    “초유함량 국내 최대”라고 표시·광고함으로써  자신의 제품에 포함된 초유함량이
    └──── ① 입력: 광고 문구 원문 ────┘          국내 최대가 아님에도  마치 국내 최대인 것처럼
                                                └──── ③ 근거: 왜 부당한가 ────┘
    … 거짓·과장의 광고행위를 다시 하여서는 아니 된다
      └ ② 라벨: 유형 ┘

  D-59 의 A/B/C 형이 그대로다.

🚨 **「이유」가 아니다.** 「이유」에는 인용부호가 훨씬 많지만 대부분 노이즈다 —
   `/LSW/flDownload.do?flSeq=…`(첨부 링크) · 「이유 1번째 이미지」(이미지 alt) ·
   「이라 한다)」(약칭 정의). 실측에서 「이유」는 665문서가 걸렸는데 광고 문구는 거의 없었다.
   **주문 261~308문서**가 실제 자리다.

🚨 **B 버킷(고객유인·위계)에는 광고 문구가 거의 없다 — 105건 중 4건.**
   09-06 인계가 「값은 B 에 있다(17→105, 6배)」고 적은 것은 **모수 증가** 관점이고,
   **광고 문구 관점에서는 A 가 압도적**(280/680)이다. 두 말이 모순이 아니라 축이 다르다.

🚨 **분류는 `sep_norm` 을 지난 문장으로 한다.** 원문으로 `classify` 를 부르면
   A 680 → 599, A′ 67 → 12 로 **135건이 샌다** (2026-09-07 실측 · D-117).
   `ftc_triage.main()` 이 그렇게 하고 있고, 여기도 같아야 두 산출물의 수가 맞는다.

🔴 **derived 로 나가는 것은 마스킹을 지난다** (D-17 · 게이트).
   문구를 뽑기 **전에** `apply_policy` 를 건다 — 뽑은 뒤에 걸면 업체명이 문구 안에 남는다.
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

from collect import store
from preprocess import stage
from preprocess.ftc_triage import CORE, _text, case_law, classify
from preprocess.mask import MARK_RE, Ledger, Trace, anchor_ftc, apply_policy
from preprocess.text import FOOTNOTE, sep_norm

SOURCE_ID = "ftc_decisions_body"  # 수집기 `collect.ftc_body`
# 🆕 D-254 — 폴더 이름은 store.FAMILY_OF 에서만 꺼낸다 (D-99 · 감사 §1-7)
RAW = store.family_path(SOURCE_ID)
OUT = pathlib.Path("data/derived/ftc_layer1_phrases.json")
#: 🔴 **단계 물질화** (D-143). `data/` 아래 — 배포되지 않는다.
STAGE = pathlib.Path("data/derived/ftc_stage.jsonl")

#: 인용부호 5종. 원천이 섞어 쓴다.
QUOTE = re.compile(r"[‘'\"“「『]([^’'\"”」』\n]{4,120})[’'\"”」』]")

#: 🚨 인용부호 안이라고 다 광고 문구가 아니다. 실측에서 걸러야 했던 것들 —
#:    법문 재인용(「소비자를 속이거나 오인시킬 우려가 있는 광고행위」) · 처분 방식(「사업장공표 문안」) ·
#:    약칭 정의(「이라 한다)」) · 첨부 링크 · 이미지 alt · 마스킹 자국.
NOISE = re.compile(
    r"법률|법 제|제\s?\d+조|시행령|시행규칙|사건번호|피심인|고시|지침|별표"
    # 🔄 2026-09-08 — `공정거래위원회`·`위원회` 를 **통째로 버리던 것**을 좁힌다.
    #    감시 지표가 잡아냈다 — 「독학학위제 학위취득 2016 합격자 배출수 1위, … 및
    #    공정거래위원회 **인정**」이 그 규칙에 걸려 사라지고 있었다.
    #    🔴 이건 **기관 사칭형 거짓·과장 광고**다. 1층이 제일 필요로 하는 종류를 버리고 있었다.
    #    처분 문안(협의)·자료 제출 명령만 좁게 막는다.
    r"|위원회와 ?협의|위원회에 .{0,20}제출"
    r"|flDownload|번째 이미지|이라 한다|사업장공표|공표 ?문안|광고행위|표시행위"
    r"|에 대한 건"  # 🔄 사건명 인용. 예전엔 마스킹 자국 규칙에 딸려 걸렸다 (아래 참조)
    # 🔄 2026-09-07 1회전 실측으로 추가한 둘 —
    #   ① 「별지 기재 문안」류 36건. 처분 **방식**이지 광고 문구가 아니다
    #   ② 마스킹이 이름만 지우고 남긴 법인격 표기가 인용부호에 감싸여 문구로 잡혔다 (2건)
    r"|별지|기재 ?문안|^주식회사$|^유한회사$|^㈜$"
    # 🔄 2026-09-30 — 결정문 자신의 약칭(「'이 사건 광고'라 한다」). 어느 광고인지도 안 알려 준다 —
    #    무혐의 주문(16081 · 16089 · 16095)에서 적법 문구로 들어갈 뻔했다. 이유 쪽 거름(`golden._REASON_DROP` ㅁ)과 같은 자리다
    r"|^이 ?사건 ?(?:광고|표시)"
)

#: 🔄 **2026-09-08 — 「자국이 들어갔다」로 버리던 것을 「알맹이가 없다」로 바꾼다.**
#:
#:    예전 `NOISE` 는 `\[업체\]` 등 **마스킹 자국이 든 인용을 통째로 버렸다.** 실측하니
#:    643 → 619 문구 · 285 → 280 문서가 그렇게 사라졌고, 버려진 15건 중 **7건이 진짜 광고 문구**였다 —
#:      「[업체] 오븐글라스」 · 「인천 [업체] 호텔」 · 「[업체] 가습기살균제」 · 「수성 [업체] 레이크시티」
#:      「한국의 톱밥우사 구조에서는 [업체]만의 특허기술인 … 40두 전후 착유가 한계입니다」
#:    마지막 것은 그 문서의 **유일한** 문구여서, 문서가 통째로 빠지며 **근거절까지** 함께 사라졌다.
#:
#: 🔴 **손실이 무작위가 아니다.** *광고주 이름을 문구에 넣은 광고*만 골라 빠진다 —
#:    라벨이 아니라 **광고 스타일과 상관된 표본 편향**이다. 1.1% 라 작아 보이지만
#:    `mfds_casebook`·`mfds_press` 는 문구 안에 브랜드가 들어가는 것이 기본이라 훨씬 크게 작동한다.
#:
#: ★ `[업체]` 자체는 학습 입력으로 문제가 아니다 — 일관된 **자리표시자**라
#:   모델이 「여기는 상호 자리」로 배운다. 버려야 할 것은 자국이 든 인용이 아니라
#:   **자국을 걷어내면 아무것도 안 남는 인용**이다(인용이 상호뿐이었던 것 — 5건).
#: 🔴 자국의 단일 출처는 `mask.MARK_RE` 다 (D-166). 여기서 다시 만들지 않는다 —
#:    2026-09-08 까지 이 파일이 `[업체]` 꼴을 따로 들고 있었고, 표기를 바꾸는 순간
#:    「상호뿐인 인용」을 못 걸러 학습 입력이 늘어난 것처럼 보였을 것이다.
_MARK = MARK_RE
#: 자국 **뒤에 붙은 조사**까지 걷어내고 센다 — 「[업체]는」의 알맹이는 0 이다.
_MARK_TAIL = re.compile(r"^(?:에게|에서|으로|은|는|이|가|을|를|의|와|과|에|로|도|만)")

#: 표시광고법 제3조 제1항 각 호. 주문의 서술어에 그대로 나온다.
#: 🔗 유형 칸은 `collect/statute.py` 가 호에서 계산한 값과 같아야 한다 — 분할이 대조하고 멈춘다(`split.ftc_docs`) ·
#:    게이트 `tests/test_statute.py` (D-99 · D-282). 이 표가 정하는 것은 **서술어 → 호**다.
#: 🚨 원천이 `·`·`ㆍ`·`.` 를 섞어 써서 `sep_norm` 뒤에 센다 (D-117).
TYPES: list[tuple[str, str, str]] = [
    ("거짓·과장", "거짓_과장", "제3조제1항제1호"),
    ("허위·과장", "거짓_과장", "제3조제1항제1호"),
    ("기만적", "소비자_기만", "제3조제1항제2호"),
    ("부당하게 비교", "부당_비교광고", "제3조제1항제3호"),
    ("비방", "비방광고", "제3조제1항제4호"),
]

#: 「… 아님에도 마치 … 인 것처럼」 — 왜 부당한가가 여기 있다.
GROUND = re.compile(r"([^.。\n]{6,120}?)(?:것처럼|것과 같이)")


def types_in(order: str) -> list[dict[str, str]]:
    """주문에 나타난 위반 유형들. 🚨 **하나가 아니다** — 한 건이 여러 호에 걸린다."""
    seen: list[dict[str, str]] = []
    for word, label, article in TYPES:
        if word in order and all(x["label"] != label for x in seen):
            seen.append({"word": word, "label": label, "article": article})
    return seen


def content_len(q: str) -> int:
    """마스킹 자국과 그에 붙은 조사를 걷어낸 **알맹이 길이**.

    🚨 「[업체]」·「[업체]는」은 0 이다 — 인용이 상호뿐이었던 것이라 학습 입력으로 값이 없다.
       반면 「[업체] 오븐글라스」는 5 다 — **판정 대상이 남아 있다.**
    """
    parts = _MARK.split(q)
    rest = parts[0] + "".join(_MARK_TAIL.sub("", x, count=1) for x in parts[1:])
    return len(rest.strip())


# ══ 주문의 처분 — 조항마다 다르다 (2026-09-30 · D-237 · D-255 ③) ═══════════════════════
#  ⛔ 종전에는 주문 **전체**에서 유형어를 찾고, 뽑힌 문구 전부에 그 유형을 붙였다.
#     「…광고한 행위는 표시ㆍ광고의 공정화에 관한 법률 제3조 제1항에 위반되지 아니한다」 뒤에 심사보고서의
#     혐의 내용(「거짓ㆍ과장의 광고로서 …」)이 이어 붙은 주문(16081 · 16089 · 16095)에서 **무혐의 문구가 위반 양성**이
#     됐다 — 봉인 평가 4행 · 학습 7행(검토 2026-09-30 §1-2). 원천이 「위반 아님」이라 한 것을 뒤집은 셈이다(D-237).
#  ⛔ 뒷광고(경제적 이해관계 미공개) 사건의 인용은 상품명이다 — 위반은 표시하지 않은 것이라 문구에 없다.
#     D-255 ③ 이 범위 밖으로 정했는데 봉인 평가에 24행이 들어가 있었다.
#  ★ 주문을 **항목**(「1.」 · 「가.」)으로 나누고 항목마다 처분을 읽는다. 유형은 **위반 항목에서만** 센다.
#  🚨 항목은 머리가 아닐 수 있다 — 「다음과 같이 … 광고행위를 다시 하여서는 아니 된다. 1. … 2. …」의 1 · 2 는 **머리 아래 행위**다.
#     그래서 처분 말이 없는 항목은 **앞의 머리**(위반 · 적법 · 종결)를 따른다(표본 857 문서 실측 — 10365 · 2963 · 8577).
#  🚨 [임의] 정규식이다 — 항목 머리가 번호도 글자도 아닌 주문(한 문단)은 통째로 한 항목이다.
_UNIT_HEAD = re.compile(r"(?<![가-힣\d])(?:\d{1,2}|[가-하])\s*\.(?!\d)\s*[^\s.\d]")


def _units(order: str) -> list[str]:
    """항목으로 자른다. 🚨 항목 머리는 **줄 머리** 또는 **문장 끝(글자 뒤 마침표) 다음**에만 선다 —
    「2022. 4. 19. 인터넷 신문」의 날짜 · 「위 1.의 행위」를 자르지 않는다(857 문서 실측 · 19183)."""
    cuts = [0]
    for m in _UNIT_HEAD.finditer(order):
        p = m.start()
        before = order[:p].rstrip(" \t")
        if p == 0 or not before:
            continue
        if before.endswith("\n") or (
            before.endswith(".") and len(before) >= 2 and not before[-2].isdigit()
        ):
            cuts.append(p)
    cuts.append(len(order))
    return [order[a:b] for a, b in zip(cuts, cuts[1:], strict=False) if order[a:b].strip()]


#: 원천이 위법이 아니라고 한 항목 · 판단 없이 닫은 항목
#: 🔄 2026-10-03 — 「법 위반에 해당하지 아니한다」 꼴을 더했다. 이 꼴을 못 읽어 16739 의 5 항(주행보조 프로그램 광고는
#:    위반 아님)의 문구 둘이 위반 양성으로 학습 쪽에 들어가 있었다(8,272 문서 실측 — 이 꼴은 그 문서 하나 · 원장 10-03 ⑫)
_LAWFUL = re.compile(r"위반되지\s*(?:아니|않)|위반에\s*해당(?:하지|되지)\s*(?:아니|않)|무혐의")
_CLOSED = re.compile(r"심의\s*절차를\s*종료|종결\s*처리")
#: 처분을 명하는 머리 — 시정명령 · 경고 · 고발
_ORDER = re.compile(r"하여서는\s*아니\s*된다|하여야\s*한다|경고한다|고발한다")
#: 처분에 딸린 항목 — 과징금 · 공표 · 통지의 **명령 꼴**. 🚨 **무엇이 위반인지 말하지 않는다** — 위반으로 세면
#:    뒷광고 사건(「1. 대가 미공개 … 2. 과징금」)이 위반 문서가 된다(표본 실측)
_ANCILLARY = re.compile(
    r"납부하여야|공표하여야|통지하여야|게재함으로써|과징금액\s*[:：]|납부\s*기한\s*[:：]|납부\s*장소\s*[:：]|납\s*부\s*처\s*[:：]"
)
_PROHIBIT = re.compile(r"하여서는\s*아니\s*된다|경고한다")
#: 뒷광고 — 경제적 이해관계(대가)를 **밝히지 않은** 것이 위반인 항목 (D-255 ③)
_ENDORSE = re.compile(r"경제적\s*(?:이해\s*관계|대가)")
_HIDE = re.compile(r"공개하지|은폐|누락|밝히지|표시하지")


def _own_kind(c: str) -> str:
    """항목 **자기 글**만으로 본 처분 — `적법` · `종결` · `뒷광고` · `부수` · `머리` · `행위`."""
    if _LAWFUL.search(c):
        return "적법"
    if _CLOSED.search(c):
        return "종결"
    if _ENDORSE.search(c) and _HIDE.search(c):
        return "뒷광고"
    if _ANCILLARY.search(c) and not _PROHIBIT.search(c):
        return "부수"
    if _ORDER.search(c):
        return "머리"
    return "행위"


def clauses(order: str) -> list[tuple[str, str]]:
    """주문 → `(처분, 항목 글)`. 처분은 `위반` · `적법` · `종결` · `뒷광고` · `기타`.

    ★ `행위` 항목(처분 말이 없다)은 **앞의 머리**를 따른다 — 위반 머리 아래면 위반, 무혐의 아래면 적법(16095 의 심사보고서 인용).
    🚨 `부수`(과징금 · 공표)와 머리가 없는 앞자리 `행위` 는 `기타` 다 — 문서 처분(`doc_disposition`)이 정한다.
    """
    out: list[tuple[str, str]] = []
    head = "기타"
    for c in _units(order):
        own = _own_kind(c)
        if own == "머리":
            head = k = "위반"
        elif own in ("적법", "종결"):
            head = k = own
        elif own == "뒷광고":
            k = own
            if _ORDER.search(c):  # 머리 자체가 뒷광고 — 아래 행위도 뒷광고다
                head = own
        elif own == "부수":
            k = "기타"
        else:
            k = head
        out.append((k, c))
    return out


def doc_disposition(cls: list[tuple[str, str]]) -> str:
    """문서 전체의 처분 — `기타` 조항의 문구가 어디로 갈지 정한다.

    위반 조항이 있으면 `위반` · 없고 적법이 있으면 `적법` · 뒷광고가 있으면 `뒷광고` · 종결이 있으면 `종결` ·
    어느 것도 없으면 `위반`(고발 · 이의신청 기각처럼 처분 말이 다른 꼴 — **종전 동작 그대로** 문서 유형을 따른다).
    🚨 `기타` 는 떨어뜨리지 않는다 — 16095 의 무혐의 문구는 「1. 심사보고서상 혐의 내용」 조항 안에 있다.
    """
    kinds = {k for k, _ in cls}
    for k in ("위반", "적법", "뒷광고", "종결"):
        if k in kinds:
            return k
    return "위반"


def place(phrases: list[str], cls: list[tuple[str, str]]) -> dict[str, list[str]]:
    """문구마다 처분을 붙여 나눈다 — `{"위반": […], "적법": […], "버림": […]}`.

    ★ 문구가 든 조항의 처분을 따른다. 위반 조항과 적법 조항에 **같이** 들면 위반이다(원천이 위반이라 적은 자리가 있다).
    🚨 공백을 접어 찾는다 — 원천은 조항 안에서 줄을 바꾼다.
    """
    whole = doc_disposition(cls)
    flat = [(k, _WS_ALL.sub("", c)) for k, c in cls]
    out: dict[str, list[str]] = {"위반": [], "적법": [], "버림": []}
    for p in phrases:
        key = _WS_ALL.sub("", p)
        kinds = {k for k, c in flat if key and key in c} or {"기타"}
        kinds = {whole if k == "기타" else k for k in kinds}
        if "위반" in kinds:
            out["위반"].append(p)
        elif "적법" in kinds:
            out["적법"].append(p)
        else:  # 뒷광고(D-255 ③) · 종결(판단 없음)
            out["버림"].append(p)
    return out


_WS_ALL = re.compile(r"\s+")


def violation_text(cls: list[tuple[str, str]]) -> str:
    """유형을 셀 글 — **위반 조항만**. 위반 조항이 없는 문서는 빈 글이다(유형 없음)."""
    return "\n".join(c for k, c in cls if k == "위반")


def phrases_in(order: str) -> list[str]:
    """주문에서 광고 문구 원문만. 🚨 이미 마스킹을 지난 문자열을 받는다."""
    out: list[str] = []
    for q in QUOTE.findall(order):
        q = FOOTNOTE.sub("", q).strip()
        if len(q) < 4 or q.isdigit() or NOISE.search(q):
            continue
        if content_len(q) < 4:  # 🔄 자국을 걷어내면 아무것도 안 남는 인용 (2026-09-08)
            continue
        if q not in out:
            out.append(q)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 결정문 주문 → 1층 라벨 삼요소")
    ap.add_argument("--dump", action="store_true", help=f"{OUT} 로 쓴다")
    ap.add_argument(
        "--stage",
        action="store_true",
        help=f"{STAGE} 에 단계 산출물을 적고 **지난 판과 맞대 본다** (D-143)",
    )
    ap.add_argument(
        "--trace",
        action="store_true",
        help="🔴 치환된 **원문**을 화면에 찍는다 (진단용). 저장 경로와 같이 쓸 수 없다",
    )
    a = ap.parse_args()

    # 🔴 진단과 저장을 같이 켤 수 없다 (D-165). 켤 수 있게 두면 언젠가 켠 채로 돈다.
    if a.trace and (a.stage or a.dump):
        print(
            "🔴 --trace 는 --stage·--dump 와 같이 쓸 수 없다.\n"
            "   원문은 화면에서만 본다 — 파일로 나가면 그때부터 보관이다 (D-17 · D-165).",
            file=sys.stderr,
        )
        return 1

    if not RAW.exists():
        print(f"🚨 {RAW} 가 없다 — 먼저 uv run python -m collect.ftc_body")
        return 1

    rows: list[dict] = []
    buck = collections.Counter()
    lab = collections.Counter()
    docs_with = 0

    # 🔴 **과잉삭제 계측** (D-142 (다) · 2026-09-08).
    #    마스킹은 **모자라도 실패, 지나쳐도 실패**인데 지나친 쪽만 계측이 없었다.
    #    실제로 643 → 619 문구 · 285 → 280 문서가 삼켜지고 있었고 **재기 전까지 아무도 몰랐다.**
    #    그래서 여기서는 늘 마스킹 **전**으로도 뽑아 맞대 본다 (비용은 정규식 한 벌).
    # 🔴 **정규화 계측** (D-154). 사슬에서 유일하게 안 세던 단계다.
    #    D-117 이 「정규화를 안 거치고 classify 를 부르면 135건이 샌다」를 **한 번** 쟀고
    #    그 뒤로 아무도 안 쟀다. 원천의 구분자 습관이 바뀌면 분류가 **조용히** 달라진다.
    #    ★ 일회성 사실을 **상시 수치**로 바꾼다 — 오늘 D-142·D-143 이 한 것과 같은 일이다.
    norm_shift: collections.Counter[tuple[str, str]] = collections.Counter()
    stage_rows: list[dict] = []
    raw_ph = raw_docs = 0
    #: 🆕 「이유」 회수 계측 (D-232 (A))
    reason_ph = reason_docs = gained_docs = gained_ph = 0
    #: 🚨 **늘 우는 지표는 무시당한다.** 그래서 「줄었다」가 아니라 **버린 근거**로 가른다.
    #:
    #: ⛔ 첫 판은 사라진 문구를 **한 개씩 다시 마스킹**해서 알맹이가 남는지 봤다. 틀렸다 —
    #:    2패스(`doc_org_names`)는 **문서 전체**에서 이름을 캐므로, 문구만 떼어 마스킹하면
    #:    덜 지워진다. 「현대에이치씨엔」이 그렇게 「먹혔다」로 잡혔다. 실제로는 정상 마스킹이다.
    #:
    #: ★ 그래서 **마스킹을 지난 주문의 인용**만 본다. 그중 알맹이가 4자 이상인데
    #:   `NOISE` 로 버려진 것이 **필터가 삼킨 것**이다 — 오늘 고친 것이 정확히 이 자리다.
    watch: list[tuple[str, str]] = []
    #: 🆕 2026-09-30 — 문서 처분 · 문구 처분 셈 (「안 셌다」와 「0 이다」를 가른다)
    disp: collections.Counter = collections.Counter()
    placed: collections.Counter = collections.Counter()

    for p in store.current_files(RAW, "*.xml"):
        blob = p.read_bytes()
        r = ET.parse(p).getroot()
        raw = {f: _text(r, f) for f in ("사건명", "주문", "결정요지", "이유")}
        # 🔴 **정규화문과 원문을 둘 다 든다** (2026-09-08 · D-152).
        #    ⛔ 예전에는 `sep_norm` 을 한 번 걸고 그 결과로 **분류도 하고 저장도** 했다.
        #       `preprocess/text.py` 가 「매칭 직전에만 쓴다 · 원문을 보관한다」고 적어 뒀는데
        #       호출부가 어겼다. 실측 — 저장된 627문구 중 **70건(11.2%)이 망가져 있었다**:
        #         「명중률 97.5%」→「97·5%」 · 「2.5배」→「2·5배」 · 「1/3」→「1·3」
        #         「www.youtube.com」→「www·youtube·com」 · 문장 마침표 65건
        #    🔴 **수치가 망가지면 거짓·과장 판정의 근거가 사라진다.**
        name, order, gist, reason = (sep_norm(raw[f]) for f in raw)
        k = classify(name, order, gist, reason)
        # 🚨 원문으로도 분류해 본다 — **저장에는 쓰지 않는다**. 세기만 한다.
        k_raw = classify(raw["사건명"], raw["주문"], raw["결정요지"], raw["이유"])
        if k_raw != k:
            norm_shift[(k_raw, k)] += 1
        buck[k] += 1
        seq = _text(r, "결정문일련번호")
        if k not in CORE:
            # 🚨 후보가 아닌 것도 한 줄 적는다 — `classify` 를 고쳤을 때 **분류 이동**이 보인다
            stage_rows.append({"seq": seq, "src": stage.src_hash(blob), "분류": k})
            continue

        # 🔴 뽑기 **전에** 마스킹한다. 뽑은 뒤에 걸면 문구 안의 업체명이 남는다.
        _, bare = anchor_ftc(r)
        # 🔴 **치환 원장** (D-144). 무엇을 몇 번 바꿨는지 적는다.
        #    🔄 2026-09-08 D-165 — **원문은 안 담는다.** 예전에는 담았고, 그래서
        #       `ftc_stage.jsonl` 에 실명 6건·괄호원어 14건·주소 36건이 남아 있었다.
        #       ★ 배포물(`rows`→`OUT`)과 자료구조가 분리돼 있어 배포되진 않았다 —
        #         그 방어는 유효했다. 다만 문서는 「원문 미보관」을 말하고 있었다.
        #    ★ `--trace` 로 볼 수 있고, 그 경로는 **저장을 거부한다.**
        mlog = Trace() if a.trace else Ledger()
        # 분류·유형 판별은 **정규화문**으로 한다 (D-117 — 원문으로 classify 하면 135건이 샌다)
        # 🔄 2026-09-30 — 유형은 아래 `violation_text(cls)` 를 정규화해 센다(항목은 원문에서만 보인다)
        # 🔴 저장은 **원문**으로 한다. 원장도 이쪽에 건다 — 나가는 것이 이쪽이다
        masked_raw = apply_policy(raw["주문"], bare, "ftc", mlog)

        # 🔴 계측 — 마스킹을 지나지 않은 문구. **산출물에는 쓰지 않는다** (D-17).
        before = phrases_in(raw["주문"])
        raw_ph += len(before)
        raw_docs += bool(before)

        ps = phrases_in(masked_raw)

        # 🆕 **「이유」 회수** (2026-09-17 · D-232 (A) · 팀장 판정 「켜고 측정」).
        #    ⛔ 종전에는 **주문만** 봤다. 의결서는 「이유 → 인정사실」에 광고 원문을 싣고,
        #       주문은 *「…것처럼 소비자를 속이는 광고행위를 다시 하여서는 아니 된다」* 같은
        #       서술형이라 인용이 없다 — CORE 854건 중 **571건이 그래서 빠졌다**.
        #    🔴 **주문 문구와 섞지 않는다.** 별도 필드로 담는다 — 이유에는 타사 광고·법문
        #       재인용·매물 표시가 섞이고(실측 채택률 39.7%), 섞으면 **한 숫자가 두 과제를
        #       평균한 수**가 된다 (D-172). 섞을지는 이 수를 보고 판정한다 (D-205).
        #    🚨 치환 원장도 **따로 든다** — 합치면 「주문 치환 418건」 같은 기존 단계 수치가
        #       움직여 D-143 의 판 대조가 어긋난다.
        rlog = Trace() if a.trace else Ledger()
        masked_reason = apply_policy(raw["이유"], bare, "ftc", rlog)
        rs = phrases_in(masked_reason)
        reason_ph += len(rs)
        reason_docs += bool(rs)
        if rs and not ps:
            gained_docs += 1
            gained_ph += len(rs)

        # 🆕 2026-09-30 — **조항마다 처분을 읽는다** (D-237 · D-255 ③ · 위 `clauses` 머리말).
        #    🚨 원문(마스킹 뒤) 주문으로 나눈다 — `sep_norm` 은 「1.」의 마침표를 바꿔 조항 머리가 안 보인다.
        cls = clauses(masked_raw)
        whole = doc_disposition(cls)
        disp[whole] += 1
        by = place(ps, cls)
        # 이유 문구는 조항 자리가 없다 — 문서 처분을 따르고, 주문의 적법·버림 문구와 같은 글자면 그쪽을 따른다
        ok_keys = {_WS_ALL.sub("", x) for x in by["적법"]}
        drop_keys = {_WS_ALL.sub("", x) for x in by["버림"]}
        rby: dict[str, list[str]] = {"위반": [], "적법": [], "버림": []}
        for q in rs:
            key = _WS_ALL.sub("", q)
            if (
                whole in ("뒷광고", "종결") or key in drop_keys
            ):  # 문서가 범위 밖이거나 판단 없이 닫혔다
                rby["버림"].append(q)
            elif whole == "적법" or key in ok_keys:
                rby["적법"].append(q)
            else:
                rby["위반"].append(q)
        for part, got in (("주문", by), ("이유", rby)):
            for kk, v in got.items():
                placed[(part, kk)] += len(v)
        ps_all = list(ps)  # 필터 감시(`watch`)는 처분과 상관없이 **뽑힌 것 전부**를 본다
        ps, ps_ok, rs, rs_ok = by["위반"], by["적법"], rby["위반"], rby["적법"]

        stage_rows.append(
            {
                "seq": seq,
                "src": stage.src_hash(blob),
                "분류": k,
                "사건명": apply_policy(raw["사건명"], bare, "ftc"),  # 🔴 원문 (D-152)
                "주문_마스킹": masked_raw,
                "문구": ps,
                "문구_이유": rs,  # 🆕 D-232 (A)
                # 🆕 2026-09-30 — 원천이 위반 아님이라 한 문구(D-237) · 버린 문구(뒷광고 D-255 ③ · 판단 없음)
                "처분": whole,
                "문구_적법": ps_ok,
                "문구_이유_적법": rs_ok,
                "문구_버림": by["버림"] + rby["버림"],
                "치환원장": mlog,
                "치환원장_이유": rlog,  # 🆕
            }
        )
        for q in QUOTE.findall(masked_raw):
            q = q.strip()
            if q in ps_all or content_len(q) < 4 or q.isdigit():
                continue
            hit = NOISE.search(q)
            watch.append((hit.group(0) if hit else "🔴미분류", q))
        # 🔴 **주문에 문구가 없어도 이유가 있으면 담는다** (2026-09-17 · D-232 (A)).
        #    ⛔ 종전에는 여기서 `continue` 라 571건이 `rows` 에 못 들어갔다.
        if not (ps or rs or ps_ok or rs_ok):
            continue
        docs_with += bool(ps)
        # 🔄 2026-09-30 — 유형은 **위반 조항에서만** 센다(무혐의 조항 · 심사보고서의 「거짓ㆍ과장」을 세지 않는다)
        ts = types_in(sep_norm(violation_text(cls)))
        for t in ts:
            lab[t["label"]] += 1
        grounds = [m.group(1).strip() for m in GROUND.finditer(masked_raw)][:3]
        rows.append(
            {
                "seq": seq,
                "결정일자": _text(r, "결정일자"),
                "분류": k,
                # 🆕 2026-10-05 — 사건에 적용된 법. `split.ftc_docs()` 가 읽어 표시광고법 사건만 남긴다(원장 10-03 ㊿-27)
                "적용법": case_law(name, order, gist, reason),
                "사건명": apply_policy(name, bare, "ftc"),
                "문구": ps,
                "문구_이유": rs,  # 🆕 D-232 (A) — 섞지 않는다
                # 🆕 2026-09-30 — 조건 L(적법) 문구. 유형이 붙지 않는다 — 원천이 위반 아님이라 했다 (D-237)
                "문구_적법": ps_ok,
                "문구_이유_적법": rs_ok,
                "유형": ts,
                "근거절": grounds,
            }
        )

    print("  🆕 주문 처분 (2026-09-30 · D-237 · D-255 ③) — 문서")
    for kk, c in disp.most_common():
        print(f"    {kk:6} {c:>5,}")
    print(
        "  🆕 문구 처분 — 🔴 버림 = 뒷광고(범위 밖) · 판단 없이 닫힌 조항 · 적법 = 원천이 위반 아님이라 한 문구"
    )
    for (part, kk), c in sorted(placed.items()):
        print(f"    {part} {kk:4} {c:>6,}")
    print()
    total_core = sum(buck[k] for k in CORE)
    n_ph = sum(len(x["문구"]) for x in rows)
    print(f"결정문 {sum(buck.values()):,}건 · 1층 후보 {total_core:,}건")
    print(f"  주문에 광고 문구가 있는 문서  {docs_with:,}건 ({docs_with * 100 // total_core}%)")
    print(f"  뽑은 문구                    {n_ph:,}개 (문서당 {n_ph / max(docs_with, 1):.1f})")
    print()
    # 🆕 **「이유」 회수 계측** (D-232 (A) · 2026-09-17)
    n_rs = sum(len(x["문구_이유"]) for x in rows)
    print("  🆕 「이유」 회수 (D-232 (A)) — 🔴 주문 문구와 **섞지 않았다**")
    print(f"    이유에 문구가 있는 문서      {reason_docs:,}건 / {total_core:,}")
    print(f"    이유에서 뽑은 문구          {reason_ph:,}개")
    print(f"    🔴 **주문 X · 이유 O**      {gained_docs:,}건 · 문구 {gained_ph:,}개  ← 회수분")
    print(f"    `rows` 에 담긴 이유 문구     {n_rs:,}개")
    print("    🚨 이 수는 판정이 아니다 — 이유에는 타사 광고·법문 재인용·매물 표시가 섞인다")
    print("       (표본 실측 채택률 39.7% · D-232). 섞을지는 이 수를 보고 판정한다 (D-205)")
    print()
    n_shift = sum(norm_shift.values())
    print("  🔵 정규화 계측 — **구분자를 펴지 않으면 분류가 달라지는 문서** (D-154)")
    print(
        f"    {n_shift:,}건 / {sum(buck.values()):,}  — 원천이 `·`·`ㆍ`·`.` 를 섞어 쓰기 때문이다"
    )
    # 🚨 루프 변수를 `a` 로 쓰지 않는다 — argparse 네임스페이스가 `a` 다 (방금 덮어서 죽었다).
    for (was, now), cnt in norm_shift.most_common(6):
        core = " ★1층 후보로 들어옴" if now in CORE and was not in CORE else ""
        print(f"      {cnt:>5}  {was or '(분류없음)'} → {now or '(분류없음)'}{core}")
    gained = sum(c for (w, n), c in norm_shift.items() if n in CORE and w not in CORE)
    lost = sum(c for (w, n), c in norm_shift.items() if w in CORE and n not in CORE)
    print(f"    ★ 1층 후보 기준 — 정규화로 **들어온 것 {gained:,} · 나간 것 {lost:,}**")
    print("    🚨 이 수가 0 이 되면 원천이 구분자를 안 섞는다는 뜻이다 — 그때 다시 판단한다")
    print()
    print("  🔴 마스킹 과잉삭제 계측 — **지나친 쪽 실패는 조용하다** (D-142)")
    print(f"    마스킹 전  문서 {raw_docs:,} · 문구 {raw_ph:,}")
    print(f"    마스킹 후  문서 {docs_with:,} · 문구 {n_ph:,}   (차 {raw_ph - n_ph:+,})")
    print("    차이는 **상호뿐인 인용·약칭 정의**가 마스킹 뒤 빈 껍데기가 된 것이다 — 정상")
    print()
    print(f"  🔎 필터 감시 — 알맹이가 남는데 버린 인용 {len(watch):,}건, **버린 근거별**")
    print("     🚨 여기 광고 문구가 섞이면 학습 입력이 소리 없이 준다 (2026-09-08 에 7건이 그랬다)")
    by = collections.Counter(k for k, _ in watch)
    for k, c in by.most_common():
        ex = next(q for kk, q in watch if kk == k)
        print(f"    {c:>5}  {k:12s} 예: {ex[:60]}")
    print(
        "     ★ 근거가 「🔴미분류」인 것은 `NOISE` 가 아니라 **길이·중복**으로 빠진 것이다 — 여기를 본다"
    )
    print()
    print("  유형별 문서 수 — 🚨 한 건이 여러 호에 걸리므로 합이 문서 수를 넘는다")
    for label, c in lab.most_common():
        mark = "★" if c >= 30 else "🚨"  # D-40 — 30건 미만은 「측정 불가」
        print(f"    {mark} {label:16s} {c:>4}건")
    if any(c < 30 for c in lab.values()):
        print("    🚨 30건 미만 유형은 D-40 상 「측정 불가」다 — 홀드아웃을 세울 수 없다")
    print()
    no_type = [x for x in rows if not x["유형"]]
    print(f"  유형을 못 붙인 문서  {len(no_type):,}건 — 주문에 유형어가 없다")
    if no_type:
        print(f"    예: {no_type[0]['seq']} {no_type[0]['문구'][:2]}")
        print(
            "    🚨 유형은 문구가 아니라 **주문의 서술어**에서 온다. 없으면 「근거절」로 사람이 붙인다"
        )

    if a.trace:
        print("\n🔴 치환된 원문 — **화면에만 찍는다. 저장되지 않는다** (D-165)")
        seen = 0
        for row in stage_rows:
            for m in row["치환원장"]:
                if "원문" in m:
                    print(f"    {row['seq']:>7}  {m['규칙']:12} {m['원문'][:40]!r} → {m['자리']}")
                    seen += 1
        print(f"  총 {seen:,}건. 🚨 이 화면을 파일로 옮기지 않는다 — 필요하면 다시 돌린다.")

    if a.stage:
        print()
        prev = stage.load(STAGE)
        stage.save(STAGE, stage_rows)
        stage.report(stage.compare(prev, stage.load(STAGE)))
        print(f"    → {STAGE}")

    if a.dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n"
        )
        print(f"\n→ {OUT}")
    else:
        print("\n(--dump 를 주면 파일로 쓴다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
