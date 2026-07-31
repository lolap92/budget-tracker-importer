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
        "/trade-republic",
        "/depot",
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


class TestAnzeigekorrekturen:
    def test_monatsname_maerz(self):
        """A1: monat_de schrieb 'Maerz', monat_kurz daneben 'Mär'."""
        from app.webutils import monat_de, monat_kurz

        assert monat_de(dt.date(2027, 3, 1)) == "März 2027"
        assert monat_kurz(dt.date(2027, 3, 1)) == "Mär 27"

    def test_forecast_vorkommen_zeigt_den_tag(self, client, bewegungen, app):
        """A2: nur der Monat liess zwei Vorkommen im selben Monat gleich aussehen."""
        text = client.get(f"/forecast?topf={app['Urlaub'].id}").text

        assert "erwartet 01.09.2026" in text

    def test_desktop_tabelle_kennzeichnet_schwebende_umbuchung(self, client, bewegungen):
        """A3: stand vorher als schlichtes 'offen' in der Tabelle."""
        text = client.get("/buchungen").text

        assert text.count("Umbuchung schwebend") >= 2, "mobile Karte und Desktop-Tabelle"

    def test_sprungleiste_entfaellt_ohne_offene_faelle(self, client, db, app):
        """A4: die Chips fuehren auf andere Seiten - ohne offene Faelle gibt es
        nichts zu springen."""
        text = client.get("/buchungen").text

        assert "offen zuordnen" not in text
        assert "abgleichen" not in text

    def test_sprungleiste_erscheint_mit_offenen_faellen(self, client, bewegungen):
        text = client.get("/buchungen").text

        assert "1 offen zuordnen" in text
        assert "1 Umbuchung abgleichen" in text

    def test_minus_warnung_auch_neben_der_sondertilgungszeile(self, client, db, app):
        """A5: die Zeile war rot markiert, der Grund fehlte."""
        from decimal import Decimal as D

        from app.forecast_engine import regel_erstellen

        kredit = app["Haus Kredit"]
        kredit.startsaldo = D("100.00")
        db.commit()
        # Bei jaehrlichen Regeln stammt der Monat aus start_datum und der Tag
        # aus anker_tag - beides muss zusammenpassen, sonst faellt die erste
        # Faelligkeit ein Jahr weiter nach hinten.
        faellig = dt.date.today() + dt.timedelta(days=60)
        regel_erstellen(
            db, topf_id=kredit.id, bezeichnung="Sondertilgung", betrag=D("-5000.00"),
            rhythmus="jaehrlich", anker_tag=faellig.day,
            start_datum=faellig, end_datum=None,
        )
        db.commit()

        text = client.get("/").text
        assert "Wird nicht erreicht" in text
        assert "rutscht lt. Prognose ins Minus" in text

    def test_zuordnen_erklaert_die_aktionen(self, client, bewegungen):
        """A6: 'löschen' stand ohne jeden Hinweis neben 'als Umbuchung'."""
        text = client.get("/zuordnen").text

        assert "Karteileichen" in text
        assert "wieder angelegt" in text


class TestDepotAufDerStartseite:
    """Neben den Toepfen, nicht in ihrer Summe: der Depotwert ist kein
    Guthaben auf dem Cashkonto."""

    def test_ohne_stand_keine_kachel(self, client, bewegungen):
        assert "Wertpapiere" not in client.get("/").text

    def test_mit_stand_erscheint_die_kachel(self, client, db, bewegungen):
        from decimal import Decimal as D

        from app.models import DepotSnapshot

        db.add(
            DepotSnapshot(
                zeitpunkt=dt.datetime(2026, 7, 30, 7, 12),
                cash=D("4812.30"),
                gesamtwert=D("12430.18"),
            )
        )
        db.commit()

        text = client.get("/").text

        assert "Wertpapiere" in text
        assert "12.430,18" in text
        assert "zählt nicht zum Kontostand" in text

    def test_der_kontostand_bleibt_unberuehrt(self, client, db, bewegungen):
        from decimal import Decimal as D

        from app.models import DepotSnapshot

        db.add(
            DepotSnapshot(
                zeitpunkt=dt.datetime(2026, 7, 30, 7, 12),
                cash=D("4812.30"),
                gesamtwert=D("12430.18"),
            )
        )
        db.commit()

        # 4x1000 Startsaldo - 450 - 800 - 60, unveraendert durch das Depot.
        assert "2.690" in client.get("/").text


class TestLetzterAbgleichAufDerStartseite:
    """Direkt unter dem Kontostand soll auf einen Blick sichtbar sein, wie
    aktuell der Depot- und Kontostand von Trade Republic ist - ohne extra auf
    die Trade-Republic- oder Depot-Seite wechseln zu muessen."""

    def test_ohne_konto_kein_hinweis(self, client, bewegungen):
        assert "Letzter Abgleich" not in client.get("/").text

    def test_mit_konto_erscheint_zeitpunkt_in_lokaler_zeit(self, client, db, bewegungen):
        from app.models import TradeRepublicKonto

        db.add(
            TradeRepublicKonto(
                telefonnummer="+4915112345678",
                letzter_sync=dt.datetime(2026, 7, 31, 12, 4),
            )
        )
        db.commit()

        text = client.get("/").text

        assert "Letzter Abgleich 31.07.2026 14:04" in text

    def test_ohne_bisherigen_abgleich_kein_hinweis(self, client, db, bewegungen):
        from app.models import TradeRepublicKonto

        db.add(TradeRepublicKonto(telefonnummer="+4915112345678", letzter_sync=None))
        db.commit()

        assert "Letzter Abgleich" not in client.get("/").text


class TestKontostandHinweis:
    """Der berechnete Kontostand muss auf den Cent zum echten passen. Tut er
    das nicht, gehoert das auf die Startseite - aber als Hinweis, nicht als
    Aufgabe: eine Abweichung ist keine Buchung, die sich zuordnen liesse."""

    @staticmethod
    def _snapshot(db, cash, zeitpunkt=dt.datetime(2027, 1, 1)):
        from decimal import Decimal as D

        from app.models import DepotSnapshot

        db.query(DepotSnapshot).delete()
        db.add(DepotSnapshot(zeitpunkt=zeitpunkt, cash=D(cash), gesamtwert=D("0")))
        db.commit()

    def test_ohne_depotstand_keine_meldung(self, client, bewegungen):
        assert "Abweichung zu Trade Republic" not in client.get("/").text

    def test_uebereinstimmung_meldet_nichts(self, client, db, bewegungen):
        # 4x1000 Startsaldo - 450 - 800 - 60 = 2690
        self._snapshot(db, "2690.00")

        assert "Abweichung zu Trade Republic" not in client.get("/").text

    def test_abweichung_erscheint_unter_zu_tun(self, client, db, bewegungen):
        self._snapshot(db, "2601.96")

        text = client.get("/").text

        assert "Kontostand: 88,04 € Abweichung zu Trade Republic" in text
        assert "Startsaldo, fehlende oder doppelte Buchung" in text

    def test_veralteter_depotstand_meldet_nichts(self, client, db, bewegungen):
        """Kam nach dem Depotstand noch eine Buchung herein, vergleicht man
        zwei Zeitpunkte - die Differenz waere nur veraltet. Genau das passiert,
        wenn die Sitzung abgelaufen ist und der Datei-Import weiterlaeuft."""
        self._snapshot(db, "2601.96", zeitpunkt=dt.datetime(2020, 1, 1))

        assert "Abweichung zu Trade Republic" not in client.get("/").text


class TestTitelVorbefuellung:
    """Beim Zuweisen ist der Verwendungszweck der naheliegende Titel - er ist
    genau der Text, den man sonst abtippen wuerde. Ungetestet stand die
    Vorbefuellung nur in zwei Templates und waere bei der naechsten Aenderung
    still verschwunden."""

    def test_zuordnen_seite_schlaegt_den_verwendungszweck_vor(self, client, bewegungen):
        text = client.get("/zuordnen").text

        assert 'value="REWE"' in text

    def test_detailseite_schlaegt_den_verwendungszweck_vor(self, client, db, bewegungen):
        b = db.query(Buchung).filter(Buchung.transaction_id == "offen").one()

        text = client.get(f"/buchungen/{b.id}").text

        assert 'value="REWE"' in text

    def test_ein_vorhandener_titel_hat_vorrang(self, client, db, bewegungen):
        """Wurde die Buchung schon benannt, gewinnt der Name - sonst
        ueberschriebe der Vorschlag die eigene Wahl."""
        b = db.query(Buchung).filter(Buchung.transaction_id == "offen").one()
        b.titel = "Wocheneinkauf"
        db.commit()

        text = client.get(f"/buchungen/{b.id}").text

        assert 'value="Wocheneinkauf"' in text

    def test_ohne_verwendungszweck_bleibt_das_feld_leer(self, client, db, bewegungen):
        """Kein Ersatz aus Beschreibung oder Empfaenger: bei Buchungen aus der
        Schnittstelle waere das "Du hast 0,01 € an ... gesendet" - als Titel
        unbrauchbar und schlechter als ein leeres Feld mit Platzhalter."""
        b = db.query(Buchung).filter(Buchung.transaction_id == "offen").one()
        b.verwendungszweck = None
        b.beschreibung = "Du hast 0,01 € an Max Mustermann gesendet"
        db.commit()

        text = client.get(f"/buchungen/{b.id}").text

        assert 'value=""' in text
        assert "Du hast 0,01" not in text.split("Topf zuweisen")[1]


class TestLokaleZeit:
    """Gespeichert wird UTC, angezeigt wird lokale Zeit. Im Sommer sind das
    zwei Stunden - genug, dass ein Nutzer den letzten Abgleich fuer veraltet
    haelt oder eine Buchung dem falschen Tag zuordnet."""

    def test_filter_rechnet_um(self):
        from app.webutils import zeit_de

        # 30.07.2026 16:40 UTC ist in Berlin 18:40 (Sommerzeit).
        assert zeit_de(dt.datetime(2026, 7, 30, 16, 40)) == "30.07.2026 18:40"

    def test_winterzeit(self):
        from app.webutils import zeit_de

        assert zeit_de(dt.datetime(2026, 1, 15, 16, 40)) == "15.01.2026 17:40"

    def test_ohne_wert(self):
        from app.webutils import zeit_de

        assert zeit_de(None) == "–"

    def test_keine_seite_zeigt_noch_utc(self, client, db, bewegungen):
        """Sieben Stellen zeigten die Zeit mit dem Kuerzel "UTC" an - eine
        davon zu uebersehen faellt sonst erst im Betrieb auf."""
        from decimal import Decimal as D

        from app.models import DepotSnapshot, TradeRepublicKonto

        db.add(DepotSnapshot(zeitpunkt=dt.datetime(2026, 7, 30, 16, 40),
                             cash=D("1.00"), gesamtwert=D("2.00")))
        db.add(TradeRepublicKonto(telefonnummer="+4915112345678",
                                  letzter_sync=dt.datetime(2026, 7, 30, 16, 40)))
        db.commit()
        b = db.query(Buchung).filter(Buchung.transaction_id == "offen").one()

        for pfad in ("/", "/mehr", "/depot", "/trade-republic", f"/buchungen/{b.id}"):
            assert "UTC" not in client.get(pfad).text, pfad

    def test_die_umgerechnete_zeit_steht_wirklich_da(self, client, db, bewegungen):
        from decimal import Decimal as D

        from app.models import DepotSnapshot

        db.add(DepotSnapshot(zeitpunkt=dt.datetime(2026, 7, 30, 16, 40),
                             cash=D("1.00"), gesamtwert=D("2.00")))
        db.commit()

        assert "30.07.2026 18:40" in client.get("/depot").text
