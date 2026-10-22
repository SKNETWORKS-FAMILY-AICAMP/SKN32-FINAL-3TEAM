# docs/ssm/배포 — 배포 실행 파일 · 기록

> **담당** 소성민 (배포 · 운영) · **갱신** 2026-10-22
> **절차의 정본** [`../../05_배포/배포절차서.md`](../../05_배포/배포절차서.md) — 이 폴더의 파일을 **어떤 순서로** 쓰는지는 거기에 있다. 이 문서는 폴더 안내와 운영 규칙만 둔다.

## 🔄 2026-10-21 — 배포는 main 하나로

- 서버는 **origin/main 에 들어 있는 커밋만** 배포한다. `deploy_server.sh fetch` 가 그 밖의 판(ssm · 다른 브랜치 · 머지 전 커밋)을 거부한다.
- 서버의 `~/deploy_server.sh` 는 저장소 안 사본(`~/SKN32-FINAL-3TEAM/docs/ssm/배포/deploy_server.sh`)을 가리키는 **링크**다. `update` 가 새 판을 받으면 새 스크립트로 이어서 돈다 — 서버에 따로 노는 사본이 없다.
- 서버에서만 다른 값(DB 종류 · Caddy 판 · 도메인 · 관리자 허용 IP)은 저장소 밖 `~/.copylane-deploy` 에 둔다 (틀: [`deploy.conf.example`](deploy.conf.example)).
- Caddy 설정은 손으로 고치지 않는다. `bash ~/deploy_server.sh caddy` 가 저장소 판으로 만들고 → validate → 적용 → 응답 확인까지 하고, 실패하면 앞 판으로 되돌린다. `update` 도 마지막에 이 단계를 돈다.
- `verify` 의 지문 기대값은 배포 커밋의 `data/derived_manifest.jsonl` 에서 읽는다 — main 이 데이터를 바꾸면 기대값도 같이 바뀐다.

### main 전환 — 서버에서 한 번 (이 폴더가 main 에 머지된 뒤)

```bash
cd ~/SKN32-FINAL-3TEAM
git status --short --untracked-files=no      # 비어 있어야 한다 — 서버에서 고친 파일이 있으면 내용을 PC 로 옮기고 git checkout -- .
git fetch origin
git show origin/main:docs/ssm/배포/deploy_server.sh > /tmp/deploy_server.sh
bash /tmp/deploy_server.sh main-switch
```

`main-switch` 가 하는 일 — ① origin/main 최신으로 맞춘다(서버에서 고친 파일이 있으면 멈춤) ② `~/deploy_server.sh` 옛 사본을 `.old-*` 로 옮기고 링크로 바꾼다 ③ `~/.copylane-deploy` 를 만든다(DB_MODE 는 `.env` 로 짐작) ④ `/etc/caddy/Caddyfile` 에 손으로 넣은 관리자 허용 IP 가 있으면 설정 파일로 옮긴다 ⑤ `~/load_test.py` · `~/perf_report.py` 옛 사본을 `.old-*` 로 ⑥ install → migrate → verify → 서비스 재시작 → caddy.

끝나면 `nano ~/.copylane-deploy` 로 값을 한 번 확인하고 `bash ~/deploy_server.sh check`. `~/.bashrc` 등에 `DEPLOY_REF` · `origin/ssm` 이 남아 있으면 `main-switch` 가 `[확인]` 줄로 보여 준다 — 지운다.

## 지금 어디까지 (2026-10-22)

| 구간 | 상태 |
|---|:-:|
| g4dn.xlarge 서버 · 탄력적 IP · 보안 그룹 · 기본 설치 | ✅ |
| 1단계 — `preflight` · GPU 드라이버(615.71.09 · Tesla T4) | ✅ |
| 웹 화면 외부 접속 (IP · http · 임시) | ✅ → 10-22 도메인 · HTTPS 로 바뀜 |
| 3단계 #18 — `.venv-sllm` (GPU torch) | ✅ |
| 판정 인코더 업로드 (잠금 채택판) | ✅ |
| 오전의 임시 구성을 스크립트 구성으로 맞추기 (`cleanup-adhoc` · `services`) | ✅ |
| 정식 DB — RDS (PostgreSQL 16 · pgvector) · 빈 스키마 · 앱 연결 | ✅ 3차 보고서 |
| 2단계 `data` · `verify` (파생물 139개 · RDS) | ✅ 10-19 · 4차 |
| 판정 인코더 D4-20 (`+encb:c451942436f0`) | ✅ 10-19 · 4차 |
| API 오류 · 응답시간 점검 (서버 안 · 외부 PC → Caddy) | ✅ 10-19 · 4차 |
| 3단계 sLLM 베이스 · 어댑터 · 실행 (고쳐 쓰기) | ✅ 10-19 · 5차 — 한 문장 시간 ⬜ |
| 카피 생성 (OpenAI) | ✅ 10-19 · 5차 — 하드 한도 ⬜ |
| 배포 기준 main 일원화 (스크립트 · Caddy 자동화) | ✅ 10-22 — 서버 `main-switch` · `bfbd834` |
| 관리자 화면 (`demo` 에디션 · IP 제한) | ✅ 10-22 — 허용 IP 1개 |
| Caddy 임시판 → `Caddyfile.ip` (닫는 경로) | ✅ 10-22 → 같은 날 정식판으로 |
| 4단계 도메인 · HTTPS | ✅ 10-22 — `CADDY_MODE=domain` · Let's Encrypt |
| 보안 점검 (실서버) | ✅ 10-22 — `.env` 600 조치 · 남은 위험 3건 (작업기록_1022) |
| 서비스 테스트 (오류 · 버그 · 부하) | ⬜ |

## 실행 파일

| 파일 | 어디서 | 무엇 |
|---|---|---|
| [`deploy_server.sh`](deploy_server.sh) | 서버 `~/deploy_server.sh` (→ 저장소 사본 링크) | 단계별 실행. `bash ~/deploy_server.sh` 만 치면 단계 목록이 나온다 |
| 🆕 [`deploy.conf.example`](deploy.conf.example) | 서버 `~/.copylane-deploy` 의 틀 | 서버 전용 값 — `DB_MODE` · `CADDY_MODE` · `CADDY_DOMAIN` · `ADMIN_ALLOW_IPS` |
| [`Caddyfile`](Caddyfile) | `caddy` 단계가 `/etc/caddy/Caddyfile` 로 | **정식판** — 도메인 · HTTPS · 닫는 경로 · `/` → `/u/` |
| [`Caddyfile.ip`](Caddyfile.ip) | `caddy` 단계가 `/etc/caddy/Caddyfile` 로 | **도메인 전 임시판** — 탄력적 IP · http. 닫는 경로는 정식판과 같다 |
| [`pack_store.py`](pack_store.py) | 내 PC (저장소 루트) | 서버로 올릴 파생물 묶음 만들기 (절차서 §4-1) |
| [`load_test.py`](load_test.py) | 서버 · 저장소 사본 (시스템 python3) | 부하 시험 (절차서 #29) |
| [`perf_report.py`](perf_report.py) | 서버 · 저장소 사본 | **성능 시험 한 번에 + 보고서 자동 작성** → `~/perf_reports/성능시험_<MMDD_HHMM>.md` |

자주 쓰는 단계

```bash
bash ~/deploy_server.sh check       # 실행 중 상태 — 서버 판 = origin/main 인지 · 포트가 전부 「안쪽만」인지 · caddy
bash ~/deploy_server.sh update      # main 의 새 커밋 반영 — fetch → install → migrate → verify → 서비스 재시작 → caddy
bash ~/deploy_server.sh caddy       # ~/.copylane-deploy 를 바꾼 뒤 (허용 IP · 도메인)
DEPLOY_REF=<main 의 커밋 해시> bash ~/deploy_server.sh update   # 되돌리기 — main 에 들어 있는 커밋만 된다
cat ~/deploy_history.log            # 언제 어느 커밋을 올렸는지
python3 ~/SKN32-FINAL-3TEAM/docs/ssm/배포/perf_report.py --quick   # 성능 시험
```

## 기록

| 파일 | 무엇 |
|---|---|
| [`작업기록_1016.md`](작업기록_1016.md) | 10-16 서버 작업 · 막힌 것과 고친 것 · 지금 서버 상태 · 다음 접속 때 순서 |
| [`작업기록_1019.md`](작업기록_1019.md) | 10-19 데이터 적재 · 인코더 D4-20 · API 점검 표 · sLLM · 카피 생성 |
| [`작업기록_1022.md`](작업기록_1022.md) | 10-22 서버 main 전환 · 도메인 · HTTPS · 보안 점검 · 스크립트 수정(Caddy 확인 대기 · `.env` 권한) |
| [`성능시험/`](성능시험/) | `perf_report.py` 가 만든 성능 시험 보고서 모음 |

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
| `AWS_배포작업보고_3차_RDS구성_소성민_20261016.docx` | 팀 공유 보고 — RDS 구성 · RDS 주의사항 |
| `AWS_배포작업보고_4차_데이터적재·인코더·API점검_소성민_20261019.docx` | 팀 공유 보고 — 적재 · 인코더 D4-20 · API 오류 및 응답시간 |
| `AWS_배포작업보고_5차_sLLM·카피생성·보안_소성민_20261019.docx` | 팀 공유 보고 — sLLM · 카피 생성 · **보안 주의사항** |
| `AWS_배포작업보고_6차_main일원화·도메인·HTTPS·보안점검_소성민_20261022.docx` | 팀 공유 보고 — 서버 main 전환 · 도메인 · HTTPS · 실서버 보안 점검 · 스크립트 수정 |
| `성능테스트_보고서_소성민_20261022.docx` | 성능 테스트 — 검수 · 고쳐 쓰기 · 섞인 부하 · 밖(HTTPS) 측정 · 486건 실패 0 · 처리량 한계 초당 약 3.2건 |

> 3차 · 4차 보고서의 「ssm → main 전환 방법」은 10-21 의 `main-switch` 로 대체됐다.

## 규칙

- 🚨 이 폴더에 `.env` · `.pem` · 비밀번호 · API 키 · 접속 문자열 · 서버 IP · 도메인 실값 · 서버 로그를 넣지 않는다 (저장소가 공개다). 서버 전용 값은 `~/.copylane-deploy` 에만.
- 🚨 모델 · 파생물 파일을 커밋하지 않는다 — 판 이름의 정본은 `models.lock.json`, 파생물 지문의 정본은 `data/derived_manifest.jsonl` 이다.
- 🚨 서버에서 코드 · 설정(`/etc/caddy/Caddyfile` 포함)을 직접 고치지 않는다. **PC → main → 서버 `update`** 순서만 쓴다. 서버 저장소에 고친 파일이 있으면 `fetch` 가 멈춘다.
- 🚨 서버에서 `git checkout ssm` · `git show origin/ssm:…` 을 쓰지 않는다. main 에 들어가지 않은 판은 서버에 올리지 않는다.
