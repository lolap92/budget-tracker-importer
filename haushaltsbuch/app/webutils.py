"""Kleine Helfer fuer die Web-Schicht: Jinja-Setup, Formatierung, und ein
Redirect-Helfer, der den Home-Assistant-Ingress-Praefix (X-Ingress-Path)
respektiert, da Ingress den Container ohne den Praefix anspricht, der
Browser aber Links/Redirects mit Praefix erwartet."""
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def eur(value) -> str:
    if value is None:
        return "-"
    d = Decimal(value)
    negativ = d < 0
    d = abs(d)
    formatiert = f"{d:,.2f}"
    formatiert = formatiert.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if negativ else ''}{formatiert} €"


def datum_de(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y")


def monat_de(value) -> str:
    if value is None:
        return "-"
    monate = [
        "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ]
    return f"{monate[value.month - 1]} {value.year}"


templates.env.filters["eur"] = eur
templates.env.filters["datum_de"] = datum_de
templates.env.filters["monat_de"] = monat_de


def base_path(request: Request) -> str:
    return request.scope.get("root_path") or ""


def ctx(request: Request, **kwargs) -> dict:
    return {"request": request, "base": base_path(request), **kwargs}


def redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=base_path(request) + path, status_code=303)
