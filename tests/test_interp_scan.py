"""1차 법령해석 계측 (`preprocess/interp_scan.py`) — 그물이 무엇을 줍고 무엇을 안 줍나.

🚨 거버넌스 게이트가 아니다 — 계측 모듈의 동작 확인이다. 원문 파일은 읽지 않는다(가짜 필드로 부른다).
"""

from __future__ import annotations

from preprocess import SCANNERS, interp_scan


def _f(**kw: str) -> dict[str, str]:
    base = {"안건명": "", "질의요지": "", "회답": "", "이유": "", "관련법령": ""}
    base.update(kw)
    return base


def test_부당광고_조항과_호를_우리_유형으로_옮긴다() -> None:
    c = interp_scan.classify(
        _f(
            관련법령="식품 등의 표시ㆍ광고에 관한 법률  제8조(부당한 표시 또는 광고행위의 금지)",
            질의요지="제품 광고에 ‘면역력 강화로 감기 예방’ 문구를 써도 되나요?",
            회답="제8조제1항제1호에 따라 질병의 예방·치료에 효능이 있는 것으로 인식할 우려가 있어 광고할 수 없습니다.",
        )
    )
    assert c["조항"] == ["식품표시광고법 제8조"]
    assert c["문구수"] == 1 and c["호유형"] == ["질병_예방치료_표방"]
    assert c["결론"] == "불가"


def test_낫표의_법령명은_문구로_세지_않는다() -> None:
    c = interp_scan.classify(_f(질의요지="「식품 등의 표시·광고에 관한 법률」 적용 대상인가요?"))
    assert c["문구수"] == 0


def test_절차_질의는_그물에_안_걸린다() -> None:
    c = interp_scan.classify(
        _f(
            안건명="수입신고 대상 여부",
            질의요지="물병 수입신고 대상인가요?",
            관련법령="수입식품안전관리 특별법",
        )
    )
    assert not c["조항"] and not c["광고어"]


def test_계측표에_등록돼_있다() -> None:
    assert SCANNERS["mfds_cgm_expc"] == "preprocess.interp_scan"
