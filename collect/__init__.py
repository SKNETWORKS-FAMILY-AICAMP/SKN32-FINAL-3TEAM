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

from collect.registry import RegistryError, require, spec
from collect.store import manifest_append, raw_dir, save_raw, stamp

__all__ = [
    "RegistryError",
    "require",
    "spec",
    "save_raw",
    "raw_dir",
    "manifest_append",
    "stamp",
]
