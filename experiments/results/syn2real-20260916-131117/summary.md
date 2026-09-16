# syn2real

Track A - train and tune on SYNTHETIC data only, test on held-out synthetic templates and on REAL data (cross-domain).

Sizes: {'train': 5463, 'val': 1214, 'synthetic_test': 1947, 'uci_test': 774, 'all_scam_spam_short': 8389, 'n_features': 18235}

Threshold for each model chosen on the validation split; test metrics at that threshold.

## Test set `synthetic_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.643 | 1.000 | 0.783 | 0.5 | 0.643 | 0.2307 | 0.034 | 0.500 |
| rules_only | 0.992 | 0.772 | 0.868 | 0.8814 | 0.9182 | None | None | 0.100 |
| nb | 0.993 | 0.994 | 0.994 | 0.9989 | 0.9993 | 0.007 | 0.0092 | 0.882 |
| logreg_noweight | 0.946 | 0.997 | 0.971 | 0.9984 | 0.9991 | 0.0334 | 0.0924 | 0.445 |
| logreg_uncal | 0.951 | 0.997 | 0.973 | 0.9986 | 0.9992 | 0.0316 | 0.0963 | 0.396 |
| logreg_cal | 0.989 | 0.990 | 0.990 | 0.9979 | 0.9989 | 0.0234 | 0.0578 | 0.327 |
| linsvc_cal | 0.956 | 0.961 | 0.959 | 0.9907 | 0.9954 | 0.0322 | 0.0418 | 0.318 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.994 R=0.971 F1=0.983; flag=Scam P=0.994 R=0.971 F1=0.983; verdicts {'Safe': 724, 'Suspicious': 0, 'Scam': 1223}; abstention {'abstained': 254, 'coverage': 0.8695, 'model_accuracy_on_covered': 0.9923}

## Test set `uci_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.124 | 1.000 | 0.221 | 0.5 | 0.124 | 0.3438 | 0.485 | 0.500 |
| rules_only | 0.722 | 0.271 | 0.394 | 0.6246 | 0.294 | None | None | 0.100 |
| nb | 0.179 | 0.708 | 0.286 | 0.6744 | 0.3504 | 0.4721 | 0.4964 | 0.882 |
| logreg_noweight | 0.139 | 0.823 | 0.238 | 0.6292 | 0.2418 | 0.378 | 0.4827 | 0.445 |
| logreg_uncal | 0.142 | 0.833 | 0.242 | 0.6287 | 0.2423 | 0.3442 | 0.4435 | 0.396 |
| logreg_cal | 0.148 | 0.771 | 0.249 | 0.6195 | 0.2257 | 0.321 | 0.3772 | 0.327 |
| linsvc_cal | 0.159 | 0.792 | 0.265 | 0.6514 | 0.2483 | 0.305 | 0.3615 | 0.318 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.170 R=0.646 F1=0.269; flag=Scam P=0.169 R=0.635 F1=0.266; verdicts {'Safe': 409, 'Suspicious': 3, 'Scam': 362}; abstention {'abstained': 278, 'coverage': 0.6408, 'model_accuracy_on_covered': 0.379}

## Test set `all_scam_spam_short`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.428 | 1.000 | 0.600 | 0.5 | 0.4281 | 0.2776 | 0.1809 | 0.500 |
| rules_only | 0.256 | 0.040 | 0.070 | 0.4756 | 0.4201 | None | None | 0.100 |
| nb | 0.467 | 0.670 | 0.550 | 0.5792 | 0.5126 | 0.4382 | 0.4211 | 0.882 |
| logreg_noweight | 0.479 | 0.836 | 0.609 | 0.6586 | 0.5781 | 0.2644 | 0.1757 | 0.445 |
| logreg_uncal | 0.477 | 0.837 | 0.608 | 0.649 | 0.5711 | 0.2589 | 0.1553 | 0.396 |
| logreg_cal | 0.517 | 0.696 | 0.593 | 0.6545 | 0.574 | 0.2622 | 0.1582 | 0.327 |
| linsvc_cal | 0.512 | 0.684 | 0.586 | 0.6397 | 0.5638 | 0.268 | 0.1795 | 0.318 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.549 R=0.551 F1=0.550; flag=Scam P=0.552 R=0.543 F1=0.548; verdicts {'Safe': 4787, 'Suspicious': 72, 'Scam': 3530}; abstention {'abstained': 3492, 'coverage': 0.5837, 'model_accuracy_on_covered': 0.6136}

## Operating points (chosen on val)

```
{
  "model_threshold": 0.327,
  "suspicious_score": 45,
  "scam_score": 46,
  "uncertain_band": {
    "low": 0.127,
    "high": 0.527
  }
}
```

## Category head (synthetic labels only)

- `synthetic_test`: accuracy 0.7227, macro-F1 0.6507 (n=1947)
