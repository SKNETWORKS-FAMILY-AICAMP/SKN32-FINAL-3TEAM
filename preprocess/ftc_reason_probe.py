"""preprocess/ftc_reason_probe.py — 「이유」에 광고 문구가 인용돼 있는가를 **세기만** 한다.

  uv run python -m preprocess.ftc_reason_probe
  uv run python -m preprocess.ftc_reason_probe --peek 30   # 마스킹 지난 문구를 화면에만
  uv run python -m preprocess.ftc_reason_probe --docs 30   # 문서 통째로 (문서 기준 회수율)
  uv run python -m preprocess.ftc_reason_probe --dump      # 전수를 파생물로 (D-68 확인 필요)

🔴 **이 파일은 판정이 아니라 재료다** (D-232 ⬜). `preprocess/ftc_extract.py` 의
   `phrases_in(raw["주문"])` 이 **주문만 본다**는 것이 D-232 에서 드러났고, 회수안 (A)의
   상한(283 → 854)은 **「이유에 문구가 인용돼 있다」를 전제한 수**다. 그 전제를 아무도 안 쟀다.
   이 탐침이 그 수를 낸다 — 그 수가 작으면 (A)의 순위가 (B) 아래로 내려간다.

🔄 **2026-09-17 5판 — `--dump` 로 파생물을 낸다. 표본 30개로 판정하는 것을 끝낸다.**
   ⛔ 4판까지는 화면 출력뿐이라 **표본이 30개에 묶여 있었다.** 그 30개로 오늘 두 번 틀렸다 —
      2판은 한 사건에 몰렸고, 3판은 문서의 첫 문구만 봤다. 표본 설계를 고칠 때마다 수가 바뀌었다.
   ★ `--dump` — **마스킹을 지난** 이유·주문 문구를 `data/derived/ftc_reason_sample.jsonl` 로
      낸다. 파일 하나면 전수를 분류할 수 있고, 표본 편향이라는 실패 방식 자체가 사라진다.
   🚨 **마스킹 전 원문은 나가지 않는다** (D-17 · D-165). 나가는 것은 `apply_policy` 를 지난
      문자열뿐이고, 그것은 `ftc_stage.jsonl`·`ftc_layer1_phrases.json` 이 이미 하는 일과 같다.
   🔴 **그래도 제3자 상호는 남는다** — `anchor_ftc` 는 피심인만 캔다. 3판 표본에서 30개 중
      4개(13%)가 「알바천국」·「일산자이」 같은 제3자였다. 이 파일을 어디로 옮길지는
      **공개 범위 판정**(D-68)이 걸린다 — 팀장 확인을 받고 만든다.
   ⛔ **생성물이다 — 손으로 고치지 않는다** (D-90). 고칠 것이 있으면 이 파일을 고치고 다시 낸다.

🔄 **2026-09-17 4판 — 문서 기준 회수율을 재고, 잡음 네 종을 필터 후보로 계측한다.**
   ⛔ 3판까지는 **문구 기준**만 쟀다 — 무작위 문구 하나가 광고 카피일 확률이 30개 중 10개(33%)다.
      그런데 (A) 회수가 묻는 것은 **문서 기준**이다 — 「이 문서를 회수하면 쓸 만한 카피가
      하나라도 나오는가」. 문서당 문구가 중앙 7개라 문서 기준은 33% 보다 **높고, 얼마나 높은지
      모른다.** 하한만 보고 켜거나 접는 것이 D-205 가 막는 자리다.
   ★ `--docs N` — 무작위 N 문서의 **문구 전부**를 위치 순으로 찍는다. 문서마다 O/X 를 세면
      **문서 기준 회수율**이 나온다. 그것이 (A)의 진짜 크기다.
   ★ 그리고 3판 표본에서 드러난 잡음 네 종을 **필터 후보로 계측한다** — 켜면 몇 개를
      버리는지 함께 낸다 (D-142 — 마스킹은 모자라도 실패, 지나쳐도 실패).

🔄 **2026-09-17 3판 — 문서당 「첫 문구」를 뽑던 것을 무작위로 바꾼다.**
   ⛔ 2판은 각 문서의 `r_ps[0]` 을 담았다. 인용 위치의 중앙이 이유의 **36%** 지점이고
      1사분이 20% 이므로 **첫 문구는 이유 앞쪽 — 배경·용어 서술 구간**이다. 실측에서
      30개 중 광고 카피가 6개(20%)였는데, 그 20% 는 **문서의 비율이 아니라 「첫 문구」의
      비율**이다. 문서당 문구가 중앙 7개라 뒤쪽에 카피가 있어도 안 보인다.
   ★ 3판은 **문서 안에서 무작위로 하나**를 뽑고 **그 문구의 위치(%)를 같이 찍는다.**
   🚨 **뽑는 축과 섞는 축의 Random 을 따로 만든다** (D-176). 하나를 공유하면 문서 수가
      바뀔 때 소모 워드가 달라져 표본이 조용히 갈린다.

🔄 **2026-09-17 2판 — `--peek` 가 한 사건에 몰려 있었다.**
   ⛔ 첫 판은 ③ 문서를 **순회 순서대로** 만나는 대로 채웠다. 실행해 보니 8개가 전부
      같은 부동산 중개 사건의 매물 표시였다 — 「율곡주공3단지 아파트 76㎡」 넷 · 「보람아파트」 둘.
      **502건을 그 8개로 판단할 뻔했다** (D-40 의 정신 · D-176 의 「축을 나눈다」와 같은 병).
   ★ 2판은 **문서당 한 개만** 뽑고 **seed 를 고정해 섞는다.** 한 사건이 표본을 못 먹는다.
   ★ 그리고 **문서당 문구 수**와 **이유 안에서의 위치**를 함께 낸다 — 한 문서가 수백 개를
      뱉으면 그건 광고 문구가 아니라 잡음이고, 위치가 쏠리면 절 단위로 좁힐 수 있다.

🚨 **아무것도 쓰지 않는다.** `data/` 에 파일을 만들지 않고 `data/raw/ftc/*.xml` 을 읽기만 한다.
   그래서 수집기 공통 규약 1(`registry.require()`)의 대상이 아니다 — `ftc_triage` 와 같은 지위다.

🚨 **`scripts/` 가 아니라 `preprocess/` 다.** 게이트 `test_raw_는_수집_전처리_밖에서_참조되지_않는다`
   의 `RAW_READERS` 가 `{"collect", "preprocess"}` 다 (D-19 · D-92 · D-116).

⛔ **원문을 찍지 않는다** (D-17 · D-165). `--peek` 도 **마스킹을 지난** 문구만, 화면에만 낸다.
   파일로 내는 경로는 이 파일에 없다 — 만들면 그때부터 보관이다.
   🔴 다만 **마스킹은 피심인만 가린다** — `anchor_ftc` 가 피심인 이름을 캐므로 **제3자 상호**는
      남는다. 1판 실행에서 「부동산114」·「부동산뱅크」가 그대로 나왔다. 회수를 켜면 이것이
      `docs/**` 와 학습 입력에 대량으로 들어온다 (D-17 · D-230).

⛔ **계수기를 다시 만들지 않는다** (D-99). `QUOTE`·`NOISE`·`content_len`·`phrases_in` 은
   전부 `ftc_extract` 에서 가져온다. 여기서 다시 쓰면 두 수가 갈리고, 갈린 줄도 모른다.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import re
import statistics
import sys
import xml.etree.ElementTree as ET

from collect import store
from preprocess.ftc_extract import NOISE, QUOTE, content_len, phrases_in
from preprocess.ftc_triage import CORE, _text, classify
from preprocess.mask import anchor_ftc, apply_policy
from preprocess.text import sep_norm

RAW = pathlib.Path("data/raw/ftc")

#: 🔄 **4판 — 3판 표본(30개)에서 눈으로 잡은 잡음 네 종.** 아직 `NOISE` 가 아니라 **후보**다 —
#:    켜면 무엇을 잃는지 재기 전에 필터에 넣지 않는다 (D-142 · D-232).
#:      ㄱ 「렉타신<각주>4</각주>」           — XML 태그가 안 벗겨진 채 문구에 들어온다
#:      ㄴ 「라 한다)」·「…공정경쟁규약(이하」 — 약칭 정의가 잘려 들어온다. `NOISE` 의
#:                                            「이라 한다」가 이 꼴을 못 잡는다
#:      ㄷ 「…오피스텔!, 「15일간」           — 중첩 인용부호에서 두 문구가 이어붙는다
#:      ㄹ 「표시ㆍ광고법」·「과태료의 부과기준」 — 법령 약칭. 「법률」·「법 제」가 못 잡는다
#:    🚨 **ㄹ 은 위험하다** — 「…법」으로 끝나는 광고 문구가 있을 수 있다. 예시를 보고 정한다.
CAND: list[tuple[str, re.Pattern[str]]] = [
    ("ㄱ XML태그", re.compile(r"<[^>]{1,24}>")),
    ("ㄴ 약칭정의", re.compile(r"라\s*한다|\(이하\s*$")),
    ("ㄷ 중첩인용", re.compile(r"[\u2018\u2019\u201c\u201d\u300c\u300d\u300e\u300f]")),
    ("ㄹ 법령약칭", re.compile(r"법$|법\)|과태료|공정경쟁규약|규약$|시행규칙|부과기준")),
]
#: 후보별로 예시를 담아 두는 상한. 그중 **무작위** 2개만 찍는다 (3판에서 배운 것)
CAND_KEEP = 300

#: 🔄 **5판 — 파생물 자리** (D-143 단계 물질화 · D-92 「등급 밖 raw 를 읽어 derived 로」).
#:    🚨 `.gitignore` 의 `data/**` 가 덮는다 — 커밋되지 않는다 (D-19 · D-92).
DUMP = pathlib.Path("data/derived/ftc_reason_sample.jsonl")

#: 🔴 **재현의 근거는 seed 가 아니라 입력이다** (D-176). 여기는 저장하는 물건이 아니라
#:    화면 표본이므로 seed 만 고정한다 — 같은 `data/raw/ftc` 에 대해 같은 표본이 나온다.
SEED = 20260917


def _pct(offset: int, total: int) -> int:
    """이유 전체 길이 대비 인용 위치(%). 🚨 길이 0 은 0 으로 본다 — 나눗셈이 터지지 않게."""
    return int(offset * 100 / total) if total else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 의결서 「이유」의 광고 문구 인용 실태 계측")
    ap.add_argument(
        "--peek",
        type=int,
        default=0,
        metavar="N",
        help="🔴 마스킹을 지난 문구를 N 개까지 화면에만 찍는다 — 문서당 1개(무작위) · seed 고정",
    )
    ap.add_argument(
        "--docs",
        type=int,
        default=0,
        metavar="N",
        help="🔴 무작위 N 문서의 **문구 전부**를 위치 순으로 찍는다 — 문서 기준 회수율을 세는 자리",
    )
    ap.add_argument(
        "--docs-cap",
        type=int,
        default=12,
        metavar="M",
        help="한 문서에서 찍을 문구 상한 (기본 12). 넘으면 몇 개를 잘랐는지 적는다",
    )
    ap.add_argument(
        "--dump",
        nargs="?",
        const=str(DUMP),
        default=None,
        metavar="경로",
        help=f"🔴 마스킹을 지난 문구 전수를 JSONL 로 낸다 (기본 {DUMP}) — D-68 확인 뒤에 쓴다",
    )
    ap.add_argument("--seed", type=int, default=SEED, help=f"표본 seed (기본 {SEED})")
    a = ap.parse_args()

    if not RAW.exists():
        # 🔴 없으면 성공으로 집계되지 않게 한다 (D-72 · D-220)
        print(f"🚨 {RAW} 가 없다 — 먼저 uv run python -m collect.ftc_body", file=sys.stderr)
        return 1

    core = 0
    #: 문서를 네 칸으로 가른다 — **(A) 회수의 크기가 ③이다**
    box: collections.Counter[str] = collections.Counter()
    ph_order = ph_reason = 0
    gain_ph = 0  # ③ 문서에서 이유가 새로 주는 문구 수
    rlen: list[int] = []  # ③ 에서 뽑은 문구의 길이
    per_doc: list[int] = []  # ③ 문서당 문구 수
    pos: list[int] = []  # ③ 문구가 이유 안에서 나온 위치(%)
    noise_hit: collections.Counter[str] = collections.Counter()
    #: 🔴 문서당 **한 개**만 담는다 — 한 사건이 표본을 먹지 못하게 (2판)
    #:    🔄 3판 — 첫 문구가 아니라 **문서 안에서 무작위로** 뽑는다. 위치(%)도 같이 담는다
    pool: list[tuple[str, str, int]] = []
    #: 🚨 **뽑는 축과 섞는 축을 나눈다** (D-176 — 인스턴스를 공유하면 표본이 조용히 갈린다)
    rnd_pick = random.Random(a.seed)
    rnd_show = random.Random(a.seed)
    rnd_docs = random.Random(a.seed)
    rnd_cand = random.Random(a.seed)
    #: 🔄 4판 — 문서 통째 표본과 후보 필터 계측
    docs_pool: list[tuple[str, list[tuple[int, str]]]] = []
    #: 🔄 5판 — `--dump` 가 낼 줄. **CORE 전부**를 담는다(④ 포함) — 「없다」도 사실이다 (D-110)
    dump_rows: list[dict] = []
    cand_hit: collections.Counter[str] = collections.Counter()
    cand_ex: dict[str, list[str]] = {k: [] for k, _ in CAND}
    cand_any = 0

    for p in store.current_files(RAW, "*.xml"):
        r = ET.parse(p).getroot()
        raw = {f: _text(r, f) for f in ("사건명", "주문", "결정요지", "이유")}
        name, order, gist, reason = (sep_norm(raw[f]) for f in raw)
        k = classify(name, order, gist, reason)
        if k not in CORE:
            continue
        core += 1

        # 🔴 뽑기 **전에** 마스킹한다 (ftc_extract 와 같은 순서 · D-17)
        _, bare = anchor_ftc(r)
        o_ps = phrases_in(apply_policy(raw["주문"], bare, "ftc"))
        masked_reason = apply_policy(raw["이유"], bare, "ftc")
        r_ps = phrases_in(masked_reason)

        ph_order += len(o_ps)
        ph_reason += len(r_ps)

        if a.dump:
            #: 🔴 **여기 담기는 것은 전부 `apply_policy` 를 지난 문자열이다** (D-17).
            #:    원문은 `raw[...]` 에만 있고 이 자료구조에 들어오지 않는다 — D-165 가
            #:    「배포물과 자료구조를 분리하라」고 한 그 형태다.
            dump_rows.append(
                {
                    "seq": _text(r, "결정문일련번호"),
                    "결정일자": _text(r, "결정일자"),
                    "분류": k,
                    "주문문구": o_ps,
                    "이유문구": [
                        [_pct(masked_reason.find(q), len(masked_reason)), q] for q in r_ps
                    ],
                }
            )

        if o_ps and r_ps:
            box["① 주문 O · 이유 O"] += 1
        elif o_ps:
            box["② 주문 O · 이유 X"] += 1
        elif r_ps:
            box["③ 🔴 주문 X · 이유 O  ← 회수 대상"] += 1
            gain_ph += len(r_ps)
            per_doc.append(len(r_ps))
            rlen.extend(len(q) for q in r_ps)
            for q in r_ps:
                pos.append(_pct(masked_reason.find(q), len(masked_reason)))
            docs_pool.append(
                (
                    _text(r, "결정문일련번호"),
                    sorted((_pct(masked_reason.find(q), len(masked_reason)), q) for q in r_ps),
                )
            )
            pick = rnd_pick.choice(r_ps)
            pool.append(
                (
                    _text(r, "결정문일련번호"),
                    pick,
                    _pct(masked_reason.find(pick), len(masked_reason)),
                )
            )
        else:
            box["④ 둘 다 X"] += 1

        # 🔄 4판 — 후보 필터가 **이유에서 살아남은 문구** 중 무엇을 더 버리는지 (D-142)
        for q in r_ps:
            struck = False
            for key, pat in CAND:
                if pat.search(q):
                    cand_hit[key] += 1
                    struck = True
                    if len(cand_ex[key]) < CAND_KEEP:
                        cand_ex[key].append(q)
            cand_any += struck

        # 🚨 이유에서 `NOISE` 가 무엇을 버렸는지 — 필터를 이유에 그대로 쓰면 안 될 수 있다
        for q in QUOTE.findall(masked_reason):
            q = q.strip()
            if len(q) < 4 or q.isdigit() or content_len(q) < 4:
                continue
            hit = NOISE.search(q)
            if hit:
                noise_hit[hit.group(0)] += 1

    if not core:
        print("🚨 CORE 문서가 0건이다 — classify 가 아무것도 못 골랐다.", file=sys.stderr)
        return 1

    print(f"1층 후보(CORE) {core:,}건")
    print(f"  뽑은 문구 — 주문 {ph_order:,}개 · 이유 {ph_reason:,}개\n")
    for k in sorted(box):
        print(f"  {k:32s} {box[k]:>5}건 ({box[k] / core:>5.1%})")

    gain_docs = box["③ 🔴 주문 X · 이유 O  ← 회수 대상"]
    now = box["① 주문 O · 이유 O"] + box["② 주문 O · 이유 X"]
    print(f"\n  🔴 회수 가능 문서 {gain_docs:,}건 — 현행 {now:,}건 → {now + gain_docs:,}건", end="")
    print(f" ({(now + gain_docs) / max(now, 1):.2f}배)")
    print(f"     그 문서들이 주는 문구 {gain_ph:,}개")

    if per_doc:
        q = statistics.quantiles(per_doc, n=10) if len(per_doc) >= 10 else []
        print(
            f"     문서당 문구 수 — 중앙 {statistics.median(per_doc):.0f}"
            + (f" · p90 {q[8]:.0f}" if q else "")
            + f" · 최대 {max(per_doc)}"
        )
        print("     🚨 최대가 수십을 넘으면 그 문서는 광고 문구가 아니라 잡음을 뱉고 있다")
    if rlen:
        print(
            f"     문구 길이 — 중앙 {statistics.median(rlen):.0f}자 · 평균 {statistics.mean(rlen):.1f}자"
        )
    if pos:
        qq = statistics.quantiles(pos, n=4) if len(pos) >= 4 else []
        print(
            f"     이유 안에서의 위치 — 중앙 {statistics.median(pos):.0f}%"
            + (f" (1사분 {qq[0]:.0f}% · 3사분 {qq[2]:.0f}%)" if qq else "")
        )
        print("     ★ 쏠려 있으면 이유 전체가 아니라 **그 절만** 보면 된다")

    print("\n  🚨 이유에서 `NOISE` 가 버린 것 — 상위 10")
    if noise_hit:
        for k, v in noise_hit.most_common(10):
            print(f"     {v:>6}  「{k}」")
        print(f"     합계 {sum(noise_hit.values()):,}건")
    else:
        print("     없다")

    if a.peek and pool:
        rnd_show.shuffle(pool)
        sample = pool[: a.peek]
        print(
            f"\n  🔴 마스킹을 지난 문구 {len(sample)}개 — 서로 다른 {len(sample)}개 사건에서 하나씩"
        )
        print(f"     (문서 안에서 **무작위** · seed {a.seed} · 화면에만 · 저장 경로 없음)")
        print("         seq   위치  문구")
        for seq, q, at in sample:
            print(f"     {seq:>7}  {at:>3}%  {q[:96]}")
        print("     🚨 제3자 상호는 마스킹을 안 지난다 — 눈으로 볼 때 그것도 같이 센다")
        print("     ★ 위치를 같이 본다 — 카피가 특정 구간에 모여 있으면 그 절만 보면 된다")

    if cand_hit:
        print(f"\n  🔄 **후보 필터가 더 버릴 것** — 이유 문구 {ph_reason:,}개 기준 (D-142)")
        for key, _pat in CAND:
            n = cand_hit[key]
            ex = cand_ex[key]
            rnd_cand.shuffle(ex)
            tail = ("  예: " + " · ".join(f"「{x[:32]}」" for x in ex[:2])) if ex else ""
            print(f"     {key:11s} {n:>6}개 ({n / max(ph_reason, 1):>5.1%}){tail}")
        print(f"     {'넷 중 하나라도':11s} {cand_any:>6}개 ({cand_any / max(ph_reason, 1):>5.1%})")
        print(f"     → 넷을 다 켜면 {ph_reason - cand_any:,}개가 남는다")
        print("     🚨 ㄹ 은 「…법」으로 끝나는 **광고 문구**도 버릴 수 있다 — 예시를 보고 정한다")

    if a.docs and docs_pool:
        rnd_docs.shuffle(docs_pool)
        n_show = min(a.docs, len(docs_pool))
        print(f"\n  🔴 문서 {n_show}개의 **문구 전부** (위치 순 · 화면에만 · 저장 경로 없음)")
        print("     ★ 문서마다 「쓸 만한 광고 카피가 하나라도 있나」를 O/X 로 센다")
        print("       — 그 비율이 **문서 기준 회수율**이고, (A) 회수의 진짜 크기다")
        for seq, qs in docs_pool[:n_show]:
            cut = qs[: a.docs_cap]
            more = len(qs) - len(cut)
            head = f"\n     -- [{seq}]  문구 {len(qs)}개"
            print(head + (f" (앞 {len(cut)}개만 · {more}개 생략)" if more else ""))
            for at, q in cut:
                print(f"        {at:>3}%  {q[:92]}")

    if a.dump:
        out = pathlib.Path(a.dump)
        out.parent.mkdir(parents=True, exist_ok=True)
        body = "\n".join(json.dumps(x, ensure_ascii=False) for x in dump_rows) + "\n"
        out.write_text(body, encoding="utf-8")
        #: 🔴 **쓰기 응답을 증거로 쓰지 않는다** — 되읽어 대조한다 (D-149)
        back = out.read_text(encoding="utf-8")
        if back != body:
            print(f"🚨 {out} 되읽기가 어긋난다 — 쓰지 못했다", file=sys.stderr)
            return 1
        print(f"\n  ✅ {out}  {out.stat().st_size:,}B · {len(dump_rows):,}줄")
        print("     🔴 제3자 상호는 마스킹을 안 지난다 — 이 파일을 옮기는 것은 공개 범위다 (D-68)")
        print("     ⛔ 생성물이다 — 손으로 고치지 않는다 (D-90)")

    print(
        "\n  ⛔ **이 수는 판정이 아니다** — 「이유에 인용이 있다」이지 「그 인용이 광고 문구다」가"
    )
    print(
        "     아니다. 이유에는 타사 광고·법문 재인용·언론 인용·매물 표시가 섞인다 (D-05 · D-232)."
    )
    print("     회수를 켜기 전에 ③ 표본을 눈으로 봐야 한다 — `--peek 30` 이 그 자리다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
