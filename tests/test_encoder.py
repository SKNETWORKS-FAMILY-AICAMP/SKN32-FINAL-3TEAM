from __future__ import annotations

import json

import pytest

from app.contracts import Violation
from app.encoder import (
    EncoderUnavailable,
    LabelScheme,
    load_label_scheme,
    select_candidates,
)


def test_label_scheme_uses_model_order_and_thresholds(tmp_path) -> None:
    (tmp_path / "label_scheme.json").write_text(
        json.dumps(
            {
                "label_list": ["거짓_과장", "의약품_오인"],
                "label_thresholds": {"거짓_과장": 0.65, "의약품_오인": 0.1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    scheme = load_label_scheme(tmp_path)

    assert scheme.labels == (Violation.거짓_과장, Violation.의약품_오인)
    assert scheme.thresholds[Violation.거짓_과장] == 0.65
    assert scheme.thresholds[Violation.의약품_오인] == 0.1


def test_label_scheme_rejects_missing_threshold(tmp_path) -> None:
    (tmp_path / "label_scheme.json").write_text(
        '{"label_list": ["거짓_과장"], "label_thresholds": {}}', encoding="utf-8"
    )

    with pytest.raises(EncoderUnavailable, match="threshold"):
        load_label_scheme(tmp_path)


def test_candidates_use_each_labels_threshold() -> None:
    scheme = LabelScheme(
        labels=(Violation.거짓_과장, Violation.의약품_오인),
        thresholds={Violation.거짓_과장: 0.65, Violation.의약품_오인: 0.1},
    )

    candidates = select_candidates(scheme, [0.64, 0.11])

    assert [(c.violation, c.threshold) for c in candidates] == [(Violation.의약품_오인, 0.1)]


# 🔄 2026-09-29 — main 병합(D-266)으로 `judge()`가 법령별 팬아웃 구조로 다시 짜이면서
#    `encoder_enabled` 상태 칸과 `judge()` 안의 직접 `encoder_predict` 호출이 없어졌다.
#    인코더 연결은 이제 `encode()` 노드(app/graph.py, 현재 스텁) 자리다 — 거기 배선할 때
#    이 자리에 새 그래프 통합 테스트를 다시 쓴다. `EncoderCandidate`/`EncoderPrediction`은
#    위 테스트들이 이미 이 모듈 자체(라벨 스킴 · 후보 선별)를 커버한다.
