"""collect — 수집기 공통 모듈.

🚨 수집기는 여기를 거치지 않고 파일을 쓰지 않는다.
   규약(수집리스트 v1.2 「수집기 공통 규약」)을 문서가 아니라 코드로 들고 있는 곳이다.

  1. registry.require(source_id, use)  로 시작한다        → registry.py
  2. 원본은 data/raw/ 에 무손상 저장 · 덮어쓰기 금지        → store.py
  3. manifest.jsonl 에 1행 append                          → store.py
  4. sha256 동일하면 스킵                                   → store.py
  5. sleep 0.5 이상 + 재시도 3회 (지수 백오프)              → http.py
  6. 크롤링형은 robots_checked_at 기록 후에만 실행          → registry.py
  7. 모든 산출 행에 provenance + redistributable            → store.py
"""

# 🚨 **여기서 아무것도 import 하지 않는다** (D-109).
#    `collect/probe.py` 는 저장을 하지 않는 경로인데, 이 파일이 `store` 를 끌어오면
#    **탐침 프로세스에 저장 코드가 로드된다.** 「안 부른다」는 약속과 「부를 수 없다」는
#    구조는 다르고, 게이트 23 이 검사하는 것은 뒤쪽이다.
#    쓰는 쪽이 `from collect import registry, store` 처럼 필요한 것만 집어 간다 —
#    실제로 재수출을 쓰는 곳은 한 군데도 없었다.
