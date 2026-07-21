"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "konfiguration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("import_verzeichnis", sa.String(), nullable=False),
    )

    op.create_table(
        "topf",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("startsaldo", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("jahresziel", sa.Numeric(12, 2), nullable=True),
        sa.Column("sondertilgung_datum", sa.Date(), nullable=True),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("name", name="uq_topf_name"),
    )

    op.create_table(
        "buchung",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("typ", sa.String(), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("verwendungszweck", sa.String(), nullable=True),
        sa.Column("empfaenger_name", sa.String(), nullable=True),
        sa.Column("empfaenger_iban", sa.String(), nullable=True),
        sa.Column("beschreibung", sa.String(), nullable=True),
        sa.Column("topf_id", sa.Integer(), sa.ForeignKey("topf.id"), nullable=True),
        sa.Column("zuordnung_quelle", sa.String(), nullable=True),
        sa.Column("ist_umbuchung", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("umbuchung_richtung", sa.String(), nullable=True),
        sa.Column("gegenbuchung_id", sa.Integer(), sa.ForeignKey("buchung.id"), nullable=True),
        sa.Column("umbuchung_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("importiert_am", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("transaction_id", name="uq_buchung_transaction_id"),
    )
    op.create_index("ix_buchung_transaction_id", "buchung", ["transaction_id"])
    op.create_index("ix_buchung_topf_id", "buchung", ["topf_id"])

    op.create_table(
        "forecast_regel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topf_id", sa.Integer(), sa.ForeignKey("topf.id"), nullable=False),
        sa.Column("bezeichnung", sa.String(), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("rhythmus", sa.String(), nullable=False),
        sa.Column("anker_tag", sa.Integer(), nullable=False),
        sa.Column("start_datum", sa.Date(), nullable=False),
        sa.Column("end_datum", sa.Date(), nullable=True),
    )

    op.create_table(
        "topf_umbuchung",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("von_topf_id", sa.Integer(), sa.ForeignKey("topf.id"), nullable=False),
        sa.Column("nach_topf_id", sa.Integer(), sa.ForeignKey("topf.id"), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("kommentar", sa.String(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "forecast_vorkommen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "regel_id", sa.Integer(), sa.ForeignKey("forecast_regel.id"), nullable=True
        ),
        sa.Column("topf_id", sa.Integer(), sa.ForeignKey("topf.id"), nullable=False),
        sa.Column("bezeichnung", sa.String(), nullable=False),
        sa.Column("erwarteter_betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("erwartetes_datum", sa.Date(), nullable=False),
        sa.Column(
            "verknuepfte_buchung_id", sa.Integer(), sa.ForeignKey("buchung.id"), nullable=True
        ),
        sa.Column(
            "verknuepfte_topf_umbuchung_id",
            sa.Integer(),
            sa.ForeignKey("topf_umbuchung.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("forecast_vorkommen")
    op.drop_table("topf_umbuchung")
    op.drop_table("forecast_regel")
    op.drop_index("ix_buchung_topf_id", table_name="buchung")
    op.drop_index("ix_buchung_transaction_id", table_name="buchung")
    op.drop_table("buchung")
    op.drop_table("topf")
    op.drop_table("konfiguration")
