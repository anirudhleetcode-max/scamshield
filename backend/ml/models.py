"""Step 3: the classifiers compared in experiments (all share one fitted FeatureUnion).

    majority          DummyClassifier(prior)         - floor: what "no model" scores
    rules_only        hand-written red-flag rules    - no learning at all
    nb                MultinomialNB on TF-IDF        - classic simple text baseline
    logreg_noweight   LogisticRegression             - no class weighting, raw probabilities
    logreg_uncal      LogisticRegression(balanced)   - class weighting, raw probabilities
    logreg_cal        logreg_uncal + sigmoid calibration (3-fold)   <- production model
    linsvc_cal        LinearSVC(balanced) + sigmoid calibration (3-fold)
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC

MODEL_NAMES = ["majority", "rules_only", "nb", "logreg_noweight", "logreg_uncal", "logreg_cal", "linsvc_cal"]


def make_model(name: str, seed: int = 42, params: dict | None = None):
    p = params or {}
    C = p.get("C", 4.0)
    if name == "majority":
        return DummyClassifier(strategy="prior")
    if name == "nb":
        return MultinomialNB(alpha=p.get("alpha", 0.1))
    if name == "logreg_noweight":
        return LogisticRegression(C=C, max_iter=3000, random_state=seed)
    if name == "logreg_uncal":
        return LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=seed)
    if name == "logreg_cal":
        base = LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=seed)
        return CalibratedClassifierCV(base, method="sigmoid", cv=3)
    if name == "linsvc_cal":
        base = LinearSVC(C=p.get("svc_C", 0.5), class_weight="balanced", random_state=seed)
        return CalibratedClassifierCV(base, method="sigmoid", cv=3)
    raise ValueError(f"unknown model {name}")


def make_category_model(seed: int = 42, params: dict | None = None) -> LogisticRegression:
    return LogisticRegression(C=(params or {}).get("category_C", 8.0), max_iter=3000,
                              class_weight="balanced", random_state=seed)


def linear_coef(model) -> np.ndarray | None:
    """Per-feature weights toward the positive class (averaged over calibration folds)."""
    if hasattr(model, "calibrated_classifiers_"):
        coefs = [c.estimator.coef_[0] for c in model.calibrated_classifiers_ if hasattr(c.estimator, "coef_")]
        return np.mean(coefs, axis=0) if coefs else None
    if hasattr(model, "coef_"):
        return np.asarray(model.coef_[0])
    if isinstance(model, MultinomialNB):
        return model.feature_log_prob_[1] - model.feature_log_prob_[0]
    return None


def rules_eval(texts: list[str]) -> list[tuple[float, frozenset]]:
    """(R in [0, 0.6], ids of rules that fired) for each text - same code path as the API."""
    from app.services.analyzer import rules_component
    from app.services.rules import check

    out = []
    for t in texts:
        flags = check(t, None)[0]
        out.append((rules_component(flags), frozenset(f["id"] for f in flags if f["hit"])))
    return out
