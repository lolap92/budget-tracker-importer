"""depot_snapshot und depot_position

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30

Der zuletzt abgerufene Depotstand, damit die Seite ihn ohne Abruf zeigen kann.
Reine Information: er fliesst in keinen Topf-Saldo und in keinen Kontostand ein
- der Depotwert ist kein Fakt der Kontofuehrung.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "depot_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("zeitpunkt", sa.DateTime(), nullable=False),
        sa.Column("cash", sa.Numeric(12, 2), nullable=False),
        sa.Column("gesamtwert", sa.Numeric(12, 2), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "depot_position",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("isin", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("stueck", sa.Numeric(18, 6), nullable=False),
        sa.Column("kurs", sa.Numeric(14, 4), nullable=False),
        sa.Column("einstand", sa.Numeric(14, 4), nullable=False),
        sa.Column("wert", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["depot_snapshot.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_depot_position_snapshot_id", "depot_position", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_depot_position_snapshot_id", table_name="depot_position")
    op.drop_table("depot_position")
    op.drop_table("depot_snapshot")
