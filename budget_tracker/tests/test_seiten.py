"""Rendering-Smoke-Tests: jede Seite muss mit realistischen Daten durchlaufen.

Server-seitig gerenderte Templates fallen sonst erst im Betrieb auf - ein
umbenanntes Feld oder ein fehlender Kontextwert wirft dort einen 500er, den
keine Unit-Test-Ebene sieht.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.models import Buchung, ForecastRegel, ForecastVorkommen


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app)


@pytest.fixture
def bewegungen(db, app):
    """Offene Buchung, schwebende Umbuchung, Forecast-Regel mit Vorkommen."""
    for t in app.values():
        t.startsaldo = Decimal("1000.00")
    db.add_all(
        [
            Buchung(
                transaction_id="offen",
                datum=dt.date(2026, 7, 10),
                typ="PAYMENT",
                betrag=Decimal("-450.00"),
                verwendungszweck="REWE",
                importiert_am=dt.datetime.utcnow(),
            ),
            Buchung(
                transaction_id="schwebend",
                datum=dt.date(2026, 7, 11),
                typ="TRANSFER",
                betrag=Decimal("-800.00"),
                ist_umbuchung=True,
                umbuchung_richtung="ausgehend",
                importiert_am=dt.datetime.utcnow(),
            ),
            Buchung(
                transaction_id="zugeordnet",
                datum=dt.date(2026, 7, 12),
                typ="PAYMENT",
                betrag=Decimal("-60.00"),
                titel="Tanken",
                topf_id=app["Urlaub"].id,
                zuordnung_quelle="manuell",
                importiert_am=dt.datetime.utcnow(),
            ),
        ]
    )
    regel = ForecastRegel(
        topf_id=app["Urlaub"].id,
        bezeichnung="Sparrate",
        betrag=Decimal("-200.00"),
        rhythmus="monatlich",
        anker_tag=1,
        start_datum=dt.date(2026, 6, 1),
    )
    db.add(regel)
    db.flush()
    db.add(
        ForecastVorkommen(
            regel_id=regel.id,
            topf_id=app["Urlaub"].id,
            bezeichnung="Sparrate",
            erwarteter_betrag=Decimal("-200.00"),
            erwartetes_datum=dt.date(2026, 9, 1),
        )
    )
    db.commit()
    return app


@pytest.mark.parametrize(
    "pfad",
    [
        "/",
        "/mehr",
        "/buchungen",
        "/buchungen/neu",
        "/zuordnen",
        "/umbuchungen",
        "/forecast",
        "/forecast?topf=alle",
        "/forecast/regeln",
        "/regeln/neu",
        "/topf-umbuchung/neu",
    ],
)
def test_seite_rendert(client, bewegungen, pfad):
    antwort = client.get(pfad)

    assert antwort.status_code == 200, antwort.text[:400]
    assert "<html" in antwort.text


def test_buchungsdetail_rendert(client, bewegungen, db):
    b = db.query(Buchung).filter(Buchung.transaction_id == "offen").one()

    assert client.get(f"/buchungen/{b.id}").status_code == 200


def test_uebersicht_weist_den_nicht_zugeordneten_teil_aus(client, bewegungen):
    """Der Kontostand bleibt bankgenau und enthaelt offene sowie schwebende
    Buchungen; die Differenz zur Summe der Toepfe muss benannt sein."""
    text = client.get("/").text

    # 4x1000 Startsaldo - 450 offen - 800 schwebend - 60 zugeordnet
    assert "2.690" in text
    # Differenz zur Toepfe-Summe (3940): -450 offen, -800 schwebend
    assert "davon -1.250,00 € noch keinem Topf zugeordnet" in text


def test_ohne_konfiguration_leitet_der_bootstrap_gate_um(db, toepfe):
    """Ohne Konfiguration muss jede Seite auf die Ersteinrichtung fuehren."""
    antwort = TestClient(fastapi_app).get("/", follow_redirects=False)

    assert antwort.status_code == 303
    assert antwort.headers["location"].endswith("/bootstrap")
