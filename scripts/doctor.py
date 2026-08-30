"""doctor.py — 환경·거버넌스 진단 (W1 반나절 상한, D-51).

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
  9.  data/ 물리 분리 구조 존재 (g3/g2_facts/g2_norepub/quarantine/.g1_blocked)
  10. data/.g1_blocked 에 파일 존재 → 즉시 실패
  11. quarantine/ 방치 일수 경고
  12. data_sources.yaml 전 소스 등급·용도 등록
  13. 모델 라이선스 등급 등록
  14. g2_norepub/ 가 **배포 스크립트**에서 참조되는가 (D-71 — 학습이 아니라 배포를 막는다)
  15. 클라우드 반출 대상에 g3/·g2_facts/ 외 등급 디렉터리가 섞였는가 (D-78)
      🚨 AWS는 **제3자 제공 계정**이다. g2_norepub/(재배포 제약)·quarantine/(미판정)을
      올리는 것은 D-71이 가른 「재배포」 축에 걸린다. 배포 이미지·동기화 목록을 검사한다.
  16. 판정 런타임 경로에 외부 API 호출이 있는가 → 즉시 실패 (D-73 · D-78)
      🚨 GPT API 크레딧이 있어도 판정·생성 경로에는 들어갈 수 없다. D-77 L4의
      「판정 경로의 외부 네트워크 요청 수 = 0」을 코드로 강제하는 검사다.

TODO(W1): 구현. 지금은 체크리스트 자리표시자.
"""

if __name__ == "__main__":
    raise SystemExit("doctor: W1에 구현 예정 — 위 docstring이 검사 목록이다")
