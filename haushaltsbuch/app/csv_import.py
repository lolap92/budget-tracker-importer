"""CSV-Import gemaess Konzept Abschnitt 7.

Quelle: Trade-Republic-Umsatzexport mit den Spalten transaction_id, date,
type, amount, payment_reference, counterparty_name, counterparty_iban,
description. Dedublizierung ausschliesslich ueber transaction_id.
"""
import csv
import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assignment import topf_zuordnen
from app.models import Buchung

logger = logging.getLogger("haushaltsbuch.csv_import")

REQUIRED_COLUMNS = {"transaction_id", "date", "type", "amount"}


def _parse_datum(value: str) -> dt.date | None:
    value = (value or "").strip()
    if not value:
        return None
    # ISO-Datum, optional mit Uhrzeit/Zeitzone (z.B. aus dem CSV-Export)
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Konnte Datum nicht parsen: %r", value)
    return None


def _parse_betrag(value: str) -> Decimal | None:
    value = (value or "").strip().replace("€", "").replace(" ", "")
    if not value:
        return None
    if "," in value and "." in value:
        # 1.234,56 -> deutsches Format
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        logger.warning("Konnte Betrag nicht parsen: %r", value)
        return None


def _sniff_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        class _Fallback(csv.excel):
            delimiter = ";" if sample.count(";") > sample.count(",") else ","

        return _Fallback


def import_csv_datei(db: Session, pfad: Path) -> dict:
    """Importiert eine einzelne CSV-Datei. Gibt eine kleine Statistik zurueck."""
    stats = {"datei": str(pfad), "gelesen": 0, "neu": 0, "duplikate": 0, "fehler": 0}

    try:
        rohtext = pfad.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        rohtext = pfad.read_text(encoding="latin-1")

    if not rohtext.strip():
        return stats

    dialect = _sniff_dialect(rohtext[:2048])
    reader = csv.DictReader(rohtext.splitlines(), dialect=dialect)
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(
        {f.strip() for f in reader.fieldnames}
    ):
        logger.error("Datei %s hat kein passendes Spaltenformat, wird uebersprungen.", pfad)
        stats["fehler"] += 1
        return stats

    vorhandene_ids = {row[0] for row in db.query(Buchung.transaction_id).all()}

    for row in reader:
        stats["gelesen"] += 1
        row = {
            (k or "").strip(): ((v[0] if isinstance(v, list) else v) or "").strip()
            for k, v in row.items()
            if k is not None
        }

        transaction_id = row.get("transaction_id")
        if not transaction_id:
            stats["fehler"] += 1
            continue

        if transaction_id in vorhandene_ids:
            stats["duplikate"] += 1
            continue

        datum = _parse_datum(row.get("date", ""))
        betrag = _parse_betrag(row.get("amount", ""))
        if datum is None or betrag is None:
            logger.warning("Zeile mit transaction_id=%s uebersprungen (Datum/Betrag ungueltig).", transaction_id)
            stats["fehler"] += 1
            continue

        buchung = Buchung(
            transaction_id=transaction_id,
            datum=datum,
            typ=row.get("type", ""),
            betrag=betrag,
            verwendungszweck=row.get("payment_reference") or None,
            empfaenger_name=row.get("counterparty_name") or None,
            empfaenger_iban=row.get("counterparty_iban") or None,
            beschreibung=row.get("description") or None,
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(buchung)
        try:
            db.flush()
        except IntegrityError:
            # Race/erneuter Import derselben transaction_id -> Wert ignorieren, warnen.
            db.rollback()
            logger.warning("transaction_id %s bereits vorhanden (Integritaetsfehler), ignoriert.", transaction_id)
            stats["duplikate"] += 1
            continue

        topf_zuordnen(db, buchung)
        vorhandene_ids.add(transaction_id)
        stats["neu"] += 1

    db.commit()
    return stats
