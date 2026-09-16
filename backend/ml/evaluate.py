"""Metrics, calibration and threshold selection.

Why these metrics: the classes are imbalanced (UCI is 13% spam), so accuracy alone is
misleading. We report precision/recall/F1 at an explicit threshold, threshold-free ranking
quality (ROC-AUC and PR-AUC - PR-AUC is the more informative one under imbalance), and,
because the API exposes a probability, calibration: Brier score, expected calibration error
(ECE, 15 equal-width bins) and the reliability table behind it.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, classification_report,
                             confusion_matrix, f1_score, precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)


def reliability(y: np.ndarray, p: np.ndarray, n_bins: int = 15) -> tuple[float, list[dict]]:
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    table, ece = [], 0.0
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        conf, acc = float(p[m].mean()), float(y[m].mean())
        ece += m.mean() * abs(conf - acc)
        table.append({"bin": f"{edges[b]:.2f}-{edges[b + 1]:.2f}", "n": int(m.sum()),
                      "mean_predicted": round(conf, 4), "fraction_positive": round(acc, 4)})
    return round(float(ece), 4), table


def binary_metrics(y, score, threshold: float = 0.5, probabilistic: bool = True) -> dict:
    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    pred = (s >= threshold).astype(int)
    both = len(set(y.tolist())) > 1
    out = {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "threshold": round(float(threshold), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "false_positive_rate": round(float(((pred == 1) & (y == 0)).sum() / max(1, (y == 0).sum())), 4),
        "roc_auc": round(float(roc_auc_score(y, s)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y, s)), 4) if both else None,
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }
    if probabilistic:
        ece, table = reliability(y, s)
        out.update({"brier": round(float(brier_score_loss(y, s)), 4), "ece": ece, "reliability": table})
    else:
        out.update({"brier": None, "ece": None})
    return out


def choose_threshold(y, score, strategy: str = "max_f1", target: float | None = None) -> float:
    """Pick a decision threshold on VALIDATION data.

    max_f1          threshold maximising F1
    min_recall      highest threshold whose recall >= target   (catch at least X% of scams)
    min_precision   lowest threshold whose precision >= target (when we say Scam, be right)
    """
    y = np.asarray(y).astype(int)
    s = np.asarray(score, dtype=float)
    prec, rec, thr = precision_recall_curve(y, s)
    prec, rec = prec[:-1], rec[:-1]  # align with thr
    if len(thr) == 0:
        return 0.5
    if strategy == "max_f1":
        f1 = 2 * prec * rec / np.clip(prec + rec, 1e-12, None)
        return float(thr[int(np.argmax(f1))])
    if strategy == "min_recall":
        ok = np.where(rec >= target)[0]
        return float(thr[ok[-1]]) if len(ok) else float(thr[0])
    if strategy == "min_precision":
        ok = np.where(prec >= target)[0]
        return float(thr[ok[0]]) if len(ok) else float(thr[-1])
    raise ValueError(strategy)


def selective_band(y, p, threshold: float, target_accuracy: float = 0.98,
                   widths=(0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3)) -> dict:
    """Smallest band [t-d, t+d] such that predictions OUTSIDE it reach target accuracy.
    Probabilities inside the band are treated as 'insufficient confidence'. If even the widest
    band misses the target, the widest band is returned with target_met=False."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    chosen = None
    for d in widths:
        lo, hi = max(0.0, threshold - d), min(1.0, threshold + d)
        outside = (p < lo) | (p > hi) if d > 0 else np.ones_like(p, dtype=bool)
        if not outside.any():
            continue
        acc = float(((p[outside] >= threshold).astype(int) == y[outside]).mean())
        chosen = {"low": round(lo, 4), "high": round(hi, 4), "coverage": round(float(outside.mean()), 4),
                  "selective_accuracy": round(acc, 4), "target_accuracy": target_accuracy,
                  "target_met": acc >= target_accuracy, "max_half_width_tried": widths[-1]}
        if acc >= target_accuracy:
            break
    return chosen or {"low": threshold, "high": threshold, "coverage": 1.0, "selective_accuracy": None,
                      "target_accuracy": target_accuracy}


def category_metrics(y_true, y_pred, labels: list[str]) -> dict:
    labels = [c for c in labels if c in set(y_true) | set(y_pred)]
    rep = classification_report(y_true, y_pred, labels=labels, output_dict=True, zero_division=0)
    return {
        "n": len(y_true),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_f1": round(float(rep["macro avg"]["f1-score"]), 4),
        "per_class": {k: {m: round(float(v), 4) for m, v in rep[k].items()} for k in labels},
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
    }
