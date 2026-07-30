"""Seite "DKB": Kontostand, Einrichtung, Freigabe.

Aufgebaut wie die Depot-Seite: ein extern gefuehrter Bestand als reine
Information, bewusst mit nichts verrechnet. Der Kontostand der DKB gehoert in
keinen Topf-Saldo, in keinen Kontostand des Cashkontos und in keine Prognose -
er steht daneben.

Die Einrichtung laeuft in drei Schritten, analog zur Trade-Republic-Anmeldung:
Bank auswaehlen, Freigabe starten, Freigabe in der Bank abschliessen. Der
dritte Schritt kommt ohne Rueckleitung aus - der Freigabe-Link wird von Hand
geoeffnet, und diese Seite fragt den Stand der Freigabe selbst ab (Variante C
des Konzepts). Grund: die App laeuft nur hinter dem Home-Assistant-Ingress und
hat keine feste, von aussen erreichbare Adresse, auf die eine Bank
zurueckspringen koennte.

Fluechtig gehalten wird nur die Bankenliste - sie ist eine Nachschlageliste,
kein Fakt der Kontofuehrung, und beim naechsten Einrichten ohnehin neu zu
holen.
"""
import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import externkonto as externkonto_logik
from app import gocardless
from app.config import externkonto_cache_sekunden, gocardless_redirect_url
from app.database import get_db
from app.models import Externkonto
from app.webutils import ctx, redirect, templates

router = APIRouter()

# Die zuletzt geholte Bankenliste, nur fuer die Dauer der Einrichtung.
_banken: dict = {}


def _dkb_seite(
    request: Request,
    db: Session,
    fehler: str | None = None,
    status_code: int = 200,
    freigabe_link: str | None = None,
    konten_auswahl: list[dict] | None = None,
    stand: externkonto_logik.SaldoStand | None = None,
):
    konto = externkonto_logik.konto(db)
    if stand is None:
        stand = externkonto_logik.SaldoStand(
            saldo=externkonto_logik.neuester_saldo(db, konto.id) if konto else None
        )
    return templates.TemplateResponse(
        "dkb.html",
        ctx(
            request,
            konto=konto,
            zugangsdaten_vorhanden=gocardless.zugangsdaten_vorhanden(),
            banken=_banken.get("liste"),
            freigabe_link=freigabe_link or _banken.get("freigabe_link"),
            konten_auswahl=konten_auswahl,
            stand=stand,
            cache_stunden=externkonto_cache_sekunden() // 3600,
            redirect_url=gocardless_redirect_url(),
            verbleibende_tage=externkonto_logik.freigabe_laeuft_ab(konto),
            fehler=fehler,
        ),
        status_code=status_code,
    )


def _freigabe_abschliessen(db: Session, konto: Externkonto) -> list[dict] | None:
    """Fragt den Stand der Freigabe ab und uebernimmt sie, sobald sie steht.

    Umfasst die Freigabe mehrere Konten, wird nichts geraten: die Auswahl
    kommt zurueck an die Seite. Ein stillschweigend gewaehltes Kreditkarten-
    konto stuende sonst als "Gehaltskonto" auf der Startseite.
    """
    stand = gocardless.freigabe_status(konto.gocardless_requisition_id)

    if stand["abgelaufen"] or stand["abgelehnt"]:
        raise gocardless.GoCardlessFehler(
            "Die Freigabe wurde abgelehnt oder ist abgelaufen – bitte neu starten."
        )
    if not stand["verknuepft"]:
        return None

    if stand["agreement_id"]:
        konto.gocardless_agreement_id = stand["agreement_id"]

    konten = stand["konten"]
    if len(konten) > 1:
        return [
            {"id": kennung, "kennzeichen": gocardless.konto_kennzeichen(kennung)}
            for kennung in konten
        ]

    konto.gocardless_account_id = konten[0]
    konto.consent_gueltig_bis = gocardless.freigabe_gueltig_bis(
        konto.gocardless_agreement_id
    )
    db.commit()
    return None


@router.get("/dkb")
async def seite(request: Request, db: Session = Depends(get_db)):
    """Kontostand, Verbindung und Einrichtung auf einer Seite.

    Zwei Dinge passieren beim Aufruf: Wartet eine Freigabe auf ihren Abschluss,
    wird einmal nachgefragt - die Seite laedt sich dafuer selbst nach. Steht die
    Verbindung, wird der gespeicherte Kontostand geprueft und nur dann live
    nachgeholt, wenn er aelter ist als die eingestellte Spanne (siehe
    app/externkonto.py).

    Beides laeuft im Worker-Thread: es spricht mit einem fremden Server und
    darf die Ereignisschleife nicht blockieren.
    """
    konto = externkonto_logik.konto(db)
    if konto is None:
        return _dkb_seite(request, db)

    if konto.gocardless_requisition_id and not konto.gocardless_account_id:
        try:
            auswahl = await asyncio.to_thread(_freigabe_abschliessen, db, konto)
        except gocardless.GoCardlessFehler as exc:
            return _dkb_seite(request, db, fehler=str(exc))
        if auswahl:
            return _dkb_seite(request, db, konten_auswahl=auswahl)

    stand = None
    if konto.gocardless_account_id:
        stand = await asyncio.to_thread(externkonto_logik.saldo_besorgen, db, konto)
    return _dkb_seite(request, db, stand=stand)


@router.post("/dkb/banken")
async def banken_laden(request: Request, db: Session = Depends(get_db)):
    """Holt die Institutionsliste. Die Kennung der DKB stammt von hier und wird
    nie im Quelltext hartkodiert - GoCardless kann sie aendern."""
    try:
        liste = await asyncio.to_thread(gocardless.institutionen, "de")
    except gocardless.GoCardlessFehler as exc:
        return _dkb_seite(request, db, fehler=str(exc), status_code=400)

    _banken["liste"] = liste
    return redirect(request, "/dkb")


@router.post("/dkb/institut")
async def institut_waehlen(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    institution_id = (form.get("institution_id") or "").strip()
    bezeichnung = (form.get("bezeichnung") or "").strip() or "DKB Gehaltskonto"
    if not institution_id:
        return _dkb_seite(request, db, fehler="Bitte eine Bank auswählen.", status_code=400)

    konto = externkonto_logik.konto(db)
    if konto is None:
        konto = Externkonto(
            bezeichnung=bezeichnung, gocardless_institution_id=institution_id
        )
        db.add(konto)
    else:
        # Ein Bankwechsel macht jede bestehende Freigabe gegenstandslos.
        if konto.gocardless_institution_id != institution_id:
            konto.gocardless_requisition_id = None
            konto.gocardless_agreement_id = None
            konto.gocardless_account_id = None
            konto.consent_gueltig_bis = None
        konto.bezeichnung = bezeichnung
        konto.gocardless_institution_id = institution_id
    db.commit()
    return redirect(request, "/dkb")


@router.post("/dkb/freigabe")
async def freigabe_starten(request: Request, db: Session = Depends(get_db)):
    """Startet eine neue Freigabe - fuer die Ersteinrichtung wie fuer die
    Erneuerung nach spaetestens 90 Tagen."""
    konto = externkonto_logik.konto(db)
    if konto is None:
        return _dkb_seite(request, db, fehler="Bitte zuerst die Bank auswählen.", status_code=400)

    referenz = f"budget-tracker-{konto.id}-{dt.datetime.utcnow():%Y%m%d%H%M%S}"
    try:
        freigabe = await asyncio.to_thread(
            gocardless.freigabe_starten, konto.gocardless_institution_id, referenz
        )
    except gocardless.GoCardlessFehler as exc:
        return _dkb_seite(request, db, fehler=str(exc), status_code=400)

    konto.gocardless_requisition_id = freigabe["requisition_id"]
    konto.gocardless_agreement_id = freigabe["agreement_id"]
    # Die alte Freigabe gilt nicht mehr, sobald eine neue laeuft - erst ihr
    # Abschluss setzt Konto und Gueltigkeit wieder.
    konto.gocardless_account_id = None
    konto.consent_gueltig_bis = None
    db.commit()

    _banken["freigabe_link"] = freigabe["link"]
    return _dkb_seite(request, db, freigabe_link=freigabe["link"])


@router.post("/dkb/konto")
async def konto_waehlen(request: Request, db: Session = Depends(get_db)):
    """Uebernimmt das ausgewaehlte Konto, wenn die Freigabe mehrere umfasst."""
    form = await request.form()
    account_id = (form.get("account_id") or "").strip()
    konto = externkonto_logik.konto(db)
    if konto is None or not account_id:
        raise HTTPException(status_code=400, detail="Kein Konto zur Auswahl.")

    konto.gocardless_account_id = account_id
    try:
        konto.consent_gueltig_bis = await asyncio.to_thread(
            gocardless.freigabe_gueltig_bis, konto.gocardless_agreement_id
        )
    except gocardless.GoCardlessFehler:
        # Ohne Ablaufdatum steht die Verbindung trotzdem; die Erinnerung
        # erscheint dann erst, wenn der naechste Abruf scheitert.
        konto.consent_gueltig_bis = None
    db.commit()
    return redirect(request, "/dkb")


@router.post("/dkb/aktualisieren")
async def aktualisieren(request: Request, db: Session = Depends(get_db)):
    """Holt den Kontostand sofort, ohne auf das Ende der Cache-Spanne zu warten."""
    konto = externkonto_logik.konto(db)
    if konto is None:
        return _dkb_seite(request, db, fehler="Es ist noch kein Konto verbunden.", status_code=400)

    stand = await asyncio.to_thread(
        externkonto_logik.saldo_besorgen, db, konto, True, None
    )
    # Scheitert der Abruf, gehoert der Grund auf die Seite - nach einer
    # Weiterleitung waere er verloren und der Knopf schiene wirkungslos.
    if stand.fehler:
        return _dkb_seite(request, db, fehler=stand.fehler, stand=stand)
    return redirect(request, "/dkb")


@router.post("/dkb/loesen")
async def verbindung_loesen(request: Request, db: Session = Depends(get_db)):
    """Verwirft die Freigabe. Die abgerufenen Salden bleiben - sie sind Fakten,
    keine Zugangsdaten."""
    konto = externkonto_logik.konto(db)
    if konto is not None:
        konto.gocardless_requisition_id = None
        konto.gocardless_agreement_id = None
        konto.gocardless_account_id = None
        konto.consent_gueltig_bis = None
        db.commit()
    _banken.pop("freigabe_link", None)
    return redirect(request, "/dkb")
