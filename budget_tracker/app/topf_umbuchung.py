"""Topf-Umbuchung: sofort wirksame, virtuelle Verschiebung zwischen zwei
Toepfen ohne reale Bankbuchung (Konzept Abschnitt 6). Zu unterscheiden
von der (Bank-)Umbuchung in app/umbuchung.py."""
import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.manual_entry import ist_zu_umbuchung_konvertierbar
from app.matching import verknuepftes_vorkommen
from app.models import Buchung, TopfUmbuchung


def erstelle_topf_umbuchung(
    db: Session,
    von_topf_id: int,
    nach_topf_id: int,
    betrag,
    datum: dt.date | None = None,
    kommentar: str | None = None,
) -> TopfUmbuchung:
    if von_topf_id == nach_topf_id:
        raise ValueError("Quell- und Zieltopf muessen unterschiedlich sein.")
    if float(betrag) <= 0:
        raise ValueError("Betrag muss groesser als 0 sein.")

    # Eine Topf-Umbuchung wirkt sofort: saldo_topf() summiert sie ohne
    # Datumsbedingung, das Datum ist reine Dokumentation. Ein Datum in der
    # Zukunft wuerde deshalb Geld verschieben, das laut Anzeige erst spaeter
    # umzieht - und der Eintrag laege in der Zeitachse unterhalb des
    # "Aktueller Monat"-Trenners, obwohl er in der Zukunft datiert ist.
    if datum is not None and datum > dt.date.today():
        raise ValueError(
            "Eine Topf-Umbuchung wirkt sofort und kann kein Datum in der Zukunft haben."
        )

    umbuchung = TopfUmbuchung(
        von_topf_id=von_topf_id,
        nach_topf_id=nach_topf_id,
        betrag=betrag,
        datum=datum or dt.date.today(),
        kommentar=kommentar or None,
    )
    db.add(umbuchung)
    db.commit()
    return umbuchung


def buchung_zu_topf_umbuchung(db: Session, buchung: Buchung, gegen_topf_id: int) -> TopfUmbuchung:
    """Wandelt eine manuell erfasste Buchung nachtraeglich in eine Topf-
    Umbuchung um - fuer den Fall, dass sich zeigt, dass eine als reale
    Bewegung erfasste Buchung eigentlich nur eine virtuelle Verschiebung
    zwischen zwei Toepfen war. Ersetzt die Buchung 1:1 durch eine
    gleichwertige Topf-Umbuchung; Richtung wird aus dem Vorzeichen des
    bisherigen Topfs abgeleitet."""
    if not ist_zu_umbuchung_konvertierbar(buchung):
        raise ValueError(
            "Nur manuell erfasste, einem Topf zugewiesene Buchungen lassen sich "
            "in eine Topf-Umbuchung umwandeln."
        )
    if gegen_topf_id == buchung.topf_id:
        raise ValueError("Quell- und Zieltopf muessen unterschiedlich sein.")

    betrag = abs(Decimal(buchung.betrag))
    if float(buchung.betrag) >= 0:
        von_topf_id, nach_topf_id = gegen_topf_id, buchung.topf_id
    else:
        von_topf_id, nach_topf_id = buchung.topf_id, gegen_topf_id

    umbuchung = TopfUmbuchung(
        von_topf_id=von_topf_id,
        nach_topf_id=nach_topf_id,
        betrag=betrag,
        datum=buchung.datum,
        kommentar=buchung.titel or buchung.verwendungszweck or buchung.beschreibung,
    )
    db.add(umbuchung)

    vorkommen = verknuepftes_vorkommen(db, buchung)
    if vorkommen is not None:
        vorkommen.verknuepfte_buchung_id = None

    db.delete(buchung)
    db.commit()
    return umbuchung
