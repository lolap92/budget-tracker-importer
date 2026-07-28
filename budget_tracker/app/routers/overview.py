from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import watcher
from app.calculations import (
    kontostand_gesamt,
    neuestes_buchungsdatum,
    offene_umbuchungen,
    prognose_topf,
    review_liste,
    sondertilgung_status,
)
from app.database import get_db
from app.models import Topf
from app.webutils import ctx, templates

router = APIRouter()


@router.get("/")
def uebersicht(request: Request, db: Session = Depends(get_db)):
    toepfe = db.query(Topf).order_by(Topf.reihenfolge).all()
    karten = []
    for topf in toepfe:
        prognose = prognose_topf(db, topf)
        karten.append(
            {
                "topf": topf,
                "saldo": prognose.aktueller_saldo,
                "tiefpunkt": prognose.tiefpunkt,
                "tiefpunkt_monat": prognose.tiefpunkt_monat,
                "minus_warnung": prognose.minus_warnung,
                "sondertilgung": sondertilgung_status(db, topf),
            }
        )
    # Der Kontostand bleibt bankgenau und enthaelt daher auch Buchungen, die
    # noch keinem Topf zugeordnet sind (offene Zuordnungen, schwebende
    # Umbuchungen). Er laeuft dadurch zwangslaeufig von der Summe der
    # Topf-Salden auseinander - die Differenz wird ausgewiesen, statt sie
    # kommentarlos zwischen zwei direkt untereinander stehenden Zahlen
    # stehen zu lassen.
    kontostand = kontostand_gesamt(db)
    nicht_zugeordnet = kontostand - sum((k["saldo"] for k in karten), Decimal(0))

    return templates.TemplateResponse(
        "overview.html",
        ctx(
            request,
            kontostand=kontostand,
            nicht_zugeordnet=nicht_zugeordnet,
            karten=karten,
            watcher_status=watcher.status(),
            offene_anzahl=len(review_liste(db)),
            umbuchungen_anzahl=len(offene_umbuchungen(db)),
            stand_datum=neuestes_buchungsdatum(db),
        ),
    )


@router.get("/mehr")
def mehr(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "mehr.html",
        ctx(
            request,
            offene_anzahl=len(review_liste(db)),
            umbuchungen_anzahl=len(offene_umbuchungen(db)),
        ),
    )
