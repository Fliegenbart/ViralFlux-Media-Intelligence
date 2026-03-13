#!/usr/bin/env bash
# Database backup script for ViralFlux Media Intelligence
# Usage: ./scripts/backup-db.sh [backup_dir]
# Recommended: run daily via cron
#   0 2 * * * /opt/viralflux/scripts/backup-db.sh /opt/viralflux/backups
set -euo pipefail

BACKUP_DIR="${1:-/opt/viralflux/backups}"
CONTAINER="${DB_CONTAINER:-virusradar_db}"
POSTGRES_USER="${POSTGRES_USER:-virusradar}"
POSTGRES_DB="${POSTGRES_DB:-virusradar_db}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/viralflux_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting database backup..."

# Dump via docker exec, compress with gzip
docker exec "$CONTAINER" pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-acl \
    --format=plain \
    | gzip > "$BACKUP_FILE"

FILESIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup created: $BACKUP_FILE ($FILESIZE)"

# Clean up old backups
DELETED=$(find "$BACKUP_DIR" -name "viralflux_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] Cleaned up $DELETED old backup(s) (older than ${RETENTION_DAYS} days)"
fi

# Verify backup is not empty
if [ ! -s "$BACKUP_FILE" ]; then
    echo "[$(date)] ERROR: Backup file is empty!" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "[$(date)] Backup completed successfully."
