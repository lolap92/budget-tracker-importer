"""externkonto und externkonto_saldo

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-30

Das extern gefuehrte Konto (DKB-Gehaltskonto) und der Verlauf seiner
abgerufenen Salden. Reine Zusatzinformation: der Saldo fliesst in keinen
Topf-Saldo, in keinen Kontostand und in keine Prognose ein.

Bewusst nicht in dieser Tabelle: die GoCardless-Zugangsdaten. Sie stehen in
den Add-on-Optionen, der daraus geholte Token lebt nur im Speicher.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "externkonto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bezeichnung", sa.String(), nullable=False),
        sa.Column("gocardless_institution_id", sa.String(), nullable=False),
        sa.Column("gocardless_requisition_id", sa.String(), nullable=True),
        sa.Column("gocardless_agreement_id", sa.String(), nullable=True),
        sa.Column("gocardless_account_id", sa.String(), nullable=True),
        sa.Column("consent_gueltig_bis", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "externkonto_saldo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("externkonto_id", sa.Integer(), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("abgerufen_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["externkonto_id"], ["externkonto.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_externkonto_saldo_externkonto_id", "externkonto_saldo", ["externkonto_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_externkonto_saldo_externkonto_id", table_name="externkonto_saldo")
    op.drop_table("externkonto_saldo")
    op.drop_table("externkonto")
