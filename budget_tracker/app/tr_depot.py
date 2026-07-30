"""Depotstand abrufen und ablegen - reine Information.

Der Wert des Wertpapierdepots ist kein Fakt der Kontofuehrung: er gehoert in
keinen Topf-Saldo, in keinen Kontostand und in keine Prognose. Er wird
abgerufen, weil er interessiert - und weil der Cash-Bestand nebenbei eine
Plausibilitaetspruefung erlaubt: die App rechnet ihren Kontostand aus
Startsalden und Buchungen aus, Trade Republic kennt den wahren Wert. Eine
Abweichung heisst, dass eine Buchung fehlt oder doppelt ist.

Ein Abruf besteht aus mehreren Anfragen: die Positionen, der Cash-Bestand, je
Position der Name und der aktuelle Kurs. Positionen ohne Kurs fallen heraus,
statt den Gesamtwert stillschweigend zu verfaelschen.
"""
import datetime as dt
import logging
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models import DepotPosition, DepotSnapshot

logger = logging.getLogger("budget_tracker.tr_depot")

# Anleihekurse notieren in Prozent des Nennwerts. Erkennbar sind Anleihen am
# Faelligkeitsmonat im Namen ("... Jan. 2030") - dieselbe Heuristik, die auch
# pytr benutzt. Ohne sie waere der Wert einer Anleiheposition um Faktor 100 zu
# hoch, was in einer Summe nicht auffiele.
_ANLEIHE = re.compile(
    r"(Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)\w*\.?\s+20\d{2}",
    re.IGNORECASE,
)


def _dezimal(wert, standard: str = "0") -> Decimal:
    try:
        return Decimal(str(wert))
    except (InvalidOperation, TypeError):
        return Decimal(standard)


async def depot_laden(api, abrufen) -> dict:
    """Holt Positionen, Kurse und Cash-Bestand.

    `abrufen` ist die Abruf-Funktion aus app/tr_sync.py - so bleibt die
    Anfrage-/Antwort-Mechanik an einer Stelle und dieses Modul ohne Netzlogik.
    """
    portfolio = await abrufen(api, api.compact_portfolio())
    cash_antwort = await abrufen(api, api.cash())

    cash = Decimal("0")
    if isinstance(cash_antwort, list) and cash_antwort:
        cash = _dezimal(cash_antwort[0].get("amount"))

    positionen = []
    for position in portfolio.get("positions") or []:
        isin = position.get("instrumentId")
        if not isin:
            continue

        try:
            instrument = await abrufen(api, api.instrument_details(isin))
        except Exception:  # noqa: BLE001 - eine Position darf den Abruf nicht kippen
            logger.warning("Stammdaten zu %s nicht abrufbar, Position uebersprungen.", isin)
            continue

        name = instrument.get("shortName") or isin
        boersen = instrument.get("exchangeIds") or []
        if not boersen:
            logger.info("Zu %s (%s) ist keine Boerse bekannt, kein Kurs ermittelbar.", name, isin)
            continue

        try:
            ticker = await abrufen(api, api.ticker(isin, exchange=boersen[0]))
        except Exception:  # noqa: BLE001
            logger.warning("Kurs zu %s (%s) nicht abrufbar, Position uebersprungen.", name, isin)
            continue

        kurs = _dezimal((ticker.get("last") or {}).get("price"))
        if _ANLEIHE.search(name):
            kurs = kurs / 100

        stueck = _dezimal(position.get("netSize"))
        positionen.append(
            {
                "isin": isin,
                "name": name,
                "stueck": stueck,
                "kurs": kurs,
                "einstand": _dezimal(position.get("averageBuyIn")),
                "wert": (kurs * stueck).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            }
        )

    return {"cash": cash, "positionen": positionen}


def snapshot_speichern(db: Session, daten: dict) -> DepotSnapshot:
    """Ersetzt den bisherigen Stand. Committet nicht."""
    for alter in db.query(DepotSnapshot).all():
        db.delete(alter)
    db.flush()

    snapshot = DepotSnapshot(
        zeitpunkt=dt.datetime.utcnow(),
        cash=daten["cash"],
        gesamtwert=sum((p["wert"] for p in daten["positionen"]), Decimal("0")),
    )
    db.add(snapshot)
    db.flush()

    for position in daten["positionen"]:
        db.add(DepotPosition(snapshot_id=snapshot.id, **position))
    return snapshot


def aktueller_snapshot(db: Session) -> DepotSnapshot | None:
    return db.query(DepotSnapshot).order_by(DepotSnapshot.zeitpunkt.desc()).first()
