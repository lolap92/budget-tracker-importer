import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.calculations import (
    prognose_topf,
    vorhandene_buchungstitel,
    zeitachse_topf,
    ziel_fortschritt_haus_kredit,
)
from app.chart import render_prognose_chart
from app.config import SONDERAUSGABEN_TOPF
from app.database import get_db
from app.forecast_engine import (
    ensure_forecast_vorkommen,
    erstelle_manuelles_vorkommen,
    vorkommen_auf_sonderausgaben_buchen,
    vorkommen_verschieben,
)
from app.models import ForecastRegel, ForecastVorkommen, Topf
from app.webutils import ctx, redirect, templates, topfklasse

router = APIRouter()


def _sonderausgaben_id(db: Session) -> int | None:
    topf = db.query(Topf).filter(Topf.name == SONDERAUSGABEN_TOPF).first()
    return topf.id if topf else None


@router.get("/forecast")
def uebersicht(request: Request, topf: int | None = None, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    gewaehlter_topf = db.get(Topf, topf) if topf else None
    if gewaehlter_topf is None and toepfe:
        gewaehlter_topf = toepfe[0]

    daten = None
    if gewaehlter_topf is not None:
        prognose = prognose_topf(db, gewaehlter_topf)
        zeitachse = zeitachse_topf(db, gewaehlter_topf)
        regeln = (
            db.query(ForecastRegel)
            .filter(ForecastRegel.topf_id == gewaehlter_topf.id)
            .order_by(ForecastRegel.bezeichnung)
            .all()
        )
        daten = {
            "topf": gewaehlter_topf,
            "prognose": prognose,
            "zeitachse": zeitachse,
            "regeln": regeln,
            "chart_svg": render_prognose_chart(prognose.monatswerte, topfklasse(gewaehlter_topf.name)),
            "ziel": ziel_fortschritt_haus_kredit(db, gewaehlter_topf),
            "sonderausgaben_topf_id": _sonderausgaben_id(db),
        }

    return templates.TemplateResponse(
        "forecast.html",
        ctx(
            request,
            toepfe=toepfe,
            gewaehlter_topf_id=gewaehlter_topf.id if gewaehlter_topf else None,
            daten=daten,
            vorhandene_titel=vorhandene_buchungstitel(db),
        ),
    )


@router.get("/regeln/neu")
def regel_formular(request: Request, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    return templates.TemplateResponse(
        "regel_neu.html",
        ctx(
            request,
            toepfe=toepfe,
            heute=dt.date.today().isoformat(),
            vorhandene_titel=vorhandene_buchungstitel(db),
        ),
    )


@router.post("/forecast/regel/neu")
async def regel_anlegen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    fehler = None
    topf_id = None
    try:
        topf_id = int(form["topf_id"])
        regel = ForecastRegel(
            topf_id=topf_id,
            bezeichnung=form["bezeichnung"],
            betrag=Decimal((form.get("betrag") or "0").replace(",", ".")),
            rhythmus=form["rhythmus"],
            anker_tag=int(form["anker_tag"]),
            start_datum=dt.date.fromisoformat(form["start_datum"]),
            end_datum=dt.date.fromisoformat(form["end_datum"]) if form.get("end_datum") else None,
        )
        db.add(regel)
        db.flush()
        ensure_forecast_vorkommen(db)
        db.commit()
    except (ValueError, KeyError, InvalidOperation) as exc:
        db.rollback()
        fehler = str(exc)

    if fehler:
        return templates.TemplateResponse(
            "regel_neu.html",
            ctx(
                request,
                toepfe=toepfe,
                heute=dt.date.today().isoformat(),
                fehler=fehler,
                vorhandene_titel=vorhandene_buchungstitel(db),
            ),
            status_code=400,
        )

    zurueck = form.get("zurueck") or f"/forecast?topf={topf_id}"
    return redirect(request, zurueck)


@router.post("/forecast/vorkommen/neu")
async def vorkommen_anlegen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    topf_id = int(form["topf_id"])
    erstelle_manuelles_vorkommen(
        db,
        topf_id,
        form["bezeichnung"],
        Decimal((form.get("erwarteter_betrag") or "0").replace(",", ".")),
        dt.date.fromisoformat(form["erwartetes_datum"]),
    )
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/verschieben")
def verschieben_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    vorkommen_verschieben(v)
    db.commit()
    return redirect(request, f"/forecast?topf={v.topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/sonderausgaben")
def sonderausgaben_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    topf_id = v.topf_id
    try:
        vorkommen_auf_sonderausgaben_buchen(db, v)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/topf/{topf_id}/einstellungen")
async def topf_einstellungen(topf_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    topf = db.get(Topf, topf_id)
    if topf is None:
        raise HTTPException(status_code=404, detail="Topf nicht gefunden")

    jahresziel = (form.get("jahresziel") or "").replace(",", ".").strip()
    topf.jahresziel = Decimal(jahresziel) if jahresziel else None

    sondertilgung = form.get("sondertilgung_datum")
    topf.sondertilgung_datum = dt.date.fromisoformat(sondertilgung) if sondertilgung else None

    db.commit()
    return redirect(request, f"/forecast?topf={topf_id}")
