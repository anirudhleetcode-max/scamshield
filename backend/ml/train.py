"""Train and evaluate the ScamShield text models.

    python -m ml.train            # generates the dataset if missing, trains, evaluates,
                                  # writes models/scamshield.joblib and models/metrics.json

Features : TF-IDF word 1-2 grams  +  TF-IDF char_wb 3-5 grams (one shared FeatureUnion)
Model (a): scam vs not-scam  -> LogisticRegression wrapped in CalibratedClassifierCV (sigmoid)
Model (b): 13-way category   -> multinomial LogisticRegression
Evaluation uses HELD-OUT TEMPLATES (see ml/templates.py), and a naive random split is
reported alongside it only to show how optimistic template leakage would be.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             precision_recall_fscore_support, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion

from app.services.textprep import WORD_TOKEN_PATTERN, normalize

from . import generate_dataset
from .templates import ALL_CATEGORIES

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "scamshield.joblib"
METRICS_PATH = ROOT / "models" / "metrics.json"
MODEL_VERSION = "1.0"


def load_rows() -> list[dict]:
    path = generate_dataset.DATA_DIR / "dataset.csv"
    if not path.exists():
        generate_dataset.build(path)
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def make_features() -> FeatureUnion:
    word = TfidfVectorizer(preprocessor=normalize, token_pattern=WORD_TOKEN_PATTERN, ngram_range=(1, 2),
                           min_df=2, max_features=12000, sublinear_tf=True, dtype=np.float32)
    char = TfidfVectorizer(preprocessor=normalize, analyzer="char_wb", ngram_range=(3, 5),
                           min_df=3, max_features=20000, sublinear_tf=True, dtype=np.float32)
    return FeatureUnion([("word", word), ("char", char)])


def make_binary() -> CalibratedClassifierCV:
    base = LogisticRegression(C=4.0, max_iter=3000, class_weight="balanced")
    return CalibratedClassifierCV(base, method="sigmoid", cv=3)


def make_category() -> LogisticRegression:
    return LogisticRegression(C=8.0, max_iter=3000, class_weight="balanced")


def fit(texts, y_bin, y_cat):
    feats = make_features()
    X = feats.fit_transform(texts)
    for _, vec in feats.transformer_list:
        vec.stop_words_ = None  # large and only needed for introspection; keeps the file small
    binary = make_binary().fit(X, y_bin)
    category = make_category().fit(X, y_cat)
    return feats, binary, category


def evaluate(feats, binary, category, texts, y_bin, y_cat) -> dict:
    X = feats.transform(texts)
    proba = binary.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(y_bin, pred, average="binary", zero_division=0)
    cat_pred = category.predict(X)
    labels = [c for c in ALL_CATEGORIES if c in set(y_cat) | set(cat_pred)]
    return {
        "n": len(texts),
        "binary": {
            "precision": round(float(p), 4), "recall": round(float(r), 4), "f1": round(float(f1), 4),
            "accuracy": round(float(accuracy_score(y_bin, pred)), 4),
            "roc_auc": round(float(roc_auc_score(y_bin, proba)), 4) if len(set(y_bin)) > 1 else None,
            "confusion_matrix": {"labels": ["not_scam", "scam"],
                                 "matrix": confusion_matrix(y_bin, pred, labels=[0, 1]).tolist()},
        },
        "category": {
            "accuracy": round(float(accuracy_score(y_cat, cat_pred)), 4),
            "macro_f1": round(float(precision_recall_fscore_support(y_cat, cat_pred, average="macro", zero_division=0)[2]), 4),
            "per_class": {k: {m: round(float(v), 4) for m, v in d.items()}
                          for k, d in classification_report(y_cat, cat_pred, labels=labels, output_dict=True,
                                                            zero_division=0).items() if k in labels},
            "confusion_matrix": {"labels": labels,
                                 "matrix": confusion_matrix(y_cat, cat_pred, labels=labels).tolist()},
        },
    }


def evaluate_system(feats, binary, category, rows) -> dict:
    """Score the held-out rows with the complete analyzer (model + rules, no community reports)
    using the TRAIN-ONLY model, so this is still an unseen-template evaluation."""
    import tempfile

    from app.services import analyzer, classifier

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "m.joblib"
        joblib.dump({"version": "eval", "features": feats, "binary": binary, "category": category}, tmp)
        old = classifier._model
        classifier._model = classifier.ScamModel(tmp)
        try:
            verdicts = [analyzer.analyze(r["text"], None, {})["verdict"] for r in rows]
        finally:
            classifier._model = old
    y = [int(r["is_scam"]) for r in rows]
    out = {}
    for name, positive in (("flagged_if_not_safe", {"Scam", "Suspicious"}), ("flagged_if_scam", {"Scam"})):
        pred = [int(v in positive) for v in verdicts]
        p, r_, f1, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
        out[name] = {"precision": round(float(p), 4), "recall": round(float(r_), 4), "f1": round(float(f1), 4),
                     "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist()}
    out["verdict_counts"] = {v: verdicts.count(v) for v in ("Safe", "Suspicious", "Scam")}
    return out


def cols(rows):
    return [r["text"] for r in rows], np.array([int(r["is_scam"]) for r in rows]), np.array([r["category"] for r in rows])


def main() -> None:
    t0 = time.time()
    rows = load_rows()
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    print(f"rows: {len(rows)}  train: {len(train)}  held-out test: {len(test)}")

    feats, binary, category = fit(*cols(train))
    held = evaluate(feats, binary, category, *cols(test))
    syn_test = [r for r in test if r["source"] != "uci"]
    uci_test = [r for r in test if r["source"] == "uci"]
    by_source = {"synthetic_heldout_templates": evaluate(feats, binary, category, *cols(syn_test))["binary"]}
    if uci_test:
        by_source["uci_sms_spam"] = evaluate(feats, binary, category, *cols(uci_test))["binary"]

    system = evaluate_system(feats, binary, category, test)
    print("held-out  full system (model + rules):", system)

    # Naive random split (templates leak between train and test) -- for contrast only.
    tr, te = train_test_split(rows, test_size=0.2, random_state=0, stratify=[r["category"] for r in rows])
    nf, nb, nc = fit(*cols(tr))
    naive = evaluate(nf, nb, nc, *cols(te))

    print("held-out  binary:", {k: v for k, v in held["binary"].items() if k != "confusion_matrix"})
    print("held-out  category acc / macro-F1:", held["category"]["accuracy"], held["category"]["macro_f1"])
    print("naive     binary F1:", naive["binary"]["f1"], " category macro-F1:", naive["category"]["macro_f1"])

    # Final model: refit on everything (train + held-out) before shipping.
    feats, binary, category = fit(*cols(rows))
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"version": MODEL_VERSION, "features": feats, "binary": binary, "category": category},
                MODEL_PATH, compress=3)

    metrics = {
        "model_version": MODEL_VERSION,
        "dataset": {
            "total": len(rows), "train": len(train), "test": len(test),
            "uci_rows": sum(1 for r in rows if r["source"] == "uci"),
            "per_category": {c: sum(1 for r in rows if r["category"] == c) for c in ALL_CATEGORIES},
            "n_features": len(feats.get_feature_names_out()),
        },
        "heldout_templates": held,
        "heldout_by_source": by_source,
        "heldout_full_system": system,
        "naive_random_split": {"binary": {k: v for k, v in naive["binary"].items() if k != "confusion_matrix"},
                               "category_macro_f1": naive["category"]["macro_f1"]},
        "model_file_kb": round(MODEL_PATH.stat().st_size / 1024),
        "train_seconds": round(time.time() - t0, 1),
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"saved {MODEL_PATH} ({metrics['model_file_kb']} KB) and {METRICS_PATH} in {metrics['train_seconds']}s")


if __name__ == "__main__":
    main()
