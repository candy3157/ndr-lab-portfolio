# Model Usage

## Smoke Workflow

```bash
python profile_public_datasets.py --max-cse-rows 12000 --max-simulation-rows 12000
python diagnose_common_data_sufficiency.py --input data/processed/common_ndr_features_smoke.csv
python src/training/train_xgboost_product.py --input data/processed/common_ndr_features_smoke.csv
python src/training/train_gru.py --input data/processed/common_ndr_features_smoke.csv
python build_final_model_report.py
```

## Full Training Commands

Use larger `--max-cse-rows` or add a full chunk conversion mode after confirming disk and runtime budget. UQ PCAP must be extracted to Zeek/tshark features before model training.

Simulation-only real training should use the latest 24h collection CSV:

```bash
python profile_public_datasets.py \
  --max-cse-rows 0 \
  --max-simulation-rows 1000000 \
  --simulation-input ../ipcam-backdoor-test-environment/data/features/datasets/seq10s-24h-scan-subtype-10s.csv
```

Then train:

```bash
python src/training/train_xgboost_product.py --input data/processed/common_ndr_features_smoke.csv
python src/training/train_gru.py --input data/processed/common_ndr_features_smoke.csv
```

## Simulation Real-Only 24h Validation

The current 24h simulation CSV can be converted and evaluated without public datasets:

```bash
python profile_public_datasets.py \
  --max-cse-rows 0 \
  --max-simulation-rows 1000000 \
  --simulation-input ../ipcam-backdoor-test-environment/data/features/datasets/seq10s-24h-scan-subtype-10s.csv \
  --output-json reports/dataset_profile_simulation_real_only_24h.json \
  --output-md reports/dataset_profile_simulation_real_only_24h.md \
  --processed-output data/processed/simulation_real_only_24h_common.csv

python diagnose_common_data_sufficiency.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --output-json reports/data_sufficiency_simulation_real_only_24h.json \
  --output-md reports/data_sufficiency_simulation_real_only_24h.md
```

Model outputs:

- `reports/xgboost_metrics_simulation_real_only_24h.json`
- `reports/gru_metrics_simulation_real_only_24h.json`
- `reports/inference_sample_output_simulation_real_only_24h.json`

Threshold and blocked validation:

```bash
python src/evaluation/evaluate_xgboost_threshold_blocked.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-list models/xgboost_feature_list_simulation_real_only_24h.json \
  --recall-floor 0.95
```

Use `reports/xgboost_threshold_blocked_validation_simulation_real_only_24h.md` before choosing an operating threshold.

Low-and-slow feature v2:

```bash
python augment_low_slow_features.py --input data/processed/simulation_real_only_24h_common.csv
python src/evaluation/evaluate_xgboost_threshold_blocked.py \
  --input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --feature-list models/xgboost_feature_list_low_slow_v2.json \
  --output-json reports/xgboost_threshold_blocked_validation_low_slow_v2.json \
  --output-md reports/xgboost_threshold_blocked_validation_low_slow_v2.md \
  --sweep-output reports/xgboost_threshold_sweep_low_slow_v2.csv \
  --predictions-output reports/xgboost_blocked_validation_predictions_low_slow_v2.csv \
  --model-output-dir models/blocked_validation_low_slow_v2
```

Read `reports/low_slow_training_coverage_report.md` to distinguish normal global future time blocking from scenario-aware future-run validation.

GRU/XGBoost cross-analysis and policy output:

```bash
python src/evaluation/evaluate_gru_blocked.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-schema configs/feature_schema.json \
  --recall-floor 0.95

python src/evaluation/analyze_gru_xgb_ensemble.py

python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_simulation_real_only_24h.json \
  --output reports/policy_ensemble_output_simulation_real_only_24h.json
```

Use `reports/gru_xgb_cross_analysis_report.md` and `docs/ensemble_policy.md` before enabling any automatic GRU promotion. Current policy keeps XGBoost as the primary decision model and uses GRU disagreement as a review signal.

## CTU-13 GRU Benchmark

Use CTU-13 as a cross-domain botnet/C2 sequence benchmark or pretraining source for the GRU challenger. Do not merge these metrics into simulation operating-performance claims.

```bash
python convert_ctu13_to_common.py \
  --max-rows-per-file 200000 \
  --output data/processed/ctu13_common_10s_smoke.csv \
  --report-json reports/ctu13_conversion_report.json \
  --report-md reports/ctu13_conversion_report.md

python diagnose_common_data_sufficiency.py \
  --input data/processed/ctu13_common_10s_smoke.csv \
  --output-json reports/data_sufficiency_ctu13_smoke.json \
  --output-md reports/data_sufficiency_ctu13_smoke.md

python src/training/train_gru.py \
  --input data/processed/ctu13_common_10s_smoke.csv \
  --feature-schema configs/feature_schema.json \
  --model-output models/gru_model_ctu13_smoke.pt \
  --scaler-output models/gru_scaler_ctu13_smoke.joblib \
  --feature-list-output models/gru_feature_list_ctu13_smoke.json \
  --metrics-output reports/gru_metrics_ctu13_smoke.json \
  --confusion-matrix-output reports/gru_confusion_matrix_ctu13_smoke.csv \
  --history-output reports/gru_training_history_ctu13_smoke.csv

python src/evaluation/evaluate_gru_blocked.py \
  --input data/processed/ctu13_common_10s_smoke.csv \
  --feature-schema configs/feature_schema.json \
  --output-json reports/gru_blocked_validation_ctu13_smoke.json \
  --output-md reports/gru_blocked_validation_ctu13_smoke.md \
  --sweep-output reports/gru_threshold_sweep_ctu13_smoke.csv \
  --predictions-output reports/gru_blocked_validation_predictions_ctu13_smoke.csv \
  --model-output-dir models/gru_blocked_validation_ctu13_smoke \
  --recall-floor 0.95
```

Full CTU conversion, if needed:

```bash
python convert_ctu13_to_common.py \
  --max-rows-per-file 0 \
  --output data/processed/ctu13_common_10s_full.csv \
  --report-json reports/ctu13_conversion_full_report.json \
  --report-md reports/ctu13_conversion_full_report.md
```

CTU full pretraining and simulation fine-tuning comparison:

```bash
python diagnose_common_data_sufficiency.py \
  --input data/processed/ctu13_common_10s_full.csv \
  --output-json reports/data_sufficiency_ctu13_full.json \
  --output-md reports/data_sufficiency_ctu13_full.md

python src/training/train_gru.py \
  --input data/processed/ctu13_common_10s_full.csv \
  --feature-schema configs/feature_schema.json \
  --model-output models/gru_model_ctu13_full.pt \
  --scaler-output models/gru_scaler_ctu13_full.joblib \
  --feature-list-output models/gru_feature_list_ctu13_full.json \
  --metrics-output reports/gru_metrics_ctu13_full.json \
  --confusion-matrix-output reports/gru_confusion_matrix_ctu13_full.csv \
  --history-output reports/gru_training_history_ctu13_full.csv

python src/evaluation/evaluate_gru_blocked.py \
  --input data/processed/ctu13_common_10s_full.csv \
  --feature-schema configs/feature_schema.json \
  --output-json reports/gru_blocked_validation_ctu13_full.json \
  --output-md reports/gru_blocked_validation_ctu13_full.md \
  --sweep-output reports/gru_threshold_sweep_ctu13_full.csv \
  --predictions-output reports/gru_blocked_validation_predictions_ctu13_full.csv \
  --model-output-dir models/gru_blocked_validation_ctu13_full \
  --recall-floor 0.95

python src/training/train_gru.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-schema configs/feature_schema.json \
  --pretrained-model models/gru_model_ctu13_full.pt \
  --model-output models/gru_model_ctu13_full_to_simulation_finetuned.pt \
  --scaler-output models/gru_scaler_ctu13_full_to_simulation_finetuned.joblib \
  --feature-list-output models/gru_feature_list_ctu13_full_to_simulation_finetuned.json \
  --metrics-output reports/gru_metrics_ctu13_full_to_simulation_finetuned.json \
  --confusion-matrix-output reports/gru_confusion_matrix_ctu13_full_to_simulation_finetuned.csv \
  --history-output reports/gru_training_history_ctu13_full_to_simulation_finetuned.csv

python src/evaluation/analyze_ctu13_pretraining_impact.py

python src/evaluation/analyze_gated_gru_review_policy.py

python src/inference/xgboost_infer.py \
  --input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --model models/xgboost_model_low_slow_v2.joblib \
  --preprocessor models/xgboost_preprocessor_low_slow_v2.joblib \
  --features models/xgboost_feature_list_low_slow_v2.json \
  --output data/predictions/xgboost_predictions_low_slow_v2_simulation_real_only_24h.json \
  --limit 500

python src/inference/gru_infer.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-schema configs/feature_schema.json \
  --model models/gru_model_ctu13_full_to_simulation_finetuned.pt \
  --scaler models/gru_scaler_ctu13_full_to_simulation_finetuned.joblib \
  --output data/predictions/gru_predictions_ctu13_finetuned_simulation_real_only_24h.json \
  --limit 500

python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_low_slow_v2_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_ctu13_finetuned_simulation_real_only_24h.json \
  --feature-input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --gate-config configs/gru_review_gate_low_slow_v1.json \
  --output reports/policy_ensemble_output_gated_ctu13_finetuned_simulation_real_only_24h.json
```

Current result: CTU pretraining improves time-blocked low-and-slow recall at threshold `0.50`. `low_slow_volume_gate_v1` keeps the 450 true low-and-slow review signals and removes the 343 scan-burst normal review signals in current validation. Keep the output as review/triage until the gate is validated on more real captures.

## Registry

Model metadata is stored in `models/registry.json`. NDR software should use this file to locate model, preprocessor/scaler, feature list, metrics, and limitations.
