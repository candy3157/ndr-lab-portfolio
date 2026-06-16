# Combined 10 NDR Model Comparison

## Overall Dataset Summary
- Input: `data/processed/combined_10_ndr_datasets.csv`
- Total rows: `178059`
- Total columns: `107`
- Label counts: `{'normal': 112021, 'attack': 66038}`
- Source dataset counts: `{'common_ndr_features_smoke': 24000, 'common_real_plus_synthetic_smoke': 32000, 'common_synthetic_smoke': 8000, 'ctu13_common_10s_full': 81671, 'ctu13_common_10s_smoke': 5172, 'direct_pc_camera_scenario_common': 264, 'simulation_real_only_24h_common': 13354, 'simulation_real_only_24h_low_slow_v2': 13354, 'uq_iot_smoke_common': 4, 'usbcam-20260608-smoke_common': 240}`
- Dataset name counts: `{'CSE-CIC-IDS2018': 26530, 'CTU-13': 86843, 'UQ-IoT-IDS2021': 4, 'simulation': 64682}`
- Data source counts: `{'real': 162059, 'synthetic': 16000}`
- Feature schema: `ndr_common_low_slow_v2`
- Model feature columns: `90`
- Column inventory: `reports/combined_10_column_inventory.csv`

## Column Information
- Target column: `label`
- Metadata columns: `['source_dataset', 'dataset_name', 'data_source', 'is_synthetic', 'attack_type', 'timestamp', 'window_start', 'window_end', 'sequence_index', 'session_id', 'scenario_id', 'run_id', 'technique_id', 'phase', 'src_entity', '_source_file']`
- Model feature columns: `['flow_count', 'unique_dst_count', 'unique_dst_port_count', 'failed_conn_ratio', 'avg_duration', 'duration_std', 'avg_src_bytes', 'avg_dst_bytes', 'avg_total_bytes', 'packet_count_mean', 'bytes_per_second', 'packets_per_second', 'src_to_dst_bytes_ratio', 'tcp_flow_ratio', 'udp_flow_ratio', 'icmp_flow_ratio', 'dst_port_well_known_ratio', 'dst_port_registered_ratio', 'dst_port_ephemeral_ratio', 'dst_port_entropy', 'service_entropy', 'conn_state_entropy', 'rolling_6_flow_count_sum', 'rolling_6_flow_count_mean', 'rolling_6_unique_dst_count_max', 'rolling_6_unique_dst_port_count_max', 'rolling_6_unique_dst_count_growth', 'rolling_6_unique_dst_port_count_growth', 'rolling_6_failed_conn_ratio_mean', 'rolling_6_failed_flow_estimate_sum', 'rolling_6_failed_flow_ratio_weighted', 'rolling_6_avg_duration_mean', 'rolling_6_avg_total_bytes_mean', 'rolling_6_dst_port_entropy_mean', 'rolling_6_inter_window_seconds_mean', 'rolling_6_inter_window_seconds_std', 'rolling_6_flow_count_per_dst', 'rolling_6_flow_count_per_dst_port', 'rolling_6_low_slow_scan_score', 'rolling_12_flow_count_sum', 'rolling_12_flow_count_mean', 'rolling_12_unique_dst_count_max', 'rolling_12_unique_dst_port_count_max', 'rolling_12_unique_dst_count_growth', 'rolling_12_unique_dst_port_count_growth', 'rolling_12_failed_conn_ratio_mean', 'rolling_12_failed_flow_estimate_sum', 'rolling_12_failed_flow_ratio_weighted', 'rolling_12_avg_duration_mean', 'rolling_12_avg_total_bytes_mean', 'rolling_12_dst_port_entropy_mean', 'rolling_12_inter_window_seconds_mean', 'rolling_12_inter_window_seconds_std', 'rolling_12_flow_count_per_dst', 'rolling_12_flow_count_per_dst_port', 'rolling_12_low_slow_scan_score', 'rolling_30_flow_count_sum', 'rolling_30_flow_count_mean', 'rolling_30_unique_dst_count_max', 'rolling_30_unique_dst_port_count_max', 'rolling_30_unique_dst_count_growth', 'rolling_30_unique_dst_port_count_growth', 'rolling_30_failed_conn_ratio_mean', 'rolling_30_failed_flow_estimate_sum', 'rolling_30_failed_flow_ratio_weighted', 'rolling_30_avg_duration_mean', 'rolling_30_avg_total_bytes_mean', 'rolling_30_dst_port_entropy_mean', 'rolling_30_inter_window_seconds_mean', 'rolling_30_inter_window_seconds_std', 'rolling_30_flow_count_per_dst', 'rolling_30_flow_count_per_dst_port', 'rolling_30_low_slow_scan_score', 'rolling_60_flow_count_sum', 'rolling_60_flow_count_mean', 'rolling_60_unique_dst_count_max', 'rolling_60_unique_dst_port_count_max', 'rolling_60_unique_dst_count_growth', 'rolling_60_unique_dst_port_count_growth', 'rolling_60_failed_conn_ratio_mean', 'rolling_60_failed_flow_estimate_sum', 'rolling_60_failed_flow_ratio_weighted', 'rolling_60_avg_duration_mean', 'rolling_60_avg_total_bytes_mean', 'rolling_60_dst_port_entropy_mean', 'rolling_60_inter_window_seconds_mean', 'rolling_60_inter_window_seconds_std', 'rolling_60_flow_count_per_dst', 'rolling_60_flow_count_per_dst_port', 'rolling_60_low_slow_scan_score']`

## Shared Train/Validation/Test Split
- Group column: `session_id`
- Train rows: `93174`, labels: `{'normal': 75880, 'attack': 17294}`
- Validation rows: `11810`, labels: `{'normal': 8827, 'attack': 2983}`
- Test rows: `73075`, labels: `{'normal': 27314, 'attack': 45761}`
- GRU train sequences: `83306`, labels: `{'normal': 66888, 'attack': 16418}`
- GRU validation sequences: `9677`, labels: `{'normal': 6900, 'attack': 2777}`
- GRU test sequences / aligned comparison rows: `64908`, labels: `{'normal': 21985, 'attack': 42923}`

## Overall Model Metrics
| Model | Eval Rows | Threshold | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | TN | FP | FN | TP | FPR | FNR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| xgboost | 64908 | 0.8000 | 0.941702 | 0.999311 | 0.912471 | 0.953919 | 0.998500 | 0.999218 | 21958 | 27 | 3757 | 39166 | 0.1228% | 8.7529% |
| gru | 64908 | 0.6000 | 0.583857 | 0.998746 | 0.371176 | 0.541214 | 0.993982 | 0.995626 | 21965 | 20 | 26991 | 15932 | 0.0910% | 62.8824% |
| xgboost_gru | 64908 | 0.5000 | 0.974965 | 0.997686 | 0.964378 | 0.980749 | 0.999331 | 0.999578 | 21889 | 96 | 1529 | 41394 | 0.4367% | 3.5622% |

## Attack-Type Detection Performance
- Scope: `target == attack` rows only.
- Metrics: `TP`, `FN`, `Recall`, and `FNR`. FPR is not shown here because attack-only rows do not contain normal samples.
- Full attack_type table: `reports/combined_10_attack_type_detection_metrics.csv`
- Full attack scenario table: `reports/combined_10_attack_scenario_detection_metrics.csv`
- Full attack source_dataset table: `reports/combined_10_attack_source_dataset_detection_metrics.csv`

### Attack-Type Summary Table (Top 20 By Attack Rows)
| Attack Type | Model | Attack Rows | TP | FN | Recall | FNR |
|---|---|---:|---:|---:|---:|---:|
| FTP-BruteForce | gru | 23806 | 0 | 23806 | 0.000000 | 100.0000% |
| FTP-BruteForce | xgboost | 23806 | 23806 | 0 | 1.000000 | 0.0000% |
| FTP-BruteForce | xgboost_gru | 23806 | 23806 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V44-TCP-Attempt | gru | 5088 | 5087 | 1 | 0.999803 | 0.0197% |
| From-Botnet-V44-TCP-Attempt | xgboost | 5088 | 5086 | 2 | 0.999607 | 0.0393% |
| From-Botnet-V44-TCP-Attempt | xgboost_gru | 5088 | 5088 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V54-TCP-Attempt | gru | 4675 | 1666 | 3009 | 0.356364 | 64.3636% |
| From-Botnet-V54-TCP-Attempt | xgboost | 4675 | 1381 | 3294 | 0.295401 | 70.4599% |
| From-Botnet-V54-TCP-Attempt | xgboost_gru | 4675 | 3258 | 1417 | 0.696898 | 30.3102% |
| service_probe | gru | 1105 | 1097 | 8 | 0.992760 | 0.7240% |
| service_probe | xgboost | 1105 | 1092 | 13 | 0.988235 | 1.1765% |
| service_probe | xgboost_gru | 1105 | 1098 | 7 | 0.993665 | 0.6335% |
| udp_scan | gru | 924 | 923 | 1 | 0.998918 | 0.1082% |
| udp_scan | xgboost | 924 | 924 | 0 | 1.000000 | 0.0000% |
| udp_scan | xgboost_gru | 924 | 924 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-1-UDP-DNS | gru | 892 | 892 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-1-UDP-DNS | xgboost | 892 | 878 | 14 | 0.984305 | 1.5695% |
| From-Botnet-V50-1-UDP-DNS | xgboost_gru | 892 | 892 | 0 | 1.000000 | 0.0000% |
| vertical_scan | gru | 887 | 885 | 2 | 0.997745 | 0.2255% |
| vertical_scan | xgboost | 887 | 886 | 1 | 0.998873 | 0.1127% |
| vertical_scan | xgboost_gru | 887 | 885 | 2 | 0.997745 | 0.2255% |
| From-Botnet-V54-UDP-DNS | gru | 782 | 751 | 31 | 0.960358 | 3.9642% |
| From-Botnet-V54-UDP-DNS | xgboost | 782 | 707 | 75 | 0.904092 | 9.5908% |
| From-Botnet-V54-UDP-DNS | xgboost_gru | 782 | 764 | 18 | 0.976982 | 2.3018% |
| From-Botnet-V54-TCP-Attempt-SPAM | gru | 697 | 684 | 13 | 0.981349 | 1.8651% |
| From-Botnet-V54-TCP-Attempt-SPAM | xgboost | 697 | 684 | 13 | 0.981349 | 1.8651% |
| From-Botnet-V54-TCP-Attempt-SPAM | xgboost_gru | 697 | 695 | 2 | 0.997131 | 0.2869% |
| From-Botnet-V43-TCP-Attempt | gru | 566 | 543 | 23 | 0.959364 | 4.0636% |
| From-Botnet-V43-TCP-Attempt | xgboost | 566 | 517 | 49 | 0.913428 | 8.6572% |
| From-Botnet-V43-TCP-Attempt | xgboost_gru | 566 | 549 | 17 | 0.969965 | 3.0035% |
| From-Botnet-V50-5-UDP-DNS | gru | 560 | 560 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-5-UDP-DNS | xgboost | 560 | 557 | 3 | 0.994643 | 0.5357% |
| From-Botnet-V50-5-UDP-DNS | xgboost_gru | 560 | 560 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-9-UDP-DNS | gru | 531 | 531 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-9-UDP-DNS | xgboost | 531 | 526 | 5 | 0.990584 | 0.9416% |
| From-Botnet-V50-9-UDP-DNS | xgboost_gru | 531 | 531 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V43-TCP-Attempt-SPAM | gru | 485 | 484 | 1 | 0.997938 | 0.2062% |
| From-Botnet-V43-TCP-Attempt-SPAM | xgboost | 485 | 459 | 26 | 0.946392 | 5.3608% |
| From-Botnet-V43-TCP-Attempt-SPAM | xgboost_gru | 485 | 485 | 0 | 1.000000 | 0.0000% |
| horizontal_scan | gru | 416 | 416 | 0 | 1.000000 | 0.0000% |
| horizontal_scan | xgboost | 416 | 416 | 0 | 1.000000 | 0.0000% |
| horizontal_scan | xgboost_gru | 416 | 416 | 0 | 1.000000 | 0.0000% |
| low_and_slow_scan | gru | 334 | 315 | 19 | 0.943114 | 5.6886% |
| low_and_slow_scan | xgboost | 334 | 195 | 139 | 0.583832 | 41.6168% |
| low_and_slow_scan | xgboost_gru | 334 | 317 | 17 | 0.949102 | 5.0898% |
| From-Botnet-V50-9-TCP-Attempt | gru | 178 | 177 | 1 | 0.994382 | 0.5618% |
| From-Botnet-V50-9-TCP-Attempt | xgboost | 178 | 175 | 3 | 0.983146 | 1.6854% |
| From-Botnet-V50-9-TCP-Attempt | xgboost_gru | 178 | 178 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V50-5-TCP-Attempt | gru | 177 | 174 | 3 | 0.983051 | 1.6949% |
| From-Botnet-V50-5-TCP-Attempt | xgboost | 177 | 169 | 8 | 0.954802 | 4.5198% |
| From-Botnet-V50-5-TCP-Attempt | xgboost_gru | 177 | 177 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V51-9-ICMP | gru | 86 | 83 | 3 | 0.965116 | 3.4884% |
| From-Botnet-V51-9-ICMP | xgboost | 86 | 85 | 1 | 0.988372 | 1.1628% |
| From-Botnet-V51-9-ICMP | xgboost_gru | 86 | 86 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V51-2-ICMP | gru | 80 | 71 | 9 | 0.887500 | 11.2500% |
| From-Botnet-V51-2-ICMP | xgboost | 80 | 80 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V51-2-ICMP | xgboost_gru | 80 | 80 | 0 | 1.000000 | 0.0000% |
| From-Botnet-V51-8-ICMP | gru | 78 | 76 | 2 | 0.974359 | 2.5641% |
| From-Botnet-V51-8-ICMP | xgboost | 78 | 77 | 1 | 0.987179 | 1.2821% |
| From-Botnet-V51-8-ICMP | xgboost_gru | 78 | 78 | 0 | 1.000000 | 0.0000% |

### Top 15 Attack Scenarios By Attack Rows
| Scenario | Model | Attack Rows | TP | FN | Recall | FNR |
|---|---|---:|---:|---:|---:|---:|
| public-cse-cic-ids2018 | gru | 23806 | 0 | 23806 | 0.000000 | 100.0000% |
| public-cse-cic-ids2018 | xgboost | 23806 | 23806 | 0 | 1.000000 | 0.0000% |
| public-cse-cic-ids2018 | xgboost_gru | 23806 | 23806 | 0 | 1.000000 | 0.0000% |
| ctu13-scenario-13 | gru | 6189 | 3129 | 3060 | 0.505574 | 49.4426% |
| ctu13-scenario-13 | xgboost | 6189 | 2789 | 3400 | 0.450638 | 54.9362% |
| ctu13-scenario-13 | xgboost_gru | 6189 | 4744 | 1445 | 0.766521 | 23.3479% |
| ctu13-scenario-3 | gru | 5114 | 5111 | 3 | 0.999413 | 0.0587% |
| ctu13-scenario-3 | xgboost | 5114 | 5106 | 8 | 0.998436 | 0.1564% |
| ctu13-scenario-3 | xgboost_gru | 5114 | 5112 | 2 | 0.999609 | 0.0391% |
| ctu13-scenario-9 | gru | 2516 | 2511 | 5 | 0.998013 | 0.1987% |
| ctu13-scenario-9 | xgboost | 2516 | 2480 | 36 | 0.985692 | 1.4308% |
| ctu13-scenario-9 | xgboost_gru | 2516 | 2516 | 0 | 1.000000 | 0.0000% |
| ctu13-scenario-2 | gru | 1163 | 1129 | 34 | 0.970765 | 2.9235% |
| ctu13-scenario-2 | xgboost | 1163 | 1063 | 100 | 0.914015 | 8.5985% |
| ctu13-scenario-2 | xgboost_gru | 1163 | 1139 | 24 | 0.979364 | 2.0636% |
| service-probe | gru | 1112 | 1098 | 14 | 0.987410 | 1.2590% |
| service-probe | xgboost | 1112 | 1092 | 20 | 0.982014 | 1.7986% |
| service-probe | xgboost_gru | 1112 | 1099 | 13 | 0.988309 | 1.1691% |
| udp-scan | gru | 931 | 923 | 8 | 0.991407 | 0.8593% |
| udp-scan | xgboost | 931 | 924 | 7 | 0.992481 | 0.7519% |
| udp-scan | xgboost_gru | 931 | 924 | 7 | 0.992481 | 0.7519% |
| vertical-scan | gru | 890 | 885 | 5 | 0.994382 | 0.5618% |
| vertical-scan | xgboost | 890 | 886 | 4 | 0.995506 | 0.4494% |
| vertical-scan | xgboost_gru | 890 | 885 | 5 | 0.994382 | 0.5618% |
| horizontal-scan | gru | 416 | 416 | 0 | 1.000000 | 0.0000% |
| horizontal-scan | xgboost | 416 | 416 | 0 | 1.000000 | 0.0000% |
| horizontal-scan | xgboost_gru | 416 | 416 | 0 | 1.000000 | 0.0000% |
| ctu13-scenario-10 | gru | 379 | 359 | 20 | 0.947230 | 5.2770% |
| ctu13-scenario-10 | xgboost | 379 | 368 | 11 | 0.970976 | 2.9024% |
| ctu13-scenario-10 | xgboost_gru | 379 | 377 | 2 | 0.994723 | 0.5277% |
| low-and-slow | gru | 334 | 315 | 19 | 0.943114 | 5.6886% |
| low-and-slow | xgboost | 334 | 195 | 139 | 0.583832 | 41.6168% |
| low-and-slow | xgboost_gru | 334 | 317 | 17 | 0.949102 | 5.0898% |
| ctu13-scenario-12 | gru | 65 | 56 | 9 | 0.861538 | 13.8462% |
| ctu13-scenario-12 | xgboost | 65 | 41 | 24 | 0.630769 | 36.9231% |
| ctu13-scenario-12 | xgboost_gru | 65 | 59 | 6 | 0.907692 | 9.2308% |
| ctu13-scenario-7 | gru | 8 | 0 | 8 | 0.000000 | 100.0000% |
| ctu13-scenario-7 | xgboost | 8 | 0 | 8 | 0.000000 | 100.0000% |
| ctu13-scenario-7 | xgboost_gru | 8 | 0 | 8 | 0.000000 | 100.0000% |

## Normal/Benign False Positive Performance
- Scope: `target == normal` rows only.
- Metrics: `TN`, `FP`, and `FPR`. Recall/FNR is not shown here because this table measures false alarms on normal traffic.
- Full normal type table: `reports/combined_10_normal_type_false_positive_metrics.csv`
- Full normal scenario table: `reports/combined_10_normal_scenario_false_positive_metrics.csv`
- Full normal source_dataset table: `reports/combined_10_normal_source_dataset_false_positive_metrics.csv`

### Normal/Benign Summary Table
| Normal Type | Model | Normal Rows | TN | FP | FPR |
|---|---|---:|---:|---:|---:|
| Benign | gru | 12051 | 12043 | 8 | 0.0664% |
| Benign | xgboost | 12051 | 12048 | 3 | 0.0249% |
| Benign | xgboost_gru | 12051 | 11967 | 84 | 0.6970% |
| normal | gru | 9934 | 9922 | 12 | 0.1208% |
| normal | xgboost | 9934 | 9910 | 24 | 0.2416% |
| normal | xgboost_gru | 9934 | 9922 | 12 | 0.1208% |

### Top 15 Normal Scenarios By Normal Rows
| Scenario | Model | Normal Rows | TN | FP | FPR |
|---|---|---:|---:|---:|---:|
| ctu13-scenario-13 | gru | 6506 | 6506 | 0 | 0.0000% |
| ctu13-scenario-13 | xgboost | 6506 | 6494 | 12 | 0.1844% |
| ctu13-scenario-13 | xgboost_gru | 6506 | 6506 | 0 | 0.0000% |
| vertical-scan | gru | 2808 | 2808 | 0 | 0.0000% |
| vertical-scan | xgboost | 2808 | 2808 | 0 | 0.0000% |
| vertical-scan | xgboost_gru | 2808 | 2808 | 0 | 0.0000% |
| udp-scan | gru | 2788 | 2788 | 0 | 0.0000% |
| udp-scan | xgboost | 2788 | 2788 | 0 | 0.0000% |
| udp-scan | xgboost_gru | 2788 | 2788 | 0 | 0.0000% |
| baseline | gru | 2777 | 2777 | 0 | 0.0000% |
| baseline | xgboost | 2777 | 2776 | 1 | 0.0360% |
| baseline | xgboost_gru | 2777 | 2777 | 0 | 0.0000% |
| ctu13-scenario-1 | gru | 2406 | 2406 | 0 | 0.0000% |
| ctu13-scenario-1 | xgboost | 2406 | 2400 | 6 | 0.2494% |
| ctu13-scenario-1 | xgboost_gru | 2406 | 2404 | 2 | 0.0831% |
| service-probe | gru | 1720 | 1720 | 0 | 0.0000% |
| service-probe | xgboost | 1720 | 1720 | 0 | 0.0000% |
| service-probe | xgboost_gru | 1720 | 1720 | 0 | 0.0000% |
| horizontal-scan | gru | 1440 | 1440 | 0 | 0.0000% |
| horizontal-scan | xgboost | 1440 | 1440 | 0 | 0.0000% |
| horizontal-scan | xgboost_gru | 1440 | 1440 | 0 | 0.0000% |
| ctu13-scenario-3 | gru | 737 | 736 | 1 | 0.1357% |
| ctu13-scenario-3 | xgboost | 737 | 734 | 3 | 0.4071% |
| ctu13-scenario-3 | xgboost_gru | 737 | 734 | 3 | 0.4071% |
| low-and-slow | gru | 334 | 334 | 0 | 0.0000% |
| low-and-slow | xgboost | 334 | 334 | 0 | 0.0000% |
| low-and-slow | xgboost_gru | 334 | 334 | 0 | 0.0000% |
| ctu13-scenario-8 | gru | 208 | 200 | 8 | 3.8462% |
| ctu13-scenario-8 | xgboost | 208 | 206 | 2 | 0.9615% |
| ctu13-scenario-8 | xgboost_gru | 208 | 204 | 4 | 1.9231% |
| public-cse-cic-ids2018 | gru | 184 | 176 | 8 | 4.3478% |
| public-cse-cic-ids2018 | xgboost | 184 | 182 | 2 | 1.0870% |
| public-cse-cic-ids2018 | xgboost_gru | 184 | 100 | 84 | 45.6522% |
| ctu13-scenario-6 | gru | 50 | 47 | 3 | 6.0000% |
| ctu13-scenario-6 | xgboost | 50 | 49 | 1 | 2.0000% |
| ctu13-scenario-6 | xgboost_gru | 50 | 47 | 3 | 6.0000% |
| ctu13-scenario-7 | gru | 14 | 14 | 0 | 0.0000% |
| ctu13-scenario-7 | xgboost | 14 | 14 | 0 | 0.0000% |
| ctu13-scenario-7 | xgboost_gru | 14 | 14 | 0 | 0.0000% |
| ctu13-scenario-12 | gru | 13 | 13 | 0 | 0.0000% |
| ctu13-scenario-12 | xgboost | 13 | 13 | 0 | 0.0000% |
| ctu13-scenario-12 | xgboost_gru | 13 | 13 | 0 | 0.0000% |

## XGBoost All-Test-Row Reference
- XGBoost can score every row, while GRU/ensemble require a sequence tail row.
- All XGBoost test rows: `73075`
- All-row FPR: `0.2563%`, FNR: `8.5269%`

## Ensemble Configuration
- XGBoost selected threshold: `0.7999999999999999`
- GRU selected threshold: `0.6`
- Method: `soft_vote`
- XGBoost weight: `0.5`
- GRU weight: `0.5`
- Selected threshold: `0.49999999999999994`
- Threshold selection: `max_validation_f1_then_recall_then_lower_fpr`

## Outputs
- xgb_model: `models/xgboost_model_combined_10_common_split.joblib`
- xgb_preprocessor: `models/xgboost_preprocessor_combined_10_common_split.joblib`
- gru_model: `models/gru_model_combined_10_common_split.pt`
- gru_scaler: `models/gru_scaler_combined_10_common_split.joblib`
- feature_list: `models/combined_10_feature_list_common_split.json`
- ensemble: `models/xgboost_gru_ensemble_combined_10.json`
- predictions: `reports/combined_10_aligned_model_predictions.csv`
- column_inventory: `reports/combined_10_column_inventory.csv`
- comparison_json: `reports/combined_10_model_comparison.json`
- comparison_md: `reports/combined_10_model_comparison.md`

## Notes
- The 10 requested datasets are combined before splitting; models are not trained per dataset.
- The model comparison table uses aligned tail-window rows so XGBoost, GRU, and XGBoost+GRU are evaluated on identical test rows.
- XGBoost can score every test row, so its all-row test metric is retained separately in evaluation_scope.
- Each model threshold is selected on the validation split and then applied once to the held-out test split.
- The ensemble is a validation-selected soft vote over XGBoost and GRU probabilities.
