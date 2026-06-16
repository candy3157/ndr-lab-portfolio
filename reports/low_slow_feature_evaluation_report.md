# Low-And-Slow Feature Evaluation

- Augmented data: `data/processed/simulation_real_only_24h_low_slow_features.csv`
- Feature count: `90`
- Added rolling features: `68`
- Rolling windows: `[6, 12, 30, 60]`

## Holdout Metrics
| Version | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 0.9321 | 0.7670 | 1.0000 | 0.8681 | 1.0000 | 1.0000 |
| low_slow_v2 | 0.9997 | 0.9988 | 1.0000 | 0.9994 | 1.0000 | 1.0000 |

## Scenario-Time-Blocked Validation
| Version | Threshold | Precision | Recall | F1 | FN | FP |
|---|---:|---:|---:|---:|---:|---:|
| low_slow_v2 | 0.35 | 0.9940 | 0.9985 | 0.9962 | 1 | 4 |
| v1 | 0.32 | 0.6677 | 0.9575 | 0.7868 | 28 | 314 |

## Conclusion
With low-and-slow present in train/validation and rolling features enabled, low_slow_v2 reduces scenario-time-blocked false negatives from 28 to 1 and false positives from 314 to 4. The remaining global time-blocked failure is caused by zero low-and-slow coverage before the future test block.

## Caution
A global future time block can still fail if an attack family has zero train/validation coverage. For operating validation, collect low-and-slow before the test horizon or use scenario-aware future-run validation plus a true future holdout.
