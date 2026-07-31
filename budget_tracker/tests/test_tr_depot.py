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
from app.tr_depot import (
    aktueller_snapshot,
    anteile,
    depot_laden,
    positionen_aus_antwort,
    snapshot_speichern,
)
from app.tr_sync import _abrufen
from tests.test_tr_sync import FakeApi


class DepotApi(FakeApi):
    """Ergaenzt die Timeline-Attrappe um die Depot-Anfragen.

    Bildet die neue Abfrage nach: compactPortfolioByType, Positionen nach
    Kategorien gruppiert, ISIN im Feld "isin". Die beiden Schalter bilden die
    Faelle nach, in denen nur die alte Abfrage bleibt.
    """

    def __init__(
        self, positionen, cash, instrumente, kurse,
        ohne_depotnummer=False, bytype_fehlt=False,
    ):
        super().__init__(seiten=[])
        self.positionen = positionen
        self.cash_bestand = cash
        self.instrumente = instrumente
        self.kurse = kurse
        self.ohne_depotnummer = ohne_depotnummer
        self.bytype_fehlt = bytype_fehlt
        self.gestellte_anfragen: list[str] = []

    def settings(self):
        if self.ohne_depotnummer:
            return {}
        return {"securitiesAccountNumber": "DE1234567"}

    async def subscribe(self, payload):
        self.gestellte_anfragen.append(payload["type"])
        if payload["type"] == "compactPortfolioByType":
            if self.bytype_fehlt:
                raise RuntimeError("unbekannter Typ")
            gruppiert = [
                {k if k != "instrumentId" else "isin": v for k, v in p.items()}
                for p in self.positionen
            ]
            return self._anmelden({"categories": [{"positions": gruppiert}]})
        if payload["type"] == "compactPortfolio":
            return self._anmelden({"positions": self.positionen})
        raise AssertionError(f"unerwartete Anfrage {payload}")

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


class TestAntwortformate:
    """Trade Republic hat compactPortfolio durch compactPortfolioByType
    ersetzt: Positionen nach Kategorien gruppiert, ISIN im Feld "isin"."""

    def test_neues_format_mit_kategorien(self):
        antwort = {
            "categories": [
                {"positions": [{"isin": "IE00B3RBWM25", "netSize": "1"}]},
                {"positions": [{"isin": "US0378331005", "netSize": "3"}]},
            ]
        }

        assert [p["isin"] for p in positionen_aus_antwort(antwort)] == [
            "IE00B3RBWM25",
            "US0378331005",
        ]

    def test_altes_format_mit_instrumentid(self):
        antwort = {"positions": [{"instrumentId": "IE00B3RBWM25", "netSize": "1"}]}

        assert positionen_aus_antwort(antwort)[0]["isin"] == "IE00B3RBWM25"

    def test_position_ohne_kennung_wird_verworfen(self):
        assert positionen_aus_antwort({"positions": [{"netSize": "1"}]}) == []

    def test_leere_antwort(self):
        assert positionen_aus_antwort({}) == []


class TestAbruf:
    def test_neue_abfrage_wird_bevorzugt(self):
        api = api_mit_zwei_positionen()

        asyncio.run(depot_laden(api, _abrufen))

        assert api.gestellte_anfragen == ["compactPortfolioByType"]

    def test_ohne_depotnummer_gleich_die_alte_abfrage(self):
        """Die neue Abfrage braucht die Depotnummer - fehlt sie, hat ein
        Versuch keinen Zweck."""
        api = api_mit_zwei_positionen(ohne_depotnummer=True)

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert api.gestellte_anfragen == ["compactPortfolio"]
        assert len(daten["positionen"]) == 2

    def test_rueckfall_wenn_die_neue_abfrage_scheitert(self):
        """Lieber ein zweiter Versuch als ein leer gemeldetes Depot."""
        api = api_mit_zwei_positionen(bytype_fehlt=True)

        daten = asyncio.run(depot_laden(api, _abrufen))

        assert api.gestellte_anfragen == ["compactPortfolioByType", "compactPortfolio"]
        assert len(daten["positionen"]) == 2

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

    def test_positionen_zeigen_ihren_anteil_und_keine_stueckzahl(self, client, db, app):
        """Der Anteil am Depot ist das, was interessiert - die Stueckzahl
        wich ihm auf der Seite."""
        snapshot_speichern(db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen)))
        db.commit()

        text = client.get("/depot").text

        assert "80,2 %" in text
        assert "19,8 %" in text
        assert "Stk" not in text


class TestAnteile:
    """Der Anteil je Position bezieht sich auf den Wert der Wertpapiere,
    nicht auf Wertpapiere plus Cash - sonst wuerde jede Einzahlung aufs
    Verrechnungskonto alle Anteile verschieben, ohne dass sich am Depot
    etwas geaendert haette."""

    def test_ohne_snapshot_leere_liste(self):
        assert anteile(None) == []

    def test_anteile_summieren_sich_auf_hundert(self, db, app):
        snapshot = snapshot_speichern(
            db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen))
        )
        db.commit()

        ergebnis = anteile(snapshot)

        assert sum(anteil for _, anteil in ergebnis) == Decimal("100.0")

    def test_groesste_position_zuerst(self, db, app):
        snapshot = snapshot_speichern(
            db, asyncio.run(depot_laden(api_mit_zwei_positionen(), _abrufen))
        )
        db.commit()

        ergebnis = anteile(snapshot)

        assert [p.name for p, _ in ergebnis] == ["Vanguard FTSE All-World", "Apple"]
        assert [a for _, a in ergebnis] == [Decimal("80.2"), Decimal("19.8")]

    def test_ohne_wert_keine_division_durch_null(self, db, app):
        """Ein frischer Snapshot, dessen Positionen noch keinen Kurs hatten,
        darf nicht crashen - er zeigt einfach ueberall 0 %."""
        snapshot = snapshot_speichern(
            db, asyncio.run(depot_laden(api_mit_zwei_positionen(kurse={}), _abrufen))
        )
        db.commit()

        assert anteile(snapshot) == []


class TestProzentFilter:
    def test_formatierung(self):
        from app.webutils import prozent

        assert prozent(Decimal("80.2")) == "80,2 %"
        assert prozent(Decimal("3")) == "3,0 %"

    def test_ohne_wert(self):
        from app.webutils import prozent

        assert prozent(None) == "-"
