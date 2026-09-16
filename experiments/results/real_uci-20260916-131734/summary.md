# real_uci

Track B - train, tune and test on REAL UCI SMS data (stratified 70/15/15). Synthetic test is reverse cross-domain.

Sizes: {'train': 3611, 'val': 774, 'synthetic_test': 1947, 'uci_test': 774, 'all_scam_spam_short': 8389, 'n_features': 27743}

Threshold for each model chosen on the validation split; test metrics at that threshold.

## Test set `synthetic_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.643 | 0.4986 | 0.5187 | 0.500 |
| rules_only | 0.992 | 0.772 | 0.868 | 0.8814 | 0.9182 | None | None | 0.120 |
| nb | 0.659 | 0.812 | 0.728 | 0.5633 | 0.7218 | 0.342 | 0.3321 | 0.912 |
| logreg_noweight | 0.604 | 0.736 | 0.663 | 0.4129 | 0.5715 | 0.3685 | 0.3155 | 0.221 |
| logreg_uncal | 0.614 | 0.764 | 0.681 | 0.4098 | 0.5675 | 0.3323 | 0.2845 | 0.445 |
| logreg_cal | 0.616 | 0.788 | 0.692 | 0.4132 | 0.5668 | 0.353 | 0.3262 | 0.430 |
| linsvc_cal | 0.631 | 0.803 | 0.707 | 0.4362 | 0.5784 | 0.3437 | 0.3006 | 0.403 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.658 R=0.999 F1=0.794; flag=Scam P=0.656 R=0.940 F1=0.773; verdicts {'Safe': 47, 'Suspicious': 105, 'Scam': 1795}; abstention {'abstained': 0, 'coverage': 1.0, 'model_accuracy_on_covered': 0.548}

## Test set `uci_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.124 | 0.1086 | 0.0003 | 0.500 |
| rules_only | 0.722 | 0.271 | 0.394 | 0.6246 | 0.294 | None | None | 0.120 |
| nb | 0.979 | 0.958 | 0.968 | 0.9926 | 0.9833 | 0.0083 | 0.0077 | 0.912 |
| logreg_noweight | 0.990 | 0.979 | 0.984 | 0.9983 | 0.9942 | 0.0049 | 0.0184 | 0.221 |
| logreg_uncal | 0.979 | 0.979 | 0.979 | 0.9984 | 0.9943 | 0.0043 | 0.0256 | 0.445 |
| logreg_cal | 0.990 | 0.979 | 0.984 | 0.9985 | 0.9945 | 0.0034 | 0.0105 | 0.430 |
| linsvc_cal | 0.979 | 0.979 | 0.979 | 0.9988 | 0.9951 | 0.0032 | 0.0099 | 0.403 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.864 R=0.990 F1=0.922; flag=Scam P=0.979 R=0.979 F1=0.979; verdicts {'Safe': 664, 'Suspicious': 14, 'Scam': 96}; abstention {'abstained': 0, 'coverage': 1.0, 'model_accuracy_on_covered': 0.9961}

## Test set `all_scam_spam_short`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.4281 | 0.3371 | 0.3037 | 0.500 |
| rules_only | 0.257 | 0.040 | 0.070 | 0.4756 | 0.4201 | None | None | 0.120 |
| nb | 0.280 | 0.190 | 0.227 | 0.4139 | 0.3569 | 0.5064 | 0.49 | 0.912 |
| logreg_noweight | 0.292 | 0.275 | 0.283 | 0.3943 | 0.3487 | 0.4305 | 0.4347 | 0.221 |
| logreg_uncal | 0.294 | 0.280 | 0.287 | 0.3937 | 0.3475 | 0.4508 | 0.4368 | 0.445 |
| logreg_cal | 0.288 | 0.277 | 0.283 | 0.3855 | 0.3431 | 0.5029 | 0.4923 | 0.430 |
| linsvc_cal | 0.312 | 0.309 | 0.311 | 0.3999 | 0.3499 | 0.489 | 0.4754 | 0.403 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.389 R=0.551 F1=0.456; flag=Scam P=0.295 R=0.290 F1=0.292; verdicts {'Safe': 3297, 'Suspicious': 1565, 'Scam': 3527}; abstention {'abstained': 0, 'coverage': 1.0, 'model_accuracy_on_covered': 0.3974}

## Operating points (chosen on val)

```
{
  "model_threshold": 0.4304,
  "suspicious_score": 11,
  "scam_score": 38,
  "uncertain_band": {
    "low": 0.4304,
    "high": 0.4304
  }
}
```

