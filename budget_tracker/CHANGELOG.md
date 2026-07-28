# Changelog

## 1.8.0 - 2026-07-28

- Neu: Auf der Forecast-Seite von Haus Kredit zeigt eine deutliche Statuszeile unterhalb der Zielfortschritts-Anzeige an, ob das Jahresziel bis zum Reset-Datum (Sondertilgung) voraussichtlich erreicht wird – grün mit Häkchen bei "erreicht", rot mit Warnsymbol und fehlendem Betrag bei "nicht erreicht". Die Prognose summiert dafür den aktuellen Saldo plus alle bis zum Reset-Datum noch offenen Forecast-Vorkommen dieses Topfs.
- Auf allen Forecast-Seiten zeigt die Regel-Übersicht ganz unten jetzt "erste Buchung" und "letzte Buchung" (die tatsächlich gebuchten Datumsgrenzen) statt des reinen Anker-Tags, sofern die Regel schon mindestens einmal gegriffen hat – aussagekräftiger als der Kalendertag, der nichts über tatsächliches Eintreffen aussagt. Ohne bisherige Buchung entfällt die Angabe.

## 1.7.0 - 2026-07-28

- Neu: Forecast-Regeln und offene Forecast-Vorkommen lassen sich jetzt vollständig bearbeiten. Regeln bekommen ein Bearbeiten-Formular auf der Forecast-Seite (Topf, Bezeichnung, Betrag, Rhythmus, Anker-Tag, Start/Ende); dabei werden ihre noch offenen, nicht gebuchten Vorkommen mit den neuen Werten neu erzeugt, während bereits gebuchte oder bewusst gelöschte Vorkommen als reales bzw. bewusst getroffenes Faktum unangetastet bleiben. Offene Vorkommen (aus einer Regel oder frei angelegt) bekommen zusätzlich zu verschieben/löschen/verknüpfen ein eigenes Bearbeiten-Formular für Bezeichnung, Betrag und Datum.
- Fehlerbehebung: Das Umbuchungs-Symbol (Pfeil) zwischen den beiden Töpfen einer Topf-Umbuchung wurde in der mobilen Buchungen-Liste ohne Größenbegrenzung gerendert und füllte dadurch die ganze Kartenbreite aus.

## 1.6.1 - 2026-07-28

- Fehlerbehebung: Das Dropdown zum manuellen Verknüpfen eines offenen Forecast-Vorkommens schlug bisher jede Buchung vor, die noch keinem Forecast-Vorkommen zugeordnet war – auch Buchungen, die bereits automatisch oder manuell einem Topf zugewiesen waren (z.B. per Zins- oder Verwendungszweck-Treffer ohne passendes Vorkommen). Eine Verknüpfung hätte deren Topf und Titel stillschweigend überschrieben. Vorgeschlagen werden jetzt nur noch reale CSV-Buchungen, die noch komplett offen sind (kein Topf zugewiesen).

## 1.6.0 - 2026-07-28

- Neu: eine manuell erfasste Buchung lässt sich auf ihrer Detailseite nachträglich in eine Topf-Umbuchung umwandeln – für Fälle, in denen sich zeigt, dass eine als reale Bewegung erfasste Buchung eigentlich nur eine virtuelle Verschiebung zwischen zwei Töpfen war. Die Buchung wird dabei 1:1 durch eine gleichwertige Topf-Umbuchung ersetzt (Richtung aus dem Vorzeichen abgeleitet, nur der Gegen-Topf muss gewählt werden); der Kontostand insgesamt bleibt gleich, da eine Topf-Umbuchung rein virtuell ist. Reale CSV-Buchungen bleiben davon ausgenommen, da sie unveränderliches Bankfaktum sind.
- Der Button „Topf-Umbuchung anlegen“ ist von der Startseite verschwunden – erreichbar ist die Funktion jetzt nur noch über das Kontextmenü oben rechts (Mehr) oder nachträglich über eine bestehende Buchung.

## 1.5.0 - 2026-07-27

- Neu: offene Forecast-Vorkommen (aus einer Regel oder einer manuell geplanten Buchung) lassen sich auf der Forecast-Seite jetzt löschen – z.B. für eine Standard-Sparrate, die es nie geben wird. Ein regelbasiertes Vorkommen wird dabei nicht wirklich aus der Datenbank entfernt, sondern nur als ignoriert markiert: so bleibt sein Zeitfenster belegt und die Regel legt bei der nächsten Prüfung kein neues Vorkommen für denselben Zeitraum an. Aus Forecast, Prognose und Zuordnung verschwindet es trotzdem vollständig. Bereits gebuchte oder verknüpfte Vorkommen lassen sich weiterhin nicht löschen.
- Der „Stand“ auf der Startseite zeigt jetzt das Datum der neuesten Buchung statt des heutigen Kalendertags – dadurch ist auf einen Blick erkennbar, wie aktuell die importierten Daten tatsächlich sind. Vor dem ersten Import steht dort „Noch keine Buchungen importiert“.

## 1.4.1 - 2026-07-27

- Fehlerbehebung: seed-data.json unterstützt jetzt den Schlüssel `buchungen` für einmalige geplante Buchungen (z.B. Öltank-Füllungen, Elternzeit-Zahlungen) – der Bootstrap-Import las bisher nur `konfiguration`, `toepfe` und `regeln`, sodass dieser Abschnitt beim First-Start stillschweigend ignoriert wurde.

## 1.4.0 - 2026-07-27

- Neu: Buchungen aus der Zuordnen-Liste (real importiert, in der Vergangenheit, noch keinem Topf zugeordnet) lassen sich jetzt löschen – direkt in der Liste oder auf der Detailseite –, für Karteileichen wie Test-Buchungen, die sich nie sinnvoll zuordnen lassen. Bereits einem Topf zugeordnete Buchungen bleiben unlöschbar, da sie in den Topf-Saldo eingeflossen sind. Taucht dieselbe transaction_id in einem späteren CSV-Import erneut auf, wird die Buchung wieder angelegt.

## 1.3.2 - 2026-07-27

- Forecast-Datumstoleranz von ±3 auf ±7 Tage angehoben: wiederkehrende Überweisungen rutschen an Monatsgrenzen durch Wochenenden/Feiertage öfter mehrere Tage in den Folgemonat, wodurch das Vorkommen trotz korrekt zugeordneter Buchung als „noch nicht gebucht“ stehen blieb.

## 1.3.1 - 2026-07-27

- Fehlerbehebung: Der Verwendungszweck-Abgleich verglich Topfnamen als reinen Text-Teilstring, sodass z.B. „Hauskredit“ (ohne Leerzeichen, wie es Banken oft schreiben) nicht auf den Topf „Haus Kredit“ traf und trotz passender Regel unzugeordnet blieb. Der Abgleich normalisiert Leer- und Sonderzeichen jetzt auf beiden Seiten vor dem Vergleich.

## 1.3.0 - 2026-07-27

- Neu: offene Forecast-Vorkommen (aus einer Regel oder einer manuell geplanten Buchung) lassen sich auf der Forecast-Seite jetzt manuell mit einer realen, noch nicht verknüpften CSV-Buchung verknüpfen – für Fälle, in denen die automatische Betrags-/Datumstoleranz keinen Treffer findet. Die Buchung übernimmt dabei denselben sprechenden Namen und Topf wie bei einem automatischen Treffer und verschwindet aus der gestrichelten Zukunfts-Ansicht.

## 1.2.1 - 2026-07-27

- Der Titel-Vorschlag bei manueller Zuordnung (Zuordnen-Liste und „Topf zuweisen“) wird jetzt automatisch mit dem CSV-Verwendungszweck (`payment_reference`) vorbefüllt, falls vorhanden – bleibt weiterhin frei änderbar.

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
