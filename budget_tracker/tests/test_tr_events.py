"""Timeline-Event -> Buchung (app/tr_events.py).

Laeuft komplett ohne Netz und ohne Anmeldung: die Beispiel-Events unter
tests/fixtures/tr_events/ bilden die Struktur nach, die `timelineDetailV2`
liefert - Kopfzeile, Abschnitt "Uebersicht" mit dem Feld "Referenz" und je nach
Buchungsart ein Abschnitt "Absender" oder "Empfaenger".
"""
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.import_core import DUPLIKAT, NEU, QUELLE_API, ImportKontext, uebernehmen
from app.models import Buchung
from app.tr_events import ist_kontobewegung, zeile_aus_event

FIXTURES = Path(__file__).parent / "fixtures" / "tr_events"


def event(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class TestUeberweisungen:
    """Der eigentliche Gewinn der Schnittstelle: der Verwendungszweck. Im
    CSV-Export der App ist die Spalte payment_reference leer, im Detail des
    Events steht er als Feld "Referenz"."""

    def test_eingang_mit_referenz_und_absender(self):
        zeile = zeile_aus_event(event("eingehende_ueberweisung"))

        assert zeile["transaction_id"] == "019f111c-930b-716a-bda6-d750fb3ef752"
        assert zeile["datum"] == dt.date(2026, 6, 29)
        assert zeile["betrag"] == Decimal("550.00")
        assert zeile["typ"] == "TRANSFER_INBOUND"
        assert zeile["verwendungszweck"] == "Haus Renovierung Anteil"
        assert zeile["empfaenger_name"] == "Klaus Mustermann"
        assert zeile["empfaenger_iban"] == "DE72120300001064363250"
        assert zeile["beschreibung"] == "Du hast 550,00 € von Klaus Mustermann erhalten"

    def test_ausgang_mit_referenz_und_empfaenger(self):
        zeile = zeile_aus_event(event("ausgehende_ueberweisung"))

        assert zeile["betrag"] == Decimal("-1500.00")
        assert zeile["typ"] == "TRANSFER_OUTBOUND"
        assert zeile["verwendungszweck"] == "Sondertilgung Haus Kredit"
        assert zeile["empfaenger_name"] == "Hans Mustermann"
        assert zeile["empfaenger_iban"] == "DE02120300000000202051"

    def test_delegation_liest_gegenseite_aus_der_uebersicht(self):
        """Diese Variante hat keinen Abschnitt "Name", sondern fuehrt den
        Empfaenger unter seinem eigenen Namen - und eine leere IBAN."""
        zeile = zeile_aus_event(event("ueberweisung_delegation"))

        assert zeile["empfaenger_name"] == "Nina"
        assert zeile["empfaenger_iban"] is None
        assert zeile["verwendungszweck"] is None


class TestWeitereBuchungsarten:
    def test_kartenzahlung_nimmt_den_haendler(self):
        zeile = zeile_aus_event(event("kartenzahlung"))

        assert zeile["betrag"] == Decimal("-12.16")
        assert zeile["typ"] == "CARD_PAYMENT"
        assert zeile["empfaenger_name"] == "Coop Pronto"
        assert zeile["verwendungszweck"] is None

    def test_zinsen_bekommen_den_typ_des_csv_exports(self):
        """Die Timeline nennt Zinsen INTEREST_PAYOUT, der CSV-Export
        INTEREST_PAYMENT - und genau darauf prueft die Topf-Zuordnung."""
        zeile = zeile_aus_event(event("zinsen"))

        assert zeile["typ"] == "INTEREST_PAYMENT"
        assert zeile["betrag"] == Decimal("19.93")

    def test_wertpapierkauf_ist_eine_kontobewegung(self):
        """Ein Sparplan zieht Geld vom Konto ab. Wuerde er fehlen, liefe der
        berechnete Kontostand dauerhaft vom echten weg."""
        zeile = zeile_aus_event(event("wertpapierkauf"))

        assert zeile["betrag"] == Decimal("-300.00")
        assert zeile["typ"] == "TRADE"


class TestAussortierteEvents:
    def test_storniertes_event_wird_verworfen(self):
        storniert = event("ausgehende_ueberweisung") | {"status": "CANCELED"}

        assert ist_kontobewegung(storniert) is False
        assert zeile_aus_event(storniert) is None

    @pytest.mark.parametrize("betrag", [None, {"currency": "EUR", "value": 0.0}])
    def test_events_ohne_geldbewegung_werden_verworfen(self, betrag):
        ohne = event("eingehende_ueberweisung") | {"amount": betrag}

        assert zeile_aus_event(ohne) is None

    def test_event_ohne_id_wird_verworfen(self):
        assert zeile_aus_event(event("zinsen") | {"id": None}) is None


class TestRobustheit:
    def test_fehlende_details_ergeben_trotzdem_eine_buchung(self):
        """Schlaegt der Detail-Abruf fehl, ist die Bewegung immer noch ein
        Fakt - sie wird ohne Verwendungszweck uebernommen statt verworfen."""
        ohne_details = {
            k: v for k, v in event("eingehende_ueberweisung").items() if k != "details"
        }
        zeile = zeile_aus_event(ohne_details)

        assert zeile["betrag"] == Decimal("550.00")
        assert zeile["verwendungszweck"] is None
        assert zeile["empfaenger_name"] == "Klaus Mustermann"  # Fallback: Titel
        assert zeile["beschreibung"] == "Fertig"  # Fallback: Untertitel

    def test_unbekannter_typ_wird_unveraendert_uebernommen(self):
        zeile = zeile_aus_event(event("zinsen") | {"eventType": "IRGENDWAS_NEUES"})

        assert zeile["typ"] == "IRGENDWAS_NEUES"

    def test_zeitstempel_wird_in_lokale_zeit_umgerechnet(self):
        """23:30 UTC ist hierzulande bereits der Folgetag - und das Datum
        entscheidet ueber Startdatum-Filter und Forecast-Abgleich."""
        spaet = event("zinsen") | {"timestamp": "2026-07-31T23:30:00.000+0000"}

        assert zeile_aus_event(spaet)["datum"] == dt.date(2026, 8, 1)

    def test_zeitstempel_mit_doppelpunkt_und_z(self):
        variante = event("zinsen") | {"timestamp": "2026-07-01T03:10:18.805Z"}

        assert zeile_aus_event(variante)["datum"] == dt.date(2026, 7, 1)


class TestZusammenspielMitDemImport:
    """Ein Event geht durch denselben Kern wie eine CSV-Zeile."""

    def test_zinsen_landen_auf_sonderausgaben(self, db, app):
        zeile = zeile_aus_event(event("zinsen"))

        assert uebernehmen(db, ImportKontext.laden(db), quelle=QUELLE_API, **zeile) == NEU

        buchung = db.query(Buchung).one()
        assert buchung.topf.name == "Sonderausgaben"
        assert buchung.zuordnung_quelle == "zins"
        assert buchung.quelle == "api"

    def test_referenz_traegt_die_automatische_topf_zuordnung(self):
        """Der Kern der Sache: mit dem Verwendungszweck aus dem Detail greift
        Regel 2 der Zuordnung, die beim CSV-Import mangels Text nie greifen
        konnte."""
        zeile = zeile_aus_event(event("eingehende_ueberweisung"))

        assert "Haus Renovierung" in zeile["verwendungszweck"]

    def test_zuordnung_ueber_die_referenz(self, db, app):
        zeile = zeile_aus_event(event("eingehende_ueberweisung"))

        uebernehmen(db, ImportKontext.laden(db), quelle=QUELLE_API, **zeile)

        assert db.query(Buchung).one().topf.name == "Haus Renovierung"

    def test_dieselbe_bewegung_wird_nur_einmal_uebernommen(self, db, app):
        zeile = zeile_aus_event(event("eingehende_ueberweisung"))
        kontext = ImportKontext.laden(db)

        assert uebernehmen(db, kontext, quelle=QUELLE_API, **zeile) == NEU
        assert uebernehmen(db, kontext, quelle=QUELLE_API, **zeile) == DUPLIKAT
        assert db.query(Buchung).count() == 1


class TestReferenzAusserhalbDerUebersicht:
    """Mit dem Girokonto hat Trade Republic neue Ereignistypen eingefuehrt
    (BANK_TRANSACTION_*), die ihre Angaben anders aufteilen. Bis 1.26.1 wurde
    nur der Abschnitt "Übersicht" durchsucht - der Verwendungszweck fehlte
    dann, obwohl er im Detail steht."""

    @staticmethod
    def _mit_sektionen(sektionen):
        return {
            "id": "019f-neu",
            "timestamp": "2026-07-30T15:42:00.000+0000",
            "title": "Max Mustermann",
            "subtitle": "Gesendet",
            "status": "EXECUTED",
            "amount": {"currency": "EUR", "value": -0.01},
            "eventType": "BANK_TRANSACTION_OUTGOING",
            "details": {"sections": sektionen},
        }

    def test_referenz_in_einem_anderen_abschnitt(self):
        event = self._mit_sektionen(
            [
                {"title": "Du hast 0,01 € gesendet", "type": "header", "data": {}},
                {
                    "title": "Übersicht",
                    "type": "table",
                    "data": [{"title": "Status", "detail": {"text": "Ausgeführt"}}],
                },
                {
                    "title": "Transaktion",
                    "type": "table",
                    "data": [
                        {"title": "Verwendungszweck", "detail": {"text": "Miete August"}}
                    ],
                },
            ]
        )

        assert zeile_aus_event(event)["verwendungszweck"] == "Miete August"

    def test_die_uebersicht_hat_vorrang(self):
        event = self._mit_sektionen(
            [
                {
                    "title": "Übersicht",
                    "type": "table",
                    "data": [{"title": "Referenz", "detail": {"text": "aus der Übersicht"}}],
                },
                {
                    "title": "Transaktion",
                    "type": "table",
                    "data": [{"title": "Betreff", "detail": {"text": "woanders"}}],
                },
            ]
        )

        assert zeile_aus_event(event)["verwendungszweck"] == "aus der Übersicht"

    def test_neuer_typ_wird_uebersetzt(self):
        event = self._mit_sektionen([])

        assert zeile_aus_event(event)["typ"] == "TRANSFER_OUTBOUND"

    def test_ohne_referenz_werden_die_beschriftungen_protokolliert(self, caplog):
        """Damit sich ein unbekannt benanntes Feld finden laesst, ohne den
        kompletten Datensatz mit Betraegen und IBANs zu protokollieren."""
        event = self._mit_sektionen(
            [
                {
                    "title": "Übersicht",
                    "type": "table",
                    "data": [
                        {"title": "Status", "detail": {"text": "Ausgeführt"}},
                        {"title": "Geheimfeld", "detail": {"text": "Streng geheim"}},
                    ],
                }
            ]
        )

        with caplog.at_level("INFO", logger="budget_tracker.tr_events"):
            assert zeile_aus_event(event)["verwendungszweck"] is None

        protokoll = caplog.text
        assert "BANK_TRANSACTION_OUTGOING" in protokoll
        assert "Geheimfeld" in protokoll
        # Nur die Beschriftungen, nie deren Inhalt.
        assert "Streng geheim" not in protokoll
