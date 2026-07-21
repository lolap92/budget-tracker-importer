from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import watcher
from app.calculations import kontostand_gesamt, prognose_topf, ziel_fortschritt_haus_kredit
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
                "ziel": ziel_fortschritt_haus_kredit(db, topf),
            }
        )
    return templates.TemplateResponse(
        "overview.html",
        ctx(
            request,
            kontostand=kontostand_gesamt(db),
            karten=karten,
            watcher_status=watcher.status(),
        ),
    )
