"""Manuelle Erfassung vergangener Buchungen direkt ueber die Buchungen-
Uebersicht - fuer den Fall, dass eine reale Kontobewegung schon bekannt
ist, bevor der naechste CSV-Export sie liefert. Bekommt eine synthetische
transaction_id (Praefix "manual-"), damit sie den echten CSV-Import nie
blockiert; sollte dieselbe Bewegung spaeter per CSV eintreffen, bleibt sie
als eigene Buchung bestehen und muss manuell entfernt werden, um doppelte
Zaehlung zu vermeiden.

Loeschbar sind zwei Faelle: jede manuell erfasste Buchung (jederzeit, da
sie kein CSV-Fakt ist), sowie reale, importierte Buchungen, solange sie
noch offen (keinem Topf zugeordnet) und keine Umbuchung sind - fuer
Karteileichen wie Test-Buchungen, die nie sinnvoll zuzuordnen sind. Eine
bereits einem Topf zugeordnete, reale Buchung bleibt unloeschbar, da sie
in den Topf-Saldo eingeflossen ist."""
import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.matching import verknuepftes_vorkommen
from app.models import Buchung, Konfiguration

MANUAL_PREFIX = "manual-"


def ist_manuelle_buchung(buchung: Buchung) -> bool:
    return buchung.transaction_id.startswith(MANUAL_PREFIX)


def ist_loeschbar(buchung: Buchung) -> bool:
    if ist_manuelle_buchung(buchung):
        return True
    return (
        buchung.topf_id is None
        and not buchung.ist_umbuchung
        and buchung.datum <= dt.date.today()
    )


def ist_zu_umbuchung_konvertierbar(buchung: Buchung) -> bool:
    """Nur manuell erfasste, einem Topf zugewiesene Buchungen lassen sich
    nachtraeglich in eine Topf-Umbuchung umwandeln - reale CSV-Buchungen
    sind unveraenderliches Bankfaktum und muessten sonst als real
    verbuchtes Geld aus dem Kontostand verschwinden."""
    return (
        ist_manuelle_buchung(buchung)
        and buchung.topf_id is not None
        and not buchung.ist_umbuchung
    )


def erstelle_manuelle_buchung(
    db: Session, topf_id: int, bezeichnung: str, betrag: Decimal, datum: dt.date
) -> Buchung:
    if datum > dt.date.today():
        raise ValueError("Eine vergangene Buchung kann kein Datum in der Zukunft haben.")

    # Gleiche Begruendung wie beim CSV-Import: vor dem Startdatum ist der
    # Topf-Startsaldo die Wahrheit, eine zusaetzliche Buchung zaehlt doppelt.
    konfiguration = db.query(Konfiguration).first()
    if konfiguration is not None and datum < konfiguration.start_datum:
        raise ValueError(
            f"Datum liegt vor dem Startdatum ({konfiguration.start_datum.strftime('%d.%m.%Y')}) - "
            "Bewegungen davor stecken bereits im Topf-Startsaldo."
        )

    buchung = Buchung(
        transaction_id=f"{MANUAL_PREFIX}{uuid.uuid4()}",
        datum=datum,
        typ="MANUELL",
        betrag=betrag,
        titel=bezeichnung,
        topf_id=topf_id,
        zuordnung_quelle="manuell",
        importiert_am=dt.datetime.utcnow(),
    )
    db.add(buchung)
    db.commit()
    return buchung


def loesche_buchung(db: Session, buchung: Buchung) -> None:
    if not ist_loeschbar(buchung):
        raise ValueError(
            "Diese Buchung kann nicht geloescht werden - nur manuell erfasste oder "
            "noch nicht zugeordnete Buchungen sind loeschbar."
        )

    if buchung.gegenbuchung_id is not None:
        gegenbuchung = db.get(Buchung, buchung.gegenbuchung_id)
        if gegenbuchung is not None:
            gegenbuchung.gegenbuchung_id = None
            gegenbuchung.topf_id = None
            gegenbuchung.umbuchung_final = False

    vorkommen = verknuepftes_vorkommen(db, buchung)
    if vorkommen is not None:
        vorkommen.verknuepfte_buchung_id = None

    db.delete(buchung)
    db.commit()
