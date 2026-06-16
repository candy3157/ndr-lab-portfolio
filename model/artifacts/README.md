# Model Artifacts

This directory is intentionally empty in the public repository.

The runtime pipeline expects these trained files when running a full demo:

```text
xgboost_model_combined_10_common_split.joblib
xgboost_preprocessor_combined_10_common_split.joblib
gru_model_combined_10_common_split.pt
gru_scaler_combined_10_common_split.joblib
combined_10_feature_list_common_split.json
xgboost_gru_ensemble_combined_10.json
```

Keep large or sensitive artifacts outside the normal Git history. Recommended
options are GitHub Releases, Git LFS, or a private artifact store.
