"""First-Start-Bootstrap gemaess Konzept Abschnitt 8.

Beim allerersten Start (noch keine KONFIGURATION vorhanden) wird zuerst
/homeassistant/budget_tracker/seed-data.json gesucht. Existiert sie,
werden Konfiguration, Toepfe und Forecast-Regeln daraus uebernommen.
Andernfalls bleibt die App im Bootstrap-Zustand, bis die Werte ueber die
First-Start-Seite eingegeben wurden.

seed-data.json enthaelt private Daten, wird nie veraendert und nie committet.
"""
import datetime as dt
import json
import logging

from sqlalchemy.orm import Session

from app.config import DEFAULT_IMPORT_DIR, SEED_FILE, TOPF_NAMEN
from app.forecast_engine import ensure_forecast_vorkommen
from app.models import ForecastRegel, Konfiguration, Topf

logger = logging.getLogger("haushaltsbuch.bootstrap")


def ist_bootstrapped(db: Session) -> bool:
    return db.query(Konfiguration).first() is not None


def _parse_date_optional(value) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def seed_datei_vorhanden() -> bool:
    return SEED_FILE.exists()


def bootstrap_aus_seed_datei(db: Session) -> bool:
    """Liest seed-data.json ein, falls vorhanden. Gibt True zurueck, wenn ausgefuehrt."""
    if not SEED_FILE.exists():
        return False

    try:
        daten = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"seed-data.json konnte nicht gelesen werden: {exc}") from exc

    konf = daten.get("konfiguration", {})
    start_datum = _parse_date_optional(konf.get("start_datum"))
    if start_datum is None:
        raise ValueError("seed-data.json: konfiguration.start_datum fehlt oder ist ungueltig.")
    import_verzeichnis = konf.get("import_verzeichnis") or DEFAULT_IMPORT_DIR

    db.add(Konfiguration(start_datum=start_datum, import_verzeichnis=import_verzeichnis))

    name_zu_id: dict[str, int] = {}
    for i, topf_daten in enumerate(daten.get("toepfe", [])):
        topf = Topf(
            name=topf_daten["name"],
            startsaldo=topf_daten.get("startsaldo", 0),
            jahresziel=topf_daten.get("jahresziel"),
            sondertilgung_datum=_parse_date_optional(topf_daten.get("sondertilgung_datum")),
            reihenfolge=topf_daten.get("reihenfolge", i),
        )
        db.add(topf)
        db.flush()
        name_zu_id[topf.name] = topf.id

    for regel_daten in daten.get("regeln", []):
        topf_name = regel_daten["topf"]
        if topf_name not in name_zu_id:
            raise ValueError(f"seed-data.json: Regel referenziert unbekannten Topf '{topf_name}'.")
        db.add(
            ForecastRegel(
                topf_id=name_zu_id[topf_name],
                bezeichnung=regel_daten["bezeichnung"],
                betrag=regel_daten["betrag"],
                rhythmus=regel_daten["rhythmus"],
                anker_tag=regel_daten["anker_tag"],
                start_datum=dt.date.fromisoformat(regel_daten["start_datum"]),
                end_datum=_parse_date_optional(regel_daten.get("end_datum")),
            )
        )

    db.flush()
    ensure_forecast_vorkommen(db)
    db.commit()
    logger.info("Bootstrap aus seed-data.json abgeschlossen (%d Toepfe, %d Regeln).", len(name_zu_id), len(daten.get("regeln", [])))
    return True


def bootstrap_manuell(db: Session, start_datum: dt.date, topf_startsalden: dict[str, float]) -> None:
    """First-Start-Bootstrap-Seite: Startdatum + die vier Topf-Startsalden."""
    db.add(Konfiguration(start_datum=start_datum, import_verzeichnis=DEFAULT_IMPORT_DIR))
    for i, name in enumerate(TOPF_NAMEN):
        db.add(Topf(name=name, startsaldo=topf_startsalden.get(name, 0) or 0, reihenfolge=i))
    db.commit()


def bootstrap_falls_noetig(db: Session) -> None:
    if ist_bootstrapped(db):
        return
    try:
        ausgefuehrt = bootstrap_aus_seed_datei(db)
        if ausgefuehrt:
            return
    except ValueError:
        logger.exception("seed-data.json vorhanden, konnte aber nicht verarbeitet werden.")
        db.rollback()
    logger.info("Keine seed-data.json gefunden - warte auf manuellen Bootstrap ueber die UI.")
