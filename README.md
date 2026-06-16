# NDR Lab Portfolio

분리된 VM 환경에서 스캔 행위를 실시간으로 탐지하기 위한 네트워크 탐지 실습 프로젝트입니다.

이 프로젝트는 라우터 트래픽을 일정 단위로 캡처하고, 패킷을 Zeek flow 로그로 변환한 뒤, low-and-slow 스캔 탐지를 위한 특징을 생성합니다. 이후 XGBoost와 GRU 모델 추론을 수행하고, 탐지 이벤트를 경량 대시보드로 실시간 스트리밍합니다.

## 포함된 내용

* `model/`: 연구 작업 공간에서 사용한 최종 모델 학습, 평가, 특징 엔지니어링, 추론 코드
* `runtime/`: 라우터 트래픽 캡처, Zeek 변환, 모델 추론, 앙상블 점수 계산, 대시보드 이벤트 전달을 위한 VM 런타임 번들
* `dashboard/`: SQLite 저장소와 Server-Sent Events 기반 실시간 업데이트를 지원하는 경량 NDR 대시보드
* `lab-services/`: 정상 트래픽 기준선을 생성하기 위한 데모 App/DB 서버 및 Ubuntu workload client
* `reports/`: 포트폴리오 검토에 적합한 주요 모델 평가 요약 자료

## 포함되지 않은 내용

이 저장소는 원시 데이터셋, 패킷 캡처 파일, 생성된 SQLite 데이터베이스, 악성코드/바이너리 샘플, 학습된 모델 아티팩트, 로컬 런타임 로그를 의도적으로 제외합니다.

제외 예시는 다음과 같습니다.

* `data/`, `datasets/`
* `*.pcap`, `*.sqlite3`, `*.exe`, 압축 파일
* `*.pt`, `*.joblib`
* 실제 `config.json`, `.env`, 로컬 로그

학습된 아티팩트는 GitHub Releases, Git LFS 또는 개인 아티팩트 저장소를 통해 별도로 첨부할 수 있습니다. 자세한 내용은 `runtime/models/README.md`를 참고하세요.

## 아키텍처

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

## 런타임 데모 흐름

대시보드를 실행합니다.

```bash
cd dashboard
cp config.example.json config.json
python3 -m dashboard_server.app -c config.json
```

클라이언트 VM에서 정상 workload client를 실행합니다.

```bash
cd lab-services/ubuntu-workload-client
cp config.example.json config.json
./scripts/install_client.sh
ubuntu-workload-client -c config.json loop
```

학습된 아티팩트를 `runtime/models/` 아래에 배치한 뒤, 실시간 모니터링 파이프라인을 실행합니다.

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

## 모델 요약

최종 런타임 경로는 다음 구조를 사용합니다.

* XGBoost를 사용하여 빠른 window-level fallback 탐지를 수행합니다.
* 충분한 이력 데이터가 확보되면 GRU 기반 시퀀스 추론을 수행합니다.
* 앙상블 점수 계산을 통해 XGBoost와 GRU의 출력을 결합합니다.
* 동적 출발지 IP 처리 기능을 포함하여 탐지 결과를 대시보드 이벤트로 변환합니다.

주요 평가 요약 자료는 `reports/` 디렉터리에 있으며, 특히 다음 파일을 참고할 수 있습니다.

* `reports/combined_10_model_comparison.md`
* `reports/xgboost_metrics_combined_10_ndr.md`
* `reports/low_slow_feature_evaluation_report.md`

## 저장소 상태

이 저장소는 프로젝트의 포트폴리오 및 공개 코드 버전입니다. 원시 트래픽 데이터나 학습된 아티팩트를 저장소에 직접 공개하지 않으면서도, 구현 품질과 재현 가능한 런타임 흐름을 보여줄 수 있도록 구성되어 있습니다.
