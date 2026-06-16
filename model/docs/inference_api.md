# Inference API

All model outputs use the same fields:

- `model_name`
- `model_version`
- `feature_schema_version`
- `input_window_start`
- `input_window_end`
- `predicted_label`
- `attack_probability`
- `risk_score`
- `confidence`
- `threshold`
- `data_source`
- `dataset_name`
- `inference_time_ms`

## XGBoost

```bash
python src/inference/xgboost_infer.py \
  --input data/processed/common_ndr_features_smoke.csv \
  --output data/predictions/xgboost_predictions.json
```

## GRU

```bash
python src/inference/gru_infer.py \
  --input data/processed/common_ndr_features_smoke.csv \
  --output data/predictions/gru_predictions.json
```

## Ensemble

```bash
python src/inference/ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions.json \
  --gru-predictions data/predictions/gru_predictions.json \
  --xgboost-weight 0.7 \
  --gru-weight 0.3 \
  --output reports/inference_sample_output.json
```

The weighted-average ensemble is for integration testing only. It is not the current operating default.

## Policy Ensemble

The current operating integration policy is XGBoost primary plus gated GRU shadow/challenger triage. XGBoost decides `predicted_label`; GRU disagreement sets `review_required=true` only when the low-slow feature gate passes.

```bash
python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_low_slow_v2_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_ctu13_finetuned_simulation_real_only_24h.json \
  --policy-config configs/ensemble_policy_low_slow_v2.json \
  --feature-input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --gate-config configs/gru_review_gate_low_slow_v1.json \
  --output reports/policy_ensemble_output_gated_ctu13_finetuned_simulation_real_only_24h.json
```

Policy output adds:

- `policy_name`
- `decision_mode`
- `decision_source`
- `review_required`
- `review_reason`
- `gate_required`
- `gate_name`
- `gate_passed`
- `gate_reason`
- `gate_failed_features`
- `raw_gru_xgboost_disagreement`
- `xgboost_attack_probability`
- `gru_attack_probability`
- `weighted_attack_probability`
- `triage_risk_score`

Naive OR promotion is disabled by default. `--promote-disagreement` is available for experiments only and still requires the gate to pass.

## Simulation Real-Only 24h Sample

```bash
python src/inference/xgboost_infer.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --model models/xgboost_model_simulation_real_only_24h.joblib \
  --preprocessor models/xgboost_preprocessor_simulation_real_only_24h.joblib \
  --features models/xgboost_feature_list_simulation_real_only_24h.json \
  --output data/predictions/xgboost_predictions_simulation_real_only_24h.json

python src/inference/gru_infer.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --model models/gru_model_simulation_real_only_24h.pt \
  --scaler models/gru_scaler_simulation_real_only_24h.joblib \
  --output data/predictions/gru_predictions_simulation_real_only_24h.json

python src/inference/ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_simulation_real_only_24h.json \
  --output reports/inference_sample_output_simulation_real_only_24h.json

python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_low_slow_v2_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_ctu13_finetuned_simulation_real_only_24h.json \
  --feature-input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --gate-config configs/gru_review_gate_low_slow_v1.json \
  --output reports/policy_ensemble_output_gated_ctu13_finetuned_simulation_real_only_24h.json
```
