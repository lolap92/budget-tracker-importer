# Changelog

## 1.2.0 - 2026-07-27

- Jede Buchung bekommt einen möglichst sprechenden Namen statt des rohen CSV-Verwendungszwecks: Bei automatisch zugeordneten Buchungen (Zins, Verwendungszweck-Treffer mit verknüpftem Forecast-Vorkommen, Regel-Treffer) wird die Bezeichnung der Regel bzw. des Vorkommens übernommen.
- Bei manueller Zuordnung (Zuordnen-Liste und „Topf zuweisen“ auf der Buchungsdetailseite) ist jetzt ein sprechender Titel Pflicht, mit Dropdown-Vorschlägen aus allen bereits verwendeten Titeln, Regel- und Vorkommen-Bezeichnungen.

## 1.1.0 - 2026-07-21

- Umbenennung von Haushaltsbuch zu **Budget-Tracker** (Add-on-Name, Slug, Datenbankdatei, Oberfläche).
- Fehlerbehebung: Das Stylesheet wurde extern per `<link>` geladen und konnte unter Ingress fehlschlagen, wodurch die Oberfläche unformatiert erschien. CSS wird jetzt direkt in jede Seite eingebettet.
- Überarbeitung der Oberfläche im Design der GUI-Mockups (Typografie, Farbpalette, Karten/Chips, 12-Monats-Sparkline).
- Neu: „Buchung anlegen“ und „Regel anlegen“ auf der Buchungen-Seite zur manuellen Erfassung – vergangene Buchungen sofort verbuchen oder zukünftige planen, die später automatisch mit dem CSV-Import verknüpft werden. Manuell erfasste vergangene Buchungen lassen sich bei Bedarf wieder löschen.

## 1.0.0 - 2026-07-21

- Erste Version: automatischer CSV-Import mit Verzeichnis-Watcher, Topf-Zuordnung (Zins → Verwendungszweck → Regel → offen), Bank-Umbuchungen als schwebender Zustand, Topf-Umbuchungen, Forecast-Regeln und -Vorkommen mit automatischem Abgleich, 12-Monats-Prognose mit Tiefpunkt und Minus-Warnung, Haus-Kredit-Zielfortschritt, First-Start-Bootstrap über `seed-data.json` oder manuelle Ersteinrichtung.
