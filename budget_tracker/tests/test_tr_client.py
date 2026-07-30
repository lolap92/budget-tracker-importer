"""Anmeldung: Eingabe-Normalisierung und Fehlerdeutung (app/tr_client.py).

Ohne Netz und ohne pytr: geprueft wird, was die App aus einer Eingabe macht
und was sie aus einer Fehlerantwort liest.
"""
import pytest

from app.tr_client import _anmeldefehler, telefonnummer_normalisieren


class Antwort:
    def __init__(self, status_code):
        self.status_code = status_code


class HttpFehler(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = Antwort(status_code)


class TestTelefonnummer:
    @pytest.mark.parametrize(
        "eingabe,erwartet",
        [
            ("+4915112345678", "+4915112345678"),
            ("+49 151 1234 5678", "+4915112345678"),
            ("+49-151-12345678", "+4915112345678"),
            ("015112345678", "+4915112345678"),
            ("0049 151 12345678", "+4915112345678"),
            ("(0151) 12345678", "+4915112345678"),
            ("  +4915112345678  ", "+4915112345678"),
        ],
    )
    def test_schreibweisen_fuehren_zur_selben_nummer(self, eingabe, erwartet):
        """Auf dem Handy tippt niemand die Nummer in genau einer Form - und die
        Schnittstelle antwortet auf jede Abweichung nur mit 'abgelehnt'."""
        assert telefonnummer_normalisieren(eingabe) == erwartet

    def test_auslaendische_nummer_bleibt_unangetastet(self):
        assert telefonnummer_normalisieren("+43 664 1234567") == "+436641234567"

    def test_leere_eingabe(self):
        assert telefonnummer_normalisieren("") == ""


class TestFehlerdeutung:
    """Vorher hiess jeder Fehlschlag 'Stimmen Telefonnummer und PIN?' - auch
    dann, wenn Trade Republic die Anfrage gar nicht angesehen hatte."""

    def test_abgelehnte_zugangsdaten(self):
        assert "PIN" in _anmeldefehler(HttpFehler(401))

    def test_bot_schutz_ist_kein_pin_problem(self):
        text = _anmeldefehler(HttpFehler(403), ohne_token=True)

        assert "Bot-Schutz" in text
        assert "nicht an Telefonnummer oder PIN" in text
        assert "aus dem Browser hinterlegt" in text

    def test_bot_schutz_mit_token_verschweigt_den_hinweis(self):
        text = _anmeldefehler(HttpFehler(403), ohne_token=False)

        assert "Bot-Schutz" in text
        assert "Browser" not in text

    def test_zu_viele_versuche(self):
        assert "Geduld" in _anmeldefehler(HttpFehler(429))

    def test_unbekannter_status_wird_genannt(self):
        assert "HTTP 503" in _anmeldefehler(HttpFehler(503))

    def test_fehlermeldung_von_trade_republic_wird_durchgereicht(self):
        text = _anmeldefehler(ValueError("[{'errorCode': 'TOO_MANY_ATTEMPTS'}]"))

        assert "TOO_MANY_ATTEMPTS" in text

    def test_netzfehler_verweist_aufs_protokoll(self):
        text = _anmeldefehler(ConnectionError("kein Netz"))

        assert "ConnectionError" in text
        assert "Protokoll" in text

    def test_code_schritt_meldet_den_code(self):
        text = _anmeldefehler(HttpFehler(401), abgelehnt="Der Code wurde nicht akzeptiert.")

        assert text == "Der Code wurde nicht akzeptiert."
