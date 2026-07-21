import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Topf
from app.topf_umbuchung import erstelle_topf_umbuchung
from app.webutils import ctx, redirect, templates

router = APIRouter()


@router.get("/topf-umbuchung/neu")
def formular(request: Request, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    return templates.TemplateResponse(
        "topf_umbuchung_neu.html", ctx(request, toepfe=toepfe, heute=dt.date.today().isoformat())
    )


@router.post("/topf-umbuchung/neu")
async def anlegen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    fehler = None
    try:
        betrag = Decimal((form.get("betrag") or "0").replace(",", "."))
        erstelle_topf_umbuchung(
            db,
            von_topf_id=int(form["von_topf_id"]),
            nach_topf_id=int(form["nach_topf_id"]),
            betrag=betrag,
            datum=dt.date.fromisoformat(form["datum"]) if form.get("datum") else None,
            kommentar=form.get("kommentar"),
        )
    except (ValueError, InvalidOperation, KeyError) as exc:
        fehler = str(exc)

    if fehler:
        return templates.TemplateResponse(
            "topf_umbuchung_neu.html",
            ctx(request, toepfe=toepfe, heute=dt.date.today().isoformat(), fehler=fehler),
            status_code=400,
        )

    return redirect(request, "/")
