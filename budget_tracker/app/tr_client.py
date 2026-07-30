"""Kapselung von pytr: Anmeldung, Sitzung, Verbindung.

Die Anmeldung laeuft wie im Web-Login von Trade Republic: Telefonnummer und PIN
starten den Vorgang, danach kommt ein vierstelliger Code in die App (auf Wunsch
per SMS), der ihn abschliesst. Das Ergebnis sind Sitzungs-Cookies, mit denen
sich die folgenden Abrufe ohne weitere Eingabe erledigen lassen.

Zwei bewusste Entscheidungen:

*Die PIN wird nirgends gespeichert.* pytrs TradeRepublicApi verlangt sie zwar im
Konstruktor, benutzt sie aber ausschliesslich beim Start einer Neuanmeldung -
zum Wiederaufnehmen einer bestehenden Sitzung genuegt ein Platzhalter. Die PIN
lebt damit nur fuer die Dauer eines einzigen Anmeldevorgangs im Speicher. Der
Preis: laeuft die Sitzung ab, ist eine Eingabe noetig; ein vollautomatischer
Dauerbetrieb ist wegen des Codes ohnehin nicht moeglich.

*Die Cookies liegen unter /data* statt in ~/.pytr, damit sie ein Add-on-Update
ueberleben.

Der Import von pytr passiert absichtlich erst beim Aufruf: die Test-Suite und
die uebrige App laufen damit auch ohne installiertes pytr.
"""
import logging
import threading
from typing import Any

from app.config import TR_COOKIES_DATEI, TR_DIR

logger = logging.getLogger("budget_tracker.tr_client")

# TradeRepublicApi verlangt im Konstruktor eine PIN. Fuer alles ausser dem
# Start einer Neuanmeldung ist ihr Wert bedeutungslos - siehe Modulkopf.
_PLATZHALTER_PIN = "0000"

# Der WAF-Token wird rein in Python geholt (pytr/awswaf/). Die Voreinstellung
# "playwright" wuerde einen echten Chromium starten - in einem Add-on weder
# noetig noch angemessen, und der Browser ist im Image gar nicht enthalten.
_WAF_MODUS = "awswaf"

# pytr haelt WebSocket, Subscriptions und Antwortpuffer als Klassenattribute.
# Zwei gleichzeitige Laeufe wuerden sich damit gegenseitig die Antworten
# zuordnen. Alles, was eine Verbindung benutzt, geht durch dieses Schloss.
verbindungsschloss = threading.Lock()

# Laeuft gerade eine Anmeldung, muss dieselbe Instanz den Code entgegennehmen:
# Vorgangsnummer und Cookie-Jar stecken in ihr.
_anmeldung: Any = None


class NichtAngemeldet(RuntimeError):
    """Es gibt keine gueltige Sitzung - der Nutzer muss sich anmelden."""


class AnmeldungFehlgeschlagen(RuntimeError):
    """Der Anmeldevorgang wurde abgelehnt (falsche Nummer, PIN oder Code)."""


def pytr_verfuegbar() -> bool:
    try:
        import pytr.api  # noqa: F401
    except ImportError:
        return False
    return True


def _neue_api(telefonnummer: str, pin: str | None = None):
    from pytr.api import TradeRepublicApi

    TR_DIR.mkdir(parents=True, exist_ok=True)
    TR_DIR.chmod(0o700)
    return TradeRepublicApi(
        phone_no=telefonnummer,
        pin=pin or _PLATZHALTER_PIN,
        locale="de",
        save_cookies=True,
        cookies_file=str(TR_COOKIES_DATEI),
        # Existiert nie: ohne diesen Verweis wuerde pytr auf ~/.pytr/credentials
        # zurueckfallen und dort im Zweifel Zugangsdaten suchen.
        credentials_file=str(TR_DIR / "credentials-unbenutzt"),
        waf_token=_WAF_MODUS,
    )


def anmeldung_laeuft() -> bool:
    """Ob gerade ein Anmeldevorgang auf seinen Code wartet."""
    return _anmeldung is not None


def sitzung_vorhanden() -> bool:
    """Ob ueberhaupt eine Sitzung hinterlegt ist. Sagt nichts darueber, ob sie
    noch gilt - das kostet einen Abruf und passiert erst in verbindung()."""
    return TR_COOKIES_DATEI.exists()


def anmeldung_starten(telefonnummer: str, pin: str) -> int:
    """Startet den Web-Login. Gibt zurueck, wie viele Sekunden bis zur
    Moeglichkeit einer SMS-Zustellung vergehen."""
    global _anmeldung

    api = _neue_api(telefonnummer, pin)
    try:
        countdown = api.initiate_weblogin()
    except Exception as exc:  # pytr wirft ValueError, requests HTTPError
        logger.warning("Anmeldung konnte nicht gestartet werden: %s", type(exc).__name__)
        raise AnmeldungFehlgeschlagen(
            "Anmeldung konnte nicht gestartet werden. Stimmen Telefonnummer und PIN?"
        ) from exc

    _anmeldung = api
    return countdown


def code_erneut_senden() -> None:
    if _anmeldung is None:
        raise AnmeldungFehlgeschlagen("Es laeuft gerade keine Anmeldung.")
    _anmeldung.resend_weblogin()


def code_bestaetigen(code: str) -> None:
    """Schliesst die Anmeldung ab und legt die Sitzungs-Cookies an."""
    global _anmeldung

    if _anmeldung is None:
        raise AnmeldungFehlgeschlagen(
            "Es laeuft gerade keine Anmeldung - bitte erneut mit Telefonnummer und PIN beginnen."
        )
    try:
        _anmeldung.complete_weblogin(code.strip())
    except Exception as exc:
        logger.warning("Code wurde abgelehnt: %s", type(exc).__name__)
        raise AnmeldungFehlgeschlagen("Der Code wurde nicht akzeptiert.") from exc
    finally:
        # In beiden Faellen los: nach Erfolg steckt die Sitzung in der
        # Cookie-Datei, nach Misserfolg beginnt der Nutzer von vorn. So bleibt
        # die PIN nicht laenger als noetig im Speicher.
        _anmeldung = None


def anmeldung_abbrechen() -> None:
    global _anmeldung
    _anmeldung = None


def abmelden() -> None:
    """Verwirft die Sitzung. Die Anmeldedaten selbst gab es nie zu loeschen."""
    anmeldung_abbrechen()
    TR_COOKIES_DATEI.unlink(missing_ok=True)


def verbindung(telefonnummer: str):
    """Eine Instanz mit wiederaufgenommener Sitzung. Wirft NichtAngemeldet,
    wenn keine gueltige Sitzung existiert.

    Bewusst je Lauf neu: die WebSocket-Verbindung wird nur waehrend eines
    Abgleichs gebraucht und danach geschlossen. Eine dauerhaft offene
    Verbindung muesste ueber Stunden am Leben gehalten werden, ohne dass es
    etwas einbraechte.
    """
    if not sitzung_vorhanden():
        raise NichtAngemeldet("Keine Sitzung hinterlegt.")

    api = _neue_api(telefonnummer)
    try:
        erfolgreich = api.resume_websession()
    except Exception as exc:
        logger.warning("Sitzung konnte nicht geprueft werden: %s", type(exc).__name__)
        raise NichtAngemeldet("Die Sitzung liess sich nicht pruefen.") from exc

    if not erfolgreich:
        raise NichtAngemeldet("Die Sitzung ist abgelaufen - bitte neu anmelden.")

    # Klassenweite Reste eines vorherigen Laufs raeumen: pytr fuehrt
    # subscriptions und Antwortpuffer auf der Klasse, nicht auf der Instanz.
    type(api).subscriptions.clear()
    type(api)._previous_responses.clear()
    return api
