"""trade_republic_konto und import_verdacht

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30

Die Trade-Republic-Schnittstelle braucht zwei Tabellen:

trade_republic_konto haelt die Telefonnummer und den Zeitpunkt des letzten
Abgleichs. Die PIN steht bewusst nicht darin - sie wird nur im Moment einer
Neuanmeldung entgegengenommen; die laufende Sitzung liegt als Cookie-Datei
unter /data/pytr/.

import_verdacht nimmt Bewegungen auf, die sehr wahrscheinlich schon als
Buchung existieren - unter einer anderen transaction_id, weil sie ueber den
anderen Weg kamen (Datei-Import gegen Schnittstelle). Sie werden weder
importiert noch verworfen, sondern zur Entscheidung vorgelegt.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade_republic_konto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telefonnummer", sa.String(), nullable=False),
        sa.Column("letzter_sync", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "import_verdacht",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("typ", sa.String(), nullable=False),
        sa.Column("betrag", sa.Numeric(12, 2), nullable=False),
        sa.Column("verwendungszweck", sa.String(), nullable=True),
        sa.Column("empfaenger_name", sa.String(), nullable=True),
        sa.Column("empfaenger_iban", sa.String(), nullable=True),
        sa.Column("beschreibung", sa.String(), nullable=True),
        sa.Column("quelle", sa.String(), nullable=False),
        sa.Column("vermutete_dopplung_id", sa.Integer(), nullable=True),
        sa.Column("entscheidung", sa.String(), nullable=True),
        sa.Column("erstellt_am", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vermutete_dopplung_id"], ["buchung.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", name="uq_import_verdacht_transaction_id"),
    )
    op.create_index("ix_import_verdacht_transaction_id", "import_verdacht", ["transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_import_verdacht_transaction_id", table_name="import_verdacht")
    op.drop_table("import_verdacht")
    op.drop_table("trade_republic_konto")
