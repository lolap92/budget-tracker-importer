"""CSV-Import: Parsing, Dedublizierung, Transaktionsverhalten, Startdatum."""
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.csv_import import _parse_betrag, _parse_datum, import_csv_datei
from app.models import Buchung
from tests.conftest import csv_schreiben


class TestParsing:
    @pytest.mark.parametrize(
        "roh,erwartet",
        [
            ("-1234.56", Decimal("-1234.56")),
            ("1.234,56", Decimal("1234.56")),
            ("1,234.56", Decimal("1234.56")),
            ("12,5", Decimal("12.5")),
            ("0,10", Decimal("0.10")),
            ("1234", Decimal("1234")),
            (" 99,00 € ", Decimal("99.00")),
        ],
    )
    def test_betrag(self, roh, erwartet):
        assert _parse_betrag(roh) == erwartet

    @pytest.mark.parametrize("roh", ["", "   ", "keine Zahl", "1.2.3"])
    def test_betrag_ungueltig(self, roh):
        assert _parse_betrag(roh) is None

    @pytest.mark.parametrize(
        "roh,erwartet",
        [
            ("2026-07-28", dt.date(2026, 7, 28)),
            ("2026-07-28T10:00:00+02:00", dt.date(2026, 7, 28)),
            ("28.07.2026", dt.date(2026, 7, 28)),
            ("28/07/2026", dt.date(2026, 7, 28)),
        ],
    )
    def test_datum(self, roh, erwartet):
        assert _parse_datum(roh) == erwartet

    @pytest.mark.parametrize("roh", ["", "2026-13-01", "irgendwas"])
    def test_datum_ungueltig(self, roh):
        assert _parse_datum(roh) is None


class TestImport:
    def test_zeilen_werden_importiert(self, db, app, tmp_path):
        pfad = csv_schreiben(
            tmp_path / "e.csv",
            [
                "tx-1,2026-07-01,PAYMENT,-100.00,Miete,Vermieter,DE1,",
                "tx-2,2026-07-02,PAYMENT,-200.00,Strom,Stadtwerke,DE2,",
            ],
        )
        stats = import_csv_datei(db, pfad)

        assert stats["gelesen"] == 2
        assert stats["neu"] == 2
        assert db.query(Buchung).count() == 2

    def test_dedublizierung_ueber_transaction_id(self, db, app, tmp_path):
        zeilen = ["tx-1,2026-07-01,PAYMENT,-100.00,Miete,Vermieter,DE1,"]
        pfad = csv_schreiben(tmp_path / "e.csv", zeilen)
        import_csv_datei(db, pfad)

        # Zweiter Export mit ueberlappendem Zeitraum - der Normalfall bei
        # Trade Republic.
        pfad2 = csv_schreiben(
            tmp_path / "e2.csv",
            zeilen + ["tx-2,2026-07-05,PAYMENT,-50.00,Neu,X,DE2,"],
        )
        stats = import_csv_datei(db, pfad2)

        assert stats["duplikate"] == 1
        assert stats["neu"] == 1
        assert db.query(Buchung).count() == 2

    def test_kaputte_zeile_blockiert_die_datei_nicht(self, db, app, tmp_path):
        pfad = csv_schreiben(
            tmp_path / "e.csv",
            [
                "tx-1,2026-07-01,PAYMENT,-100.00,Miete,X,DE1,",
                "tx-2,kein-datum,PAYMENT,-200.00,Kaputt,X,DE2,",
                ",2026-07-03,PAYMENT,-300.00,Ohne ID,X,DE3,",
                "tx-4,2026-07-04,PAYMENT,-400.00,Ok,X,DE4,",
            ],
        )
        stats = import_csv_datei(db, pfad)

        assert stats["fehler"] == 2
        assert stats["neu"] == 2
        assert {b.transaction_id for b in db.query(Buchung).all()} == {"tx-1", "tx-4"}

    def test_falsches_spaltenformat_wird_uebersprungen(self, db, app, tmp_path):
        pfad = tmp_path / "fremd.csv"
        pfad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        stats = import_csv_datei(db, pfad)

        assert stats["fehler"] == 1
        assert db.query(Buchung).count() == 0

    def test_semikolon_getrennte_datei(self, db, app, tmp_path):
        pfad = tmp_path / "semi.csv"
        pfad.write_text(
            "transaction_id;date;type;amount;payment_reference;"
            "counterparty_name;counterparty_iban;description\n"
            "tx-1;2026-07-01;PAYMENT;-100,00;Miete;Vermieter;DE1;\n",
            encoding="utf-8",
        )
        stats = import_csv_datei(db, pfad)

        assert stats["neu"] == 1
        assert db.query(Buchung).one().betrag == Decimal("-100.00")


class TestIntegritaetsfehler:
    """Regression: ein Integritaetsfehler darf nur die eigene Zeile verwerfen.

    Vor dem Fix rief der Import bei einem IntegrityError db.rollback() und nahm
    damit die gesamte offene Transaktion zurueck. Die Statistik meldete die
    verlorenen Zeilen weiter als 'neu', und der Watcher merkte sich die Datei
    trotzdem als verarbeitet - die Buchungen waren endgueltig weg.
    """

    @staticmethod
    def _flush_der_bei_kollidiert(db, kollidierende_id):
        """Laesst flush() genau fuer eine bestimmte transaction_id scheitern -
        simuliert das, was die Datenbank bei einem echten Race tut."""
        echtes_flush = db.flush

        def flush(*args, **kwargs):
            if any(getattr(o, "transaction_id", None) == kollidierende_id for o in db.new):
                raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))
            return echtes_flush(*args, **kwargs)

        return flush

    def test_vorherige_zeilen_ueberleben(self, db, app, tmp_path):
        pfad = csv_schreiben(
            tmp_path / "e.csv",
            [
                "tx-A,2026-07-01,PAYMENT,-100.00,A,X,DE1,",
                "tx-B,2026-07-02,PAYMENT,-200.00,B,X,DE2,",
                "tx-KOLLISION,2026-07-03,PAYMENT,-10.00,K,X,DE3,",
                "tx-C,2026-07-04,PAYMENT,-300.00,C,X,DE4,",
            ],
        )
        db.flush = self._flush_der_bei_kollidiert(db, "tx-KOLLISION")
        stats = import_csv_datei(db, pfad)
        del db.flush

        assert stats["duplikate"] == 1
        # Statistik und Datenbank muessen uebereinstimmen.
        assert stats["neu"] == 3
        assert db.query(Buchung).count() == 3
        assert {b.transaction_id for b in db.query(Buchung).all()} == {"tx-A", "tx-B", "tx-C"}


class TestStartdatum:
    """Regression: Bewegungen vor dem Startdatum stecken bereits im Startsaldo."""

    def test_zeilen_vor_dem_startdatum_werden_uebersprungen(self, db, app, tmp_path):
        pfad = csv_schreiben(
            tmp_path / "voll.csv",
            [
                "tx-alt,2023-05-01,PAYMENT,-1500.00,Alt,X,DE1,",
                "tx-grenze,2025-12-31,PAYMENT,-10.00,Tag davor,X,DE2,",
                "tx-erster,2026-01-01,PAYMENT,-20.00,Startdatum selbst,X,DE3,",
                "tx-neu,2026-07-01,PAYMENT,-100.00,Aktuell,X,DE4,",
            ],
        )
        stats = import_csv_datei(db, pfad)

        assert stats["vor_startdatum"] == 2
        assert stats["neu"] == 2
        # Das Startdatum selbst gehoert noch dazu.
        assert {b.transaction_id for b in db.query(Buchung).all()} == {"tx-erster", "tx-neu"}

    def test_ohne_konfiguration_wird_nichts_gefiltert(self, db, toepfe, tmp_path):
        """Vor dem Bootstrap gibt es kein Startdatum - dann darf der Import
        nicht stillschweigend alles verwerfen."""
        pfad = csv_schreiben(
            tmp_path / "e.csv", ["tx-alt,2023-05-01,PAYMENT,-1500.00,Alt,X,DE1,"]
        )
        stats = import_csv_datei(db, pfad)

        assert stats["vor_startdatum"] == 0
        assert stats["neu"] == 1
