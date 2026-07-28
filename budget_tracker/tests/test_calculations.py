"""Abgeleitete Logik: Salden, Kontostand, Prognose, Zielfortschritt, Zeitachse."""
import datetime as dt
from decimal import Decimal

from app.calculations import (
    kontostand_gesamt,
    prognose_topf,
    review_liste,
    saldo_topf,
    sondertilgung_status,
    zeitachse_topf,
)
from app.models import Buchung, ForecastRegel, ForecastVorkommen, TopfUmbuchung
from tests.conftest import HEUTE


def buchung(db, topf=None, betrag="-100.00", datum=dt.date(2026, 7, 1), **kwargs):
    b = Buchung(
        transaction_id=kwargs.pop("transaction_id", f"tx-{id(kwargs)}-{datum}-{betrag}"),
        datum=datum,
        typ=kwargs.pop("typ", "PAYMENT"),
        betrag=Decimal(betrag),
        topf_id=topf.id if topf else None,
        importiert_am=dt.datetime.utcnow(),
        **kwargs,
    )
    db.add(b)
    db.commit()
    return b


def vorkommen(db, topf, betrag="-100.00", datum=dt.date(2026, 8, 1), **kwargs):
    v = ForecastVorkommen(
        topf_id=topf.id,
        bezeichnung=kwargs.pop("bezeichnung", "Erwartung"),
        erwarteter_betrag=Decimal(betrag),
        erwartetes_datum=datum,
        **kwargs,
    )
    db.add(v)
    db.commit()
    return v


class TestSaldo:
    def test_startsaldo_plus_buchungen(self, db, app):
        urlaub = app["Urlaub"]
        urlaub.startsaldo = Decimal("1000.00")
        db.commit()
        buchung(db, urlaub, "-250.00")
        buchung(db, urlaub, "80.00")

        assert saldo_topf(db, urlaub) == Decimal("830.00")

    def test_nicht_zugeordnete_buchung_zaehlt_nicht(self, db, app):
        buchung(db, None, "-500.00")

        assert saldo_topf(db, app["Urlaub"]) == Decimal("0.00")

    def test_schwebende_umbuchung_zaehlt_nicht(self, db, app):
        urlaub = app["Urlaub"]
        buchung(db, None, "-500.00", ist_umbuchung=True, umbuchung_richtung="ausgehend")

        assert saldo_topf(db, urlaub) == Decimal("0.00")

    def test_final_verbuchte_umbuchung_zaehlt(self, db, app):
        urlaub = app["Urlaub"]
        buchung(db, urlaub, "-500.00", ist_umbuchung=True, umbuchung_final=True)

        assert saldo_topf(db, urlaub) == Decimal("-500.00")

    def test_topf_umbuchung_verschiebt_zwischen_toepfen(self, db, app):
        db.add(
            TopfUmbuchung(
                von_topf_id=app["Urlaub"].id,
                nach_topf_id=app["Sonderausgaben"].id,
                betrag=Decimal("300.00"),
                datum=dt.date(2026, 7, 5),
            )
        )
        db.commit()

        assert saldo_topf(db, app["Urlaub"]) == Decimal("-300.00")
        assert saldo_topf(db, app["Sonderausgaben"]) == Decimal("300.00")


class TestKontostand:
    def test_enthaelt_auch_offene_und_schwebende_buchungen(self, db, app):
        """Echtes Geld auf dem Konto - unabhaengig vom Zuordnungsstatus."""
        for t in app.values():
            t.startsaldo = Decimal("1000.00")
        db.commit()
        buchung(db, app["Urlaub"], "-100.00")
        buchung(db, None, "-450.00")
        buchung(db, None, "-2000.00", ist_umbuchung=True, umbuchung_richtung="ausgehend")

        assert kontostand_gesamt(db) == Decimal("1450.00")

    def test_topf_umbuchung_aendert_den_kontostand_nicht(self, db, app):
        app["Urlaub"].startsaldo = Decimal("1000.00")
        db.commit()
        db.add(
            TopfUmbuchung(
                von_topf_id=app["Urlaub"].id,
                nach_topf_id=app["Sonderausgaben"].id,
                betrag=Decimal("300.00"),
                datum=dt.date(2026, 7, 5),
            )
        )
        db.commit()

        assert kontostand_gesamt(db) == Decimal("1000.00")

    def test_differenz_zur_summe_der_toepfe_ist_das_noch_offene(self, db, app):
        app["Urlaub"].startsaldo = Decimal("1000.00")
        db.commit()
        buchung(db, None, "-450.00")

        summe_toepfe = sum(saldo_topf(db, t) for t in app.values())
        assert kontostand_gesamt(db) - summe_toepfe == Decimal("-450.00")


class TestPrognose:
    def test_offene_vorkommen_kumulieren_ueber_die_monate(self, db, app):
        urlaub = app["Urlaub"]
        urlaub.startsaldo = Decimal("1000.00")
        db.commit()
        vorkommen(db, urlaub, "-200.00", dt.date(2026, 8, 15))
        vorkommen(db, urlaub, "-300.00", dt.date(2026, 9, 15))

        p = prognose_topf(db, urlaub, heute=HEUTE)

        assert p.aktueller_saldo == Decimal("1000.00")
        assert p.monatswerte[0].monat == dt.date(2026, 7, 1)
        assert p.monatswerte[0].saldo == Decimal("1000.00")
        assert p.monatswerte[1].saldo == Decimal("800.00")
        assert p.monatswerte[2].saldo == Decimal("500.00")
        assert len(p.monatswerte) == 12

    def test_verknuepftes_vorkommen_zaehlt_nicht_mehr(self, db, app):
        urlaub = app["Urlaub"]
        b = buchung(db, urlaub, "-200.00", dt.date(2026, 8, 15))
        v = vorkommen(db, urlaub, "-200.00", dt.date(2026, 8, 15))
        v.verknuepfte_buchung_id = b.id
        db.commit()

        p = prognose_topf(db, urlaub, heute=HEUTE)

        # Nur die reale Buchung, nicht zusaetzlich die Erwartung.
        assert p.monatswerte[-1].saldo == Decimal("-200.00")

    def test_ignoriertes_vorkommen_zaehlt_nicht(self, db, app):
        urlaub = app["Urlaub"]
        vorkommen(db, urlaub, "-500.00", dt.date(2026, 8, 15), ignoriert=True)

        assert prognose_topf(db, urlaub, heute=HEUTE).monatswerte[-1].saldo == Decimal("0.00")

    def test_tiefpunkt_und_minus_warnung(self, db, app):
        urlaub = app["Urlaub"]
        urlaub.startsaldo = Decimal("500.00")
        db.commit()
        vorkommen(db, urlaub, "-900.00", dt.date(2026, 9, 1))
        vorkommen(db, urlaub, "1200.00", dt.date(2026, 11, 1))

        p = prognose_topf(db, urlaub, heute=HEUTE)

        assert p.minus_warnung is True
        assert p.tiefpunkt == Decimal("-400.00")
        assert p.tiefpunkt_monat == dt.date(2026, 9, 1)

    def test_keine_warnung_wenn_alles_im_plus(self, db, app):
        urlaub = app["Urlaub"]
        urlaub.startsaldo = Decimal("500.00")
        db.commit()
        vorkommen(db, urlaub, "-100.00", dt.date(2026, 9, 1))

        p = prognose_topf(db, urlaub, heute=HEUTE)

        assert p.minus_warnung is False
        assert p.tiefpunkt == Decimal("400.00")


class TestGesamtprognose:
    """prognose_topf(db, None) - kombinierte Prognose ueber das ganze Konto."""

    def test_basis_ist_der_kontostand_nicht_die_summe_der_toepfe(self, db, app):
        app["Urlaub"].startsaldo = Decimal("1000.00")
        db.commit()
        # Noch nicht zugeordnet: zaehlt in keinen Topf, aber ins Konto.
        buchung(db, None, "-400.00")

        gesamt = prognose_topf(db, None, heute=HEUTE)

        assert gesamt.aktueller_saldo == kontostand_gesamt(db) == Decimal("600.00")

    def test_vorkommen_aller_toepfe_zaehlen_mit(self, db, app):
        app["Urlaub"].startsaldo = Decimal("1000.00")
        db.commit()
        vorkommen(db, app["Urlaub"], "-200.00", dt.date(2026, 8, 15))
        vorkommen(db, app["Sonderausgaben"], "-300.00", dt.date(2026, 8, 20))

        gesamt = prognose_topf(db, None, heute=HEUTE)

        assert gesamt.monatswerte[0].saldo == Decimal("1000.00")
        assert gesamt.monatswerte[1].saldo == Decimal("500.00")

    def test_topf_umbuchung_hebt_sich_in_der_gesamtsicht_auf(self, db, app):
        app["Urlaub"].startsaldo = Decimal("1000.00")
        db.commit()
        db.add(
            TopfUmbuchung(
                von_topf_id=app["Urlaub"].id,
                nach_topf_id=app["Sonderausgaben"].id,
                betrag=Decimal("300.00"),
                datum=dt.date(2026, 7, 5),
            )
        )
        db.commit()

        assert prognose_topf(db, None, heute=HEUTE).aktueller_saldo == Decimal("1000.00")


class TestSondertilgungStatus:
    """Startseiten-Aussage fuer Haus Kredit.

    Betrag stammt aus der jaehrlichen 'Sondertilgung'-Regel, das
    Faelligkeitsdatum aus deren naechstem offenen Vorkommen - bewusst nicht
    arithmetisch aus Anker-Tag/Startdatum, damit manuelle Verschiebungen
    einzelner Vorkommen mitgehen.

    sondertilgung_status() liest dt.date.today() selbst, deshalb sind alle
    Datumsangaben hier relativ zu heute aufgebaut.
    """

    @staticmethod
    def _regel_mit_vorkommen(db, topf, betrag="-5000.00", in_tagen=120, bezeichnung="Sondertilgung"):
        faellig = dt.date.today() + dt.timedelta(days=in_tagen)
        regel = ForecastRegel(
            topf_id=topf.id,
            bezeichnung=bezeichnung,
            betrag=Decimal(betrag),
            rhythmus="jaehrlich",
            anker_tag=faellig.day,
            start_datum=faellig,
        )
        db.add(regel)
        db.flush()
        v = ForecastVorkommen(
            regel_id=regel.id,
            topf_id=topf.id,
            bezeichnung=bezeichnung,
            erwarteter_betrag=Decimal(betrag),
            erwartetes_datum=faellig,
        )
        db.add(v)
        db.commit()
        return regel, v

    def test_nur_fuer_haus_kredit(self, db, app):
        self._regel_mit_vorkommen(db, app["Urlaub"])

        assert sondertilgung_status(db, app["Urlaub"]) is None

    def test_ohne_passende_regel_kein_ergebnis(self, db, app):
        self._regel_mit_vorkommen(db, app["Haus Kredit"], bezeichnung="Jahresbeitrag")

        assert sondertilgung_status(db, app["Haus Kredit"]) is None

    def test_ohne_offenes_zukuenftiges_vorkommen_kein_ergebnis(self, db, app):
        _, v = self._regel_mit_vorkommen(db, app["Haus Kredit"])
        v.ignoriert = True
        db.commit()

        assert sondertilgung_status(db, app["Haus Kredit"]) is None

    def test_betrag_aus_regel_faelligkeit_aus_vorkommen(self, db, app):
        """Regression zu 1.14.1: das Datum darf nicht neu berechnet werden."""
        kredit = app["Haus Kredit"]
        _, v = self._regel_mit_vorkommen(db, kredit)
        verschoben = v.erwartetes_datum + dt.timedelta(days=17)
        v.erwartetes_datum = verschoben
        db.commit()

        status = sondertilgung_status(db, kredit)

        assert status["betrag"] == Decimal("5000.00")
        assert status["faelligkeit"] == verschoben

    def test_wird_erreicht_wenn_saldo_und_zufluesse_decken(self, db, app):
        kredit = app["Haus Kredit"]
        kredit.startsaldo = Decimal("3000.00")
        db.commit()
        self._regel_mit_vorkommen(db, kredit, in_tagen=120)
        vorkommen(db, kredit, "2000.00", dt.date.today() + dt.timedelta(days=30))

        assert sondertilgung_status(db, kredit)["wird_erreicht"] is True

    def test_wird_nicht_erreicht_bei_luecke(self, db, app):
        kredit = app["Haus Kredit"]
        kredit.startsaldo = Decimal("3000.00")
        db.commit()
        self._regel_mit_vorkommen(db, kredit, in_tagen=120)
        vorkommen(db, kredit, "1000.00", dt.date.today() + dt.timedelta(days=30))

        assert sondertilgung_status(db, kredit)["wird_erreicht"] is False

    def test_zufluesse_nach_der_faelligkeit_zaehlen_nicht(self, db, app):
        kredit = app["Haus Kredit"]
        kredit.startsaldo = Decimal("3000.00")
        db.commit()
        self._regel_mit_vorkommen(db, kredit, in_tagen=120)
        vorkommen(db, kredit, "9000.00", dt.date.today() + dt.timedelta(days=200))

        assert sondertilgung_status(db, kredit)["wird_erreicht"] is False

    def test_die_sondertilgung_selbst_mindert_die_deckung_nicht(self, db, app):
        """Sonst wuerde die Regel sich selbst aus dem Saldo rechnen."""
        kredit = app["Haus Kredit"]
        kredit.startsaldo = Decimal("5000.00")
        db.commit()
        self._regel_mit_vorkommen(db, kredit, in_tagen=120)

        assert sondertilgung_status(db, kredit)["wird_erreicht"] is True



class TestListenUndZeitachse:
    def test_review_liste_zeigt_nur_offene_nicht_umbuchungen(self, db, app):
        buchung(db, None, "-100.00", transaction_id="offen")
        buchung(db, app["Urlaub"], "-100.00", transaction_id="zugeordnet")
        buchung(db, None, "-100.00", transaction_id="schwebend", ist_umbuchung=True)

        assert [b.transaction_id for b in review_liste(db)] == ["offen"]

    def test_zeitachse_trennt_reales_von_erwartetem(self, db, app):
        urlaub = app["Urlaub"]
        buchung(db, urlaub, "-100.00", dt.date(2026, 6, 1))
        buchung(db, urlaub, "-50.00", dt.date(2026, 7, 10))
        vorkommen(db, urlaub, "-200.00", dt.date(2026, 9, 1))

        achse = zeitachse_topf(db, urlaub)

        assert [e.datum for e in achse["vergangenheit"]] == [
            dt.date(2026, 7, 10),
            dt.date(2026, 6, 1),
        ]
        assert [e.datum for e in achse["zukunft"]] == [dt.date(2026, 9, 1)]
        assert all(e.gestrichelt for e in achse["zukunft"])

    def test_zeitachse_zeigt_topf_umbuchung_aus_beiden_richtungen(self, db, app):
        db.add(
            TopfUmbuchung(
                von_topf_id=app["Urlaub"].id,
                nach_topf_id=app["Sonderausgaben"].id,
                betrag=Decimal("300.00"),
                datum=dt.date(2026, 7, 5),
            )
        )
        db.commit()

        von = zeitachse_topf(db, app["Urlaub"])["vergangenheit"]
        nach = zeitachse_topf(db, app["Sonderausgaben"])["vergangenheit"]

        assert von[0].betrag == Decimal("-300.00")
        assert nach[0].betrag == Decimal("300.00")
