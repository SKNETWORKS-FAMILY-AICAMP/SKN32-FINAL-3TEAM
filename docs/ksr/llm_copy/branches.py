"""분기 6종 — 품목 × 인증·기능 여부 (설계 요약 §7).

분기 하나가 정하는 것: 프롬프트의 「쓸 수 있는 것」 · 코드 필터의 금지 낱말 · 고정 문구 필요 여부 · 판정엔진에 넘길 품목.
🚨 금지 낱말은 **임시 기준**이다 — 화장품은 판정 사전에 화장품법 항목이 0 이라 지침을 직접 옮겼다.
   지침이 사전에 편입되면 사전을 읽는 쪽으로 돌린다 (점검목록 §3-4).
🔗 화면의 분기 표는 `app/routers/user.py` `_GEN_BRANCHES` 다 — 이름 · 판정 전제(`premise`)가 여기의 `label` · `category` 와
   맞아야 한다. 앱이 이 폴더를 import 하지 않아 표가 둘이다 — `tests/test_user_screens.py` 가 둘을 견준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: GPT 가 고정 문구 자리에 쓰는 표시 — 코드가 인정·심사 문구를 끼운다 (§8-3)
PLACEHOLDER = "{{고정문구}}"

# 질병·치료 — 세 품목 공통. 식품 · 화장품은 의약품이 아니다
DISEASE = (
    "치료", "치유", "완치", "예방", "개선 효과", "질병", "질환", "증상", "염증", "항염", "소염",
    "항암", "발암", "암 예방", "암세포", "당뇨", "혈압", "혈당", "콜레스테롤", "고지혈", "관절염", "아토피", "습진",
    "비염", "감기에", "감기를", "감기 예방", "독감", "불면", "우울", "치매", "변비 해소", "해독", "디톡스", "독소",
    "약효", "처방", "의약", "부작용 없",
)  # fmt: skip

# 식품에 못 쓰는 기능성·효능 — 건강기능식품으로 오인시키는 표현
FOOD_FUNCTION = (
    "면역", "피로 회복", "피로회복", "체지방", "다이어트", "살이 빠", "감량", "항산화",
    "혈행", "간 건강", "장 건강", "뼈 건강", "눈 건강", "기억력", "집중력", "키 성장",
    "성장 발육", "노화 방지", "안티에이징", "활력 증진", "원기 회복", "숙면",
    "에 도움을 줄 수 있", "에 도움을 줍", "효능", "효과",
    "건강기능식품",
)  # fmt: skip

# 화장품 — 의약품 오인 (화장품법 제13조①1호 · 지침 [별표 1] 계열)
COSMETIC_DRUG = (
    "재생", "회복", "상처", "흉터", "여드름", "트러블 완화", "진정 효과", "살균", "항균",
    "발모", "양모", "탈모", "피부과", "세포", "줄기세포", "혈액순환", "부종", "붓기",
    "셀룰라이트", "지방 분해", "가려움", "면역",
)  # fmt: skip

# 화장품 — 기능성화장품 오인 (같은 조 2호). 심사·보고가 없으면 못 쓴다
COSMETIC_FUNCTION = (
    "미백", "화이트닝", "브라이트닝", "주름", "탄력 개선", "자외선", "SPF", "PA+",
    "기미", "주근깨", "잡티", "튼살", "안티에이징", "노화", "리프팅",
)  # fmt: skip

# 화장품 — 사실 확인이 필요한 표시 (입력에 근거가 없으면 지어낸 것)
COSMETIC_FACT = ("유기농", "천연", "무첨가", "저자극", "무자극", "알레르기 없")


@dataclass(frozen=True)
class Branch:
    key: str
    label: str
    #: 판정엔진에 넘기는 품목 (`app.contracts.Category` 의 값)
    category: str
    recognized: bool
    #: 프롬프트 — 허용 범위를 금지보다 먼저 준다 (§8-1)
    allowed: tuple[str, ...]
    rules: tuple[str, ...]
    forbidden: tuple[str, ...]
    #: 입력에 적혀 있을 때만 쓸 수 있는 낱말 — 심사·보고된 기능성(선크림의 SPF 등)
    unless_given: tuple[str, ...] = ()
    #: 인정·심사 문구가 **반드시** 들어가야 하는 분기인가
    needs_fixed: bool = False
    #: 이용자에게 먼저 보여 줄 안내 (건기식 · 인증 아니오)
    notice: str = ""
    good: tuple[str, ...] = field(default_factory=tuple)
    bad: tuple[tuple[str, str], ...] = field(default_factory=tuple)


_FOOD_ALLOWED = (
    "맛 · 식감 · 향 (고소하다 · 바삭하다 · 진하다)",
    "먹는 장면 · 시간대 (아침 · 간식 · 캠핑)",
    "입력에 적힌 원재료와 그 산지 · 가공 방식",
    "입력에 적힌 사실 (용량 · 포장 · 보관)",
)
_FOOD_RULES = (
    "몸에 미치는 효과 · 기능을 말하지 않는다 (건강기능식품이 아니다)",
    "질병 · 증상 · 치료 · 예방을 말하지 않는다",
)
# 🚨 예시는 **시험 입력에 없는 제품**으로 쓰고 문장 틀을 서로 다르게 한다 — 같은 제품이면 GPT 가 예시를 그대로 돌려준다
_FOOD_GOOD = (
    "퇴근길에 하나, 쫄깃하게 구운 현미 가래떡",
    "얼음 동동 띄워 마시는 보리차 한 잔",
    "오늘 저녁은 들기름 향 가득한 막국수로 정했어요",
    "한입 베어 물면 터지는 방울토마토의 단맛",
)
_FOOD_BAD = (
    ("면역력을 채워 주는 보리차", "식품에 기능성 표현"),
    ("식이섬유 12g 으로 가볍게", "입력에 없는 수치"),
)

_COS_ALLOWED = (
    "사용감 · 제형 · 발림 (산뜻하다 · 촉촉하다 · 끈적임 없다)",
    "쓰는 장면 · 시간대 (세안 후 · 메이크업 전 · 자기 전)",
    "입력에 적힌 성분 이름 (효능을 붙이지 않고)",
    "보습 · 수분감 · 피부결 정돈 같은 화장품 본래 범위",
)
_COS_GOOD = (
    "샤워 후 물기 남은 몸에 쓱, 가볍게 퍼지는 바디로션",
    "뻑뻑함 없이 부드럽게 감기는 샴푸 거품",
    "자기 전 립밤 하나로 마무리해요",
    "손등에 덜면 금세 사라지는 묽은 제형의 토너",
)
_COS_BAD = (
    ("지친 피부를 재생시키는 바디로션", "의약품으로 오인 — 재생"),
    ("피부과 테스트를 마친 순한 토너", "입력에 없는 시험 사실"),
)

BRANCHES: dict[str, Branch] = {
    b.key: b
    for b in (
        Branch(
            key="food_no",
            label="식품 · 인증 아니오",
            category="식품",
            recognized=False,
            allowed=_FOOD_ALLOWED,
            rules=_FOOD_RULES,
            forbidden=DISEASE + FOOD_FUNCTION,
            good=_FOOD_GOOD,
            bad=_FOOD_BAD,
        ),
        Branch(
            key="food_yes",
            label="식품 · 인증 예 (HACCP 등)",
            category="식품",
            recognized=False,
            allowed=_FOOD_ALLOWED
            + ("입력에 적힌 인증을 **사실로만** 언급 (예: HACCP 인증 시설에서 만든)",),
            rules=_FOOD_RULES + ("인증은 효능을 열어 주지 않는다 — 인증과 효과를 잇지 않는다",),
            forbidden=DISEASE + FOOD_FUNCTION,
            good=_FOOD_GOOD + ("HACCP 인증 시설에서 빚은 손만두",),
            bad=_FOOD_BAD + (("HACCP 인증으로 검증된 건강 효과", "인증을 효능의 근거로 씀"),),
        ),
        Branch(
            key="hf_yes",
            label="건강기능식품 · 인증 예 (기능성 인정)",
            category="건기식",
            recognized=True,
            allowed=(
                f"인정 기능성 문구는 직접 쓰지 않고 그 자리에 {PLACEHOLDER} 를 한 번 넣는다",
                "먹는 방법 · 습관 · 장면 (하루 한 번 · 출근 전)",
                "제형 · 맛 · 휴대 (작은 정제 · 스틱 포장)",
                "입력에 적힌 원료 이름과 사실",
            ),
            rules=(
                f"기능성은 {PLACEHOLDER} 로만 말한다 — 풀어 쓰거나 강조어(확실히 · 빠르게)를 붙이지 않는다",
                "그 밖의 효능 · 질병 · 치료 · 예방을 말하지 않는다",
            ),
            forbidden=DISEASE,
            needs_fixed=True,
            good=(
                f"출근 전 한 알, {PLACEHOLDER}",
                f"{PLACEHOLDER} — 작은 정제로 간편하게",
                f"가방 속 스틱 하나면 돼요. {PLACEHOLDER}",
                f"물 없이 씹어 먹는 츄어블, {PLACEHOLDER}",
            ),
            bad=(
                ("뼈 건강을 확실하게 지켜 주는 칼슘", "인정 문구를 고쳐 씀 · 강조어"),
                (f"{PLACEHOLDER} 관절염까지 해결", "인정 범위 밖 효능"),
            ),
        ),
        Branch(
            key="hf_no",
            label="건강기능식품 · 인증 아니오",
            category="식품",
            recognized=False,
            allowed=_FOOD_ALLOWED,
            rules=_FOOD_RULES,
            forbidden=DISEASE + FOOD_FUNCTION,
            notice="기능성 인정이 없으면 건강기능식품으로 광고할 수 없습니다. 일반식품으로 생성합니다.",
            good=_FOOD_GOOD,
            bad=_FOOD_BAD,
        ),
        Branch(
            key="cos_no",
            label="화장품 · 인증 아니오 (일반)",
            category="화장품",
            recognized=False,
            allowed=_COS_ALLOWED,
            rules=(
                "의약품처럼 말하지 않는다 (치료 · 재생 · 여드름 · 흉터)",
                "기능성화장품 효능을 말하지 않는다 (미백 · 주름 · 자외선 차단)",
                "천연 · 유기농 · 무첨가 · 저자극은 입력에 있을 때만",
            ),
            forbidden=DISEASE + COSMETIC_DRUG + COSMETIC_FUNCTION,
            good=_COS_GOOD,
            bad=_COS_BAD + (("바르는 순간 환해지는 미백 로션", "기능성 심사 없는 미백"),),
        ),
        Branch(
            key="cos_yes",
            label="화장품 · 인증 예 (기능성 심사·보고)",
            category="화장품",
            recognized=True,
            allowed=_COS_ALLOWED
            + (f"심사·보고된 효능은 직접 쓰지 않고 그 자리에 {PLACEHOLDER} 를 한 번 넣는다",),
            rules=(
                f"기능성 효능은 {PLACEHOLDER} 로만 말한다 — 범위를 넓히지 않는다",
                "의약품처럼 말하지 않는다 (치료 · 재생 · 여드름 · 흉터)",
            ),
            forbidden=DISEASE + COSMETIC_DRUG,
            unless_given=COSMETIC_FUNCTION,
            needs_fixed=True,
            good=(
                f"아침 스킨케어 마지막 단계, {PLACEHOLDER}",
                f"{PLACEHOLDER} — 묽게 퍼지는 에센스",
                f"화장솜에 덜어 가볍게 닦아 내요. {PLACEHOLDER}",
            ),
            bad=(
                ("주름을 지워 주는 기적의 크림", "심사 문구를 고쳐 씀 · 과장"),
                (f"{PLACEHOLDER} 피부 재생까지", "의약품으로 오인"),
            ),
        ),
    )
}

#: 프롬프트가 후보를 나눠 뽑는 각도 (§8-2) — 3개를 고를 때도 각도가 겹치지 않게 한다
ANGLES = ("사용 장면", "감각", "원료 이야기", "대상", "제품 사실")
