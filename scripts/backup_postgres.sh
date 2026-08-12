#!/bin/sh
set -eu

PROJECT_DIR="${PROJECT_DIR:-/root/smartFoodIA}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups/postgres}"
KEEP_DAYS="${KEEP_DAYS:-14}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.production.yml"

cd "$PROJECT_DIR"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$BACKUP_DIR/smartfoodia-$STAMP.dump.tmp"
OUT="$BACKUP_DIR/smartfoodia-$STAMP.dump"

# O dump custom (-Fc) permite restore seletivo e é comprimido pelo PostgreSQL.
docker compose $COMPOSE_FILES exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$TMP"

if [ ! -s "$TMP" ]; then
  rm -f "$TMP"
  echo "ERRO: backup vazio" >&2
  exit 1
fi

mv "$TMP" "$OUT"
chmod 600 "$OUT"

# Validação mínima: pg_restore precisa conseguir listar o arquivo.
docker compose $COMPOSE_FILES exec -T db \
  pg_restore -l < "$OUT" >/dev/null

find "$BACKUP_DIR" -type f -name 'smartfoodia-*.dump' -mtime "+$KEEP_DAYS" -delete

echo "BACKUP_OK $OUT"
