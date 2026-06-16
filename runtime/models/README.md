# Runtime Model Artifacts

Place trained runtime artifacts here before running the VM lab pipeline.

Required files:

```text
xgboost_model_combined_10_common_split.joblib
xgboost_preprocessor_combined_10_common_split.joblib
gru_model_combined_10_common_split.pt
gru_scaler_combined_10_common_split.joblib
combined_10_feature_list_common_split.json
xgboost_gru_ensemble_combined_10.json
```

These files are excluded from Git by the repository `.gitignore`.
