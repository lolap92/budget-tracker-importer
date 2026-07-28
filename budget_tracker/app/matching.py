"""Gemeinsame Matching-Logik zwischen realen Buchungen und offenen
FORECAST_VORKOMMEN (Betrags-/Datumstoleranz gemaess Konzept Abschnitt 6/12)."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import FORECAST_BETRAG_TOLERANZ, FORECAST_DATUM_TOLERANZ_TAGE
from app.models import Buchung, ForecastVorkommen


def verknuepftes_vorkommen(db: Session, buchung: Buchung) -> ForecastVorkommen | None:
    """Das FORECAST_VORKOMMEN, das diese Buchung als erledigt betrachtet.

    Invariante: eine Buchung gehoert zu hoechstens einem Vorkommen. Hier
    zentral, weil mehrere Stellen die Verknuepfung wieder loesen muessen
    (Buchung loeschen, in eine Topf-Umbuchung umwandeln, als Bank-Umbuchung
    markieren) und eine weitere sie gegen Doppelvergabe absichern muss.
    """
    return (
        db.query(ForecastVorkommen)
        .filter(ForecastVorkommen.verknuepfte_buchung_id == buchung.id)
        .first()
    )


def offene_vorkommen_query(db: Session, topf_id: int | None = None):
    q = db.query(ForecastVorkommen).filter(
        ForecastVorkommen.verknuepfte_buchung_id.is_(None),
        ForecastVorkommen.verknuepfte_topf_umbuchung_id.is_(None),
        ForecastVorkommen.ignoriert.is_(False),
    )
    if topf_id is not None:
        q = q.filter(ForecastVorkommen.topf_id == topf_id)
    return q


def finde_passendes_vorkommen(
    db: Session,
    buchung: Buchung,
    topf_id: int | None = None,
    nur_aus_regel: bool = False,
) -> ForecastVorkommen | None:
    kandidaten = offene_vorkommen_query(db, topf_id).all()
    if nur_aus_regel:
        kandidaten = [v for v in kandidaten if v.regel_id is not None]

    beste: ForecastVorkommen | None = None
    beste_tage_diff = None
    for v in kandidaten:
        betrag_diff = abs(Decimal(v.erwarteter_betrag) - Decimal(buchung.betrag))
        if betrag_diff > Decimal(FORECAST_BETRAG_TOLERANZ):
            continue
        tage_diff = abs((v.erwartetes_datum - buchung.datum).days)
        if tage_diff > FORECAST_DATUM_TOLERANZ_TAGE:
            continue
        if beste is None or tage_diff < beste_tage_diff:
            beste = v
            beste_tage_diff = tage_diff
    return beste
