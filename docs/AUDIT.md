# ScamShield audit (phase 2, step 0)

This audit was written before any phase-2 change, from a fresh read of the whole repo at commit `f62ecfd`.
Severity: **H** high, **M** medium, **L** low. The "Resolution" column was filled in at the end of phase 2.

## 1. ML and data

| # | Finding | Sev | Resolution |
|---|---|---|---|
| ML1 | The main corpus (≈8.6k rows, ~200 templates) is **synthetic**. The README, the `/api/model` output and the Insights "About the model" panel show its metrics as "Unseen wordings" F1 0.981 and never say the word *synthetic*. A reader will overestimate real-world accuracy. | H | Every surface now labels synthetic data: README, model card (`data_kind`), Model page, Insights panel. Synthetic and real results are reported in separate tables. |
| ML2 | Real data (UCI SMS Spam) is used, but only after **relabelling**: ham is turned into `personal`, and spam matching a prize regex is turned into `lottery_prize` (the rest is dropped). Real data never gets its own evaluation track; it is only mixed into the held-out set. | H | Loaders now use a common schema, and UCI rows keep only `label_binary` (`category=null`). There are three real-data tracks: synthetic→real, real→real, and combined. |
| ML3 | There are no baselines: no majority class, no rule-only, no NB/SVM comparison. | H | Added majority, rules-only, TF-IDF+MultinomialNB, LogReg with and without `class_weight`, LogReg uncalibrated vs calibrated, and LinearSVC+calibration. All run on the same splits. |
| ML4 | The only calibration evidence is "we used CalibratedClassifierCV". There is no Brier score, ECE or reliability table. | M | Added Brier, ECE (15 bins) and a reliability table for every probabilistic model, before and after calibration. |
| ML5 | The Safe/Suspicious/Scam cut-offs (35/70) are **magic numbers**, never tuned or validated. There is no validation split, and the shipped model is refit on the test set, so any tuning would leak. | H | A template-grouped validation split was added. Operating points are chosen on validation (precision/recall targets), saved in the model card, and read by the analyzer. The shipped model is trained on train+val only; test is never used for fitting or tuning. |
| ML6 | There is no abstention. A 3-word message, a Devanagari message (never in the training data) or a bare URL still gets a confident-looking verdict. | H | Added an `insufficient_confidence` state with explicit reasons: too short, non-Latin script, mostly URL, model in the uncertain band with no corroborating signal. |
| ML7 | There is no error-analysis script. The README describes weak classes but no errors file supports it. | M | Added `ml/errors.py`, which writes `experiments/results/<run>/errors.csv` with the top contributing tokens. README analysis is based on that file. |
| ML8 | Model versioning is just `MODEL_VERSION = "1.0"` inside the pickle. There is no sidecar card (training date, dataset hash, library versions, seed, hyper-parameters). | M | Versioned artifacts (`scamshield-<ver>.joblib` + `.card.json`). `/api/model` serves the card; the UI has a Model page. |
| ML9 | Code organisation: training, feature construction, evaluation and dataset generation are mixed across `ml/train.py` and `ml/generate_dataset.py`. `normalize` lives in `app/services`, but training imports it from there. | L | Split into `ml/preprocess.py`, `features.py`, `models.py`, `evaluate.py`, `errors.py`, `data/*`, `train.py`. `app/services/textprep.py` stays as a thin re-export for compatibility. |
| ML10 | There is no experiments structure, and runs are not recorded with git commit, environment or data hash. | M | Added `experiments/` with JSON configs, `run.py`, `results/<run_id>/` (metrics, config snapshot, env, errors) and `reports/`. |
| ML11 | The held-out sextortion class has F1 0.00 (its templates share little vocabulary with training). This is known but not investigated. | L | Documented in error analysis. The synthetic category head is kept but clearly described as synthetic-only. |
| ML12 | Semantic mismatch: UCI "spam" includes marketing, but the product treats marketing as *not* a scam. Any real-data score is affected by this. | M | Documented in the README and the report. Per-source metrics show its effect on synthetic promotional messages. |

## 2. Backend and security

| # | Finding | Sev | Resolution |
|---|---|---|---|
| S1 | The JWT secret defaults to `change-me-in-production`. The app starts silently with it, and tests set their own. | H | `ENV` setting added. Production refuses to start with a placeholder or short secret. Development warns and generates an ephemeral random secret. `.env.example` explains how to generate one. |
| S2 | There is no login rate limiting (unlimited password guessing). | M | Added an in-memory sliding window per IP+email (10 attempts / 5 min → 429). |
| S3 | If the model file is missing or corrupt, the app crashes at startup (the lifespan raises). `/api/health` doesn't report model state. | H | Startup catches load errors and logs them. Health returns `status: degraded`. Analysis endpoints return 503 with a clear message. Lookup and reports keep working. |
| S4 | Model inference has no timeout. | L | `asyncio.wait_for` (configurable, default 10 s) → 503. |
| S5 | The body-size limit only checks `Content-Length`. Chunked bodies bypass it (pydantic `max_length` still caps the text fields). | L | Documented. Text fields stay capped at 2,000 chars and the lookup value at 500. |
| S6 | Logging: the unhandled-error handler logs the traceback, but there are no access logs, and nothing ensures message text is never logged. | L | Added a request log line (method, path, status, ms; no bodies or query strings). Message text is never logged. |
| S7 | The minimum password length is 6. | L | Raised to 8 for new registrations. Login is unchanged. |
| S8 | There are no file uploads in this app, so upload/magic-byte validation and path traversal don't apply. User input never becomes a file path. | — | N/A (documented). |
| S9 | CORS is restricted to configured origins (good). Credentials are allowed although the app uses bearer tokens. | L | `allow_credentials` set to false. Methods and headers narrowed. |
| S10 | Demo seed data looks like real activity (user "Ananya Rao", 78 checks). Nothing marks it as demo. | M | Seeded users and checks carry `is_demo` / `demo` flags. `/api/auth/me` exposes `is_demo`, and the UI shows a "Demo account — seeded sample data" banner. |

## 3. Frontend and UX

| # | Finding | Sev | Resolution |
|---|---|---|---|
| U1 | The Model info shown in the UI omits synthetic-vs-real and limitations. | H | New Model page (nav item) with the card, per-track metrics, operating points and limitations. The Insights panel links to it. |
| U2 | Deleting a check or report has no confirmation. | M | Confirm dialog (native `<dialog>`). |
| U3 | Loading states are the plain text "Loading…". There are no toasts for delete or report errors. | L | Skeleton rows and a small toast provider. |
| U4 | There is no UI for low confidence (see ML6). | H | The VerdictPanel shows an "Insufficient confidence" state with reasons and the calibrated confidence. |
| U5 | No frontend unit tests. | M | vitest + Testing Library: verdict/abstention rendering, highlight segmentation, report form validation, history error state. |

## 4. Tests and repo

| # | Finding | Sev | Resolution |
|---|---|---|---|
| T1 | There are no robustness tests: malformed JSON, missing model, corrupt model, non-Latin input, low-confidence path. | M | Added in `tests/test_robustness.py`. |
| T2 | There is no CI. | L | `.github/workflows/ci.yml` (pytest with a mongo service, frontend build + vitest). Not executed here. |
| T3 | There is no LICENSE, and the README lacks the required section order. | L | MIT LICENSE. README rewritten in the required order. |
| T4 | `.gitignore` ignores all of `backend/ml/data/`, which would also hide new loader code placed there. | L | Raw and processed data moved to `backend/data/{raw,processed}` (ignored). `backend/data/manifest.json` and README are committed. |

## Prioritised plan

1. Data layer with a common schema and manifest. Label synthetic data everywhere.
2. Restructure the ML package. Add baselines and calibration metrics. Build the experiment runner with three real tracks plus the synthetic track.
3. Threshold tuning on validation, feeding the operating points in the model card. Add the abstention logic.
4. Versioned artifact, model card and `/api/model`. Degraded startup.
5. Security: JWT secret policy, login rate limit, logging, CORS.
6. Frontend: Model page, abstention UI, confirm dialogs, skeletons, toasts, demo banner, vitest.
7. Error analysis. README rewrite. CI. LICENSE. Screenshots. Final full test run.
