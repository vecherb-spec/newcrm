#!/bin/sh
set -eu

APP_DIR="${APP_DIR:-/opt/ledops}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/ledops}"
COMPOSE="docker compose -p ledops -f docker-compose.yml -f docker-compose.prod.yml"

install -d -m 0700 "$BACKUP_DIR"
cd "$APP_DIR"

filename="$BACKUP_DIR/ledops-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
$COMPOSE exec -T postgres sh -c \
  'pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip -9 > "$filename"

test -s "$filename"
find "$BACKUP_DIR" -type f -name 'ledops-*.sql.gz' -mtime +14 -delete
