"""Erzeugung und Aufloesung von FORECAST_VORKOMMEN."""
import datetime as dt
from decimal import Decimal

import pytest

from app.forecast_engine import (
    _occurrence_dates,
    ensure_forecast_vorkommen,
    forecast_untergrenze,
    regel_bearbeiten,
    vorkommen_auf_sonderausgaben_buchen,
    vorkommen_loeschen,
    vorkommen_manuell_verknuepfen,
    vorkommen_verschieben,
)
from app.models import Buchung, ForecastRegel, ForecastVorkommen
from tests.conftest import HEUTE, START_DATUM


def regel_anlegen(db, topf, **kwargs) -> ForecastRegel:
    daten = {
        "topf_id": topf.id,
        "bezeichnung": "Sparrate",
        "betrag": Decimal("-200.00"),
        "rhythmus": "monatlich",
        "anker_tag": 1,
        "start_datum": START_DATUM,
        "end_datum": None,
    }
    daten.update(kwargs)
    regel = ForecastRegel(**daten)
    db.add(regel)
    db.commit()
    return regel


class TestOccurrenceDates:
    def test_monatlich(self, db, app):
        regel = regel_anlegen(db, app["Urlaub"], start_datum=dt.date(2026, 7, 1), anker_tag=15)
        dates = _occurrence_dates(regel, dt.date(2026, 10, 31), dt.date(2026, 6, 1))

        assert dates == [
            dt.date(2026, 7, 15),
            dt.date(2026, 8, 15),
            dt.date(2026, 9, 15),
            dt.date(2026, 10, 15),
        ]

    def test_anker_tag_vor_dem_startdatum_rueckt_einen_monat_weiter(self, db, app):
        regel = regel_anlegen(db, app["Urlaub"], start_datum=dt.date(2026, 7, 20), anker_tag=5)
        dates = _occurrence_dates(regel, dt.date(2026, 9, 30), dt.date(2026, 6, 1))

        assert dates[0] == dt.date(2026, 8, 5)

    def test_anker_tag_31_faellt_auf_das_monatsende(self, db, app):
        """Regression: der Februar darf den Anker-Tag nicht dauerhaft kappen.

        Wurde das Folgedatum durch Weiterzaehlen des gekappten Vormonats
        gebildet, rutschte eine Regel mit Anker-Tag 31 ab Februar fuer den
        Rest des Jahres auf den 28.
        """
        regel = regel_anlegen(db, app["Urlaub"], start_datum=dt.date(2026, 1, 1), anker_tag=31)
        dates = _occurrence_dates(regel, dt.date(2026, 5, 31), dt.date(2026, 1, 1))

        assert dates == [
            dt.date(2026, 1, 31),
            dt.date(2026, 2, 28),
            dt.date(2026, 3, 31),
            dt.date(2026, 4, 30),
            dt.date(2026, 5, 31),
        ]

    def test_befristet_endet_am_enddatum(self, db, app):
        regel = regel_anlegen(
            db,
            app["Urlaub"],
            rhythmus="befristet",
            start_datum=dt.date(2026, 7, 1),
            end_datum=dt.date(2026, 9, 1),
            anker_tag=1,
        )
        dates = _occurrence_dates(regel, dt.date(2027, 7, 1), dt.date(2026, 6, 1))

        assert dates == [dt.date(2026, 7, 1), dt.date(2026, 8, 1), dt.date(2026, 9, 1)]

    def test_jaehrlich(self, db, app):
        regel = regel_anlegen(
            db, app["Urlaub"], rhythmus="jaehrlich", start_datum=dt.date(2026, 3, 10), anker_tag=10
        )
        dates = _occurrence_dates(regel, dt.date(2027, 7, 28), dt.date(2026, 6, 1))

        assert dates == [dt.date(2027, 3, 10)]

    def test_unbekannter_rhythmus_liefert_nichts(self, db, app):
        regel = regel_anlegen(db, app["Urlaub"], rhythmus="quartalsweise")

        assert _occurrence_dates(regel, dt.date(2027, 7, 1), dt.date(2026, 1, 1)) == []


class TestUntergrenze:
    """Regression: Regeln duerfen nicht rueckwirkend Vorkommen erzeugen.

    Eine Regel mit weit zurueckliegendem Startdatum (Normalfall bei
    seed-data.json) legte fuer jeden vergangenen Monat ein Vorkommen an. Diese
    fanden nie eine reale Buchung, blieben dauerhaft offen und wurden von
    prognose_topf() in jedem Prognosemonat mitsummiert.
    """

    def test_untergrenze_ist_der_vormonat(self, db, app):
        assert forecast_untergrenze(db, HEUTE) == dt.date(2026, 6, 1)

    def test_untergrenze_nie_vor_dem_startdatum(self, db, toepfe, konfiguration):
        konfiguration.start_datum = dt.date(2026, 7, 15)
        db.commit()

        assert forecast_untergrenze(db, HEUTE) == dt.date(2026, 7, 15)

    def test_ohne_konfiguration_gilt_der_vormonat(self, db, toepfe):
        assert forecast_untergrenze(db, HEUTE) == dt.date(2026, 6, 1)

    def test_alte_regel_erzeugt_keine_vergangenen_vorkommen(self, db, app):
        regel_anlegen(db, app["Urlaub"], start_datum=dt.date(2024, 1, 1), anker_tag=1)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        vorkommen = db.query(ForecastVorkommen).all()
        assert vorkommen, "Zukuenftige Vorkommen muessen weiterhin entstehen"
        assert min(v.erwartetes_datum for v in vorkommen) == dt.date(2026, 6, 1)

    def test_horizont_endet_nach_zwoelf_monaten(self, db, app):
        regel_anlegen(db, app["Urlaub"], start_datum=dt.date(2026, 1, 1), anker_tag=1)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        vorkommen = db.query(ForecastVorkommen).all()
        assert max(v.erwartetes_datum for v in vorkommen) == dt.date(2027, 7, 1)
        # Jun 2026 bis Jul 2027
        assert len(vorkommen) == 14


class TestEnsureIdempotenz:
    def test_wiederholter_lauf_erzeugt_nichts_neues(self, db, app):
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        anzahl = db.query(ForecastVorkommen).count()

        assert ensure_forecast_vorkommen(db, heute=HEUTE) == 0
        db.commit()
        assert db.query(ForecastVorkommen).count() == anzahl

    def test_verschobenes_vorkommen_wird_nicht_neu_erzeugt(self, db, app):
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        vorkommen = (
            db.query(ForecastVorkommen)
            .filter(ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15))
            .one()
        )
        vorkommen_verschieben(vorkommen)
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        august = db.query(ForecastVorkommen).filter(
            ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15)
        )
        assert august.count() == 0, "Der August wurde verschoben, nicht neu faellig"

    def test_ignoriertes_vorkommen_wird_nicht_neu_erzeugt(self, db, app):
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        vorkommen = (
            db.query(ForecastVorkommen)
            .filter(ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15))
            .one()
        )
        vorkommen_loeschen(db, vorkommen)
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        august = db.query(ForecastVorkommen).filter(
            ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15)
        ).all()
        assert len(august) == 1 and august[0].ignoriert


class TestAufloesung:
    def test_manuell_verknuepfen_uebernimmt_topf_und_titel(self, db, app):
        vorkommen = ForecastVorkommen(
            topf_id=app["Urlaub"].id,
            bezeichnung="Hotel Mallorca",
            erwarteter_betrag=Decimal("-800.00"),
            erwartetes_datum=dt.date(2026, 7, 20),
        )
        buchung = Buchung(
            transaction_id="tx-1",
            datum=dt.date(2026, 7, 22),
            typ="PAYMENT",
            betrag=Decimal("-812.40"),
            importiert_am=dt.datetime.utcnow(),
        )
        db.add_all([vorkommen, buchung])
        db.commit()

        vorkommen_manuell_verknuepfen(db, vorkommen, buchung)
        db.commit()

        assert buchung.topf_id == app["Urlaub"].id
        assert buchung.titel == "Hotel Mallorca"
        # Das Vorkommen uebernimmt die Realitaet, nicht umgekehrt.
        assert vorkommen.erwarteter_betrag == Decimal("-812.40")
        assert vorkommen.erwartetes_datum == dt.date(2026, 7, 22)

    def test_doppelte_verknuepfung_wird_abgelehnt(self, db, app):
        buchung = Buchung(
            transaction_id="tx-1",
            datum=dt.date(2026, 7, 20),
            typ="PAYMENT",
            betrag=Decimal("-100.00"),
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(buchung)
        db.commit()
        vorkommen = [
            ForecastVorkommen(
                topf_id=app["Urlaub"].id,
                bezeichnung=f"V{i}",
                erwarteter_betrag=Decimal("-100.00"),
                erwartetes_datum=dt.date(2026, 7, 20),
            )
            for i in range(2)
        ]
        db.add_all(vorkommen)
        db.commit()

        vorkommen_manuell_verknuepfen(db, vorkommen[0], buchung)
        db.commit()

        with pytest.raises(ValueError, match="bereits mit einem anderen Vorkommen"):
            vorkommen_manuell_verknuepfen(db, vorkommen[1], buchung)

    def test_loeschen_setzt_nur_ignoriert(self, db, app):
        vorkommen = ForecastVorkommen(
            topf_id=app["Urlaub"].id,
            bezeichnung="V",
            erwarteter_betrag=Decimal("-100.00"),
            erwartetes_datum=dt.date(2026, 7, 20),
        )
        db.add(vorkommen)
        db.commit()

        vorkommen_loeschen(db, vorkommen)
        db.commit()

        assert vorkommen.ignoriert is True
        assert db.query(ForecastVorkommen).count() == 1

    def test_auf_sonderausgaben_nur_fuer_ausgehende(self, db, app):
        vorkommen = ForecastVorkommen(
            topf_id=app["Urlaub"].id,
            bezeichnung="Eingang",
            erwarteter_betrag=Decimal("500.00"),
            erwartetes_datum=dt.date(2026, 8, 1),
        )
        db.add(vorkommen)
        db.commit()

        with pytest.raises(ValueError, match="ausgehende"):
            vorkommen_auf_sonderausgaben_buchen(db, vorkommen)

    def test_auf_sonderausgaben_erzeugt_topf_umbuchung(self, db, app):
        vorkommen = ForecastVorkommen(
            topf_id=app["Urlaub"].id,
            bezeichnung="Ausflug",
            erwarteter_betrag=Decimal("-250.00"),
            erwartetes_datum=dt.date(2026, 8, 1),
        )
        db.add(vorkommen)
        db.commit()

        umbuchung = vorkommen_auf_sonderausgaben_buchen(db, vorkommen)
        db.commit()

        assert umbuchung.von_topf_id == app["Urlaub"].id
        assert umbuchung.nach_topf_id == app["Sonderausgaben"].id
        assert umbuchung.betrag == Decimal("250.00")
        assert vorkommen.verknuepfte_topf_umbuchung_id == umbuchung.id


class TestGeneriertFuer:
    """B3: 'schon angelegt?' wird exakt beantwortet statt ueber ein Zeitfenster.

    Das alte Fenster war 61 Tage breit - breit genug, um ein um einen Monat
    verschobenes Vorkommen wiederzuerkennen, und damit zwangslaeufig auch
    breit genug, um den Nachbarmonat einer monatlichen Regel mitzuzaehlen.
    """

    def test_generierte_vorkommen_merken_sich_ihren_termin(self, db, app):
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        for v in db.query(ForecastVorkommen):
            assert v.generiert_fuer == v.erwartetes_datum

    def test_frei_angelegtes_vorkommen_belegt_keinen_termin(self, db, app):
        from app.forecast_engine import erstelle_manuelles_vorkommen

        v = erstelle_manuelles_vorkommen(
            db, app["Urlaub"].id, "Öltank", Decimal("-900.00"), dt.date(2026, 9, 1)
        )

        assert v.generiert_fuer is None

    def test_verschobenes_vorkommen_behaelt_seinen_termin(self, db, app):
        """Eine verschobene Rate ist verschoben, nicht verschwunden - ihr
        Ursprungsmonat darf nicht neu befuellt werden."""
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        v = db.query(ForecastVorkommen).filter(
            ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15)).one()
        v.erwartetes_datum = dt.date(2026, 12, 15)
        db.commit()

        assert ensure_forecast_vorkommen(db, heute=HEUTE) == 0
        assert v.generiert_fuer == dt.date(2026, 8, 15)

    def test_regel_bearbeiten_fuellt_alle_monate_neu(self, db, app):
        """Regression: ein verworfenes Vorkommen, das nach einem Abgleich ein
        paar Tage in den Folgemonat gerutscht war, verschluckte dessen
        regulaeren Termin - nach 'Regel bearbeiten' fehlte der Monat still."""
        regel = regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        verworfen = db.query(ForecastVorkommen).filter(
            ForecastVorkommen.erwartetes_datum == dt.date(2026, 6, 15)).one()
        verworfen.erwartetes_datum = dt.date(2026, 7, 6)
        verworfen.ignoriert = True
        db.commit()

        regel_bearbeiten(
            db, regel, topf_id=regel.topf_id, bezeichnung="Sparrate",
            betrag=Decimal("-250.00"), rhythmus="monatlich", anker_tag=15,
            start_datum=regel.start_datum, end_datum=None,
        )
        db.commit()

        juli = sorted(
            v.erwartetes_datum
            for v in db.query(ForecastVorkommen)
            if v.erwartetes_datum.month == 7 and v.erwartetes_datum.year == 2026
        )
        assert juli == [dt.date(2026, 7, 6), dt.date(2026, 7, 15)]

    def test_verworfenes_vorkommen_blockiert_seinen_termin_weiter(self, db, app):
        regel_anlegen(db, app["Urlaub"], anker_tag=15)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        v = db.query(ForecastVorkommen).filter(
            ForecastVorkommen.erwartetes_datum == dt.date(2026, 8, 15)).one()
        vorkommen_loeschen(db, v)
        db.commit()

        assert ensure_forecast_vorkommen(db, heute=HEUTE) == 0
