"""preprocess/stage.py — **전처리 단계의 산출물을 물질화하고, 두 판을 맞대 본다** (D-143).

  uv run python -m preprocess.ftc_extract --stage      # 이번 판을 적고, 지난 판과 비교한다

★ **왜 저장하는가 — 비교할 대상이 없으면 손실이 안 보인다.**

  2026-09-08 에 `NOISE` 하나가 **643 → 619 문구**를 삼키고 있었는데 아무도 몰랐다.
  마스킹된 본문이 **어디에도 안 적히기 때문**이다. 한 번의 메모리 통과로 세고 버렸다.

🔴 **차이의 원인이 둘이다 — 이걸 못 가르면 지표가 거짓말을 한다.**

     ① 원천이 늘었다   (식약처 게시판 650 → 655 · ftc 는 2026년 건이 계속 들어온다)
     ② 규칙을 고쳤다

  「627 → 641」만 보면 규칙이 좋아진 건지 문서가 들어온 건지 알 수 없다.
  그래서 **문서 단위로 맞대고**, 양쪽에 다 있는 문서의 차이만 **규칙 탓**으로 센다.

🚨 **판이 섞이면 멈춘다.** 규칙을 고친 뒤 일부만 재생성되면 절반은 옛 마스킹,
   절반은 새 마스킹인 코퍼스가 **겉으로 멀쩡하게** 만들어진다 — 조용한 실패의 교과서다.
   그래서 줄마다 규칙 판(`rule`)과 원천 판(`src`)을 박는다.

🔴 **`data/` 아래에만 쓴다 — 배포되지 않는다** (D-71).
   마스킹을 지난 것만 담지만, 그래도 배포면에 두지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

#: 규칙을 정의하는 모듈들. 🚨 하나라도 바뀌면 판이 달라진다.
#:    이 목록에 빠진 모듈이 산출물을 바꾸면 **판이 같은데 결과가 다른** 상태가 된다.
RULE_FILES = (
    "preprocess/mask.py",
    "preprocess/text.py",
    "preprocess/ftc_triage.py",
    "preprocess/ftc_extract.py",
)


def rule_hash() -> str:
    """규칙 판. 규칙 모듈들의 내용 해시."""
    h = hashlib.sha256()
    for name in RULE_FILES:
        h.update(pathlib.Path(name).read_bytes())
    return h.hexdigest()[:12]


def src_hash(data: bytes) -> str:
    """원천 판. 그 문서 원본의 해시 — 원천이 조용히 바뀌면 여기서 드러난다."""
    return hashlib.sha256(data).hexdigest()[:12]


def save(path: pathlib.Path, rows: list[dict]) -> None:
    """줄 하나에 문서 하나. 🚨 `seq` 순으로 적는다 — 순서가 흔들리면 diff 가 무의미하다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rule = rule_hash()
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(rows, key=lambda x: str(x["seq"])):
            f.write(json.dumps({**r, "rule": rule}, ensure_ascii=False) + "\n")


def load(path: pathlib.Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[str(r["seq"])] = r
    return out


#: 🚨 **산출물이 같아도 본문은 바뀔 수 있다.** 2026-09-08 에 조사 먹힘을 고쳤더니
#:    `주문_마스킹` 이 63곳 바뀌었는데 `문구` 는 그대로여서 「내용바뀜 0」으로 보고됐다.
#:    산출물만 보면 **마스킹 규칙 변경이 통째로 안 보인다** — 축을 둘로 나눈다.
TEXT_FIELD = "주문_마스킹"


def compare(old: dict[str, dict], new: dict[str, dict], field: str = "문구") -> dict:
    """지난 판과 이번 판. **원천 탓과 규칙 탓을 갈라서** 센다.

    🚨 양쪽에 다 있는 문서만 「규칙 탓」이다. 새로 들어오거나 사라진 문서의 증감을
       규칙 효과로 세면, 원천이 늘어난 날 규칙이 좋아진 것처럼 보인다.
    """
    ko, kn = set(old), set(new)
    added, gone, both = kn - ko, ko - kn, ko & kn

    def n(d: dict, keys) -> int:
        return sum(len(d[k].get(field) or []) for k in keys)

    changed = [k for k in both if old[k].get(field) != new[k].get(field)]
    text_changed = [k for k in both if old[k].get(TEXT_FIELD) != new[k].get(TEXT_FIELD)]
    n_repl = sum(len(r.get("치환원장") or []) for r in new.values())
    rules = {r.get("rule") for r in new.values() if r.get("rule")}
    return {
        "문서_추가": len(added),
        "문서_사라짐": len(gone),
        "문서_내용바뀜": len(changed),
        "문서_본문바뀜": len(text_changed),
        "예시_본문바뀐문서": sorted(text_changed)[:8],
        "치환_이번판": n_repl,
        "치환_지난판": sum(len(r.get("치환원장") or []) for r in old.values()),
        "예시_바뀐문서": sorted(changed)[:8],
        f"{field}_지난판": n(old, ko),
        f"{field}_이번판": n(new, kn),
        f"{field}_원천탓": n(new, added) - n(old, gone),
        f"{field}_규칙탓": n(new, both) - n(old, both),
        "규칙판_지난": sorted({r.get("rule") for r in old.values() if r.get("rule")}),
        "규칙판_이번": sorted(rules),
        "🚨판섞임": len(rules) > 1,
    }


def report(c: dict, field: str = "문구") -> None:
    print("  📦 지난 판과 비교 (D-143)")
    prev, now = c["규칙판_지난"], c["규칙판_이번"]
    if not prev:
        print("    지난 판이 없다 — 이번이 첫 물질화다")
    else:
        same = prev == now
        print(
            f"    규칙 판  {','.join(prev)} → {','.join(now)}  {'(같다)' if same else '🔄 바뀌었다'}"
        )
    if c["🚨판섞임"]:
        print("    🚨 **판이 섞였다** — 규칙을 고친 뒤 일부만 재생성됐다. 전량 재생성할 것")
    print(
        f"    문서   추가 {c['문서_추가']:+,} · 사라짐 -{c['문서_사라짐']:,}"
        f" · 산출바뀜 {c['문서_내용바뀜']:,} · **본문바뀜 {c['문서_본문바뀜']:,}**"
    )
    if c["문서_본문바뀜"] and not c["문서_내용바뀜"]:
        print("    🚨 **산출물은 같은데 본문이 바뀌었다** — 마스킹 규칙이 움직였다는 뜻이다")
        print(f"       예: {', '.join(c['예시_본문바뀐문서'])}")
    print(f"    치환   {c['치환_지난판']:,} → {c['치환_이번판']:,}건 (치환 원장 · D-144)")
    print(f"    {field}   {c[f'{field}_지난판']:,} → {c[f'{field}_이번판']:,}")
    print(f"      ├ 원천 탓 {c[f'{field}_원천탓']:+,}   (문서가 늘거나 줄어서)")
    print(f"      └ 규칙 탓 {c[f'{field}_규칙탓']:+,}   ← **이쪽이 우리가 한 일이다**")
    if c["예시_바뀐문서"]:
        print(f"    바뀐 문서 예: {', '.join(c['예시_바뀐문서'])}")
