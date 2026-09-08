"""`preprocess.mfds_guide` — 해설서 3분류 → 우리 유형 **후보** 매핑 (D-151).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

이 파일이 지키는 것은 하나다 — **없는 확신을 만들지 않는다.**
해설서 3분류가 우리 6종을 뭉치므로, 하나로 확정하면 홀드아웃이 자기 채점이 된다 (D-40).
"""

from __future__ import annotations

from preprocess.hwp import Cell, Table
from preprocess.mfds_guide import CANDIDATES, REGIME, block_of, extract  # noqa: F401
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
