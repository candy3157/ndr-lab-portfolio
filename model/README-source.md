# ndr-ml

NDR solution ML pipeline with an XGBoost operating-candidate model and a GRU sequence challenger model.

This repository keeps public dataset experiments, simulation experiments, real-only evaluation, and synthetic-augmented evaluation separated. Public CSE-CIC-IDS2018, UQ-IoT-IDS2021, and CTU-13 results are cross-domain references only and must not be merged into simulation operating-performance claims.

## Current Smoke Pipeline

```bash
source .venv-wsl/bin/activate
python check_wsl_dependencies.py --output-json reports/wsl_dependency_report.json --output-md reports/wsl_dependency_report.md --zeek-mode docker
python profile_public_datasets.py --max-cse-rows 12000 --max-simulation-rows 12000
python diagnose_common_data_sufficiency.py --input data/processed/common_ndr_features_smoke.csv
python generate_synthetic_data.py --input data/processed/common_ndr_features_smoke.csv --output data/synthetic/common_synthetic_smoke.csv --combined-output data/synthetic/common_real_plus_synthetic_smoke.csv --report-json reports/synthetic_data_report.json --report-md reports/synthetic_data_report.md --config configs/synthetic_data_config.json --label-column label
python src/training/train_xgboost_product.py --input data/processed/common_ndr_features_smoke.csv
python src/training/train_gru.py --input data/processed/common_ndr_features_smoke.csv
python src/inference/xgboost_infer.py --input data/processed/common_ndr_features_smoke.csv --output data/predictions/xgboost_predictions.json
python src/inference/gru_infer.py --input data/processed/common_ndr_features_smoke.csv --output data/predictions/gru_predictions.json
python src/inference/ensemble_infer.py --xgboost-predictions data/predictions/xgboost_predictions.json --gru-predictions data/predictions/gru_predictions.json --output reports/inference_sample_output.json
python src/inference/policy_ensemble_infer.py --xgboost-predictions data/predictions/xgboost_predictions.json --gru-predictions data/predictions/gru_predictions.json --output reports/policy_ensemble_output.json
python build_final_model_report.py
```

## Main Outputs

- Dataset profile: `reports/dataset_profile.md`, `reports/dataset_profile.json`
- Common schema: `configs/feature_schema.json`, `configs/dataset_mapping.json`
- Data sufficiency: `reports/data_sufficiency_report.md`
- Synthetic data: `data/synthetic/common_synthetic_smoke.csv`
- XGBoost model: `models/xgboost_model.joblib`
- GRU model: `models/gru_model.pt`
- CTU-13 GRU smoke model: `models/gru_model_ctu13_smoke.pt`
- CTU-13 conversion: `reports/ctu13_conversion_report.md`
- CTU-13 full GRU pretraining: `models/gru_model_ctu13_full.pt`
- CTU-13 pretraining impact: `reports/ctu13_pretraining_impact_report.md`
- Gated GRU review policy: `reports/gated_gru_review_policy_report.md`
- Inference sample: `reports/inference_sample_output.json`
- Policy ensemble sample: `reports/policy_ensemble_output.json`
- Registry: `models/registry.json`
- Final comparison: `reports/final_model_comparison.md`

Current operating integration keeps XGBoost low-slow v2 as the primary decision model and uses GRU sequence disagreement as a review/triage signal. See `docs/ensemble_policy.md` before enabling automatic GRU promotion.

See `docs/` for dataset preparation, WSL setup, model usage, ensemble policy, and inference API details.
