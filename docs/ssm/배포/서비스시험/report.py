"""서비스 시험 — 결과 파일 작성기 · HTML 도우미 (2026-10-22 · 소성민).

`conftest.py` 가 시험이 끝나면 `write_all()` 을 부른다. 쓰는 파일:

    서비스시험_로그.log      요청 한 줄씩 (conftest 가 시험 중에 쓴다)
    서비스시험_결과.csv      항목별 결과 — 엑셀에서 바로 열린다(utf-8-sig)
    서비스시험_원자료.json   항목 · 요청 · 관찰 전부
    서비스시험_보고서.md     결과보고서 초안 — 요약 · 분류별 · 항목별 · 실패 상세 · 판정 관찰 · 응답 시간

🚨 비밀번호 · 쿠키 값은 처음부터 레코드에 담지 않는다 — 여기서 거를 것이 없게.
"""

from __future__ import annotations

import csv
import html.parser
import json
import pathlib
import statistics

OUTCOME_LABEL = {"passed": "통과", "failed": "실패", "skipped": "건너뜀"}


# ══════════════════════════════════════════════════════════════════════
#  HTML 도우미 — 표준 라이브러리만
# ══════════════════════════════════════════════════════════════════════
class _Forms(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.inputs: list[dict] = []
        self._cur: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            self._cur = {"action": a.get("action", ""), "method": a.get("method", "get").lower(), "fields": []}
            self.forms.append(self._cur)
        elif tag in ("input", "textarea", "select"):
            item = {"name": a.get("name", ""), "value": a.get("value", ""), "type": a.get("type", tag)}
            self.inputs.append(item)
            if self._cur is not None and item["name"]:
                self._cur["fields"].append(item)

    def handle_endtag(self, tag):
        if tag == "form":
            self._cur = None


def parse_forms(page: str) -> list[dict]:
    p = _Forms()
    p.feed(page)
    return p.forms


def find_input(page: str, name: str) -> str | None:
    """이름이 `name` 인 첫 입력 칸의 값. 없으면 `None`."""
    p = _Forms()
    p.feed(page)
    for i in p.inputs:
        if i["name"] == name:
            return i["value"]
    return None


def count_inputs(page: str, name: str) -> int:
    p = _Forms()
    p.feed(page)
    return sum(1 for i in p.inputs if i["name"] == name)


# ══════════════════════════════════════════════════════════════════════
#  집계
# ══════════════════════════════════════════════════════════════════════
def summarize(results: list[dict]) -> dict:
    s = {"total": len(results), "passed": 0, "failed": 0, "skipped": 0}
    for r in results:
        s[r["outcome"]] += 1
    run = s["passed"] + s["failed"]
    s["rate"] = round(100 * s["passed"] / run, 1) if run else 0.0
    return s


def _by_area(results: list[dict]) -> list[tuple[str, dict]]:
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for r in results:
        if r["area"] not in groups:
            order.append(r["area"])
            groups[r["area"]] = []
        groups[r["area"]].append(r)
    return [(a, summarize(groups[a])) for a in order]


def _endpoint_key(row: dict) -> str:
    path = row["path"].split("?", 1)[0]
    return f"{row['method']} {path}"


def _timing_table(results: list[dict]) -> list[dict]:
    """응답 시간 — 같은 요청(방법 + 경로)끼리 묶는다. 연결 실패(상태 없음)는 뺀다."""
    groups: dict[str, list[float]] = {}
    for r in results:
        for q in r["requests"]:
            if q["status"] is None:
                continue
            groups.setdefault(_endpoint_key(q), []).append(q["ms"])
    out = []
    for key, xs in sorted(groups.items(), key=lambda kv: -max(kv[1])):
        out.append(
            {
                "endpoint": key,
                "n": len(xs),
                "avg": round(statistics.fmean(xs)),
                "median": round(statistics.median(xs)),
                "max": round(max(xs)),
            }
        )
    return out


# ══════════════════════════════════════════════════════════════════════
#  파일 쓰기
# ══════════════════════════════════════════════════════════════════════
def _md_cell(v: object) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def write_all(results: list[dict], judge_obs: list[dict], meta: dict, out: pathlib.Path) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "서비스시험_로그.log"]

    # ── CSV ─────────────────────────────────────────────
    p_csv = out / "서비스시험_결과.csv"
    with p_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "분류", "항목", "기대 결과", "결과", "소요(초)", "요청 수", "최대 응답(ms)", "실패·건너뜀 사유", "비고", "시작"])
        for r in results:
            mx = max((q["ms"] for q in r["requests"]), default=0)
            w.writerow(
                [
                    r["id"],
                    r["area"],
                    r["title"],
                    r["expect"],
                    OUTCOME_LABEL[r["outcome"]],
                    f"{r['duration']:.2f}",
                    len(r["requests"]),
                    round(mx),
                    r["message"],
                    " / ".join(r["notes"]),
                    r["started"],
                ]
            )
    paths.append(p_csv)

    # ── JSON ────────────────────────────────────────────
    p_json = out / "서비스시험_원자료.json"
    p_json.write_text(
        json.dumps(
            {"meta": meta, "summary": summarize(results), "results": results, "judge_observations": judge_obs},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths.append(p_json)

    # ── 보고서 (Markdown) ───────────────────────────────
    p_md = out / "서비스시험_보고서.md"
    p_md.write_text(_markdown(results, judge_obs, meta), encoding="utf-8")
    paths.append(p_md)
    return paths


def _markdown(results: list[dict], judge_obs: list[dict], meta: dict) -> str:
    s = summarize(results)
    L: list[str] = []
    a = L.append
    a("# CopyLane 서비스 시험 결과보고서")
    a("")
    a(f"> 자동 작성 · `run.py` · {meta['finished']}")
    a("")
    a("## 1. 시험 개요")
    a("")
    a("| 항목 | 내용 |")
    a("|---|---|")
    a(f"| 대상 주소 | {meta['base']} |")
    a(f"| 시험 일시 | {meta['started']} ~ {meta['finished']} ({meta['elapsed_s']}초) |")
    a("| 시험 방식 | API 호출 자동화 (Python requests + pytest) · 화면 캡처 없음 · 요청별 로그 기록 |")
    a(f"| 회원 로그인 시험 | {('시험 계정 ' + meta['member']) if meta['member'] else '계정 없음 — 건너뜀'} |")
    a(f"| 관리자 화면 | {'허용 IP 에서 실행 — 접근 시험' if meta['admin_open'] else '외부에서 닫혀 있는지 확인'} |")
    a(f"| 고쳐 쓰기(sLLM) | {'포함' if meta['with_llm'] else '제외 (`--with-llm` 으로 포함)'} |")
    a(f"| 실행 환경 | Python {meta['python']} · {meta['platform']} |")
    a("")
    a("## 2. 결과 요약")
    a("")
    a("| 전체 | 통과 | 실패 | 건너뜀 | 통과율(실행분 기준) |")
    a("|:-:|:-:|:-:|:-:|:-:|")
    a(f"| {s['total']} | {s['passed']} | {s['failed']} | {s['skipped']} | {s['rate']}% |")
    a("")
    a("### 분류별")
    a("")
    a("| 분류 | 전체 | 통과 | 실패 | 건너뜀 |")
    a("|---|:-:|:-:|:-:|:-:|")
    for area, g in _by_area(results):
        a(f"| {area} | {g['total']} | {g['passed']} | {g['failed']} | {g['skipped']} |")
    a("")
    a("## 3. 항목별 결과")
    a("")
    a("| ID | 분류 | 시험 항목 | 기대 결과 | 결과 | 소요(초) | 비고 |")
    a("|---|---|---|---|:-:|--:|---|")
    for r in results:
        mark = {"passed": "✅ 통과", "failed": "❌ 실패", "skipped": "➖ 건너뜀"}[r["outcome"]]
        remark = r["message"] if r["outcome"] != "passed" else ""
        if r["notes"]:
            remark = (remark + " / " if remark else "") + " / ".join(r["notes"])
        a(
            f"| {r['id']} | {r['area']} | {_md_cell(r['title'])} | {_md_cell(r['expect'])} | {mark} | "
            f"{r['duration']:.2f} | {_md_cell(remark)} |"
        )
    a("")
    failed = [r for r in results if r["outcome"] == "failed"]
    a("## 4. 실패 상세")
    a("")
    if not failed:
        a("실패한 항목이 없다.")
    for r in failed:
        a(f"### {r['id']} {r['title']}")
        a("")
        a(f"- 분류: {r['area']}")
        a(f"- 기대 결과: {r['expect']}")
        a(f"- 실패 사유: `{r['message']}`")
        if r["requests"]:
            a("- 요청 기록:")
            for q in r["requests"]:
                a(f"  - `{q['method']} {q['path']}` → {q['status'] if q['status'] is not None else '연결 실패'} ({q['ms']:.0f}ms)")
        a("")
    a("## 5. 판정 결과 관찰")
    a("")
    if judge_obs:
        a("합격 여부와 별개로, 시험 문구(지어낸 예시)를 판정한 결과를 그대로 적는다. 판정의 옳고 그름은 사람이 본다.")
        a("")
        a("| ID | 시험 문구 | 의도 | 종착(outcome) | 문장 | 확정 | 보류 | 위반 유형 | 인코더 후보 문장 | 응답(ms) |")
        a("|---|---|---|---|:-:|:-:|:-:|---|:-:|--:|")
        for o in judge_obs:
            a(
                f"| {o['id']} | {_md_cell(o['text'][:40])}{'…' if len(o['text']) > 40 else ''} | {o['intent']} | "
                f"{o['outcome']} | {o['sentences']} | {o['confirmed']} | {o['hold']} | "
                f"{_md_cell(', '.join(o['violations']) or '-')} | {o['encoder_sentences']} | {o['ms']:.0f} |"
            )
        versions = sorted({(o.get("judged_by", ""), o.get("law_version", "")) for o in judge_obs})
        a("")
        for jb, lv in versions:
            a(f"- 판정기 판(`judged_by`): `{jb}` · 법령 판(`law_version`): `{lv}`")
    else:
        a("판정 시험이 돌지 않았다.")
    a("")
    a("## 6. 응답 시간")
    a("")
    a("요청(방법 + 경로)별로 묶었다. 판정 첫 호출은 인코더를 올리느라 느릴 수 있다.")
    a("")
    a("| 요청 | 횟수 | 평균(ms) | 중앙값(ms) | 최대(ms) |")
    a("|---|--:|--:|--:|--:|")
    for t in _timing_table(results):
        a(f"| `{t['endpoint']}` | {t['n']} | {t['avg']} | {t['median']} | {t['max']} |")
    a("")
    a("## 7. 자동 시험 범위 밖 (수동 확인)")
    a("")
    a("- 카피 생성(`/u/generate`) — 외부 GPT 호출 비용이 들어 자동 시험에서 뺐다.")
    a("- 광고 만들기 편집 화면의 스크립트 동작(버튼 · 미리보기) — 브라우저에서 확인한다.")
    if not meta["with_llm"]:
        a("- 지적 문장 고쳐 쓰기(sLLM) — 이번 실행에서 뺐다(`--with-llm` 으로 포함).")
    if not meta["admin_open"]:
        a("- 관리자 화면 기능 — 외부에서는 닫혀 있어 접근 차단만 확인했다(허용 IP 에서 `--admin-open` 으로 실행).")
    a("")
    a("## 8. 결과 파일")
    a("")
    a("- `서비스시험_로그.log` — 요청 한 줄씩(방법 · 경로 · 상태 · 시간 · 크기)")
    a("- `서비스시험_결과.csv` — 항목별 결과(엑셀)")
    a("- `서비스시험_원자료.json` — 위 전부의 원자료")
    a("")
    return "\n".join(L)
