# Dataset Preparation

## Expected Layout

```text
../datasets/cse-cic-ids2018/archive.zip
../datasets/UQ-iot-ids-dataset-2021/69897e94e24170c0_UQIOT2022_A7369.zip
../ipcam-backdoor-test-environment/data/features/datasets/seq10s-24h-scan-subtype-10s.csv
```

## Profiling and Common Schema

Run a bounded smoke profile first. The CSE CSV zip is large, so the default path reads chunks instead of full-loading all CSVs.

```bash
python profile_public_datasets.py --max-cse-rows 12000 --max-simulation-rows 12000
```

Outputs:

- `reports/dataset_profile.md`
- `reports/dataset_profile.json`
- `configs/feature_schema.json`
- `configs/dataset_mapping.json`
- `data/processed/common_ndr_features_smoke.csv`

## Schema Rules

- Keep `dataset_name`, `data_source`, `is_synthetic`, `label`, and `attack_type`.
- Normalize `label` to `normal` or `attack`.
- Exclude raw `src_ip` and `dst_ip` from model inputs.
- Raw ports may be bucketed into behavior features such as well-known, registered, or ephemeral port ratios.
- Use behavior features such as connection count, unique destination count, failed ratio, duration, bytes, packets, protocol ratios, and entropy.

## UQ-IoT-IDS2021

The UQ dataset in this workspace is PCAP-based. It is profiled as a manifest in the smoke run. To train on it, first extract flow/window features with Zeek or tshark, then map those rows into `ndr_common_v1`.

Example Docker Zeek command pattern:

```bash
docker run --rm -v "$PWD:/work" zeek/zeek:latest zeek -r /work/path/to/input.pcap LogAscii::use_json=T
```

After extraction, convert `conn.log` windows to the common schema before training.

```bash
python convert_zeek_conn_to_common.py \
  --input path/to/conn.log \
  --output data/processed/uq_iot_common_windows.csv \
  --dataset-name UQ-IoT-IDS2021 \
  --label attack \
  --attack-type "Port Scan" \
  --window-seconds 10
```

## CTU-13

CTU-13 is botnet/C2-centric cross-domain data. Use it for GRU sequence challenger benchmark/pretraining only. Do not merge CTU-13 metrics into IPCAM simulation operating-performance claims.

Current local path:

```text
data/CTU-13/CTU-13-Dataset/*/*.binetflow
```

The converter uses `.binetflow` flow labels, aggregates them into 10 second windows, and preserves `dataset_name`, `data_source`, `is_synthetic`, `label`, `attack_type`, `scenario_id`, `run_id`, `session_id`, `src_entity`, and window timestamps. `SrcAddr` and `DstAddr` are used only for grouping and unique-count aggregation; raw IPs are not model input features.

Smoke conversion:

```bash
python convert_ctu13_to_common.py \
  --max-rows-per-file 200000 \
  --output data/processed/ctu13_common_10s_smoke.csv \
  --report-json reports/ctu13_conversion_report.json \
  --report-md reports/ctu13_conversion_report.md

python diagnose_common_data_sufficiency.py \
  --input data/processed/ctu13_common_10s_smoke.csv \
  --output-json reports/data_sufficiency_ctu13_smoke.json \
  --output-md reports/data_sufficiency_ctu13_smoke.md
```

Full conversion, if RAM and runtime budget allow:

```bash
python convert_ctu13_to_common.py \
  --max-rows-per-file 0 \
  --output data/processed/ctu13_common_10s_full.csv \
  --report-json reports/ctu13_conversion_full_report.json \
  --report-md reports/ctu13_conversion_full_report.md
```

Default label policy:

- `Botnet`, `C&C`, `-CC` labels -> `attack`
- `Normal` labels -> `normal`
- `Background` labels -> excluded by default

For robustness experiments only, background can be mapped to normal:

```bash
python convert_ctu13_to_common.py --background-policy normal
```
