"""preprocess/mask.py — [P3] 마스킹 · 앵커 방식 (전처리 사양 [P3] · D-17 · 2026-09-06).

    uv run python -m preprocess.mask --target ftc --survey
    uv run python -m preprocess.mask --target mfds_sanctions --survey

수집이 아니라 **읽기만 한다** — `registry.require()` 를 부르지 않는다
(`ftc_triage.py` 와 같은 자리다. `RAW_READERS` 가 `preprocess` 를 허용한다).

──────────────────────────────────────────────────────────────
🚨 왜 사전도 NER 도 아닌가

  둘 다 **놓쳤는지를 알 방법이 없다.** 「업체명 200개 사전으로 지웠다」는 몇 개를
  못 지웠는지 말해 주지 않고, 마스킹은 못 지운 하나가 전부를 무의미하게 만든다.

★ 원천이 **업체명을 구조 필드로 준다** (2026-09-06 실측) —

      mfds_sanctions   PRCSCITYPOINT_BSSHNM   5,370 / 5,370
      ftc              <피심정보내용> · <사건명>

  그래서 이렇게 한다 —

      ① 앵커 확보   구조 필드에서 이름을 그대로 가져온다
      ② 변형 전개   ㈜X · 주식회사 X · X㈜ · X …
      ③ 치환        긴 변형부터 [업체] 로 바꾼다
      ④ 🚨 검증     치환 후 **앵커가 남아 있는지 다시 본다**

  ④가 이 방법의 값이다. **자기 채점이 된다** — 남으면 실패이고 그 수를 셀 수 있다.

🚨 **이름이 없는 것은 못 지운다.** 앵커에 없는 제3자(거래처·계열사·인물)는 안 잡힌다.
   그 잔여를 재는 것이 `--survey` 의 일이고, **재기 전에는 「됐다」고 하지 않는다.**

──────────────────────────────────────────────────────────────
🚨 무엇을 가리고 무엇을 남기나 (2026-09-06 · 팀장 결정)

  [업체]  법인명 — 구조 필드에 있는 것. **식별자다**
  [대표]  대표자명 — 원천이 이미 `000`·`고ㅇㅇ` 로 가려서 준다. 우리는 **표기를 통일**한다
  보존    제품명 · 관련 태그 · 수치

  🔴 **사양 [P3] 의 「상표 → [상표]」를 좁혔다.** 실측이 이유다 —

      (제품명 중) 혈압케어 혈액 순환 정맥류 혈관
      (관련태그) #혈압영양제 #항산화제 #고혈압 #저혈압 #건강기능식품

    **이 제품명이 곧 위법 광고다.** 처분 사유가 「제품명란과 태그에 기능성을 연상시키는
    문구를 썼다」인데 `[상표]` 로 바꾸면 **1층 라벨의 증거가 통째로 사라진다.**
    사양이 같은 자리에서 「제품 유형명과 수치는 보존한다 — 판정 대상이다」라고
    적고 있고, 제품명도 같은 이유다.

  ⬜ `ftc` 의 **영업표지**(`'청년피자'`·`'에듀플렉스'`)는 아직 안 정했다.
     그쪽은 광고 문구가 아니라 브랜드라 결론이 다를 수 있다.
     🚨 **두 원천을 한 규칙으로 덮지 않는다** — 2026-09-06 에 `decc` 어휘를 `prec` 에
        그대로 옮겨 세무 판례가 딸려 온 것과 같은 자리다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

MASK_ORG = "[업체]"
MASK_CEO = "[대표]"
MASK_ADDR = "[주소]"
MASK_BRAND = "[상표]"

#: 🚨 **원천마다 마스킹 대상이 다르다.** 레지스트리가 그렇게 적어 두었다 —
#:
#:     ftc_decisions_body   masking: 업체명·상표·피심인 주소 즉시 마스킹
#:     mfds_sanctions       masking: 업체명·대표자명 즉시 마스킹
#:
#:   `ftc` 에는 「상표」가 있고 `mfds_sanctions` 에는 **없다.** 우연이 아니다 —
#:   `ftc` 의 상표는 **영업표지**(「청년피자」)이고, `mfds` 에서 상표 자리에 오는 것은
#:   **제품명**인데 그게 곧 위법 광고 문구다(「혈압케어 혈액 순환 정맥류 혈관」).
#:   지우면 1층 라벨의 증거가 사라진다.
#:
#: 🚨 **이 표는 레지스트리의 사본이다 — 두 번째 원본이 아니다** (D-54).
#:    `tests/test_mask.py` 가 레지스트리 원문과 대조한다. 원문이 바뀌면 테스트가 깨진다.
POLICY: dict[str, frozenset[str]] = {
    "ftc": frozenset({"org", "brand", "addr", "person"}),
    "mfds_sanctions": frozenset({"org", "person"}),
}

#: 정책 키 ↔ 레지스트리 문언. 대조 테스트가 이걸 쓴다.
POLICY_WORDS = {"org": "업체명", "brand": "상표", "addr": "주소", "person": "대표자명"}

#: 🚨 `ftc_decisions_body` 의 `masking:` 에는 「대표자명」이 없고 대신 이 문장이 있다 —
#:    「대표자명은 원천이 이미 가려서 준다 — 그래도 우리 쪽 마스킹을 끄지 않는다.
#:     원천의 정책이지 우리의 보장이 아니다.」
#:    ⛔ 나는 2026-09-06 에 가림 표기가 47.6% 라는 실측을 보고 「원천이 처리해 놓았다」고
#:       적었다. 레지스트리가 그 함정을 **미리 적어 두었는데 안 읽고 시작했다.**
_PERSON_EXEMPT_WORDING = "원천의 정책이지 우리의 보장이 아니다"

RAW = pathlib.Path("data/raw")
DERIVED = pathlib.Path("data/derived")
OUT = DERIVED / "mask_survey.json"

#: 법인격 표기. 앵커에서 떼고, 변형을 만들 때 다시 붙인다.
#: 🚨 순서가 길이순이다 — `주식회사` 를 `㈜` 보다 먼저 봐야 「농업회사법인 … 주식회사」가 산다.
LEGAL_FORMS = (
    "농업회사법인",
    "유한책임회사",
    "주식회사",
    "유한회사",
    "합자회사",
    "합명회사",
    "재단법인",
    "사단법인",
    "의료법인",
    "(주)",
    "（주）",
    "㈜",
    "(유)",
    "㈜",
)

_LEGAL_RE = re.compile("|".join(re.escape(x) for x in LEGAL_FORMS))

#: 🚨 **짧은 앵커는 맨몸으로 지우지 않는다.** 두세 글자 상호가 일반 명사와 겹친다 —
#:    `ftc` 8,253건 실측에서 **324건(3.9%)** 이 이렇다:
#:      「**대상**」 「대한」 「무학」 「두산」 「효성」 「화승」 「삼호」 「세정」
#:    「대상 제품」·「검사 대상」이 전부 `[업체]` 가 되면 문장이 무너진다.
#:
#: ⛔ 첫 판은 이것들을 **통째로 건너뛰었다.** 그게 더 나빴다 —
#:    건너뛴 문서에서는 `residue()` 도 0 이 나와 **자기 채점이 꺼진다.**
#:    「324건은 검사 안 했다」가 「324건 이상 없음」으로 보인다.
#: ★ 지금은 **법인격이 붙은 형태만 지우고**(「㈜대상」·「주식회사 대상」),
#:   맨 「대상」은 남기되 **몇 번 남았는지 센다.** 못 하는 것을 못 한다고 세는 쪽이다.
MIN_ANCHOR = 3

#: 대표자명 가림 표기 — 원천마다 다르다 (2026-09-06 실측).
#:    `대표이사 000` · `대표이사 고ㅇㅇ` · `변호사 조ㅇㅇ`
#: 🚨 **가리는 것이 아니라 통일하는 것**이다. 원천이 이미 가렸고, 표기가 둘이라
#:    그대로 두면 같은 것이 두 토큰이 된다.
#: 🚨 `ㅇ` 을 자모 분리(S3)로 세지 않는 이유가 여기 있다 — `preprocess/text.py` 참조.
#:
#: ⛔ 첫 판은 앞뒤에 **숫자**만 없으면 됐다. 테스트가 바로 잡았다 —
#:      「과징금 1,000만 원」 → 「과징금 1,[대표]만 원」
#:    `000` 앞이 쉼표라 숫자 검사를 통과했다. 🚨 **수치는 판정 대상**인데(사양 1-4)
#:    마스킹이 숫자를 먹는 실패는 **조용하다** — 개인정보가 남는 것과 달리 아무도 안 놀란다.
#:    그래서 쉼표·마침표까지 앞자리에서 막는다. 뒤의 마침표는 막지 않는다 —
#:    「대표이사 000.」 처럼 문장 끝에 오는 것이 실재한다.
_REDACTED_NAME = re.compile(r"(?<![0-9,.])(?:000+|[가-힣][ㅇo○●]{2,})(?![0-9,])")

#: 🔴 **원천이 늘 가려 주지는 않는다** (2026-09-06, `ftc` 8,253건 표본에서 발견).
#:
#:     피 심 인 : 주식회사 경기고속 광주시 송정동 222 … **대표이사 허명회**
#:     주식회사 덕화스포츠 … **대표이사 김창범** / 위 피심인의 대리인 … **담당변호사 진종백**
#:
#: ⛔ 나는 가림 표기가 **47.6%** 에만 있다는 숫자를 보고도 「원천이 처리해 놓았다」고 적었다.
#:    나머지 52.4% 는 **안 가려진 것**이었다. 숫자를 봤는데 뜻을 잘못 읽었다.
#: 🚨 회사명은 학습에 남으면 곤란한 정도지만 **개인 실명은 종류가 다르다.**
#:    D-17 이 「대표자명」을 마스킹 대상에 넣은 것이 바로 이 자리다.
#:
#: 🚨 성씨 목록을 쓰는 이유 — 직함만 보고 뒤 2~4자를 지우면 「대표자 **표시광고**」처럼
#:    **판정 어휘를 지운다.** 성씨는 열린 추측이 아니라 **닫힌 집합**이라 근거가 된다.
#:    ⬜ 흔한 30여 개만 넣었다. 드문 성씨는 못 잡는다 — `--survey` 가 잔여로 센다.
_TITLES = r"(?:공동대표이사|대표이사|대표사원|대표자|담당변호사|소송대리인|변호사|사장|회장|이사)"
_SURNAMES = "김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽차주민진엄채"
_PERSON_NAME = rf"[{_SURNAMES}][가-힣]{{1,3}}"
_TITLED_PERSON = re.compile(rf"({_TITLES}\s*)({_PERSON_NAME}(?:\s*[,·]\s*{_PERSON_NAME})*)")


def strip_legal(name: str) -> str:
    """법인격 표기를 떼고 알맹이만 남긴다. `㈜비에스비푸드` → `비에스비푸드`."""
    return _LEGAL_RE.sub("", name).strip(" ·,.'\"’”「」()（）")


def variants(bare: str, *, with_bare: bool = True) -> list[str]:
    """앵커 하나에서 표기 변형을 만든다. **긴 것부터** 돌려준다.

    `with_bare=False` 면 맨 이름을 뺀다 — 짧은 앵커(「대상」)에 쓴다.

    🚨 긴 것부터여야 한다. `비에스비푸드` 를 먼저 지우면 `주식회사 [업체]` 가 남아
       원문이 무엇이었는지 알 수 없게 되고, 남은 `주식회사` 가 다음 문서에서
       또 걸린다.

    ★ 공정위 결정문은 **자기 약칭 규칙을 문장으로 선언한다** —
        「이하 회사 명칭을 기재함에 있어 '주식회사’는 생략한다.」
        「이하 법인명을 기재함에 있어 '주식회사’는 생략하거나 ㈜로 약칭한다.」
      추측이 아니라 원천이 알려 주는 것이라, 아래 목록이 그 선언과 맞는지
      `--survey` 가 실제로 센다.
    """
    out = [
        f"주식회사 {bare}",
        f"주식회사{bare}",
        f"{bare} 주식회사",
        f"{bare}주식회사",
        f"㈜{bare}",
        f"(주){bare}",
        f"{bare}㈜",
        f"{bare}(주)",
        f"유한회사 {bare}",
        f"{bare} 유한회사",
    ]
    if with_bare:
        out.append(bare)
    seen: set[str] = set()
    uniq = [v for v in out if not (v in seen or seen.add(v))]
    return sorted(uniq, key=len, reverse=True)


def is_short(bare: str) -> bool:
    """맨몸으로 지우기엔 짧아 일반 명사와 부딪히는 앵커인가."""
    return bool(bare) and len(bare) < MIN_ANCHOR


def usable(bare: str) -> bool:
    """앵커로 쓸 수 있는가.

    ⛔ 빈 문자열을 걸러 낸다. `strip_legal()` 이 법인격만 있는 상호에서 **빈 값**을 낸다
       (`mfds_sanctions` 5,370건 중 1건 실측). 그대로 두면 `variants("")` 가
       `"주식회사 "` · `"㈜"` 를 만들고, 그것이 **본문 전역에서 치환**된다 —
       엉뚱한 회사의 법인격 표기가 통째로 `[업체]` 가 된다.
    🚨 `--survey` 의 「표기 변형」 표에 **이름 없는 줄**이 하나 떠서 보였다.
       숫자를 보라고 만든 표가 자기 버그를 잡았다.
    """
    return bool(bare.strip())


def mask(text: str, bare: str) -> str:
    """자유 텍스트에서 앵커의 변형을 `[업체]` 로, 가려진 이름을 `[대표]` 로 바꾼다.

    🚨 짧은 앵커는 **법인격이 붙은 형태만** 지운다 — 「㈜대상」은 지우고 「대상」은 남긴다.
       남긴 것은 `residue()` 가 센다. 지우지 못한 것을 **세지도 않는 것**이 제일 나쁘다.
    """
    if usable(bare):
        for v in variants(bare, with_bare=not is_short(bare)):
            text = text.replace(v, MASK_ORG)
    text = _REDACTED_NAME.sub(MASK_CEO, text)
    # 🚨 직함을 남기고 이름만 지운다 — 「대표이사 [대표]」.
    #    직함까지 지우면 그 자리가 사람이었다는 사실이 사라져, 다음 사람이
    #    「여기 이름이 있었나」를 못 본다. 지운 자국은 남긴다.
    return _TITLED_PERSON.sub(lambda m: m.group(1) + MASK_CEO, text)


def residue(text: str, bare: str) -> int:
    """🚨 ④ 검증 — 마스킹 뒤에 앵커가 **몇 번 남았는가**.

    🚨 짧은 앵커에서도 **센다.** 여기서 0 을 돌려주면 자기 채점이 꺼지고,
       「검사하지 않았다」가 「이상 없다」로 보인다 (⛔ 첫 판의 실수).
       다만 짧은 앵커의 잔여는 **오탐이 섞인 수**다 — 「검사 대상」의 「대상」도 세어진다.
       그래서 `survey()` 가 긴 앵커와 짧은 앵커의 잔여를 **따로** 보고한다.
    """
    return text.count(bare) if usable(bare) else 0


# ══ 원천별 앵커 ═══════════════════════════════════════════════


def _t(root: ET.Element, tag: str) -> str:
    el = root.find(f".//{tag}")
    return (el.text or "").strip() if el is not None and el.text else ""


def anchor_ftc(root: ET.Element) -> tuple[str, str]:
    """공정위 결정문의 피심인 이름. 돌려주는 값은 `(원표기, 알맹이)`.

    🚨 `<사건명>` 을 쓴다 — 「㈜비에스비푸드**의** 가맹사업법 위반행위에 대한 건」.
       `<피심정보내용>` 은 이름 뒤에 주소가 공백으로 이어 붙어 있어
       (「주식회사 비에스비푸드 안성시 원곡면 지문로 203-86 대표이사 000 …」)
       **어디까지가 이름인지 문자열만 보고는 못 가른다.** 주소 어휘로 자르는 방법은
       「서울식품」 같은 상호에서 바로 깨진다.

    ── 2차 규칙 (2026-09-06, 전량 실측 뒤 추가) ──
    ① 「X**의** …」  ← 대부분
    ② 「X …」에서 **X 에 법인격 표기가 있을 때만**  ← 79건 중 일부를 구한다

    🚨 ②에 조건을 단 이유 — 실측된 79건에 이런 것들이 섞여 있다:

         (주)제너시스 이의신청에 대한 건      ← 회사다. 「의」가 안 붙었을 뿐
         대우웨딩홀 사용계약서상 …            ← 회사인데 법인격 표기가 없다
         불공정약관조항에 대한 건              ← **회사가 아예 없다**

       첫 어절을 무조건 앵커로 삼으면 세 번째에서 「불공정약관조항」을 지우게 된다.
       **판정 대상 어휘가 사라지는 쪽이 회사명이 남는 것보다 나쁘다** —
       개인정보가 남으면 누구나 사고로 보지만, 판정 어휘가 사라진 것은 아무도 못 본다.
       법인격 표기(㈜·주식회사 …)가 있으면 **그 자리는 회사가 확실하다.**

    ⬜ 「대우웨딩홀」류는 이 규칙으로 못 잡는다. 그건 `residual_orgs()` 가 센다.
    """
    name = _t(root, "사건명")
    m = re.match(r"^(.+?)의\s", name)
    if m:
        return m.group(1), strip_legal(m.group(1))
    head = name.split()[0] if name.split() else ""
    if head and _LEGAL_RE.search(head):
        return head, strip_legal(head)
    return "", ""


#: 마스킹 뒤에 **법인격 표기를 달고 남아 있는 이름**을 찾는다.
#: 🚨 앵커와 무관하게 돈다 — 그래서 세 가지를 한꺼번에 센다:
#:    ① 앵커를 못 뽑은 문서  ② 앵커가 놓친 표기  ③ **앵커에 없는 제3자**(거래처·계열사)
#: ★ ③ 은 지금까지 **한 번도 안 재 본 것**이다. 「앵커에 있는 이름은 다 지웠다」가
#:   「이름이 다 지워졌다」로 읽히던 자리를, 이 검사가 막는다.
_ORG_WORD = r"(?:주식회사|유한회사|유한책임회사)"  # 풀어 쓴 것
_ORG_SIGN = r"(?:㈜|\(주\)|（주）)"  # 기호
_ORG_FORM = f"(?:{_ORG_WORD}|{_ORG_SIGN})"

#: 「주식회사 **X**」 — 법인격이 앞에 오는 꼴
#: 🚨 **풀어 쓴 것 뒤에는 공백을 요구하고, 기호 뒤에는 요구하지 않는다.**
#:    「㈜현대건설」은 붙여 쓰는 것이 정상이지만, 「주식회사에게」는 회사가 아니라
#:    **조사가 붙은 것**이다. 공백을 안 따지면 그 「에게」가 회사명으로 세어진다 —
#:    실측에서 699건이 그렇게 잡혔다 (2026-09-06 · `ftc` 8,253건).
_ORG_PREFIX = re.compile(
    f"(?:{_ORG_WORD}" + r"\s+|" + f"{_ORG_SIGN}" + r"\s*)([가-힣A-Za-z0-9]{2,12})"
)
#: 「**X** 주식회사」 — 법인격이 뒤에 오는 꼴
_ORG_SUFFIX = re.compile(r"([가-힣A-Za-z0-9]{2,12})\s*" + _ORG_FORM)

#: 🚨 이름 **수집** 전용 뒤꼴 — 기호 `(주)` 를 뺀다.
#:    기호는 이름 **앞**에 오므로(「(주)미래이엔지」), 뒤꼴로 훑으면 그 앞의 무관한 낱말이
#:    이름으로 잡힌다. 실측에서 「합계액」·「로부터」가 그렇게 들어왔다 (2026-09-07).
#:    `_ORG_SUFFIX` 는 **잔여 계수**용이라 넓게 두고, 수집은 이쪽을 쓴다.
_ORG_SUFFIX_WORD = re.compile(r"([가-힣A-Za-z0-9]{2,12})\s*" + _ORG_WORD)


def residual_orgs(text: str) -> list[str]:
    """마스킹 뒤 텍스트에 법인격 표기를 달고 남은 이름들.

    🚨 **두 번에 나눠 훑는다. 한 번에 하면 틀린다** (2026-09-06, `ftc` 8,253건 실측).

       「피심인 주식회사 삼성생명」처럼 **앞말 + 법인격 + 진짜이름** 꼴에서,
       하나의 정규식에 두 꼴을 `|` 로 묶으면 스캐너가 **왼쪽부터** 훑기 때문에
       「피심인 주식회사」가 먼저 걸리고 진짜 이름은 못 본다.
       실제로 상위가 이렇게 나왔다 —

           피심인 1,821 · 피심인은 720 · 수급사업자인 653 · 관련 362 · 에게 342

       ★ 그래서 **앞에 오는 꼴을 먼저 다 걷어내고**, 남은 자리에서 뒤에 오는 꼴을 본다.

    🚨 그래도 **오탐이 섞인 하한**이다. 「주식회사 대표이사」 같은 것이 남는다.
       정밀도가 아니라 하한을 재는 자리다 — 0 이면 확실히 없고, 아니면 사람이 목록을 본다.
    🚨 법인격 표기 **없이** 쓰인 이름(「세원」·「대우웨딩홀」)은 이 검사도 못 잡는다.
       그건 사전 없이는 안 되고, 사전은 [P6] 이다. 못 하는 것을 못 한다고 적는다.
    """
    out: list[str] = []
    rest = _ORG_PREFIX.sub(lambda m: out.append(m.group(1)) or " ", text)  # type: ignore[func-returns-value]
    out += _ORG_SUFFIX.findall(rest)
    bare_mark = MASK_ORG.strip("[]")
    got = (_drop_particle(x.strip()) for x in out)
    return [
        x
        for x in got
        if x and bare_mark not in x and not _ONLY_PARTICLE.match(x) and not x.isdigit()
    ]


#: 🚨 **세기 위한 것이지 지우기 위한 것이 아니다.**
#:    조사를 안 떼면 같은 회사가 「현대건설과」·「현대건설은」·「현대건설이」로 흩어져
#:    「7,183종」 같은 부풀려진 수가 나온다. 몇 **종**인지가 판단의 근거이므로 뗀다.
#: 🚨 마스킹 자체는 이 함수를 쓰지 않는다 — 조사를 잘못 떼면 이름이 바뀌는데,
#:    바뀐 이름으로 치환하면 원문이 망가진다. 세는 쪽에서만 감수한다.
#: ⛔ 「에」가 빠져 있었다 — 「(주)대우건설**에** 대한 과징금」이 `대우건설에` 로 세어졌다.
_PARTICLE = re.compile(r"(?:에게|에서|으로|부터|까지|과|와|은|는|이|가|을|를|의|도|만|로|및|에)$")

#: 🚨 조사만 남은 후보를 버린다. 「석정개발(주)**에게**」에서 기호 뒤 캡처가 「에게」를 잡는다 —
#:    기호(㈜·(주))는 공백 없이 이름이 붙는 것이 정상이라 공백을 요구할 수 없고,
#:    그 대가로 조사가 걸린다. 세는 쪽에서 걷어낸다.
_ONLY_PARTICLE = re.compile(
    r"^(?:에게|에서|으로|부터|까지|과|와|은|는|이|가|을|를|의|도|만|로|및|에)$"
)


def _drop_particle(name: str) -> str:
    """끝에 붙은 조사를 뗀다. 남는 것이 2자 미만이면 **떼지 않는다.**"""
    cut = _PARTICLE.sub("", name)
    return cut if len(cut) >= 2 else name


# ══ 이름을 몰라도 지우는 것들 ═════════════════════════════════
#
# 🚨 앵커(피심인) 방식은 **제3자를 구조적으로 못 잡는다** (2026-09-06 실측 · 6,244종).
#    「수급사업자인 (주)미래이엔지에게」·「원사업자인 케이티건설 주식회사가」 —
#    이 이름들이 사건의 골자라서, 이름 목록으로는 절대 못 따라간다.
# ★ 그래서 **이름이 아니라 자리를 지운다.** 법인격 표기가 붙은 자리는 회사가 확실하다.
#
# 🚨 **이것은 반쪽이다.** 「(주)창연실업」은 잡지만 두 번째 언급의 「창연실업」은 못 잡는다.
#    `redistributable: true` 인 데이터에서 반쪽을 「됐다」로 읽는 것이 제일 위험하므로,
#    `residual_orgs()` 로 **남은 것을 세는 것과 한 짝으로만** 쓴다.

#: B — 법인격이 붙은 자리 전체. 앞뒤 두 꼴을 **따로** 훑는다(`residual_orgs` 와 같은 이유).
_SLOT_PREFIX = re.compile(
    f"(?:{_ORG_WORD}" + r"\s+|" + f"{_ORG_SIGN}" + r"\s*)([가-힣A-Za-z0-9]{2,12})"
)
_SLOT_SUFFIX = re.compile(r"[가-힣A-Za-z0-9]{2,12}\s*" + _ORG_FORM)


def _slot_sub(m: re.Match[str]) -> str:
    """🚨 뒤에 붙은 조사는 **남긴다.**

    ⛔ 첫 판은 「(주)미래이엔지**에게** 건설위탁한」을 「[업체] 건설위탁한」으로 만들었다.
       이름을 지우려다 문장 성분을 먹었다. 판정 어휘는 아니지만, 마스킹이 **필요 이상으로
       지우는 실패는 조용하다** — 오늘 `1,000만` 을 먹은 것과 같은 종류다.
    """
    name = m.group(1)
    tail = _PARTICLE.search(name)
    if tail and len(name) - len(tail.group(0)) >= 2:
        return MASK_ORG + tail.group(0)
    return MASK_ORG


def mask_org_slots(text: str) -> str:
    """법인격이 붙은 자리를 이름과 무관하게 `[업체]` 로 바꾼다.

    🚨 이미 `[업체]` 인 자리는 건드리지 않는다 — 앵커 치환이 먼저 돈다.
    """
    text = _SLOT_PREFIX.sub(_slot_sub, text)
    return _SLOT_SUFFIX.sub(MASK_ORG, text)


#: 🚨 **피심인 주소** (레지스트리 `ftc_decisions_body.masking`). 실측 —
#:      「주식회사 덕화스포츠 **서울 서대문구 연희동 81-32** 대표이사 …」
#: 🚨 시도명 뒤에 **주소 꼴 토막이 하나 이상** 있어야 한다. 안 그러면
#:    「**서울** 지역 시장에서」의 「서울」까지 [주소] 가 된다 — 잔여 상위에 1,622건이었다.
_SIDO = (
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청북도|충북|충청남도|충남"
    r"|전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남|제주)"
)
_ADDRESS = re.compile(
    _SIDO + r"(?:특별시|광역시|특별자치시|특별자치도|도)?"
    r"(?:\s+[가-힣A-Za-z0-9]+(?:시|군|구|읍|면|동|리|로|길|가))+"
    r"(?:\s+[0-9][0-9\-]*)?"
    r"(?:\s+[가-힣A-Za-z0-9]+(?:빌딩|타워|타운|센터|아파트|오피스텔|빌라|프라자))?"
    r"(?:\s*,?\s*[0-9]+호)?"
)


def mask_address(text: str) -> str:
    """주소를 `[주소]` 로. 🚨 시·도 이름 하나만 있는 자리는 안 건드린다."""
    return _ADDRESS.sub(MASK_ADDR, text)


# ══ 2패스 — 문서 안에서 사전을 만든다 ═══════════════════════════════
#
# 🚨 B(자리 치환)는 **반쪽이다** (P3결정요청_ftc_2026-09-06 §3-B).
#    「(주)창연실업」은 잡지만, 같은 문서 뒤쪽의 맨몸 「창연실업」은 못 잡는다.
#    실측 — `apply_policy` 를 돌린 뒤에도 **8,253건 중 1,972건(23.9%)** 에
#    법인격 이름이 맨몸으로 남았다. 종으로는 2,118 (2026-09-07).
#
# ★ 외부 사전을 만들지 않는다. **그 문서가 스스로 알려 준 이름만** 쓴다 —
#   「주식회사 X」 가 있는 문서에서만 「X」 를 지운다. 근거가 문서 안에 있다.
#
# 🚨 그냥 돌리면 위험하다. 필터 없이 재면 상위가 **「서울」466 · 「발주」113 ·
#    「이하」113** 이었다. 「㈜서울…」 한 건 때문에 본문의 모든 「서울」이 사라진다 —
#    **필요 이상으로 지우는 실패는 조용하다**(`_slot_sub` 가 같은 이유로 조사를 남긴다).
#    그래서 셋을 건다: ① 최소 3자 ② 행정구역명 배제 ③ 일반어 배제.

#: 행정구역 — 「성남시」처럼 회사명 조각으로 잡히면 본문의 지명까지 지운다.
_ADMIN_DIV = re.compile(r"^(?:" + _SIDO + r"|[가-힣]{2,4}(?:특별시|광역시|시|군|구|도))$")

#: 법인격 표기 주변에서 흔히 잘려 나오는 일반어. 회사명이 아니다.
_GENERIC_ORG_WORDS = frozenset(
    [
        "발주",
        "이하",
        "대표",
        "대표자",
        "대표이사",
        "제품",
        "제품인",
        "계열사",
        "협력사",
        "관계사",
        "가맹점",
        "가맹본부",
        "대리점",
        "합계액",
        "청구액",
        "지급액",
        "법무법인",
        "법무조합",
        "회계법인",
        "세무법인",
        "특허법인",
        "의료법인",
        "학교법인",
    ]
)

#: 🚨 **역할 명사 + 어미**. 「수급사업자**인** 주식회사 X」에서 앞말이 이름으로 잡힌다.
#:    실측 — 필터 없이 돌리니 「수급사업자인」 200 · 「중소기업자인」 68 · 「중소기업자로서」 44 가
#:    상위에 섰다 (2026-09-07 · `ftc` 8,253건). 어미가 붙으므로 낱말 집합으로는 못 막는다.
#: 🚨 조사·어미만으로 된 토막. 「…**로부터** 주식회사 X」의 「로부터」가 이름으로 잡혔다.
#:    `_drop_particle` 은 남는 길이를 지키느라 「로부터」를 통째로 두고 나온다 — 그 뒤를 여기서 막는다.
_PARTICLE_ONLY = re.compile(
    r"^(?:으로부터|로부터|에게서|에서|에게|으로|부터|까지|하여|하고|한|및|또는|그리고)$"
)

_ROLE_NOUN = re.compile(
    r"^(?:수급사업자|원사업자|중소기업자|사업자|피심인|신청인|이의신청인|발주자"
    r"|가맹점주|가맹본부|사업시행자|시공사|시행사|위탁자|수탁자)"
    r"(?:인|로서|으로서|가|는|은|이|와|과|에게|의)?$"
)

#: 맨몸 치환의 최소 길이. `MIN_ANCHOR` 와 같은 뜻이나 **쓰임이 다르다** —
#: 저쪽은 앵커(피심인 하나), 이쪽은 문서에서 캐낸 이름 여럿이라 오탐 비용이 크다.
MIN_BARE = 3


def _bare_candidate(name: str) -> str | None:
    """법인격 표기에서 캐낸 토막을 맨몸 치환에 쓸 수 있는 이름으로. 아니면 None."""
    name = _drop_particle(name).strip()
    if len(name) < MIN_BARE:
        return None
    if name in _GENERIC_ORG_WORDS or _ADMIN_DIV.match(name) or _ROLE_NOUN.match(name):
        return None
    if _PARTICLE_ONLY.match(name):
        return None
    return name


def doc_org_names(text: str) -> list[str]:
    """이 문서가 **스스로 밝힌** 회사 이름들 (법인격 표기가 붙은 것).

    🚨 앞꼴·뒷꼴을 따로 훑는다 — `residual_orgs` 와 같은 이유다.
       긴 이름부터 돌려야 「대우건설」을 지우고 남은 「대우」가 또 잡히지 않는다.
    """
    seen: set[str] = set()
    for pat in (_ORG_PREFIX, _ORG_SUFFIX_WORD):
        for raw in pat.findall(text):
            if (n := _bare_candidate(raw)) is not None:
                seen.add(n)
    return sorted(seen, key=len, reverse=True)


#: 🚨 마스킹 **직후 괄호 안의 원어 표기**. 「[업체](NGK Spark Plug Co., Ltd)」 꼴이다.
#:    한글 상호는 지웠는데 원어가 남아 같은 법인이 그대로 드러난다.
#:    ★ 새 판단이 아니다 — **이미 지우기로 판정된 그 법인**의 다른 표기다.
#:    🚨 이것으로 외국 법인 누출의 **7%(38/500)만** 막힌다. 나머지 462건은 본문에
#:       그냥 실명으로 나오고(「한일홀딩스」·「프리스케일 세미컨덕터즈 리미티드」),
#:       한글의 「법인격이 곧 경계」 전략이 영문에는 통하지 않는다 — **미결이다**.
_MASKED_PAREN = re.compile(r"(\[(?:업체|대표)\])\s*\([^)\n]{2,80}\)")


def mask_paren_alias(text: str) -> str:
    """`[업체](Original Name)` 의 괄호를 지운다. 앞의 마스킹 자국은 남긴다."""
    return _MASKED_PAREN.sub(r"\1", text)


def mask_org_bare(text: str, names: list[str]) -> tuple[str, list[str]]:
    """문서 자기 사전으로 맨몸 언급을 `[업체]` 로. **무엇을 지웠는지 함께 돌려준다.**

    🚨 지운 목록을 돌려주는 것이 설계다 — 결정요청 §4 가 *「지우는 것과 세는 것을
       한 짝으로」* 라고 적은 그 자리다. 세는 쪽이 없으면 커버리지가 오른 만큼
       안심하게 되고, 안심한 만큼 확인을 안 하게 된다.
    """
    used: list[str] = []
    for n in names:
        if n in text:
            text = text.replace(n, MASK_ORG)
            used.append(n)
    return text, used


#: 🚨 **영업표지**는 따옴표 안에 있고 앞에 그 말이 붙는다 (실측) —
#:      「자신의 **영업표지 '청년피자'**를 사용하여」
#:      「'에듀플렉스, 에듀코치 **영업표지** …」
#: 🚨 문맥 없이 따옴표만 보고 지우면 **인용된 광고 문구가 사라진다** —
#:    결정문은 위법 문구도 따옴표로 인용한다(「'바르는게 운동입니다'」).
#:    그것이 우리가 가장 원하는 데이터다. 그래서 **앞말을 요구한다.**
_BRAND = re.compile(
    r"(영업표지|상표|서비스표|상호)(\s*(?:인|는|가|를|은)?\s*)['‘“「『]([^'’”」』\n]{1,20})['’”」』]"
)


def mask_brand(text: str) -> str:
    """「영업표지 'X'」의 X 만 `[상표]` 로. 앞말과 따옴표는 남긴다."""
    return _BRAND.sub(lambda m: f"{m.group(1)}{m.group(2)}'{MASK_BRAND}'", text)


class MaskPolicyError(RuntimeError):
    """마스킹 정책이 없는 원천을 지우려 했다."""


def apply_policy(text: str, bare: str, source: str) -> str:
    """레지스트리가 그 원천에 정한 것만 지운다 (`POLICY`).

    🚨 순서가 있다 — 앵커(정확) → 자리(넓음) → 주소 → 상표 → 사람.
       넓은 것을 먼저 돌리면 앵커가 이미 지워진 자리를 또 훑어 `[업체]` 가 겹친다.

    🔴 **모르는 원천은 통과시키지 않고 거부한다** (D-72 fail-closed · 2026-09-06).

       `data_sources.yaml` 을 훑어 보니 `masking:` 을 선언한 원천이 **5종뿐**이다.
       `mfds_press`(부당광고 점검 보도자료)·`mfds_casebook`(사례집)에는 없는데,
       **둘 다 적발 업체명이 나오는 문서다.**

       🚨 선언이 없는 것이 「마스킹 불필요」인지 「안 적은 것」인지 **구분이 안 된다.**
          조용히 통과시키면 그 구분이 영영 안 생긴다 — 「돌아갔으니 됐다」가 되기 때문이다.
          그래서 멈추고, **레지스트리를 채우라고 말한다.** 판단은 2인 확인이 한다.
    """
    if source not in POLICY:
        raise MaskPolicyError(
            f"{source!r} 의 마스킹 정책이 없다.\n"
            f"  🚨 조용히 통과시키지 않는다 (D-72 fail-closed) — 선언이 없는 것이\n"
            f"     「불필요」인지 「안 적은 것」인지 구분이 안 되기 때문이다.\n"
            f"  고치는 법 — ① data_sources.yaml 의 {source!r} 에 masking: 을 적는다\n"
            f"              ② 2인 확인을 거친다 (게이트 15)\n"
            f"              ③ preprocess/mask.py 의 POLICY 에 같은 뜻으로 옮긴다\n"
            f"     🚨 마스킹이 정말 불필요하다면 그 판단도 masking: 에 적는다 — 빈 칸으로 두지 않는다."
        )
    todo = POLICY[source]
    if "org" in todo:
        text = mask(text, bare)  # 앵커 + 사람(항상)
        names = doc_org_names(text)  # 🚨 자리 치환 **전에** 캔다 — 치환 뒤엔 이름이 없다
        text = mask_org_slots(text)
        text, _ = mask_org_bare(text, names)  # 2패스 — 같은 문서의 맨몸 언급
        text = mask_paren_alias(text)  # 마스킹 직후 괄호 안 원어 표기
    if "addr" in todo:
        text = mask_address(text)
    if "brand" in todo:
        text = mask_brand(text)
    return text


def _iter_ftc(limit: int | None):
    d = RAW / "ftc"
    for n, p in enumerate(sorted(d.glob("*.xml")), 1):
        if limit and n > limit:
            return
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            yield p.name, "", "", "", 0
            continue
        raw, bare = anchor_ftc(root)
        body = "\n".join(_t(root, t) for t in ("주문", "결정요지", "이유"))
        yield p.name, raw, bare, body, body.count("피심인")


def _iter_mfds(limit: int | None):
    d = RAW / "mfds_sanctions"
    n = 0
    for p in sorted(d.glob("page_*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        for row in obj.get("I0470", {}).get("row", []):
            n += 1
            if limit and n > limit:
                return
            raw = (row.get("PRCSCITYPOINT_BSSHNM") or "").strip()
            yield f"{p.name}#{n}", raw, strip_legal(raw), (row.get("VILTCN") or ""), 0


ITER = {"ftc": _iter_ftc, "mfds_sanctions": _iter_mfds}


# ══ 측정 ═════════════════════════════════════════════════════


def survey(target: str, limit: int | None, dump: bool) -> int:
    """🚨 **짜기 전에 재는 자리다.**

    2026-09-06 에 `ftc` 를 **2건만** 보고 「본문은 피심인으로 부르니 마스킹 부담이
    작다」고 적었다. 2건이다. 같은 날 `prec` 어휘를 표본으로 정했다가 `--audit` 에서
    오탈락이 나왔다 — **표본으로 정한 규칙은 전량에서 다르게 행동한다.**
    """
    rows: list[dict] = []
    stat = collections.Counter()
    hits = collections.Counter()
    residues: list[tuple[str, str, int]] = []
    short_left: list[tuple[str, str, int]] = []
    noanchor: list[tuple[str, str]] = []
    short: list[tuple[str, str]] = []
    leftover: collections.Counter[str] = collections.Counter()

    for doc, raw, bare, body, pronoun in ITER[target](limit):
        stat["문서"] += 1
        if not usable(bare):
            # 🚨 `raw` 는 있는데 `bare` 가 빈 경우도 여기다 — 상호가 법인격 표기뿐일 때.
            stat["🔴 앵커 없음"] += 1
            noanchor.append((doc, (raw or body[:60]).replace("\n", " ")[:60]))
            rows.append({"doc": doc, "anchor": None})
            continue
        if is_short(bare):
            stat["앵커 짧음"] += 1
            short.append((doc, bare))
        vs = variants(bare, with_bare=not is_short(bare))
        found = {v: body.count(v) for v in vs if body.count(v)}
        for v in found:
            hits[_shape(v, bare)] += 1
        masked = mask(body, bare)
        left = residue(masked, bare)
        if left:
            if is_short(bare):
                # 🚨 오탐이 섞인 수다 — 「검사 대상」의 「대상」도 세어진다. 따로 본다.
                stat["짧은 앵커 잔여"] += 1
                short_left.append((doc, bare, left))
            else:
                stat["🔴 잔여 있음"] += 1
                residues.append((doc, bare, left))
        if not found:
            stat["본문에 실명 0회"] += 1
        # 🚨 앵커 밖까지 보는 유일한 검사다 — 제3자 회사가 여기서 처음 세어진다.
        orgs = residual_orgs(masked)
        if orgs:
            stat["법인격 붙은 이름 잔존"] += 1
            leftover.update(orgs)
        stat["대표자 가림 발견"] += 1 if _REDACTED_NAME.search(body) else 0
        rows.append(
            {
                "doc": doc,
                "anchor": bare,
                "실명": sum(found.values()),
                "피심인": pronoun,
                "잔여": left,
            }
        )

    n = stat["문서"] or 1
    print(f"\n  [P3] 앵커 측정 — {target} · 문서 {stat['문서']:,}건\n")
    for k in (
        "🔴 앵커 없음",
        "앵커 짧음",
        "짧은 앵커 잔여",
        "본문에 실명 0회",
        "대표자 가림 발견",
        "🔴 잔여 있음",
        "법인격 붙은 이름 잔존",
    ):
        print(f"    {k:18}{stat[k]:>7,}  {stat[k] * 100 / n:>5.1f}%")
    covered = n - stat["🔴 앵커 없음"]
    print(f"\n    ★ 마스킹이 닿은 문서  {covered:>7,}  {covered * 100 / n:>5.1f}%")

    print("\n  표기 변형이 실제로 쓰인 빈도 (문서 수)")
    for shape, c in hits.most_common():
        print(f"    {shape:20}{c:>7,}  {c * 100 / n:>5.1f}%")

    named = [r for r in rows if r.get("anchor")]
    if named:
        cnt = sorted(r["실명"] for r in named)
        pro = sorted(r["피심인"] for r in named)
        print("\n  한 문서 안 등장 횟수 (5/50/95 백분위)")
        print(f"    실명   {_pct(cnt)}")
        if target == "ftc":
            print(f"    피심인 {_pct(pro)}")
            print("    🚨 「피심인」이 실명을 크게 웃돌면 본문이 이미 익명이라는 뜻이다.")

    if noanchor:
        print(f"\n  🔴 앵커를 못 뽑았다 — {len(noanchor):,}건. **이 문서는 마스킹이 안 된다.**")
        print("     사건명이 「X의 … 에 대한 건」 꼴이 아니라는 뜻이다. 아래를 보고 규칙을 늘린다.")
        for doc, head in noanchor[:10]:
            print(f"    {doc}  {head}")
        if len(noanchor) > 10:
            print(f"    … 외 {len(noanchor) - 10:,}건")

    if short:
        print(f"\n  ⬜ 앵커가 {MIN_ANCHOR}자 미만 — {len(short):,}건")
        print("     법인격이 붙은 형태(「㈜대상」)만 지웠고 **맨 이름은 남겼다.**")
        print("     🚨 「대상 제품」·「검사 대상」이 [업체] 가 되는 쪽이 더 나쁘기 때문이다.")
        seen_bare = sorted({b for _, b in short})
        print(f"     상호 {len(seen_bare)}종 — {' · '.join(seen_bare[:20])}")
        if short_left:
            print(f"\n     그중 맨 이름이 본문에 남은 문서 {len(short_left):,}건 (오탐 섞임)")
            for doc, bare, left in short_left[:6]:
                print(f"       {doc}  {bare!r}  {left}회")
            if len(short_left) > 6:
                print(f"       … 외 {len(short_left) - 6:,}건")

    if residues:
        print(f"\n  🔴 마스킹 뒤에도 앵커가 남았다 — {len(residues):,}건")
        print("     변형 목록이 부족하다는 뜻이다. 아래를 눈으로 보고 `variants()` 를 고친다.")
        for doc, bare, left in residues[:10]:
            print(f"    {doc}  {bare!r}  {left}회")
        if len(residues) > 10:
            print(f"    … 외 {len(residues) - 10:,}건")
    if leftover:
        print(f"\n  🚨 마스킹 뒤에도 **법인격을 달고 남은 이름** — {len(leftover):,}종")
        print("     ★ 이것이 앵커 밖까지 보는 유일한 검사다. 셋을 한꺼번에 센다 —")
        print("        앵커를 못 뽑은 문서 · 앵커가 놓친 표기 · **제3자 회사(거래처·계열사)**")
        print("     🚨 오탐이 섞인 하한이다. 0 이면 확실히 없고, 아니면 사람이 목록을 본다.")
        for name, c in leftover.most_common(15):
            print(f"       {name:20}{c:>6,}건")
        if len(leftover) > 15:
            print(f"       … 외 {len(leftover) - 15:,}종")

    if not residues:
        print("\n  ✅ 긴 앵커의 잔여 0 — **변형 목록이 실제 표기를 덮는다.**")
        print("     🚨 「이름이 다 지워졌다」가 **아니다.** 이 검사 밖에 셋이 있다 —")
        print(f"        ① 앵커를 못 뽑은 {stat['🔴 앵커 없음']:,}건")
        print(f"        ② 짧아서 맨 이름을 남긴 {stat['앵커 짧음']:,}건")
        print("        ③ 앵커에 없는 제3자(거래처·계열사·인물)")

    if dump:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  → {OUT} ({len(rows):,}행)")
        print("     🚨 data/ 는 커밋되지 않는다 (D-19). 이 스크립트가 원본이다.")
    return 0


#: `ftc` 결정문에서 우리가 읽는 필드. `ftc_triage.py` 가 쓰는 것과 같은 넷이다.
FTC_FIELDS = ("사건명", "주문", "결정요지", "이유")


def fields(limit: int | None) -> int:
    """🚨 **필드마다 마스킹 부담이 다르다.** 그걸 재는 자리다 (2026-09-06 · 팀장 결정).

    「제3자 회사명을 어떻게 지울까」 앞에 물어야 할 것이 있다 —
    **`ftc` 에서 우리가 정말 쓰는 것이 무엇인가.**

      사건명·주문·결정요지  짧다. 피심인 위주다
      이유                 한 건에 26,214자. **제3자 이름의 대부분이 여기 있다**

    안 쓰는 필드를 안 쓰면 지울 일도 없다. **지우는 방법을 고르기 전에 범위를 정한다.**

    🚨 다만 데이터현황판이 「층 3 공존 규칙 재료 — 공정위 737건 **<이유>**·「판단」에서
       (인용 문구 요소 집합 → 유형) 쌍 추출」이라고 적어 두었다.
       **이유를 버리면 그 재료가 사라진다.** 그래서 이 표는 「버리자」가 아니라
       「무엇을 얻고 무엇을 치르는가」를 나란히 놓는다.
    """
    d = RAW / "ftc"
    stat: dict[str, dict] = {
        f: {"n": 0, "len": [], "docs": 0, "orgs": collections.Counter(), "eg": []}
        for f in FTC_FIELDS
    }
    total = 0
    for n, p in enumerate(sorted(d.glob("*.xml")), 1):
        if limit and n > limit:
            break
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        total += 1
        _, bare = anchor_ftc(root)
        for f in FTC_FIELDS:
            text = _t(root, f)
            if not text:
                continue
            s = stat[f]
            s["n"] += 1
            s["len"].append(len(text))
            orgs = residual_orgs(mask(text, bare))
            if orgs:
                s["docs"] += 1
                s["orgs"].update(orgs)
                # 🚨 숫자만 보면 「제3자」인지 「앵커가 하나만 잡은 공동 피심인」인지
                #    구분이 안 된다. 원문을 몇 개 눈에 보여야 판단이 선다.
                if len(s["eg"]) < 8:
                    s["eg"].append((p.name, bare, text[:110].replace("\n", " "), orgs[:5]))

    print(f"\n  [P3] 필드별 마스킹 부담 — ftc · 문서 {total:,}건\n")
    print(f"    {'필드':10}{'있음':>8}{'길이 5/50/95':>26}{'잔존 문서':>10}{'잔존 종':>9}")
    for f in FTC_FIELDS:
        s = stat[f]
        ln = sorted(s["len"])
        span = _pct(ln).split("(")[0].strip() if ln else "—"
        print(f"    {f:10}{s['n']:>8,}{span:>26}{s['docs']:>10,}{len(s['orgs']):>9,}")

    for f in FTC_FIELDS:
        eg = stat[f]["eg"]
        if not eg:
            continue
        print(f"\n  ── {f} — 잔존 표본 (앵커 → 남은 이름) ──")
        for name, bare, text, orgs in eg:
            print(f"    {name}  앵커={bare!r}  남음={orgs}")
            print(f"      {text}")

    print("\n  🚨 「잔존 종」이 곧 그 필드를 쓸 때 감수해야 하는 제3자 회사 수다.")
    print("     ⬜ 오탐이 섞인 하한이다 — 지명·역할어가 아직 남아 있다.")
    print("     🚨 <이유> 를 버리면 층 3 공존 규칙의 귀납 재료(인용 문구 → 유형)가 같이 사라진다.")
    print("        무엇을 얻고 무엇을 치르는지 보고 정한다 — 이 표는 그 재료다.")
    return 0


def apply(target: str, limit: int | None) -> int:
    """🔴 **마스킹된 사본을 만든다.** D-17 이 「수집 직후 즉시」라고 한 그 자리다.

    🚨 이게 없던 동안 마스킹은 **함수일 뿐이었다.** 부르는 사람이 없으면 안 돌고,
       실제로 `preprocess/ftc_triage.py` 가 `data/derived/ftc_layer1_triage.json` 에
       **마스킹 안 된 사건명**(「㈜비에스비푸드의 …」)을 쓰고 있었다.
       규칙을 아무리 다듬어도 **적용을 강제하지 않으면 소용이 없다.**

    산출 — `data/derived/masked/<target>.jsonl` (한 줄에 한 문서)
    🚨 `data/` 는 커밋되지 않는다 (D-19). 이 스크립트가 원본이고, 산출물은 재생성한다.
    """
    out = DERIVED / "masked"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{target}.jsonl"
    left: collections.Counter[str] = collections.Counter()
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for doc, _raw, bare, body, _pronoun in ITER[target](limit):
            masked = apply_policy(body, bare, target)
            left.update(residual_orgs(masked))
            f.write(
                json.dumps({"doc": doc, "source_id": target, "text": masked}, ensure_ascii=False)
                + "\n"
            )
            n += 1
    print(f"\n  → {path}  ({n:,}건)")
    print(f"    적용한 정책: {' · '.join(sorted(POLICY.get(target, ())))}")
    # 🚨 만들면서 동시에 잰다. 산출과 검증을 두 명령으로 나누면 두 번째를 안 돌린다.
    if left:
        print(f"\n  🚨 마스킹 뒤에도 법인격을 달고 남은 이름 — {len(left):,}종 (오탐 섞인 하한)")
        for name, c in left.most_common(10):
            print(f"       {name:20}{c:>6,}건")
        print("     🚨 0 이 아니다. **「됐다」로 읽지 마라** — 원장에 이 수를 적는다 (D-54).")
    else:
        print("\n  ✅ 법인격을 달고 남은 이름 0 — 다만 법인격 없이 쓴 이름은 이 검사 밖이다.")
    return 0


def _shape(v: str, bare: str) -> str:
    """변형을 사람이 읽을 모양으로. `주식회사 비에스비푸드` → `주식회사 X`."""
    return v.replace(bare, "X") if bare else v


def _pct(xs: list[int]) -> str:
    if not xs:
        return "—"
    q = [xs[int(len(xs) * p)] for p in (0.05, 0.5)] + [xs[min(int(len(xs) * 0.95), len(xs) - 1)]]
    return f"{q[0]:>5,} / {q[1]:>5,} / {q[2]:>5,}   (최대 {xs[-1]:,})"


def main() -> int:
    ap = argparse.ArgumentParser(description="[P3] 마스킹 · 앵커 방식")
    ap.add_argument("--target", choices=sorted(ITER), required=True)
    ap.add_argument("--survey", action="store_true", help="🚨 재기만 한다. 아무것도 쓰지 않는다")
    ap.add_argument("--fields", action="store_true", help="필드별 마스킹 부담 (ftc 전용)")
    ap.add_argument("--apply", action="store_true", help="🔴 마스킹된 사본을 만든다 (D-17)")
    ap.add_argument("--limit", type=int, help="앞 N건만")
    ap.add_argument("--dump", action="store_true", help=f"문서별 표를 {OUT} 로 쓴다")
    a = ap.parse_args()

    if not (RAW / a.target).exists():
        print(f"🚨 {RAW / a.target} 가 없다 — 먼저 수집한다", file=sys.stderr)
        return 1
    if a.apply:
        return apply(a.target, a.limit)
    if a.fields:
        if a.target != "ftc":
            # 🚨 다른 원천은 필드가 하나뿐이라 나눌 것이 없다. 조용히 빈 표를 내지 않는다.
            print("--fields 는 ftc 전용이다 — 다른 원천은 자유 텍스트가 한 필드다", file=sys.stderr)
            return 1
        return fields(a.limit)
    if not a.survey:
        print("--survey · --fields · --apply 중 하나를 골라라.", file=sys.stderr)
        return 1
    return survey(a.target, a.limit, a.dump)


if __name__ == "__main__":
    raise SystemExit(main())
