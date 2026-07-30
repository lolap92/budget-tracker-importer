# Changelog

## 1.19.3 - 2026-07-30

- **Das Feld für den Schutz-Token ist jetzt sichtbar.** Es steckte in einem aufklappbaren Bereich, der sich in der Home-Assistant-App auf dem Handy nicht öffnen ließ – die eine Eingabe, die den Bot-Schutz umgeht, war damit unerreichbar. Es ist jetzt ein gewöhnliches, optionales Feld.
- **Anleitung für PC und Handy** steht direkt unter dem Formular, inklusive eines Lesezeichen-Schnipsels für Mobilgeräte, wo es keine Entwicklerwerkzeuge gibt.
- **Hinweis auf das Netz:** Der Token sollte von einem Gerät im selben Netz wie Home Assistant stammen – Trade Republic kann ihn sonst wegen der abweichenden Herkunft ebenfalls ablehnen.

## 1.19.2 - 2026-07-30

- **HTTP 405 bei der Anmeldung wird erklärt.** Trade Republic verschickt auf diesem Pfad selbst kein 405. Der Status entsteht unterwegs: die Anfrage wird umgeleitet, `requests` folgt der Umleitung und macht dabei aus dem POST ein GET, das der Zielpfad nicht kennt. Umgeleitet wird zur Bot-Schutz-Prüfung – mit Telefonnummer und PIN hat das nichts zu tun. Die Meldung sagt das jetzt und verweist auf das Feld für den Token aus dem Browser.
- **Jede HTTP-Antwort steht mit Methode, Pfad und Status im Add-on-Protokoll**, Umleitungen inklusive. Ohne diese Kette ist ein solcher Fehlschlag nicht zu deuten. Der Bestätigungscode steht im Pfad der Abschluss-Anfrage und wird dabei ausgeblendet.
- **Fehlerbehebung (Depot wäre leer geblieben):** Trade Republic hat die Depot-Abfrage umgestellt – `compactPortfolio` heißt jetzt `compactPortfolioByType`, verlangt die Depotnummer aus den Kontoeinstellungen und liefert die Positionen nach Kategorien gruppiert, mit der ISIN im Feld `isin` statt `instrumentId`. Die in 1.19.0 verwendete Abfrage stammt aus der veröffentlichten `pytr`-Version und kennt die Umstellung noch nicht; das Depot wäre dauerhaft leer geblieben. Beide Formate werden jetzt gelesen, und schlägt die neue Abfrage fehl, wird die alte versucht.
- Test-Suite auf 300 Tests.

## 1.19.1 - 2026-07-30

Fehlersuche bei der Trade-Republic-Anmeldung – die bisherige Meldung war unbrauchbar.

- **Die Anmeldung sagt jetzt, woran sie gescheitert ist.** Bisher endete *jeder* Fehlschlag in „Anmeldung konnte nicht gestartet werden. Stimmen Telefonnummer und PIN?" – auch dann, wenn Trade Republic die Anfrage gar nicht erst angesehen hatte. Unterschieden werden jetzt: abgelehnte Zugangsdaten (HTTP 401), Abweisung durch den Amazon-Bot-Schutz (403, hat mit PIN und Nummer nichts zu tun), zu viele Versuche (429), Fehlermeldungen von Trade Republic selbst und Netzfehler. Der vollständige Hergang steht mit Statuscode im Add-on-Protokoll.
- **Die Telefonnummer wird normalisiert.** `015112345678`, `+49 151 1234 5678`, `0049...` und Schreibweisen mit Bindestrichen oder Klammern führen jetzt alle zur selben Nummer. Vorher wurde alles außer der exakten `+49…`-Form von Trade Republic abgelehnt – ununterscheidbar von einer falschen PIN.
- **Der Bot-Schutz-Token lässt sich von Hand hinterlegen.** Das Add-on löst ihn selbst, ohne Browser. Scheitert das, kann der `aws-waf-token`-Cookie aus einer Browser-Sitzung eingetragen werden; ein aufklappbarer Bereich im Anmeldeformular erklärt, wo er steht. Scheitert die automatische Ermittlung, wird der Versuch trotzdem unternommen – erst die Antwort zeigt, ob der Token überhaupt nötig war.
- **Die eingetippte Nummer bleibt nach einem Fehlschlag im Formular stehen**, statt für den nächsten Versuch erneut getippt werden zu müssen.
- Fehlt `pytr`, erscheint eine Meldung statt eines Serverfehlers.
- Der Logger von `pytr` wird fest auf INFO gesetzt. Er steht intern auf DEBUG und würde dort vollständige Antworten protokollieren – darunter die Anmeldedaten. Dass das bisher nicht sichtbar wurde, lag allein an seiner Handler-Einstellung.
- Test-Suite auf 293 Tests.

## 1.19.0 - 2026-07-30

- **Neu: Depotstand** unter „Mehr → Depot". Jeder Abgleich mit Trade Republic holt in derselben Verbindung die Positionen mit Stückzahl, Kurs, Einstand und Wert sowie den Cash-Bestand mit. Bewusst eine eigene Seite und nicht die Startseite: der Depotwert ist weder ein Topf noch Teil des Kontostands und **fließt in keine Berechnung ein**. Scheitert der Abruf, bleiben die Buchungen davon unberührt – sie sind das Wesentliche.
- **Der Kontostand lässt sich jetzt gegenprüfen.** Die App rechnet ihn aus den Topf-Startsalden und allen Buchungen seit dem Startdatum, Trade Republic kennt den echten Bestand. Die Depot-Seite stellt beide nebeneinander und weist die Abweichung aus – eine fehlende oder doppelt erfasste Buchung fällt damit sofort auf, statt jahrelang unbemerkt in den Salden zu stecken.
- Positionen ohne abrufbaren Kurs fallen aus der Anzeige heraus, statt den Gesamtwert stillschweigend zu verfälschen. Anleihen werden erkannt und ihr Kurs vom Prozent des Nennwerts umgerechnet – sonst stünde ihr Wert um Faktor 100 zu hoch in der Summe.
- Es wird immer nur der jüngste Stand gespeichert; eine Historie würde mit jedem Abgleich wachsen, ohne dass sie irgendwer auswertet.
- Test-Suite auf 274 Tests.

## 1.18.0 - 2026-07-30

- **Neu: Trade Republic lässt sich direkt anbinden** (Mehr → Trade Republic). Anmeldung über den Web-Login mit Telefonnummer, PIN und dem vierstelligen Code aus der App; danach gleicht die App alle sechs Stunden selbstständig ab, ein Knopf holt jederzeit sofort. Gelesen wird ab dem jüngsten bekannten Buchungsdatum minus 14 Tage, nie vor dem Startdatum.
- **Der Verwendungszweck ist da.** Der CSV-Export der Trade-Republic-App führt zwar eine Spalte `payment_reference`, füllt sie aber nie – ohne diesen Text kann die automatische Topf-Zuordnung über den Verwendungszweck grundsätzlich nicht greifen, und praktisch jede Buchung landet in der Review-Liste. Über die Schnittstelle steht er zur Verfügung (Feld „Referenz" der jeweiligen Buchung), dazu Name und IBAN der Gegenseite.
- **Die PIN wird nirgends gespeichert** – weder in der Datenbank noch in einer Datei. Sie wird ausschließlich für den Anmeldevorgang selbst benutzt; erhalten bleibt nur die Sitzung als Cookie-Datei unter `/data/pytr/`, die ein Add-on-Update übersteht. Ein vollautomatischer Dauerbetrieb ist wegen des Bestätigungscodes nicht möglich: läuft die Sitzung nach einigen Wochen ab, meldet die Übersicht „Anmeldung erforderlich".
- **Schutz vor doppelten Buchungen.** Datei-Export und Schnittstelle stammen aus zwei verschiedenen Diensten von Trade Republic – schon die Typbezeichnungen unterscheiden sich (`TRANSFER_INBOUND` gegen `INCOMING_TRANSFER`) – und vergeben möglicherweise unterschiedliche Transaktionsnummern. Sieht eine abgerufene Bewegung aus wie eine bereits vorhandene Buchung, wird sie weder importiert noch verworfen, sondern zur Entscheidung vorgelegt: automatisch übernehmen würde den Betrag doppelt zählen, automatisch verwerfen ihn verlieren. Als schärfster Hinweis dient der in der Transaktionsnummer eingebettete Zeitstempel (Trade Republic vergibt UUIDs der Version 7, deren erste 48 Bit der Erzeugungszeitpunkt in Millisekunden sind).
- **Der CSV-Import bleibt unverändert bestehen** und ist die Rückfallebene, falls die inoffizielle Schnittstelle ausfällt. Beide Wege nehmen denselben Übernahme-Kern, dedupliziert wird weiterhin über die `transaction_id`.
- **Basis-Image ist jetzt Debian statt Alpine.** `pytr` hängt zwingend an `playwright`, wovon es kein musl-Wheel gibt – unter Alpine ließe es sich gar nicht installieren. Der Browser wird nie gestartet (der Anmelde-Token wird rein in Python geholt), sein mitgelieferter Treiber deshalb beim Bauen wieder entfernt: 131 der 270 MB.
- Test-Suite auf 260 Tests.

## 1.17.0 - 2026-07-30

Vorbereitung der Trade-Republic-Schnittstelle. **An der Oberfläche und an jeder Berechnung ändert sich nichts** – der CSV-Import verhält sich exakt wie bisher und bleibt dauerhaft der Weg, der auch ohne Anmeldung funktioniert.

- **Der Übernahme-Kern ist jetzt geteilt** (`app/import_core.py`). Dedublizierung über die `transaction_id`, der Startdatum-Filter und die automatische Topf-Zuordnung standen bisher mitten in der CSV-Leseschleife. Sie stehen jetzt für sich, damit eine Bewegung aus der Schnittstelle exakt denselben Weg nimmt wie eine CSV-Zeile – inklusive des SAVEPOINTs, der bei einem Integritätsfehler nur die eine Buchung verwirft. In `app/csv_import.py` bleibt, was mit Dateien zu tun hat: Encoding, Trennzeichen, Zahlenformat, Datums- und Betragsparsing.
- **Neue Spalte `quelle`** an jeder Buchung (`csv` / `api` / `manuell`), Migration `0006`. Bestehende Buchungen werden anhand der `transaction_id` zugeordnet (Präfix `manual-` → manuell, sonst CSV). Sie dient der Anzeige und der Dopplungsprüfung, sobald beide Wege parallel laufen können; in keine Berechnung fließt sie ein.
- **Übersetzung Timeline-Event → Buchung** (`app/tr_events.py`), noch ohne Verbindung nach außen. Sie liest den Verwendungszweck aus dem Feld „Referenz" des Event-Details – genau die Angabe, die der CSV-Export der Trade-Republic-App in seiner Spalte `payment_reference` leer lässt – dazu Name und IBAN der Gegenseite. Stornierte Vorgänge und Events ohne Geldbewegung werden verworfen, Zeitstempel von UTC in lokale Zeit umgerechnet, und der Zins-Typ der Timeline (`INTEREST_PAYOUT`) auf den des CSV-Exports (`INTEREST_PAYMENT`) übersetzt, damit die Zins-Regel der Topf-Zuordnung weiter greift.
- Test-Suite auf 227 Tests.

## 1.16.1 - 2026-07-28

- **Fehlerbehebung: Topf-Umbuchungen mit Datum in der Zukunft werden abgelehnt.** Eine Topf-Umbuchung wirkt sofort – der Saldo summiert sie ohne Datumsbedingung, das Datum ist reine Dokumentation. Ein Datum in der Zukunft verschob deshalb Geld, das laut Anzeige erst später umziehen sollte, und der Eintrag landete in der Zeitachse unterhalb des „Aktueller Monat"-Trenners, obwohl er in der Zukunft datiert war. Das Datumsfeld ist jetzt auf heute begrenzt, der Server lehnt spätere Daten mit einer verständlichen Meldung ab. Bereits angelegte Umbuchungen mit Zukunftsdatum bleiben unverändert bestehen.

## 1.16.0 - 2026-07-28

- **Neu: Die Buchungsliste blättert.** Statt aller Einträge auf einer Seite werden 50 gezeigt, darunter „← neuere / ältere →" mit Seitenzahl und Gesamtanzahl. Der Topf-Filter bleibt beim Blättern erhalten. Nach ein paar Jahren CSV-Import wurde die Seite sonst mehrere tausend Einträge lang. Nebenbei behoben: bei mehreren Buchungen mit demselben Datum war die Reihenfolge nicht festgelegt – beim Blättern hätte ein Eintrag dadurch doppelt oder gar nicht erscheinen können.
- **Die Zeitachse auf der Forecast-Seite zeigt die 25 jüngsten vergangenen Einträge**, darunter einen Verweis auf die vollständige Liste des Topfs. Die geplanten Einträge oberhalb des Trenners bleiben ungekürzt – sie sind durch den 12-Monats-Horizont ohnehin begrenzt und alle handlungsrelevant.
- **„Buchung anlegen" heißt jetzt, was es tut.** Die Auswahl „Vergangenheit / Zukunft" hieß irreführend so, obwohl die geplante Variante auch ein bereits fälliges Datum akzeptiert – und das ist richtig so: eine fällige, aber noch nicht eingetroffene Erwartung bleibt sinnvollerweise in der Prognose, bis die reale Buchung sie auflöst. Die Optionen heißen jetzt „Ist schon passiert – sofort verbuchen" und „Wird noch erwartet – als geplante Buchung anlegen", der Hinweistext erklärt beide Fälle. Ergänzt wurden die bisher komplett fehlenden Prüfungen für geplante Buchungen: Betrag 0 und ein Datum vor dem Startdatum werden abgelehnt.
- Test-Suite auf 204 Tests.

## 1.15.0 - 2026-07-28

- **Fehlerbehebung (fehlende Monate im Plan):** Ob ein Monat schon eingeplant war, wurde über ein Zeitfenster um den berechneten Termin geraten. Das Fenster musste breit genug sein, um ein um einen Monat verschobenes Vorkommen wiederzuerkennen – 61 Tage – und war damit zwangsläufig auch breit genug, um bei einer monatlichen Regel den Nachbarmonat mitzuzählen. Folge: eine Lücke im Plan blieb dauerhaft unsichtbar, weil der Folgemonat sie „belegte". Besonders nach „Regel bearbeiten" fehlten still einzelne Monate. Die neue Spalte `generiert_fuer` hält den berechneten Termin unveränderlich fest, damit wird aus der Schätzung ein exakter Abgleich. Migration `0005` füllt sie für bestehende Vorkommen. **Nach dem Update füllt der nächste Scan die bisher unsichtbar fehlenden Monate auf – die Prognose ändert sich dadurch.** Bereits doppelt vorhandene Vorkommen werden bewusst nicht zusammengeführt: zwei Einträge am selben Tag können legitim sein (ein verschobener plus der reguläre).
- **Fehlerbehebung (Faktor-1000-Fehler beim Import):** Ein Betrag wie `1.234` ist für sich genommen nicht entscheidbar – englisch gelesen sind es 1,23 €, deutsch gelesen 1.234 €. Bisher wurde immer englisch gelesen. Das Zahlenformat wird jetzt aus der gesamten Datei abgeleitet (ein einziger eindeutiger Wert genügt) und für alle Zeilen konsistent angewendet. Lässt sich das Format nicht bestimmen, wird die mehrdeutige Zeile mit Meldung übersprungen statt geraten – ein um Faktor 1000 falscher Betrag fällt in keiner Summe auf.
- **Warnung bei jährlichen Regeln:** Der Monat einer jährlichen Regel stammt aus dem Startdatum, nur der Tag aus dem Anker-Tag. Passt beides nicht zusammen (Start 26.09., Anker-Tag 1), greift die Regel erst ein volles Jahr später. Das stand nirgends. Die Regel-Karte zeigt jetzt eine Warnung mit dem tatsächlichen ersten Fälligkeitsdatum, und beide Formulare erklären die Regel.
- **„Befristet" verlangt jetzt ein Enddatum.** Ohne Enddatum war der Rhythmus von „monatlich" nicht zu unterscheiden und lief entgegen seinem Namen unbegrenzt weiter. Zusätzlich wird ein Enddatum vor dem Startdatum abgelehnt.
- **Jahresziel und Reset entfernt.** Seit 1.13.0 leitet die Startseite Betrag und Fälligkeit der Sondertilgung aus der Forecast-Regel ab und bleibt damit automatisch mit ihr in Sync. Die alten, separat zu pflegenden Ziel-Felder waren daneben faktisch unerreichbar – das Bearbeiten-Formular erschien nur, wenn bereits ein Ziel gesetzt war, was ausschließlich über `seed-data.json` ging. Ein zweites, manuell gepflegtes Ziel lädt genau die Drift ein, die 1.13.0 beseitigt hat. Nebeneffekt: Haus Kredit zeigt jetzt wie alle anderen Töpfe den Prognose-Chart, der vorher von der Ziel-Anzeige verdrängt wurde. Die Datenbankspalten bleiben erhalten, damit bestehende `seed-data.json` weiter gelesen werden – es geht nichts verloren.
- Test-Suite auf 187 Tests.

## 1.14.5 - 2026-07-28

Sammelrelease für Darstellung, Fehlerverhalten und Eingabeprüfung – an keiner Berechnung ändert sich etwas.

- **Neu: CSV-Import ist jetzt einsehbar.** Unter „Mehr" zeigt eine Import-Karte das überwachte Verzeichnis, ob es gefunden wird, den letzten Scan, den letzten tatsächlichen Import und die Bilanz des letzten Laufs (gelesen / neu / schon bekannt / vor Startdatum übersprungen / nicht verarbeitet), inklusive Klartext-Meldungen wie „kein passendes Spaltenformat". Die Übersicht meldet sich nur, wenn etwas klemmt – fehlendes Import-Verzeichnis oder nicht verarbeitete Zeilen erscheinen als Zeile unter „Zu tun". Bewusst keine Dauer-Statusanzeige: der Watcher scannt alle 30 Sekunden, „letzter Scan vor 12 Sekunden" wäre nur Rauschen. Der Zeitpunkt des letzten Imports kommt aus der Datenbank und übersteht damit einen Neustart des Add-ons.
- **Fehler erscheinen im gewohnten Layout** statt als nacktes `{"detail": ...}` ohne Navigation. Betraf rund acht Routen (Zuordnen, Forecast-Vorkommen, Regel bearbeiten, Buchung löschen). „Einmalige geplante Buchung anlegen" hatte gar keine Fehlerbehandlung und quittierte einen Tippfehler im Betrag mit einem 500er – jetzt eine verständliche Meldung.
- **Eingabeprüfungen nachgezogen:** Ein Betrag von 0 war nur beim Bearbeiten einer Regel verboten, beim Anlegen ging er durch; der Rhythmus wurde gar nicht geprüft, ein unbekannter Wert erzeugte stillschweigend nie ein Vorkommen. Anlegen und Bearbeiten teilen sich jetzt dieselben Prüfungen. „Endgültig verbuchen" lehnt bereits abgeglichene oder zugeordnete Umbuchungen ab.
- Forecast-Vorkommen zeigen das vollständige Datum („erwartet 01.09.2026") statt nur den Monat – zwei Vorkommen im selben Monat waren vorher nicht unterscheidbar, obwohl der Tag fürs Matching zählt.
- Die Buchungen-Tabelle am Desktop kennzeichnet schwebende Umbuchungen als solche statt als schlichtes „offen" – am Desktop suchte man sie danach vergeblich unter „Zuordnen".
- Die Chip-Reihe über der Buchungsliste mischte Filter und Navigation: „Alle" war ein totes Element ohne Funktion, „Offen"/„Umbuchungen" sahen wie Filter aus, führten aber auf andere Seiten. Sie ist jetzt eine reine Sprungleiste zu den offenen Fällen und entfällt, wenn es nichts zu tun gibt. Gefiltert wird ausschließlich in der Topf-Reihe darunter.
- Bei Haus Kredit unterdrückte die Sondertilgungs-Zeile die Minus-Warnung – die Zeile war rot markiert, der Grund stand nirgends. Beide Angaben erscheinen jetzt nebeneinander.
- Die Zuordnen-Seite erklärt „als Umbuchung markieren" und „löschen", statt beide Schaltflächen unkommentiert nebeneinander zu stellen.
- „Maerz" heißt jetzt „März".
- Intern: `review_liste`/`unverknuepfte_buchungen` und `offene_umbuchungen`/`offene_umbuchungen_query` waren jeweils dieselbe Abfrage in zwei Fassungen – zusammengeführt. Test-Suite auf 155 Tests.

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
