"""Serverseitige Eingabepruefungen und die einheitliche Fehlerseite."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.forecast_engine import regel_bearbeiten, regel_erstellen
from app.main import app as fastapi_app
from app.models import Buchung, ForecastRegel
from app.umbuchung import abgleichen, endgueltig_verbuchen, markiere_als_umbuchung
from tests.conftest import START_DATUM


def regel_daten(topf, **abweichungen):
    daten = {
        "topf_id": topf.id,
        "bezeichnung": "Sparrate",
        "betrag": Decimal("-200.00"),
        "rhythmus": "monatlich",
        "anker_tag": 15,
        "start_datum": START_DATUM,
        "end_datum": None,
    }
    daten.update(abweichungen)
    return daten


class TestRegelEingaben:
    """Anlegen und Bearbeiten muessen dieselben Pruefungen durchlaufen -
    vorher war ein Betrag von 0 nur beim Bearbeiten verboten."""

    @pytest.mark.parametrize(
        "abweichung,meldung",
        [
            ({"betrag": Decimal("0")}, "Betrag darf nicht 0 sein"),
            ({"rhythmus": "quartalsweise"}, "Unbekannter Rhythmus"),
            ({"anker_tag": 0}, "Anker-Tag"),
            ({"anker_tag": 32}, "Anker-Tag"),
        ],
    )
    def test_anlegen_lehnt_ab(self, db, app, abweichung, meldung):
        with pytest.raises(ValueError, match=meldung):
            regel_erstellen(db, **regel_daten(app["Urlaub"], **abweichung))

    @pytest.mark.parametrize(
        "abweichung,meldung",
        [
            ({"betrag": Decimal("0")}, "Betrag darf nicht 0 sein"),
            ({"rhythmus": "quartalsweise"}, "Unbekannter Rhythmus"),
            ({"anker_tag": 32}, "Anker-Tag"),
        ],
    )
    def test_bearbeiten_lehnt_ab(self, db, app, abweichung, meldung):
        regel = regel_erstellen(db, **regel_daten(app["Urlaub"]))
        db.commit()

        with pytest.raises(ValueError, match=meldung):
            regel_bearbeiten(db, regel, **regel_daten(app["Urlaub"], **abweichung))

    def test_gueltige_regel_wird_angelegt_und_erzeugt_vorkommen(self, db, app):
        regel = regel_erstellen(db, **regel_daten(app["Urlaub"]))
        db.commit()

        assert db.query(ForecastRegel).count() == 1
        assert regel.vorkommen, "Vorkommen werden direkt mit angelegt"


class TestEndgueltigVerbuchen:
    def _umbuchung(self, db, betrag="-500.00", tag=1):
        b = Buchung(
            transaction_id=f"tx-{betrag}-{tag}",
            datum=dt.date(2026, 7, tag),
            typ="TRANSFER",
            betrag=Decimal(betrag),
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(b)
        db.commit()
        markiere_als_umbuchung(db, b)
        return b

    def test_abgeglichene_umbuchung_kann_nicht_final_verbucht_werden(self, db, app):
        """Sonst haengt die Gegenbuchung an einer Buchung, die sich fuer
        alleinstehend haelt."""
        ab = self._umbuchung(db, "-500.00", 1)
        auf = self._umbuchung(db, "500.00", 3)
        abgleichen(db, ab, auf, app["Urlaub"].id)

        with pytest.raises(ValueError, match="bereits mit einer Gegenbuchung"):
            endgueltig_verbuchen(db, ab, app["Sonderausgaben"].id)

    def test_bereits_zugeordnete_umbuchung_wird_abgelehnt(self, db, app):
        b = self._umbuchung(db)
        endgueltig_verbuchen(db, b, app["Urlaub"].id)

        with pytest.raises(ValueError, match="bereits einem Topf zugeordnet"):
            endgueltig_verbuchen(db, b, app["Sonderausgaben"].id)

    def test_nicht_markierte_buchung_wird_abgelehnt(self, db, app):
        b = Buchung(
            transaction_id="tx-normal",
            datum=dt.date(2026, 7, 1),
            typ="PAYMENT",
            betrag=Decimal("-10.00"),
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(b)
        db.commit()

        with pytest.raises(ValueError, match="nicht als Umbuchung markiert"):
            endgueltig_verbuchen(db, b, app["Urlaub"].id)


class TestFehlerseite:
    """Eingabefehler kommen im gewohnten Layout zurueck, nicht als rohes JSON."""

    @pytest.fixture
    def client(self, db, app):
        return TestClient(fastapi_app)

    def test_unbekannte_buchung_liefert_html(self, client):
        antwort = client.get("/buchungen/9999")

        assert antwort.status_code == 404
        assert "text/html" in antwort.headers["content-type"]
        assert "Buchung nicht gefunden" in antwort.text
        assert "Zur Übersicht" in antwort.text

    def test_ungueltiger_betrag_beim_vorkommen_ist_kein_500er(self, client, app):
        """Regression: die Route hatte gar keine Fehlerbehandlung."""
        antwort = client.post(
            "/forecast/vorkommen/neu",
            data={
                "topf_id": str(app["Urlaub"].id),
                "bezeichnung": "Test",
                "erwarteter_betrag": "keine Zahl",
                "erwartetes_datum": "2026-09-01",
            },
        )

        assert antwort.status_code == 400
        assert "text/html" in antwort.headers["content-type"]

    def test_ungueltiger_rhythmus_ueber_das_formular(self, client, app):
        antwort = client.post(
            "/forecast/regel/neu",
            data={
                "topf_id": str(app["Urlaub"].id),
                "bezeichnung": "Test",
                "betrag": "-100",
                "rhythmus": "quartalsweise",
                "anker_tag": "15",
                "start_datum": "2026-07-01",
            },
        )

        assert antwort.status_code == 400
        assert "Unbekannter Rhythmus" in antwort.text
