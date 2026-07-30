"""Zentrale Pfade und Konstanten. Alles hier ist per Umgebungsvariable
uebersteuerbar, damit sich die App auch ausserhalb des HA-Containers
(z.B. lokal zum Testen) starten laesst."""
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "budget_tracker.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

HA_CONFIG_DIR = Path(os.environ.get("HA_CONFIG_DIR", "/homeassistant"))
BUDGET_TRACKER_DIR = HA_CONFIG_DIR / "budget_tracker"
DEFAULT_IMPORT_DIR = str(BUDGET_TRACKER_DIR / "imports")
SEED_FILE = BUDGET_TRACKER_DIR / "seed-data.json"

# Die vier Toepfe sind laut Konzept fest vorgegeben.
TOPF_NAMEN = ["Haus Kredit", "Haus Renovierung", "Urlaub", "Sonderausgaben"]

# Erlaubte Rhythmen einer Forecast-Regel. Ein unbekannter Wert erzeugt in
# _occurrence_dates() stillschweigend nie ein Vorkommen - die Regel waere
# angelegt, wuerde aber nie greifen, ohne dass es irgendwo auffiele.
RHYTHMEN = ("monatlich", "jaehrlich", "befristet")
SONDERAUSGABEN_TOPF = "Sonderausgaben"
HAUS_KREDIT_TOPF = "Haus Kredit"

# Toleranzen fuer automatisches Matching (Startwerte laut Konzept Abschnitt 6/12).
# Auf 7 Tage angehoben: wiederkehrende Ueberweisungen rutschen an Monats-
# grenzen durch Wochenenden/Feiertage oft mehrere Tage in den Folgemonat,
# was mit den urspruenglichen 3 Tagen regelmaessig nicht mehr traf.
FORECAST_DATUM_TOLERANZ_TAGE = 7
FORECAST_BETRAG_TOLERANZ = 0  # exakter Betrag als Startwert

# Toleranz fuer den Abgleich-Vorschlag zwischen zwei Bankumbuchungen.
UMBUCHUNG_DATUM_TOLERANZ_TAGE = 10

DIRECTORY_SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "30"))

# Trade-Republic-Schnittstelle. Sitzungs-Cookies liegen unter /data, damit sie
# ein Add-on-Update ueberleben - pytr wuerde sie sonst nach ~/.pytr schreiben,
# also in den fluechtigen Teil des Containers. Die PIN wird bewusst nirgends
# gespeichert (siehe app/tr_client.py).
TR_DIR = DATA_DIR / "pytr"
TR_COOKIES_DATEI = TR_DIR / "cookies.txt"


def tr_sync_intervall_sekunden() -> int:
    """Abstand zwischen zwei automatischen Abgleichen; 0 heisst: nur auf Knopfdruck.

    Einstellbar in den Add-on-Optionen, voreingestellt sind sechs Stunden.

    Seltener abzufragen senkt das Risiko einer Sperre praktisch nicht: der
    Bot-Schutz von Trade Republic sitzt vor der *Anmeldung*, nicht vor den
    Abrufen, und ein Lauf sind eine Handvoll Anfragen. Ganz ohne automatischen
    Lauf kann es sogar schaden - laeuft die Sitzung mangels Nutzung ab, sind
    mehr Anmeldungen noetig, und genau die gehen durch den Schutz.
    """
    aus_umgebung = os.environ.get("TR_SYNC_INTERVAL_SECONDS")
    if aus_umgebung is not None:
        return max(0, int(aus_umgebung))

    stunden = read_addon_options().get("tr_sync_intervall_stunden", 6)
    try:
        stunden = int(stunden)
    except (TypeError, ValueError):
        stunden = 6
    return max(0, stunden) * 3600


# GoCardless Bank Account Data - der PSD2-Zugang zum DKB-Kontostand.
#
# Die Zugangsdaten stehen in den Add-on-Optionen und *nicht* in der Datenbank:
# haushaltsbuch.db enthaelt Fachdaten, keine Zugaenge. Gelesen werden sie ueber
# read_addon_options() aus /data/options.json - derselbe Weg wie beim
# Abgleich-Turnus. Die Umgebungsvariablen daneben existieren fuer den Betrieb
# ausserhalb des Add-ons (lokale Entwicklung, Tests).
GOCARDLESS_BASIS_URL = os.environ.get(
    "GOCARDLESS_BASE_URL", "https://bankaccountdata.gocardless.com/api/v2"
)

# Wie lange eine Freigabe laufen soll. 90 Tage sind das regulatorische Maximum
# ohne erneute Anmeldung bei der Bank (SCA) - kuerzer zu waehlen braechte nur
# haeufigeres Erneuern.
GOCARDLESS_FREIGABE_TAGE = 90

# Wie kurz vor Ablauf der Freigabe die Startseite daran erinnert.
EXTERNKONTO_WARNUNG_TAGE = 7


def gocardless_zugangsdaten() -> tuple[str, str]:
    """Secret-ID und Secret-Key. Leere Zeichenketten heissen: nicht hinterlegt."""
    optionen = read_addon_options()
    secret_id = os.environ.get("GOCARDLESS_SECRET_ID") or optionen.get(
        "gocardless_secret_id", ""
    )
    secret_key = os.environ.get("GOCARDLESS_SECRET_KEY") or optionen.get(
        "gocardless_secret_key", ""
    )
    return (secret_id or "").strip(), (secret_key or "").strip()


def gocardless_redirect_url() -> str:
    """Optionale feste Redirect-Adresse fuer den Freigabe-Abschluss.

    Die App laeuft nur hinter dem Home-Assistant-Ingress und hat damit keine
    feste, von aussen erreichbare Adresse. Der Einrichtungs-Weg kommt deshalb
    ohne Rueckleitung aus (der Freigabe-Link wird von Hand geoeffnet, den Rest
    erledigt eine Statusabfrage). Wer eine erreichbare Adresse hat - Nabu Casa
    oder die lokale HA-Adresse im selben Netz - kann sie hier nachtragen; dann
    springt die Bank am Ende dorthin zurueck.
    """
    aus_umgebung = os.environ.get("GOCARDLESS_REDIRECT_URL")
    if aus_umgebung is not None:
        return aus_umgebung.strip()
    return str(read_addon_options().get("gocardless_redirect_url", "") or "").strip()


def externkonto_cache_sekunden() -> int:
    """Wie lange ein abgerufener Saldo als aktuell genug gilt.

    Der kostenlose GoCardless-Tarif erlaubt nur wenige Kontoabrufe pro Tag
    (ueblicherweise vier). Abgerufen wird ausschliesslich beim Aufruf der
    Gesamtvermoegen-Seite und nur, wenn der letzte Abruf aelter ist als diese
    Spanne - kein Hintergrundlauf, der auch dann zaehlt, wenn niemand hinsieht.

    Sechs Stunden als Startwert, nicht vier: bei vier Stunden koennte ein Tag
    mit ueber den ganzen Tag verteilten Aufrufen rechnerisch sechs Abrufe
    ergeben und damit ueber dem Kontingent liegen. Sechs Stunden decken vier
    Abrufe ab und passen damit auch im ungeguenstigsten Fall.
    """
    aus_umgebung = os.environ.get("EXTERNKONTO_CACHE_SECONDS")
    if aus_umgebung is not None:
        return max(0, int(aus_umgebung))

    stunden = read_addon_options().get("gesamtvermoegen_cache_stunden", 6)
    try:
        stunden = int(stunden)
    except (TypeError, ValueError):
        stunden = 6
    return max(0, stunden) * 3600


# Wie weit jeder Lauf ueber die juengste bekannte Buchung hinaus zurueckschaut.
# Faengt nachtraeglich verbuchte Vorgaenge ein; alles Aeltere ist ueber die
# transaction_id ohnehin bekannt und kostet nur einen Mengenvergleich.
TR_SYNC_RUECKGRIFF_TAGE = 14
FORECAST_HORIZON_MONATE = 12

# Seitengroesse der Buchungsliste. Nach ein paar Jahren CSV-Import waeren es
# sonst mehrere tausend Eintraege auf einer Seite.
BUCHUNGEN_PRO_SEITE = 50

# Wie viele vergangene Eintraege die Zeitachse auf der Forecast-Seite zeigt.
# Sie ist eine Uebersicht, keine vollstaendige Liste - dafuer gibt es
# /buchungen, worauf am Ende der gekuerzten Liste auch verwiesen wird.
ZEITACHSE_VERGANGENHEIT_MAX = 25

# Wie weit vor dem aktuellen Monat noch Vorkommen erzeugt werden. Ohne diese
# Untergrenze legt eine Regel mit weit zurueckliegendem Startdatum (der
# Normalfall bei seed-data.json) fuer jeden vergangenen Monat ein Vorkommen an.
# Diese finden nie eine reale Buchung, bleiben dauerhaft offen und werden von
# prognose_topf() in jedem Prognosemonat mitsummiert - die Prognose liegt dann
# um ein Vielfaches der Rate daneben. Ein Monat Rueckgriff bleibt, damit eine
# Buchung, die knapp in den Vormonat gehoerte, ihr Vorkommen noch findet
# (siehe FORECAST_DATUM_TOLERANZ_TAGE).
FORECAST_RUECKWIRKEND_MONATE = 1


def version() -> str:
    """Die Add-on-Version aus dem Manifest.

    Gelesen statt im Quelltext gepflegt: eine zweite Stelle mit derselben Zahl
    laeuft frueher oder spaeter auseinander, und dann zeigt die App eine
    Version an, die es nicht gibt.
    """
    manifest = Path(__file__).resolve().parent.parent / "config.yaml"
    try:
        for zeile in manifest.read_text(encoding="utf-8").splitlines():
            treffer = re.match(r'^version:\s*"?([^"\s]+)"?', zeile)
            if treffer:
                return treffer.group(1)
    except OSError:
        pass
    return "unbekannt"


def read_addon_options() -> dict:
    """Liest optionale Add-on-Optionen aus /data/options.json (Supervisor-Konvention)."""
    options_path = DATA_DIR / "options.json"
    if options_path.exists():
        try:
            return json.loads(options_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}
