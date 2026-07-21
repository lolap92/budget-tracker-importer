"""Erzeugung von FORECAST_VORKOMMEN aus FORECAST_REGEL sowie die drei
Wege, ein offenes Vorkommen aufzuloesen (Konzept Abschnitt 6)."""
import datetime as dt

from sqlalchemy.orm import Session

from app.config import FORECAST_HORIZON_MONATE, SONDERAUSGABEN_TOPF
from app.dateutils import add_months, safe_date
from app.models import ForecastRegel, ForecastVorkommen, Topf, TopfUmbuchung


def _occurrence_dates(regel: ForecastRegel, horizon_end: dt.date) -> list[dt.date]:
    dates: list[dt.date] = []
    if regel.rhythmus in ("monatlich", "befristet"):
        d = safe_date(regel.start_datum.year, regel.start_datum.month, regel.anker_tag)
        if d < regel.start_datum:
            d = add_months(d, 1)
        while d <= horizon_end:
            if regel.end_datum and d > regel.end_datum:
                break
            dates.append(d)
            d = add_months(d, 1)
    elif regel.rhythmus == "jaehrlich":
        year = regel.start_datum.year
        while True:
            d = safe_date(year, regel.start_datum.month, regel.anker_tag)
            if d > horizon_end:
                break
            if d >= regel.start_datum and (not regel.end_datum or d <= regel.end_datum):
                dates.append(d)
            year += 1
    return dates


def ensure_forecast_vorkommen(
    db: Session, heute: dt.date | None = None, horizon_monate: int = FORECAST_HORIZON_MONATE
) -> int:
    """Legt fuer jede aktive Regel die noch fehlenden Vorkommen bis zum Horizont an.

    Erkennung von "bereits generiert" laeuft ueber ein Zeitfenster um die
    berechnete Erwartung (deckt ein einmaliges manuelles Verschieben um
    einen Monat ab), da keine zusaetzliche Spalte im Datenmodell vorgesehen ist.
    """
    heute = heute or dt.date.today()
    horizon_end = add_months(heute, horizon_monate)
    erzeugt = 0

    for regel in db.query(ForecastRegel).all():
        vorhandene = db.query(ForecastVorkommen).filter(ForecastVorkommen.regel_id == regel.id).all()
        for d in _occurrence_dates(regel, horizon_end):
            fenster_start = d - dt.timedelta(days=20)
            fenster_ende = add_months(d, 1) + dt.timedelta(days=10)
            bereits_vorhanden = any(
                fenster_start <= v.erwartetes_datum <= fenster_ende for v in vorhandene
            )
            if bereits_vorhanden:
                continue
            neues_vorkommen = ForecastVorkommen(
                regel_id=regel.id,
                topf_id=regel.topf_id,
                bezeichnung=regel.bezeichnung,
                erwarteter_betrag=regel.betrag,
                erwartetes_datum=d,
            )
            db.add(neues_vorkommen)
            vorhandene.append(neues_vorkommen)
            erzeugt += 1

    if erzeugt:
        db.flush()
    return erzeugt


def vorkommen_verschieben(vorkommen: ForecastVorkommen) -> None:
    """Manuelles Verschieben um einen Monat nach hinten - aktualisiert nur erwartetes_datum."""
    vorkommen.erwartetes_datum = add_months(vorkommen.erwartetes_datum, 1)


def vorkommen_auf_sonderausgaben_buchen(db: Session, vorkommen: ForecastVorkommen) -> TopfUmbuchung:
    """Dritte Aufloesungsoption fuer ausgehende Vorkommen: statt auf eine reale
    Buchung zu warten, wird der Betrag per TOPF_UMBUCHUNG nach Sonderausgaben verschoben."""
    if float(vorkommen.erwarteter_betrag) >= 0:
        raise ValueError("Nur ausgehende (negative) Vorkommen koennen auf Sonderausgaben gebucht werden.")

    sonderausgaben = db.query(Topf).filter(Topf.name == SONDERAUSGABEN_TOPF).first()
    if sonderausgaben is None:
        raise ValueError("Topf 'Sonderausgaben' existiert nicht.")
    if vorkommen.topf_id == sonderausgaben.id:
        raise ValueError("Vorkommen gehoert bereits zu Sonderausgaben.")

    umbuchung = TopfUmbuchung(
        von_topf_id=vorkommen.topf_id,
        nach_topf_id=sonderausgaben.id,
        betrag=abs(vorkommen.erwarteter_betrag),
        datum=dt.date.today(),
        kommentar=f"Forecast-Aufloesung: {vorkommen.bezeichnung}",
    )
    db.add(umbuchung)
    db.flush()
    vorkommen.verknuepfte_topf_umbuchung_id = umbuchung.id
    return umbuchung
