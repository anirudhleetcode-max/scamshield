"""Train the production model and write a versioned artifact + model card.

    python -m ml.train                                   # combined recipe, version 2.0.0
    python -m ml.train --config ../experiments/configs/combined.json --version 2.0.0

What it does (see ml/experiment.py for the details):
  1. builds / loads the datasets listed in the config (synthetic + real UCI),
  2. fits TF-IDF features + calibrated logistic regression + the category head on TRAIN,
  3. evaluates every baseline on VAL / TEST and picks operating points on VAL,
  4. records the run in experiments/results/<run_id>/ (metrics, config, env, errors),
  5. saves models/scamshield-<version>.joblib and models/scamshield-<version>.card.json.

The shipped model is the one trained on the TRAIN split only - it is exactly the model whose
test metrics are reported (no refit on validation or test data).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

from .experiment import REPO_ROOT, env_info, run_experiment, write_run
from .templates import ALL_CATEGORIES, CATEGORY_LABELS

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "experiments" / "configs" / "combined.json"
DEFAULT_VERSION = "2.0.0"

LIMITATIONS = [
    "The 13-way scam category head is trained ONLY on synthetic, template-generated Indian messages; its "
    "labels have never been validated on real messages.",
    "The only real labelled SMS data (UCI SMS Spam Collection, 2011) is English, UK/Singapore and "
    "labels generic spam vs ham - not Indian UPI/KYC fraud, and it counts marketing as spam.",
    "Trained on English and romanised Hindi only; Devanagari and other scripts trigger 'insufficient confidence'.",
    "Out-of-domain email-style spam (all-scam-spam short subset) is detected poorly - see the model card metrics.",
    "Scam scripts change quickly; a TF-IDF model only knows words it has seen.",
    "Probabilities are calibrated on the validation mix of synthetic + UCI data; calibration on real Indian "
    "traffic is not measured.",
]


def headline(res: dict, main: str) -> dict:
    out = {}
    for k, t in res["models"][main]["test"].items():
        m = t["at_tuned"]
        out[k] = {x: m[x] for x in ("n", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier", "ece")}
    return out


def build_card(cfg: dict, res: dict, version: str, run_id: str) -> dict:
    main = cfg["main_model"]
    env = env_info()
    baselines = {name: {k: {x: t["at_tuned"][x] for x in ("precision", "recall", "f1", "pr_auc")}
                        for k, t in m["test"].items()} for name, m in res["models"].items()}
    calib = {}
    for name in ("logreg_uncal", "logreg_cal"):
        if name in res["models"]:
            calib[name] = {k: {"brier": t["at_default"]["brier"], "ece": t["at_default"]["ece"]}
                           for k, t in res["models"][name]["test"].items()}
            calib[name]["val"] = {"brier": res["models"][name]["val"]["brier"], "ece": res["models"][name]["val"]["ece"]}
    datasets = []
    for name, info in res["data"].items():
        datasets.append({k: info.get(k) for k in ("name", "kind", "version", "source_url", "licence",
                                                   "processed_sha256", "raw_sha256", "counts", "description")})
    return {
        "model_name": "scamshield-text",
        "model_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment_run": run_id,
        "git_commit": env["git_commit"],
        "intended_use": "Assist a person in judging whether an SMS / WhatsApp message is a scam. "
                        "Advisory only - not a guarantee, not for automated blocking.",
        "pipeline": ["normalise text (lower-case, digits->0, length preserving)",
                     "TF-IDF word 1-2-grams + char_wb 3-5-grams",
                     f"{main}: LogisticRegression(class_weight=balanced) + sigmoid calibration, GroupKFold(3)",
                     "multinomial LogisticRegression category head (synthetic labels)",
                     "rule engine + community reports fused with noisy-OR",
                     "operating points + uncertain band chosen on validation"],
        "training_data": {
            "datasets": datasets,
            "train_rows": res["sizes"]["train"],
            "val_rows": res["sizes"]["val"],
            "contains_synthetic": any(d["kind"] == "synthetic" for d in datasets),
            "note": "synthetic_in is SYNTHETIC (templated). uci_sms_spam is REAL but generic English spam.",
        },
        "preprocessing_version": env["preprocess_version"],
        "hyperparameters": {"features": cfg.get("features"), "model": cfg.get("model_params"), "seed": cfg.get("seed")},
        "libraries": env["libraries"],
        "python": env["python"],
        "operating_points": res["system"]["operating_points"],
        "metrics": {
            "main_model_test": headline(res, main),
            "full_system_test": {k: {a: {x: v[a][x] for x in ("precision", "recall", "f1")}
                                     for a in ("flag_if_suspicious_or_scam", "flag_if_scam")} |
                                 {"verdict_counts": v["verdict_counts"], "abstention": v["abstention_uncertain_band"]}
                                 for k, v in res["system"]["test"].items()},
            "category_head_test": {k: {"accuracy": c["accuracy"], "macro_f1": c["macro_f1"], "n": c["n"]}
                                   for k, c in res.get("category", {}).items()},
            "baselines_test_at_val_threshold": baselines,
            "calibration": calib,
        },
        "test_set_notes": {
            "synthetic_test": "SYNTHETIC - held-out templates, never seen in training",
            "uci_test": "REAL - UCI SMS Spam Collection, stratified 15% test split",
            "all_scam_spam_short": "REAL - multilingual email/message spam, out-of-domain stress test",
        },
        "categories": {c: CATEGORY_LABELS[c] for c in ALL_CATEGORIES},
        "limitations": LIMITATIONS,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--model-dir", type=Path, default=BACKEND / "models")
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    run_id = f"{cfg['name']}-train-v{args.version}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    out = REPO_ROOT / "experiments" / "results" / run_id
    res = run_experiment(cfg, out)
    write_run(cfg, res, out)
    fitted = res["_fitted"]
    if fitted["category"] is None:
        raise SystemExit("config must enable category_head for a production model")

    args.model_dir.mkdir(parents=True, exist_ok=True)
    art = args.model_dir / f"scamshield-{args.version}.joblib"
    card_path = args.model_dir / f"scamshield-{args.version}.card.json"
    joblib.dump({"version": args.version, "features": fitted["features"], "binary": fitted["binary"],
                 "category": fitted["category"]}, art, compress=3)
    card = build_card(cfg, res, args.version, run_id)
    card["artifact"] = {"file": art.name, "size_kb": round(art.stat().st_size / 1024)}
    card_path.write_text(json.dumps(card, indent=2) + "\n")
    print(f"saved {art.name} ({card['artifact']['size_kb']} KB) + {card_path.name}; run {run_id}")


if __name__ == "__main__":
    main()
