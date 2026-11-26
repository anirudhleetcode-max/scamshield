"""Full classical-ML evaluation: CV hyperparameter search -> tuned NB / LogReg / SVM ->
calibration -> threshold optimisation -> abstention -> error analysis -> figures.

    cd backend && python -m ml.analysis                         # Track C (combined) config
    python -m ml.analysis --config ../experiments/configs/combined.json --folds 5

Writes experiments/results/<name>-analysis-<UTC>/ with metrics.json, cv_results.json,
summary.md, errors_*.csv, figures/*.png and scores.npz (per-message scores, git-ignored;
used by ml.transformer to overlay DistilBERT on the same plots).

This does NOT change the shipped model (models/scamshield-2.0.0). It answers "were the
shipped hyperparameters a good choice, and how do the classical models compare?".
Honesty rules are the same as ml.experiment: search on TRAIN folds, choose thresholds and
abstention band on VAL, score TEST once.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV

from . import plots
from .errors import dump_errors
from .evaluate import (binary_metrics, choose_threshold, min_cost_threshold, risk_coverage, selective_band,
                       threshold_sweep)
from .experiment import REPO_ROOT, env_info, fit_model, select
from .tuning import make_classifier, make_feature_set, search

COST_FN, COST_FP = 5.0, 1.0
MAIN = "logreg_cal (tuned)"
# fixed colour slot per model across every figure
SLOTS = {"nb": 1, "nb_cal": 4, "logreg_uncal (tuned)": 2, MAIN: 0, "linsvc_cal (tuned)": 3,
         "logreg_cal (shipped v2.0.0)": 6, "distilbert": 7, "distilbert (temp-scaled)": 5}


def _y(rows):
    return np.array([r["label_binary"] for r in rows])


def fit_variants(best: dict, train, val, tests, cfg, seed, log=print) -> dict:
    """Fit each tuned model on the whole TRAIN split. Returns name -> (val scores, {test: scores}, extra)."""
    ytr = _y(train)
    groups = np.array([r["group"] for r in train])
    texts = {"train": [r["text"] for r in train], "val": [r["text"] for r in val],
             **{k: [r["text"] for r in v] for k, v in tests.items()}}
    feat_cache: dict = {}

    def feats_for(kind):
        if kind not in feat_cache:
            f = make_feature_set(kind, cfg.get("features"))
            Xtr = f.fit_transform(texts["train"])
            feat_cache[kind] = (f, Xtr, {k: f.transform(v) for k, v in texts.items() if k != "train"})
        return feat_cache[kind]

    specs = {
        "nb": ("nb", best["nb"], False),
        "nb_cal": ("nb", best["nb"], True),
        "logreg_uncal (tuned)": ("logreg", best["logreg"], False),
        MAIN: ("logreg", best["logreg"], True),
        "linsvc_cal (tuned)": ("linsvc", best["linsvc"], True),
        "logreg_cal (shipped v2.0.0)": ("logreg", {"feature_set": "word+char",
                                                    "params": {"C": cfg["model_params"]["C"]}}, True),
    }
    out = {}
    for name, (model, b, calibrate) in specs.items():
        t0 = time.time()
        f, Xtr, Xo = feats_for(b["feature_set"])
        clf = make_classifier(model, b["params"], seed)
        if calibrate:
            clf = fit_model(CalibratedClassifierCV(clf, method="sigmoid", cv=3), Xtr, ytr, groups)
        else:
            clf.fit(Xtr, ytr)
        s = {k: clf.predict_proba(X)[:, 1] for k, X in Xo.items()}
        out[name] = {"val": s.pop("val"), "test": s, "model": clf, "features": f,
                     "config": {"model": model, "feature_set": b["feature_set"], "params": b["params"],
                                "calibrated": calibrate}, "fit_seconds": round(time.time() - t0, 2)}
        log(f"  fitted {name:30s} {b['feature_set']:10s} {b['params']}  ({out[name]['fit_seconds']}s)")
    return out


def run(cfg: dict, n_splits: int, out_dir: Path, seed: int = 42, log=print) -> dict:
    t0 = time.time()
    train, val = select(cfg["train"]), select(cfg["val"])
    tests = {k: v for k, v in ((n, select(s)) for n, s in cfg["test_sets"].items()) if v}
    yva = _y(val)
    log(f"[analysis] train={len(train)} val={len(val)} " + " ".join(f"{k}={len(v)}" for k, v in tests.items()))

    # 1. cross-validated hyperparameter search (TRAIN only)
    cv = search(train, n_splits=n_splits, seed=seed, feat_params=cfg.get("features"), log=log)
    best = {m: {"feature_set": r["feature_set"], "params": r["params"]} for m, r in cv["best_per_model"].items()}
    for m, r in cv["best_per_model"].items():
        log(f"  best {m:7s} {r['feature_set']:10s} {r['params']}  PR-AUC {r['pr_auc_mean']:.4f}±{r['pr_auc_std']:.4f}"
            f"  F1 {r['f1_mean']:.4f}±{r['f1_std']:.4f}")

    # 2. refit tuned models on all of TRAIN
    fitted = fit_variants(best, train, val, tests, cfg, seed, log)

    # 3. thresholds on VAL for every model (max F1); for the main model also cost / recall targets
    res: dict = {"cv": {k: v for k, v in cv.items() if k != "summary"}, "models": {}}
    for name, f in fitted.items():
        t = choose_threshold(yva, f["val"], "max_f1")
        res["models"][name] = {
            "config": f["config"], "fit_seconds": f["fit_seconds"], "threshold_max_f1_val": round(t, 4),
            "val": binary_metrics(yva, f["val"], t),
            "test": {k: binary_metrics(_y(tests[k]), s, t) for k, s in f["test"].items()},
        }
    main = fitted[MAIN]
    t_f1 = choose_threshold(yva, main["val"], "max_f1")
    t_cost, cost_val = min_cost_threshold(yva, main["val"], COST_FN, COST_FP)
    t_rec = choose_threshold(yva, main["val"], "min_recall", 0.95)
    thresholds = {"default 0.5": 0.5, "max F1": t_f1, f"min cost (FN={COST_FN:g}, FP={COST_FP:g})": t_cost,
                  "recall >= 0.95": t_rec}
    res["thresholds"] = {
        "chosen_on": "val",
        "values": {k: round(v, 4) for k, v in thresholds.items()},
        "val_cost_at_min_cost": cost_val,
        "test": {k: {lab: {m: binary_metrics(_y(rows), main["test"][k], t)[m]
                           for m in ("precision", "recall", "f1", "false_positive_rate", "confusion_matrix")}
                     for lab, t in thresholds.items()} for k, rows in tests.items()},
    }

    # 4. abstention: band chosen on val, applied to test
    band = selective_band(yva, main["val"], t_f1, 0.98)
    res["abstention"] = {"band_chosen_on_val": band, "test": {}}
    for k, rows in tests.items():
        p, y = main["test"][k], _y(rows)
        inside = (p >= band["low"]) & (p <= band["high"])
        cov = ~inside
        res["abstention"]["test"][k] = {
            "abstained": int(inside.sum()), "coverage": round(float(cov.mean()), 4),
            "accuracy_all": round(float(((p >= t_f1).astype(int) == y).mean()), 4),
            "accuracy_answered": round(float(((p[cov] >= t_f1).astype(int) == y[cov]).mean()), 4) if cov.any() else None,
            "errors_all": int(((p >= t_f1).astype(int) != y).sum()),
            "errors_answered": int(((p[cov] >= t_f1).astype(int) != y[cov]).sum()),
        }

    # 5. error analysis of the main model
    out_dir.mkdir(parents=True, exist_ok=True)
    feats, lr = main["features"], main["model"]
    res["errors"] = {k: dump_errors(out_dir / f"errors_{k}.csv", feats, lr, tests[k], main["test"][k], t_f1, 25)
                     for k in cfg.get("error_analysis", {}).get("test_sets", []) if k in tests}

    # 6. figures
    fig = out_dir / "figures"
    figs = []
    figs.append(plots.cv_bars(cv["best_per_model_feature"], "pr_auc",
                              "CV PR-AUC by model and feature set (best params each)", fig / "cv_pr_auc.png"))
    figs.append(plots.cv_bars(cv["best_per_model_feature"], "f1",
                              "CV F1 at default threshold by model and feature set", fig / "cv_f1.png"))
    show = ["nb", "logreg_uncal (tuned)", MAIN, "linsvc_cal (tuned)"]
    for k, rows in tests.items():
        y = _y(rows)
        figs.append(plots.roc_pr(y, {n: fitted[n]["test"][k] for n in show}, k, fig / f"roc_pr_{k}.png", SLOTS))
        figs.append(plots.confusion(res["models"][MAIN]["test"][k]["confusion_matrix"],
                                    f"{k} - logreg_cal, t={t_f1:.2f}", fig / f"confusion_{k}.png"))
        figs.append(plots.reliability(y, {n: fitted[n]["test"][k] for n in ("nb", "nb_cal", "logreg_uncal (tuned)", MAIN)},
                                      f"Reliability - {k}", fig / f"reliability_{k}.png", slots=SLOTS))
    figs.append(plots.reliability(yva, {n: fitted[n]["val"] for n in ("nb", "nb_cal", "logreg_uncal (tuned)", MAIN)},
                                  "Reliability - validation", fig / "reliability_val.png", slots=SLOTS))
    figs.append(plots.threshold_sweep(threshold_sweep(yva, main["val"], cost_fn=COST_FN, cost_fp=COST_FP),
                                      {k: v for k, v in thresholds.items() if k != "default 0.5"},
                                      "validation, logreg_cal (tuned)", fig / "threshold_sweep_val.png"))
    curves = {k: risk_coverage(_y(rows), main["test"][k], t_f1) for k, rows in tests.items()}
    res["risk_coverage"] = curves
    figs.append(plots.risk_coverage(curves, "Risk-coverage, logreg_cal (tuned)", fig / "risk_coverage.png",
                                    {"val-chosen band (val coverage)": band["coverage"]}))
    res["figures"] = sorted(figs)

    np.savez_compressed(out_dir / "scores.npz", **{f"{n}|{k}": s for n, f in fitted.items() for k, s in f["test"].items()},
                        **{f"{n}|val": f["val"] for n, f in fitted.items()})
    res["sizes"] = {"train": len(train), "val": len(val), **{k: len(v) for k, v in tests.items()}}
    res["seconds"] = round(time.time() - t0, 1)
    (out_dir / "cv_results.json").write_text(json.dumps(cv["summary"], indent=1) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(res, indent=1) + "\n")
    (out_dir / "config.json").write_text(json.dumps({**cfg, "analysis": {"folds": n_splits, "cost_fn": COST_FN,
                                                                          "cost_fp": COST_FP}}, indent=2) + "\n")
    (out_dir / "env.json").write_text(json.dumps(env_info(), indent=2) + "\n")
    (out_dir / "summary.md").write_text(summary_md(res, cv))
    return res


def summary_md(res: dict, cv: dict) -> str:
    L = ["# Classical-ML analysis", "", f"CV: {cv['scheme']}", "",
         "## Best configuration per model (CV on train, selected by mean PR-AUC)", "",
         "| model | features | params | PR-AUC | ROC-AUC | F1 @ default | P | R |", "|---|---|---|---|---|---|---|---|"]
    for m, r in cv["best_per_model"].items():
        L.append(f"| {m} | {r['feature_set']} | {r['params']} | {r['pr_auc_mean']:.4f} ± {r['pr_auc_std']:.4f} | "
                 f"{r['roc_auc_mean']:.4f} ± {r['roc_auc_std']:.4f} | {r['f1_mean']:.4f} ± {r['f1_std']:.4f} | "
                 f"{r['precision_mean']:.3f} | {r['recall_mean']:.3f} |")
    L += ["", "## Feature-set ablation (best params per cell, CV PR-AUC)", "", "| model | word | char | word+char |",
          "|---|---|---|---|"]
    for m in cv["grid"]:
        cells = {r["feature_set"]: r for r in cv["best_per_model_feature"] if r["model"] == m}
        L.append(f"| {m} | " + " | ".join(f"{cells[k]['pr_auc_mean']:.4f} ± {cells[k]['pr_auc_std']:.4f}"
                                          for k in cv["feature_sets"]) + " |")
    L += ["", "## Paired comparison (corrected resampled t-test, Nadeau & Bengio)", "",
          "| comparison | mean diff | folds LR better | t | p |", "|---|---|---|---|---|"]
    for k, v in cv["paired_tests"].items():
        L.append(f"| {k} | {v['mean_diff']:+.4f} | {v['folds_ref_better']}/{v['folds']} | {v['corrected_t']} | {v['p_value']} |")
    tests = list(next(iter(res["models"].values()))["test"])
    for k in tests:
        L += ["", f"## Test `{k}` (threshold = max F1 on val)", "",
              "| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |", "|---|---|---|---|---|---|---|---|---|"]
        for n, m in res["models"].items():
            t = m["test"][k]
            L.append(f"| {n} | {t['precision']:.3f} | {t['recall']:.3f} | {t['f1']:.3f} | {t['roc_auc']} | "
                     f"{t['pr_auc']} | {t['brier']} | {t['ece']} | {t['threshold']:.3f} |")
    L += ["", "## Decision thresholds for the main model (chosen on val)", "",
          "| rule | t | " + " | ".join(f"{k} P / R / F1 / FPR" for k in tests) + " |",
          "|---|---|" + "---|" * len(tests)]
    for lab, t in res["thresholds"]["values"].items():
        L.append(f"| {lab} | {t:.3f} | " + " | ".join(
            "{precision:.3f} / {recall:.3f} / {f1:.3f} / {false_positive_rate:.3f}".format(**res["thresholds"]["test"][k][lab])
            for k in tests) + " |")
    b = res["abstention"]["band_chosen_on_val"]
    L += ["", f"## Abstention (band {b['low']}–{b['high']} chosen on val; val coverage {b['coverage']}, "
              f"selective accuracy {b['selective_accuracy']}, target met: {b.get('target_met')})", "",
          "| test set | abstained | coverage | accuracy (all) | accuracy (answered) | errors all -> answered |",
          "|---|---|---|---|---|---|"]
    for k, a in res["abstention"]["test"].items():
        L.append(f"| {k} | {a['abstained']} | {a['coverage']} | {a['accuracy_all']} | {a['accuracy_answered']} | "
                 f"{a['errors_all']} -> {a['errors_answered']} |")
    L += ["", "## Figures", ""] + [f"- `figures/{f}`" for f in res["figures"]]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(REPO_ROOT / "experiments" / "configs" / "combined.json"))
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(a.out) if a.out else REPO_ROOT / "experiments" / "results" / f"{cfg['name']}-analysis-{stamp}"
    run(cfg, a.folds, out, cfg.get("seed", 42))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
