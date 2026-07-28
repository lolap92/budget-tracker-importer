"""Bank-Umbuchungen: bidirektionaler, schwebender Zustand (Konzept Abschnitt 6).

Eine Umbuchung ist kein eigenes Konstrukt, sondern ein Self-Join auf
BUCHUNG. Solange sie nicht final zugeordnet ist (Abgleich mit
Gegenbuchung oder "endgueltig verbuchen"), bleibt topf_id NULL und sie
fliesst nicht in den Topf-Saldo ein.
"""
from sqlalchemy.orm import Session

from app.config import UMBUCHUNG_DATUM_TOLERANZ_TAGE
from app.matching import verknuepftes_vorkommen
from app.models import Buchung


def markiere_als_umbuchung(db: Session, buchung: Buchung) -> None:
    """Erklaert eine reale Buchung zur (Bank-)Umbuchung: sie verlaesst den Topf
    und schwebt, bis sie abgeglichen oder endgueltig verbucht wird.

    Hat bisher ein FORECAST_VORKOMMEN diese Buchung als seine Erfuellung
    betrachtet, wird es dabei wieder freigegeben. Die Markierung sagt ja
    gerade aus, dass es sich nicht um die erwartete Ausgabe handelte, sondern
    um eine Verschiebung, die sich mit ihrer Gegenbuchung ausgleicht - die
    Erwartung steht also weiter aus und gehoert zurueck in die Prognose.
    Ohne diese Freigabe verschwaende der Betrag vollstaendig: die Buchung
    zaehlt nicht mehr im Topf-Saldo, das Vorkommen gilt weiter als gebucht.

    Erwarteter Betrag und Datum des Vorkommens bleiben auf den Werten der
    Buchung stehen - der urspruenglich geplante Termin ist beim Verknuepfen
    ueberschrieben worden. Beim automatischen Abgleich ist der Betrag ohnehin
    identisch (FORECAST_BETRAG_TOLERANZ = 0) und das Datum hoechstens um die
    Datumstoleranz verschoben; bei Bedarf laesst sich das Vorkommen auf der
    Forecast-Seite bearbeiten.
    """
    vorkommen = verknuepftes_vorkommen(db, buchung)
    if vorkommen is not None:
        vorkommen.verknuepfte_buchung_id = None

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
    if buchung.gegenbuchung_id is not None:
        raise ValueError(
            "Diese Umbuchung ist bereits mit einer Gegenbuchung abgeglichen. "
            "Dafuer zuerst die Markierung zuruecksetzen."
        )
    if buchung.topf_id is not None:
        raise ValueError("Diese Umbuchung ist bereits einem Topf zugeordnet.")
    buchung.topf_id = topf_id
    buchung.umbuchung_final = True
    buchung.zuordnung_quelle = "manuell"
    db.commit()
