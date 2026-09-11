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
import collections
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
        # 🔴 골든셋의 판정 단위 (2026-09-10 · D-18). ⛔ 없어서 `golden_sample.fragment_id`
        #    NOT NULL 을 채울 수 없었다 — 「막는 것 넷」 중 하나였다.
        #    🚨 같은 소스라도 성격이 다르면 등급이 갈린다. 의결서 인용 광고 문구는 G2 다
        #    (40자 상한 · NOREDIST 로 다루는 조각 · D-133).
        ("ftc_decisions_body:golden", "ftc_decisions_body", "의결서 인용 광고 문구", "G2"),
        ("mfds_casebook:golden", "mfds_casebook", "사례집 인용표현", "G2"),
        ("mfds_hf_ingredient_board:approved", "mfds_hf_ingredient_board", "승인 기능성 문구", "G3"),
        # 🚨 주입본은 **우리 생성물**이지만 원본이 승인 문구라 계보를 그쪽에 둔다 (D-71).
        ("mfds_hf_ingredient_board:injected", "mfds_hf_ingredient_board", "규칙 주입 합성문", "G3"),
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


#: 🚨 `--allow-missing` 이 켜졌는가. 모듈 전역이라 `_jsonl` 이 인자 없이 본다.
ALLOW_MISSING = False

#: 🔴 없으면 **적재가 0행이 되는** 입력들. 이름을 여기 적어 두는 것이 계약이다.
REQUIRED = {
    "law_article.jsonl": "uv run python -m preprocess.law_article --dump",
    "banned_terms.jsonl": "uv run python launcher.py golden --write",
    "hf_api_labels.jsonl": "uv run python -m preprocess.hf_api --dump",
}


def _jsonl_at(p: pathlib.Path, how: str) -> list[dict]:
    """경로를 직접 받는 판. 🔴 없으면 멈춘다 — `_jsonl` 과 같은 계약이다."""
    if not p.exists():
        if not ALLOW_MISSING:
            raise SystemExit(
                f"🔴 {p} 가 없다 — 이대로 적재하면 그 테이블이 **0행인 채 성공**한다.\n"
                f"  먼저: {how}\n"
                "  🚨 일부러 비운 채 돌리려면 --allow-missing 을 붙인다."
            )
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _jsonl(name: str, *, required: bool = True) -> list[dict]:
    """🔴 **없으면 멈춘다** (2026-09-10 · D-72 fail-closed).

    ⛔ 종전에는 없으면 빈 리스트를 돌려줬다. 그래서 `document 0 / dict_entry 0 /
       product_fact 0` 이 **오류도 경고도 없이 「정상 완료」로** 찍혔다 —
       원장에는 `document 32 · product_fact 1,250` 이라 적혀 있는데도.
    🚨 ENUM 값에는 `SystemExit` 을 던지면서 입력 부재에는 침묵하는 것이
       이 파일 docstring 의 fail-closed 원칙과 정면으로 어긋났다.
    ★ `--allow-missing` 은 **일부러** 비운 채 돌릴 때만 쓴다 (새 기기 첫 적재 등).
    """
    p = DERIVED / name
    if not p.exists():
        if required and not ALLOW_MISSING:
            raise SystemExit(
                f"🔴 {p} 가 없다 — 이대로 적재하면 그 테이블이 **0행인 채 성공**한다.\n"
                f"  먼저: {REQUIRED.get(name, '해당 전처리를 돌린다')}\n"
                "  🚨 일부러 비운 채 돌리려면 --allow-missing 을 붙인다."
            )
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
                # 🔴 **`event` 를 넣는다** (2026-09-10). ⛔ 안 넣어서 전부 기본값 `'fetch'` 였다 —
                #    스키마가 `fetch/skip/delete` 를 받게 해 뒀는데 **skip·delete 이력이 소실**됐다.
                #    ★ 원장 줄이 `supersedes` 를 들고 있으면 새 판으로 저장된 것이다.
                "INSERT INTO collect_manifest "
                "(source_id, fetched_at, url, sha256, bytes, rows, event) "
                "SELECT %s,%s,%s,%s,%s,%s,%s WHERE NOT EXISTS "
                "(SELECT 1 FROM collect_manifest WHERE sha256 = %s AND sha256 IS NOT NULL)",
                (
                    r["source_id"],
                    r.get("fetched_at"),
                    r.get("url"),
                    r.get("sha256"),
                    r.get("bytes"),
                    r.get("rows"),
                    "fetch",
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
    if not norm_dir.exists() and not ALLOW_MISSING:
        raise SystemExit(
            f"🔴 {norm_dir} 가 없다 — 별표가 통째로 빠진 채 document 가 채워진다.\n"
            "  먼저: uv run python -m preprocess.law_norm --write   🚨 --dump 가 아니다\n"
            "  🚨 일부러 비운 채 돌리려면 --allow-missing 을 붙인다."
        )
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


def load_dict(cur, dry: bool) -> tuple[int, int]:
    """금지표현 사전 (D-155). 반환 — (행 수, 유형이 붙은 수).

    🔄 **`violation_type` 을 채운다** (2026-09-10 · D-178). 종전에는 「V0~V8 대응이
       미판정」이라 비워 뒀는데, 라벨이 곧 타입이 되면서 대응이 필요 없어졌다.
    🚨 **유형이 하나인 항목만** 채운다. `dict_entry.violation_type` 은 단수인데
       실측 106종이 여러 유형에 걸린다 — 하나를 고르면 그건 판정이고,
       **낱말이 라벨을 감당할 만큼 크지 않다는 뜻**이다 (D-155). 비워 두는 것이 사실에 맞다.
    """
    n = typed = 0
    for r in _jsonl("banned_terms.jsonl"):
        kinds = r.get("유형") or []
        vt = kinds[0] if len(kinds) == 1 else None
        typed += vt is not None
        if not dry:
            cur.execute(
                "INSERT INTO dict_entry "
                "(fragment_id, dict_kind, term, law_ref, exact_match, violation_type) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (dict_kind, term) DO UPDATE SET "
                "  violation_type = EXCLUDED.violation_type, "
                "  law_ref = EXCLUDED.law_ref, exact_match = EXCLUDED.exact_match",
                (
                    "ftc_decisions_body:dict",
                    "금지표현",
                    r["term"],
                    "; ".join(r.get("근거") or []),
                    bool(r.get("단독판정")),
                    vt,
                ),
            )
        n += 1
    return n, typed


#: 🔴 **정본 축만 여기 들어온다** (2026-09-11 · D-185). `product_fact` 는 「**인정받은** 기능성
#:    문구」다 — 업체 신고 현황(I-0040)의 표시 문구는 인정 사실이 아니므로 넣지 않는다.
#:    ⛔ 종전에는 둘 다 넣었다. 그래서 `2024-19` 의 「인지기능 개선에 도움을 **줌**」이
#:       — 정본은 「**노화로 인해 저하된** 인지기능 개선에 도움을 **줄 수 있음**」인데 —
#:       **적법 근거로 적재돼 있었다.** 우리가 잡으려는 위반을 적법이라 가르치는 자리였다.
#:    ★ 그 문구들은 사라지지 않는다. `hf_display_claims.jsonl` 에 **경계 사례 후보**로 남는다.
PRODUCT_FACT_SOURCES = {
    "mfds_hf_individual": ("PRIMARY_FNCLTY", "RAWMTRL_NM", "DAY_INTK_LOWLIMIT", "개별인정형"),
}


def load_product_fact(cur, dry: bool) -> int:
    """2층 적법라벨 — **인정받은** 기능성 문구. 🚨 표시 문구는 여기 오지 않는다 (D-185)."""
    kinds = PRODUCT_FACT_SOURCES
    n = 0
    skipped: dict[str, int] = {}
    seen: dict[str, set[tuple[str, str]]] = {}
    for r in _jsonl("hf_api_labels.jsonl"):
        src = r["원천"]
        if src not in kinds:
            # 🚨 조용히 거르지 않는다 — 몇 행을 왜 뺐는지 부른 쪽이 안다 (D-153)
            skipped[src] = skipped.get(src, 0) + 1
            continue
        claim_f, ing_f, intake_f, kind = kinds[src]
        claim = (r.get(claim_f) or "").strip()
        ingredient = (r.get(ing_f) or "").strip()
        if not claim or not ingredient:
            continue  # 문구가 없는 행은 2층 라벨이 아니다
        if not dry:
            cur.execute(
                "INSERT INTO product_fact (fragment_id, ingredient, recognition_no, "
                "functional_claim, daily_intake, caution, category, recog_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                # 🔴 **멱등** (2026-09-10). ⛔ 종전에는 ON CONFLICT 가 없어
                #    두 번 돌리면 1,250 → 2,500 이었다. 이 파일 docstring 이
                #    「모든 적재가 ON CONFLICT 로 간다」고 적어 뒀는데 여기만 빠졌다.
                "ON CONFLICT ON CONSTRAINT uq_product_fact DO UPDATE SET "
                "  recognition_no = EXCLUDED.recognition_no, "
                "  daily_intake = EXCLUDED.daily_intake, caution = EXCLUDED.caution",
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
        seen.setdefault(f"{src}:api", set()).add((ingredient, claim))
        n += 1
    for src, cnt in sorted(skipped.items()):
        print(
            f"    ⬜ {src} {cnt}행은 product_fact 에 넣지 않았다 — 표시 문구는 인정이 아니다 (D-185)"
        )
    if not dry:
        n -= _retire_product_fact(cur, seen)
    return n


def _retire_product_fact(cur, seen: dict[str, set[tuple[str, str]]]) -> int:
    """🔴 **이번 덤프에 없는 옛 문구 행을 거둔다** (2026-09-11 · D-185 ②).

    ⛔ 실측 사고 — `page_0003` 의 판을 정본으로 승격했더니 제2022-12호(가자추출물)의
       문구가 「관절 및 연골」 하나에서 「관절 및 연골 + 다리 부기」 둘로 **고쳐졌는데**,
       `uq_product_fact` 가 `(fragment_id, ingredient, functional_claim, recog_kind)` 라
       **문구가 다르면 다른 행**이라 옛 문구가 그대로 남았다. 보낸 447 인데 표에 448 이었다.
    🚨 `mfds_hf_ingredient:api` 554행을 손으로 DELETE 한 것과 **같은 부류**다 —
       적재기가 「안 넣을 뿐 지우지 않는」 자리는 판정이 바뀔 때마다 고아를 만든다.

    ★ **정본 축은 최신을 따른다** (D-185 ②). 저장소가 정본이면 DB 도 정본을 따라야 한다.
    🚨 지우는 것은 **이 함수가 방금 넣은 fragment 안에서만**이고, 무엇을 지웠는지 찍는다.
       `product_fact` 는 파생물이라 언제든 재생성되지만, **말없이 지우지는 않는다** (D-153).
    """
    gone = 0
    for fid, keys in sorted(seen.items()):
        cur.execute(
            "SELECT ingredient, functional_claim FROM product_fact WHERE fragment_id = %s",
            (fid,),
        )
        stale = [(i, c) for i, c in cur.fetchall() if (i, c) not in keys]
        for ing, claim in stale:
            cur.execute(
                "DELETE FROM product_fact WHERE fragment_id = %s AND ingredient = %s "
                "AND functional_claim = %s",
                (fid, ing, claim),
            )
            print(f"    🔄 거둠 {fid} · {ing[:24]} · {claim[:36]}")
        gone += len(stale)
    if gone:
        print(f"    🔄 옛 문구 {gone}행을 거뒀다 — 원천이 문구를 고친 자리다 (D-185 ②)")
    return gone


#: 골든셋 행 → 프래그먼트. 🚨 `(provenance, origin)` 두 축으로 갈린다 (D-18).
GOLDEN_FRAGMENT = {
    ("ftc_decisions_body", "real"): "ftc_decisions_body:golden",
    ("mfds_casebook", "real"): "mfds_casebook:golden",
    ("mfds_hf_ingredient_board", "approved"): "mfds_hf_ingredient_board:approved",
    ("mfds_hf_ingredient_board", "injected"): "mfds_hf_ingredient_board:injected",
}


def load_golden(cur, dry: bool) -> tuple[int, collections.Counter]:
    """골든셋을 적재한다 (2026-09-10 · D-178).

    ⛔ 2026-09-09~10 내내 「판정 둘이 걸려 있다」로 비어 있던 자리다. 실제로 막던 것은 **넷**이었다 —
       `split_t` 에 `test_sentence` 없음 · `violation_t` 대응표 미정 ·
       `risk` NOT NULL 인데 산출물에 그 필드가 없음 · `fragment_id` 에 대응이 없음.
       앞의 둘만 풀어도 안 들어갔다.
    🚨 `risk` 는 넣지 않는다 — 시험지는 위험도를 담는 곳이 아니다. 판정 시 계산한다 (D-09).
    """
    rows = _jsonl_at(
        DERIVED / "golden" / "golden.jsonl", "uv run python launcher.py golden --write"
    )
    stat: collections.Counter = collections.Counter()
    n = 0
    for r in rows:
        key = (r["provenance"], r["origin"])
        fid = GOLDEN_FRAGMENT.get(key)
        if fid is None:
            raise SystemExit(
                f"🔴 골든셋 행의 계보에 프래그먼트가 없다 — {key}\n"
                "  🚨 등급·재배포 판정 단위가 없는 행은 넣지 않는다 (D-18).\n"
                "     `GOLDEN_FRAGMENT` 와 `load_fragments()` 에 함께 등재한다."
            )
        stat[r["split"]] += 1
        stat[f"unit:{r['unit']}"] += 1
        if not dry:
            cur.execute(
                "INSERT INTO golden_sample "
                "(sample_id, fragment_id, text, unit, violations, origin, rule_id, "
                " provenance, redistributable, split) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (sample_id) DO UPDATE SET "
                "  text = EXCLUDED.text, unit = EXCLUDED.unit, "
                "  violations = EXCLUDED.violations, split = EXCLUDED.split",
                (
                    r["id"],
                    fid,
                    r["text"],
                    r["unit"],
                    r["labels"],
                    r["origin"],
                    r.get("rule_id"),
                    r["provenance"],
                    r["redistributable"],
                    r["split"],
                ),
            )
        n += 1
    return n, stat


def main() -> int:
    ap = argparse.ArgumentParser(description="파생물 → 거버넌스 DB 적재")
    ap.add_argument("--dry-run", action="store_true", help="세기만 한다 — DB 에 붙지 않는다")
    ap.add_argument(
        "--allow-missing",
        action="store_true",
        help="🚨 입력이 없어도 0행으로 적재한다 — **일부러** 비운 채 돌릴 때만",
    )
    args = ap.parse_args()
    global ALLOW_MISSING  # noqa: PLW0603 — CLI 플래그를 모듈 전역으로 내린다
    ALLOW_MISSING = args.allow_missing

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
        n_dict, n_typed = load_dict(cur, True)
        print(f"  dict_entry        {n_dict:>6}  (유형 붙은 것 {n_typed})")
        print(f"  product_fact      {load_product_fact(cur, True):>6}")
        n_gold, gstat = load_golden(cur, True)
        print(f"  golden_sample     {n_gold:>6}")
        for k in sorted(gstat):
            print(f"      {k:18} {gstat[k]:>6}")
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
        n_dict, n_typed = load_dict(cur, False)
        print(f"  dict_entry        {n_dict:>6}  (유형 붙은 것 {n_typed})")
        print(f"  product_fact      {load_product_fact(cur, False):>6}")
        n_gold, gstat = load_golden(cur, False)
        print(f"  golden_sample     {n_gold:>6}")
        for k in sorted(gstat):
            print(f"      {k:18} {gstat[k]:>6}")
    print("\n★ 골든셋이 들어갔다 (D-178). 🚨 `risk` 는 비워 둔다 — 시험지는 위험도를 담는 곳이")
    print("   아니다. 판정 시 sanction_rule · v_risk_lookup 으로 계산한다 (D-09 래칫).")
    print("⬜ `violation_article`(라벨 ↔ 조문 대응)은 아직 비어 있다 — 별표1 파싱에서 채운다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
