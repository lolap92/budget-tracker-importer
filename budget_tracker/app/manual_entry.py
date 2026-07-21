"""Manuelle Erfassung vergangener Buchungen direkt ueber die Buchungen-
Uebersicht - fuer den Fall, dass eine reale Kontobewegung schon bekannt
ist, bevor der naechste CSV-Export sie liefert. Bekommt eine synthetische
transaction_id (Praefix "manual-"), damit sie den echten CSV-Import nie
blockiert; sollte dieselbe Bewegung spaeter per CSV eintreffen, bleibt sie
als eigene Buchung bestehen und muss manuell entfernt werden, um doppelte
Zaehlung zu vermeiden - dafuer laesst sich eine manuelle Buchung wieder
loeschen, eine echte importierte nie."""
import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Buchung

MANUAL_PREFIX = "manual-"


def ist_manuelle_buchung(buchung: Buchung) -> bool:
    return buchung.transaction_id.startswith(MANUAL_PREFIX)


def erstelle_manuelle_buchung(
    db: Session, topf_id: int, bezeichnung: str, betrag: Decimal, datum: dt.date
) -> Buchung:
    if datum > dt.date.today():
        raise ValueError("Eine vergangene Buchung kann kein Datum in der Zukunft haben.")

    buchung = Buchung(
        transaction_id=f"{MANUAL_PREFIX}{uuid.uuid4()}",
        datum=datum,
        typ="MANUELL",
        betrag=betrag,
        verwendungszweck=bezeichnung,
        topf_id=topf_id,
        zuordnung_quelle="manuell",
        importiert_am=dt.datetime.utcnow(),
    )
    db.add(buchung)
    db.commit()
    return buchung


def loesche_manuelle_buchung(db: Session, buchung: Buchung) -> None:
    if not ist_manuelle_buchung(buchung):
        raise ValueError("Nur manuell erfasste Buchungen koennen geloescht werden.")

    if buchung.gegenbuchung_id is not None:
        gegenbuchung = db.get(Buchung, buchung.gegenbuchung_id)
        if gegenbuchung is not None:
            gegenbuchung.gegenbuchung_id = None
            gegenbuchung.topf_id = None
            gegenbuchung.umbuchung_final = False

    db.delete(buchung)
    db.commit()
