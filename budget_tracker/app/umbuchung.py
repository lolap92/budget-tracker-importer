"""Bank-Umbuchungen: bidirektionaler, schwebender Zustand (Konzept Abschnitt 6).

Eine Umbuchung ist kein eigenes Konstrukt, sondern ein Self-Join auf
BUCHUNG. Solange sie nicht final zugeordnet ist (Abgleich mit
Gegenbuchung oder "endgueltig verbuchen"), bleibt topf_id NULL und sie
fliesst nicht in den Topf-Saldo ein.
"""
from sqlalchemy.orm import Session

from app.config import UMBUCHUNG_DATUM_TOLERANZ_TAGE
from app.models import Buchung


def markiere_als_umbuchung(db: Session, buchung: Buchung) -> None:
    buchung.ist_umbuchung = True
    buchung.umbuchung_richtung = "eingehend" if float(buchung.betrag) >= 0 else "ausgehend"
    buchung.topf_id = None
    buchung.zuordnung_quelle = None
    buchung.umbuchung_final = False
    buchung.gegenbuchung_id = None
    db.commit()


def entmarkiere_umbuchung(db: Session, buchung: Buchung) -> None:
    """Setzt eine faelschlich markierte Umbuchung zurueck und laesst die
    automatische Topf-Zuordnung erneut laufen."""
    from app.assignment import topf_zuordnen  # lokaler Import gegen Zirkelbezug

    if buchung.gegenbuchung_id is not None:
        gegenbuchung = db.get(Buchung, buchung.gegenbuchung_id)
        if gegenbuchung is not None:
            gegenbuchung.gegenbuchung_id = None
            gegenbuchung.topf_id = None
            gegenbuchung.ist_umbuchung = False
            gegenbuchung.umbuchung_richtung = None
            gegenbuchung.umbuchung_final = False
            topf_zuordnen(db, gegenbuchung)

    buchung.ist_umbuchung = False
    buchung.umbuchung_richtung = None
    buchung.gegenbuchung_id = None
    buchung.umbuchung_final = False
    buchung.topf_id = None
    topf_zuordnen(db, buchung)
    db.commit()


def offene_umbuchungen_query(db: Session):
    return db.query(Buchung).filter(
        Buchung.ist_umbuchung.is_(True),
        Buchung.topf_id.is_(None),
    )


def vorschlaege_fuer_abgleich(db: Session, buchung: Buchung) -> list[Buchung]:
    """Offene Umbuchungen mit gegensaetzlichem Vorzeichen und naher
    Betrags-/Datumsuebereinstimmung."""
    kandidaten = (
        offene_umbuchungen_query(db)
        .filter(Buchung.id != buchung.id)
        .all()
    )
    eigenes_vorzeichen = float(buchung.betrag) >= 0
    treffer = []
    for k in kandidaten:
        anderes_vorzeichen = float(k.betrag) >= 0
        if anderes_vorzeichen == eigenes_vorzeichen:
            continue
        if abs(abs(float(k.betrag)) - abs(float(buchung.betrag))) > 0.01:
            continue
        if abs((k.datum - buchung.datum).days) > UMBUCHUNG_DATUM_TOLERANZ_TAGE:
            continue
        treffer.append(k)
    treffer.sort(key=lambda k: abs((k.datum - buchung.datum).days))
    return treffer


def abgleichen(db: Session, buchung_a: Buchung, buchung_b: Buchung, topf_id: int) -> None:
    if not (buchung_a.ist_umbuchung and buchung_b.ist_umbuchung):
        raise ValueError("Beide Buchungen muessen als Umbuchung markiert sein.")
    if buchung_a.topf_id is not None or buchung_b.topf_id is not None:
        raise ValueError("Mindestens eine der Buchungen ist bereits final zugeordnet.")
    if (float(buchung_a.betrag) >= 0) == (float(buchung_b.betrag) >= 0):
        raise ValueError("Abgleich erfordert entgegengesetzte Vorzeichen.")

    buchung_a.topf_id = topf_id
    buchung_b.topf_id = topf_id
    buchung_a.gegenbuchung_id = buchung_b.id
    buchung_b.gegenbuchung_id = buchung_a.id
    buchung_a.zuordnung_quelle = "manuell"
    buchung_b.zuordnung_quelle = "manuell"
    db.commit()


def endgueltig_verbuchen(db: Session, buchung: Buchung, topf_id: int) -> None:
    if not buchung.ist_umbuchung:
        raise ValueError("Buchung ist nicht als Umbuchung markiert.")
    buchung.topf_id = topf_id
    buchung.umbuchung_final = True
    buchung.zuordnung_quelle = "manuell"
    db.commit()
