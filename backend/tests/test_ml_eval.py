"""Unit tests for evaluation helpers and the CV splitter (synthetic toy data, no downloads)."""
import numpy as np
import pytest

from ml.evaluate import min_cost_threshold, risk_coverage, threshold_sweep
from ml.tuning import corrected_ttest, cv_splits


def test_min_cost_threshold_follows_cost_asymmetry():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.6, 0.4, 0.9])
    # missed scams expensive -> low threshold (catch the 0.4 scam, accept the 0.6 false alarm)
    t, c = min_cost_threshold(y, s, cost_fn=5, cost_fp=1)
    assert t == pytest.approx(0.4) and c == pytest.approx(0.25)
    # false alarms expensive -> high threshold
    t, c = min_cost_threshold(y, s, cost_fn=1, cost_fp=5)
    assert t == pytest.approx(0.9) and c == pytest.approx(0.25)


def test_min_cost_threshold_perfect_separation_is_free():
    y = np.array([0, 0, 0, 1, 1])
    s = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    t, c = min_cost_threshold(y, s)
    assert c == 0 and 0.3 < t <= 0.8


def test_threshold_sweep_endpoints():
    y = np.array([0, 1, 0, 1])
    s = np.array([0.2, 0.7, 0.4, 0.9])
    sw = threshold_sweep(y, s, n=11)
    assert sw[0]["recall"] == 1.0 and sw[0]["fpr"] == 1.0
    assert sw[-1]["threshold"] == 1.0 and sw[-1]["recall"] == 0.0


def test_risk_coverage_drops_least_confident_first():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.95, 0.05, 0.45, 0.55])  # the two near 0.5 are both wrong
    rc = risk_coverage(y, p, threshold=0.5, n=3)
    assert rc[0]["coverage"] == 1.0 and rc[0]["selective_accuracy"] == 0.5
    assert rc[-1]["selective_accuracy"] == 1.0
    accs = [r["selective_accuracy"] for r in rc]
    assert accs == sorted(accs)


def test_cv_splits_keep_groups_apart_and_stratify():
    rng = np.random.default_rng(0)
    rows = []
    for g in range(60):
        label = g % 3 == 0
        src = "synthetic_in" if g < 40 else "uci_sms_spam"
        for _ in range(rng.integers(1, 6)):
            rows.append({"group": f"g{g}", "label_binary": int(label), "source": src, "text": "x"})
    splits = cv_splits(rows, n_splits=4, seed=1)
    assert len(splits) == 4
    seen = np.zeros(len(rows), dtype=int)
    for tr, te in splits:
        seen[te] += 1
        assert not {rows[i]["group"] for i in tr} & {rows[i]["group"] for i in te}
        rate = np.mean([rows[i]["label_binary"] for i in te])
        assert 0.15 < rate < 0.55
    assert (seen == 1).all()  # every row is held out exactly once


def test_corrected_ttest_is_more_conservative_than_naive():
    d = np.array([0.01, 0.012, 0.009, 0.011, 0.013])
    t, p = corrected_ttest(d, n_train=800, n_test=200)
    naive_t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    assert 0 < t < naive_t
    assert 0 < p < 1
