"""Erkennt dieselbe Kontobewegung unter zwei verschiedenen transaction_ids.

Der Datei-Import und die Schnittstelle beziehen ihre Daten aus zwei
verschiedenen Diensten von Trade Republic. Dass beide dieselbe Bewegung unter
derselben ID fuehren, ist wahrscheinlich, aber nicht garantiert - schon die
Typbezeichnungen unterscheiden sich (der Export sagt TRANSFER_INBOUND, die
Timeline INCOMING_TRANSFER). Waere die ID verschieden, wuerde die
Dedublizierung ueber transaction_id ins Leere greifen und jede Bewegung doppelt
zaehlen.

Diese Pruefung ist die zweite Verteidigungslinie. Sie schlaegt bewusst *nicht*
selbst zu, sondern legt einen Verdacht an: sowohl stilles Importieren (Betrag
doppelt) als auch stilles Verwerfen (Betrag weg) waeren falsch, wenn die
Vermutung nicht stimmt.

Der schaerfste verfuegbare Hinweis steckt in der ID selbst: Trade Republic
vergibt UUIDs der Version 7, und deren erste 48 Bit sind der
Erzeugungszeitpunkt in Millisekunden. Bei den Zeilen des CSV-Exports stimmt er
exakt mit dem Buchungszeitstempel ueberein. Zwei IDs, deren Zeitstempel
Sekundenbruchteile auseinanderliegen und die denselben Betrag tragen, gehoeren
zur selben Bewegung.
"""
import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Buchung

logger = logging.getLogger("budget_tracker.dopplung")

# Zeitfenster fuer den Vergleich zweier UUIDv7-Zeitstempel. Beide Dienste
# vergeben ihre ID beim Verbuchen desselben Vorgangs, aber nicht in derselben
# Millisekunde.
UUID7_TOLERANZ = dt.timedelta(seconds=5)

# Ohne verwertbare Zeitstempel bleibt nur der grobe Vergleich: gleicher Betrag
# innerhalb weniger Tage. Das erzeugt eher einen Verdacht zu viel als einen zu
# wenig - was hier die richtige Richtung ist.
DATUM_TOLERANZ_TAGE = 5


def uuid7_zeitpunkt(transaction_id: str) -> dt.datetime | None:
    """Der in einer UUIDv7 eingebettete Erzeugungszeitpunkt (UTC), oder None,
    wenn die ID keine UUIDv7 ist (z.B. die synthetischen 'manual-'-IDs)."""
    roh = (transaction_id or "").replace("-", "")
    if len(roh) != 32:
        return None
    try:
        version = int(roh[12], 16)
        millisekunden = int(roh[:12], 16)
    except ValueError:
        return None
    if version != 7:
        return None
    try:
        return dt.datetime.utcfromtimestamp(millisekunden / 1000)
    except (OverflowError, OSError, ValueError):
        return None


def _zeitlich_identisch(a: str, b: str) -> bool:
    zeit_a, zeit_b = uuid7_zeitpunkt(a), uuid7_zeitpunkt(b)
    if zeit_a is None or zeit_b is None:
        return False
    return abs(zeit_a - zeit_b) <= UUID7_TOLERANZ


def finde_moegliche_dopplung(
    db: Session,
    *,
    transaction_id: str,
    datum: dt.date,
    betrag: Decimal,
    quelle: str,
) -> Buchung | None:
    """Sucht eine bestehende Buchung, die dieselbe reale Bewegung sein duerfte.

    Verglichen wird nur mit Buchungen aus einer *anderen* Quelle: zwei Zeilen
    derselben Quelle mit gleichem Betrag am selben Tag sind der Normalfall
    (zweimal tanken, zweimal dieselbe Rate) und ueber die transaction_id
    ohnehin sauber getrennt.
    """
    kandidaten = (
        db.query(Buchung)
        .filter(
            Buchung.betrag == betrag,
            Buchung.quelle != quelle,
            Buchung.transaction_id != transaction_id,
            Buchung.datum >= datum - dt.timedelta(days=DATUM_TOLERANZ_TAGE),
            Buchung.datum <= datum + dt.timedelta(days=DATUM_TOLERANZ_TAGE),
        )
        .order_by(Buchung.datum)
        .all()
    )
    if not kandidaten:
        return None

    # Ein Treffer ueber die eingebetteten Zeitstempel ist der belastbarste -
    # er geht allen anderen vor.
    for kandidat in kandidaten:
        if _zeitlich_identisch(transaction_id, kandidat.transaction_id):
            return kandidat

    # Sonst der zeitlich naechste Kandidat. Dass ueberhaupt einer existiert,
    # genuegt fuer einen Verdacht; welcher genau es ist, entscheidet ohnehin
    # der Mensch.
    return min(kandidaten, key=lambda b: abs((b.datum - datum).days))
