"""Der DKB-Kontostand: abrufen, zwischenspeichern, zusammenrechnen.

Was hier steht, ist die Fachlogik um das externe Konto - ohne HTTP (das steckt
in app/gocardless.py) und ohne Web-Schicht (app/routers/dkb.py).

Zwei Grundsaetze aus dem Konzept:

*Der DKB-Saldo ist Zusatzinformation.* Er fliesst in keinen Topf-Saldo, in
keinen Kontostand, in keine Prognose und in keine Minus-Erkennung ein - genau
wie der Depotwert. Er steht als eigener Abschnitt auf der Startseite, unter dem
Depot, und wird bewusst mit nichts verrechnet: es ist Geld auf einem anderen
Konto, keine Groesse der Topf-Logik.

*Jeder Abruf ist ein eigener Fakt.* Ein Saldo wird nie ueberschrieben, sondern
als neue Zeile mit Zeitstempel angelegt. Der "aktuelle Stand" ist der neueste
Eintrag - eine berechnete Sicht, keine gepflegte Spalte.
"""
import datetime as dt
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app import gocardless
from app.config import EXTERNKONTO_WARNUNG_TAGE, externkonto_cache_sekunden
from app.models import Externkonto, ExternkontoSaldo

logger = logging.getLogger("budget_tracker.externkonto")


def konto(db: Session) -> Externkonto | None:
    """Das eingerichtete externe Konto. Vorerst gibt es hoechstens eines - die
    eigene Tabelle laesst ein zweites zu, ohne das Modell zu aendern."""
    return db.query(Externkonto).order_by(Externkonto.id).first()


def neuester_saldo(db: Session, konto_id: int) -> ExternkontoSaldo | None:
    return (
        db.query(ExternkontoSaldo)
        .filter(ExternkontoSaldo.externkonto_id == konto_id)
        .order_by(ExternkontoSaldo.abgerufen_am.desc(), ExternkontoSaldo.id.desc())
        .first()
    )


def ist_veraltet(saldo: ExternkontoSaldo | None, jetzt: dt.datetime | None = None) -> bool:
    if saldo is None:
        return True
    jetzt = jetzt or dt.datetime.utcnow()
    return (jetzt - saldo.abgerufen_am).total_seconds() >= externkonto_cache_sekunden()


def saldo_speichern(
    db: Session, konto: Externkonto, betrag: Decimal, jetzt: dt.datetime | None = None
) -> ExternkontoSaldo:
    """Legt den abgerufenen Stand als neuen, unveraenderlichen Fakt ab.
    Committet nicht."""
    eintrag = ExternkontoSaldo(
        externkonto_id=konto.id,
        betrag=betrag,
        abgerufen_am=jetzt or dt.datetime.utcnow(),
    )
    db.add(eintrag)
    db.flush()
    return eintrag


@dataclass
class SaldoStand:
    """Was die Seite ueber den Kontostand weiss - inklusive der Frage, wie er
    zustande kam. Ohne diese Unterscheidung stuende ein tagealter Wert
    kommentarlos neben einem gerade geholten."""

    saldo: ExternkontoSaldo | None
    frisch_geholt: bool = False
    fehler: str | None = None


def saldo_besorgen(
    db: Session,
    konto: Externkonto,
    erzwingen: bool = False,
    jetzt: dt.datetime | None = None,
) -> SaldoStand:
    """Der Kontostand nach der Cache-Regel aus dem Konzept.

    Ist der letzte Abruf juenger als die eingestellte Spanne, wird er gezeigt;
    sonst wird live geholt und als neuer Datensatz gespeichert. Scheitert der
    Abruf - abgelaufene Freigabe, erschoepftes Kontingent, GoCardless nicht
    erreichbar -, bleibt der zuletzt bekannte Stand stehen und der Grund wird
    daneben genannt. Ein Fehler beim Abruf darf die Seite nicht leeren: der
    alte Wert ist immer noch die beste verfuegbare Auskunft.
    """
    vorhanden = neuester_saldo(db, konto.id)
    if not erzwingen and not ist_veraltet(vorhanden, jetzt):
        return SaldoStand(saldo=vorhanden)

    if not konto.gocardless_account_id:
        return SaldoStand(
            saldo=vorhanden,
            fehler="Für dieses Konto liegt noch keine Freigabe vor.",
        )

    try:
        betrag = gocardless.saldo(konto.gocardless_account_id)
    except gocardless.GoCardlessFehler as exc:
        logger.warning("Kontostand nicht abrufbar: %s", exc)
        return SaldoStand(saldo=vorhanden, fehler=str(exc))

    neu = saldo_speichern(db, konto, betrag, jetzt)
    db.commit()
    return SaldoStand(saldo=neu, frisch_geholt=True)


def freigabe_laeuft_ab(
    konto: Externkonto | None, heute: dt.date | None = None
) -> int | None:
    """Tage bis zum Ablauf der Freigabe, sobald es knapp wird - sonst None.

    Negative Werte heissen: schon abgelaufen. PSD2 begrenzt jede Freigabe auf
    hoechstens 90 Tage; das laesst sich nicht umgehen, wohl aber rechtzeitig
    ankuendigen.
    """
    if konto is None or konto.consent_gueltig_bis is None:
        return None
    verbleibend = (konto.consent_gueltig_bis - (heute or dt.date.today())).days
    return verbleibend if verbleibend <= EXTERNKONTO_WARNUNG_TAGE else None


def warnung(konto: Externkonto | None, heute: dt.date | None = None) -> str | None:
    """Der Text fuer die "Zu tun"-Karte auf der Startseite."""
    verbleibend = freigabe_laeuft_ab(konto, heute)
    if verbleibend is None:
        return None
    if verbleibend < 0:
        return f"{konto.bezeichnung}: Zugriff abgelaufen – erneuern"
    if verbleibend == 0:
        return f"{konto.bezeichnung}: Zugriff läuft heute ab – erneuern"
    return (
        f"{konto.bezeichnung}: Zugriff läuft in {verbleibend} Tag"
        f"{'en' if verbleibend != 1 else ''} ab – erneuern"
    )
