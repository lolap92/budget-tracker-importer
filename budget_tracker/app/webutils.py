"""Kleine Helfer fuer die Web-Schicht: Jinja-Setup, Formatierung, und ein
Redirect-Helfer, der den Home-Assistant-Ingress-Praefix (X-Ingress-Path)
respektiert, da Ingress den Container ohne den Praefix anspricht, der
Browser aber Links/Redirects mit Praefix erwartet."""
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from app.config import DEMO_MODUS
from app.dateutils import nach_lokaler_zeit
from app.manual_entry import ist_loeschbar, ist_manuelle_buchung, ist_zu_umbuchung_konvertierbar

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["demo_modus"] = DEMO_MODUS


def eur(value) -> str:
    if value is None:
        return "-"
    d = Decimal(value)
    negativ = d < 0
    d = abs(d)
    formatiert = f"{d:,.2f}"
    formatiert = formatiert.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if negativ else ''}{formatiert} €"


def stueck(value) -> str:
    """Stueckzahlen im Depot: bis zu sechs Nachkommastellen (Sparplaene kaufen
    Bruchteile), aber ohne die Nullen, die dabei fast immer hinten stehen."""
    if value is None:
        return "-"
    formatiert = f"{Decimal(value):,.6f}".rstrip("0").rstrip(".")
    return formatiert.replace(",", "X").replace(".", ",").replace("X", ".")


def prozent(value) -> str:
    """Anteile im Depot: eine Nachkommastelle reicht, um zwei Positionen zu
    unterscheiden, ohne eine Genauigkeit vorzutaeuschen, die ein schwankender
    Kurs ohnehin nicht hat."""
    if value is None:
        return "-"
    return f"{Decimal(value):.1f}".replace(".", ",") + " %"


def zeit_de(value) -> str:
    """Zeitpunkt in lokaler Zeit, ohne Zeitzonen-Kuerzel.

    Gespeichert wird UTC; wer in der Oberflaeche auf die Uhr schaut, will die
    Zeit sehen, die seine Uhr auch zeigt. Das Kuerzel entfaellt bewusst - es
    stand nur da, weil die Zahl davor eine Erklaerung brauchte.
    """
    if value is None:
        return "–"
    return nach_lokaler_zeit(value).strftime("%d.%m.%Y %H:%M")


def datum_de(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y")


def monat_de(value) -> str:
    if value is None:
        return "-"
    monate = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ]
    return f"{monate[value.month - 1]} {value.year}"


def monat_kurz(value) -> str:
    if value is None:
        return "-"
    monate = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    return f"{monate[value.month - 1]} {value.strftime('%y')}"


def datum_kurz(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.")


TOPF_KLASSEN = {
    "Haus Kredit": "kredit",
    "Haus Renovierung": "renov",
    "Urlaub": "urlaub",
    "Sonderausgaben": "sonder",
}


def topfklasse(name) -> str:
    if name is None:
        return "sonder"
    return TOPF_KLASSEN.get(name, "sonder")


templates.env.filters["eur"] = eur
templates.env.filters["stueck"] = stueck
templates.env.filters["prozent"] = prozent
templates.env.filters["datum_de"] = datum_de
templates.env.filters["zeit_de"] = zeit_de
templates.env.filters["datum_kurz"] = datum_kurz
templates.env.filters["monat_kurz"] = monat_kurz
templates.env.filters["monat_de"] = monat_de
templates.env.filters["topfklasse"] = topfklasse
templates.env.filters["ist_manuell"] = ist_manuelle_buchung
templates.env.filters["ist_loeschbar"] = ist_loeschbar
templates.env.filters["ist_konvertierbar"] = ist_zu_umbuchung_konvertierbar


def base_path(request: Request) -> str:
    return request.scope.get("root_path") or ""


def ctx(request: Request, **kwargs) -> dict:
    return {"request": request, "base": base_path(request), **kwargs}


def redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=base_path(request) + path, status_code=303)
