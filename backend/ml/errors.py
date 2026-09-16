"""Error analysis: dump the most confident false positives / false negatives with the
tokens (n-gram features) that pushed each prediction, for a linear model."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .models import linear_coef


def top_tokens(feats, coef: np.ndarray, X_row, k: int = 6, sign: int = 1) -> list[str]:
    names = feats.get_feature_names_out()
    row = X_row.tocoo()
    contrib = [(names[j].split("__", 1)[-1], float(coef[j] * v)) for j, v in zip(row.col, row.data)]
    contrib.sort(key=lambda t: -sign * t[1])
    return [f"{n!r}:{c:+.2f}" for n, c in contrib[:k] if sign * c > 0]


def dump_errors(path: Path, feats, model, rows: list[dict], p: np.ndarray, threshold: float,
                top_k: int = 25) -> dict:
    y = np.array([r["label_binary"] for r in rows])
    pred = (p >= threshold).astype(int)
    fp = [i for i in np.argsort(-p) if y[i] == 0 and pred[i] == 1][:top_k]
    fn = [i for i in np.argsort(p) if y[i] == 1 and pred[i] == 0][:top_k]
    coef = linear_coef(model)
    X = feats.transform([rows[i]["text"] for i in fp + fn])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["error_type", "p_scam", "threshold", "source", "category", "text", "top_tokens"])
        for n, i in enumerate(fp + fn):
            kind = "false_positive" if n < len(fp) else "false_negative"
            toks = top_tokens(feats, coef, X[n], sign=1 if kind == "false_positive" else -1) if coef is not None else []
            w.writerow([kind, round(float(p[i]), 4), round(threshold, 4), rows[i]["source"],
                        rows[i]["category"] or "", rows[i]["text"], " ".join(toks)])
    return {"file": path.name, "false_positives_total": int(((pred == 1) & (y == 0)).sum()),
            "false_negatives_total": int(((pred == 0) & (y == 1)).sum()), "dumped": len(fp) + len(fn)}
