"""Erkennung derselben Bewegung unter zwei transaction_ids (app/dopplung.py)."""
import datetime as dt
from decimal import Decimal

from app.dopplung import finde_moegliche_dopplung, uuid7_zeitpunkt
from app.import_core import QUELLE_API, QUELLE_CSV, ImportKontext, uebernehmen

# Echte IDs aus einem Transaktionsexport (UUIDv7). Ihr eingebetteter Zeitstempel
# stimmt auf die Millisekunde mit dem Buchungszeitpunkt ueberein.
ID_CSV = "019f7537-223d-769c-9c85-92dd484480d4"  # 2026-07-18 12:32:55.357 UTC
ID_GLEICHZEITIG = "019f7537-2240-7aaa-8000-000000000001"  # 3 ms spaeter
ID_SPAETER = "019f7c00-0000-7aaa-8000-000000000002"  # gut einen Tag spaeter


def buchung_anlegen(db, transaction_id, datum, betrag, quelle=QUELLE_CSV):
    uebernehmen(
        db,
        ImportKontext.laden(db),
        transaction_id=transaction_id,
        datum=datum,
        betrag=Decimal(betrag),
        typ="TRANSFER_OUTBOUND",
        quelle=quelle,
    )
    db.commit()


class TestUuid7Zeitpunkt:
    def test_zeitstempel_wird_gelesen(self):
        zeitpunkt = uuid7_zeitpunkt(ID_CSV)

        assert zeitpunkt == dt.datetime(2026, 7, 18, 12, 32, 55, 357000)

    def test_andere_uuid_version_ergibt_nichts(self):
        # UUIDv4 (viertes Feld beginnt mit 4) - keine Zeitinformation.
        assert uuid7_zeitpunkt("6aec5a4c-f424-4b9e-a1c2-1ac2faac3439") is None

    def test_synthetische_id_ergibt_nichts(self):
        assert uuid7_zeitpunkt("manual-1234") is None
        assert uuid7_zeitpunkt("") is None


class TestDopplungsverdacht:
    def test_gleicher_betrag_und_zeitpunkt_aus_anderer_quelle(self, db, app):
        buchung_anlegen(db, ID_CSV, dt.date(2026, 7, 18), "-1500.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id=ID_GLEICHZEITIG,
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-1500.00"),
            quelle=QUELLE_API,
        )

        assert treffer is not None
        assert treffer.transaction_id == ID_CSV

    def test_dieselbe_quelle_wird_nicht_verglichen(self, db, app):
        """Zweimal derselbe Betrag am selben Tag ist innerhalb einer Quelle der
        Normalfall und ueber die transaction_id sauber getrennt."""
        buchung_anlegen(db, ID_CSV, dt.date(2026, 7, 18), "-1500.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id=ID_GLEICHZEITIG,
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-1500.00"),
            quelle=QUELLE_CSV,
        )

        assert treffer is None

    def test_anderer_betrag_ist_kein_verdacht(self, db, app):
        buchung_anlegen(db, ID_CSV, dt.date(2026, 7, 18), "-1500.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id=ID_GLEICHZEITIG,
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-1499.99"),
            quelle=QUELLE_API,
        )

        assert treffer is None

    def test_zu_weit_auseinander_ist_kein_verdacht(self, db, app):
        buchung_anlegen(db, ID_CSV, dt.date(2026, 7, 1), "-1500.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id=ID_SPAETER,
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-1500.00"),
            quelle=QUELLE_API,
        )

        assert treffer is None

    def test_naechstgelegener_kandidat_gewinnt(self, db, app):
        """Ohne verwertbare Zeitstempel zaehlt die Naehe im Datum."""
        buchung_anlegen(db, "csv-fern", dt.date(2026, 7, 14), "-80.00")
        buchung_anlegen(db, "csv-nah", dt.date(2026, 7, 17), "-80.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id="api-neu",
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-80.00"),
            quelle=QUELLE_API,
        )

        assert treffer.transaction_id == "csv-nah"

    def test_zeitstempel_schlaegt_datumsnaehe(self, db, app):
        """Der eingebettete Zeitstempel ist der belastbarste Hinweis und geht
        einem blossen Datumstreffer vor."""
        buchung_anlegen(db, "csv-ohne-zeitstempel", dt.date(2026, 7, 18), "-1500.00")
        buchung_anlegen(db, ID_CSV, dt.date(2026, 7, 17), "-1500.00")

        treffer = finde_moegliche_dopplung(
            db,
            transaction_id=ID_GLEICHZEITIG,
            datum=dt.date(2026, 7, 18),
            betrag=Decimal("-1500.00"),
            quelle=QUELLE_API,
        )

        assert treffer.transaction_id == ID_CSV
