# NDR Dashboard

Dashboard VM에서 실행하는 경량 NDR 탐지 결과 대시보드다. Sensor VM이 모델 추론 결과를 `POST /api/events`로 보내면 이 서버가 SQLite에 저장하고 브라우저에 실시간으로 표시한다.

## 구조

```text
NDR Sensor VM
  -> POST http://10.10.99.20:8000/api/events

Dashboard VM
  -> Python HTTP server
  -> SQLite
  -> Server-Sent Events
  -> Static web dashboard
```

## 실행

```bash
cd ndr-dashboard
cp config.example.json config.json
python3 -m dashboard_server.app -c config.json
```

브라우저에서 접속한다.

```text
http://10.10.99.20:8000
```

로컬 테스트:

```text
http://127.0.0.1:8000
```

## 데모 이벤트 전송

다른 터미널에서 샘플 이벤트를 보낸다.

```bash
python3 scripts/send_demo_events.py --url http://127.0.0.1:8000 --mode demo
```

특정 상태만 보낼 수도 있다.

```bash
python3 scripts/send_demo_events.py --url http://127.0.0.1:8000 --mode normal --count 3
python3 scripts/send_demo_events.py --url http://127.0.0.1:8000 --mode warning --count 3
python3 scripts/send_demo_events.py --url http://127.0.0.1:8000 --mode scanning --count 3
```

## Sensor VM에서 보내는 이벤트 포맷

```json
{
  "timestamp": "2026-06-08T14:30:12Z",
  "sensor_id": "sensor-01",
  "status": "scanning",
  "score": 0.93,
  "src_ip": "10.10.90.10",
  "target_network": "10.10.20.0/24",
  "window_seconds": 10,
  "flow_count": 482,
  "unique_dst_ips": 18,
  "unique_dst_ports": 76,
  "syn_count": 390,
  "failed_connection_ratio": 0.82,
  "top_dst_ports": [22, 80, 443, 445, 5432]
}
```

`status`는 `normal`, `warning`, `scanning` 중 하나다. `status`가 없으면 `score` 기준으로 자동 분류한다.

## Telegram 알림

`scanning` 이벤트가 들어왔을 때 Telegram으로 휴대폰 알림을 보낼 수 있다. 같은 source IP는
`cooldown_seconds` 동안 중복 전송하지 않는다.

`config.json` 예시:

```json
{
  "alerts": {
    "enabled": true,
    "provider": "telegram",
    "cooldown_seconds": 300,
    "timeout_seconds": 5,
    "telegram": {
      "bot_token": "env:TELEGRAM_BOT_TOKEN",
      "chat_id": "env:TELEGRAM_CHAT_ID"
    }
  }
}
```

환경변수 대신 실제 token/chat_id 값을 직접 넣을 수도 있다. token을 파일에 직접 넣는 경우
해당 `config.json`은 외부에 공유하지 않는다.

## API

```text
POST /api/events
GET  /api/status
GET  /api/events/recent?limit=80
GET  /api/metrics
GET  /api/snapshot
GET  /api/stream
GET  /api/health
```

## systemd 등록

프로젝트를 `/opt/ndr-dashboard`에 배치한 경우:

```bash
sudo cp systemd/ndr-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ndr-dashboard
```

다른 경로에 둘 경우 service 파일의 `WorkingDirectory`와 `ExecStart`를 수정한다.

## pfSense 룰

Monitor-Net 기준 예시:

```text
NDR Sensor 10.10.99.10 -> Dashboard 10.10.99.20 TCP/8000 allow
Host PC    -> Dashboard 10.10.99.20 TCP/8000 allow
Kali       -> Dashboard 10.10.99.20 block
```
