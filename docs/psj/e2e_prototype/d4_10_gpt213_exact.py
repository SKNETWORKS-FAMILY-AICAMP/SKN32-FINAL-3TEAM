"""D-339 결정 1 ④ (팀장 10-15 요청) — GPT 적법 213 행이 D4-10 의 **실제 학습 행 4,511** 에 없는지 id · 문장 지문으로 대조 (박수진 · 2026-10-15)

`d4_10_gpt213_check.py`(10-14)는 학습 행의 상위 집합(골든 전 행 · 900 검수판 전 행)과 문장만 맞댔다.
이 스크립트는 D4-10 노트북의 데이터 셀(3 · 7 · 9)을 **그대로 실행해** 학습 행 4,511 을 다시 만들고(EXPECT_TRAIN 대조),
GPT 검수판 353 행(그중 「적법」 · 애매 없음 213)과 ① id ② 문장 지문(norm_text) ③ 느슨한 열쇠(공백 · 부호 지움)로 맞댄다.
문장 칸은 `text` 와 `판정에 넘긴 글자(고정 문구 뺌)` 둘 다 본다.

  python docs/psj/e2e_prototype/d4_10_gpt213_exact.py --gpt-csv <353 검수판> --review-csv <900 검수판> --golden <golden.jsonl> [--out-md <집계표>]
🔴 출력은 건수만 — 겹치는 행이 있으면 그 id 만 적는다(문장은 적지 않는다 · D-249).
"""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NB = os.path.normpath(os.path.join(HERE, "..", "notebooks", "copylane_encoder_D4-10_사실전제학습_20261013.ipynb"))
SYN_NAME = "LLM_카피생성_정상카피_900_판독용_사람칸채움_ksr_2026-10-11.csv"
GPT_SHA = "c5c78314d1732a25"


def norm_text(s):
    return " ".join(s.split())


def loose(s):
    return re.sub(r"[\s\W_]+", "", s)


def train_rows(golden, review):
    """노트북 데이터 셀을 그대로 실행해 TRAIN_ROWS 를 돌려준다 (셀 3 · 5(설정만) · 7 · 9)."""
    nb = json.load(open(NB, encoding="utf-8"))
    code = [("".join(c["source"])) for c in nb["cells"] if c["cell_type"] == "code"]
    want = [c for c in code if "EXPECTED_GOLDEN_SHA" in c or "CAT_VALUES = " in c or "def dev_eligible" in c or "TRAIN_ROWS = rows" in c]
    if len(want) != 4:
        raise SystemExit(f"🔴 노트북 데이터 셀을 찾지 못했다 ({len(want)})")
    want[1] = want[1].split("OUT_ROOT =")[0]          # 설정 셀은 Drive 마운트 앞까지만
    tmp = tempfile.mkdtemp()
    shutil.copy(golden, os.path.join(tmp, "golden.jsonl"))
    shutil.copy(review, os.path.join(tmp, SYN_NAME))
    cwd = os.getcwd()
    os.chdir(tmp)
    g = {"display": lambda *a, **k: None}
    try:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            for c in want:
                exec(compile(c, "nb", "exec"), g)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    if "✅ 학습셋이 D4 기록에 적은 수와 같다" not in buf.getvalue():
        raise SystemExit("🔴 학습 행이 노트북 기록(4,511)과 같다는 확인이 나오지 않았다")
    return g["TRAIN_ROWS"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpt-csv", required=True)
    ap.add_argument("--review-csv", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out-md", default=None)
    a = ap.parse_args(argv)
    gsha = hashlib.sha256(open(a.gpt_csv, "rb").read()).hexdigest()
    if not gsha.startswith(GPT_SHA):
        raise SystemExit(f"🔴 GPT 검수판 sha 가 다르다 — {gsha[:16]} (기대 {GPT_SHA})")
    gpt = list(csv.DictReader(open(a.gpt_csv, encoding="utf-8-sig", newline="")))
    t213 = [r for r in gpt if r["판독(사람)"].strip() == "적법" and not r["애매표시"].strip()]
    if (len(gpt), len(t213)) != (353, 213):
        raise SystemExit(f"🔴 행 수가 다르다 — {len(gpt)} · {len(t213)}")
    tr = train_rows(a.golden, a.review_csv)
    if len(tr) != 4511:
        raise SystemExit(f"🔴 학습 행이 {len(tr)} 이다 (기대 4,511)")
    ids = {r["id"] for r in tr} | {r["id"].split(":", 1)[1] for r in tr if r["id"].startswith("syn:")}
    kn = {norm_text(r["text"]) for r in tr}
    kl = {loose(r["text"]) for r in tr}
    COLS = ["text", "판정에 넘긴 글자(고정 문구 뺌)"]

    def hits(rows):
        out = {"id": [r["id"] for r in rows if r["id"] in ids]}
        for col in COLS:
            out[f"{col} · 같은 문구"] = [r["id"] for r in rows if r.get(col, "").strip() and norm_text(r[col]) in kn]
            out[f"{col} · 느슨한 열쇠"] = [r["id"] for r in rows if r.get(col, "").strip() and loose(r[col]) in kl]
        return out

    h213, hall = hits(t213), hits(gpt)
    clean = not any(h213.values())
    md = ["# D-339 결정 1 ④ — GPT 적법 213 행 · D4-10 실제 학습 행(4,511) 대조 (id · 문장 지문)", "",
          f"> GPT 검수판 `{gsha[:16]}` (353 행 · 적법 · 애매 없음 213) · 학습 행 = D4-10 노트북 데이터 셀을 그대로 실행해 다시 만든 4,511 행"
          "(노트북의 EXPECT_TRAIN 대조 통과 · 골든 3,966 + 900 검수판 정상 문구 545) · 건수만 적는다", "",
          "| 맞대기 | 213 행 겹침 | 353 전 행 겹침 |", "|---|---:|---:|"]
    for k in h213:
        md.append(f"| {k} | {len(h213[k])} | {len(hall[k])} |")
    md += ["", f"판정 — **{'겹침 0 · D-339 결정 1 ④ 충족' if clean else '겹침 있음'}**", "",
           "id 맞대기는 학습 행 id(골든 id · `syn:` + 900 검수판 id) 와 그 접두 없는 id 둘 다로 · 문장은 `text` 와 `판정에 넘긴 글자(고정 문구 뺌)` 둘 다로 맞댔다."]
    if not clean:
        md += ["", "겹친 id — " + " · ".join(sorted({i for v in h213.values() for i in v}))]
    out = "\n".join(md) + "\n"
    print(out)
    if a.out_md:
        open(a.out_md, "w", encoding="utf-8", newline="\n").write(out)
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
