"""Ueberbleibsel einer alten Erzeugung entfernen (app/forecast_engine.py).

Bis 1.15.0 leitete die Erzeugung den Anker-Tag durch Weiterzaehlen des
Vormonats ab. Ein Anker-Tag 29 wurde damit vom Februar dauerhaft auf den 28.
gekappt und blieb dort fuer den Rest des Jahres. Nach der Korrektur erzeugt
dieselbe Regel wieder den 29., waehrend die alten 28er-Vorkommen liegen
bleiben - jeder Monat doppelt, und einzeln loeschen half nicht, weil der
naechste Scan sie ohnehin nicht anfasste.
"""
import datetime as dt
from decimal import Decimal

import pytest

from app.config import FORECAST_HORIZON_MONATE
from app.dateutils import add_months
from app.forecast_engine import ensure_forecast_vorkommen, regel_erstellen
from app.models import Buchung, ForecastVorkommen
from tests.conftest import HEUTE


@pytest.fixture
def regel(db, app):
    """Monatlich am 29. - der Fall, den der Februar frueher gekappt hat."""
    r = regel_erstellen(
        db,
        topf_id=app["Urlaub"].id,
        bezeichnung="Standard-Sparrate",
        betrag=Decimal("-200.00"),
        rhythmus="monatlich",
        anker_tag=29,
        start_datum=dt.date(2026, 1, 29),
        end_datum=None,
    )
    db.commit()
    ensure_forecast_vorkommen(db, heute=HEUTE)
    db.commit()
    return r


def altes_vorkommen(db, regel, datum, **abweichungen):
    """Ein Vorkommen, wie es die alte Erzeugung hinterlassen hat."""
    felder = {
        "regel_id": regel.id,
        "topf_id": regel.topf_id,
        "bezeichnung": regel.bezeichnung,
        "erwarteter_betrag": regel.betrag,
        "erwartetes_datum": datum,
        "generiert_fuer": datum,
    }
    felder.update(abweichungen)
    v = ForecastVorkommen(**felder)
    db.add(v)
    db.commit()
    return v


class TestUeberbleibsel:
    def test_der_gekappte_termin_verschwindet(self, db, app, regel):
        alt = altes_vorkommen(db, regel, dt.date(2026, 8, 28))

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=alt.id).first() is None
        # Der richtige Termin steht weiterhin da.
        assert (
            db.query(ForecastVorkommen)
            .filter(ForecastVorkommen.generiert_fuer == dt.date(2026, 8, 29))
            .count()
            == 1
        )

    def test_der_februar_bleibt_unangetastet(self, db, app, regel):
        """2027 hat keinen 29. Februar - fuer diesen Monat *ist* der 28. der
        richtige Termin, kein Ueberbleibsel."""
        februar = (
            db.query(ForecastVorkommen)
            .filter(ForecastVorkommen.generiert_fuer == dt.date(2027, 2, 28))
            .one()
        )

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=februar.id).one()

    def test_gebuchtes_ueberbleibsel_bleibt(self, db, app, regel):
        """Ein mit einer realen Buchung verknuepftes Vorkommen ist Fakt."""
        buchung = Buchung(
            transaction_id="tx-1",
            datum=dt.date(2026, 8, 28),
            typ="PAYMENT",
            betrag=Decimal("-200.00"),
            importiert_am=dt.datetime.utcnow(),
        )
        db.add(buchung)
        db.flush()
        alt = altes_vorkommen(
            db, regel, dt.date(2026, 8, 28), verknuepfte_buchung_id=buchung.id
        )

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=alt.id).one()

    def test_verworfenes_ueberbleibsel_bleibt(self, db, app, regel):
        alt = altes_vorkommen(db, regel, dt.date(2026, 8, 28), ignoriert=True)

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=alt.id).one()

    def test_verschobenes_vorkommen_bleibt(self, db, app, regel):
        """Wurde es von Hand verschoben, war das eine Entscheidung - sie darf
        nicht stillschweigend rueckgaengig gemacht werden."""
        alt = altes_vorkommen(
            db, regel, dt.date(2026, 8, 28), erwartetes_datum=dt.date(2026, 8, 15)
        )

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=alt.id).one()

    def test_frei_angelegtes_vorkommen_bleibt(self, db, app, regel):
        """Ohne Regel-Herkunft geht die Aufraeumarbeit es nichts an."""
        frei = ForecastVorkommen(
            regel_id=None,
            topf_id=app["Urlaub"].id,
            bezeichnung="Einmalig",
            erwarteter_betrag=Decimal("-50.00"),
            erwartetes_datum=dt.date(2026, 8, 28),
            generiert_fuer=None,
        )
        db.add(frei)
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=frei.id).one()

    def test_ueberfaellige_erwartung_bleibt(self, db, app, regel):
        """Aelter als der Erzeugungszeitraum: eine faellige, aber nicht
        eingetroffene Erwartung gehoert weiter in die Prognose."""
        alt = altes_vorkommen(db, regel, dt.date(2026, 3, 28))

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).filter_by(id=alt.id).one()

    def test_vorgezogenes_enddatum_raeumt_auf(self, db, app, regel):
        """Derselbe Mechanismus greift, wenn eine Regel nachtraeglich frueher
        endet - die Vorkommen danach erzeugt sie nicht mehr."""
        vorher = db.query(ForecastVorkommen).count()
        regel.end_datum = dt.date(2026, 9, 30)
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert db.query(ForecastVorkommen).count() < vorher
        # Alles zwischen neuem Ende und Erzeugungshorizont ist weg. Der
        # Horizont selbst ist die Grenze: was jenseits davon liegt, faellt
        # bewusst nicht unter die Aufraeumarbeit - darueber weiss dieser Lauf
        # nichts.
        horizont = add_months(HEUTE, FORECAST_HORIZON_MONATE)
        assert (
            db.query(ForecastVorkommen)
            .filter(
                ForecastVorkommen.generiert_fuer > dt.date(2026, 9, 30),
                ForecastVorkommen.generiert_fuer <= horizont,
            )
            .count()
            == 0
        )
