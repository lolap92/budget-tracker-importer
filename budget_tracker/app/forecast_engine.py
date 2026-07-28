"""Erzeugung von FORECAST_VORKOMMEN aus FORECAST_REGEL sowie die Wege,
ein offenes Vorkommen aufzuloesen oder zu verwerfen (Konzept Abschnitt 6)."""
import datetime as dt

from sqlalchemy.orm import Session

from app.config import (
    FORECAST_HORIZON_MONATE,
    FORECAST_RUECKWIRKEND_MONATE,
    RHYTHMEN,
    SONDERAUSGABEN_TOPF,
)
from app.dateutils import add_months, month_start, safe_date
from app.models import (
    Buchung,
    ForecastRegel,
    ForecastVorkommen,
    Konfiguration,
    Topf,
    TopfUmbuchung,
)


def _occurrence_dates(
    regel: ForecastRegel, horizon_end: dt.date, untergrenze: dt.date
) -> list[dt.date]:
    """Alle Faelligkeiten einer Regel zwischen untergrenze und horizon_end.

    Die Untergrenze ist bewusst Teil der Signatur: eine Regel darf ein
    Startdatum weit in der Vergangenheit haben (Kreditrate seit 2024), ohne
    dass dafuer rueckwirkend Vorkommen entstehen, die nie eine reale Buchung
    finden koennen.
    """
    dates: list[dt.date] = []
    if regel.rhythmus in ("monatlich", "befristet"):
        erster = safe_date(regel.start_datum.year, regel.start_datum.month, regel.anker_tag)
        if erster < regel.start_datum:
            erster = add_months(erster, 1)
        # Der Anker-Tag wird fuer jeden Monat neu aus dem Monatsanfang
        # abgeleitet, nicht durch Weiterzaehlen des Vormonatsdatums: sonst
        # kappt der Februar einen Anker-Tag 29-31 dauerhaft und die Regel
        # faellt fuer den Rest des Jahres auf den 28. zurueck.
        monat = month_start(erster)
        while True:
            d = safe_date(monat.year, monat.month, regel.anker_tag)
            if d > horizon_end:
                break
            if regel.end_datum and d > regel.end_datum:
                break
            if d >= untergrenze:
                dates.append(d)
            monat = add_months(monat, 1)
    elif regel.rhythmus == "jaehrlich":
        year = regel.start_datum.year
        while True:
            d = safe_date(year, regel.start_datum.month, regel.anker_tag)
            if d > horizon_end:
                break
            if (
                d >= regel.start_datum
                and d >= untergrenze
                and (not regel.end_datum or d <= regel.end_datum)
            ):
                dates.append(d)
            year += 1
    return dates


def forecast_untergrenze(db: Session, heute: dt.date) -> dt.date:
    """Fruehestes Datum, fuer das ueberhaupt noch Vorkommen erzeugt werden.

    Rueckwirkend nur bis FORECAST_RUECKWIRKEND_MONATE vor dem aktuellen Monat
    und nie vor dem Startdatum der Konfiguration: davor liegende Bewegungen
    stecken bereits in den Topf-Startsalden.
    """
    grenze = add_months(month_start(heute), -FORECAST_RUECKWIRKEND_MONATE)
    konfiguration = db.query(Konfiguration).first()
    if konfiguration is not None and konfiguration.start_datum > grenze:
        grenze = konfiguration.start_datum
    return grenze


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
    untergrenze = forecast_untergrenze(db, heute)
    erzeugt = 0

    for regel in db.query(ForecastRegel).all():
        vorhandene = db.query(ForecastVorkommen).filter(ForecastVorkommen.regel_id == regel.id).all()
        for d in _occurrence_dates(regel, horizon_end, untergrenze):
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


def vorkommen_bearbeiten(
    db: Session, vorkommen: ForecastVorkommen, bezeichnung: str, erwarteter_betrag, erwartetes_datum: dt.date
) -> None:
    """Direktes Bearbeiten eines noch offenen Vorkommens - fuer Korrekturen,
    die ueber das reine Verschieben um einen Monat hinausgehen (Regel-basiert
    oder frei angelegt, macht hier keinen Unterschied: das Vorkommen selbst
    wird korrigiert, die erzeugende Regel bleibt unangetastet)."""
    if (
        vorkommen.verknuepfte_buchung_id is not None
        or vorkommen.verknuepfte_topf_umbuchung_id is not None
        or vorkommen.ignoriert
    ):
        raise ValueError("Nur noch offene Vorkommen koennen bearbeitet werden.")
    vorkommen.bezeichnung = bezeichnung
    vorkommen.erwarteter_betrag = erwarteter_betrag
    vorkommen.erwartetes_datum = erwartetes_datum


def _pruefe_regel_eingaben(betrag, rhythmus: str, anker_tag: int) -> None:
    """Gemeinsame Pruefungen fuer Anlegen und Bearbeiten einer Regel."""
    if float(betrag) == 0:
        raise ValueError("Betrag darf nicht 0 sein.")
    if rhythmus not in RHYTHMEN:
        raise ValueError(
            f"Unbekannter Rhythmus '{rhythmus}' - erlaubt sind: {', '.join(RHYTHMEN)}."
        )
    if not 1 <= int(anker_tag) <= 31:
        raise ValueError("Anker-Tag muss zwischen 1 und 31 liegen.")


def regel_erstellen(
    db: Session,
    topf_id: int,
    bezeichnung: str,
    betrag,
    rhythmus: str,
    anker_tag: int,
    start_datum: dt.date,
    end_datum: dt.date | None,
) -> ForecastRegel:
    """Legt eine Regel an und erzeugt ihre Vorkommen bis zum Horizont.

    Bewusst hier statt im Router, damit Anlegen und Bearbeiten dieselben
    Pruefungen durchlaufen - vorher war ein Betrag von 0 nur beim Bearbeiten
    verboten, beim Anlegen ging er durch.
    """
    _pruefe_regel_eingaben(betrag, rhythmus, anker_tag)

    regel = ForecastRegel(
        topf_id=topf_id,
        bezeichnung=bezeichnung,
        betrag=betrag,
        rhythmus=rhythmus,
        anker_tag=anker_tag,
        start_datum=start_datum,
        end_datum=end_datum,
    )
    db.add(regel)
    db.flush()
    ensure_forecast_vorkommen(db)
    return regel


def regel_bearbeiten(
    db: Session,
    regel: ForecastRegel,
    topf_id: int,
    bezeichnung: str,
    betrag,
    rhythmus: str,
    anker_tag: int,
    start_datum: dt.date,
    end_datum: dt.date | None,
) -> None:
    """Bearbeitet eine bestehende Regel und erzeugt ihre noch offenen (nicht
    gebuchten, nicht verworfenen) Vorkommen mit den neuen Parametern neu -
    bereits gebuchte/verknuepfte Vorkommen sind reales Faktum und bleiben
    unangetastet, bewusst verworfene (ignoriert) bleiben es auch."""
    _pruefe_regel_eingaben(betrag, rhythmus, anker_tag)

    regel.topf_id = topf_id
    regel.bezeichnung = bezeichnung
    regel.betrag = betrag
    regel.rhythmus = rhythmus
    regel.anker_tag = anker_tag
    regel.start_datum = start_datum
    regel.end_datum = end_datum

    offene = (
        db.query(ForecastVorkommen)
        .filter(
            ForecastVorkommen.regel_id == regel.id,
            ForecastVorkommen.verknuepfte_buchung_id.is_(None),
            ForecastVorkommen.verknuepfte_topf_umbuchung_id.is_(None),
            ForecastVorkommen.ignoriert.is_(False),
        )
        .all()
    )
    for v in offene:
        db.delete(v)
    db.flush()
    ensure_forecast_vorkommen(db)


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
