"""Die GoCardless-Kapselung ohne Netz.

Geprueft wird das, was am ehesten stillschweigend falsch waere: welcher der
gelieferten Salden gilt, wie eine abgelehnte Antwort in Klartext wird und dass
der Zugriffstoken nur einmal geholt und danach aus dem Speicher genommen wird.
"""
import datetime as dt
from decimal import Decimal

import pytest

from app import gocardless


@pytest.fixture(autouse=True)
def frischer_token(monkeypatch):
    gocardless.token_verwerfen()
    monkeypatch.setenv("GOCARDLESS_SECRET_ID", "test-id")
    monkeypatch.setenv("GOCARDLESS_SECRET_KEY", "test-key")
    yield
    gocardless.token_verwerfen()


class FakeAntwort:
    def __init__(self, status_code=200, daten=None):
        self.status_code = status_code
        self._daten = daten if daten is not None else {}

    def json(self):
        if self._daten is None:
            raise ValueError("keine JSON-Antwort")
        return self._daten


def _requests_ersetzen(monkeypatch, antworten: dict, protokoll: list | None = None):
    """antworten: Pfad -> FakeAntwort (oder Liste, dann der Reihe nach)."""

    def fake_request(methode, url, **kwargs):
        pfad = url.replace(gocardless.GOCARDLESS_BASIS_URL, "")
        if protokoll is not None:
            protokoll.append((methode, pfad, kwargs.get("json")))
        eintrag = antworten[pfad]
        if isinstance(eintrag, list):
            return eintrag.pop(0)
        return eintrag

    monkeypatch.setattr(gocardless.requests, "request", fake_request)


TOKEN_ANTWORT = FakeAntwort(200, {"access": "tok", "access_expires": 86400})


class TestSaldoAuswahl:
    def test_verfuegbarer_saldo_hat_vorrang(self):
        """Banken liefern mehrere Sichten auf dasselbe Konto. Ohne feste
        Reihenfolge haenge der angezeigte Wert von der Reihenfolge der Bank ab."""
        daten = {
            "balances": [
                {"balanceAmount": {"amount": "1000.00"}, "balanceType": "closingBooked"},
                {"balanceAmount": {"amount": "812.34"}, "balanceType": "interimAvailable"},
            ]
        }

        assert gocardless.saldo_aus_antwort(daten) == Decimal("812.34")

    def test_unbekannte_typen_nehmen_den_ersten(self):
        daten = {"balances": [{"balanceAmount": {"amount": "5.00"}, "balanceType": "eigenartig"}]}

        assert gocardless.saldo_aus_antwort(daten) == Decimal("5.00")

    def test_ohne_saldo_ein_verstaendlicher_fehler(self):
        with pytest.raises(gocardless.GoCardlessFehler):
            gocardless.saldo_aus_antwort({"balances": []})

    def test_unlesbarer_betrag_kippt_nicht_in_einen_500er(self):
        daten = {"balances": [{"balanceAmount": {"amount": None}, "balanceType": "expected"}]}

        with pytest.raises(gocardless.GoCardlessFehler):
            gocardless.saldo_aus_antwort(daten)


class TestToken:
    def test_wird_nur_einmal_geholt(self, monkeypatch):
        protokoll = []
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/accounts/kto/balances/": FakeAntwort(
                    200,
                    {"balances": [{"balanceAmount": {"amount": "1.00"}, "balanceType": "expected"}]},
                ),
            },
            protokoll,
        )

        gocardless.saldo("kto")
        gocardless.saldo("kto")

        assert [p for m, p, _ in protokoll if p == "/token/new/"] == ["/token/new/"]

    def test_ohne_zugangsdaten_eine_eigene_ausnahme(self, monkeypatch):
        monkeypatch.delenv("GOCARDLESS_SECRET_ID", raising=False)
        monkeypatch.delenv("GOCARDLESS_SECRET_KEY", raising=False)

        assert gocardless.zugangsdaten_vorhanden() is False
        with pytest.raises(gocardless.ZugangsdatenFehlen):
            gocardless.saldo("kto")


class TestFehlermeldungen:
    def test_grund_aus_der_antwort_wird_durchgereicht(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/accounts/kto/balances/": FakeAntwort(
                    429, {"detail": "Kontingent für heute erschöpft"}
                ),
            },
        )

        with pytest.raises(gocardless.GoCardlessFehler, match="Kontingent"):
            gocardless.saldo("kto")

    def test_ohne_grund_wenigstens_der_status(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {"/token/new/": TOKEN_ANTWORT, "/accounts/kto/balances/": FakeAntwort(500, {})},
        )

        with pytest.raises(gocardless.GoCardlessFehler, match="500"):
            gocardless.saldo("kto")

    def test_netzfehler_wird_uebersetzt(self, monkeypatch):
        def fake_request(*args, **kwargs):
            raise gocardless.requests.RequestException("weg")

        monkeypatch.setattr(gocardless.requests, "request", fake_request)

        with pytest.raises(gocardless.GoCardlessFehler, match="nicht erreichbar"):
            gocardless.institutionen()


class TestFreigabe:
    def test_status_erkennt_beide_schreibweisen(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/requisitions/r1/": FakeAntwort(
                    200, {"status": "LN", "accounts": ["kto-1"], "agreement": "ag-1"}
                ),
                "/requisitions/r2/": FakeAntwort(200, {"status": "EXPIRED", "accounts": []}),
            },
        )

        verknuepft = gocardless.freigabe_status("r1")
        abgelaufen = gocardless.freigabe_status("r2")

        assert verknuepft["verknuepft"] is True
        assert verknuepft["konten"] == ["kto-1"]
        assert abgelaufen["abgelaufen"] is True
        assert abgelaufen["verknuepft"] is False

    def test_offene_freigabe_gilt_nicht_als_verknuepft(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/requisitions/r/": FakeAntwort(200, {"status": "CR", "accounts": []}),
            },
        )

        assert gocardless.freigabe_status("r")["verknuepft"] is False

    def test_gueltigkeit_rechnet_ab_zustimmung(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/agreements/enduser/ag-1/": FakeAntwort(
                    200, {"accepted": "2026-07-01T10:00:00Z", "access_valid_for_days": 90}
                ),
            },
        )

        assert gocardless.freigabe_gueltig_bis("ag-1") == dt.date(2026, 9, 29)

    def test_ohne_zustimmung_faellt_die_rechnung_auf_heute_zurueck(self, monkeypatch):
        """Eine Warnung ein paar Tage zu frueh ist harmlos - eine fehlende nicht."""
        _requests_ersetzen(monkeypatch, {"/token/new/": TOKEN_ANTWORT})

        erwartet = dt.date.today() + dt.timedelta(days=gocardless.GOCARDLESS_FREIGABE_TAGE)
        assert gocardless.freigabe_gueltig_bis(None) == erwartet

    def test_scheiternde_zustimmung_stoppt_die_freigabe_nicht(self, monkeypatch):
        """Nicht jede Bank unterstuetzt jeden Zugriffsumfang. Dann gilt die
        Voreinstellung von GoCardless statt gar keiner Freigabe."""
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/agreements/enduser/": FakeAntwort(400, {"detail": "nicht unterstützt"}),
                "/requisitions/": FakeAntwort(200, {"id": "r-1", "link": "https://bank/x"}),
            },
        )

        freigabe = gocardless.freigabe_starten("DKB_BYLADEM1001", "ref")

        assert freigabe["requisition_id"] == "r-1"
        assert freigabe["link"] == "https://bank/x"
        assert freigabe["agreement_id"] is None

    def test_institutionen_kommen_sortiert_und_ohne_kennungslose(self, monkeypatch):
        _requests_ersetzen(
            monkeypatch,
            {
                "/token/new/": TOKEN_ANTWORT,
                "/institutions/?country=de": FakeAntwort(
                    200,
                    [
                        {"id": "SPK", "name": "Sparkasse"},
                        {"id": "DKB", "name": "Deutsche Kreditbank", "bic": "BYLADEM1001"},
                        {"name": "ohne Kennung"},
                    ],
                ),
            },
        )

        banken = gocardless.institutionen()

        assert [b["id"] for b in banken] == ["DKB", "SPK"]
        assert banken[0]["bic"] == "BYLADEM1001"
