"""Invarianten des Forecast-Plans.

Die vorhandenen Tests pruefen einzelne Verhaltensweisen. Diese hier pruefen die
Eigenschaft, die immer gelten muss - und deren Verletzung die beiden bisherigen
Fehler ausgemacht hat:

    Fuer jede Regel ist die Menge der offenen, unveraenderten Vorkommen genau
    die Menge der Termine, die die Regel erzeugt. Kein Termin doppelt, keiner
    fehlt.

Ein fehlender Termin war der Fehler von 1.15.0 (ein Zeitfenster zaehlte den
Nachbarmonat als belegt), ein doppelter der von 1.26.0 (der Februar kappte
einen Anker-Tag 29-31, die gekappten Vorkommen blieben nach der Korrektur
liegen). Beide waeren hier aufgefallen, ohne dass man sie vorher kennen muss.
"""
import datetime as dt
from collections import Counter
from decimal import Decimal

import pytest

from app.calculations import prognose_topf
from app.forecast_engine import (
    _occurrence_dates,
    ensure_forecast_vorkommen,
    forecast_untergrenze,
)
from app.config import FORECAST_HORIZON_MONATE
from app.dateutils import add_months
from app.models import ForecastRegel, ForecastVorkommen
from tests.conftest import HEUTE


def plan(db, regel) -> Counter:
    """Die Termine, fuer die offene, unveraenderte Vorkommen bestehen."""
    return Counter(
        v.generiert_fuer
        for v in db.query(ForecastVorkommen).filter(
            ForecastVorkommen.regel_id == regel.id,
            ForecastVorkommen.verknuepfte_buchung_id.is_(None),
            ForecastVorkommen.ignoriert.is_(False),
        )
    )


def termine(db, regel) -> list[dt.date]:
    return _occurrence_dates(
        regel,
        add_months(HEUTE, FORECAST_HORIZON_MONATE),
        forecast_untergrenze(db, HEUTE),
    )


def anlegen(db, topf, **abweichungen):
    daten = {
        "topf_id": topf.id,
        "bezeichnung": "Sparrate",
        "betrag": Decimal("-200.00"),
        "rhythmus": "monatlich",
        "anker_tag": 1,
        "start_datum": dt.date(2026, 1, 1),
        "end_datum": None,
    }
    daten.update(abweichungen)
    # Bewusst direkt statt ueber regel_erstellen: das erzeugt seine Vorkommen
    # gegen den echten Kalendertag, waehrend diese Tests gegen ein festes
    # Bezugsdatum rechnen. Sonst reicht der Horizont beider Seiten
    # unterschiedlich weit und der Vergleich vergliche Aepfel mit Birnen.
    regel = ForecastRegel(**daten)
    db.add(regel)
    db.commit()
    return regel


class TestPlanInvariante:
    """Der Plan bildet die Regel exakt ab - fuer jeden Anker-Tag."""

    @pytest.mark.parametrize("anker_tag", [1, 15, 27, 28, 29, 30, 31])
    def test_monatlich(self, db, app, anker_tag):
        regel = anlegen(db, app["Urlaub"], anker_tag=anker_tag)

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        erwartet = Counter(termine(db, regel))
        assert plan(db, regel) == erwartet
        assert all(anzahl == 1 for anzahl in erwartet.values()), "kein Termin doppelt"

    @pytest.mark.parametrize("anker_tag", [1, 28, 29, 30, 31])
    def test_jaehrlich(self, db, app, anker_tag):
        regel = anlegen(
            db, app["Urlaub"], rhythmus="jaehrlich", anker_tag=anker_tag,
            start_datum=dt.date(2026, 2, 1),
        )

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert plan(db, regel) == Counter(termine(db, regel))

    def test_befristet(self, db, app):
        regel = anlegen(
            db, app["Urlaub"], rhythmus="befristet", anker_tag=29,
            end_datum=dt.date(2026, 11, 30),
        )

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert plan(db, regel) == Counter(termine(db, regel))
        assert max(plan(db, regel)) <= dt.date(2026, 11, 30)

    @pytest.mark.parametrize("anker_tag", [28, 29, 30, 31])
    def test_hoechstens_ein_termin_je_monat(self, db, app, anker_tag):
        """Der Kern des 1.26.0-Fehlers: der Februar kappt hohe Anker-Tage, und
        die gekappten Eintraege standen danach neben den richtigen."""
        regel = anlegen(db, app["Urlaub"], anker_tag=anker_tag)

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        je_monat = Counter((d.year, d.month) for d in plan(db, regel))
        assert all(anzahl == 1 for anzahl in je_monat.values()), je_monat


class TestMonatsgrenzen:
    """Kurze Monate und Schaltjahre - die Stelle, an der es zweimal krachte."""

    @pytest.mark.parametrize(
        "anker_tag,monat,erwartet",
        [
            (31, (2027, 4), dt.date(2027, 4, 30)),
            (31, (2027, 2), dt.date(2027, 2, 28)),
            (30, (2027, 2), dt.date(2027, 2, 28)),
            (29, (2027, 2), dt.date(2027, 2, 28)),
            (28, (2027, 2), dt.date(2027, 2, 28)),
        ],
    )
    def test_kurzer_monat_kappt_nur_diesen_monat(self, db, app, anker_tag, monat, erwartet):
        regel = anlegen(db, app["Urlaub"], anker_tag=anker_tag)

        alle = termine(db, regel)
        im_monat = [d for d in alle if (d.year, d.month) == monat]

        assert im_monat == [erwartet]

    def test_der_folgemonat_faellt_nicht_zurueck(self, db, app):
        """Genau das war der alte Fehler: nach dem Februar blieb die Regel auf
        dem 28. stehen, statt zum Anker-Tag zurueckzukehren."""
        regel = anlegen(db, app["Urlaub"], anker_tag=31)

        nach_februar = [
            d for d in termine(db, regel) if (d.year, d.month) == (2027, 3)
        ]

        assert nach_februar == [dt.date(2027, 3, 31)]

    def test_schaltjahr(self, db, app):
        """2028 hat einen 29. Februar - dann ist er auch der Termin."""
        regel = anlegen(db, app["Urlaub"], anker_tag=29)
        heute = dt.date(2028, 1, 15)

        februar = [
            d
            for d in _occurrence_dates(
                regel,
                add_months(heute, FORECAST_HORIZON_MONATE),
                forecast_untergrenze(db, heute),
            )
            if (d.year, d.month) == (2028, 2)
        ]

        assert februar == [dt.date(2028, 2, 29)]


class TestStabilitaet:
    def test_mehrfache_laeufe_aendern_nichts(self, db, app):
        """Der Scan laeuft alle 30 Sekunden - er darf beim zweiten und dritten
        Mal nichts hinzufuegen und nichts wegnehmen."""
        regel = anlegen(db, app["Urlaub"], anker_tag=29)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        vorher = plan(db, regel)

        for _ in range(3):
            ensure_forecast_vorkommen(db, heute=HEUTE)
            db.commit()

        assert plan(db, regel) == vorher

    def test_der_plan_erholt_sich_von_altlasten(self, db, app):
        """Ueberbleibsel einer frueheren Fassung werden eingesammelt, ohne dass
        jemand eingreifen muss."""
        regel = anlegen(db, app["Urlaub"], anker_tag=29)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        for monat in (8, 9, 10):
            db.add(
                ForecastVorkommen(
                    regel_id=regel.id,
                    topf_id=regel.topf_id,
                    bezeichnung=regel.bezeichnung,
                    erwarteter_betrag=regel.betrag,
                    erwartetes_datum=dt.date(2026, monat, 28),
                    generiert_fuer=dt.date(2026, monat, 28),
                )
            )
        db.commit()

        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert plan(db, regel) == Counter(termine(db, regel))


class TestGeldwirkung:
    """Was ein doppelter Eintrag anrichtet: er zaehlt in der Prognose mit."""

    def test_doppelte_vorkommen_verfaelschen_die_prognose(self, db, app):
        regel = anlegen(db, app["Urlaub"], anker_tag=29)
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()
        sauber = prognose_topf(db, app["Urlaub"], heute=HEUTE)

        # Altlast einschleusen, wie sie die alte Erzeugung hinterliess ...
        db.add(
            ForecastVorkommen(
                regel_id=regel.id,
                topf_id=regel.topf_id,
                bezeichnung=regel.bezeichnung,
                erwarteter_betrag=regel.betrag,
                erwartetes_datum=dt.date(2026, 8, 28),
                generiert_fuer=dt.date(2026, 8, 28),
            )
        )
        db.commit()
        verfaelscht = prognose_topf(db, app["Urlaub"], heute=HEUTE)
        assert verfaelscht.tiefpunkt < sauber.tiefpunkt, "200 EUR zu viel eingeplant"

        # ... und der naechste Scan raeumt sie weg.
        ensure_forecast_vorkommen(db, heute=HEUTE)
        db.commit()

        assert prognose_topf(db, app["Urlaub"], heute=HEUTE).tiefpunkt == sauber.tiefpunkt
