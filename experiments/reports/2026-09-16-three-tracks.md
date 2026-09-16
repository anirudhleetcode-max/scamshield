# Synthetic vs real: three training tracks (2026-09-16)

**Runs:**
- `ablation_random_calib_folds-20260916-131947` (ablation)
- `syn2real-20260916-131719`
- `real_uci-20260916-131734`
- `combined-train-v2.0.0-20260916-131746`

Tracks A–C were run at git commit `28ed024` and the ablation at `dd3f1fe`, all on a clean tree, with scikit-learn 1.8.0 and Python 3.11.15.

**Datasets** (full details in `backend/data/manifest.json`):
- `synthetic_in` v2.0 (**synthetic**): 8,624 rows, split by template (train 5,463 / val 1,214 / test 1,947).
- `uci_sms_spam` (**real**, CC BY 4.0): 5,159 rows after de-duplication. Stratified split: train 3,611 / val 774 / test 774 (96 spam).
- `all_scam_spam_short` (**real**, Apache-2.0): 8,389 rows of at most 320 characters, 3,591 of them spam. Used for testing only. The rows are mostly email fragments.

**How to read the tables:**
- Each model's threshold was chosen on its own track's validation split (max F1).
- Brier and ECE are measured at the raw probability.
- "System" means `logreg_cal` combined with the rule engine, using the val-chosen Safe/Suspicious/Scam cut-offs and the safety-floor rules.

## 1. Headline: synthetic-only training does not transfer to real SMS

Test set: UCI (real).

| Trained on | Model | P | R | F1 | PR-AUC | Brier | ECE |
|---|---|---|---|---|---|---|---|
| synthetic (A) | majority (all spam) | 0.124 | 1.000 | 0.221 | 0.124 | 0.344 | 0.485 |
| synthetic (A) | rules only | 0.722 | 0.271 | 0.394 | 0.294 | – | – |
| synthetic (A) | logreg_cal | 0.148 | 0.771 | 0.249 | 0.226 | 0.321 | 0.377 |
| UCI (B) | nb | 0.979 | 0.958 | 0.968 | 0.983 | 0.008 | 0.008 |
| UCI (B) | logreg_cal | 0.990 | 0.979 | 0.984 | 0.995 | 0.003 | 0.011 |
| UCI (B) | linsvc_cal | 0.979 | 0.979 | 0.979 | 0.995 | 0.003 | 0.010 |
| combined (C) | logreg_cal | 1.000 | 0.948 | 0.973 | 0.991 | 0.005 | 0.011 |
| combined (C) | linsvc_cal | 1.000 | 0.969 | 0.984 | 0.992 | 0.004 | 0.011 |

- The model trained only on synthetic data scores F1 0.249 on real SMS. The trivial "everything is spam" baseline scores 0.221.
- Its synthetic held-out F1 was 0.990. That number measures how well the model learns our own templates, not how well it detects real spam.
- The reverse holds too. Trained on UCI only, the model scores F1 0.692 and ROC-AUC 0.413 on the synthetic test set, which is worse than random ranking. UCI "spam" (UK premium-rate texts) and Indian UPI/KYC scams share very little vocabulary.

## 2. The combined model is the only one that is reasonable on both

| Test set | Model | P | R | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| synthetic | rules only | 0.992 | 0.772 | 0.868 | 0.881 | 0.918 |
| synthetic | nb | 0.933 | 0.964 | 0.948 | 0.988 | 0.994 |
| synthetic | logreg_noweight | 0.943 | 0.968 | 0.955 | 0.987 | 0.993 |
| synthetic | logreg_uncal (balanced) | 0.951 | 0.967 | 0.959 | 0.992 | 0.995 |
| synthetic | **logreg_cal** | 0.942 | 0.980 | 0.961 | 0.987 | 0.993 |
| synthetic | linsvc_cal | 0.942 | 0.982 | 0.962 | 0.986 | 0.993 |
| UCI | rules only | 0.722 | 0.271 | 0.394 | 0.625 | 0.294 |
| UCI | **logreg_cal** | 1.000 | 0.948 | 0.973 | 0.994 | 0.991 |
| all-scam-spam (OOD) | **logreg_cal** | 0.321 | 0.166 | 0.219 | 0.446 | 0.381 |

System view (Track C, shipped v2.0.0), comparing two ways of counting a message as flagged:

| Test set | Flag rule | P | R | F1 |
|---|---|---|---|---|
| synthetic | Suspicious or Scam | 0.967 | 0.948 | 0.957 |
| synthetic | Scam only | 0.996 | 0.888 | 0.939 |
| UCI | Suspicious or Scam | 0.989 | 0.948 | 0.968 |
| UCI | Scam only | 1.000 | 0.917 | 0.957 |

- **Class weighting** (`logreg_noweight` vs `logreg_uncal`) makes almost no difference once the threshold is tuned on validation. Threshold tuning does the same job as re-weighting.
- **Linear SVM vs logistic regression:** LinearSVC+calibration is marginally better on UCI (F1 0.984 vs 0.973). The two are otherwise tied. Logistic regression stays in production because its coefficients drive the explanations directly.
- **Rules alone** are precise on the synthetic scams (P 0.992), but they miss most real UK spam (R 0.271). The rules were written for Indian scam patterns.

## 3. Calibration

Calibration uses sigmoid scaling with GroupKFold(3) on template ids.

| Track | Set | logreg_uncal Brier / ECE | logreg_cal Brier / ECE |
|---|---|---|---|
| C | val | 0.0558 / 0.0624 | 0.0593 / **0.0503** |
| C | synthetic test | 0.0424 / 0.0777 | 0.0461 / 0.0754 |
| C | UCI test | 0.0065 / 0.0246 | **0.0053 / 0.0113** |
| B | UCI test | 0.0043 / 0.0256 | **0.0034 / 0.0105** |
| A | synthetic test | 0.0316 / 0.0963 | **0.0234 / 0.0578** |

**Ablation `ablation_random_calib_folds-20260916-131947`:** the same Track C recipe, but with random (not grouped) calibration folds. Calibration then makes things clearly *worse*:

| Set | Brier / ECE |
|---|---|
| val | 0.0855 / 0.1233 |
| synthetic test | 0.0866 / 0.1774 |
| UCI test | 0.0336 / 0.1478 |

UCI F1 at the val threshold also drops to 0.898, and synthetic PR-AUC drops from 0.993 to 0.936.

The cause is that the same template sits on both sides of a random fold. The fold predictions look over-confident, so the fitted sigmoid comes out too steep. Grouping the folds by template fixes it.

- On real UCI data, calibration more than halves ECE in both tracks.

## 4. Operating points and abstention (chosen on validation)

| Track | model_threshold | Suspicious ≥ | Scam ≥ | Uncertain band | Val coverage / selective acc. |
|---|---|---|---|---|---|
| A | 0.327 | 45 | 46 | 0.127–0.527 | 0.819 / 0.981 (target met) |
| B | 0.430 | 11 | 38 | none | 1.000 / 0.992 |
| **C (shipped)** | 0.496 | 60 | 71 | 0.196–0.796 | 0.813 / **0.966 (target 0.98 not met)** |

- In Track C, even the widest band tried (±0.3) does not reach 98% selective accuracy on the mixed validation set, and the model card says so.
- In the API, the band only produces "insufficient confidence" when no rule or community report fires.
- On the UCI test set that happens for 6 of 774 messages. On the synthetic test set it happens for 324 of 1,947.

## 5. Out-of-domain stress test (all-scam-spam short)

- Every model scores ROC-AUC below or near 0.5 on this set. The combined model is at 0.446, so it ranks spam slightly *below* ham.
- The set is dominated by lower-cased, space-tokenised business emails (Enron) and pharmacy/stock spam. Neither our Indian templates nor UK SMS spam resemble it.
- We report the number rather than tuning on it. The app should not be trusted on email text.

## 6. Error analysis (Track C, `errors_*.csv`)

**Synthetic test: 75 false positives, 25 false negatives.**
- All 25 of the most confident false positives come from one held-out legitimate template: "Money received! Rs X from NAME (upi-id) credited to your BANK account. UPI Ref N" (p = 0.69–0.83).
- The features that push them are the digit-shape n-grams `000`, `0000`, `00000` and the words `account`, `to`, `your`.
- Our normaliser maps every digit to `0`, so long amounts and reference numbers look like the large prize and loan amounts in scam templates.
- Possible fix: bucket number lengths or add a separate `<amount>` token.

**Synthetic test false negatives are mostly Hinglish:**
- "Bhai galti se tumhare number pe OTP aa gaya … bhej do" (p ≈ 0.08–0.11)
- "Tumhari video mere paas hai … bhejo warna" (p ≈ 0.2–0.5)
- "Bitcoin mining opportunity … no risk. Sign up at …"

The negative weights come from casual words (`do`, `mere`, `ko`, `no`, `at`), which the UCI ham data made "safe". The rule engine catches the OTP request (the safety floor makes it Suspicious). The Hinglish sextortion wording has no rule and is still missed. This is a gap in the rules.

**UCI test: 0 false positives, 5 false negatives.**
- Examples: "Will u meet ur dream partner soon? … txt HORO", "Are you unique enough? Find out … www.areyouunique.co.uk", and flirty premium-rate chat.
- They are written like personal messages. Arguably they are marketing, not scams, which is the label mismatch noted in the audit.

## Conclusions
1. **Synthetic results are not evidence of real-world accuracy.** The 0.99 → 0.25 drop in Track A is the single most important number in this project.
2. **Real data is needed.** The only real labelled SMS data available (UCI) fixes generic spam but says nothing about Indian UPI/KYC fraud. A labelled Indian scam SMS set is required before claiming real performance on the target problem.
3. **The shipped model** is Track C, logistic regression with group-aware calibration. Its cut-offs come from validation, and its card lists these limitations.
