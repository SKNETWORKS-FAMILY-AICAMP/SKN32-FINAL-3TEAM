"""load_db.py — 파생물을 거버넌스 DB 에 적재한다 (D-95 · D-20).

  uv run python -m scripts.load_db --dry-run
  uv run python -m scripts.load_db

왜 있는가 — 2026-09-09 확인: **적재 스크립트가 한 줄도 없었다.** 25 테이블과 pgvector 가
서 있는데 내용이 없어서, 팀원이 DB 를 열면 빈 테이블만 본다. 그것이 착수를 막는 유일한 것이었다.

🚨 **멱등이다.** 같은 것을 두 번 넣지 않는다 — 모든 적재가 `ON CONFLICT` 로 간다.
   반쯤 넣고 죽은 뒤 다시 돌릴 수 있어야 한다.

🚨 **fail-closed.** 열거형에 없는 값을 만나면 **멈춘다.** 조용히 건너뛰면
   「행 수가 맞아도 전량이 아니다」가 된다 (D-149).

🔴 **골든셋은 아직 못 넣는다 — 판정 둘이 걸려 있다** (2026-09-09):

   ① `split_t` 가 `('train','dev','test_holdout')` 인데 골든셋은 **`test_sentence`** 를 쓴다.
      `test_holdout` 은 `mfds_press` 홀드아웃이라 뜻이 다르다. 접으면 두 평가가 한 칸에 섞인다.
      → 열거형에 `test_sentence` 를 더하는 마이그레이션이 필요하고, 그건 거버넌스 층
        DDL 변경이라 판정 사항이다.

   ② `violation_t` 는 `V0~V8` 인데 **어디에도 뜻이 적혀 있지 않다.** 우리 라벨은 한글 8종이다.
      2026-09-09 에 013453 [별표 1] 을 파싱해 **조문이 대응표를 준다**는 것이 드러났다 —
      제1호 질병 · 제2호 의약품 · 제3호 건기식 · 제4호 거짓과장 · 제5호 기만 ·
      제6호 비방 · 제7호 부당비교 · 제8호 사행심·음란 (D-158 「조문이 확정 라벨」).
      🚨 그런데 우리 `후기_체험기_기만` 은 **법에서 제5호의 목**이고, 제8호는 우리 목록에 없다.
      → `docs/ohb/결정요청_2026-09-09_밤_5건.md` ⑤ 가 그 판정이다.

   둘 다 정해지기 전에 넣으면 **되돌리기 어려운 잘못된 라벨**이 DB 에 남는다.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
REGISTRY = ROOT / "data_sources.yaml"

USE_CODE = {"U1": "U1_train", "U2": "U2_rag", "U3": "U3_cite", "U4": "U4_deploy"}
FLAGS = {
    "BY",
    "NC",
    "SA",
    "PII",
    "TOS",
    "GATED",
    "NOREDIST",
    "NOSTORE",
    "QUERYLOG",
    "PREAPPROVAL",
    "NOTRAIN",
}


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or (
        "postgresql://copylane:copylane@localhost:5432/copylane"
    )


def _sources() -> dict[str, dict]:
    raw = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["sources"]
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def load_sources(cur, dry: bool) -> tuple[int, list[str]]:
    """🚨 CHECK 둘을 못 지나는 소스는 **넣지 않고 이름을 돌려준다.**

    - `ck_source_four_eyes` — `decided_by <> reviewed_by`, 둘 다 있어야 한다
    - `ck_source_by_attr`   — `attribution IS NOT NULL OR grade = 'G1'`

    조용히 건너뛰면 「46개가 다 들어갔다」로 읽힌다. 이름을 들고 나온다.
    """
    ok, skipped = 0, []
    for sid, s in sorted(_sources().items()):
        dec, rev = s.get("decided_by"), s.get("reviewed_by")
        attr = s.get("attribution")
        if not dec or not rev or dec == rev:
            skipped.append(f"{sid} (2인 확인 미완: {dec!r}/{rev!r})")
            continue
        if not attr and s.get("grade") != "G1":
            skipped.append(f"{sid} (attribution 없음 · grade={s.get('grade')})")
            continue
        if dry:
            ok += 1
            continue
        cur.execute(
            """
            INSERT INTO source (source_id, name, publisher, url, layer, grade, cost, value,
                                access, license, attribution, robots_checked_at,
                                grade_decided_by, grade_reviewed_by, grade_decided_at,
                                grade_evidence_url, note)
            VALUES (%(id)s,%(name)s,%(pub)s,%(url)s,%(layer)s,%(grade)s,%(cost)s,%(value)s,
                    %(access)s,%(lic)s,%(attr)s,%(robots)s,%(dec)s,%(rev)s,%(dat)s,%(ev)s,%(note)s)
            ON CONFLICT (source_id) DO UPDATE SET
                name=EXCLUDED.name, license=EXCLUDED.license, attribution=EXCLUDED.attribution,
                grade=EXCLUDED.grade, grade_reviewed_by=EXCLUDED.grade_reviewed_by
            """,
            {
                "id": sid,
                "name": s.get("name", sid),
                "pub": s.get("org") or "미상",
                "url": s.get("url"),
                "layer": s.get("layer", ""),
                "grade": s.get("grade"),
                "cost": s.get("cost", "unknown"),
                "value": s.get("value", "X"),
                "access": s.get("access"),
                "lic": s.get("license"),
                "attr": attr,
                "robots": s.get("robots_checked_at"),
                "dec": dec,
                "rev": rev,
                "dat": s.get("decided_at"),
                "ev": s.get("evidence_url"),
                "note": s.get("caution"),
            },
        )
        for flag in s.get("constraints") or []:
            if flag not in FLAGS:
                raise SystemExit(f"🚨 {sid}: 알 수 없는 제약 플래그 {flag!r} — flag_t 에 없다")
            cur.execute(
                "INSERT INTO source_constraint (source_id, flag) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING",
                (sid, flag),
            )
        for axis, val in (s.get("use") or {}).items():
            if axis not in USE_CODE:
                raise SystemExit(f"🚨 {sid}: 알 수 없는 용도 축 {axis!r}")
            cur.execute(
                "INSERT INTO source_use (source_id, use_code, allowed) VALUES (%s,%s,%s) "
                "ON CONFLICT (source_id, use_code) DO UPDATE SET allowed=EXCLUDED.allowed",
                (sid, USE_CODE[axis], val == "allow"),
            )
        ok += 1
    return ok, skipped


def load_fragments(cur, dry: bool) -> int:
    """파생물 단위로 프래그먼트를 만든다 (D-18 — 판정 단위는 FRAGMENT).

    🚨 소스마다 하나가 아니다. 같은 소스에서 나온 것도 성격이 다르면 등급이 갈린다.
    """
    frags = [
        ("law_go_kr:article", "law_go_kr", "조문 본문", "G3"),
        ("law_go_kr:annex", "law_go_kr", "별표", "G3"),
        ("law_go_kr:prec", "law_go_kr", "판례", "G3"),
        ("law_go_kr:decc", "law_go_kr", "재결례", "G3"),
        ("mfds_hf_ingredient:api", "mfds_hf_ingredient", "기능성 원료인정", "G3"),
        ("mfds_hf_individual:api", "mfds_hf_individual", "개별인정형", "G3"),
        ("ftc_decisions_body:dict", "ftc_decisions_body", "금지표현 사전", "G2"),
    ]
    known = set(_sources())
    n = 0
    for fid, sid, kind, grade in frags:
        if sid not in known:
            raise SystemExit(f"🚨 {fid}: 원천 {sid!r} 가 레지스트리에 없다 (D-15)")
        if not dry:
            cur.execute(
                "INSERT INTO fragment (fragment_id, source_id, frag_type, grade) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (fragment_id) DO NOTHING",
                (fid, sid, kind, grade),
            )
        n += 1
    return n


def _jsonl(name: str) -> list[dict]:
    p = DERIVED / name
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_manifest(cur, dry: bool) -> int:
    """수집 원장을 그대로 옮긴다 (규약 3). 같은 sha256 은 다시 넣지 않는다."""
    p = ROOT / "data" / "manifest.jsonl"
    if not p.exists():
        return 0
    known = set(_sources())
    rows = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("source_id") not in known:
            continue
        if not dry:
            cur.execute(
                "INSERT INTO collect_manifest (source_id, fetched_at, url, sha256, bytes, rows) "
                "SELECT %s,%s,%s,%s,%s,%s WHERE NOT EXISTS "
                "(SELECT 1 FROM collect_manifest WHERE sha256 = %s AND sha256 IS NOT NULL)",
                (
                    r["source_id"],
                    r.get("fetched_at"),
                    r.get("url"),
                    r.get("sha256"),
                    r.get("bytes"),
                    r.get("rows"),
                    r.get("sha256"),
                ),
            )
            # 🚨 **보낸 수가 아니라 들어간 수를 센다** (D-149 · 2026-09-09).
            #    ⛔ 첫 실행에서 19,980 이라 찍었는데 DB 에는 10,849 였다. 같은 sha256 을
            #       다시 받은 것(규약 4)이라 안 들어가는 게 맞지만, **출력은 그걸 몰랐다.**
            rows += cur.rowcount
        else:
            rows += 1
    return rows


def load_documents(cur, dry: bool) -> int:
    """법령·별표를 문서로 넣는다. 조문·별표 노드는 [P5] 청킹이 `chunk` 로 만든다."""
    seen: set[str] = set()
    n = 0
    for r in _jsonl("law_article.jsonl"):
        doc_id = f"law:{r['파일'].replace('.xml', '')}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        if not dry:
            cur.execute(
                "INSERT INTO document (doc_id, fragment_id, doc_type, title, law_id, source_ref) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (doc_id) DO NOTHING",
                (
                    doc_id,
                    "law_go_kr:article",
                    "법령",
                    r["법령"],
                    r["파일"].split("_")[1],
                    r["파일"],
                ),
            )
        n += 1
    norm_dir = DERIVED / "law_norm"
    for p in sorted(norm_dir.glob("*.jsonl")) if norm_dir.exists() else []:
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        if not rows:
            continue
        doc_id = f"annex:{p.stem}"
        if not dry:
            cur.execute(
                "INSERT INTO document (doc_id, fragment_id, doc_type, title, law_id) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (doc_id) DO NOTHING",
                (doc_id, "law_go_kr:annex", "별표", rows[0]["annex_title"], rows[0]["law_id"]),
            )
        n += 1
    return n


def load_dict(cur, dry: bool) -> int:
    """금지표현 사전 (D-155). 🚨 `violation_type` 은 **비워 둔다** — V0~V8 대응이 미판정이다."""
    n = 0
    for r in _jsonl("banned_terms.jsonl"):
        if not dry:
            cur.execute(
                "INSERT INTO dict_entry (fragment_id, dict_kind, term, law_ref, exact_match) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (dict_kind, term) DO NOTHING",
                (
                    "ftc_decisions_body:dict",
                    "금지표현",
                    r["term"],
                    "; ".join(r.get("근거") or []),
                    bool(r.get("단독판정")),
                ),
            )
        n += 1
    return n


def load_product_fact(cur, dry: bool) -> int:
    """2층 적법라벨 — 인정받은 기능성 문구."""
    kinds = {
        "mfds_hf_ingredient": ("FNCLTY_CN", "APLC_RAWMTRL_NM", "DAY_INTK_CN", "고시형"),
        "mfds_hf_individual": ("PRIMARY_FNCLTY", "RAWMTRL_NM", "DAY_INTK_LOWLIMIT", "개별인정형"),
    }
    n = 0
    for r in _jsonl("hf_api_labels.jsonl"):
        src = r["원천"]
        claim_f, ing_f, intake_f, kind = kinds[src]
        claim = (r.get(claim_f) or "").strip()
        ingredient = (r.get(ing_f) or "").strip()
        if not claim or not ingredient:
            continue  # 문구가 없는 행은 2층 라벨이 아니다
        if not dry:
            cur.execute(
                "INSERT INTO product_fact (fragment_id, ingredient, recognition_no, "
                "functional_claim, daily_intake, caution, category, recog_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    f"{src}:api",
                    ingredient,
                    r.get("인정번호"),
                    claim,
                    r.get(intake_f),
                    r.get("IFTKN_ATNT_MATR_CN"),
                    "건강기능식품",
                    kind,
                ),
            )
        n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="파생물 → 거버넌스 DB 적재")
    ap.add_argument("--dry-run", action="store_true", help="세기만 한다 — DB 에 붙지 않는다")
    args = ap.parse_args()

    if args.dry_run:

        class _Null:
            def execute(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
                raise AssertionError("dry-run 에서는 실행하지 않는다")

        cur = _Null()
        n_src, skipped = load_sources(cur, True)
        print(f"  source            {n_src:>6}  (건너뜀 {len(skipped)})")
        for s in skipped:
            print(f"      ⛔ {s}")
        print(f"  fragment          {load_fragments(cur, True):>6}")
        print(f"  collect_manifest  {load_manifest(cur, True):>6}")
        print(f"  document          {load_documents(cur, True):>6}")
        print(f"  dict_entry        {load_dict(cur, True):>6}")
        print(f"  product_fact      {load_product_fact(cur, True):>6}")
        print("\n🔴 golden_sample 은 넣지 않는다 — split_t 에 test_sentence 가 없고")
        print("   violation_t(V0~V8) 대응표가 미판정이다 (결정요청 ⑤).")
        return 0

    try:
        import psycopg  # 🚨 --dry-run 은 DB 없이 돌아야 한다 — 여기서 들여온다

        conn = psycopg.connect(dsn())
    except Exception as e:  # noqa: BLE001
        print(
            f"🚨 DB 에 못 붙었다 — {e}\n   `uv run python launcher.py db-up` 을 먼저 돌린다.",
            file=sys.stderr,
        )
        return 1

    with conn, conn.cursor() as cur:
        n_src, skipped = load_sources(cur, False)
        print(f"  source            {n_src:>6}  (건너뜀 {len(skipped)})")
        for s in skipped:
            print(f"      ⛔ {s}")
        print(f"  fragment          {load_fragments(cur, False):>6}")
        print(f"  collect_manifest  {load_manifest(cur, False):>6}")
        print(f"  document          {load_documents(cur, False):>6}")
        print(f"  dict_entry        {load_dict(cur, False):>6}")
        print(f"  product_fact      {load_product_fact(cur, False):>6}")
    print("\n🔴 golden_sample 은 넣지 않았다 — 판정 둘이 걸려 있다 (결정요청 ⑤).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
