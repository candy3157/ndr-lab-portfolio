# App DB Server

Lightweight App/DB server for the NDR VM lab.

It provides:

- HTTP app endpoints on port `80`
- PostgreSQL demo database on port `5432`
- Sample `demoapp` database with `users` and `orders` tables

The Ubuntu workload client can use this server as both `app.internal` and
`db.internal`.

## Install On App/DB VM

```bash
cd /opt/app-db-server
sudo scripts/install_server.sh
```

## Run HTTP App Manually

```bash
sudo python3 -m app_db_server.app -c config.json
```

## Enable HTTP App With systemd

```bash
sudo cp systemd/app-db-http.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now app-db-http
```

## Expected Client Config

On the Ubuntu client VM, map these names to the App/DB VM IP.

```text
<app-db-ip> app.internal
<app-db-ip> db.internal
```

The workload client default DB credentials are:

```text
database: demoapp
username: demo
password: demo
```

## Quick Checks

```bash
curl http://app.internal/
curl http://app.internal/api/users
PGPASSWORD=demo psql -h db.internal -U demo -d demoapp -c "select count(*) from users;"
```
