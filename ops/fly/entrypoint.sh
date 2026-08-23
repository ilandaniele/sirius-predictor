#!/usr/bin/env bash
set -Eeuo pipefail

readonly data_root="/data"
readonly postgres_data="${PGDATA:-${data_root}/postgres}"
readonly postgres_socket="${PGSOCKET:-${data_root}/postgres-socket}"
readonly redis_data="${data_root}/redis"
readonly storage_data="${data_root}/storage"
readonly postgres_bin="$(pg_config --bindir)"

postgres_pid=""
redis_pid=""
api_pid=""
worker_pid=""
web_pid=""

shutdown() {
  trap - TERM INT EXIT
  for pid in "$web_pid" "$api_pid" "$worker_pid" "$redis_pid" "$postgres_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}
trap shutdown TERM INT EXIT

mkdir -p "$postgres_data" "$postgres_socket" "$redis_data" "$storage_data"
chown -R postgres:postgres "$postgres_data" "$postgres_socket"
chown -R redis:redis "$redis_data"
chown -R sirius:sirius "$storage_data"
chmod 700 "$postgres_data"
chmod 775 "$postgres_socket"

if [[ ! -s "${postgres_data}/PG_VERSION" ]]; then
  echo "Inicializando PostgreSQL persistente..."
  runuser -u postgres -- "$postgres_bin/initdb" \
    --pgdata="$postgres_data" \
    --username=sirius \
    --encoding=UTF8 \
    --locale=C.UTF-8 \
    --auth-local=trust \
    --auth-host=scram-sha-256 \
    --no-instructions
fi

# Postgres and Redis are independent services; start both immediately instead of
# waiting for Postgres to become ready before even launching Redis.
runuser -u postgres -- "$postgres_bin/postgres" \
  -D "$postgres_data" \
  -c listen_addresses='' \
  -c unix_socket_directories="$postgres_socket" &
postgres_pid=$!

runuser -u redis -- redis-server \
  --bind 127.0.0.1 \
  --port 6379 \
  --protected-mode yes \
  --dir "$redis_data" \
  --appendonly yes \
  --appendfsync everysec \
  --maxmemory-policy noeviction \
  --daemonize no &
redis_pid=$!

for _attempt in $(seq 1 60); do
  if runuser -u postgres -- "$postgres_bin/pg_isready" \
    --host="$postgres_socket" --username=sirius --dbname=postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
runuser -u postgres -- "$postgres_bin/pg_isready" \
  --host="$postgres_socket" --username=sirius --dbname=postgres >/dev/null

if ! runuser -u postgres -- "$postgres_bin/psql" \
  --host="$postgres_socket" --username=sirius --dbname=postgres \
  --tuples-only --command="SELECT 1 FROM pg_database WHERE datname = 'sirius'" \
  | grep -q 1; then
  runuser -u postgres -- "$postgres_bin/createdb" \
    --host="$postgres_socket" --username=sirius --owner=sirius sirius
fi

for _attempt in $(seq 1 30); do
  if redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 1
done
redis-cli -h 127.0.0.1 ping | grep -q PONG

echo "Aplicando migraciones append-only..."
runuser -u sirius -- python -m alembic upgrade head

runuser -u sirius -- uvicorn services.api.main:app \
  --host 127.0.0.1 --port 8000 --proxy-headers &
api_pid=$!

if [[ "${SIRIUS_ALLOW_REMOTE_COMPUTE:-false}" == "true" ]]; then
  runuser -u sirius -- celery -A services.api.tasks:celery_app worker \
    --loglevel=INFO --pool=solo --concurrency=1 &
  worker_pid=$!
else
  echo "Cómputo remoto deshabilitado; no se inicia el worker Monte Carlo."
fi

# Node's own startup takes real wall-clock time; overlap it with the API health
# check below instead of waiting for the API before even launching the web server.
runuser -u sirius -- env HOSTNAME=0.0.0.0 PORT=3000 node /app/web/server.js &
web_pid=$!

for _attempt in $(seq 1 60); do
  if runuser -u sirius -- python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/scenario', timeout=1).close()" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
runuser -u sirius -- python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/scenario', timeout=2).close()"

service_pids=("$postgres_pid" "$redis_pid" "$api_pid" "$web_pid")
if [[ -n "$worker_pid" ]]; then
  service_pids+=("$worker_pid")
fi
wait -n "${service_pids[@]}"
echo "Un proceso principal terminó; deteniendo Sirius de forma segura." >&2
exit 1
