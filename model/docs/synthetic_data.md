# Synthetic Data

Synthetic rows are used for training augmentation and pipeline validation. They are not proof of operating performance.

## Generate

```bash
python generate_synthetic_data.py \
  --input data/processed/common_ndr_features_smoke.csv \
  --output data/synthetic/common_synthetic_smoke.csv \
  --combined-output data/synthetic/common_real_plus_synthetic_smoke.csv \
  --report-json reports/synthetic_data_report.json \
  --report-md reports/synthetic_data_report.md \
  --config configs/synthetic_data_config.json \
  --label-column label
```

The generated rows include `data_source=synthetic` and `is_synthetic=true`. Real rows in the combined output include `data_source=real` and `is_synthetic=false`.

## Evaluation Rules

- Report real-only, real+synthetic, and synthetic-only results separately.
- Prefer real test data for final evaluation.
- If synthetic rows are evaluated, label the result as synthetic-test or synthetic-only.
- Do not claim that synthetic-driven gains guarantee real operating performance.
- Check for run/session/domain leakage before using synthetic rows for model selection.
