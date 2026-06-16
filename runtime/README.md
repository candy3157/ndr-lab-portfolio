# NDR ML VM Runtime Bundle

This folder is a runtime-only subset of `ndr-ml` for moving the trained
Combined 10 XGBoost+GRU model to a VM lab.

It intentionally excludes training datasets, reports, notebooks, and historical
experiment outputs.

## Included Files

- `models/`
  - `xgboost_model_combined_10_common_split.joblib`
  - `xgboost_preprocessor_combined_10_common_split.joblib`
  - `gru_model_combined_10_common_split.pt`
  - `gru_scaler_combined_10_common_split.joblib`
  - `combined_10_feature_list_common_split.json`
  - `xgboost_gru_ensemble_combined_10.json`
- `configs/`
  - `feature_schema_low_slow_v2.json`
  - `inference_config.yaml`
  - `ensemble_policy_low_slow_v2.json`
  - `gru_review_gate_low_slow_v1.json`
- Feature generation scripts
  - `convert_zeek_conn_to_common.py`
  - `augment_low_slow_features.py`
  - `profile_public_datasets.py`
- Inference package
  - `src/inference/`
  - `src/models/gru_model.py`
  - `src/data/sequence_dataset.py`
- `requirements.txt`

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Automated VM Lab Flow

Run this on the monitor VM after the dashboard server is already running.

## Chunk-Based Realtime VM Lab Flow

Use this when the dashboard should keep updating while the lab is running. Start
the dashboard server and `ubuntu-workload-client` first, then run:

```bash
scripts/run_realtime_router_pipeline.sh --include-raw
```

The realtime script repeats this loop until `Ctrl+C`:

1. Capture a short router pcap chunk with `tcpdump`.
2. Copy the chunk pcap to the monitor VM.
3. Convert the chunk to Zeek `conn.log`.
4. Append the chunk's common feature rows to the current run.
5. Rebuild rolling low-and-slow features over the accumulated run.
6. Run XGBoost on all accumulated rows.
7. Run GRU where enough sequence history exists.
8. Emit XGBoost-only fallback rows until GRU has enough windows.
9. Convert only newly created predictions into dashboard events and post them.

Default realtime values are tuned for the server zone and IoT lab scenario:

- Router SSH: `root@10.10.99.1`
- Router capture interface: `em2`
- Capture filter: `(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24`
- Chunk length: `60` seconds
- Model window length: `10` seconds
- Dashboard URL: `http://127.0.0.1:8000`
- Dashboard target display: `10.10.20.0/24`
- Source IP handling: dynamic, based on Zeek `id.orig_h`
- Server zone hosts: App/DB `10.10.20.10`, IoT lab `10.10.20.20-24`, Debian `10.10.20.30`

Recommended server zone realtime command:

```bash
scripts/run_realtime_router_pipeline.sh \
  --router-interface em2 \
  --capture-filter "(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24" \
  --dynamic-src-ip \
  --target-network "10.10.20.0/24" \
  --dashboard-url http://127.0.0.1:8000 \
  --chunk-seconds 60 \
  --window-seconds 10 \
  --include-raw
```

With this mode, normal Ubuntu client traffic should continue to create normal
events. When Kali starts scanning the server zone or IoT lab, later chunks should move
to warning or scanning depending on the model probability. The first five
windows can only use XGBoost because GRU needs six windows of history; from the
sixth window onward the script sends XGBoost+GRU ensemble results where aligned
GRU predictions exist.

Manual Kali scan mode:

```bash
scripts/run_vm_lab_pipeline.sh --manual-scan
```

The bundle default values are currently set to:

- Router SSH: `root@10.10.99.1`
- Router capture interface: `em4`
- Kali IP: `10.10.90.10`
- Capture filter: `host 10.10.90.10 or net 10.10.10.0/24 or net 10.10.20.0/24`
- Dashboard target display: `10.10.10.0/24,10.10.20.0/24`
- Dashboard URL: `http://127.0.0.1:8000`

You can still override these defaults:

```bash
scripts/run_vm_lab_pipeline.sh \
  --manual-scan \
  --router-ssh root@<router-ip> \
  --router-interface <router-lan-interface> \
  --capture-filter "host <kali-ip> or net <target-cidr>" \
  --src-ip <kali-ip> \
  --target-network <target-cidr> \
  --dashboard-url http://127.0.0.1:8000 \
  --sensor-id sensor-01 \
  --window-seconds 10 \
  --include-raw
```

After the script starts router capture, run the scan on Kali manually. When the
scan is done, return to the monitor VM terminal and press Enter.

Timed capture mode:

```bash
scripts/run_vm_lab_pipeline.sh \
  --capture-seconds 60 \
  --router-ssh root@<router-ip> \
  --router-interface <router-lan-interface> \
  --capture-filter "host <kali-ip> or net <target-cidr>" \
  --src-ip <kali-ip> \
  --target-network <target-cidr> \
  --dashboard-url http://127.0.0.1:8000 \
  --sensor-id sensor-01 \
  --window-seconds 10 \
  --include-raw
```

Normal baseline followed by Kali scan against the App/DB network:

```bash
scripts/run_vm_lab_pipeline.sh \
  --manual-scan \
  --router-interface em2 \
  --capture-filter "(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24" \
  --dynamic-src-ip \
  --target-network "10.10.20.0/24" \
  --dashboard-url http://127.0.0.1:8000 \
  --sensor-id sensor-01 \
  --window-seconds 10 \
  --include-raw
```

Start `ubuntu-workload-client` before running the pipeline. After router capture
starts, wait briefly so normal traffic is captured, then run the Kali scan
against `10.10.20.0/24`. Press Enter after the scan ends.

Remote Kali scan mode:

```bash
scripts/run_vm_lab_pipeline.sh \
  --kali-ssh root@<kali-ip> \
  --router-ssh root@<router-ip> \
  --router-interface <router-lan-interface> \
  --scan-command "nmap -sS -Pn -T4 <target-cidr>" \
  --capture-filter "host <kali-ip> or net <target-cidr>" \
  --src-ip <kali-ip> \
  --target-network <target-cidr> \
  --dashboard-url http://127.0.0.1:8000 \
  --sensor-id sensor-01 \
  --window-seconds 10 \
  --include-raw
```

This single command performs:

1. Start `tcpdump` on the router.
2. Wait for a manual Kali scan, wait for a timed capture, or run the scan command on Kali.
3. Stop router capture and copy the pcap to the monitor VM.
4. Convert pcap to Zeek `conn.log`.
5. Convert Zeek logs into common NDR features.
6. Add low-and-slow rolling features.
7. Run XGBoost, GRU, and XGBoost+GRU ensemble inference.
8. Convert ensemble output into dashboard events.
9. Send dashboard events to `POST /api/events`.

## Typical Flow

1. Convert Zeek `conn.log` into common window features.

```bash
python convert_zeek_conn_to_common.py \
  --input path/to/conn.log \
  --output data/processed/current_common.csv \
  --dataset-name vm-lab \
  --label normal \
  --scenario-id vm-lab \
  --window-seconds 10
```

2. Add low-and-slow rolling features.

```bash
python augment_low_slow_features.py \
  --input data/processed/current_common.csv \
  --output data/processed/current_low_slow_features.csv \
  --schema-output configs/feature_schema_low_slow_v2.json \
  --feature-list-output models/combined_10_feature_list_common_split.json
```

3. Run XGBoost probability inference.

```bash
python src/inference/xgboost_infer.py \
  --input data/processed/current_low_slow_features.csv \
  --model models/xgboost_model_combined_10_common_split.joblib \
  --preprocessor models/xgboost_preprocessor_combined_10_common_split.joblib \
  --features models/combined_10_feature_list_common_split.json \
  --output data/predictions/xgboost_predictions.json
```

4. Run GRU sequence probability inference.

```bash
python src/inference/gru_infer.py \
  --input data/processed/current_low_slow_features.csv \
  --feature-schema configs/feature_schema_low_slow_v2.json \
  --model models/gru_model_combined_10_common_split.pt \
  --scaler models/gru_scaler_combined_10_common_split.joblib \
  --output data/predictions/gru_predictions.json
```

5. Combine XGBoost and GRU probabilities with the Combined 10 soft-vote policy.

```bash
python src/inference/ensemble_infer.py \
  --xgboost-predictions data/predictions/xgboost_predictions.json \
  --gru-predictions data/predictions/gru_predictions.json \
  --xgboost-weight 0.5 \
  --gru-weight 0.5 \
  --threshold 0.5 \
  --output reports/ensemble_predictions.json
```

6. Convert the ensemble output into dashboard events.

```bash
python scripts/convert_ensemble_predictions_to_dashboard_events.py \
  --ensemble reports/ensemble_predictions.json \
  --features data/processed/current_low_slow_features.csv \
  --output reports/dashboard_events.json \
  --sensor-id sensor-01 \
  --window-seconds 10 \
  --include-raw
```

7. Post the dashboard events.

```bash
python scripts/send_dashboard_events.py \
  --url http://127.0.0.1:8000 \
  --input reports/dashboard_events.json \
  --delay 0.1
```

## Notes

- The Combined 10 ensemble policy is a late-fusion soft vote:
  `p_ensemble = 0.5 * p_xgboost + 0.5 * p_gru`.
- GRU produces predictions only after a 6-window sequence is available.
- The current dashboard expects HTTP events at `POST /api/events`; this bundle
  only contains model runtime files and does not include the dashboard server.
- For live VM operation, add a small adapter that maps the final ensemble result
  to the dashboard event JSON format.
- The conversion script uses the feature CSV to recover per-window evidence such
  as `flow_count`, `unique_dst_ips`, and `failed_conn_ratio`.
- Zeek conversion preserves `id.orig_h` as `src_ip`, so dashboard events can show
  the scanner or suspicious source IP. In this lab, the default source IP is
  fixed to `10.10.90.10`.
