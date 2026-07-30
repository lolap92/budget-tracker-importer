"""Kapselung der GoCardless-Bank-Account-Data-Schnittstelle (PSD2).

Warum dieser Weg und nicht FinTS/HBCI direkt zur DKB: FinTS verlangt den echten
Bank-PIN im System - genau das Risiko, das die App bei Trade Republic bewusst
vermeidet (dort wird die PIN nie gespeichert, siehe app/tr_client.py). Ueber
einen lizenzierten Kontoinformationsdienst bleibt statt des Bankzugangs nur ein
jederzeit widerrufbarer API-Zugang.

Drei bewusste Entscheidungen:

*Die Zugangsdaten stehen in den Add-on-Optionen*, nicht in der Datenbank. Die
Fachdatenbank enthaelt Buchungen, keine Zugaenge.

*Der Zugriffstoken lebt nur im Speicher.* GoCardless gibt ihn fuer 24 Stunden
aus; ihn auf die Platte zu schreiben brauchte Verschluesselung, Schluesselab-
lage und eine Loeschstrategie - fuer etwas, das sich aus den Zugangsdaten in
einer einzigen Anfrage neu holen laesst. Ein Neustart kostet damit genau einen
zusaetzlichen Aufruf. Die Ausgabe des Tokens zaehlt nicht gegen das Abruf-
kontingent der Konten.

*Ohne Rueckleitung.* Der Freigabe-Ablauf verlangt eine feste Redirect-Adresse,
die eine Ingress-App nicht hat. Statt darauf zu bauen, wird der Freigabe-Link
von Hand geoeffnet und der Abschluss ueber den Status der Requisition erkannt
(Variante C des Konzepts). Eine eigene Adresse laesst sich als Add-on-Option
nachtragen.

Die Antworten der Schnittstelle werden defensiv gelesen: GoCardless liefert den
Status einer Freigabe je nach Version als Kuerzel ("LN") oder ausgeschrieben
("LINKED"), und die Salden je nach Bank unter verschiedenen Typbezeichnungen.
"""
import datetime as dt
import logging
import threading
from decimal import Decimal, InvalidOperation

import requests

from app.config import (
    GOCARDLESS_BASIS_URL,
    GOCARDLESS_FREIGABE_TAGE,
    gocardless_redirect_url,
    gocardless_zugangsdaten,
)

logger = logging.getLogger("budget_tracker.gocardless")

ZEITLIMIT = 30.0

# Welcher der gelieferten Salden gilt. Banken liefern mehrere Sichten auf
# dasselbe Konto; gesucht ist der Betrag, ueber den tatsaechlich verfuegt werden
# kann - also der verfuegbare Zwischenstand vor dem zuletzt abgeschlossenen
# Buchungstag. Ohne feste Reihenfolge haenge der angezeigte Wert davon ab, in
# welcher Reihenfolge die Bank ihre Salden auflistet.
SALDO_TYPEN = (
    "interimAvailable",
    "closingBooked",
    "interimBooked",
    "expected",
    "forwardAvailable",
    "openingBooked",
)

# GoCardless verlangt beim Anlegen einer Freigabe eine Redirect-Adresse, auch
# wenn sie - wie hier - nicht gebraucht wird. Die Adresse von GoCardless selbst
# ist die harmloseste Wahl: dort landet der Browser nach der Bankfreigabe und
# das Fenster kann geschlossen werden. Der Abschluss wird ueber den Status der
# Requisition erkannt, nicht ueber die Rueckleitung.
STANDARD_REDIRECT = "https://bankaccountdata.gocardless.com/"

# Die Freigabe deckt nur ab, was die Anzeige braucht: den Kontostand und die
# Kontostammdaten zur Identifikation. Umsaetze werden bewusst nicht angefragt -
# die Buchungen kommen von Trade Republic, das DKB-Konto steuert nur eine Zahl
# bei.
ZUGRIFFSUMFANG = ["balances", "details"]

# Zustaende einer Requisition, in beiden Schreibweisen.
VERKNUEPFT = ("LN", "LINKED")
ABGELAUFEN = ("EX", "EXPIRED")
ABGELEHNT = ("RJ", "REJECTED")


class GoCardlessFehler(RuntimeError):
    """Der Abruf ist gescheitert - mit einem Text, der dem Nutzer etwas sagt."""


class ZugangsdatenFehlen(GoCardlessFehler):
    """Secret-ID und Secret-Key sind nicht in den Add-on-Optionen hinterlegt."""


# Zugriffstoken und sein Ablauf, ausschliesslich im Speicher. Das Schloss
# verhindert, dass zwei gleichzeitige Seitenaufrufe zwei Token holen.
_token_schloss = threading.Lock()
_token: dict = {"wert": None, "gueltig_bis": None}


def zugangsdaten_vorhanden() -> bool:
    secret_id, secret_key = gocardless_zugangsdaten()
    return bool(secret_id and secret_key)


def token_verwerfen() -> None:
    """Naechster Aufruf holt einen frischen Token. Fuer Tests und fuer den Fall,
    dass die Zugangsdaten in den Add-on-Optionen gewechselt wurden."""
    with _token_schloss:
        _token.update(wert=None, gueltig_bis=None)


def _fehlertext(antwort: requests.Response) -> str:
    """Uebersetzt eine abgelehnte Antwort in etwas Handhabbares.

    GoCardless legt den Grund je nach Endpunkt unterschiedlich ab - mal als
    summary/detail, mal als Feldfehler. Ohne diese Aufbereitung stuende auf der
    Seite nur "HTTP 400", was keinen Schritt weiterhilft.
    """
    try:
        daten = antwort.json()
    except ValueError:
        daten = {}

    if isinstance(daten, dict):
        for schluessel in ("detail", "summary"):
            if isinstance(daten.get(schluessel), str):
                return daten[schluessel]
        for wert in daten.values():
            if isinstance(wert, dict) and isinstance(wert.get("summary"), str):
                return wert["summary"]
            if isinstance(wert, list) and wert and isinstance(wert[0], str):
                return wert[0]

    if antwort.status_code == 401:
        return "GoCardless hat die Zugangsdaten abgelehnt (Secret-ID/Secret-Key)."
    if antwort.status_code == 429:
        return (
            "GoCardless hat das Abruf-Kontingent gesperrt (zu viele Abrufe fuer "
            "heute). Der zuletzt geholte Stand bleibt gueltig."
        )
    return f"GoCardless antwortete mit HTTP {antwort.status_code}."


def _anfrage(methode: str, pfad: str, token: str | None = None, **kwargs):
    url = f"{GOCARDLESS_BASIS_URL}{pfad}"
    kopf = {"Accept": "application/json"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"

    try:
        antwort = requests.request(methode, url, headers=kopf, timeout=ZEITLIMIT, **kwargs)
    except requests.RequestException as exc:
        logger.warning("GoCardless nicht erreichbar: %s", type(exc).__name__)
        raise GoCardlessFehler(
            f"GoCardless war nicht erreichbar ({type(exc).__name__})."
        ) from exc

    logger.info("GoCardless: %s %s -> %s", methode, pfad, antwort.status_code)
    if antwort.status_code >= 400:
        raise GoCardlessFehler(_fehlertext(antwort))

    try:
        return antwort.json()
    except ValueError as exc:
        raise GoCardlessFehler("GoCardless hat keine lesbare Antwort geschickt.") from exc


def _token_holen() -> str:
    """Ein gueltiger Zugriffstoken - aus dem Speicher oder frisch geholt.

    Die Ablaufzeit wird um eine Minute vorgezogen: ein Token, der waehrend der
    naechsten Anfrage ablaeuft, wuerde einen vermeidbaren Fehler erzeugen.
    """
    secret_id, secret_key = gocardless_zugangsdaten()
    if not (secret_id and secret_key):
        raise ZugangsdatenFehlen(
            "In den Add-on-Optionen sind gocardless_secret_id und "
            "gocardless_secret_key noch nicht hinterlegt."
        )

    with _token_schloss:
        jetzt = dt.datetime.utcnow()
        if _token["wert"] and _token["gueltig_bis"] and _token["gueltig_bis"] > jetzt:
            return _token["wert"]

        daten = _anfrage(
            "POST", "/token/new/", json={"secret_id": secret_id, "secret_key": secret_key}
        )
        wert = daten.get("access")
        if not wert:
            raise GoCardlessFehler("GoCardless hat keinen Zugriffstoken geliefert.")

        try:
            sekunden = int(daten.get("access_expires") or 0)
        except (TypeError, ValueError):
            sekunden = 0
        sekunden = max(60, sekunden or 86400)
        _token.update(
            wert=wert, gueltig_bis=jetzt + dt.timedelta(seconds=sekunden - 60)
        )
        return wert


def institutionen(land: str = "de") -> list[dict]:
    """Die Banken eines Landes, alphabetisch. Kennung, Name und Logo.

    Die Kennung der DKB wird beim Einrichten hieraus uebernommen und nicht im
    Quelltext hartkodiert - GoCardless kann sie aendern.
    """
    daten = _anfrage("GET", f"/institutions/?country={land}", token=_token_holen())
    banken = [
        {
            "id": eintrag.get("id"),
            "name": eintrag.get("name") or eintrag.get("id"),
            "bic": eintrag.get("bic") or "",
            "logo": eintrag.get("logo") or "",
        }
        for eintrag in (daten or [])
        if eintrag.get("id")
    ]
    return sorted(banken, key=lambda b: b["name"].lower())


def _zustimmung_anlegen(institution_id: str) -> str | None:
    """Legt die Zustimmung mit fester Laufzeit und minimalem Umfang an.

    Scheitert das - nicht jede Bank unterstuetzt jeden Zugriffsumfang -, wird
    ohne eigene Zustimmung weitergemacht: GoCardless setzt dann seine
    Voreinstellung (90 Tage). Die Freigabe daran scheitern zu lassen waere die
    schlechtere Wahl.
    """
    try:
        daten = _anfrage(
            "POST",
            "/agreements/enduser/",
            token=_token_holen(),
            json={
                "institution_id": institution_id,
                "max_historical_days": 1,
                "access_valid_for_days": GOCARDLESS_FREIGABE_TAGE,
                "access_scope": ZUGRIFFSUMFANG,
            },
        )
    except GoCardlessFehler as exc:
        logger.info("Eigene Zustimmung nicht moeglich (%s), GoCardless-Vorgabe gilt.", exc)
        return None
    return daten.get("id")


def freigabe_starten(institution_id: str, referenz: str) -> dict:
    """Startet eine Kontofreigabe. Gibt Kennung, Freigabe-Link und Zustimmung.

    Der Link wird vom Nutzer selbst geoeffnet; auf die Rueckleitung kommt es
    nicht an (siehe Modulkopf).
    """
    zustimmung = _zustimmung_anlegen(institution_id)
    rumpf = {
        "redirect": gocardless_redirect_url() or STANDARD_REDIRECT,
        "institution_id": institution_id,
        "reference": referenz,
        "user_language": "DE",
    }
    if zustimmung:
        rumpf["agreement"] = zustimmung

    daten = _anfrage("POST", "/requisitions/", token=_token_holen(), json=rumpf)
    if not daten.get("id") or not daten.get("link"):
        raise GoCardlessFehler("GoCardless hat keinen Freigabe-Link geliefert.")
    return {
        "requisition_id": daten["id"],
        "link": daten["link"],
        "agreement_id": daten.get("agreement") or zustimmung,
    }


def freigabe_status(requisition_id: str) -> dict:
    """Wo die Freigabe steht: Zustand, freigegebene Konten, Link zum Fortsetzen."""
    daten = _anfrage("GET", f"/requisitions/{requisition_id}/", token=_token_holen())
    zustand = str(daten.get("status") or "").upper()
    konten = [k for k in (daten.get("accounts") or []) if k]
    return {
        "zustand": zustand,
        "konten": konten,
        # Der Zustand allein genuegt nicht: manche Banken lassen die
        # Requisition auf "GA"/"granting access" stehen, obwohl das Konto
        # bereits freigegeben ist. Umgekehrt gibt es "LN" nie ohne Konto.
        "verknuepft": bool(konten) and zustand not in ABGELAUFEN + ABGELEHNT,
        "abgelaufen": zustand in ABGELAUFEN,
        "abgelehnt": zustand in ABGELEHNT,
        "link": daten.get("link") or "",
        "agreement_id": daten.get("agreement") or None,
    }


def _datum(roh) -> dt.date | None:
    if not roh:
        return None
    text = str(roh).replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None


def freigabe_gueltig_bis(agreement_id: str | None) -> dt.date | None:
    """Wann die Freigabe ablaeuft: Zustimmungsdatum plus ihre Laufzeit.

    Die Requisition selbst nennt kein Ablaufdatum - es steht an der Zustimmung.
    Ist keine hinterlegt oder nicht lesbar, faellt die Rechnung auf heute plus
    die Regel-Laufzeit zurueck: eine Warnung ein paar Tage zu frueh ist
    harmlos, eine fehlende Warnung nicht.
    """
    angenommen = None
    laufzeit = GOCARDLESS_FREIGABE_TAGE

    if agreement_id:
        try:
            daten = _anfrage(
                "GET", f"/agreements/enduser/{agreement_id}/", token=_token_holen()
            )
        except GoCardlessFehler as exc:
            logger.info("Zustimmung %s nicht lesbar (%s).", agreement_id, exc)
            daten = {}
        angenommen = _datum(daten.get("accepted")) or _datum(daten.get("created"))
        try:
            laufzeit = int(daten.get("access_valid_for_days") or laufzeit)
        except (TypeError, ValueError):
            pass

    return (angenommen or dt.date.today()) + dt.timedelta(days=laufzeit)


def konto_kennzeichen(account_id: str) -> str:
    """IBAN oder Kontoname zu einer Konto-Kennung - fuer die Auswahl, wenn eine
    Freigabe mehrere Konten umfasst.

    Bewusst die Stammdaten-Abfrage und nicht die Detailabfrage: diese zaehlt
    nicht gegen das taegliche Abruf-Kontingent. Scheitert sie, wird die nackte
    Kennung angezeigt - fuer eine Auswahl reicht auch die.
    """
    try:
        daten = _anfrage("GET", f"/accounts/{account_id}/", token=_token_holen())
    except GoCardlessFehler:
        return ""
    return str(daten.get("iban") or daten.get("name") or daten.get("owner_name") or "")


def saldo(account_id: str) -> Decimal:
    """Der aktuelle Kontostand. Zaehlt gegen das taegliche Abruf-Kontingent."""
    daten = _anfrage("GET", f"/accounts/{account_id}/balances/", token=_token_holen())
    return saldo_aus_antwort(daten)


def saldo_aus_antwort(daten: dict) -> Decimal:
    """Waehlt aus den gelieferten Salden den verfuegbaren aus.

    Getrennt vom Abruf, damit die Auswahl ohne Netz pruefbar bleibt.
    """
    salden = [s for s in ((daten or {}).get("balances") or []) if isinstance(s, dict)]
    if not salden:
        raise GoCardlessFehler("GoCardless hat zu diesem Konto keinen Saldo geliefert.")

    nach_typ = {str(s.get("balanceType") or ""): s for s in salden}
    gewaehlt = next((nach_typ[t] for t in SALDO_TYPEN if t in nach_typ), salden[0])

    betrag = (gewaehlt.get("balanceAmount") or {}).get("amount")
    try:
        return Decimal(str(betrag))
    except (InvalidOperation, TypeError):
        raise GoCardlessFehler(
            f"Der gelieferte Saldo war keine Zahl ({betrag!r})."
        ) from None
