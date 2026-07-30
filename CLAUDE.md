# Arbeitsanweisungen für dieses Repository

## Ausliefern: immer zwei Branches

Der Default-Branch ist **`main`** – dorthin gehört jede Änderung.

Zusätzlich muss **jeder** Push auf `main` auf den Branch
`claude/haushaltsbuch-home-assistant-gxdybb` gespiegelt werden:

```
git push origin main
git push origin main:claude/haushaltsbuch-home-assistant-gxdybb
```

**Grund:** Der Home-Assistant-Supervisor klont ein Add-on-Repository einmal
beim Hinzufügen und holt bei „Store neu laden" immer *genau den Branch, den er
damals ausgecheckt hat*. Das war der alte Default-Branch. Dass GitHub inzwischen
auf `main` zeigt, bekommt dieser Klon nicht mit – ohne die Spiegelung sieht
Home Assistant kein Update mehr, ohne dass irgendwo ein Fehler erscheint.

Der Branch ist also kein zweiter Entwicklungszweig, sondern ein reiner Abzug für
den Supervisor. Er darf nie eigene Commits bekommen.

Aufheben ließe sich das nur, indem das Repository in Home Assistant entfernt und
neu hinzugefügt wird – dazu müsste das Add-on deinstalliert werden, was `/data`
samt Datenbank löscht. Solange das nicht ausdrücklich gewünscht ist: spiegeln.

## Version und Changelog

Home Assistant erkennt ein Update ausschließlich an der Versionsnummer im
Manifest. Jede ausgelieferte Änderung braucht deshalb:

1. `budget_tracker/config.yaml`: `version` erhöhen.
2. `budget_tracker/CHANGELOG.md`: Eintrag ganz oben, in derselben Sprache und
   Ausführlichkeit wie die bestehenden – was sich ändert, und *warum*.

`app/config.py: version()` liest die Nummer aus dem Manifest, damit sie nicht an
zwei Stellen gepflegt werden muss.

## Tests

```
cd budget_tracker && pytest
```

Die Suite läuft ohne Netz und ohne installiertes `pytr`; beides ist Absicht.
Wer an der Trade-Republic-Anbindung arbeitet, sollte zusätzlich einmal *mit*
installiertem `pytr` laufen lassen – nur dann greifen die Pfade, die es
importieren.

## Sprache

Oberfläche, Changelog, Kommentare und Testnamen sind deutsch. Kommentare
erklären, *warum* etwas so ist – meist der Fehler, der ohne diese Zeile
entstünde –, nicht was der Code tut.
