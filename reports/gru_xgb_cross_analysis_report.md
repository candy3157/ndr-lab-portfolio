# GRU vs XGBoost Cross Analysis

- Aligned rows: `15668`
- Test rows by strategy: `{'run_blocked': 2778, 'scenario_time_blocked': 2537, 'time_blocked': 2496}`

## Tail-Window Metrics
| Strategy | Model/Policy | Precision | Recall | F1 | FN | FP |
|---|---|---:|---:|---:|---:|---:|
| run_blocked | xgb_v1 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| run_blocked | xgb_v2 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| run_blocked | gru | 0.5436 | 1.0000 | 0.7043 | 0 | 529 |
| run_blocked | or_xgb_v2_gru | 0.5436 | 1.0000 | 0.7043 | 0 | 529 |
| run_blocked | weighted_xgb_v2_gru_0_50 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| scenario_time_blocked | xgb_v1 | 0.6611 | 0.9615 | 0.7835 | 24 | 307 |
| scenario_time_blocked | xgb_v2 | 0.9984 | 1.0000 | 0.9992 | 0 | 1 |
| scenario_time_blocked | gru | 0.5988 | 0.9968 | 0.7482 | 2 | 416 |
| scenario_time_blocked | or_xgb_v2_gru | 0.5990 | 1.0000 | 0.7492 | 0 | 417 |
| scenario_time_blocked | weighted_xgb_v2_gru_0_50 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| time_blocked | xgb_v1 | 1.0000 | 0.4939 | 0.6612 | 457 | 0 |
| time_blocked | xgb_v2 | 1.0000 | 0.4939 | 0.6612 | 457 | 0 |
| time_blocked | gru | 0.6558 | 0.7154 | 0.6843 | 257 | 339 |
| time_blocked | or_xgb_v2_gru | 0.6634 | 0.7398 | 0.6995 | 235 | 339 |
| time_blocked | weighted_xgb_v2_gru_0_50 | 1.0000 | 0.4939 | 0.6612 | 457 | 0 |

## XGBoost v2 False Negatives Caught By GRU
- run_blocked: GRU caught `0` / `0` XGBoost v2 FNs; by scenario `{}`
- scenario_time_blocked: GRU caught `0` / `0` XGBoost v2 FNs; by scenario `{}`
- time_blocked: GRU caught `222` / `457` XGBoost v2 FNs; by scenario `{'low-and-slow': 457}`

## Ensemble Value Judgement
- run_blocked: Ensemble is not justified for run_blocked without additional tuning.
- scenario_time_blocked: Ensemble is not justified for scenario_time_blocked without additional tuning.
- time_blocked: GRU catches 222/457 XGBoost v2 false negatives but adds 339 false positives; use with policy constraints.

## Notes
- Aligned comparison uses GRU sequence predictions at the final window original_index.
- Tail-label metrics compare all models against the final window label, matching XGBoost row-level output.
- Sequence-label metrics are not used for XGBoost operating judgement because XGBoost is not a sequence model.
