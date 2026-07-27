"""Abgeleitete Logik (Konzept Abschnitt 6).

Nichts hier wird persistiert - jede Funktion berechnet ihr Ergebnis frisch
aus BUCHUNG / TOPF_UMBUCHUNG / FORECAST_VORKOMMEN.
"""
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import FORECAST_HORIZON_MONATE, HAUS_KREDIT_TOPF
from app.dateutils import add_months, month_end
from app.matching import offene_vorkommen_query
from app.models import Buchung, ForecastRegel, ForecastVorkommen, Topf, TopfUmbuchung


def _umbuchung_zaehlt_fuer_saldo(b: Buchung) -> bool:
    return (not b.ist_umbuchung) or b.umbuchung_final or (b.gegenbuchung_id is not None)


def saldo_topf(db: Session, topf: Topf) -> Decimal:
    """Saldo(Topf) = startsaldo + reale Buchungen (nicht schwebend) + TOPF_UMBUCHUNGen."""
    total = Decimal(topf.startsaldo or 0)

    buchungen = db.query(Buchung).filter(Buchung.topf_id == topf.id).all()
    for b in buchungen:
        if _umbuchung_zaehlt_fuer_saldo(b):
            total += Decimal(b.betrag)

    eingaenge = db.query(TopfUmbuchung).filter(TopfUmbuchung.nach_topf_id == topf.id).all()
    for u in eingaenge:
        total += Decimal(u.betrag)

    ausgaenge = db.query(TopfUmbuchung).filter(TopfUmbuchung.von_topf_id == topf.id).all()
    for u in ausgaenge:
        total -= Decimal(u.betrag)

    return total


def kontostand_gesamt(db: Session) -> Decimal:
    """Realer Kontostand: Summe aller Topf-Startsalden + jede reale CSV-Buchung.

    Topf-Umbuchungen sind rein virtuell (heben sich zwischen den Toepfen
    auf) und schwebende Buchungen sind trotzdem echtes Geld auf dem Konto -
    beides zaehlt hier unabhaengig vom Zuordnungsstatus mit.
    """
    startsalden = sum(Decimal(t.startsaldo or 0) for t in db.query(Topf).all())
    buchungen_summe = db.query(Buchung).all()
    return startsalden + sum(Decimal(b.betrag) for b in buchungen_summe)


@dataclass
class MonatsWert:
    monat: dt.date  # erster Tag des Monats
    saldo: Decimal


@dataclass
class PrognoseErgebnis:
    aktueller_saldo: Decimal
    monatswerte: list = field(default_factory=list)
    tiefpunkt: Decimal = Decimal(0)
    tiefpunkt_monat: dt.date | None = None
    minus_warnung: bool = False


def prognose_topf(
    db: Session, topf: Topf, heute: dt.date | None = None, monate: int = FORECAST_HORIZON_MONATE
) -> PrognoseErgebnis:
    """Prognose(Topf, Monat i) = aktueller Saldo + Summe offener FORECAST_VORKOMMEN bis Monat i."""
    heute = heute or dt.date.today()
    aktueller_saldo = saldo_topf(db, topf)

    offene_vorkommen = offene_vorkommen_query(db, topf.id).all()

    monatswerte = []
    for i in range(monate):
        monatsdatum = add_months(heute.replace(day=1), i)
        ende = month_end(monatsdatum)
        saldo_i = aktueller_saldo + sum(
            Decimal(v.erwarteter_betrag)
            for v in offene_vorkommen
            if v.erwartetes_datum <= ende
        )
        monatswerte.append(MonatsWert(monat=monatsdatum, saldo=saldo_i))

    tiefster = min(monatswerte, key=lambda m: m.saldo)
    return PrognoseErgebnis(
        aktueller_saldo=aktueller_saldo,
        monatswerte=monatswerte,
        tiefpunkt=tiefster.saldo,
        tiefpunkt_monat=tiefster.monat,
        minus_warnung=tiefster.saldo < 0,
    )


def ziel_fortschritt_haus_kredit(db: Session, topf: Topf) -> dict | None:
    if topf.name != HAUS_KREDIT_TOPF or not topf.jahresziel:
        return None
    saldo = saldo_topf(db, topf)
    ziel = Decimal(topf.jahresziel)
    anteil = float(saldo / ziel) if ziel else 0.0
    return {
        "saldo": saldo,
        "jahresziel": ziel,
        "anteil": max(0.0, min(1.0, anteil)),
        "sondertilgung_datum": topf.sondertilgung_datum,
    }


@dataclass
class ZeitachsenEintrag:
    datum: dt.date
    art: str  # "buchung" | "topf_umbuchung" | "forecast"
    bezeichnung: str
    betrag: Decimal
    gestrichelt: bool
    objekt: object


def zeitachse_topf(db: Session, topf: Topf) -> dict:
    """Chronologische Liste, verankert am aktuellen Kalendermonat.

    Vergangenheit (reale Buchungen + Topf-Umbuchungen) absteigend unterhalb
    des Ankers, offene Forecast-Vorkommen aufsteigend oberhalb (gestrichelt).
    """
    vergangenheit: list[ZeitachsenEintrag] = []

    for b in db.query(Buchung).filter(Buchung.topf_id == topf.id).all():
        if _umbuchung_zaehlt_fuer_saldo(b):
            bezeichnung = b.titel or b.verwendungszweck or b.beschreibung or b.typ
            vergangenheit.append(
                ZeitachsenEintrag(
                    datum=b.datum,
                    art="buchung",
                    bezeichnung=bezeichnung,
                    betrag=Decimal(b.betrag),
                    gestrichelt=False,
                    objekt=b,
                )
            )

    for u in db.query(TopfUmbuchung).filter(TopfUmbuchung.von_topf_id == topf.id).all():
        vergangenheit.append(
            ZeitachsenEintrag(
                datum=u.datum,
                art="topf_umbuchung",
                bezeichnung=f"Umbuchung -> {u.nach_topf.name}"
                + (f" ({u.kommentar})" if u.kommentar else ""),
                betrag=-Decimal(u.betrag),
                gestrichelt=False,
                objekt=u,
            )
        )

    for u in db.query(TopfUmbuchung).filter(TopfUmbuchung.nach_topf_id == topf.id).all():
        vergangenheit.append(
            ZeitachsenEintrag(
                datum=u.datum,
                art="topf_umbuchung",
                bezeichnung=f"Umbuchung <- {u.von_topf.name}"
                + (f" ({u.kommentar})" if u.kommentar else ""),
                betrag=Decimal(u.betrag),
                gestrichelt=False,
                objekt=u,
            )
        )

    vergangenheit.sort(key=lambda e: e.datum, reverse=True)

    zukunft: list[ZeitachsenEintrag] = []
    offene_vorkommen = (
        offene_vorkommen_query(db, topf.id).order_by(ForecastVorkommen.erwartetes_datum.asc()).all()
    )
    for v in offene_vorkommen:
        zukunft.append(
            ZeitachsenEintrag(
                datum=v.erwartetes_datum,
                art="forecast",
                bezeichnung=v.bezeichnung,
                betrag=Decimal(v.erwarteter_betrag),
                gestrichelt=True,
                objekt=v,
            )
        )

    return {"zukunft": zukunft, "vergangenheit": vergangenheit, "anker_monat": dt.date.today().replace(day=1)}


def review_liste(db: Session) -> list[Buchung]:
    """WHERE topf_id IS NULL AND ist_umbuchung = false."""
    return (
        db.query(Buchung)
        .filter(Buchung.topf_id.is_(None), Buchung.ist_umbuchung.is_(False))
        .order_by(Buchung.datum.desc())
        .all()
    )


def offene_umbuchungen(db: Session) -> list[Buchung]:
    """WHERE ist_umbuchung = true AND topf_id IS NULL (noch nicht final zugeordnet)."""
    return (
        db.query(Buchung)
        .filter(Buchung.ist_umbuchung.is_(True), Buchung.topf_id.is_(None))
        .order_by(Buchung.datum.desc())
        .all()
    )


def neuestes_buchungsdatum(db: Session) -> dt.date | None:
    """Datum der zuletzt importierten/erfassten Buchung - fuer den 'Stand'
    auf der Uebersicht, da dieser zeigen soll, wie aktuell die Datenlage
    tatsaechlich ist, statt nur des heutigen Kalendertags."""
    buchung = db.query(Buchung).order_by(Buchung.datum.desc()).first()
    return buchung.datum if buchung else None


def vorhandene_buchungstitel(db: Session) -> list[str]:
    """Alle bereits verwendeten sprechenden Namen - fuer Vorschlaege bei der
    manuellen Titelvergabe (Buchungs-Titel, Regel- und Vorkommen-Bezeichnungen)."""
    titel = {t for (t,) in db.query(Buchung.titel).filter(Buchung.titel.isnot(None)).distinct()}
    regeln = {b for (b,) in db.query(ForecastRegel.bezeichnung).distinct()}
    vorkommen = {b for (b,) in db.query(ForecastVorkommen.bezeichnung).distinct()}
    return sorted(titel | regeln | vorkommen, key=str.lower)


def unverknuepfte_buchungen(db: Session) -> list[Buchung]:
    """Reale Buchungen, die noch mit keinem FORECAST_VORKOMMEN verknuepft sind -
    Kandidaten fuer die manuelle Verknuepfung eines offenen Vorkommens."""
    verknuepfte_ids = {
        v
        for (v,) in db.query(ForecastVorkommen.verknuepfte_buchung_id).filter(
            ForecastVorkommen.verknuepfte_buchung_id.isnot(None)
        )
    }
    query = db.query(Buchung).filter(Buchung.ist_umbuchung.is_(False))
    if verknuepfte_ids:
        query = query.filter(~Buchung.id.in_(verknuepfte_ids))
    return query.order_by(Buchung.datum.desc()).all()
