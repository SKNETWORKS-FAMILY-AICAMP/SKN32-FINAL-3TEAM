"""`collect.law_api._parse` — 법제처 응답이 XML 규격을 벗어날 때 (2026-09-06).

🚨 **거버넌스 게이트가 아니다.** `gate` 마크를 붙이지 않는다 (D-89).

왜 생겼나 — 법제처가 XML 안에 **HTML 엔티티**를 섞어 보낸다.

    <키워드>식품등의 표시&middot;광고에 관한 법률</키워드>

XML 이 정의하는 엔티티는 `&amp; &lt; &gt; &quot; &apos;` 다섯뿐이라 `&middot;` 에서
파서가 죽는다. 그러면 `_parse` 가 `None` 을 돌려주고, `search()` 가 그것을
**「OC 가 승인되지 않았거나 값이 틀렸다」로 단정**했다 — 키는 멀쩡한데.
바로 앞뒤 질의가 성공하는 상황에서 다음 사람은 키를 재발급하며 시간을 쓴다.

🚨 이 모듈이 지키는 불변식은 둘이다.
   ① 규격 밖 엔티티가 섞여도 **읽어낸다.** 다만 `data/raw/` 에 저장되는 것은
      언제나 서버가 준 **원문 바이트**다 (D-117 「매칭은 정규화문, 보관은 원문」).
   ② 못 읽었을 때 **원인을 단정하지 않는다.** 응답을 보여주고 판단은 사람에게 남긴다.
"""

from __future__ import annotations

import pytest

from collect.law_api import _parse, _parse_failure

HEAD = '<?xml version="1.0" encoding="UTF-8"?>'

#: 실측 응답 (2026-09-06). `·` 가 든 질의를 보내면 서버가 `&middot;` 로 되돌려준다.
MIDDOT_BODY = (
    f"{HEAD}<PrecSearch><target>prec</target>"
    "<키워드>식품등의 표시&middot;광고에 관한 법률</키워드>"
    "<section>evtNm</section><totalCnt>0</totalCnt><page>1</page></PrecSearch>"
).encode()

#: 엔티티가 없는 정상 응답 — 회귀 방지용 대조군
PLAIN_BODY = (
    f"{HEAD}<PrecSearch><target>prec</target><키워드>표시광고</키워드>"
    "<section>bdyText</section><totalCnt>1293</totalCnt></PrecSearch>"
).encode()

#: 인증 실패 시 오는 HTML. 🚨 `<meta>`·`<br>` 이 닫히지 않아 XML 로는 안 읽힌다.
HTML_BODY = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>오류</title></head>'
    "<body><br><p>인증 실패</body></html>"
).encode()


def test_middot_is_parsed() -> None:
    """🚨 수정 전에는 여기서 `None` 이 온다 — 이 테스트가 잡는 것이 그 자리다."""
    root = _parse(MIDDOT_BODY)
    assert root is not None
    assert root.findtext("키워드") == "식품등의 표시·광고에 관한 법률"


def test_middot_body_is_not_mutated() -> None:
    """정규화는 파싱 직전에만 한다 — 원문 바이트는 그대로다 (D-117).

    `collect()` 가 `store.save_raw()` 에 넘기는 것이 이 `body` 이므로,
    `data/raw/` 에는 서버가 준 그대로가 남아야 한다.
    """
    before = bytes(MIDDOT_BODY)
    _parse(MIDDOT_BODY)
    assert before == MIDDOT_BODY
    assert b"&middot;" in MIDDOT_BODY


def test_plain_xml_still_parses() -> None:
    """엔티티가 없는 응답은 경로가 바뀌지 않는다."""
    root = _parse(PLAIN_BODY)
    assert root is not None
    assert root.findtext("totalCnt") == "1293"


def test_xml_predefined_entities_survive() -> None:
    """XML 5대 엔티티는 건드리지 않는다 — 원문 의미가 바뀌면 안 된다."""
    body = f"{HEAD}<r><a>A&amp;B</a><b>&lt;태그&gt;</b></r>".encode()
    root = _parse(body)
    assert root is not None
    assert root.findtext("a") == "A&B"
    assert root.findtext("b") == "<태그>"


@pytest.mark.parametrize(
    ("entity", "expected"),
    [("&middot;", "·"), ("&nbsp;", "\xa0"), ("&deg;", "°"), ("&hellip;", "…")],
)
def test_other_html_entities(entity: str, expected: str) -> None:
    """`&middot;` 만 고치지 않는다 — 오늘 본 것 하나만 막으면 내일 다른 것에 또 죽는다."""
    root = _parse(f"{HEAD}<r><a>가{entity}나</a></r>".encode())
    assert root is not None
    assert root.findtext("a") == f"가{expected}나"


def test_unknown_entity_still_fails() -> None:
    """모르는 엔티티는 **고치지 않고 실패한다.** 추측해서 값을 지어내지 않는다."""
    assert _parse(f"{HEAD}<r><a>가&nosuchthing;나</a></r>".encode()) is None


def test_html_response_is_not_xml() -> None:
    """인증 실패 HTML 은 여전히 읽히지 않아야 한다."""
    assert _parse(HTML_BODY) is None


# ─────────────────────────────────────────────────────────────
#  진단 메시지 — 원인을 단정하지 않는다
# ─────────────────────────────────────────────────────────────


def test_failure_message_names_oc_only_for_html() -> None:
    """HTML 이 왔을 때만 OC 를 의심한다. 그때도 「~일 수 있다」로 남긴다."""
    msg = _parse_failure(HTML_BODY)
    assert "OC" in msg
    assert "HTML" in msg


def test_failure_message_does_not_blame_oc_for_broken_xml() -> None:
    """🚨 이것이 이 수정의 핵심이다.

    깨진 XML 은 키 문제가 아니다. 그런데 예전 메시지는 두 경우를 같은 문장으로
    처리해 **키를 의심하게 만들었다.** 응답 앞부분을 보여주고 끝낸다.
    """
    body = f"{HEAD}<r><a>가&nosuchthing;나</a></r>".encode()
    msg = _parse_failure(body)
    assert "OC" not in msg
    assert "nosuchthing" in msg


def test_failure_message_is_single_line_and_bounded() -> None:
    """응답 전문을 쏟지 않는다 — 오류 메시지가 산출물로 커밋되는 자리가 있다 (probe.py)."""
    body = f"{HEAD}<r>{'가' * 5000}&nosuchthing;</r>".encode()
    msg = _parse_failure(body)
    assert "\n" not in msg
    assert len(msg) < 400


def test_real_responses_never_reach_the_failure_path() -> None:
    """양성 대조 — 2026-09-06 에 실측한 두 응답은 **둘 다 읽힌다.**

    §9 의 교훈이다. 이 단언이 없으면 위 진단 테스트들이 통과한다는 사실만으로
    「고쳐졌다」고 읽힐 수 있다. 진단이 좋아진 것과 파싱이 되는 것은 다른 일이다.
    """
    for body in (MIDDOT_BODY, PLAIN_BODY):
        assert _parse(body) is not None, body[:80]
