# ablation_random_calib_folds

Ablation of Track C: identical except calibration uses random (not template-grouped) 3-fold CV.

Sizes: {'train': 9074, 'val': 1988, 'synthetic_test': 1947, 'uci_test': 774, 'all_scam_spam_short': 8389, 'n_features': 32000}

Threshold for each model chosen on the validation split; test metrics at that threshold.

## Test set `synthetic_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| logreg_uncal | 0.951 | 0.967 | 0.959 | 0.9915 | 0.9954 | 0.0424 | 0.0777 | 0.511 |
| logreg_cal | 0.929 | 0.990 | 0.959 | 0.9365 | 0.9358 | 0.0866 | 0.1774 | 0.646 |
| linsvc_cal | 0.939 | 0.953 | 0.946 | 0.9564 | 0.9644 | 0.0975 | 0.1772 | 0.760 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.944 R=0.998 F1=0.970; flag=Scam P=0.952 R=0.826 F1=0.884; verdicts {'Safe': 624, 'Suspicious': 237, 'Scam': 1086}; abstention {'abstained': 506, 'coverage': 0.7401, 'model_accuracy_on_covered': 0.9882}

## Test set `uci_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| logreg_uncal | 1.000 | 0.948 | 0.973 | 0.9945 | 0.9909 | 0.0065 | 0.0246 | 0.511 |
| logreg_cal | 0.988 | 0.823 | 0.898 | 0.991 | 0.9804 | 0.0336 | 0.1478 | 0.646 |
| linsvc_cal | 1.000 | 0.594 | 0.745 | 0.9923 | 0.9875 | 0.0364 | 0.1665 | 0.760 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.973 R=0.740 F1=0.840; flag=Scam P=1.000 R=0.427 F1=0.599; verdicts {'Safe': 701, 'Suspicious': 32, 'Scam': 41}; abstention {'abstained': 77, 'coverage': 0.9005, 'model_accuracy_on_covered': 0.9971}

## Test set `all_scam_spam_short`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| logreg_uncal | 0.335 | 0.165 | 0.221 | 0.4661 | 0.397 | 0.3502 | 0.2963 | 0.511 |
| logreg_cal | 0.349 | 0.263 | 0.300 | 0.45 | 0.3849 | 0.3281 | 0.2658 | 0.646 |
| linsvc_cal | 0.369 | 0.133 | 0.195 | 0.4568 | 0.3948 | 0.3236 | 0.2602 | 0.760 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.323 R=0.206 F1=0.252; flag=Scam P=0.231 R=0.023 F1=0.042; verdicts {'Safe': 6100, 'Suspicious': 1929, 'Scam': 360}; abstention {'abstained': 4376, 'coverage': 0.4784, 'model_accuracy_on_covered': 0.5046}

## Operating points (chosen on val)

```
{
  "model_threshold": 0.6456,
  "suspicious_score": 64,
  "scam_score": 73,
  "uncertain_band": {
    "low": 0.3456,
    "high": 0.9456
  }
}
```

## Category head (synthetic labels only)

- `synthetic_test`: accuracy 0.7232, macro-F1 0.6551 (n=1947)
