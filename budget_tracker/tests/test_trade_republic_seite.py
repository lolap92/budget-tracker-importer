"""Die Trade-Republic-Seite und die Entscheidung ueber Verdachtsfaelle.

Ohne Anmeldung und ohne Netz: geprueft wird, was die Seite in ihren Zustaenden
zeigt und dass eine Entscheidung genau eine der beiden Wirkungen hat.
"""
import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.import_core import QUELLE_API, QUELLE_CSV, ImportKontext, uebernehmen
from app.main import app as fastapi_app
from app.models import Buchung, ImportVerdacht, TradeRepublicKonto


@pytest.fixture
def client(db, app):
    return TestClient(fastapi_app, follow_redirects=False)


@pytest.fixture
def verdacht(db, app):
    """Eine per CSV bekannte Buchung und dieselbe Bewegung als Verdachtsfall."""
    uebernehmen(
        db,
        ImportKontext.laden(db),
        transaction_id="csv-id",
        datum=dt.date(2026, 6, 29),
        betrag=Decimal("550.00"),
        typ="TRANSFER_INBOUND",
        quelle=QUELLE_CSV,
    )
    db.commit()
    fall = ImportVerdacht(
        transaction_id="api-id",
        datum=dt.date(2026, 6, 29),
        typ="TRANSFER_INBOUND",
        betrag=Decimal("550.00"),
        verwendungszweck="Haus Renovierung Anteil",
        empfaenger_name="Klaus Mustermann",
        quelle=QUELLE_API,
        vermutete_dopplung_id=db.query(Buchung).one().id,
    )
    db.add(fall)
    db.commit()
    return fall


class TestSeite:
    def test_ohne_anmeldung_erscheint_das_anmeldeformular(self, client):
        text = client.get("/trade-republic").text

        assert "Telefonnummer" in text
        assert "nicht angemeldet" in text
        assert "nirgends gespeichert" in text

    def test_verdachtsfaelle_werden_gezeigt(self, client, verdacht):
        text = client.get("/trade-republic").text

        assert "Zur Entscheidung (1)" in text
        assert "Haus Renovierung Anteil" in text
        assert "550,00" in text

    def test_uebersicht_meldet_offene_faelle(self, client, verdacht):
        assert "1 Bewegung zu klären" in client.get("/").text

    def test_uebersicht_meldet_abgelaufene_sitzung(self, client, db, app):
        db.add(TradeRepublicKonto(telefonnummer="+4915112345678"))
        db.commit()

        assert "Anmeldung erforderlich" in client.get("/").text

    def test_ohne_konto_keine_meldung(self, client, db, app):
        assert "Trade Republic:" not in client.get("/").text

    def test_hinweis_ist_nur_noch_das_icon_oben(self, client, db, app):
        """Ersetzt die fruehere Zeile im "Zu tun"-Bereich: ein Icon oben
        rechts fuehrt direkt zur selben Seite, ohne den Hinweis zusaetzlich
        weiter unten zu wiederholen."""
        db.add(TradeRepublicKonto(telefonnummer="+4915112345678"))
        db.commit()

        text = client.get("/").text

        assert 'class="icon-btn accent"' in text
        assert 'href="/trade-republic"' in text
        assert "ansehen" not in text

    def test_icon_fehlt_ohne_hinweis(self, client, db, app):
        assert 'href="/trade-republic" aria-label' not in client.get("/").text

    def test_uebersicht_nennt_den_grund_des_fehlgeschlagenen_abgleichs(
        self, client, db, app, monkeypatch
    ):
        """Die abgelaufene Sitzung ist der mit Abstand haeufigste Grund - ein
        pauschales "fehlgeschlagen" liesse sie wie einen echten Fehler
        aussehen, den es zu untersuchen gilt."""
        from app import tr_client, tr_sync

        db.add(TradeRepublicKonto(telefonnummer="+4915112345678"))
        db.commit()
        monkeypatch.setattr(tr_client, "sitzung_vorhanden", lambda: True)
        monkeypatch.setattr(
            tr_sync,
            "status",
            lambda: {
                "erfolgreich": False,
                "meldung": "Die Sitzung ist abgelaufen - bitte neu anmelden.",
            },
        )

        text = client.get("/").text

        assert "Trade Republic: Die Sitzung ist abgelaufen - bitte neu anmelden." in text


class TestAnmeldung:
    def test_unvollstaendige_eingabe_wird_abgelehnt(self, client):
        antwort = client.post(
            "/trade-republic/anmelden", data={"telefonnummer": "0151", "pin": ""}
        )

        assert antwort.status_code == 400
        assert "werden benötigt" in antwort.text

    def test_eingetippte_nummer_bleibt_im_formular(self, client):
        """Sie noch einmal zu tippen ist die haerteste Art, einen Tippfehler zu
        wiederholen."""
        antwort = client.post(
            "/trade-republic/anmelden", data={"telefonnummer": "0151 1234", "pin": ""}
        )

        assert 'value="0151 1234"' in antwort.text

    def test_ohne_pytr_kein_serverfehler(self, client, monkeypatch):
        """Fehlt die Bibliothek, muss eine Meldung erscheinen - kein 500er."""
        monkeypatch.setattr("app.tr_client.pytr_verfuegbar", lambda: False)

        antwort = client.post(
            "/trade-republic/anmelden",
            data={"telefonnummer": "015112345678", "pin": "1234"},
        )

        assert antwort.status_code == 400
        assert "pytr" in antwort.text

    def test_code_ohne_laufende_anmeldung(self, client):
        antwort = client.post("/trade-republic/code", data={"code": "1234"})

        assert antwort.status_code == 400
        assert "erneut mit Telefonnummer und PIN" in antwort.text

    def test_schutz_token_feld_ist_normalerweise_nicht_da(self, client):
        """Der automatische Weg klappt praktisch immer - das Feld waere sonst
        taeglich sichtbarer Ballast fuer etwas, das so gut wie nie gebraucht wird."""
        assert "Schutz-Token" not in client.get("/trade-republic").text

    def test_schutz_token_feld_erscheint_erst_nach_bot_schutz_fehler(self, client, monkeypatch):
        def _starten(telefonnummer, pin, waf_token):
            from app import tr_client

            raise tr_client.AnmeldungFehlgeschlagen(
                "Trade Republic hat die Anfrage abgewiesen (Bot-Schutz)."
            )

        # pytr muss fuer diesen Test nicht wirklich installiert sein - nur die
        # Pruefung davor darf den eigentlichen Anmeldeversuch nicht blockieren.
        monkeypatch.setattr("app.tr_client.pytr_verfuegbar", lambda: True)
        monkeypatch.setattr("app.tr_client.anmeldung_starten", _starten)

        antwort = client.post(
            "/trade-republic/anmelden",
            data={"telefonnummer": "015112345678", "pin": "1234"},
        )

        assert "Schutz-Token" in antwort.text

    def test_klick_auf_todo_zeile_fuehrt_direkt_zur_pin_eingabe(self, client, db, app, monkeypatch):
        """Der haeufigste Fall: die Cookie-Datei liegt noch da, Trade Republic
        hat die Sitzung aber schon abgelehnt. Ein Klick von der Startseite
        soll direkt das Anmeldeformular zeigen, nicht "angemeldet"."""
        from app import tr_client, tr_sync

        db.add(TradeRepublicKonto(telefonnummer="+4915112345678"))
        db.commit()
        monkeypatch.setattr(tr_client, "sitzung_vorhanden", lambda: True)
        monkeypatch.setitem(tr_sync._letzter_lauf, "sitzung_verloren", True)

        text = client.get("/trade-republic").text

        assert "PIN" in text
        assert "Jetzt abgleichen" not in text
        assert 'value="+4915112345678"' in text


class TestEntscheidung:
    def test_zusammenfuehren_legt_keine_zweite_buchung_an(self, client, db, verdacht):
        antwort = client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "zusammenfuehren"}
        )

        assert antwort.status_code == 303
        assert db.query(Buchung).count() == 1
        # Die Route arbeitet in einer eigenen Sitzung - erst nach expire_all
        # sieht die Test-Sitzung deren Aenderungen.
        db.expire_all()
        assert db.query(ImportVerdacht).one().entscheidung == "zusammenfuehren"

    def test_uebernehmen_legt_die_zweite_buchung_an(self, client, db, verdacht):
        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "uebernehmen"}
        )

        assert db.query(Buchung).count() == 2
        neue = db.query(Buchung).filter(Buchung.transaction_id == "api-id").one()
        assert neue.betrag == Decimal("550.00")
        assert neue.quelle == "api"
        # Der Verwendungszweck traegt die automatische Topf-Zuordnung.
        assert neue.topf.name == "Haus Renovierung"

    def test_ein_fall_wird_nur_einmal_entschieden(self, client, db, verdacht):
        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "zusammenfuehren"}
        )
        antwort = client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "uebernehmen"}
        )

        assert antwort.status_code == 404
        assert db.query(Buchung).count() == 1


class TestZusammenfuehren:
    """Zusammenfuehren heisst: keine zweite Buchung, aber die Angaben der
    Schnittstelle retten - vor allem den Verwendungszweck, den nur sie kennt."""

    def test_verwendungszweck_wandert_in_die_bestehende_buchung(self, client, db, verdacht):
        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "zusammenfuehren"}
        )

        db.expire_all()
        buchung = db.query(Buchung).one()
        assert buchung.verwendungszweck == "Haus Renovierung Anteil"
        assert buchung.empfaenger_name == "Klaus Mustermann"

    def test_vorhandene_angaben_werden_nicht_ueberschrieben(self, client, db, verdacht):
        buchung = db.query(Buchung).one()
        buchung.verwendungszweck = "vom Nutzer gepflegt"
        db.commit()

        client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "zusammenfuehren"}
        )

        db.expire_all()
        assert db.query(Buchung).one().verwendungszweck == "vom Nutzer gepflegt"

    def test_alte_beschriftung_wird_weiter_angenommen(self, client, db, verdacht):
        """Eine Seite, die noch vor der Umbenennung geladen wurde, soll nicht
        mit einem Fehler enden."""
        antwort = client.post(
            f"/trade-republic/verdacht/{verdacht.id}", data={"entscheidung": "verwerfen"}
        )

        assert antwort.status_code == 303
        db.expire_all()
        assert db.query(Buchung).count() == 1
        assert db.query(Buchung).one().verwendungszweck == "Haus Renovierung Anteil"
