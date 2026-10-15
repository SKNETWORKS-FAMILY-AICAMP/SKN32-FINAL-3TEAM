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
#: 🔄 10-14 — 그릇 「통」(얼음통 · 물통 · 쌀통 · 김치통 …)도 질병이 아니다(다듬기 6차 시험에서 걸림)
#: 🔄 10-12 — 그릇 「병」(젖병 · 보온병 · 물병 · 유리병 · 꽃병 · 술병 · 페트병) · 「수염」은 질병이 아니다(다듬기 데이터 · v15 데이터에서 걸림)
DISEASE = re.compile(
    r"치료|완치|예방|낫(?!또)|증후군|질환|질병|[가-힣]{1,6}(?<!젖)(?<!온)(?<!물)(?<!리)(?<!꽃)(?<!술)(?<!트)병(?![원아])|[가-힣]*(?<!얼음)(?<!물)(?<!쌀)(?<!필)(?<!밥)(?<!휴지)(?<!김치)(?<!반찬)(?<!저금)통(?:증)?에|관절통|두통|당뇨|고혈압|암(?:을|에|세포|예방)|"
    r"빈혈|감기|비만|아토피|탈모|변비|불면증|우울증|골다공증|염증|(?<!춘)천식|소화불량|속쓰림|(?!무염|저염|죽염|천일염)[가-힣]+(?<!수)염(?![색료])"
)
#: 의약품 · 의약품 오인
#:    🔄 10-01 — 「[가-힣]+약」 꼴은 「곤약」 · 「치약」을 잡았다 → 의약품 낱말을 직접 적는다
DRUG = re.compile(
    r"의약품|처방|치료제|수면제|소화제|진통제|해열제|항생제|발모제|호르몬제|스테로이드|위고비|인슐린|주사|복용|"
    # 🔄 10-04 — 팀 사전 D-311 로 단독판정에서 빠진 낱말을 관문이 직접 든다(천식 · 소화불량 · 속쓰림은 DISEASE).
    #    「건강기능식품」은 고친 문장 본문에 둘 말이 아니다(정답 본문 0건) — 일반식품의 건기식 표방을 막는다
    r"안정제|수면유도|건강기능식품|"
    # 🆕 10-14 — 다듬기가 먹는 법을 「투여해 보세요」로 썼다(다듬기 5차 시험 · 직접 만든 제품). 약을 넣는 말이다
    r"투여|투약|복약|"
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
    "모발의 색상을 변화시키는 데 도움",  # 🆕 10-05 염모(모발 색상 변화) 범주
)
#: 🆕 10-05 — 공식 화장품 문구 ↔ 원문에 있어야 할 기능 낱말. 원문과 무관한 기능을 붙이면(「기미 주근깨」 원문에 「주름 개선」) 막는다
COSMETIC_CONCEPT = {
    "피부의 미백에 도움": ("미백", "기미", "주근깨", "하얘", "화이트닝", "톤", "브라이트닝", "잡티", "밝아"),
    "피부의 주름 개선에 도움": ("주름", "링클"),
    "자외선으로부터 피부를 보호하는 데 도움": ("자외선", "UV", "선크림", "선스틱", "선쿠션", "햇빛", "SPF", "썬"),
    "탈모 증상의 완화에 도움": ("탈모", "머리카락", "머리숱", "빠짐"),
    "여드름성 피부를 완화하는 데 도움": ("여드름", "트러블", "뾰루지", "좁쌀"),  # redistribution: ok — 일반 키워드
    "피부장벽의 기능을 회복하여 가려움 등의 개선에 도움": ("장벽", "가려움", "아토피", "건조"),
    "튼살로 인한 붉은 선을 엷게 하는 데 도움": ("튼살",),
    "모발의 색상을 변화시키는 데 도움": ("염색", "새치", "흰머리", "모발 색", "블랙 샴푸"),
}
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
    """식약처 인정 기능성 문구를 이어 붙인 정규화문 — 주장 구가 여기 들어 있어야 「인정된 기능성」이다.

    🔴 2026-10-06 (ohb 흡수 검토) — 파일이 없으면 **멈춘다** (D-220). ⛔ 종전에는 빈 문자열을 돌려줘서
       인정 기능성 대조(`unapproved_claim`)가 경고 없이 빠졌다 — 파생물을 안 받은 PC 에서 관문이 열린 채 돈다.
    """
    if not HF_CLAIMS.exists():
        raise FileNotFoundError(
            f"🔴 {HF_CLAIMS} 가 없다 — 인정 기능성 대조 없이 관문을 돌리지 않는다. `launcher.py data-sync` 로 받는다."
        )
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
        if any(k in chunk for k in ("미백", "주름", "자외선", "탈모", "여드름", "피부장벽", "튼살", "모발의 색상")):
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
                       r"((?:[가-힣A-Za-z0-9·\-]+\s)?[가-힣A-Za-z0-9·\-]{2,30}?)\s*(?:을|를)?\s*함유|"
                       r"([가-힣A-Za-z0-9·\-]{2,20}?)(?:\s?(?:캡슐|소프트젤|젤리|스틱|타블렛|츄어블|구미|앰플|세럼)|\s(?:정|환))"
                       r"(?=$|[^가-힣]|[을를은는이가의와과로도만에])")
#: 🆕 10-14 제형 낱말 자체(「젤리 스틱」의 「젤리」)는 원료명이 아니다
_FORM_WORD = {"캡슐", "소프트젤", "젤리", "스틱", "타블렛", "츄어블", "구미", "앰플", "세럼"}
#: 🆕 10-14 제형 꼴(「○○ 캡슐」)에서 떼어도 되는 앞 말 — 꾸밈 활용형(「촉촉한」 · 「쫀득한」) · 한 글자 말
_ADJ_END = re.compile(r"(?:[한은는운된진던린긴쓴든큰픈쁜]|있는|없는)$")
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
    (「흑마늘추출물 → 마늘추출물」)도 같은 규칙으로 본다.
    🆕 10-14 — 제형 앞 원료명(「○○ △△ 캡슐」 → 「△△ 캡슐」)도 원료명으로 읽는다(시연 연기 시험에서 본 꼴 · 직접 만든 문구로 회귀)."""
    words = original.split()
    joined = [re.sub(r"[^\w가-힣·\-]", "", w) for w in words]
    s_norm = dm.norm(s)
    for m in _ING_NAME.finditer(s):
        name = dm.norm(m.group(1) or m.group(2) or m.group(3) or "")
        form = m.group(3) is not None
        if len(name) < (2 if form else 3) or name in _GENERIC or (form and name in _FORM_WORD):
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
                        and not (form and (_ADJ_END.search(prev) or len(prev) < 2))
                        and len(prev) <= 6 and dm.norm(prev) not in s_norm):
                    return f"{prev} {name}"
            break
    return None


#: 사실 문장에 원문 없이 붙어도 되는 연결 낱말 — 「○○로 만든」 · 「○○를 담은」 · 「○○ 함유」
_LINK = {"만든", "담은", "담긴", "쓴", "사용", "사용한", "함유", "제품", "넣은", "포함", "구성", "구성한", "된", "한", "든", "으로", "로", "x",
         "위한"}
_PARTICLE = re.compile(r"(으로|에서|이|가|은|는|을|를|의|와|과|로|에|도|만)$")
#: 활용형 끝 음절 — 「달인」 · 「구운」 · 「삭힌」 · 「말린」 · 「갈아」 · 「볶아」 · 「달여」(원문 「달였어요」 · 「갈았어요」 꼴)
_CONJ_END = re.compile(r"[인은는한된던운린긴친쓴든힌킨진근픈쁜게고아어여워와]$")
#: 기능성 문구에 들어가는 공통 낱말 — 「~에 도움을 줄 수 있음」 · 「~에 도움을 줍니다」
_CLAIM_COMMON = {"도움", "도움을", "줄", "수", "있음", "있습니다", "줍니다", "주는", "데", "하는"}


def _claim_word(w: str) -> bool:
    """🆕 10-06 (§2 #5) — 인정 기능성 · 공식 화장품 문구에 쓰이는 낱말인가. 「도움」 문장에서도 사실 부분은 보되 이 낱말은 허용한다."""
    stem = _PARTICLE.sub("", w.removesuffix("(반복)"))
    if w in _CLAIM_COMMON or stem in _CLAIM_COMMON:
        return True
    n = dm.norm(stem)
    return bool(n) and (n in approved_blob() or any(n in dm.norm(c) for c in OFFICIAL_COSMETIC))


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
        # 🔄 10-06 — 두 글자 「쌀로」 · 「잎을」도 조사를 뗀다(남는 게 있을 때만) · 괄호를 떼고 남은 조사 하나(「(MSM)은」 → 「은」)는 낱말이 아니다
        if len(w) == 2 and _PARTICLE.sub("", w):
            stem = _PARTICLE.sub("", w)
        if not stem or _PARTICLE.fullmatch(w):
            continue
        if w in _LINK or stem in _LINK:
            continue
        # 🔄 10-06 (팀장 전달 §2 #5) — 두 글자 명사는 **통째로** 본다. 첫 음절만 보면 「항암」이 원문 「항상」으로 지나간다.
        #    활용형 끝(「달인」 · 「구운」 · 「삭힌」 …)은 종전대로 앞 절반만 본다
        if len(stem) == 2 and all("가" <= c <= "힣" for c in stem) and not _CONJ_END.search(stem):
            if stem.lower() not in o:
                out.append(w)
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


#: 🆕 10-11 — 4B 시험판 dev 검수(19 행 · 이서은 확인)에서 관문을 지나간 꼴 셋 + 쓸모없는 후보. 🚨 규칙은 **직접 만든 문구**로
#:    골랐다(`docs/lse/gate_regress.py`) — dev 문구로 맞추지 않았다(D-322 원칙)
#: 보장 주장 — 「수익보장」 · 「효과 보장」은 지운 문장에 남으면 그대로 위반이다
GUARANTEE = re.compile(r"보장")
#: 영양성분 기능 표시 꼴(「…하는 데 필요」) · 항산화 — 「도움」 꼴이 아니라 인정 문구 대조(`unapproved_claim`)를 비껴간다.
#: 🔄 주어(영양성분 「칼슘은 …」)가 있는 「필요합니다」 문장은 후처리가 영양성분 조건(`NOTE_NUTRI`)을 붙이므로 둔다 —
#:    막는 것은 **주어 없이 기능만 남은** 꼴(「눈의 건강을 유지하는 데 필요」)과 「도움」 없는 「항산화」다
NUTRIENT_FUNC = re.compile(r"(?:데|에)\s*필요(?:함|합니다|한|하다|$)|항산화")
NUTRIENT_SUBJECT = re.compile(r"^\s*[가-힣A-Za-z0-9·()\- ]{1,20}?(?:은|는)\s")
#: 원문이 체험기 꼴(후기 · 체험 · 「(홍길동님)」) — 이때 원문의 **몸 변화 단위** 숫자가 남으면 막는다(「4kg 가량」은 용량이 아니라 감량).
#: 🔄 용량 · 비율(30g · 500ml · 7:3)은 체험기 원문에서도 사실이다 — 학습 정답 오탐 5 를 보고 몸 단위로 좁혔다
TESTIMONY_SRC = re.compile(r"후기|체험|[가-힣a-zA-Z*x○]{1,4}\s*님\s*[)\],]|\(\s*[가-힣a-zA-Z*x○]{1,4}\s*님")
BODY_NUM = re.compile(r"(\d+)\s*(?:kg|㎏|킬로|키로|cm|센티|인치|사이즈)", re.I)
#: 낱말 조각 — 살린 사실이 없는 후보(「견적」 · 「OO 제품」). 원료 · 공정 · 산지 낱말이나 숫자가 있으면 사실로 본다
_FRAGMENT_GENERIC = {"제품", "상품", "서비스", "브랜드", "회원"}


#: 🆕 10-11 — 2단계(말투)가 **새로 넣은 낱말**이 건강 고민 · 몸 상태를 말하면 막는다(「면역이 약한 아이에게」 · 「관절이 아픈 부모님께」).
#:    말투 낱말은 허용하지만(`check(persona=True)`) 대상을 건강 고민으로 짚으면 효능을 암시한다. 1단계 문장에 이미 있던 낱말은 보지 않는다
HEALTH_CUE = re.compile(r"혈압|혈당|콜레스테롤|면역|피로|다이어트|체중|뱃살|체지방|관절|연골|뼈|시력|변비|숙면|불면|수면|스트레스|"
                        r"기억력|집중력|탈모|노화|주름|미백|여드름|아토피|염증|통증|아프|아픈|약한|허약|회복|갱년기|소화|위장|건강")
#: 🆕 10-12 — 2단계가 **새로 지어 넣은 사실**(산지 · 원료 · 무첨가 · 인증 · 천연). 말투는 사실을 더하지 않는다
#:    (프롬프트 다듬기 시험에서 「국내산 원료로 제조되며, 무첨가로 생산」을 지어 붙였다 · 관문이 못 막았다)
NEW_FACT = re.compile(r"국내산|국산|[가-힣]{2,4}산$|산지|원료|무첨가|첨가물|함유|인증|천연|유기농|무농약|수제|직접|제조|생산|공정")
#: 🆕 10-15 — 2단계가 **새로 정한 용량 · 횟수 · 때**(「식사 후 한 알」 · 「한 숟갈」 · 「세안 후」). 섭취 · 사용 방법은 제품마다 표시가 정한다 —
#:    다듬기가 정하면 표시와 다른 말이 된다(팀장 지적 · 규칙판 표에 있었다 · 사전 · 재판정은 못 잡는다). 1단계 문장에 이미 있던 표현은 보지 않는다
DOSE_TIME = re.compile(
    r"(?:한|두|세|네|다섯|\d+)\s*(?:알|정|캡슐|포|스푼|숟갈|숟가락|큰술|작은술|잔|컵|병|봉지?|방울|스틱|팩|펌프)"
    r"(?=씩|으로|로|을|를|이|가|은|는|도|만|에|[^가-힣]|$)"  # 조사까지만 — 「포기」 · 「정말」은 단위가 아니다
    r"|하나씩|한\s*개씩|하루\s*(?:\d|한|두|세|에)|(?:\d|한|두|세)\s*(?:번|회)\s*씩|매일|아침\s*저녁|공복|식전|식후"
    r"|식사\s*(?:전|후|중|와\s*함께)"  # 「한 번 써 보세요」(말투)는 막지 않는다 — 횟수는 「하루 …」 · 「… 번씩」만
    r"|(?:자기|잠들기|외출|운동)\s*전|(?:세안|샤워|샴푸|목욕|운동)\s*후"
)


def dose_time_added(original: str, s: str) -> list[str]:
    """`s` 에 새로 생긴 용량 · 횟수 · 때 표현 — 원문(1단계 문장)에 같은 표현이 있으면 뺀다(공백은 무시하고 견준다)."""
    base = re.sub(r"\s+", "", original)
    return sorted({m.group() for m in DOSE_TIME.finditer(s) if re.sub(r"\s+", "", m.group()) not in base})

#: 🆕 10-12 — 4B v14 dev 검수(33 행 · 이서은 동의)에서 지나간 꼴 둘. 🚨 규칙은 직접 만든 문구로 골랐다(`gate_regress.py`)
#: 「무+원료」(없음)를 「함유」로 — 「무○○ 함유」 · 「○○ 함유」(원문에는 「무○○」로만). 무(채소) · 무게 · 무료 같은 낱말은 뺀다
NEG_ING = re.compile(r"(?<![가-힣])무([가-힣]{2,4})")
_NOT_NEG = ("말랭이", "생채", "김치", "청", "순", "즙", "화과", "기질", "게", "늬", "료", "역", "릎", "지개", "조건", "한", "려", "엇", "척", "대", "사")  # redistribution: ok — 일반어
HAS_ING = r"\)?\s*(?:을|를|이|가)?\s*(?:함유|첨가|넣은|들어)"
#: 원문의 효능 주장(대상 + 효과 동사)이 그대로 남음 — 「…바이러스를 제거합니다」 · 「…배출을 줄인」. 실증이 필요한 주장이다.
#: 🚨 대상을 좁혀 둔다 — 「씨를 제거한 대추」 · 「저온 살균 우유」 같은 공정 사실은 막지 않는다
EFFECT_TARGET = r"바이러스|세균|유해균|균|미세\s*먼지|먼지|냄새|악취|유해\s*물질|독소|노폐물|질소산화물|배출\s*가스|배출|오염\s*물질|진드기|곰팡이|기미|잡티"
EFFECT_CLAIM = re.compile(rf"({EFFECT_TARGET})\s*(?:을|를|이|가|도)?\s*(?:[가-힣]+\s+){{0,2}}?(제거|차단|억제|줄이|줄인|줄여|감소|박멸|살균|없애|없앤|잡아|잡는|흡착|분해)")


def negation_flipped(original: str, s: str) -> str | None:
    """원문의 「무○○」(없음)가 출력에서 「○○ 함유」로 뒤집혔는가."""
    for m in NEG_ING.finditer(original):
        x = m.group(1)
        if x.startswith(_NOT_NEG):
            continue
        if re.search(rf"무{x}{HAS_ING}", s):
            return f"무{x} → 함유"
        rest = original.replace(m.group(), " ")
        if x not in rest and re.search(rf"(?<!무){x}{HAS_ING}", s):
            return f"무{x} → {x} 함유"
    return None


def effect_claim_kept(original: str, s: str) -> str | None:
    """원문에 있던 효능 주장(대상 + 효과 동사)이 출력에도 남았는가.
    「…에 도움」 꼴은 인정 기능성 문구 대조(`unapproved_claim`)가 맡는다 — 「유해균 억제에 도움」(인정 문구 · 학습 정답 23)은 보지 않는다"""
    if "도움" in s:
        return None
    for m in EFFECT_CLAIM.finditer(s):
        target = re.sub(r"\s", "", m.group(1))
        if EFFECT_CLAIM.search(original) and target in re.sub(r"\s", "", original):
            return m.group().strip()
    return None


_FACT_SKIP = re.compile(r"^(?:있|없|하|합|함|해|됩|된|되|입니|이며|이고|줍|줄|줌|주는|수$|필요|미흡|확인|도움|등$|및$|또는$|으나$)")


def facts_dropped(s1: str, s2: str) -> list[str]:
    """🆕 10-12 — 2단계(말투 · 다듬기)가 **1단계 문장의 사실 낱말**을 빼거나 바꿨는가. 말투는 덧붙이는 일이지 사실을 고치는 일이 아니다.
    낱말은 조사를 떼고, 활용 어미 한 글자(「압착한」 → 「압착」)는 떼고 본다 · 숫자는 그대로 남아야 한다.
    (다듬기 시험에서 「저온 건조해 빚은 여주」 → 「…뚱한 여주」, 「채 썬」 → 「썬」이 나왔다)"""
    out = dm.norm(s2)
    lost = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", s1):
        if _FACT_SKIP.match(w):
            continue  # 서술 · 완화 표현(「있습니다」 · 「필요함」)은 말투가 바꿔 쓸 수 있다 — 주장 검사가 따로 본다
        t = _PARTICLE.sub("", w) if len(w) > 2 else w
        if len(t) >= 2 and _CONJ_END.search(t):
            t = t[:-1]  # 「빚은」 → 「빚」 · 「압착한」 → 「압착」
        if t and dm.norm(t) not in out:
            lost.append(w)
    return lost


def fragment_only(s: str) -> bool:
    """후보가 낱말 하나(일반어 제외) 뿐이고 숫자 · 연결 낱말(함유 · 사용 · 만든 …)이 없는가."""
    if NUM.search(s):
        return False
    words = [w for w in re.findall(r"[가-힣A-Za-z]+", s)]
    if any((w in _LINK or _PARTICLE.sub("", w) in _LINK) and w not in _FRAGMENT_GENERIC for w in words):
        return False
    content = [w for w in words if len(w) >= 2 and w not in _FRAGMENT_GENERIC]
    return len(content) <= 1


#: 🆕 10-08 — 앞말과의 관계를 뒤집는 말. 빠지면 뜻이 바뀐다(「국산 당면 대신 곤약면」 → 「국산 당면 곤약면」 · 살리기 평가 #24).
#: 같은 갈래의 다른 말로 바꿔 쓴 것(「설탕 없이」 → 「무설탕」)은 뜻이 남은 것으로 본다  redistribution: ok — 일반 관계어
_RELATION = {
    "대체": re.compile(r"대신|빼고|제외하고"),
    "부정": re.compile(r"없이|없는|없고|않은|않고|않았|아닌|무첨가|무설탕|무가당|무색소|무방부제|무농약|미함유|미첨가|프리(?!미엄)|\bfree\b", re.I),  # redistribution: ok — 일반 관계어
}
_VERB_TAIL = re.compile(r"(지|게|고)$")


def meaning_flipped(original: str, s: str) -> str | None:
    """원문의 관계어(대신 · 없이 · 무첨가 …)가 빠졌는데 **그 앞말은 남았는가** — 「A 대신 B」가 「A B」가 되는 꼴.
    앞말까지 함께 지웠으면(「숙취해소제 대신 황태국」 → 「황태를 우려 냄」) 뜻이 바뀐 게 아니다."""
    s_low = s.lower()
    for group, pat in _RELATION.items():
        if pat.search(s_low):
            continue  # 같은 갈래의 말이 출력에 있다
        for m in pat.finditer(original):
            word = m.group()
            # 관계어가 걸리는 말 하나만 본다 — 「무설탕」은 설탕 · 「당면 대신」은 당면 · 「방부제 넣지 않고」는 동사를 건너 방부제.  redistribution: ok — 일반 관계어
            # 🔄 두 낱말 앞까지 보면 「튼살 걱정 없는」의 튼살 · 「국내 유일 무농약」의 국내를 잡았다(학습 정답 오탐 4)
            # 「무첨가 · 미함유 · 미첨가」는 대상이 앞말(「색소 무첨가」)이다 — 뒤쪽 「첨가」는 일반어
            if word.startswith(("무", "미")) and len(word) >= 3 and word not in ("무첨가", "미함유", "미첨가"):  # redistribution: ok — 일반 관계어
                target = word[1:]
            else:
                before = re.findall(r"[가-힣A-Za-z0-9]+", original[: m.start()])
                if before and _VERB_TAIL.search(before[-1]) and len(before) >= 2:
                    before = before[:-1]
                if not before:
                    continue
                target = _PARTICLE.sub("", before[-1]) if len(before[-1]) > 2 else before[-1]
            if len(target) >= 2 and dm.norm(target) in dm.norm(s):
                return f"「{word}」 빠짐 ({target} · {group})"
    return None


def _cv(ch: str) -> int:
    """한글 음절의 초성 · 중성 번호(받침을 뗀다)."""
    return (ord(ch) - 0xAC00) // 28


@cache
def dict_entries() -> tuple[dm.Entry, ...]:
    """금지 표현 사전 — **단독판정 자격** 항목만(D-156).

    🔴 2026-10-06 (ohb 흡수 검토) — 파일이 없으면 **멈춘다** (D-220). ⛔ 종전에는 빈 사전을 돌려주고
       「경고는 부르는 쪽」이라 적었는데 경고하는 호출부가 없었다 — 사전 검사가 조용히 빠졌다.
    """
    if not DICT.exists():
        raise FileNotFoundError(
            f"🔴 {DICT} 가 없다 — 금지 표현 사전 없이 관문을 돌리지 않는다. `launcher.py data-sync` 로 받는다."
        )
    out = []
    for line in DICT.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("단독판정"):
            out.append(dm.Entry(term=r["term"], violation_type=(r["유형"][0] if len(r["유형"]) == 1 else None)))
    return tuple(out)


def check(original: str, stage1: str | None, persona: bool = False) -> GateResult:
    """1단계 결과가 2단계로 넘어가도 되는가. 하나라도 걸리면 보류.

    🆕 10-11 `persona=True` — 2단계(말투)의 출력을 1단계 문장과 견줄 때. 말투는 **새 낱말을 넣는 일**이라
    「원문에 없는 낱말」 · 「살릴 사실 없음」 · 「원문 그대로」는 보지 않는다(10-06 부터 늘 보게 되면서 2단계가 거의 다 보류돼
    1단계 문장으로 돌아갔다 · 3B 114/114). 주장에 관한 검사(사전 · 질병 · 의약품 · 수치 · 보장 · 기능 문구 · 인정 문구 대조 …)는 그대로다."""
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
    if kept and not persona:
        # 🔄 10-12 — 말투 모드의 「원문」은 이미 관문을 지난 1단계 문장이다 — 그 숫자(28cm · 주 2회)는 남아야 맞다
        why.append(f"원문 숫자 남음: {sorted(kept)}")
    for m in TESTIMONY.finditer(s):
        if not PRODUCER.search(s[: m.start()]):
            why.append(f"체험기 말투: {m.group()}")
            break
    if not persona and dm.norm(s).rstrip(".") == dm.norm(original).rstrip("."):
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
    for claim, kws in COSMETIC_CONCEPT.items():
        if claim in s and not any(k in original for k in kws):
            why.append(f"원문에 없는 기능(화장품): {claim}")
    # 🆕 10-02 (v11) — 「~에 도움」 꼴이 아닌 기능성 주장(「뼈성장과 뼈강도를 지원합니다」)이 대조를 빠져나갔다
    if m := FUNC_VERB.search(s):
        why.append(f"기능성 주장(도움 꼴 아님): {m.group().strip()}")
    if (g := ingredient_changed(original, s)) is not None:
        why.append(f"원문에 없는 원료명: {g}")
    if (t := ingredient_truncated(original, s)) is not None:
        why.append(f"원료명 앞부분 잃음: {t}")
    if (f := meaning_flipped(original, s)) is not None:
        why.append(f"뜻 바뀜 의심: {f}")
    if (f := negation_flipped(original, s)) is not None:
        why.append(f"뜻 뒤집힘: {f}")
    if (e := effect_claim_kept(original, s)) is not None:
        why.append(f"효능 주장 남음: {e}")
    if GUARANTEE.search(s):
        why.append("보장 주장 남음")
    if "도움" not in s and (m := NUTRIENT_FUNC.search(s)) and not (m.group().strip() != "항산화" and NUTRIENT_SUBJECT.search(s)):
        why.append(f"기능 문구(조건 필요): {m.group().strip()}")
    if TESTIMONY_SRC.search(original) and (k := set(BODY_NUM.findall(original)) & set(BODY_NUM.findall(s))):
        why.append(f"체험기 수치 남음: {sorted(k)}")
    if not persona and fragment_only(s):
        why.append("살릴 사실 없음(낱말 조각)")
    # 🔄 10-06 (팀장 전달 §2 #5) — 종전에는 「도움」이 있으면 이 검사를 통째로 건너뛰어 「…달인 곶감은 면역에 도움」이 지나갔다.
    #    이제 늘 보고, 「도움」 문장에서는 인정 문구 낱말(`_claim_word`)만 허용한다
    if persona:
        # 말투가 넣은 낱말 중 건강 고민 · 몸 상태 낱말 — 원문(1단계 문장)에 없던 것만
        cue = sorted({w for w in new_words(original, s) if HEALTH_CUE.search(w)})
        if cue:
            why.append(f"말투에 건강 고민 낱말: {', '.join(cue[:3])}")
        # 🆕 10-12 — 제품 모양에 안 맞는 쓰는 법을 지어냄(「선스틱, …두드리고」 · 「젤리 스틱, 물에 녹여」) · `usage_dict.py`
        from usage_dict import usage_mismatch  # noqa: PLC0415

        if bad_use := usage_mismatch(original, new_words(original, s)):
            why.append(f"쓰는 법이 제품과 안 맞음: {', '.join(bad_use[:2])}")
        if lost := facts_dropped(original, s):
            why.append(f"말투가 사실 낱말을 빼거나 바꿈: {', '.join(lost[:3])}")
        fact = sorted({w for w in new_words(original, s) if NEW_FACT.search(_PARTICLE.sub("", w))})
        if fact:
            why.append(f"말투가 지어낸 사실: {', '.join(fact[:3])}")
        if dose := dose_time_added(original, s):
            why.append(f"말투가 정한 용량 · 때: {', '.join(dose[:3])}")
    nw = [] if persona else new_words(original, s)
    if "도움" in s:
        nw = [w for w in nw if not _claim_word(w)]
    if nw:
        why.append(f"원문에 없는 낱말: {', '.join(nw[:3])}")
    return GateResult(not why, tuple(why))
