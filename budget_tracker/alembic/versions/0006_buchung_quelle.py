"""add buchung.quelle

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30

Vorbereitung der Trade-Republic-Schnittstelle: eine reale Kontobewegung kann
die App kuenftig als CSV-Zeile *oder* als Timeline-Event erreichen. Welcher Weg
es war, laesst sich hinterher an der Buchung selbst nicht mehr ablesen - die
neue Spalte haelt es fest. Sie dient der Anzeige und der Dopplungspruefung
zwischen beiden Wegen, an keiner Berechnung aendert sie etwas.

Backfill: alles Bestehende stammt entweder aus dem Datei-Import oder aus der
manuellen Erfassung. Letztere ist an der synthetischen transaction_id mit
Praefix "manual-" erkennbar (siehe app/manual_entry.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "buchung",
        sa.Column("quelle", sa.String(), nullable=False, server_default="csv"),
    )
    op.execute("UPDATE buchung SET quelle = 'manuell' WHERE transaction_id LIKE 'manual-%'")


def downgrade() -> None:
    op.drop_column("buchung", "quelle")
