"""scripts/psj_seed_dummy_source.py — 화면 확인용 더미 소스 4건 삽입 (psj, 임시 스크립트)

🚨 실제 데이터 파이프라인(load_db.py)과 무관하다 — /admin/sources 화면 확인용 테스트 데이터만
   넣는다. 확인 끝나면 지워도 된다 (source_id 가 'DUMMY-' 로 시작해서 구분 쉬움).

⬜ 2026-09-16 재작성 — 처음 버전은 G0~G3 를 L1~L4(신뢰도 서열)로 착각해서 잘못 매핑했다.
   실제 등급 정의(D-15 · D-16 · D-106)에 맞춰 4건 전부 다시 골랐다:
   G0 미확인 · G1 배제(확인된 허락 없음) · G2 사실만(원문 아님) · G3 원문 자유
"""
from __future__ import annotations

import psycopg

from app.settings import dsn

# 기존(2026-09-16 첫 버전)에 잘못 매핑해 넣은 더미 3건 — 새로 넣기 전에 지운다
OLD_IDS = ["DUMMY-L1-001", "DUMMY-L2-001", "DUMMY-L4-001"]

ROWS = [
    dict(
        source_id="DUMMY-G0-001",
        name="화장품 원료 정보 API (이용허락범위 미확인)",
        publisher="식품의약품안전처",
        url="https://data.go.kr/",
        layer="공공데이터",
        grade="G0",
        cost="unknown",
        value="C",
        access=None,
        license=None,
        attribution="식약처 화장품 원료 정보",
        grade_decided_by="psj",
        grade_reviewed_by="ssm",
        grade_evidence_url=None,
        verified=False,
        note="화면 확인용 더미 — G0 예시: data.go.kr 접근 차단으로 이용허락범위 미확인 "
        "(D-101 이 실제로 지적한 패턴과 같은 유형)",
    ),
    dict(
        source_id="DUMMY-G1-001",
        name="KLUE-RoBERTa (라이선스 확인 결과 없음)",
        publisher="KLUE 팀",
        url="https://huggingface.co/klue",
        layer="모델",
        grade="G1",
        cost="unknown",
        value="X",
        access="공개",
        license=None,
        attribution="다섯 경로로 확인해서 라이선스 없음을 확인함 (D-106)",
        grade_decided_by="ssm",
        grade_reviewed_by="psj",
        grade_evidence_url="https://huggingface.co/klue",
        verified=True,
        note="화면 확인용 더미 — G1 예시: 확인 결과 허락 없음으로 판명 — 배제, 비교군으로도 안 씀",
    ),
    dict(
        source_id="DUMMY-G2-001",
        name="화장품협회 금지표현 해설서 (사실만 취함)",
        publisher="대한화장품협회",
        url=None,
        layer="협회자료",
        grade="G2",
        cost="unknown",
        value="B",
        access=None,
        license=None,
        attribution="화장품법·고시로 소급 확인한 사실만 취함, 해설 문장은 취하지 않음",
        grade_decided_by="psj",
        grade_reviewed_by="ssm",
        grade_evidence_url=None,
        verified=True,
        note="화면 확인용 더미 — G2 예시: 원문·해설은 협회 저작물이라 안 취하고 "
        "금지 표현 목록(사실)만 원 출처로 소급해서 취함 (D-16)",
    ),
    dict(
        source_id="DUMMY-G3-001",
        name="식품 등의 표시·광고에 관한 법률 시행령",
        publisher="법제처",
        url="https://www.law.go.kr/",
        layer="법령",
        grade="G3",
        cost="free",
        value="A",
        access="공개",
        license="공공누리",
        attribution="법제처 국가법령정보센터",
        grade_decided_by="ssm",
        grade_reviewed_by="psj",
        grade_evidence_url="https://www.law.go.kr/",
        verified=True,
        note="화면 확인용 더미 — G3 예시: 공공저작물, 원문 그대로 보관·색인·인용·배포 가능",
    ),
]

DELETE_SQL = "DELETE FROM source WHERE source_id = ANY(%s)"

INSERT_SQL = """
INSERT INTO source (
    source_id, name, publisher, url, layer, grade, cost, value,
    access, license, attribution, grade_decided_by, grade_reviewed_by,
    grade_evidence_url, verified, note
) VALUES (
    %(source_id)s, %(name)s, %(publisher)s, %(url)s, %(layer)s, %(grade)s,
    %(cost)s, %(value)s, %(access)s, %(license)s, %(attribution)s,
    %(grade_decided_by)s, %(grade_reviewed_by)s, %(grade_evidence_url)s,
    %(verified)s, %(note)s
)
ON CONFLICT (source_id) DO NOTHING
"""

with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
    cur.execute(DELETE_SQL, (OLD_IDS,))
    deleted = cur.rowcount
    for row in ROWS:
        cur.execute(INSERT_SQL, row)
    conn.commit()

print(f"done — 기존 잘못된 더미 {deleted}건 삭제, 새 더미 {len(ROWS)}건 삽입 시도")
