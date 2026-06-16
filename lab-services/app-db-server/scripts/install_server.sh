#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root: sudo scripts/install_server.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y python3 postgresql postgresql-client curl

if [[ ! -f config.json ]]; then
  cp config.example.json config.json
fi

systemctl enable --now postgresql

sudo -u postgres psql <<'SQL'
do $$
begin
  if not exists (select from pg_roles where rolname = 'demo') then
    create role demo login password 'demo';
  else
    alter role demo with login password 'demo';
  end if;
end
$$;
SQL

if ! sudo -u postgres psql -tAc "select 1 from pg_database where datname = 'demoapp'" | grep -q 1; then
  sudo -u postgres createdb -O demo demoapp
fi

sudo -u postgres psql -d demoapp -f scripts/demoapp_schema.sql

PG_VERSION="$(psql -V | awk '{print $3}' | cut -d. -f1)"
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

if [[ -f "$PG_CONF" ]]; then
  sed -i "s/^#\\?listen_addresses\\s*=.*/listen_addresses = '*'/" "$PG_CONF"
fi

if [[ -f "$PG_HBA" ]] && ! grep -q "NDR lab demo client access" "$PG_HBA"; then
  cat >> "$PG_HBA" <<'EOF'

# NDR lab demo client access
host    demoapp    demo    10.10.0.0/16    scram-sha-256
EOF
fi

systemctl restart postgresql

echo "App/DB server installed."
echo "HTTP app:"
echo "  sudo python3 -m app_db_server.app -c config.json"
echo "PostgreSQL:"
echo "  database=demoapp username=demo password=demo port=5432"
