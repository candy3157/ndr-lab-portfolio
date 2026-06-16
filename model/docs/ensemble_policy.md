# Ensemble Policy

## Current Decision

Use `xgboost_low_slow_v2` as the primary operating-candidate model. Keep CTU-pretrained GRU as a gated sequence challenger that emits review/triage signals only when it disagrees with XGBoost and the low-slow feature gate passes.

Do not use naive OR promotion as the default operating decision. In the current aligned blocked validation, OR promotion helps global `time_blocked` recall but damages precision on the better-covered splits.

## Evidence

Report:

```bash
python src/evaluation/analyze_gru_xgb_ensemble.py
```

Outputs:

- `reports/gru_xgb_cross_analysis_report.md`
- `reports/gru_xgb_cross_analysis_report.json`
- `reports/gru_xgb_aligned_predictions.csv`

Key result:

- `run_blocked`: OR with GRU is not justified; it adds 529 false positives with no recall gain.
- `scenario_time_blocked`: OR with GRU is not justified; XGBoost low-slow v2 already has no aligned false negatives and OR adds 416 false positives.
- `time_blocked`: CTU-pretrained GRU catches most XGBoost low-slow misses, but ungated direct promotion adds scan-burst normal reviews.
- `gated review`: `low_slow_volume_gate_v1` removes those scan-burst normal reviews while preserving current low-and-slow review recovery.

## Operating Policy

Policy config:

```text
configs/ensemble_policy_low_slow_v2.json
```

Default behavior:

- XGBoost decides `predicted_label`.
- CTU-pretrained GRU runs in gated shadow/challenger mode.
- If GRU predicts attack while XGBoost predicts normal, evaluate `configs/gru_review_gate_low_slow_v1.json`.
- Set `review_required=true` only if the feature gate passes.
- Weighted average remains available only for integration testing.

Gate conditions:

- `rolling_12_flow_count_mean <= 4.0`
- `rolling_12_failed_flow_ratio_weighted <= 0.35`
- `rolling_60_flow_count_mean <= 4.0`
- `rolling_60_failed_flow_ratio_weighted <= 0.35`

Validation result:

- `run_blocked`: review rows `529 -> 0`, normal reviews `529 -> 0`.
- `scenario_time_blocked`: review rows `416 -> 0`, normal reviews `416 -> 0`.
- `time_blocked`: review rows `793 -> 450`, normal reviews `343 -> 0`, true attack reviews `450 -> 450`.
- If gated reviews were promoted, time-blocked F1 becomes `0.9961` with `FN=7`, `FP=0`.

Generate policy output:

```bash
python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_low_slow_v2_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_ctu13_finetuned_simulation_real_only_24h.json \
  --feature-input data/processed/simulation_real_only_24h_low_slow_features.csv \
  --gate-config configs/gru_review_gate_low_slow_v1.json \
  --output reports/policy_ensemble_output_gated_ctu13_finetuned_simulation_real_only_24h.json
```

Optional promotion mode exists for experiments only:

```bash
python src/inference/policy_ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions_simulation_real_only_24h.json \
  --gru-predictions data/predictions/gru_predictions_simulation_real_only_24h.json \
  --promote-disagreement \
  --output reports/policy_ensemble_output_promoted_simulation_real_only_24h.json
```

## Limitation

GRU sequence predictions are not identical to final-window labels. The gate was calibrated on current simulation captures, so it must be revalidated on additional real captures before automatic promotion is used in production. Keep gated GRU output as review/triage unless a larger validation set supports promotion.
