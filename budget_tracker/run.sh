#!/bin/sh
set -e

cd /app

# Demo-Modus: die Demo-Datenbank wird vor JEDER Migration verworfen, damit die
# App bei jedem Start wieder mit denselben frei erfundenen Testdaten beginnt -
# nie mit Staenden aus einer vorherigen Vorfuehrung. Muss vor "alembic upgrade
# head" laufen, sonst baut die Migration auf einem veralteten Stand auf.
DEMO_MODUS=$(python3 -c "
import json, pathlib
p = pathlib.Path('/data/options.json')
try:
    print(bool(json.loads(p.read_text()).get('demo_modus', False)))
except Exception:
    print(False)
")
if [ "$DEMO_MODUS" = "True" ]; then
    echo "[budget-tracker] Demo-Modus aktiv: Demo-Datenbank wird frisch aufgebaut."
    rm -f /data/demo_budget_tracker.db /data/demo_budget_tracker.db-*
fi

DB_FILE="/data/budget_tracker.db"
BACKUP_DIR="/data/backups"

if [ -f "$DB_FILE" ]; then
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    cp "$DB_FILE" "$BACKUP_DIR/budget_tracker-$TIMESTAMP.db"
    echo "[budget-tracker] Backup vor Migration angelegt: $BACKUP_DIR/budget_tracker-$TIMESTAMP.db"
    # nur die letzten 10 Backups behalten
    ls -1t "$BACKUP_DIR"/budget_tracker-*.db 2>/dev/null | tail -n +11 | xargs -r rm --
fi

echo "[budget-tracker] Fuehre Datenbank-Migrationen aus..."
alembic upgrade head

echo "[budget-tracker] Starte Web-Server..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
