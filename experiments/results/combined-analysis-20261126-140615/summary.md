# Classical-ML analysis

CV: StratifiedGroupKFold(n_splits=5, shuffle=True, seed=42); stratify=source+label; groups=template id (synthetic) / message id (UCI); TF-IDF refit per fold; TRAIN split only

## Best configuration per model (CV on train, selected by mean PR-AUC)

| model | features | params | PR-AUC | ROC-AUC | F1 @ default | P | R |
|---|---|---|---|---|---|---|---|
| nb | word+char | {'alpha': 0.1} | 0.9804 ± 0.0119 | 0.9836 ± 0.0092 | 0.8984 ± 0.0334 | 0.879 | 0.921 |
| logreg | word+char | {'C': 1.0} | 0.9688 ± 0.0217 | 0.9773 ± 0.0147 | 0.9020 ± 0.0254 | 0.873 | 0.933 |
| linsvc | word+char | {'C': 0.03} | 0.9689 ± 0.0215 | 0.9771 ± 0.0146 | 0.8938 ± 0.0224 | 0.880 | 0.910 |

## Feature-set ablation (best params per cell, CV PR-AUC)

| model | word | char | word+char |
|---|---|---|---|
| nb | 0.9749 ± 0.0140 | 0.9758 ± 0.0138 | 0.9804 ± 0.0119 |
| logreg | 0.9644 ± 0.0263 | 0.9688 ± 0.0268 | 0.9688 ± 0.0217 |
| linsvc | 0.9635 ± 0.0269 | 0.9687 ± 0.0243 | 0.9689 ± 0.0215 |

## Paired comparison (corrected resampled t-test, Nadeau & Bengio)

| comparison | mean diff | folds LR better | t | p |
|---|---|---|---|---|
| logreg_minus_nb_pr_auc | -0.0117 | 1/5 | -1.439 | 0.2235 |
| logreg_minus_nb_f1 | +0.0036 | 3/5 | 0.184 | 0.8629 |
| logreg_minus_linsvc_pr_auc | -0.0001 | 4/5 | -0.058 | 0.9562 |
| logreg_minus_linsvc_f1 | +0.0081 | 5/5 | 1.763 | 0.1526 |

## Test `synthetic_test` (threshold = max F1 on val)

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| nb | 0.933 | 0.964 | 0.948 | 0.9876 | 0.9939 | 0.04 | 0.0406 | 0.049 |
| nb_cal | 0.969 | 0.926 | 0.947 | 0.9831 | 0.9917 | 0.0513 | 0.0748 | 0.621 |
| logreg_uncal (tuned) | 0.951 | 0.984 | 0.967 | 0.9932 | 0.9963 | 0.0504 | 0.1206 | 0.486 |
| logreg_cal (tuned) | 0.942 | 0.981 | 0.961 | 0.9861 | 0.9925 | 0.047 | 0.0687 | 0.493 |
| linsvc_cal (tuned) | 0.948 | 0.914 | 0.931 | 0.9841 | 0.9911 | 0.0486 | 0.0743 | 0.640 |
| logreg_cal (shipped v2.0.0) | 0.942 | 0.980 | 0.961 | 0.9873 | 0.9932 | 0.0461 | 0.0754 | 0.496 |

## Test `uci_test` (threshold = max F1 on val)

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| nb | 0.956 | 0.896 | 0.925 | 0.9793 | 0.953 | 0.0234 | 0.0256 | 0.049 |
| nb_cal | 0.962 | 0.781 | 0.862 | 0.9788 | 0.9527 | 0.0236 | 0.0333 | 0.621 |
| logreg_uncal (tuned) | 1.000 | 0.948 | 0.973 | 0.9933 | 0.9895 | 0.0107 | 0.0562 | 0.486 |
| logreg_cal (tuned) | 1.000 | 0.938 | 0.968 | 0.9932 | 0.9894 | 0.0065 | 0.0123 | 0.493 |
| linsvc_cal (tuned) | 1.000 | 0.917 | 0.957 | 0.9925 | 0.9884 | 0.0078 | 0.0128 | 0.640 |
| logreg_cal (shipped v2.0.0) | 1.000 | 0.948 | 0.973 | 0.9941 | 0.9906 | 0.0053 | 0.0113 | 0.496 |

## Test `all_scam_spam_short` (threshold = max F1 on val)

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| nb | 0.330 | 0.191 | 0.242 | 0.434 | 0.3945 | 0.4203 | 0.4156 | 0.049 |
| nb_cal | 0.526 | 0.045 | 0.083 | 0.4279 | 0.3885 | 0.3857 | 0.3741 | 0.621 |
| logreg_uncal (tuned) | 0.321 | 0.159 | 0.212 | 0.457 | 0.3896 | 0.3259 | 0.2698 | 0.486 |
| logreg_cal (tuned) | 0.280 | 0.139 | 0.185 | 0.4363 | 0.3745 | 0.3952 | 0.3677 | 0.493 |
| linsvc_cal (tuned) | 0.196 | 0.059 | 0.091 | 0.4325 | 0.3723 | 0.3954 | 0.372 | 0.640 |
| logreg_cal (shipped v2.0.0) | 0.321 | 0.166 | 0.219 | 0.4456 | 0.3813 | 0.3893 | 0.3492 | 0.496 |

## Decision thresholds for the main model (chosen on val)

| rule | t | synthetic_test P / R / F1 / FPR | uci_test P / R / F1 / FPR | all_scam_spam_short P / R / F1 / FPR |
|---|---|---|---|---|
| default 0.5 | 0.500 | 0.942 / 0.981 / 0.961 / 0.109 | 1.000 / 0.938 / 0.968 / 0.000 | 0.279 / 0.135 / 0.182 / 0.262 |
| max F1 | 0.493 | 0.942 / 0.981 / 0.961 / 0.109 | 1.000 / 0.938 / 0.968 / 0.000 | 0.280 / 0.139 / 0.185 / 0.267 |
| min cost (FN=5, FP=1) | 0.122 | 0.799 / 0.994 / 0.886 / 0.452 | 0.940 / 0.979 / 0.959 / 0.009 | 0.387 / 0.459 / 0.420 / 0.544 |
| recall >= 0.95 | 0.450 | 0.942 / 0.985 / 0.963 / 0.109 | 1.000 / 0.948 / 0.973 / 0.000 | 0.291 / 0.159 / 0.205 / 0.289 |

## Abstention (band 0.193–0.793 chosen on val; val coverage 0.7978, selective accuracy 0.9754, target met: False)

| test set | abstained | coverage | accuracy (all) | accuracy (answered) | errors all -> answered |
|---|---|---|---|---|---|
| synthetic_test | 450 | 0.7689 | 0.9486 | 0.99 | 100 -> 15 |
| uci_test | 8 | 0.9897 | 0.9922 | 0.9961 | 6 -> 3 |
| all_scam_spam_short | 3168 | 0.6224 | 0.4784 | 0.5039 | 4376 -> 2590 |

## Figures

- `figures/confusion_all_scam_spam_short.png`
- `figures/confusion_synthetic_test.png`
- `figures/confusion_uci_test.png`
- `figures/cv_f1.png`
- `figures/cv_pr_auc.png`
- `figures/reliability_all_scam_spam_short.png`
- `figures/reliability_synthetic_test.png`
- `figures/reliability_uci_test.png`
- `figures/reliability_val.png`
- `figures/risk_coverage.png`
- `figures/roc_pr_all_scam_spam_short.png`
- `figures/roc_pr_synthetic_test.png`
- `figures/roc_pr_uci_test.png`
- `figures/threshold_sweep_val.png`
