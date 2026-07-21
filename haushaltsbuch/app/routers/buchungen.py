from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Buchung, Topf, TopfUmbuchung
from app.umbuchung import (
    entmarkiere_umbuchung,
    markiere_als_umbuchung,
    vorschlaege_fuer_abgleich,
)
from app.webutils import ctx, redirect, templates

router = APIRouter()


@router.get("/buchungen")
def liste(request: Request, topf: int | None = None, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()

    buchungen_q = db.query(Buchung)
    umbuchungen_q = db.query(TopfUmbuchung)
    if topf:
        buchungen_q = buchungen_q.filter(Buchung.topf_id == topf)
        umbuchungen_q = umbuchungen_q.filter(
            or_(TopfUmbuchung.von_topf_id == topf, TopfUmbuchung.nach_topf_id == topf)
        )

    eintraege = [{"art": "buchung", "datum": b.datum, "objekt": b} for b in buchungen_q.all()]
    eintraege += [
        {"art": "topf_umbuchung", "datum": u.datum, "objekt": u} for u in umbuchungen_q.all()
    ]
    eintraege.sort(key=lambda e: (e["datum"]), reverse=True)

    return templates.TemplateResponse(
        "buchungen.html",
        ctx(request, eintraege=eintraege, toepfe=toepfe, gewaehlter_topf=topf),
    )


@router.get("/buchungen/{buchung_id}")
def detail(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    vorschlaege = []
    if b.ist_umbuchung and b.topf_id is None:
        vorschlaege = vorschlaege_fuer_abgleich(db, b)
    return templates.TemplateResponse(
        "buchung_detail.html", ctx(request, b=b, toepfe=toepfe, vorschlaege=vorschlaege)
    )


@router.post("/buchungen/{buchung_id}/topf")
async def topf_setzen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    b.topf_id = int(form["topf_id"])
    b.zuordnung_quelle = "manuell"
    db.commit()
    ziel = form.get("zurueck") or f"/buchungen/{buchung_id}"
    return redirect(request, ziel)


@router.post("/buchungen/{buchung_id}/als-umbuchung")
def als_umbuchung_markieren(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    markiere_als_umbuchung(db, b)
    return redirect(request, f"/buchungen/{buchung_id}")


@router.post("/buchungen/{buchung_id}/umbuchung-entfernen")
def umbuchung_entfernen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    entmarkiere_umbuchung(db, b)
    return redirect(request, f"/buchungen/{buchung_id}")
