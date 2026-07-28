"""Automatische Topf-Zuordnung und die Zustandsuebergaenge der Bank-Umbuchung."""
import datetime as dt
from decimal import Decimal

import pytest

from app.assignment import topf_zuordnen
from app.manual_entry import erstelle_manuelle_buchung, ist_loeschbar, loesche_buchung
from app.matching import finde_passendes_vorkommen
from app.models import Buchung, ForecastRegel, ForecastVorkommen
from app.umbuchung import abgleichen, endgueltig_verbuchen, markiere_als_umbuchung
from tests.conftest import START_DATUM


def zuordnen(db, **kwargs) -> Buchung:
    b = Buchung(
        transaction_id=kwargs.pop("transaction_id", "tx-1"),
        datum=kwargs.pop("datum", dt.date(2026, 7, 1)),
        typ=kwargs.pop("typ", "PAYMENT"),
        betrag=Decimal(kwargs.pop("betrag", "-100.00")),
        importiert_am=dt.datetime.utcnow(),
        **kwargs,
    )
    db.add(b)
    db.flush()
    topf_zuordnen(db, b)
    db.commit()
    return b


class TestZuordnungsReihenfolge:
    def test_zinszahlung_geht_auf_sonderausgaben(self, db, app):
        b = zuordnen(db, typ="INTEREST_PAYMENT", betrag="3.42")

        assert b.topf_id == app["Sonderausgaben"].id
        assert b.zuordnung_quelle == "zins"
        assert b.titel == "Zinsgutschrift"

    def test_topfname_im_verwendungszweck(self, db, app):
        b = zuordnen(db, verwendungszweck="Anzahlung Urlaub Kreta")

        assert b.topf_id == app["Urlaub"].id
        assert b.zuordnung_quelle == "verwendungszweck"

    def test_topfname_ohne_leerzeichen(self, db, app):
        b = zuordnen(db, verwendungszweck="Rate HAUSKREDIT 07/2026")

        assert b.topf_id == app["Haus Kredit"].id

    def test_regel_treffer_wenn_betrag_und_datum_passen(self, db, app):
        db.add(
            ForecastVorkommen(
                regel_id=self._regel(db, app["Haus Renovierung"]).id,
                topf_id=app["Haus Renovierung"].id,
                bezeichnung="Handwerker",
                erwarteter_betrag=Decimal("-1200.00"),
                erwartetes_datum=dt.date(2026, 7, 5),
            )
        )
        db.commit()

        b = zuordnen(db, betrag="-1200.00", datum=dt.date(2026, 7, 8))

        assert b.topf_id == app["Haus Renovierung"].id
        assert b.zuordnung_quelle == "regel"
        assert b.titel == "Handwerker"

    def test_ohne_treffer_bleibt_die_buchung_offen(self, db, app):
        b = zuordnen(db, verwendungszweck="REWE Filiale 4711")

        assert b.topf_id is None
        assert b.zuordnung_quelle is None

    @staticmethod
    def _regel(db, topf) -> ForecastRegel:
        regel = ForecastRegel(
            topf_id=topf.id,
            bezeichnung="Handwerker",
            betrag=Decimal("-1200.00"),
            rhythmus="monatlich",
            anker_tag=5,
            start_datum=START_DATUM,
        )
        db.add(regel)
        db.flush()
        return regel


class TestMatchingToleranz:
    def _vorkommen(self, db, topf, betrag, datum):
        v = ForecastVorkommen(
            topf_id=topf.id,
            bezeichnung="V",
            erwarteter_betrag=Decimal(betrag),
            erwartetes_datum=datum,
        )
        db.add(v)
        db.commit()
        return v

    def test_datumstoleranz_wird_eingehalten(self, db, app):
        self._vorkommen(db, app["Urlaub"], "-100.00", dt.date(2026, 7, 1))
        b = Buchung(
            transaction_id="tx",
            datum=dt.date(2026, 7, 20),
            typ="PAYMENT",
            betrag=Decimal("-100.00"),
            importiert_am=dt.datetime.utcnow(),
        )

        assert finde_passendes_vorkommen(db, b, topf_id=app["Urlaub"].id) is None

    def test_abweichender_betrag_trifft_nicht(self, db, app):
        self._vorkommen(db, app["Urlaub"], "-100.00", dt.date(2026, 7, 1))
        b = Buchung(
            transaction_id="tx",
            datum=dt.date(2026, 7, 2),
            typ="PAYMENT",
            betrag=Decimal("-100.50"),
            importiert_am=dt.datetime.utcnow(),
        )

        assert finde_passendes_vorkommen(db, b, topf_id=app["Urlaub"].id) is None

    def test_naechstliegendes_datum_gewinnt(self, db, app):
        fern = self._vorkommen(db, app["Urlaub"], "-100.00", dt.date(2026, 7, 1))
        nah = self._vorkommen(db, app["Urlaub"], "-100.00", dt.date(2026, 7, 6))
        b = Buchung(
            transaction_id="tx",
            datum=dt.date(2026, 7, 5),
            typ="PAYMENT",
            betrag=Decimal("-100.00"),
            importiert_am=dt.datetime.utcnow(),
        )

        treffer = finde_passendes_vorkommen(db, b, topf_id=app["Urlaub"].id)
        assert treffer is nah and treffer is not fern


class TestUmbuchung:
    def test_markieren_nimmt_die_buchung_aus_dem_saldo(self, db, app):
        b = zuordnen(db, verwendungszweck="Urlaub Kreta", betrag="-800.00")
        assert b.topf_id is not None

        markiere_als_umbuchung(db, b)

        assert b.ist_umbuchung is True
        assert b.topf_id is None
        assert b.umbuchung_richtung == "ausgehend"

    def test_abgleich_ordnet_beide_seiten_demselben_topf_zu(self, db, app):
        ab = zuordnen(db, transaction_id="tx-ab", betrag="-500.00")
        auf = zuordnen(db, transaction_id="tx-auf", betrag="500.00", datum=dt.date(2026, 7, 3))
        markiere_als_umbuchung(db, ab)
        markiere_als_umbuchung(db, auf)

        abgleichen(db, ab, auf, app["Urlaub"].id)

        assert ab.gegenbuchung_id == auf.id
        assert auf.gegenbuchung_id == ab.id
        # Beide Seiten zusammen sind fuer den Topf ein Nullsummenspiel.
        from app.calculations import saldo_topf

        assert saldo_topf(db, app["Urlaub"]) == Decimal("0.00")

    def test_abgleich_verlangt_entgegengesetzte_vorzeichen(self, db, app):
        a = zuordnen(db, transaction_id="tx-a", betrag="-500.00")
        b = zuordnen(db, transaction_id="tx-b", betrag="-500.00")
        markiere_als_umbuchung(db, a)
        markiere_als_umbuchung(db, b)

        with pytest.raises(ValueError, match="Vorzeichen"):
            abgleichen(db, a, b, app["Urlaub"].id)

    def test_endgueltig_verbuchen_bringt_die_buchung_in_den_saldo(self, db, app):
        b = zuordnen(db, betrag="-500.00")
        markiere_als_umbuchung(db, b)

        endgueltig_verbuchen(db, b, app["Urlaub"].id)

        from app.calculations import saldo_topf

        assert b.umbuchung_final is True
        assert saldo_topf(db, app["Urlaub"]) == Decimal("-500.00")


class TestManuelleErfassung:
    def test_zukunftsdatum_wird_abgelehnt(self, db, app):
        morgen = dt.date.today() + dt.timedelta(days=1)

        with pytest.raises(ValueError, match="Zukunft"):
            erstelle_manuelle_buchung(db, app["Urlaub"].id, "Test", Decimal("-10.00"), morgen)

    def test_datum_vor_dem_startdatum_wird_abgelehnt(self, db, app):
        """Regression: sonst zaehlt die Bewegung zusaetzlich zum Startsaldo."""
        davor = START_DATUM - dt.timedelta(days=1)

        with pytest.raises(ValueError, match="Startdatum"):
            erstelle_manuelle_buchung(db, app["Urlaub"].id, "Test", Decimal("-10.00"), davor)

    def test_manuelle_buchung_ist_sofort_zugeordnet_und_loeschbar(self, db, app):
        b = erstelle_manuelle_buchung(
            db, app["Urlaub"].id, "Bargeld", Decimal("-50.00"), dt.date(2026, 7, 1)
        )

        assert b.transaction_id.startswith("manual-")
        assert b.topf_id == app["Urlaub"].id
        assert ist_loeschbar(b) is True

    def test_zugeordnete_csv_buchung_ist_nicht_loeschbar(self, db, app):
        b = zuordnen(db, verwendungszweck="Urlaub Kreta")

        assert ist_loeschbar(b) is False
        with pytest.raises(ValueError, match="nicht geloescht werden"):
            loesche_buchung(db, b)

    def test_loeschen_loest_die_forecast_verknuepfung(self, db, app):
        b = erstelle_manuelle_buchung(
            db, app["Urlaub"].id, "Bargeld", Decimal("-50.00"), dt.date(2026, 7, 1)
        )
        v = ForecastVorkommen(
            topf_id=app["Urlaub"].id,
            bezeichnung="V",
            erwarteter_betrag=Decimal("-50.00"),
            erwartetes_datum=dt.date(2026, 7, 1),
            verknuepfte_buchung_id=b.id,
        )
        db.add(v)
        db.commit()

        loesche_buchung(db, b)

        assert v.verknuepfte_buchung_id is None
