"""B11: Buchungsliste blaettert, Zeitachse ist gekuerzt."""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.calculations import zeitachse_topf
from app.config import BUCHUNGEN_PRO_SEITE, ZEITACHSE_VERGANGENHEIT_MAX
from app.main import app as fastapi_app
from app.models import Buchung, TopfUmbuchung


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app)


def viele_buchungen(db, topf, anzahl, start=dt.date(2026, 2, 1)):
    for i in range(anzahl):
        db.add(
            Buchung(
                transaction_id=f"tx-{i:04d}",
                datum=start + dt.timedelta(days=i),
                typ="PAYMENT",
                betrag=Decimal("-10.00"),
                titel=f"Buchung {i:04d}",
                topf_id=topf.id,
                zuordnung_quelle="manuell",
                importiert_am=dt.datetime.utcnow(),
            )
        )
    db.commit()


class TestBuchungsliste:
    def test_erste_seite_ist_begrenzt(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], BUCHUNGEN_PRO_SEITE + 20)

        text = client.get("/buchungen").text

        assert f"Seite 1 von 2" in text
        assert f"{BUCHUNGEN_PRO_SEITE + 20} Einträge" in text

    def test_ohne_ueberlauf_keine_navigation(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], 5)

        assert "Seite 1 von" not in client.get("/buchungen").text

    def test_zweite_seite_zeigt_andere_eintraege(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], BUCHUNGEN_PRO_SEITE + 10)

        seite1 = client.get("/buchungen").text
        seite2 = client.get("/buchungen?seite=2").text

        # Absteigend sortiert: die aeltesten stehen auf der letzten Seite.
        assert "Buchung 0059" in seite1 and "Buchung 0059" not in seite2
        assert "Buchung 0000" in seite2 and "Buchung 0000" not in seite1

    def test_jeder_eintrag_erscheint_genau_einmal(self, db, app, client):
        """Bei gleichem Datum muss die Reihenfolge stabil sein - sonst rutscht
        ein Eintrag beim Blaettern zwischen zwei Seiten durch."""
        gleiches_datum = dt.date(2026, 7, 1)
        for i in range(BUCHUNGEN_PRO_SEITE + 10):
            db.add(
                Buchung(
                    transaction_id=f"tx-{i:04d}",
                    datum=gleiches_datum,
                    typ="PAYMENT",
                    betrag=Decimal("-10.00"),
                    titel=f"Buchung {i:04d}",
                    topf_id=app["Urlaub"].id,
                    importiert_am=dt.datetime.utcnow(),
                )
            )
        db.commit()

        gesehen = []
        for seite in (1, 2):
            text = client.get(f"/buchungen?seite={seite}").text
            gesehen += [f"Buchung {i:04d}" for i in range(60) if f"Buchung {i:04d}" in text]

        assert sorted(gesehen) == sorted(set(gesehen))
        assert len(gesehen) == BUCHUNGEN_PRO_SEITE + 10

    def test_topf_filter_bleibt_beim_blaettern_erhalten(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], BUCHUNGEN_PRO_SEITE + 5)

        text = client.get(f"/buchungen?topf={app['Urlaub'].id}").text

        assert f"topf={app['Urlaub'].id}&amp;seite=2" in text

    @pytest.mark.parametrize("seite", ["0", "-3", "999"])
    def test_unsinnige_seitenzahl_landet_im_gueltigen_bereich(self, client, db, app, seite):
        viele_buchungen(db, app["Urlaub"], BUCHUNGEN_PRO_SEITE + 5)

        assert client.get(f"/buchungen?seite={seite}").status_code == 200

    def test_topf_umbuchungen_zaehlen_mit(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], BUCHUNGEN_PRO_SEITE)
        db.add(
            TopfUmbuchung(
                von_topf_id=app["Urlaub"].id,
                nach_topf_id=app["Sonderausgaben"].id,
                betrag=Decimal("50.00"),
                datum=dt.date(2026, 7, 20),
            )
        )
        db.commit()

        assert f"{BUCHUNGEN_PRO_SEITE + 1} Einträge" in client.get("/buchungen").text


class TestZeitachse:
    def test_vergangenheit_wird_gekuerzt(self, db, app):
        viele_buchungen(db, app["Urlaub"], ZEITACHSE_VERGANGENHEIT_MAX + 10)

        achse = zeitachse_topf(db, app["Urlaub"])

        assert len(achse["vergangenheit"]) == ZEITACHSE_VERGANGENHEIT_MAX
        assert achse["vergangenheit_gesamt"] == ZEITACHSE_VERGANGENHEIT_MAX + 10
        assert achse["vergangenheit_gekuerzt"] is True

    def test_kurze_liste_bleibt_vollstaendig(self, db, app):
        viele_buchungen(db, app["Urlaub"], 3)

        achse = zeitachse_topf(db, app["Urlaub"])

        assert len(achse["vergangenheit"]) == 3
        assert achse["vergangenheit_gekuerzt"] is False

    def test_juengste_eintraege_bleiben_stehen(self, db, app):
        viele_buchungen(db, app["Urlaub"], ZEITACHSE_VERGANGENHEIT_MAX + 10)

        achse = zeitachse_topf(db, app["Urlaub"])

        daten = [e.datum for e in achse["vergangenheit"]]
        assert daten == sorted(daten, reverse=True)
        assert daten[0] == dt.date(2026, 2, 1) + dt.timedelta(
            days=ZEITACHSE_VERGANGENHEIT_MAX + 9
        )

    def test_forecast_seite_verweist_auf_die_vollstaendige_liste(self, client, db, app):
        viele_buchungen(db, app["Urlaub"], ZEITACHSE_VERGANGENHEIT_MAX + 10)

        text = client.get(f"/forecast?topf={app['Urlaub'].id}").text

        assert f"Alle {ZEITACHSE_VERGANGENHEIT_MAX + 10} Buchungen dieses Topfs" in text
