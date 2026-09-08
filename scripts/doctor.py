"""doctor.py — 환경·거버넌스 진단 (D-51 · D-89).

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
  18. manifest.jsonl 의 모든 source_id 가 data_sources.yaml 에 존재하는가   ← `--data` 로 구현
  19. raw/ 하위 파일이 derived/ 없이 방치돼 있지 않은가 (전처리 미실행 감지)

TODO: 1~17·19 는 아직 자리표시자다. 지금 도는 것은 `--data` 뿐이다.
      🚨 「TODO(W1)」로 적혀 있던 것을 고쳤다 — W1~W10 은 폐기된 표기다 (D-62).
         죽은 표를 가리키는 TODO 는 다음 사람이 일정표를 찾다가 시간을 쓴다.

────────────────────────────────────────────────────────────────
`--data` — 원장과 디스크를 대조한다 (2026-09-06)

🚨 왜 doctor 인가 — **기기마다 답이 다른 검사**이기 때문이다 (D-89).
   `data/` 는 커밋되지 않고(D-19) `manifest.jsonl` 만 커밋된다. 그래서 원장은 팀 공용,
   파일은 기기 사유다. 이 둘이 어긋나는 방식이 기기마다 다르다 — pytest 로 옮길 수 없다.

🚨 무엇이 이 검사를 만들게 했나 (2026-09-06 전수조사) —
   ① 원장 레코드 9,858 인데 고유 path 는 8,753 이었다. 같은 파일에 줄이 두 번 붙는다.
      두 클론이 같은 것을 각자 받으면 그렇게 된다. **원장 줄 수를 건수로 읽으면 틀린다** (D-54).
   ② `law_002011_20250121.xml` 이 두 기기에서 **바이트가 달랐다** (70,794 / 70,789).
      같은 ID·같은 시행일·같은 URL 인데 5바이트 다르다. 규약 2 는 「내용이 다른데 같은
      이름이면 거부」인데, 클론 B 는 그 파일이 없어서 검사에 걸리지 않고 저장했다.
      🚨 이건 클론 A 가 다음 수집에서 `StoreError` 로 **멈춘다**는 뜻이기도 하다.
   손으로 찾았다. 손으로 찾은 것은 다음에 또 손으로 찾게 된다.

🚨 「파일이 없다」를 무조건 결손으로 보지 않는다 —
   ㄱ. G2 소스는 사실을 뽑은 뒤 원본을 **지우는 것이 규칙**이다 (D-17 · `drop_raw_for_g2`).
   ㄴ. 다른 클론에서 받은 것은 이 기기에 없는 것이 정상이다 (D-19).
   그래서 결손은 🔴 가 아니라 🟡 로 찍고, 어느 쪽인지 사람이 보게 한다.
   🔴 는 **이 기기에서 답할 수 있는 것**만이다 — 해시 불일치 · 원장에 없는 파일 ·
   내용이 갈린 중복 · 미등록 source_id.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.jsonl"
RAW = ROOT / "data" / "raw"

# 🚨 `python scripts/doctor.py` 로 부르면 sys.path 에 들어가는 것은 **scripts/** 다.
#    저장소 뿌리가 아니라서 `from collect import registry` 가 실패한다.
#    scripts/ 에 `__init__.py` 를 두어 `-m` 으로 부르게 하는 방법도 있지만,
#    그러면 다른 스크립트의 호출법까지 같이 바뀐다. 여기서만 흡수한다.
# 🔄 **2026-09-08 — 「들어 있나」가 아니라 「맨 앞인가」를 본다.**
#    ⛔ 첫 판은 `if str(ROOT) not in sys.path` 였다. `PYTHONPATH=.` 로 부르면
#       ROOT 가 **이미 들어 있지만 `scripts/` 뒤**라서 가드가 통과되고,
#       `from collect import registry` 가 `scripts/collect.py` 를 집어 죽었다.
#    ★ 막으려던 것이 「가려짐」인데 검사한 것은 「존재」였다 — 같은 종류의 실수를
#      오늘 마스킹에서도 했다(계수기가 0 인 것과 대상이 사라진 것은 다르다).
if sys.path and sys.path[0] != str(ROOT):
    sys.path.insert(0, str(ROOT))

from collect import registry  # noqa: E402 — 위 sys.path 조정 뒤여야 한다


def _rows() -> list[dict[str, Any]]:
    """원장을 읽는다. 🚨 깨진 줄에서 멈추지 않는다 — 몇 번째 줄인지 찍고 넘어간다.

    append 전용 파일이라 중간에 한 줄이 깨져도 나머지는 멀쩡하다.
    한 줄 때문에 진단 전체를 못 돌리면 진단이 아니다.
    """
    out: list[dict[str, Any]] = []
    broken = 0
    for i, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            broken += 1
            print(f"  🔴 원장 {i}행이 JSON 이 아니다 — 그 줄만 손으로 봐라")
    if broken:
        print(f"  🔴 깨진 줄 {broken}개를 건너뛰고 검사했다. 아래 숫자는 그만큼 적다.")
    return out


def _disk_path(recorded: str) -> Path:
    """원장의 path 를 이 기기의 경로로 바꾼다.

    🚨 원장에는 기록한 기기의 구분자가 그대로 남는다 (`data\\raw\\...`).
       윈도우에서 쓴 줄을 리눅스에서 읽는 일이 실제로 있으므로 여기서 흡수한다.
    """
    return ROOT / Path(recorded.replace("\\", "/"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_data(*, verify_hash: bool) -> int:
    """원장 ↔ 디스크 대조. 돌려주는 값은 🔴 의 개수다."""
    if not MANIFEST.exists():
        print(f"  🟡 원장이 없다 — {MANIFEST}")
        print("     아직 아무것도 수집하지 않은 클론이다. 이상이 아니다.")
        return 0

    rows = _rows()
    by_path: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_path[r.get("path") or "<path 없음>"].append(r)

    red = 0

    # ── ① 원장 자체 ────────────────────────────────────────
    print(f"\n  원장 {len(rows):,}행 · 고유 path {len(by_path):,}개")
    dups = {k: v for k, v in by_path.items() if len(v) > 1}
    if dups:
        split = {k: v for k, v in dups.items() if len({x.get("sha256") for x in v}) > 1}
        print(f"  🟡 같은 path 에 줄이 두 번 이상 붙은 것 {len(dups):,}개")
        print("     두 클론이 같은 파일을 각자 받으면 이렇게 된다. 파일은 하나다.")
        print("     🚨 원장 줄 수를 건수로 쓰지 마라 — 고유 path 를 세라 (D-54).")
        for k, v in list(dups.items())[:3]:
            days = " / ".join(sorted(x.get("fetched_at", "")[:10] for x in v))
            print(f"       {k}  ({days})")
        if len(dups) > 3:
            print(f"       … 외 {len(dups) - 3:,}개")
        if split:
            # 🚨 2026-09-06 이전에는 여기서 🔴 를 세고 종료코드 1 을 냈다. 내린 이유는
            #    **수집기가 이 상황을 다루게 됐기 때문**이다 — `store.save_raw` 가
            #    같은 이름·다른 내용을 만나면 새 판(`__c<수집일>`)으로 저장한다.
            #    더는 팀원의 수집이 멈추지 않으므로 이것은 **이력**이지 고장이 아니다.
            # 🚨 검사를 약하게 만든 것이 아니다 — 「디스크가 어느 기록과도 안 맞는다」는
            #    아래 `--hash` 가 여전히 🔴 로 잡는다. 그쪽이 진짜 무결성 검사다.
            #    고칠 수 없는 것을 매번 🔴 로 띄우면 사람이 🔴 를 안 보게 된다.
            print(f"\n  🟡 그중 **내용이 갈린 것** {len(split):,}개 — 같은 이름, 다른 바이트")
            print("     원천이 같은 이름으로 다른 것을 준 자리다. 지금은 수집기가 새 판으로")
            print("     저장하므로 수집이 멈추지 않는다 (`store.EDITION_MARK`).")
            print("     🚨 무엇이 바뀌었는지는 여전히 사람이 원장에 적는다 (D-54).")
            for k, v in split.items():
                print(f"       {k}")
                for x in sorted(v, key=lambda y: y.get("fetched_at", "")):
                    stamp = x.get("fetched_at", "")[:19]
                    print(
                        f"         {stamp}  {x.get('bytes', 0):>10,} B  "
                        f"sha {str(x.get('sha256'))[:16]}"
                    )
            print("     🚨 하나만 확인해라 — **호출마다 다른 것**은 이 얘기가 아니다.")
            print("        재호출해서 「동일 — 스킵」이 나오면 원천이 고친 것이고,")
            print("        또 갈리면 응답이 비결정적인 것이라 판으로 다룰 일이 아니다.")

    # ── ② 디스크 대조 ──────────────────────────────────────
    missing: list[str] = []
    mismatched: list[str] = []
    checked = 0
    for path_str, entries in by_path.items():
        disk = _disk_path(path_str)
        if not disk.exists():
            missing.append(path_str)
            continue
        if not verify_hash:
            continue
        got = _sha256(disk)
        checked += 1
        if got not in {e.get("sha256") for e in entries}:
            mismatched.append(path_str)

    present = len(by_path) - len(missing)
    print(f"\n  이 기기에 있는 파일 {present:,} / {len(by_path):,}")

    if missing:
        print(f"  🟡 원장에 있고 디스크에 없는 것 {len(missing):,}개")
        print("     🚨 두 가지가 섞여 있고, 하나는 정상이다 —")
        print("        ㄱ. G2 소스는 사실 추출 뒤 원본을 지우는 것이 규칙이다 (D-17)")
        print("        ㄴ. 다른 클론에서 받은 것은 여기 없는 것이 정상이다 (D-19)")
        # 🔄 **2026-09-08 — 「등급을 보고 판단한다」를 doctor 가 대신 한다.**
        #    사람에게 넘기면 아무도 안 본다. 실제로 73건이 그렇게 남아 있었다.
        #    ★ 등급을 적용하면 **설명 ㄱ이 배제되는 원천**이 드러나고, 거기는
        #      「정상일 수도 있다」가 아니라 **재수집으로만 닫힌다.**
        by_sid: collections.Counter[str] = collections.Counter()
        for path_str in missing:
            sid = by_path[path_str][0].get("source_id") or "<source_id 없음>"
            by_sid[sid] += 1
        g2, rest = [], []
        for sid, n in by_sid.most_common():
            try:
                grade = str(registry.spec(sid).get("grade", "?"))
            except Exception:  # noqa: BLE001 — 미등록 자체가 검사 결과다
                grade = "🔴 미등록"
            (g2 if grade.startswith("G2") else rest).append((sid, n, grade))
        if g2:
            print(
                f"     ✅ ㄱ 으로 설명되는 것 {sum(n for _, n, _ in g2):,}개 (G2 — 지우는 것이 규칙)"
            )
            for sid, n, grade in g2:
                print(f"       {sid:26} {n:>5,}  {grade}")
        if rest:
            print(
                f"     🚨 ㄱ 이 **배제되는** 것 {sum(n for _, n, _ in rest):,}개 — 설명이 ㄴ 하나뿐이다"
            )
            for sid, n, grade in rest:
                print(f"       {sid:26} {n:>5,}  {grade}")
            print("        ★ 「다른 클론에서 받았다」와 「유실됐다」는 원장으로 구분되지 않는다.")
            print(
                "          **이 기기에서 재수집하면 닫힌다** — 동일하면 수집기가 스킵한다(규약 2)."
            )
        # 🚨 디렉터리로 묶을 때 **문자열 앞자리로 세지 않는다.**
        #    `data/raw/mfds_press` 는 `data/raw/mfds_press_pdf` 의 앞자리이기도 해서
        #    startswith 로 세면 107개가 양쪽에 잡혀 합이 실제보다 커진다.
        #    2026-09-06 첫 판이 그렇게 나왔다 — 같은 날 `가처분`⊂`허가처분` 으로 겪은
        #    **부분문자열은 단위가 아니다**와 똑같은 실수를, 세는 쪽에서 한 번 더 했다.
        groups: collections.Counter[str] = collections.Counter()
        for path_str in missing:
            parts = Path(path_str.replace("\\", "/")).parts
            groups["/".join(parts[:3])] += 1
        for head, n in groups.most_common():
            print(f"       {head}/…  {n:,}개")

    if verify_hash:
        print(f"\n  해시를 다시 계산한 파일 {checked:,}개")
        if mismatched:
            red += len(mismatched)
            print(f"  🔴 원장과 해시가 다른 파일 {len(mismatched):,}개 — **원본이 바뀌었다**")
            print("     규약 2 의 전제가 깨진 자리다. 파일을 되돌리거나 재수집한다.")
            for path_str in mismatched[:20]:
                print(f"       {path_str}")
            if len(mismatched) > 20:
                print(f"       … 외 {len(mismatched) - 20:,}개")
    else:
        print("\n  ⬜ 해시는 건너뛰었다 — `--hash` 를 붙이면 전 파일을 다시 계산한다.")
        print("     🚨 해시를 안 보면 「내용이 조용히 바뀐 파일」은 못 잡는다.")

    # ── ③ 디스크에 있는데 원장에 없는 것 ───────────────────
    if RAW.exists():
        recorded = {_disk_path(p).resolve() for p in by_path}
        orphans = [p for p in RAW.rglob("*") if p.is_file() and p.resolve() not in recorded]
        orphans = [p for p in orphans if p.name != ".gitkeep"]
        if orphans:
            red += len(orphans)
            print(f"\n  🔴 디스크에 있는데 원장에 없는 파일 {len(orphans):,}개 — **출처 불명**")
            print("     🚨 raw 는 원장이 유일한 증언이다 (규약 3). 증언 없는 파일은")
            print("        어디서 왔는지·재배포해도 되는지 답할 수 없다 (D-71).")
            for p in orphans[:20]:
                print(f"       {p.relative_to(ROOT)}")
            if len(orphans) > 20:
                print(f"       … 외 {len(orphans) - 20:,}개")

    # ── ④ 원천별 요약 (게이트 18 겸) ───────────────────────
    uniq: collections.Counter[str] = collections.Counter()
    size: collections.Counter[str] = collections.Counter()
    on_disk: collections.Counter[str] = collections.Counter()
    for path_str, entries in by_path.items():
        sid = entries[0].get("source_id") or "<source_id 없음>"
        uniq[sid] += 1
        size[sid] += entries[0].get("bytes", 0)
        if _disk_path(path_str).exists():
            on_disk[sid] += 1

    print(f"\n  {'source_id':26}{'고유':>8}{'이 기기':>9}{'MB':>9}  등급")
    for sid, n in uniq.most_common():
        try:
            grade = registry.spec(sid).get("grade", "?")
        except Exception:  # noqa: BLE001 — 미등록 자체가 검사 결과다
            grade = "🔴 미등록"
            red += 1
        print(f"  {sid:26}{n:>8,}{on_disk[sid]:>9,}{size[sid] / 1048576:>9.1f}  {grade}")

    return red


def main() -> int:
    ap = argparse.ArgumentParser(description="CopyLane 진단 (D-51 · D-89)")
    ap.add_argument("--data", action="store_true", help="원장 ↔ 디스크 대조")
    ap.add_argument("--hash", action="store_true", help="--data 에서 전 파일 해시를 재계산")
    args = ap.parse_args()

    if not args.data:
        print("doctor: 지금 도는 것은 --data 뿐이다. 나머지는 docstring 의 자리표시자다.")
        print("  uv run python scripts/doctor.py --data [--hash]")
        return 0

    print("── 원장 ↔ 디스크 대조 ──────────────────────────")
    red = check_data(verify_hash=args.hash)
    print("\n────────────────────────────────────────────────")
    if red:
        # 🚨 🔴 만 종료코드에 반영한다. 🟡 는 기기 사정이라 실패가 아니다 —
        #    🟡 로 1 을 내면 다른 클론에서는 항상 실패해서 아무도 안 돌리게 된다.
        print(f"🔴 {red:,}건 — 위 「고치는 법」을 먼저 읽어라.")
        return 1
    print("🔴 없음. 🟡 가 있으면 기기 사정인지 사람이 확인한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
