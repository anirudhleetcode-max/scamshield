"""One experiment = one config: datasets/splits -> features -> every model -> metrics.

Used by `experiments/run.py` (research runs) and `ml/train.py` (the production artifact).
Rules for honesty:
  * features, models and the category head are fit on TRAIN rows only;
  * thresholds, operating points and the abstention band are chosen on VAL rows only;
  * TEST rows are only ever scored.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import GroupKFold

from .data import registry
from .data.schema import Record
from .evaluate import binary_metrics, category_metrics, choose_threshold, selective_band
from .errors import dump_errors
from .features import fit_features
from .models import make_category_model, make_model, rules_eval
from .preprocess import PREPROCESS_VERSION
from .templates import ALL_CATEGORIES


def verdict_for(score, ops, hits):
    from app.services.analyzer import verdict_for as _v

    return _v(score, ops, hits)

REPO_ROOT = Path(__file__).resolve().parents[2]


def select(specs: list[dict]) -> list[Record]:
    rows: list[Record] = []
    for spec in specs:
        rows += [r for r in registry.load(spec["dataset"]) if r["split"] in spec["splits"]]
    return rows


def env_info() -> dict:
    import joblib
    import scipy
    import sklearn

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            return None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain", "--", "backend/ml", "backend/app")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "libraries": {"scikit-learn": sklearn.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
                      "joblib": joblib.__version__},
        "preprocess_version": PREPROCESS_VERSION,
    }


class RuleCache:
    """Rule-engine results are deterministic; compute each distinct text once."""

    def __init__(self):
        self._c: dict[str, tuple[float, frozenset]] = {}

    def _fill(self, texts):
        todo = [t for t in dict.fromkeys(texts) if t not in self._c]
        for t, v in zip(todo, rules_eval(todo)):
            self._c[t] = v

    def __call__(self, texts: list[str]) -> np.ndarray:
        self._fill(texts)
        return np.array([self._c[t][0] for t in texts])

    def hits(self, texts: list[str]) -> list[frozenset]:
        self._fill(texts)
        return [self._c[t][1] for t in texts]


def fit_model(model, X, y, groups=None):
    """Calibrated models use GROUP-aware folds (template id for synthetic rows): with random
    folds the same template sits on both sides, fold predictions look over-confident and the
    sigmoid is fit too steep."""
    if isinstance(model, CalibratedClassifierCV) and groups is not None:
        n = model.cv if isinstance(model.cv, int) else 3
        model.cv = list(GroupKFold(n_splits=n).split(X, y, groups))
        model.fit(X, y)
        model.cv = f"GroupKFold({n})"  # drop the index arrays before pickling
    else:
        model.fit(X, y)
    return model


def _y(rows):
    return np.array([r["label_binary"] for r in rows])


def run_experiment(cfg: dict, out_dir: Path | None = None, log=print) -> dict:
    t0 = time.time()
    seed = cfg.get("seed", 42)
    np.random.seed(seed)
    train, val = select(cfg["train"]), select(cfg["val"])
    tests = {name: select(specs) for name, specs in cfg["test_sets"].items()}
    tests = {k: v for k, v in tests.items() if v}
    log(f"[{cfg['name']}] train={len(train)} val={len(val)} " + " ".join(f"{k}={len(v)}" for k, v in tests.items()))

    feats, Xtr = fit_features([r["text"] for r in train], cfg.get("features"))
    Xva = feats.transform([r["text"] for r in val])
    Xte = {k: feats.transform([r["text"] for r in v]) for k, v in tests.items()}
    ytr, yva = _y(train), _y(val)
    # calibration_folds: "group" (default) or "random" (ablation)
    groups = np.array([r["group"] for r in train]) if cfg.get("calibration_folds", "group") == "group" else None
    rules = RuleCache()
    strategy = cfg.get("threshold", {}).get("strategy", "max_f1")

    results: dict = {"models": {}}
    fitted: dict = {}
    for name in cfg["models"]:
        m0 = time.time()
        probabilistic = name != "rules_only"
        if name == "rules_only":
            model = None
            s_va = rules([r["text"] for r in val])
            s_te = {k: rules([r["text"] for r in v]) for k, v in tests.items()}
        else:
            model = make_model(name, seed, cfg.get("model_params"))
            fit_model(model, Xtr, ytr, groups)
            s_va = model.predict_proba(Xva)[:, 1]
            s_te = {k: model.predict_proba(X)[:, 1] for k, X in Xte.items()}
        default_t = 0.5 if probabilistic else 0.25
        tuned_t = default_t if name == "majority" else choose_threshold(yva, s_va, strategy)
        entry = {
            "threshold_strategy": "none" if name == "majority" else f"{strategy} on val",
            "val": binary_metrics(yva, s_va, tuned_t, probabilistic),
            "test": {k: {"at_default": binary_metrics(_y(tests[k]), s, default_t, probabilistic),
                         "at_tuned": binary_metrics(_y(tests[k]), s, tuned_t, probabilistic)}
                     for k, s in s_te.items()},
            "fit_seconds": round(time.time() - m0, 2),
        }
        results["models"][name] = entry
        fitted[name] = (model, s_va, s_te, tuned_t)
        log(f"  {name:16s} " + "  ".join(
            f"{k}: F1={v['at_tuned']['f1']:.3f} PR-AUC={v['at_tuned']['pr_auc']}" for k, v in entry["test"].items()))

    main = cfg["main_model"]
    model, p_va, p_te, t_model = fitted[main]
    ops_cfg = cfg.get("operating_points", {})
    # full system: model + rules (no community reports offline)
    r_va = rules([r["text"] for r in val])
    sys_va = 1 - (1 - 0.9 * p_va) * (1 - r_va)
    susp = choose_threshold(yva, sys_va, "min_recall", ops_cfg.get("suspicious_min_recall", 0.98))
    scam = choose_threshold(yva, sys_va, "min_precision", ops_cfg.get("scam_min_precision", 0.97))
    susp_score = int(np.floor(100 * susp))
    scam_score = max(susp_score + 1, int(np.ceil(100 * scam)))
    band = selective_band(yva, p_va, t_model, ops_cfg.get("selective_target_accuracy", 0.98))
    operating_points = {
        "model_threshold": round(float(t_model), 4),
        "suspicious_score": susp_score,
        "scam_score": scam_score,
        "uncertain_band": {"low": band["low"], "high": band["high"]},
        "chosen_on": "val",
        "rules": {"suspicious": f"highest risk-score cut-off with val recall >= {ops_cfg.get('suspicious_min_recall', 0.98)}",
                  "scam": f"lowest risk-score cut-off with val precision >= {ops_cfg.get('scam_min_precision', 0.97)}",
                  "model_threshold": f"{strategy} on val",
                  "uncertain_band": f"narrowest band around model_threshold (half-width <= {band.get('max_half_width_tried')}) "
                                    f"with val selective accuracy >= {band['target_accuracy']}; "
                                    f"target met: {band.get('target_met')}"},
        "val_selective": band,
    }
    system = {}
    for k, rows in tests.items():
        r_te = rules([r["text"] for r in rows])
        s = 1 - (1 - 0.9 * p_te[k]) * (1 - r_te)
        y = _y(rows)
        score = np.round(100 * s)
        ops_now = {"scam_score": scam_score, "suspicious_score": susp_score}
        verdicts = np.array([verdict_for(sc, ops_now, h) for sc, h in zip(score, rules.hits([r["text"] for r in rows]))])
        flagged = (verdicts != "Safe").astype(float)
        inside = (p_te[k] >= band["low"]) & (p_te[k] <= band["high"]) & (r_te == 0)
        outside = ~inside
        sel_acc = float(((p_te[k][outside] >= t_model).astype(int) == y[outside]).mean()) if outside.any() else None
        system[k] = {
            # uses the same verdict function as the API (incl. the safety-floor rules)
            "flag_if_suspicious_or_scam": binary_metrics(y, flagged, 0.5, probabilistic=False),
            "flag_if_scam": binary_metrics(y, score / 100, scam_score / 100, probabilistic=False),
            "verdict_counts": {v: int((verdicts == v).sum()) for v in ("Safe", "Suspicious", "Scam")},
            "abstention_uncertain_band": {"abstained": int(inside.sum()), "coverage": round(float(outside.mean()), 4),
                                          "model_accuracy_on_covered": round(sel_acc, 4) if sel_acc is not None else None},
        }
    results["system"] = {"main_model": main, "operating_points": operating_points, "test": system}

    category_model = None
    if cfg.get("category_head"):
        tr_c = [(i, r) for i, r in enumerate(train) if r["category"]]
        if tr_c:
            category_model = make_category_model(seed, cfg.get("model_params"))
            category_model.fit(Xtr[[i for i, _ in tr_c]], [r["category"] for _, r in tr_c])
            results["category"] = {}
            for k, rows in tests.items():
                idx = [i for i, r in enumerate(rows) if r["category"]]
                if idx:
                    pred = category_model.predict(Xte[k][idx])
                    results["category"][k] = category_metrics([rows[i]["category"] for i in idx], list(pred),
                                                              ALL_CATEGORIES)

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        results["errors"] = {}
        for k in cfg.get("error_analysis", {}).get("test_sets", []):
            if k in tests:
                results["errors"][k] = dump_errors(out_dir / f"errors_{k}.csv", feats, model, tests[k], p_te[k],
                                                   t_model, cfg["error_analysis"].get("top_k", 25))

    results["data"] = {name: registry.info(name) for name in
                       sorted({s["dataset"] for part in ("train", "val") for s in cfg[part]} |
                              {s["dataset"] for specs in cfg["test_sets"].values() for s in specs})}
    results["sizes"] = {"train": len(train), "val": len(val), **{k: len(v) for k, v in tests.items()},
                        "n_features": int(Xtr.shape[1])}
    results["seconds"] = round(time.time() - t0, 1)
    results["_fitted"] = {"features": feats, "binary": model, "category": category_model}
    return results


def write_run(cfg: dict, results: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in results.items() if not k.startswith("_")}
    (out_dir / "metrics.json").write_text(json.dumps(clean, indent=2) + "\n")
    (out_dir / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (out_dir / "env.json").write_text(json.dumps(env_info(), indent=2) + "\n")
    (out_dir / "summary.md").write_text(summary_markdown(cfg, clean))


def summary_markdown(cfg: dict, res: dict) -> str:
    lines = [f"# {cfg['name']}", "", cfg.get("description", ""), "",
             f"Sizes: {res['sizes']}", "",
             "Threshold for each model chosen on the validation split; test metrics at that threshold.", ""]
    for k in next(iter(res["models"].values()))["test"]:
        lines += [f"## Test set `{k}`", "",
                  "| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |", "|---|---|---|---|---|---|---|---|---|"]
        for name, m in res["models"].items():
            t = m["test"][k]["at_tuned"]
            lines.append(f"| {name} | {t['precision']:.3f} | {t['recall']:.3f} | {t['f1']:.3f} | {t['roc_auc']} | "
                         f"{t['pr_auc']} | {t['brier']} | {t['ece']} | {t['threshold']:.3f} |")
        s = res["system"]["test"][k]
        a, b = s["flag_if_suspicious_or_scam"], s["flag_if_scam"]
        lines += ["", f"Full system ({res['system']['main_model']} + rules): "
                      f"flag≥Suspicious P={a['precision']:.3f} R={a['recall']:.3f} F1={a['f1']:.3f}; "
                      f"flag=Scam P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f}; "
                      f"verdicts {s['verdict_counts']}; abstention {s['abstention_uncertain_band']}", ""]
    ops = res["system"]["operating_points"]
    lines += ["## Operating points (chosen on val)", "", "```", json.dumps({k: ops[k] for k in
              ("model_threshold", "suspicious_score", "scam_score", "uncertain_band")}, indent=2), "```", ""]
    if res.get("category"):
        lines += ["## Category head (synthetic labels only)", ""]
        for k, c in res["category"].items():
            lines.append(f"- `{k}`: accuracy {c['accuracy']}, macro-F1 {c['macro_f1']} (n={c['n']})")
    return "\n".join(lines) + "\n"
