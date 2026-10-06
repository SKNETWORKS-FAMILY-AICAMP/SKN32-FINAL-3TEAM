"""1단계 후처리 — 막지 않고 **고친다** (2026-10-05).

관문(`stage_gate.py`)은 「막을 이유」를 찾는다. 여기는 1단계가 낸 문장의 **기계로 고칠 수 있는 실수**를 관문 전에 고친다.
실제 광고 정답표의 조건부 7개 중 보류 5개를 뜯어보니 「조건을 못 써서」가 아니라 베끼기 실수 · 지어낸 기능성 문구였다.

  ① 원료명 수리   — 앞부분을 떼었으면(「○○ △△추출물 → △△추출물」) 원문에서 이름 전체를 되찾고,
                    한 글자 틀렸으면 원문 표기로 되돌린다.
  ② 공식 문구로   — 관문이 「인정되지 않은 기능성」으로 막은 문장을, 원문 · 고친 문장의 낱말로 식약처 인정 문구(`CLAIMS`)를 골라 바꾼다.
                    🚨 위반 유형에 건강기능식품_오인이 있으면 하지 않는다(일반식품은 기능성 주장 자체가 안 된다).
                    🚨 낱말이 두 기능 이상을 가리키면(모호) 하지 않는다 — 고르지 못한 것을 고른 척하지 않는다.
  ③ 조건 붙이기   — 1단계의 조건 칸(`mandatory_note`)은 자유 글이라 없는 범주를 지어낸다(「모공 기능성화장품」).
                    정해진 메뉴(`NOTE_MENU`) 안의 조건만 받고, 본문이 요구하는 조건(기능성 → 인정 제품 한정 · 함유 → 함량 병기)은 붙인다.

🚨 고친 문장도 관문을 **다시** 지난다 — 후처리가 위반을 들여오지 않았는지는 관문이 본다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from stage_gate import (  # noqa: E402
    _ING_NAME,
    DISEASE,
    DRUG,
    INGREDIENT,
    approved_blob,
    ingredient_truncated,
)

from app import dictmatch as dm  # noqa: E402

# ── ① 원료명 수리 ────────────────────────────────────────────────────────────


def _lev1(a: str, b: str) -> bool:
    """편집 거리 1 이하(한 글자 바꿈 · 넣음 · 뺌)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


def _original_form(original: str, norm_piece: str) -> str | None:
    """정규화 조각을 원문 표기(띄어쓰기 포함)로 되찾는다."""
    pat = r"\s*".join(map(re.escape, norm_piece))
    m = re.search(pat, original)
    return m.group() if m else None


def _names(s: str) -> list[str]:
    out = []
    for m in list(_ING_NAME.finditer(s)) + list(INGREDIENT.finditer(s)):
        n = (m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else "") or "").strip()
        if n and n not in out:
            out.append(n)
    return out


def repair_ingredients(original: str, s: str) -> tuple[str, list[str]]:
    """원료명 베끼기 실수를 원문 표기로 되돌린다. (고친 문장, 고친 내역)."""
    fixes: list[str] = []
    o = dm.norm(original)
    # 앞부분 잘림 — 관문 검사가 돌려준 「앞말 이름」으로 바꾼다
    for _ in range(3):
        t = ingredient_truncated(original, s)
        if not t:
            break
        full = t.split()[-1] if " " in t else t
        cut = t.rsplit(" ", 1)[-1]
        for name in sorted(_names(s), key=len, reverse=True):
            nn = dm.norm(name)
            if dm.norm(cut).endswith(nn) or dm.norm(t).endswith(nn):
                s2 = s.replace(name, t if " " in t else full, 1)
                if s2 != s:
                    fixes.append(f"앞부분 되찾음: {name} → {t}")
                    s = s2
                break
        else:
            break
    # 한 글자 오타 — 원문에 없는 이름을 원문의 같은 길이(±1) 조각과 대조한다
    for name in _names(s):
        nn = dm.norm(name)
        if len(nn) < 4 or nn in o:
            continue
        best = None
        for L in (len(nn), len(nn) + 1, len(nn) - 1):  # 바꿈 → 넣음 → 뺌 순(뺌을 먼저 보면 한 글자 짧은 엉뚱한 조각이 먼저 잡힌다)
            for i in range(0, max(0, len(o) - L) + 1):
                piece = o[i:i + L]
                if piece[-2:] == nn[-2:] and _lev1(piece, nn):
                    best = piece
                    break
            if best:
                break
        if best and (form := _original_form(original, best)):
            s = s.replace(name, form, 1)
            fixes.append(f"오타 되돌림: {name} → {form}")
    return s, fixes


# ── ② 공식 기능성 문구 ────────────────────────────────────────────────────────

#: 식약처 인정 기능성 문구(`hf_display_claims` · 재배포 가능)에서 고른 깨끗한 꼴 — 낱말 → 문구.
#: 🚨 문구마다 관문의 인정 기능성 대조(`unapproved_claim`)를 통과하는지 시험이 본다(`test_postfix` 대신 __main__ 자가 점검).
CLAIMS: list[tuple[tuple[str, ...], str]] = [
    (("체지방", "다이어트", "감량", "뱃살", "살 빠", "살빠", "지방"), "체지방 감소에 도움을 줄 수 있음"),  # redistribution: ok — 일반어 키워드
    (("뼈",), "뼈 건강에 도움을 줄 수 있음"),
    (("눈", "시력", "안구"), "눈의 피로 개선에 도움을 줄 수 있음"),
    (("혈당", "당뇨"), "식후 혈당상승 억제에 도움을 줄 수 있음"),
    (("관절", "연골", "무릎"), "관절 건강에 도움을 줄 수 있음"),
    (("간 ", "간수치", "간 건강", "간건강", "간 해독"), "간 건강에 도움을 줄 수 있음"),  # redistribution: ok — 일반어 키워드
    (("면역",), "면역기능 증진에 도움을 줄 수 있음"),
    (("배변", "변비", "장 건강", "장건강", "쾌변"), "배변활동 원활에 도움을 줄 수 있음"),
    (("혈압",), "혈압 조절에 도움을 줄 수 있음"),
    (("콜레스테롤",), "혈중 콜레스테롤 개선에 도움을 줄 수 있음"),
    (("기억력", "두뇌", "머리가 좋"), "기억력 개선에 도움을 줄 수 있음"),
    (("보습", "건조한 피부", "피부 건조"), "피부 보습에 도움을 줄 수 있음"),
    (("항산화", "활성산소"), "항산화에 도움을 줄 수 있음"),  # 🔄 10-05 「노화」 뺌 — 노화 방지는 인정 기능이 아니다(항산화와 다르다 · 정답표 #17)
    (("혈행", "혈액순환", "혈액 순환", "피가 맑"), "혈행 개선에 도움을 줄 수 있음"),  # redistribution: ok — 일반어 키워드
]
#: 기능성화장품 범주(화장품법 시행규칙 [별표 3]) — 낱말 → (범주, 공식 문구)
COSMETIC = [
    (("미백", "기미", "주근깨", "하얘"), "미백", "피부의 미백에 도움을 줍니다"),
    (("주름",), "주름", "피부의 주름 개선에 도움을 줍니다"),
    (("자외선", "선크림", "SPF"), "자외선", "자외선으로부터 피부를 보호하는 데 도움을 줍니다"),
    (("탈모",), "탈모", "탈모 증상의 완화에 도움을 줍니다"),
    (("여드름",), "여드름", "여드름성 피부를 완화하는 데 도움을 줍니다"),
    (("피부장벽",), "피부장벽", "피부장벽의 기능을 회복하여 가려움 등의 개선에 도움을 줍니다"),
    (("튼살",), "튼살", "튼살로 인한 붉은 선을 엷게 하는 데 도움을 줍니다"),
    (("염색", "새치", "흰머리", "모발 색"), "염모", "모발의 색상을 변화시키는 데 도움을 줍니다"),  # 🆕 10-05
]
def _kw(k: str, text: str) -> bool:
    """낱말 찾기 — 공백을 단 키워드(「간 」)는 앞이 한글이 아닐 때만(「인간」 · 「시간」에 걸리지 않게). 「뼈」 · 「눈」은 그대로 찾는다."""
    if k.endswith(" "):
        return re.search(rf"(?<![가-힣]){re.escape(k.strip())}(?:\s|건강|수치|해독|기능)", text) is not None
    return k in text


_COSMETIC_PRODUCT = re.compile(
    r"크림|세럼|앰플|토너|로션|에센스|샴푸|패드|마스크팩|선크림|선스틱|바르|화장품|토닉|미스트|비누|클렌저|클렌징|립밤|바디워시|트리트먼트|두피|롤온"
)  # 🚨 「팩」은 넣지 않는다 — 「멸치 육수팩」
_CLAIM_HOLD = ("인정되지 않은 기능성", "기능성 주장(도움 꼴 아님)")


def to_approved_claim(original: str, s: str, labels: list[str]) -> tuple[str, str] | None:
    """(공식 문구, 조건) 또는 None. 원문과 고친 문장에서 낱말을 찾아 **하나의 기능**으로 모일 때만 고른다."""
    if "건강기능식품_오인" in labels:
        return None
    # 🔄 10-05 — 원문이 질병 · 의약품을 표방하면 바꾸지 않는다(정답표 기준 불가). 호르몬 작용을 주장한 실제 광고가
    #    「간 건강에 도움」이 됐다(정답표 v2 · 위반 포장) — 「간」 낱말이 「인간」에 걸렸고, 호르몬 주장은 고칠 대상이 아니다
    if {"질병_예방치료_표방", "의약품_오인"} & set(labels) or DISEASE.search(original) or DRUG.search(original)             or re.search(r"호르몬|치료|완치|처방", original):
        return None
    text = f"{original} {s}"
    if _COSMETIC_PRODUCT.search(original):
        hits = {(cat, claim) for kws, cat, claim in COSMETIC if any(k in text for k in kws)}
        if len(hits) == 1:
            cat, claim = next(iter(hits))
            return claim, f"{cat} 기능성화장품으로 심사·보고된 제품에 한함"
        return None
    hits = {claim for kws, claim in CLAIMS if any(_kw(k, text) for k in kws)}
    if len(hits) == 1:
        return next(iter(hits)), NOTE_FOOD_FUNC
    return None


# ── ④ 위반 유형 · 주어 검사 (관문은 위반 유형을 모른다) ─────────────────────────

_FOOD_FORM = re.compile(r"먹는|마시는|섭취|캡슐|알약|정제|환|드세요|드시")
_SUBJECT = re.compile(r"^\s*([가-힣A-Za-z0-9·\-() ]{2,40}?)(?:은|는)\s+.*도움")


def label_check(original: str, s: str, labels: list[str]) -> list[str]:
    """🆕 10-05 (v12) — 관문이 못 보는 것. ① 위반 유형이 건강기능식품_오인인데 기능성 주장(「~에 도움」)을 냈다 —
    일반식품은 기능성 주장 자체가 안 된다(정답표 기준 불가). ② 「○○은 ~에 도움」의 주어(원료명)가 원문에 없고 공식 원료명도 아니다 —
    v12 가 존재하지 않는 원료명을 지어냈다(실제 광고 1건 · 위반 포장)."""
    why: list[str] = []
    if "건강기능식품_오인" in labels and "도움" in s:
        why.append("건기식 오인 문구에 기능성 주장")
    if any(c[:8] in s for _, _, c in COSMETIC) and _FOOD_FORM.search(original):
        why.append("먹는 제품에 화장품 기능성")
    official_cos = any(c[:8] in s for _, _, c in COSMETIC)  # 공식 화장품 문구(「튼살로 인한 붉은 선」의 「은」은 주어 표시가 아니다)
    if not official_cos and (m := _SUBJECT.match(s)) and not re.search(r"(?:을|를|으로|로부터)\s|하$|되$", m.group(1).strip() + " "):
        # 「여드름성 피부를 완화하는 데 도움」의 「하는」은 주어 표시가 아니다 — 목적어 조사가 있거나 동사로 끝나면 주어가 아니다
        subj = m.group(1).strip()
        core = dm.norm(re.sub(r"\([^)]*\)", "", subj))
        # 공식 문구의 주어(「크레아틴의 섭취는」 · 「혈압이 높은 사람에게」)는 원문에 없어도 된다 — 인정 문구 본문에서도 찾는다
        if (len(core) >= 3 and core not in dm.norm(original) and core not in _official_ingredients()
                and core not in approved_blob()):
            why.append(f"원문에 없는 원료명(주어): {subj}")
    return why


def _official_ingredients() -> str:
    """식약처 인정 원료명(고시 · 개별인정 · 재배포 가능) — 주어가 공식 원료명이면 원문에 없어도 된다."""
    global _OFFICIAL
    if _OFFICIAL is None:
        import json  # noqa: PLC0415

        path = HERE.parents[1] / "data" / "derived" / "hf_display_claims.jsonl"
        names = []
        # 🔴 2026-10-06 (ohb 흡수 검토) — 파일이 없으면 멈춘다 (D-220). ⛔ 종전에는 빈 목록으로 지나가
        #    「공식 원료명에 있는가」 대조가 늘 「없음」이 됐다. `stage_gate.approved_blob` · `dict_entries` 와 같은 규칙이다
        if not path.exists():
            raise FileNotFoundError(f"🔴 {path} 가 없다 — 공식 원료명 대조 없이 후처리를 돌리지 않는다.")
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            names.append(dm.norm(re.sub(r"\([^)]*\)", "", r.get("APLC_RAWMTRL_NM") or "")))
        _OFFICIAL = "\n".join(n for n in names if n)
    return _OFFICIAL


_OFFICIAL: str | None = None


# ── ③ 조건 ───────────────────────────────────────────────────────────────────

NOTE_FOOD_FUNC = "기능성 인정 건강기능식품에 한해 표시"
NOTE_CONTENT = "원재료 함량을 함께 표시"
NOTE_RANK = "순위 · 인증 · 수상은 근거(기관 · 기간 · 번호)와 함께만"
NOTE_NUTRI = "영양성분 기능 표시 — 함량 기준 충족 시"
_COS_CATS = "|".join(c for _, c, _ in COSMETIC)
#: 받는 조건 — 이 밖의 조건은 지어낸 것으로 본다
NOTE_MENU = [
    re.compile(r"기능성\s*인정\s*건강기능식품에\s*한해"),
    re.compile(r"원재료\s*함량"),
    re.compile(r"순위.*근거"),
    re.compile(r"영양성분\s*기능\s*표시"),
    re.compile(rf"(?:{_COS_CATS}|해당)\s*기능성화장품으로\s*심사\s*·?\s*보고된"),
    # 🆕 10-05 (v12 화장품) — 염모 기능성 · 실증이 필요한 화장품 표현(논코메도제닉 · 저자극 · 내수성)
    re.compile(r"(?:모발\s*색상\s*변화|염모)\s*기능성화장품으로\s*심사\s*·?\s*보고된"),
    re.compile(r"내수성\s*시험"),
    re.compile(r"(?:인체적용시험|실증)\s*자료"),
]


_COS_NOTE = re.compile(r"기능성화장품")
_FOOD_NOTE = re.compile(r"건강기능식품|영양성분")


def condition(body: str, note: str | None, original: str = "") -> tuple[str | None, str | None]:
    """(최종 조건, 문제). 본문이 요구하는 조건을 먼저 정하고, 1단계 조건은 메뉴 안이고 요구와 어긋나지 않을 때만 쓴다.

    🆕 10-05 — **제품 종류와 맞는가.** 다이어트 보조제(식품)에 「해당 기능성화장품으로 심사·보고된」이 붙었다(실제 광고 1건 · 보류라
    나가지는 않았다). 원문 · 본문에 화장품 낱말(`_COSMETIC_PRODUCT`)이 있으면 화장품 — 화장품에는 건기식 · 영양성분 조건을,
    화장품이 아니면 기능성화장품 조건을 받지 않는다. 화장품의 「~에 도움」(일반화장품 표현)에는 건기식 조건을 붙이지 않는다."""
    cosmetic = bool(_COSMETIC_PRODUCT.search(f"{original} {body}"))
    need = None
    for _, cat, claim in COSMETIC:
        if claim[:8] in body:
            need = f"{cat} 기능성화장품으로 심사·보고된 제품에 한함"
            break
    if need is None and "도움" in body and not cosmetic:
        need = NOTE_FOOD_FUNC if "필요합니다" not in body else NOTE_NUTRI
    if need is None and "필요합니다" in body and not cosmetic:
        need = NOTE_NUTRI
    if need is None and "함유" in body:
        need = NOTE_CONTENT
    problem = None
    if note and not any(p.search(note) for p in NOTE_MENU):
        problem = f"메뉴 밖 조건: {note}"
        note = None
    if note and ((_COS_NOTE.search(note) and not cosmetic) or (_FOOD_NOTE.search(note) and cosmetic)):
        problem = f"제품 종류와 어긋난 조건({'화장품' if cosmetic else '식품'}): {note}"
        note = None
    if need and note and need.split()[0] not in note and not (need == NOTE_CONTENT and "함량" in note):
        # 1단계 조건이 본문과 어긋난다(「주름」 문장에 「미백」 조건) — 본문 쪽을 따른다
        problem = problem or f"본문과 어긋난 조건: {note}"
        note = None
    return (note or need), problem


if __name__ == "__main__":
    # 자가 점검 — 공식 문구가 관문의 인정 기능성 대조를 통과하는가 · 수리 예시
    from stage_gate import check, unapproved_claim

    bad = [c for _, c in CLAIMS if unapproved_claim(c)]
    print("관문이 안 받는 공식 문구:", bad or "없음")
    for o, s in [("영지 버섯추출물", "버섯추출물 함유"), ("아로니아잎추출물", "아로나아잎추출물 함유"),
                 ("모링가 잎추출물 듬뿍", "잎추출물 함유"), ("귀한 홍화씨 추출물", "홍화씨 추출물 함유")]:
        r, f = repair_ingredients(o, s)
        print(f"{o!r} | {s!r} → {r!r} {f} 관문 {check(o, r).passed}")
    print(to_approved_claim("뼈 성장 쑥쑥 칼슘", "뼈성장과 뼈강도를 지원합니다", []))
    print(to_approved_claim("국내 1위 다이어트 보조제, 3일만에 5kg 감량", "x", []))
    print(to_approved_claim("다이어트에 효과 좋은 곤약젤리", "x", ["건강기능식품_오인"]))
    print(condition("피부의 주름 개선에 도움을 줍니다", None), condition("세럼", "모공 기능성화장품으로 심사·보고된 세럼에 한함"))
