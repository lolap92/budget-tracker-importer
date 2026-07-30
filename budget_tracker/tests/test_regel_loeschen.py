"""Regel loeschen (app/forecast_engine.py).

Bis 1.25.0 gab es diesen Weg nicht: eine ueberfluessige oder versehentlich
doppelt angelegte Regel liess sich nicht loswerden. Ihre Vorkommen einzeln zu
loeschen half nicht - ensure_forecast_vorkommen legt sie beim naechsten Scan,
also binnen 30 Sekunden, wieder an.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.forecast_engine import (
    ensure_forecast_vorkommen,
    regel_erstellen,
    regel_loeschen,
)
from app.main import app as fastapi_app
from app.models import Buchung, ForecastRegel, ForecastVorkommen
from tests.conftest import HEUTE


@pytest.fixture
def regel(db, app):
    r = regel_erstellen(
        db,
        topf_id=app["Urlaub"].id,
        bezeichnung="Standard-Sparrate",
        betrag=Decimal("-200.00"),
        rhythmus="monatlich",
        anker_tag=28,
        start_datum=dt.date(2026, 1, 28),
        end_datum=None,
    )
    db.commit()
    ensure_forecast_vorkommen(db, heute=HEUTE)
    db.commit()
    return r


class TestLoeschen:
    def test_regel_und_offene_vorkommen_verschwinden(self, db, app, regel):
        assert db.query(ForecastVorkommen).count() > 0

        entfernt = regel_loeschen(db, regel)
        db.commit()

        assert entfernt > 0
        assert db.query(ForecastRegel).count() == 0
        assert db.query(ForecastVorkommen).count() == 0

    def test_die_vorkommen_kommen_nicht_wieder(self, db, app, regel):
        """Der Kern der Sache: ohne Regel erzeugt der naechste Scan nichts."""
        regel_loeschen(db, regel)
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).count() == 0

    def test_gebuchtes_vorkommen_bleibt_als_fakt(self, db, app, regel):
        buchung = Buchung(
            transaction_id="tx-1",
            datum=dt.date(2026, 7, 28),
            typ="PAYMENT",
            betrag=Decimal("-200.00"),
            topf_id=app["Urlaub"].id,
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(buchung)
        db.flush()
        verknuepft = db.query(ForecastVorkommen).first()
        verknuepft.verknuepfte_buchung_id = buchung.id
        db.commit()
        verknuepft_id = verknuepft.id

        regel_loeschen(db, regel)
        db.commit()

        uebrig = db.query(ForecastVorkommen).filter_by(id=verknuepft_id).one()
        assert uebrig.verknuepfte_buchung_id == buchung.id
        # Nur die Herkunft ist weg - sonst haenge es an einer Regel, die es
        # nicht mehr gibt.
        assert uebrig.regel_id is None

    def test_verworfenes_vorkommen_bleibt_als_entscheidung(self, db, app, regel):
        verworfen = db.query(ForecastVorkommen).first()
        verworfen.ignoriert = True
        db.commit()
        verworfen_id = verworfen.id

        regel_loeschen(db, regel)
        db.commit()

        uebrig = db.query(ForecastVorkommen).filter_by(id=verworfen_id).one()
        assert uebrig.ignoriert is True
        assert uebrig.regel_id is None


class TestUeberDieSeite:
    @pytest.fixture
    def client(self, db, app):
        return TestClient(fastapi_app, follow_redirects=False)

    def test_knopf_steht_auf_der_regel_seite(self, client, regel, app):
        # Die Seite zeigt immer einen Topf - hier den der Regel.
        text = client.get(f"/forecast/regeln?topf={app['Urlaub'].id}").text

        assert "Regel löschen" in text
        assert "Einzelne Vorkommen zu löschen genügt nicht" in text

    def test_loeschen_ueber_die_route(self, client, db, regel):
        antwort = client.post(f"/forecast/regel/{regel.id}/loeschen")

        assert antwort.status_code == 303
        db.expire_all()
        assert db.query(ForecastRegel).count() == 0

    def test_unbekannte_regel(self, client):
        assert client.post("/forecast/regel/999/loeschen").status_code == 404
