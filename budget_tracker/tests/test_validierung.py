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


class TestBefristet:
    """B8: 'befristet' heisst 'monatlich mit Enddatum' - ohne Enddatum war es
    von 'monatlich' nicht zu unterscheiden und lief entgegen dem Namen weiter."""

    def test_ohne_enddatum_abgelehnt(self, db, app):
        with pytest.raises(ValueError, match="Enddatum erforderlich"):
            regel_erstellen(db, **regel_daten(app["Urlaub"], rhythmus="befristet"))

    def test_mit_enddatum_erlaubt(self, db, app):
        regel = regel_erstellen(
            db,
            **regel_daten(
                app["Urlaub"], rhythmus="befristet", end_datum=dt.date(2026, 12, 31)
            ),
        )
        db.commit()

        assert regel.end_datum == dt.date(2026, 12, 31)

    def test_enddatum_vor_startdatum_abgelehnt(self, db, app):
        with pytest.raises(ValueError, match="nicht vor dem Startdatum"):
            regel_erstellen(
                db, **regel_daten(app["Urlaub"], end_datum=START_DATUM - dt.timedelta(days=1))
            )

    def test_monatlich_bleibt_ohne_enddatum_erlaubt(self, db, app):
        regel = regel_erstellen(db, **regel_daten(app["Urlaub"], rhythmus="monatlich"))
        db.commit()

        assert regel.end_datum is None


class TestJahresregelAnkerWarnung:
    """Bei jaehrlichen Regeln stammt der Monat aus start_datum, nur der Tag aus
    anker_tag - passt das nicht zusammen, greift die Regel erst ein Jahr spaeter."""

    def _regel(self, db, topf, anker_tag, start_datum):
        return regel_erstellen(
            db,
            **regel_daten(
                topf, rhythmus="jaehrlich", anker_tag=anker_tag, start_datum=start_datum
            ),
        )

    def test_warnt_wenn_die_erste_faelligkeit_ein_jahr_springt(self, db, app):
        from app.forecast_engine import jahresregel_anker_warnung

        regel = self._regel(db, app["Urlaub"], anker_tag=1, start_datum=dt.date(2026, 9, 26))
        db.commit()

        warnung = jahresregel_anker_warnung(regel)
        assert warnung is not None
        assert "01.09.2027" in warnung

    def test_schweigt_bei_passender_kombination(self, db, app):
        from app.forecast_engine import jahresregel_anker_warnung

        regel = self._regel(db, app["Urlaub"], anker_tag=26, start_datum=dt.date(2026, 9, 26))
        db.commit()

        assert jahresregel_anker_warnung(regel) is None

    def test_schweigt_bei_monatlichen_regeln(self, db, app):
        from app.forecast_engine import jahresregel_anker_warnung

        regel = regel_erstellen(db, **regel_daten(app["Urlaub"], anker_tag=1))
        db.commit()

        assert jahresregel_anker_warnung(regel) is None

    def test_warnung_steht_auf_der_regeln_seite(self, db, app):
        regel = self._regel(db, app["Urlaub"], anker_tag=1, start_datum=dt.date(2026, 9, 26))
        db.commit()

        text = TestClient(fastapi_app).get(f"/forecast/regeln?topf={regel.topf_id}").text

        assert "liegt im Startmonat vor dem Startdatum" in text
