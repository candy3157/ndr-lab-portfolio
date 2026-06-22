# AI 기반 네트워크 스캔 탐지 NDR 시스템 | 포트폴리오 요약

## 한 줄 소개

VM Lab에서 수집한 네트워크 트래픽을 Zeek 로그와 AI 모델로 분석해, 일반 포트 스캔과 단일 구간에서 식별하기 어려운 low-and-slow scan을 탐지하는 실시간 NDR 시스템을 구현했습니다.

## 프로젝트 정보

| 항목 | 내용 |
| --- | --- |
| 기간 | 2026년 캡스톤디자인 |
| 역할 | 팀장 |
| 핵심 기술 | Python, Zeek, tcpdump, XGBoost, GRU, FastAPI, pfSense, Docker, SQLite |
| 데이터 | 공개 데이터셋 + VM Lab 시뮬레이션 데이터, 178,059 rows / 90 model features |
| 결과물 | AI 탐지 모델, 실시간 분석 파이프라인, SSE 대시보드, 상태 알림 |

## 문제와 접근

**문제**: 임계값 기반 탐지는 짧은 시간에 연결이 집중되는 일반 스캔에는 강하지만, 여러 시간 구간에 연결을 분산시키는 low-and-slow scan은 정상 트래픽처럼 보일 수 있습니다.

**접근**: Zeek `conn.log`에서 단일 window의 통계 feature와 여러 window의 누적·시계열 feature를 생성했습니다. XGBoost는 빠른 통계적 판단을 담당하고, GRU는 저속 스캔의 시간적 변화를 보완적으로 분석합니다. 두 결과를 앙상블해 탐지 상태를 결정하고 대시보드와 알림으로 전달했습니다.

## 담당한 일

- 팀장으로서 프로젝트 목표, 실험 범위, 시스템 구조를 설계했습니다.
- Kali 공격자·Ubuntu 사용자·Debian 서버·pfSense 라우터·NDR Sensor를 분리한 VM Lab을 구축했습니다.
- 공격/정상 트래픽 수집 시나리오와 Zeek 기반 데이터 처리 흐름을 설계했습니다.
- flow 수, 목적지 IP/포트 다양성, 실패율, entropy, rolling window 통계 등 90개 모델 feature를 설계했습니다.
- XGBoost 기반 단일 window 탐지와 GRU 기반 시계열 탐지 모델을 개발·비교했습니다.
- 동일 session/run이 학습·평가에 교차하지 않도록 group split을 적용해 데이터 누수를 방지했습니다.
- FPR, FNR, Low-and-slow Recall을 포함하는 보안 탐지 중심의 평가 기준을 정리했습니다.
- tcpdump → Zeek → feature → 모델 추론 → dashboard/alert로 이어지는 실시간 경로를 구현했습니다.

## 기술적 의사결정

| 결정 | 이유 |
| --- | --- |
| raw IP 대신 접근 패턴 feature 사용 | 특정 IP/환경에 대한 과적합을 줄이고 일반화 가능성을 높이기 위해 |
| session 단위 group split | 유사한 같은 세션 샘플이 train/test에 함께 들어가 생기는 성능 과대평가를 방지하기 위해 |
| XGBoost + GRU 역할 분리 | 빠른 tabular 탐지와 low-and-slow 시계열 탐지를 각각 최적화하기 위해 |
| Accuracy 외 FPR/FNR 평가 | 보안 운영에서 오탐과 미탐이 각각 실질적인 비용을 만들기 때문에 |
| 대시보드·알림 연동 | 오프라인 모델 평가를 실제 관제 흐름으로 확장하기 위해 |

## 시스템 흐름

```text
VM Lab 트래픽 수집
→ tcpdump capture
→ Zeek conn.log 변환
→ window/rolling feature 생성
→ XGBoost + GRU ensemble 추론
→ Normal · Warning · Scanning 상태 판단
→ SSE Dashboard 및 Alert
```

## 결과와 배운 점

- Zeek 기반 flow feature만으로 스캔 탐지에 필요한 통계 신호를 구성할 수 있음을 확인했습니다.
- 저속 스캔은 단일 window가 아니라 시간 흐름을 포함해 분석해야 한다는 점을 실험 설계에 반영했습니다.
- 모델 성능뿐 아니라 데이터 누수, 추론 비용, 해석 가능성, 운영 시 오탐/미탐까지 함께 고려하는 보안 ML 개발 경험을 쌓았습니다.
- 모델 학습에서 끝나지 않고 트래픽 수집부터 사용자에게 보이는 관제 화면까지 연결했습니다.

## 포트폴리오 본문 예시

> **AI 기반 네트워크 스캔 탐지 NDR 시스템** — VM Lab에서 수집한 트래픽을 Zeek flow 로그로 변환하고, XGBoost와 GRU 앙상블로 일반 포트 스캔 및 low-and-slow scan을 탐지하는 실시간 NDR 시스템을 개발했습니다. 팀장으로서 VM 네트워크 설계, 데이터셋 구성, 90개 feature engineering, 모델 개발, 데이터 누수 방지용 session group split, 대시보드·알림 연동을 주도했습니다. 보안 탐지의 운영 특성을 반영해 Accuracy뿐 아니라 FPR, FNR, Low-and-slow Recall을 평가 기준으로 설계했습니다.

## 후속 개선 계획

- 실제 환경에 가까운 정상 트래픽 수집 및 검증
- lateral movement, brute force, C2 통신까지 탐지 범위 확장
- threshold 자동 튜닝과 모델 drift 감지
- ONNX 기반 경량화 및 탐지 근거 설명 기능 추가

