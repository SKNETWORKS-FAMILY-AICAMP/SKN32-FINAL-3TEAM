#Requires -Version 5.1
<#
  CopyLane 부트스트랩 (D-51)

  이 스크립트는 "런처를 실행할 수 있는 상태"를 만든다.
  런처 자신은 이 일을 할 수 없다 — uv 가 없으면 런처도 못 뜬다.

  실행: setup.bat 더블클릭  (PowerShell 실행 정책을 우회한다)
  여러 번 돌려도 안전하다 (멱등).
#>

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Step($n, $msg) { Write-Host "`
[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "  OK   $msg" -ForegroundColor Green }
function Warn($msg)     { Write-Host "  경고 $msg" -ForegroundColor Yellow }
function Info($msg)     { Write-Host "       $msg" -ForegroundColor DarkGray }

Set-Location $PSScriptRoot
Write-Host ""
Write-Host "  CopyLane 환경 설정" -ForegroundColor White
Write-Host "  ------------------" -ForegroundColor DarkGray

# ── [1] uv ────────────────────────────────────────────────
Step 1 "uv 확인"
$uvHome = Join-Path $env:USERPROFILE ".local\bin"
$uvExe  = Join-Path $uvHome "uv.exe"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (Test-Path $uvExe) {
        Ok "설치돼 있으나 PATH 에 없음 — 잡아준다"
    } else {
        Info "uv 설치 중 (관리자 권한 불필요)"
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    }
    $env:Path = "$uvHome;$env:Path"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Warn "uv 를 찾지 못했다. 창을 닫고 setup.bat 을 다시 실행할 것"
    exit 1
}
Ok "$(uv --version)"

# PATH 영구 등록
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$uvHome*") {
    [Environment]::SetEnvironmentVariable("Path", "$uvHome;$userPath", "User")
    Ok "PATH 영구 등록 (새 창부터 적용)"
}

# ── [2] 한글 인코딩 ───────────────────────────────────────
Step 2 "PYTHONUTF8 확인"
if ([Environment]::GetEnvironmentVariable("PYTHONUTF8", "User") -ne "1") {
    [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
    Ok "PYTHONUTF8=1 등록 — cp949 디코딩 오류 방지"
} else {
    Ok "이미 설정됨"
}
$env:PYTHONUTF8 = "1"

# ── [3] 파이썬 환경 ───────────────────────────────────────
Step 3 "의존성 동기화 (uv sync)"
Info "Python 3.11 이 없으면 uv 가 알아서 내려받는다"
uv sync
if ($LASTEXITCODE -ne 0) { Warn "uv sync 실패 — 위 오류를 팀장에게 그대로 전달할 것"; exit 1 }
Ok "uv.lock 과 일치"

# ── [4] 커밋 훅 ───────────────────────────────────────────
Step 4 "pre-commit 훅 설치"
uv run pre-commit install | Out-Null
Ok "설치 완료 (ruff · gitleaks)"

# ── [5] .env ──────────────────────────────────────────────
Step 5 ".env 확인"
if (Test-Path ".env") {
    Ok "이미 있음"
} else {
    Copy-Item ".env.example" ".env"
    Ok ".env.example 을 복사했다"
    Warn "LAW_OC_KEY 를 직접 채워야 한다 (법제처 개인 발급 키)"
}

# ── [6] Docker (선택) ─────────────────────────────────────
Step 6 "Docker + DB (postgres + pgvector)"

$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Warn "Docker 가 설치돼 있지 않다 — W2 walking skeleton 부터 필요하다"
    Info "https://www.docker.com/products/docker-desktop/  (설치 후 재부팅 필요)"
    Info "지금 단계(파이썬 환경·테스트·훅)는 Docker 없이 전부 동작한다"
} else {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Info "Docker 엔진이 응답하지 않는다 — Docker Desktop 을 켠다"
        $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $exe) { Start-Process $exe | Out-Null }

        # 콜드 스타트는 보통 30~60초. 무한 대기는 절대 하지 않는다.
        $waited = 0
        while ($waited -lt 90) {
            Start-Sleep -Seconds 5
            $waited += 5
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Write-Host "       기동 대기 ${waited}s / 90s" -ForegroundColor DarkGray
        }
    }

    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Warn "Docker 엔진이 90초 안에 뜨지 않았다 — Docker Desktop 을 직접 켜고 다시 실행할 것"
    } else {
        Ok "Docker 실행 중"
        docker compose up -d
        if ($LASTEXITCODE -ne 0) {
            Warn "컨테이너 기동 실패 — 위 오류를 팀장에게 전달할 것"
        } else {
            # healthcheck 통과까지 대기
            $waited = 0
            while ($waited -lt 60) {
                $state = docker inspect -f "{{.State.Health.Status}}" copylane-postgres 2>$null
                if ($state -eq "healthy") { break }
                Start-Sleep -Seconds 3
                $waited += 3
            }
            docker compose exec -T postgres psql -U copylane -d copylane -c "CREATE EXTENSION IF NOT EXISTS vector;" *> $null
            if ($LASTEXITCODE -eq 0) { Ok "postgres 기동 + pgvector 확장 확인 (127.0.0.1:5432)" }
            else { Warn "postgres 는 떴으나 pgvector 확장 생성에 실패했다" }
        }
    }
}

$ErrorActionPreference = $prev

# ── [7] 게이트 ────────────────────────────────────────────
Step 7 "거버넌스 게이트 확인"
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
uv run pytest -m gate -q
$gateOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prev
if ($gateOk) { Ok "전부 통과" } else { Warn "게이트 실패 — 위 내용을 팀장에게 전달할 것" }

# ── [8] 런처 ──────────────────────────────────────────────
Write-Host ""
Write-Host "  환경 설정 완료. 런처를 띄운다." -ForegroundColor Green
Write-Host "  다음부터는:  uv run python launcher.py" -ForegroundColor DarkGray
Write-Host ""
uv run python launcher.py
