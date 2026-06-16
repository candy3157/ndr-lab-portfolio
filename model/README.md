# NDR Model Code

This folder contains the final model-side code kept for portfolio and future
maintenance.

## Key Components

- `scripts/convert_zeek_conn_to_common.py`: converts Zeek `conn.log` output to
  the common NDR feature input format.
- `scripts/augment_low_slow_features.py`: adds rolling low-and-slow scan
  features over 10-second windows.
- `src/training/train_xgboost_product.py`: trains the XGBoost detector.
- `src/training/train_gru.py`: trains the GRU sequence detector.
- `src/inference/xgboost_infer.py`: runs XGBoost inference.
- `src/inference/gru_infer.py`: runs GRU sequence inference.
- `src/inference/ensemble_infer.py`: combines XGBoost and GRU predictions.
- `src/inference/policy_ensemble_infer.py`: applies the operational ensemble
  policy.
- `scripts/export_ndr_model_bundle.py`: exports a runtime bundle for the VM lab.
- `scripts/validate_model_bundle.py`: validates exported model artifacts.

## Artifacts

Trained `.pt` and `.joblib` files are intentionally not committed to this public
repository. See `artifacts/README.md`.

## Reports

Selected model evaluation summaries are kept at the repository root under
`reports/`.
