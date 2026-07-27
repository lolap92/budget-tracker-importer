from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.calculations import review_liste, vorhandene_buchungstitel
from app.database import get_db
from app.models import Buchung, Topf
from app.webutils import ctx, redirect, templates

router = APIRouter()


@router.get("/zuordnen")
def liste(request: Request, db: Session = Depends(get_db)):
    offene = review_liste(db)
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    return templates.TemplateResponse(
        "zuordnen.html",
        ctx(request, offene=offene, toepfe=toepfe, vorhandene_titel=vorhandene_buchungstitel(db)),
    )


@router.post("/zuordnen/{buchung_id}")
async def topf_zuweisen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    titel = (form.get("titel") or "").strip()
    if not titel:
        raise HTTPException(status_code=400, detail="Bitte einen sprechenden Titel vergeben.")
    b.titel = titel
    b.topf_id = int(form["topf_id"])
    b.zuordnung_quelle = "manuell"
    db.commit()
    return redirect(request, "/zuordnen")
