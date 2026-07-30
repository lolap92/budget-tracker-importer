"""Timeline-Event von Trade Republic -> Buchung.

Reine Uebersetzung, ohne Netz und ohne Datenbank: was hier hereinkommt, ist ein
Event aus `timelineTransactions`, dem die Abschnitte aus `timelineDetailV2`
unter dem Schluessel "details" beigelegt wurden - genau die Struktur, die auch
pytr in seinen Event-Dateien ablegt. Heraus kommen die Argumente fuer
app.import_core.uebernehmen().

Der Grund fuer den Detail-Abruf ist der Verwendungszweck: der CSV-Export der
Trade-Republic-App fuehrt zwar eine Spalte `payment_reference`, laesst sie aber
leer. Im Detail eines Events steht er als Feld "Referenz" im Abschnitt
"Uebersicht" - zusammen mit Name und IBAN der Gegenseite in einem eigenen
Abschnitt "Absender" bzw. "Empfaenger".

Wichtige Einschraenkung: die Abschnitts- und Feldnamen sind lokalisierte
Anzeigetexte, keine stabilen API-Schluessel. Die Verbindung laeuft deshalb fest
auf locale="de", und je Feld werden mehrere bekannte Beschriftungen akzeptiert.
Findet sich keine, bleibt das Feld leer - eine Buchung entsteht trotzdem.
"""
import datetime as dt
import logging
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("budget_tracker.tr_events")

# Die Zeitstempel der Timeline sind UTC. Eine Buchung um 23:30 UTC gehoert
# hierzulande bereits zum Folgetag - und das Datum entscheidet ueber Startdatum-
# Filter und Forecast-Abgleich, also wird umgerechnet.
try:
    LOKALE_ZONE: ZoneInfo | None = ZoneInfo("Europe/Berlin")
except ZoneInfoNotFoundError:  # pragma: no cover - nur ohne tzdata im Image
    logger.warning("Zeitzonendaten fehlen, Timeline-Zeitstempel werden als UTC gelesen.")
    LOKALE_ZONE = None

UEBERSICHT = ("Übersicht", "Overview")
ABSENDER = ("Absender", "Sender")
EMPFAENGER = ("Empfänger", "Empfaenger", "Recipient")

REFERENZ_LABELS = (
    "Referenz",
    "Verwendungszweck",
    "Reference",
    "Zahlungsreferenz",
    "Payment reference",
    "Betreff",
    "Nachricht",
    "Kommentar",
    "Note",
)
NAME_LABELS = ("Name", "Empfänger", "Absender", "Von", "An", "Händler", "Merchant")
IBAN_LABELS = ("IBAN",)

# Die App kennt die Typ-Bezeichnungen des CSV-Exports; die Timeline benutzt
# eigene. Uebersetzt wird, damit beide Wege dieselbe Buchung gleich benennen -
# und vor allem, damit die Zins-Regel der automatischen Topf-Zuordnung
# (app/assignment.py) weiter greift: sie prueft auf "INTEREST_PAYMENT".
# Nicht aufgefuehrte Typen werden unveraendert uebernommen; das ist ungefaehrlich,
# weil der Typ ausser bei Zinsen nur angezeigt wird.
TYP_MAPPING = {
    "INCOMING_TRANSFER": "TRANSFER_INBOUND",
    "INCOMING_TRANSFER_DELEGATION": "TRANSFER_INBOUND",
    "ACCOUNT_TRANSFER_INCOMING": "TRANSFER_INBOUND",
    "PAYMENT_INBOUND": "TRANSFER_INBOUND",
    "PAYMENT_INBOUND_CREDIT_CARD": "TRANSFER_INBOUND",
    "PAYMENT_INBOUND_SEPA_DIRECT_DEBIT": "TRANSFER_INBOUND",
    "OUTGOING_TRANSFER": "TRANSFER_OUTBOUND",
    "OUTGOING_TRANSFER_DELEGATION": "TRANSFER_OUTBOUND",
    "PAYMENT_OUTBOUND": "TRANSFER_OUTBOUND",
    # Seit dem Girokonto benennt Trade Republic Ueberweisungen neu.
    "BANK_TRANSACTION_INCOMING": "TRANSFER_INBOUND",
    "BANK_TRANSACTION_OUTGOING": "TRANSFER_OUTBOUND",
    "INTEREST_PAYOUT": "INTEREST_PAYMENT",
    "INTEREST_PAYOUT_CREATED": "INTEREST_PAYMENT",
    "card_successful_transaction": "CARD_PAYMENT",
    "card_order_billed": "CARD_PAYMENT",
    "card_failed_transaction": "CARD_PAYMENT",
    "card_successful_atm_withdrawal": "ATM_WITHDRAWAL",
    "card_refund": "CARD_REFUND",
    "card_tr_refund": "CARD_REFUND",
    "card_successful_oct": "CARD_REFUND",
    "ORDER_EXECUTED": "TRADE",
    "TRADE_INVOICE": "TRADE",
    "TRADE_CORRECTED": "TRADE",
    "SAVINGS_PLAN_EXECUTED": "TRADE",
    "SAVINGS_PLAN_INVOICE_CREATED": "TRADE",
    "trading_trade_executed": "TRADE",
    "trading_savingsplan_executed": "TRADE",
    "CREDIT": "DIVIDEND",
    "TAX_REFUND": "TAX_REFUND",
    "TAX_CORRECTION": "TAX_REFUND",
}

# Ein storniertes oder abgelehntes Event hat zwar einen Betrag, aber es hat nie
# Geld bewegt. Wuerde es importiert, waere der Kontostand dauerhaft falsch.
NICHT_AUSGEFUEHRT = {"canceled", "cancelled", "rejected", "failed"}


def _sektion(event: dict[str, Any], titel: tuple[str, ...]) -> dict[str, Any] | None:
    for sektion in _sektionen(event):
        if sektion.get("title") in titel:
            return sektion
    return None


def _feld(sektion: dict[str, Any] | None, labels: tuple[str, ...]) -> str | None:
    """Liest ein Feld einer Tabellen-Sektion. Deren `data` ist eine Liste aus
    {"title": Beschriftung, "detail": {"text": Wert}}; bei anderen Sektionstypen
    (header, steps) ist `data` ein Objekt und enthaelt keine Felder."""
    if sektion is None:
        return None
    data = sektion.get("data")
    if not isinstance(data, list):
        return None
    for label in labels:
        for eintrag in data:
            if not isinstance(eintrag, dict) or eintrag.get("title") != label:
                continue
            detail = eintrag.get("detail")
            text = detail.get("text") if isinstance(detail, dict) else detail
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def _sektionen(event: dict[str, Any]) -> list[dict[str, Any]]:
    return event.get("details", {}).get("sections", []) or []


def _referenz(event: dict[str, Any]) -> str | None:
    """Der Verwendungszweck - erst in der Uebersicht, dann ueberall sonst.

    Bis 1.26.1 wurde ausschliesslich der Abschnitt "Uebersicht" durchsucht.
    Das genuegte fuer die Ereignistypen, die es damals gab; mit dem Girokonto
    hat Trade Republic neue eingefuehrt (BANK_TRANSACTION_*), die ihre Angaben
    anders aufteilen. Die Beschriftung ist der verlaessliche Anker, nicht der
    Abschnitt, in dem sie steht.
    """
    uebersicht = _sektion(event, UEBERSICHT)
    treffer = _feld(uebersicht, REFERENZ_LABELS)
    if treffer:
        return treffer

    for sektion in _sektionen(event):
        if sektion.get("title") in UEBERSICHT:
            continue
        treffer = _feld(sektion, REFERENZ_LABELS)
        if treffer:
            return treffer

    treffer = _freitext(event)
    if treffer:
        return treffer

    _struktur_protokollieren(event)
    return None


def _freitext(event: dict[str, Any]) -> str | None:
    """Letzter Ausweg: ein Abschnitt vom Typ "note".

    Manche Ereignistypen fuehren gar keine beschriftete Referenz, sondern
    haengen den Text als freien Absatz an. Bewusst erst, wenn kein
    beschriftetes Feld gefunden wurde - ein Hinweis wie "Diese Ueberweisung
    wurde storniert" waere als Verwendungszweck falsch, aber immer noch
    besser als nichts, und im Zweifel korrigiert ihn der Mensch beim
    Zuordnen.
    """
    for sektion in _sektionen(event):
        if sektion.get("type") != "note":
            continue
        daten = sektion.get("data")
        if not isinstance(daten, dict):
            continue
        for schluessel in ("text", "title", "detail"):
            wert = daten.get(schluessel)
            if isinstance(wert, str) and wert.strip():
                logger.info(
                    "Verwendungszweck aus einem freien Textabschnitt von %s uebernommen.",
                    event.get("eventType"),
                )
                return wert.strip()[:200]
    return None


def _art(wert: Any) -> str:
    """Beschreibt einen Wert, ohne ihn preiszugeben."""
    if isinstance(wert, str):
        return f"str[{len(wert)}]"
    if isinstance(wert, dict):
        return "{" + ",".join(str(k) for k in wert) + "}"
    if isinstance(wert, list):
        return f"list[{len(wert)}]"
    return type(wert).__name__


def _struktur_protokollieren(event: dict[str, Any]) -> None:
    """Haelt den Aufbau eines Events fest, das keinen Verwendungszweck hergibt.

    Ohne das laesst sich ein unbekannt benanntes Feld nicht finden, ohne den
    kompletten Datensatz zu protokollieren - und darin stuenden Betraege,
    Namen und IBANs. Notiert werden deshalb Abschnittstyp, Beschriftungen und
    die *Art* der Werte (Zeichenkette der Laenge n, Objekt mit den Schluesseln
    x und y), nie deren Inhalt. Das genuegt, um zu erkennen, wo etwas steht -
    und reicht nicht, um zu erfahren, was.
    """
    if not _sektionen(event):
        return

    beschreibung = []
    for sektion in _sektionen(event):
        daten = sektion.get("data")
        if isinstance(daten, list):
            inhalt = ", ".join(
                str(e.get("title")) for e in daten if isinstance(e, dict) and e.get("title")
            )
        elif isinstance(daten, dict):
            inhalt = ", ".join(f"{k}={_art(v)}" for k, v in daten.items())
        else:
            inhalt = _art(daten)
        beschreibung.append(
            f"{sektion.get('title')!r}({sektion.get('type')}): {inhalt or '-'}"
        )

    logger.info(
        "Kein Verwendungszweck in Event vom Typ %s gefunden. Aufbau: %s",
        event.get("eventType"),
        " | ".join(beschreibung),
    )


def _datum(zeitstempel: str) -> dt.date | None:
    """'2024-09-02T17:49:12.516+0000' -> lokales Datum."""
    roh = (zeitstempel or "").strip()
    if not roh:
        return None
    # fromisoformat kennt vor Python 3.11 kein '+0000' ohne Doppelpunkt.
    if len(roh) >= 5 and (roh[-5] in "+-") and roh[-3] != ":":
        roh = roh[:-2] + ":" + roh[-2:]
    try:
        zeitpunkt = dt.datetime.fromisoformat(roh.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Konnte Zeitstempel nicht lesen: %r", zeitstempel)
        return None
    if zeitpunkt.tzinfo is not None and LOKALE_ZONE is not None:
        zeitpunkt = zeitpunkt.astimezone(LOKALE_ZONE)
    return zeitpunkt.date()


def _betrag(event: dict[str, Any]) -> Decimal | None:
    wert = (event.get("amount") or {}).get("value")
    if wert is None:
        return None
    try:
        return Decimal(str(wert))
    except InvalidOperation:
        logger.warning("Konnte Betrag nicht lesen: %r", wert)
        return None


def _gegenseite(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """Name und IBAN der Gegenseite. Bei Ueberweisungen stehen sie in einem
    eigenen Abschnitt, bei manchen Varianten stattdessen in der Uebersicht."""
    for titel in (ABSENDER, EMPFAENGER):
        sektion = _sektion(event, titel)
        name = _feld(sektion, NAME_LABELS)
        iban = _feld(sektion, IBAN_LABELS)
        if name or iban:
            return name, iban

    uebersicht = _sektion(event, UEBERSICHT)
    return _feld(uebersicht, NAME_LABELS), _feld(uebersicht, IBAN_LABELS)


def _beschreibung(event: dict[str, Any]) -> str | None:
    """Der Kopf des Details ist der sprechendste Text, den TR liefert
    ("Du hast 88,04 € von Klaus Mustermann erhalten") und entspricht dem, was
    der CSV-Export in `description` schreibt. Sonst der Untertitel."""
    for sektion in _sektionen(event):
        if sektion.get("type") == "header" and (sektion.get("title") or "").strip():
            return sektion["title"].strip()
    untertitel = (event.get("subtitle") or "").strip()
    return untertitel or None


def ist_kontobewegung(event: dict[str, Any]) -> bool:
    """Nur Events, die tatsaechlich Geld auf dem Konto bewegt haben, werden zu
    Buchungen. Alles andere - Dokumente, Kartenpruefungen, Depotuebertraege,
    stornierte Auftraege - hat keinen Betrag oder keinen ausgefuehrten Status.
    """
    if (event.get("status") or "").lower() in NICHT_AUSGEFUEHRT:
        return False
    betrag = _betrag(event)
    return betrag is not None and betrag != 0


def zeile_aus_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Gibt die Argumente fuer import_core.uebernehmen() zurueck, oder None,
    wenn das Event keine Kontobewegung ist."""
    if not ist_kontobewegung(event):
        return None

    transaction_id = event.get("id")
    datum = _datum(event.get("timestamp", ""))
    betrag = _betrag(event)
    if not transaction_id or datum is None or betrag is None:
        logger.warning(
            "Event ohne id/Zeitstempel/Betrag uebersprungen: %r", event.get("id") or event.get("title")
        )
        return None

    name, iban = _gegenseite(event)
    event_typ = event.get("eventType") or ""

    return {
        "transaction_id": transaction_id,
        "datum": datum,
        "betrag": betrag,
        "typ": TYP_MAPPING.get(event_typ, event_typ),
        "verwendungszweck": _referenz(event),
        "empfaenger_name": name or (event.get("title") or "").strip() or None,
        "empfaenger_iban": iban,
        "beschreibung": _beschreibung(event),
    }
