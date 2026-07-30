"""Depotstand abrufen, ablegen und anzeigen (app/tr_depot.py).

Ohne Netz: die Attrappe aus test_tr_sync verhaelt sich wie pytrs Schnittstelle.
"""
import asyncio
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.import_core import QUELLE_CSV, ImportKontext, uebernehmen
from app.main import app as fastapi_app
from app.models import DepotPosition, DepotSnapshot, Topf
from app.tr_depot import aktueller_snapshot, depot_laden, snapshot_speichern
from app.tr_sync import _abrufen
from tests.test_tr_sync import FakeApi


class DepotApi(FakeApi):
    """Ergaenzt die Timeline-Attrappe um die Depot-Anfragen."""

    def __init__(self, positionen, cash, instrumente, kurse):
        super().__init__(seiten=[])
        self.positionen = positionen
        self.cash_bestand = cash
        self.instrumente = instrumente
        self.kurse = kurse

    async def compact_portfolio(self):
        return self._anmelden({"positions": self.positionen})

    async def cash(self):
        return self._anmelden(self.cash_bestand)

    async def instrument_details(self, isin):
        if isin not in self.instrumente:
            raise RuntimeError("unbekanntes Instrument")
        return self._anmelden(self.instrumente[isin])

    async def ticker(self, isin, exchange="LSX"):
        if isin not in self.kurse:
            raise RuntimeError("kein Kurs")
        return self._anmelden({"last": {"price": self.kurse[isin]}})


def api_mit_zwei_positionen(**abweichungen):
    daten = {
        "positionen": [
            {"instrumentId": "IE00B3RBWM25", "netSize": "18.431870", "averageBuyIn": "92.15"},
            {"instrumentId": "US0378331005", "netSize": "3", "averageBuyIn": "180.00"},
        ],
        "cash": [{"currencyId": "EUR", "amount": "4812.30"}],
        "instrumente": {
            "IE00B3RBWM25": {"shortName": "Vanguard FTSE All-World", "exchangeIds": ["LSX"]},
            "US0378331005": {"shortName": "Apple", "exchangeIds": ["LSX"]},
        },
        "kurse": {"IE00B3RBWM25": "128.50", "US0378331005": "195.20"},
    }
    daten.update(abweichungen)
    return DepotApi(**daten)


class TestAbruf:
    def test_positionen_mit_wert_und_cash(self):
        daten = asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen))

        assert daten["cash"] == Decimal("4812.30")
        assert len(daten["positionen"]) == 2

        vanguard = daten["positionen"][0]
        assert vanguard["name"] == "Vanguard FTSE All-World"
        assert vanguard["stueck"] == Decimal("18.431870")
        # 18,43187 * 128,50 = 2368,495295, kaufmaennisch auf Cent gerundet
        assert vanguard["wert"] == Decimal("2368.50")

    def test_position_ohne_kurs_faellt_heraus(self):
        """Lieber eine Position weniger als ein stillschweigend zu niedriger
        Gesamtwert."""
        api = api_mit_zwei_positionen(kurse={"IE00B3RBWM25": "128.50"})

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert [p["isin"] for p in daten["positionen"]] == ["IE00B3RBWM25"]

    def test_position_ohne_boerse_faellt_heraus(self):
        api = api_mit_zwei_positionen(
            instrumente={
                "IE00B3RBWM25": {"shortName": "Vanguard FTSE All-World", "exchangeIds": ["LSX"]},
                "US0378331005": {"shortName": "Apple", "exchangeIds": []},
            }
        )

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert [p["isin"] for p in daten["positionen"]] == ["IE00B3RBWM25"]

    def test_anleihekurs_notiert_in_prozent_des_nennwerts(self):
        """Anleihen notieren je 100 EUR Nennwert - ohne Umrechnung waere der
        Wert um Faktor 100 zu hoch, was in einer Summe nicht auffiele."""
        api = DepotApi(
            positionen=[{"instrumentId": "DE000BU2Z015", "netSize": "10", "averageBuyIn": "98.00"}],
            cash=[{"currencyId": "EUR", "amount": "0"}],
            instrumente={"DE000BU2Z015": {"shortName": "Bundesrepublik Deutschland Feb. 2032",
                                          "exchangeIds": ["LSX"]}},
            kurse={"DE000BU2Z015": "99.50"},
        )

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert daten["positionen"][0]["wert"] == Decimal("9.95")

    def test_leeres_depot(self):
        api = DepotApi(positionen=[], cash=[], instrumente={}, kurse={})

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert daten == {"cash": Decimal("0"), "positionen": []}


class TestSpeichern:
    def test_snapshot_ersetzt_den_vorherigen(self, db, app):
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()

        assert db.query(DepotSnapshot).count() == 1
        # Die Positionen des alten Standes duerfen nicht zurueckbleiben.
        assert db.query(DepotPosition).count() == 2

    def test_gesamtwert_ist_die_summe_der_positionen(self, db, app):
        snapshot = snapshot_speichern(
            db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen))
        )
        db.commit()

        assert snapshot.gesamtwert == Decimal("2368.50") + Decimal("585.60")
        assert aktueller_snapshot(db).cash == Decimal("4812.30")


class TestSeite:
    @pytest.fixture
    def client(self, db, app):
        return TestClient(fastapi_app)

    def test_ohne_stand_erklaert_die_seite_sich(self, client):
        assert "Noch kein Depotstand abgerufen" in client.get("/depot").text

    def test_positionen_und_summe(self, client, db, app):
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()

        text = client.get("/depot").text

        assert "Vanguard FTSE All-World" in text
        assert "2.368,50" in text
        assert "4.812,30" in text

    def test_abweichung_zum_berechneten_kontostand(self, client, db, app):
        """Der Cash-Bestand bei Trade Republic gegen den selbst gerechneten
        Kontostand - eine fehlende Buchung faellt so sofort auf."""
        for topf in db.query(Topf).all():
            topf.startsaldo = Decimal("1000.00")
        uebernehmen(
            db,
            ImportKontext.laden(db),
            transaction_id="csv-1",
            datum=dt.date(2026, 7, 1),
            betrag=Decimal("-187.70"),
            typ="PAYMENT",
            quelle=QUELLE_CSV,
        )
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()

        text = client.get("/depot").text

        # Berechnet 4000 - 187,70 = 3.812,30; laut TR 4.812,30 -> 1.000 fehlen.
        assert "3.812,30" in text
        assert "1.000,00" in text
        assert "fehlt eine Buchung" in text

    def test_keine_abweichung_wird_als_solche_benannt(self, client, db, app):
        # Startsalden, die zusammen exakt dem Cash-Bestand entsprechen.
        for topf, saldo in zip(db.query(Topf).all(), ["1000.00", "1000.00", "1000.00", "1812.30"]):
            topf.startsaldo = Decimal(saldo)
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()

        assert "stimmt mit dem echten Bestand überein" in client.get("/depot").text
