# XGBoost Combined 10 NDR Evaluation

- Combined dataset: `data/processed/combined_10_ndr_datasets.csv`
- Metrics JSON: `reports/xgboost_metrics_combined_10_ndr.json`
- Threshold: `0.5`
- Features: `90` using `ndr_common_low_slow_v2`
- Train rows: `104984`
- Test rows: `73075`
- Combined label counts: `{'attack': 66038, 'normal': 112021}`

## Overall Metrics
| metric | value |
|---|---:|
| accuracy | 0.987301 |
| precision | 0.992400 |
| recall | 0.987282 |
| f1 | 0.989834 |
| roc_auc | 0.997910 |
| pr_auc | 0.998723 |
| false_positive_rate | 1.2667% |
| false_negative_rate | 1.2718% |

## Confusion Matrix
| actual \ predicted | normal | attack |
|---|---:|---:|
| normal | 26968 | 346 |
| attack | 582 | 45179 |

## Source Dataset Test Breakdown
| source_dataset | rows | FP | FN | FPR | FNR | precision | recall | f1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `common_ndr_features_smoke` | 15883 | 86 | 2 | 2.7608% | 0.0157% | 0.993308 | 0.999843 | 0.996565 |
| `common_real_plus_synthetic_smoke` | 19378 | 133 | 3 | 2.4855% | 0.0214% | 0.990605 | 0.999786 | 0.995175 |
| `common_synthetic_smoke` | 3495 | 47 | 1 | 2.1020% | 0.0794% | 0.963985 | 0.999206 | 0.981279 |
| `ctu13_common_10s_full` | 24607 | 56 | 337 | 0.5874% | 2.2356% | 0.996214 | 0.977644 | 0.986842 |
| `ctu13_common_10s_smoke` | 1106 | 5 | 74 | 0.7776% | 15.9827% | 0.987310 | 0.840173 | 0.907818 |
| `direct_pc_camera_scenario_common` | 37 | 6 | 3 | 37.5000% | 14.2857% | 0.750000 | 0.857143 | 0.800000 |
| `simulation_real_only_24h_common` | 4250 | 0 | 154 | 0.0000% | 14.7087% | 1.000000 | 0.852913 | 0.920619 |
| `simulation_real_only_24h_low_slow_v2` | 4250 | 8 | 1 | 0.2498% | 0.0955% | 0.992410 | 0.999045 | 0.995716 |
| `usbcam-20260608-smoke_common` | 69 | 5 | 7 | 35.7143% | 12.7273% | 0.905660 | 0.872727 | 0.888889 |

## Notes
- The split is the existing group-aware split in `train_xgboost_product.py`, using `session_id` when available.
- This run combines the 10 requested datasets exactly as listed, so overlapping datasets are counted more than once.
- `uq_iot_smoke_common` has only 4 attack rows and did not land in this test split, so it is not present in the source-dataset test breakdown.
