"""`preprocess.mfds_guide` — 해설서 3분류 → 우리 유형 **후보** 매핑 (D-151).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 하나다 — **없는 확신을 만들지 않는다.**
해설서 3분류가 우리 6종을 뭉치므로, 하나로 확정하면 홀드아웃이 자기 채점이 된다 (D-40).
"""

from __future__ import annotations

from preprocess.hwp import Cell, Table
from preprocess.mfds_guide import (  # noqa: F401
    CANDIDATES,
    MASK_FIELDS,
    REGIME,
    block_of,
    extract,
    masked,
)
from scripts.collect import CANDIDATE_TYPES, VIOLATION_TYPES


def test_every_candidate_is_a_known_type() -> None:
    """🔴 후보로 적는 유형은 **우리 목록에 실재해야** 한다 — 오타 하나가 유령 라벨을 만든다."""
    known = set(VIOLATION_TYPES) | set(CANDIDATE_TYPES)
    for src, cands in CANDIDATES.items():
        unknown = [c for c in cands if c not in known]
        assert not unknown, f"{src}: 목록에 없는 유형 {unknown}"


def test_bangbang_is_in_the_list() -> None:
    """⛔ `비방광고` 는 표시광고법 §3①**4호**인데 목록에서 빠져 있었다 (2026-09-08 추가).

    `ftc_extract` 는 이미 뽑고 있었다 — **뽑는 쪽과 인정하는 쪽이 어긋난 채로** 지나갔다.
    """
    assert "비방광고" in CANDIDATE_TYPES


def test_merged_labels_stay_merged() -> None:
    """🔴 뭉친 것은 **여럿으로** 남는다. 하나로 줄이면 그 순간 거짓말이 된다."""
    assert len(CANDIDATES["질병의 예방 치료, 의약품 혼동, 건강기능식품 혼동"]) == 3
    assert len(CANDIDATES["거짓ㆍ과장ㆍ기만"]) == 3  # 후기_체험기_기만 포함 (D-139 실측)
    assert len(CANDIDATES["부당한 비교ㆍ비방"]) == 2


def test_regime_is_recorded() -> None:
    """🚨 사전심의 자료다 — 현행(자율심의)과 섞이면 3층으로 새어 들어간다 (D-138)."""
    assert REGIME["연도"] == 2017 and "사전심의" in REGIME["심의제도"]


def test_block_takes_the_nearest_lead() -> None:
    """앞 문단이 표의 정체다. 🚨 **가장 가까운 것**이 이긴다 — 앞엣것이 남아 있다."""
    lead = ["심의시 '삭제'판정을 받은 문구", "심의시 '수정' 판정을 받은 문구"]
    assert block_of(lead) == "수정"
    assert block_of(["부당한 표시ㆍ광고에 해당할 우려가 있는 key-word"]) == "키워드"
    assert block_of(["아무 말"]) == "미상"


def test_table_check_is_enforced_before_extract() -> None:
    """🔴 어긋난 표에서 라벨을 만들지 않는다 — 파싱 오류는 데이터에 박히면 못 되돌린다."""
    t = Table(rows=2, cols=1, row_cells=(1, 1), cells=[Cell(0, 0, 1, 1)])
    assert t.check()  # 선언 (1,1) 인데 셀이 하나뿐이다


def test_masking_keeps_order_and_count() -> None:
    """🔴 `--sheet` 가 마스킹 사본에서 뽑는다 — 그래도 **같은 seed 면 같은 행**이어야 한다 (D-54).

    마스킹이 순서나 개수를 바꾸면 재현 조건이 깨진다. 그래서 여기를 고정한다.
    """
    rows = [{"종류": "위반문구", "원천라벨": "가", "문구": f"문구{i}"} for i in range(5)]
    out, _ = masked(rows)
    assert len(out) == len(rows)
    assert [r["원천라벨"] for r in out] == [r["원천라벨"] for r in rows]


def test_masking_is_applied_to_the_sheet_fields() -> None:
    """⛔ 2026-09-08 까지 `--sheet` 만 원문을 썼다. `data/derived/` 에 떨어지면 D-17 대상이다.

    🚨 그때도 **깨끗해 보였다** — 이 원천의 상호는 3,037문구 중 2건뿐이라 표본에 안 걸렸다.
       **오늘 깨끗한 것은 표본 운이지 규칙이 아니다.**
    """
    out, changed = masked([{"문구": "㈜oo과 전략적 MOU를 체결했습니다"}])
    assert out[0]["문구"] != "㈜oo과 전략적 MOU를 체결했습니다"
    assert changed["문구"] == 1


def test_mask_fields_cover_every_text_that_leaves() -> None:
    """🚨 나가는 글은 전부 지나야 한다 — `원천라벨` 에도 원천의 표기가 들어온다."""
    assert set(MASK_FIELDS) == {"문구", "수정문구", "원천라벨"}
