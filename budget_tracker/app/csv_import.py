"""CSV-Import gemaess Konzept Abschnitt 7.

Quelle: Trade-Republic-Umsatzexport mit den Spalten transaction_id, date,
type, amount, payment_reference, counterparty_name, counterparty_iban,
description (der reale Export bringt weitere Spalten mit, die ungenutzt
bleiben). Dedublizierung ausschliesslich ueber transaction_id.

Hier steht ausschliesslich, was mit *Dateien* zu tun hat: Encoding, Trennzeichen,
Zahlenformat, Datums- und Betragsparsing. Was danach mit einer gelesenen Zeile
passiert - Dedublizierung, Startdatum, Topf-Zuordnung - steht in
app/import_core.py und wird mit der Trade-Republic-Schnittstelle geteilt.
"""
import csv
import datetime as dt
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.orm import Session

from app.import_core import QUELLE_CSV, ImportKontext, uebernehmen

logger = logging.getLogger("budget_tracker.csv_import")

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


def _bereinigt(value: str) -> str:
    return (value or "").strip().replace("€", "").replace(" ", "").replace(" ", "")


# "1.234" ist fuer sich genommen nicht entscheidbar: englisch gelesen sind es
# 1,234 (gerundet 1,23 EUR), deutsch gelesen 1.234 EUR - ein Faktor 1000.
_MEHRDEUTIG = re.compile(r"^-?\d{1,3}\.\d{3}$")


def zahlenformat(werte: list[str]) -> str | None:
    """Leitet aus allen Betraegen einer Datei ab, ob sie deutsch oder englisch
    formatiert sind. Einzelne Werte sind teils mehrdeutig, die Datei als
    Ganzes fast nie: es genuegt ein Wert mit eindeutigem Dezimaltrenner.
    """
    for roh in werte:
        v = _bereinigt(roh)
        if "," in v and "." in v:
            return "deutsch" if v.rfind(",") > v.rfind(".") else "englisch"
        if re.search(r",\d{1,2}$", v):
            return "deutsch"
        if re.search(r"\.\d{1,2}$", v):
            return "englisch"
        if re.search(r",\d{3}(?:\D|$)", v):
            return "englisch"  # Komma als Tausendertrenner
    return None


def _parse_betrag(value: str, format_hinweis: str | None = None) -> Decimal | None:
    value = _bereinigt(value)
    if not value:
        return None

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    elif _MEHRDEUTIG.match(value):
        # Nur der Dateikontext kann das aufloesen. Ohne ihn wird die Zeile
        # bewusst verworfen statt geraten - ein um Faktor 1000 falscher Betrag
        # faellt in keiner Summe auf.
        if format_hinweis == "deutsch":
            value = value.replace(".", "")
        elif format_hinweis != "englisch":
            logger.warning(
                "Betrag %r ist ohne Dateikontext nicht eindeutig (1.234 EUR oder 1,234 EUR?).",
                value,
            )
            return None

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
    stats = {
        "datei": str(pfad),
        "gelesen": 0,
        "neu": 0,
        "duplikate": 0,
        "vor_startdatum": 0,
        "verdacht": 0,
        "fehler": 0,
        "meldung": None,  # Klartext fuer die Import-Anzeige, sonst nur im Log
    }

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
        stats["meldung"] = "kein passendes Spaltenformat"
        return stats

    # Erst komplett einlesen: das Zahlenformat laesst sich nur aus der ganzen
    # Datei ableiten, nicht aus einer einzelnen Zeile (siehe zahlenformat()).
    zeilen = list(reader)
    format_hinweis = zahlenformat([(z.get("amount") or "") for z in zeilen])
    if format_hinweis is None and zeilen:
        logger.info("Zahlenformat von %s nicht eindeutig bestimmbar.", pfad.name)

    kontext = ImportKontext.laden(db)

    for row in zeilen:
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

        if kontext.ist_bekannt(transaction_id):
            stats["duplikate"] += 1
            continue

        datum = _parse_datum(row.get("date", ""))
        betrag = _parse_betrag(row.get("amount", ""), format_hinweis)
        if datum is None or betrag is None:
            logger.warning("Zeile mit transaction_id=%s uebersprungen (Datum/Betrag ungueltig).", transaction_id)
            stats["fehler"] += 1
            continue

        ergebnis = uebernehmen(
            db,
            kontext,
            transaction_id=transaction_id,
            datum=datum,
            betrag=betrag,
            typ=row.get("type", ""),
            quelle=QUELLE_CSV,
            verwendungszweck=row.get("payment_reference"),
            empfaenger_name=row.get("counterparty_name"),
            empfaenger_iban=row.get("counterparty_iban"),
            beschreibung=row.get("description"),
        )
        stats[ergebnis] += 1

    db.commit()
    logger.info(
        "%s: %d gelesen, %d neu, %d Duplikate, %d vor Startdatum, %d fehlerhaft.",
        pfad.name,
        stats["gelesen"],
        stats["neu"],
        stats["duplikate"],
        stats["vor_startdatum"],
        stats["fehler"],
    )
    return stats
