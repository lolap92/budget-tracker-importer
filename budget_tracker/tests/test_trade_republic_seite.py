"""Die Trade-Republic-Seite und die Entscheidung ueber Verdachtsfaelle.

Ohne Anmeldung und ohne Netz: geprueft wird, was die Seite in ihren Zustaenden
zeigt und dass eine Entscheidung genau eine der beiden Wirkungen hat.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.import_core import QUELLE_API, QUELLE_CSV, ImportKontext, uebernehmen
from app.main import app as fastapi_app
from app.models import Buchung, ImportVerdacht, TradeRepublicKonto


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app, follow_redirects=False)


@pytest.fixture
def verdacht(db, app):
    """Eine per CSV bekannte Buchung und dieselbe Bewegung als Verdachtsfall."""
    uebernehmen(
        db,
        ImportKontext.laden(db),
        transaction_id="csv-id",
        datum=dt.date(2026, 6, 29),
        betrag=Decimal("550.00"),
        typ="TRANSFER_INBOUND",
        quelle=QUELLE_CSV,
    )
    db.commit()
    fall = ImportVerdacht(
        transaction_id="api-id",
        datum=dt.date(2026, 6, 29),
        typ="TRANSFER_INBOUND",
        betrag=Decimal("550.00"),
        verwendungszweck="Haus Renovierung Anteil",
        empfaenger_name="Klaus Mustermann",
        quelle=QUELLE_API,
        vermutete_dopplung_id=db.query(Buchung).one().id,
    )
    db.add(fall)
    db.commit()
    return fall


class TestSeite:
    def test_ohne_anmeldung_erscheint_das_anmeldeformular(self, client):
        text = client.get("/trade-republic").text

        assert "Telefonnummer" in text
        assert "nicht angemeldet" in text
        assert "nirgends gespeichert" in text

    def test_verdachtsfaelle_werden_gezeigt(self, client, verdacht):
        text = client.get("/trade-republic").text

        assert "Zur Entscheidung (1)" in text
        assert "Haus Renovierung Anteil" in text
        assert "550,00" in text

    def test_uebersicht_meldet_offene_faelle(self, client, verdacht):
        assert "1 Bewegung zu klären" in client.get("/").text

    def test_uebersicht_meldet_abgelaufene_sitzung(self, client, db, app):
        db.add(TradeRepublicKonto(telefonnummer="+4915112345678"))
        db.commit()

        assert "Anmeldung erforderlich" in client.get("/").text

    def test_ohne_konto_keine_meldung(self, client, db, app):
        assert "Trade Republic:" not in client.get("/").text


class TestAnmeldung:
    def test_unvollstaendige_eingabe_wird_abgelehnt(self, client):
        antwort = client.post(
            "/trade-republic/anmelden", data={"telefonnummer": "015112345678", "pin": "1234"}
        )

        assert antwort.status_code == 400
        assert "+4915112345678" in antwort.text

    def test_code_ohne_laufende_anmeldung(self, client):
        antwort = client.post("/trade-republic/code", data={"code": "1234"})

        assert antwort.status_code == 400
        assert "erneut mit Telefonnummer und PIN" in antwort.text


class TestEntscheidung:
    def test_verwerfen_legt_keine_buchung_an(self, client, db, verdacht):
        antwort = client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "verwerfen"}
        )

        assert antwort.status_code == 303
        assert db.query(Buchung).count() == 1
        # Die Route arbeitet in einer eigenen Sitzung - erst nach expire_all
        # sieht die Test-Sitzung deren Aenderungen.
        db.expire_all()
        assert db.query(ImportVerdacht).one().entscheidung == "verwerfen"

    def test_uebernehmen_legt_die_zweite_buchung_an(self, client, db, verdacht):
        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "uebernehmen"}
        )

        assert db.query(Buchung).count() == 2
        neue = db.query(Buchung).filter(Buchung.transaction_id == "api-id").one()
        assert neue.betrag == Decimal("550.00")
        assert neue.quelle == "api"
        # Der Verwendungszweck traegt die automatische Topf-Zuordnung.
        assert neue.topf.name == "Haus Renovierung"

    def test_ein_fall_wird_nur_einmal_entschieden(self, client, db, verdacht):
        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "verwerfen"}
        )
        antwort = client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "uebernehmen"}
        )

        assert antwort.status_code == 404
        assert db.query(Buchung).count() == 1
