#!/usr/bin/env python3
"""gen_registry.py — 판정 매트릭스 → data_sources.yaml 생성기 (D-90).

  python scripts/gen_registry.py            # data_sources.yaml 을 다시 만든다

🚨 손으로 양쪽을 고치지 않는다. 매트릭스(판정 근거 73건)와 레지스트리(집행 대상 43건)는
   범위가 다르고, 방향을 매트릭스 -> 레지스트리 한쪽으로 고정하지 않으면 반드시 어긋난다.

입력 : docs/03_데이터/_matrix/sources.json
       (판정매트릭스.html 의 data.js 에서 뽑은 것 — 갱신 방법은 _matrix/README.md)
출력 : data_sources.yaml  (머리말 scripts/registry_head.yaml + 본문 + 꼬리말 scripts/registry_tail.yaml)
       🚨 밑줄 접두사를 뗐다 — head/tail 은 손으로 쓴 **입력**이고 잃으면 복원되지 않는다.
          생성물은 build/ 아래로만 나간다 (.gitignore 는 build/ 한 줄로 끝난다).

원래 설계 메모:

설계 원칙 (2026-08-31 · 아키텍처 검토)
  1. 레지스트리의 등재 단위는 「데이터셋」이 아니라 「이용조건」이다.
     법제처 OPEN API로 받는 11종(법령·별표·고시·지침·재결례·판례)은
     하나의 이용조건을 공유하므로 law_go_kr 1건으로 묶고 covers 로 편다.
  2. 미채택 판정은 blocked(협상 불가 · G1)와 분리해 not_adopted 로 둔다.
     가치가 없다는 이유로 G2 자료에 G1을 찍으면 등급 축 자체가 오염된다.
  3. cond/unknown 은 fail-closed. 등급이 허용하는 상한을 넘지 않게 자른다.
"""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
with open(ROOT / "docs/03_데이터/_matrix/sources.json", encoding="utf-8") as _f:
    SRC = json.load(_f)
BY_ID = {s["id"]: s for s in SRC}

# ── 2인 확인 원장 (D-66 · D-90 ④) — 생성기의 입력이다.
#    🚨 data_sources.yaml 은 생성물이므로 거기에 reviewed_by 를 적으면 사라진다.
REVIEW_PATH = ROOT / "scripts/registry_review.yaml"
REVIEW = yaml.safe_load(REVIEW_PATH.read_text(encoding="utf-8")) or {}


def _scalar(v):
    """YAML 스칼라로. 빈 값은 null."""
    return "null" if v in (None, "", "null") else str(v)


# ── 1. 법제처 OPEN API 한 건으로 묶는 것들 (같은 OC 키 · 같은 이용조건)
LAW_COVERS = [
    ("law_acts", "표시광고법 · 식품표시광고법 · 화장품법 (+시행령·시행규칙)"),
    ("law_annex", "시행령 [별표] 부당한 표시·광고의 유형 및 기준"),
    ("mfds_notice", "식약처 고시 「식품등의 부당한 표시 또는 광고의 내용 기준」"),
    ("func_claim_rule", "「부당한 표시·광고로 보지 아니하는 식품등의 기능성 표시·광고 규정」"),
    ("ftc_guidelines", "공정위 고시·지침 5종 (유형기준 · 추천보증 · 환경 · 비교 · 인터넷)"),
    ("cosmetic_guides", "화장품 지침 3종 (관리지침 · 실증규정 · 기능성심사규정)"),
    ("sanction_annex", "행정처분 기준 [별표] (화장품법 · 식품표시광고법)"),
    ("penalty_notice", "과징금 부과 세부기준 고시 (2026.7.1 개정)"),
    ("penal_clause", "각 법 벌칙 조항 (징역 · 벌금 상한)"),
    ("admin_appeal", "행정심판 재결례"),
    ("precedent", "표시광고법 관련 판례"),
    ("hf_standard", "「건강기능식품의 기준 및 규격」 고시"),  # D-102 로 흡수
]
LAW_IDS = {i for i, _ in LAW_COVERS}

# ── 2. 매트릭스 id → 레지스트리 키 (기존 키를 깨지 않는다 — collect.py 가 문자열로 참조)
RENAME = {
    "ftc_decisions_bulk": "ftc_decisions",
    "kfia_approved": "kfia_approved_list",
    "kcia_guideline_2025": "kcia_guideline",
    "aihub_review": "aihub_review_corpus",
    "kmhas": "k_mhas",
}

MODEL_IDS = {"qwen3", "kure", "bge_reranker", "kcbert"}

# 법제처 OPEN API — 11종을 흡수한 합성 레코드 (이용조건이 하나이므로 등재도 하나)
BY_ID["law_go_kr"] = {
    "id": "law_go_kr",
    "layer": "3층 판단규범 · 4층 위험도 · 5층 반례",
    "name": "법제처 국가법령정보 OPEN API (법령·시행령·시행규칙·행정규칙/고시·재결례·판례)",
    "org": "법제처",
    "grade": "G3",
    "constraints": [],
    "value": "A",
    "cost": "free",
    "url": "https://open.law.go.kr/LSO/openApi/guideList.do",
    "scale": "아래 covers 11종",
    "u": {"train": "ok", "raw": "ok", "cite": "ok", "deploy": "ok", "commercial": "ok"},
    "caution": "",
}

# ── 3. 등급이 허용하는 용도 상한 (레지스트리 불변식 · 게이트로 검사)
#    G2 = 사실만 추출 · 원문 미보관  →  U2(원문 색인) · U3(화면 인용) 구조적으로 불가
#    G0 = 미표기 · 미확인            →  fail-closed. 확인 후 2인 판정으로 승격
GRADE_CAP = {
    "G3": {"U1": 1, "U2": 1, "U3": 1, "U4": 1},
    "G2": {"U1": 1, "U2": 0, "U3": 0, "U4": 1},
    "G1": {"U1": 0, "U2": 0, "U3": 0, "U4": 0},
    "G0": {"U1": 0, "U2": 0, "U3": 0, "U4": 0},
}
AXIS = {"U1": "train", "U2": "raw", "U3": "cite", "U4": "deploy"}


def use_vector(s):
    """매트릭스 u → use. cond/unknown 은 등급 상한에 걸어 fail-closed."""
    out = {}
    for u, key in AXIS.items():
        v = (s.get("u") or {}).get(key, "unknown")
        allow = 1 if v == "ok" else (1 if v == "cond" and s["grade"] == "G2" else 0)
        allow &= GRADE_CAP[s["grade"]][u]
        out[u] = "allow" if allow else "deny"
    return out


def esc(t):
    """YAML 스칼라로 안전하게 — 매트릭스 원문에 콜론·아포스트로피·HTML 태그가 섞여 있다."""
    import json as _j
    import re as _r

    t = (t or "").replace("\n", " ").strip()
    t = _r.sub(r"</?b>", "", t)
    t = _r.sub(r"\s+", " ", t)
    return _j.dumps(t, ensure_ascii=False)


def block(key, s, extra=None, covers=None, status="collect"):
    g = s["grade"]
    uses = use_vector(s)
    cons = list(s.get("constraints") or [])
    L = [f"  {key}:"]
    L.append(f"    name: {esc(s['name'])}")
    if s.get("org"):
        L.append(f"    org: {esc(s['org'])}")
    if s.get("url"):
        L.append(f"    url: {esc(s['url'])}")
    L.append(f"    layer: {esc(s['layer'])}")
    L.append(f"    grade: {g}")
    L.append("    use: {" + ", ".join(f"{k}: {v}" for k, v in uses.items()) + "}")
    L.append(f"    constraints: [{', '.join(cons)}]")
    L.append(f"    redistributable: {'false' if 'NOREDIST' in cons else 'true'}")
    L.append(f"    value: {s['value']}")
    L.append(f"    cost: {s['cost']}")
    L.append(f"    status: {status}")
    if covers:
        L.append("    covers:")
        for _cid, label in covers:
            L.append(f"      - {esc(label)}")
    if s.get("access"):
        L.append(f"    access: {esc(s['access'])}")
    if s.get("scale"):
        L.append(f"    scale: {esc(s['scale'])}")
    for line in extra or []:
        L.append("    " + line)
    if s.get("caution"):
        L.append(f"    caution: {esc(s['caution'])}")
    # 🚨 판정·검토·수집 시각은 하드코딩하지 않는다. 원장(registry_review.yaml)이 단일 출처다.
    #    여기에 박아 두면 손으로 채운 reviewed_by 가 다음 생성 때 사라진다.
    rv = REVIEW.get(key) or {}
    L.append(f"    collected_at: {_scalar(rv.get('collected_at'))}")
    L.append(f"    decided_at: {_scalar(rv.get('decided_at'))}")
    L.append(f"    decided_by: {_scalar(rv.get('decided_by'))}")
    L.append(f"    reviewed_by: {_scalar(rv.get('reviewed_by'))}")
    if rv.get("reviewed_at"):
        L.append(f"    reviewed_at: {_scalar(rv.get('reviewed_at'))}")
    # 🚨 크롤링형 소스는 `collect/registry.py` 의 규약 6 이 robots_checked_at 을 요구하는데,
    #    그 필드를 만드는 코드가 어디에도 없었다 — 게이트는 초록불이고 수집기 첫 줄에서 죽는다
    #    (권소라 역검토 v1.2 §1). 원장에서 읽어 낸다. 값은 **사람이 robots.txt 를 열어 본 날**이다.
    # 🔄 이견 기록 — 「보고 반대함」과 「아직 안 봄」을 가른다 (권소라 역검토 v1.2 §21).
    #    게이트와 require() 는 그대로 reviewed_by 만 본다.
    if rv.get("dissent_note"):
        L.append(f"    dissent_note: {esc(rv['dissent_note'])}")
    if rv.get("robots_checked_at"):
        L.append(f"    robots_checked_at: {_scalar(rv.get('robots_checked_at'))}")
    if s.get("url"):
        L.append(f"    evidence_url: {esc(s['url'])}")
    return "\n".join(L)


# ── 수동 보강 (기존 yaml 에 있던 손으로 쓴 필드를 잃지 않는다)
EXTRA = {
    "ftc_decisions": [
        "masking: 업체명·상표·대표자명 즉시 마스킹, 원문 미보관 (D-17)",
        "fragment_note: 광고 화면 캡처 이미지는 G1~G2로 개별 하향 (D-18)",
    ],
    "kcia_guideline": [
        "note: >-",
        "  🔄 2026-08-20 정정 — 2025판 확인으로 G0 → G2. 금지/허용 표현 목록은",
        "  원 출처(화장품법·고시)로 소급해 G3화한다 (D-16). 이용조건 문의 회신 시 재판정.",
    ],
    "law_go_kr": [
        "access: API (OC 키 필요 — .env LAW_OC_KEY · 2026-08-20 승인 완료)",
        "note: >-",
        "  🚨 [별표] 조회 가능 여부가 미확인이다. 조회되지 않으면 시행령 별표를",
        "  본문 HTML 파싱으로 받아야 하며 수집 경로가 갈린다 (수집리스트 S2-04).",
    ],
}

ORDER = [
    # 1층 판정 라벨
    "ftc_decisions",
    "ftc_decisions_api",
    "mfds_sanctions",
    "mfds_press",
    "ftc_noviolation",
    # 2층 적법 라벨
    "kfia_approved_list",
    "mfds_hf_ingredient",
    "mfds_hf_individual",
    "kcia_guideline",
    # 3층 판단 규범
    "law_go_kr",
    "platform_guide",
    # 제품 사실
    "mfds_hf_ingredient_board",
    "cosmetic_ingredient",
    "cosmetic_restricted",
    # 5층 코퍼스·반례
    "aihub_71486",
    "aihub_71723",
    "aihub_558",
    "aihub_71694",
    "aihub_71843",
    "bab2min_shopping",
    "nsmc",
    "klue_dataset",
    "k_mhas",
    # 6층 세그먼트·페르소나
    "kobaco_mcr",
    "kobaco_mcr_report",
    "krei_food",
    "khff_survey",
    "nasmedia_npr",
    "nasmedia_fb",
    "kcc_media",
    "kosis",
    "knhanes",
    "kisdi_panel",
    "aihub_review_corpus",
    # 7층 광고 카피
    "meta_adlibrary",
    "google_atc",
    "youtube_api",
    "google_trends",
    # 경제성 근거
    "self_sanction_stat",
    "mfds_production",
]
HOLD = {
    "ftc_noviolation",
    "google_trends",
    "youtube_api",
    "platform_guide",
    "knhanes",
    "kisdi_panel",
    "kobaco_mcr_report",
    "aihub_71843",
}

REV = {v: k for k, v in RENAME.items()}

out = []
for key in ORDER:
    mid = REV.get(key, key)
    s = BY_ID[mid]
    covers = LAW_COVERS if key == "law_go_kr" else None
    st = "hold" if key in HOLD else "collect"
    out.append(block(key, s, EXTRA.get(key), covers, st))

(ROOT / "build").mkdir(exist_ok=True)
with open(ROOT / "build/registry_body.yaml", "w", encoding="utf-8") as _out:
    _out.write("\n\n".join(out) + "\n")
print("등재", len(ORDER), "건 · 법제처 covers", len(LAW_COVERS), "종 흡수")
missing = [
    s["id"]
    for s in SRC
    if s["id"] not in LAW_IDS
    and s["id"] not in MODEL_IDS
    and RENAME.get(s["id"], s["id"]) not in ORDER
]
print("미등재", len(missing))
for m in missing:
    print("   ", m, BY_ID[m]["grade"], BY_ID[m]["value"], BY_ID[m]["name"][:40])


# ── 머리말 + 본문 + 꼬리말을 이어 붙여 최종 파일을 만든다
body = (ROOT / "build/registry_body.yaml").read_text(encoding="utf-8")
head = (ROOT / "scripts/registry_head.yaml").read_text(encoding="utf-8")
tail = (ROOT / "scripts/registry_tail.yaml").read_text(encoding="utf-8")
(ROOT / "data_sources.yaml").write_text(head + body + tail, encoding="utf-8")
print("data_sources.yaml 생성 완료 —", len(head + body + tail), "문자")
print("🚨 이어서 반드시: uv run pytest -m gate")
