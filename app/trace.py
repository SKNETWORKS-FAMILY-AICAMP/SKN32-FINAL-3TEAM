"""app/trace.py — 판정 노드마다 **무엇을 냈는지** 콘솔에 한 덩어리씩 찍는다 · 🆕 2026-10-15 (ksr).

  .env 에 COPYLANE_TRACE=on → 서버 재시작 → 검수 한 번 → 서버 콘솔에 노드별 줄이 나온다
  uv run python -m scripts.trace_judge "면역력 증진에 도움을 줄 수 있습니다." --category 식품   # 서버 없이 한 번

★ 왜 있나 — 검수 결과가 이상할 때 **사전 · 인코더 · 판정 로직 중 어디서 그렇게 됐는지**를 가르려고.
  노드 순서대로 split → classify → retrieve → match_dict → encode → law_* → merge_laws → judge → assess_risk
  → premise_branches → doc_rules → 종착 이 찍힌다.
🚨 판정은 사전 적중으로 선다 — 인코더 신호는 `encoder_candidates` 칸에만 실리고 판정(확정 · 보류 · violations)은 그 칸을
   읽지 않는다(`app/graph.py` 모듈 docstring · D-323). 그래서 match_dict 줄이 비었는데 judge 가 위반을 냈다면 로직을 본다.
🔴 문구 원문은 찍지 않는다(보안점검 P1-4) — 문장은 `s0` · `s1` … 과 `mask()` 로만 나온다. 원문이 필요하면
   `scripts/trace_judge.py` 가 **자기 터미널에** 문장 표를 따로 낸다.
⛔ 끄면(기본) `isEnabledFor` 한 번으로 끝난다 — 요약을 만들지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

from app.logging_conf import mask

#: 이 로거 하나다. 레벨은 `setup_logging` 이 스위치(`settings.trace_enabled`)로 정한다 — 켜면 INFO, 끄면 WARNING.
log = logging.getLogger("copylane.trace")


def _f(x: float) -> str:
    return f"{x:.2f}"


def _val(v: Any) -> str:
    return getattr(v, "value", str(v))


def _hits(hits: Any) -> str:
    return ", ".join(f"「{h.term}」→{h.violation_type or '유형없음'}" for h in hits) or "-"


def _sent(s: Any) -> str:
    risk = s.risk.final or s.risk.floor
    enc = ", ".join(f"{_val(c.violation)} {_f(c.confidence)}" for c in s.encoder_candidates) or "-"
    return (
        f"    {s.sent_id} {mask(s.text)}  판정={_val(s.verdict)}"
        + (f"({_val(s.hold_reason)})" if s.hold_reason else "")
        + f"  위반={[_val(v) for v in s.violations] or '-'}"
        + f"  위험도={_val(risk) if risk else '-'}"
        + f"  인코더후보={enc}"
    )


def _lines(key: str, v: Any) -> list[str]:
    """상태 칸 하나를 사람이 읽는 줄로. 모르는 칸은 개수만 적는다."""
    if key == "timings":
        return []
    if key == "sents":
        return [f"  문장 {len(v)}개: " + " · ".join(f"s{i} {mask(t)}" for i, t in enumerate(v))]
    if key == "laws":
        return [f"  적용 법: {list(v)}"]
    if key == "evidence":
        return [
            f"  {e.sent_id} 검색  벡터={'O' if e.vector else 'X'} 어휘={'O' if e.lexical else 'X'} 후보={e.pool}"
            for e in v
        ]
    if key == "dict_scans":
        return [
            f"  {d.sent_id} 사전  {'돌았음' if d.ran else '❌ 안 돌았음(DB 없음)'}"
            f"  적중={_hits(d.hits)}  약한적중={_hits(d.weak)}"
            for d in v
        ]
    if key == "encodings":
        out = []
        for e in v:
            top = sorted(e.scores, key=lambda p: -p[1])[:3]
            out.append(
                f"  {e.sent_id} 인코더[{e.input}]  문턱넘음={list(e.candidates) or '-'}"
                f"  상위={', '.join(f'{t} {_f(p)}' for t, p in top)}"
                + ("  (뒤 잘림)" if e.truncated else "")
            )
        return out or ["  인코더 신호 없음 — 모델 폴더 미설정 · 잠금 밖이면 비어 있다"]
    if key == "law_results":
        out = []
        for r in v:
            arts = {sid: len(a) for sid, a in r.articles}
            hits = {sid: _hits(h) for sid, h in r.dict_hits if h}
            out.append(
                f"  [{r.law}] 본 문장={list(r.sent_ids)}  근거 수={arts}  이 법의 사전 적중={hits or '-'}"
            )
        return out
    if key == "sentences":
        return ["  문장 판정 (이 노드가 적은 것):"] + [_sent(s) for s in v]
    if key == "branches":
        out = []
        for b in v:
            out.append(f"  분기 [{_val(b.premise)}] → {_val(b.outcome)}")
            out += ["  " + _sent(s) for s in b.sentences]
        return out
    if key == "outcome":
        return [f"  ▶ 종착 = {_val(v)}"]
    if key == "certificate":
        return [f"  증명서 {'있음' if v else '없음'}"]
    if isinstance(v, list | tuple | dict):
        return [f"  {key}: {len(v)}개"]
    return [f"  {key}: {type(v).__name__}"]


def node(name: str, out: dict[str, Any], ms: float) -> None:
    """노드 하나가 끝났을 때 `timed` 가 부른다."""
    if not log.isEnabledFor(logging.INFO):
        return
    body: list[str] = []
    for k, v in out.items():
        try:
            body += _lines(k, v)
        except Exception as e:  # noqa: BLE001 — 추적이 판정을 멈추게 하지 않는다
            body.append(f"  {k}: (요약 실패 {type(e).__name__})")
    log.info("── %s (%.0fms)\n%s", name, ms, "\n".join(body) or "  (낸 것 없음)")
