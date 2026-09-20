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
   🔄 2026-09-20 (D-253) — 갈래가 **여덟**이 됐다(옮겨짐 · 정책 제외 · G2 · 오류 판 치움 · 다른 기기 · 유실 ·
      질의 필터 · 기기 칸 이전). 가르는 일은 `collect/missing.py` 가 하고 inventory 도 같은 것을 쓴다.
      🔴 는 그중 **이 기기가 받았다고 적혔는데 없는 것**(`lost`) 하나다.
   🔴 는 **이 기기에서 답할 수 있는 것**만이다 — 해시 불일치 · 원장에 없는 파일 ·
   내용이 갈린 중복 · 미등록 source_id.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePath
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

from collect import missing as missing_mod  # noqa: E402 — 결손 가르기의 정본 (D-253)
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


#: 휘발 값이 박힌 원천의 **폴더 이름**. 🚨 `store.VOLATILE` 은 소스 id 키인데
#:    원장 경로는 폴더 이름이라 축이 다르다 — 여기서 한 번만 옮긴다 (D-99 의 대가).
_VOLATILE_DIRS = {"mfds_press", "mfds_hf_board"}


def _source_of(path_str: str) -> str:
    """`data\\raw\\mfds_hf_board\\x.html` → `mfds_hf_board`. 🚨 폴더 이름이지 소스 id 가 아니다."""
    parts = PurePath(path_str.replace("\\", "/")).parts
    return parts[2] if len(parts) > 2 else "?"


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


def _report_missing(rows: list[dict[str, Any]], n: int) -> int:
    """원장에 있고 디스크에 없는 것을 **왜 없는지**로 가른다 (D-253 · `collect/missing.py`). 돌려주는 값은 🔴 개수.

    🔄 2026-09-20 — ⛔ 종전에는 ㄱ(G2)·ㄴ(다른 클론)·ㄷ(질의 필터) 셋을 찍고 사람에게 넘겼다.
       실측 `law_go_kr` 36개는 셋 다 아니었고(서식 34 · 옮긴 흔적 2), 「재수집하면 닫힌다」는 **틀린 안내**였다.
    ★ 이제 정상으로 설명되는 것은 한 줄로 접고, **사람이 볼 것**만 목록을 편다.
    🚨 🔴 는 `lost`(이 기기가 받았다고 적혔는데 없다) 하나다 — 이 기기에서 답할 수 있는 결손만 종료코드에 넣는다.
       `legacy`·`query` 는 🟡 — 원장으로 못 가르는 것을 🔴 로 세면 다른 클론에서 늘 울어 아무도 안 본다.
    """
    got = missing_mod.classify(rows)
    count = missing_mod.tally(got)
    eyes = missing_mod.needs_eyes(got)
    head = "🟡" if eyes else "✅"
    print(f"  {head} 원장에 있고 디스크에 없는 것 {n:,}개 — 사람이 볼 것 **{eyes:,}개**")
    for reason, (mark, normal, why) in missing_mod.REASONS.items():
        if not count.get(reason):
            continue
        print(f"     {mark} {reason:9} {count[reason]:>6,}  {why}")
        if normal:
            continue
        # 정상이 아닌 것만 원천별로 편다 — 🚨 원천마다 셋까지만 (전량은 화면을 덮는다)
        by_sid: collections.Counter[str] = collections.Counter()
        shown: collections.Counter[str] = collections.Counter()
        index = {str(r.get("path") or "").replace("\\", "/"): r for r in rows}
        for p, (rsn, extra) in sorted(got.items()):
            if rsn != reason:
                continue
            sid = str(index.get(p, {}).get("source_id") or "<미상>")
            by_sid[sid] += 1
            if shown[sid] < 3:
                shown[sid] += 1
                print(f"          {p}" + (f"  ({extra})" if extra else ""))
        print(f"        원천별 — {dict(by_sid.most_common())}")
    if count.get("legacy"):
        print("     🚨 `legacy` — 기기 칸(D-250) 이전 줄이라 원장만으로는 못 가른다.")
        print("        이 기기에서 쓸 원천이면 다시 받는다 — 같으면 수집기가 스킵한다(규약 2).")
        print(
            "        ⛔ 안 돌아오면: 수집기가 안 받게 바뀐 것이다 → 그 수집기에 `NOT_KEPT` 를 선언한다."
        )
    if count.get("query"):
        print("     🚨 `query` — `collect law_go_kr --dry-run` 의 「질의별 실측」 합집합과 맞대야")
        print("        유실인지 필터인지 갈린다 (D-153). 필터가 뺀 것이면 **돌아오면 안 된다.**")
    if count.get("lost"):
        print("     🔴 `lost` — 되돌리려면 이 기기에서 다시 받는다. 일부러 지운 것이면")
        print(
            "        그 이유를 수집기 `NOT_KEPT` 에 선언한다 — 원장 줄은 지우지 않는다(참인 이력이다)."
        )
    return count.get("lost", 0)


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
            # 🔄 **2026-09-08 — 원천별로 묶는다.** 예전에는 갈린 것을 전부 뿌렸다.
            #    실측에서 56개 중 53개가 `mfds_sanctions` 페이지였고, **화면 54줄이 그것으로 덮여**
            #    정작 봐야 할 셋(146B 오류 응답 · law_002011 · page_0001 3판)이 묻혔다.
            # 🚨 그리고 안내가 틀렸다 — 한 원천에서 페이지가 **한꺼번에** 갈리는 것은
            #    「원천이 고쳤다」가 아니라 **offset 페이징에서 경계가 밀린 것**일 수 있다 (D-149).
            #    레코드 하나만 들어와도 그 뒤 전 페이지의 바이트가 달라진다.
            # ★ doctor 는 어느 쪽인지 모른다 — **모른다고 말하고 갈래를 보여 준다.**
            by_src: collections.Counter[str] = collections.Counter()
            for k in split:
                by_src[(by_path.get(k) or [{}])[0].get("source_id") or "<미상>"] += 1
            print(f"     원천별 — {dict(by_src.most_common())}")
            bulk = [sid for sid, n in by_src.items() if n >= 5]
            if bulk:
                print(f"     🚨 **한꺼번에 갈린 원천 {bulk}** — 개별 파일이 바뀐 것이 아니라")
                print("        **offset 페이징에서 경계가 밀린 것**일 수 있다 (D-149).")
                print("        레코드 하나만 들어와도 그 뒤 전 페이지의 바이트가 달라진다.")
                print("        🚨 이 원천에서는 **파일 해시로 판을 비교하는 것이 의미가 약하다.**")
            # 🔴 **크기가 급감한 판을 따로 잡는다** (2026-09-08 · D-147 을 자동으로 잡는 자리).
            #    ⛔ `mfds_hf_individual/page_0001.json` 이 51,636 B → **146 B** 로 바뀌었는데
            #       그냥 목록에 섞여 지나갔다. 그 146바이트는 `ERROR-503` **오류 본문**이었다.
            #    ★ 급감은 「원천이 내용을 고쳤다」가 아니라 **오류 응답이 데이터로 저장된 것**의
            #      전형적 모양이다. 사람이 54줄에서 그걸 찾아내길 기대하면 안 된다.
            # 🚨 **디스크를 본다 — 원장만 보면 영영 운다.**
            #    ⛔ 첫 판은 원장 줄만 보고 🔴 를 냈다. 그런데 그 146바이트 파일은 **이미 지웠고**
            #       원장 줄은 append 전용이라 남는다 — **고칠 것이 없는데 매번 🔴 가 뜬다.**
            #       늘 우는 지표는 사람이 안 보게 만든다 (오늘 D-142 (다)에서 같은 실수를 했다).
            #    ★ 그래서 **지금 디스크에 그 나쁜 판이 살아 있을 때만** 🔴 다.
            #      지워졌으면 이력이고, 그건 위의 「원장에 있고 디스크에 없는 것」이 이미 센다.
            live: list[tuple[str, int, int]] = []
            past: list[str] = []
            for k, v in split.items():
                ordered = sorted(v, key=lambda y: y.get("fetched_at", ""))
                # 🚨 `strict=False` 다 — `ordered[1:]` 은 **한 칸 짧은 것이 설계**다.
                #    이웃한 두 판을 맞대는 것이라 길이가 같으면 오히려 틀린다.
                for a, b in zip(ordered, ordered[1:], strict=False):
                    pa, pb = a.get("bytes") or 0, b.get("bytes") or 0
                    if not (
                        pa >= missing_mod.COLLAPSE_MIN_BYTES
                        and pb < pa * missing_mod.COLLAPSE_RATIO
                    ):
                        continue
                    disk = _disk_path(k)
                    if disk.exists() and abs(disk.stat().st_size - pb) <= 2:
                        live.append((k, pa, pb))
                    else:
                        past.append(k)
            if live:
                red += len(live)
                print(f"\n  🔴 **크기가 급감한 판이 지금 디스크에 있다 {len(live)}개**")
                print(
                    "     원천이 HTTP 200 에 오류를 실어 주면 수집기가 그것을 데이터로 저장한다 (D-147)."
                )
                for k, pa, pb in live[:8]:
                    print(f"       {k}  {pa:,} B → **{pb:,} B** ({pb * 100 // max(pa, 1)}%)")
                print("     고치는 법 — 그 파일을 열어 본다. 오류 본문이면 지우고 다시 받는다.")
                print(
                    "     🚨 원장 줄은 지우지 않는다 — 「그때 원천이 오류를 줬다」는 참인 사실이다."
                )
            if past:
                print(
                    f"\n  🟡 크기가 급감한 판이 **원장에만** 있다 {len(past)}개 — 이미 치웠다는 뜻이다"
                )
                for k in past[:4]:
                    print(f"       {k}")

            print("\n     🚨 무엇이 바뀌었는지는 여전히 사람이 원장에 적는다 (D-54).")
            print("     아래는 **원천마다 두 개까지만** 보인다 — 전량은 원장을 본다.")
            shown: collections.Counter[str] = collections.Counter()
            for k, v in split.items():
                sid = (by_path.get(k) or [{}])[0].get("source_id") or "<미상>"
                shown[sid] += 1
                if shown[sid] > 2:
                    continue
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
    stale: list[str] = []
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
            continue
        # 🔴 **세 번째 축** — 「있다」도 「훼손 안 됐다」도 아닌, **「팀 최신판인가」** (D-177).
        #    ⛔ 바로 위 검사는 `got not in {기록된 sha 전부}` 라 「원본이 훼손됐는가」(규약 2 · D-92)를
        #       묻는다. 그건 이 기기 파일이 **09-07 판**이어도 통과한다 — 그 판도 원장에 있으니까.
        #    🚨 실측 2026-09-10 — `mfds_hf_ingredient_board` 672개 중 **662개**가
        #       팀 최신 기록과 다른데 `--hash` 는 **0 을 냈다.** 묻는 것이 달라서다.
        latest = max(entries, key=lambda e: str(e.get("fetched_at") or ""))
        if got != latest.get("sha256"):
            stale.append(path_str)

    present = len(by_path) - len(missing)
    print(f"\n  이 기기에 있는 파일 {present:,} / {len(by_path):,}")

    if missing:
        red += _report_missing(rows, len(missing))

    if verify_hash:
        print(f"\n  해시를 다시 계산한 파일 {checked:,}개")
        if stale:
            groups: collections.Counter = collections.Counter(_source_of(x) for x in stale)
            print(
                f"  🟡 **팀 최신판이 아닌 파일 {len(stale):,}개** — "
                "「있다」와 「최신이다」는 다른 축이다 (D-177)"
            )
            print(f"     원천별 — {dict(groups.most_common())}")
            print(
                "     ★ 위 🔴(훼손)과 **다르다.** 원본은 멀쩡하고, 다른 기기가 그 뒤에 더 받았다는 뜻이다."
            )
            # 🚨 휘발 값이 박힌 원천은 **원문 해시로 못 가른다** (D-168).
            #    실측 — `mfds_press` 105건은 갈린 것이 `jsessionid` 뿐이었다.
            #    여기서 「낡음」으로 세지만 실제로는 같을 수 있다. 오탐으로 시작한 검사는 곧 꺼진다.
            vol = sorted(g for g in groups if g.split("_pdf")[0] in _VOLATILE_DIRS)
            if vol:
                print(
                    f"     🚨 다만 {', '.join(vol)} 는 **휘발 값이 박힌 원천**이라"
                    " 원문 해시로는 못 가른다 (D-168) —"
                )
                print(
                    "        이 수에 「토큰만 갈린 것」이 섞여 있다."
                    " 재수집해 「동일 — 스킵」이 나오면 같은 것이다."
                )
            print("     🚨 이 기기에서 그 원천을 추출하면 **팀이 보는 것과 다른 수가 나온다** —")
            print("        실측: 승인문구 178 vs 177 이 골든셋 1,910 과 1,915 를 갈랐다 (D-176).")
            print(
                "     → 이 기기에서 다시 받는다: uv run python launcher.py collect <소스id> --use U1"
            )
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


# ══════════════════════════════════════════════════════════════════════
#  🆕 --env — 팀원이 첫날 여는 검사 (2026-09-12 밤 · D-51 · D-208)
# ══════════════════════════════════════════════════════════════════════

#: 🚨 이 검사들은 **데이터가 없어도 돈다.** 새 클론에서 제일 먼저 부를 자리다.
#:    ⛔ 종전에는 「환경 진단」(메뉴 3)이 원장↔디스크 대조 **하나만** 봤다. 팀원이 초록을
#:       보고도 파이썬 버전·git 신원·DB 리비전은 **아무도 안 본 상태**였다 (D-170).


def _git(*args: str) -> str:
    """git 한 줄. 🚨 실패는 빈 문자열이다 — git 이 없어도 진단이 죽지 않는다."""
    try:
        out = subprocess.run(  # noqa: S603
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def _sanction_signatures(cur) -> tuple[int, int] | None:  # noqa: ANN001
    """`sanction_rule` 의 (전체, 서명 안 끝난 것). 표가 없으면 `None`.

    🔴 **왜 doctor 인가** — 기기마다 답이 다르다 (D-89). `data/` 는 미커밋이고(D-19)
       적재 상태가 클론마다 갈린다. pytest 로 옮길 수 없는 검사다.
    """
    cur.execute("SELECT to_regclass('sanction_rule')")
    if not cur.fetchone()[0]:
        return None
    cur.execute(
        "SELECT count(*), count(*) FILTER "
        "(WHERE verified_by IS NULL OR reviewed_by IS NULL) FROM sanction_rule"
    )
    total, pending = cur.fetchone()
    return int(total), int(pending)


def _report_sanction(stat: tuple[int, int] | None) -> None:
    """🔴 **서명 안 끝난 제재 행은 `v_risk_lookup` 에 안 보인다** (0013 · D-66 · D-170).

    ⛔ 🔴 로 세지 않는다 — 적재하고 나서 서명하는 것이 정상 순서이고, 그 사이를 실패로
       찍으면 이 검사는 곧 꺼진다 (D-170 이 경계한 반대 방향). 대신 **왜 문제인지**를 적는다.
    ⬜ 여기서 안 보는 것 — **서명자가 누구여야 하는가** (사람 몫 · `registry_review.yaml`).
    """
    if stat is None:
        print("⬜ sanction_rule 표가 없다 — 마이그레이션 전이다 (D-188).")
        return
    total, pending = stat
    if total == 0:
        print("⬜ sanction_rule 0행 — 2인 확인을 셀 것이 아직 없다. 적재기가 붙으면 여기가 센다.")
        print("   🚨 **0행을 「초록」으로 읽지 않는다** — 셀 것이 없는 것과 다 맞는 것은 다르다.")
        return
    if pending:
        print(f"🟡 sanction_rule {total:,}행 중 **2인 확인 대기 {pending:,}행** (D-66).")
        print("   🔴 이 행들은 `v_risk_lookup` 에 **안 보인다** — 위험도 하한이 안 잡히고,")
        print("      하한이 없으면 계약이 최종 위험도를 거부한다 (D-09 래칫). 판정이 멈춘다.")
        print("   ★ 사람만 채운다 — verified_by · reviewed_by 는 서로 달라야 한다.")
        return
    print(f"✅ sanction_rule {total:,}행 · 2인 확인 전량 완료")


def check_env() -> int:
    """환경·신원·DB 를 본다. 🔴 반환값은 **빨간 건수**다.

    ⬜ 여기서 안 보는 것 — uv.lock 동기화 · 모델 캐시 · GPU. 아직 자리표시자다 (D-188).
    """
    red = 0

    # ① 파이썬 — 스택 핀 (D-87)
    want = (
        (ROOT / ".python-version").read_text(encoding="utf-8").strip()
        if (ROOT / ".python-version").exists()
        else ""
    )
    now = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if want and not now.startswith(want.rsplit(".", 1)[0]):
        print(f"🔴 파이썬 {now} — 핀은 {want} 다 (D-87).")
        print("   고치는 법 — uv python install && uv sync --frozen")
        red += 1
    else:
        print(f"✅ 파이썬 {now}" + (f" (핀 {want})" if want else ""))

    # ② git 신원 — 🔴 없으면 커밋이 전부 같은 이름으로 들어온다
    name, email = _git("config", "user.name"), _git("config", "user.email")
    if not name or not email:
        print("🔴 git 신원이 없다 — 커밋이 기기 계정 이름으로 들어간다.")
        print("   ⛔ 실제로 커밋 266건 중 1건이 그렇게 남았다. 5인이 붙으면 저자를 못 가른다.")
        print('   고치는 법 — git config user.name "이름"; git config user.email "메일"')
        red += 1
    else:
        print(f"✅ git 신원 {name} <{email}>")

    # ③ .env — 없으면 키가 하나도 안 읽힌다
    if not (ROOT / ".env").exists():
        print("🟡 .env 가 없다 — .env.example 을 복사한다 (setup 이 해 준다).")
    else:
        print("✅ .env 있음  (값은 launcher.py keys 로 지문만 본다)")

    # ④ DB — 붙는가 · 리비전이 최신인가 · pgvector 가 있는가
    try:
        import psycopg  # noqa: PLC0415

        from app.settings import dsn  # noqa: PLC0415

        with psycopg.connect(dsn(), connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            has_vec = cur.fetchone() is not None
            cur.execute("SELECT to_regclass('alembic_version')")
            rev = None
            if cur.fetchone()[0]:
                cur.execute("SELECT version_num FROM alembic_version")
                row = cur.fetchone()
                rev = row[0] if row else None
            sanction = _sanction_signatures(cur)
        print("✅ DB 접속" + (f" · alembic {rev}" if rev else " · 🔴 alembic 미적용"))
        if not has_vec:
            print("🔴 pgvector 확장이 없다 — CREATE EXTENSION vector (db-up 이 해 준다).")
            red += 1
        if not rev:
            print("🔴 테이블이 없다 — uv run python launcher.py migrate 를 먼저 돌린다.")
            red += 1
        _report_sanction(sanction)
    except Exception as e:  # noqa: BLE001
        print(f"🟡 DB 에 못 붙었다 ({type(e).__name__}) — launcher.py db-up 을 먼저 돌린다.")

    # ⑤ 화면 골격 — 팀원이 첫날 여는 자리
    for rel in ("app/templates/base.html", "app/static/base.css"):
        print(("✅ " if (ROOT / rel).exists() else "🔴 없다 — ") + rel)
        red += 0 if (ROOT / rel).exists() else 1

    return red


def main() -> int:
    ap = argparse.ArgumentParser(description="CopyLane 진단 (D-51 · D-89)")
    ap.add_argument("--data", action="store_true", help="원장 ↔ 디스크 대조")
    ap.add_argument("--hash", action="store_true", help="--data 에서 전 파일 해시를 재계산")
    ap.add_argument("--env", action="store_true", help="환경·git 신원·DB — 데이터 없이 돈다")
    args = ap.parse_args()

    if args.env:
        print("── 환경 진단 ───────────────────────────────────")
        red = check_env()
        print("────────────────────────────────────────────────")
        if red:
            print(f"🔴 {red}건 — 위 「고치는 법」을 먼저 읽어라.")
            return 1
        print("🔴 없음. ⬜ 다만 uv.lock 동기화·모델 캐시·GPU 는 **아직 안 본다** (D-188).")
        return 0 if not args.data else 0

    if not args.data:
        print("doctor: 지금 도는 것은 --data · --env 다. 나머지는 docstring 의 자리표시자다.")
        print("  uv run python scripts/doctor.py --env    ← 새 클론에서 먼저")
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
    if args.hash:
        print("🔴 없음. 🟡 가 있으면 기기 사정인지 사람이 확인한다.")
        return 0
    # 🔴 **해시를 안 봤으면 「없음」이라 말하지 않는다** (2026-09-10 · D-177).
    #    ⛔ 종전에는 마지막 줄이 무조건 「🔴 없음」이었다. 실측 —
    #       `mfds_hf_ingredient_board` 672개 중 **662개가 팀 최신판이 아닌 상태에서**
    #       이 줄이 「🔴 없음」을 찍었다. 「있다」와 「최신이다」는 다른 축인데
    #       마지막 줄이 그 구분을 지우고 안심시켰다.
    print("⬜ 🔴 없음 — **다만 축 둘만 봤다.**")
    print("   ① 있는가 ✅   ② 훼손됐는가 ⬜   ③ **팀 최신판인가** ⬜   (D-177)")
    print("   → uv run python scripts/doctor.py --data --hash   ← ②③ 을 함께 본다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
