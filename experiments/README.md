# Experiments

Each experiment is one JSON config. A run of that config trains every model on the same features and splits, then evaluates them all on the same test sets.

## How to run

The runner needs Python on the path with the backend requirements installed. Run it from the repo root:

```bash
python -m ml.data.registry          # run from backend/: downloads UCI + all-scam-spam, builds data/processed/*.csv
python experiments/run.py --config experiments/configs/syn2real.json
python experiments/run.py --config experiments/configs/real_uci.json
cd backend && python -m ml.train    # the "combined" config + saves the production artifact
```

A run writes `experiments/results/<name>-<UTC timestamp>/`, which contains:

| File | What it holds |
|---|---|
| `metrics.json` | Every model's val + test metrics: P/R/F1, ROC-AUC, PR-AUC, confusion matrix, Brier, ECE, reliability table. Also the full-system metrics, operating points, category head and error summary. |
| `config.json` | Exact config used |
| `env.json` | UTC timestamp, git commit (+ dirty flag), Python / scikit-learn / numpy / scipy / joblib versions, preprocessing version |
| `summary.md` | Human-readable tables |
| `errors_<test_set>.csv` | Top-25 false positives and false negatives of the main model, with the n-gram features that pushed each one |

Dataset names, hashes and row counts are recorded under `metrics.json → data`. They are copied from `backend/data/manifest.json`.

## How to add an experiment

1. Copy a config in `configs/` and change `name`, `train`, `val`, `test_sets`, `models` or `model_params`.
   - Datasets are referenced by manifest name: `synthetic_in`, `uci_sms_spam`, `all_scam_spam_short`.
   - Splits are `train` / `val` / `test`.
2. To add a new dataset, write a loader in `backend/ml/data/` that returns `Record`s (see `schema.py`) and register it in `registry.py`.
3. Run the config. Commit the results folder only if the run finished and used committed code (`env.json → git_dirty: false`).

## Rules the runner enforces
- Features, models and the category head are fit on **train** only.
- Thresholds, the Safe/Suspicious/Scam operating points and the abstention band are chosen on **val** only.
- **Test** is scored once.
- Calibrated models use GroupKFold on template ids, so a synthetic template never sits on both sides of a calibration fold.

## Runs (2026-09-16)

| Run | Train / tune on | Main result | Folder |
|---|---|---|---|
| Track A: synthetic → real | synthetic only | Synthetic test F1 0.990; **real UCI test F1 0.249** | `results/syn2real-20260916-131719` |
| Track B: real → real | UCI only | UCI test F1 0.984; synthetic test F1 0.692 | `results/real_uci-20260916-131734` |
| Track C: combined (shipped model v2.0.0) | synthetic + UCI | Synthetic test F1 0.961; UCI test F1 0.973; all-scam-spam (email, out-of-domain) F1 0.219 | `results/combined-train-v2.0.0-20260916-132846` |
| Ablation: random calibration folds | same as C | logreg_cal val ECE 0.123 (grouped: 0.050) | `results/ablation_random_calib_folds-20260916-131947` |

The F1 values are for `logreg_cal` at its validation-chosen threshold. All baselines are in each run's `summary.md`.

The write-up is in [`reports/2026-09-16-three-tracks.md`](reports/2026-09-16-three-tracks.md).

Not run yet:
- **Real Indian scam SMS:** dataset required before evaluation. The one candidate found, `gandharvbakshi/SMS-dataset-OTP-OTP_INTENT_Phishing`, is gated on Hugging Face.
- **Repeated seeds / confidence intervals:** experiment not run.
