"""Demo-Daten fuer den Demo-Modus (siehe config.DEMO_MODUS).

Nutzt bewusst die echte Fachlogik (assignment.topf_zuordnen,
forecast_engine.ensure_forecast_vorkommen) statt Buchungen von Hand mit
Vorkommen zu verknuepfen - so sehen die Demo-Daten genauso aus wie ein
echter Import/Abgleich. Datumsangaben sind relativ zu "heute", damit die
Demo bei jedem Neustart unabhaengig vom Kalenderdatum plausibel aussieht.

Erzeugt bewusst KEINEN TradeRepublicKonto-Eintrag: die Trade-Republic-Seite
soll im Demo-Modus im "nicht verbunden"-Zustand bleiben, nie eine echte
Telefonnummer/Sitzung vortaeuschen. Alle Namen, IBANs und Wertpapiere sind
frei erfunden.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app.assignment import topf_zuordnen
from app.calculations import kontostand_gesamt
from app.config import DEFAULT_IMPORT_DIR, TOPF_NAMEN
from app.forecast_engine import ensure_forecast_vorkommen
from app.models import (
    Buchung,
    DepotPosition,
    DepotSnapshot,
    ForecastRegel,
    ImportVerdacht,
    Konfiguration,
    Topf,
    TopfUmbuchung,
)


def lade_demo_daten(db: Session) -> None:
    heute = dt.date.today()
    start_datum = heute - dt.timedelta(days=400)

    db.add(Konfiguration(start_datum=start_datum, import_verzeichnis=DEFAULT_IMPORT_DIR))

    startsalden = {
        "Haus Kredit": Decimal("0"),
        "Haus Renovierung": Decimal("1200"),
        "Urlaub": Decimal("650"),
        "Sonderausgaben": Decimal("2000"),
    }
    toepfe: dict[str, Topf] = {}
    for i, name in enumerate(TOPF_NAMEN):
        topf = Topf(name=name, startsaldo=startsalden.get(name, Decimal("0")), reihenfolge=i)
        db.add(topf)
        db.flush()
        toepfe[name] = topf

    regeln = [
        ("Haus Renovierung", "Demo-Sparrate", Decimal("200"), "monatlich", 1),
        ("Urlaub", "Demo-Sparrate", Decimal("100"), "monatlich", 15),
        ("Haus Kredit", "Demo-Kreditrate", Decimal("-650"), "monatlich", 3),
    ]
    for topf_name, bezeichnung, betrag, rhythmus, anker_tag in regeln:
        db.add(
            ForecastRegel(
                topf_id=toepfe[topf_name].id,
                bezeichnung=bezeichnung,
                betrag=betrag,
                rhythmus=rhythmus,
                anker_tag=anker_tag,
                start_datum=start_datum,
            )
        )
    db.flush()
    ensure_forecast_vorkommen(db, heute)
    db.flush()

    zaehler = {"n": 0}

    def _naechste_id() -> str:
        zaehler["n"] += 1
        return f"demo-{zaehler['n']:03d}"

    def buchung(
        tage_zurueck: int,
        betrag: Decimal,
        titel: str | None = None,
        verwendungszweck: str | None = None,
        empfaenger: str | None = None,
        iban: str | None = None,
        topf_name: str | None = None,
        automatisch_zuordnen: bool = True,
    ) -> Buchung:
        b = Buchung(
            transaction_id=_naechste_id(),
            datum=heute - dt.timedelta(days=tage_zurueck),
            typ="TRANSFER_INBOUND" if betrag > 0 else "TRANSFER_OUTBOUND",
            betrag=betrag,
            titel=titel,
            verwendungszweck=verwendungszweck,
            empfaenger_name=empfaenger,
            empfaenger_iban=iban,
            quelle="csv",
        )
        db.add(b)
        db.flush()
        if automatisch_zuordnen:
            topf_zuordnen(db, b)
        elif topf_name is not None:
            b.topf_id = toepfe[topf_name].id
            b.zuordnung_quelle = "manuell"
        return b

    # Passende Buchungen der letzten zwei Monate - werden von topf_zuordnen()
    # automatisch ueber die Regeln oben verknuepft, wie bei einem echten Abgleich.
    for monate_zurueck in (0, 1):
        buchung(
            monate_zurueck * 30 + 1,
            Decimal("200"),
            empfaenger="Demo GmbH",
            iban="DE00 1000 0000 0000 0001 00".replace(" ", ""),
        )
        buchung(
            monate_zurueck * 30 + 15,
            Decimal("100"),
            empfaenger="Demo GmbH",
            iban="DE00 1000 0000 0000 0001 00".replace(" ", ""),
        )
        buchung(
            monate_zurueck * 30 + 3,
            Decimal("-650"),
            empfaenger="Demo-Bank Kreditservice",
            iban="DE00 2000 0000 0000 0002 00".replace(" ", ""),
        )

    # Aeltere, frei erfundene Alltagsbuchungen - manuell zugeordnet, damit sie
    # nicht ueber die Regel-Toleranz zufaellig mit einem Vorkommen kollidieren.
    buchung(
        90, Decimal("-89.50"), titel="Demo-Ausgabe: Baumarkt", empfaenger="Demo Baumarkt",
        iban="DE00 3000 0000 0000 0003 00".replace(" ", ""), topf_name="Haus Renovierung",
        automatisch_zuordnen=False,
    )
    buchung(
        150, Decimal("-240.00"), titel="Demo-Ausgabe: Ferienwohnung", empfaenger="Demo Reisebuero",
        iban="DE00 4000 0000 0000 0004 00".replace(" ", ""), topf_name="Urlaub",
        automatisch_zuordnen=False,
    )
    buchung(
        200, Decimal("500.00"), titel="Demo-Einnahme: Sonderzahlung", empfaenger="Demo Arbeitgeber GmbH",
        iban="DE00 5000 0000 0000 0005 00".replace(" ", ""), topf_name="Sonderausgaben",
        automatisch_zuordnen=False,
    )

    # Zwei unzugeordnete Buchungen fuer die Review-Liste ("Zuordnen").
    buchung(
        5, Decimal("-45.90"), titel="Demo-Ausgabe: Restaurant Beispiel",
        empfaenger="Demo Restaurant", iban="DE00 6000 0000 0000 0006 00".replace(" ", ""),
    )
    buchung(
        2, Decimal("-32.10"), titel="Demo-Ausgabe: Drogerie Beispiel",
        empfaenger="Demo Drogeriemarkt", iban="DE00 7000 0000 0000 0007 00".replace(" ", ""),
    )

    # Virtuelle Topf-Umbuchung.
    db.add(
        TopfUmbuchung(
            von_topf_id=toepfe["Sonderausgaben"].id,
            nach_topf_id=toepfe["Urlaub"].id,
            betrag=Decimal("150.00"),
            datum=heute - dt.timedelta(days=20),
            kommentar="Demo-Umbuchung: Urlaubskasse aufgestockt",
        )
    )

    # Ein offener Verdachtsfall fuer die Dopplungspruefung.
    erste_buchung = db.query(Buchung).order_by(Buchung.id).first()
    if erste_buchung is not None:
        db.add(
            ImportVerdacht(
                transaction_id=_naechste_id(),
                datum=erste_buchung.datum,
                typ=erste_buchung.typ,
                betrag=erste_buchung.betrag,
                verwendungszweck="Demo-Verdachtsfall: moeglicherweise dieselbe Bewegung",
                empfaenger_name=erste_buchung.empfaenger_name,
                empfaenger_iban=erste_buchung.empfaenger_iban,
                beschreibung=None,
                quelle="api",
                vermutete_dopplung_id=erste_buchung.id,
            )
        )

    # Depotstand - unabhaengig von einer echten Trade-Republic-Verbindung.
    # Cash auf den berechneten Kontostand gesetzt, damit die
    # Abweichungs-Anzeige auf /depot nicht faelschlich einen Fehler nahelegt.
    wertpapiere = Decimal("1192.50") + Decimal("3286.00")
    cash = kontostand_gesamt(db)
    snapshot = DepotSnapshot(zeitpunkt=dt.datetime.utcnow(), cash=cash, gesamtwert=cash + wertpapiere)
    db.add(snapshot)
    db.flush()
    db.add(
        DepotPosition(
            snapshot_id=snapshot.id,
            isin="DE000DEMO001",
            name="Demo-ETF Welt",
            stueck=Decimal("12.5"),
            kurs=Decimal("95.40"),
            einstand=Decimal("88.10"),
            wert=Decimal("1192.50"),
        )
    )
    db.add(
        DepotPosition(
            snapshot_id=snapshot.id,
            isin="DE000DEMO002",
            name="Demo-Aktie Beispiel AG",
            stueck=Decimal("8"),
            kurs=Decimal("410.75"),
            einstand=Decimal("380.00"),
            wert=Decimal("3286.00"),
        )
    )

    db.commit()
