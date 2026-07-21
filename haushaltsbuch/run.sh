#!/bin/sh
set -e

cd /app

DB_FILE="/data/haushaltsbuch.db"
BACKUP_DIR="/data/backups"

if [ -f "$DB_FILE" ]; then
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    cp "$DB_FILE" "$BACKUP_DIR/haushaltsbuch-$TIMESTAMP.db"
    echo "[haushaltsbuch] Backup vor Migration angelegt: $BACKUP_DIR/haushaltsbuch-$TIMESTAMP.db"
    # nur die letzten 10 Backups behalten
    ls -1t "$BACKUP_DIR"/haushaltsbuch-*.db 2>/dev/null | tail -n +11 | xargs -r rm --
fi

echo "[haushaltsbuch] Fuehre Datenbank-Migrationen aus..."
alembic upgrade head

echo "[haushaltsbuch] Starte Web-Server..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
