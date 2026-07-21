import datetime as dt

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap_manuell, ist_bootstrapped, seed_datei_vorhanden
from app.config import TOPF_NAMEN
from app.database import get_db
from app.webutils import ctx, redirect, templates

router = APIRouter()

TOPF_SLUGS = [(name.lower().replace(" ", "_"), name) for name in TOPF_NAMEN]


@router.get("/bootstrap")
def bootstrap_seite(request: Request, db: Session = Depends(get_db)):
    if ist_bootstrapped(db):
        return redirect(request, "/")
    return templates.TemplateResponse(
        "bootstrap.html",
        ctx(
            request,
            topf_slugs=TOPF_SLUGS,
            heute=dt.date.today().isoformat(),
            seed_datei_vorhanden=seed_datei_vorhanden(),
        ),
    )


@router.post("/bootstrap")
async def bootstrap_absenden(request: Request, db: Session = Depends(get_db)):
    if ist_bootstrapped(db):
        return redirect(request, "/")

    form = await request.form()
    fehler = None
    try:
        start_datum = dt.date.fromisoformat(form.get("start_datum", ""))
        startsalden = {}
        for slug, name in TOPF_SLUGS:
            wert = (form.get(f"startsaldo_{slug}") or "0").replace(",", ".").strip()
            startsalden[name] = float(wert) if wert else 0.0
        bootstrap_manuell(db, start_datum, startsalden)
    except (ValueError, TypeError) as exc:
        fehler = f"Eingabe ungueltig: {exc}"

    if fehler:
        return templates.TemplateResponse(
            "bootstrap.html",
            ctx(
                request,
                topf_slugs=TOPF_SLUGS,
                heute=dt.date.today().isoformat(),
                seed_datei_vorhanden=seed_datei_vorhanden(),
                fehler=fehler,
            ),
            status_code=400,
        )

    return redirect(request, "/")
