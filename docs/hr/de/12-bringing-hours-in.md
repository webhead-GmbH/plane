# Stunden von anderswo übernehmen

Diese Seite ist für die Person, die das Team betreut, und zwar dann, wenn Stunden, Abwesenheiten oder Salden anderswo erfasst wurden — in einer alten Tabelle, im System davor — und hier landen sollen. Sie erklärt die drei Arten von Dateien, was in den Spaltenüberschriften stehen muss, wie die Prüfung abläuft, bevor etwas geschrieben wird, und wie Sie eine ganze Datei wieder herausnehmen. Sie geht davon aus, dass Ihre Tabelle aus Excel kommt.

Nur wer das Team betreut, kann diese Seite benutzen. Wenn Sie das nicht sind, ist „Meine Zeit — Ihr eigener Monat“ die Seite, die Sie suchen.

## Was auf dieser Seite steht

- [Wo Sie diese Seite finden](#wo-sie-diese-seite-finden)
- [Die drei Arten von Dateien](#die-drei-arten-von-dateien)
- [Mit der Vorlage anfangen](#mit-der-vorlage-anfangen)
- [Was die einzelnen Spalten bedeuten](#was-die-einzelnen-spalten-bedeuten)
- [Wie eine Dauer gelesen wird](#wie-eine-dauer-gelesen-wird)
- [Wie ein Datum gelesen wird](#wie-ein-datum-gelesen-wird)
- [Die Prüfung, bevor etwas geschrieben wird](#die-prüfung-bevor-etwas-geschrieben-wird)
- [Warum eine Zeile abgelehnt oder übersprungen wurde](#warum-eine-zeile-abgelehnt-oder-übersprungen-wurde)
- [Übernehmen](#übernehmen)
- [Was das Übernehmen nicht tut](#was-das-übernehmen-nicht-tut)
- [Eine ganze Datei zurücknehmen](#eine-ganze-datei-zurücknehmen)
- [Ein durchgerechnetes Beispiel](#ein-durchgerechnetes-beispiel)
- [Entscheiden Sie vor dem Start, wie weit Sie zurückgehen](#entscheiden-sie-vor-dem-start-wie-weit-sie-zurückgehen)
- [Häufige Stolperfallen](#häufige-stolperfallen)
- [Wenn Sie nicht weiterkommen](#wenn-sie-nicht-weiterkommen)

## Wo Sie diese Seite finden

1. Öffnen Sie in der Seitenleiste **Meine Zeit**.
2. Öffnen Sie rechts oben auf dieser Seite das Menü **…** und wählen Sie **Stunden aller Personen**. Sie sind jetzt auf **Teamzeit**.
3. Wählen Sie in der Zeile mit den Links neben dem Monatsnamen **Frühere Aufzeichnungen importieren**.

Die Seite öffnet sich mit einer Zeile grauem Text unter der Überschrift, einer umrandeten Karte mit einem Auswahlfeld und zwei Schaltflächen und ganz unten einer Liste mit der Überschrift **Früher importierte Dateien**. Wurde noch nie etwas importiert, steht dort **Es wurde noch nichts importiert.**

Steht dort statt der Karte **Sie haben keine Berechtigung für diese Ansicht**, dann ist Ihr Konto nicht als Teamleitung eingerichtet. Bitten Sie darum, das auf der Seite **Personen** zu ändern.

Ziehen Sie keine Datei auf die Karte. Hier fängt nichts eine fallen gelassene Datei auf; der Browser verlässt deshalb diese Seite und öffnet stattdessen die Datei, und Sie müssen sich zurückfinden. Nehmen Sie die Schaltfläche **Datei auswählen**.

## Die drei Arten von Dateien

Das Auswahlfeld heißt **Inhalt der Datei**. Es hat drei Möglichkeiten, und es entscheidet, wie Ihre Datei gelesen wird.

| Möglichkeit       | Was geschrieben wird                                                                         | Wo es danach zu sehen ist                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Stunden**       | Stunden, die jemand an einem bestimmten Tag gearbeitet hat, ohne ein Arbeitselement dahinter | Am Tag dieser Person, unter **Stunden ohne Arbeitselement**, mit der Kennzeichnung **Importiert** |
| **Abwesenheiten** | Tage, an denen jemand abwesend war und die bereits genehmigt sind                            | Auf der Seite **Abwesenheiten**, im Status **Genehmigt**                                          |
| **Anfangssalden** | Der Wert, von dem der laufende Saldo einer Person ausgeht                                    | Im Datensatz dieser Person, unter **Anfangssaldo**                                                |

Zwei Dinge über dieses Auswahlfeld sollten Sie wissen, bevor Sie anfangen.

Es steht immer zuerst auf **Stunden**, und es stellt sich nie von selbst zurück. Der häufigste Fehler am Anfang: **Abwesenheiten** wählen, **Vorlage herunterladen** drücken, die Vorlage ausfüllen und dann **Datei auswählen** drücken, ohne noch einmal zum Auswahlfeld zurückzugehen. Die Datei wird dann als Stunden gelesen, sie hat keine Spalte `date`, und jede einzelne Zeile kommt als **Kann nicht gelesen werden** zurück. Erst das Auswahlfeld einstellen, dann die Datei auswählen — in dieser Reihenfolge.

Die Prüfung, die danach kommt, nennt die Art, mit der sie gelesen hat. Über den geprüften Zeilen steht zum Beispiel _maerz-2026.csv, gelesen als Stunden_. Lesen Sie diese Zeile, bevor Sie irgendetwas anderes lesen. Steht dort das falsche Wort, wurde nichts geschrieben; stellen Sie das Auswahlfeld richtig ein und wählen Sie die Datei noch einmal aus.

## Mit der Vorlage anfangen

Drücken Sie **Vorlage herunterladen**, wenn die richtige Art eingestellt ist. Eine kleine CSV-Datei landet in Ihren Downloads, benannt nach der Art: `time_entries-template.csv`, `absences-template.csv` oder `opening_balances-template.csv`. Sie enthält die Überschriftenzeile und eine Beispielzeile, damit Sie den Aufbau sehen.

Öffnen Sie sie, löschen Sie die Beispielzeile, fügen Sie Ihre eigenen Zeilen ein und speichern Sie. Die Vorlage ist so geschrieben, dass Excel sie öffnet, ohne Umlaute in Namen zu verstümmeln.

Sie können auch eine eigene Datei nehmen. Es muss eine `.csv`-Datei oder eine Excel-Arbeitsmappe `.xlsx` sein, und höchstens 5 MB groß. Aus einer Arbeitsmappe wird nur das Blatt gelesen, das beim Öffnen erscheint, und die Spaltenüberschriften müssen in dessen erster Zeile stehen — was auf einem zweiten Blatt steht, wird kommentarlos übergangen.

Eine CSV-Datei darf ihre Spalten mit Komma, Semikolon oder Tabulator trennen. Verwendet wird das Zeichen, das in der Überschriftenzeile am häufigsten vorkommt. Das ist wichtig, weil Excel auf einem deutschen oder österreichischen Windows CSV mit Semikolon speichert; eine solche Datei wird hier richtig gelesen.

## Was die einzelnen Spalten bedeuten

Überschriften werden zugeordnet, nachdem Leerzeichen am Rand entfernt, Großbuchstaben klein gemacht und übrig gebliebene Leerzeichen in Unterstriche verwandelt wurden. `Email`, `EMAIL` und `email` funktionieren also alle, und aus `Start Date` wird `start_date`.

Ein Bindestrich bleibt unangetastet. **`E-Mail` wird nicht als Überschrift erkannt.** Genau so wird die Spalte auf Deutsch geschrieben, und genau das steht am ehesten oben in einer schon vorhandenen Bürotabelle. Wenn jede Zeile zurückkommt und sagt, dass sich niemand als nichts anmeldet, dann ist die Überschrift das Problem und nicht die Adressen. Schreiben Sie `email`.

Die Reihenfolge der Spalten spielt keine Rolle. Zusätzliche Spalten werden übergangen.

### Stunden

| Überschrift                | Pflicht              | Was hineingehört                                                                                         |
| -------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------- |
| `email`                    | Ja                   | Die Adresse, mit der sich die Person anmeldet. `e_mail` funktioniert bei dieser Art von Datei ebenfalls. |
| `date`                     | Ja                   | Der Tag, an dem die Stunden gearbeitet wurden. `datum` funktioniert auch.                                |
| `hours` **oder** `minutes` | Ja, eines von beiden | Wie lang. Siehe den nächsten Abschnitt. `stunden`, `std` und `minuten` funktionieren auch.               |
| `note`                     | Nein                 | Bleibt beim Eintrag stehen und wird daneben angezeigt. `notiz` funktioniert auch.                        |

### Abwesenheiten

| Überschrift  | Pflicht | Was hineingehört                                                                           |
| ------------ | ------- | ------------------------------------------------------------------------------------------ |
| `email`      | Ja      | Die Adresse, mit der sich die Person anmeldet.                                             |
| `start_date` | Ja      | Erster Tag der Abwesenheit. `von` funktioniert auch.                                       |
| `end_date`   | Nein    | Letzter Tag der Abwesenheit. Für einen einzelnen Tag leer lassen. `bis` funktioniert auch. |
| `type`       | Ja      | Der Code für den Grund. `art` funktioniert auch.                                           |

Standardmäßig eingerichtet sind die Codes `urlaub` (Urlaub), `krankenstand` (Krankenstand), `zeitausgleich` (Zeitausgleich), `pflegefreistellung` (Pflegefreistellung), `dienstverhinderung` (sonstige gerechtfertigte Dienstverhinderung) und `unbezahlt` (unbezahlter Urlaub). Welche Liste Ihr Unternehmen tatsächlich hat, steht auf der Seite **Abwesenheiten** unter **Gründe**.

Eine so importierte Abwesenheit wird gleich als **Genehmigt** geschrieben, in ganzen Tagen. Auf der Seite **Abwesenheiten** steht in ihrer Spalte **Grund** der Name des Grundes und dahinter „Aus einem früheren System importiert.“ — daran erkennen Sie eine importierte Zeile gegenüber einer, die jemand beantragt hat. Halbe Tage lassen sich nicht importieren; erfassen Sie die von Hand auf der Seite **Abwesenheiten**.

Wie viel eine Abwesenheit wert ist, ergibt sich aus der Arbeitswoche dieser Person und nicht aus der Zahl der Tage im Zeitraum. Eine Woche Urlaub kostet bei jemandem, der Montag bis Mittwoch arbeitet, drei Tage und nicht fünf.

### Anfangssalden

| Überschrift                | Pflicht              | Was hineingehört                                                                                                                                                                                                                                                                                                                                                                                                      |
| -------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `email`                    | Ja                   | Die Adresse, mit der sich die Person anmeldet.                                                                                                                                                                                                                                                                                                                                                                        |
| `date`                     | Ja                   | Der Tag, ab dem der Saldo gilt. `effective_on` funktioniert auch.                                                                                                                                                                                                                                                                                                                                                     |
| `hours` **oder** `minutes` | Ja, eines von beiden | Der Saldo selbst. Ein Minuszeichen bedeutet Rückstand. Null ist erlaubt.                                                                                                                                                                                                                                                                                                                                              |
| `basis`                    | Ja                   | Woher die Zahl stammt, in Worten. `grundlage` funktioniert auch. Eine Zeile, bei der diese Zelle leer ist, wird abgelehnt.                                                                                                                                                                                                                                                                                            |
| `kind`                     | Nein                 | `time` für Stunden, `leave` für Urlaub, `overtime` für auszuzahlende Überstunden. Leer bedeutet `time`.                                                                                                                                                                                                                                                                                                               |
| `confidence`               | Nein                 | Wie sicher die Zahl ist: `documented` oder `exact` wird als **Aus Aufzeichnungen übernommen** erfasst, `reconstructed` als **Aus anderen Aufzeichnungen ermittelt**, `estimated` als **Geschätzt**, `agreed` als **Aus einem Gespräch mit der Person**. Eine leere Zelle oder irgendein anderes Wort wird als **Aus einem Gespräch mit der Person** erfasst, und ein Tippfehler an dieser Stelle wird nicht gemeldet. |

**Nur ein Saldo der Art `time` wird irgendwo mitgezählt.** Ein Saldo, der als `leave` oder `overtime` importiert wird, wird gespeichert und im Datensatz der Person angezeigt, und keine Berechnung liest ihn. Der Urlaub für das Jahr wird pro Person auf der Seite **Personen** festgelegt, mit **Urlaubsjahr hinzufügen** und **Urlaub für das Jahr**. Wenn Sie den Resturlaub aller Personen aus der alten Tabelle als Anfangssaldo übernehmen, sieht das nach Erfolg aus und bewirkt nichts.

## Wie eine Dauer gelesen wird

**Die Spaltenüberschrift entscheidet, was eine bloße Zahl bedeutet. Die Zahl selbst nie.**

- Unter der Überschrift `hours` bedeutet `7.7` sieben Stunden und zweiundvierzig Minuten.
- Unter der Überschrift `minutes` bedeutet `462` dasselbe.
- Als `7:42` geschrieben bedeutet es unter beiden Überschriften dasselbe, weil es selbst sagt, was es ist.

`462` unter der Überschrift `hours` sind also 462 Stunden, das ist mehr als ein Tag, und die Zeile wird abgelehnt. Und `7.7` unter der Überschrift `minutes` sind sieben Minuten und werden ohne Beanstandung geschrieben.

Weitere Regeln, die festgelegt sind:

| Sie schreiben    | Unter `hours`                                            | Unter `minutes`                             |
| ---------------- | -------------------------------------------------------- | ------------------------------------------- |
| `8`              | 8:00                                                     | 0:08                                        |
| `0.5`            | 0:30                                                     | 0:00 — ein Bruchteil einer Minute fällt weg |
| `7.99`           | 7:59 — 479,4 Minuten, auf die nächste Minute gerundet    | 0:07                                        |
| `6,42`           | 6:25 — ein Komma wird als Dezimaltrennzeichen angenommen | 0:06                                        |
| `-1.5`           | −1:30                                                    | −0:01                                       |
| `-1:30`          | −1:30                                                    | −1:30                                       |
| `ein halber Tag` | abgelehnt                                                | abgelehnt                                   |

Eine Dezimalzahl unter der Überschrift `hours` wird auf die nächste Minute gerundet. Bei einer Dezimalzahl unter der Überschrift `minutes` fällt der Teil nach dem Komma weg; deshalb wird aus einer Stundenzahl, die unter `minutes` steht, eine Handvoll Minuten, und es sieht nach fast nichts aus.

Hat eine Datei sowohl eine Spalte `hours` als auch eine Spalte `minutes` und steht in beiden etwas, wird die Minutenspalte genommen, weil bei Minuten kein Rest verloren gehen kann.

Eine negative Dauer ist erlaubt; so wird eine Korrektur importiert. Null ist nicht erlaubt: Eine Zeile mit null Stunden wird abgelehnt, weil null etwas bedeuten müsste und niemand sagen kann, was. Lassen Sie den Tag stattdessen ganz aus der Datei weg.

Nichts darf an einem Tag mehr als 24 Stunden ergeben, in keine der beiden Richtungen.

## Wie ein Datum gelesen wird

Drei Schreibweisen für ein Datum werden gelesen:

- `2026-03-02`
- `02.03.2026`
- `02/03/2026`

**Vorsicht bei der dritten.** Ein Datum mit Schrägstrichen wird immer mit dem Tag zuerst gelesen, und die Datei kann es nicht anders sagen. `03/04/2026` ist der 3. April und nicht der 4. März. Eine Datei aus einem englischsprachigen System, wo das den 4. März bedeutet hätte, wird um einen Monat verschoben gelesen, und jede Zeile kommt trotzdem als **Wird geschrieben** zurück. Nichts warnt Sie. Wenn Ihre Datei Datumsangaben mit Schrägstrichen enthält, stellen Sie die Spalte vor dem Hochladen auf die Form `2026-03-02` um.

In einer Excel-Arbeitsmappe wird eine echte Datumszelle so genommen, wie sie ist.

Bei jedem Datum, mit dem das Einlesen nichts anfangen kann, bekommen Sie **Das Datum konnte nicht gelesen werden.** — eine Ablehnung, die Sie sehen und beheben können. Ein verdreht gelesenes Datum ist das nicht.

## Die Prüfung, bevor etwas geschrieben wird

Drücken Sie **Datei auswählen** und wählen Sie die Datei aus. Sie wird hochgeladen und gelesen, und **es wird nichts geschrieben**. Zwischen der Karte und der Liste erscheint ein Bereich, überschrieben mit Ihrem Dateinamen und der Art, als die sie gelesen wurde, und darunter: _Es wurde noch nichts geschrieben. Zeilen kommen zu dem hinzu, was für diese Tage bereits erfasst ist; ein doppelt importierter Tag zählt deshalb doppelt. Um eine bereits importierte Datei zu berichtigen, nehmen Sie sie zuerst zurück, statt eine korrigierte Fassung zu importieren._

### Die drei Zahlen

| Zahl                            | Was sie zählt                                                                                                   |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **werden geschrieben**          | Zeilen, die jede Prüfung bestanden haben. Nur diese werden beim Übernehmen geschrieben.                         |
| **können nicht gelesen werden** | Zeilen, in denen etwas nicht stimmt. Sie werden nie geschrieben, und das Übernehmen bricht ihretwegen nicht ab. |
| **übersprungen**                | Zeilen für einen Monat, der nicht mehr offen ist. Werden ebenfalls nie geschrieben.                             |

Die drei ergeben zusammen immer die Zahl der Datenzeilen in der Datei.

### Die Tabelle

Drei Spalten: **Zeile**, **Was passiert** und **Details**. Die Zeilen sind gruppiert und stehen nicht in der Reihenfolge der Datei — zuerst alles, was **Kann nicht gelesen werden**, dann alles **Übersprungen**, dann alles, was **Wird geschrieben**. Innerhalb jeder Gruppe bleibt die Reihenfolge der Datei erhalten.

**Zeile** ist die Zeilennummer in der Tabelle, wobei die Überschriftenzeile als Zeile 1 zählt. Es ist dieselbe Nummer, die Excel links am Rand anzeigt — und die Sie vor sich haben, während Sie die Datei berichtigen. Zeile 9 ist die neunte Zeile der Datei, also die achte Zeile Ihrer Daten. Die erste Datenzeile ist immer Zeile 2.

**Details** sagt eines von zwei Dingen. Bei einer Zeile, die nicht verwendet werden kann, steht dort der Grund. Bei einer Zeile, die geschrieben wird, steht dort kurz, was gleich gespeichert wird — damit die Zahl auf der Schaltfläche zum Übernehmen etwas ist, das Sie prüfen können, und nicht etwas, dem Sie vertrauen müssen:

- Eine Stundenzeile zeigt das Datum mit Jahr und die Dauer: _2. März 2026 · 7:42_.
- Eine Abwesenheitszeile zeigt **nur ihren ersten Tag**. Ein einzelner freier Tag und zwei Wochen Urlaub sehen hier genau gleich aus. Weil importierte Abwesenheiten gleich als genehmigt geschrieben werden und den Urlaub der Person verbrauchen, prüfen Sie die Enddaten in Ihrer eigenen Datei, bevor Sie übernehmen — diese Tabelle zeigt sie Ihnen nicht.
- Ein Anfangssaldo zeigt das Datum und die Zahl — nur dass **bei einem Saldo von null gar keine Zahl steht**. Eine Datei, die alle bei null beginnen lässt, ist deshalb eine Spalte aus nackten Datumsangaben. Das ist richtig so, und es ist keine leere Zeile.

Die Tabelle scrollt in ihrem eigenen Kasten. Es gibt keine Suche und keinen Filter; bei einer langen Datei müssen Sie also scrollen.

### Liegen lassen und wiederkommen

**Vorerst liegen lassen** schließt den Bereich. Es löscht nichts und nimmt nichts zurück. Die Datei bleibt unter **Früher importierte Dateien** im Status **Wartet auf Übernahme** stehen, und Sie können den Bereich jederzeit mit **Wieder öffnen** in dieser Zeile zurückholen.

Deshalb ist eine versehentlich zweimal hochgeladene Datei auch zweimal in der Liste und wartet zweimal auf die Übernahme; beide zu übernehmen würde alles doppelt schreiben.

## Warum eine Zeile abgelehnt oder übersprungen wurde

Das sind die genauen Sätze, die Sie in der Spalte **Details** sehen.

| Was dort steht                                                                                                                          | Was nicht stimmt                                                                                               | Was zu tun ist                                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Hier meldet sich niemand als {Adresse} an. Legen Sie die Person unter Personen an oder korrigieren Sie die Adresse in der Datei.        | Die Adresse ist leer, falsch geschrieben oder gehört zu jemandem ohne Dienstverhältnis                         | Berichtigen Sie die Datei oder legen Sie die Person zuerst unter **Personen** an. Steht dort überhaupt kein Name, schauen Sie auf die Überschrift — siehe `E-Mail` weiter oben |
| Das Datum konnte nicht gelesen werden.                                                                                                  | Die Datumszelle ist leer oder in einer Form, die nicht erkannt wird                                            | Schreiben Sie es als `2026-03-02` oder `02.03.2026`                                                                                                                            |
| Das Startdatum konnte nicht gelesen werden.                                                                                             | Dasselbe, in einer Datei mit Abwesenheiten                                                                     | Dasselbe                                                                                                                                                                       |
| Die Dauer konnte nicht gelesen werden oder ist null. Jede Zeile braucht eine Dauer — lassen Sie den Tag sonst ganz aus der Datei weg.   | Die Zelle mit der Dauer ist leer, unlesbar oder null                                                           | Tragen Sie eine echte Dauer ein oder löschen Sie die Zeile                                                                                                                     |
| Das sind mehr als 24 Stunden an einem Tag. Prüfen Sie, ob die Zahl Stunden oder Minuten meint und ob die Spaltenüberschrift dazu passt. | Die Zeile ergibt mehr als 24 Stunden, in die eine oder die andere Richtung                                     | Meist eine Minutenzahl, die unter der Überschrift `hours` steht                                                                                                                |
| Dieser Monat ist nicht mehr offen, es kann nichts mehr hinein. Bitten Sie darum, ihn wieder zu öffnen, wenn das hinein soll.            | Der Monat ist eingereicht, genehmigt oder abgeschlossen. Das ist ein Fall von **Übersprungen** und kein Fehler | Wenn es wirklich hinein muss, öffnen Sie den Monat dieser Person zuerst auf **Teamzeit** wieder und laden Sie die Datei dann noch einmal hoch                                  |
| Der Saldo konnte nicht gelesen werden.                                                                                                  | In einer Datei mit Anfangssalden ist die Zelle mit dem Saldo leer oder unlesbar                                | Schreiben Sie ihn als `12:30`, `-12:30` oder als Dezimalzahl. Null ist hier in Ordnung                                                                                         |
| In der Spalte kind muss time, leave oder overtime stehen.                                                                               | In der Zelle `kind` steht ein anderes Wort                                                                     | Nehmen Sie eines dieser drei. Eine leere Zelle ist in Ordnung und bedeutet Stunden                                                                                             |
| Die Spalte basis ist leer. Schreiben Sie hinein, woher die Zahl stammt, zum Beispiel: aus der alten Urlaubstabelle.                     | Die Zelle `basis` ist leer, wird aber gebraucht                                                                | Schreiben Sie in Worten, woher die Zahl stammt                                                                                                                                 |
| Es endet, bevor es beginnt.                                                                                                             | `end_date` liegt vor `start_date`                                                                              | Tauschen Sie die beiden, oder leeren Sie das Enddatum für einen einzelnen Tag                                                                                                  |
| Kein Abwesenheitsgrund hat den Code „{code}“. Die Codes finden Sie auf der Seite **Abwesenheiten** unter **Gründe**.                    | In der Zelle `type` steht keiner der hier eingerichteten Codes                                                 | Nehmen Sie einen davon, oder legen Sie den Grund zuerst an                                                                                                                     |

Beachten Sie: „Dieser Monat ist nicht mehr offen“ wird auch über einen Monat gesagt, der bloß **Abgegeben** ist, genauso wie über einen, der **Genehmigt** oder **Abgeschlossen** ist. Bei allen dreien wird nicht mehr neu gerechnet, es kann also in keinen davon etwas Neues mitgezählt werden.

## Übernehmen

**Beim Übernehmen werden die Zeilen geschrieben. Es gibt keine Rückfrage: ein Druck, und es ist erledigt.** Es lässt sich als ganze Datei zurücknehmen, aber nur unter den Bedingungen im übernächsten Abschnitt — lesen Sie also zuerst die Prüfung.

1. Lesen Sie die Überschrift und vergewissern Sie sich, dass dort die Art steht, die Sie gemeint haben.
2. Lesen Sie die Zahlen. Steht bei **können nicht gelesen werden** oder bei **übersprungen** nicht null, schauen Sie sich diese Zeilen an und entscheiden Sie, ob Sie die Datei berichtigen und von vorne anfangen.
3. Drücken Sie die Schaltfläche; auf ihr steht **22 Zeilen übernehmen** — die Zahl ist die Zahl der Zeilen, die geschrieben werden. Ist nichts verwendbar, steht dort **0 Zeilen übernehmen**, und sie lässt sich nicht drücken.
4. Eine grüne Meldung erscheint: **Übernommen**, und darunter **22 Zeilen geschrieben**. Der Bereich schließt sich. Unter **Früher importierte Dateien** steht bei der Datei jetzt **Übernommen**, mit **Zurücknehmen** daneben.

Die Zahl in der Meldung ist das, was tatsächlich geschrieben wurde, und sie sollte mit der Zahl auf der Schaltfläche übereinstimmen.

Erscheint stattdessen eine rote Meldung — **Nicht durchgeführt** —, wurde nichts geschrieben, und der Bereich bleibt offen, Sie verlieren also nichts. Was die Sätze bedeuten, steht unten unter „Häufige Stolperfallen“.

**Übernehmen Sie am selben Tag, an dem Sie prüfen.** Ob ein Monat noch offen ist, wird beim _Prüfen_ der Datei entschieden und beim _Übernehmen_ nicht noch einmal gefragt. Eine Datei, die am Montag geprüft und am Freitag übernommen wird, während der Monat einer Person am Mittwoch eingereicht wurde, schreibt ihre Zeilen in diesen Monat — wo sie nie jemand mitzählt und niemand sieht, warum der Monat zu kurz ist. Liegt eine geprüfte Datei länger als einen Tag, laden Sie sie lieber noch einmal hoch, statt **Wieder öffnen** zu drücken.

## Was das Übernehmen nicht tut

**Es rechnet niemandes Monat neu.** Die Zeilen werden sofort geschrieben, aber die Zahlen auf **Meine Zeit** und **Teamzeit** werden erst dann neu berechnet, wenn jemand diesen Monat öffnet. Beim laufenden Monat und beim Monat davor passiert das zusätzlich einmal pro Stunde von selbst. Bei allem, was älter ist, ändert sich auf dem Bildschirm nichts, bis jemand zu diesem Monat blättert.

Wenn Sie also das letzte Frühjahr importieren und danach das letzte Frühjahr aufrufen, sehen Sie es. Schauen Sie zuerst auf die Zahl in irgendeiner Übersicht, sehen Sie vielleicht nichts und schließen daraus, der Import sei fehlgeschlagen. Ist er nicht. Importieren Sie die Datei nicht ein zweites Mal — schauen Sie stattdessen unter **Früher importierte Dateien** nach, dort steht bei der Datei **Übernommen**.

**Es reicht nicht bis in die Kundenverrechnung.** Importierte Stunden werden absichtlich als Stunden ohne Arbeitselement dahinter geschrieben, damit sie nie in die Verrechnung gespiegelt werden. Drei Jahre Vergangenheit zu importieren spielt nicht drei Jahre Rechnungen noch einmal ab.

**Es hindert Sie nicht daran, denselben Tag zweimal zu importieren.** Zwei Zeilen für dieselbe Person und denselben Tag schreiben zwei Einträge, und der Tag zählt beide zusammen. Der einzige Schutz gilt dem Fall, dass die byteweise identische Datei nach dem Übernehmen noch einmal hochgeladen wird; das wird mit „Genau diese Datei wurde bereits übernommen.“ abgelehnt. Eine Datei, die sich um ein einziges Zeichen unterscheidet, ist eine andere Datei und schreibt ihre Zeilen bereitwillig ein zweites Mal.

## Eine ganze Datei zurücknehmen

Das Zurücknehmen entfernt alles, was eine Datei geschrieben hat, und sonst nichts. Es gilt pro Datei, nicht pro Zeile.

**Es geht gar nicht mehr, sobald irgendetwas von dem, was die Datei geschrieben hat, in einen abgeschlossenen Monat mitgezählt wurde.** Auch nicht teilweise: Das Zurücknehmen wird als Ganzes abgelehnt, und es wird nichts entfernt. Das Fenster, das Sie gleich sehen, sagt genau das.

1. Suchen Sie die Datei unter **Früher importierte Dateien**. Nur bei einer Datei, bei der **Übernommen** steht, gibt es daneben **Zurücknehmen**.
2. Drücken Sie **Zurücknehmen**. Ein Fenster geht auf, überschrieben mit **maerz-2026.csv zurücknehmen?**, und darin steht: _Alles, was diese Datei geschrieben hat, wird wieder entfernt; sonst wird nichts verändert. Zählt etwas davon zu einem Monat, der inzwischen abgeschlossen ist, wird nichts entfernt, solange dieser Monat nicht wieder geöffnet ist._
3. Schreiben Sie eine Antwort auf **Warum wird der Import zurückgenommen?** Sie ist Pflicht — die Schaltfläche bleibt grau, bis Sie etwas geschrieben haben. Was Sie schreiben, bleibt bei der Datei stehen, mit Ihrem Namen und der Uhrzeit.
4. Drücken Sie **Zurücknehmen**. **Unverändert lassen** schließt das Fenster und tut nichts.
5. Eine grüne Meldung: **Zurückgenommen**, und darunter **22 Zeilen entfernt**. Der Status der Datei wird **Zurückgenommen**, und daneben gibt es keine Schaltflächen mehr.

Bekommen Sie stattdessen **Nicht durchgeführt** mit dem Satz „Ein Teil davon wurde in einen Monat mitgezählt, der jetzt abgeschlossen ist. Öffnen Sie den Monat zuerst wieder.“, dann steckt ein Teil dessen, was die Datei geschrieben hat, in einem abgeschlossenen Monat. Es wurde nichts entfernt. Öffnen Sie den Monat dieser Person mit **Wieder öffnen** auf **Teamzeit**, kommen Sie zurück und nehmen Sie den Import zurück, und schließen Sie den Monat danach wieder ab.

Auch das Zurücknehmen rechnet niemandes Monat neu. Es gilt dieselbe Regel wie oben.

Eine zurückgenommene Datei darf berichtigt und noch einmal importiert werden. Der Schutz gegen identische Dateien schaut nur auf Dateien, die gerade übernommen sind.

Aus **Früher importierte Dateien** lässt sich keine Zeile entfernen. Jede jemals hochgeladene Datei bleibt in der Liste stehen, die neueste zuerst, auch die fehlgeschlagenen. Die Zeilen tragen kein Datum, zwei Uploads von `maerz-2026.csv` sehen deshalb gleich aus. Bevor Sie bei einer von zwei gleichnamigen Zeilen **Zurücknehmen** drücken, drücken Sie bei der anderen **Wieder öffnen** und prüfen Sie, welche welche ist — nehmen Sie die falsche zurück, löschen Sie einen Monat Stunden, die richtig waren.

## Ein durchgerechnetes Beispiel

Anna arbeitet Montag bis Freitag, ihr Soll sind **7:42** am Tag. Das sind 462 Minuten. Ihr März hat 21 Arbeitstage, einer davon ist ein Feiertag, und sie hat zwei Tage Urlaub genommen. Ihr März stand in der alten Tabelle und ist nie in dieses System gekommen.

**Ihr Soll für den Monat.** 21 Arbeitstage × 7:42 = 9702 Minuten = **161:42**. Feiertage und Urlaub verringern das nicht. **Soll** bleibt bei 161:42, was auch passiert.

**Was aus der Datei kommen muss.** Tatsächlich am Schreibtisch war sie an 21 − 1 − 2 = **18 Tagen**. Nur diese Tage gehören in die Stundendatei. Der Feiertag wird über den Kalender **Feiertage** gutgeschrieben, die zwei Urlaubstage über die Seite **Abwesenheiten**. Beides kommt zu **Ist** hinzu und wird nicht von **Soll** abgezogen.

**Die Datei.** Sofia, die den Monat betreut, drückt **Vorlage herunterladen** mit der Einstellung **Stunden** und fügt Annas 18 Tage ein, dazu fünf Tage für einen Kollegen und einen versehentlich mitgekommenen Tag aus dem Februar. Vierundzwanzig Datenzeilen, also die Tabellenzeilen 2 bis 25.

**Die Prüfung.** Sie drückt **Datei auswählen**. Es wird nichts geschrieben. In dem Bereich steht _maerz-2026.csv, gelesen als Stunden_, und:

- **22 werden geschrieben**
- **1 können nicht gelesen werden**
- **1 übersprungen**

| Zeile | Was passiert              | Details                                                                                                                                        |
| ----- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 9     | Kann nicht gelesen werden | Hier meldet sich niemand als anna.berger@exampel.com an. Legen Sie die Person unter Personen an oder korrigieren Sie die Adresse in der Datei. |
| 25    | Übersprungen              | Dieser Monat ist nicht mehr offen, es kann nichts mehr hinein. Bitten Sie darum, ihn wieder zu öffnen, wenn das hinein soll.                   |
| 2     | Wird geschrieben          | 2. März 2026 · 7:42                                                                                                                            |
| 3     | Wird geschrieben          | 3. März 2026 · 7:42                                                                                                                            |

Zeile 9 ist Zeile 9 der Tabelle — die achte Datenzeile — und die Adresse ist falsch geschrieben. Zeile 25 ist der Februartag, und der Februar ist bereits abgeschlossen.

**Das Übernehmen.** Sie drückt **22 Zeilen übernehmen** und bekommt **Übernommen** / **22 Zeilen geschrieben**.

**Was Annas März jetzt zeigt,** sobald jemand den März öffnet:

|                                                         | Minuten            | Angezeigt als |
| ------------------------------------------------------- | ------------------ | ------------- |
| 17 importierte Tage (eine ihrer Zeilen wurde abgelehnt) | 17 × 462 = 7854    | 130:54        |
| Der Feiertag                                            | 462                | 7:42          |
| Zwei Urlaubstage                                        | 2 × 462 = 924      | 15:24         |
| **Ist**                                                 | 9240               | **154:00**    |
| **Soll**                                                | 9702               | **161:42**    |
| **Saldo**                                               | 9240 − 9702 = −462 | **−7:42**     |

Die fehlenden 7:42 sind der eine Tag, dessen E-Mail-Adresse falsch geschrieben war.

**Die eine Zeile berichtigen.** Sofia korrigiert die Adresse, speichert _nur diese eine Zeile_ als neue Datei, lädt sie hoch, bekommt „1 werden geschrieben“ und drückt **1 Zeile übernehmen**. Der März zeigt jetzt **Ist** 161:42, **Soll** 161:42, **Saldo** 0:00.

Sie darf nicht die ganze berichtigte Datei hochladen. Sie unterscheidet sich um ein Zeichen von der bereits übernommenen, der Schutz gegen identische Dateien hält sie also nicht auf, und alle ihre guten Zeilen kämen noch einmal zu den schon vorhandenen dazu — Annas März käme auf fast das Doppelte ihrer Stunden.

**Was passiert wäre, hätte die Datei alle 21 Arbeitstage aufgeführt,** den Feiertag und die zwei Urlaubstage eingeschlossen, und wäre jede Zeile geschrieben worden. Stunden aus der Datei: 21 × 462 = 9702. Dazu der Feiertag, 462. Dazu der Urlaub, 924. **Ist** = 11088 Minuten = **184:48**, gegen ein **Soll** von 161:42 — ein **Saldo** von **+23:06** für einen Monat, den Anna in Wirklichkeit genau ausgeglichen beendet hat. Die freien Tage sind bereits bezahlt. Schreiben Sie sie nicht zusätzlich in die Stundendatei.

## Entscheiden Sie vor dem Start, wie weit Sie zurückgehen

Aus dem Import alter Monate folgen drei Dinge, und alle drei entscheiden sich jetzt leichter, als sie sich später wieder auseinandernehmen lassen.

**Monate werden der Reihe nach abgeschlossen.** Jeder Monat beginnt mit dem, womit der Monat davor abgeschlossen wurde. Sobald ein Monat Tage enthält, in denen etwas steht — und genau das gibt ihm ein übernommener Import —, lässt sich der Monat danach erst abschließen, wenn er selbst abgeschlossen ist. Wenn Sie zwei Jahre Vergangenheit importieren, um dem Saldo eine Vorgeschichte zu geben, müssen diese vierundzwanzig Monate nun der Reihe nach eingereicht, genehmigt und abgeschlossen werden, der älteste zuerst, bevor Sie den Monat abschließen können, auf den die Lohnverrechnung wartet.

**Ein Saldo beginnt am Tag seines Anfangssaldos zu zählen.** Stunden, die vor diesem Tag datiert sind, werden geprüft, geschrieben und sind zu sehen, wenn jemand den Monat öffnet — und sie erreichen den laufenden Saldo nie. Alles vor diesem Datum bleibt absichtlich außen vor. Gibt es für jemanden keinen Anfangssaldo, beginnt das Zählen mit dem Eintrittsdatum.

**Gehen Sie deshalb in dieser Reihenfolge vor:** Legen Sie fest, ab welchem frühesten Tag der laufende Saldo zählen soll, importieren Sie zuerst die Stunden und die Abwesenheiten und erfassen Sie dann den Anfangssaldo auf diesen Tag. Erst die Salden zu importieren und danach die drei Jahre Tabellen macht die ältere Hälfte der Arbeit wirkungslos.

## Häufige Stolperfallen

**„Die Daten sind nicht gültig“.** Dieser eine Satz erscheint bei einer Datei mit Anfangssalden und bedeutet etwas ganz Bestimmtes: Für jemanden in der Datei ist für diesen Tag und diese Art bereits ein Anfangssaldo erfasst, oder zwei Zeilen Ihrer Datei betreffen dieselbe Person, dieselbe Art und denselben Tag. Erlaubt ist nur eine. Es wurde überhaupt nichts geschrieben — weder diese Zeile noch irgendeine andere Zeile der Datei —, nehmen Sie also die doppelte heraus und übernehmen Sie noch einmal, oder korrigieren Sie stattdessen den vorhandenen Wert im Datensatz der Person. Die Zeilen zeigen weiterhin **Wird geschrieben**, weil die Prüfung darauf nicht achtet.

**„Diese Datei ist größer als hier zulässig“.** Über 5 MB. Speichern Sie sie als CSV statt als Arbeitsmappe, oder teilen Sie sie auf.

**„Die Datei konnte nicht gelesen werden. Prüfen Sie, ob es eine CSV- oder XLSX-Datei ist“.** Aus der Datei war überhaupt nichts herauszuholen — eine beschädigte Arbeitsmappe, eine leere Datei, etwas Umbenanntes. Die Datei bleibt trotzdem für immer in der Liste, als **Konnte nicht gelesen werden**. Speichern Sie sie aus der Tabellenkalkulation neu.

**„Dieser Import wurde nicht geprüft oder ist bereits übernommen“.** Jemand anderer hat diese Datei zuerst übernommen, von einem anderen Browser aus. Laden Sie die Seite neu und schauen Sie sich den Status der Datei an.

**In jeder Zeile steht, dass sich niemand als nichts anmeldet.** Die Überschrift `email` wird nicht erkannt. `E-Mail` ist die übliche Ursache.

**Eine ganze Datei als falsche Art gelesen.** Das Auswahlfeld stand noch auf **Stunden**. Es wurde nichts geschrieben; stellen Sie es ein und wählen Sie die Datei noch einmal aus.

**Die Zahlen einer Person haben sich nicht bewegt.** Sie werden neu berechnet, wenn jemand diesen Monat öffnet. Siehe „Was das Übernehmen nicht tut“.

**Soll und Saldo einer Person bleiben bei 0:00.** Zwei der vier Beschäftigungsarten — **Remote, Vollzeit, stellt uns Rechnungen** und **Remote, Teilzeit, stellt uns Rechnungen** — geben kein Soll vor. Bei ihnen ist **Soll** 0:00 und **Saldo** ebenso, wie viele Stunden Sie auch importieren. **Ist** steigt sehr wohl. Das ist richtig so und kein fehlgeschlagener Import. „Personen und ihre Bedingungen“ erklärt die Beschäftigungsarten.

**Eine einzelne importierte Zeile berichtigen.** Es gibt keine Möglichkeit, eine zu bearbeiten. Die Person selbst kann sie an ihrem eigenen Tag auf **Meine Zeit** entfernen, solange ihr Monat noch offen ist — importierte Stunden stehen dort mit einer kleinen Kennzeichnung **Importiert**. Sonst bleibt nur, die ganze Datei zurückzunehmen und eine berichtigte zu importieren.

## Wenn Sie nicht weiterkommen

- Um zu sehen, was für jemanden tatsächlich geschrieben wurde und an welchen Tagen, nehmen Sie **Stunden im Detail** — „Stunden im Detail“ erklärt diese Seite.
- Um einen Monat wieder zu öffnen, damit ein Import hinein kann oder damit eine Rücknahme möglich wird, nehmen Sie **Wieder öffnen** auf **Teamzeit** — „Der Monat, von offen bis abgeschlossen“ erklärt, was das Wiederöffnen bewirkt und was es kostet.
- Um jemanden anzulegen, bevor seine Zeilen zugeordnet werden können, oder um einen Anfangssaldo oder ein Urlaubsjahr von Hand zu erfassen, nehmen Sie **Personen** — „Personen und ihre Bedingungen“.
- Was eine importierte Abwesenheit mit einem Monat und mit dem Urlaubskonto macht, steht in „Abwesenheit von der Arbeit“ und „Urlaub“.
- Was ein Feiertag für die einzelne Person wert ist, steht in „Feiertage“.
- Zu einer Ablehnung, die hier nicht steht, siehe „Wenn etwas schiefgeht“.

Verhält sich eine Datei so, wie es auf dieser Seite nicht beschrieben ist, übernehmen Sie sie nicht ein zweites Mal, um zu sehen, ob es dann klappt. Lassen Sie sie liegen und fragen Sie die Person, die das Team betreut.
