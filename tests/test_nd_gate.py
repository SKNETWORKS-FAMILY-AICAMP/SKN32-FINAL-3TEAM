"""변경금지(ND) 게이트 — 파생 데이터셋에 ND 소스의 행이 들어오지 못한다 (2026-09-25 · 팀장 판정 (가) · D-110).

🔴 막는 것
   ① ND 소스(공공누리 제3·4유형 — 첫 사례 `mfds_cosmetic_faq_2025`)의 행이 골든셋 · 사전 · 주입 · 평가셋 · 라벨 시트로 가는 것
   ② 원천을 적지 않은 행이 검사를 조용히 지나가는 것 (D-220)
   ③ 파생 데이터셋을 쓰는 새 모듈이 게이트를 부르지 않은 채 들어오는 것 — 아래 `WRITERS` / `EXEMPT` 에 분류해야 한다
🚨 `U1: deny` 를 ND 로 읽지 않는다 — 그 칸은 「평가 전용」 뜻으로도 쓰였다(D-155 사례집).
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from collect import registry

pytestmark = pytest.mark.gate

ROOT = pathlib.Path(__file__).resolve().parents[1]

FAKE = {
    "sources": {
        "nd_src": {"grade": "G3", "constraints": ["BY", "ND"]},
        "ok_src": {"grade": "G3", "constraints": ["BY"]},
        "eval_only": {"grade": "G3", "constraints": ["BY"], "use": {"U1": "deny"}},
    }
}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_load", lambda: FAKE)


def test_ND_행이_있으면_멈춘다(fake: None) -> None:
    rows = [{"원천": "ok_src"}, {"provenance": "nd_src"}]
    with pytest.raises(registry.RegistryError, match="nd_src 1행"):
        registry.assert_derivable(rows, who="t")


def test_목록_칸_출처도_본다(fake: None) -> None:
    with pytest.raises(registry.RegistryError, match="변경금지"):
        registry.assert_derivable([{"출처": ["ok_src", "nd_src"]}], who="t")


def test_원천이_없는_행은_멈추고_default_로_적을_수_있다(fake: None) -> None:
    with pytest.raises(registry.RegistryError, match="원천을 적지 않은 행이 1건"):
        registry.assert_derivable([{"문구": "x"}], who="t")
    assert registry.assert_derivable([{"문구": "x"}], who="t", default="ok_src") == 1
    with pytest.raises(registry.RegistryError, match="변경금지"):
        registry.assert_derivable([{"문구": "x"}], who="t", default="nd_src")


def test_U1_deny_는_ND_가_아니다(fake: None) -> None:
    """🚨 D-155 — 사례집은 U1 deny 인데 사전으로 학습에 든다. 이 게이트는 그 길을 막지 않는다."""
    assert registry.assert_derivable([{"원천": "eval_only"}], who="t") == 1


def test_레지스트리에_없는_원천은_멈춘다(fake: None) -> None:
    with pytest.raises(registry.RegistryError, match="data_sources.yaml 에 없다"):
        registry.assert_derivable([{"원천": "모르는_소스"}], who="t")


def test_레지스트리의_ND_소스는_학습이_닫혀_있다() -> None:
    raw = yaml.safe_load((ROOT / "data_sources.yaml").read_text(encoding="utf-8"))["sources"]
    nd = {
        k: v for k, v in raw.items() if isinstance(v, dict) and "ND" in (v.get("constraints") or [])
    }
    assert "mfds_cosmetic_faq_2025" in nd, (
        "🔴 공공누리 제3유형 소스에 ND 가 없다 (2026-09-25 팀장 판정 (가))"
    )
    opened = [k for k, v in nd.items() if (v.get("use") or {}).get("U1") != "deny"]
    assert not opened, f"🔴 ND 인데 U1 이 열렸다: {opened}"


# ── ③ 파생 데이터셋을 쓰는 모듈의 분류 ─────────────────────────────────────────────
#: 게이트를 **부르는** 모듈 — 파생 데이터셋(골든셋 · 사전 · 주입 · 평가셋 · 라벨/판독 시트 · 전사)을 쓴다
WRITERS = {
    "preprocess/golden.py",
    "preprocess/inject.py",
    "preprocess/dictionary.py",
    "preprocess/guide_label.py",
    "scripts/label_round.py",
    "scripts/guide_statute_round.py",
    "scripts/casebook2021_sheet.py",
}
#: 게이트를 부르지 않는 모듈과 그 이유 — 🚨 새 모듈이 아래 탐지에 걸리면 어느 쪽인지 **정하고** 적는다
EXEMPT = {
    # 원천 하나의 추출기 — 원문 레코드를 낸다. 라벨 파생은 위 WRITERS 가 입력에서 막는다 ·
    # `--sheet` 는 런처가 ND 소스에서 거부한다(`launcher.extract`)
    "preprocess/mfds_casebook.py": "원천 하나의 추출기",
    "preprocess/mfds_guide.py": "원천 하나의 추출기",
    "preprocess/mfds_hf.py": "원천 하나의 추출기",
    "preprocess/mfds_press.py": "원천 하나의 추출기",
    "preprocess/ftc_extract.py": "원천 하나의 추출기",
    "preprocess/hf_api.py": "원천 하나의 추출기",
    "preprocess/law_norm.py": "법령 [별표] 파서 — 원문 노드",
    "preprocess/evasion_scan.py": "센다 — 데이터셋을 쓰지 않는다",
    "preprocess/ftc_reason_probe.py": "표본 탐침 — 의결서(ftc) 전용",
    "preprocess/ftc_triage.py": "의결서(ftc) 전용 분류",
    "preprocess/mask.py": "마스킹 도구",
    "preprocess/split.py": "문서 id 만 쓴다 — 글은 golden 이 물질화하고 거기서 막는다",
    "scripts/label_merge.py": "사람이 채운 시트를 합친다 — 시트는 WRITERS 가 만들 때 막았다",
    "scripts/label_sheet.py": "시트 ↔ CSV 왕복 — 시트는 WRITERS 가 만들 때 막았다",
    "scripts/derived_manifest.py": "원장 기록",
    "scripts/build_pdf.py": "문서 출력",
    "scripts/extract_rationale.py": "레지스트리 생성물",
    "scripts/gen_registry.py": "레지스트리 생성물",
    "scripts/raw_mirror.py": "원문 사본",
    "scripts/review_sheet.py": "2인 확인 검토표",
}
_WRITES = re.compile(r'open\("w"|\.write_text\(')
_DATASET = re.compile(r"golden|label|banned|evalset|inject")


def test_파생_데이터셋을_쓰는_모듈은_분류되어_있다() -> None:
    found = set()
    for d in ("preprocess", "scripts"):
        for p in sorted((ROOT / d).glob("*.py")):
            t = p.read_text(encoding="utf-8")
            if _WRITES.search(t) and _DATASET.search(t):
                found.add(p.relative_to(ROOT).as_posix())
    loose = sorted(found - WRITERS - set(EXEMPT))
    assert not loose, (
        f"🔴 파생 데이터셋을 쓸 수 있는데 분류가 없다 — WRITERS 또는 EXEMPT(이유) 에 적는다: {loose}"
    )
    assert not WRITERS & set(EXEMPT)


@pytest.mark.parametrize("path", sorted(WRITERS))
def test_WRITERS_는_게이트를_부른다(path: str) -> None:
    assert "registry.assert_derivable(" in (ROOT / path).read_text(encoding="utf-8"), (
        f"🔴 {path} 가 변경금지 게이트를 부르지 않는다"
    )


def test_런처는_ND_소스의_시트를_거부한다() -> None:
    t = (ROOT / "launcher.py").read_text(encoding="utf-8")
    assert "reg.no_derivatives(source)" in t
