"""Datumshelfer - Grundlage saemtlicher Forecast- und Prognoseberechnungen."""
import datetime as dt

import pytest

from app.dateutils import add_months, month_end, month_start, safe_date


class TestAddMonths:
    @pytest.mark.parametrize(
        "start,monate,erwartet",
        [
            (dt.date(2026, 1, 15), 1, dt.date(2026, 2, 15)),
            (dt.date(2026, 12, 1), 1, dt.date(2027, 1, 1)),
            (dt.date(2026, 7, 1), 12, dt.date(2027, 7, 1)),
            (dt.date(2026, 7, 1), -1, dt.date(2026, 6, 1)),
            (dt.date(2026, 1, 1), -1, dt.date(2025, 12, 1)),
            (dt.date(2026, 7, 1), 0, dt.date(2026, 7, 1)),
        ],
    )
    def test_grundfaelle(self, start, monate, erwartet):
        assert add_months(start, monate) == erwartet

    def test_kappt_auf_das_monatsende(self):
        assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
        assert add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)


class TestMonatsgrenzen:
    def test_month_start(self):
        assert month_start(dt.date(2026, 7, 28)) == dt.date(2026, 7, 1)

    @pytest.mark.parametrize(
        "d,erwartet",
        [
            (dt.date(2026, 2, 1), dt.date(2026, 2, 28)),
            (dt.date(2024, 2, 1), dt.date(2024, 2, 29)),
            (dt.date(2026, 7, 15), dt.date(2026, 7, 31)),
        ],
    )
    def test_month_end(self, d, erwartet):
        assert month_end(d) == erwartet


class TestSafeDate:
    def test_gueltiger_tag_bleibt(self):
        assert safe_date(2026, 7, 15) == dt.date(2026, 7, 15)

    def test_zu_grosser_tag_wird_gekappt(self):
        assert safe_date(2026, 2, 31) == dt.date(2026, 2, 28)
        assert safe_date(2026, 4, 31) == dt.date(2026, 4, 30)
