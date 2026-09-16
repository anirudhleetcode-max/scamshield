"""Unit tests for the ML pipeline pieces (no model file needed)."""
import numpy as np
import pytest

from ml.data.schema import Record, dedup_key, validate
from ml.data.synthetic import template_split
from ml.evaluate import binary_metrics, choose_threshold, reliability, selective_band
from ml.preprocess import normalize, quality_signals


def test_reliability_perfectly_calibrated_has_zero_ece():
    p = np.array([0.0] * 50 + [1.0] * 50)
    y = np.array([0] * 50 + [1] * 50)
    ece, table = reliability(y, p)
    assert ece == 0.0 and sum(r["n"] for r in table) == 100


def test_reliability_overconfident_model_has_high_ece():
    p = np.full(100, 0.95)
    y = np.array([1] * 50 + [0] * 50)
    ece, _ = reliability(y, p)
    assert ece == pytest.approx(0.45, abs=1e-6)


def test_binary_metrics_confusion_and_auc():
    y = [0, 0, 1, 1]
    s = [0.1, 0.6, 0.4, 0.9]
    m = binary_metrics(y, s, 0.5)
    assert m["confusion_matrix"] == [[1, 1], [1, 1]]
    assert m["roc_auc"] == 0.75 and m["brier"] is not None
    assert binary_metrics(y, s, 0.5, probabilistic=False)["ece"] is None


def test_threshold_strategies():
    y = np.array([0, 0, 0, 1, 1, 1])
    s = np.array([0.1, 0.2, 0.7, 0.4, 0.8, 0.9])
    assert choose_threshold(y, s, "min_recall", 1.0) == pytest.approx(0.4)
    assert choose_threshold(y, s, "min_precision", 1.0) == pytest.approx(0.8)
    t = choose_threshold(y, s, "max_f1")
    assert 0.1 < t <= 0.8


def test_selective_band_reports_target_miss():
    rng = np.random.default_rng(0)
    p = rng.uniform(0, 1, 500)
    y = (rng.uniform(0, 1, 500) < 0.5).astype(int)  # labels unrelated to p
    band = selective_band(y, p, 0.5, target_accuracy=0.99)
    assert band["target_met"] is False and band["low"] < 0.5 < band["high"]


def test_template_split_is_deterministic_and_disjoint():
    splits = [template_split(i) for i in range(16)]
    assert splits.count("test") == 4 and splits.count("val") == 2
    assert template_split(3) == "test" and template_split(1) == "val" and template_split(0) == "train"


def test_schema_validation_rejects_bad_rows():
    ok = Record(text="hi there", label_binary=0, category=None, source="x", split="train", group="g")
    validate([ok])
    with pytest.raises(ValueError):
        validate([{**ok, "label_binary": 2}])
    with pytest.raises(ValueError):
        validate([{**ok, "category": "made_up"}])
    with pytest.raises(ValueError):
        validate([{**ok, "text": "  "}])
    assert dedup_key("  Hello   WORLD ") == dedup_key("hello world")


def test_quality_signals():
    q = quality_signals("आपका खाता बंद कर दिया जाएगा")
    assert q["non_latin_ratio"] > 0.9
    q = quality_signals("http://bit.ly/abc123")
    assert q["url_ratio"] > 0.7 and q["n_words"] >= 1
    assert quality_signals("")["n_chars"] == 0
    assert len(normalize("ÀB 12")) == 5
