#!/usr/bin/env python3
"""derived_manifest.py — **파생물 원장** (기기 사이 동등성 · D-19 의 짝).

  uv run python scripts/derived_manifest.py             # 표만 찍는다 (쓰지 않는다)
  uv run python scripts/derived_manifest.py --write     # data/derived_manifest.jsonl
  uv run python scripts/derived_manifest.py --check      # 원장 ↔ 디스크 대조 (종료코드)

──────────────────────────────────────────────────────────────
🚨 **왜 필요한가 — `data/manifest.jsonl` 은 raw 전용이다.**

    원장(raw)   20,395행 · sha256 전부 있음 · **git 으로 공유된다**
    원장(파생물) **없었다** — 그래서 「네가 받은 파생물이 내 것과 같은가」를 물을 수 없다

`RAW_READERS = {"collect","preprocess"}`(게이트)라 `scripts/`·`app/`·`db/` 는 전부
파생물만 읽는다. 즉 **팀원은 raw 없이 `golden` 아래 전부를 돌릴 수 있다.**
그 길을 쓰려면 파생물에도 원장이 있어야 한다 — 이 파일이 그것이다.

──────────────────────────────────────────────────────────────
🔴 **부류가 넷이다. 이것이 「무엇을 git 에 넣는가」를 정한다.** (정본은 아래 `KIND_RULES`)

    원천    사람의 판정이다. **어떤 명령으로도 다시 안 나온다.** 잃으면 끝이다
            → `data/derived/labels/**`
    표본    명령으로 다시 나오지만 **다시 뽑으면 그 표본이 아니다.**
            갈리면 그때까지 채운 라벨과 평가 수치가 비교 불가가 된다
            → `*_labelsheet.jsonl` · `golden/split_manifest.json`
    생성물  명령이 같은 입력에서 같은 것을 낸다. 옮기지 않아도 다시 만들 수 있다
    원문캐시 마스킹 전 원문 조각이다(2026-09-17 추가). raw 와 같은 자리 — **옮기지 않는다**
            → `mfds_press_pdf/`

★ **원천·표본은 git 으로, 생성물은 파일로 옮기고 원장만 git 으로** — raw 와 같은 구조다.
🔄 **2026-09-20 (D-249) — 원천·표본도 공유 저장소로 옮긴다. git 은 `GIT_CARRIES` 만 나른다.**
   ⛔ 이 저장소는 **공개**다. 라벨 시트와 사람 라벨에 **인용 광고 문구 원문**이 들어 있어 git 이 그것을 공개하고 있었다.
   ★ 옮기는 길은 D-247 의 저장소(팀 비공개) 하나다 — 정본이 올리고 사본이 받는다. 이미 올라간 이력은 지우지 않는다(팀장 판정).

──────────────────────────────────────────────────────────────
🚨 **만든 명령을 손으로 적지 않는다** (D-99).

모듈이 어느 파생물에 쓰는지는 **코드에 이미 있다.** AST 로 훑어 경로 상수를 모은다 —
문자열 `"data/derived/x.jsonl"` 과 분절 `ROOT / "data" / "derived" / "x.jsonl"` 둘 다 본다
(게이트 `_path_segments` 가 같은 이유로 둘을 본다 — 분절 표기가 검사를 지나간 적이 있다).

🔴 **쓰는 곳을 못 찾은 파생물이 있으면 멈춘다** (D-72 fail-closed).
   분류 없는 파일이 조용히 묶음에 섞이면 **재배포 가부를 모르는 채로 나간다.**
"""

from __future__ import annotations

import argparse
import ast
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 🔴 **스크립트로 실행하면 `collect` 가 엉뚱한 파일로 풀린다** (2026-09-19 실측 · 클론 B).
#    `python scripts/derived_manifest.py` 는 sys.path[0] 이 `scripts/` 라 `from collect import env` 가
#    패키지 `collect/` 가 아니라 **`scripts/collect.py`** 를 집었고, 그것이 `app` 을 못 찾아 죽었다 —
#    런처 42번(`derived-manifest --check`)이 이 경로다. pytest 는 `pythonpath=["."]` 라 **못 잡았다.**
#    ★ 레포 루트를 맨 앞에 둔다. `tests/test_derived_manifest.py` 가 스크립트 경로로 한 번 돌려 본다.
if sys.path[:1] != [str(ROOT)]:
    sys.path.insert(0, str(ROOT))
DERIVED = ROOT / "data" / "derived"
OUT = ROOT / "data" / "derived_manifest.jsonl"
SCAN_DIRS = ("preprocess", "scripts", "collect")

#: 부류 — 경로 패턴으로 판정한다. 위에서부터 먼저 맞는 것.
#: 🚨 이 셋만 손으로 적는다. 「만든 명령」은 코드에서 나온다.
KIND_RULES: tuple[tuple[str, str, str], ...] = (
    # 🔴 **원문 캐시가 `data/derived` 안에 섞여 있다** (2026-09-17 실측 · 내 층 구분 오류).
    #    `preprocess/mfds_press.py:165` 의 `CACHE` 는 「PDF 의 표들. 캐시가 PDF 보다 새로우면
    #    그것을 쓴다」다 — **마스킹 전 원문**이고, 마스킹은 그 뒤 `--dump` 경로에서
    #    `mfds_press_labels.jsonl` 에 적용된다(그 파일은 잔여 0).
    #    ⛔ 그래서 「derived 는 마스킹을 지난 층」이 **캐시에는 참이 아니다.**
    #    ★ 캐시는 raw 와 같은 자리다 — **묶음에 넣지 않는다.** raw 가 없는 기기는
    #      어차피 `extract` 를 못 돌리므로 캐시가 없어도 잃는 것이 없다.
    ("원문캐시", "mfds_press_pdf/", "마스킹 전 원문 캐시 — raw 와 같은 자리다. 묶음에서 뺀다"),
    ("원천", "labels/", "사람의 판정 — 어떤 명령으로도 다시 안 나온다"),
    ("표본", "_labelsheet.jsonl", "다시 뽑으면 그 표본이 아니다 — 라벨과 κ 가 갈린다"),
    ("표본", "golden/split_manifest.json", "다시 나누면 평가 누수 방어와 수치 비교가 무너진다"),
)
DEFAULT_KIND = "생성물"

#: 🔄 2026-09-20 (D-249) — **git 이 나르는 파생물.** 🚨 공개 저장소다 — 인용 원문이 든 파일은 여기 두지 않는다.
#:    `split_manifest.json` 은 문서 id · 분할 · 입력 sha 뿐이라 남긴다. `.gitignore` 예외와 같아야 한다(게이트가 대조).
GIT_CARRIES: frozenset[str] = frozenset({"data/derived/golden/split_manifest.json"})

#: 저장소가 옮기는 부류 — 원문캐시만 뺀다(마스킹 전 원문 · D-17 · D-244).
STORE_KINDS: frozenset[str] = frozenset({"원천", "표본", "생성물"})


def moved(path: str, kind: str) -> bool:
    """공유 저장소가 옮기는가 (D-247 · D-249). git 이 나르는 것과 원문캐시는 아니다."""
    return kind in STORE_KINDS and path not in GIT_CARRIES


#: 🚨 **저장소 안에 만드는 코드가 없는 파생물.** 이름과 사유를 여기 적는다.
#:    ⛔ 검사를 약하게 두지 않고 목록으로 둔다 — 게이트의 `RAW_EXCEPTIONS` 와 같은 자리.
#:    ★ 만드는 코드가 없다는 것은 **다시 만들 수 없다**는 뜻이므로 부류는 자동으로 「원천」이다.
#:      즉 이 목록에 오르는 순간 공유 저장소로 따라가야 하는 것이 된다 (🔄 D-249 — 종전 「git」).
UNWRITTEN: dict[str, str] = {
    # 🔄 2026-09-17 — 비었다. `casebook2021_labelsheet.jsonl` 이 여기 있었는데
    #    전사기를 `scripts/casebook2021_sheet.py` 로 커밋해 **1차 대조로 넘어갔다**
    #    (재생성 결과가 기기 파일과 바이트 동일 · sha 999710e20ac3 · 161,601 B).
    #    ★ 이 목록이 비어 있는 것이 정상이다. 여기 이름이 늘면 「한 기기에만 사는 원천」이 늘었다는 뜻이다.
}


#: 🔴 **반출 전 검사** — 마스킹이 실제로 됐는가 (D-17 · D-78 ③).
#:    ⛔ 게이트 `test_derived_로_나가는_원문은_마스킹을_지난다` 는 스스로 적어 두었다:
#:       *"import 만 본다. 「제대로 마스킹했는가」는 이 게이트가 못 본다."*
#:       그래서 **코드를 고친 뒤에도 낡은 산출물이 그대로 남는다** — 실측 2026-09-17:
#:       `ftc_layer1_triage.json` 은 `ftc_triage.py` 가 `mask` 를 들게 고쳐진 뒤에도
#:       **09-06 판이 그대로 있어 법인 표기 6,082건**을 싣고 있었다. 아무도 읽지 않는 파일이라
#:       지표로도 안 보였다. 묶음에 넣으면 그 6,082건이 같이 나간다.
#: 🚨 **실명이 붙은 법인 표기만** 센다. 원천이 이미 `ㅇㅇㅇ`·`000` 으로 가려 준 것과,
#:    「'주식회사'는 생략한다」처럼 **낱말로 쓰인 것**은 세지 않는다 — 실측으로 확인했다:
#:    성긴 패턴은 우리 추출물에서 12건을 잡았는데 전부 그 두 꼴이었다(거짓 양성).
#:    좁힌 뒤 우리 추출물 **0건** · 낡은 `ftc_layer1_triage.json` **2,972건**으로 갈렸다.
#: ⚠️ 이것은 **거름망**이지 증명이 아니다. 법인 표기가 없는 이름(개인·상호)은 못 잡는다 —
#:    그 잔여를 재는 것은 `preprocess/mask.py --survey` 의 일이다 (D-110).
_LEAK_NAME = r"(?![ㅇ○0]+)[가-힣A-Za-z][가-힣A-Za-z0-9]{1,}"
LEAK_PAT = re.compile(rf"(?:{_LEAK_NAME}\s*(?:㈜|\(주\))|(?:주식회사|유한회사)\s*{_LEAK_NAME})")

#: 법인 표기가 **정당하게** 남는 파일. 이름과 사유를 적는다 (검사를 약하게 두지 않는다).
LEAK_ALLOW: dict[str, str] = {
    "law_decc.jsonl": "법제처 결정례 원문 — 당사자명이 관보에 공표된 판단문의 일부다 (공공저작물)",
    "law_prec.jsonl": "법제처 판례 원문 — 같은 이유",
}


def leaks() -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """(파생물 잔여, 원문캐시 잔여) — 둘은 **다른 문제**다.

    파생물에 남으면 **마스킹이 안 된 것**이고 추출기를 다시 돌려야 한다.
    캐시에 남는 것은 **정상**이다 — 마스킹 전 원문이니까. 대신 **묶음에서 뺀다.**
    🚨 한 목록에 섞으면 「고쳐야 할 것」과 「빼야 할 것」이 구별되지 않는다 (D-160).
    """
    got: list[tuple[str, int]] = []
    cache: list[tuple[str, int]] = []
    for f in sorted(DERIVED.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep" or f.suffix not in {".json", ".jsonl"}:
            continue
        rel = f.relative_to(DERIVED).as_posix()
        if rel in LEAK_ALLOW or f.name in LEAK_ALLOW:
            continue
        n = len(LEAK_PAT.findall(f.read_text(encoding="utf-8", errors="ignore")))
        if n:
            (cache if kind_of(rel)[0] == "원문캐시" else got).append((rel, n))
    return got, cache


# ══════════════════════════════════════════════════════════
# 🔴 개인 식별 — 반출 검사의 **첫 번째** 축 (2026-09-19 · D-17 · 팀장 지적)
# ══════════════════════════════════════════════════════════
#  팀장 — *「마스킹 검사에서 개인이 특정될 수 있는 사안을 가장 중요하게 잡아야 한다」*.
#  ⛔ 종전 반출 검사(`leaks`)는 **법인 표기만** 셌다. 개인은 법인격 표기가 없으므로 **구조적으로 0** 이었고,
#     클론 A 가 본 사건명 속 개인 대표자 실명(09-08 판 `ftc_stage` seq 14635 · 클론A 인계 §5 ③)은
#     그 검사를 **초록으로 지나갈 자리**였다. 무탐은 안심시킨다 (D-188).
#  ★ 회사명은 「곤란한」 것이고 개인 실명·식별번호는 **종류가 다르다**(`preprocess/mask.py` 주석 · D-17).
#    그래서 이 검사가 법인 검사보다 **앞에** 돌고, 하나라도 걸리면 반출이 멈춘다.
#
#  🚨 **재현율 쪽으로 기운다.** 걸린 것은 사람이 본다 — 오탐은 `PERSON_ALLOW` 에 **이름과 사유**로 적는다.
#     반대로 놓친 것은 아무도 모른다. 두 실패의 비용이 같지 않다.
#  🚨 **걸린 이름을 화면에 그대로 내지 않는다** — 출력이 대화·로그로 옮겨지면 그 자체가 반출이다.
#     첫 글자만 두고 가린다(`_hint`).
#  ⚠️ 이것도 거름망이다. 직함·식별번호·사건명 꼴이 없는 실명(「20대 주부」 옆의 이름 같은 것)은 못 잡는다.
#     마스킹의 잔여를 **재는** 것은 여전히 `preprocess.mask --survey` 의 일이다 (D-110).


def _mask_rules():
    """`preprocess/mask.py` 의 직함+이름 규칙을 **빌려 온다** — 지우는 쪽과 세는 쪽이 같은 표를 본다 (D-99).

    ⛔ 여기 성씨·직함을 다시 적으면 마스킹이 넓어질 때 검사만 좁은 채로 남는다 (D-165 가 넓힌 그 목록).
    """
    from preprocess import mask  # noqa: PLC0415 — 모듈을 늦게 연다. 런처가 이 파일을 가볍게 부른다

    return mask._TITLED_PERSON, mask._NOT_NAME, mask._SURNAMES  # noqa: SLF001


#: 식별번호 — 이름이 없어도 **그 자체로** 한 사람을 가리킨다. 오탐이 거의 없는 쪽이다.
PERSON_IDS: dict[str, re.Pattern[str]] = {
    "주민등록번호": re.compile(r"(?<!\d)\d{6}\s?-\s?[1-8]\d{6}(?!\d)"),
    # 🚨 휴대전화만 — 기관 대표번호(043-719-…)는 사람이 아니다
    "휴대전화": re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"),
    "이메일": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
}

#: 개인이 **특정될 수 있어도 정당하게 남는** 자리 — `(파일, 유형)` → 사유. 🚨 비어 있는 것이 정상이다.
#:    ⛔ 법인 쪽 `LEAK_ALLOW`(판례·결정례)를 여기로 **물려받지 않는다.** 공표된 판단문이라도
#:       개인 실명은 법원·행정심판이 비실명 처리하는 대상이다 — 남아 있으면 원천의 실수이지 허용이 아니다.
PERSON_ALLOW: dict[tuple[str, str], str] = {}


#: 🔄 2026-09-19 — **창구 메일**의 계정 이름. 사람을 가리키지 않는다(팀장 판정 — 도메인은 피심인일 때만 지운다).
#:    ⛔ 목록에 없는 계정은 **사람으로 본다** — 모르면 막는 쪽이다 (D-220).
ROLE_MAIL = frozenset(
    {
        "cs",
        "cscenter",
        "help",
        "helpdesk",
        "info",
        "support",
        "contact",
        "admin",
        "webmaster",
        "master",
        "service",
        "customer",
        "center",
        "qna",
        "ask",
        "sales",
        "privacy",
        "noreply",
        "no-reply",
    }
)


def _role_mail(addr: str) -> bool:
    return addr.split("@", 1)[0].lower() in ROLE_MAIL


def _hint(s: str) -> str:
    """걸린 값을 **가려서** 보여 준다 — 어디 있는지는 알되 누구인지는 모르게."""
    s = s.strip()
    return (s[:1] + "○" * (len(s) - 1)) if s else ""


def _pii_scan(files: list[pathlib.Path] | None = None):
    """개인 식별 후보를 **원문 그대로** 낸다 — `(rel, 유형, 줄, 원값, 줄 전체, 시작, 끝)`.

    🚨 이 함수의 결과를 화면에 그대로 내지 않는다. 화면용은 `people()`(가림) ·
       원값은 `triage()` 가 **레포 밖 파일**로만 쓴다.
    """
    titled, not_name, surnames = _mask_rules()
    from preprocess.mask import strip_legal  # noqa: PLC0415

    # 🔄 2026-09-19 — **사건명 꼴 그 자체만** 본다: 「X의 … 위반행위에 대한 건」.
    #    ⛔ 첫 판(성씨로 시작하는 1~3자 + 「…위반」)은 클론 B 생성물에서 **119건 전부 오탐**이었다 —
    #       「둘 이상의 위반행위」·「해당 조문의 벌금형」·「소비자의 안전」. 성씨 목록이 흔한 음절이라서다.
    #    ★ 사건명 자리의 X 는 **피심인**이다(`mask.anchor_ftc` 가 앵커를 뽑는 그 자리). 개인이든 상호든
    #      지워져 있어야 한다(D-17 · D-233) — 그래서 성씨로 거르지 않고 **자국이 아닌 모든 X** 를 본다.
    # 🔄 2026-09-19 3판 — **사건명 자리만** 본다: 값의 머리 · 인용부호 뒤 · 「…건 및 」 뒤의 「X의 …행위에 대한 건」.
    #    ⛔ 2판은 줄 어디서든 잡아 「공정거래위원회 2023. 11. 7. 제1소회의 의결」·「[업체] 등 3개 사업자의」
    #       같은 **묶음 설명**이 걸렸다(클론 B 실측 116건 중 대부분). X 에 자국(`[업체]`)이 들면 볼 것이 없다.
    # 🔄 2026-09-19 4판 — 두 자리를 더 본다 (마스킹이 놓친 실측 2건과 같은 꼴):
    #    · 「…) 및 X(…)의 」 — 괄호 설명을 단 **개인 피심인** 나열. 3판은 「건 및」 뒤만 봐서 실명을 놓쳤다
    #    · 머리 **80자**까지 — 앵커가 47자인 병합 사건명이 40자 한도 밖이었다
    case_person = re.compile(
        r"(?:\"사건명\":\s*\"|[\"'‘「]|(?:건(?:\(병합\))?|\))\s*(?:및|,|·|ㆍ)\s*)\s*"
        r"([^\s\"'\[\]○●ㅇ][^\"'\[\]]{0,79}?)의\s+[^\"]{0,60}?행위에\s*대한\s*건"
    )
    descriptor = re.compile(r"\d+\s*개|(?:^|\s)(?:등|외)(?:\s|$)|\d{4}\.\s*\d")
    targets = files if files is not None else sorted(DERIVED.rglob("*"))
    for f in targets:
        if not f.is_file() or f.suffix not in {".json", ".jsonl"}:
            continue
        rel = f.relative_to(DERIVED).as_posix() if f.is_relative_to(DERIVED) else f.name
        if kind_of(rel)[0] == "원문캐시":
            continue
        for no, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for kind, pat in PERSON_IDS.items():
                for m in pat.finditer(line):
                    if kind == "이메일" and _role_mail(m.group(0)):
                        continue  # 창구 메일은 사람이 아니다 — 도메인(업체)은 `mask` 가 피심인일 때 지운다
                    yield rel, kind, no, m.group(0), line, m.start(), m.end()
            for m in titled.finditer(line):
                if m.group(2) not in not_name:
                    yield rel, "직함+실명", no, m.group(0), line, m.start(), m.end()
            for m in case_person.finditer(line):
                # 🚨 법인격 토막만 남은 것(「[업체](유)의」)은 누구도 가리키지 않는다 (2026-09-19 실측)
                if not strip_legal(m.group(1)).strip(" ()") or descriptor.search(m.group(1)):
                    continue
                yield rel, "사건명 피심인", no, m.group(1), line, m.start(1), m.end(1)


def people(files: list[pathlib.Path] | None = None) -> list[tuple[str, str, int, str]]:
    """개인이 특정될 수 있는 자리 — `(상대경로, 유형, 줄, 가린 예)`. **원문캐시는 보지 않는다**(묶음 밖).

    유형 셋 —
      식별번호    주민등록번호 · 휴대전화 · 이메일
      직함+실명    `mask.py` 의 `_TITLED_PERSON` 이 **지웠어야 할** 꼴이 남은 것 (`[대표]` 로 바뀌지 않았다)
      사건명 피심인 「X의 … 위반행위에 대한 건」의 X 가 자국(`[업체]`·○)이 아니다 — 개인사업자면 실명이다
    """
    out: list[tuple[str, str, int, str]] = []
    for rel, kind, no, raw, _line, _s, _e in _pii_scan(files):
        if (rel, kind) in PERSON_ALLOW:
            continue
        if kind in PERSON_IDS:
            hint = ""
        elif kind == "직함+실명":
            m = _mask_rules()[0].match(raw)
            hint = (m.group(1) + _hint(m.group(2))) if m else _hint(raw)
        else:
            hint = _hint(raw) + "의 …"
        out.append((rel, kind, no, hint))
    return out


#: 무료 메일 — 개인 계정일 가능성이 높다. 🚨 도메인만 본다(계정 부분은 안 본다)
_FREE_MAIL = (
    "naver.com",
    "gmail.com",
    "daum.net",
    "hanmail.net",
    "kakao.com",
    "nate.com",
    "hotmail.com",
)


def triage(out: pathlib.Path) -> int:
    """🔴 판정용 **원값 표**를 레포 **밖** 파일로 쓰고, 화면에는 **누구인지 모르는 특징만** 낸다.

    ⛔ 원값을 화면에 내면 그 출력을 옮기는 순간 반출이다. 사람이 파일을 **기기에서** 열어 본다.
    ★ 화면의 특징은 오탐 규칙을 고르는 데 쓴다 —
       직함   「직함 앞이 한글 음절이다」= 낱말 안쪽(예: 「공사장」의 「사장」) · 오탐 쪽
       사건명  이름 자리 글자 수 (2 = 성+1자 · 3 = 성+2자) — 2자는 「이상의」 같은 보통명사가 많다(추정)
       이메일  무료 메일 / 그 밖(기관·업체) — 계정은 안 본다
    """
    rows = list(_pii_scan())
    out.parent.mkdir(parents=True, exist_ok=True)
    feat: collections.Counter = collections.Counter()
    distinct: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write("file\tkind\tline\tvalue\tbefore\tafter\tfeature\n")
        for rel, kind, no, raw, line, s, e in rows:
            if kind == "직함+실명":
                fx = "낱말안쪽" if s > 0 and "가" <= line[s - 1] <= "힣" else "낱말경계"
            elif kind == "사건명 피심인":
                fx = f"이름{len(raw)}자"
            elif kind == "이메일":
                fx = "무료메일" if raw.lower().split("@")[-1] in _FREE_MAIL else "기관·업체"
            else:
                fx = kind
            feat[(rel, kind, fx)] += 1
            distinct[(rel, kind)].add(raw)
            clean = [
                x.replace("\t", " ") for x in (raw, line[max(0, s - 30) : s], line[e : e + 30])
            ]
            f.write(f"{rel}\t{kind}\t{no}\t{clean[0]}\t{clean[1]}\t{clean[2]}\t{fx}\n")
    print(f"후보 {len(rows):,}건 → {out}")
    print("  🚨 이 파일에는 **원값**이 있다 — 기기에서만 연다. 대화·커밋·저장소에 붙이지 않는다\n")
    print(f"  {'파일':<28}{'유형':<12}{'특징':<10}{'건':>6}{'서로 다른 값':>12}")
    for (rel, kind, fx), n in sorted(feat.items(), key=lambda x: (x[0][0], x[0][1], -x[1])):
        print(f"  {rel:<28}{kind:<12}{fx:<10}{n:>6}{len(distinct[(rel, kind)]):>12}")
    return 0


def _report_people(found: list[tuple[str, str, int, str]]) -> None:
    by = collections.Counter((rel, kind) for rel, kind, _, _ in found)
    print("🔴 **개인이 특정될 수 있는 자리가 있다 — 반출하지 않는다** (D-17)")
    for (rel, kind), n in sorted(by.items(), key=lambda x: -x[1]):
        eg = next((f"{no}행 {h}" for r, k, no, h in found if r == rel and k == kind), "")
        print(f"     {rel}  {kind} {n:,}건   예: {eg}")
    print(
        "\n  → 만든 추출기의 마스킹을 고치고 다시 뽑는다. 오탐이면 `PERSON_ALLOW` 에 (파일, 유형)과 사유를 적는다.\n"
        "  🚨 걸린 값은 가려서 보였다 — 이 출력을 옮길 때도 원문을 붙이지 않는다"
    )


def kind_of(rel: str) -> tuple[str, str]:
    """`data/derived` 아래 상대경로 → (부류, 이유)."""
    for name, pat, why in KIND_RULES:
        if pat in rel:
            return name, why
    return DEFAULT_KIND, "명령이 같은 입력에서 같은 것을 낸다"


#: 파생물 뿌리를 뜻하는 표시. 경로가 문자열이 아니라 **함수 호출**로 시작할 때 쓴다 —
#: `collect.store.derived_dir(".") / "law_article.jsonl"` 이 실제로 그 꼴이다.
#: ⛔ 이 표시가 없었을 때 `law_article.jsonl`·`law_prec.jsonl` 이 「쓰는 곳 없음」으로 걸렸다.
_ROOTMARK = "\x00derived\x00"
_DERIVED_CALLS = {"derived_dir"}


def _tokens(node: ast.AST) -> list[str]:
    """`x / "a" / f"b{v}"` 사슬을 조각으로 편다.

    - 문자열 상수는 그대로
    - f-string 은 **앞쪽 리터럴까지만** — 뒤는 실행 때 정해진다 (`law_{kind}.jsonl`)
    - `derived_dir(...)` 호출과 `DERIVED` 이름은 파생물 뿌리 표시로 바꾼다
    - 그 밖(변수 등)은 빈 조각 — 경로로 세지 않는다
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _tokens(node.left) + _tokens(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        head: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                head.append(v.value)
            else:
                break
        return ["".join(head)] if head else []
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name in _DERIVED_CALLS:
            return [_ROOTMARK]
        # `pathlib.Path("data/derived")` — 문자열 인자를 그대로 조각으로 쓴다.
        # ⛔ 이것이 없을 때 `mfds_press_pdf/tables/*.json` 108개가 전부 「쓰는 곳 없음」이었다.
        if name in {"Path", "PurePath"} and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return [first.value]
        return []
    if isinstance(node, ast.Name | ast.Attribute):
        last = node.attr if isinstance(node, ast.Attribute) else node.id
        return [_ROOTMARK] if last == "DERIVED" else []
    return []


def _scan(path: pathlib.Path) -> tuple[set[str], set[str]]:
    """한 모듈에서 (경로 후보, 문자열 상수 전부). 주석·docstring 은 보지 않는다.

    🚨 문자열 상수를 따로 모으는 이유 — 이름이 **실행 때 정해지는** 파생물이 있다.
       `store.derived_dir(".") / f"{source}.jsonl"` (cosmetic) ·
       `store.derived_dir(".") / name` (hf_api) · `store.derived_dir(FAMILY) / "…"` (mfds_press).
       AST 로는 어느 파일인지 모르지만 **그 이름의 조각은 같은 모듈 안에 리터럴로 있다** —
       `SOURCES = {"cosmetic_ingredient": …}` · `OUT_OFFICIAL = "hf_api_labels.jsonl"`.
    ⛔ 이 2차 대조가 없을 때 실측으로 **114개**가 미분류로 걸렸다 (클론 B · 2026-09-17).
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value.value = ""
    cands: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = [p for p in _tokens(node) if p]
            if parts:
                cands.add("/".join(p.strip("/") for p in parts))
    unparsed = ast.unparse(tree)
    for m in re.finditer(r"""["']([^"'\n]*derived/[^"'\n]*)["']""", unparsed):
        cands.add(m.group(1))
    lits = {
        n.value.strip("./")
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and 0 < len(n.value) < 80
    }
    return cands, lits


def _rel(cand: str) -> str | None:
    """후보에서 `data/derived` 뒤쪽만 떼어 낸다. 아니면 None."""
    cand = cand.replace("\\", "/")
    if _ROOTMARK in cand:
        cand = cand.rsplit(_ROOTMARK, 1)[1]
        return cand.strip("/").removeprefix("./").strip("/")
    m = re.search(r"(?:^|/)data/derived/?(.*)$", cand)
    if m is None:
        return None
    return m.group(1).strip("/")


class Table:
    """경로 → 모듈. 증거가 센 것과 약한 것을 **섞지 않는다.**

    `paths`  1차 — 코드가 경로를 상수로 든다. 확실하다
    `lits`   2차 — 그 모듈이 파생물을 만지는 것은 분명하고, 파일 이름 조각이 그 안에
             리터럴로 있다. **추정**이라 `(추정)` 을 붙여 낸다 (D-110 — 센 것과 약한 것을 가른다)
             🚨 2차는 **쓰는 것과 읽는 것을 못 가른다** — `load_db` 가 읽기만 하는 파일도
                이름을 들면 걸린다. 부류 판정에는 「쓰는 코드가 있는가」만 쓰므로
                그 한계를 안고 간다. 정확한 생산자가 필요하면 1차만 본다.
    """

    def __init__(self) -> None:
        self.paths: dict[str, set[str]] = collections.defaultdict(set)
        self.lits: dict[str, set[str]] = {}


def writers() -> Table:
    t = Table()
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            if f.name in {"__init__.py", pathlib.Path(__file__).name}:
                # 🚨 자기 자신은 뺀다 — `UNWRITTEN` 에 적은 파일 이름이 리터럴이라
                #    2차 대조에서 **이 파일이 그 파생물을 주장한다.** 실제로 그렇게 나왔다.
                continue
            mod = f"{d}.{f.stem}" if d != "scripts" else f"scripts/{f.name}"
            cands, lits = _scan(f)
            rels = {r for c in cands if (r := _rel(c)) is not None}
            for rel in rels:
                if rel:
                    t.paths[rel].add(mod)
            # 🚨 2차 대조는 **파생물을 만지는 것이 이미 확인된 모듈에만** 준다.
            #    그러지 않으면 아무 모듈의 문자열이 아무 파일을 주장할 수 있다.
            if rels:
                t.lits[mod] = lits
    return t


def match_writers(rel: str, table: Table) -> set[str]:
    """1차(경로 상수) → 2차(같은 모듈 안의 리터럴 조각) 순서로 찾는다.

    🚨 이름이 동적인 파생물이 있다 — `law_norm/<법령ID>_<별표>.jsonl` ·
       `labels/<이름>.jsonl` · `f"{source}.jsonl"`. 코드에는 조각만 상수로 있다.
    """
    if rel in table.paths:
        return table.paths[rel]
    got: set[str] = set()
    for key, mods in table.paths.items():
        if not key:
            continue
        if rel.startswith(key.rstrip("/") + "/"):
            got |= mods  # 디렉터리 접두사 — `law_norm/` · `labels/`
        elif "/" not in key and "/" not in rel and rel.startswith(key):
            got |= mods  # f-string 앞쪽 리터럴 — `law_` → `law_prec.jsonl`
    if got:
        return got

    p = pathlib.PurePosixPath(rel)
    pieces = {p.name, p.stem, *p.parts[:-1]}
    return {f"{mod} (추정)" for mod, lits in table.lits.items() if pieces & lits}


def rows() -> list[dict[str, object]]:
    if not DERIVED.exists():
        raise SystemExit(f"🔴 {DERIVED} 가 없다 — 이 기기에는 파생물이 없다")
    table = writers()
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    got: list[dict[str, object]] = []
    orphan: list[str] = []
    for f in sorted(DERIVED.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        rel = f.relative_to(DERIVED).as_posix()
        mods = sorted(match_writers(rel, table))
        if not mods and rel not in UNWRITTEN:
            orphan.append(rel)
            continue
        data = f.read_bytes()
        lines = None
        if f.suffix == ".jsonl":
            lines = sum(1 for x in data.split(b"\n") if x.strip())
        if mods:
            name, why = kind_of(rel)
        else:
            # 만드는 코드가 없다 = 다시 만들 수 없다 → 원천이다
            name, why = "원천", UNWRITTEN[rel]
            mods = ["(없음 — 저장소에 만드는 코드가 없다)"]
        got.append(
            {
                "경로": f"data/derived/{rel}",
                "부류": name,
                "부류근거": why,
                "만든모듈": mods,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "행": lines,
                "기록시각": now,
            }
        )
    if orphan:
        raise SystemExit(
            "🔴 쓰는 곳을 못 찾은 파생물이 있다 — 분류 없이 묶음에 섞이면 재배포 가부를 "
            "모르는 채로 나간다 (D-72). 만드는 모듈에 경로 상수를 두거나, 손으로 만든 것이면 "
            f"`data/derived` 밖으로 옮긴다: {orphan}"
        )
    return got


# ══════════════════════════════════════════════════════════
# 🆕 기기 역할 — 「이 기기가 무엇을 가져야 하나」 (2026-09-19 · D-247 · 검토 2026-09-19 §11-1)
# ══════════════════════════════════════════════════════════
#  ⛔ 종전 `--check` 는 **모든 기기에 클론 B 와 같은 151개**를 요구했다. 그래서 —
#     · CI 는 git 이 옮기는 5개뿐이라 146개를 「없다」로 잡아 **원리적으로 빨강**이었고
#     · 묶음을 완벽히 받은 사본도 원문캐시 105개(옮기지 않는 부류 · D-244)로 **영원히 빨강**이었고
#     · 반대로 게이트 10개는 파일이 없으면 skip 해 **옛 판 위에서 초록**이었다 (클론A 인계 F1)
#  ★ 셋 다 뿌리가 하나다 — 검사가 기기 역할을 몰랐다. 역할은 `.env` 의 `DATA_ROLE` 이다.
#  🚨 **자동으로 추정하지 않는다** — 「raw 가 있으면 정본」은 클론 A(raw 있음)를 정본으로 오판한다.

ROLES: tuple[str, ...] = ("canonical", "replica")

#: (역할, 부류) → 요구. 🚨 **표가 정본이다** — `--check` · 게이트 · `data_store` 가 전부 이것을 읽는다 (D-99).
#:    필수    없으면 실패 · sha 가 다르면 실패
#:    있으면  있는 것만 sha 대조 · 없으면 「안 봤다」로 이름만 낸다 (CI)
#:    무시    보지 않는다 — 옮기지 않는 부류다
NEED: dict[str | None, dict[str, str]] = {
    "canonical": {"원천": "필수", "표본": "필수", "생성물": "필수", "원문캐시": "필수"},
    "replica": {"원천": "필수", "표본": "필수", "생성물": "필수", "원문캐시": "무시"},
    # 역할 없음 = CI · `.env` 가 없는 기기. 🔄 2026-09-20 (D-249) — 원천·표본도 git 에 없어서 「있으면」이다.
    #    git 이 나르는 `GIT_CARRIES` 는 CI 에 늘 있으므로 「있으면」으로도 sha 대조가 돈다.
    None: {"원천": "있으면", "표본": "있으면", "생성물": "있으면", "원문캐시": "무시"},
}


def role() -> str | None:
    """이 기기의 역할. 비었으면 None. 🔴 **모르는 값이면 멈춘다** (D-220).

    ⛔ 오타(`canonnical`)가 조용히 「역할 없음」이 되면 클론 B 가 사본처럼 굴어
       방금 만든 생성물을 옛 판으로 되돌릴 수 있다. `COPYLANE_EDITION` 과 같은 규칙이다 (D-213).
    """
    from collect import env  # noqa: PLC0415 — `.env` 를 여는 곳은 한 곳이다 (D-99)

    v = env.setting("DATA_ROLE")
    if not v:
        return None
    if v not in ROLES:
        raise SystemExit(
            f"🔴 DATA_ROLE 이 {v!r} 이다 — 아는 것은 {list(ROLES)}.\n"
            "  🚨 오타는 조용히 넘어가지 않는다 (D-220). 클론 B 만 canonical, 나머지는 replica."
        )
    return v


def ledger() -> dict[str, dict[str, object]]:
    """git 이 나른 원장 — 경로 → 행. 없으면 빈 dict."""
    if not OUT.exists():
        return {}
    return {
        str(r["경로"]): r
        for r in (json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip())
    }


def diff(who: str | None) -> dict[str, list[str]]:
    """원장 ↔ 디스크를 **역할의 표대로** 가른다.

    반환 — `missing`(있어야 하는데 없다) · `changed`(sha 가 다르다) · `added`(원장에 없는 파일) ·
    `unseen`(있으면 보는 부류가 없어서 안 봤다) · `ignored`(무시하는 부류).
    🚨 `added` 는 **정본에서만 실패**다 — 사본에 남은 옛 파일은 지우지 않고 이름만 낸다.
    """
    need = NEED[who]
    old = ledger()
    new = {str(r["경로"]): r for r in rows()} if DERIVED.exists() else {}
    out: dict[str, list[str]] = {
        k: [] for k in ("missing", "changed", "added", "unseen", "ignored")
    }
    for path, r in sorted(old.items()):
        rule = need.get(str(r["부류"]), "필수")  # 🚨 모르는 부류는 가장 엄하게 (fail-closed)
        if rule == "무시":
            out["ignored"].append(path)
        elif path not in new:
            out["missing" if rule == "필수" else "unseen"].append(path)
        elif new[path]["sha256"] != r["sha256"]:
            out["changed"].append(path)
    for path in sorted(set(new) - set(old)):
        if need.get(str(new[path]["부류"]), "필수") != "무시":
            out["added"].append(path)
    return out


def failed(who: str | None, d: dict[str, list[str]]) -> bool:
    """이 역할에서 `diff` 결과가 실패인가."""
    return bool(d["missing"] or d["changed"] or (who == "canonical" and d["added"]))


def gate_state(*paths: pathlib.Path) -> tuple[str, str]:
    """파생물을 읽는 **게이트**가 돌아도 되는가 — `("run"|"skip"|"fail", 이유)`.

    🔴 F1 (클론A 인계 §3) — 게이트 10개가 「파일이 있나」만 봐서, 옛 판을 든 기기(클론 A)에서는
       **옛 판 위의 초록·빨강**이, 정본에서 파일이 사라지면 **skip 으로 초록**이 났다.
    ★ 규칙 —
      정본    없으면 **fail** (있어야 하는 기기다). 있으면 돈다 — 방금 다시 뽑아 원장보다 새 것은
              정상이다(원장 갱신은 `--write` 의 일이고, 커밋을 막지 않는다 · `test_원장이_디스크와_같다`)
      사본    없거나 **원장과 다르면(옛 판) skip** — 옛 판 위에서 돌지 않는다. `data-sync` 가 채운다
      역할 없음  없으면 skip (CI)
    """
    who = role()
    old = ledger()
    for p in paths:
        rel = p.resolve().relative_to(ROOT).as_posix()
        if not p.exists():
            why = f"{rel} 이 이 기기에 없다"
            if who == "canonical":
                return "fail", f"🔴 {why} — 정본(DATA_ROLE=canonical)에는 있어야 한다"
            hint = (
                " — `launcher.py data-sync` 로 받는다" if who == "replica" else " — 기기 축 (D-19)"
            )
            return "skip", why + hint
        stale = (
            who != "canonical"
            and rel in old
            and hashlib.sha256(p.read_bytes()).hexdigest() != old[rel]["sha256"]
        )
        if stale:
            return "skip", (
                f"🔴 {rel} 이 원장과 다르다(옛 판) — 그 위에서 돌지 않는다. "
                "`launcher.py data-sync` 로 받는다"
            )
    return "run", ""


def gate_guard(*paths: pathlib.Path) -> None:
    """게이트 첫 줄 — `gate_state` 대로 **fail 이나 skip 을 던진다.** 규칙을 테스트마다 베끼지 않는다 (D-99).

    인자가 없으면 **생성물 전부**를 본다 — 입력 목록을 모르는 게이트(`split.plan()`)용이다.
    🚨 pytest 는 여기서만 늦게 import 한다 — 이 모듈은 런처·스크립트도 쓴다.
    """
    import pytest  # noqa: PLC0415

    if paths:
        act, why = gate_state(*paths)
    elif role() == "replica":
        d = diff("replica")
        bad = [p for p in d["missing"] + d["changed"] if NEED["replica"].get(_kind(p)) == "필수"]
        act, why = (
            ("skip", f"🔴 파생물 {len(bad)}개가 없거나 옛 판이다 — `launcher.py data-sync`")
            if bad
            else ("run", "")
        )
    else:
        act, why = "run", ""
    if act == "fail":
        pytest.fail(why)
    if act == "skip":
        pytest.skip(why)


def gate_missing(why: str) -> None:
    """입력이 없어 게이트가 **물리적으로 못 도는** 자리 — 정본이면 fail, 아니면 이름을 낸 skip."""
    import pytest  # noqa: PLC0415

    if role() == "canonical":
        pytest.fail(f"🔴 정본(DATA_ROLE=canonical)인데 입력이 없다 — {why}")
    pytest.skip(why)


def _kind(path: str) -> str:
    """원장 경로(`data/derived/…`)의 부류."""
    return kind_of(path.removeprefix("data/derived/"))[0]


def report(got: list[dict[str, object]]) -> None:
    by = collections.Counter(str(r["부류"]) for r in got)
    size = collections.Counter()
    for r in got:
        size[str(r["부류"])] += int(r["bytes"])  # type: ignore[arg-type]
    total = sum(size.values())
    print(f"파생물 {len(got)}개 · 합계 {total / 1024 / 1024:,.1f} MB")
    print(f"\n  {'부류':<8}{'개':>5}{'크기':>12}   {'비중':>7}")
    for name in ("원천", "표본", "생성물", "원문캐시"):
        if by[name]:
            pct = size[name] / total * 100 if total else 0
            print(f"  {name:<8}{by[name]:>5}{size[name] / 1024:>10,.0f} KB{pct:>7.2f}%")
    keep = [r for r in got if r["부류"] in ("원천", "표본")]
    # 🔄 2026-09-20 (D-249) — 「git 으로 따라가야 하는 것」이 아니다. git 은 `GIT_CARRIES` 만 나르고
    #    나머지 원천·표본은 공유 저장소가 옮긴다(`data-publish`). ⛔ 옛 문구가 남아 사람을 git 으로 보냈다.
    print(f"\n  🔴 다시 만들 수 없거나 갈리는 것 {len(keep)}개 — 잃으면 끝이다")
    for r in keep:
        how = "git" if r["경로"] in GIT_CARRIES else "공유 저장소 (data-publish)"
        print(f"     {r['경로']}  ({r['행'] or '-'}행)  {r['부류']} → {how}")


def _utf8_out() -> None:
    """🔴 화면이 아니라 **파이프·파일**로 나갈 때도 한글·기호를 쓸 수 있게 한다 (2026-09-19 · CI 실측).

    ⛔ Windows 에서 출력이 파이프로 가면 파이썬은 ANSI 코드 페이지로 쓴다 — CI 러너는 cp1252 라
       첫 줄 「역할 · …」에서 `UnicodeEncodeError` 로 죽었다. 한국어 Windows(cp949)는 한글은 되지만
       🔴 같은 기호에서 같은 식으로 죽는다. 콘솔은 원래 UTF-8 이라 로컬 `check` 에서는 안 보였다.
    ★ 콘솔(이미 UTF-8)은 건드리지 않는다. ⛔ `errors="replace"` 로 글자를 뭉개 죽음만 감추지 않는다 (D-162).
    """
    for s in (sys.stdout, sys.stderr):
        enc = (getattr(s, "encoding", "") or "").lower().replace("-", "").replace("_", "")
        if enc != "utf8" and hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")


def main() -> int:
    _utf8_out()
    ap = argparse.ArgumentParser(description="파생물 원장 (D-19 의 짝)")
    ap.add_argument("--write", action="store_true", help=f"{OUT.name} 을 쓴다")
    ap.add_argument("--check", action="store_true", help="원장 ↔ 디스크 대조. 다르면 1")
    ap.add_argument(
        "--pii-triage",
        metavar="파일",
        help="개인 식별 후보의 원값 표를 레포 밖 파일로 쓴다 (화면에는 특징만)",
    )
    ap.add_argument(
        "--export-check",
        action="store_true",
        help="🔴 묶음을 내보내기 전 검사 — 마스킹 잔여가 있으면 1 (D-17 · D-78 ③)",
    )
    a = ap.parse_args()

    if a.pii_triage:
        out = pathlib.Path(a.pii_triage).resolve()
        if out.is_relative_to(ROOT):
            print(f"🔴 레포 안에 쓰지 않는다 — 원값이 커밋될 수 있다: {out}", file=sys.stderr)
            return 1
        return triage(out)

    got = rows()

    if a.export_check:
        # 🔴 **개인이 먼저다** (2026-09-19 · 팀장 지적) — 걸리면 법인 검사로 넘어가지 않는다.
        found = people()
        if found:
            _report_people(found)
            return 1
        print(
            f"개인 식별 0 — 식별번호 · 직함+실명 · 사건명 피심인 (허용 {len(PERSON_ALLOW)}건 제외)"
        )
        bad, cache = leaks()
        pack = [r for r in got if r["부류"] != "원문캐시"]
        nc = len(got) - len(pack)
        if cache:
            print(
                f"⬜ **원문캐시 {len(cache)}개에 법인 표기가 있다 — 정상이다.** 마스킹 전 원문이다."
            )
            print(f"   → 묶음에서 뺀다. 캐시 {nc}개는 raw 와 같은 자리다(부류 원문캐시).")
            print(f"   예: {cache[0][0]}  {cache[0][1]:,}건\n")
        if not bad:
            print(f"반출 가능 — 묶음 대상 {len(pack)}개에 마스킹 잔여 0 (캐시 {nc}개 제외)")
            print(f"  ⬜ 허용 목록 {len(LEAK_ALLOW)}개는 세지 않았다: {', '.join(LEAK_ALLOW)}")
            return 0
        print("🔴 **묶음 대상에 마스킹 잔여가 있다 — 이대로 묶으면 업체명이 나간다** (D-17)")
        for rel, n in bad:
            print(f"     {rel}  법인 표기 {n:,}건")
        print("\n  🚨 만든 추출기를 다시 돌린다 — 코드는 고쳐졌어도 **산출물이 낡았을 수 있다.**")
        print("     예: uv run python -m preprocess.ftc_triage --dump", file=sys.stderr)
        return 1

    if a.check:
        # 🔄 2026-09-19 — **역할의 표대로** 가른다 (D-247). 종전의 「151개 전부」는 위 NEED 주석 참고.
        who = role()
        if not OUT.exists():
            print(f"🔴 {OUT.name} 이 없다 — 먼저 --write", file=sys.stderr)
            return 1
        d = diff(who)
        need = NEED[who]
        print(f"역할 — {who or '없음 (CI 와 같다)'} · 표: {need}")
        for k in d["missing"]:
            print(f"  ⛔ 이 기기에 없다      {k}")
        for k in d["changed"]:
            print(f"  🔄 sha256 이 다르다   {k}")
        for k in d["added"]:
            mark = "🆕 원장에 없다       " if who == "canonical" else "🟡 원장에 없는 파일  "
            print(f"  {mark} {k}")
        if d["unseen"]:
            print(
                f"  ⬜ 안 봤다 {len(d['unseen'])}개 — 이 기기에 없고, 이 역할에서는 요구하지 않는다"
            )
        if d["ignored"]:
            print(f"  ⬜ 무시 {len(d['ignored'])}개 — 옮기지 않는 부류(원문캐시)")
        if not failed(who, d):
            print(f"원장 최신 — 이 역할이 요구하는 파일이 전부 같다 (원장 {len(ledger())}개)")
            return 0
        if who == "replica":
            print(
                "\n🔴 부족하거나 옛 판이다 — `uv run python launcher.py data-sync`", file=sys.stderr
            )
        else:
            print("\n🔴 원장이 디스크와 다르다 — 갱신하려면 --write", file=sys.stderr)
        return 1

    report(got)
    if a.write:
        OUT.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in got) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n→ {OUT.relative_to(ROOT).as_posix()}")
    else:
        print("\n🚨 쓰지 않았다 — 원장을 만들려면 --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
