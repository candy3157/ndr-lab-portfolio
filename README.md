# NDR Lab Portfolio

Real-time network detection lab for scan behavior in a segmented VM environment.

The project captures router traffic in chunks, converts packets to Zeek flow
logs, builds low-and-slow scan features, runs XGBoost and GRU inference, and
streams detection events to a lightweight dashboard.

## What Is Included

- `model/`: final model training, evaluation, feature engineering, and inference
  code from the research workspace.
- `runtime/`: VM runtime bundle for router capture, Zeek conversion, model
  inference, ensemble scoring, and dashboard event delivery.
- `dashboard/`: lightweight NDR dashboard with SQLite storage and server-sent
  updates.
- `lab-services/`: demo App/DB server and Ubuntu workload client used to create
  benign baseline traffic.
- `reports/`: selected model evaluation summaries suitable for portfolio review.

## What Is Not Included

The repository intentionally excludes raw datasets, packet captures, generated
SQLite databases, malware/binary samples, trained model artifacts, and local
runtime logs.

Excluded examples:

- `data/`, `datasets/`
- `*.pcap`, `*.sqlite3`, `*.exe`, archives
- `*.pt`, `*.joblib`
- real `config.json`, `.env`, local logs

Trained artifacts can be attached separately through GitHub Releases, Git LFS,
or a private artifact store. See `runtime/models/README.md`.

## Architecture

```text
Ubuntu workload client
  -> Debian file server
  -> App/DB server

Kali / test attacker
  -> Server zone

pfSense router
  -> tcpdump chunk capture
  -> Monitor VM runtime pipeline
  -> Zeek conn.log
  -> common 10-second window features
  -> low-and-slow rolling features
  -> XGBoost + GRU ensemble
  -> Dashboard API
```

## Runtime Demo Flow

Start the dashboard:

```bash
cd dashboard
cp config.example.json config.json
python3 -m dashboard_server.app -c config.json
```

Start the normal workload client on the client VM:

```bash
cd lab-services/ubuntu-workload-client
cp config.example.json config.json
./scripts/install_client.sh
ubuntu-workload-client -c config.json loop
```

Run the real-time monitor pipeline after placing trained artifacts under
`runtime/models/`:

```bash
cd runtime

./scripts/run_realtime_router_pipeline.sh \
  --router-ssh ndr-router \
  --router-interface em2 \
  --capture-filter "(host 10.10.10.10 or host 10.10.90.10) and net 10.10.20.0/24" \
  --dynamic-src-ip \
  --target-network "10.10.20.0/24" \
  --dashboard-url "http://127.0.0.1:8000" \
  --chunk-seconds 60 \
  --window-seconds 10 \
  --include-raw
```

## Model Summary

The final runtime path uses:

- XGBoost for fast window-level fallback detection.
- GRU sequence inference once enough history exists.
- Ensemble scoring to combine XGBoost and GRU outputs.
- Dashboard event conversion with dynamic source IP handling.

Selected evaluation summaries are in `reports/`, especially:

- `reports/combined_10_model_comparison.md`
- `reports/xgboost_metrics_combined_10_ndr.md`
- `reports/low_slow_feature_evaluation_report.md`

## Repository Status

This is a portfolio/public-code version of the project. It is structured to
show implementation quality and reproducible runtime flow without publishing raw
traffic data or trained artifacts directly in the repository.
