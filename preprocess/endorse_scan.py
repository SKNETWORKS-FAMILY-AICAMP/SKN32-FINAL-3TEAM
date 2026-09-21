"""preprocess/endorse_scan.py — 공정위 의결서의 **추천·보증(인플루언서·후기) 사건**이 평가 문구를 주는가.

  uv run python -m preprocess.endorse_scan                 # 세기만 한다 (화면에 수만)
  uv run python -m preprocess.endorse_scan --candidates    # + 후보를 build/ 에 쓴다 (마스킹 뒤)

🔴 이 모듈은 라벨을 만들지 않는다 — 계측(`SCANNERS`)이다. D-255 ⬜ 「후기 실사례를 늘릴 수 있는 마지막 원천」을 잰다.

팀장 — *「의결서에서 인플루언서 뒷광고에 대한 내용을 찾아볼 수 있을 것 같은데」* (2026-09-20).
사용자 실행(09-20): 8,272건 중 「인플루언서」 27 · 「추천·보증」 32 · 「경제적 이해관계」 49 · 「협찬」 33 파일.

**셋을 가른다** — 주문(처분 문장)이 무엇을 위반으로 적었나

  | 갈래           | 주문의 모양                                              | 우리 유형 (D-255)              |
  |----------------|----------------------------------------------------------|--------------------------------|
  | `미표시`       | 「경제적 이해관계를 … 은폐 또는 누락」                     | `추천_보증_뒷광고` — **범위 밖** |
  | `거짓후기`     | 「실제로 사용해 본 사실이 없음에도 경험적 사실에 부합하는 것처럼」 | `후기_체험기_기만` 후보 — 문구로 보일 **수도** 있다 |
  | `기타`         | 인플루언서·후기가 나오지만 위 둘이 아니다                   | 사람이 본다                     |

🚨 **표본 20건 실측 (2026-09-20 · 컨테이너)** — 광고물(게시글)은 **이미지로만** 실린다(`flDownload` · 「광고물(예시 1)」).
   이유 본문의 인용부호는 대부분 **도표 캡션 · 고시 이름 · 「이 사건 게시물」 같은 약칭**이다. 그래서 인용을 **거른 뒤** 센다.
🔴 **후보 파일은 마스킹을 지난 뒤에만 쓴다** (`mask.apply_policy` · `ftc_decisions_body` 정책 · 업체명·상표).
   쓰는 자리는 `build/` 다 — 커밋되지 않고 공유 저장소로도 안 간다(파생물이 아니다). 사건명은 쓰지 않는다(피심인 상호).
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

from collect import store
from preprocess.text import quoted

SOURCE_ID = "ftc_decisions_body"
#: 🔴 마스킹 정책의 키는 **원천 id 가 아니라 원문 폴더(계열)** 다 — `ftc_extract` 가 쓰는 `"ftc"` 와 같다.
#:    ⛔ 첫 판은 `SOURCE_ID` 를 넘겨 `MaskPolicyError` 로 멈췄다(기기 실행 09-21). 표는 `store.FAMILY_OF` 한 곳 (D-99)
MASK_KEY = store.families(SOURCE_ID)[0]

#: 이 사건이 추천·보증 사건인가 — 🚨 그물이다. 주문·이유 어디에든 있으면 줍는다
NET = re.compile(
    r"인플루언서|추천\s*[ㆍ·]?\s*보증|경제적\s*이해관계|협찬|체험단|기자단|구매평|뒷광고"
)

#: 주문이 무엇을 위반으로 적었나 — 순서가 가르는 순서다(한 주문에 둘이 다 있으면 둘 다 센다)
KINDS: dict[str, re.Pattern[str]] = {
    "미표시": re.compile(r"경제적\s*이해관계[^.]{0,40}(공개하지|표시하지|은폐|누락)"),
    "거짓후기": re.compile(
        r"(사용|체험|구매)(해\s*본|한)\s*(사실|적)이\s*없[^.]{0,60}(경험|체험|후기)|경험적\s*사실에\s*부합"
    ),
}

#: 매체 — 주문·이유에서 처음 보이는 것들
MEDIA: dict[str, re.Pattern[str]] = {
    "인스타그램": re.compile(r"인스타그램|instagram", re.I),
    "유튜브": re.compile(r"유튜브|youtube", re.I),
    "블로그": re.compile(r"블로그"),
    "쇼핑몰구매평": re.compile(r"구매평|상품평|리뷰\s*게시판"),
}

#: 표시광고법 제3조제1항 각 호 — 1호 거짓·과장 · 2호 기만
HO = re.compile(r"제3조\s*제1항\s*제([1-4])호")

#: 🚨 인용부호 안이지만 **광고 문구가 아닌 것** — 실측 20건에서 걸러야 했던 모양들
NOT_AD = re.compile(
    r"flDownload|번째\s*이미지|^이\s*사건|심사지침|예규|고시|법률|시행령|근거이론|"
    r"^온라인에\s*게시된|이하\s|^[\w\s]{0,12}$"  # 짧은 약칭(12자 이하 공백·글자뿐)
    r"|['‘’“”\"]|<각주>|^[,、·와과의]\s"  # 인용 안에 또 인용부호 · 각주 · 앞말 조각 — 인용을 잘못 연 자리
    # 🔄 전량 실측(09-21) — 212개 중 **135개가 한 사건(대규모유통업법)의 증거 문서 제목**이었다.
    #    광고 문구가 아니라 파일 이름·계획서·거래내역이다. 세면 「후보가 늘었다」는 착시가 된다.
    r"|\.(png|jpg|xlsx|pptx|docx|pdf|hwp)\b|Plan\b|Target|supplier|update\b|거래내역|"
    r"단가인상|가격\s*인상|협의\s*자료|설문|계약서|공문|이메일|^\d{4}[.\-년]"
    r"|^○+[\s.,○]*$|^[◎▩*\s]+$"  # 마스킹만 남은 자리 — 사람이 읽을 것이 없다
    # 법 조문·판결 인용 — 의결서가 자기 근거를 적는 자리다(광고 문구가 아니다)
    r"|대통령령|제3조|거래상의?\s*지위|납품업자|구매자가\s*상품"
)

#: 광고물이 이미지로만 실렸다는 표시 — 「광고물(예시 N)」 · 「게시물 작성 지침」
IMAGE_AD = re.compile(
    r"광고물\s*\(?\s*예시|게시물\s*(작성\s*)?(지침|예시)|<그림\s*\d+>[^<]{0,30}(광고물|게시물)"
)


def _fields(path: pathlib.Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    return {ch.tag: (ch.text or "").strip() for ch in root}


def ad_quotes(text: str) -> list[str]:
    """이유 본문에서 **광고 문구일 수 있는** 인용만 — 캡션·고시명·약칭을 뺀다. 🚨 판정이 아니다(사람이 본다)."""
    return [q for q in quoted(text, min_len=8, max_len=120) if not NOT_AD.search(q)]


def classify(f: dict[str, str]) -> dict | None:
    """한 의결서 → 계측 칸. 추천·보증 그물에 안 걸리면 None. 🚨 원문을 담지 않는다."""
    order, why = f.get("주문", ""), f.get("이유", "")
    if not NET.search(order + "\n" + why):
        return None
    kinds = [k for k, p in KINDS.items() if p.search(re.sub(r"\s+", " ", order))]
    return {
        "갈래": kinds or ["기타"],
        "주문에서": bool(NET.search(order)),
        "매체": [m for m, p in MEDIA.items() if p.search(order + why)],
        "호": sorted(set(HO.findall(order + why))),
        "광고물_이미지": len(IMAGE_AD.findall(why)),
        "문구후보": len(ad_quotes(why)),
        "연도": (f.get("결정일자") or f.get("의결일자") or "")[:4],
    }


def scan(source: str = SOURCE_ID) -> tuple[dict, list[tuple[pathlib.Path, dict, dict]]]:
    raw = store.family_path(source)
    files = store.current_files(raw, "*.xml")
    if not files:
        raise FileNotFoundError(f"{raw} 에 *.xml 이 없다 — 먼저 수집기를 돌린다")
    hits = []
    for p in files:
        f = _fields(p)
        c = classify(f)
        if c is not None:
            hits.append((p, f, c))
    cnt = collections.Counter
    core = [h for h in hits if h[2]["주문에서"]]
    return {
        "의결서": len(files),
        "그물(주문∪이유)": len(hits),
        "그중_주문에서_걸린_것": len(core),
        "갈래(주문에서)": dict(cnt(k for h in core for k in h[2]["갈래"]).most_common()),
        "매체(주문에서)": dict(cnt(m for h in core for m in h[2]["매체"]).most_common()),
        "호(주문에서)": dict(cnt(x for h in core for x in h[2]["호"]).most_common()),
        "광고물이_이미지뿐(주문에서)": sum(
            1 for h in core if h[2]["광고물_이미지"] and not h[2]["문구후보"]
        ),
        "문구후보가_있는_것(주문에서)": sum(1 for h in core if h[2]["문구후보"]),
        "문구후보_수(주문에서)": sum(h[2]["문구후보"] for h in core),
        "연도(주문에서)": dict(sorted(cnt(h[2]["연도"] for h in core).items())),
    }, core


def candidates(core: list[tuple[pathlib.Path, dict, dict]], out: pathlib.Path) -> int:
    """🔴 사람이 볼 후보 — **마스킹을 지난 인용만** 쓴다. 사건명·피심정보는 쓰지 않는다. 쓰는 곳은 `build/`."""
    from preprocess.mask import apply_policy  # noqa: PLC0415 — 쓸 때만 무겁다

    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8", newline="\n") as w:
        for p, f, c in core:
            qs = [apply_policy(q, "", MASK_KEY) for q in ad_quotes(f.get("이유", ""))]
            rec = {"id": p.stem, "사건번호": f.get("사건번호", ""), **c, "문구": qs}
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="공정위 추천·보증 사건 — 평가 문구를 주는가")
    ap.add_argument("source", nargs="?", default=SOURCE_ID)
    ap.add_argument(
        "--candidates",
        action="store_true",
        help="후보를 build/endorse_candidates.jsonl 에 쓴다 (마스킹 뒤 · 커밋 안 됨)",
    )
    a = ap.parse_args()
    got, core = scan(a.source)
    for k, v in got.items():
        print(f"  {k:<28} {v}")
    print(
        "\n  🚨 그물이다 — 판정이 아니다. `미표시`는 범위 밖(D-255)이고,"
        " 평가 문구가 될 수 있는 것은 `거짓후기`의 **문구후보**뿐이다(사람이 본다)."
    )
    if a.candidates:
        out = pathlib.Path("build") / "endorse_candidates.jsonl"
        n = candidates(core, out)
        print(f"\n  → {out} {n}행 (마스킹 뒤 · build/ 는 커밋되지 않는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
