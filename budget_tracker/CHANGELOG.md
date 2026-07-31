# Changelog

## 1.30.2 - 2026-07-31

- **Der Hinweis zu einem fehlgeschlagenen Trade-Republic-Abgleich nennt jetzt den Grund** statt pauschal „letzter Abgleich fehlgeschlagen" – meistens „Die Sitzung ist abgelaufen – bitte neu anmelden.", denn genau das ist der mit Abstand häufigste Fall. Die Trade-Republic-Websession hält erfahrungsgemäß nur etwa einen Tag, danach verlangt Trade Republic serverseitig eine neue Anmeldung samt Bestätigung in der App – ein pauschales „fehlgeschlagen" ließe das wie einen echten Fehler aussehen, den es zu untersuchen gilt.
- Der Grund stand technisch schon vorher bereit (`tr_sync.status()["meldung"]`), wurde auf der Startseite aber verworfen zugunsten eines festen Textes.
- Test-Suite auf 410 Tests.

## 1.30.1 - 2026-07-31

- **Auf der Startseite steht jetzt „Letzter Abgleich" mit Datum und Uhrzeit (lokale Zeit) unter dem Kontostand** – der Zeitpunkt der letzten erfolgreichen Abfrage über die Trade-Republic-Schnittstelle, sichtbar ohne extra auf die Trade-Republic- oder Depot-Seite zu wechseln. Erscheint nur, wenn ein Konto verbunden ist.
- **Der bisherige „Stand"-Hinweis (Datum der zuletzt importierten Buchung) ist dafür entfallen.** `neuestes_buchungsdatum()` war dadurch ungenutzt und wurde entfernt.
- Test-Suite auf 409 Tests.

## 1.30.0 - 2026-07-31

- **Jede Position im Depot zeigt jetzt ihren Anteil am Gesamtdepot** – prominent, direkt neben dem Namen, dazu ein Balken darunter. Der Anteil bezieht sich auf den Wert der Wertpapiere allein, nicht auf Wertpapiere plus Cash: sonst würde jede Einzahlung aufs Verrechnungskonto alle Anteile verschieben, ohne dass sich am Depot etwas geändert hätte.
- **Im Gegenzug fielen Stückzahl, Kurs und ISIN aus der Detailzeile** – geblieben sind Einstand und Gewinn/Verlust je Position. Das Prozent war der Wunsch, alles Weitere trat dafür zurück.
- Die Rechnung steht in `app/tr_depot.py: anteile()`, nicht im Template – ein Snapshot ganz ohne Wert (frisch angelegt, noch keine Position mit Kurs) liefert überall 0 % statt einer Division durch null.
- Test-Suite auf 406 Tests.

## 1.29.0 - 2026-07-30

- **Alle Zeitangaben stehen jetzt in lokaler Zeit** statt in UTC – und ohne das Kürzel dahinter, das nur nötig war, weil die Zahl davor eine Erklärung brauchte. Betroffen waren sieben Stellen: letzter Abgleich und Zeitpunkt des letzten Laufs (Trade Republic), letzter Scan und zuletzt importiert (Mehr), der Depot-Stand auf der Depot-Seite **und** auf der Startseite sowie „Importiert" in der Buchungs-Detailansicht. Im Sommer waren das zwei Stunden Unterschied – genug, um einen frischen Abgleich für veraltet zu halten.
- Gespeichert wird unverändert UTC; umgerechnet wird erst bei der Anzeige, an einer einzigen Stelle (`app/dateutils.py: nach_lokaler_zeit`). Die Zeitzonen-Behandlung der Timeline-Zeitstempel benutzt jetzt dieselbe Stelle statt einer eigenen Kopie.
- Test-Suite auf 399 Tests, darunter einer, der jede Seite darauf prüft, dass nirgends mehr „UTC" steht.

## 1.28.0 - 2026-07-30

- **Der Aufbau eines Events wird jetzt vollständig protokolliert**, wenn sich kein Verwendungszweck finden lässt: Abschnittstyp, Beschriftungen und die *Art* der Werte („Zeichenkette der Länge 23", „Objekt mit den Schlüsseln text und icon") – nie deren Inhalt. Die bisherige Fassung zeigte nur beschriftete Tabellenfelder und ließ damit offen, was in den unbenannten Abschnitten steckt.
- **Ein freier Textabschnitt gilt als letzter Ausweg für den Verwendungszweck.** Manche Ereignistypen führen kein beschriftetes Feld, sondern hängen den Text als Absatz an. Er wird nur genommen, wenn kein beschriftetes Feld gefunden wurde, und der Griff dorthin steht im Protokoll.
- **Der Abgleich holt Verdachtsfälle nicht mehr bei jedem Lauf neu ab.** Bereits vorgelegte Bewegungen galten nur bei der Übernahme als bekannt, nicht schon beim Einsammeln – jeder Lauf lud also ihre Details erneut, nur damit sie anschließend als Duplikat verworfen wurden. Im Protokoll sah das aus wie „4 neu und relevant", gefolgt von „1 neu, 3 bekannt".
- **Berichtigung: der HTTP 405 entstand nicht durch eine Umleitung.** Das Protokoll weist „Umleitungen: keine" aus – Trade Republic antwortet auf dem alten Anmeldepfad direkt so, weil er kein POST mehr annimmt. Fehlermeldung und die betreffenden Code-Kommentare sagen das jetzt richtig. An der Lösung ändert sich nichts: der neue Anmeldeweg (seit 1.21.0) umgeht ihn.

## 1.27.0 - 2026-07-30

- **Der Verwendungszweck wird jetzt im ganzen Detail gesucht**, nicht mehr nur im Abschnitt „Übersicht". Trade Republic hat mit dem Girokonto neue Ereignistypen eingeführt (`BANK_TRANSACTION_INCOMING`/`_OUTGOING`), die ihre Angaben anders aufteilen – bei denen blieb das Feld leer, obwohl es in der App und im Transaktions-PDF zu sehen ist. Der verlässliche Anker ist die Beschriftung, nicht der Abschnitt, in dem sie steht. Zusätzlich akzeptiert werden „Zahlungsreferenz", „Betreff", „Nachricht", „Kommentar" und „Note".
- **Findet sich trotzdem keiner, notiert das Protokoll die vorhandenen Feld-Beschriftungen** – ausschließlich die Beschriftungen, nie deren Inhalt. Ohne das ließe sich ein unbekannt benanntes Feld nur finden, indem man den kompletten Datensatz protokolliert, und darin stünden Beträge, Namen und IBANs.
- Die neuen Ereignistypen werden auf die Typ-Bezeichnungen des CSV-Exports übersetzt (`TRANSFER_INBOUND`/`TRANSFER_OUTBOUND`) statt roh angezeigt.
- **Die Buchungs-Detailseite zeigt den Verwendungszweck** – die Zeile fehlte dort schlicht.
- **Fehlerbehebung: die Detailseite behauptete bei jeder Buchung „CSV-Import".** Der Text war fest verdrahtet und älter als die Spalte `quelle`; Buchungen aus der Schnittstelle wurden dadurch falsch ausgewiesen. Jetzt steht dort, woher die Buchung wirklich stammt.
- Test-Suite auf 390 Tests.

## 1.26.1 - 2026-07-30

- **Invarianten-Tests für den Forecast.** Die bisherigen Tests prüften einzelne Verhaltensweisen; diese prüfen die Eigenschaft, die immer gelten muss: *für jede Regel ist die Menge der offenen, unveränderten Vorkommen genau die Menge der Termine, die die Regel erzeugt – keiner doppelt, keiner fehlt.* Beide bisherigen Forecast-Fehler waren Verletzungen genau dieser Aussage (1.15.0 ein fehlender Termin, 1.26.0 ein doppelter) und wären damit aufgefallen, ohne dass man sie vorher kennen muss.
- Geprüft wird über die Anker-Tage 1, 15, 27, 28, 29, 30 und 31, für monatlich, jährlich und befristet, dazu die Monatsgrenzen im Einzelnen: kurze Monate kappen nur sich selbst, der Folgemonat kehrt zum Anker-Tag zurück, und im Schaltjahr ist der 29. Februar auch wirklich der Termin. Ergänzt um zwei Stabilitätsprüfungen (mehrfache Scans ändern nichts; eingeschleuste Altlasten werden von selbst eingesammelt) und eine, die die Geldwirkung festhält: ein doppelter Eintrag verschiebt den Prognose-Tiefpunkt, nach dem Aufräumen stimmt er wieder.
- Test-Suite auf 386 Tests.

## 1.26.0 - 2026-07-30

- **Fehlerbehebung (doppelte Forecast-Einträge, einer pro Monat):** Bis 1.15.0 leitete die Erzeugung den Anker-Tag durch Weiterzählen des Vormonats ab. Ein Anker-Tag 29–31 wurde damit vom Februar dauerhaft auf den 28. gekappt und blieb dort für den Rest des Jahres. Seit der Korrektur erzeugt dieselbe Regel wieder den richtigen Tag – die alten, gekappten Vorkommen blieben aber liegen, weil sie ein `generiert_fuer` tragen, das die Regel nie wieder trifft. Ergebnis: jeder Monat doppelt, und einzelnes Löschen half nicht. Solche Überbleibsel werden jetzt beim Scan entfernt. **Nach dem Update verschwinden die doppelten Einträge von selbst; die Prognose ändert sich dadurch.**
- Angefasst wird nur, was zweifelsfrei ein Überbleibsel ist: aus einer Regel erzeugt, noch offen, unverändert und innerhalb des Erzeugungszeitraums. Ein mit einer Buchung verknüpftes Vorkommen (Fakt), ein bewusst verworfenes (Entscheidung), ein von Hand verschobenes oder bearbeitetes, ein frei angelegtes sowie überfällige Erwartungen aus der Vergangenheit bleiben unberührt.
- Derselbe Mechanismus räumt auch auf, wenn das Enddatum einer Regel nachträglich vorgezogen wird – auch dort blieben bisher Vorkommen jenseits des neuen Endes stehen.
- Test-Suite auf 359 Tests.

## 1.25.0 - 2026-07-30

- **Neu: Forecast-Regeln lassen sich löschen** (Forecast → Regeln → bearbeiten → „Regel löschen"). Bisher fehlte dieser Weg vollständig: eine überflüssige oder versehentlich doppelt angelegte Regel war nicht mehr loszuwerden, und ihre Vorkommen einzeln zu löschen half nicht – der Verzeichnis-Scan legte sie binnen 30 Sekunden wieder an. Genau so entstehen scheinbar „doppelte" Forecast-Einträge, die sich nicht entfernen lassen.
- Gelöscht werden nur die **noch offenen** Vorkommen der Regel. Ein mit einer realen Buchung verknüpftes Vorkommen ist ein Fakt, ein bewusst verworfenes eine Entscheidung – beide bleiben bestehen und verlieren lediglich ihre Herkunft, stehen also danach wie ein frei angelegtes Vorkommen da.
- Test-Suite auf 351 Tests.

## 1.24.0 - 2026-07-30

- **Neu: Weicht der berechnete Kontostand vom echten ab, steht das auf der Startseite** unter „Zu tun", mit Verweis auf die Depot-Seite. Die App rechnet Startsalden plus alle Buchungen seit dem Startdatum – dasselbe, was Trade Republic auch tut; beide Zahlen müssen auf den Cent übereinstimmen. Bisher war die Abweichung nur zu sehen, wenn man die Depot-Seite aufrief.
- Bewusst **kein** Eintrag in der Zuordnen-Liste: eine Abweichung ist keine Buchung, es gibt nichts zuzuordnen, und dieselbe Zahl kann drei Ursachen haben – ein falscher Topf-Startsaldo (konstante Differenz), eine fehlende oder doppelt erfasste Buchung (wachsende Differenz) oder eine reservierte, noch nicht verbuchte Kartenzahlung (verschwindet beim nächsten Abgleich). Deshalb ein Hinweis mit Erklärung statt einer Aufgabe mit Knopf.
- **Kein Fehlalarm bei veraltetem Stand:** Kam nach dem letzten Depotstand noch eine Buchung herein, wird nichts gemeldet – sonst würden zwei verschiedene Zeitpunkte verglichen. Genau das passierte sonst, wenn die Sitzung abgelaufen ist und der Datei-Import weiterläuft.
- Test-Suite auf 344 Tests.

## 1.23.0 - 2026-07-30

- **Der Abgleich-Turnus ist einstellbar** – Add-on-Option `tr_sync_intervall_stunden`, **voreingestellt bleiben sechs Stunden** wie bisher. `0` schaltet den automatischen Abgleich ab; dann holt ausschließlich „Jetzt abgleichen". Die Trade-Republic-Seite zeigt an, was gerade gilt.
- Hintergrund, falls die Frage nach einer Sperre aufkommt: seltener abzufragen senkt das Risiko praktisch nicht. Der Bot-Schutz sitzt vor der **Anmeldung**, nicht vor den Abrufen, und ein Lauf besteht aus einer Handvoll Anfragen. Ganz ohne automatischen Lauf kann es sogar schaden – läuft die Sitzung mangels Nutzung ab, sind mehr Anmeldungen nötig, und genau die gehen durch den Schutz.
- Test-Suite auf 340 Tests.

## 1.22.0 - 2026-07-30

- **„Ist die gleiche Buchung – zusammenführen"** heißt der Knopf jetzt, der vorher „verwerfen" hieß. Seit 1.21.1 wird dabei nichts mehr weggeworfen: die vorhandene Buchung übernimmt, was ihr fehlt – vor allem den Verwendungszweck. Die alte Beschriftung beschrieb das Gegenteil dessen, was passiert. Der erklärende Text darüber sagt jetzt ausdrücklich, was Zusammenführen tut und was unangetastet bleibt. Eine Seite, die noch vor der Umbenennung geöffnet wurde, funktioniert weiter.
- **Neu: Depot-Kachel auf der Startseite**, unter den vier Töpfen, mit Gesamtwert und Stand. Bewusst als eigener Abschnitt neben den Töpfen und nicht in ihrer Summe: der Depotwert ist kein Guthaben auf dem Cashkonto, fließt in keinen Topf-Saldo und in keine Prognose ein – die Kachel sagt das auch. Ohne abgerufenen Stand erscheint sie gar nicht.
- Test-Suite auf 335 Tests.

## 1.21.1 - 2026-07-30

Der erste echte Abgleich hat bestätigt, dass Datei-Export und Schnittstelle **unterschiedliche Transaktionsnummern** für dieselbe Bewegung vergeben. Daraus folgen zwei Korrekturen.

- **Fehlerbehebung (doppelte Beträge beim Datei-Import):** Die Dopplungsprüfung lief nur beim Abgleich über die Schnittstelle. Eine CSV-Datei, die eine bereits per Schnittstelle geholte Buchung enthält, wäre also ungeprüft ein zweites Mal importiert worden – der Betrag hätte doppelt gezählt. Die Prüfung sitzt jetzt im gemeinsamen Übernahme-Kern und wirkt damit in beide Richtungen. Verdachtsfälle aus dem Datei-Import erscheinen auf derselben Seite zur Entscheidung, und die Import-Karte unter „Mehr" weist sie aus.
- **„Ist dieselbe Buchung – verwerfen" rettet jetzt den Verwendungszweck.** Es ist dieselbe Bewegung, aber nur die Fassung aus der Schnittstelle kennt das Feld „Referenz". Sie mitsamt dem Verdachtsfall wegzuwerfen hieße, genau das aufzugeben, wofür die Anbindung da ist. Ergänzt wird ausschließlich, was an der vorhandenen Buchung leer ist – eine gepflegte Angabe wird nie überschrieben, die Topf-Zuordnung bleibt unangetastet.
- Test-Suite auf 331 Tests.

## 1.21.0 - 2026-07-30

- **Neu: Anmeldung über die Bestätigung in der Trade-Republic-App.** Trade Republic hat die Web-Anmeldung umgestellt – statt eines vierstelligen Codes kommt eine Anfrage in die App, die dort angenommen wird. `pytr` kennt in der veröffentlichten Fassung nur den alten Weg (`/api/v1/auth/web/login`), und genau darauf antwortet der Bot-Schutz mit der Umleitung, aus der der HTTP 405 entsteht. Der aktuelle Weg (`/api/v2/auth/web/login`) ist jetzt eingebaut; der alte bleibt als Rückfall, falls die neue Anmeldung nicht antwortet.
- Die Anmeldeseite zeigt dabei „Bitte in der Trade-Republic-App bestätigen" und prüft alle drei Sekunden selbst nach – kein Tippen mehr, kein SMS-Countdown.
- **Falsche Zugangsdaten führen nicht mehr zu einem zweiten Versuch.** Lehnt Trade Republic Nummer oder PIN ab, wird abgebrochen statt auf den alten Weg auszuweichen – ein zweiter Versuch mit derselben falschen PIN bringt nur die Kontosperre näher.
- **Die Add-on-Version steht jetzt auf der Trade-Republic-Seite.** Gelesen aus dem Manifest, nicht ein zweites Mal im Quelltext gepflegt. Damit lässt sich nicht mehr verwechseln, welche Fassung gerade läuft.
- Grundlage sind wieder Endpunkte und Kopfzeilen aus dem Quelltext von [cdamken/tr-api](https://github.com/cdamken/tr-api), das den v2-Ablauf bereits fährt.
- Test-Suite auf 327 Tests.

## 1.20.0 - 2026-07-30

- **Vermutliche Ursache des Anmeldefehlers behoben: die Anfragen sahen nicht nach Browser aus.** `pytr` schickt als einzige Kopfzeile einen User-Agent. Der Bot-Schutz vor der Anmeldung bewertet aber auch die Herkunftsangaben – fehlen `Origin`, `Referer` und die `Sec-Fetch-*`-Angaben, wird die Anfrage zur Schutzprüfung umgeleitet, und genau daraus entsteht der HTTP 405: `requests` folgt der Umleitung und macht dabei aus dem POST ein GET, das der Zielpfad nicht kennt. Diese Kopfzeilen werden jetzt mitgeschickt.
- **Der Schutz-Token wird zusätzlich als Kopfzeile `X-aws-waf-token` gesendet**, nicht nur als Cookie. Die Weboberfläche von Trade Republic macht es genauso.
- Grundlage ist der Quelltext von [cdamken/tr-api](https://github.com/cdamken/tr-api), das denselben Weg geht und dazu festhält: „The Sec-Fetch-* and Origin/Referer trio is what tells TR's WAF that we're a same-site XHR from app.traderepublic.com. Without these you'll get blocked."
- Test-Suite auf 305 Tests.

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
