import datetime as dt
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.calculations import (
    prognose_topf,
    regel_erste_faelligkeit,
    review_liste,
    vorhandene_buchungstitel,
    zeitachse_topf,
)
from app.chart import render_prognose_chart
from app.config import SONDERAUSGABEN_TOPF
from app.database import get_db
from app.forecast_engine import (
    ensure_forecast_vorkommen,
    erstelle_manuelles_vorkommen,
    jahresregel_anker_warnung,
    regel_bearbeiten,
    regel_erstellen,
    vorkommen_auf_sonderausgaben_buchen,
    vorkommen_bearbeiten,
    vorkommen_loeschen,
    vorkommen_manuell_verknuepfen,
    vorkommen_verschieben,
)
from app.models import Buchung, ForecastRegel, ForecastVorkommen, Topf
from app.webutils import ctx, redirect, templates, topfklasse

router = APIRouter()


def _sonderausgaben_id(db: Session) -> int | None:
    topf = db.query(Topf).filter(Topf.name == SONDERAUSGABEN_TOPF).first()
    return topf.id if topf else None


@router.get("/forecast")
def uebersicht(request: Request, topf: str | None = None, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()

    alle_gewaehlt = topf == "alle"
    gewaehlter_topf: Topf | None = None
    if not alle_gewaehlt and topf:
        try:
            gewaehlter_topf = db.get(Topf, int(topf))
        except ValueError:
            gewaehlter_topf = None

    # Ohne (oder mit ungueltigem) Topf-Parameter startet die Seite auf
    # Sonderausgaben statt auf dem ersten Topf in der Reihenfolge.
    if not alle_gewaehlt and gewaehlter_topf is None:
        gewaehlter_topf = next(
            (t for t in toepfe if t.name == SONDERAUSGABEN_TOPF), toepfe[0] if toepfe else None
        )

    daten = None
    if alle_gewaehlt:
        prognose = prognose_topf(db, None)
        daten = {
            "topf": None,
            "prognose": prognose,
            "chart_svg": render_prognose_chart(prognose.monatswerte, "alle"),
        }
    elif gewaehlter_topf is not None:
        prognose = prognose_topf(db, gewaehlter_topf)
        zeitachse = zeitachse_topf(db, gewaehlter_topf)
        regeln = (
            db.query(ForecastRegel)
            .filter(ForecastRegel.topf_id == gewaehlter_topf.id)
            .order_by(ForecastRegel.bezeichnung)
            .all()
        )
        for r in regeln:
            r.erste_faelligkeit = regel_erste_faelligkeit(db, r.id)
            r.anker_warnung = jahresregel_anker_warnung(r)
        daten = {
            "topf": gewaehlter_topf,
            "prognose": prognose,
            "zeitachse": zeitachse,
            "regeln": regeln,
            "chart_svg": render_prognose_chart(prognose.monatswerte, topfklasse(gewaehlter_topf.name)),
            "sonderausgaben_topf_id": _sonderausgaben_id(db),
            "kandidaten_buchungen": review_liste(db),
        }

    return templates.TemplateResponse(
        "forecast.html",
        ctx(
            request,
            toepfe=toepfe,
            alle_gewaehlt=alle_gewaehlt,
            gewaehlter_topf_id=gewaehlter_topf.id if gewaehlter_topf else None,
            daten=daten,
            vorhandene_titel=vorhandene_buchungstitel(db),
        ),
    )


@router.get("/forecast/regeln")
def regeln_uebersicht(request: Request, topf: int | None = None, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    gewaehlter_topf = db.get(Topf, topf) if topf else None
    if gewaehlter_topf is None and toepfe:
        gewaehlter_topf = toepfe[0]

    regeln = []
    if gewaehlter_topf is not None:
        regeln = (
            db.query(ForecastRegel)
            .filter(ForecastRegel.topf_id == gewaehlter_topf.id)
            .order_by(ForecastRegel.bezeichnung)
            .all()
        )
        for r in regeln:
            r.erste_faelligkeit = regel_erste_faelligkeit(db, r.id)
            r.anker_warnung = jahresregel_anker_warnung(r)

    return templates.TemplateResponse(
        "forecast_regeln.html",
        ctx(
            request,
            toepfe=toepfe,
            gewaehlter_topf_id=gewaehlter_topf.id if gewaehlter_topf else None,
            topf=gewaehlter_topf,
            regeln=regeln,
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
        regel_erstellen(
            db,
            topf_id=topf_id,
            bezeichnung=form["bezeichnung"],
            betrag=Decimal((form.get("betrag") or "0").replace(",", ".")),
            rhythmus=form["rhythmus"],
            anker_tag=int(form["anker_tag"]),
            start_datum=dt.date.fromisoformat(form["start_datum"]),
            end_datum=dt.date.fromisoformat(form["end_datum"]) if form.get("end_datum") else None,
        )
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


@router.post("/forecast/regel/{regel_id}/bearbeiten")
async def regel_bearbeiten_route(regel_id: int, request: Request, db: Session = Depends(get_db)):
    regel = db.get(ForecastRegel, regel_id)
    if regel is None:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")
    form = await request.form()
    topf_id = int(form.get("topf_id") or regel.topf_id)
    try:
        regel_bearbeiten(
            db,
            regel,
            topf_id=topf_id,
            bezeichnung=form["bezeichnung"],
            betrag=Decimal((form.get("betrag") or "0").replace(",", ".")),
            rhythmus=form["rhythmus"],
            anker_tag=int(form["anker_tag"]),
            start_datum=dt.date.fromisoformat(form["start_datum"]),
            end_datum=dt.date.fromisoformat(form["end_datum"]) if form.get("end_datum") else None,
        )
        db.commit()
    except (ValueError, KeyError, InvalidOperation) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/forecast/vorkommen/neu")
async def vorkommen_anlegen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    try:
        topf_id = int(form["topf_id"])
        erstelle_manuelles_vorkommen(
            db,
            topf_id,
            form["bezeichnung"],
            Decimal((form.get("erwarteter_betrag") or "0").replace(",", ".")),
            dt.date.fromisoformat(form["erwartetes_datum"]),
        )
    except (ValueError, KeyError, InvalidOperation) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/verschieben")
def verschieben_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    vorkommen_verschieben(v)
    db.commit()
    return redirect(request, f"/forecast?topf={v.topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/bearbeiten")
async def vorkommen_bearbeiten_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    form = await request.form()
    topf_id = v.topf_id
    try:
        vorkommen_bearbeiten(
            db,
            v,
            bezeichnung=form["bezeichnung"],
            erwarteter_betrag=Decimal((form.get("erwarteter_betrag") or "0").replace(",", ".")),
            erwartetes_datum=dt.date.fromisoformat(form["erwartetes_datum"]),
        )
        db.commit()
    except (ValueError, KeyError, InvalidOperation) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/verknuepfen")
async def verknuepfen_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    form = await request.form()
    buchung = db.get(Buchung, int(form["buchung_id"])) if form.get("buchung_id") else None
    if buchung is None:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    topf_id = v.topf_id
    try:
        vorkommen_manuell_verknuepfen(db, v, buchung)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


@router.post("/forecast/vorkommen/{vorkommen_id}/loeschen")
def vorkommen_loeschen_route(vorkommen_id: int, request: Request, db: Session = Depends(get_db)):
    v = db.get(ForecastVorkommen, vorkommen_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Vorkommen nicht gefunden")
    topf_id = v.topf_id
    try:
        vorkommen_loeschen(db, v)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return redirect(request, f"/forecast?topf={topf_id}")


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

