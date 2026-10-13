"""카피 생성 엔진의 오류 둘 — 화면이 「준비 안 됨」과 「실패」를 가른다 (D-147 — 없는 것을 있는 것처럼 그리지 않는다)."""

from __future__ import annotations


class CopyGenOff(Exception):
    """엔진을 쓸 수 없다 — 스위치가 꺼졌거나 키 · 판정 인코더가 없다. 메시지는 화면에 그대로 나간다."""


class CopyGenError(Exception):
    """엔진을 불렀는데 실패했다 — 외부 호출 오류 · 깨진 응답. 🚨 메시지에 키 · 문구를 담지 않는다."""
