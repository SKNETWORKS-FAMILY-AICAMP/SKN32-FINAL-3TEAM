"""doctor.py — 환경·거버넌스 진단 (W1 반나절 상한, D-51 · D-89).

launcher는 얇은 껍데기, 로직은 여기. 출력은 「무엇이 틀렸나」가 아니라 「어떻게 고치나」.
기본 실행 3초 이내 — 무거운 검사(모델 로드)는 --full로 분리.

일반 검사 (기획서 7-5):
  1. Python 3.11 · uv.lock 동기화
  2. .env가 git에 추적되고 있지 않은가
  3. postgres 접속 + pgvector 확장
  4. Alembic head == DB revision
  5. LangGraph 버전 == 핀
  6. 모델 캐시 (인코더·리랭커·GGUF)
  7. GPU 가용 → 없으면 CPU 폴백 안내
  8. kiwipiepy 사전 로드

거버넌스 검사 (CopyLane 고유):
  🚨 9·10·12·13 은 D-89 로 pytest 로 이관됐다 — 저장소에서 답이 하나인 검사다.
     doctor 에 남는 것은 「기기마다 답이 다른 것」이고, 여기서는 자리만 비워 둔다.
     tests/test_governance_layout.py 가 게이트 16건을 돌린다 (uv run pytest -m gate):
       등급 디렉터리 5종 · .g1_blocked 공백 · .env 미추적 · 전 소스 등급/용도 ·
       G1 전 용도 deny · 편입금지 사유 · 모델 라이선스·등급
       + 등급↔용도 상한 · 제약 플래그 정의 · NOREDIST↔redistributable 정합 ·
         collected_at 이 있으면 2인 확인 완료 · 모델 use.U4 필드   (D-71 · D-90)

  9.  → pytest (test_등급_디렉터리가_존재한다)
  10. → pytest (test_g1_blocked_는_비어있다)
  11. quarantine/ 방치 일수 경고
  12. → pytest (test_모든_소스에_등급과_용도가_있다)
  13. → pytest (test_모든_모델에_라이선스와_등급과_배포용도가_있다)
  14. g2_norepub/ 가 **배포 스크립트**에서 참조되는가 (D-71 — 학습이 아니라 배포를 막는다)
  15. 클라우드 반출 대상에 g3/·g2_facts/ 외 등급 디렉터리가 섞였는가 (D-78)
      🚨 AWS는 **제3자 제공 계정**이다. g2_norepub/(재배포 제약)·quarantine/(미판정)을
      올리는 것은 D-71이 가른 「재배포」 축에 걸린다. 배포 이미지·동기화 목록을 검사한다.
  16. 판정 런타임 경로에 외부 API 호출이 있는가 → 즉시 실패 (D-73 · D-78)
      🚨 GPT API 크레딧이 있어도 판정·생성 경로에는 들어갈 수 없다. D-77 L4의
      「판정 경로의 외부 네트워크 요청 수 = 0」을 코드로 강제하는 검사다.
  17. derived/golden/*.jsonl 의 모든 행에 provenance · redistributable 이 있는가 (D-71)
      🚨 NOREDIST 소스에서 온 문장이 한 줄이라도 섞이면 그 골든셋 전체를 공개할 수 없고,
      섞인 뒤에는 어느 줄이 어디서 왔는지 되돌릴 수 없다.
  18. manifest.jsonl 의 모든 source_id 가 data_sources.yaml 에 존재하는가
  19. raw/ 하위 파일이 derived/ 없이 방치돼 있지 않은가 (전처리 미실행 감지)

TODO(W1): 구현. 지금은 체크리스트 자리표시자.
"""

if __name__ == "__main__":
    raise SystemExit("doctor: W1에 구현 예정 — 위 docstring이 검사 목록이다")
