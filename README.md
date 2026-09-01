# CopyLane

> **작성자** 오한빈 (팀장)
> **작성** 2026-08-16 *(추정)* · **최종 갱신** 2026-08-31 12:13 KST

**광고 문구 준법 검수·생성 플랫폼** — SKN Final Project (발표: 2026-10-26)

> 수치·일정·파라미터의 단일 출처는 [`docs/00_사실원장.md`](docs/00_사실원장.md)입니다.
> 다른 문서에 값을 옮겨 적지 마십시오 (D-54).
>
> 설계 결정의 단일 출처는 [`docs/00_설계결정기록.md`](docs/00_설계결정기록.md)입니다.
> **ADR 개별 파일은 만들지 않습니다** — 결정은 `D-XX` 번호로만 지칭하십시오 (D-58).

## 시작하기 — 처음 한 번

```
git clone https://github.com/LukasBeanz/CopyLane_Final_project.git
cd CopyLane_Final_project
setup.bat        더블클릭
```

이것으로 끝입니다. uv·Python 3.11.9·의존성·커밋 훅·`.env`·로컬 DB까지 자동으로 섭니다.
진입점이 `.bat` 인 이유와 부트스트랩이 런처와 별개인 이유는 **D-86**, DB 를 각자 컨테이너로 두는 이유는 **D-88** 입니다.
여러 번 실행해도 안전합니다(멱등). 두 번째부터는 `uv run python launcher.py` 로 바로 들어가면 됩니다.

**손이 필요한 것 두 가지**

| 항목 | 이유 |
|---|---|
| **Docker Desktop** 설치 | 관리자 권한 + 재부팅이 필요해 자동화 불가. 없으면 DB만 빠지고 나머지는 그대로 섭니다 |
| **`.env` 의 `LAW_OC_KEY`** | 법제처 개인 발급 키. 기계가 만들 수 없습니다 |

> 🚨 `.python-version` · `uv.lock` · DB 이미지 태그는 **팀장 단독 변경**입니다. 각자 올리면 그 순간 환경이 갈립니다.
> 커밋이 훅에 막히면 실패가 아닙니다 — 훅이 파일을 고친 것이니 `git add` 후 같은 커밋을 한 번 더 하십시오.

## 폴더 구조

```
CopyLane_Final_project/
├── setup.bat                # ★ 더블클릭 진입점 — 이것만 실행하면 환경이 선다
├── setup.ps1                #   부트스트랩 본문 (uv·PATH·의존성·훅·.env·DB·게이트)
├── launcher.py              # ★ 작업 진입점 — 대화형 메뉴 + 직접 실행 (D-51)
├── pyproject.toml           # 의존성 선언 · ruff · pytest 설정
├── uv.lock                  # 🚨 커밋 필수 — 5인 환경 동일성은 여기서 보장된다
├── .python-version          # 파이썬 패치 버전 고정
├── docker-compose.yml       # 로컬 DB — pgvector. 127.0.0.1 만 바인딩 (P3-14)
├── .pre-commit-config.yaml  # 커밋 훅 — ruff · gitleaks (P0-2)
├── data_sources.yaml        # 소스 레지스트리 — 등급(G0~G3)·용도(U1~U4) 게이트 (D-15)
├── .env.example             # 법제처 OC 키 · DB 접속 정보 틀 (.env은 절대 커밋 금지)
├── data/                    # 🚨 등급별 물리 분리 (D-19) — 위치가 곧 게이트
│   ├── manifest.jsonl       #   수집 원장. 내용 없음 — 유일하게 커밋되는 것
│   ├── raw/                 # 🚨 무손상 원본 · 등급 혼재 · 소비 금지 (D-92)
│   ├── derived/             #   파생물 — 사전 · 골든셋 · 페어 · 세그먼트
│   ├── g3/                  #   학습·RAG·인용·배포 전부 허용
│   ├── g2_facts/            #   추출된 사실만. 원문 없음
│   ├── g2_norepub/          #   데이터 재배포 금지 (모델 배포는 허용 — D-71)
│   ├── quarantine/          #   G0 미판정 — 어떤 스크립트도 읽지 않는다
│   └── .g1_blocked/         #   빈 디렉터리. 존재 자체가 「배제했다」는 기록
├── tests/                   # 거버넌스 게이트 — 저장소 구조를 코드가 검사
├── docs/
│   ├── 00_사실원장.md            # ★ 사실 원장 (SSOT)
│   ├── 00_설계결정기록.md        # ★ 결정의 단일 원장 (adr/ 디렉터리 없음 — D-58)
│   ├── 00_산출물현황.md          # 산출물 현황 (제출본은 여기서 빌드 — D-53)
│   ├── 01_기획/
│   ├── 02_설계/             # 청크·DB·LangGraph 상태 스키마
│   ├── 03_데이터/           # 전처리 사양 (D-74)
│   ├── 04_보안/
│   ├── 05_배포/
│   └── ohb/ ksr/ lse/ psj/ ssm/   # 개인 작업 문서 — 이니셜 = 브랜치명
└── scripts/                 # doctor.py · collect.py · build_pdf.py · db/init/
```

## 지금 어디인가 — 1W (8/28 공식 착수 · 8/31 기준)

> 일정·게이트 날짜의 단일 출처는 [`docs/00_사실원장.md`](docs/00_사실원장.md)입니다.
> 🚨 기획서 8-1의 `W1`~`W10` 표기는 **폐기**했습니다. 주차는 공식 WBS의 `1W`~`9W` 로만 씁니다 (D-62).

| 다음 마감 | 내용 |
|---|---|
| **Phase 0 게이트 — 9/2 (수)** | **end-to-end 1회전** (walking skeleton) |

**선 것 — 저장소 기반 (D-51 중 launcher 부분)**

- 개인 작업 브랜치 5개 (`ohb` `ksr` `ise` `psj` `ssm`) · PR 병합
- 환경 고정: Python 3.11.9 · `uv.lock` · pre-commit(ruff · gitleaks)
- 거버넌스 게이트 11건 — `uv run python launcher.py gate`
- 로컬 DB — pgvector 컨테이너 (`127.0.0.1:5432`)
- `setup.bat` 1회로 위 전부 자동 구성

**아직 없는 것 — Phase 0 게이트 대상**

- `scripts/doctor.py` 본문 (검사 16종 목록만 있음)
- Alembic 마이그레이션 · DB 스키마 실물
- FastAPI · LangGraph — end-to-end 경로 전부

## 팀 규칙 (요약)

1. **주제 재논의 없음.** 전환 판단은 9/13 단 한 번, 정해진 기준으로만 (D-49).
2. **Phase 게이트 미통과 시 다음 Phase 착수 금지.** 판정일: 8/30 · 9/13 · 9/27 · 10/11.
3. **10/16 기능 동결.** 이후 10일은 만들기가 아니라 보여주기.
4. **거버넌스는 코드로 강제.** G1 자료는 수집 자체를 하지 않고, 데이터는 등급 디렉터리 밖에 두지 않는다.
5. **업체명·상표·대표자명은 수집 직후 즉시 마스킹.** 원문 미보관 (D-17).

## 스택 (핀)

Python 3.11 · uv(lock 커밋) · LangGraph 1.2.x · PostgreSQL 16 + pgvector · FastAPI 단독 · MLflow 로컬만 (**LangSmith·W&B 금지** — D-43). 상세는 기획서 7-3절.
