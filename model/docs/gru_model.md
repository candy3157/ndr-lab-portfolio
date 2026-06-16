# GRU Model

Role: sequence challenger model.

PyTorch was selected because the project already uses Python/scikit-learn/joblib and PyTorch provides a small, direct CPU training path for sequence models without changing the existing tabular pipeline.

## Train Real-Only Smoke Model

```bash
python src/training/train_gru.py \
  --input data/processed/common_ndr_features_smoke.csv \
  --config configs/gru_config.yaml
```

Outputs:

- `models/gru_model.pt`
- `models/gru_scaler.joblib`
- `models/gru_feature_list.json`
- `reports/gru_metrics.json`
- `reports/gru_confusion_matrix.csv`
- `reports/gru_training_history.csv`

## Configuration

`configs/gru_config.yaml` controls:

- `sequence_length`
- `stride`
- `batch_size`
- `hidden_size`
- `num_layers`
- `dropout`
- `learning_rate`
- `epochs`
- `early_stopping_patience`

The model is binary normal/attack in this version. Multiclass `attack_type` can be added by replacing the final linear head and label encoder.

## CTU-13 Sequence Benchmark

CTU-13 can be converted into the same common schema for GRU sequence challenger benchmark/pretraining. It is not an IPCAM operating-performance dataset.

```bash
python convert_ctu13_to_common.py \
  --max-rows-per-file 200000 \
  --output data/processed/ctu13_common_10s_smoke.csv

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

The smoke output currently uses 10 second windows and excludes CTU background flows. Raw `SrcAddr` and `DstAddr` are used only for grouping/sessionization and unique-count aggregation.

Full CTU pretraining can be run with `data/processed/ctu13_common_10s_full.csv` and stored as:

- `models/gru_model_ctu13_full.pt`
- `reports/gru_metrics_ctu13_full.json`
- `reports/gru_blocked_validation_ctu13_full.md`

The CTU-pretrained model can initialize simulation fine-tuning:

```bash
python src/training/train_gru.py \
  --input data/processed/simulation_real_only_24h_common.csv \
  --feature-schema configs/feature_schema.json \
  --pretrained-model models/gru_model_ctu13_full.pt \
  --model-output models/gru_model_ctu13_full_to_simulation_finetuned.pt \
  --scaler-output models/gru_scaler_ctu13_full_to_simulation_finetuned.joblib \
  --feature-list-output models/gru_feature_list_ctu13_full_to_simulation_finetuned.json \
  --metrics-output reports/gru_metrics_ctu13_full_to_simulation_finetuned.json
```

Current impact report: `reports/ctu13_pretraining_impact_report.md`. CTU pretraining improves global time-blocked low-and-slow recall at threshold `0.50`, but it is not enabled as the default GRU policy because it creates many non-low-and-slow review signals.

## Caution

GRU is not promoted to operating candidate yet. It needs more real sequence data, full group/time blocked validation, and sequence length comparison.
