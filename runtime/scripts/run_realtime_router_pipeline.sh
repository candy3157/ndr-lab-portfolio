#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_ROOT="data/realtime-runs"
ROUTER_SSH="root@10.10.99.1"
ROUTER_INTERFACE="em2"
ROUTER_PCAP_DIR="/tmp"
ROUTER_TCPDUMP_PREFIX=""
CAPTURE_FILTER="(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24"
DASHBOARD_URL="http://127.0.0.1:8000"
SENSOR_ID="sensor-01"
DATASET_NAME="vm-lab-realtime"
SCENARIO_ID="vm-lab-realtime"
WINDOW_SECONDS="10"
CHUNK_SECONDS="60"
SRC_IP=""
TARGET_NETWORK="10.10.20.0/24"
INCLUDE_RAW="0"
KEEP_REMOTE_PCAP="0"
MAX_CHUNKS="0"
SEND_DELAY="0.02"
CAPTURE_PID=""
SENT_COUNT="0"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_realtime_router_pipeline.sh

Default realtime lab settings:
  router SSH:        root@10.10.99.1
  router interface:  em2
  capture filter:    (host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24
  chunk seconds:     60
  dashboard URL:     http://127.0.0.1:8000
  target network:    10.10.20.0/24
  server zone hosts: app/db 10.10.20.10, IoT 10.10.20.20-24, Debian 10.10.20.30

Useful overrides:
  --router-interface em2
  --capture-filter "(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24"
  --chunk-seconds 60
  --window-seconds 10
  --dashboard-url http://127.0.0.1:8000
  --dynamic-src-ip
  --target-network 10.10.20.0/24
  --include-raw
  --max-chunks 30

The script runs until Ctrl+C unless --max-chunks is set.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --work-root) WORK_ROOT="$2"; shift 2 ;;
    --router-ssh) ROUTER_SSH="$2"; shift 2 ;;
    --router-interface) ROUTER_INTERFACE="$2"; shift 2 ;;
    --router-pcap-dir) ROUTER_PCAP_DIR="$2"; shift 2 ;;
    --router-tcpdump-prefix) ROUTER_TCPDUMP_PREFIX="$2"; shift 2 ;;
    --capture-filter) CAPTURE_FILTER="$2"; shift 2 ;;
    --dashboard-url) DASHBOARD_URL="$2"; shift 2 ;;
    --sensor-id) SENSOR_ID="$2"; shift 2 ;;
    --dataset-name) DATASET_NAME="$2"; shift 2 ;;
    --scenario-id) SCENARIO_ID="$2"; shift 2 ;;
    --window-seconds) WINDOW_SECONDS="$2"; shift 2 ;;
    --chunk-seconds) CHUNK_SECONDS="$2"; shift 2 ;;
    --src-ip) SRC_IP="$2"; shift 2 ;;
    --dynamic-src-ip) SRC_IP=""; shift ;;
    --target-network) TARGET_NETWORK="$2"; shift 2 ;;
    --include-raw) INCLUDE_RAW="1"; shift ;;
    --keep-remote-pcap) KEEP_REMOTE_PCAP="1"; shift ;;
    --max-chunks) MAX_CHUNKS="$2"; shift 2 ;;
    --send-delay) SEND_DELAY="$2"; shift 2 ;;
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
  if [[ -n "$CAPTURE_PID" ]]; then
    echo "[realtime] stopping router tcpdump pid=$CAPTURE_PID"
    ssh "$ROUTER_SSH" "kill -INT $CAPTURE_PID >/dev/null 2>&1 || true; sleep 2" || true
    CAPTURE_PID=""
  fi
}

cleanup() {
  stop_router_capture
}
trap cleanup EXIT

json_length() {
  python -c 'import json, sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' "$1"
}

append_csv() {
  local source_csv="$1"
  local target_csv="$2"
  if [[ ! -s "$source_csv" ]]; then
    return
  fi
  if [[ ! -s "$target_csv" ]]; then
    cp "$source_csv" "$target_csv"
  else
    tail -n +2 "$source_csv" >> "$target_csv"
  fi
}

has_zeek_rows() {
  local conn_log="$1"
  grep -qvE '^(#|[[:space:]]*$)' "$conn_log"
}

require_command python
require_command ssh
require_command scp
require_command zeek
require_command grep

RUN_DIR="$WORK_ROOT/$RUN_ID"
PCAP_DIR="$RUN_DIR/pcap"
ZEEK_ROOT="$RUN_DIR/zeek"
CHUNK_COMMON_DIR="$RUN_DIR/common"
CUMULATIVE_COMMON="data/processed/${RUN_ID}_realtime_common.csv"
LOW_SLOW_CSV="data/processed/${RUN_ID}_realtime_low_slow_features.csv"
RUN_FEATURE_SCHEMA="$RUN_DIR/feature_schema_low_slow_v2.json"
RUN_FEATURE_LIST="$RUN_DIR/feature_list_common_split.json"
RUN_AUGMENT_REPORT_JSON="$RUN_DIR/low_slow_feature_augmentation_report.json"
RUN_AUGMENT_REPORT_MD="$RUN_DIR/low_slow_feature_augmentation_report.md"
XGB_PRED="data/predictions/${RUN_ID}_realtime_xgboost_predictions.json"
GRU_PRED="data/predictions/${RUN_ID}_realtime_gru_predictions.json"
ENSEMBLE_JSON="reports/${RUN_ID}_realtime_ensemble_predictions.json"
DASHBOARD_EVENTS="reports/${RUN_ID}_realtime_dashboard_events.json"

mkdir -p "$PCAP_DIR" "$ZEEK_ROOT" "$CHUNK_COMMON_DIR" data/processed data/predictions reports

echo "[realtime] run_id=$RUN_ID"
echo "[realtime] router=$ROUTER_SSH interface=$ROUTER_INTERFACE chunk_seconds=$CHUNK_SECONDS"
echo "[realtime] dashboard=$DASHBOARD_URL"
echo "[realtime] press Ctrl+C to stop"

CHUNK_INDEX="0"
while true; do
  if [[ "$MAX_CHUNKS" != "0" && "$CHUNK_INDEX" -ge "$MAX_CHUNKS" ]]; then
    echo "[realtime] reached max chunks: $MAX_CHUNKS"
    break
  fi

  printf -v CHUNK_ID "%06d" "$CHUNK_INDEX"
  REMOTE_PCAP="${ROUTER_PCAP_DIR%/}/ndr-live-${RUN_ID}-${CHUNK_ID}.pcap"
  REMOTE_LOG="${ROUTER_PCAP_DIR%/}/ndr-live-${RUN_ID}-${CHUNK_ID}.log"
  LOCAL_PCAP="$PCAP_DIR/chunk-${CHUNK_ID}.pcap"
  ZEEK_DIR="$ZEEK_ROOT/chunk-${CHUNK_ID}"
  CHUNK_COMMON="$CHUNK_COMMON_DIR/chunk-${CHUNK_ID}_common.csv"

  router_pcap_q="$(shell_quote "$REMOTE_PCAP")"
  router_iface_q="$(shell_quote "$ROUTER_INTERFACE")"
  router_log_q="$(shell_quote "$REMOTE_LOG")"
  filter_clause=""
  if [[ -n "$CAPTURE_FILTER" ]]; then
    filter_clause=" $(shell_quote "$CAPTURE_FILTER")"
  fi
  capture_cmd="rm -f $router_pcap_q; nohup $ROUTER_TCPDUMP_PREFIX tcpdump -U -i $router_iface_q -w $router_pcap_q$filter_clause >$router_log_q 2>&1 & echo \$!"

  echo "[realtime] chunk=$CHUNK_ID starting router capture"
  CAPTURE_PID="$(ssh "$ROUTER_SSH" "$capture_cmd" | tail -n 1 | tr -d '\r')"
  sleep "$CHUNK_SECONDS"
  stop_router_capture

  echo "[realtime] chunk=$CHUNK_ID copying pcap"
  scp "$ROUTER_SSH:$REMOTE_PCAP" "$LOCAL_PCAP"
  if [[ "$KEEP_REMOTE_PCAP" != "1" ]]; then
    ssh "$ROUTER_SSH" "rm -f $(shell_quote "$REMOTE_PCAP") $(shell_quote "$REMOTE_LOG")" || true
  fi

  PCAP_SIZE="$(wc -c < "$LOCAL_PCAP" | tr -d ' ')"
  if [[ "$PCAP_SIZE" -le 24 ]]; then
    echo "[realtime] chunk=$CHUNK_ID has no packets; skipping"
    CHUNK_INDEX="$((CHUNK_INDEX + 1))"
    continue
  fi

  echo "[realtime] chunk=$CHUNK_ID converting pcap to Zeek"
  mkdir -p "$ZEEK_DIR"
  (cd "$ZEEK_DIR" && zeek -r "$ROOT_DIR/$LOCAL_PCAP")
  CONN_LOG="$ZEEK_DIR/conn.log"
  if [[ ! -f "$CONN_LOG" ]]; then
    echo "[realtime] chunk=$CHUNK_ID has no Zeek conn.log; skipping"
    CHUNK_INDEX="$((CHUNK_INDEX + 1))"
    continue
  fi
  if ! has_zeek_rows "$CONN_LOG"; then
    echo "[realtime] chunk=$CHUNK_ID has no Zeek connection rows; skipping"
    CHUNK_INDEX="$((CHUNK_INDEX + 1))"
    continue
  fi

  echo "[realtime] chunk=$CHUNK_ID creating common features"
  python convert_zeek_conn_to_common.py \
    --input "$CONN_LOG" \
    --output "$CHUNK_COMMON" \
    --dataset-name "$DATASET_NAME" \
    --label normal \
    --attack-type scanning \
    --scenario-id "$SCENARIO_ID" \
    --run-id "$RUN_ID" \
    --window-seconds "$WINDOW_SECONDS"

  append_csv "$CHUNK_COMMON" "$CUMULATIVE_COMMON"

  echo "[realtime] chunk=$CHUNK_ID updating rolling features"
  python augment_low_slow_features.py \
    --input "$CUMULATIVE_COMMON" \
    --output "$LOW_SLOW_CSV" \
    --schema-output "$RUN_FEATURE_SCHEMA" \
    --feature-list-output "$RUN_FEATURE_LIST" \
    --report-json "$RUN_AUGMENT_REPORT_JSON" \
    --report-md "$RUN_AUGMENT_REPORT_MD"

  echo "[realtime] chunk=$CHUNK_ID running XGBoost"
  python src/inference/xgboost_infer.py \
    --input "$LOW_SLOW_CSV" \
    --model models/xgboost_model_combined_10_common_split.joblib \
    --preprocessor models/xgboost_preprocessor_combined_10_common_split.joblib \
    --features models/combined_10_feature_list_common_split.json \
    --output "$XGB_PRED"

  echo "[realtime] chunk=$CHUNK_ID running GRU"
  python src/inference/gru_infer.py \
    --input "$LOW_SLOW_CSV" \
    --feature-schema configs/feature_schema_low_slow_v2.json \
    --model models/gru_model_combined_10_common_split.pt \
    --scaler models/gru_scaler_combined_10_common_split.joblib \
    --output "$GRU_PRED" \
    --allow-empty

  echo "[realtime] chunk=$CHUNK_ID combining predictions"
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

  echo "[realtime] chunk=$CHUNK_ID converting dashboard events"
  "${event_args[@]}"

  TOTAL_EVENTS="$(json_length "$DASHBOARD_EVENTS")"
  if [[ "$TOTAL_EVENTS" -gt "$SENT_COUNT" ]]; then
    echo "[realtime] chunk=$CHUNK_ID sending events $SENT_COUNT..$((TOTAL_EVENTS - 1))"
    python scripts/send_dashboard_events.py \
      --url "$DASHBOARD_URL" \
      --input "$DASHBOARD_EVENTS" \
      --start-index "$SENT_COUNT" \
      --delay "$SEND_DELAY"
    SENT_COUNT="$TOTAL_EVENTS"
  else
    echo "[realtime] chunk=$CHUNK_ID no new dashboard events"
  fi

  CHUNK_INDEX="$((CHUNK_INDEX + 1))"
done

echo "[realtime] stopped"
echo "[realtime] run_dir=$RUN_DIR"
echo "[realtime] dashboard_events=$DASHBOARD_EVENTS"
