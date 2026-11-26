# Classical NLP vs DistilBERT for ScamShield (2026-11-26)

Two runs, both on the Track C data (synthetic + UCI train / val, three test sets), both committed:

| Run | Code | Folder |
|---|---|---|
| Classical analysis: CV search, tuned NB / LogReg / SVM, thresholds, abstention | `backend/ml/analysis.py`, `tuning.py` | [`results/combined-analysis-20261126-140615`](../results/combined-analysis-20261126-140615/summary.md) |
| DistilBERT fine-tune + deployment costs | `backend/ml/transformer.py` | [`results/combined-distilbert-20261126-141142`](../results/combined-distilbert-20261126-141142/metrics.json) |

Rules used in both runs:
- Fit or search on **train** only.
- Choose thresholds, temperature and the abstention band on **val**.
- Score **test** once.
- Set every model's threshold the same way: max F1 on val.

The shipped model (`scamshield-2.0.0`) is not changed by either run.

## 1. Model selection: cross-validation and hyperparameter search

**Set-up**
- Scheme: `StratifiedGroupKFold(5)` on the 9,074 training rows.
  - Stratified by source × label, so every fold has about 41.5% scams and the same synthetic/UCI mix.
  - Grouped by synthetic template, so no template sits on both sides of a fold.
  - TF-IDF is refit inside every fold.
- Grid: 3 feature sets × (NB α ∈ {0.01…1}, LogReg C ∈ {0.25…64}, LinearSVC C ∈ {0.03…8}). That is 45 configurations × 5 folds = 225 fits, about 10 seconds on 4 CPUs.
- Selection metric: mean PR-AUC.

| Model | Best features | Best params | CV PR-AUC | CV F1 @ default threshold |
|---|---|---|---|---|
| MultinomialNB | word+char | α = 0.1 | **0.980 ± 0.012** | 0.898 ± 0.033 |
| LogisticRegression (balanced) | word+char | C = 1 | 0.969 ± 0.022 | **0.902 ± 0.025** |
| LinearSVC (balanced) | word+char | C = 0.03 | 0.969 ± 0.022 | 0.894 ± 0.022 |

Feature ablation (CV PR-AUC, best params per cell):

| Model | word 1–2 | char_wb 3–5 | word + char |
|---|---|---|---|
| NB | 0.975 | 0.976 | **0.980** |
| LogReg | 0.964 | 0.969 | **0.969** |
| SVM | 0.964 | 0.969 | **0.969** |

**What this shows**
- **Grouped CV is harder than the fixed split.** CV PR-AUC is about 0.97, while the fixed val/test sets give 0.99. Each CV fold holds out whole templates, and training data is 20% smaller.
- **No model is significantly better.** The corrected resampled t-test (Nadeau & Bengio, which accounts for folds sharing training data) gives:
  - LogReg − NB PR-AUC: −0.012, p = 0.22
  - LogReg − SVM F1: +0.008, p = 0.15
  - With 5 folds and these standard deviations, none of the gaps is distinguishable from noise.
- **Character n-grams carry most of the signal.** Adding word n-grams gives a small, consistent gain.
- **NB ranks well in CV but fails on real held-out data.**
  - On real UCI test, NB scores F1 0.925 and PR-AUC 0.953, against 0.97 and 0.99 for LogReg.
  - Its probabilities are extreme: the F1-optimal threshold on val is 0.049.
  - Sigmoid calibration does not rescue it (val ECE 0.075 → 0.089).
- **Tuning confirms the shipped settings.**
  - CV prefers C = 1. The shipped model uses C = 4.
  - On test, C = 4 is as good or slightly better (UCI F1 0.973 vs 0.968, synthetic 0.961 vs 0.961).
  - So v2.0.0 is kept, and C ∈ [1, 4] is a flat region.

Figures:
- [CV PR-AUC](../results/combined-analysis-20261126-140615/figures/cv_pr_auc.png)
- [CV F1](../results/combined-analysis-20261126-140615/figures/cv_f1.png)

## 2. Test results at the validation-chosen threshold

| Model | synthetic P / R / F1 | UCI P / R / F1 | UCI PR-AUC | UCI ECE | out-of-domain ROC-AUC |
|---|---|---|---|---|---|
| NB (tuned) | 0.933 / 0.964 / 0.948 | 0.956 / 0.896 / 0.925 | 0.953 | 0.026 | 0.43 |
| LinearSVC + sigmoid (tuned) | 0.948 / 0.914 / 0.931 | 1.000 / 0.917 / 0.957 | 0.988 | 0.013 | 0.43 |
| LogReg + sigmoid (tuned C = 1) | 0.942 / 0.981 / 0.961 | 1.000 / 0.938 / 0.968 | 0.989 | 0.012 | 0.44 |
| **LogReg + sigmoid (shipped v2.0.0, C = 4)** | 0.942 / 0.980 / **0.961** | 1.000 / 0.948 / **0.973** | 0.991 | **0.011** | 0.45 |
| DistilBERT (fine-tuned, epoch 2) | **0.995** / 0.921 / 0.956 | 1.000 / 0.896 / 0.945 | **0.999** | **0.005** | 0.50 |
| DistilBERT + temperature scaling | 0.995 / 0.921 / 0.956 | 1.000 / 0.896 / 0.945 | 0.999 | 0.047 | 0.50 |

Figures:
- ROC / PR, classical models: [synthetic](../results/combined-analysis-20261126-140615/figures/roc_pr_synthetic_test.png) · [UCI](../results/combined-analysis-20261126-140615/figures/roc_pr_uci_test.png) · [out-of-domain](../results/combined-analysis-20261126-140615/figures/roc_pr_all_scam_spam_short.png)
- ROC / PR with DistilBERT: [synthetic](../results/combined-distilbert-20261126-141142/figures/roc_pr_synthetic_test.png) · [UCI](../results/combined-distilbert-20261126-141142/figures/roc_pr_uci_test.png)
- Confusion matrices: [synthetic](../results/combined-analysis-20261126-140615/figures/confusion_synthetic_test.png) · [UCI](../results/combined-analysis-20261126-140615/figures/confusion_uci_test.png)

## 3. Calibration

- **Sigmoid calibration with template-grouped folds** is what makes the LogReg probability usable.
  - Val ECE: 0.077 uncalibrated → **0.035** calibrated (tuned C).
  - UCI test ECE: 0.056 → 0.012.
  - See the [reliability diagram on val](../results/combined-analysis-20261126-140615/figures/reliability_val.png).
- **NB is over-confident** (the usual result for NB, because it assumes features are independent). Its scores cluster at 0 and 1, and calibration does not fix it here.
- **DistilBERT also looks well calibrated on UCI** (ECE 0.005), but only because almost every score is near 0 or 1.
- **Temperature scaling (T = 2.68, fitted on val NLL) made things worse:**
  - It improved val Brier (0.074 → 0.061).
  - It made test ECE **worse** (UCI 0.005 → 0.047, synthetic 0.048 → 0.068).
- **Why temperature scaling failed here:** the val set mixes two populations.
  - On synthetic val the transformer is confidently wrong about unseen templates, which pushes T up.
  - On real UCI messages it was already calibrated, so the larger T makes it under-confident there.
  - One global temperature cannot fit both. Calibration has to be checked per population, not only on the pooled val set.
  - Reliability diagrams with DistilBERT: [UCI](../results/combined-distilbert-20261126-141142/figures/reliability_uci_test.png) · [synthetic](../results/combined-distilbert-20261126-141142/figures/reliability_synthetic_test.png)

## 4. Decision thresholds

Shipped-recipe LogReg (tuned) with thresholds chosen on val ([sweep and cost curve](../results/combined-analysis-20261126-140615/figures/threshold_sweep_val.png)):

| Rule | t | UCI confusion [[TN, FP], [FN, TP]] | UCI P / R | synthetic FPR |
|---|---|---|---|---|
| default 0.5 | 0.500 | [[678, 0], [6, 90]] | 1.000 / 0.938 | 0.109 |
| max F1 | 0.493 | [[678, 0], [6, 90]] | 1.000 / 0.938 | 0.109 |
| recall ≥ 0.95 | 0.450 | [[678, 0], [5, 91]] | 1.000 / 0.948 | 0.109 |
| **min expected cost (FN = 5, FP = 1)** | 0.122 | [[672, 6], [2, 94]] | 0.940 / 0.979 | **0.452** |

**Reading the table**
- If a missed scam is assumed to cost five times a false alarm, the cost-optimal threshold drops to 0.12.
  - On real SMS this trades 6 false alarms for 4 more caught scams.
  - On the synthetic set it flags 45% of legitimate messages, which users would not tolerate.
- The cost ratio is a product decision, not a modelling one.
  - The app handles it by not relying on the model threshold alone.
  - Two risk-score cut-offs (Suspicious ≥ 60, Scam ≥ 71) give a "Suspicious" middle tier that raises recall without labelling a message a scam.
- **DistilBERT's threshold does not transfer.**
  - Its val-chosen threshold is 0.999 (0.93 after temperature scaling), because its val scores are packed against 1.
  - At that threshold it misses 10 UCI spams that sit at p = 0.73–0.89.
  - Its ranking is the best of all models (UCI PR-AUC 0.999), but its F1 at the chosen threshold is lower (0.945 vs 0.973).
  - With a saturated transformer the threshold itself is fragile, and calibration and threshold choice need real in-domain validation data.

## 5. Abstention

Uncertain band chosen on val: the narrowest band around the threshold whose outside reaches 98% selective accuracy.

| Model | Band | Val coverage / selective accuracy | UCI test: abstained, accuracy on answered | Synthetic test: abstained, errors before → after |
|---|---|---|---|---|
| LogReg (tuned) | 0.19–0.79 | 0.80 / 0.975 (target missed) | 8 abstained, 0.996 | 450 abstained, 100 → 15 errors |
| DistilBERT (temp-scaled) | 0.88–0.98 | 0.50 / 0.983 (target met) | – | – |

- For LogReg, abstaining on 23% of synthetic test messages removes 85% of the errors.
- On out-of-domain email text abstention barely helps: accuracy goes from 0.48 to 0.50. **The model is confidently wrong there, so input-quality checks and domain checks are needed, not just a probability band.**
- DistilBERT meets the accuracy target only by refusing half of the validation messages.
- See the [risk–coverage curves](../results/combined-analysis-20261126-140615/figures/risk_coverage.png) and the [UCI risk–coverage curve with DistilBERT](../results/combined-distilbert-20261126-141142/figures/risk_coverage_uci_test.png).

## 6. Errors: where each model fails

| Case | TF-IDF LogReg | DistilBERT |
|---|---|---|
| Hinglish sextortion ("Tumhari video mere paas hai … bhejo warna …") | missed | **missed** (p ≈ 0.07–0.10) |
| Hinglish OTP request ("OTP aa gaya hoga, please bhej do jaldi …") | p = 0.30 (missed; rules catch it) | p = 0.51 (borderline) |
| Legitimate "Money received! Rs 45000 … UPI Ref …" | p = 0.69 (false positive) | p = 0.86 (false positive) |
| Legitimate Amazon Pay cashback promo (with typos) | not in the top-25 FPs | p ≈ 0.94 (false positive) |
| UCI chatty marketing ("Are you unique enough?", "txt HORO …") | missed | missed |
| Out-of-domain email spam | ROC-AUC 0.45 | ROC-AUC 0.50 |

- **Pre-training did not help with Hinglish.** `distilbert-base-uncased` is an English model, and romanised Hindi becomes word pieces it has little prior knowledge of.
- **Both models fail on the same messages.** They are limited by the same training data, not by model capacity. Per-file errors: [classical](../results/combined-analysis-20261126-140615/errors_synthetic_test.csv), [DistilBERT](../results/combined-distilbert-20261126-141142/errors_synthetic_test.csv).

## 7. Deployment cost

Measured in this container: 4 vCPU, batch size 1, **one inference thread**, 300 real and synthetic test messages.

| | TF-IDF + LogReg (shipped) | DistilBERT fp32 | DistilBERT int8 (dynamic) |
|---|---|---|---|
| Parameters | ~32k n-gram weights | 67 M | 67 M (int8 linear layers) |
| Artifact on disk | **2.4 MB** | 268.5 MB | 138.7 MB |
| Peak RAM, fresh process (load + 1 prediction) | **175 MB** | 964 MB | 1,355 MB (fp32 loaded, then quantised) |
| Latency p50 / p95 (probability only) | **2.2 / 2.6 ms** | 41.9 / 53.2 ms | 12.6 / 17.7 ms |
| Latency p50 / p95 (full API: probability + 13-way category + explanation spans) | 3.5 / 5.4 ms | – | – |
| Throughput, 1 thread | ~446 msg/s | ~24 msg/s | ~79 msg/s |
| Training time | ~20 s (2 CPUs, incl. calibration) | 774 s (3 epochs, 4 CPUs) | + quantisation |
| Explanation | exact, free: coefficient × tf-idf | leave-one-word-out occlusion: 14–16 forward passes, 550–690 ms per message | same |
| Accuracy at the val threshold | as in §2 | as in §2 | **recall drops**: synthetic 0.92 → 0.70, UCI 0.90 → 0.75 (PR-AUC unchanged at 0.99) |

- **int8 changes the threshold.** Quantisation keeps the ranking (PR-AUC 0.990 / 0.999) but shifts the logits. At the fp32 threshold it loses a quarter of the scams. A quantised model needs its own threshold and calibration chosen on validation data; it cannot reuse the fp32 operating points.
- **The occlusion explanation is weak where it matters most.**
  - On the KYC message, DistilBERT is so sure (p = 0.97) that removing any single word changes the probability by less than 0.002, so the explanation shows almost nothing.
  - The linear model's explanation is exact and gives the four phrases the UI highlights: "account will be blocked", "Update KYC", the link, and "Dear customer your".

## 8. Why the lightweight model is the right choice here

The transformer ranks slightly better on the two in-domain test sets (PR-AUC 0.999 vs 0.991 on UCI, 0.995 vs 0.993 on synthetic). It is **not** better at the decision the product actually makes, and it is worse on every deployment axis:

1. **Accuracy at the operating point.**
   - At validation-chosen thresholds, TF-IDF + LogReg has higher F1 on both test sets (UCI 0.973 vs 0.945, synthetic 0.961 vs 0.956).
   - Both fail on the same Hinglish and out-of-domain messages.
   - The bottleneck is data (no real labelled Indian scam SMS), not model capacity. A 67M-parameter model trained on 214 templates mostly learns the templates better.
2. **Latency and cost.**
   - About 19× faster per message on one CPU thread (2.2 ms vs 42 ms), and still 6× faster than int8 DistilBERT.
   - The API scores live as the user types (400 ms debounce) on a free-tier Render instance. TF-IDF fits that budget; DistilBERT on a shared CPU would not keep up with several concurrent users.
3. **Memory and size.**
   - 175 MB vs ~1 GB peak RAM. Render's free and starter instances have 512 MB, so the transformer would not even load there.
   - The 2.4 MB artifact is committed to git and loads in milliseconds. The 269 MB transformer needs model storage and cold-start time.
4. **Explainability.**
   - The product's core promise is "explain why", with highlighted phrases. The linear model gives exact additive contributions for free.
   - The transformer needs ~15 extra forward passes (about 0.6 s) for an approximate explanation that goes blank on confident predictions.
5. **Calibration and thresholds.**
   - The API shows a probability and uses fixed cut-offs. The calibrated linear model's ECE is 0.011 and its threshold transfers between populations.
   - The transformer's scores are saturated. Its threshold does not transfer, temperature scaling over-corrected, and quantisation moves the threshold again.
6. **Privacy, offline use and auditability.**
   - A model this small can run in the browser or on a phone, so messages never leave the device.
   - It can be retrained in seconds when scammers change scripts.
   - Its weights can be read by a reviewer.

**When a transformer would be worth it:**
- A real, labelled Indian scam SMS dataset exists, so its extra ranking quality and paraphrase robustness can be measured on the target domain.
- A multilingual model (e.g. MuRIL, IndicBERT, XLM-R) is used for Hinglish and Indic scripts.
- It is distilled or quantised with its own calibration and thresholds, and run in a second stage only on the messages the linear model abstains on. That is about 1% of real UCI traffic, so the cost is small.

## Caveats

- **Single seeds.** One seed per run, with no confidence intervals beyond CV fold spread. DistilBERT's 0.945 vs 0.973 UCI F1 is 10 vs 6 misses out of 96 spams, which is a small difference.
- **DistilBERT hyperparameters were not tuned** (lr 5e-5, batch 32, max length 128, 3 epochs, best epoch by val PR-AUC = 2).
- **The latency numbers are one container's numbers.** Their ratios matter more than their absolute values.
- **No real Indian scam data.** Everything about Indian scam patterns is measured on synthetic data.
