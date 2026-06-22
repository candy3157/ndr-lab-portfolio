# AI 기반 네트워크 스캔 탐지 NDR 시스템 | 포트폴리오

## 한 줄 소개

pfSense 기반 VM Lab에서 수집한 트래픽을 Zeek flow 로그로 변환하고, **XGBoost 단독 탐지**와 **XGBoost+LSTM 앙상블**으로 포트 스캔 및 low-and-slow scan을 분석하는 NDR 시스템을 설계했습니다.

## 프로젝트 정보

| 항목 | 내용 |
| --- | --- |
| 기간 | 2026년 캡스톤디자인 |
| 소속 | 대전대학교 정보보안학과 캡스톤디자인 팀 디지털 혁명단 |
| 역할 | 팀장 |
| 핵심 기술 | Python, Zeek, tcpdump, XGBoost, LSTM, FastAPI, pfSense, Docker, SQLite, SSE |
| 구현 범위 | VM Lab · 데이터 파이프라인 · 모델 설계/평가 · Sensor runtime · Dashboard · Telegram 알림 |

## 문제와 접근

일반 포트 스캔은 한 window 안에서 flow 수, 목적지 포트 수, 연결 실패율이 급격히 증가합니다. 그러나 low-and-slow scan은 연결을 여러 window로 분산해 단일 window만 보면 정상처럼 보일 수 있습니다.

이를 위해 XGBoost는 현재 window의 통계 feature로 빠르게 판단하고, LSTM은 최근 6개 window의 목적지 확산·포트 다양성·실패율 변화를 분석합니다. 두 확률은 같은 tail window에 맞춰 결합합니다.

```text
p_xgb  = XGBoost(x_t)
p_lstm = LSTM(x_(t-5), …, x_t)
p_ens  = α × p_xgb + (1 - α) × p_lstm
```

`α`와 attack threshold `τ`는 validation split에서 정한 뒤 held-out test에 한 번만 적용합니다.

## 최종 모델

LSTM 단독 모델은 포트폴리오의 최종 모델이 아닙니다. 최종적으로 제시하는 모델은 다음 두 가지입니다.

| 모델 | 입력 | 목적 |
| --- | --- | --- |
| XGBoost | 현재 10초 window의 `1 × 90` feature | 빠른 단독 탐지 및 운영 기준선 |
| XGBoost+LSTM | XGBoost 확률 + 최근 6개 window의 LSTM 확률 | 시간에 누적되는 low-and-slow scan 보완 |

XGBoost+LSTM은 XGBoost의 빠른 tabular 판단과 LSTM의 시계열 문맥을 결합하는 최종 앙상블 후보입니다. GRU와 XGBoost+GRU는 과거 비교·runtime 자료일 뿐, 이 포트폴리오의 최종 모델 표나 성능 지표에는 사용하지 않습니다.

## 데이터셋 설계

10개 공개·시뮬레이션·VM Lab 데이터셋을 `ndr_common_low_slow_v2` schema로 통합했습니다.

| 항목 | 값 |
| --- | ---: |
| 전체 rows | 178,059 |
| 전체 columns | 107 |
| 모델 feature | 90 |
| normal / attack | 112,021 / 66,038 |
| real / synthetic | 162,059 / 16,000 |
| train / validation / test | 93,174 / 11,810 / 73,075 rows |

90개 feature는 22개 base feature와 68개 rolling feature로 구성했습니다. `flow_count`, 목적지 IP/port 다양성, `failed_conn_ratio`, protocol ratio, entropy, `rolling_6/12/30/60_*`, `low_slow_scan_score`를 사용했습니다.

원시 IP·포트·시간·scenario metadata는 모델 입력에서 제외하고, `session_id` 기준 group-aware split을 적용했습니다. 같은 session이 train/test에 섞여 특정 run을 외우는 데이터 누수를 줄이기 위한 결정입니다.

## 검증 근거

sequence/ensemble 비교는 동일한 64,908개 aligned tail-window test rows를 기준으로 합니다.

| 최종 모델 | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| XGBoost | 94.17% | 99.93% | 91.25% | 0.9539 | 0.9985 | 0.9992 | 0.12% | 8.75% |
| XGBoost+LSTM | 99.51% | 99.77% | 99.49% | 0.9963 | 0.9995 | 0.9997 | 0.45% | 0.51% |

XGBoost+LSTM은 Recall을 **91.25% → 99.49%**, F1을 **0.9539 → 0.9963**으로 높이고 FNR을 **8.75% → 0.51%**로 낮췄습니다. 반면 FPR은 **0.12% → 0.45%**로 증가했습니다. 따라서 이 앙상블은 약간의 오탐 증가를 감수하고 공격 미탐을 줄이는 방향의 모델입니다. 기존 Notion의 XGBoost+GRU 결과는 다른 모델이므로 이 표에 사용하지 않았습니다.

## 내가 담당한 일

- 팀장으로서 문제 정의, VM Lab 아키텍처, 모델 검증 범위를 설계했습니다.
- Kali 공격자, Ubuntu 사용자, App/DB·IoT 서버, pfSense 라우터, Sensor, Dashboard를 분리한 네트워크를 구성했습니다.
- Zeek `conn.log`를 기반으로 flow·entropy·rolling feature를 포함한 90개 공통 schema를 설계했습니다.
- XGBoost 단독과 XGBoost+LSTM 앙상블의 입력·정렬·검증 절차를 정의했습니다.
- raw IP 배제, session/run group split, real/synthetic 분리 평가로 데이터 누수와 성능 과장을 통제했습니다.
- `tcpdump → Zeek → feature → inference → Dashboard` 경로와 SQLite/SSE/Telegram 알림을 구현했습니다.

## 구현 상태와 한계

- 현재 공개 runtime에는 XGBoost+GRU adapter가 남아 있습니다.
- LSTM 모델 및 비교 산출물은 있으나, XGBoost+LSTM score 결합 정책과 실시간 adapter는 통합 전입니다.
- 따라서 이 문서는 XGBoost+LSTM을 목표 모델 구조로 제시하며, 미완성인 runtime 통합을 이미 완료한 것처럼 표현하지 않습니다.
- VM Lab 중심 결과는 실제 기업망의 복잡한 정상 트래픽을 대표하지 않으므로, future-run holdout과 실제 정상 트래픽 확대 수집이 필요합니다.

## 포트폴리오 본문 예시

> **AI 기반 네트워크 스캔 탐지 NDR 시스템** — pfSense 기반 VM Lab에서 수집한 트래픽을 Zeek flow 로그로 변환하고, XGBoost 단독 모델과 XGBoost+LSTM 앙상블로 포트 스캔 및 low-and-slow scan을 분석하는 NDR 시스템을 설계했습니다. 팀장으로서 VM 네트워크, 수집 시나리오, 90개 공통 feature schema, 데이터 누수 방지용 session-aware split, 모델 검증 절차, Sensor runtime, SQLite/SSE Dashboard와 Telegram 알림을 구성했습니다. XGBoost는 현재 10초 window를 빠르게 판단하고, LSTM은 최근 6개 window의 누적 패턴을 분석하며, 두 확률은 validation-selected 가중치와 threshold로 결합하도록 설계했습니다.

## Sources

- [Notion — 데이터셋 관련 페이지](https://app.notion.com/p/37a4b27666b0806d9b42f28e41465200) (작업공간 권한 필요)

