"""scripts/guide_build.py — 두 겹 안내의 **원문 보기** 글자를 수집본에서 옮긴다 (🆕 2026-10-20 · D-348 보충 32 결정 3).

  uv run python scripts/guide_build.py --write          # 승인 짝 표(`app/guide_table.py` ARTICLES)의 조문 → app/guide_articles.json
  uv run python scripts/guide_build.py --check          # 생성물이 수집본 · 짝 표와 같은가(다르면 1)
  uv run python scripts/guide_build.py --show <좌표> …   # 좌표의 글자를 본다(초안 쓰기용 · 읽기만)
  uv run python scripts/guide_build.py --list <앞부분>   # 그 앞부분으로 시작하는 좌표를 다 본다(초안 쓰기용 · 읽기만)

★ 좌표 두 꼴 — 수집본 칸 그대로:
   · 본문 `<문서>|<조>|<가지>|<항>|<호>` — `data/derived/law_article.jsonl` · 문서 = 파일 이름에서 날짜를 뺀 것(`law_013094` · `admrul_75449`)
   · 별표 `별표:<법 ID>_<별표 번호>:<경로>` — `data/derived/law_norm/<법 ID>_<별표 번호>.jsonl` 의 `path`(`별표:013453_0001:3.나`)
   좌표 하나는 수집본의 **한 줄**이어야 한다 — 없거나 둘 이상이면 멈춘다(D-220).
🔴 글자를 고치지 않는다 — 수집본 그대로 옮긴다(D-90). 수집본이 바뀌면 `--write` 로 다시 만든다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.contracts import GuideArticle  # noqa: E402
from app.guide_table import ARTICLES  # noqa: E402

CORPUS = ROOT / "data" / "derived" / "law_article.jsonl"
ANNEX_DIR = ROOT / "data" / "derived" / "law_norm"
OUT = ROOT / "app" / "guide_articles.json"
_FILE = re.compile(r"^(?P<doc>(?:law|admrul)_(?P<id>[^_]+))_(?P<date>\d{8})\.xml$")


def _doc(file: str) -> tuple[str, str | None]:
    m = _FILE.match(file)
    if m is None:
        return file, None
    d = m["date"]
    return m["doc"], f"{d[:4]}-{d[4:6]}-{d[6:]}"


def coord_of(r: dict) -> str:
    doc, _ = _doc(r["파일"])
    return "|".join(
        [
            doc,
            str(r.get("조", "")),
            str(r.get("가지", "")),
            str(r.get("항", "")),
            str(r.get("호", "")),
        ]
    )


def _where(r: dict) -> str:
    jo, hang = str(r["조"]), str(r.get("항", ""))
    if not jo.isdigit():
        return hang or jo  # 산문 고시 — 항 칸이 이미 「Ⅳ.1.가」 꼴로 장부터 적혀 있다
    w = f"제{jo}조" + (f"의{r['가지']}" if r.get("가지") else "")
    ho = str(r.get("호", ""))
    m = re.fullmatch(r"(\d+(?:의\d+)?)\.", ho)
    return w + hang + (f"제{m[1]}호" if m else ho)


def load_corpus(path: Path = CORPUS, annex_dir: Path = ANNEX_DIR) -> dict[str, list[dict]]:
    """좌표 → 수집본 줄들. 별표 줄에는 법 이름 · 판(같은 법 ID 의 본문 파일에서)을 붙여 둔다."""
    if not path.exists():
        raise SystemExit(f"🔴 수집본이 없다 — {path} (사본은 data-sync)")
    out: dict[str, list[dict]] = {}
    names: dict[str, tuple[str, str | None]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out.setdefault(coord_of(r), []).append(r)
            m = _FILE.match(r["파일"])
            if m is not None:
                names.setdefault(m["id"], (r["법령"], _doc(r["파일"])[1]))
    for f in sorted(annex_dir.glob("*.jsonl")) if annex_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            law, version = names.get(str(r["law_id"]), (None, None))
            out.setdefault(f"별표:{f.stem}:{r['path']}", []).append(
                {**r, "_law": law, "_version": version}
            )
    return out


def article(coord: str, corpus: dict[str, list[dict]]) -> GuideArticle:
    rows = corpus.get(coord, [])
    if len(rows) != 1:
        raise SystemExit(f"🔴 좌표가 수집본의 한 줄이 아니다 — {coord} · {len(rows)} 줄 (D-220)")
    r = rows[0]
    if coord.startswith("별표:"):
        if not r.get("_law"):
            raise SystemExit(
                f"🔴 별표의 법 이름을 모른다 — {coord} (본문 수집본에 그 법 ID 가 없다 · D-220)"
            )
        stem = coord.split(":")[1]
        kind = "별지" if "별지" in stem else "별표"
        no = int(r["annex_no_head"] if r.get("annex_no_head") is not None else r["annex_no"])
        # 판 — 줄에 원문 파일이 적혀 있으면 그 날짜 · 없으면 같은 법 ID 본문 파일의 날짜
        version = _doc(r["원문파일"])[1] if r.get("원문파일") else r["_version"]
        return GuideArticle(
            law_name=f"{r['_law']} [{kind} {no}] {r['annex_title']}",
            where=str(r["path"]),
            text=r["text"],
            version=version,
        )
    _, version = _doc(r["파일"])
    lead = r.get("항본문") if r.get("호") and r.get("항본문") != r.get("본문") else None
    return GuideArticle(
        law_name=r["법령"], where=_where(r), lead=lead, text=r["본문"], version=version
    )


def build(corpus: dict[str, list[dict]]) -> dict[str, dict]:
    coords = sorted({c for cs in ARTICLES.values() for c in cs})
    return {c: article(c, corpus).model_dump() for c in coords}


def _dump(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--show", nargs="+", metavar="좌표")
    g.add_argument("--list", metavar="앞부분")
    a = ap.parse_args(argv)
    corpus = load_corpus()
    if a.show:
        for c in a.show:
            print(c, "\n ", article(c, corpus).model_dump_json(indent=1))
        return 0
    if a.list:
        for c, rows in sorted(corpus.items()):
            if c.startswith(a.list):
                body = rows[0].get("본문") or rows[0].get("text") or ""
                print(c, "·", len(rows), "줄 ·", body[:70].replace("\n", " "))
        return 0
    built = build(corpus)
    text = _dump(built)
    if a.write:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"✅ {OUT.relative_to(ROOT)} — 조문 {len(built)} 개")
        return 0
    have = OUT.read_text(encoding="utf-8") if OUT.exists() else _dump({})
    if have != text:
        print("🔴 생성물이 수집본 · 짝 표와 다르다 — uv run python scripts/guide_build.py --write")
        return 1
    print("✅ 같다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
