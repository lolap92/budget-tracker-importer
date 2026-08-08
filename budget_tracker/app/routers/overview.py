from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import tr_sync, watcher
from app.calculations import (
    kontostand_gesamt,
    letzter_import_zeitpunkt,
    offene_umbuchungen,
    prognose_topf,
    review_liste,
    sondertilgung_status,
)
from app.database import get_db
from app.models import Buchung, ImportVerdacht, Topf, TradeRepublicKonto
from app.tr_depot import aktueller_snapshot
from app.webutils import ctx, eur, templates

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


def _tr_verdacht_anzahl(db: Session) -> int:
    """Bewegungen aus der Schnittstelle, die auf eine Entscheidung warten -
    eine echte Aufgabe, kein Fehler."""
    return db.query(ImportVerdacht).filter(ImportVerdacht.entscheidung.is_(None)).count()


def _tr_fehler(db: Session) -> str | None:
    """Ein echter Fehler beim letzten Abgleich.

    Eine fehlende oder abgelaufene Anmeldung zaehlt bewusst nicht dazu: sie
    ist bei der taeglichen Nutzung der Normalfall, dafuer steht oben rechts
    immer der Download-Button. Wer die Schnittstelle gar nicht nutzt oder noch
    nie einen Abgleich versucht hat, sieht hier nichts.
    """
    if db.query(TradeRepublicKonto).first() is None:
        return None
    status = tr_sync.status()
    if status.get("erfolgreich") is False and not status.get("sitzung_verloren"):
        return f"Trade Republic: {status.get('meldung') or 'letzter Abgleich fehlgeschlagen'}"
    return None


def _kontostand_hinweis(db: Session) -> str | None:
    """Weicht der berechnete Kontostand vom echten ab, stimmt etwas nicht.

    Die App rechnet Startsalden plus alle Buchungen seit dem Startdatum -
    dasselbe, was Trade Republic auch tut. Beide Zahlen muessen auf den Cent
    uebereinstimmen. Bewusst kein Eintrag in der Zuordnen-Liste: eine
    Abweichung ist keine Buchung, es gibt nichts zuzuordnen, und dieselbe Zahl
    kann drei Ursachen haben (falscher Startsaldo, fehlende oder doppelte
    Buchung). Deshalb ein Hinweis mit Verweis auf die Depot-Seite, wo die
    Deutung steht - keine Aufgabe mit Knopf.
    """
    snapshot = aktueller_snapshot(db)
    if snapshot is None:
        return None

    # Ist seit dem Depotstand noch eine Buchung hereingekommen, vergleicht man
    # zwei Zeitpunkte miteinander - die Differenz waere dann nur veraltet.
    # Genau das passiert, wenn die Sitzung abgelaufen ist und der Datei-Import
    # weiterlaeuft.
    juengste = db.query(func.max(Buchung.importiert_am)).scalar()
    if juengste is not None and juengste > snapshot.zeitpunkt:
        return None

    abweichung = Decimal(snapshot.cash) - kontostand_gesamt(db)
    if abweichung == 0:
        return None
    return f"Kontostand: {eur(abs(abweichung))} Abweichung zu Trade Republic"


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
    tr_konto = db.query(TradeRepublicKonto).first()

    return templates.TemplateResponse(
        "overview.html",
        ctx(
            request,
            kontostand=kontostand,
            nicht_zugeordnet=nicht_zugeordnet,
            karten=karten,
            import_warnung=_import_warnung(watcher.status()),
            tr_verdacht_anzahl=_tr_verdacht_anzahl(db),
            tr_fehler=_tr_fehler(db),
            kontostand_hinweis=_kontostand_hinweis(db),
            # Bewusst neben den Toepfen und nicht in ihrer Summe: der Depotwert
            # ist kein Guthaben auf dem Cashkonto.
            depot=aktueller_snapshot(db),
            offene_anzahl=len(review_liste(db)),
            umbuchungen_anzahl=len(offene_umbuchungen(db)),
            tr_letzter_sync=tr_konto.letzter_sync if tr_konto else None,
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
            tr_angemeldet=tr_sync.sitzung_gilt(),
            tr_verdacht=db.query(ImportVerdacht)
            .filter(ImportVerdacht.entscheidung.is_(None))
            .count(),
        ),
    )
