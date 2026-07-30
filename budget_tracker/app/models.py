"""SQLAlchemy-Modelle - 1:1 Abbildung des Mermaid-ER-Diagramms aus dem Konzept.

Es wird ausschliesslich gespeichert, was Fakt ist. Salden, Prognosen,
Zeitachsen und die Review-Liste werden nirgends persistiert, sondern in
app/calculations.py aus diesen Tabellen berechnet.
"""
import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Konfiguration(Base):
    """Singleton-Tabelle fuer globale Fakten."""

    __tablename__ = "konfiguration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_datum: Mapped[dt.date] = mapped_column(Date, nullable=False)
    import_verzeichnis: Mapped[str] = mapped_column(String, nullable=False)


class Topf(Base):
    __tablename__ = "topf"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    startsaldo: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Seit 1.15.0 nicht mehr ausgewertet: die Sondertilgungs-Aussage auf der
    # Startseite leitet Betrag und Faelligkeit aus der Forecast-Regel ab
    # (calculations.sondertilgung_status) und bleibt damit automatisch mit ihr
    # in Sync. Die Spalten bleiben erhalten, damit bestehende seed-data.json
    # weiter gelesen werden koennen, ohne dass eine Migration Daten wegwirft.
    jahresziel: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    sondertilgung_datum: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    buchungen: Mapped[list["Buchung"]] = relationship(
        "Buchung", back_populates="topf", foreign_keys="Buchung.topf_id"
    )
    forecast_regeln: Mapped[list["ForecastRegel"]] = relationship(
        "ForecastRegel", back_populates="topf"
    )
    forecast_vorkommen: Mapped[list["ForecastVorkommen"]] = relationship(
        "ForecastVorkommen", back_populates="topf"
    )
    umbuchungen_als_quelle: Mapped[list["TopfUmbuchung"]] = relationship(
        "TopfUmbuchung", back_populates="von_topf", foreign_keys="TopfUmbuchung.von_topf_id"
    )
    umbuchungen_als_ziel: Mapped[list["TopfUmbuchung"]] = relationship(
        "TopfUmbuchung", back_populates="nach_topf", foreign_keys="TopfUmbuchung.nach_topf_id"
    )


class Buchung(Base):
    """Jede importierte, reale CSV-Zeile aus dem Trade-Republic-Export."""

    __tablename__ = "buchung"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_buchung_transaction_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    datum: Mapped[dt.date] = mapped_column(Date, nullable=False)
    typ: Mapped[str] = mapped_column(String, nullable=False)
    betrag: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    titel: Mapped[str | None] = mapped_column(String, nullable=True)
    verwendungszweck: Mapped[str | None] = mapped_column(String, nullable=True)
    empfaenger_name: Mapped[str | None] = mapped_column(String, nullable=True)
    empfaenger_iban: Mapped[str | None] = mapped_column(String, nullable=True)
    beschreibung: Mapped[str | None] = mapped_column(String, nullable=True)

    # Auf welchem Weg die Buchung in die App kam: csv | api | manuell (siehe
    # app/import_core.py). Rein dokumentarisch - fuer die Anzeige und fuer die
    # Dopplungspruefung, sobald Datei-Import und Schnittstelle parallel laufen.
    # Nicht zu verwechseln mit zuordnung_quelle, die sagt, *warum* ein Topf
    # gewaehlt wurde.
    quelle: Mapped[str] = mapped_column(String, nullable=False, default="csv", server_default="csv")

    topf_id: Mapped[int | None] = mapped_column(ForeignKey("topf.id"), nullable=True, index=True)
    zuordnung_quelle: Mapped[str | None] = mapped_column(String, nullable=True)

    ist_umbuchung: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    umbuchung_richtung: Mapped[str | None] = mapped_column(String, nullable=True)
    gegenbuchung_id: Mapped[int | None] = mapped_column(
        ForeignKey("buchung.id"), nullable=True
    )
    umbuchung_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    importiert_am: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )

    topf: Mapped["Topf | None"] = relationship(
        "Topf", back_populates="buchungen", foreign_keys=[topf_id]
    )
    gegenbuchung: Mapped["Buchung | None"] = relationship(
        "Buchung", remote_side=[id], foreign_keys=[gegenbuchung_id]
    )


class ForecastRegel(Base):
    """Wiederkehrende Erwartung - erzeugt FORECAST_VORKOMMEN und dient dem Regel-Matching."""

    __tablename__ = "forecast_regel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topf_id: Mapped[int] = mapped_column(ForeignKey("topf.id"), nullable=False)
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    betrag: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    rhythmus: Mapped[str] = mapped_column(String, nullable=False)  # monatlich|jaehrlich|befristet
    anker_tag: Mapped[int] = mapped_column(Integer, nullable=False)
    start_datum: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_datum: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    topf: Mapped["Topf"] = relationship("Topf", back_populates="forecast_regeln")
    vorkommen: Mapped[list["ForecastVorkommen"]] = relationship(
        "ForecastVorkommen", back_populates="regel"
    )


class ForecastVorkommen(Base):
    """Eine konkrete erwartete Buchung - aus einer Regel erzeugt oder frei angelegt."""

    __tablename__ = "forecast_vorkommen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regel_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_regel.id"), nullable=True)
    topf_id: Mapped[int] = mapped_column(ForeignKey("topf.id"), nullable=False)
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    erwarteter_betrag: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    erwartetes_datum: Mapped[dt.date] = mapped_column(Date, nullable=False)

    # Der von der Regel berechnete Termin, fuer den dieses Vorkommen erzeugt
    # wurde - im Gegensatz zu erwartetes_datum unveraenderlich. Nur so laesst
    # sich exakt beantworten, ob ein Monat bereits angelegt wurde:
    # erwartetes_datum wird beim Abgleich mit einer realen Buchung, beim
    # Verschieben und beim Bearbeiten ueberschrieben und taugt dafuer nicht.
    # NULL bei frei angelegten Vorkommen, die keine Regel erzeugt hat.
    generiert_fuer: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    verknuepfte_buchung_id: Mapped[int | None] = mapped_column(
        ForeignKey("buchung.id"), nullable=True
    )
    verknuepfte_topf_umbuchung_id: Mapped[int | None] = mapped_column(
        ForeignKey("topf_umbuchung.id"), nullable=True
    )
    ignoriert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    regel: Mapped["ForecastRegel | None"] = relationship(
        "ForecastRegel", back_populates="vorkommen"
    )
    topf: Mapped["Topf"] = relationship("Topf", back_populates="forecast_vorkommen")
    buchung: Mapped["Buchung | None"] = relationship("Buchung")
    topf_umbuchung: Mapped["TopfUmbuchung | None"] = relationship(
        "TopfUmbuchung", foreign_keys=[verknuepfte_topf_umbuchung_id]
    )


class TopfUmbuchung(Base):
    """Sofort wirksame, rein virtuelle Verschiebung zwischen zwei Toepfen."""

    __tablename__ = "topf_umbuchung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    von_topf_id: Mapped[int] = mapped_column(ForeignKey("topf.id"), nullable=False)
    nach_topf_id: Mapped[int] = mapped_column(ForeignKey("topf.id"), nullable=False)
    betrag: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    datum: Mapped[dt.date] = mapped_column(Date, nullable=False)
    kommentar: Mapped[str | None] = mapped_column(String, nullable=True)
    erstellt_am: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )

    von_topf: Mapped["Topf"] = relationship(
        "Topf", back_populates="umbuchungen_als_quelle", foreign_keys=[von_topf_id]
    )
    nach_topf: Mapped["Topf"] = relationship(
        "Topf", back_populates="umbuchungen_als_ziel", foreign_keys=[nach_topf_id]
    )
