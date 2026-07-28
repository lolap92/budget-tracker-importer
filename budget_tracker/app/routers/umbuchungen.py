from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.calculations import offene_umbuchungen
from app.database import get_db
from app.models import Buchung, Topf
from app.umbuchung import (
    abgleichen,
    endgueltig_verbuchen,
    vorschlaege_fuer_abgleich,
)
from app.webutils import ctx, redirect, templates

router = APIRouter()


@router.get("/umbuchungen")
def liste(request: Request, db: Session = Depends(get_db)):
    offene = offene_umbuchungen(db)
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    vorschlaege = {b.id: vorschlaege_fuer_abgleich(db, b) for b in offene}
    return templates.TemplateResponse(
        "umbuchungen.html", ctx(request, offene=offene, toepfe=toepfe, vorschlaege=vorschlaege)
    )


@router.post("/umbuchungen/abgleichen")
async def abgleichen_route(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    a = db.get(Buchung, int(form["buchung_a"]))
    b = db.get(Buchung, int(form["buchung_b"]))
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    try:
        abgleichen(db, a, b, int(form["topf_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, "/umbuchungen")


@router.post("/umbuchungen/{buchung_id}/final")
async def final_route(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    try:
        endgueltig_verbuchen(db, b, int(form["topf_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, "/umbuchungen")
