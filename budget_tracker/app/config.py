"""Zentrale Pfade und Konstanten. Alles hier ist per Umgebungsvariable
uebersteuerbar, damit sich die App auch ausserhalb des HA-Containers
(z.B. lokal zum Testen) starten laesst."""
import json
import os
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
SONDERAUSGABEN_TOPF = "Sonderausgaben"
HAUS_KREDIT_TOPF = "Haus Kredit"

# Toleranzen fuer automatisches Matching (Startwerte laut Konzept Abschnitt 6/12).
FORECAST_DATUM_TOLERANZ_TAGE = 3
FORECAST_BETRAG_TOLERANZ = 0  # exakter Betrag als Startwert

# Toleranz fuer den Abgleich-Vorschlag zwischen zwei Bankumbuchungen.
UMBUCHUNG_DATUM_TOLERANZ_TAGE = 10

DIRECTORY_SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "30"))
FORECAST_HORIZON_MONATE = 12


def read_addon_options() -> dict:
    """Liest optionale Add-on-Optionen aus /data/options.json (Supervisor-Konvention)."""
    options_path = DATA_DIR / "options.json"
    if options_path.exists():
        try:
            return json.loads(options_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}
