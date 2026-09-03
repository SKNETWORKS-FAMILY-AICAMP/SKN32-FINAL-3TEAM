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
     법제처 OPEN API로 받는 12종(법령·별표·고시·지침·재결례·판례 + 건기식 기준규격 고시)은
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

# 법제처 OPEN API — 12종을 흡수한 합성 레코드 (이용조건이 하나이므로 등재도 하나)
# 🚨 숫자는 LAW_COVERS 의 길이다. hf_standard 흡수(D-102 ②)로 11 → 12 가 됐는데
#    **숫자를 적은 문장들만 안 고쳐져** 네 곳이 어긋나 있었다 (권소라 역검토 v1.3 §6).
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
    "scale": "아래 covers 12종",
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
    # 🔄 GATED 승인 기록 — 사람이 신청해 받아 온 사실이라 사람이 적는다 (D-109).
    #    🚨 「신청했다」가 아니라 「승인됐다」의 날짜다. 둘을 같은 칸에 적으면
    #       승인 대기 중인 소스가 승인된 것으로 읽힌다.
    if rv.get("approved_at"):
        L.append(f"    approved_at: {_scalar(rv.get('approved_at'))}")
        L.append(f"    approved_by: {_scalar(rv.get('approved_by'))}")
    # 🚨 **근거 URL 과 접근 URL 은 다른 것이다** (권소라 역검토 v1.3 §2 · 인계 §3-①).
    #    한 필드를 두 자리에 넣고 있어서, 검토표의 확인 항목 4번(「근거 URL 이 실제로 그 조건을
    #    말하는가」)이 **31건 전부에서 성립하지 않았다.** AI Hub 판정의 전체 무게가 이용정책
    #    제4항에 실려 있는데 그 주소는 `why` 산문 안에 텍스트로만 박혀 있었다.
    #    🚨 폴백은 하되 **폴백했다고 말한다** — 추정한 URL 은 빈 칸보다 나쁘다.
    #    빈 칸은 「미확인」이라 말하지만 추정값은 「확인됨」이라고 거짓말한다.
    # 🔄 파생 소스의 원천 (권소라 2인확인 §6-7·8). 🚨 「어디서 나왔는가」는 산문이 아니라
    #    필드여야 한다 — 원천이 재판정되면 파생물도 따라가야 하고, 그 추적을 게이트가 한다.
    if s.get("derivedFrom"):
        L.append("    derived_from: [" + ", ".join(s["derivedFrom"]) + "]")
    ev = s.get("evidenceUrl") or s.get("url")
    if ev:
        L.append(f"    evidence_url: {esc(ev)}")
        if not s.get("evidenceUrl"):
            L.append("    evidence_is_access: true")
    return "\n".join(L)


# ── 수동 보강 (기존 yaml 에 있던 손으로 쓴 필드를 잃지 않는다)
# 🚨 D-17(업체명 마스킹)은 **저작권이 아니라 명예·개인정보 축**이라 등급으로 막히지 않는다.
#    업체명이 들어오는 소스에는 전부 붙어야 하는데 `ftc_decisions` 하나에만 있었다
#    (권소라 역검토 v1.2 §4-2 · 2026-09-02 예행 검토에서 대상 4건 확정).
EXTRA = {
    "ftc_decisions": [
        "masking: 업체명·상표·대표자명·🔄 **주소** 즉시 마스킹, 원문 미보관 (D-17)",
        "  🚨 2026-09-02 의결서 실물 확인 — 피심인 항목에 **사업장 주소와 대표이사 성명**이 전면에",
        "  나온다(「서울특별시 종로구 서린동 88 · 대표이사 임충헌」). 종전 masking 문구에 주소가 빠져 있었다.",
        "fragment_note: 광고 화면 캡처 이미지는 G1~G2로 개별 하향 (D-18)",
    ],
    "ftc_decisions_api": [
        "masking: 업체명·상표·대표자명 즉시 마스킹, 원문 미보관 (D-17)",
        "fragment_note: 🚨 ftc_decisions 와 같은 원천이다 — 조건이 다를 이유가 없다",
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — data.go.kr 「이용허락범위 제한 없음」.",
        "  🚨 다만 심의유형이 「개발단계: 자동승인 / 운영단계: 심의승인」이다 — 개발은 그냥 되지만",
        "  **운영 계정은 심의를 받는다.** 배포(U4) 시점의 선결 조건인데 지금 어느 플래그도",
        "  이것을 말하지 않는다. mfds_hf_individual · cosmetic 2건도 같은 조건이다. 2인 확인에서 판단할 것.",
    ],
    "ftc_decisions_body": [
        "masking: >-",
        "  업체명·상표·피심인 주소 즉시 마스킹, 원문 미보관 (D-17).",
        "  🚨 대표자명은 **원천이 이미 가려서 준다**(「대표이사 이ㅇㅇ」) — 그래도 우리 쪽 마스킹을",
        "  끄지 않는다. 원천의 정책이지 우리의 보장이 아니다.",
        "fragment_note: >-",
        "  🔄 ftc_decisions 의 「광고 화면 캡처는 G1」 문제가 **이 경로에는 없다** —",
        "  XML 본문에 이미지가 들어오지 않는다. 같은 원천이라도 **경로가 프래그먼트 구성을 바꾼다**.",
        "probe_note: >-",
        "  🔄 2026-09-02 실측 — data.go.kr 15103247 「이용허락범위 제한 없음」· 포맷 XML ·",
        "  API 유형 **LINK**(linkUrl 이 법제처 cmtInfoGuide#ftc). 본문을 실제로 받아 확인했다:",
        "  ㈜24프로미 부당한 광고행위 건(2016서소1562)의 「주문」에 금지 광고행위가 원문으로 적혀 있다.",
        "  🚨 심의유형 「개발 자동승인 / 운영 심의승인」 — 배포 시점의 선결 조건이다.",
    ],
    "kcc_media": [
        "fragment_note: >-",
        "  🚨 통계표만 받는다 — 다이어리 자료·아동 조사표는 수집 대상에서 제외한다 (D-18).",
        "  2026-09-02 data.go.kr 실측 구성: 가구·개인 통계표 + 방송매체 이용행태 다이어리 +",
        "  아동 조사표. 다이어리는 응답자별 시간대 기록이라 개인 단위 레코드다.",
        "  🚨 다이어리를 받게 되면 그때는 PII 플래그가 붙어야 한다 — 지금은 그 조각을",
        "  가져오지 않으므로 소스 전체에 플래그를 다는 것이 과하다. 판정 단위는 FRAGMENT 다.",
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — 「공공저작물 : 출처표시 (제 1유형)」.",
        "  BY 를 붙인 판정(D-108 작업)이 실측으로 확인됐다.",
    ],
    "mfds_sanctions": [
        "masking: 업체명·대표자명 즉시 마스킹, 원문 미보관 (D-17)",
        "fragment_note: 행정처분 레코드에 처분 대상 업체가 들어온다",
    ],
    "self_sanction_stat": [
        "masking: 🚨 원천이 마스킹된 뒤의 값만 쓴다 — 「반복 위반 비율」은 업체 식별을 전제하므로",
        "  집계 단계에서 식별자를 다시 만들지 않는다 (D-17)",
    ],
    "kcia_guideline": [
        "note: >-",
        "  🔄 2026-08-20 정정 — 2025판 확인으로 G0 → G2. 금지/허용 표현 목록은",
        "  원 출처(화장품법·고시)로 소급해 G3화한다 (D-16). 이용조건 문의 회신 시 재판정.",
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — 협회 공지 페이지에 **이용조건 문구가 없다.** 근거 URL 이 조건을",
        "  말하지 않는다 (확인 항목 4). 바로 위 「문의 회신 시 재판정」과 같은 자리다.",
    ],
    "mfds_hf_ingredient": [
        "fragment_note: >-",
        "  ★ 취하는 것 — 인정번호 · 인정일자 · 신청원료명 · **기능성 내용** · 1일 섭취량 · 섭취시 주의사항.",
        "  🚨 **업체명 · 업종 · 주소는 취하지 않는다.** 응답에 함께 오지만 우리가 쓸 이유가 없고,",
        "  **주소는 사업장 소재지**라 더욱 그렇다. 판정 단위는 FRAGMENT 다 (D-18).",
        "  ★ 게시판(mfds_hf_ingredient_board)이 주던 것과 **같은 필드**다 — 조건이 깨끗한 경로로 대체된다.",
    ],
    # ★ 2026-09-02 게시물 본문 실물 확인으로 프래그먼트가 갈렸다.
    "mfds_hf_ingredient_board": [
        "fragment_note: >-",
        "  ★ **게시물 본문만 취한다** — 원료명 · 인정번호 · **기능성내용** · 일일섭취량 · 섭취 시 주의사항.",
        "  🚨 **첨부 「소비자 리포트」 PDF 는 취하지 않는다.** 1쪽에 이렇게 적혀 있다:",
        "  「소비자 이해를 돕기 위하여 작성하였으며 **건강기능식품 판매 목적의 표시·광고 또는",
        "  홍보 수단으로 사용할 수 없음**을 알려드립니다」.",
        "  🚨 **이 프로젝트에서 그 금지는 남의 일이 아니다** — 우리 제품은 광고 문구를 **생성**한다.",
        "  PDF 의 「12주간 섭취시킨 결과 체지방률이 대조군 대비 유의적으로 개선되었음」 같은",
        "  인체적용시험 서술이 학습에 들어가면, 생성 모델이 그 문장을 뱉고 사용자가 광고에 쓴다.",
        "  **그것이 정확히 우리가 막으려는 부당광고다.** 원천이 스스로 금지한 것을 우리가 유통하는 꼴이 된다.",
        "  ✅ 반면 **기능성내용 문구는 취해도 된다** — 「체지방 감소에 도움을 줄 수 있음」은 인정 사실이고",
        "  제품 라벨에 실제로 찍히는 법정 표시사항이다. 금지된 것은 **리포트를 광고 수단으로 쓰는 것**이지",
        "  인정 문구 자체가 아니다.",
        "  🚨 **업체명은 취하지 않는다** — 제재 맥락은 아니지만(D-17 과 사유가 다르다) 학습 데이터에",
        "  회사명이 들어갈 이유가 없다.",
        "  ★ 영문판 병기 · 관련 규정은 「건강기능식품 기능성 원료 및 기준·규격 인정에 관한 규정」 제15조 —",
        "  law_go_kr covers 에 이 규정이 있는지 확인이 남는다.",
    ],
    # 🚨 2026-09-02 탐침 2회전 — 접근 페이지까지 보게 되자 **레지스트리 규모와 실측이 갈렸다.**
    #    숫자를 여기서 고치지 않는다. 어느 쪽이 맞는지는 사람이 보고 정한다 —
    #    「고도화」 판본 차이일 수 있고, 그렇다면 고치는 것이 아니라 **판본을 적어야** 한다.
    "aihub_71486": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — 규모 불일치. 레지스트리 「라벨링 166,339문장」 vs 상세 페이지",
        "  「데이터 구축량 2022년/165,000개 문장」. 문서 수 10,021 은 일치한다(합계 10,021 100%).",
        "  어느 쪽이 맞는지 2인 확인에서 눈으로 정한다.",
    ],
    "aihub_71723": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — 규모가 크게 다르다. 레지스트리 「원문 251,946 · 어노테이션 157,455 ·",
        "  QA 90,944」 vs 상세 페이지 「데이터셋1 원천 66,511 · 라벨링 66,511 / 데이터셋2 QA 20,160」.",
        "  🚨 QA 가 90,944 대 20,160 이다 — 오차가 아니라 **다른 것을 세고 있다.**",
        "  이름에 「(고도화)」가 붙어 있으므로 **판본이 갈렸을 가능성**이 높다. 숫자를 고치기 전에",
        "  어느 판본을 받았는지부터 확인한다 — 판본이 다르면 고칠 것이 아니라 적을 것이다.",
    ],
    "aihub_558": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — 규모 불일치. 레지스트리 「문장 451,110 · 대화세트 132,303」 vs",
        "  상세 페이지 「453,340문장(대화세트 132,807건)」. 둘 다 어긋난다(+2,230 / +504).",
        "  상세 페이지에 비윤리 문장 251,064 · 문형 258,904 · 어휘단위 77,978 도 함께 나온다.",
    ],
    "aihub_71694": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 2회전 — 승인 후 상세 페이지를 열었는데도 **규모가 여전히 안 나온다.**",
        "  페이지에 데이터 구축량 표기가 없고 잡힌 숫자는 예시 표의 「20 건」뿐이다.",
        "  🚨 「미확인」을 유지한다 — 탐침이 못 찾은 것이지 없는 것이 아니다. 승인이 났으므로",
        "  이제 **다운로드해서 직접 세는 것**이 가장 확실하다(가치 C 라 우선순위는 낮다).",
    ],
    "aihub_review_corpus": [
        "probe_note: >-",
        "  ✅ 2026-09-02 탐침 — 상세 페이지 「250,312건」으로 레지스트리와 **일치 확인**.",
    ],
    "mfds_press": [
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 — 보도자료 게시판 총량 **4,347건**(435페이지)을 처음 확인했다.",
        "  레지스트리의 「회차당 수십~수백 건」은 회차 기준이라 총량이 없었다.",
        "  🚨 부당광고 점검 회차만 걸러야 하므로 4,347 이 곧 수집량은 아니다.",
    ],
    # 🔄 2026-09-02 탐침 1회전(S0-16 · D-109)에서 나온 것. 「열어봐야 답이 나온다」던 자리들이다.
    "mfds_hf_individual": [
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — 「이용허락범위 제한 없음」 · 운영단계 심의승인.",
        "  🚨 ftc_decisions_api 와 같은 조건이다 (아래 cosmetic 2건도 같다).",
    ],
    "cosmetic_ingredient": [
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — 「이용허락범위 제한 없음」. G3 전 용도 개방이 뒷받침된다.",
        "  🚨 운영단계 심의승인 + 개발계정 트래픽 10,000. caution 의 「전부 미확인」은 해소됐다.",
    ],
    "cosmetic_restricted": [
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — 「이용허락범위 제한 없음」 · 운영단계 심의승인.",
    ],
    "kosis": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — 근거 URL(serviceInfo/openAPIGuide.do)은 **API 가이드 페이지이고",
        "  이용조건을 말하지 않는다.** caution 은 「상업 이용이 명시적으로 허용된 몇 안 되는 항목」",
        "  이라고 단언하는데, 그 근거를 보여 주는 페이지가 지금 없다. 역검토 v1.3 §2 가 예측한 형태다.",
    ],
    "kisdi_panel": [
        "probe_note: >-",
        "  🚨 2026-09-02 탐침 — TLS 인증서 검증 실패(self-signed in chain). 접근 자체가 안 된다.",
        "  🚨 검증을 끄지 않는다 — 이용조건을 확인하러 가는 길에 검증을 끄는 것은 앞뒤가 안 맞는다.",
    ],
    "knhanes": [
        "probe_note: >-",
        "  🔄 2026-09-02 탐침 확인 — 라이선스 「저작자표시-비영리」. NC·BY 표기가 맞다.",
        "  상업 제품 전제에서는 인용만 가능하다는 기존 판단이 실측으로 뒷받침된다.",
    ],
    # D-108 — status 를 옮긴 4건. 「왜 collect 가 아닌가」를 사람이 읽을 자리에 남긴다
    "krei_food": [
        "probe_note: >-",
        "  ✅ 2026-09-02 확인 완료 — D-108 로 hold 였던 것이 풀렸다. 건기식 문항 존재 확인,",
        "  공공누리 **제1유형**(출처표시만) 확인으로 G0 → G3 승격. status 도 collect 로 올린다.",
        "  🚨 개인 단위 응답 레코드다 — 세그먼트 생성 시 k-익명성 게이트가 걸린다.",
    ],
    "meta_adlibrary": [
        "status_note: >-",
        "  🚨 D-108 — 자동 수집은 약관 위반이다. 그 사실이 caution 자유 문장에만 있었고",
        "  기계가 읽는 자리에 없었다. status: manual 은 수집기가 이 키를 거부한다는 뜻이다.",
        "  🚨 용도 축이 미결이다 — 실제 용도는 test_holdout(평가)인데 U1~U4 에 평가 축이 없다.",
        "  게다가 G2(원문 미보관)와 골든셋 원문 보관이 충돌한다. 수기 경로 규약과 함께 결정한다.",
    ],
    "google_atc": [
        "status_note: >-",
        "  🚨 D-108 — 공식 API 가 없고 UI 열람만 가능하다. meta_adlibrary 와 같은 이유로 manual.",
        "  ⚠️ ATC 추가 약관이 JS SPA 라 저장·재배포 조항을 아직 못 읽었다 — 미확인인 채로",
        "  자동 수집을 열어 두는 것이 가장 나쁘다.",
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
    "ftc_decisions_body",
    "mfds_sanctions",
    "mfds_press",
    "ftc_noviolation",
    # 2층 적법 라벨
    "mfds_hf_ingredient",
    "mfds_hf_individual",
    "kcia_guideline",
    # 3층 판단 규범
    "law_go_kr",
    "platform_guide",
    "mfds_hf_ingredient_board",
    # 제품 사실
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
# 🚨 status 는 「수집기가 이 소스를 실행하는가」 하나만 뜻한다 — 작업 목록이 아니다 (D-108).
#    collect : 자동 수집기가 실행한다.  use 중 최소 하나가 allow 여야 한다 (게이트 22)
#    manual  : 🚨 사람이 눈으로 보고 손으로 옮긴다. 자동 수집은 약관 위반이라 수집기가 거부한다
#    hold    : 이번 범위 밖 — 판정 완료·착수 전이거나 선결 조건 대기
#    여기 없는 키는 collect 다. blocked·not_adopted 는 status 값이 아니라 별도 섹션이다.
STATUS = {
    "ftc_noviolation": "hold",
    "google_trends": "hold",
    "youtube_api": "hold",
    "platform_guide": "hold",
    "knhanes": "hold",
    "kisdi_panel": "hold",
    "kobaco_mcr_report": "hold",
    "aihub_71843": "hold",
    # D-108 — G0 는 확인이 선행이다. 확인 전에 자동으로 가져오면 fail-closed 가 수집 단계에서 뚫린다
    # D-108 — ★사용자제공. 자동 수집이 약관 위반이라는 사실을 caution 문장이 아니라 기계가 읽는 자리에 둔다
    "meta_adlibrary": "manual",
    "google_atc": "manual",
}

REV = {v: k for k, v in RENAME.items()}

out = []
for key in ORDER:
    mid = REV.get(key, key)
    s = BY_ID[mid]
    covers = LAW_COVERS if key == "law_go_kr" else None
    st = STATUS.get(key, "collect")
    out.append(block(key, s, EXTRA.get(key), covers, st))

(ROOT / "build").mkdir(exist_ok=True)
with open(ROOT / "build/registry_body.yaml", "w", encoding="utf-8") as _out:
    _out.write("\n\n".join(out) + "\n")
print("등재", len(ORDER), "건 · 법제처 covers", len(LAW_COVERS), "종 흡수")
# 🔄 미채택으로 내린 것은 매트릭스에 판정 근거로 남지만 레지스트리 sources 에는 없다.
#    registry_tail.yaml 의 not_adopted 가 그 자리다 (D-110).
NOT_ADOPTED_IDS = {"nasmedia_npr", "nasmedia_fb", "kfia_approved"}
missing = [
    s["id"]
    for s in SRC
    if s["id"] not in LAW_IDS
    and s["id"] not in MODEL_IDS
    and s["id"] not in NOT_ADOPTED_IDS
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
