"""Stratified, group-aware cross-validation and hyperparameter search on the TRAIN split.

Why this CV scheme:
  * StratifiedGroupKFold: each fold keeps the scam rate AND the synthetic/UCI mix of the
    training data (stratify key = source + label), and a synthetic template never sits on
    both sides of a fold (group = template id). Plain KFold would leak near-duplicate
    template messages and reward memorising templates.
  * TF-IDF is re-fit inside every fold, so the vocabulary and IDF weights never see the
    held-out fold.
  * The search only uses TRAIN rows. Validation stays untouched for threshold / operating
    point selection, and test is scored once afterwards.

Search space (selected by mean PR-AUC = average precision, which is threshold-free and the
most informative ranking metric under class imbalance):
  feature sets : word 1-2-grams | char_wb 3-5-grams | word + char
  nb           : alpha
  logreg       : C (class_weight=balanced)
  linsvc       : C (class_weight=balanced)
"""
from __future__ import annotations

import itertools
import time

import numpy as np
from joblib import Parallel, delayed
from scipy import stats
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

from .features import DEFAULTS
from .preprocess import WORD_TOKEN_PATTERN, normalize

FEATURE_SETS = ("word", "char", "word+char")
GRID = {
    "nb": {"alpha": [0.01, 0.03, 0.1, 0.3, 1.0]},
    "logreg": {"C": [0.25, 1.0, 4.0, 16.0, 64.0]},
    "linsvc": {"C": [0.03, 0.1, 0.5, 2.0, 8.0]},
}
METRICS = ("pr_auc", "roc_auc", "f1", "precision", "recall")


def make_feature_set(kind: str, params: dict | None = None):
    p = {**DEFAULTS, **(params or {})}
    word = ("word", TfidfVectorizer(preprocessor=normalize, token_pattern=WORD_TOKEN_PATTERN, ngram_range=(1, 2),
                                    min_df=p["word_min_df"], max_features=p["word_max_features"],
                                    sublinear_tf=p["sublinear_tf"], dtype=np.float32))
    char = ("char", TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5),
                                    min_df=p["char_min_df"], max_features=p["char_max_features"],
                                    sublinear_tf=p["sublinear_tf"], dtype=np.float32))
    parts = {"word": [word], "char": [char], "word+char": [word, char]}[kind]
    return FeatureUnion(parts)


def make_classifier(model: str, params: dict, seed: int = 42):
    if model == "nb":
        return MultinomialNB(alpha=params["alpha"])
    if model == "logreg":
        return LogisticRegression(C=params["C"], max_iter=3000, class_weight="balanced", random_state=seed)
    if model == "linsvc":
        return LinearSVC(C=params["C"], class_weight="balanced", random_state=seed)
    raise ValueError(model)


def scores_of(clf, X) -> tuple[np.ndarray, float]:
    """(ranking score, default decision threshold) - SVM has no probabilities."""
    if hasattr(clf, "predict_proba"):
        return clf.predict_proba(X)[:, 1], 0.5
    return clf.decision_function(X), 0.0


def fold_metrics(y, s, threshold) -> dict:
    pred = (s >= threshold).astype(int)
    return {"pr_auc": average_precision_score(y, s), "roc_auc": roc_auc_score(y, s),
            "f1": f1_score(y, pred, zero_division=0), "precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred, zero_division=0)}


def cv_splits(rows: list[dict], n_splits: int = 5, seed: int = 42) -> list[tuple[np.ndarray, np.ndarray]]:
    strat = np.array([f"{r['source']}:{r['label_binary']}" for r in rows])
    groups = np.array([r["group"] for r in rows])
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(cv.split(np.zeros(len(rows)), strat, groups))


def _one_fold(fold: int, kind: str, texts, y, tr, te, grid, feat_params, seed) -> list[dict]:
    feats = make_feature_set(kind, feat_params)
    Xtr = feats.fit_transform([texts[i] for i in tr])
    Xte = feats.transform([texts[i] for i in te])
    out = []
    for model, space in grid.items():
        keys = sorted(space)
        for values in itertools.product(*(space[k] for k in keys)):
            params = dict(zip(keys, values))
            t0 = time.time()
            clf = make_classifier(model, params, seed).fit(Xtr, y[tr])
            s, thr = scores_of(clf, Xte)
            out.append({"fold": fold, "feature_set": kind, "model": model, "params": params,
                        "fit_seconds": time.time() - t0, **fold_metrics(y[te], s, thr)})
    return out


def corrected_ttest(diffs: np.ndarray, n_train: int, n_test: int) -> tuple[float, float]:
    """Nadeau & Bengio (2003) corrected resampled t-test for k-fold CV score differences.
    CV folds share training data, so the naive t-test is over-confident; the correction
    inflates the variance by n_test / n_train."""
    k = len(diffs)
    var = np.var(diffs, ddof=1)
    if var == 0:
        return float("inf") if diffs.mean() else 0.0, 0.0 if diffs.mean() else 1.0
    t = diffs.mean() / np.sqrt((1 / k + n_test / n_train) * var)
    p = 2 * stats.t.sf(abs(t), df=k - 1)
    return float(t), float(p)


def search(rows: list[dict], n_splits: int = 5, seed: int = 42, grid: dict | None = None,
           feature_sets=FEATURE_SETS, feat_params: dict | None = None, n_jobs: int = -1, log=print) -> dict:
    grid = grid or GRID
    texts = [r["text"] for r in rows]
    y = np.array([r["label_binary"] for r in rows])
    splits = cv_splits(rows, n_splits, seed)
    t0 = time.time()
    folds = Parallel(n_jobs=n_jobs)(delayed(_one_fold)(f, kind, texts, y, tr, te, grid, feat_params, seed)
                                    for f, (tr, te) in enumerate(splits) for kind in feature_sets)
    per_fold = [r for chunk in folds for r in chunk]
    log(f"  CV search: {len(per_fold)} fits in {time.time() - t0:.0f}s")

    # aggregate per (model, feature set, params)
    table: dict[tuple, list[dict]] = {}
    for r in per_fold:
        table.setdefault((r["model"], r["feature_set"], tuple(sorted(r["params"].items()))), []).append(r)
    summary = []
    for (model, kind, params), rs in table.items():
        row = {"model": model, "feature_set": kind, "params": dict(params), "folds": len(rs)}
        for m in METRICS:
            v = np.array([r[m] for r in rs])
            row[f"{m}_mean"], row[f"{m}_std"] = round(float(v.mean()), 4), round(float(v.std(ddof=1)), 4)
        row["fit_seconds_mean"] = round(float(np.mean([r["fit_seconds"] for r in rs])), 3)
        summary.append(row)
    summary.sort(key=lambda r: (r["model"], r["feature_set"], str(r["params"])))

    def best(filter_fn):
        cands = [r for r in summary if filter_fn(r)]
        return max(cands, key=lambda r: (r["pr_auc_mean"], -r["pr_auc_std"]))

    best_per_model = {m: best(lambda r, m=m: r["model"] == m) for m in grid}
    best_per_model_feature = [best(lambda r, m=m, k=k: r["model"] == m and r["feature_set"] == k)
                              for m in grid for k in feature_sets]

    # paired comparison of the best configs, fold by fold
    def fold_scores(cfg, metric="pr_auc"):
        rs = table[(cfg["model"], cfg["feature_set"], tuple(sorted(cfg["params"].items())))]
        return np.array([r[metric] for r in sorted(rs, key=lambda r: r["fold"])])

    n_te = int(np.mean([len(te) for _, te in splits]))
    n_tr = len(rows) - n_te
    ref = "logreg"
    paired = {}
    for m in grid:
        if m == ref:
            continue
        for metric in ("pr_auc", "f1"):
            d = fold_scores(best_per_model[ref], metric) - fold_scores(best_per_model[m], metric)
            t, p = corrected_ttest(d, n_tr, n_te)
            paired[f"{ref}_minus_{m}_{metric}"] = {
                "mean_diff": round(float(d.mean()), 4), "folds_ref_better": int((d > 0).sum()), "folds": len(d),
                "corrected_t": round(t, 3), "p_value": round(p, 4)}
    return {
        "scheme": f"StratifiedGroupKFold(n_splits={n_splits}, shuffle=True, seed={seed}); stratify=source+label; "
                  "groups=template id (synthetic) / message id (UCI); TF-IDF refit per fold; TRAIN split only",
        "selection_metric": "pr_auc (mean over folds)",
        "grid": grid, "feature_sets": list(feature_sets),
        "fold_sizes": [int(len(te)) for _, te in splits],
        "fold_positive_rate": [round(float(y[te].mean()), 4) for _, te in splits],
        "summary": summary,
        "best_per_model": best_per_model,
        "best_per_model_feature": best_per_model_feature,
        "paired_tests": paired,
        "seconds": round(time.time() - t0, 1),
    }
