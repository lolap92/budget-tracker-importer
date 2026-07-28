"""Abgeleitete Logik (Konzept Abschnitt 6).

Nichts hier wird persistiert - jede Funktion berechnet ihr Ergebnis frisch
aus BUCHUNG / TOPF_UMBUCHUNG / FORECAST_VORKOMMEN.
"""
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import FORECAST_HORIZON_MONATE, HAUS_KREDIT_TOPF
from app.dateutils import add_months, month_end
from app.matching import offene_vorkommen_query
from app.models import Buchung, ForecastRegel, ForecastVorkommen, Topf, TopfUmbuchung
from app.umbuchung import offene_umbuchungen_query


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
    db: Session, topf: Topf | None, heute: dt.date | None = None, monate: int = FORECAST_HORIZON_MONATE
) -> PrognoseErgebnis:
    """Prognose(Topf, Monat i) = aktueller Saldo + Summe offener FORECAST_VORKOMMEN bis Monat i.

    topf=None liefert die Prognose ueber alle Toepfe hinweg (gesamtes Konto):
    Topf-Umbuchungen zwischen den eigenen Toepfen heben sich dabei automatisch
    auf, da kontostand_gesamt sie wie saldo_topf ignoriert."""
    heute = heute or dt.date.today()
    aktueller_saldo = saldo_topf(db, topf) if topf is not None else kontostand_gesamt(db)

    offene_vorkommen = offene_vorkommen_query(db, topf.id if topf is not None else None).all()

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



def sondertilgung_status(db: Session, topf: Topf) -> dict | None:
    """Fuer den Haus-Kredit-Topf auf der Startseite: ob die naechste faellige
    jaehrliche Sondertilgungs-Regel laut Prognose gedeckt sein wird. Der Betrag
    stammt aus der hinterlegten Forecast-Regel, das Faelligkeitsdatum aus dem
    naechsten offenen Forecast-Vorkommen dieser Regel (nicht arithmetisch aus
    Anker-Tag/Startdatum neu berechnet) - so bleibt die Aussage konsistent mit
    dem, was auf der Forecast-Seite tatsaechlich als naechste Buchung geplant
    ist, inklusive manueller Verschiebungen einzelner Vorkommen."""
    if topf.name != HAUS_KREDIT_TOPF:
        return None

    regel = (
        db.query(ForecastRegel)
        .filter(
            ForecastRegel.topf_id == topf.id,
            ForecastRegel.rhythmus == "jaehrlich",
            ForecastRegel.bezeichnung.ilike("%sondertilgung%"),
        )
        .first()
    )
    if regel is None:
        return None

    heute = dt.date.today()
    naechstes_vorkommen = (
        offene_vorkommen_query(db, topf.id)
        .filter(ForecastVorkommen.regel_id == regel.id, ForecastVorkommen.erwartetes_datum >= heute)
        .order_by(ForecastVorkommen.erwartetes_datum.asc())
        .first()
    )
    if naechstes_vorkommen is None:
        return None
    faelligkeit = naechstes_vorkommen.erwartetes_datum

    betrag = abs(Decimal(regel.betrag))
    saldo = saldo_topf(db, topf)
    offene_bis = [
        v
        for v in offene_vorkommen_query(db, topf.id)
        .filter(ForecastVorkommen.erwartetes_datum <= faelligkeit)
        .all()
        if v.regel_id != regel.id
    ]
    projizierter_saldo = saldo + sum(Decimal(v.erwarteter_betrag) for v in offene_bis)

    return {
        "betrag": betrag,
        "faelligkeit": faelligkeit,
        "wird_erreicht": projizierter_saldo >= betrag,
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
    """WHERE topf_id IS NULL AND ist_umbuchung = false.

    Dieselbe Liste dient zwei Zwecken: den offenen Faellen unter "Zuordnen"
    und den Kandidaten fuer die manuelle Verknuepfung eines Forecast-
    Vorkommens. Buchungen mit bereits gesetztem topf_id sind bewusst
    ausgeschlossen, egal ob automatisch (Zins, Verwendungszweck, Regel) oder
    manuell zugeordnet: sie sind aufgeloest, eine Verknuepfung wuerde sie
    sonst stillschweigend per vorkommen_manuell_verknuepfen umtopfen.
    Manuell erfasste Buchungen haben immer sofort einen Topf und tauchen
    damit hier nie auf.
    """
    return (
        db.query(Buchung)
        .filter(Buchung.topf_id.is_(None), Buchung.ist_umbuchung.is_(False))
        .order_by(Buchung.datum.desc())
        .all()
    )


def offene_umbuchungen(db: Session) -> list[Buchung]:
    """Schwebende Bank-Umbuchungen, juengste zuerst.

    Was "offen" heisst, definiert offene_umbuchungen_query() in app/umbuchung.py
    - dort braucht vorschlaege_fuer_abgleich() dieselbe Menge als Query.
    """
    return offene_umbuchungen_query(db).order_by(Buchung.datum.desc()).all()


def neuestes_buchungsdatum(db: Session) -> dt.date | None:
    """Datum der zuletzt importierten/erfassten Buchung - fuer den 'Stand'
    auf der Uebersicht, da dieser zeigen soll, wie aktuell die Datenlage
    tatsaechlich ist, statt nur des heutigen Kalendertags."""
    buchung = db.query(Buchung).order_by(Buchung.datum.desc()).first()
    return buchung.datum if buchung else None


def letzter_import_zeitpunkt(db: Session) -> dt.datetime | None:
    """Wann zuletzt eine Buchung angelegt wurde (UTC).

    Bewusst aus der Datenbank statt aus dem Watcher-Speicher: die Angabe
    ueberlebt damit einen Neustart des Add-ons. Sie beantwortet die Frage
    "ist mein letzter Export angekommen?", waehrend der Zeitpunkt des letzten
    Scans nur sagt, dass der Watcher ueberhaupt laeuft.
    """
    return db.query(func.max(Buchung.importiert_am)).scalar()


def vorhandene_buchungstitel(db: Session) -> list[str]:
    """Alle bereits verwendeten sprechenden Namen - fuer Vorschlaege bei der
    manuellen Titelvergabe (Buchungs-Titel, Regel- und Vorkommen-Bezeichnungen)."""
    titel = {t for (t,) in db.query(Buchung.titel).filter(Buchung.titel.isnot(None)).distinct()}
    regeln = {b for (b,) in db.query(ForecastRegel.bezeichnung).distinct()}
    vorkommen = {b for (b,) in db.query(ForecastVorkommen.bezeichnung).distinct()}
    return sorted(titel | regeln | vorkommen, key=str.lower)



def regel_erste_faelligkeit(db: Session, regel_id: int) -> dt.date | None:
    """Fruehestes Datum (real gebucht oder noch geplant) einer Forecast-Regel -
    fuer die Regel-Uebersicht auf der Forecast-Seite aussagekraeftiger als der
    reine Anker-Tag, der nichts darueber sagt, ob und wann die Regel bisher
    tatsaechlich getroffen hat bzw. zum ersten Mal faellig wird. Sobald ein
    Vorkommen mit einer realen Buchung verknuepft wird, uebernimmt es deren
    Datum (siehe assignment.py/forecast_engine.py), das fruehste Vorkommen
    liefert also automatisch das reale Datum, falls schon gebucht, sonst das
    geplante. Verworfene (ignorierte) Vorkommen zaehlen nicht mit. Bewusst
    kein "letztes Datum": bei unbefristeten Regeln gibt es keins, bei
    befristeten steht das tatsaechliche Ende bereits separat (Regel-Enddatum)
    - ein aus den bisher generierten Vorkommen abgeleitetes "letztes Datum"
    waere nur der aktuelle 12-Monats-Horizont-Stand, nicht das echte Ende."""
    datum = (
        db.query(ForecastVorkommen.erwartetes_datum)
        .filter(ForecastVorkommen.regel_id == regel_id, ForecastVorkommen.ignoriert.is_(False))
        .order_by(ForecastVorkommen.erwartetes_datum.asc())
        .first()
    )
    return datum[0] if datum else None
