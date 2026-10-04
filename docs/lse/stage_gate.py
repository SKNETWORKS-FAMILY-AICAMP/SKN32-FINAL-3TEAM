"""1단계(위반 제거) → 2단계(페르소나 말투) 사이 관문 (2026-10-01).

e2e 실험에서 1단계가 위반을 못 지운 문장(「관절통에 도움을 줄 수 있음」 · 「천연 의약품」 · 「모발이 178% 감소」)에
2단계가 페르소나 말투만 입혀 **위반을 그럴듯하게 포장**했다. 2단계는 「적법한 문장」을 전제로 하므로,
그 전제가 서지 않는 문장은 여기서 멈추고 보류(hold)로 돌린다.

🔴 **보류가 기본값이다** — 이 관문은 「통과시킬 근거」를 찾지 않고 「막을 이유」를 찾는다. 틀려도 막는 쪽으로 틀린다
   (D-09 래칫과 같은 방향). 질병 치료 · 예방 주장은 원래 고쳐 쓸 대상이 아니라 합법화 불가(D-32)로 가는 문장이다.
★ 사전 매칭은 `app/dictmatch.py` 한 곳을 쓴다(D-99) — 판정 그래프 `match_dict` 와 같은 규칙 · 단독판정 항목만(D-156).
🚨 판정 인코더는 쓰지 않는다 — 생성 문장에 과다 예측한다(10-01 실험) · 누수 논의와도 떨어뜨린다.
🚨 이 관문은 판정이 아니다. 통과는 「2단계에 넘겨도 된다」일 뿐 적법 확정이 아니다 — 최종 문장은 판정 코어를 다시 지난다(D-119).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from app import dictmatch as dm

ROOT = Path(__file__).resolve().parents[2]
DICT = ROOT / "data" / "derived" / "banned_terms.jsonl"

#: 질병 표현 — 사전이 놓치는 일반 질병명 · 치료 어휘. 🚨 고시 문구의 「혈압이 높은 사람」 · 「혈당조절」은 질병명이 아니다
DISEASE = re.compile(
    r"치료|완치|예방|낫(?!또)|증후군|질환|질병|[가-힣]{1,6}병(?![원아])|[가-힣]*통(?:증)?에|관절통|두통|당뇨|고혈압|암(?:을|에|세포|예방)|"
    r"빈혈|감기|비만|아토피|탈모|변비|불면증|우울증|골다공증|염증|천식|소화불량|속쓰림|(?!무염|저염|죽염|천일염)[가-힣]+염(?![색료])"
)
#: 의약품 · 의약품 오인
#:    🔄 10-01 — 「[가-힣]+약」 꼴은 「곤약」 · 「치약」을 잡았다 → 의약품 낱말을 직접 적는다
DRUG = re.compile(
    r"의약품|처방|치료제|수면제|소화제|진통제|해열제|항생제|발모제|호르몬제|스테로이드|위고비|인슐린|주사|복용|"
    # 🔄 10-04 — 팀 사전 D-311 로 단독판정에서 빠진 낱말을 관문이 직접 든다(천식 · 소화불량 · 속쓰림은 DISEASE).
    #    「건강기능식품」은 고친 문장 본문에 둘 말이 아니다(정답 본문 0건) — 일반식품의 건기식 표방을 막는다
    r"안정제|수면유도|건강기능식품|"
    r"(?<![가-힣])약(?![가-힣])|(?:높이는|먹는|좋은|잘하는|낫는)\s*약(?![가-힣])"
)
#: 체험기 · 후기 말투 — 1인칭 과거 경험
TESTIMONY = re.compile(r"(?:었|았|였|했)(?:어요|는데요?|더니)|더라고요|봤어요|컸어요|줄고|먹는데|써 ?보니")
#: 주장 대상이 기능이 아니라 제품 범주 — 「건강기능식품에 도움」 · 「영양제 도움」
VAGUE_TARGET = re.compile(r"(?:건강기능식품|영양제|식품|제품|차|원료)(?:에|는|도|가)?\s*도움")
#: 한글 · 영문 · 숫자 · 흔한 문장부호 · 원문자(①②) 밖의 글자(「lóg나무」 같은 깨짐)
BROKEN = re.compile(r"[^\s0-9A-Za-z가-힣ㆍ·.,!?%()\[\]~'\"“”‘’/:;\-+&①-⑳]")
#: 자격 · 인증 표방 — 특허 · 수상 · 논문은 표방 자격이 아니다(D-59) · 인증 주장은 실증이 따로 필요하다
CREDENTIAL = re.compile(r"특허|인증|공인|식약처|임상|수상|논문")
#: 기능이 아니라 노화 자체에 「도움」 — 「피부노화에 도움」은 뜻이 뒤집히고 노화방지 주장이 남는다
#: 🔄 10-01 — 「피부노화개선에 도움」이 빠져나갔다(v5 실제 광고) · 노화 뒤에 무엇이 붙든 「도움」으로 이어지면 막는다
#: 🔄 10-01 (v7) — 「피부노화의 방지에 도움」이 빠져나갔다 · 띄어쓰기를 건너 잡는다
AGING = re.compile(r"노화[가-힣\s]{0,8}(?:에|를)\s*도움|노화\S{0,2}\s*방지|안티\s*에이징")
#: 기능 동사로 끝나는 기능성 주장 — 「○○를 지원합니다」 · 「○○ 강화」 · 「○○를 증진시켜요」. 고시 문구는 「~에 도움」 꼴이라 걸리지 않는다
FUNC_VERB = re.compile(r"[가-힣]{2,12}\s*(?:을|를|이|가)?\s*(?:지원|강화|증진|촉진|개선|향상|활성화)(?:합니다|해요|해\s*줍니다|시켜|하는|함\b|$)")
#: 숫자 — 성분명에 붙은 숫자(코엔자임 Q10 · CO2 · 비타민 B12)는 수치 주장이 아니다
NUM = re.compile(r"(?<![A-Za-z\d])\d+")
#: 🆕 10-02 (v9) — **사실로 읽히는 숫자**. 「원문 숫자 남음」이 용량 · 제조 · 배합까지 막아(v9 정답 51개 중 49개)
#:    살릴 사실이 보류로 갔다. 아래 맥락의 숫자는 원문과 고친 문장 **양쪽에서 모두** 이 맥락일 때만 풀어 준다.
#:    ⛔ 효과 · 순위 · 기간 보장(「3일만에」 · 「5kg 감량」 · 「1위」 · 「효과 100%」)은 그대로 막는다.
_EFFECT = r"(?!\s*(?:감량|빠|줄|증가|성장|효과|개선|상승|하락|만에|이내|↓|↑|위\b|등\b))"
FACT_NUM = re.compile(
    r"(\d[\d,.]*)\s*(?:kg|mg|ml|mL|g|L|IU|포|개입|개(?!월)|곡|종|봉|스틱|정|캡슐|병|팩|매입|매)" + _EFFECT  # 용량 · 개수
    + r"|(\d+)\s*(?:시간|일|주|개월|년)\s*(?:간\s*|동안\s*)?(?:숙성|발효|달|우|고아|건조|말|볶|덖|끓|졸|저온|숙)"  # 제조 공정
    + r"|(\d+)\s*년근|(\d+)\s*가지(?!\s*효)"                                                          # 원료 연근 · 가짓수
    + r"|(\d+)\s*:\s*(\d+)"                                                                            # 배합비
    + r"|(\d+)\s*%\s*(?:함유|착즙|원액|과즙|추출물|함량|사용|로|으로)"                                       # 함량
)


def fact_numbers(s: str) -> set[str]:
    """사실 맥락의 숫자 — 쉼표를 떼고 NUM 과 같은 조각으로 낸다(「1,000mg」 → 1 · 000)."""
    out: set[str] = set()
    for m in FACT_NUM.finditer(s):
        out |= set(NUM.findall(m.group()))
    return out


#: 🆕 10-05 — 기능성화장품 공식 표시 문구 전부(`postfix.COSMETIC` 과 같은 7개) — 이 꼴만 「인정된 화장품 기능성」으로 본다
OFFICIAL_COSMETIC = (
    "피부의 미백에 도움", "피부의 주름 개선에 도움", "자외선으로부터 피부를 보호하는 데 도움", "탈모 증상의 완화에 도움",
    "여드름성 피부를 완화하는 데 도움", "피부장벽의 기능을 회복하여 가려움 등의 개선에 도움", "튼살로 인한 붉은 선을 엷게 하는 데 도움",
)
#: 원문에 이것이 있으면 공식 화장품 문구라도 예외를 두지 않는다 — 의약품 표방에서 나온 문구다
_DRUG_ORIGIN = re.compile(r"치료|약|발모|육모|처방|완치|재생|호르몬")
#: 기능성화장품 공식 표시 문구(화장품법 시행규칙 [별표 3] 범주) — 「탈모 증상의 완화」 · 「여드름성 피부」는 질병어 검사에서 뺀다
COSMETIC_CLAIMS = (
    "탈모 증상의 완화에 도움", "여드름성 피부를 완화하는 데 도움", "피부장벽의 기능을 회복하여 가려움 등의 개선에 도움",
)
#: 체험기 말투 중 **만든 사람의 제조 설명**(「달였어요」 · 「볶았어요」 · 「만들었어요」) — 소비 경험이 아니다
PRODUCER = re.compile(r"(?:썰|달|빚|넣|담|만들|끓|갈|섞|볶|착즙|발효|숙성|건조|짜|졸|고|찧|절|삶|구|저)$")


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


HF_CLAIMS = ROOT / "data" / "derived" / "hf_display_claims.jsonl"
#: 「~에 도움」 앞의 주장 구 — 「X에 도움」 · 「X하는 데 도움」 · 「X하는데 도움」
#: 🔄 10-02 (v9) — 「흰모발의 개수를 감소시키는데 도움」이 빠져나갔다 · 「~시키는 데」 · 「~주는 데」 등 동사 어간을 가리지 않는다
CLAIM = re.compile(r"([가-힣A-Za-z0-9·,\s()]{2,40}?)(?:에|[가-힣]{0,2}는\s*데)\s*도움")


@cache
def approved_blob() -> str:
    """식약처 인정 기능성 문구를 이어 붙인 정규화문 — 주장 구가 여기 들어 있어야 「인정된 기능성」이다."""
    if not HF_CLAIMS.exists():
        return ""
    parts = []
    for line in HF_CLAIMS.open(encoding="utf-8"):
        r = json.loads(line)
        parts.append(dm.norm(r.get("정본_문구") or r.get("FNCLTY_CN") or ""))
    return "\n".join(parts)


def unapproved_claim(s: str) -> str | None:
    """🆕 10-01 (v7) — 모델이 인정되지 않은 기능성을 지어냈다(「생체기능의 회복에 도움」 · 「피부노화의 방지에 도움」).
    「~에 도움」의 기능 구를 고시 기능성 문구와 대조해, 핵심 낱말(주어 · 조사를 떼고 끝 8글자)이 어디에도 없으면 그 구를 낸다.
    🚨 기능성화장품 문구(「피부의 미백에 도움을 줍니다」)는 식품 고시에 없으니 화장품 범주 낱말은 예외로 둔다."""
    blob = approved_blob()
    if not blob:
        return None
    # 주장마다 끊는다 — 「…도움을 줄 수 있음, …체지방 감소에 도움」이 한 덩어리로 잡히지 않게
    for chunk in re.split(r"(?<=있음)|(?<=있습니다)|(?<=줍니다)|(?<=줌)|[.]", s):
        m = CLAIM.search(chunk)
        if not m:
            continue
        phrase = re.sub(r"^.*?(?:은|는|이|가)\s+", "", m.group(1)).strip(" ,·")
        if any(k in chunk for k in ("미백", "주름", "자외선", "탈모", "여드름", "피부장벽", "튼살")):
            # 기능성화장품 범주 — 식품 고시에 없다. 🔄 10-05 — **공식 문구일 때만** 건너뛴다.
            #    「피부의 여드름 개선에 도움」(공식은 「여드름성 피부를 완화하는 데 도움」)이 치료를 표방한 실제 광고에서 나와 통과했다(정답표 v2)
            if any(dm.norm(c) in dm.norm(chunk) for c in OFFICIAL_COSMETIC):
                continue
            return phrase
        # 「중성지질 개선, 혈행 개선」 · 「유익균 증식 및 배변활동 원활」 — 기능마다 대조한다
        for seg in re.split(r"[,、]|\s및\s|및(?=[가-힣])", phrase):
            core = dm.norm(re.sub(r"(의|을|를)$", "", seg.strip()))[-8:]
            if len(core) >= 2 and core not in blob and core.replace("의", "") not in blob:
                return seg.strip()
    return None


#: 원료명 자리 — 「○○추출물 함유」 의 ○○. 🚨 「○○은 …에 도움」 의 주어는 보지 않는다 — 고시 공식 원료명
#:    (「Dimethylsulfone (MSM)은」)을 쓰는 게 정상이라 원문의 짧은 이름과 다르다(학습 정답 84개가 걸렸다)
INGREDIENT = re.compile(r"([가-힣A-Za-z0-9·\-()]{2,40}?)\s*(?:을|를)?\s*함유")
#: 원료명이 아니라 일반 낱말인 경우(「제품은」 · 「이 제품은」)
_GENERIC = {"제품", "이제품", "본제품", "원료", "이원료", "식품", "차", "음료"}


def ingredient_changed(original: str, s: str) -> str | None:
    """🆕 10-01 (v7) — 원료명을 바꿔 썼다(원료명 한 글자 오타 · 원료명 앞부분을 다른 낱말로 잘못 읽음 — 실제 광고 평가셋).
    고친 문장의 원료명이 원문(띄어쓰기 무시)에 그대로 없으면 그 원료명을 낸다. 일반 낱말은 보지 않는다."""
    o = dm.norm(original)
    for m in INGREDIENT.finditer(s):
        # 괄호 속 공식 영문명(「유비퀴놀(Ubiquinol)」)은 원문에 없어도 된다 — 괄호 밖 이름으로 대조한다
        name = dm.norm(re.sub(r"\([^)]*\)?", "", m.group(1)))
        if len(name) < 3 or name in _GENERIC or any(ch.isdigit() for ch in name[:1]):
            continue
        if name not in o:
            return m.group(1).strip()
    return None


#: 원료명으로 읽는 꼴 — 「○○추출물 함유」의 ○○ · 「○○분말」 · 「○○오일」
_ING_NAME = re.compile(r"([가-힣A-Za-z0-9·\-]{2,30}?(?:추출물|추출분말|분말|오일|농축액|엑기스|가루|펩타이드|발효물))|"
                       r"((?:[가-힣A-Za-z0-9·\-]+\s)?[가-힣A-Za-z0-9·\-]{2,30}?)\s*(?:을|를)?\s*함유")
#: 원료명 앞에서 떼어도 되는 말 — 과장 · 품질 수식어(원산지 · 품종은 사실이라 여기 넣지 않는다)
_ING_MODIFIER = {"귀한", "듬뿍", "고함량", "고농축", "프리미엄", "최고급", "고급", "천연", "순수", "특급", "명품", "정품", "기적의",  # redistribution: ok — 일반 수식어
                 "특별한", "엄선한", "엄선된", "신비의", "황금", "슈퍼", "진짜", "100%", "고품질", "최상급", "희귀한", "비법",  # redistribution: ok — 일반 수식어
                 "보톡스", "바르는", "먹는", "마시는",
                 "성분", "원료", "주성분", "유효성분", "고시"}  # 🔄 10-05 — 「○○ 성분 △△」의 「성분」은 원료명이 아니다(정답표 v2)
_ING_PARTICLE = re.compile(r"(?:을|를|은|는|의|에|로|으로|와|과|도|만|이며|이고|하고|에서|요|다|죠|니다)$|[!?.,~]$|\d")


def ingredient_truncated(original: str, s: str) -> str | None:
    """🆕 10-02 (v10) — 원료명의 **앞부분을 떼어냈다**(원문 「○○ 버섯추출물」 → 「버섯추출물 함유」 · 실제 광고 1건).
    띄어 쓴 원료명의 앞 낱말이 조사처럼 보이면(「○○가」) 모델이 떼어낸다. 고친 문장의 원료명이 원문에서 시작하는 자리의
    **바로 앞 말**이 수식어 · 조사 붙은 말 · 숫자가 아닌데 고친 문장에 없으면 그 말을 낸다. 낱말 안에서 잘린 것
    (「흑마늘추출물 → 마늘추출물」)도 같은 규칙으로 본다."""
    words = original.split()
    joined = [re.sub(r"[^\w가-힣·\-]", "", w) for w in words]
    s_norm = dm.norm(s)
    for m in _ING_NAME.finditer(s):
        name = dm.norm(m.group(1) or m.group(2) or "")
        if len(name) < 3 or name in _GENERIC:
            continue
        for i, w in enumerate(joined):
            tail = "".join(joined[i:])
            pos = w.find(name[: len(w)]) if len(w) < len(name) else w.find(name)
            if pos < 0 or not tail[pos:].startswith(name):
                continue
            # 낱말 안에서 잘림 — 「흑마늘추출물」의 「흑」
            cut = w[:pos]
            if cut and cut not in _ING_MODIFIER and not _ING_PARTICLE.search(cut) and dm.norm(cut) not in s_norm:
                return cut + name
            # 띄어 쓴 앞 낱말 — 「○○ 버섯추출물」의 「○○」
            if pos == 0 and i > 0:
                prev = joined[i - 1]
                if (prev and prev not in _ING_MODIFIER and not _ING_PARTICLE.search(words[i - 1])
                        and len(prev) <= 6 and dm.norm(prev) not in s_norm):
                    return f"{prev} {name}"
            break
    return None


#: 사실 문장에 원문 없이 붙어도 되는 연결 낱말 — 「○○로 만든」 · 「○○를 담은」 · 「○○ 함유」
_LINK = {"만든", "담은", "담긴", "쓴", "사용", "사용한", "함유", "제품", "넣은", "포함", "구성", "구성한", "된", "한", "든", "으로", "로", "x",
         "위한"}
_PARTICLE = re.compile(r"(으로|에서|이|가|은|는|을|를|의|와|과|로|에|도|만)$")


def new_words(original: str, s: str) -> list[str]:
    """🆕 10-02 (v9) — **사실만 남긴 문장**에 원문에 없는 낱말이 생겼는가(「카카오닙스를 저온 로스팅한 곶감 200g」).
    v9 정답 다수가 「…한 [제품명]」으로 끝나 모델이 제품명을 붙이는 버릇을 배웠고, 붙일 이름이 없으면 지어낸다.
    낱말마다 조사를 떼고 **앞 절반**이 원문(띄어쓰기 무시)에 있으면 원문 낱말로 본다 — 「삭혔어요 → 삭힌」 · 「구웠어요 → 구운」 같은
    활용은 통과한다. 🚨 기능성 문구(「~에 도움」)는 고시 · 공식 문구라 원문에 없는 게 정상이다 — 부르는 쪽에서 뺀다."""
    o = dm.norm(original).lower()
    o_cv = {_cv(ch) for ch in o if "가" <= ch <= "힣"}
    out = []
    # 괄호 속 공식명(「유비퀴놀(Ubiquinol)」 · 「서목태(쥐눈이콩)」)은 보지 않는다 — 원료명 검사와 같다
    words = re.findall(r"[가-힣A-Za-z]+", re.sub(r"\([^)]*\)?", " ", s))
    for w in words:
        stem = _PARTICLE.sub("", w) if len(w) > 2 else w
        if w in _LINK or stem in _LINK:
            continue
        head = stem[: max(1, len(stem) // 2)].lower()
        # 한 음절 어간은 받침만 다른 불규칙 활용(「갈았어요 → 간」 · 「냈어요 → 낸」)을 같은 말로 본다
        if head in o or (len(head) == 1 and "가" <= head <= "힣" and _cv(head) in o_cv):
            continue
        out.append(w)
    # 원문보다 많이 되풀이된 낱말 — 「곶감을 띄운 곶감」(제품명 자리에 원료명을 다시 씀)
    for w in {_PARTICLE.sub("", x) for x in words if len(x) >= 2}:
        if len(w) >= 2 and sum(_PARTICLE.sub("", x) == w for x in words) > max(1, o.count(w)):
            out.append(f"{w}(반복)")
    return out


def _cv(ch: str) -> int:
    """한글 음절의 초성 · 중성 번호(받침을 뗀다)."""
    return (ord(ch) - 0xAC00) // 28


@cache
def dict_entries() -> tuple[dm.Entry, ...]:
    """금지 표현 사전 — **단독판정 자격** 항목만(D-156). 파일이 없으면 빈 사전(경고는 부르는 쪽)."""
    if not DICT.exists():
        return ()
    out = []
    for line in DICT.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("단독판정"):
            out.append(dm.Entry(term=r["term"], violation_type=(r["유형"][0] if len(r["유형"]) == 1 else None)))
    return tuple(out)


def check(original: str, stage1: str | None) -> GateResult:
    """1단계 결과가 2단계로 넘어가도 되는가. 하나라도 걸리면 보류."""
    if not stage1 or not stage1.strip():
        return GateResult(False, ("1단계 실패",))
    s = stage1
    why: list[str] = []
    s_claim = s  # 기능성화장품 공식 문구를 뺀 문장 — 질병어 · 사전 검사용
    # 🚨 원문이 기능성(심사 · 보고)을 말할 때만 뺀다 — 「탈모약 대신 바르는 토닉」에 공식 문구를 지어 붙인 것(v8 · 살리기 평가 #38)은 막는다
    # 🔄 10-05 — 또는 원문이 **같은 기능 개념**을 말하고 의약품 표현이 없을 때(탈모 기능만 말한 실제 광고 → 공식 문구 · 정답표 v2)
    for c in COSMETIC_CLAIMS:
        concept = c.split()[0].replace("여드름성", "여드름").replace("피부장벽의", "피부장벽")
        if "기능성" in original or (concept in original and not _DRUG_ORIGIN.search(original)):
            s_claim = s_claim.replace(c, " ")
    hits = dm.find(s_claim, dict_entries())
    if hits:
        why.append("금지 사전: " + ", ".join(sorted({h.entry.term for h in hits})[:3]))
    if m := DISEASE.search(s_claim):
        why.append(f"질병 표현: {m.group()}")
    if m := DRUG.search(s):
        why.append(f"의약품 표현: {m.group().strip()}")
    kept = (set(NUM.findall(original)) & set(NUM.findall(s))) - (fact_numbers(original) & fact_numbers(s))
    if kept:
        why.append(f"원문 숫자 남음: {sorted(kept)}")
    for m in TESTIMONY.finditer(s):
        if not PRODUCER.search(s[: m.start()]):
            why.append(f"체험기 말투: {m.group()}")
            break
    if dm.norm(s).rstrip(".") == dm.norm(original).rstrip("."):
        why.append("원문 그대로")
    if m := VAGUE_TARGET.search(s):
        why.append(f"주장 대상 불명: {m.group()}")
    if m := BROKEN.search(s):
        why.append(f"깨진 글자: {m.group()}")
    if m := CREDENTIAL.search(s):
        why.append(f"자격·인증 표방: {m.group()}")
    if m := AGING.search(s):
        why.append(f"노화 주장: {m.group()}")
    if (u := unapproved_claim(s)) is not None:
        why.append(f"인정되지 않은 기능성: {u}")
    # 🆕 10-02 (v11) — 「~에 도움」 꼴이 아닌 기능성 주장(「뼈성장과 뼈강도를 지원합니다」)이 대조를 빠져나갔다
    if m := FUNC_VERB.search(s):
        why.append(f"기능성 주장(도움 꼴 아님): {m.group().strip()}")
    if (g := ingredient_changed(original, s)) is not None:
        why.append(f"원문에 없는 원료명: {g}")
    if (t := ingredient_truncated(original, s)) is not None:
        why.append(f"원료명 앞부분 잃음: {t}")
    if "도움" not in s and (nw := new_words(original, s)):
        why.append(f"원문에 없는 낱말: {', '.join(nw[:3])}")
    return GateResult(not why, tuple(why))
