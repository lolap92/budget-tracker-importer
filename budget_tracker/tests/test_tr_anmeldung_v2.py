"""Der aktuelle Anmeldeweg: Bestaetigung in der Trade-Republic-App.

Trade Republic hat die Web-Anmeldung umgestellt. Statt eines vierstelligen
Codes kommt eine Anfrage in die App, die dort angenommen wird; die Seite fragt
so lange nach. pytr 0.4.9 kennt nur den alten Weg - deshalb steht der neue hier.

Alles ohne Netz: die Attrappe beantwortet die beiden Anfragen des Ablaufs.
"""
import base64
import json

import pytest

from app import tr_client
from app.tr_client import (
    VERFAHREN_V2,
    AnmeldungFehlgeschlagen,
    _Anmeldevorgang,
    _geraete_info,
    _kopfzeilen_v2,
    _V2NichtVerfuegbar,
    _v2_starten,
    bestaetigung_pruefen,
)


class Antwort:
    def __init__(self, status_code, daten=None, text=""):
        self.status_code = status_code
        self._daten = daten
        self.text = text

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class Keks:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class Sitzung:
    def __init__(self, antwort, kekse=()):
        self.antwort = antwort
        self.cookies = list(kekse)
        self.gesendet = []

    def post(self, url, **kwargs):
        self.gesendet.append(("POST", url, kwargs))
        return self.antwort

    def get(self, url, **kwargs):
        self.gesendet.append(("GET", url, kwargs))
        return self.antwort


class Api:
    _host = "https://api.traderepublic.com"

    def __init__(self, antwort, kekse=()):
        self._websession = Sitzung(antwort, kekse)
        self.gesichert = False

    def save_websession(self):
        self.gesichert = True


@pytest.fixture
def ohne_laufende_anmeldung(monkeypatch):
    monkeypatch.setattr(tr_client, "_anmeldung", None)


def vorgang_setzen(monkeypatch, api, process_id="p-1"):
    vorgang = _Anmeldevorgang(
        api=api, geraete_id="abc", token="waf", verfahren=VERFAHREN_V2, process_id=process_id
    )
    monkeypatch.setattr(tr_client, "_anmeldung", vorgang)
    return vorgang


class TestKopfzeilen:
    def test_geraeteangaben_sind_lesbares_json(self):
        angaben = json.loads(base64.b64decode(_geraete_info("kennung-1")))

        assert angaben["stableDeviceId"] == "kennung-1"
        assert angaben["timezone"] == "Europe/Berlin"

    def test_die_angaben_der_weboberflaeche(self):
        kopf = _kopfzeilen_v2("waf-token", "kennung-1")

        assert kopf["x-tr-platform"] == "web"
        assert kopf["x-tr-app-version"]
        assert kopf["X-aws-waf-token"] == "waf-token"
        # Die Herkunftsangaben muessen auch hier mit - ohne sie greift der
        # Bot-Schutz ein.
        assert kopf["Origin"] == "https://app.traderepublic.com"
        assert kopf["Sec-Fetch-Site"] == "same-site"

    def test_ohne_token_keine_leere_kopfzeile(self):
        assert "X-aws-waf-token" not in _kopfzeilen_v2(None, "kennung-1")


class TestAnmeldungStarten:
    def test_erfolgreicher_start_merkt_die_vorgangsnummer(self, monkeypatch):
        api = Api(Antwort(200, {"processId": "vorgang-7", "countdownInSeconds": 60}))
        vorgang = vorgang_setzen(monkeypatch, api, process_id="")

        countdown = _v2_starten(api, "+4915112345678", "1234", "waf", "abc")

        assert countdown == 60
        assert vorgang.process_id == "vorgang-7"
        methode, url, kwargs = api._websession.gesendet[0]
        assert methode == "POST"
        assert url.endswith("/api/v2/auth/web/login")
        assert kwargs["json"] == {"phoneNumber": "+4915112345678", "pin": "1234"}

    @pytest.mark.parametrize("status", [400, 401])
    def test_abgelehnte_zugangsdaten_fuehren_nicht_zum_zweiten_versuch(
        self, monkeypatch, status
    ):
        """Ein zweiter Versuch mit derselben falschen PIN braechte nur die
        Kontosperre naeher - hier wird abgebrochen statt auf den alten Weg
        auszuweichen."""
        api = Api(Antwort(status))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(AnmeldungFehlgeschlagen, match="PIN"):
            _v2_starten(api, "+4915112345678", "0000", "waf", "abc")

    def test_zu_viele_versuche(self, monkeypatch):
        api = Api(Antwort(429))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(AnmeldungFehlgeschlagen, match="Geduld"):
            _v2_starten(api, "+4915112345678", "1234", "waf", "abc")

    @pytest.mark.parametrize("status", [404, 405, 500])
    def test_anderer_fehlschlag_laesst_den_alten_weg_zu(self, monkeypatch, status):
        api = Api(Antwort(status))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(_V2NichtVerfuegbar):
            _v2_starten(api, "+4915112345678", "1234", "waf", "abc")

    def test_antwort_ohne_vorgangsnummer(self, monkeypatch):
        api = Api(Antwort(200, {}))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(_V2NichtVerfuegbar):
            _v2_starten(api, "+4915112345678", "1234", "waf", "abc")


class TestBestaetigung:
    def test_noch_nicht_bestaetigt(self, monkeypatch):
        api = Api(Antwort(200, {"state": "PENDING"}))
        vorgang_setzen(monkeypatch, api)

        assert bestaetigung_pruefen() is False
        assert api.gesichert is False

    def test_bestaetigt_sichert_die_sitzung(self, monkeypatch):
        api = Api(Antwort(200, {"state": "APPROVED"}))
        vorgang_setzen(monkeypatch, api)

        assert bestaetigung_pruefen() is True
        assert api.gesichert is True
        # Der Vorgang ist beendet - die PIN-behaftete Instanz wird losgelassen.
        assert tr_client.anmeldeverfahren() == ""

    def test_sitzungscookie_genuegt_auch_ohne_zustand(self, monkeypatch):
        """Manche Antworten nennen keinen Zustand, setzen aber schon das
        Sitzungs-Cookie."""
        api = Api(Antwort(200, {}), kekse=[Keks("tr_session", "xyz")])
        vorgang_setzen(monkeypatch, api)

        assert bestaetigung_pruefen() is True
        assert api.gesichert is True

    def test_in_der_app_abgelehnt(self, monkeypatch):
        api = Api(Antwort(200, {"state": "REJECTED"}))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(AnmeldungFehlgeschlagen, match="abgelehnt"):
            bestaetigung_pruefen()
        assert tr_client.anmeldeverfahren() == ""

    @pytest.mark.parametrize("status", [401, 403, 404, 410])
    def test_abgelaufener_vorgang(self, monkeypatch, status):
        api = Api(Antwort(status))
        vorgang_setzen(monkeypatch, api)

        with pytest.raises(AnmeldungFehlgeschlagen, match="abgelaufen"):
            bestaetigung_pruefen()

    def test_ohne_laufende_anmeldung_passiert_nichts(self, ohne_laufende_anmeldung):
        assert bestaetigung_pruefen() is False
