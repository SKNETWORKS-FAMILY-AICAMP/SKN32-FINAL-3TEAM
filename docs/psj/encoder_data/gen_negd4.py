"""판정 대상 아님(D)형 음성 v4 — 실험 전용, 채택은 팀장 판정 (🔄 2026-09-29 설계결정 준수판 · 박수진)

  set COPYLANE_REPO=C:\\SKN32-FINAL-3TEAM
  python gen_negd4.py                       # → proto_negd4.jsonl  (my_negd.txt 가 있으면 함께)

v2 · v3 → v4 에서 고친 것
  · 원천 행은 **split_manifest 의 train 으로 배정된 게시물**에서만 뽑는다 — 게시물(hf:i:*)이 하나라도 test_sentence 면 뺀다 (D-174)
  · **test 를 읽지 않는다** — v3 의 test 유사도 검사를 지웠다. 누수는 공식 물질화가 평가 쪽에서 뺀다 (D-174 · D-175)
  · 금지 어휘(효능 · 건강 · 의료 · 거래 조건 · 자랑)를 **모든 행**에 적용한다 — v3 는 새 행에만 걸어 v2 의 가격배송 18행 ·
    효능 문장(「체지방 감소에 효과적임」)이 남았다 (D-272 개정 — 거래 조건은 not_claim 이 아니다 · D-286 ⑥ — 효능 암시면 D 가 아니다)
  · 계보: provenance 는 **원천 ID**(`mfds_hf_ingredient_board`) · 템플릿은 `synthetic_template` · 생성기는 `generator` 칸 (D-71 · D-249)
    `redistributable` 은 `preprocess.lineage.lineage()` 로만 정한다 — 표에 없는 계보는 False + `lineage_pending: True` (D-220)
  · 블록 제목(D-286 ④)은 넣지 않는다 — 결정 예시가 평가 문구와 같다

규칙 근거: D-286 ③(섭취대상만 · 효능 없음 → D) · D-275(인코더는 not_claim 을 내지 않는다 — 음성은 학습 재료일 뿐)
"""

import hashlib
import json
import os
import random
import re
import sys
from collections import Counter

REPO = os.environ.get("COPYLANE_REPO", r"C:\SKN32-FINAL-3TEAM")
sys.path.insert(0, REPO)
try:
    from preprocess.lineage import lineage
except ImportError as e:
    raise SystemExit(
        f"🔴 preprocess.lineage 를 못 읽었다 — COPYLANE_REPO={REPO} 를 저장소 경로로 둔다"
    ) from e

HF = os.path.join(REPO, "data", "derived", "mfds_hf_labels.jsonl")
MANIFEST = os.path.join(REPO, "data", "derived", "golden", "split_manifest.json")
HERE = os.path.dirname(os.path.abspath(__file__))
rng = random.Random(20260929)

#: 음성에 넣지 않는 어휘 — 효능 · 건강 · 의료 · 거래 조건 · 입증이 필요한 자랑(B)
BLOCK = re.compile(
    r"건강|효과|효능|개선|도움|예방|치료|완화|회복|면역|질환|질병|증상|환자|당뇨|혈압|혈당|혈행|콜레스테롤|비만|다이어트|체중|체지방|"
    r"피로|활력|기능성|성장|발달|두뇌|기억|수면|스트레스|관절|뼈|장\s*건강|간\s*건강|소화|변비|해독|디톡스|항산화|노화|피부|미용|"
    r"의약|약사|의사|복용|처방|과민|부작용|이상사례|"
    r"할인|적립|무료|배송|최저가|특가|환불|반품|교환|보상|쿠폰|이벤트|사은품|1\+1|2\+1|\d\s*원|만원|가격|"
    r"최초|최고|유일|1위|인증|특허|수상|검증|입증|안심|안전|100\s*%|천연|무첨가|프리미엄"
)
#: 🔄 10-01 — 대상 · 알레르기 낱말은 **섭취 맥락일 때만** 막는다.
#:    「임산부 · 어린이는 섭취 전 상담」 같은 건기식형 섭취 주의 문구는 건기식 오인 단서라 음성에 넣지 않는다.
#:    「어린이 손에 닿지 않는 곳에 보관」 · 「영유아 질식 우려」 · 「알레르기 유발물질 ○○ 함유」(의무 표시)는 D 라 막지 않는다.
BLOCK_CONTEXT = re.compile(
    r"(임산부|수유부|어린이|영유아|노약자|유아|소아)[^.]{0,30}(섭취|복용|드시|드실|먹|상담|전문가)|"
    r"(섭취|복용)[^.]{0,30}(임산부|수유부|어린이|영유아|노약자|유아|소아)|"
    r"알레르기(?!\s*유발)"
)


def blocked(text: str):
    return BLOCK.search(text) or BLOCK_CONTEXT.search(text)


def norm_key(s):
    return re.sub(r"[\s·‧․ㆍ\-,.:()\[\]/]", "", s)


def split_lines(s):
    out = []
    for x in re.split(
        r"[\n\r]+|(?<=[.。])\s+|(?:^|\s)[-‐‑·•]\s+|\(\d\)\s*|[①②③④⑤]", s or ""
    ):
        x = re.sub(r"^[\s\-‐·•*\d\)\.]+", "", x).strip(" .")
        if 6 <= len(x) <= 90:
            out.append(x)
    return out


def train_hf_rows():
    """split_manifest 로 train 에 배정된 게시물 번호. 🔴 없으면 멈춘다 (D-174 · D-72)."""
    for p in (HF, MANIFEST):
        if not os.path.exists(p):
            raise SystemExit(
                f"🔴 없음: {p} — `launcher.py data-setup` 으로 받는다 (D-174 fail-closed)"
            )
    with open(MANIFEST, encoding="utf-8") as f:
        assign = json.load(f)["assign"]
    by_row = {}
    for k, v in assign.items():
        if k.startswith("hf:"):
            by_row.setdefault(int(k.split(":")[1]), set()).add(v)
    return {i for i, vs in by_row.items() if vs == {"train"}}


# ── 템플릿 — 대상만 · 방법 · 보관 · 표시 (효능 · 거래 조건 없음)
WHO = [
    "바쁜 직장인",
    "아침을 자주 거르는 분",
    "운동을 좋아하시는 분",
    "캠핑을 즐기는 분",
    "혼자 사는 자취생",
    "출장이 잦은 분",
    "간편한 한 끼를 찾는 분",
    "등산을 즐기시는 분",
    "야근이 잦은 직장인",
    "요리를 잘 안 하시는 분",
    "맛있는 간식을 찾는 분",
    "부모님 선물을 고민하시는 분",
    "휴대하기 편한 제품을 찾는 분",
    "새로운 맛을 좋아하시는 분",
    "대학생",
    "주말 나들이를 계획하시는 분",
    "선물용 제품을 찾으시는 분",
    "달지 않은 맛을 좋아하시는 분",
    "차 마시기를 즐기는 분",
]
WHO_T = [
    "{w}",
    "{w}께 추천합니다",
    "이런 분께 권해요: {w}",
    "{w}을 위한 제품",
    "{w}에게 알맞은 구성",
]
HOW_WHAT = [
    "물 200ml에 1포를 넣고",
    "우유 한 컵에 2스푼을 넣고",
    "뜨거운 물 150ml에 티백 1개를 넣고",
    "1회 1포를",
    "하루 2~3회 1정씩",
    "요거트나 시리얼에",
    "샐러드 위에",
    "밥 지을 때 쌀과 함께",
]
HOW_END = [
    "잘 저어 드세요",
    "흔들어 드십시오",
    "드시면 됩니다",
    "넣어 드세요",
    "뿌려 드셔도 좋아요",
    "섞어 드세요",
]
KEEP_WHERE = [
    "직사광선을 피해 서늘하고 건조한 곳에",
    "직사광선과 고온다습한 곳을 피해",
    "습기가 적고 서늘한 곳에",
    "개봉 후에는 냉장",
    "개봉 후 밀봉하여 냉장",
    "0~10℃에서 냉장",
    "-18℃ 이하에서 냉동",
    "상온에",
    "실온(1~35℃)에",
    "다른 용기에 옮기지 말고 그대로",
    "개봉한 제품은 지퍼백을 잠가",
]
KEEP_END = [
    "보관하세요",
    "보관하십시오",
    "보관해 주세요",
    "보관 바랍니다",
    "보관하여 주시기 바랍니다",
    "보관",
]
LABEL_INFO = [
    "소비기한: 제조일로부터 {m}개월",
    "소비기한은 제품 상단에 별도 표기",
    "제조일자: 용기 하단 표기일까지",
    "내용량 {g}g ({u}g x {n}포)",
    "총 내용량 {ml}ml",
    "{n}개입 ({u}g x {n})",
    "1박스 {n}포 구성",
    "영양정보는 제품 뒷면을 참고해 주세요",
    "원재료명: 정제수, 설탕, 사과농축과즙, 구연산, 향료",
    "원재료명 및 함량: 쌀 90%, 보리 10%",
    "원산지: 상세페이지 참조",
    "제조원: ○○식품(주)",
    "판매원: (주)○○컴퍼니",
    "소비자 상담실 080-000-0000 (평일 09:00~18:00)",
    "품목보고번호 20XX0000000-000",
    "식품유형: 과·채주스",
    "식품유형 : 기타가공품",
    "제조국: 대한민국",
    "분리배출: 종이",
    "분리배출 표시: 플라스틱(PET)",
    "용기는 깨끗이 헹궈 분리배출해 주세요",
    "포장재질: 폴리에틸렌(내면)",
]
HANDLE = [
    "개봉 후에는 가급적 빨리 드시기 바랍니다",
    "제품 특성상 침전물이 생길 수 있으나 품질에는 이상이 없습니다",
    "원료 특성상 제품마다 색상 차이가 있을 수 있습니다",
    "전자레인지에 용기째 넣지 마세요",
    "뜨거우니 드실 때 주의하세요",
    "포장재 모서리에 손이 베이지 않도록 주의하세요",
    "이미 개봉된 제품은 구입하지 마세요",
    "흔들면 거품이 생길 수 있습니다",
    "냉동 제품이므로 해동 후 재냉동하지 마세요",
    "제습제는 먹지 마세요",
]


def fill(t):
    return t.format(
        m=rng.choice([6, 9, 12, 18, 24]),
        g=rng.choice([30, 60, 90, 120, 300]),
        u=rng.choice([1, 2, 3, 5, 10, 20]),
        n=rng.choice([10, 14, 20, 30]),
        ml=rng.choice([180, 200, 350, 500, 1000]),
    )


def main():
    out_path = (
        sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "proto_negd4.jsonl")
    )
    my_path = os.path.join(HERE, "my_negd.txt")
    lin = {}

    def lineage_of(prov, origin):
        if (prov, origin) not in lin:
            try:
                lin[(prov, origin)] = (lineage(prov, origin)[1], False)
            except SystemExit:
                lin[(prov, origin)] = (
                    False,
                    True,
                )  # 🔴 표에 없는 계보 — 공개 불가로 두고 등재 대기 표시 (D-220 · D-249)
        return lin[(prov, origin)]

    rows, seen, drop = [], set(), Counter()

    def add(text, fam, prov, origin="proto_negative"):
        text = re.sub(r"\s+", " ", text).strip()
        k = norm_key(text)
        if len(text) < 4 or k in seen:
            drop["짧음·중복"] += 1
            return
        if blocked(text):
            drop["금지 어휘"] += 1
            if fam == "직접작성":
                print(f"  [제외 · 금지 어휘] {text}")
            return
        seen.add(k)
        redist, pending = lineage_of(prov, origin)
        rows.append(
            {
                "id": f"protonegd4:{fam}:{hashlib.sha1(text.encode()).hexdigest()[:10]}",
                "text": text,
                "labels": [],
                "근거": [],
                "조건": "D",
                "unit": "문장",
                "origin": origin,
                "provenance": prov,
                "generator": "gen_negd4",
                "구역": None,
                "split": "train",
                "redistributable": redist,
                "lineage_pending": pending,
                "family": fam,
            }
        )

    ok_rows = train_hf_rows()
    n_skip = 0
    with open(HF, encoding="utf-8") as f:
        hf_rows = [json.loads(x) for x in f]
    for i, r in enumerate(hf_rows):
        if i not in ok_rows:
            n_skip += 1
            continue
        for x in split_lines(r.get("섭취주의사항")):
            add(x, "섭취주의", "mfds_hf_ingredient_board")
        d = (r.get("일일섭취량") or "").strip()
        if 4 <= len(d) <= 90:
            add(d, "섭취량", "mfds_hf_ingredient_board")

    for w in WHO:
        for t in rng.sample(WHO_T, 3):
            add(t.format(w=w), "섭취대상", "synthetic_template")
    for w in HOW_WHAT:
        for e in rng.sample(HOW_END, 3):
            add(f"{w} {e}", "섭취방법", "synthetic_template")
    for w in KEEP_WHERE:
        for e in rng.sample(KEEP_END, 3):
            add(f"{w} {e}", "보관", "synthetic_template")
    for t in LABEL_INFO:
        add(fill(t), "표시사항", "synthetic_template")
    for t in HANDLE:
        add(t, "취급주의", "synthetic_template")
    if os.path.exists(my_path):
        with open(my_path, encoding="utf-8-sig") as f:
            my_lines = f.read().splitlines()
        for line in my_lines:
            line = line.strip()
            if line and not line.startswith("#"):
                m = re.match(r"^\[([^\]]+)\]\s*(.+)$", line)
                add(m.group(2) if m else line, "직접작성", "synthetic_template")

    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)}행 → {out_path}")
    print("  종류:", dict(Counter(r["family"] for r in rows)))
    print(
        "  계보:",
        {
            f"{p}/{o}": (
                "공개 불가 · 등재 대기"
                if pend
                else ("재배포 가능" if rd else "재배포 불가")
            )
            for (p, o), (rd, pend) in lin.items()
        },
    )
    print(f"  제외: {dict(drop)} · test 배정 게시물 {n_skip}건 건너뜀")


if __name__ == "__main__":
    main()
