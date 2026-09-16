# combined

Track C - production recipe: train on synthetic + UCI train, tune on synthetic + UCI val, test on each source separately.

Sizes: {'train': 9074, 'val': 1988, 'synthetic_test': 1947, 'uci_test': 774, 'all_scam_spam_short': 8389, 'n_features': 32000}

Threshold for each model chosen on the validation split; test metrics at that threshold.

## Test set `synthetic_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.643 | 0.281 | 0.2269 | 0.500 |
| rules_only | 0.992 | 0.772 | 0.868 | 0.8814 | 0.9182 | None | None | 0.100 |
| nb | 0.933 | 0.964 | 0.948 | 0.9876 | 0.9939 | 0.04 | 0.0406 | 0.049 |
| logreg_noweight | 0.943 | 0.968 | 0.955 | 0.9866 | 0.9926 | 0.0485 | 0.0796 | 0.444 |
| logreg_uncal | 0.951 | 0.967 | 0.959 | 0.9915 | 0.9954 | 0.0424 | 0.0777 | 0.511 |
| logreg_cal | 0.942 | 0.980 | 0.961 | 0.9873 | 0.9932 | 0.0461 | 0.0754 | 0.496 |
| linsvc_cal | 0.942 | 0.982 | 0.962 | 0.9863 | 0.9927 | 0.0493 | 0.0872 | 0.479 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.967 R=0.948 F1=0.957; flag=Scam P=0.996 R=0.888 F1=0.939; verdicts {'Safe': 719, 'Suspicious': 112, 'Scam': 1116}; abstention {'abstained': 324, 'coverage': 0.8336, 'model_accuracy_on_covered': 0.9834}

## Test set `uci_test`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.124 | 0.194 | 0.2921 | 0.500 |
| rules_only | 0.722 | 0.271 | 0.394 | 0.6246 | 0.294 | None | None | 0.100 |
| nb | 0.956 | 0.896 | 0.925 | 0.9793 | 0.953 | 0.0234 | 0.0256 | 0.049 |
| logreg_noweight | 1.000 | 0.948 | 0.973 | 0.9942 | 0.991 | 0.0061 | 0.0212 | 0.444 |
| logreg_uncal | 1.000 | 0.948 | 0.973 | 0.9945 | 0.9909 | 0.0065 | 0.0246 | 0.511 |
| logreg_cal | 1.000 | 0.948 | 0.973 | 0.9941 | 0.9906 | 0.0053 | 0.0113 | 0.496 |
| linsvc_cal | 1.000 | 0.969 | 0.984 | 0.9963 | 0.9922 | 0.0038 | 0.0107 | 0.479 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.989 R=0.948 F1=0.968; flag=Scam P=1.000 R=0.917 F1=0.957; verdicts {'Safe': 682, 'Suspicious': 4, 'Scam': 88}; abstention {'abstained': 6, 'coverage': 0.9922, 'model_accuracy_on_covered': 0.9974}

## Test set `all_scam_spam_short`

| model | P | R | F1 | ROC-AUC | PR-AUC | Brier | ECE | thr |
|---|---|---|---|---|---|---|---|---|
| majority | 0.000 | 0.000 | 0.000 | 0.5 | 0.4281 | 0.245 | 0.0119 | 0.500 |
| rules_only | 0.256 | 0.040 | 0.070 | 0.4756 | 0.4201 | None | None | 0.100 |
| nb | 0.330 | 0.191 | 0.242 | 0.434 | 0.3945 | 0.4203 | 0.4156 | 0.049 |
| logreg_noweight | 0.331 | 0.185 | 0.237 | 0.4535 | 0.3854 | 0.3638 | 0.3181 | 0.444 |
| logreg_uncal | 0.335 | 0.165 | 0.221 | 0.4661 | 0.397 | 0.3502 | 0.2963 | 0.511 |
| logreg_cal | 0.321 | 0.166 | 0.219 | 0.4456 | 0.3813 | 0.3893 | 0.3492 | 0.496 |
| linsvc_cal | 0.324 | 0.185 | 0.235 | 0.4497 | 0.3851 | 0.3888 | 0.3496 | 0.479 |

Full system (logreg_cal + rules): flag≥Suspicious P=0.257 R=0.096 F1=0.139; flag=Scam P=0.193 R=0.053 F1=0.083; verdicts {'Safe': 7053, 'Suspicious': 344, 'Scam': 992}; abstention {'abstained': 2608, 'coverage': 0.6891, 'model_accuracy_on_covered': 0.4617}

## Operating points (chosen on val)

```
{
  "model_threshold": 0.4957,
  "suspicious_score": 60,
  "scam_score": 71,
  "uncertain_band": {
    "low": 0.1957,
    "high": 0.7957
  }
}
```

## Category head (synthetic labels only)

- `synthetic_test`: accuracy 0.7232, macro-F1 0.6551 (n=1947)
