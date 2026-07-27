"""Erzeugung von FORECAST_VORKOMMEN aus FORECAST_REGEL sowie die Wege,
ein offenes Vorkommen aufzuloesen oder zu verwerfen (Konzept Abschnitt 6)."""
import datetime as dt

from sqlalchemy.orm import Session

from app.config import FORECAST_HORIZON_MONATE, SONDERAUSGABEN_TOPF
from app.dateutils import add_months, safe_date
from app.models import Buchung, ForecastRegel, ForecastVorkommen, Topf, TopfUmbuchung


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


def erstelle_manuelles_vorkommen(db: Session, topf_id: int, bezeichnung: str, betrag, datum: dt.date) -> ForecastVorkommen:
    """Freie, einmalige geplante Buchung ohne Regel - wird spaeter automatisch
    mit einer realen CSV-Buchung abgeglichen (Konzept Abschnitt 6)."""
    vorkommen = ForecastVorkommen(
        regel_id=None,
        topf_id=topf_id,
        bezeichnung=bezeichnung,
        erwarteter_betrag=betrag,
        erwartetes_datum=datum,
    )
    db.add(vorkommen)
    db.commit()
    return vorkommen


def vorkommen_manuell_verknuepfen(db: Session, vorkommen: ForecastVorkommen, buchung: Buchung) -> None:
    """Manuelle Verknuepfung mit einer realen CSV-Buchung - fuer Faelle, in denen
    die automatische Betrags-/Datumstoleranz keinen Treffer gefunden hat.
    Wirkt wie ein automatischer Treffer: das Vorkommen uebernimmt Betrag/Datum
    der Buchung, die Buchung uebernimmt Topf und sprechenden Namen des
    Vorkommens und verschwindet damit aus der gestrichelten Zukunfts-Ansicht."""
    if vorkommen.verknuepfte_buchung_id is not None or vorkommen.verknuepfte_topf_umbuchung_id is not None:
        raise ValueError("Vorkommen ist bereits aufgeloest.")
    if buchung.ist_umbuchung:
        raise ValueError("Eine Umbuchung kann nicht mit einem Forecast-Vorkommen verknuepft werden.")
    bereits_verknuepft = (
        db.query(ForecastVorkommen)
        .filter(ForecastVorkommen.verknuepfte_buchung_id == buchung.id)
        .first()
    )
    if bereits_verknuepft is not None:
        raise ValueError("Diese Buchung ist bereits mit einem anderen Vorkommen verknuepft.")

    vorkommen.verknuepfte_buchung_id = buchung.id
    vorkommen.erwarteter_betrag = buchung.betrag
    vorkommen.erwartetes_datum = buchung.datum

    buchung.topf_id = vorkommen.topf_id
    buchung.titel = vorkommen.bezeichnung
    buchung.zuordnung_quelle = "regel"


def vorkommen_loeschen(db: Session, vorkommen: ForecastVorkommen) -> None:
    """Verwirft ein offenes Vorkommen (z.B. eine nie eingetroffene Erwartung).

    Setzt statt eines echten Deletes nur ignoriert=True: der Datensatz bleibt
    fuer eine aus einer Regel erzeugte Buchung erhalten, damit die
    Generierung in ensure_forecast_vorkommen ihn weiter als "bereits
    vorhanden" fuer diesen Zeitraum erkennt und ihn nicht beim naechsten
    Scan erneut anlegt. Aus allen Listen (Zeitachse, Prognose, Matching)
    verschwindet er trotzdem, da die dortigen offene_vorkommen_query()-
    Abfragen ignorierte Vorkommen ausschliessen."""
    if vorkommen.verknuepfte_buchung_id is not None or vorkommen.verknuepfte_topf_umbuchung_id is not None:
        raise ValueError("Nur noch offene Vorkommen koennen geloescht werden.")
    vorkommen.ignoriert = True


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
