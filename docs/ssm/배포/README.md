# docs/ssm/배포 — 배포 실행 파일 · 기록

> **담당** 소성민 (배포 · 운영) · **갱신** 2026-10-16
> **절차의 정본** [`../../05_배포/배포절차서.md`](../../05_배포/배포절차서.md) — 이 폴더의 파일을 **어떤 순서로** 쓰는지는 거기에 있다. 이 문서는 폴더 안내만 한다.

## 지금 어디까지 (2026-10-16)

| 구간 | 상태 |
|---|:-:|
| g4dn.xlarge 서버 · 탄력적 IP · 보안 그룹 · 기본 설치 | ✅ |
| 1단계 — `preflight` · GPU 드라이버(615.71.09 · Tesla T4) | ✅ |
| 웹 화면 외부 접속 (IP · http · 임시) | ✅ — 🚨 HTTPS 전이라 팀 안 확인용 |
| 3단계 #18 — `.venv-sllm` (GPU torch) | ✅ |
| 판정 인코더 업로드 (잠금 채택판) | ✅ |
| 오전의 임시 구성을 스크립트 구성으로 맞추기 | ⬜ [`작업기록_1016.md`](작업기록_1016.md) 「다음 접속 때 순서」 |
| 정식 DB — RDS (PostgreSQL 16 · pgvector) · 빈 스키마 · 앱 연결 | ✅ 3차 보고서 |
| 2단계 `data` · `verify` (파생물) | ⬜ 판정 ② 뒤 |
| 3단계 sLLM 베이스 · 어댑터 · 실행 | ⬜ |
| 4단계 도메인 · HTTPS · 부하 시험 | ⬜ 판정 ③ 뒤 |

## 실행 파일

| 파일 | 어디서 | 무엇 |
|---|---|---|
| [`deploy_server.sh`](deploy_server.sh) | 서버 `~/deploy_server.sh` | 단계별 실행. `bash deploy_server.sh` 만 치면 단계 목록이 나온다 |
| [`Caddyfile`](Caddyfile) | 서버 `/etc/caddy/Caddyfile` | **정식판** — 도메인 · HTTPS · 닫는 경로 · `/` → `/u/` |
| [`Caddyfile.ip`](Caddyfile.ip) | 서버 `/etc/caddy/Caddyfile` | **도메인 전 임시판** — 탄력적 IP · http. 닫는 경로는 정식판과 같다 |
| [`pack_store.py`](pack_store.py) | 내 PC (저장소 루트) | 서버로 올릴 파생물 묶음 만들기 (절차서 §4-1) |
| [`load_test.py`](load_test.py) | 서버 (시스템 python3) | 부하 시험 (절차서 #29) |

자주 쓰는 단계

```bash
bash ~/deploy_server.sh preflight   # 서버 · GPU 점검
bash ~/deploy_server.sh check       # 실행 중 상태 (포트가 전부 「안쪽만」인지)
bash ~/deploy_server.sh update      # main 의 새 커밋 반영 — fetch → install → migrate → verify → 서비스 재시작
```

## 기록

| 파일 | 무엇 |
|---|---|
| [`작업기록_1016.md`](작업기록_1016.md) | 10-16 서버 작업 · 막힌 것과 고친 것 · 지금 서버 상태 · 다음 접속 때 순서 |

작업한 날마다 `작업기록_<MMDD>.md` 를 하나 더한다 (절차서 §8 다섯 칸).

## 문서 (`문서/`)

| 파일 | 무엇 |
|---|---|
| `AWS_배포환경_구성_작업기록_2026-10-08.docx` | 계정 · 첫 서버를 만든 기록 |
| `요청_2026-10-08_AWS_DB_분리구성_RDS.docx` | 요청 ① — RDS 분리 |
| `배포준비_통합문서_요청·스크립트·체크리스트_소성민_20261012.docx` | 요청 ①②③ · 당일 체크리스트 (스크립트 본문은 옛 판 — 실행은 `deploy_server.sh`) |
| `AWS_배포계획_g4dn.xlarge_소성민_20261014.docx` | g4dn 전환 · 비용 시나리오 · 요청 ④⑤ |
| `배포점검_보안·부하·비용_소성민_20261014.docx` | 보안 · 부하 · 비용 점검 |
| `AWS_배포작업보고_1차_웹화면외부접속_소성민_20261016.docx` | 팀 공유 보고 — 웹 화면 외부 접속 |
| `AWS_배포작업보고_2차_에이전트탑재준비_소성민_20261016.docx` | 팀 공유 보고 — GPU · 모델 전송 · 스크립트 |
| `AWS_배포작업보고_3차_RDS구성_소성민_20261016.docx` | 팀 공유 보고 — RDS 구성 · ssm → main 전환 방법 · RDS 주의사항 |

> 지운 것 — `AWS_배포가이드_설정값·순서·주의사항_소성민_20261012.docx` (m7i 기준 · 10-14 배포계획이 대체 · `docs/ssm/` 과 이 폴더에 같은 파일이 둘 있었다). git 기록에 남아 있다.

## 규칙

- 🚨 이 폴더에 `.env` · `.pem` · 비밀번호 · 접속 문자열 · 서버 로그를 넣지 않는다.
- 🚨 모델 · 파생물 파일을 커밋하지 않는다 — 판 이름의 정본은 `models.lock.json` 이다.
- 서버에서 코드를 고치지 않는다. 여기서 고쳐 main 에 머지 → 서버에서 `update`.
- 머지 전 판을 서버에서 써야 하면 **파일만** 꺼낸다: `git fetch origin ssm && git show origin/ssm:docs/ssm/배포/deploy_server.sh > ~/deploy_server.sh` (🚨 서버에서 `git checkout ssm` 금지).
