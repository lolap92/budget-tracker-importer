"""Kopfzeilen der Anfragen an Trade Republic (app/tr_client.py).

Der Bot-Schutz vor der Anmeldung bewertet die Herkunftsangaben mit. Fehlen sie,
sieht die Anfrage nicht nach Browser aus und wird zur Schutzpruefung umgeleitet -
woraus am Ende ein HTTP 405 wird, weil `requests` der Umleitung folgt und dabei
aus dem POST ein GET macht.

Die Tests brauchen kein pytr: geprueft wird die Zusammenstellung selbst.
"""
from app.tr_client import _BROWSER_KOPFZEILEN, _WAF_KOPFZEILE


class Sitzung:
    """So viel von requests.Session, wie _neue_api anfasst."""

    def __init__(self):
        self.headers = {"User-Agent": "pytr-Vorgabe"}
        self.hooks = {"response": []}


def kopfzeilen_setzen(sitzung, token=None):
    """Bildet nach, was _neue_api und anmeldung_starten mit der Sitzung tun."""
    sitzung.headers = {**sitzung.headers, **_BROWSER_KOPFZEILEN}
    if token:
        sitzung.headers[_WAF_KOPFZEILE] = token
    return sitzung


class TestHerkunftsangaben:
    def test_die_vier_entscheidenden_angaben(self):
        kopf = kopfzeilen_setzen(Sitzung()).headers

        assert kopf["Origin"] == "https://app.traderepublic.com"
        assert kopf["Referer"] == "https://app.traderepublic.com/"
        assert kopf["Sec-Fetch-Site"] == "same-site"
        assert kopf["Sec-Fetch-Mode"] == "cors"

    def test_user_agent_von_pytr_bleibt_erhalten(self):
        """pytr pflegt eine aktuelle Chrome-Kennung - die wird ergaenzt,
        nicht ersetzt."""
        kopf = kopfzeilen_setzen(Sitzung()).headers

        assert kopf["User-Agent"] == "pytr-Vorgabe"

    def test_schutz_token_auch_als_kopfzeile(self):
        """pytr legt ihn nur als Cookie ab; die Weboberflaeche schickt ihn
        zusaetzlich als Kopfzeile."""
        kopf = kopfzeilen_setzen(Sitzung(), token="abc123").headers

        assert kopf[_WAF_KOPFZEILE] == "abc123"

    def test_ohne_token_keine_leere_kopfzeile(self):
        """Eine leere Kopfzeile waere schlechter als gar keine."""
        assert _WAF_KOPFZEILE not in kopfzeilen_setzen(Sitzung()).headers

    def test_die_gemeinsame_abbildung_von_pytr_bleibt_unberuehrt(self):
        """pytr weist allen Sitzungen dieselbe Klassen-Abbildung zu - sie zu
        veraendern wuerde jede weitere Sitzung mitziehen."""
        gemeinsam = {"User-Agent": "pytr-Vorgabe"}
        sitzung = Sitzung()
        sitzung.headers = gemeinsam

        kopfzeilen_setzen(sitzung, token="abc123")

        assert gemeinsam == {"User-Agent": "pytr-Vorgabe"}
