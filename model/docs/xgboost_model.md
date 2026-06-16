# XGBoost Model

Role: operating-candidate tabular/window model.

## Train Real-Only Smoke Model

```bash
python src/training/train_xgboost_product.py \
  --input data/processed/common_ndr_features_smoke.csv
```

Outputs:

- `models/xgboost_model.joblib`
- `models/xgboost_preprocessor.joblib`
- `models/xgboost_feature_list.json`
- `reports/xgboost_metrics.json`
- `reports/xgboost_confusion_matrix.csv`
- `reports/xgboost_feature_importance.csv`

## Comparison Runs

```bash
python src/training/train_xgboost_product.py \
  --input data/synthetic/common_real_plus_synthetic_smoke.csv \
  --model-output models/xgboost_model_real_plus_synthetic.joblib \
  --preprocessor-output models/xgboost_preprocessor_real_plus_synthetic.joblib \
  --feature-list-output models/xgboost_feature_list_real_plus_synthetic.json \
  --metrics-output reports/xgboost_metrics_real_plus_synthetic.json \
  --confusion-matrix-output reports/xgboost_confusion_matrix_real_plus_synthetic.csv \
  --feature-importance-output reports/xgboost_feature_importance_real_plus_synthetic.csv
```

Synthetic-only is also supported with `data/synthetic/common_synthetic_smoke.csv`, but it is only a pipeline check.

## Threshold Tuning And Blocked Validation

For operating-candidate review, tune the threshold on validation data and verify it on blocked test splits:

```bash
python src/evaluation/evaluate_xgboost_threshold_blocked.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-list models/xgboost_feature_list_simulation_real_only_24h.json \
  --recall-floor 0.95
```

Outputs:

- `reports/xgboost_threshold_blocked_validation_simulation_real_only_24h.md`
- `reports/xgboost_threshold_sweep_simulation_real_only_24h.csv`
- `reports/xgboost_blocked_validation_predictions_simulation_real_only_24h.csv`
- `reports/xgboost_time_blocked_error_analysis_simulation_real_only_24h.md`

Current interpretation:

- Run-blocked validation benefits from a higher threshold around `0.95`, reducing false positives without losing recall in that split.
- Time-blocked validation still misses later `low-and-slow` attack windows. This is a temporal generalization issue, not a simple threshold issue.
- Do not deploy the XGBoost model until low-and-slow time-blocked misses are reduced or covered by an additional detector/GRU/ensemble rule.

## Low-And-Slow Feature V2

Rolling behavior features can be generated without raw IP inputs:

```bash
python augment_low_slow_features.py \
  --input data/processed/simulation_real_only_24h_common.csv
```

Outputs:

- `data/processed/simulation_real_only_24h_low_slow_features.csv`
- `configs/feature_schema_low_slow_v2.json`
- `models/xgboost_feature_list_low_slow_v2.json`
- `reports/low_slow_feature_augmentation_report.md`
- `reports/low_slow_feature_evaluation_report.md`

Current result:

- Standard holdout improves from F1 `0.8681` to `0.9994`.
- Under `scenario_time_blocked`, low-slow v2 reduces false negatives from `28` to `1` and false positives from `314` to `4`.
- Under global future `time_blocked`, the model still fails when `low-and-slow` is absent from train/validation and appears only in the future test block.

Operating implication: use low-slow v2 only with explicit low-and-slow training coverage, and keep a true future holdout to detect unseen attack-family gaps.
