"""Gemeinsamer Kern der Buchungsuebernahme.

Eine reale Kontobewegung kann die App auf mehreren Wegen erreichen: als Zeile
einer CSV-Datei aus dem Import-Verzeichnis (app/csv_import.py) oder - ab 1.18.0 -
als Timeline-Event der Trade-Republic-Schnittstelle (app/tr_sync.py). Was
*nach* dem Lesen passiert, ist in beiden Faellen identisch und steht deshalb
hier: Dedublizierung ueber die transaction_id, das Verwerfen von Bewegungen vor
dem Startdatum und die automatische Topf-Zuordnung.

Bewusst nicht hier: das Parsen. Wie ein Datum oder ein Betrag aussieht, ist
Sache der Quelle - eine CSV liefert mehrdeutige Zeichenketten (siehe
zahlenformat() in app/csv_import.py), die API liefert ISO-Zeitstempel und
Zahlen. uebernehmen() bekommt deshalb bereits geparste Werte.
"""
import datetime as dt
import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assignment import topf_zuordnen
from app.dopplung import finde_moegliche_dopplung
from app.models import Buchung, ImportVerdacht, Konfiguration

logger = logging.getLogger("budget_tracker.import")

# Ergebnis von uebernehmen(). Die Werte sind zugleich die Schluessel der
# Import-Statistik, die unter "Mehr" angezeigt wird.
NEU = "neu"
DUPLIKAT = "duplikate"
VOR_STARTDATUM = "vor_startdatum"
VERDACHT = "verdacht"

# Woher die Buchung stammt. Rein dokumentarisch - fuer die Anzeige und, sobald
# beide Wege parallel laufen, fuer die Dopplungspruefung zwischen ihnen.
QUELLE_CSV = "csv"
QUELLE_API = "api"
QUELLE_MANUELL = "manuell"


@dataclass
class ImportKontext:
    """Was fuer einen ganzen Importlauf gilt - einmal geladen statt je Zeile.

    vorhandene_ids wird beim Uebernehmen fortgeschrieben, damit auch zwei
    identische Zeilen innerhalb desselben Laufs als Duplikat erkannt werden.
    """

    vorhandene_ids: set[str]
    start_datum: dt.date | None
    # Bewegungen, die schon einmal als moegliche Dopplung vorgelegt wurden -
    # auch die verworfenen, die gerade deshalb keine Buchung haben.
    beurteilte_ids: set[str] = field(default_factory=set)

    @classmethod
    def laden(cls, db: Session) -> "ImportKontext":
        konfiguration = db.query(Konfiguration).first()
        return cls(
            vorhandene_ids={row[0] for row in db.query(Buchung.transaction_id).all()},
            start_datum=konfiguration.start_datum if konfiguration is not None else None,
            beurteilte_ids={row[0] for row in db.query(ImportVerdacht.transaction_id).all()},
        )

    def ist_bekannt(self, transaction_id: str) -> bool:
        """Erlaubt der Quelle, eine bereits bekannte Bewegung zu erkennen,
        *bevor* sie Aufwand ins Parsen oder in einen Detail-Abruf steckt."""
        return transaction_id in self.vorhandene_ids or transaction_id in self.beurteilte_ids


def uebernehmen(
    db: Session,
    kontext: ImportKontext,
    *,
    transaction_id: str,
    datum: dt.date,
    betrag: Decimal,
    typ: str,
    quelle: str,
    verwendungszweck: str | None = None,
    empfaenger_name: str | None = None,
    empfaenger_iban: str | None = None,
    beschreibung: str | None = None,
    trotz_verdacht: bool = False,
) -> str:
    """Uebernimmt eine bereits geparste Bewegung. Gibt NEU, DUPLIKAT,
    VOR_STARTDATUM oder VERDACHT zurueck; committet nicht (das entscheidet der
    Aufrufer)."""
    if transaction_id in kontext.vorhandene_ids:
        return DUPLIKAT
    # trotz_verdacht setzt genau diese Sperre ausser Kraft: der Mensch hat den
    # Fall angesehen und entschieden, dass es eben *keine* Dopplung ist.
    if not trotz_verdacht and transaction_id in kontext.beurteilte_ids:
        return DUPLIKAT

    # Bewegungen vor dem Startdatum stecken bereits in den Topf-Startsalden.
    # Wuerden sie zusaetzlich uebernommen, zaehlt die App sie ein zweites Mal -
    # sowohl der CSV-Export als auch die Timeline liefern regelmaessig den
    # kompletten Verlauf.
    if kontext.start_datum is not None and datum < kontext.start_datum:
        return VOR_STARTDATUM

    # Dieselbe reale Bewegung unter zwei verschiedenen transaction_ids: der
    # Datei-Export und die Schnittstelle beziehen ihre Daten aus zwei
    # verschiedenen Diensten von Trade Republic, die ihre Nummern unabhaengig
    # vergeben. Die Pruefung sitzt hier und nicht in einer der beiden Quellen,
    # damit sie in beide Richtungen wirkt.
    dopplung = (
        None
        if trotz_verdacht
        else finde_moegliche_dopplung(
            db, transaction_id=transaction_id, datum=datum, betrag=betrag, quelle=quelle
        )
    )
    if dopplung is not None:
        logger.info(
            "Bewegung %s sieht aus wie Buchung %s - zur Entscheidung vorgelegt.",
            transaction_id,
            dopplung.id,
        )
        db.add(
            ImportVerdacht(
                transaction_id=transaction_id,
                datum=datum,
                typ=typ,
                betrag=betrag,
                verwendungszweck=verwendungszweck or None,
                empfaenger_name=empfaenger_name or None,
                empfaenger_iban=empfaenger_iban or None,
                beschreibung=beschreibung or None,
                quelle=quelle,
                vermutete_dopplung_id=dopplung.id,
                erstellt_am=dt.datetime.utcnow(),
            )
        )
        kontext.beurteilte_ids.add(transaction_id)
        return VERDACHT

    buchung = Buchung(
        transaction_id=transaction_id,
        datum=datum,
        typ=typ,
        betrag=betrag,
        verwendungszweck=verwendungszweck or None,
        empfaenger_name=empfaenger_name or None,
        empfaenger_iban=empfaenger_iban or None,
        beschreibung=beschreibung or None,
        quelle=quelle,
        importiert_am=dt.datetime.utcnow(),
    )
    # SAVEPOINT je Buchung: ein Integritaetsfehler darf ausschliesslich diese
    # eine verwerfen. Ein db.rollback() wuerde die gesamte offene Transaktion
    # und damit alle bereits gelesenen Zeilen dieses Laufs zuruecknehmen - der
    # Watcher merkt sich die Datei danach trotzdem als verarbeitet und liest
    # sie nie wieder, die Buchungen waeren endgueltig weg.
    try:
        with db.begin_nested():
            db.add(buchung)
            db.flush()
    except IntegrityError:
        # Race/erneute Uebernahme derselben transaction_id -> ignorieren, warnen.
        logger.warning(
            "transaction_id %s bereits vorhanden (Integritaetsfehler), ignoriert.",
            transaction_id,
        )
        return DUPLIKAT

    topf_zuordnen(db, buchung)
    kontext.vorhandene_ids.add(transaction_id)
    return NEU
