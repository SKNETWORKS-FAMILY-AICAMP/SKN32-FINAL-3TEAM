"""scripts/e2e_review.py — 판정 응답이 **검수 화면까지 그대로 닿는가**를 한 바퀴로 본다 (🆕 2026-10-19 · E2E).

    uv run python scripts/e2e_review.py                       # 실제 DB · 인코더로 (집 기기)
    uv run python scripts/e2e_review.py --fixtures            # 골든 픽스처를 코어 응답으로 끼워 화면만 본다(DB 없이)
    uv run python scripts/e2e_review.py --out build/e2e/e2e_1019.json
    uv run python scripts/e2e_review.py --save-fixtures build/e2e/fixtures   # 실제 응답을 화면 픽스처 꼴로 저장

★ 무엇을 답하나 — 화면 담당이 만든 화면(`app/templates/user/review.html`)에 **실제 응답 꼴이 빠짐없이 그려지는가**
  ① JSON `POST /judge` — 계약(`JudgeResponse`)을 지나는가 · 질문(`fact_check`)에 승인된 질문 글자가 있는가
  ② 화면 `POST /u/judge` — 같은 문구의 화면에 **응답이 가진 것이 다 보이는가**:
     기록 문장과 **분기 문장**의 질문 글자 · 답 버튼(`fact:<종류>:true|false|na`) · 실증 버튼(`subst:*`) · 분기마다 「이 전제라면」 기준 줄
  ③ 답 `POST /u/review/answer` — 질문 하나에 「맞아요」로 답하면 다시 판정되고 그 문장의 질문이 닫히는가(JSON 으로 대조)
🔴 화면은 이 도구가 고치지 않는다 — 어긋남은 「화면에 안 닿음」으로 보고만 한다(화면 소유자 ksr · 병렬작업 계약 §5).
🔴 문구는 우리가 지은 문장이다 — 골든 · 원천 문구를 쓰지 않는다(재배포 제한 · `lse` 훅).
🚨 게이트가 아니다 — 인코더 판 · DB(`data/**` 미커밋)마다 서는 질문이 다르다. 문구마다 「기대한 자리에 닿았는가」가 아니라
   **「응답에 있는 것이 화면에 있는가」** 를 본다 · 기대한 종류가 안 섰으면 「미도달(응답에 없음)」로 따로 센다.
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contracts import (  # noqa: E402
    Answer,
    Category,
    JudgeRequest,
    JudgeResponse,
    ProductContext,
    UserFact,
)

#: (이름, 문구, 품목 · None 이면 모름, 서기를 기대하는 사실 종류 — 기록 · 분기 어디든) — 🚨 기대는 보고용이다(판정 아님)
#: 🔴 이름은 영문 — 픽스처 이름 규칙(`app/api.py` `_FIXTURE_NAME`)과 같아야 `--save-fixtures` 로 저장한 응답을 `/u/preview/<이름>` 으로 연다
SCENARIOS: list[tuple[str, str, str | None, tuple[str, ...]]] = [
    ("cos_function", "이 크림은 피부 미백에 도움을 줍니다.", "화장품", ("기능성_심사",)),
    ("cos_drug", "아토피 피부염을 치료해 주는 크림입니다.", "화장품", ()),
    ("food_function", "피로 회복에 도움을 줍니다.", "식품", ("기능성_표시",)),
    ("food_cert", "HACCP 인증을 받은 공장에서 만들었습니다.", "식품", ("인증",)),
    ("food_patent", "특허받은 공법으로 만들었습니다.", "식품", ("특허",)),
    ("food_nofree", "합성보존료 무첨가 제품입니다.", "식품", ("무첨가_조건",)),
    ("food_disease", "당뇨병 치료에 효과가 있습니다.", "식품", ()),
    ("gen_compare", "다른 회사 제품보다 2배 더 오래갑니다.", "일반상품", ("비교_기준",)),
    ("gen_condition", "지금 가입하면 평생 무료로 이용할 수 있습니다.", "일반상품", ("조건_고지",)),
    ("gen_review", "직접 써 보고 정말 만족한 제품이에요.", "일반상품", ("후기_실재",)),
    ("unk_immune", "면역력 강화에 도움을 줍니다.", None, ()),
    ("unk_caution", "섭취 전 전문가와 상담하세요.", None, ()),
]


@dataclasses.dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _post_form(client: Any, path: str, pairs: list[tuple[str, str]]) -> Any:
    return client.post(
        path,
        content=urlencode(pairs).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _questions(res: JudgeResponse) -> list[tuple[str | None, Any]]:
    """(분기 전제 · 기록이면 None, 문장) — 질문 · 실증 칸이 있는 문장 전부."""
    out: list[tuple[str | None, Any]] = [
        (None, s) for s in res.sentences if s.fact_check or s.substantiation
    ]
    for b in res.branches:
        out += [(b.premise.value, s) for s in b.sentences if s.fact_check or s.substantiation]
    return out


def _asked(res: JudgeResponse) -> list[tuple[str | None, Any]]:
    """화면이 **답 칸을 그려야 하는** 문장 — 화면과 같은 함수(`reasons.question_text`)로 고른다 (D-99).

    ★ 분기가 있는 문구는 유형을 고른 뒤(분기 안)에만 묻는다(화면 규칙) — 기록 문장은 분기가 없을 때만 센다.
    """
    from app import reasons  # noqa: PLC0415

    pool = (
        [(b.premise.value, s) for b in res.branches for s in b.sentences]
        if res.branches
        else [(None, s) for s in res.sentences]
    )
    return [(w, s) for w, s in pool if reasons.question_text(s)]


def _json_checks(res: JudgeResponse) -> list[Check]:
    from app import factcheck as fc  # noqa: PLC0415

    out: list[Check] = []
    for where, s in _questions(res):
        tag = f"{where or '기록'}:{s.sent_id}"
        if s.fact_check:
            q = fc.fact_question(s.fact_check.kind)
            out.append(
                Check(
                    f"질문 글자 승인 · {tag} · {s.fact_check.kind.value}",
                    q != fc.FALLBACK_QUESTION,
                    q,
                )
            )
            out.append(
                Check(
                    f"질문 기준 · 증빙 · {tag}",
                    bool(s.fact_check.criteria) and bool(s.fact_check.accepted_evidence),
                )
            )
    return out


def _html_checks(res: JudgeResponse, page: str) -> list[Check]:
    """응답에 있는 것이 화면에 있는가 — 🔴 Jinja 가 이스케이프하므로 글자를 같은 방식으로 이스케이프해 찾는다."""
    from app import factcheck as fc  # noqa: PLC0415

    out: list[Check] = [Check("화면 200 · 엔진 준비 중 아님", "엔진" not in page or "결과" in page)]
    for b in res.branches:
        out.append(
            Check(
                f"분기 기준 줄 · {b.premise.value}",
                html.escape(b.criteria, quote=False) in page or html.escape(b.criteria) in page,
                b.criteria[:40],
            )
        )
    for where, s in _asked(res):
        tag = f"{where or '기록'}:{s.sent_id}"
        if s.fact_check:
            k = s.fact_check.kind.value
            q = fc.fact_question(s.fact_check.kind)
            out.append(
                Check(
                    f"질문이 화면에 · {tag} · {k}",
                    html.escape(q, quote=False) in page or html.escape(q) in page,
                    q,
                )
            )
            for a in ("true", "false", "na"):
                out.append(Check(f"답 버튼 · {tag} · {k}:{a}", f'value="fact:{k}:{a}"' in page))
        elif s.substantiation:
            for a in ("yes", "no", "na"):
                out.append(Check(f"실증 버튼 · {tag} · {a}", f'value="subst:{a}"' in page))
    return out


def _answer_round(client: Any, text: str, res: JudgeResponse, judge_json: Any) -> list[Check]:
    """첫 사실 질문에 「맞아요」로 답한다 — 화면 200 · 답한 문장의 같은 질문이 닫히는가(JSON 으로 다시 판정해 대조)."""
    qs = [(w, s) for w, s in _asked(res) if s.fact_check]
    if not qs:
        return []
    where, s = qs[0]
    k = s.fact_check.kind
    pairs = [("text", text), ("target", f"1:{s.sent_id}"), ("answer", f"fact:{k.value}:true")]
    if where:
        pairs.append(("premise", where))
    r = _post_form(client, "/u/review/answer", pairs)
    out = [
        Check(
            f"답 화면 200 · {where or '기록'}:{s.sent_id} · {k.value}",
            r.status_code == 200,
            str(r.status_code),
        ),
        Check("답 화면에 「다시 판정」 안내", "답한 내용으로 다시 판정했어요" in r.text),
    ]
    after = judge_json(
        text, ProductContext(facts=[UserFact(text=s.text, kind=k, answer=Answer.예)])
    )
    pool = (
        after.sentences
        if where is None
        else next((b.sentences for b in after.branches if b.premise.value == where), [])
    )
    same = [x for x in pool if x.text == s.text]
    closed = bool(same) and all(not (x.fact_check and x.fact_check.kind is k) for x in same)
    out.append(Check(f"답 뒤 같은 질문이 닫힘 · {k.value}", closed))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--fixtures", action="store_true", help="골든 픽스처를 코어 응답으로 끼운다(DB 없이 화면만)"
    )
    ap.add_argument("--out", default="", help="결과 JSON 경로(비우면 build/e2e/e2e_<시각>.json)")
    ap.add_argument(
        "--save-fixtures",
        default="",
        help="실제 응답(화면이 받는 응답 · 품목 모름)을 이 폴더에 `live_<이름>.json` 으로 저장한다 — 화면 담당에게 넘길 픽스처",
    )
    args = ap.parse_args(argv)

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app import api  # noqa: PLC0415
    from app.routers import user as user_router  # noqa: PLC0415

    client = TestClient(api.app)
    cases: list[tuple[str, str, str | None, tuple[str, ...]]]
    fixed: dict[str, JudgeResponse] = {}
    if args.fixtures:
        cases = []
        for p in sorted(api.FIXTURE_ROOT.joinpath("judge").glob("*.json")):
            r = JudgeResponse.model_validate_json(p.read_text(encoding="utf-8"))
            text = " ".join(s.text for s in r.sentences) or p.stem
            fixed[text] = r
            cases.append((p.stem, text, None, ()))

        def fake(text: str, product: Any = None) -> tuple[str, JudgeResponse]:
            return "ok", fixed[text]

        user_router._core_judge = fake  # type: ignore[assignment]
    else:
        cases = SCENARIOS

    def judge_json(text: str, product: ProductContext | None) -> JudgeResponse:
        if args.fixtures:
            return fixed[text]
        body = JudgeRequest(text=text, product=product or ProductContext()).model_dump(mode="json")
        r = client.post("/judge", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"/judge {r.status_code}: {r.text[:200]}")
        return JudgeResponse.model_validate(r.json())

    report: list[dict[str, Any]] = []
    fails = 0
    for name, text, cat, want in cases:
        t0 = time.perf_counter()
        prod = ProductContext(category=Category(cat)) if cat else None
        row: dict[str, Any] = {"name": name, "text": text, "category": cat}
        try:
            res = judge_json(text, prod)
            # 화면은 품목을 넘기지 않는다(`_core_judge(text)`) — 화면과 같은 응답을 따로 받는다
            res_screen = judge_json(text, None)
        except Exception as e:  # noqa: BLE001 — 문구 하나의 실패를 기록하고 다음으로 간다(삼키지 않고 실패로 센다)
            row["error"] = f"{type(e).__name__}: {e}"
            fails += 1
            report.append(row)
            print(f"🔴 {name} — {row['error']}")
            continue
        page = _post_form(client, "/u/judge", [("text", text), ("op", "judge:1")])
        checks = _json_checks(res) + _json_checks(res_screen)
        checks.append(Check("화면 HTTP 200", page.status_code == 200, str(page.status_code)))
        checks += _html_checks(res_screen, page.text)
        checks += _answer_round(client, text, res_screen, judge_json)
        kinds = {
            s.fact_check.kind.value
            for _, s in _questions(res) + _questions(res_screen)
            if s.fact_check
        }
        missing = [k for k in want if k not in kinds]
        bad = [c for c in checks if not c.ok]
        fails += len(bad)
        row.update(
            outcome=res.outcome.value,
            outcome_screen=res_screen.outcome.value,
            branches_screen=[b.premise.value for b in res_screen.branches],
            kinds=sorted(kinds),
            not_reached=missing,
            checks=[dataclasses.asdict(c) for c in checks],
            ms=round((time.perf_counter() - t0) * 1000),
            response=res.model_dump(mode="json"),
            response_screen=res_screen.model_dump(mode="json"),
        )
        report.append(row)
        if args.save_fixtures and not args.fixtures:
            d = Path(args.save_fixtures)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"live_{name}.json").write_text(
                res_screen.model_dump_json(indent=1) + "\n", encoding="utf-8", newline="\n"
            )
        mark = "✅" if not bad else "🔴"
        print(
            f"{mark} {name} · 품목 {cat or '모름'} · {res.outcome.value} / 화면 {res_screen.outcome.value}"
            f" · 분기 {row['branches_screen']} · 질문 {row['kinds']}"
            + (f" · 미도달 {missing}" if missing else "")
            + f" · 검사 {len(checks) - len(bad)}/{len(checks)} · {row['ms']} ms"
        )
        for c in bad:
            print(f"     ✗ {c.name} {('— ' + c.detail) if c.detail else ''}")

    out = Path(
        args.out
        or f"build/e2e/e2e_{time.strftime('%Y%m%d_%H%M%S')}{'_fixtures' if args.fixtures else ''}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"\n문구 {len(cases)} · 실패 검사 {fails} → {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
