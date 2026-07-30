"""Der DKB-Kontostand: Cache-Regel, Gesamtvermoegen, Ablauf-Erinnerung.

Ohne Netz - der Abruf selbst wird ersetzt. Geprueft wird, wann ueberhaupt
abgerufen wird, was passiert, wenn der Abruf scheitert, und dass der Saldo in
keine Topf-Rechnung einsickert.
"""
import datetime as dt
from decimal import Decimal

import pytest

from app import externkonto, gocardless
from app.calculations import kontostand_gesamt, saldo_topf
from app.models import Buchung, Externkonto, ExternkontoSaldo

JETZT = dt.datetime(2026, 7, 30, 12, 0)


@pytest.fixture
def konto(db, app):
    eintrag = Externkonto(
        bezeichnung="DKB Gehaltskonto",
        gocardless_institution_id="DKB_BYLADEM1001",
        gocardless_requisition_id="req-1",
        gocardless_account_id="kto-1",
        consent_gueltig_bis=dt.date(2026, 10, 28),
    )
    db.add(eintrag)
    db.commit()
    return eintrag


def _saldo(db, konto, betrag, abgerufen_am):
    eintrag = ExternkontoSaldo(
        externkonto_id=konto.id, betrag=Decimal(betrag), abgerufen_am=abgerufen_am
    )
    db.add(eintrag)
    db.commit()
    return eintrag


class TestCache:
    def test_frischer_stand_wird_nicht_neu_geholt(self, db, konto, monkeypatch):
        _saldo(db, konto, "1500.00", JETZT - dt.timedelta(hours=1))
        monkeypatch.setattr(
            gocardless, "saldo", lambda *a: pytest.fail("darf nicht abrufen")
        )

        stand = externkonto.saldo_besorgen(db, konto, jetzt=JETZT)

        assert stand.saldo.betrag == Decimal("1500.00")
        assert stand.frisch_geholt is False

    def test_veralteter_stand_wird_geholt_und_gespeichert(self, db, konto, monkeypatch):
        _saldo(db, konto, "1500.00", JETZT - dt.timedelta(hours=7))
        monkeypatch.setattr(gocardless, "saldo", lambda *a: Decimal("1610.55"))

        stand = externkonto.saldo_besorgen(db, konto, jetzt=JETZT)

        assert stand.frisch_geholt is True
        assert stand.saldo.betrag == Decimal("1610.55")
        # Der alte Wert bleibt stehen: jeder Abruf ist ein eigener Fakt.
        assert db.query(ExternkontoSaldo).count() == 2

    def test_ohne_jeden_stand_wird_geholt(self, db, konto, monkeypatch):
        monkeypatch.setattr(gocardless, "saldo", lambda *a: Decimal("42.00"))

        stand = externkonto.saldo_besorgen(db, konto, jetzt=JETZT)

        assert stand.saldo.betrag == Decimal("42.00")

    def test_erzwungener_abruf_ignoriert_den_cache(self, db, konto, monkeypatch):
        _saldo(db, konto, "1500.00", JETZT - dt.timedelta(minutes=5))
        monkeypatch.setattr(gocardless, "saldo", lambda *a: Decimal("1600.00"))

        stand = externkonto.saldo_besorgen(db, konto, erzwingen=True, jetzt=JETZT)

        assert stand.saldo.betrag == Decimal("1600.00")

    def test_gescheiterter_abruf_laesst_den_alten_stand_stehen(self, db, konto, monkeypatch):
        """Ein Fehler darf die Seite nicht leeren - der alte Wert ist immer
        noch die beste verfuegbare Auskunft."""
        alt = _saldo(db, konto, "1500.00", JETZT - dt.timedelta(hours=9))

        def scheitert(*args):
            raise gocardless.GoCardlessFehler("Kontingent erschöpft")

        monkeypatch.setattr(gocardless, "saldo", scheitert)

        stand = externkonto.saldo_besorgen(db, konto, jetzt=JETZT)

        assert stand.saldo.id == alt.id
        assert "Kontingent" in stand.fehler
        assert db.query(ExternkontoSaldo).count() == 1

    def test_ohne_freigabe_wird_gar_nicht_erst_abgerufen(self, db, konto, monkeypatch):
        konto.gocardless_account_id = None
        db.commit()
        monkeypatch.setattr(gocardless, "saldo", lambda *a: pytest.fail("darf nicht abrufen"))

        stand = externkonto.saldo_besorgen(db, konto, jetzt=JETZT)

        assert stand.saldo is None
        assert "keine Freigabe" in stand.fehler


class TestKeineVerrechnung:
    """Der DKB-Saldo steht neben den Toepfen und wird mit nichts verrechnet -
    es ist Geld auf einem anderen Konto, keine Groesse der Topf-Logik."""

    def test_der_saldo_beruehrt_keine_topf_rechnung(self, db, app, konto):
        _saldo(db, konto, "9999.00", JETZT)

        assert kontostand_gesamt(db) == Decimal("0")
        assert saldo_topf(db, app["Urlaub"]) == Decimal("0")

    def test_auch_neben_realen_buchungen(self, db, app, konto):
        db.add(
            Buchung(
                transaction_id="offen",
                datum=dt.date(2026, 7, 10),
                typ="PAYMENT",
                betrag=Decimal("-250.00"),
            )
        )
        db.commit()
        _saldo(db, konto, "9999.00", JETZT)

        assert kontostand_gesamt(db) == Decimal("-250.00")


class TestAblaufErinnerung:
    @staticmethod
    def _konto(tage_bis_ablauf):
        return Externkonto(
            bezeichnung="DKB Gehaltskonto",
            gocardless_institution_id="DKB",
            consent_gueltig_bis=dt.date(2026, 7, 30) + dt.timedelta(days=tage_bis_ablauf),
        )

    def test_frisch_freigegeben_meldet_nichts(self):
        assert externkonto.warnung(self._konto(80), heute=dt.date(2026, 7, 30)) is None

    def test_sieben_tage_vorher_faengt_die_erinnerung_an(self):
        text = externkonto.warnung(self._konto(7), heute=dt.date(2026, 7, 30))

        assert "läuft in 7 Tagen ab" in text

    def test_am_letzten_tag(self):
        text = externkonto.warnung(self._konto(0), heute=dt.date(2026, 7, 30))

        assert "läuft heute ab" in text

    def test_abgelaufen(self):
        text = externkonto.warnung(self._konto(-3), heute=dt.date(2026, 7, 30))

        assert "abgelaufen" in text

    def test_ohne_datum_keine_erinnerung(self):
        konto = Externkonto(bezeichnung="X", gocardless_institution_id="DKB")

        assert externkonto.warnung(konto, heute=dt.date(2026, 7, 30)) is None

    def test_ohne_konto_keine_erinnerung(self):
        assert externkonto.warnung(None) is None
