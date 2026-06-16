# Ubuntu Workload Client

16GB VM lab에서 Ubuntu Client가 Debian Server와 App/DB Server에 접근하는 정상 업무 트래픽을 만드는 경량 프로젝트다. NDR 모델 시연에서 `Normal` baseline을 만들기 위한 용도이며, 외부 Python 패키지 없이 동작한다.

## 역할

```text
Ubuntu Client
  -> Debian Server
       DNS lookup
       SMB share access
       SSH/SMB TCP connection

  -> App/DB Server
       HTTP page/API request
       DB query or DB TCP fallback
```

## 포함 기능

- DNS 이름 조회: `app.internal`, `files.internal`, `db.internal`
- HTTP/API 호출: 내부 포털, 로그인, users/orders/reports API
- TCP 연결 확인: SSH, SMB, HTTP, PostgreSQL/MySQL 포트
- SMB 접근: `smbclient`가 있으면 실제 공유 접근
- DB 접근: `psql` 또는 `mysql`이 있으면 실제 query, 없으면 TCP fallback
- JSONL 로그 기록: `logs/client-traffic.jsonl`
- systemd 서비스 예시 포함

## 설치

Ubuntu Client VM에서 실행한다.

```bash
cd ubuntu-workload-client
./scripts/install_client.sh
```

선택 도구는 실제 SMB/DB 트래픽을 더 그럴듯하게 만든다.

```bash
sudo apt update
sudo apt install -y smbclient postgresql-client dnsutils
```

MySQL을 쓸 경우:

```bash
sudo apt install -y mysql-client
```

## 설정

```bash
cp config.example.json config.json
```

VM lab 주소에 맞게 `config.json`을 수정한다.

기본 DNS 이름:

```text
app.internal   -> App/DB Server
db.internal    -> App/DB Server 또는 DB 전용 이름
files.internal -> Debian Server
```

DNS 서버가 아직 없으면 Ubuntu Client의 `/etc/hosts`에 임시로 넣어도 된다.

```text
10.10.20.10 files.internal
10.10.20.20 app.internal
10.10.20.20 db.internal
```

## 실행

전체 접근 가능 여부를 한 번씩 점검한다.

```bash
. .venv/bin/activate
ubuntu-workload-client -c config.json check
```

랜덤 작업을 한 번 실행한다.

```bash
ubuntu-workload-client -c config.json once
```

정상 트래픽을 계속 발생시킨다.

```bash
ubuntu-workload-client -c config.json loop
```

## systemd 등록

프로젝트를 `/opt/ubuntu-workload-client`에 배치한 경우:

```bash
sudo cp systemd/ubuntu-workload-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ubuntu-workload-client
```

다른 경로에 둘 경우 service 파일의 `WorkingDirectory`와 `ExecStart`를 수정한다.

## 데모 운영 팁

- 발표 전에는 `check`로 DNS, HTTP, SMB, DB 접근을 확인한다.
- 실제 DB client가 없어도 TCP fallback으로 DB 포트 연결 트래픽은 생성된다.
- SMB 트래픽을 제대로 보이려면 Debian Server에 Samba 공유와 `demo/demo` 계정을 만들어둔다.
- 정상 baseline은 5~15초 랜덤 간격으로 반복되는 낮은 fan-out 트래픽이면 충분하다.
- Kali 스캔과 대비되도록 이 클라이언트는 다수 호스트/포트를 훑지 않게 유지한다.
