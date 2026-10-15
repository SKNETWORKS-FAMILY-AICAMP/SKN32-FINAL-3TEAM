#!/usr/bin/env bash
# deploy_server.sh — CopyLane 을 AWS EC2 g4dn.xlarge(Ubuntu 24.04 · T4 GPU)에 올리는 순서를 단계별로 실행한다.
#
#   🔄 2026-10-14 · 소성민 — 인스턴스를 m7i.xlarge → g4dn.xlarge 로 바꾸며 다시 씀
#       · GPU 드라이버 · sLLM 환경(.venv-sllm) · sLLM 모델 · sLLM 실행 단계를 더했다
#       · 인코더 확인을 지문 한 줄에서 모델 잠금(models.lock.json · D-333) 검사로 바꿨다
#   초안 2026-10-12 · 🚨 서버에서 실행해 본 기록이 없다. 첫 실행은 단계를 하나씩 돌린다.
#   근거  docs/05_배포/배포계획.md §1-2 · §4 / docs/lse/sLLM_연결_안내_2026-10-05.md / models.lock.json
#
# 쓰는 법 (서버에서 · tmux 안에서)
#   tmux new -s deploy
#   bash deploy_server.sh preflight     #  1. 서버 · GPU 상태 점검
#   bash deploy_server.sh gpu           #  2. NVIDIA 드라이버 설치 (처음 한 번 · 끝나면 재부팅)
#   bash deploy_server.sh fetch         #  3. 저장소 받기 · 배포 커밋으로 맞추기
#   bash deploy_server.sh env           #  4. .env 자리 만들기 (비밀 값은 넣지 않는다)
#   bash deploy_server.sh install       #  5. 앱 패키지 설치 (.venv · CPU torch)
#   bash deploy_server.sh model         #  6. 임베딩 모델 받기 · 판정 인코더 잠금 검사
#   bash deploy_server.sh data          #  7. migrate → data-sync → load → embed
#   bash deploy_server.sh verify        #  8. 지문 대조
#   bash deploy_server.sh sllm-env      #  9. sLLM 가상환경 (.venv-sllm · GPU torch)
#   bash deploy_server.sh sllm-model    # 10. sLLM 베이스 받기 · 어댑터 잠금 검사
#   bash deploy_server.sh sllm          # 11. sLLM 서버 실행 (127.0.0.1:8765 · tmux 창 1)
#   bash deploy_server.sh serve         # 12. 앱 실행 (127.0.0.1:8000 · tmux 창 2 · 앞에 Caddy)
#   bash deploy_server.sh check         #     실행 중 상태 한 번에 보기 (GPU · 두 서버 · 포트)
#   bash deploy_server.sh services      # 13. 상시 가동 — sLLM · 앱을 systemd 서비스로 (재부팅해도 다시 뜬다)
#   bash deploy_server.sh services-off  #     서비스를 내리고 해제 (다시 tmux 로 띄울 때)
#   bash deploy_server.sh backup        #     DB 덤프 하나 (컨테이너 DB · ~/backup · 7개만 남긴다)
#   bash deploy_server.sh all           #  3~10 을 이어서 (gpu · sllm · serve 는 따로)
#
#   🔄 2026-10-15 — DB 비밀번호 자동 생성(env) · 기본 비밀번호면 적재 거부(data) · services · backup 을 더했다
#
# 🚨 이 파일에는 비밀번호 · 키 · DB 접속 문자열을 적지 않는다. 그 값은 서버의 .env 에만 둔다.
# 🚨 g4dn 의 로컬 NVMe(125GB · /dev/nvme1n1 등)는 **인스턴스를 중지하면 지워진다**. 모델 · DB 를 거기 두지 않는다.

set -euo pipefail

# ── 배포할 판 — 올리기 전에 이 줄들만 확인한다 ────────────────────────────────
REPO_URL="https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN32-FINAL-3TEAM.git"
DEPLOY_REF="${DEPLOY_REF:-main}"            # 브랜치 · 태그 · 커밋. 배포 때는 커밋 해시를 권한다
APP_DIR="${APP_DIR:-$HOME/SKN32-FINAL-3TEAM}"
EXPECT_GOLDEN="f6ccc5a7de44"                 # 골든 지문 (sha256 앞 12자 · 원장 data/derived_manifest.jsonl)
EXPECT_DICT="c6e29452c81b"                   # 사전 지문
DB_MODE="${DB_MODE:-container}"              # container = 서버 안 pgvector 컨테이너 · rds = RDS (승인 뒤)
EXPECT_INSTANCE="g4dn.xlarge"
MIN_DISK_GB=55                               # 루트 디스크 권장 60GB — 40GB 면 sLLM 까지 못 담는다

# sLLM — 판은 sllm_meta.py(기본값)와 models.lock.json(채택)이 정한다. 여기서는 바꾸지 않는다
SLLM_VENV="$APP_DIR/.venv-sllm"
SLLM_PORT=8765
SLLM_DRIVER="570-server"                     # CUDA 12.8 용 torch(cu128)는 드라이버 570 이상을 요구한다
TORCH_PIN="torch==2.11.0"
TORCH_INDEX="https://download.pytorch.org/whl/cu128"
SLLM_PKGS=(transformers==5.17.0 peft==0.21.0 accelerate==1.15.0 fastapi==0.142.2 uvicorn==0.54.0
           pydantic==2.13.5 python-dotenv==1.2.4)   # 버전은 docs/lse/sLLM_연결_안내 §2 (lse 가 쓰는 판)

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; }
warn() { printf '  [확인] %s\n' "$*"; }
die()  { printf '  [중단] %s\n' "$*" >&2; exit 1; }
L()    { (cd "$APP_DIR" && uv run python launcher.py "$@"); }
SPY()  { "$SLLM_VENV/bin/python" "$@"; }

# .env 의 한 줄을 바꾸거나 없으면 붙인다. 🚨 비밀이 아닌 값에만 쓴다.
set_env() {
  local key="$1" val="$2" f="$APP_DIR/.env"
  if grep -q "^${key}=" "$f"; then sed -i "s|^${key}=.*|${key}=${val}|" "$f"; else echo "${key}=${val}" >> "$f"; fi
}
get_env() { grep "^$1=" "$APP_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- || true; }

# models.lock.json 에서 역할(encoder · sllm_stage1 · sllm_stage2)의 채택 판 이름을 읽는다
adopted() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"][sys.argv[2]]["adopted"])' \
    "$APP_DIR/models.lock.json" "$1"
}
lock_check() {   # $1 = 폴더 · $2 = 역할 — 잠금 밖 판이면 멈춘다 (app 과 같은 규칙 · app/model_lock.py)
  (cd "$APP_DIR" && uv run python -m scripts.model_lock check "$1" --role "$2") \
    && ok "잠금 일치 — $2 · $(basename "$1")" || die "잠금 밖 판이다 — $1 ($2). 폴더를 다시 옮긴다"
}

instance_type() {  # IMDSv2
  local t; t="$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token \
                  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' || true)"
  curl -s -m 2 -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/instance-type || echo "?"
}

# ── 1. 서버 · GPU 상태 ───────────────────────────────────────────────────────
preflight() {
  say "1. 서버 · GPU 상태"
  local it; it="$(instance_type)"
  [ "$it" = "$EXPECT_INSTANCE" ] && ok "인스턴스 유형 $it" || warn "인스턴스 유형이 $it 이다 (기대 $EXPECT_INSTANCE)"
  [ -n "${TMUX:-}" ] && ok "tmux 안이다" || warn "tmux 밖이다 — 접속이 끊기면 작업도 끊긴다 (tmux new -s deploy)"
  docker ps >/dev/null 2>&1 && ok "docker" || warn "docker ps 실패 — 그룹 권한이면 접속을 끊고 다시 들어온다"
  docker compose version >/dev/null 2>&1 && ok "docker compose" || warn "docker compose 없음"
  command -v uv >/dev/null && ok "uv $(uv --version | awk '{print $2}')" || die "uv 없음 — curl -LsSf https://astral.sh/uv/install.sh | sh"
  uv python list --only-installed 2>/dev/null | grep -q "3.11.9" && ok "Python 3.11.9" || warn "Python 3.11.9 없음 — uv python install 3.11.9"
  sudo ufw status | grep -q "Status: active" && ok "ufw active" || warn "ufw 가 꺼져 있다"
  free -h | awk '/Mem/ {print "  [정보] 메모리 " $2} /Swap/ {print "  [정보] swap " $2}'
  local size; size="$(df -BG --output=size / | tail -1 | tr -dc 0-9)"
  [ "$size" -ge "$MIN_DISK_GB" ] && ok "루트 디스크 ${size}GB" \
    || warn "루트 디스크 ${size}GB — 60GB 로 늘린다 (콘솔 볼륨 수정 → sudo growpart /dev/nvme0n1 1 → sudo resize2fs /dev/nvme0n1p1)"
  df -h / | awk 'NR==2 {print "  [정보] 디스크 " $2 " 중 " $4 " 남음"}'
  command -v caddy >/dev/null && ok "caddy" || warn "caddy 없음"
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
    ok "GPU $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader)"
  else
    warn "nvidia-smi 가 안 된다 — bash deploy_server.sh gpu (드라이버 설치 · 재부팅)"
  fi
}

# ── 2. NVIDIA 드라이버 — 처음 한 번 ──────────────────────────────────────────
gpu() {
  say "2. NVIDIA 드라이버 ($SLLM_DRIVER)"
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
    ok "이미 동작 — $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader)"; return
  fi
  lspci | grep -qi nvidia && ok "GPU 장치가 보인다 ($(lspci | grep -i nvidia | head -1 | cut -d: -f3))" \
    || die "NVIDIA 장치가 없다 — 인스턴스 유형이 $EXPECT_INSTANCE 인지 콘솔에서 확인"
  sudo apt-get update
  sudo apt-get install -y ubuntu-drivers-common
  # ubuntu-drivers 가 이 커널(aws)에 맞는 서명된 모듈 꾸러미를 함께 고른다
  sudo ubuntu-drivers install --gpgpu "nvidia:$SLLM_DRIVER"
  sudo apt-get install -y "nvidia-utils-$SLLM_DRIVER"
  warn "설치 끝 — sudo reboot 후 다시 접속해서 bash deploy_server.sh preflight 로 GPU 줄을 본다"
  warn "재부팅하면 탄력적 IP 는 그대로다. tmux 는 새로 연다"
}

# ── 3. 저장소 ───────────────────────────────────────────────────────────────
fetch() {
  say "3. 저장소 받기 — $DEPLOY_REF"
  if [ -d "$APP_DIR/.git" ]; then git -C "$APP_DIR" fetch origin; else git clone "$REPO_URL" "$APP_DIR"; fi
  git -C "$APP_DIR" checkout --detach "$(git -C "$APP_DIR" rev-parse "origin/$DEPLOY_REF" 2>/dev/null || echo "$DEPLOY_REF")"
  ok "배포 커밋 $(git -C "$APP_DIR" log -1 --format='%h %s')"
  warn "이 커밋 해시를 작업기록에 적는다 — 커밋을 바꾸면 7번(data)을 다시 돈다"
}

# ── 4. .env ────────────────────────────────────────────────────────────────
env_file() {
  say "4. .env 자리 만들기"
  cd "$APP_DIR"
  [ -f .env ] || { cp .env.example .env; chmod 600 .env; ok ".env 를 .env.example 에서 만들었다 (권한 600)"; }
  set_env COPYLANE_EDITION cloud
  set_env DATA_ROLE replica
  set_env COPYLANE_MODEL_DIR "$(adopted encoder)"          # 판 이름 — app 이 models/<이름> 을 본다 (D-333)
  set_env COPYLANE_SLLM_URL "http://127.0.0.1:$SLLM_PORT"  # 🔄 g4dn — 같은 서버의 sLLM 을 부른다 (빈 값이면 꺼진다)
  set_env LANGCHAIN_TRACING_V2 false
  set_env LANGSMITH_TRACING false
  if [ -z "$(get_env COPYLANE_SESSION_SECRET)" ]; then     # 서버에서 만들어 바로 넣는다 — 화면에 찍지 않는다
    set_env COPYLANE_SESSION_SECRET "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    ok "COPYLANE_SESSION_SECRET 을 만들어 넣었다"
  fi
  # 🔄 2026-10-15 — 컨테이너 DB 비밀번호. compose 는 같은 폴더의 .env 에서 POSTGRES_PASSWORD 를 읽는다.
  #    🚨 첫 db-up 전에만 뜻이 있다 — DB 폴더(볼륨)가 한 번 만들어지면 비밀번호는 그때 값으로 굳는다.
  #    16진수만 쓰므로 URL 에 넣어도 바꿀 글자가 없다.
  if [ "$DB_MODE" = container ] && [ -z "$(get_env POSTGRES_PASSWORD)" ]; then
    local pw; pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
    set_env POSTGRES_PASSWORD "$pw"
    set_env DATABASE_URL "postgresql+psycopg://copylane:${pw}@localhost:5432/copylane"
    ok "DB 비밀번호를 만들어 POSTGRES_PASSWORD · DATABASE_URL 에 넣었다 (화면에 찍지 않음)"
    if docker volume ls -q 2>/dev/null | grep -q "pgdata"; then
      warn "이미 DB 볼륨이 있다 — 옛 비밀번호로 만들어졌으면 접속이 거부된다. 적재 전이면: docker compose down -v 뒤 data 단계"
    fi
  fi
  ok "COPYLANE_MODEL_DIR=$(get_env COPYLANE_MODEL_DIR)"
  ok "COPYLANE_SLLM_URL=$(get_env COPYLANE_SLLM_URL)"
  warn "sLLM 을 싣지 않기로 판정되면 COPYLANE_SLLM_URL=off 로 바꾼다"
  if [ "$DB_MODE" = container ]; then
    warn "직접 채울 것 — DATA_STORE=$HOME/CopyLane_store (파생물을 올린 폴더 · 절차서 §4-1)"
  else
    warn "직접 채울 것 — DATABASE_URL (RDS · 끝에 ?sslmode=require · 절차서 §4-3) · DATA_STORE"
  fi
  warn "편집: nano $APP_DIR/.env   🚨 값을 셸 인자나 대화창에 쓰지 않는다"
}

# ── 5. 앱 패키지 ────────────────────────────────────────────────────────────
install() {
  say "5. 앱 패키지 설치 (uv sync --no-dev · CPU torch)"
  cd "$APP_DIR" && uv sync --frozen --no-dev
  ok "설치 끝 — 앱 .venv 는 CPU torch 다. GPU torch 는 9번에서 따로 만든다 (한 환경에 못 합친다)"
}

# ── 6. 임베딩 · 판정 인코더 ─────────────────────────────────────────────────
model() {
  say "6. 임베딩 · 판정 인코더"
  L embed --check && ok "임베딩 모델(KURE-v1) 차원 확인" || die "embed --check 실패"
  local enc; enc="$APP_DIR/models/$(adopted encoder)"
  [ -d "$enc" ] || die "인코더 폴더가 없다 — $enc (PC 에서 SFTP 로 폴더째 올린다)"
  lock_check "$enc" encoder
}

# ── 7. DB · 데이터 — 순서가 뜻이 있다 (migrate 가 load 앞) ───────────────────
data() {
  say "7. DB · 데이터"
  [ -n "$(get_env DATABASE_URL)" ] || die ".env 의 DATABASE_URL 이 비어 있다"
  [ -n "$(get_env DATA_STORE)" ]   || die ".env 의 DATA_STORE 가 비어 있다"
  # 🔄 2026-10-15 — .env.example 의 개발용 기본 접속(copylane:copylane)으로는 배포 DB 를 만들지 않는다
  case "$(get_env DATABASE_URL)" in
    *copylane:copylane@*) die "DATABASE_URL 이 개발용 기본 비밀번호다 — POSTGRES_PASSWORD 줄을 지우고 env 단계를 다시" ;;
  esac
  [ -d "$(get_env DATA_STORE)/copylane-derived/objects" ] \
    || die "DATA_STORE 아래 copylane-derived/objects 가 없다 — pack_store.py 로 만든 묶음을 그 구조대로 올린다 (절차서 §4-1)"
  if [ "$DB_MODE" = container ]; then
    L db-up
    docker compose -f "$APP_DIR/docker-compose.yml" ps | grep -q "0.0.0.0:5432" && die "5432 가 0.0.0.0 에 열려 있다" || ok "5432 는 127.0.0.1 에만"
  else
    warn "DB_MODE=rds — db-up 을 건너뛴다. RDS 에서 CREATE EXTENSION IF NOT EXISTS vector; 를 먼저 실행했는지 확인"
  fi
  L migrate
  L data-sync --dry-run
  L data-sync
  L load
  L embed
  ok "적재 끝"
}

# ── 8. 지문 대조 ────────────────────────────────────────────────────────────
verify() {
  say "8. 지문 대조"
  local g d
  g="$(sha256sum "$APP_DIR/data/derived/golden/golden.jsonl" | cut -c1-12)"
  d="$(sha256sum "$APP_DIR/data/derived/banned_terms.jsonl" | cut -c1-12)"
  [ "$g" = "$EXPECT_GOLDEN" ] && ok "골든 $g" || die "골든 지문이 다르다 — $g (기대 $EXPECT_GOLDEN)"
  [ "$d" = "$EXPECT_DICT" ]   && ok "사전 $d" || die "사전 지문이 다르다 — $d (기대 $EXPECT_DICT)"
  [ "$(get_env COPYLANE_EDITION)" = cloud ] && ok "COPYLANE_EDITION=cloud" || die "COPYLANE_EDITION 이 cloud 가 아니다"
  [ -f "$APP_DIR/data/derived/hf_display_claims.jsonl" ] && ok "sLLM 관문용 hf_display_claims.jsonl 있음" \
    || warn "hf_display_claims.jsonl 이 없다 — sLLM /rewrite 가 500 을 낸다 (data-sync 확인)"
  warn "DB 사전이 파일과 같은지는 평가 도구(scripts/eval_graph.py --dev)가 도는지로 본다"
}

# ── 9. sLLM 가상환경 — 앱 .venv 와 따로 ─────────────────────────────────────
sllm_env() {
  say "9. sLLM 가상환경 ($SLLM_VENV)"
  nvidia-smi >/dev/null 2>&1 || die "GPU 드라이버가 먼저다 — bash deploy_server.sh gpu"
  [ -x "$SLLM_VENV/bin/python" ] || uv venv "$SLLM_VENV" --python 3.11.9
  uv pip install --python "$SLLM_VENV/bin/python" "$TORCH_PIN" --index-url "$TORCH_INDEX"
  uv pip install --python "$SLLM_VENV/bin/python" "${SLLM_PKGS[@]}"
  SPY - <<'PY'
import torch
assert torch.cuda.is_available(), "torch 가 GPU 를 못 본다"
name = torch.cuda.get_device_name(0)
cap = torch.cuda.get_device_capability(0)
print(f"  [OK]   torch {torch.__version__} · {name} · compute {cap[0]}.{cap[1]}")
if cap < (8, 0):
    print("  [확인] 이 GPU(T4 · 7.5)는 bf16 을 하드웨어로 못 한다 — sllm_service.py 는 bf16 고정이다.")
    print("         11번 뒤 문장 1건 시간을 잰다. 느리거나 오류면 lse 에 fp16 선택지를 요청한다 (계획 보고서 요청 ⑤)")
PY
  warn "다 받은 뒤 uv cache clean 으로 디스크를 되찾는다 (torch cu128 꾸러미가 크다)"
}

# ── 10. sLLM 베이스 · 어댑터 ────────────────────────────────────────────────
sllm_model() {
  say "10. sLLM 베이스 · 어댑터"
  [ -x "$SLLM_VENV/bin/python" ] || die "9번(sllm-env)이 먼저다"
  local base; base="$(cd "$APP_DIR" && python3 -c 'import sys; sys.path.insert(0,"docs/lse"); import sllm_meta; print(sllm_meta.base_model())')"
  ok "베이스 $base (약 8GB · 서버에서 허브로 직접 받는다)"
  # 🚨 safetensors 만 받는다 (*.bin · *.pt 받지 않음)
  HF_HUB_OFFLINE=0 SPY -c "from huggingface_hub import snapshot_download as s; \
s('$base', allow_patterns=['*.json','*.safetensors','*.txt','tokenizer*','merges.txt','vocab.json'])" \
    && ok "베이스 받기 끝" || die "베이스 받기 실패"
  local s1 s2
  s1="$APP_DIR/models/$(adopted sllm_stage1)"
  s2="$APP_DIR/models/$(adopted sllm_stage2)"
  for d in "$s1" "$s2"; do
    [ -d "$d" ] || die "어댑터 폴더가 없다 — $d (공유 저장소 copylane-models/ 에서 PC 를 거쳐 SFTP 로 폴더째 올린다)"
  done
  lock_check "$s1" sllm_stage1
  lock_check "$s2" sllm_stage2
}

# ── 11. sLLM 서버 — 127.0.0.1:8765 · 외부에 열지 않는다 ─────────────────────
sllm() {
  say "11. sLLM 서버 — 127.0.0.1:$SLLM_PORT (처음 약 30초 모델을 올린다)"
  warn "이 창은 sLLM 이 차지한다. 앱은 다른 tmux 창(Ctrl-b c)에서 serve 로 띄운다"
  cd "$APP_DIR"
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  exec "$SLLM_VENV/bin/python" docs/lse/sllm_service.py --serve --port "$SLLM_PORT"
}

# ── 12. 앱 실행 ────────────────────────────────────────────────────────────
serve() {
  say "12. 앱 실행 — 127.0.0.1:8000 (밖으로는 Caddy 만 연다)"
  export HF_HUB_OFFLINE=1      # 모델을 받은 뒤에는 허브로 나가지 않는다
  L serve --no-reload
}

# ── 실행 중 상태 ────────────────────────────────────────────────────────────
check() {
  say "실행 중 상태"
  nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader \
    | awk '{print "  [정보] GPU " $0}' || warn "nvidia-smi 실패"
  curl -s -m 5 "http://127.0.0.1:$SLLM_PORT/health" && echo || warn "sLLM /health 응답 없음"
  curl -s -o /dev/null -m 5 -w "  [정보] 앱 HTTP %{http_code}\n" http://127.0.0.1:8000/ || warn "앱 응답 없음"
  ss -ltn | awk 'NR>1 {print $4}' | grep -E ':(8000|8765|5432)$' | while read -r a; do
    case "$a" in 127.0.0.1:*) ok "$a (안쪽만)";; *) warn "$a — 밖에 열려 있다";; esac
  done
}

# ── 13. 상시 가동 — systemd 서비스 (🔄 2026-10-15) ──────────────────────────
# tmux 로 띄운 서버는 재부팅 · 접속 끊김 사고에 같이 죽는다. 10/24 ~ 26 상시 가동 구간은 서비스로 둔다.
# 🚨 tmux 의 sllm · serve 창을 먼저 끈다(Ctrl-C) — 포트가 겹치면 서비스가 못 뜬다.
services() {
  say "13. 서비스 등록 — copylane-sllm · copylane-app"
  local uvbin user; uvbin="$(command -v uv)" || die "uv 없음"; user="$(id -un)"
  if ss -ltn | awk '{print $4}' | grep -qE ':(8000|8765)$' && ! systemctl is-active -q copylane-app copylane-sllm 2>/dev/null; then
    die "8000 이나 8765 를 이미 누가 쓰고 있다 — tmux 의 serve · sllm 창을 Ctrl-C 로 끈 뒤 다시"
  fi
  local with_sllm=1
  [ "$(get_env COPYLANE_SLLM_URL)" = off ] && { with_sllm=0; warn "COPYLANE_SLLM_URL=off — sLLM 서비스는 만들지 않는다"; }

  if [ "$with_sllm" = 1 ]; then
    [ -x "$SLLM_VENV/bin/python" ] || die "9번(sllm-env)이 먼저다"
    sudo tee /etc/systemd/system/copylane-sllm.service >/dev/null <<UNIT
[Unit]
Description=CopyLane sLLM rewrite server (127.0.0.1:$SLLM_PORT)
After=network-online.target
Wants=network-online.target

[Service]
User=$user
WorkingDirectory=$APP_DIR
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
ExecStart=$SLLM_VENV/bin/python docs/lse/sllm_service.py --serve --port $SLLM_PORT
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT
  fi

  sudo tee /etc/systemd/system/copylane-app.service >/dev/null <<UNIT
[Unit]
Description=CopyLane app (uvicorn 127.0.0.1:8000)
After=network-online.target docker.service$( [ "$with_sllm" = 1 ] && echo " copylane-sllm.service")
Wants=network-online.target

[Service]
User=$user
WorkingDirectory=$APP_DIR
Environment=HF_HUB_OFFLINE=1
Environment=UV_FROZEN=1
# launcher 가 안에서 다시 uv 를 부른다 — systemd 의 기본 PATH 에는 ~/.local/bin 이 없다
Environment=PATH=$(dirname "$uvbin"):/usr/local/bin:/usr/bin:/bin
ExecStart=$uvbin run python launcher.py serve --no-reload
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

  sudo systemctl daemon-reload
  [ "$with_sllm" = 1 ] && sudo systemctl enable --now copylane-sllm
  sudo systemctl enable --now copylane-app
  ok "등록 끝 — 상태: systemctl status copylane-app · 로그: journalctl -u copylane-app -f"
  warn "sLLM 은 약 30초 뒤에 응답한다 — 그 뒤 bash deploy_server.sh check"
}

services_off() {
  say "서비스 내리기 · 해제"
  for u in copylane-app copylane-sllm; do
    systemctl list-unit-files "$u.service" >/dev/null 2>&1 && sudo systemctl disable --now "$u" 2>/dev/null && ok "$u 내림" || true
  done
  warn "다시 tmux 로 띄울 때는 창 1 sllm · 창 2 serve"
}

# ── DB 백업 (🔄 2026-10-15) — 컨테이너 DB 만. RDS 는 자동 백업이 있다 ──────────
backup() {
  say "DB 백업"
  [ "$DB_MODE" = container ] || { warn "DB_MODE=$DB_MODE — RDS 는 콘솔의 자동 백업 · 스냅샷을 쓴다"; return; }
  mkdir -p "$HOME/backup" && chmod 700 "$HOME/backup"
  local f; f="$HOME/backup/copylane_$(date +%Y%m%d_%H%M).sql.gz"
  docker exec copylane-postgres pg_dump -U copylane copylane | gzip > "$f"
  [ -s "$f" ] && ok "$f ($(du -h "$f" | cut -f1))" || die "덤프가 비었다 — $f"
  ls -1t "$HOME/backup"/copylane_*.sql.gz | tail -n +8 | xargs -r rm --
  warn "주 1회는 MobaXterm SFTP 로 내 PC 에 내려받는다 — 서버 안에만 있는 백업은 백업이 아니다"
  warn "🚨 덤프에는 가입 계정이 들어 있다 — 저장소 · 메신저에 올리지 않는다"
}

case "${1:-}" in
  preflight)  preflight ;;
  gpu)        gpu ;;
  fetch)      fetch ;;
  env)        env_file ;;
  install)    install ;;
  model)      model ;;
  data)       data ;;
  verify)     verify ;;
  sllm-env)   sllm_env ;;
  sllm-model) sllm_model ;;
  sllm)       sllm ;;
  serve)      serve ;;
  check)      check ;;
  services)   services ;;
  services-off) services_off ;;
  backup)     backup ;;
  all)        preflight; fetch; env_file; install; model; data; verify; sllm_env; sllm_model ;;
  *) sed -n '2,30p' "$0"; exit 1 ;;
esac
