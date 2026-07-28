"""Verzeichnis-Watcher (Konzept Abschnitt 7): periodischer Scan des
Import-Verzeichnisses auf neue oder veraenderte CSV-Dateien.

Bewusst als leichtgewichtiges Polling statt inotify/watchdog umgesetzt,
um keine zusaetzliche Abhaengigkeit zu benoetigen - das Konzept nennt
periodischen Scan explizit als gleichwertige Option.
"""
import asyncio
import datetime as dt
import logging
from pathlib import Path

from app.config import DIRECTORY_SCAN_INTERVAL_SECONDS
from app.csv_import import import_csv_datei
from app.database import SessionLocal
from app.forecast_engine import ensure_forecast_vorkommen
from app.models import Konfiguration

logger = logging.getLogger("budget_tracker.watcher")

# Datei -> (mtime, groesse) der zuletzt verarbeiteten Version, nur im
# Speicher gehalten: ein Neustart fuehrt hoechstens zu einem harmlosen
# Re-Scan, Dedublizierung passiert ohnehin ueber transaction_id.
_bekannte_dateien: dict[str, tuple[float, int]] = {}

# Zustand des letzten Scans fuer die Import-Anzeige. Bewusst nur im Speicher:
# nach einem Neustart ist er nach spaetestens einem Scan-Intervall wieder
# gefuellt. Wann zuletzt real importiert wurde, kommt dagegen aus der
# Datenbank (calculations.letzter_import_zeitpunkt) und ueberlebt Neustarts.
_letzter_scan_status = {
    "zeitpunkt": None,
    "verzeichnis": None,
    "verzeichnis_gefunden": None,
    "letzte_zahlen": None,
    "meldungen": [],
}


def status() -> dict:
    return dict(_letzter_scan_status)


def _zahlen_zusammenfassen(alle_stats: list[dict]) -> dict:
    summe = {"dateien": len(alle_stats), "gelesen": 0, "neu": 0, "duplikate": 0,
             "vor_startdatum": 0, "fehler": 0}
    for s in alle_stats:
        for schluessel in ("gelesen", "neu", "duplikate", "vor_startdatum", "fehler"):
            summe[schluessel] += s.get(schluessel, 0)
    return summe


def scan_einmal() -> dict:
    db = SessionLocal()
    try:
        konfiguration = db.query(Konfiguration).first()
        if konfiguration is None:
            return {"uebersprungen": "keine Konfiguration (Bootstrap ausstehend)"}

        verzeichnis = Path(konfiguration.import_verzeichnis)
        _letzter_scan_status["verzeichnis"] = str(verzeichnis)
        _letzter_scan_status["zeitpunkt"] = dt.datetime.utcnow()

        if not verzeichnis.is_dir():
            _letzter_scan_status["verzeichnis_gefunden"] = False
            logger.debug("Import-Verzeichnis %s existiert (noch) nicht.", verzeichnis)
            return {"uebersprungen": f"Verzeichnis {verzeichnis} nicht gefunden"}
        _letzter_scan_status["verzeichnis_gefunden"] = True

        gesamt_stats = []
        meldungen = []
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
                meldungen.append(f"{datei.name}: Import abgebrochen")
                continue
            gesamt_stats.append(stats)
            if stats.get("meldung"):
                meldungen.append(f"{datei.name}: {stats['meldung']}")
            elif stats.get("fehler"):
                meldungen.append(f"{datei.name}: {stats['fehler']} Zeile(n) fehlerhaft")
            _bekannte_dateien[str(datei)] = signatur

        # Zahlen nur ueberschreiben, wenn dieser Scan tatsaechlich Dateien
        # verarbeitet hat - sonst wuerde die Anzeige bei jedem Leerlauf-Scan
        # (alle 30 Sekunden) auf Null zurueckfallen.
        if gesamt_stats:
            _letzter_scan_status["letzte_zahlen"] = _zahlen_zusammenfassen(gesamt_stats)
            _letzter_scan_status["meldungen"] = meldungen

        # Guenstige, idempotente Operation: haelt den 12-Monats-Horizont der
        # generierten Vorkommen unabhaengig von neuen CSV-Importen aktuell.
        ensure_forecast_vorkommen(db)
        db.commit()

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
