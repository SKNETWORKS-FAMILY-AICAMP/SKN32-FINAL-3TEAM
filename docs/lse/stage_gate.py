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
    r"치료|완치|예방|낫|증후군|질환|질병|[가-힣]{1,6}병(?![원아])|[가-힣]*통(?:증)?에|관절통|두통|당뇨|고혈압|암(?:을|에|세포|예방)|"
    r"빈혈|감기|비만|아토피|탈모|변비|불면증|우울증|골다공증|염증|[가-힣]+염(?![색료])"
)
#: 의약품 · 의약품 오인
#:    🔄 10-01 — 「[가-힣]+약」 꼴은 「곤약」 · 「치약」을 잡았다 → 의약품 낱말을 직접 적는다
DRUG = re.compile(
    r"의약품|처방|치료제|수면제|소화제|진통제|해열제|항생제|발모제|호르몬제|스테로이드|위고비|인슐린|주사|복용|"
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
#: 숫자 — 성분명에 붙은 숫자(코엔자임 Q10 · CO2 · 비타민 B12)는 수치 주장이 아니다
NUM = re.compile(r"(?<![A-Za-z\d])\d+")


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


HF_CLAIMS = ROOT / "data" / "derived" / "hf_display_claims.jsonl"
#: 「~에 도움」 앞의 주장 구 — 「X에 도움」 · 「X하는 데 도움」 · 「X하는데 도움」
CLAIM = re.compile(r"([가-힣A-Za-z0-9·,\s()]{2,40}?)(?:에|하는\s*데|하는데|되는\s*데)\s*도움")


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
            continue  # 기능성화장품 범주 — 식품 고시에 없다
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
    hits = dm.find(s, dict_entries())
    if hits:
        why.append("금지 사전: " + ", ".join(sorted({h.entry.term for h in hits})[:3]))
    if m := DISEASE.search(s):
        why.append(f"질병 표현: {m.group()}")
    if m := DRUG.search(s):
        why.append(f"의약품 표현: {m.group().strip()}")
    kept = set(NUM.findall(original)) & set(NUM.findall(s))
    if kept:
        why.append(f"원문 숫자 남음: {sorted(kept)}")
    if m := TESTIMONY.search(s):
        why.append(f"체험기 말투: {m.group()}")
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
    if (g := ingredient_changed(original, s)) is not None:
        why.append(f"원문에 없는 원료명: {g}")
    return GateResult(not why, tuple(why))
