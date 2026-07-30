"""Die Seiten "Gesamtvermoegen" und "DKB" sowie die Kachel auf der Startseite.

Ohne Netz: die GoCardless-Aufrufe werden ersetzt. Geprueft wird, was die Seiten
in ihren Zustaenden zeigen und dass der Einrichtungs-Weg (Bank waehlen,
Freigabe starten, Freigabe abschliessen) am Ende ein verbundenes Konto ergibt.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import gocardless
from app.main import app as fastapi_app
from app.models import Externkonto, ExternkontoSaldo


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app, follow_redirects=False)


@pytest.fixture
def zugangsdaten(monkeypatch):
    monkeypatch.setenv("GOCARDLESS_SECRET_ID", "test-id")
    monkeypatch.setenv("GOCARDLESS_SECRET_KEY", "test-key")


@pytest.fixture
def konto(db, app):
    eintrag = Externkonto(
        bezeichnung="DKB Gehaltskonto",
        gocardless_institution_id="DKB_BYLADEM1001",
        gocardless_requisition_id="req-1",
        gocardless_account_id="kto-1",
        consent_gueltig_bis=dt.date.today() + dt.timedelta(days=80),
    )
    db.add(eintrag)
    db.add(
        ExternkontoSaldo(
            externkonto_id=1, betrag=Decimal("2480.55"), abgerufen_am=dt.datetime.utcnow()
        )
    )
    db.commit()
    return eintrag


class TestKontostandSeite:
    def test_zeigt_den_gespeicherten_stand(self, client, db, konto, monkeypatch):
        monkeypatch.setattr(gocardless, "saldo", lambda *a: pytest.fail("Cache greift nicht"))

        text = client.get("/dkb").text

        assert "2.480,55" in text
        assert "verbunden" in text

    def test_nichts_wird_verrechnet(self, client, db, app, konto, monkeypatch):
        """Weder die Toepfe-Summe noch ein Gesamtwert stehen auf der Seite -
        es ist Geld auf einem anderen Konto."""
        for topf in app.values():
            topf.startsaldo = Decimal("1000.00")
        db.commit()
        monkeypatch.setattr(gocardless, "saldo", lambda *a: pytest.fail("Cache greift nicht"))

        text = client.get("/dkb").text

        assert "6.480" not in text
        assert "4.000,00" not in text

    def test_der_stand_steht_in_lokaler_zeit(self, client, db, konto, monkeypatch):
        """Gespeichert wird UTC, angezeigt die Zeit, die die eigene Uhr zeigt -
        sonst haelt man einen frischen Stand fuer zwei Stunden alt."""
        monkeypatch.setenv("EXTERNKONTO_CACHE_SECONDS", "999999999")
        db.query(ExternkontoSaldo).one().abgerufen_am = dt.datetime(2026, 7, 30, 16, 40)
        db.commit()

        for pfad in ("/dkb", "/"):
            text = client.get(pfad).text

            assert "30.07.2026 18:40" in text, pfad
            assert "UTC" not in text, pfad

    def test_veralteter_stand_wird_beim_aufruf_geholt(self, client, db, konto, monkeypatch):
        db.query(ExternkontoSaldo).one().abgerufen_am = dt.datetime.utcnow() - dt.timedelta(
            hours=9
        )
        db.commit()
        monkeypatch.setattr(gocardless, "saldo", lambda *a: Decimal("3000.00"))

        text = client.get("/dkb").text

        assert "3.000,00" in text

    def test_gescheiterter_abruf_zeigt_grund_und_alten_stand(self, client, db, konto, monkeypatch):
        db.query(ExternkontoSaldo).one().abgerufen_am = dt.datetime.utcnow() - dt.timedelta(
            hours=9
        )
        db.commit()

        def scheitert(*args):
            raise gocardless.GoCardlessFehler("Kontingent für heute erschöpft")

        monkeypatch.setattr(gocardless, "saldo", scheitert)

        text = client.get("/dkb").text

        assert "Kontingent für heute erschöpft" in text
        assert "2.480,55" in text


class TestStartseite:
    def test_ohne_konto_keine_kachel(self, client, app):
        assert "DKB" not in client.get("/").text

    def test_mit_konto_erscheint_die_kachel_unter_dem_depot(self, client, db, app, konto):
        from app.models import DepotSnapshot

        for topf in app.values():
            topf.startsaldo = Decimal("1000.00")
        db.add(
            DepotSnapshot(
                zeitpunkt=dt.datetime(2026, 7, 30, 7, 12),
                cash=Decimal("4000.00"),
                gesamtwert=Decimal("28096.48"),
            )
        )
        db.commit()

        text = client.get("/").text

        assert "DKB Gehaltskonto" in text
        assert "2.480,55" in text
        assert "zählt nicht zum Cashkonto und in keinen Topf" in text
        # Eigener Abschnitt unterhalb des Depots, wie bei den Wertpapieren.
        assert text.index(">Depot<") < text.index(">DKB<")

    def test_es_wird_nichts_summiert(self, client, db, app, konto):
        """Der DKB-Saldo steht separat - nicht mit den Toepfen verrechnet."""
        for topf in app.values():
            topf.startsaldo = Decimal("1000.00")
        db.commit()

        text = client.get("/").text

        assert "6.480" not in text
        assert "Zusammen" not in text

    def test_die_kachel_ruft_nie_selbst_ab(self, client, db, konto, monkeypatch):
        """Die Startseite wird staendig geoeffnet - ein Abruf je Aufruf
        brauchte das taegliche Kontingent auf."""
        db.query(ExternkontoSaldo).one().abgerufen_am = dt.datetime.utcnow() - dt.timedelta(
            days=3
        )
        db.commit()
        monkeypatch.setattr(gocardless, "saldo", lambda *a: pytest.fail("darf nicht abrufen"))

        assert client.get("/").status_code == 200

    def test_kontostand_und_toepfe_bleiben_unberuehrt(self, client, db, app, konto):
        for topf in app.values():
            topf.startsaldo = Decimal("1000.00")
        db.commit()

        text = client.get("/").text

        # Kontostand Cashkonto: 4x1000, unveraendert durch die DKB-Anbindung.
        assert "4.000" in text

    def test_ablauf_erscheint_unter_zu_tun(self, client, db, konto):
        konto.consent_gueltig_bis = dt.date.today() + dt.timedelta(days=3)
        db.commit()

        text = client.get("/").text

        assert "Zugriff läuft in 3 Tagen ab" in text
        assert "90 Tagen ab" in text


class TestEinrichtung:
    def test_ohne_zugangsdaten_erklaert_die_seite_was_fehlt(self, client, monkeypatch):
        monkeypatch.delenv("GOCARDLESS_SECRET_ID", raising=False)
        monkeypatch.delenv("GOCARDLESS_SECRET_KEY", raising=False)

        text = client.get("/dkb").text

        assert "gocardless_secret_id" in text
        assert "nie in der Datenbank" in text

    def test_banken_laden_und_bank_uebernehmen(self, client, db, zugangsdaten, monkeypatch):
        monkeypatch.setattr(
            gocardless,
            "institutionen",
            lambda land="de": [{"id": "DKB_BYLADEM1001", "name": "DKB", "bic": "", "logo": ""}],
        )

        assert client.post("/dkb/banken").status_code == 303
        assert "DKB_BYLADEM1001" in client.get("/dkb").text

        antwort = client.post(
            "/dkb/institut",
            data={"institution_id": "DKB_BYLADEM1001", "bezeichnung": "DKB Gehaltskonto"},
        )

        assert antwort.status_code == 303
        konto = db.query(Externkonto).one()
        assert konto.gocardless_institution_id == "DKB_BYLADEM1001"
        assert konto.bezeichnung == "DKB Gehaltskonto"

    def test_bank_ohne_auswahl_wird_abgelehnt(self, client, zugangsdaten):
        antwort = client.post("/dkb/institut", data={"institution_id": ""})

        assert antwort.status_code == 400
        assert "Bank auswählen" in antwort.text

    def test_freigabe_zeigt_den_link_statt_umzuleiten(self, client, db, zugangsdaten, monkeypatch):
        """Variante C: es gibt keine Rueckleitung - der Link wird von Hand
        geoeffnet, den Rest erledigt die Statusabfrage."""
        db.add(Externkonto(bezeichnung="DKB", gocardless_institution_id="DKB_BYLADEM1001"))
        db.commit()
        monkeypatch.setattr(
            gocardless,
            "freigabe_starten",
            lambda institution, referenz: {
                "requisition_id": "req-9",
                "link": "https://ob.gocardless.com/psd2/start/xyz",
                "agreement_id": "ag-9",
            },
        )

        text = client.post("/dkb/freigabe").text

        assert "https://ob.gocardless.com/psd2/start/xyz" in text
        db.expire_all()
        assert db.query(Externkonto).one().gocardless_requisition_id == "req-9"

    def test_abgeschlossene_freigabe_wird_beim_aufruf_uebernommen(
        self, client, db, zugangsdaten, monkeypatch
    ):
        db.add(
            Externkonto(
                bezeichnung="DKB",
                gocardless_institution_id="DKB_BYLADEM1001",
                gocardless_requisition_id="req-9",
            )
        )
        db.commit()
        monkeypatch.setattr(
            gocardless,
            "freigabe_status",
            lambda req: {
                "zustand": "LN",
                "konten": ["kto-7"],
                "verknuepft": True,
                "abgelaufen": False,
                "abgelehnt": False,
                "link": "",
                "agreement_id": "ag-9",
            },
        )
        monkeypatch.setattr(
            gocardless, "freigabe_gueltig_bis", lambda ag: dt.date(2026, 10, 28)
        )

        text = client.get("/dkb").text

        assert "verbunden" in text
        db.expire_all()
        konto = db.query(Externkonto).one()
        assert konto.gocardless_account_id == "kto-7"
        assert konto.consent_gueltig_bis == dt.date(2026, 10, 28)

    def test_mehrere_konten_werden_zur_auswahl_gestellt(
        self, client, db, zugangsdaten, monkeypatch
    ):
        """Sonst stuende womoeglich ein Kreditkartenkonto als "Gehaltskonto"
        auf der Startseite."""
        db.add(
            Externkonto(
                bezeichnung="DKB",
                gocardless_institution_id="DKB_BYLADEM1001",
                gocardless_requisition_id="req-9",
            )
        )
        db.commit()
        monkeypatch.setattr(
            gocardless,
            "freigabe_status",
            lambda req: {
                "zustand": "LN",
                "konten": ["kto-giro", "kto-visa"],
                "verknuepft": True,
                "abgelaufen": False,
                "abgelehnt": False,
                "link": "",
                "agreement_id": "ag-9",
            },
        )
        monkeypatch.setattr(
            gocardless,
            "konto_kennzeichen",
            lambda kennung: "DE02120300000000202051" if kennung == "kto-giro" else "",
        )

        text = client.get("/dkb").text

        assert "Welches Konto?" in text
        assert "DE02120300000000202051" in text
        db.expire_all()
        assert db.query(Externkonto).one().gocardless_account_id is None

        monkeypatch.setattr(
            gocardless, "freigabe_gueltig_bis", lambda ag: dt.date(2026, 10, 28)
        )
        antwort = client.post("/dkb/konto", data={"account_id": "kto-giro"})

        assert antwort.status_code == 303
        db.expire_all()
        assert db.query(Externkonto).one().gocardless_account_id == "kto-giro"

    def test_abgelehnte_freigabe_meldet_sich(self, client, db, zugangsdaten, monkeypatch):
        db.add(
            Externkonto(
                bezeichnung="DKB",
                gocardless_institution_id="DKB",
                gocardless_requisition_id="req-9",
            )
        )
        db.commit()
        monkeypatch.setattr(
            gocardless,
            "freigabe_status",
            lambda req: {
                "zustand": "RJ",
                "konten": [],
                "verknuepft": False,
                "abgelaufen": False,
                "abgelehnt": True,
                "link": "",
                "agreement_id": None,
            },
        )

        assert "abgelehnt oder ist abgelaufen" in client.get("/dkb").text

    def test_verbindung_loesen_behaelt_die_salden(self, client, db, konto):
        antwort = client.post("/dkb/loesen")

        assert antwort.status_code == 303
        db.expire_all()
        gelöst = db.query(Externkonto).one()
        assert gelöst.gocardless_account_id is None
        assert gelöst.consent_gueltig_bis is None
        # Abgerufene Salden sind Fakten, keine Zugangsdaten.
        assert db.query(ExternkontoSaldo).count() == 1

    def test_jetzt_aktualisieren_holt_sofort(self, client, db, konto, monkeypatch):
        monkeypatch.setattr(gocardless, "saldo", lambda *a: Decimal("77.00"))

        antwort = client.post("/dkb/aktualisieren")

        assert antwort.status_code == 303
        assert antwort.headers["location"].endswith("/dkb")
        db.expire_all()
        assert db.query(ExternkontoSaldo).count() == 2

    def test_gescheitertes_aktualisieren_nennt_den_grund(self, client, db, konto, monkeypatch):
        """Nach einer Weiterleitung waere der Grund verloren und der Knopf
        schiene wirkungslos."""

        def scheitert(*args):
            raise gocardless.GoCardlessFehler("Kontingent für heute erschöpft")

        monkeypatch.setattr(gocardless, "saldo", scheitert)

        antwort = client.post("/dkb/aktualisieren")

        assert antwort.status_code == 200
        assert "Kontingent für heute erschöpft" in antwort.text
