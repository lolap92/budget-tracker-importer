"""Import-Status: Datenbasis im Watcher und Anzeige auf Übersicht und /mehr."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import watcher
from app.calculations import letzter_import_zeitpunkt
from app.main import app as fastapi_app
from app.models import Buchung, Konfiguration
from tests.conftest import csv_schreiben


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def watcher_zuruecksetzen():
    """Der Watcher-Status ist Modulzustand - zwischen den Tests leeren."""
    watcher._bekannte_dateien.clear()
    watcher._letzter_scan_status.update(
        zeitpunkt=None, verzeichnis=None, verzeichnis_gefunden=None,
        letzte_zahlen=None, meldungen=[],
    )
    yield


def importverzeichnis(db, pfad):
    db.query(Konfiguration).one().import_verzeichnis = str(pfad)
    db.commit()


class TestWatcherStatus:
    def test_fehlendes_verzeichnis_wird_vermerkt(self, db, app, tmp_path):
        importverzeichnis(db, tmp_path / "gibt-es-nicht")

        watcher.scan_einmal()

        assert watcher.status()["verzeichnis_gefunden"] is False

    def test_vorhandenes_verzeichnis_wird_vermerkt(self, db, app, tmp_path):
        importverzeichnis(db, tmp_path)

        watcher.scan_einmal()

        status = watcher.status()
        assert status["verzeichnis_gefunden"] is True
        assert status["zeitpunkt"] is not None

    def test_zahlen_des_letzten_imports(self, db, app, tmp_path):
        importverzeichnis(db, tmp_path)
        csv_schreiben(
            tmp_path / "e.csv",
            [
                "tx-1,2026-07-01,PAYMENT,-100.00,Miete,X,DE1,",
                "tx-2,2025-01-01,PAYMENT,-50.00,Alt,X,DE2,",
                "tx-3,kaputt,PAYMENT,-50.00,Fehler,X,DE3,",
            ],
        )

        watcher.scan_einmal()

        zahlen = watcher.status()["letzte_zahlen"]
        assert zahlen["dateien"] == 1
        assert zahlen["neu"] == 1
        assert zahlen["vor_startdatum"] == 1
        assert zahlen["fehler"] == 1

    def test_leerlauf_scan_setzt_die_zahlen_nicht_zurueck(self, db, app, tmp_path):
        """Der Watcher scannt alle 30 s - ohne neue Datei muss die letzte
        Bilanz stehen bleiben, sonst zeigt /mehr dauerhaft Nullen."""
        importverzeichnis(db, tmp_path)
        csv_schreiben(tmp_path / "e.csv", ["tx-1,2026-07-01,PAYMENT,-100.00,Miete,X,DE1,"])
        watcher.scan_einmal()
        vorher = watcher.status()["letzte_zahlen"]

        watcher.scan_einmal()  # nichts Neues

        assert watcher.status()["letzte_zahlen"] == vorher

    def test_falsches_spaltenformat_wird_als_klartext_gemeldet(self, db, app, tmp_path):
        importverzeichnis(db, tmp_path)
        (tmp_path / "fremd.csv").write_text("foo,bar\n1,2\n", encoding="utf-8")

        watcher.scan_einmal()

        assert any("kein passendes Spaltenformat" in m for m in watcher.status()["meldungen"])


class TestLetzterImportZeitpunkt:
    def test_ohne_buchungen_none(self, db, app):
        assert letzter_import_zeitpunkt(db) is None

    def test_juengster_zeitstempel(self, db, app):
        frueh = dt.datetime(2026, 7, 1, 8, 0)
        spaet = dt.datetime(2026, 7, 20, 17, 30)
        for i, zeitpunkt in enumerate((frueh, spaet)):
            db.add(
                Buchung(
                    transaction_id=f"tx-{i}",
                    datum=dt.date(2026, 7, 1),
                    typ="PAYMENT",
                    betrag=Decimal("-1.00"),
                    importiert_am=zeitpunkt,
                )
            )
        db.commit()

        assert letzter_import_zeitpunkt(db) == spaet


class TestAnzeige:
    def test_mehr_zeigt_verzeichnis_und_zahlen(self, client, db, app, tmp_path):
        importverzeichnis(db, tmp_path)
        csv_schreiben(tmp_path / "e.csv", ["tx-1,2026-07-01,PAYMENT,-100.00,Miete,X,DE1,"])
        watcher.scan_einmal()

        text = client.get("/mehr").text

        assert str(tmp_path) in text
        assert "wird überwacht" in text
        assert "Neu übernommen" in text

    def test_uebersicht_warnt_bei_fehlendem_verzeichnis(self, client, db, app, tmp_path):
        importverzeichnis(db, tmp_path / "gibt-es-nicht")
        watcher.scan_einmal()

        assert "Import-Verzeichnis nicht gefunden" in client.get("/").text

    def test_uebersicht_warnt_bei_nicht_verarbeiteten_zeilen(self, client, db, app, tmp_path):
        importverzeichnis(db, tmp_path)
        csv_schreiben(tmp_path / "e.csv", ["tx-1,kaputt,PAYMENT,-100.00,X,X,DE1,"])
        watcher.scan_einmal()

        assert "1 Zeile(n) nicht verarbeitet" in client.get("/").text

    def test_uebersicht_schweigt_im_normalfall(self, client, db, app, tmp_path):
        """Kein Dauer-Statusrauschen, wenn alles laeuft."""
        importverzeichnis(db, tmp_path)
        csv_schreiben(tmp_path / "e.csv", ["tx-1,2026-07-01,PAYMENT,-100.00,Miete,X,DE1,"])
        watcher.scan_einmal()

        text = client.get("/").text
        assert "Import-Verzeichnis nicht gefunden" not in text
        assert "nicht verarbeitet" not in text
