from __future__ import annotations

import json

import pytest

from app.contracts import Violation
from app.encoder import (
    EncoderCandidate,
    EncoderPrediction,
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


def test_graph_treats_encoder_candidates_as_hold(monkeypatch) -> None:
    from app import graph

    prediction = EncoderPrediction(
        scores={Violation.거짓_과장: 0.9},
        candidates=(EncoderCandidate(Violation.거짓_과장, 0.9, 0.65),),
    )
    monkeypatch.setattr(graph, "encoder_predict", lambda _: prediction)

    result = graph.judge({"sents": ["근거 없는 과장 문구"], "encoder_enabled": True})
    sentence = result["sentences"][0]

    assert sentence.verdict.value == "hold"
    assert sentence.hold_reason.value == "low_conf"
    assert sentence.violations == [Violation.거짓_과장]
    assert result["encoder_used"] is True
