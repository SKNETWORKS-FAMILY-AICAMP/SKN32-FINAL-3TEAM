"""scripts/db_reset.py — **DB 를 선언 상태로 다시 만든다** (2026-09-14 · D-90 의 DB 판).

    uv run python launcher.py db-reset                 # 미리보기 — 아무것도 안 지운다
    uv run python launcher.py db-reset --yes           # 볼륨을 지우고 스키마를 다시 세운다
    uv run python launcher.py db-reset --yes --data    # 역할별 — 정본: 재추출→적재→청킹→임베딩→원장
                                                       #          사본: 받은 파생물로 적재→임베딩

🔴 **왜 있나 — 09-13(이서은)·09-14(박수진) 이틀 연속 같은 자리에서 막혔다.**
   두 사람 다 `docker compose down -v` 로 **자력으로** 풀었다. 즉 처방은 이미 있었는데
   **절차가 아니어서 각자 따로 발견했다.** ⛔ 채팅으로 돌린 처방은 다음 사람이 또 묻는다.

★ **DB 를 생성물로 본다.** 집행계약이 이미 *「생성물은 손으로 고치지 않는다 — 원천을 고치고
  `rebuild`」* 라 적었다 (D-90). **DB 만 그 분류가 안 돼 있었다.** 원천은 셋이다 —
  마이그레이션 체인 · `data/derived/**` · 시드. 그래서 **고치지 않고 다시 만든다.**
  ⛔ 옛 볼륨을 고쳐 쓰는 길을 열어 두면 **기기마다 다른 중간 상태가 쌓인다** — 그것이 09-14 다.

🚨 **비밀번호는 복구할 수 없다.** `app_account` 는 **DB 에만 있고 파일에 없는 유일한 값**이다
   (D-66 · D-213 — 가입 화면이 없어 `admin-add` 로만 만든다). 그래서 지우기 **전에** 명단을
   읽어 두고, 다시 세운 뒤 **사람이 칠 명령을 이니셜마다 찍는다.** 값은 안 찍는다 (D-111).

🚨 **원천 디렉터리를 이 파일이 직접 보지 않는다** (2026-09-14 · D-92 · D-19).
   ⛔ 처음에 원문 디렉터리가 있는지 미리 봐 주려고 그 경로를 들었다가
      `test_raw_는_수집_전처리_밖에서_참조되지_않는다` 에 걸렸다. **게이트가 옳다** —
      원천을 읽는 것은 수집·전처리 모듈뿐이고, 이 도구는 그것들을 **부르기만** 한다.
   ★ 대신 **출력(파생물)이 비었는지**를 본다. 그게 더 나은 검사다 — 원천이 없을 때뿐 아니라
     추출이 조용히 0건을 낸 모든 경우를 잡는다 (D-149 의 「보낸 수가 아니라 들어간 수」).

🔴 **역할을 지우기 전에 본다** (2026-09-20 · D-254 · 감사 §1-5).
   ⛔ 종전 `--data` 는 **볼륨을 먼저 지우고** 추출 모듈을 직접 불러 `only_canonical`·`needs_raw` 를
      우회했다. 사본은 원문이 없어 추출이 빈 것을 내고 **빈 DB** 가 남았고, 원문이 있는 사본은
      파생물을 덮어쓴 뒤 `chunk --dump`(정본 전용)에서 멈춰 **반쪽 DB** 가 남았고, 정본은 파생물
      원장(`derived_manifest.jsonl`)이 낡은 채로 남았다.
   ★ 이제 —
       정본(canonical)  지우기 전  합치지 않은 팀원 원문 확인(`raw_inbox.check_pending`)
                        지운 뒤    조문·별표 재추출 → load → chunk --dump → embed
                                   → `data-refresh --no-golden`(원장 쓰기 + 올리기 전 검사 · 같은 단계표)
       사본(replica)    지우기 전  받은 파생물(조문·별표·청크)이 있는지 — 없으면 `data-sync` 안내 후 멈춤
                        지운 뒤    load → embed 만. **재추출·청킹을 하지 않는다** (D-226 · 만들지 않고 받는다)
       역할 없음        `--data` 를 거부한다 — 어느 쪽인지 모르면 만들지도 받지도 않는다 (D-220)
   🚨 판단은 `derived_manifest.role()` 한 곳이다 — 여기서 다시 만들지 않는다 (D-99).

⬜ **여기서 다시 만들지 않는 것** (D-188) —
   ① **원문.** git 으로 안 온다 (D-19). `launcher.py inventory` 가 이 기기에 없는 것을 낸다.
   ② **골든셋·금지표현 사전 등 다른 파생물.** `--data` 는 법령·별표만 다시 뽑는다 —
      나머지는 마스킹 정책·2인 확인이 걸려 자동으로 돌릴 것이 아니다 (D-72 · D-109).
   ③ **비밀번호.** 위 참조.
   ④ **`.env` 의 API 키.** `.gitignore` 다 (D-111).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # noqa: S404 — docker 와 launcher 를 자식 프로세스로 돌린다
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import derived_manifest as dm  # noqa: E402 — 위 sys.path 뒤에 들여온다
from scripts.load_db import LOAD_INPUTS  # noqa: E402 — 적재 입력의 정본 (D-99)

LAUNCHER = ROOT / "launcher.py"
DERIVED = ROOT / "data" / "derived"
#: 🔴 재추출이 **정말 뭔가를 냈는지** 보는 자리. 비었으면 멈춘다 — 빈 파생물이 임베딩까지
#:    흘러가면 그 층이 통째로 빠진 채 「성공」으로 찍힌다 (D-220 · `chunk.py` 의 가드와 같다).
#:    ⛔ 원천 디렉터리는 안 본다 (D-92) — 위 docstring 참조.
DERIVED_CHECKS: tuple[tuple[str, str], ...] = (
    ("조문", "law_article.jsonl"),
    ("별표", "law_norm"),
)
#: 🔴 `load` 가 읽는 것 — `load_db.LOAD_INPUTS` 에서 꺼낸다 (D-99).
#: 🔄 2026-09-21 — ⛔ 종전에는 조문·별표만 적어, 금지표현 사전·건기식 라벨·골든셋이 없으면
#:    볼륨을 **지운 뒤에** `load` 가 멈췄다. 이제 지우기 전에 본다.
LOAD_CHECKS: tuple[tuple[str, str], ...] = tuple((label, name) for label, name, _ in LOAD_INPUTS)
#: 🔴 사본이 **받아 와야 하는** 것 — 재추출을 안 하므로 청크까지 받은 판이 있어야 한다 (D-247).
REPLICA_CHECKS: tuple[tuple[str, str], ...] = (*LOAD_CHECKS, ("청크", "chunks.jsonl"))
#: 🔴 정본이 **다시 만들지 않는** 적재 입력 — 재추출(조문·별표) 밖이라 지우기 전에 있어야 한다.
CANONICAL_CHECKS: tuple[tuple[str, str], ...] = tuple(
    c for c in LOAD_CHECKS if c[1] not in {n for _, n in DERIVED_CHECKS}
)
#: 🚨 DB 를 **기다리지 않는다** — 아래 `accounts()` 참조. `[임의]` — 로컬 도커다.
CONNECT_TIMEOUT_S = 3


def _derived_empty(checks: tuple[tuple[str, str], ...] = DERIVED_CHECKS) -> list[str]:
    """비어 있는 파생물 이름. 🚨 **파일이 있는지가 아니라 내용이 있는지**를 본다."""
    empty = []
    for label, name in checks:
        p = DERIVED / name
        if p.is_dir():
            if not any(f.stat().st_size > 0 for f in p.glob("*.jsonl")):
                empty.append(f"{label}({name}/)")
        elif not p.exists() or p.stat().st_size == 0:
            empty.append(f"{label}({name})")
    return empty


def _run(*args: str) -> int:
    print(f"\n  $ {' '.join(args)}", flush=True)
    return subprocess.run(args, cwd=ROOT, check=False).returncode  # noqa: S603


def _launcher(*args: str) -> int:
    """런처를 통해 돈다 — 🚨 `db-up` 의 `CREATE EXTENSION vector` 를 여기 베끼지 않는다 (D-99)."""
    return _run(sys.executable, str(LAUNCHER), *args)


def accounts() -> list[str] | None:
    """지우기 **전에** 콘솔 계정 이니셜을 읽어 둔다.

    🔴 **`None` 과 `[]` 는 다르다** (D-188) — `None` 은 「못 읽었다」(DB 가 꺼져 있거나 표가
       없다), `[]` 는 「읽었고 계정이 없다」다. ⛔ 못 읽은 것을 「없다」고 말하지 않는다.

    🔴 **기다리지 않는다** (2026-09-14 실측). 처음에 타임아웃 없이 붙었더니 **말없이 멈췄고
       사람이 `Ctrl-C` 를 눌렀다.** ⛔ DB 가 나쁜 상태일 때 쓰는 도구가 DB 를 기다리다
       멈추면 쓸 수가 없다 — 그게 이 도구가 있는 이유다.
    """
    try:
        import psycopg  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with (
            psycopg.connect(dsn(), connect_timeout=CONNECT_TIMEOUT_S) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT initials FROM app_account ORDER BY initials")
            return [r[0] for r in cur.fetchall()]
    except Exception:  # noqa: BLE001 — DB 가 꺼져 있어도 이 도구는 서야 한다
        return None


def _report_accounts(found: list[str] | None) -> None:
    if found is None:
        print("  ⬜ 콘솔 계정을 **못 읽었다** — DB 가 꺼져 있거나 표가 없다.")
        print("     🚨 「계정이 없다」가 아니다. 있었다면 지운 뒤 다시 만들어야 한다 (D-188).")
    elif not found:
        print("  ⬜ 콘솔 계정이 없다 — 지워질 것이 없다.")
    else:
        print(f"  🔴 **콘솔 계정 {len(found)}개가 사라진다** — {', '.join(found)}")
        print("     비밀번호는 Argon2id 해시라 **되살릴 수 없다.** 아래에서 다시 만든다.")


def _seed_guide(found: list[str] | None) -> None:
    print("\n  ④ 시드 — 🚨 **사람만 할 수 있다** (비밀번호는 `getpass` 로만 · D-111)")
    if not found:
        print("     uv run python launcher.py admin-add <이니셜>")
        print("     🚨 가입 화면은 없다 (D-66 — 온프레미스는 계정 주입).")
        return
    for ini in found:
        print(f"     uv run python launcher.py admin-add {ini}")
    print("     ⛔ 이 목록은 **지우기 전에 읽어 둔 것**이다. 빠진 사람이 있으면 직접 더한다.")


def reset_schema() -> int:
    """볼륨을 지우고 컨테이너를 다시 띄우고 마이그레이션을 건다."""
    print("\n  ① 볼륨 삭제 — 🔴 여기서 데이터가 사라진다")
    if code := _run("docker", "compose", "down", "-v"):
        print("  🔴 `docker compose down -v` 가 실패했다 — Docker Desktop 을 본다.")
        return code

    print("\n  ② 컨테이너 기동 + `vector` 확장")
    if code := _launcher("db-up"):
        print("  🔴 db-up 실패 — 여기서 멈춘다. DB 없이 뒤 단계를 돌리면 전부 거짓이 된다.")
        return code

    print("\n  ③ 마이그레이션 — 🧊 0번은 동결본을 읽는다")
    if code := _launcher("migrate"):
        print("  🔴 마이그레이션 실패 — **빈 DB 에서만 나는 종류**일 수 있다.")
        print("     uv run python launcher.py db-fresh   의 출력을 팀에 준다 (D-221)")
        return code
    return 0


def preflight_data(who: str | None) -> int:
    """🔴 `--data` 를 **지우기 전에** 역할별로 확인한다 (2026-09-20 · D-254). 0 이면 진행해도 된다.

    ⛔ 종전에는 볼륨을 지운 **뒤에야** 추출이 빈 것을 냈는지 알았다 — 멈춰도 DB 는 이미 비었다.
    🚨 미리보기에서도 돈다 — 「지우면 어떻게 되는지」를 지우기 전에 보여 준다.
    """
    if who is None:
        print(
            "\n  🔴 `--data` — 이 기기 역할(DATA_ROLE)이 설정 안 됐다. 지우기 전에 멈춘다 (D-220)."
        )
        print("     역할을 모르면 파생물을 만들지도(정본) 받지도(사본) 않는다.")
        print("     · 클론 A·팀원 — uv run python launcher.py data-setup --role replica")
        print("     · 클론 B     — uv run python launcher.py data-setup --role canonical")
        return 1
    if who == "replica":
        if missing := _derived_empty(REPLICA_CHECKS):
            print(f"\n  🔴 받은 파생물이 없다 — {' · '.join(missing)}. 지우기 전에 멈춘다.")
            print("     ⛔ 사본은 재추출하지 않는다 (D-226) — 정본이 올린 판을 받는다:")
            print("       uv run python launcher.py data-sync")
            print("     ⬜ 아무것도 안 지웠다.")
            return 1
        return 0
    # 정본 — 🔴 합치지 않은 팀원 원문이 있으면 재추출이 **그 원문을 빼고** 파생물을 만든다 (D-250).
    #    런처 `needs_raw` 가 부르는 것과 같은 함수다 (D-99).
    from scripts import raw_inbox  # noqa: PLC0415 — 정본에서만 필요하다

    if raw_inbox.check_pending():
        print("     ⬜ 아무것도 안 지웠다 — `raw-import` 뒤에 다시 부른다.")
        return 1
    if missing := _derived_empty(CANONICAL_CHECKS):
        how = {name: cmd for _, name, cmd in LOAD_INPUTS}
        print(f"\n  🔴 적재 입력이 없다 — {' · '.join(missing)}. 지우기 전에 멈춘다.")
        print("     `--data` 는 조문·별표만 다시 뽑는다 — 나머지는 먼저 만들어 둔다:")
        for _label, name in CANONICAL_CHECKS:
            print(f"       {how[name]}")
        print("     ⬜ 아무것도 안 지웠다.")
        return 1
    return 0


def _steps(label_args: list[tuple[str, tuple[str, ...]]], step: int) -> tuple[int, int]:
    """단계를 차례로 돈다. 🔴 한 단계가 죽으면 **거기서 멈춘다** (D-220). 반환 — (코드, 다음 번호)."""
    for label, args in label_args:
        print(f"\n  {step}. {label}")
        step += 1
        if code := _run(*args):
            # 🔴 뒤 단계가 「성공」으로 찍히면 무엇이 비었는지 모르는 DB 가 남는다.
            print(f"  🔴 {label} 실패 — 여기서 멈춘다. 뒤 단계는 돌리지 않았다.")
            return code, step
    return 0, step


def reload_data(who: str | None) -> int:
    """역할에 맞게 DB 를 다시 채운다. 🚨 `preflight_data()` 를 **지우기 전에** 통과한 뒤에만 부른다.

    🔴 **정본은 재추출이 앞에 온다.** `onboard` §7 은 `load` → `chunk` → `embed` 뿐이어서, 그 순서를
       따른 사람은 **낡은 파생물로 DB 를 세운다.** 2026-09-14 에 `citation()` 커버리지가
       38.1% 였던 원인이 정확히 그것이다 — 코드는 09-12 에 고쳤는데 파생물이 09-10 판이었다.
    🔴 **사본은 재추출·청킹을 하지 않는다** (D-226) — 받은 파생물로 load → embed 만 (D-254).
    """
    py = sys.executable
    if who == "replica":
        print("\n  ⬜ 사본 — 재추출·청킹을 하지 않는다. 받은 파생물로 적재한다 (D-226)")
        code, _ = _steps(
            [
                ("DB 적재", (py, str(LAUNCHER), "load")),
                ("임베딩", (py, str(LAUNCHER), "embed")),
            ],
            5,
        )
        return code
    if who != "canonical":  # 🚨 preflight 가 먼저 막는다 — 여기 오면 호출 순서가 틀린 것이다
        print("  🔴 역할을 모른다 — 적재하지 않는다 (D-220)")
        return 1

    # ⛔ 조문·별표는 `preprocess.EXTRACTORS` 에 없어 `data-refresh <원천>` 으로 못 부른다 —
    #    그래서 추출만 직접 부르고, 앞(원문 확인)·뒤(원장)는 런처의 같은 단계표를 탄다 (D-99).
    code, step = _steps(
        [
            ("조문 재추출", (py, "-m", "preprocess.law_article", "--dump")),
            # 🚨 `--write` 다. `law_norm.py` 의 docstring 은 `--dump` 라 적혀 있으나 쓰기 플래그는
            #    이쪽이다 — 문서대로 돌린 사람은 별표가 통째로 빠진 채 다음 단계로 간다.
            ("별표 재추출", (py, "-m", "preprocess.law_norm", "--write")),
        ],
        5,
    )
    if code:
        return code

    # 🔴 **추출이 0 을 냈는지 여기서 본다** — 종료코드 0 은 「돌았다」이고 「뭔가 나왔다」가
    #    아니다 (D-149). ⛔ 이 검사가 없으면 빈 파생물이 임베딩까지 흘러가고, `embed` 의
    #    `sweep_orphans` 가 **DB 의 청크를 전부 거둔다.**
    if empty := _derived_empty():
        print(f"\n  🔴 재추출이 빈 것을 냈다 — {' · '.join(empty)}")
        print("     ⛔ 여기서 멈춘다. 이대로 가면 `embed` 가 DB 의 청크를 전부 거둔다 (D-187).")
        print("     ★ 이 기기에 원문이 없을 것이다 — git 으로 안 온다 (D-19):")
        print("       uv run python launcher.py inventory")
        return 1

    code, step = _steps(
        [
            ("DB 적재", (py, str(LAUNCHER), "load")),
            ("청킹", (py, str(LAUNCHER), "chunk", "--dump")),
            ("임베딩", (py, str(LAUNCHER), "embed")),
            # 🔴 **파생물을 다시 만들었으니 원장도 다시 쓴다** (D-254). ⛔ 종전에는 여기서 끝나
            #    `derived_manifest.jsonl` 이 낡은 채 남았다. 원문 확인 → 원장 쓰기 → 올리기 전 검사를
            #    `launcher.py data-refresh` 의 **같은 단계표**로 돈다 — 베끼지 않는다 (D-99).
            #    🚨 외부 전송(`data-publish`)·git 은 하지 않는다 — 끝에 칠 명령을 그쪽이 찍는다.
            ("파생물 원장 · 올리기 전 검사", (py, str(LAUNCHER), "data-refresh", "--no-golden")),
        ],
        step,
    )
    if code:
        print("     🚨 DB 는 섰을 수 있다 — 원장·올리기가 남았다:")
        print("       uv run python launcher.py data-refresh --no-golden")
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description="DB 를 선언 상태로 다시 만든다")
    ap.add_argument("--yes", action="store_true", help="🔴 실제로 지운다 (없으면 미리보기)")
    ap.add_argument("--data", action="store_true", help="파생물 재추출 → 적재 → 임베딩까지")
    args = ap.parse_args()

    if shutil.which("docker") is None:
        print("🔴 docker 가 없다 — Docker Desktop 을 켜고 다시 부른다.")
        return 1

    # 🔴 **역할을 지우기 전에 본다 — 미리보기에서도** (2026-09-20 · D-254 · 감사 §1-5).
    #    🚨 `role()` 은 오타면 여기서 멈춘다 (D-220) — 지운 뒤에 멈추지 않게 맨 앞이다.
    who = dm.role()

    # 🔴 **연결보다 출력이 먼저다** (2026-09-14 실측). 처음에는 `accounts()` 가 먼저였고,
    #    붙는 동안 화면이 비어서 **멈춘 것처럼 보였다** — 사람이 `Ctrl-C` 를 눌렀다.
    #    ⛔ 기다리게 만드는 도구는 무엇을 기다리는지 먼저 말한다.
    print("🚨 **DB 를 지우고 다시 만든다** — 되돌릴 수 없다.\n")
    print(f"  콘솔 계정 명단을 먼저 읽는다 (최대 {CONNECT_TIMEOUT_S}초) …", flush=True)
    found = accounts()
    print("\n  무엇이 사라지나")
    _report_accounts(found)
    print("  ⬜ 청크·임베딩·거버넌스 표는 파생물에서 되세운다 — `--data` 가 그 일을 한다.")
    print(f"  이 기기 역할: {who or '설정 안 됨'}")
    if who == "canonical":
        print("  🔴 정본 — `--data` 는 원문에서 다시 뽑는다. 원문이 없으면 되세울 수 없다 (D-19).")
        print("     uv run python launcher.py inventory   로 없는 것을 본다")
    elif who == "replica":
        print("  ⬜ 사본 — `--data` 는 받은 파생물로만 채운다. 원문은 필요 없다 (D-226).")

    # 🔴 `--data` 의 선결은 **지우기 전에** 본다 — 미리보기에서도 같은 답을 낸다.
    if args.data and (code := preflight_data(who)):
        return code

    if not args.yes:
        # 🔴 fail-closed — **기본이 미리보기다.** 지우는 것은 명시해야 돈다 (D-220).
        print("\n⬜ **미리보기였다 — 아무것도 안 지웠다.**")
        print("   실제로 하려면:  uv run python launcher.py db-reset --yes")
        print("   파생물까지:     uv run python launcher.py db-reset --yes --data")
        return 0

    if code := reset_schema():
        return code
    _seed_guide(found)

    if args.data:
        if code := reload_data(who):
            return code
    else:
        print("\n  ⬜ 데이터는 안 실었다 — 스키마와 시드까지다.")
        print("     uv run python launcher.py db-reset --yes --data   로 이어서 한다")

    print("\n✅ DB 가 선언 상태다.")
    print("   🚨 계정은 위 `admin-add` 를 사람이 쳐야 돌아온다 — 이 도구는 못 한다.")
    print("   ★ 확인:  uv run python launcher.py doctor --env   ·   launcher.py admin-list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
