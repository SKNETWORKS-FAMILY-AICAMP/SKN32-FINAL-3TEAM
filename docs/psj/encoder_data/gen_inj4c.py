"""식품 4호 입증 필요형(B) 주입 v4c — 실험 전용, 채택은 팀장 판정 (🔄 2026-09-29 설계결정 준수판 · 박수진)

v4b → v4c
  · 영양 강조(「칼슘 8g 함유」 · 「당 함량 50% 감소」 · kcal) · 「원물 90% 그대로」 · 「첨가 없이」 틀을 뺐다 —
    D-286 개정 3: 「A: 천연·자연 · 100% · 무첨가 · Non-GMO · 영양 강조」 → 조성으로 갈리는 A 라 문장만으로 거짓_과장 정답이 서지 않는다
  · test 를 읽지 않는다(D-174 · D-175) — 누수는 공식 물질화 게이트가 평가 쪽에서 뺀다. v4b 의 test 유사도 검사 · v7.1 의 test 문구 제거는 없다
  · 계보: provenance 는 원천이 없는 합성문이라 `synthetic_template` · 생성기는 `generator` 칸 (D-71 · D-249)
    `redistributable` 은 `preprocess.lineage.lineage()` 로 정한다 — 표에 없으면 False + `lineage_pending: True`(팀장 등재 대기 · D-220)
  · 틀 다양성을 계측해 출력한다 — family 별 고유 틀 수 (D-173)

근거: D-286 개정 2·3·4 — 입증에 달린 주장(인증·특허, 수치, 안심·안전, 객관 속성·효과, 1:1 맞춤식)은 B.
최초·유일·1위·최고(대상 없는 최상급)는 B·6(비교 암시)이라 거짓_과장 주입에서 뺀다.
문장은 이 파일의 어휘로만 만든다 — test 문장을 보지 않는다. test와의 겹침은 gen 뒤 누수 검사로만 확인한다."""

import hashlib
import json
import os
import random
import sys
from collections import Counter

rng = random.Random(20260929)

PRODUCTS = [
    "",
    "",
    "",
    "이 두유",
    "우리 그래놀라",
    "이 단백질 쉐이크",
    "이 과채주스",
    "우리 견과바",
    "이 현미 누룽지",
    "우리 김치",
    "이 그릭요거트",
    "우리 꿀",
    "이 녹차",
    "우리 떡",
    "이 시리얼",
    "우리 소스",
    "이 곤약면",
    "이 선식",
]
# ① 인증 · 승인 · 시험 (B · 인증 · 특허)
ORGS = [
    "HACCP",
    "ISO 22000",
    "미국 FDA",
    "유럽 EFSA",
    "국제 유기농",
    "할랄",
    "비건",
    "해외 품질 심사기관",
    "글로벌 식품안전",
    "국가 공인 시험기관",
]
CERT_T = [
    "{o} 인증 획득",
    "{o} 승인 완료",
    "{o} 인증을 받은 믿을 수 있는 원료",
    "{p} {o} 인증 제품입니다",
    "{o}에서 품질을 인정받았습니다",
    "{o} 심사 통과",
]
# ② 특허 · 수상
TECH = [
    "저온 추출 공법",
    "발효 기술",
    "동결 건조 공법",
    "미세 분쇄 기술",
    "숙성 공법",
    "캡슐화 기술",
]
AWARD = ["품질 대상", "식품 박람회 금상", "소비자 선정 품질 대상", "국제 식품 품평회 최우수상"]
PAT_T = [
    "특허받은 {t}",
    "{t} 특허 등록",
    "{p} 특허 {tro} 만들었습니다",
    "특허 기술 {t} 적용",
    "{y}년 {a} 수상",
    "{a}에 빛나는 {p2}",
]
# ③ 수치 주장
NUT = ["단백질", "식이섬유", "칼슘", "비타민C", "철분", "오메가3"]
# 🔄 v4c — 영양 강조 · 함량 · 100% · 그대로(A · D-286 개정 3) 틀 제거. 효과 · 공정 수치(입증이 필요한 B)만 남긴다
NUM_T = [
    "흡수율 {pct}% 향상",
    "{h}시간 저온 숙성",
    "소화 흡수가 {k}배 빠른",
    "{h}시간 동안 포만감 유지",
    "{pct}%가 만족한 맛",
]
# ④ 안심 · 안전
SAFE_T = [
    "안심하고 드실 수 있는",
    "온 가족이 안심하고 먹을 수 있는",
    "안전성이 검증된 원료",
    "{n2}가지 유해물질 불검출",
    "잔류농약 걱정 없는 안전한 원료",
    "{p} 안전하게 만들었습니다",
    "매일 먹어도 안전합니다",
    "엄격한 안전성 검사를 모두 통과",
]
# ⑤ 객관 속성 · 효과 (D-286 개정 4 (다) 평가어 — 객관)
ATTR_T = [
    "갓 수확한 그대로의 신선함",
    "한 끼 식사를 완벽하게 해결",
    "탄수화물을 {pct}% 줄인",
    "{p} 영양 손실 없이 그대로",
    "하루 필요한 영양을 한 번에 해결",
    "{h}시간 안에 배송되는 산지 직송 신선함",
]
# ⑥ 시험 · 연구 결과
TEST_T = [
    "{o2} 시험 결과로 입증",
    "인체적용시험 완료",
    "자체 연구소 {y2}년 연구 끝에 개발",
    "{o2}에서 효과를 확인했습니다",
    "임상 시험으로 확인된 원료",
]
ORG2 = ["국내 대학 연구소", "공인 시험기관", "해외 연구기관", "식품 연구원"]
# ⑦ 1:1 맞춤식 (개정 4 — 개인별 맞춤 사실 주장)
FIT_T = ["1:1 맞춤 설계 식단", "나만을 위한 1:1 맞춤 영양식", "체질별 1:1 맞춤 배합"]


def ro(w):
    c = ord(w[-1]) - 0xAC00
    return w + ("으로" if 0 <= c < 11172 and c % 28 not in (0, 8) else "로")


def fill(t):
    p = rng.choice(PRODUCTS)
    tech = rng.choice(TECH)
    return " ".join(
        t.format(
            o=rng.choice(ORGS),
            p=p,
            t=tech,
            tro=ro(tech),
            a=rng.choice(AWARD),
            p2=(p.split()[-1] if p else "제품"),
            y=rng.choice([2019, 2021, 2022, 2023, 2024]),
            nut=rng.choice(NUT),
            n=rng.choice([45, 80, 95, 120, 150]),
            g=rng.choice([5, 8, 10, 12, 20]),
            k=rng.choice([2, 3, 5, 10]),
            pct=rng.choice([30, 40, 50, 70, 90, 99]),
            h=rng.choice([12, 24, 48, 72]),
            n2=rng.choice([120, 300, 320, 500]),
            o2=rng.choice(ORG2),
            y2=rng.choice([5, 10, 15, 20]),
        ).split()
    )


FAMILIES = {
    "인증": CERT_T,
    "특허수상": PAT_T,
    "수치": NUM_T,
    "안심안전": SAFE_T,
    "객관속성": ATTR_T,
    "시험연구": TEST_T,
    "맞춤": FIT_T,
}
QUOTA = {
    "인증": 60,
    "특허수상": 50,
    "수치": 30,
    "안심안전": 45,
    "객관속성": 35,
    "시험연구": 25,
    "맞춤": 10,
}
REPO = os.environ.get("COPYLANE_REPO", r"C:\SKN32-FINAL-3TEAM")
sys.path.insert(0, REPO)
PROV, ORIGIN = "synthetic_template", "injected_proto"
try:
    from preprocess.lineage import lineage

    try:
        _, REDIST = lineage(PROV, ORIGIN)
        PENDING = False
    except SystemExit:
        REDIST, PENDING = (
            False,
            True,
        )  # 🔴 표에 없는 계보 — 공개 가능으로 두지 않는다 (D-220 · D-249)
except ImportError as e:
    raise SystemExit(
        f"🔴 preprocess.lineage 를 못 읽었다 — COPYLANE_REPO={REPO} 를 저장소 경로로 둔다"
    ) from e
frame_of = {}
out, seen = [], set()
for fam, temps in FAMILIES.items():
    tries = 0
    while sum(r["family"] == fam for r in out) < QUOTA[fam] and tries < 5000:
        tries += 1
        tpl = rng.choice(temps)
        s = fill(tpl)
        if s in seen:
            continue
        seen.add(s)
        h = hashlib.sha1(s.encode()).hexdigest()[:10]
        frame_of[s] = tpl
        out.append(
            {
                "id": f"proto4c:{fam}:{h}",
                "text": s,
                "labels": ["거짓_과장"],
                "근거": ["013094:제8조제1항제4호"],
                "조건": "B",
                "unit": "문장",
                "origin": ORIGIN,
                "provenance": PROV,
                "generator": "gen_inj4c",
                "구역": None,
                "split": "train",
                "redistributable": REDIST,
                "lineage_pending": PENDING,
                "family": fam,
            }
        )
OUT = sys.argv[1] if len(sys.argv) > 1 else "proto_inj4c.jsonl"
with open(OUT, "w", encoding="utf-8") as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(len(out), Counter(r["family"] for r in out), "· lineage_pending" if PENDING else "")
print(
    "family별 고유 틀 수 (D-173):",
    {f: len({frame_of[r["text"]] for r in out if r["family"] == f}) for f in FAMILIES},
)
for r in rng.sample(out, 15):
    print(" ", r["family"], "|", r["text"])
