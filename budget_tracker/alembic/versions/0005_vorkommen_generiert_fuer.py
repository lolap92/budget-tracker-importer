"""add forecast_vorkommen.generiert_fuer

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28

Bis 1.14.5 entschied ensure_forecast_vorkommen() ueber ein Zeitfenster um den
berechneten Termin, ob ein Vorkommen fuer diesen Monat schon existiert. Das
Fenster musste breit genug sein, um ein um einen Monat verschobenes Vorkommen
wiederzuerkennen (61 Tage) - und war damit zwangslaeufig breit genug, um bei
einer monatlichen Regel den Nachbarmonat mitzuzaehlen. Folgen: eine Luecke im
Plan blieb dauerhaft unsichtbar, weil der Folgemonat sie "belegte", und ein
weiter verschobenes Vorkommen erzeugte im Zielmonat eine Dopplung.

generiert_fuer haelt den berechneten Termin fest und wird - anders als
erwartetes_datum - nie wieder veraendert. Damit wird aus der Schaetzung ein
exakter Abgleich.

Backfill: generiert_fuer = erwartetes_datum fuer alle aus einer Regel
erzeugten Vorkommen. Fuer unverschobene Eintraege ist das exakt richtig. Bei
verschobenen wird der verschobene Termin als belegt vermerkt, der urspruengliche
Monat gilt also als frei und wird beim naechsten Scan neu angelegt - genau die
Luecken, die vorher unsichtbar waren. Bereits doppelt vorhandene Vorkommen
werden bewusst nicht zusammengefuehrt: zwei Eintraege am selben Tag koennen
legitim sein (ein verschobener plus der regulaere), das ist eine Entscheidung
des Nutzers auf der Forecast-Seite.

Frei angelegte Vorkommen (regel_id IS NULL) bleiben auf NULL - sie werden nie
generiert und belegen keinen Regel-Termin.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("forecast_vorkommen", sa.Column("generiert_fuer", sa.Date(), nullable=True))
    op.create_index(
        "ix_forecast_vorkommen_generiert_fuer", "forecast_vorkommen", ["generiert_fuer"]
    )
    op.execute(
        "UPDATE forecast_vorkommen "
        "SET generiert_fuer = erwartetes_datum "
        "WHERE regel_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_vorkommen_generiert_fuer", table_name="forecast_vorkommen")
    op.drop_column("forecast_vorkommen", "generiert_fuer")
