"""Topf-Umbuchung: sofort wirksame, virtuelle Verschiebung zwischen zwei
Toepfen ohne reale Bankbuchung (Konzept Abschnitt 6). Zu unterscheiden
von der (Bank-)Umbuchung in app/umbuchung.py."""
import datetime as dt

from sqlalchemy.orm import Session

from app.models import TopfUmbuchung


def erstelle_topf_umbuchung(
    db: Session,
    von_topf_id: int,
    nach_topf_id: int,
    betrag,
    datum: dt.date | None = None,
    kommentar: str | None = None,
) -> TopfUmbuchung:
    if von_topf_id == nach_topf_id:
        raise ValueError("Quell- und Zieltopf muessen unterschiedlich sein.")
    if float(betrag) <= 0:
        raise ValueError("Betrag muss groesser als 0 sein.")

    umbuchung = TopfUmbuchung(
        von_topf_id=von_topf_id,
        nach_topf_id=nach_topf_id,
        betrag=betrag,
        datum=datum or dt.date.today(),
        kommentar=kommentar or None,
    )
    db.add(umbuchung)
    db.commit()
    return umbuchung
