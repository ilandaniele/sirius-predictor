#!/bin/sh
set -eu

umask 077
mkdir -p /backups

while true; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  temporary="/backups/sirius-${timestamp}.sql.gz.tmp"
  target="/backups/sirius-${timestamp}.sql.gz"
  pg_dump --no-owner --no-privileges | gzip -9 > "${temporary}"
  mv "${temporary}" "${target}"
  find /backups -type f -name 'sirius-*.sql.gz' -mtime "+${BACKUP_RETENTION_DAYS}" -delete
  sleep "${BACKUP_INTERVAL_SECONDS}"
done
