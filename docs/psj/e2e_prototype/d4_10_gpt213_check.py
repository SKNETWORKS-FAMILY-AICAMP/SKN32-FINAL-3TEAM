"""D-339 결정 1 ④ — 다른 생성기(GPT) 적법 213 행이 D4-10 학습에 없는지 지문 대조 (박수진 · 2026-10-14 · 학습 없음)

D4-10 의 학습 행은 골든(train) 3,966 + 권소라 900 검수판의 정상 문구 545 다. 그 둘의 **상위 집합**
(골든 전 행 · 900 검수판 전 행)과 GPT 353 검수판의 문구를 맞댄다 — 상위 집합에 없으면 학습에도 없다.

  uv run python docs\\psj\\e2e_prototype\\d4_10_gpt213_check.py --gpt-csv <LLM_카피생성_GPT정상문구_353_검수용_ksr_2026-10-13.csv> --review-csv <900 검수판> [--golden <golden.jsonl>] [--out-md <집계표>]

  · 맞대는 열쇠 둘 — ① 노트북과 같은 `norm_text`(공백 하나로) ② 느슨한 열쇠(공백 · 문장부호를 모두 지움 · 같은 문구의 띄어쓰기 · 부호만 다른 것)
  · 대상 — 213 행(판독(사람) 「적법」 · 애매 표시 없음 · D-331 결정 2 의 정의) 과 353 전 행을 따로 센다
  · 파일 지문 — GPT 검수판 `c5c78314d1732a25` · 900 검수판 `f3bfec9079e05c36` · 골든 `f6ccc5a7de44` 가 아니면 멈춘다
🔴 건수만 적는다 — 문구 · id 는 출력하지 않는다 (D-249).
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
GOLDEN = os.path.join(REPO, "data", "derived", "golden", "golden.jsonl")
SHA = {"gpt": "c5c78314d1732a25", "review": "f3bfec9079e05c36", "golden": "f6ccc5a7de44"}
OK = "적법"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def norm_text(s):
    return " ".join(s.split())


def loose(s):
    return re.sub(r"[\s\W_]+", "", s)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpt-csv", required=True)
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args(argv)

    got = {"gpt": sha(a.gpt_csv), "review": sha(a.review_csv), "golden": sha(a.golden)}
    bad = {k: v[:16] for k, v in got.items() if not v.startswith(SHA[k])}
    if bad:
        raise SystemExit(f"🔴 파일 지문이 기록과 다르다 — {bad} · 기대 {SHA}")

    gpt = read_csv(a.gpt_csv)
    need = {"text", "판독(사람)"}
    if not need <= set(gpt[0]):
        raise SystemExit(f"🔴 GPT 검수판에 {need - set(gpt[0])} 칸이 없다 — 칸: {list(gpt[0])}")
    amb_col = "애매표시" if "애매표시" in gpt[0] else None
    t213 = [r for r in gpt if r["판독(사람)"].strip() == OK and not (amb_col and r[amb_col].strip())]
    if len(gpt) != 353 or len(t213) != 213:
        raise SystemExit(f"🔴 행 수가 원장과 다르다 — 전 행 {len(gpt)} (353) · 적법 · 애매 없음 {len(t213)} (213)")

    review = read_csv(a.review_csv)
    golden = []
    with open(a.golden, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                golden.append(json.loads(line))
    pools = {
        "골든 전 행": [r["text"] for r in golden],
        "골든 train": [r["text"] for r in golden if r.get("split") == "train"],
        "900 검수판 전 행": [r["text"] for r in review],
    }
    keys = {name: ({norm_text(t) for t in ts}, {loose(t) for t in ts}) for name, ts in pools.items()}

    def count(rows):
        out = {}
        for name, (ks, kl) in keys.items():
            out[name] = (sum(1 for r in rows if norm_text(r["text"]) in ks), sum(1 for r in rows if loose(r["text"]) in kl))
        return out

    c213, call = count(t213), count(gpt)
    md = ["# D-339 결정 1 ④ — 다른 생성기(GPT) 적법 213 행 · D4-10 학습 겹침 지문 대조", "",
          f"> GPT 검수판 `{got['gpt'][:16]}` (353 행 · 적법 · 애매 없음 213) · 900 검수판 `{got['review'][:16]}` · 골든 `{got['golden'][:12]}` · "
          "D4-10 학습 행(골든 train 3,966 + 900 검수판 정상 문구 545)의 상위 집합과 맞댐 · 건수만 적는다", "",
          "| 맞댄 묶음 | 213 행 — 같은 문구(norm_text) | 213 행 — 느슨한 열쇠 | 353 전 행 — 같은 문구 | 353 전 행 — 느슨한 열쇠 |",
          "|---|---:|---:|---:|---:|"]
    for name in pools:
        md.append(f"| {name} ({len(pools[name]):,}) | {c213[name][0]} | {c213[name][1]} | {call[name][0]} | {call[name][1]} |")
    clean = all(v == (0, 0) for v in c213.values())
    md += ["", f"판정 — **{'겹침 0 · D-339 결정 1 ④ 충족' if clean else '겹침 있음 · 그 행이 실제 학습 행인지 노트북 규칙으로 다시 본다'}**", "",
           "느슨한 열쇠 = 공백 · 문장부호를 모두 지운 글자열 · 상위 집합에 없으면 D4-10 학습에도 없다."]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        with open(a.out_md, "w", encoding="utf-8", newline="\n") as fo:
            fo.write(out)
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
