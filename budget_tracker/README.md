# Budget-Tracker (Home Assistant Add-on)

Privater Budget-Tracker zur Verwaltung von vier virtuellen Spartöpfen
(**Haus Kredit, Haus Renovierung, Urlaub, Sonderausgaben**) auf einem
einzigen realen Konto. Importiert automatisch Trade-Republic-CSV-Exporte,
ordnet Buchungen den Töpfen zu und berechnet Salden, eine 12-Monats-Prognose
und eine Zeitachse je Topf – **es wird nur gespeichert, was Fakt ist**;
alles andere wird berechnet.

## Funktionen

- **Direkter Abgleich mit Trade Republic** (optional, unter „Mehr → Trade Republic"): holt die Kontobewegungen alle sechs Stunden selbst ab – **inklusive Verwendungszweck**, den der CSV-Export nicht mitliefert. Der Datei-Import bleibt unverändert bestehen und ist die Rückfallebene.
- **Depotstand** unter „Mehr → Depot“: Positionen, Kurse und Cash-Bestand als reine Information – und als Plausibilitätsprüfung, weil der echte Kontostand dem selbst berechneten gegenübergestellt wird.
- Automatischer CSV-Import aus `/homeassistant/budget_tracker/imports`, dedupliziert über `transaction_id`. Zeilen mit einem Datum vor dem Startdatum werden übersprungen – sie stecken bereits in den Topf-Startsalden.
- Automatische Topf-Zuordnung: Zins → Verwendungszweck → Forecast-Regel → offen zur manuellen Zuordnung.
- Bank-Umbuchungen als bidirektionaler, schwebender Zustand mit Abgleich-Vorschlägen.
- Topf-Umbuchung: sofort wirksame, rein virtuelle Verschiebung zwischen zwei Töpfen.
- Forecast-Regeln (wiederkehrend) und einmalige geplante Buchungen, automatischer Abgleich mit realen Buchungen.
- Dritte Forecast-Auflösung: offenes, ausgehendes Vorkommen direkt „auf Sonderausgaben buchen“.
- 12-Monats-Prognose je Topf mit Tiefpunkt-Berechnung und Minus-Warnung.
- Haus Kredit als Sonderfall: Ziel-Fortschrittsanzeige statt Tiefpunkt-Logik.
- Optionaler First-Start-Bootstrap über `seed-data.json`, sonst manuelle Ersteinrichtung in der App.
- Manuelle Erfassung über „Buchung anlegen“ auf der Buchungen-Seite: vergangene Buchungen sofort real verbuchen (bevor der nächste CSV-Export sie liefert) oder zukünftige planen (legt ein offenes Forecast-Vorkommen an, das automatisch mit der späteren CSV-Buchung verknüpft wird). Manuell erfasste vergangene Buchungen lassen sich bei Bedarf wieder löschen (z. B. bei einer späteren Dopplung durch den echten CSV-Import) – importierte Buchungen nie.
- „Regel anlegen“ auf der Buchungen-Seite als Kurzweg zur Forecast-Regel-Erstellung, topfübergreifend.

## Installation

1. Dieses Repository als Add-on-Repository in Home Assistant eintragen
   (**Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**).
2. Add-on **Budget-Tracker** installieren und starten.
3. „In Seitenleiste anzeigen“ aktivieren – die App öffnet sich per Ingress.

## Einmalige Einrichtung auf dem Host

Vor dem ersten Start (oder direkt danach) auf dem Home-Assistant-Host anlegen:

```
/homeassistant/budget_tracker/imports/          <- hier regelmäßig CSV-Exporte ablegen
/homeassistant/budget_tracker/seed-data.json    <- optional, siehe unten
```

Der Ordner `imports` wird per `homeassistant_config:ro`-Mount read-only
in den Container eingebunden; das Add-on überwacht ihn selbstständig
(periodischer Scan, kein manueller Trigger nötig).

### Variante A: Start mit `seed-data.json`

Lege eine `seed-data.json` (siehe [`seed-data.example.json`](./seed-data.example.json))
direkt unter `/homeassistant/budget_tracker/` ab – **nicht** im `imports`-Unterordner.
Beim allerersten Start liest die App daraus automatisch Startdatum,
Topf-Startsalden, alle Forecast-Regeln (Schlüssel `regeln`) sowie optional
einmalige geplante Buchungen (Schlüssel `buchungen`, je Eintrag `topf`,
`datum`, `betrag`, `kommentar`) ein – letztere erscheinen als offene
Forecast-Vorkommen und werden automatisch mit der passenden realen
CSV-Buchung verknüpft, sobald sie importiert wird.

Die Datei enthält private Beträge und bleibt ausschließlich auf dem Green:
Sie wird nie verändert, nie geloggt und nie ins Repository committet
(siehe `.gitignore`).

### Variante B: Start ohne `seed-data.json`

Fehlt die Datei, zeigt die App beim ersten Aufruf eine Bootstrap-Seite zur
Eingabe von Startdatum und den vier Topf-Startsalden. Forecast-Regeln lassen
sich danach direkt in der App unter „Forecast“ anlegen.

## Demo-Modus

Für Vorführzwecke lässt sich die App über die Add-on-Option `demo_modus`
(Registerkarte „Konfiguration") komplett auf frei erfundene Testdaten
umschalten - Töpfe, Forecast-Regeln, Buchungen (inkl. offener Zuordnungen
und eines Verdachtsfalls) und ein Depotstand, damit sich Übersicht,
Buchungen, Forecast und Depot sinnvoll zeigen lassen.

Das läuft auf einer eigenen Datenbankdatei (`demo_budget_tracker.db` statt
`budget_tracker.db`) - die echten Daten werden dabei nie gelesen oder
geschrieben, unabhängig davon, was im Demo-Modus passiert. Bei jedem Start
wird die Demo-Datenbank zusätzlich verworfen und frisch aus denselben
Testdaten neu aufgebaut. Ein Hinweisbalken oben in der App macht den
Demo-Modus jederzeit sichtbar.

Der Verzeichnis-Watcher und der Trade-Republic-Abgleich (Hintergrundlauf,
Anmeldung, manueller Button) sind im Demo-Modus komplett deaktiviert -
weder werden echte CSV-Dateien aus dem konfigurierten Verzeichnis
importiert, noch lässt sich ein echtes Trade-Republic-Konto verbinden.

Zum Zurückschalten auf die echten Daten die Option wieder auf `false`
setzen und das Add-on neu starten.

## Trade Republic direkt anbinden (optional)

Unter **Mehr → Trade Republic** lässt sich das Konto direkt anbinden, statt
regelmäßig CSV-Dateien abzulegen. Verwendet wird der Web-Login über die
Bibliothek [pytr](https://pypi.org/project/pytr/): Telefonnummer und PIN
eingeben, danach den vierstelligen Code bestätigen, der in die
Trade-Republic-App kommt (auf Wunsch per SMS).

**Warum das lohnt:** der CSV-Export der App führt zwar eine Spalte
`payment_reference`, füllt sie aber nie. Ohne Verwendungszweck kann die
automatische Topf-Zuordnung nicht greifen und praktisch jede Buchung landet in
der Review-Liste. Über die Schnittstelle steht der Text zur Verfügung.

Was dabei zu wissen ist:

- **Die PIN wird nirgends gespeichert** – weder in der Datenbank noch in einer
  Datei. Sie wird ausschließlich für den Anmeldevorgang selbst benutzt.
  Erhalten bleibt nur die Sitzung, als Cookie-Datei unter `/data/pytr/`.
- **Kein vollautomatischer Dauerbetrieb.** Läuft die Sitzung nach einigen
  Wochen ab, ist wegen des Bestätigungscodes eine erneute Eingabe nötig. Die
  Übersicht meldet das unter „Zu tun".
- **Der CSV-Weg bleibt vollständig erhalten.** Beide Wege nehmen denselben
  Übernahme-Kern; fällt die Schnittstelle aus – etwa weil Trade Republic etwas
  ändert – genügt es, wieder Dateien in `imports/` abzulegen.
- **Doppelte Buchungen werden abgefangen.** Datei-Export und Schnittstelle
  stammen aus zwei verschiedenen Diensten und vergeben möglicherweise
  unterschiedliche Transaktionsnummern. Sieht eine abgerufene Bewegung aus wie
  eine bereits vorhandene Buchung (gleicher Betrag, nahezu gleicher Zeitpunkt),
  wird sie **weder importiert noch verworfen**, sondern auf der
  Trade-Republic-Seite zur Entscheidung vorgelegt – automatisch übernehmen
  würde den Betrag doppelt zählen, automatisch verwerfen ihn verlieren.
- Es werden ausschließlich lesende Abrufe verwendet. Die Schnittstelle ist
  inoffiziell; `pytr` ist deshalb exakt auf eine Version gepinnt.

### Depot

Jeder Abgleich holt in derselben Verbindung den Depotstand mit: Positionen mit
Stückzahl, Kurs, Einstand und Wert sowie den Cash-Bestand. Zu sehen unter
**Mehr → Depot**.

Der Depotwert ist **reine Information** – er fließt in keinen Topf-Saldo, in
keinen Kontostand und in keine Prognose ein. Nützlich ist vor allem der
Cash-Bestand daneben: die App rechnet ihren Kontostand aus Startsalden und
Buchungen, Trade Republic kennt den echten. Weichen beide voneinander ab, fehlt
eine Buchung, ist eine doppelt erfasst, oder ein Startsaldo stimmt nicht.
Scheitert der Depot-Abruf, bleiben die Buchungen davon unberührt.

## Laufender Betrieb

- CSV-Export aus Trade Republic regelmäßig in `imports/` ablegen – wird automatisch erkannt und importiert.
- Offene Fälle (Review-Liste unter „Zuordnen“, schwebende Umbuchungen unter „Umbuchungen“, unverknüpfte Forecast-Einträge unter „Forecast“) manuell in der App klären.
- Migrationen laufen bei jedem Add-on-Update automatisch; vor jeder Migration wird die SQLite-Datenbank nach `/data/backups/` gesichert.

## Architektur

- **Backend:** FastAPI (Python), Server-seitig gerenderte, responsive Oberfläche (mobil-first, PC-tauglich). Basis-Image seit 1.18.0 Debian statt Alpine – `pytr` hängt an `playwright`, wovon es kein musl-Wheel gibt. Der Browser selbst wird nie gestartet und sein Treiber beim Bauen wieder entfernt.
- **Datenbank:** SQLite unter `/data/budget_tracker.db`, verwaltet über SQLAlchemy + Alembic.
- **Einbindung:** Home-Assistant-Ingress.
- **Zusätzlicher Mount:** `homeassistant_config:ro` für den Lesezugriff auf `/homeassistant/budget_tracker/imports`.

Details zum Datenmodell und zur abgeleiteten Logik (Saldo-, Prognose- und
Zuordnungsberechnung) stehen als Kommentare direkt in `app/models.py`,
`app/calculations.py`, `app/assignment.py` und `app/forecast_engine.py`.

## Tests

Die Berechnungs- und Importlogik ist durch eine Test-Suite abgedeckt (Salden,
Kontostand, Prognose, Zielfortschritt, Zeitachse, CSV-Parsing und
-Dedublizierung, Forecast-Generierung, automatische Zuordnung, Umbuchungs-
Zustandsübergänge). Ausführen im Ordner `budget_tracker/`:

```
pip install -r requirements-dev.txt
pytest
```

Die Tests laufen gegen eine temporäre SQLite-Datei und rechnen gegen ein
festes Bezugsdatum, sind also unabhängig vom Kalendertag des Testlaufs.

## Fehlersuche

- **Add-on erscheint nicht im Store:** Store neu laden, Repo-URL und Sichtbarkeit (public) prüfen.
- **CSV wird nicht erkannt:** Prüfen, dass der Ordner exakt `/homeassistant/budget_tracker/imports` heißt, `*.csv`-Endung hat und das Add-on-Manifest den `homeassistant_config`-Mount enthält.
- **Bootstrap-Seite erscheint nach Update erneut:** Datenbank in `/data` wurde entfernt – Add-on-Backups prüfen.
