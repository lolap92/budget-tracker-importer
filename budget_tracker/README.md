# Budget-Tracker (Home Assistant Add-on)

Privater Budget-Tracker zur Verwaltung von vier virtuellen Spartöpfen
(**Haus Kredit, Haus Renovierung, Urlaub, Sonderausgaben**) auf einem
einzigen realen Konto. Importiert automatisch Trade-Republic-CSV-Exporte,
ordnet Buchungen den Töpfen zu und berechnet Salden, eine 12-Monats-Prognose
und eine Zeitachse je Topf – **es wird nur gespeichert, was Fakt ist**;
alles andere wird berechnet.

## Funktionen

- Automatischer CSV-Import aus `/homeassistant/budget_tracker/imports`, dedupliziert über `transaction_id`.
- Automatische Topf-Zuordnung: Zins → Verwendungszweck → Forecast-Regel → offen zur manuellen Zuordnung.
- Bank-Umbuchungen als bidirektionaler, schwebender Zustand mit Abgleich-Vorschlägen.
- Topf-Umbuchung: sofort wirksame, rein virtuelle Verschiebung zwischen zwei Töpfen.
- Forecast-Regeln (wiederkehrend) und einmalige geplante Buchungen, automatischer Abgleich mit realen Buchungen.
- Dritte Forecast-Auflösung: offenes, ausgehendes Vorkommen direkt „auf Sonderausgaben buchen“.
- 12-Monats-Prognose je Topf mit Tiefpunkt-Berechnung und Minus-Warnung.
- Haus Kredit als Sonderfall: Ziel-Fortschrittsanzeige statt Tiefpunkt-Logik.
- Optionaler First-Start-Bootstrap über `seed-data.json`, sonst manuelle Ersteinrichtung in der App.

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
Topf-Startsalden und alle Forecast-Regeln ein.

Die Datei enthält private Beträge und bleibt ausschließlich auf dem Green:
Sie wird nie verändert, nie geloggt und nie ins Repository committet
(siehe `.gitignore`).

### Variante B: Start ohne `seed-data.json`

Fehlt die Datei, zeigt die App beim ersten Aufruf eine Bootstrap-Seite zur
Eingabe von Startdatum und den vier Topf-Startsalden. Forecast-Regeln lassen
sich danach direkt in der App unter „Forecast“ anlegen.

## Laufender Betrieb

- CSV-Export aus Trade Republic regelmäßig in `imports/` ablegen – wird automatisch erkannt und importiert.
- Offene Fälle (Review-Liste unter „Zuordnen“, schwebende Umbuchungen unter „Umbuchungen“, unverknüpfte Forecast-Einträge unter „Forecast“) manuell in der App klären.
- Migrationen laufen bei jedem Add-on-Update automatisch; vor jeder Migration wird die SQLite-Datenbank nach `/data/backups/` gesichert.

## Architektur

- **Backend:** FastAPI (Python), Server-seitig gerenderte, responsive Oberfläche (mobil-first, PC-tauglich).
- **Datenbank:** SQLite unter `/data/budget_tracker.db`, verwaltet über SQLAlchemy + Alembic.
- **Einbindung:** Home-Assistant-Ingress.
- **Zusätzlicher Mount:** `homeassistant_config:ro` für den Lesezugriff auf `/homeassistant/budget_tracker/imports`.

Details zum Datenmodell und zur abgeleiteten Logik (Saldo-, Prognose- und
Zuordnungsberechnung) stehen als Kommentare direkt in `app/models.py`,
`app/calculations.py`, `app/assignment.py` und `app/forecast_engine.py`.

## Fehlersuche

- **Add-on erscheint nicht im Store:** Store neu laden, Repo-URL und Sichtbarkeit (public) prüfen.
- **CSV wird nicht erkannt:** Prüfen, dass der Ordner exakt `/homeassistant/budget_tracker/imports` heißt, `*.csv`-Endung hat und das Add-on-Manifest den `homeassistant_config`-Mount enthält.
- **Bootstrap-Seite erscheint nach Update erneut:** Datenbank in `/data` wurde entfernt – Add-on-Backups prüfen.
