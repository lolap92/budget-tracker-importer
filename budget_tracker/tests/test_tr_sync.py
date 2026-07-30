"""Abgleich mit der Timeline (app/tr_sync.py).

Netzzugriff und Verarbeitung sind getrennt, deshalb laeuft hier beides ohne
Verbindung: die Verarbeitung bekommt fertige Events, das Einsammeln eine
Attrappe, die sich wie pytrs WebSocket-Schnittstelle verhaelt.
"""
import asyncio
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.import_core import QUELLE_CSV, ImportKontext, uebernehmen
from app.models import Buchung, ImportVerdacht
from app.tr_events import zeile_aus_event
from app.tr_sync import ab_zeitpunkt, events_laden, lauf, verarbeiten
from tests.conftest import START_DATUM

FIXTURES = Path(__file__).parent / "fixtures" / "tr_events"


def event(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FakeApi:
    """Verhaelt sich wie TradeRepublicApi, soweit der Abgleich sie benutzt:
    jede Anfrage liefert eine Subscription-Nummer, die Antwort kommt ueber
    recv() - moeglicherweise nach Antworten auf andere Anfragen."""

    def __init__(self, seiten: list[dict], details: dict[str, dict] | None = None):
        self.seiten = seiten
        self.details = details or {}
        self.warteschlange: list[tuple[str, dict, dict]] = []
        self.naechste_nummer = 0
        self.abgefragte_details: list[str] = []
        self.geschlossen = False
        self.offene_subscriptions: set[str] = set()

    def _anmelden(self, antwort: dict) -> str:
        self.naechste_nummer += 1
        nummer = str(self.naechste_nummer)
        self.offene_subscriptions.add(nummer)
        self.warteschlange.append((nummer, {}, antwort))
        return nummer

    async def timeline_transactions(self, cursor=None):
        seite = next(
            (s for s in self.seiten if s.get("_cursor") == cursor),
            {"items": [], "cursors": {}},
        )
        return self._anmelden({k: v for k, v in seite.items() if k != "_cursor"})

    async def timeline_detail_v2(self, event_id):
        self.abgefragte_details.append(event_id)
        if event_id not in self.details:
            raise RuntimeError("kein Detail")
        return self._anmelden(self.details[event_id])

    async def recv(self):
        return self.warteschlange.pop(0)

    async def unsubscribe(self, nummer):
        self.offene_subscriptions.discard(nummer)

    async def close(self):
        self.geschlossen = True


class TestEventsLaden:
    def test_blaettert_bis_zur_zeitgrenze(self):
        grenze = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
        neu = {"id": "a", "timestamp": "2026-07-18T12:00:00.000+0000",
               "status": "EXECUTED", "amount": {"value": -10.0}}
        alt = {"id": "b", "timestamp": "2026-05-02T12:00:00.000+0000",
               "status": "EXECUTED", "amount": {"value": -20.0}}
        api = FakeApi(
            seiten=[
                {"_cursor": None, "items": [neu], "cursors": {"after": "s2"}},
                {"_cursor": "s2", "items": [alt], "cursors": {"after": "s3"}},
            ],
            details={"a": {"sections": []}},
        )

        events = asyncio.run(events_laden(api, grenze, lambda _: False))

        assert [e["id"] for e in events] == ["a"]
        # Die dritte Seite wird nicht mehr geholt: ab dem ersten zu alten
        # Event ist der Rest der Timeline erst recht zu alt.
        assert api.naechste_nummer == 3  # zwei Seiten + ein Detail
        assert not api.offene_subscriptions

    def test_details_nur_fuer_unbekannte_kontobewegungen(self):
        grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        bekannt = {"id": "bekannt", "timestamp": "2026-07-18T12:00:00.000+0000",
                   "status": "EXECUTED", "amount": {"value": -10.0}}
        storniert = {"id": "storniert", "timestamp": "2026-07-18T12:00:00.000+0000",
                     "status": "CANCELED", "amount": {"value": -10.0}}
        ohne_geld = {"id": "dokument", "timestamp": "2026-07-18T12:00:00.000+0000",
                     "status": "EXECUTED", "amount": None}
        neu = {"id": "neu", "timestamp": "2026-07-18T12:00:00.000+0000",
               "status": "EXECUTED", "amount": {"value": -10.0}}
        api = FakeApi(
            seiten=[{"_cursor": None, "items": [bekannt, storniert, ohne_geld, neu],
                     "cursors": {}}],
            details={"neu": {"sections": []}},
        )

        events = asyncio.run(events_laden(api, grenze, {"bekannt"}.__contains__))

        assert [e["id"] for e in events] == ["neu"]
        assert api.abgefragte_details == ["neu"]

    def test_fehlendes_detail_verhindert_die_buchung_nicht(self):
        """Ohne Detail fehlt nur der Verwendungszweck - die Bewegung selbst
        ist trotzdem ein Fakt."""
        grenze = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        # Wie aus der Timeline: das Event allein, ohne Detail.
        roh = {k: v for k, v in event("zinsen").items() if k != "details"}
        api = FakeApi(
            seiten=[{"_cursor": None, "items": [roh], "cursors": {}}],
            details={},  # jeder Detail-Abruf scheitert
        )

        events = asyncio.run(events_laden(api, grenze, lambda _: False))

        assert len(events) == 1
        assert events[0]["details"] == {}
        # ... und wird trotzdem zu einer Buchung, nur ohne Verwendungszweck.
        assert zeile_aus_event(events[0])["verwendungszweck"] is None


class TestLauf:
    """Buchungen und Depotstand teilen sich eine Verbindung."""

    def test_verbindung_wird_geschlossen(self):
        api = FakeApi(seiten=[{"_cursor": None, "items": [], "cursors": {}}])

        events, depot = asyncio.run(
            lauf(api, dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), lambda _: False)
        )

        assert events == []
        assert api.geschlossen is True

    def test_scheiterndes_depot_kostet_nicht_die_buchungen(self):
        """Die Buchungen sind das Wesentliche - der Depotstand ist Beiwerk."""
        api = FakeApi(
            seiten=[{"_cursor": None, "items": [event("zinsen")], "cursors": {}}],
            details={"019f1ba7-f0b5-72c0-a7ff-b17274609d95": {"sections": []}},
        )
        # FakeApi kennt compact_portfolio nicht -> der Depot-Abruf scheitert.

        events, depot = asyncio.run(
            lauf(api, dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), lambda _: False)
        )

        assert len(events) == 1
        assert depot is None
        assert api.geschlossen is True


class TestVerarbeiten:
    def test_neue_bewegungen_werden_buchungen(self, db, app):
        zahlen = verarbeiten(db, [event("eingehende_ueberweisung"), event("zinsen")])

        assert zahlen["neu"] == 2
        assert db.query(Buchung).count() == 2
        assert {b.quelle for b in db.query(Buchung).all()} == {"api"}

    def test_bekannte_transaction_id_wird_uebersprungen(self, db, app):
        verarbeiten(db, [event("zinsen")])
        zahlen = verarbeiten(db, [event("zinsen")])

        assert zahlen == {"gelesen": 1, "neu": 0, "duplikate": 1, "vor_startdatum": 0,
                          "verdacht": 0, "uebersprungen": 0}
        assert db.query(Buchung).count() == 1

    def test_bewegung_vor_dem_startdatum(self, db, app):
        alt = event("zinsen") | {"timestamp": "2025-11-30T10:00:00.000+0000"}

        zahlen = verarbeiten(db, [alt])

        assert zahlen["vor_startdatum"] == 1
        assert db.query(Buchung).count() == 0

    def test_events_ohne_geldbewegung_zaehlen_als_uebersprungen(self, db, app):
        zahlen = verarbeiten(db, [event("zinsen") | {"status": "CANCELED"}])

        assert zahlen["uebersprungen"] == 1
        assert db.query(Buchung).count() == 0


class TestDopplungsverdacht:
    """Der gefaehrlichste Fall: dieselbe Zahlung kam schon per CSV herein,
    fuehrt dort aber eine andere transaction_id."""

    @pytest.fixture
    def bereits_per_csv(self, db, app):
        uebernehmen(
            db,
            ImportKontext.laden(db),
            transaction_id="csv-eigene-id",
            datum=dt.date(2026, 6, 29),
            betrag=Decimal("550.00"),
            typ="TRANSFER_INBOUND",
            quelle=QUELLE_CSV,
        )
        db.commit()
        return db.query(Buchung).one()

    def test_verdacht_statt_doppelter_buchung(self, db, app, bereits_per_csv):
        zahlen = verarbeiten(db, [event("eingehende_ueberweisung")])

        assert zahlen["verdacht"] == 1
        assert zahlen["neu"] == 0
        assert db.query(Buchung).count() == 1  # keine zweite Buchung

        verdacht = db.query(ImportVerdacht).one()
        assert verdacht.entscheidung is None
        assert verdacht.vermutete_dopplung_id == bereits_per_csv.id
        assert verdacht.betrag == Decimal("550.00")
        # Der Verwendungszweck aus dem Detail bleibt erhalten, damit sich der
        # Fall ueberhaupt beurteilen laesst.
        assert verdacht.verwendungszweck == "Haus Renovierung Anteil"

    def test_derselbe_fall_wird_nicht_zweimal_vorgelegt(self, db, app, bereits_per_csv):
        verarbeiten(db, [event("eingehende_ueberweisung")])
        zahlen = verarbeiten(db, [event("eingehende_ueberweisung")])

        assert zahlen["verdacht"] == 0
        assert db.query(ImportVerdacht).count() == 1

    def test_verworfener_fall_kehrt_nicht_zurueck(self, db, app, bereits_per_csv):
        verarbeiten(db, [event("eingehende_ueberweisung")])
        db.query(ImportVerdacht).one().entscheidung = "verworfen"
        db.commit()

        zahlen = verarbeiten(db, [event("eingehende_ueberweisung")])

        assert zahlen["verdacht"] == 0
        assert db.query(ImportVerdacht).count() == 1
        assert db.query(Buchung).count() == 1


class TestZeitgrenze:
    def test_ohne_buchungen_ab_startdatum(self, db, app):
        assert ab_zeitpunkt(db).date() == START_DATUM

    def test_mit_buchungen_vierzehn_tage_zurueck(self, db, app):
        uebernehmen(
            db,
            ImportKontext.laden(db),
            transaction_id="letzte",
            datum=dt.date(2026, 7, 20),
            betrag=Decimal("-10.00"),
            typ="PAYMENT",
            quelle=QUELLE_CSV,
        )
        db.commit()

        assert ab_zeitpunkt(db).date() == dt.date(2026, 7, 6)

    def test_nie_vor_dem_startdatum(self, db, app):
        uebernehmen(
            db,
            ImportKontext.laden(db),
            transaction_id="frueh",
            datum=START_DATUM,
            betrag=Decimal("-10.00"),
            typ="PAYMENT",
            quelle=QUELLE_CSV,
        )
        db.commit()

        assert ab_zeitpunkt(db).date() == START_DATUM
