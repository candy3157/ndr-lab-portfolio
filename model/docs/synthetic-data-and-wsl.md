# Synthetic Data And WSL Setup

이 문서는 `ndr-ml`의 시뮬레이션 데이터 부족 진단, 합성 데이터 생성, 데이터 출처별 평가, WSL 의존성 점검 절차를 정리한다.

## 현재 데이터 진단 결과

실행 명령:

```bash
python3 diagnose_data_sufficiency.py \
  --input ipcam-scan-subtype-60s-train.csv \
  --input ipcam-scan-subtype-60s-test.csv \
  --train ipcam-scan-subtype-60s-train.csv \
  --test ipcam-scan-subtype-60s-test.csv \
  --output-json models/data_sufficiency_report.json \
  --output-md models/data_sufficiency_report.md
```

생성된 리포트:

```text
models/data_sufficiency_report.json
models/data_sufficiency_report.md
```

2026-05-29 현재 진단 기준으로 전체 샘플은 1,071개이고 라벨 분포는 normal 874개, scanning 197개다. train/test 사이 run_id 중복은 없지만 `low-and-slow`, `udp-scan`, `service-probe` 같은 일부 scenario와 run의 샘플 수가 기본 기준인 30개보다 적어 데이터 부족으로 판정된다.

진단 스크립트는 다음 항목을 확인한다.

- 전체 샘플 수
- normal/scanning 라벨 비율
- `scenario_id`, `run_id`, `technique_id` 계열 메타데이터 컬럼 존재 여부
- `scenario_id`, `run_id`, `technique_id`별 샘플 수
- train/validation/test split별 라벨 분포
- 특정 run 또는 scenario에 대한 과도한 의존도
- split 간 `run_id` 중복에 따른 데이터 누수 가능성
- 원시 `src_ip`, `dst_ip` 컬럼 존재 여부
- 모델 학습 최소 기준 충족 여부

기본 최소 기준은 CLI 옵션으로 조정할 수 있다.

```bash
python3 diagnose_data_sufficiency.py \
  --input data.csv \
  --min-total 1000 \
  --min-per-label 100 \
  --min-per-scenario 30 \
  --min-per-run 30 \
  --max-run-share 0.40 \
  --max-scenario-share 0.50
```

`run_id`, `scenario_id`, `technique_id`가 없는 탐색용 flow-level 데이터는 행 수가 많아도 운영 일반화와 split 누수 검증이 불가능하므로 기본적으로 부족 판정한다. 비운영 탐색 목적으로만 볼 때는 `--allow-missing-group-metadata`를 명시한다.

대용량 flow-level 데이터 진단 결과:

```text
models/flow_level_data_sufficiency_report.md
```

`data/processed/normal_scanning_features.csv`는 62,040행이지만 `scenario_id`, `run_id`, `technique_id`가 없어 운영 readiness 근거로 쓰지 않는다.

## 합성 데이터 생성

합성 데이터는 실제 수집 train 데이터의 컬럼명, 값 범위, 라벨별 수치 분포를 읽어 같은 CSV 스키마로 생성한다. 원시 IP는 생성하지 않고, `flow_count`, `unique_dst_count`, `unique_dst_port_count`, `failed_conn_ratio`, duration, bytes, packets, entropy 계열의 행위 기반 feature만 변형한다.

실행 명령:

```bash
python3 generate_synthetic_data.py \
  --input ipcam-scan-subtype-60s-train.csv \
  --output data/synthetic/ipcam-scan-subtype-60s-synthetic-train.csv \
  --combined-output data/synthetic/ipcam-scan-subtype-60s-real-plus-synthetic-train.csv \
  --ground-truth-output data/synthetic/ipcam-scan-subtype-60s-synthetic-ground-truth.jsonl \
  --report-json models/synthetic_data_report.json \
  --report-md models/synthetic_data_report.md \
  --config synthetic_data_config.example.json \
  --target-total 1200 \
  --min-per-label 400
```

생성된 산출물:

```text
data/synthetic/ipcam-scan-subtype-60s-synthetic-train.csv
data/synthetic/ipcam-scan-subtype-60s-real-plus-synthetic-train.csv
data/synthetic/ipcam-scan-subtype-60s-synthetic-ground-truth.jsonl
models/synthetic_data_report.json
models/synthetic_data_report.md
```

생성된 합성 데이터에는 `is_synthetic=true`, `data_source=synthetic`이 추가된다. combined 파일의 실제 데이터에는 `is_synthetic=false`, `data_source=real`이 추가된다. `--ground-truth-output`을 지정하면 synthetic window와 같은 `window_start`, `window_end`, `scenario_id`, `run_id`, `label`, `phase`, `technique_id`를 가진 JSONL ground-truth 이벤트도 생성한다.

합성 데이터 생성 파라미터는 `synthetic_data_config.example.json` 또는 CLI 옵션으로 조절한다.

주요 파라미터:

- `target_total`: 실제+합성 train 목표 행 수
- `min_per_label`: label별 최소 목표 행 수
- `synthetic_runs_per_label`: 합성 run 분산 개수
- `jitter_ratio`: 실제 수치 feature 주변 변동 폭
- `respect_observed_ranges`: 실제 관찰 범위를 넘지 않도록 clamp
- `attack_profiles`: `low_and_slow_scan`, `vertical_scan`, `horizontal_scan`, `service_probe`, `udp_scan`

생성 결과 검증:

```bash
python3 validate_synthetic_data.py \
  --real ipcam-scan-subtype-60s-train.csv \
  --synthetic data/synthetic/ipcam-scan-subtype-60s-synthetic-train.csv \
  --combined data/synthetic/ipcam-scan-subtype-60s-real-plus-synthetic-train.csv \
  --ground-truth data/synthetic/ipcam-scan-subtype-60s-synthetic-ground-truth.jsonl \
  --output-json models/synthetic_data_validation.json \
  --output-md models/synthetic_data_validation.md
```

검증 항목:

- 합성 CSV가 실제 CSV 스키마에 `is_synthetic`, `data_source`만 추가했는지
- synthetic rows와 combined rows의 source flag가 맞는지
- 합성 numeric feature가 실제 관찰 min/max 범위를 벗어나지 않는지
- 원시 IP 컬럼이 합성 row에 채워지지 않았는지
- synthetic ground-truth JSONL 행 수와 필수 키가 맞는지

## 평가 분리

합성 데이터는 train 보강과 파이프라인 검증용이다. 최종 성능 평가는 real-only test를 기준으로 보고해야 하며, synthetic-test를 사용한다면 반드시 별도 항목으로 분리한다.

실행 예시:

```bash
python3 train_eval_xgb_sources.py \
  --real-train ipcam-scan-subtype-60s-train.csv \
  --real-test ipcam-scan-subtype-60s-test.csv \
  --synthetic-train data/synthetic/ipcam-scan-subtype-60s-synthetic-train.csv \
  --mode real-only \
  --mode synthetic-only \
  --mode real+synthetic \
  --output-dir models/source_evaluations
```

출력:

```text
models/source_evaluations/source_evaluation_report.json
models/source_evaluations/source_evaluation_report.md
models/source_evaluations/<mode>/metrics_real-test.json
models/source_evaluations/<mode>/predictions_real-test.csv
```

2026-05-30 재실행 결과, `.venv-wsl`에 ML 패키지를 설치한 뒤 source-separated 평가가 정상 생성됐다.

| mode | test set | precision | recall | F1 | ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| real-only | real-test | 1.0000 | 0.2075 | 0.3438 | 0.8625 |
| synthetic-only | real-test | 1.0000 | 0.0755 | 0.1404 | 0.6485 |
| real+synthetic | real-test | 1.0000 | 0.3208 | 0.4857 | 0.8892 |

`real+synthetic`은 이 데이터셋에서 recall/F1을 올렸지만, 성능 주장은 실제 test 기준으로만 제한한다. 합성 데이터 보강으로 개선된 수치는 운영 성능 보장으로 해석하지 않는다.

## Run 분리 실제 데이터 교차검증

기존 holdout은 train/test 행 수가 작기 때문에, 전체 실제 60초 window 데이터를 `run_id` 기준으로 분리한 real-only 교차검증도 생성한다.

실행 명령:

```bash
python3 train_eval_xgb_group_cv.py \
  --input ipcam-scan-subtype-60s-train.csv \
  --input ipcam-scan-subtype-60s-test.csv \
  --output-dir models/group_cv_evaluation \
  --group-column run_id \
  --n-splits 5 \
  --threshold 0.8 \
  --feature-names models/feature_names_v3_holdout.json \
  --final-model
```

출력:

```text
models/group_cv_evaluation/group_cv_report.json
models/group_cv_evaluation/group_cv_report.md
models/group_cv_evaluation/group_cv_predictions.csv
models/group_cv_evaluation/group_cv_threshold_sweep.csv
```

2026-05-30 현재 결과:

| 평가 | rows | precision | recall | F1 | ROC-AUC |
| --- | --- | --- | --- | --- | --- |
| run_id group CV out-of-fold, bundle 22-feature schema | 1,071 | 0.7451 | 0.5787 | 0.6514 | 0.8737 |

이 평가는 train/test 간 `run_id` 중복이 없고 raw IP feature도 없다. `--feature-names`로 현재 번들 모델의 22개 feature schema와 평가 schema도 맞춘다. 데이터 볼륨은 운영 증거로 충분한 크기에 가까워졌지만, precision/recall/F1/ROC-AUC가 운영 게이트에 미달한다. 따라서 현재 모델은 lab integration 후보로만 유지하며, 운영 ready로 표시하지 않는다.

## Docker Lab Smoke 수집 검증

WSL 환경에서 host Zeek 대신 Docker Zeek으로 실제 수집 파이프라인을 검증했다.

실행한 smoke 명령:

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/collect_bulk_scan_dataset.py \
  --skip-existing \
  --skip-pull \
  --run-prefix smoke \
  --scenario-log-root data/scenarios/generated \
  --baseline-repeats 1 \
  --attack-repeats 1 \
  --baseline-seconds 180 \
  --scenario baseline \
  --scenario vertical-scan \
  --scenario horizontal-scan \
  --scenario service-probe \
  --scenario udp-scan
```

초기 실행에서는 `data/scenarios/events.jsonl`가 컨테이너 사용자(`nobody:nogroup`) 소유로 생성되어 host Python이 append하지 못했다. 이를 피하기 위해 bulk collector가 기본적으로 `data/scenarios/generated` 아래에 scenario event와 ground-truth를 기록하도록 수정했다.

검증 결과:

```text
data/pcap/smoke-*.pcap
data/zeek/smoke-*/conn.log
data/features/windowed/smoke-*-60s.csv
data/features/datasets/ipcam-scan-subtype-60s.csv
```

생성된 smoke dataset은 27개 window이며 normal 18개, scanning 9개다. 이 데이터는 너무 작아서 성능 주장에 쓰지 않고, 수집/변환/feature 생성/번들 추론 통합 확인용으로만 사용한다.

Smoke 추론 리포트:

```text
models/smoke_data_sufficiency_report.md
models/smoke_prediction_report.md
models/smoke_predictions_lab_bundle.csv
models/smoke_predictions_groupcv_bundle.csv
```

Docker Desktop WSL integration 복구 후 짧은 host-capture 검증도 실행했다. 초기 `docker-verify`는 nmap 결과에는 TCP 스캔이 있었지만 pcap/Zeek에는 UDP와 DNS만 남아 최종 dataset이 normal-only가 됐다. 원인은 WSL/Docker Desktop에서 tcpdump sidecar를 `camera-app` 네임스페이스에 붙인 방식이 nmap TCP 흐름을 놓친 것이다. 이후 collector 기본값을 Docker host-mode tcpdump로 변경했고, nmap은 계속 `camera-app` 네임스페이스에서 실행해 source IP 의미를 유지한다. 또한 기본 capture filter를 `tcp or (udp and not port 8000 and not port 8001)`로 바꿔 고용량 MediaMTX RTP/RTCP UDP가 짧은 nmap control burst를 가리지 않게 했다.

검증 명령:

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/collect_bulk_scan_dataset.py \
  --skip-pull \
  --skip-existing \
  --run-prefix verify-hostcap-fast-v3 \
  --scenario-log-root data/scenarios/verify-hostcap-fast-v3 \
  --attack-repeats 1 \
  --scenario vertical-scan \
  --scenario horizontal-scan \
  --scenario service-probe \
  --scenario udp-scan \
  --capture-network-mode host \
  --dataset-output data/features/datasets/verify-hostcap-fast-v3-scan-subtype-60s.csv
```

이 검증은 Docker Compose, host-mode tcpdump sidecar, Docker Zeek, window feature build, ground-truth label merge가 실제로 이어지는지만 확인한다. 생성 row는 10개뿐이라 운영 성능 근거로 쓰지 않는다. 다만 검증 summary에는 `vertical_scan`, `horizontal_scan`, `service_probe`, `udp_scan`이 모두 포함되어 ground-truth와 Zeek flow가 fast scan subtype 전체에서 정상 결합되는 것을 확인했다.

```text
../ipcam-backdoor-test-environment/data/pcap/verify-hostcap-fast-v3-*.pcap
../ipcam-backdoor-test-environment/data/zeek/verify-hostcap-fast-v3-*/conn.log
../ipcam-backdoor-test-environment/data/features/windowed/verify-hostcap-fast-v3-*-60s.csv
../ipcam-backdoor-test-environment/data/features/datasets/verify-hostcap-fast-v3-scan-subtype-60s.csv
../ipcam-backdoor-test-environment/data/features/datasets/verify-hostcap-fast-v3-collection-summary.json
models/docker_hostcap_fast_v3_data_sufficiency_report.md
```

반복 capture 경로도 2분짜리 mini-long 수집으로 확인했다. 이 검증은 운영 성능 근거가 아니라, 20분짜리 본 수집에서 쓰는 `--repeat-until-seconds`, `--repeat-interval-seconds`, host capture, Docker Zeek 변환, multi-window 라벨링이 함께 동작하는지 확인하기 위한 것이다.

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/collect_bulk_scan_dataset.py \
  --skip-pull \
  --skip-existing \
  --run-prefix mini-long-v1 \
  --scenario-log-root data/scenarios/mini-long-v1 \
  --scenario baseline \
  --scenario vertical-scan \
  --scenario horizontal-scan \
  --scenario service-probe \
  --scenario udp-scan \
  --baseline-repeats 1 \
  --attack-repeats 1 \
  --baseline-seconds 120 \
  --attack-duration-seconds 120 \
  --attack-interval-seconds 20 \
  --capture-network-mode host \
  --long-capture-scenario vertical-scan \
  --long-capture-scenario horizontal-scan \
  --long-capture-scenario service-probe \
  --long-capture-scenario udp-scan \
  --dataset-output data/features/datasets/mini-long-v1-scan-subtype-60s.csv
```

결과는 33개 window, normal 17개, scanning 16개였고 `vertical_scan`, `horizontal_scan`, `service_probe`, `udp_scan`이 모두 포함됐다. 진단 리포트는 `models/mini_long_v1_data_sufficiency_report.md`에 저장했다.

Docker가 복구된 뒤 운영 readiness 근거를 만들려면 smoke 대신 긴 bulk 수집을 실행한다. 이 명령은 60초 window 기준으로 최소 500개 train window와 200개 test window를 목표로 하고, test split은 `run_id` 기준으로 분리한다.

먼저 Docker 없이도 실행 가능한 estimate를 만든다.

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/collect_bulk_scan_dataset.py \
  --estimate-only \
  --run-prefix bulk \
  --scenario-log-root data/scenarios/generated \
  --baseline-repeats 8 \
  --attack-repeats 8 \
  --baseline-seconds 1200 \
  --attack-duration-seconds 1200 \
  --attack-interval-seconds 20 \
  --capture-network-mode host \
  --long-capture-scenario vertical-scan \
  --long-capture-scenario horizontal-scan \
  --long-capture-scenario service-probe \
  --long-capture-scenario udp-scan \
  --test-repeat 7 \
  --test-repeat 8
```

현재 estimate 산출물은 다음 경로에 생성되며, 780 train window와 260 test window로 500/200 운영 볼륨 게이트를 통과하는 계획이다. 예상 순차 실행 시간은 약 17.3시간이다.

```text
../ipcam-backdoor-test-environment/data/features/datasets/bulk-collection-plan.json
../ipcam-backdoor-test-environment/data/features/datasets/bulk-collection-plan.md
```

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/collect_bulk_scan_dataset.py \
  --compose-up \
  --skip-existing \
  --run-prefix bulk \
  --scenario-log-root data/scenarios/generated \
  --baseline-repeats 8 \
  --attack-repeats 8 \
  --baseline-seconds 1200 \
  --attack-duration-seconds 1200 \
  --attack-interval-seconds 20 \
  --capture-network-mode host \
  --long-capture-scenario vertical-scan \
  --long-capture-scenario horizontal-scan \
  --long-capture-scenario service-probe \
  --long-capture-scenario udp-scan \
  --test-repeat 7 \
  --test-repeat 8
```

`low-and-slow`는 이 명령에 포함되지만 긴 반복 캡처 대상에는 넣지 않는다. 해당 nmap profile 자체가 `--scan-delay 60s`를 사용하므로 한 번의 scan도 긴 window를 만든다. 짧은 pilot 수집은 파이프라인 검증용이며 운영 성능 근거로 쓰지 않는다.

수집이 완료되어 `ipcam-scan-subtype-60s.csv`, `ipcam-scan-subtype-60s-train.csv`, `ipcam-scan-subtype-60s-test.csv`가 생성되면 `ndr-ml`에서 후속 readiness 파이프라인을 실행한다. 이 스크립트는 데이터 진단, 합성 데이터 재생성/검증, real-only/synthetic-only/real+synthetic 평가, run-group CV, final model export, 감사 리포트 생성을 순서대로 실행한다.

```bash
cd ../ndr-ml
.venv-wsl/bin/python run_operational_readiness_pipeline.py \
  --solution-root ../ipcam-backdoor-test-environment
```

명령 계획만 확인하려면:

```bash
.venv-wsl/bin/python run_operational_readiness_pipeline.py \
  --solution-root ../ipcam-backdoor-test-environment \
  --dry-run
```

파이프라인 실행 리포트:

```text
models/operational_readiness_pipeline_report.json
models/operational_readiness_pipeline_report.md
```

주의 사항:

- `real-only`: 실제 train으로 학습하고 실제 test로 평가한다.
- `synthetic-only`: 합성 train으로 학습하고 실제 test로 평가한다. 운영 성능 근거로 단독 사용하지 않는다.
- `real+synthetic`: 실제+합성 train으로 학습하고 실제 test로 평가한다.
- synthetic-test를 추가할 경우 `--synthetic-test`로 넣고, 리포트에서 synthetic-test 항목을 real-test와 분리해 본다.
- `src_ip`, `dst_ip`, `src_entity`, `scenario_id`, `run_id`, `technique_id`, `data_source`, `is_synthetic`은 모델 입력 피처에서 제외된다.

## NDR 모델 번들

현재 운영 후보는 multi-class subtype 모델이 아니라 binary scan detector다. subtype 모델은 일부 scan subtype recall이 낮아 운영 판정에 쓰지 않는다.

최신 운영 후보는 `targeted-op20s-v1-scan-subtype-20s.csv` real dataset으로 만든다. 이 dataset은 20초 window 1,025개, normal 645개, scanning 380개이며, train/test는 `run_id` 기준으로 분리된다. labeler는 ground-truth의 `source`/`target` alias를 Zeek flow의 실제 endpoint IP로 해석한 뒤 라벨을 붙인다. 이 보정은 정상 source flow가 같은 port/proto/time window에 있었다는 이유만으로 scanning 라벨을 받는 오염을 막기 위한 것이다. raw IP는 모델 피처나 alert 출력에 포함하지 않는다.

최신 bundle readiness는 통과 상태다. real-only holdout은 366개 실제 test window에서 precision 1.0000, recall 1.0000, F1 1.0000, ROC-AUC 1.0000이다. run-group CV는 70개 run, 1,025개 실제 window out-of-fold 기준 precision 1.0000, recall 0.9947, F1 0.9974, ROC-AUC 0.99999다. 이 수치는 시뮬레이션 lab의 정제된 real dataset 기준이며, 운영망 성능을 보장하지 않는다.

번들 생성:

```bash
python3 export_ndr_model_bundle.py \
  --output-dir ../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml
```

추가 bulk 수집 후 운영 후보를 갱신할 때는 run-group CV가 만든 final model을 export한다. 이렇게 해야 readiness 리포트의 group-separated real-only 평가와 실제 번들 모델이 같은 feature schema와 학습 산출물을 사용한다.

```bash
.venv-wsl/bin/python export_ndr_model_bundle.py \
  --model-json models/group_cv_evaluation/final_model.json \
  --model-pkl models/group_cv_evaluation/final_model.pkl \
  --feature-names models/group_cv_evaluation/final_feature_names.json \
  --metrics models/group_cv_evaluation/final_model_metrics.json \
  --output-dir ../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml \
  --bundle-name xgboost-scan-detection-ndr-ml
```

생성 산출물:

```text
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/model.json
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/feature_names.json
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/metrics.json
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/manifest.json
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/model_card.md
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/readiness_report.md
../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/predict_xgb_scan_detection.py
```

번들 runtime 검증:

```bash
.venv-wsl/bin/python validate_model_bundle.py \
  --model-dir ../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml \
  --input ../ipcam-backdoor-test-environment/data/features/datasets/ipcam-scan-subtype-60s.csv \
  --output-json models/model_bundle_validation.json \
  --output-md models/model_bundle_validation.md \
  --prediction-output models/model_bundle_validation_predictions.csv
```

이 검증은 manifest, artifact SHA-256, feature schema, raw identity feature 제외 여부, XGBoost 모델 로딩, feature CSV 추론 출력 row 수와 확률 범위를 확인한다. 현재 smoke dataset 기준 검증은 통과하지만, 27개 row smoke metric은 운영 성능 근거로 쓰지 않는다.

솔루션용 NDR alert adapter:

```bash
cd ../ipcam-backdoor-test-environment
python3 scripts/run_ndr_scan_detection.py \
  --model-dir data/models/xgboost-scan-detection-ndr-ml \
  --input data/features/datasets/ipcam-scan-subtype-60s.csv \
  --predictions-output data/ndr/predictions/scan_detection_predictions.csv \
  --alerts-output data/ndr/alerts/scan_detection_alerts.jsonl \
  --summary-output data/ndr/alerts/scan_detection_summary.json
```

생성 산출물:

```text
../ipcam-backdoor-test-environment/data/ndr/predictions/scan_detection_predictions.csv
../ipcam-backdoor-test-environment/data/ndr/alerts/scan_detection_alerts.jsonl
../ipcam-backdoor-test-environment/data/ndr/alerts/scan_detection_summary.json
```

alert JSONL은 `ndr-alert/v1` 스키마를 사용하며, raw `src_ip`, `dst_ip`는 출력하지 않고 해시된 `src_entity`와 window/run/scenario 메타데이터만 포함한다.

alert 출력 계약 검증:

```bash
python3 scripts/validate_ndr_alerts.py \
  --alerts data/ndr/alerts/scan_detection_alerts.jsonl \
  --summary data/ndr/alerts/scan_detection_summary.json \
  --output-json data/ndr/alerts/scan_detection_alert_validation.json \
  --output-md data/ndr/alerts/scan_detection_alert_validation.md
```

추론 실행 예시:

```bash
python3 ../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml/predict_xgb_scan_detection.py \
  --model-dir ../ipcam-backdoor-test-environment/data/models/xgboost-scan-detection-ndr-ml \
  --input realcam-scan-expanded-60s-test.csv \
  --output models/pilot_predictions.csv
```

추론과 평가 명령은 Linux용 `.venv-wsl`을 활성화한 뒤 실행한다.

## WSL 의존성 점검

실행 명령:

```bash
python3 check_wsl_dependencies.py \
  --project-root . \
  --output-json models/wsl_dependency_report.json \
  --output-md models/wsl_dependency_report.md \
  --zeek-mode docker
```

생성된 리포트:

```text
models/wsl_dependency_report.json
models/wsl_dependency_report.md
```

2026-06-02 현재 이 환경은 WSL2로 감지된다. tcpdump, tshark, nmap, Docker CLI, Docker Compose, Docker Zeek 이미지, ML Python 패키지는 사용 가능하다. Zeek은 호스트 패키지 대신 `zeek/zeek:latest` Docker 이미지로 사용한다. 기존 `.venv`는 Windows 형식(`Scripts/python.exe`)이라 Linux에서 사용할 수 없으므로 `.venv-wsl`을 사용한다.

현재 `models/wsl_dependency_report.md` 기준 `missing_or_unusable=none`이다. Docker는 `/usr/bin/docker`에서 `Docker version 28.4.0`으로 확인됐고, Docker Compose는 `v2.39.2-desktop.1`, Docker Zeek 이미지는 `zeek/zeek:latest` SHA-256 image id로 확인됐다. 앞선 점검에서는 Docker Desktop WSL integration이 비활성/깨진 상태라 `docker`, `docker_compose`, `zeek`이 사용 불가였지만 현재는 복구되어 bulk collection 실행 전제 조건을 충족한다.

초기 점검 시 `sudo -n apt update`는 `sudo: a password is required`로 실패했으므로 sudo가 필요한 시스템 패키지 설치는 사용자가 승인한 WSL 셸에서만 수행한다. 필요한 Python 패키지는 `.venv-wsl`에 설치되어 있고 현재 모두 import 가능하다.

Windows 형식 `.venv/Scripts/python.exe`도 WSL에서 실행을 시도했지만 `UtilBindVsockAnyPort` 오류로 실패했다. 이 WSL 세션에서는 Linux용 venv를 새로 만드는 방식이 필요하다.

Docker Desktop을 사용할 경우 먼저 Windows Docker Desktop에서 WSL integration을 복구한다.

```bash
# Windows Docker Desktop:
# Settings > Resources > WSL Integration > 이 Ubuntu distro 활성화

# Windows PowerShell에서 WSL 재시작:
wsl --shutdown

# WSL에 다시 들어온 뒤 확인:
docker --version
docker compose version
docker pull zeek/zeek:latest
docker run --rm zeek/zeek:latest zeek --version
```

Docker Desktop을 쓰지 않고 WSL Ubuntu 안에 native Docker Engine을 설치할 경우:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
docker pull zeek/zeek:latest
docker run --rm zeek/zeek:latest zeek --version
```

방어적 NDR 분석에 필요한 기타 시스템 패키지 설치 명령. Zeek을 Docker로 사용할 경우 `zeek` apt 패키지는 설치하지 않아도 된다.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip tcpdump tshark nmap
```

호스트 Zeek을 사용할 경우에만 `zeek` apt 패키지 또는 사용하는 Ubuntu 버전에 맞는 Zeek 공식 패키지 저장소를 추가한다.

```bash
sudo apt install -y zeek
```

Python 가상환경 설치 명령:

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

설치 후 다시 점검한다.

```bash
python3 check_wsl_dependencies.py --project-root . --zeek-mode docker
```

## 한계

- 합성 데이터는 실제 운영 트래픽을 대체하지 않는다.
- 합성 데이터로 성능이 좋아져도 실제 운영 성능이 보장된다고 표현하면 안 된다.
- 최종 보고서에는 real-only 결과와 real+synthetic 결과를 분리한다.
- test set은 가능한 실제 수집 데이터만 사용한다.
- split 간 `run_id` 중복이 발견되면 run 기반 split으로 다시 나눠야 한다.

## 완료 감사

현재 산출물이 목표 요구사항을 어느 정도 만족하는지 확인하려면 감사 스크립트를 실행한다.

```bash
python3 audit_goal_readiness.py \
  --project-root . \
  --solution-root ../ipcam-backdoor-test-environment \
  --output-json models/goal_readiness_audit.json \
  --output-md models/goal_readiness_audit.md
```

현재 감사 결과는 `goal_complete=true`, `overall_status=pass`이다. 데이터 진단, 합성 데이터 생성/검증, source-separated 평가, WSL 점검/설치 지원, Docker Zeek 수집 경로, 모델 번들 export, runtime validation, solution alert adapter 검증, lab/operational readiness gate가 모두 통과한다.
