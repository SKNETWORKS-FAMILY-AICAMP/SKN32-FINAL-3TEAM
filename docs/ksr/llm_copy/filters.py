"""코드 필터 — 판정 전에 거른다 (설계 요약 §4).

판정엔진은 법 위반만 본다. **입력에 없는 사실을 지어낸 문장**은 위반이 아니라서 엔진이 못 잡는다 — 그래서 코드가 먼저 거른다.
🚨 표면 형태만 본다 — 숫자 · 목록에 안 걸리는 「말로 풀어 쓴 새 주장」은 지나간다 (점검목록 §3-3).
"""

from __future__ import annotations

import difflib
import functools
import json
import pathlib
import re
from dataclasses import dataclass

from branches import COSMETIC_FACT, PLACEHOLDER, Branch

ROOT = pathlib.Path(__file__).resolve().parents[3]
DICT_FILE = ROOT / "data/derived/banned_terms.jsonl"
COSMETIC_INGREDIENT_FILE = ROOT / "data/derived/cosmetic_ingredient.jsonl"

#: 탈락 사유 유형 — 다음 라운드 프롬프트에는 **이 이름과 건수만** 넘긴다 (§5-3 · 탈락 문구 원문은 안 넘긴다)
REASONS = {
    "format": "길이 범위 밖",
    "duplicate": "보관분 · 이전 후보와 거의 같음",
    "number": "입력에 없는 수치",
    "cert": "입력에 없는 인증 · 시험 사실",
    "ingredient": "입력에 없는 성분",
    "superlative": "비교 · 최상급",
    "forbidden": "분기 금지어",
    "fixed": "고정 문구 자리가 없거나 여럿",
    "judge": "판정엔진 미통과",
}

MIN_LEN, MAX_LEN = 8, 60
DUP_RATIO = 0.8

CERT_WORDS = (
    "인증", "특허", "임상", "테스트", "시험", "검증", "수상", "선정", "논문", "연구 결과",
    "전문의", "의사", "약사", "피부과", "FDA", "식약처", "HACCP", "GMP", "ISO", "비건",
    "더마", "입증", "검사 완료", "심사",
)  # fmt: skip

SUPERLATIVE = (
    "최고", "최상", "최초", "최대", "최저", "유일", "1위", "1등", "넘버원", "No.1", "no.1",
    "타사", "경쟁사", "다른 제품보다", "어디에도 없는", "국내 최", "세계 최", "업계",
    "완벽", "기적", "만능", "절대", "무조건", "반드시", "확실",
)  # fmt: skip

# 화장품 광고에 흔한 성분 계열 이름 — 원료 사전은 「세라마이드엔피」처럼 정식 이름만 갖는다
COSMETIC_COMMON = (
    "세라마이드", "펩타이드", "레티놀", "레티날", "콜라겐", "엘라스틴", "나이아신아마이드",
    "비타민", "판테놀", "시카", "병풀", "티트리", "알로에", "스쿠알란", "히알루론산",
    "AHA", "BHA", "PHA", "프로폴리스", "어성초", "녹차", "마데카소사이드", "알부틴",
    "아데노신", "글루타치온", "살리실산", "유산균", "발효",
)  # fmt: skip

# 식품 · 건기식에서 「성분」으로 읽히는 이름 — 화장품은 원료 사전(`cosmetic_ingredient.jsonl`)을 쓴다.
# 🚨 손으로 적은 임시 목록이다 — 식품 쪽 원료 사전을 무엇으로 할지는 아직 안 정했다 (점검목록 2-4)
FOOD_INGREDIENTS = (
    "비타민", "미네랄", "칼슘", "마그네슘", "아연", "철분", "셀레늄", "오메가3", "오메가-3",
    "DHA", "EPA", "루테인", "콜라겐", "히알루론산", "프로바이오틱스", "유산균", "프리바이오틱스",
    "식이섬유", "단백질", "아미노산", "BCAA", "홍삼", "인삼", "녹용", "밀크씨슬", "실리마린",
    "글루코사민", "MSM", "코엔자임", "쏘팔메토", "가르시니아", "카테킨", "폴리페놀", "안토시아닌",
    "베타글루칸", "프로폴리스", "크릴오일", "스피루리나", "클로렐라", "레시틴", "타우린",
    "카페인", "테아닌", "커큐민", "강황", "흑마늘", "양배추", "노니", "석류", "아사이",
    "올리고당", "자일리톨", "스테비아", "알룰로스",
)  # fmt: skip

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_KOR_MULT = re.compile(r"(두|세|네|다섯|열|몇)\s?배")
_SQUEEZE = re.compile(r"[\s\W_]+")


def squeeze(text: str) -> str:
    """띄어쓰기 · 문장부호를 뺀 글자열 — 「피로 회복」과 「피로회복」을 같게 본다."""
    return _SQUEEZE.sub("", text).lower()


@dataclass(frozen=True)
class Inputs:
    """이용자가 적은 것 — 여기 적힌 것이 「제품 사실」의 전부다 (§2-2)."""

    #: 🔄 제품명 · 유형은 선택 칸이다 — 분기 + 대상 + 간단한 문구만으로도 돈다
    name: str = ""
    kind: str = ""
    #: 이용자가 적은 간단한 문구 — 제품을 한 줄로 설명한 것. 여기 든 낱말 · 숫자도 「입력에 있는 것」이다
    phrase: str = ""
    features: tuple[str, ...] = ()
    ingredients: tuple[str, ...] = ()
    certs: tuple[str, ...] = ()
    #: 인정 기능성 문구 · 심사 효능 문구 — 글자 그대로 끼운다
    fixed: str = ""
    target: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> Inputs:
        if not any(d.get(k) for k in ("name", "kind", "phrase", "features")):
            raise ValueError("제품명 · 유형 · 간단한 문구 · 특징 중 하나는 있어야 한다")
        return cls(
            name=d.get("name", ""),
            kind=d.get("kind", ""),
            phrase=d.get("phrase", ""),
            features=tuple(d.get("features", ())),
            ingredients=tuple(d.get("ingredients", ())),
            certs=tuple(d.get("certs", ())),
            fixed=d.get("fixed", ""),
            target=d.get("target", ""),
        )

    def text(self) -> str:
        parts = (
            self.name,
            self.kind,
            self.phrase,
            *self.features,
            *self.ingredients,
            *self.certs,
            self.target,
        )
        return " ".join(p for p in parts if p)


@functools.cache
def cosmetic_ingredients() -> frozenset[str]:
    """화장품 원료 이름 — 3자 이상만 (「꿀」 · 「물」 같은 짧은 이름은 일반 낱말과 겹친다)."""
    if not COSMETIC_INGREDIENT_FILE.exists():
        return frozenset()
    names: set[str] = set()
    with COSMETIC_INGREDIENT_FILE.open(encoding="utf-8") as f:
        for line in f:
            name = json.loads(line).get("INGR_KOR_NAME", "").strip()
            if len(name) >= 3 and " " not in name:
                names.add(name)
    return frozenset(names)


@functools.cache
def dict_terms() -> tuple[str, ...]:
    """판정 사전의 단독판정 낱말 — 엔진이 어차피 잡을 것을 미리 거른다 (판정 호출을 아낀다)."""
    if not DICT_FILE.exists():
        return ()
    out = []
    with DICT_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("단독판정") and len(row["term"]) >= 2:
                out.append(squeeze(row["term"]))
    return tuple(t for t in out if t)


def _hits(words: tuple[str, ...] | frozenset[str], cand: str, given: str) -> list[str]:
    """후보에는 있고 입력에는 없는 낱말."""
    return [w for w in words if squeeze(w) in cand and squeeze(w) not in given]


def too_similar(text: str, others: list[str]) -> bool:
    a = squeeze(text)
    return any(difflib.SequenceMatcher(None, a, squeeze(o)).ratio() >= DUP_RATIO for o in others)


def check(text: str, inputs: Inputs, branch: Branch, seen: list[str]) -> tuple[str, str] | None:
    """탈락이면 `(사유 유형, 걸린 것)` · 통과면 `None`. `text` 는 고정 문구를 끼우기 **전**의 후보다."""
    n_fixed = text.count(PLACEHOLDER)
    if branch.needs_fixed and n_fixed != 1:
        return "fixed", f"자리표시자 {n_fixed}개"
    if not branch.needs_fixed and n_fixed:
        return "fixed", "이 분기는 고정 문구가 없다"
    # 고정 문구 안의 효능 낱말은 허용된 것이다 — 나머지 글자만 검사한다
    body = text.replace(PLACEHOLDER, " ").strip()
    if not MIN_LEN <= len(body) <= MAX_LEN and not (branch.needs_fixed and len(body) >= 4):
        return "format", f"{len(body)}자"
    if too_similar(text, seen):
        return "duplicate", ""

    cand, given = squeeze(body), squeeze(inputs.text())
    if hit := [w for w in SUPERLATIVE if squeeze(w) in cand]:
        return "superlative", hit[0]
    nums = [n for n in _NUM.findall(body) if n not in inputs.text()]
    if nums or _KOR_MULT.search(body):
        return "number", ", ".join(nums) or "배수"
    if hit := _hits(CERT_WORDS, cand, given):
        return "cert", hit[0]
    is_cosmetic = branch.category == "화장품"
    names = (
        cosmetic_ingredients() | set(COSMETIC_COMMON) | set(FOOD_INGREDIENTS)
        if is_cosmetic
        else FOOD_INGREDIENTS
    )
    if hit := _hits(tuple(names), cand, given):
        return "ingredient", max(hit, key=len)
    if hit := [w for w in branch.forbidden if squeeze(w) in cand]:
        return "forbidden", hit[0]
    if hit := _hits(branch.unless_given, cand, given):
        return "forbidden", hit[0]
    if is_cosmetic and (hit := _hits(COSMETIC_FACT, cand, given)):
        return "forbidden", hit[0]
    if hit := [t for t in dict_terms() if t in cand and t not in given]:
        return "forbidden", f"사전:{hit[0]}"
    return None


def render(text: str, inputs: Inputs) -> str:
    """고정 문구를 끼운다 — GPT 가 쓰지 않고 코드가 넣는다 (§8-3)."""
    return text.replace(PLACEHOLDER, inputs.fixed).strip()
