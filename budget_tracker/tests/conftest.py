"""Gemeinsame Fixtures.

Die App liest ihre Pfade beim Import von app.config aus der Umgebung, deshalb
muessen DATA_DIR/DATABASE_URL gesetzt sein, *bevor* irgendein app-Modul
importiert wird - daher die Zuweisungen ganz oben auf Modulebene.
"""
import datetime as dt
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="budget-tracker-tests-"))
os.environ["DATA_DIR"] = str(_TMP / "data")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'data' / 'test.db'}"
os.environ["HA_CONFIG_DIR"] = str(_TMP / "homeassistant")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import TOPF_NAMEN  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Konfiguration, Topf  # noqa: E402

# Fester "heute"-Bezug: alle Berechnungen der App nehmen ein Datum entgegen,
# damit die Tests nicht vom Kalendertag des Testlaufs abhaengen.
HEUTE = dt.date(2026, 7, 28)
START_DATUM = dt.date(2026, 1, 1)


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def toepfe(db):
    """Die vier Toepfe mit Startsaldo 0, als dict name -> Topf."""
    for i, name in enumerate(TOPF_NAMEN):
        db.add(Topf(name=name, startsaldo=Decimal("0.00"), reihenfolge=i))
    db.commit()
    return {t.name: t for t in db.query(Topf).all()}


@pytest.fixture
def konfiguration(db):
    konf = Konfiguration(start_datum=START_DATUM, import_verzeichnis=str(_TMP / "imports"))
    db.add(konf)
    db.commit()
    return konf


@pytest.fixture
def app(db, toepfe, konfiguration):
    """Vollstaendig eingerichtete App: Konfiguration + die vier Toepfe."""
    return toepfe


def csv_schreiben(pfad: Path, zeilen: list[str]) -> Path:
    kopf = (
        "transaction_id,date,type,amount,payment_reference,"
        "counterparty_name,counterparty_iban,description"
    )
    pfad.write_text("\n".join([kopf, *zeilen]) + "\n", encoding="utf-8")
    return pfad
