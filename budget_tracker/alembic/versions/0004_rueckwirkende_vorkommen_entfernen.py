"""rueckwirkend erzeugte Forecast-Vorkommen entfernen

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28

Bis einschliesslich 1.12.0 erzeugte ensure_forecast_vorkommen() fuer jede
Regel Vorkommen ab deren start_datum - ohne Untergrenze. Eine Regel mit
Startdatum in der Vergangenheit (Normalfall bei seed-data.json) hinterliess
damit fuer jeden vergangenen Monat ein Vorkommen, das nie eine reale Buchung
finden konnte, dauerhaft offen blieb und von prognose_topf() in jedem
Prognosemonat mitsummiert wurde.

Diese Migration raeumt genau diese Karteileichen weg. Bewusst nur:
- regel_id IS NOT NULL      -> frei angelegte, geplante Buchungen sind
                               Nutzereingaben und bleiben unangetastet
- nicht verknuepft          -> bereits gebuchte Vorkommen sind reales Faktum
- nicht ignoriert           -> bewusst verworfene bleiben verworfen und
                               blockieren weiterhin die Neuerzeugung
- vor dem Vormonat faellig  -> deckt sich mit FORECAST_RUECKWIRKEND_MONATE

Reale BUCHUNGen werden hier nicht angefasst: Buchungen mit einem Datum vor
dem Startdatum wurden bis 1.12.0 ebenfalls importiert und zaehlen zusaetzlich
zum Topf-Startsaldo. Sie sind aber echte, teils manuell zugeordnete
Datensaetze - ob sie geloescht oder die Startsalden angepasst werden sollen,
ist eine Entscheidung des Nutzers und nichts fuer eine automatische Migration.
"""
import datetime as dt
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _untergrenze() -> dt.date:
    """Erster Tag des Vormonats - identisch zu FORECAST_RUECKWIRKEND_MONATE = 1."""
    monatsanfang = dt.date.today().replace(day=1)
    return (monatsanfang - dt.timedelta(days=1)).replace(day=1)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM forecast_vorkommen "
            "WHERE regel_id IS NOT NULL "
            "AND verknuepfte_buchung_id IS NULL "
            "AND verknuepfte_topf_umbuchung_id IS NULL "
            "AND ignoriert = 0 "
            "AND erwartetes_datum < :untergrenze"
        ).bindparams(untergrenze=_untergrenze().isoformat())
    )


def downgrade() -> None:
    # Geloeschte Vorkommen sind aus der jeweiligen Regel jederzeit neu
    # ableitbar; ein Wiederherstellen waere weder moeglich noch sinnvoll.
    pass
