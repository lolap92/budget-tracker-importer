from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app import tr_client, tr_sync, watcher
from app.calculations import (
    kontostand_gesamt,
    letzter_import_zeitpunkt,
    neuestes_buchungsdatum,
    offene_umbuchungen,
    prognose_topf,
    review_liste,
    sondertilgung_status,
)
from app.database import get_db
from app.models import ImportVerdacht, Topf, TradeRepublicKonto
from app.tr_depot import aktueller_snapshot
from app.webutils import ctx, templates

router = APIRouter()


def _import_warnung(status: dict) -> str | None:
    """Kurztext fuer die "Zu tun"-Karte - nur, wenn der Import wirklich klemmt.

    Der Watcher scannt alle 30 Sekunden; "letzter Scan vor 12 Sekunden" waere
    als Dauereinblendung reines Rauschen. Gemeldet wird deshalb nur, was ein
    Eingreifen erfordert: ein fehlendes Import-Verzeichnis (CSV liegt am
    falschen Ort) oder Zeilen bzw. Dateien, die der letzte Import nicht
    verarbeiten konnte.
    """
    if status.get("verzeichnis_gefunden") is False:
        return "Import-Verzeichnis nicht gefunden"
    zahlen = status.get("letzte_zahlen") or {}
    if zahlen.get("fehler"):
        return f"Letzter Import: {zahlen['fehler']} Zeile(n) nicht verarbeitet"
    return None


def _tr_warnung(db: Session) -> str | None:
    """Meldet sich nur, wenn der Abgleich ein Eingreifen braucht.

    Zwei Faelle: eine Sitzung, die abgelaufen ist (der Abgleich laeuft dann
    still ins Leere, was sonst niemandem auffiele), und Bewegungen, die auf
    eine Entscheidung warten. Wer die Schnittstelle gar nicht nutzt, sieht
    hier nichts.
    """
    offene = (
        db.query(ImportVerdacht).filter(ImportVerdacht.entscheidung.is_(None)).count()
    )
    if offene:
        return f"{offene} Bewegung{'en' if offene != 1 else ''} zu klären (Trade Republic)"

    konto = db.query(TradeRepublicKonto).first()
    if konto is not None and not tr_client.sitzung_vorhanden():
        return "Trade Republic: Anmeldung erforderlich"
    if tr_sync.status().get("erfolgreich") is False:
        return "Trade Republic: letzter Abgleich fehlgeschlagen"
    return None


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
            import_warnung=_import_warnung(watcher.status()),
            tr_warnung=_tr_warnung(db),
            # Bewusst neben den Toepfen und nicht in ihrer Summe: der Depotwert
            # ist kein Guthaben auf dem Cashkonto.
            depot=aktueller_snapshot(db),
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
            import_status=watcher.status(),
            letzter_import=letzter_import_zeitpunkt(db),
            depot_gesamt=(
                snapshot.gesamtwert + snapshot.cash
                if (snapshot := aktueller_snapshot(db)) is not None
                else None
            ),
            tr_angemeldet=tr_client.sitzung_vorhanden(),
            tr_verdacht=db.query(ImportVerdacht)
            .filter(ImportVerdacht.entscheidung.is_(None))
            .count(),
        ),
    )
