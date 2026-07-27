"""Automatische Topf-Zuordnung neuer Buchungen (Konzept Abschnitt 6, feste Reihenfolge):

1. typ == INTEREST_PAYMENT           -> Sonderausgaben
2. verwendungszweck enthaelt Topfname -> dieser Topf
3. Betrag/Datum passt zu FORECAST_REGEL -> deren Topf, Vorkommen wird verknuepft
4. sonst                              -> topf_id = NULL (Review-Liste)

Buchung muss bereits einen Datenbank-Primaerschluessel besitzen (fuer die
Verknuepfung mit einem FORECAST_VORKOMMEN), also vor dem Aufruf flushen.
"""
import re

from sqlalchemy.orm import Session

from app.config import SONDERAUSGABEN_TOPF
from app.matching import finde_passendes_vorkommen
from app.models import Buchung, Topf


def _topf_by_name(db: Session, name: str) -> Topf | None:
    return db.query(Topf).filter(Topf.name == name).first()


def _normalisiert(text: str) -> str:
    """Entfernt Leer- und Sonderzeichen, damit z.B. 'Hauskredit' (wie es Banken
    im Verwendungszweck oft ohne Leerzeichen schreiben) den Topf 'Haus Kredit'
    trifft."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _verknuepfe_offenes_forecast_vorkommen(db: Session, buchung: Buchung) -> None:
    """Zusaetzlicher Forecast-Abgleich: verlinkt ein offenes Vorkommen desselben
    Topfs, unabhaengig davon, wie der Topf ermittelt wurde (Zins, Text oder Regel).
    Uebernimmt dabei dessen Bezeichnung als sprechenden Namen der Buchung."""
    vorkommen = finde_passendes_vorkommen(db, buchung, topf_id=buchung.topf_id)
    if vorkommen is not None:
        vorkommen.verknuepfte_buchung_id = buchung.id
        vorkommen.erwarteter_betrag = buchung.betrag
        vorkommen.erwartetes_datum = buchung.datum
        buchung.titel = vorkommen.bezeichnung


def topf_zuordnen(db: Session, buchung: Buchung) -> None:
    if buchung.ist_umbuchung:
        return

    if buchung.typ == "INTEREST_PAYMENT":
        topf = _topf_by_name(db, SONDERAUSGABEN_TOPF)
        if topf is not None:
            buchung.topf_id = topf.id
            buchung.zuordnung_quelle = "zins"
            buchung.titel = "Zinsgutschrift"
            _verknuepfe_offenes_forecast_vorkommen(db, buchung)
            return

    verwendungszweck_norm = _normalisiert(
        " ".join(filter(None, [buchung.verwendungszweck, buchung.beschreibung]))
    )
    if verwendungszweck_norm:
        for topf in db.query(Topf).order_by(Topf.reihenfolge).all():
            if _normalisiert(topf.name) in verwendungszweck_norm:
                buchung.topf_id = topf.id
                buchung.zuordnung_quelle = "verwendungszweck"
                _verknuepfe_offenes_forecast_vorkommen(db, buchung)
                return

    vorkommen = finde_passendes_vorkommen(db, buchung, nur_aus_regel=True)
    if vorkommen is not None:
        buchung.topf_id = vorkommen.topf_id
        buchung.zuordnung_quelle = "regel"
        buchung.titel = vorkommen.bezeichnung
        vorkommen.verknuepfte_buchung_id = buchung.id
        vorkommen.erwarteter_betrag = buchung.betrag
        vorkommen.erwartetes_datum = buchung.datum
        return

    buchung.topf_id = None
    buchung.zuordnung_quelle = None
