"""Verzeichnis-Watcher (Konzept Abschnitt 7): periodischer Scan des
Import-Verzeichnisses auf neue oder veraenderte CSV-Dateien.

Bewusst als leichtgewichtiges Polling statt inotify/watchdog umgesetzt,
um keine zusaetzliche Abhaengigkeit zu benoetigen - das Konzept nennt
periodischen Scan explizit als gleichwertige Option.
"""
import asyncio
import logging
from pathlib import Path

from app.config import DIRECTORY_SCAN_INTERVAL_SECONDS
from app.csv_import import import_csv_datei
from app.database import SessionLocal
from app.forecast_engine import ensure_forecast_vorkommen
from app.models import Konfiguration

logger = logging.getLogger("haushaltsbuch.watcher")

# Datei -> (mtime, groesse) der zuletzt verarbeiteten Version, nur im
# Speicher gehalten: ein Neustart fuehrt hoechstens zu einem harmlosen
# Re-Scan, Dedublizierung passiert ohnehin ueber transaction_id.
_bekannte_dateien: dict[str, tuple[float, int]] = {}

_letzter_scan_status = {"zeitpunkt": None, "verzeichnis": None, "importierte_dateien": 0}


def status() -> dict:
    return dict(_letzter_scan_status)


def scan_einmal() -> dict:
    import datetime as dt

    db = SessionLocal()
    try:
        konfiguration = db.query(Konfiguration).first()
        if konfiguration is None:
            return {"uebersprungen": "keine Konfiguration (Bootstrap ausstehend)"}

        verzeichnis = Path(konfiguration.import_verzeichnis)
        _letzter_scan_status["verzeichnis"] = str(verzeichnis)
        _letzter_scan_status["zeitpunkt"] = dt.datetime.utcnow().isoformat()

        if not verzeichnis.is_dir():
            logger.debug("Import-Verzeichnis %s existiert (noch) nicht.", verzeichnis)
            return {"uebersprungen": f"Verzeichnis {verzeichnis} nicht gefunden"}

        importierte_dateien = 0
        gesamt_stats = []
        for datei in sorted(verzeichnis.glob("*.csv")):
            try:
                stat = datei.stat()
            except OSError:
                continue
            signatur = (stat.st_mtime, stat.st_size)
            if _bekannte_dateien.get(str(datei)) == signatur:
                continue

            logger.info("Verarbeite CSV-Datei: %s", datei)
            try:
                stats = import_csv_datei(db, datei)
            except Exception:  # noqa: BLE001 - eine kaputte Datei darf andere nicht blockieren
                logger.exception("Fehler beim Import von %s, wird beim naechsten Scan erneut versucht.", datei)
                db.rollback()
                continue
            gesamt_stats.append(stats)
            _bekannte_dateien[str(datei)] = signatur
            importierte_dateien += 1

        # Guenstige, idempotente Operation: haelt den 12-Monats-Horizont der
        # generierten Vorkommen unabhaengig von neuen CSV-Importen aktuell.
        ensure_forecast_vorkommen(db)
        db.commit()

        _letzter_scan_status["importierte_dateien"] = importierte_dateien
        return {"dateien": gesamt_stats}
    finally:
        db.close()


async def scan_schleife() -> None:
    while True:
        try:
            scan_einmal()
        except Exception:  # noqa: BLE001 - Watcher darf nie durch einen Fehler sterben
            logger.exception("Fehler beim Scannen des Import-Verzeichnisses")
        await asyncio.sleep(DIRECTORY_SCAN_INTERVAL_SECONDS)
