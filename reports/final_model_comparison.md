# Final Model Comparison

- Created at: `2026-06-05T12:37:53.826119+00:00`
- Feature schema: `ndr_common_v1`
- Evaluation scope: `smoke_sample_pipeline_validation`

## Dataset Summary
- Processed rows: `24000`
- Dataset counts: `{'CSE-CIC-IDS2018': 12000, 'simulation': 12000}`
- Label counts: `{'attack': 14549, 'normal': 9451}`
- Synthetic rows: `8000`

## Simulation Real-Only 24h Summary
- Rows: `13354`
- Label counts: `{'attack': 3285, 'normal': 10069}`
- Sequence counts: `{'12': 12694, '24': 11974, '6': 13054}`
- Findings: `[{'message': 'dataset_name is dominated by simulation (1.000).', 'severity': 'medium'}]`

## Metrics
| Scope | Model | Rows/Seq | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| xgboost_real_only | xgboost | 3021 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| xgboost_real_plus_synthetic | xgboost | 4684 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| xgboost_synthetic_only | xgboost | 1663 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| gru_real_only | gru | 2956 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| gru_real_plus_synthetic | gru | 4619 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| gru_synthetic_only | gru | 1598 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| xgboost_simulation_real_only_24h | xgboost | 3639 | 0.9321 | 0.7670 | 1.0000 | 0.8681 | 1.0000 | 1.0000 |
| gru_simulation_real_only_24h | gru | 3564 | 0.9994 | 1.0000 | 0.9993 | 0.9996 | 0.9996 | 0.9999 |
| xgboost_low_slow_v2 | xgboost | 3639 | 0.9997 | 0.9988 | 1.0000 | 0.9994 | 1.0000 | 1.0000 |
| gru_ctu13_smoke | gru | 434 | 0.9862 | 0.9368 | 1.0000 | 0.9674 | 0.9920 | 0.9613 |
| gru_ctu13_full | gru | 13398 | 0.9911 | 0.9863 | 0.9886 | 0.9874 | 0.9990 | 0.9984 |
| gru_simulation_baseline_compare | gru | 3564 | 0.9994 | 1.0000 | 0.9993 | 0.9996 | 0.9996 | 0.9999 |
| gru_ctu13_full_to_simulation_finetuned | gru | 3564 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## XGBoost Threshold And Blocked Validation
- Report: `reports/xgboost_threshold_blocked_validation_simulation_real_only_24h.md`
- Sweep: `reports/xgboost_threshold_sweep_simulation_real_only_24h.csv`
- Predictions: `reports/xgboost_blocked_validation_predictions_simulation_real_only_24h.csv`
- run_blocked: threshold `0.95`, test precision `1.0000`, recall `1.0000`, F1 `1.0000`
- scenario_time_blocked: threshold `0.32`, test precision `0.6677`, recall `0.9575`, F1 `0.7868`
- time_blocked: threshold `0.95`, test precision `1.0000`, recall `0.4768`, F1 `0.6457`
- Time-blocked false negatives: `507`
- False negatives by scenario: `{'low-and-slow': 507}`
- Interpretation: Time-blocked misses are concentrated in later attack windows. This should be treated as temporal generalization risk, not a threshold-only issue.

## Low-And-Slow Feature V2
- Report: `reports/low_slow_feature_evaluation_report.md`
- Augmented data: `data/processed/simulation_real_only_24h_low_slow_features.csv`
- Feature count: `90`
- Added rolling features: `68`
- Conclusion: With low-and-slow present in train/validation and rolling features enabled, low_slow_v2 reduces scenario-time-blocked false negatives from 28 to 1 and false positives from 314 to 4. The remaining global time-blocked failure is caused by zero low-and-slow coverage before the future test block.

## GRU/XGBoost Cross Analysis
- Report: `reports/gru_xgb_cross_analysis_report.md`
- Aligned predictions: `reports/gru_xgb_aligned_predictions.csv`
- Policy config: `configs/ensemble_policy_low_slow_v2.json`
- Policy sample output: `reports/policy_ensemble_output_simulation_real_only_24h.json`
- Test rows by strategy: `{'run_blocked': 2778, 'scenario_time_blocked': 2537, 'time_blocked': 2496}`
- run_blocked: Ensemble is not justified for run_blocked without additional tuning. F1 delta `-0.2957`, recall delta `0.0000`, FP delta `529`
- scenario_time_blocked: Ensemble is not justified for scenario_time_blocked without additional tuning. F1 delta `-0.2499`, recall delta `0.0000`, FP delta `416`
- time_blocked: GRU catches 222/457 XGBoost v2 false negatives but adds 339 false positives; use with policy constraints. F1 delta `0.0382`, recall delta `0.2458`, FP delta `339`

## CTU-13 Cross-Domain Sequence Benchmark
- Conversion report: `reports/ctu13_conversion_report.md`
- Data sufficiency report: `reports/data_sufficiency_ctu13_smoke.md`
- GRU metrics: `reports/gru_metrics_ctu13_smoke.json`
- GRU blocked validation: `reports/gru_blocked_validation_ctu13_smoke.md`
- Processed output: `data/processed/ctu13_common_10s_smoke.csv`
- Window rows: `5172`
- Window label counts: `{'attack': 966, 'normal': 4206}`
- Sequence counts: `{'12': 4336, '24': 3887, '6': 4636}`
- Background policy: `exclude`
- Sampled: `True`
- Intended use: Cross-domain GRU sequence challenger benchmark/pretraining only.

## CTU-13 Full Pretraining Impact
- Conversion report: `reports/ctu13_conversion_full_report.md`
- Data sufficiency report: `reports/data_sufficiency_ctu13_full.md`
- CTU full GRU metrics: `reports/gru_metrics_ctu13_full.json`
- CTU full GRU blocked validation: `reports/gru_blocked_validation_ctu13_full.md`
- Simulation fine-tuned metrics: `reports/gru_metrics_ctu13_full_to_simulation_finetuned.json`
- Simulation fine-tuned blocked validation: `reports/gru_blocked_validation_ctu13_pretrained_simulation_finetuned.md`
- Impact report: `reports/ctu13_pretraining_impact_report.md`
- Processed output: `data/processed/ctu13_common_10s_full.csv`
- Window rows: `81671`
- Window label counts: `{'attack': 26054, 'normal': 55617}`
- Sequence counts: `{'12': 79847, '24': 78621, '6': 80620}`
- run_blocked: CTU pretraining does not clearly improve run_blocked.
- scenario_time_blocked: CTU pretraining does not clearly improve scenario_time_blocked.
- time_blocked: CTU pretraining improves default-threshold F1 for time_blocked, but threshold policy still needs validation.

## Gated GRU Review Policy
- Report: `reports/gated_gru_review_policy_report.md`
- Predictions: `reports/gated_gru_review_policy_predictions.csv`
- Gate config: `configs/gru_review_gate_low_slow_v1.json`
- Policy sample output: `reports/policy_ensemble_output_gated_ctu13_finetuned_simulation_real_only_24h.json`
- Gate: `low_slow_volume_gate_v1`
- run_blocked: reviews `529` -> `0`, normal reviews `529` -> `0`, attack reviews `0` -> `0`. Gate removes 529 normal reviews while preserving true attack reviews for run_blocked.
- scenario_time_blocked: reviews `416` -> `0`, normal reviews `416` -> `0`, attack reviews `0` -> `0`. Gate removes 416 normal reviews while preserving true attack reviews for scenario_time_blocked.
- time_blocked: reviews `793` -> `450`, normal reviews `343` -> `0`, attack reviews `450` -> `450`. Gate removes 343 normal reviews while preserving true attack reviews for time_blocked.

## Judgement
- XGBoost: Operating-candidate structure is present. The simulation real-only 24h run has full recall at threshold 0.5 but lower precision. Run-blocked tuning recommends a higher threshold, while time-blocked validation exposes low-and-slow false negatives. Low-slow v2 rolling features fix the issue under scenario-aware future-run validation when low-and-slow has train/validation coverage, but global future validation still fails if low-and-slow is absent before the test horizon.
- GRU: Sequence challenger structure is present. Cross-analysis shows it can catch some low-and-slow misses under global future time blocking, but its sequence-level alerts are not equivalent to single-window labels and should remain challenger/shadow until additional validation.
- Ensemble: Naive OR promotion is not justified. The current recommended integration is XGBoost low-slow v2 as primary, with CTU-pretrained GRU review allowed only when the low-slow feature gate passes. The gate preserved low-and-slow review recovery and removed scan-burst normal reviews in current validation. Weighted average remains available only for integration testing.

## Limitations
- Public CSE-CIC-IDS2018 and UQ-IoT-IDS2021 results are cross-domain references only.
- CTU-13 results are cross-domain botnet/C2 references for GRU sequence development only.
- UQ-IoT-IDS2021 is present as PCAP in this workspace; row-level training requires Zeek/tshark extraction.
- Smoke metrics can be inflated by easy domain separation and must not be used as operating performance claims.
- Synthetic data is for augmentation and pipeline validation, not final performance proof.
- Raw IP addresses are excluded from model input; IPs may only be used upstream for grouping/sessionization.
- GRU sequence predictions should not be directly OR-promoted into final-window attack labels without policy constraints.
- The GRU review gate was calibrated on current simulation captures and must be recalibrated with additional real captures.

## Next Steps
- Run full CSE chunk conversion and Zeek feature extraction for UQ PCAPs.
- Run full CTU-13 conversion with --max-rows-per-file 0 if CTU pretraining is needed beyond smoke validation.
- Run group/time blocked real-only simulation evaluation after more 24h captures are collected.
- Validate low_slow_volume_gate_v1 on additional 24h/daily simulation captures before treating gated GRU reviews as production-grade.
- Tune GRU sequence_length and gated review thresholds on a larger real validation split.
- Add production monitoring for schema drift and score calibration.
