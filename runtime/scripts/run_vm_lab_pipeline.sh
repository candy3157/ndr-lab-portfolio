#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_ROOT="data/lab-runs"
KALI_SSH=""
ROUTER_SSH="root@10.10.99.1"
ROUTER_INTERFACE="em4"
ROUTER_PCAP=""
ROUTER_TCPDUMP_PREFIX=""
CAPTURE_FILTER="host 10.10.90.10 or net 10.10.10.0/24 or net 10.10.20.0/24"
SCAN_COMMAND=""
MANUAL_SCAN="0"
CAPTURE_SECONDS=""
LOCAL_PCAP=""
DASHBOARD_URL="http://127.0.0.1:8000"
SENSOR_ID="sensor-01"
DATASET_NAME="vm-lab"
SCENARIO_ID="vm-lab-router-scan"
WINDOW_SECONDS="10"
SRC_IP="10.10.90.10"
TARGET_NETWORK="10.10.10.0/24,10.10.20.0/24"
INCLUDE_RAW="0"
KEEP_REMOTE_PCAP="0"
CAPTURE_PID=""
CAPTURE_STOPPED="0"

usage() {
  cat <<'EOF'
Usage:
  Manual Kali scan mode:
  scripts/run_vm_lab_pipeline.sh \
    --manual-scan \
    --router-ssh root@<router-ip> \
    --router-interface <router-lan-iface> \
    --target-network <target-cidr> \
    --dashboard-url http://127.0.0.1:8000

  Timed router capture mode:
  scripts/run_vm_lab_pipeline.sh \
    --capture-seconds 60 \
    --router-ssh root@<router-ip> \
    --router-interface <router-lan-iface> \
    --target-network <target-cidr> \
    --dashboard-url http://127.0.0.1:8000

  Remote Kali scan mode:
  scripts/run_vm_lab_pipeline.sh \
    --kali-ssh root@<kali-ip> \
    --router-ssh root@<router-ip> \
    --router-interface <router-lan-iface> \
    --scan-command "nmap -sS -Pn -T4 <target-cidr>" \
    --target-network <target-cidr> \
    --dashboard-url http://127.0.0.1:8000

Optional:
  --capture-filter "host <kali-ip> or net <target-cidr>"
  --router-pcap /tmp/ndr-router-scan.pcap
  --router-tcpdump-prefix "sudo"
  --local-pcap path/to/existing.pcap
  --manual-scan
  --capture-seconds 60
  --run-id custom-run-id
  --src-ip <kali-ip>
  --dynamic-src-ip
  --sensor-id sensor-01
  --window-seconds 10
  --include-raw
  --keep-remote-pcap

If --local-pcap is provided, SSH capture and Kali scan are skipped.
If --manual-scan is provided, start the router capture, run Kali manually,
then press Enter to stop capture and continue analysis.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --work-root) WORK_ROOT="$2"; shift 2 ;;
    --kali-ssh) KALI_SSH="$2"; shift 2 ;;
    --router-ssh) ROUTER_SSH="$2"; shift 2 ;;
    --router-interface) ROUTER_INTERFACE="$2"; shift 2 ;;
    --router-pcap) ROUTER_PCAP="$2"; shift 2 ;;
    --router-tcpdump-prefix) ROUTER_TCPDUMP_PREFIX="$2"; shift 2 ;;
    --capture-filter) CAPTURE_FILTER="$2"; shift 2 ;;
    --scan-command) SCAN_COMMAND="$2"; shift 2 ;;
    --manual-scan) MANUAL_SCAN="1"; shift ;;
    --capture-seconds) CAPTURE_SECONDS="$2"; shift 2 ;;
    --local-pcap) LOCAL_PCAP="$2"; shift 2 ;;
    --dashboard-url) DASHBOARD_URL="$2"; shift 2 ;;
    --sensor-id) SENSOR_ID="$2"; shift 2 ;;
    --dataset-name) DATASET_NAME="$2"; shift 2 ;;
    --scenario-id) SCENARIO_ID="$2"; shift 2 ;;
    --window-seconds) WINDOW_SECONDS="$2"; shift 2 ;;
    --src-ip) SRC_IP="$2"; shift 2 ;;
    --dynamic-src-ip) SRC_IP=""; shift ;;
    --target-network) TARGET_NETWORK="$2"; shift 2 ;;
    --include-raw) INCLUDE_RAW="1"; shift ;;
    --keep-remote-pcap) KEEP_REMOTE_PCAP="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "required command is missing: $1" >&2
    exit 1
  fi
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

stop_router_capture() {
  if [[ -n "$CAPTURE_PID" && "$CAPTURE_STOPPED" == "0" ]]; then
    echo "[pipeline] stopping router tcpdump pid=$CAPTURE_PID"
    ssh "$ROUTER_SSH" "kill -INT $CAPTURE_PID >/dev/null 2>&1 || true; sleep 2" || true
    CAPTURE_STOPPED="1"
  fi
}

cleanup() {
  stop_router_capture
}
trap cleanup EXIT

require_command python
require_command ssh
require_command scp
require_command zeek

RUN_DIR="$WORK_ROOT/$RUN_ID"
PCAP_LOCAL="$RUN_DIR/router_capture.pcap"
ZEEK_DIR="$RUN_DIR/zeek"
COMMON_CSV="data/processed/${RUN_ID}_common.csv"
LOW_SLOW_CSV="data/processed/${RUN_ID}_low_slow_features.csv"
RUN_FEATURE_SCHEMA="$RUN_DIR/feature_schema_low_slow_v2.json"
RUN_FEATURE_LIST="$RUN_DIR/feature_list_common_split.json"
RUN_AUGMENT_REPORT_JSON="$RUN_DIR/low_slow_feature_augmentation_report.json"
RUN_AUGMENT_REPORT_MD="$RUN_DIR/low_slow_feature_augmentation_report.md"
XGB_PRED="data/predictions/${RUN_ID}_xgboost_predictions.json"
GRU_PRED="data/predictions/${RUN_ID}_gru_predictions.json"
ENSEMBLE_JSON="reports/${RUN_ID}_ensemble_predictions.json"
DASHBOARD_EVENTS="reports/${RUN_ID}_dashboard_events.json"

mkdir -p "$RUN_DIR" "$ZEEK_DIR" data/processed data/predictions reports

if [[ -n "$LOCAL_PCAP" ]]; then
  echo "[pipeline] using existing local pcap: $LOCAL_PCAP"
  cp "$LOCAL_PCAP" "$PCAP_LOCAL"
else
  if [[ -z "$ROUTER_SSH" || -z "$ROUTER_INTERFACE" ]]; then
    echo "missing required router capture arguments" >&2
    usage
    exit 2
  fi
  if [[ "$MANUAL_SCAN" != "1" && -z "$CAPTURE_SECONDS" && ( -z "$KALI_SSH" || -z "$SCAN_COMMAND" ) ]]; then
    echo "missing Kali scan arguments; use --manual-scan or --capture-seconds when scanning manually" >&2
    usage
    exit 2
  fi
  if [[ -z "$ROUTER_PCAP" ]]; then
    ROUTER_PCAP="/tmp/ndr-${RUN_ID}.pcap"
  fi

  router_pcap_q="$(shell_quote "$ROUTER_PCAP")"
  router_iface_q="$(shell_quote "$ROUTER_INTERFACE")"
  router_log_q="$(shell_quote "/tmp/ndr-router-capture-${RUN_ID}.log")"
  filter_clause=""
  if [[ -n "$CAPTURE_FILTER" ]]; then
    filter_clause=" $(shell_quote "$CAPTURE_FILTER")"
  fi
  capture_cmd="rm -f $router_pcap_q; nohup $ROUTER_TCPDUMP_PREFIX tcpdump -U -i $router_iface_q -w $router_pcap_q$filter_clause >$router_log_q 2>&1 & echo \$!"

  echo "[pipeline] starting router tcpdump on $ROUTER_SSH:$ROUTER_INTERFACE"
  CAPTURE_PID="$(ssh "$ROUTER_SSH" "$capture_cmd" | tail -n 1 | tr -d '\r')"
  sleep 2

  if [[ "$MANUAL_SCAN" == "1" ]]; then
    echo "[pipeline] router capture is running."
    echo "[pipeline] run the Kali scan manually now, then press Enter here to stop capture and continue."
    read -r _
  elif [[ -n "$CAPTURE_SECONDS" ]]; then
    echo "[pipeline] router capture is running for ${CAPTURE_SECONDS}s. Run the Kali scan manually now."
    sleep "$CAPTURE_SECONDS"
  else
    echo "[pipeline] running Kali scan: $SCAN_COMMAND"
    ssh "$KALI_SSH" "$SCAN_COMMAND"
  fi

  stop_router_capture

  echo "[pipeline] copying router pcap to $PCAP_LOCAL"
  scp "$ROUTER_SSH:$ROUTER_PCAP" "$PCAP_LOCAL"
  if [[ "$KEEP_REMOTE_PCAP" != "1" ]]; then
    ssh "$ROUTER_SSH" "rm -f $(shell_quote "$ROUTER_PCAP")" || true
  fi
fi

PCAP_SIZE="$(wc -c < "$PCAP_LOCAL" | tr -d ' ')"
if [[ "$PCAP_SIZE" -le 24 ]]; then
  echo "[pipeline] router capture pcap has no packets: $PCAP_LOCAL (${PCAP_SIZE} bytes)" >&2
  echo "[pipeline] check that the Kali scan ran before pressing Enter, router interface is correct, and capture filter matches the traffic." >&2
  exit 1
fi

echo "[pipeline] converting pcap to Zeek conn.log"
(cd "$ZEEK_DIR" && zeek -r "$ROOT_DIR/$PCAP_LOCAL")
CONN_LOG="$ZEEK_DIR/conn.log"
if [[ ! -f "$CONN_LOG" ]]; then
  echo "Zeek did not create conn.log: $CONN_LOG" >&2
  exit 1
fi

echo "[pipeline] converting Zeek conn.log to common features"
python convert_zeek_conn_to_common.py \
  --input "$CONN_LOG" \
  --output "$COMMON_CSV" \
  --dataset-name "$DATASET_NAME" \
  --label normal \
  --attack-type scanning \
  --scenario-id "$SCENARIO_ID" \
  --run-id "$RUN_ID" \
  --window-seconds "$WINDOW_SECONDS"

echo "[pipeline] adding low-and-slow rolling features"
python augment_low_slow_features.py \
  --input "$COMMON_CSV" \
  --output "$LOW_SLOW_CSV" \
  --schema-output "$RUN_FEATURE_SCHEMA" \
  --feature-list-output "$RUN_FEATURE_LIST" \
  --report-json "$RUN_AUGMENT_REPORT_JSON" \
  --report-md "$RUN_AUGMENT_REPORT_MD"

echo "[pipeline] running XGBoost inference"
python src/inference/xgboost_infer.py \
  --input "$LOW_SLOW_CSV" \
  --model models/xgboost_model_combined_10_common_split.joblib \
  --preprocessor models/xgboost_preprocessor_combined_10_common_split.joblib \
  --features models/combined_10_feature_list_common_split.json \
  --output "$XGB_PRED"

echo "[pipeline] running GRU inference"
python src/inference/gru_infer.py \
  --input "$LOW_SLOW_CSV" \
  --feature-schema configs/feature_schema_low_slow_v2.json \
  --model models/gru_model_combined_10_common_split.pt \
  --scaler models/gru_scaler_combined_10_common_split.joblib \
  --output "$GRU_PRED" \
  --allow-empty

echo "[pipeline] combining XGBoost and GRU predictions"
python src/inference/ensemble_infer.py \
  --xgboost-predictions "$XGB_PRED" \
  --gru-predictions "$GRU_PRED" \
  --xgboost-weight 0.5 \
  --gru-weight 0.5 \
  --threshold 0.5 \
  --include-xgboost-fallback \
  --output "$ENSEMBLE_JSON"

event_args=(
  python scripts/convert_ensemble_predictions_to_dashboard_events.py
  --ensemble "$ENSEMBLE_JSON"
  --features "$LOW_SLOW_CSV"
  --output "$DASHBOARD_EVENTS"
  --sensor-id "$SENSOR_ID"
  --window-seconds "$WINDOW_SECONDS"
)
if [[ -n "$SRC_IP" ]]; then
  event_args+=(--src-ip "$SRC_IP")
fi
if [[ -n "$TARGET_NETWORK" ]]; then
  event_args+=(--target-network "$TARGET_NETWORK")
fi
if [[ "$INCLUDE_RAW" == "1" ]]; then
  event_args+=(--include-raw)
fi

echo "[pipeline] converting ensemble output to dashboard events"
"${event_args[@]}"

echo "[pipeline] posting events to dashboard: $DASHBOARD_URL"
python scripts/send_dashboard_events.py \
  --url "$DASHBOARD_URL" \
  --input "$DASHBOARD_EVENTS" \
  --delay 0.1

echo "[pipeline] complete"
echo "[pipeline] run_dir=$RUN_DIR"
echo "[pipeline] dashboard_events=$DASHBOARD_EVENTS"
