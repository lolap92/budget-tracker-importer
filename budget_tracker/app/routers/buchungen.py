import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.calculations import offene_umbuchungen, review_liste, vorhandene_buchungstitel
from app.config import BUCHUNGEN_PRO_SEITE
from app.database import get_db
from app.forecast_engine import erstelle_manuelles_vorkommen
from app.manual_entry import erstelle_manuelle_buchung, loesche_buchung
from app.models import Buchung, Topf, TopfUmbuchung
from app.topf_umbuchung import buchung_zu_topf_umbuchung
from app.umbuchung import (
    entmarkiere_umbuchung,
    markiere_als_umbuchung,
    vorschlaege_fuer_abgleich,
)
from app.webutils import ctx, redirect, templates

router = APIRouter()


@router.get("/buchungen")
def liste(
    request: Request,
    topf: int | None = None,
    seite: int = 1,
    db: Session = Depends(get_db),
):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()

    buchungen_q = db.query(Buchung)
    umbuchungen_q = db.query(TopfUmbuchung)
    if topf:
        buchungen_q = buchungen_q.filter(Buchung.topf_id == topf)
        umbuchungen_q = umbuchungen_q.filter(
            or_(TopfUmbuchung.von_topf_id == topf, TopfUmbuchung.nach_topf_id == topf)
        )

    alle = [
        {"art": "buchung", "datum": b.datum, "objekt": b, "id": b.id} for b in buchungen_q.all()
    ]
    alle += [
        {"art": "topf_umbuchung", "datum": u.datum, "objekt": u, "id": u.id}
        for u in umbuchungen_q.all()
    ]
    # Buchungen und Topf-Umbuchungen liegen in zwei Tabellen und muessen fuer
    # die gemeinsame Zeitachse in Python sortiert werden. Die ID als zweites
    # Kriterium haelt die Reihenfolge bei gleichem Datum stabil - sonst koennte
    # derselbe Eintrag beim Blaettern auf zwei Seiten auftauchen oder ganz
    # zwischen ihnen verschwinden.
    alle.sort(key=lambda e: (e["datum"], e["art"], e["id"]), reverse=True)

    seiten_gesamt = max(1, -(-len(alle) // BUCHUNGEN_PRO_SEITE))
    seite = max(1, min(seite, seiten_gesamt))
    start = (seite - 1) * BUCHUNGEN_PRO_SEITE

    return templates.TemplateResponse(
        "buchungen.html",
        ctx(
            request,
            eintraege=alle[start : start + BUCHUNGEN_PRO_SEITE],
            anzahl_gesamt=len(alle),
            seite=seite,
            seiten_gesamt=seiten_gesamt,
            toepfe=toepfe,
            gewaehlter_topf=topf,
            offene_anzahl=len(review_liste(db)),
            umbuchungen_anzahl=len(offene_umbuchungen(db)),
        ),
    )


@router.get("/buchungen/neu")
def neue_buchung_formular(request: Request, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    return templates.TemplateResponse(
        "buchung_neu.html",
        ctx(
            request,
            toepfe=toepfe,
            heute=dt.date.today().isoformat(),
            vorhandene_titel=vorhandene_buchungstitel(db),
        ),
    )


@router.post("/buchungen/neu")
async def neue_buchung_anlegen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    fehler = None
    try:
        art = form.get("art")
        topf_id = int(form["topf_id"])
        bezeichnung = form["bezeichnung"]
        betrag = Decimal((form.get("betrag") or "0").replace(",", "."))
        datum = dt.date.fromisoformat(form["datum"])
        if art == "vergangenheit":
            erstelle_manuelle_buchung(db, topf_id, bezeichnung, betrag, datum)
        elif art == "zukunft":
            erstelle_manuelles_vorkommen(db, topf_id, bezeichnung, betrag, datum)
        else:
            raise ValueError(
                "Bitte auswaehlen, ob die Buchung schon passiert ist oder noch erwartet wird."
            )
    except (ValueError, KeyError, InvalidOperation) as exc:
        fehler = str(exc)

    if fehler:
        return templates.TemplateResponse(
            "buchung_neu.html",
            ctx(
                request,
                toepfe=toepfe,
                heute=dt.date.today().isoformat(),
                fehler=fehler,
                vorhandene_titel=vorhandene_buchungstitel(db),
            ),
            status_code=400,
        )
    return redirect(request, "/buchungen")


@router.post("/buchungen/{buchung_id}/loeschen")
async def buchung_loeschen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    try:
        loesche_buchung(db, b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ziel = form.get("zurueck") or "/buchungen"
    return redirect(request, ziel)


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
        "buchung_detail.html",
        ctx(
            request,
            b=b,
            toepfe=toepfe,
            vorschlaege=vorschlaege,
            vorhandene_titel=vorhandene_buchungstitel(db),
        ),
    )


@router.post("/buchungen/{buchung_id}/topf")
async def topf_setzen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")

    titel = (form.get("titel") or "").strip()
    if not titel:
        toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
        vorschlaege = []
        if b.ist_umbuchung and b.topf_id is None:
            vorschlaege = vorschlaege_fuer_abgleich(db, b)
        return templates.TemplateResponse(
            "buchung_detail.html",
            ctx(
                request,
                b=b,
                toepfe=toepfe,
                vorschlaege=vorschlaege,
                vorhandene_titel=vorhandene_buchungstitel(db),
                fehler="Bitte einen sprechenden Titel vergeben.",
            ),
            status_code=400,
        )

    b.titel = titel
    b.topf_id = int(form["topf_id"])
    b.zuordnung_quelle = "manuell"
    db.commit()
    ziel = form.get("zurueck") or f"/buchungen/{buchung_id}"
    return redirect(request, ziel)


@router.post("/buchungen/{buchung_id}/zu-topf-umbuchung")
async def buchung_zu_umbuchung_route(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    try:
        gegen_topf_id = int(form["gegen_topf_id"])
        buchung_zu_topf_umbuchung(db, b, gegen_topf_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, "/buchungen")


@router.post("/buchungen/{buchung_id}/als-umbuchung")
async def als_umbuchung_markieren(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    markiere_als_umbuchung(db, b)
    ziel = form.get("zurueck") or f"/buchungen/{buchung_id}"
    return redirect(request, ziel)


@router.post("/buchungen/{buchung_id}/umbuchung-entfernen")
def umbuchung_entfernen(buchung_id: int, request: Request, db: Session = Depends(get_db)):
    b = db.get(Buchung, buchung_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    entmarkiere_umbuchung(db, b)
    return redirect(request, f"/buchungen/{buchung_id}")
