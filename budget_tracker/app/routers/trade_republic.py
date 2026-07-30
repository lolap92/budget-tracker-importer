"""Seite "Trade Republic": Anmeldung, Abgleich, Verdachtsfaelle.

Die Anmeldung ist zweistufig (Telefonnummer + PIN, dann der vierstellige Code
aus der App). Zwischen beiden Schritten muss dieselbe pytr-Instanz erhalten
bleiben - sie haelt Vorgangsnummer und Cookies. Diese Instanz liegt in
app/tr_client.py; hier steht nur, welche Telefonnummer der laufende Vorgang
betrifft, damit sie nach Erfolg gespeichert werden kann.
"""
import asyncio
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import config, tr_client, tr_sync
from app.calculations import kontostand_gesamt
from app.database import get_db
from app.tr_depot import aktueller_snapshot
from app.import_core import ImportKontext, uebernehmen
from app.models import ImportVerdacht, TradeRepublicKonto
from app.webutils import ctx, redirect, templates

router = APIRouter()

# Nur fuer die Dauer eines Anmeldevorgangs: Nummer und Countdown bis zur
# SMS-Option. Bewusst fluechtig - ein Neustart bricht die Anmeldung ohnehin ab.
_offene_anmeldung: dict = {}

# Werte der Entscheidung ueber einen Verdachtsfall.
ENTSCHEIDUNG_UEBERNEHMEN = "uebernehmen"
ENTSCHEIDUNG_ZUSAMMENFUEHREN = "zusammenfuehren"


def _seite(
    request: Request,
    db: Session,
    fehler: str | None = None,
    status_code: int = 200,
    telefonnummer: str | None = None,
):
    konto = db.query(TradeRepublicKonto).first()
    verdachtsfaelle = (
        db.query(ImportVerdacht)
        .filter(ImportVerdacht.entscheidung.is_(None))
        .order_by(ImportVerdacht.datum.desc())
        .all()
    )
    return templates.TemplateResponse(
        "trade_republic.html",
        ctx(
            request,
            konto=konto,
            angemeldet=tr_client.sitzung_vorhanden(),
            anmeldung_laeuft=tr_client.anmeldung_laeuft(),
            wartet_auf_app=tr_client.anmeldeverfahren() == tr_client.VERFAHREN_V2,
            countdown=_offene_anmeldung.get("countdown"),
            pytr_verfuegbar=tr_client.pytr_verfuegbar(),
            version=config.version(),
            sync_intervall_stunden=config.tr_sync_intervall_sekunden() // 3600,
            sync_status=tr_sync.status(),
            verdachtsfaelle=verdachtsfaelle,
            fehler=fehler,
            # Nach einem Fehlschlag soll die Nummer im Feld stehen bleiben -
            # sie noch einmal zu tippen ist die haerteste Art, einen Tippfehler
            # zu wiederholen.
            telefonnummer=telefonnummer
            or (konto.telefonnummer if konto is not None else ""),
        ),
        status_code=status_code,
    )


def _telefonnummer_merken(db: Session) -> None:
    telefonnummer = _offene_anmeldung.pop("telefonnummer", None)
    _offene_anmeldung.pop("countdown", None)
    if not telefonnummer:
        return
    konto = db.query(TradeRepublicKonto).first()
    if konto is None:
        db.add(TradeRepublicKonto(telefonnummer=telefonnummer))
    else:
        konto.telefonnummer = telefonnummer
    db.commit()


@router.get("/trade-republic")
def seite(request: Request, db: Session = Depends(get_db)):
    """Wartet eine Anmeldung auf die Bestaetigung in der App, fragt jeder
    Seitenaufruf einmal nach - die Seite laedt sich dafuer selbst nach."""
    if tr_client.anmeldeverfahren() == tr_client.VERFAHREN_V2:
        try:
            if tr_client.bestaetigung_pruefen():
                _telefonnummer_merken(db)
                return redirect(request, "/trade-republic")
        except tr_client.AnmeldungFehlgeschlagen as exc:
            _offene_anmeldung.clear()
            return _seite(request, db, fehler=str(exc))
    return _seite(request, db)


@router.get("/depot")
def depot(request: Request, db: Session = Depends(get_db)):
    """Der Depotstand als reine Information - bewusst eine eigene Seite und
    nicht auf der Uebersicht: er ist weder ein Topf noch Teil des Kontostands.

    Der Cash-Bestand daneben ist mehr als Deko: die App rechnet ihren
    Kontostand aus Startsalden und Buchungen, Trade Republic kennt den echten.
    Eine Abweichung heisst, dass eine Buchung fehlt oder doppelt ist.
    """
    snapshot = aktueller_snapshot(db)
    kontostand = kontostand_gesamt(db)
    abweichung = Decimal(0)
    if snapshot is not None:
        abweichung = Decimal(snapshot.cash) - kontostand

    return templates.TemplateResponse(
        "depot.html",
        ctx(request, snapshot=snapshot, kontostand=kontostand, abweichung=abweichung),
    )


@router.post("/trade-republic/anmelden")
async def anmelden(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    eingabe = (form.get("telefonnummer") or "").strip()
    pin = (form.get("pin") or "").strip()
    waf_token = (form.get("waf_token") or "").strip() or None

    # Erst die Eingabe pruefen, dann die Umgebung: was der Nutzer selbst
    # beheben kann, soll er zuerst erfahren.
    telefonnummer = tr_client.telefonnummer_normalisieren(eingabe)
    if not telefonnummer.startswith("+") or len(telefonnummer) < 8 or not pin:
        return _seite(
            request,
            db,
            fehler="Telefonnummer (z.B. +4915112345678 oder 015112345678) und PIN werden benötigt.",
            status_code=400,
            telefonnummer=eingabe,
        )

    if not tr_client.pytr_verfuegbar():
        return _seite(
            request,
            db,
            fehler="Die Bibliothek pytr ist nicht installiert - der direkte Abgleich "
            "steht in dieser Installation nicht zur Verfügung.",
            status_code=400,
            telefonnummer=eingabe,
        )

    try:
        countdown = await asyncio.to_thread(
            tr_client.anmeldung_starten, telefonnummer, pin, waf_token
        )
    except tr_client.AnmeldungFehlgeschlagen as exc:
        return _seite(request, db, fehler=str(exc), status_code=400, telefonnummer=telefonnummer)

    _offene_anmeldung.update(telefonnummer=telefonnummer, countdown=countdown)
    return redirect(request, "/trade-republic")


@router.post("/trade-republic/code")
async def code(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    eingabe = (form.get("code") or "").strip()
    if not eingabe:
        return _seite(request, db, fehler="Bitte den Code eingeben.", status_code=400)

    try:
        await asyncio.to_thread(tr_client.code_bestaetigen, eingabe)
    except tr_client.AnmeldungFehlgeschlagen as exc:
        return _seite(request, db, fehler=str(exc), status_code=400)

    _telefonnummer_merken(db)
    return redirect(request, "/trade-republic")


@router.post("/trade-republic/code-erneut")
async def code_erneut(request: Request, db: Session = Depends(get_db)):
    try:
        await asyncio.to_thread(tr_client.code_erneut_senden)
    except tr_client.AnmeldungFehlgeschlagen as exc:
        return _seite(request, db, fehler=str(exc), status_code=400)
    return redirect(request, "/trade-republic")


@router.post("/trade-republic/abbrechen")
def abbrechen(request: Request):
    tr_client.anmeldung_abbrechen()
    _offene_anmeldung.clear()
    return redirect(request, "/trade-republic")


@router.post("/trade-republic/abmelden")
def abmelden(request: Request):
    tr_client.abmelden()
    _offene_anmeldung.clear()
    return redirect(request, "/trade-republic")


@router.post("/trade-republic/sync")
async def jetzt_abgleichen(request: Request, db: Session = Depends(get_db)):
    """Holt sofort ab, statt auf den naechsten Turnus zu warten."""
    await asyncio.to_thread(tr_sync.sync_einmal_mit_eigener_session)
    return redirect(request, "/trade-republic")


def _angaben_uebernehmen(verdacht: ImportVerdacht) -> None:
    """Beim Verwerfen die Angaben retten, die nur die Schnittstelle kennt.

    Es ist dieselbe Bewegung - und die Fassung aus der Schnittstelle bringt den
    Verwendungszweck mit, den der CSV-Export leer laesst. Ihn mit dem
    Verdachtsfall wegzuwerfen hiesse, genau das aufzugeben, wofuer die
    Anbindung da ist. Ergaenzt wird nur, was leer ist: eine vorhandene Angabe
    wird nie ueberschrieben, und die Topf-Zuordnung bleibt unangetastet.
    """
    buchung = verdacht.vermutete_dopplung
    if buchung is None:
        return
    for feld in ("verwendungszweck", "empfaenger_name", "empfaenger_iban", "beschreibung"):
        if not getattr(buchung, feld) and getattr(verdacht, feld):
            setattr(buchung, feld, getattr(verdacht, feld))


@router.post("/trade-republic/verdacht/{verdacht_id}")
async def verdacht_entscheiden(
    verdacht_id: int, request: Request, db: Session = Depends(get_db)
):
    """Entweder ist es dieselbe Bewegung wie die bereits vorhandene Buchung -
    dann werden beide zusammengefuehrt - oder es sind zwei echte Zahlungen,
    dann wird sie nachtraeglich als eigene Buchung uebernommen."""
    verdacht = db.query(ImportVerdacht).filter(ImportVerdacht.id == verdacht_id).first()
    if verdacht is None or verdacht.entscheidung is not None:
        raise HTTPException(status_code=404, detail="Dieser Fall wurde bereits entschieden.")

    form = await request.form()
    entscheidung = form.get("entscheidung")
    # "verwerfen" hiess das bis 1.21.1, als noch nichts uebernommen wurde -
    # eine offene Seite aus der Zeit soll trotzdem funktionieren.
    if entscheidung == "verwerfen":
        entscheidung = ENTSCHEIDUNG_ZUSAMMENFUEHREN
    if entscheidung not in (ENTSCHEIDUNG_UEBERNEHMEN, ENTSCHEIDUNG_ZUSAMMENFUEHREN):
        raise HTTPException(status_code=400, detail="Unbekannte Entscheidung.")

    if entscheidung == ENTSCHEIDUNG_UEBERNEHMEN:
        uebernehmen(
            db,
            ImportKontext.laden(db),
            transaction_id=verdacht.transaction_id,
            datum=verdacht.datum,
            betrag=verdacht.betrag,
            typ=verdacht.typ,
            # Seit die Pruefung im Kern sitzt, kann ein Fall auch aus dem
            # Datei-Import stammen - die Quelle steht am Fall selbst.
            quelle=verdacht.quelle,
            verwendungszweck=verdacht.verwendungszweck,
            empfaenger_name=verdacht.empfaenger_name,
            empfaenger_iban=verdacht.empfaenger_iban,
            beschreibung=verdacht.beschreibung,
            # Der Fall wurde gerade angesehen und als eigene Zahlung beurteilt -
            # die Dopplungspruefung darf ihn jetzt nicht erneut abfangen.
            trotz_verdacht=True,
        )

    else:
        _angaben_uebernehmen(verdacht)

    # Der Fall bleibt bestehen: nur so erkennt der naechste Abgleich, dass
    # diese Bewegung schon beurteilt wurde.
    verdacht.entscheidung = entscheidung
    db.commit()
    return redirect(request, "/trade-republic")
