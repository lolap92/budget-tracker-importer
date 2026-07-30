"""Abgleich mit der Trade-Republic-Timeline.

Ablauf eines Laufs:

1. Zeitgrenze bestimmen - juengstes bekanntes Buchungsdatum minus Rueckgriff,
   nie vor dem Startdatum.
2. `timelineTransactions` seitenweise lesen, bis die Events aelter sind.
3. Fuer jedes noch unbekannte Event mit Geldbewegung das Detail nachladen -
   nur dort steht der Verwendungszweck.
4. Uebersetzen (app/tr_events.py) und uebernehmen (app/import_core.py), also
   durch denselben Kern wie eine CSV-Zeile.

Netzzugriff und Datenbankarbeit sind getrennt: Schritt 1-3 liefern eine Liste
von Events, Schritt 4 arbeitet rein lokal darauf. Das haelt die WebSocket-
Verbindung kurz und macht die Verarbeitung ohne Netz testbar.
"""
import asyncio
import datetime as dt
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import TR_SYNC_INTERVAL_SECONDS, TR_SYNC_RUECKGRIFF_TAGE
from app.database import SessionLocal
from app.dopplung import finde_moegliche_dopplung
from app.import_core import QUELLE_API, ImportKontext, uebernehmen
from app.models import Buchung, ImportVerdacht, Konfiguration, TradeRepublicKonto
from app.tr_client import NichtAngemeldet, verbindung, verbindungsschloss
from app.tr_events import ist_kontobewegung, zeile_aus_event

logger = logging.getLogger("budget_tracker.tr_sync")

# Wie lange auf die Antwort einer einzelnen Anfrage gewartet wird.
ANTWORT_TIMEOUT = 30.0

# Zustand des letzten Laufs fuer die Anzeige. Wie beim Verzeichnis-Watcher nur
# im Speicher; der Zeitpunkt des letzten erfolgreichen Abgleichs steht dauerhaft
# in trade_republic_konto.letzter_sync und uebersteht einen Neustart.
_letzter_lauf = {
    "zeitpunkt": None,
    "erfolgreich": None,
    "meldung": None,
    "zahlen": None,
}


def status() -> dict:
    return dict(_letzter_lauf)


def _zeitstempel(event: dict) -> dt.datetime | None:
    roh = (event.get("timestamp") or "").strip()
    if not roh:
        return None
    if len(roh) >= 5 and roh[-5] in "+-" and roh[-3] != ":":
        roh = roh[:-2] + ":" + roh[-2:]
    try:
        zeitpunkt = dt.datetime.fromisoformat(roh.replace("Z", "+00:00"))
    except ValueError:
        return None
    if zeitpunkt.tzinfo is None:
        return zeitpunkt.replace(tzinfo=dt.timezone.utc)
    return zeitpunkt


def ab_zeitpunkt(db: Session) -> dt.datetime:
    """Ab wann die Timeline gelesen wird.

    Der Rueckgriff hinter die juengste bekannte Buchung faengt Vorgaenge ein,
    die Trade Republic nachtraeglich einbucht. Manuell erfasste Buchungen
    bleiben aussen vor - sie sagen nichts darueber, wie weit die Schnittstelle
    schon gelesen wurde.
    """
    konfiguration = db.query(Konfiguration).first()
    start_datum = konfiguration.start_datum if konfiguration is not None else dt.date.min

    juengstes = (
        db.query(func.max(Buchung.datum))
        .filter(Buchung.quelle.in_(("csv", "api")))
        .scalar()
    )
    basis = start_datum
    if juengstes is not None:
        basis = max(start_datum, juengstes - dt.timedelta(days=TR_SYNC_RUECKGRIFF_TAGE))
    return dt.datetime.combine(basis, dt.time.min, tzinfo=dt.timezone.utc)


async def _abrufen(api, anfrage, timeout: float = ANTWORT_TIMEOUT):
    """Stellt eine Anfrage und wartet auf genau ihre Antwort. Benutzt nur die
    oeffentliche Schnittstelle von pytr (subscribe/recv/unsubscribe)."""
    subscription_id = await anfrage

    async def _warten():
        while True:
            antwort_id, _, antwort = await api.recv()
            if antwort_id == subscription_id:
                return antwort

    try:
        return await asyncio.wait_for(_warten(), timeout)
    finally:
        try:
            await api.unsubscribe(subscription_id)
        except Exception:  # noqa: BLE001 - Aufraeumen darf den Lauf nicht kippen
            logger.debug("Abmelden der Subscription fehlgeschlagen.", exc_info=True)


async def events_laden(api, ab: dt.datetime, ist_bekannt) -> list[dict]:
    """Alle Kontobewegungen ab `ab`, jeweils mit angehaengtem Detail."""
    gesammelt: list[dict] = []
    cursor = None
    seiten = 0

    while True:
        antwort = await _abrufen(api, api.timeline_transactions(cursor))
        seiten += 1
        zu_alt = False
        for event in antwort.get("items") or []:
            zeitpunkt = _zeitstempel(event)
            if zeitpunkt is not None and zeitpunkt < ab:
                zu_alt = True
                break
            gesammelt.append(event)

        cursor = (antwort.get("cursors") or {}).get("after")
        if zu_alt or not cursor:
            break

    # Details kosten je einen Abruf - deshalb nur fuer das, was ueberhaupt
    # eine Buchung werden kann. Status und Betrag stehen bereits im Event.
    relevant = [
        event
        for event in gesammelt
        if event.get("id") and not ist_bekannt(event["id"]) and ist_kontobewegung(event)
    ]
    logger.info(
        "Timeline: %d Seite(n), %d Event(s), davon %d neu und relevant.",
        seiten,
        len(gesammelt),
        len(relevant),
    )

    for event in relevant:
        try:
            event["details"] = await _abrufen(api, api.timeline_detail_v2(event["id"]))
        except Exception:  # noqa: BLE001 - ohne Detail fehlt nur der Verwendungszweck
            logger.warning(
                "Detail zu Event %s nicht abrufbar, Buchung entsteht ohne Verwendungszweck.",
                event["id"],
            )
            event.setdefault("details", {})

    await api.close()
    return relevant


def verarbeiten(db: Session, events: list[dict]) -> dict:
    """Uebersetzt die Events und uebernimmt sie. Rein lokal, ohne Netz."""
    zahlen = {
        "gelesen": len(events),
        "neu": 0,
        "duplikate": 0,
        "vor_startdatum": 0,
        "verdacht": 0,
        "uebersprungen": 0,
    }
    kontext = ImportKontext.laden(db)
    # Bereits beurteilte Verdachtsfaelle nicht erneut vorlegen - auch die
    # verworfenen, die gerade deshalb keine Buchung haben.
    beurteilt = {row[0] for row in db.query(ImportVerdacht.transaction_id).all()}

    for event in events:
        zeile = zeile_aus_event(event)
        if zeile is None:
            zahlen["uebersprungen"] += 1
            continue

        transaction_id = zeile["transaction_id"]
        if kontext.ist_bekannt(transaction_id):
            zahlen["duplikate"] += 1
            continue
        if transaction_id in beurteilt:
            zahlen["duplikate"] += 1
            continue

        dopplung = finde_moegliche_dopplung(
            db,
            transaction_id=transaction_id,
            datum=zeile["datum"],
            betrag=zeile["betrag"],
            quelle=QUELLE_API,
        )
        if dopplung is not None:
            logger.info(
                "Bewegung %s sieht aus wie Buchung %s - zur Entscheidung vorgelegt.",
                transaction_id,
                dopplung.id,
            )
            db.add(
                ImportVerdacht(
                    quelle=QUELLE_API,
                    vermutete_dopplung_id=dopplung.id,
                    erstellt_am=dt.datetime.utcnow(),
                    **zeile,
                )
            )
            beurteilt.add(transaction_id)
            zahlen["verdacht"] += 1
            continue

        ergebnis = uebernehmen(db, kontext, quelle=QUELLE_API, **zeile)
        zahlen[ergebnis] += 1

    db.commit()
    return zahlen


def sync_einmal(db: Session) -> dict:
    """Ein vollstaendiger Abgleich. Blockiert - gehoert in einen Worker-Thread."""
    konto = db.query(TradeRepublicKonto).first()
    if konto is None:
        return {"uebersprungen": "keine Telefonnummer hinterlegt"}

    _letzter_lauf["zeitpunkt"] = dt.datetime.utcnow()
    with verbindungsschloss:
        try:
            api = verbindung(konto.telefonnummer)
        except NichtAngemeldet as exc:
            _letzter_lauf.update(erfolgreich=False, meldung=str(exc))
            return {"uebersprungen": str(exc)}

        kontext_ids = {row[0] for row in db.query(Buchung.transaction_id).all()}
        try:
            events = asyncio.run(
                events_laden(api, ab_zeitpunkt(db), kontext_ids.__contains__)
            )
        except Exception as exc:  # noqa: BLE001 - ein Fehler darf die App nicht kippen
            logger.exception("Abgleich mit Trade Republic fehlgeschlagen.")
            _letzter_lauf.update(
                erfolgreich=False, meldung=f"Abruf fehlgeschlagen ({type(exc).__name__})"
            )
            return {"fehler": str(exc)}

    zahlen = verarbeiten(db, events)
    konto.letzter_sync = dt.datetime.utcnow()
    db.commit()

    _letzter_lauf.update(erfolgreich=True, meldung=None, zahlen=zahlen)
    logger.info(
        "Abgleich: %d gelesen, %d neu, %d bekannt, %d zur Entscheidung.",
        zahlen["gelesen"],
        zahlen["neu"],
        zahlen["duplikate"],
        zahlen["verdacht"],
    )
    return zahlen


def sync_einmal_mit_eigener_session() -> dict:
    db = SessionLocal()
    try:
        return sync_einmal(db)
    finally:
        db.close()


async def sync_schleife() -> None:
    while True:
        try:
            await asyncio.to_thread(sync_einmal_mit_eigener_session)
        except Exception:  # noqa: BLE001 - die Schleife darf nie sterben
            logger.exception("Fehler im Trade-Republic-Abgleich")
        await asyncio.sleep(TR_SYNC_INTERVAL_SECONDS)
