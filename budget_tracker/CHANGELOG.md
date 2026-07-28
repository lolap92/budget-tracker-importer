# Changelog

## 1.14.4 - 2026-07-28

- **Fehlerbehebung (Betrag verschwand):** Wurde eine bereits einem Topf zugeordnete Buchung nachträglich „als Umbuchung markiert", blieb ein damit verknüpftes Forecast-Vorkommen weiterhin als erledigt verbucht. Die Buchung zählte danach nicht mehr im Topf-Saldo und die Erwartung nicht mehr in der Prognose – der Betrag war aus beiden Sichten verschwunden. Das Vorkommen wird jetzt wieder freigegeben: Die Markierung sagt ja gerade aus, dass es sich nicht um die erwartete Ausgabe handelte, sondern um eine Verschiebung, die sich mit ihrer Gegenbuchung ausgleicht – die Erwartung steht also weiter aus und gehört zurück in die Prognose. Eine Umbuchung ist damit über ihren gesamten Lebenszyklus spurlos: 800 € raus und wieder rein lassen Kontostand, Topf-Saldo und Prognose exakt so stehen wie vorher.
- **Fehlerbehebung (doppelte Verknüpfung):** „Ist doch keine Umbuchung – automatisch neu zuordnen" ließ die automatische Zuordnung erneut laufen und hängte dabei ein *zweites* Forecast-Vorkommen an dieselbe Buchung. Beide galten dann als gebucht und fielen aus der Prognose, obwohl es nur eine reale Zahlung gab. Eine Buchung gehört jetzt garantiert zu höchstens einem Vorkommen.
- Die Übersicht weist unter dem Kontostand aus, welcher Teil davon noch keinem Topf zugeordnet ist („davon -1.250,00 € noch keinem Topf zugeordnet"). Der Kontostand enthält bewusst auch offene und schwebende Buchungen und bleibt damit deckungsgleich mit dem echten Kontoauszug; die Differenz zur Summe der vier Töpfe stand bisher unkommentiert zwischen zwei direkt untereinander liegenden Zahlen.
- Test-Suite auf 123 Tests erweitert, darunter Rendering-Smoke-Tests für alle Seiten (fangen Template-Fehler, die vorher erst im Betrieb als 500er aufgefallen wären).

## 1.14.3 - 2026-07-28

- **Fehlerbehebung (Datenverlust beim Import):** Scheiterte eine einzelne CSV-Zeile an einem Datenbank-Integritätsfehler, nahm der Import mit `rollback()` die komplette offene Transaktion zurück und verwarf damit alle bereits gelesenen Zeilen derselben Datei. Die Statistik meldete sie trotzdem als importiert, und der Watcher merkte sich die Datei als verarbeitet – die Buchungen waren endgültig weg. Jede Zeile läuft jetzt in einem eigenen SAVEPOINT; ein Fehler verwirft ausschließlich die betroffene Zeile.
- **Fehlerbehebung (falsche Prognose):** Forecast-Regeln erzeugten ihre Vorkommen rückwirkend ab dem Regel-Startdatum, ohne Untergrenze. Eine Regel mit Startdatum in der Vergangenheit – der Normalfall bei `seed-data.json` – legte für jeden vergangenen Monat ein Vorkommen an. Diese konnten nie eine reale Buchung finden, blieben dauerhaft offen und wurden in jedem Prognosemonat mitsummiert; bei einer Kreditrate lag die Prognose dadurch um ein Vielfaches daneben. Vorkommen entstehen jetzt frühestens ab dem Vormonat und nie vor dem Startdatum der Konfiguration. Bereits entstandene Karteileichen räumt Migration `0004` beim Update weg (nur offene, aus Regeln erzeugte Vorkommen – gebuchte, verworfene und frei angelegte bleiben unangetastet).
- **Fehlerbehebung (doppelte Zählung):** `start_datum` aus der Ersteinrichtung wurde nach dem Bootstrap nirgends mehr ausgewertet. Da der Trade-Republic-Export regelmäßig den kompletten Verlauf liefert, wurden Bewegungen von vor dem Startdatum zusätzlich zu den Topf-Startsalden verbucht – Kontostand und Topf-Salden waren dauerhaft falsch. Der Import überspringt solche Zeilen jetzt und weist sie in der Import-Statistik als `vor_startdatum` aus; die manuelle Erfassung lehnt sie mit einer Meldung ab.
- **Fehlerbehebung (Anker-Tag):** Bei einer monatlichen Regel mit Anker-Tag 29–31 wurde das nächste Fälligkeitsdatum aus dem bereits gekappten Vormonatsdatum weitergezählt. Nach dem Februar fiel die Regel dadurch für den Rest des Jahres dauerhaft auf den 28. zurück (31.01 → 28.02 → 28.03 → 28.04). Der Anker-Tag wird jetzt für jeden Monat neu abgeleitet (31.01 → 28.02 → 31.03 → 30.04).
- Neu: Test-Suite (`pytest`, 106 Tests) für die Berechnungs- und Importlogik – Salden, Kontostand, Einzel- und Gesamtprognose, Sondertilgungs-Status, Zielfortschritt, Zeitachse, CSV-Parsing und -Dedublizierung, Forecast-Generierung, automatische Zuordnung und die Zustandsübergänge der Bank-Umbuchung. Ausführen mit `pip install -r requirements-dev.txt && pytest` im Ordner `budget_tracker/`.

## 1.14.2 - 2026-07-28

- Die Topf-Filter-Buttons auf der Buchungen-Seite sind wieder so kompakt wie zuvor (statt auf volle Breite gestreckt), umbrechen aber jetzt in zwei Reihen statt horizontal zu scrollen.

## 1.14.1 - 2026-07-28

- Fehlerbehebung: Das Fälligkeitsdatum in der Haus-Kredit-Statuszeile auf der Startseite ("Wird (nicht) erreicht (X € zum TT.MM.)") wurde rein arithmetisch aus Anker-Tag und Startdatum der Sondertilgung-Regel neu berechnet und konnte dadurch vom tatsächlich auf der Forecast-Seite geplanten Vorkommen abweichen (z.B. nach einer manuellen Verschiebung). Das Datum stammt jetzt aus dem nächsten offenen Forecast-Vorkommen dieser Regel, konsistent mit der Forecast-Seite.
- Die Topf-Filter-Buttons auf der Buchungen-Seite stehen jetzt untereinander statt in einer horizontal scrollbaren Reihe – alle Töpfe sind ohne Scrollen nach rechts sichtbar.

## 1.14.0 - 2026-07-28

- Die Forecast-Seite startet jetzt standardmäßig auf dem Topf Sonderausgaben statt auf dem ersten Topf in der Reihenfolge (Haus Kredit).
- Neu: Im Topf-Filter der Forecast-Seite gibt es jetzt "Alle Töpfe" – zeigt die kombinierte 12-Monats-Prognose über das gesamte Konto (aktueller Gesamtsaldo, Chart, Monats-Streifen, Tiefpunkt-Status). Da Forecast-Regeln und die Buchungen-Liste inhärent an einen einzelnen Topf gebunden sind, bleiben sie in dieser Ansicht ausgeblendet.

## 1.13.0 - 2026-07-28

- Auf der Startseite zeigt der Haus-Kredit-Topf jetzt statt der bisherigen Ziel/Reset-Zeile eine direkte Aussage zur jährlichen Sondertilgung: "Wird erreicht (X € zum TT.MM.)" bzw. "Wird nicht erreicht (X € zum TT.MM.)", grün bzw. rot. Betrag und Fälligkeitsdatum stammen automatisch aus der hinterlegten "Sondertilgung"-Forecast-Regel (jährlicher Rhythmus, Anker-Tag), nicht mehr aus separat zu pflegenden Ziel-Feldern – beide Werte bleiben damit immer mit der Regel in Sync. Geprüft wird, ob Saldo plus alle bis zum Fälligkeitstermin erwarteten Buchungen (ohne die Sondertilgung selbst) den Betrag decken.

## 1.12.0 - 2026-07-28

- "Buchung anlegen" / "Regel anlegen" auf der Buchungen-Seite sowie die Anlegen-Buttons auf der neuen Forecast-Regeln-Unterseite haben jetzt einen festen, akzentfarbenen Rahmen statt des gestrichelten. Die beiden Formulare der Regeln-Unterseite ("Neue Regel anlegen" / "Einmalige geplante Buchung anlegen") stehen dafür jetzt oben statt als reiner Textlink am Seitenende.

## 1.11.0 - 2026-07-28

- Die Forecast-Seite ist jetzt deutlich kürzer: die Regel-Karten und die Anlegen-Formulare ("Neue Regel anlegen" / "Einmalige geplante Buchung anlegen") sind von der Hauptseite auf eine eigene, fokussierte Unterseite umgezogen. Direkt unter dem Prognose-Chart führt ein kompakter Button "Forecast-Regeln (n) →" dorthin; der "+"-Button im Header springt jetzt direkt zum Anlegen-Formular auf dieser Unterseite.

## 1.10.0 - 2026-07-28

- Die Forecast-Regeln-Übersicht ganz unten auf der Forecast-Seite ist jetzt übersichtlicher: jede Regel steht als eigene Karte (Name, Betrag, Rhythmus als Chip, erste Buchung/Enddatum) statt als gedrängte Textzeile, mit einem deutlichen "✎ Bearbeiten"-Link, der das vorbefüllte Bearbeiten-Formular direkt darunter aufklappt.

## 1.9.2 - 2026-07-28

- Fehlerbehebung: In der Forecast-Regeln-Übersicht fehlte "erste Buchung" bei Regeln, die noch nie real getroffen haben (nur zukünftige geplante Vorkommen) – jetzt wird stattdessen das früheste geplante Datum angezeigt. Bei unbefristeten Regeln (kein Enddatum) fiel "letzte Buchung" außerdem fälschlich wie ein Ende der Regel aus, obwohl sie einfach nur bisher noch nicht weiter real getroffen hat – "letzte Buchung" wird jetzt generell nicht mehr angezeigt, das tatsächliche Ende einer befristeten Regel steht bereits separat ("bis ...").

## 1.9.1 - 2026-07-28

- Fehlerbehebung: Die "Ziel wird voraussichtlich (nicht) erreicht"-Anzeige bei Haus Kredit erschien nur, wenn unter "Ziel & Reset bearbeiten" ein Reset-Datum (Sondertilgung) gesetzt war - ohne Reset-Datum fehlte der Text komplett. Die Prognose greift jetzt ohne Reset-Datum auf das Ende des sichtbaren 12-Monats-Zeitraums zurück ("Ziel wird in den nächsten 12 Monaten voraussichtlich erreicht/nicht erreicht"), sodass die Aussage immer sichtbar ist.

## 1.9.0 - 2026-07-28

- Neu: Auf der Forecast-Seite ist jetzt für jeden Monat genau erkennbar, welchen Stand ein Topf voraussichtlich haben wird. Ein horizontal scrollbarer Monats-Streifen unter dem Kontostand zeigt für alle 12 Monate der Prognose Monat und exakten Saldo als Kachel (aktueller Monat hervorgehoben, Minus-Monate rot) – für jeden Topf, auch für Haus Kredit, das bisher gar keine Monats-für-Monats-Ansicht hatte. Zusätzlich ist der Prognose-Chart (bei den anderen Töpfen) jetzt interaktiv: ein Tipp auf einen Punkt zeigt Monat und genauen Betrag über dem Chart an, statt nur den reinen Tiefpunkt auslesen zu können.

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
