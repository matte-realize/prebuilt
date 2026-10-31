import pytest


from eval.fit import classify, fit_accuracy, scored_window
from eval.metrics import with_fit

TH = {"press_below": 0.0, "slip": [0.1, 0.3], "loose_above": 0.4}


def test_classify_bands_and_gaps():
    assert [classify(c, TH) for c in (-0.1, 0.2, 0.5)] == ["press", "slip", "loose"]
    assert classify(0.03, TH) == "press" and classify(0.08, TH) == "slip"   # gap below slip: nearer class
    assert classify(0.33, TH) == "slip" and classify(0.38, TH) == "loose"   # gap above slip
    assert scored_window(TH) == pytest.approx((-0.2, 0.6))


def _row(kind, nominal, mean, measured, arm="networked"):
    return {"round": 1, "site": "resin", "arm": arm, "kind": kind, "nominal_d": nominal,
            "mean": mean, "measured_d": measured, "truth": measured}


def test_fit_accuracy_scores_only_near_boundary_pairs():
    preds = [
        _row("pin", 5.0, 5.00, 5.00),
        _row("hole", 5.2, 5.20, 5.20),   # nominal clearance 0.2: scored, slip == slip
        _row("hole", 5.1, 5.15, 4.95),   # 0.1: scored, predicted slip (0.15) vs measured press (-0.05)
        _row("hole", 7.0, 7.00, 7.00),   # 2.0: outside the window, not scored
    ]
    (row,) = fit_accuracy(preds, {"resin": TH}, {"resin": "resin"})
    assert (row["fit_pairs"], row["fit_acc"]) == (2, 0.5)
    scores = [{"round": 1, "site": "resin", "arm": "networked", "mae": 0.1}]
    merged = with_fit(scores, preds, {"resin": TH}, {"resin": "resin"})
    assert merged[0]["fit_acc"] == 0.5 and merged[0]["fit_acc_truth"] == 0.5
    assert with_fit(scores, preds, None, {"resin": "resin"}) == scores
