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
import re
import threading
from typing import Any
from urllib.parse import urlsplit

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
    try:
        from pytr.api import TradeRepublicApi
    except ImportError as exc:
        # Kann im Add-on nicht passieren, wohl aber bei lokaler Entwicklung
        # ohne pytr. Eine verstaendliche Meldung statt eines 500ers.
        raise AnmeldungFehlgeschlagen(
            "Die Bibliothek pytr ist nicht installiert - der direkte Abgleich "
            "steht in dieser Installation nicht zur Verfuegung."
        ) from exc

    TR_DIR.mkdir(parents=True, exist_ok=True)
    TR_DIR.chmod(0o700)
    api = TradeRepublicApi(
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
    # pytr setzt seinen Logger auf DEBUG und protokolliert dort komplette
    # Antworten - darunter die Anmeldedaten. Sichtbar wird das derzeit nur
    # deshalb nicht, weil sein Handler auf INFO steht. Darauf verlassen wir uns
    # nicht: hier wird es festgeschrieben.
    api.log.setLevel(logging.INFO)
    api._websession.hooks["response"].append(_antwort_protokollieren)
    return api


def _antwort_protokollieren(antwort, *args, **kwargs):
    """Jede HTTP-Antwort mit Methode, Pfad und Status ins Protokoll.

    Ohne das ist eine fehlgeschlagene Anmeldung nicht zu deuten: `requests`
    folgt Umleitungen selbsttaetig und macht dabei aus einem POST ein GET.
    Landet das auf einem Pfad ohne GET, kommt am Ende ein HTTP 405 heraus -
    ein Status, den Trade Republic nie geschickt hat. Erst die Kette zeigt das.
    """
    pfad = urlsplit(antwort.url).path
    # Der Bestaetigungscode steht im Pfad - er gehoert nicht ins Protokoll.
    if "/auth/web/login/" in pfad:
        pfad = pfad.split("/auth/web/login/")[0] + "/auth/web/login/…"
    logger.info("Trade Republic: %s %s -> %s", antwort.request.method, pfad, antwort.status_code)
    return antwort


def telefonnummer_normalisieren(eingabe: str) -> str:
    """Bringt die Nummer in die Form, die Trade Republic erwartet (+49...).

    Auf dem Handy tippt man Nummern mit Leerzeichen, Bindestrichen oder als
    0151..., und die Schnittstelle antwortet darauf schlicht mit "abgelehnt" -
    ununterscheidbar von einer falschen PIN.
    """
    roh = re.sub(r"[\s\-/().]", "", eingabe or "")
    if roh.startswith("00"):
        roh = "+" + roh[2:]
    elif roh.startswith("0"):
        # Landesvorwahl fehlt. Deutschland ist die einzige sinnvolle Annahme -
        # Trade Republic gibt es nur in Europa, aber raten waere hier falsch.
        roh = "+49" + roh[1:]
    return roh


def anmeldung_laeuft() -> bool:
    """Ob gerade ein Anmeldevorgang auf seinen Code wartet."""
    return _anmeldung is not None


def sitzung_vorhanden() -> bool:
    """Ob ueberhaupt eine Sitzung hinterlegt ist. Sagt nichts darueber, ob sie
    noch gilt - das kostet einen Abruf und passiert erst in verbindung()."""
    return TR_COOKIES_DATEI.exists()


def _waf_token_besorgen(api, manuell: str | None) -> str | None:
    """Holt den Bot-Schutz-Token von Amazon WAF - rein in Python, ohne Browser.

    Scheitert das, wird trotzdem weitergemacht: die Antwort von Trade Republic
    auf den Anmeldeversuch sagt uns dann, ob der Token ueberhaupt noetig war
    (HTTP 403) oder ob es an etwas anderem lag. Ein stiller Abbruch hier
    verwechselt beides.
    """
    if manuell:
        logger.info("Verwende manuell hinterlegten WAF-Token.")
        return manuell.strip()
    try:
        token = api._fetch_waf_token_awswaf()
    except Exception:  # noqa: BLE001 - jede Ursache ist hier gleich behandelbar
        logger.warning("WAF-Token konnte nicht ermittelt werden.", exc_info=True)
        return None
    if not token:
        logger.warning("WAF-Token war leer.")
    return token


def _anmeldefehler(exc: Exception, ohne_token: bool = False, abgelehnt: str = "") -> str:
    """Uebersetzt die Ausnahme in etwas, mit dem sich etwas anfangen laesst.

    Vorher hiess jeder Fehlschlag "Stimmen Telefonnummer und PIN?" - auch dann,
    wenn Trade Republic die Anfrage gar nicht erst angesehen hatte.
    """
    antwort = getattr(exc, "response", None)
    status = getattr(antwort, "status_code", None)

    if status in (400, 401):
        return abgelehnt or "Telefonnummer oder PIN wurden nicht akzeptiert."
    if status == 403:
        hinweis = (
            "Trade Republic hat die Anfrage abgewiesen (Bot-Schutz). "
            "Das liegt nicht an Telefonnummer oder PIN."
        )
        if ohne_token:
            hinweis += (
                " Der Schutz-Token liess sich nicht automatisch ermitteln - er kann "
                "unten aus dem Browser hinterlegt werden."
            )
        return hinweis
    if status == 405:
        # Trade Republic verschickt selbst kein 405 auf diesem Pfad. Der Status
        # entsteht, wenn die Anfrage vorher umgeleitet wurde: `requests` folgt
        # der Umleitung und macht aus dem POST ein GET, das der Zielpfad nicht
        # kennt. Umgeleitet wird typischerweise auf die Bot-Schutz-Pruefung.
        hinweis = (
            "Die Anfrage wurde umgeleitet und dann abgewiesen (HTTP 405) - fast immer "
            "der Bot-Schutz vor der Anmeldung. Das liegt nicht an Telefonnummer oder PIN."
        )
        if ohne_token:
            hinweis += (
                " Der Schutz-Token liess sich nicht automatisch ermitteln; unten lässt "
                "er sich aus dem Browser hinterlegen."
            )
        return hinweis
    if status == 429:
        return "Zu viele Versuche. Trade Republic bittet um etwas Geduld."
    if status is not None:
        return f"Trade Republic antwortete mit HTTP {status}."
    if isinstance(exc, ValueError):
        # pytr reicht die Fehlerliste von Trade Republic durch.
        return f"Trade Republic meldet: {exc}"
    return (
        f"Die Anfrage kam nicht durch ({type(exc).__name__}). "
        "Details stehen im Add-on-Protokoll."
    )


def anmeldung_starten(telefonnummer: str, pin: str, waf_token: str | None = None) -> int:
    """Startet den Web-Login. Gibt zurueck, wie viele Sekunden bis zur
    Moeglichkeit einer SMS-Zustellung vergehen."""
    global _anmeldung

    api = _neue_api(telefonnummer, pin)
    token = _waf_token_besorgen(api, waf_token)
    # Konkreter Wert oder None: pytr wuerde sonst selbst noch einmal losziehen.
    api._waf_token = token

    try:
        countdown = api.initiate_weblogin()
    except Exception as exc:  # pytr wirft ValueError, requests HTTPError
        antwort = getattr(exc, "response", None)
        umleitungen = [
            f"{v.status_code} -> {urlsplit(v.headers.get('Location', '')).path or '?'}"
            for v in getattr(antwort, "history", []) or []
        ]
        logger.warning(
            "Anmeldung fehlgeschlagen (WAF-Token %s, Antwort %s, Umleitungen: %s, Text: %.200s).",
            "vorhanden" if token else "fehlt",
            getattr(antwort, "status_code", "-"),
            " | ".join(umleitungen) or "keine",
            getattr(antwort, "text", "") or "",
            exc_info=True,
        )
        raise AnmeldungFehlgeschlagen(_anmeldefehler(exc, ohne_token=not token)) from exc

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
        logger.warning("Code wurde abgelehnt.", exc_info=True)
        raise AnmeldungFehlgeschlagen(
            _anmeldefehler(exc, abgelehnt="Der Code wurde nicht akzeptiert.")
        ) from exc
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
    # subscriptions und Antwortpuffer auf der Klasse, nicht auf der Instanz -
    # eine neue Instanz erbt sie sonst. Interna, deshalb defensiv: verschwinden
    # sie in einer kuenftigen pytr-Version, soll der Abgleich weiterlaufen und
    # nicht an der Aufraeumarbeit scheitern.
    for name in ("subscriptions", "_previous_responses"):
        rest = getattr(type(api), name, None)
        if hasattr(rest, "clear"):
            rest.clear()
    return api
