"""Static evaluation figures (PNG) for reports: ROC, precision-recall, confusion matrix,
reliability diagram, threshold sweep and risk-coverage.

Needs matplotlib (requirements-ml.txt); the API never imports this module.
Colours: fixed categorical order, so a model keeps its colour in every figure; every line
also has its own dash pattern and a legend entry, so colour is never the only cue.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import precision_recall_curve, roc_curve  # noqa: E402

SERIES = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2", "#ec4647"]
DASHES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1)), (0, (3, 1)), (0, (1, 1)), (0, (8, 2))]
TEXT, TEXT2, GRID = "#191919", "#666666", "#e6e6e6"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 160, "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.edgecolor": TEXT2, "axes.labelcolor": TEXT, "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "lines.linewidth": 2,
})


def _style(names: list[str], fixed: dict[str, int] | None = None) -> dict[str, tuple[str, object]]:
    """Model name -> (colour, dash). `fixed` pins a slot per name so colours never depend on rank."""
    out = {}
    for i, n in enumerate(names):
        k = (fixed or {}).get(n, i) % len(SERIES)
        out[n] = (SERIES[k], DASHES[k])
    return out


def _legend_below(ax, ncol: int = 2):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=ncol, fontsize=8)


def _mark(ax, label: str, x: float, n: int):
    ax.axvline(x, color=TEXT2, linewidth=1, linestyle=DASHES[(n + 1) % len(DASHES)])
    ax.annotate(label, (x, 0.98), xycoords=("data", "axes fraction"), rotation=90, fontsize=7, color=TEXT2,
                ha="right", va="top", xytext=(-2, 0), textcoords="offset points")


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path.name


def roc_pr(y, scores: dict[str, np.ndarray], title: str, path: Path, slots: dict[str, int] | None = None) -> str:
    """Side-by-side ROC and precision-recall curves for several models on one test set."""
    y = np.asarray(y).astype(int)
    st = _style(list(scores), slots)
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2))
    for name, s in scores.items():
        c, d = st[name]
        fpr, tpr, _ = roc_curve(y, s)
        auc = float(np.trapezoid(tpr, fpr))
        a.plot(fpr, tpr, color=c, linestyle=d, label=f"{name} (AUC {auc:.3f})")
        prec, rec, _ = precision_recall_curve(y, s)
        ap = float(-np.sum(np.diff(rec) * prec[:-1]))
        b.plot(rec, prec, color=c, linestyle=d, label=f"{name} (AP {ap:.3f})")
    fx = np.logspace(-3, 0, 100)
    a.plot(fx, fx, color=TEXT2, linewidth=1, linestyle=":", label="chance")
    a.set_xscale("log")
    b.axhline(y.mean(), color=TEXT2, linewidth=1, linestyle=":", label=f"prevalence {y.mean():.2f}")
    a.set(xlabel="False positive rate (log scale)", ylabel="True positive rate (recall)", title=f"ROC - {title}",
          xlim=(1e-3, 1), ylim=(0, 1.01))
    b.set(xlabel="Recall", ylabel="Precision", title=f"Precision-recall - {title}", xlim=(0, 1), ylim=(0, 1.01))
    _legend_below(a)
    _legend_below(b)
    return _save(fig, path)


def confusion(cm: list[list[int]], title: str, path: Path) -> str:
    """2x2 confusion matrix with counts and row-normalised rates (one sequential hue)."""
    cm = np.asarray(cm)
    rates = cm / np.clip(cm.sum(axis=1, keepdims=True), 1, None)
    fig, ax = plt.subplots(figsize=(3.8, 3.4))
    ax.imshow(rates, cmap="Blues", vmin=0, vmax=1)
    ax.grid(False)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]}\n({rates[i, j]:.1%})", ha="center", va="center",
                    color="white" if rates[i, j] > 0.6 else TEXT, fontsize=10)
    ax.set_xticks([0, 1], ["legit", "scam"])
    ax.set_yticks([0, 1], ["legit", "scam"])
    ax.set(xlabel="Predicted", ylabel="Actual", title=title)
    return _save(fig, path)


def reliability(y, probs: dict[str, np.ndarray], title: str, path: Path, n_bins: int = 10,
                slots: dict[str, int] | None = None) -> str:
    """Reliability diagram: mean predicted probability vs observed scam rate per bin."""
    y = np.asarray(y).astype(int)
    st = _style(list(probs), slots)
    edges = np.linspace(0, 1, n_bins + 1)
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    ax.plot([0, 1], [0, 1], color=TEXT2, linewidth=1, linestyle=":", label="perfect calibration")
    for name, p in probs.items():
        idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
        xs, ys = [], []
        for b in range(n_bins):
            m = idx == b
            if m.sum() >= 5:
                xs.append(p[m].mean()); ys.append(y[m].mean())
        c, d = st[name]
        ece = float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean()
                        for b in range(n_bins) if (idx == b).any()))
        ax.plot(xs, ys, color=c, linestyle=d, marker="o", markersize=5, label=f"{name} (ECE {ece:.3f})")
    ax.set(xlabel="Mean predicted P(scam)", ylabel="Observed scam rate", title=title, xlim=(0, 1), ylim=(0, 1))
    _legend_below(ax, 1)
    return _save(fig, path)


def threshold_sweep(sweep: list[dict], marks: dict[str, float], title: str, path: Path) -> str:
    """P / R / F1 vs threshold (left axis is the only axis) + expected cost in a second panel."""
    t = [r["threshold"] for r in sweep]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.8))
    for k, key in enumerate(("precision", "recall", "f1")):
        a.plot(t, [r[key] for r in sweep], color=SERIES[k], linestyle=DASHES[k], label=key)
    b.plot(t, [r["cost"] for r in sweep], color=SERIES[3], linestyle=DASHES[0], label="expected cost / message")
    for ax in (a, b):
        for n, (label, x) in enumerate(marks.items()):
            _mark(ax, label, x, n)
    a.set(xlabel="Model threshold", ylabel="Score", title=f"Threshold sweep - {title}", xlim=(0, 1), ylim=(0, 1.02))
    b.set(xlabel="Model threshold", ylabel="Cost (FN=5, FP=1) per message", title="Expected cost", xlim=(0, 1))
    _legend_below(a, 3)
    _legend_below(b, 1)
    return _save(fig, path)


def risk_coverage(curves: dict[str, list[dict]], title: str, path: Path, chosen: dict[str, float] | None = None,
                  slots: dict[str, int] | None = None) -> str:
    """Selective accuracy as the model abstains on its least-confident messages."""
    st = _style(list(curves), slots)
    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    for name, c in curves.items():
        col, d = st[name]
        ax.plot([r["coverage"] for r in c], [r["selective_accuracy"] for r in c], color=col, linestyle=d, label=name)
    for n, (label, cov) in enumerate((chosen or {}).items()):
        _mark(ax, label, cov, n)
    ax.set(xlabel="Coverage (share of messages answered)", ylabel="Accuracy on answered messages",
           title=title, xlim=(1.0, 0.0))
    _legend_below(ax)
    return _save(fig, path)


def cv_bars(rows: list[dict], metric: str, title: str, path: Path) -> str:
    """Mean +/- std of a CV metric per (model, feature set), horizontal bars, one hue per feature set."""
    feats = list(dict.fromkeys(r["feature_set"] for r in rows))
    models = list(dict.fromkeys(r["model"] for r in rows))
    h = 0.8 / len(feats)
    fig, ax = plt.subplots(figsize=(6.4, 0.6 + 0.9 * len(models)))
    for k, f in enumerate(feats):
        for i, m in enumerate(models):
            r = next((r for r in rows if r["model"] == m and r["feature_set"] == f), None)
            if r is None:
                continue
            y = i + (k - (len(feats) - 1) / 2) * h
            ax.barh(y, r[f"{metric}_mean"], height=h * 0.9, color=SERIES[k], xerr=r[f"{metric}_std"],
                    error_kw={"ecolor": TEXT2, "elinewidth": 1, "capsize": 2},
                    label=f if i == 0 else None)
            ax.text(r[f"{metric}_mean"] + r[f"{metric}_std"] + 0.002, y, f"{r[f'{metric}_mean']:.3f}",
                    va="center", fontsize=7, color=TEXT)
    lo = min(r[f"{metric}_mean"] - r[f"{metric}_std"] for r in rows)
    ax.set_yticks(range(len(models)), models)
    ax.set(xlabel=f"{metric} (5-fold CV, mean +/- std)", title=title, xlim=(max(0, lo - 0.02), 1.0))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8, title="features", title_fontsize=8)
    return _save(fig, path)
