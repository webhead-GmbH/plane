# Stunden erfassen

Diese Seite ist für alle, die ihre Arbeitszeit in das System eintragen müssen und denen das nie jemand gezeigt hat. Sie erklärt die drei Wege, auf denen Stunden in einen Monat kommen, wie man eine Dauer schreibt und wie Sie Erfasstes hinzufügen, korrigieren und entfernen. Wenn Sie wissen möchten, was die Zahlen in Ihrem Monat bedeuten, lesen Sie stattdessen „Meine Zeit — Ihr eigener Monat“.

## Inhalt

- [Die drei Wege, auf denen Stunden in Ihren Monat kommen](#die-drei-wege-auf-denen-stunden-in-ihren-monat-kommen)
- [Eine Dauer schreiben](#eine-dauer-schreiben)
- [Ein Timer auf einem Arbeitselement](#ein-timer-auf-einem-arbeitselement)
- [Stunden ohne Arbeitselement](#stunden-ohne-arbeitselement)
- [Stunden, die jemand für Sie erfasst](#stunden-die-jemand-für-sie-erfasst)
- [Wenn der Monat eingereicht ist](#wenn-der-monat-eingereicht-ist)
- [Ein Monat, durchgerechnet](#ein-monat-durchgerechnet)
- [Wenn Sie nicht weiterkommen](#wenn-sie-nicht-weiterkommen)

## Die drei Wege, auf denen Stunden in Ihren Monat kommen

Jede Stunde, die in Ihrem Monat gezählt wird, kommt auf einem von drei Wegen herein.

| Wie die Stunden hereinkommen                                           | Wo Sie das tun                                                           | In welcher Spalte sie auf **Meine Zeit** landen                                 |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| Ein Timer, den Sie auf einem Arbeitselement starten und stoppen        | Auf dem Arbeitselement selbst                                            | **Arbeitselemente**                                                             |
| Stunden, die Sie für einen Tag eintippen, ohne Arbeitselement dahinter | **Meine Zeit**, indem Sie den Tag öffnen                                 | **Ohne Arbeitselement**                                                         |
| Stunden, die jemand für Sie erfasst                                    | Auf einem Arbeitselement oder aus einer Datei, die diese Person einliest | **Arbeitselemente** oder **Ohne Arbeitselement**, je nachdem, was erfasst wurde |

Zwei weitere Dinge zählen ebenfalls zum **Ist**, und keines davon wird auf dieser Seite erfasst: Abwesenheiten und Feiertage. Dazu gibt es „Abwesenheit von der Arbeit“ und „Feiertage“.

Die Spalten stehen in der Tagestabelle auf **Meine Zeit**. Von links nach rechts für einen Tag gelesen: **Soll** ist das, was Sie an diesem Tag schulden, **Arbeitselemente** und **Ohne Arbeitselement** sind die beiden Arten von Stunden, die Sie erfasst haben, **Abwesend** steht für Abwesenheit und Feiertage, **Ist** ist alles davon zusammengezählt, und **Saldo** ist **Ist** minus **Soll**.

## Eine Dauer schreiben

Überall dort, wo das System fragt, wie lange etwas gedauert hat, versteht es mehrere Schreibweisen. Das sind die, die es liest.

| Was Sie eintippen  | Was erfasst wird     | Hinweis                                                           |
| ------------------ | -------------------- | ----------------------------------------------------------------- |
| `1:30`             | 1 Stunde 30 Minuten  | Stunden und Minuten. Die Minuten müssen zwischen 00 und 59 liegen |
| `7:42`             | 7 Stunden 42 Minuten |                                                                   |
| `1.5` oder `1,5`   | 1 Stunde 30 Minuten  | Dezimalstunden. Ein Komma geht genauso wie ein Punkt              |
| `7.7`              | 7 Stunden 42 Minuten | Dezimalstunden, auf die nächste Minute gerundet                   |
| `7h`               | 7 Stunden            |                                                                   |
| `90m` oder `90min` | 90 Minuten           |                                                                   |

Eine Zahl allein wird abgelehnt. Wenn Sie `20` eintippen und auf **Hinzufügen** klicken, erscheint:

> Geben Sie die Dauer an: 1:30, 7h oder 90m. Eine Zahl allein sagt nicht, ob Stunden oder Minuten gemeint sind.

Das ist Absicht. Zwanzig Minuten und zwanzig Stunden sind beide denkbar, und das System rät nicht. Schreiben Sie `20m` für zwanzig Minuten oder `20:00` für zwanzig Stunden.

Alles andere, was es nicht lesen kann, bekommt eine kürzere Meldung:

> Die Dauer fehlt. Geben Sie 1:30 oder 1,5 ein.

Für Stunden, die Sie für einen Tag eintippen, gelten zwei Grenzen. Ein Eintrag über gar keine Zeit wird abgelehnt. Ein einzelner Eintrag über mehr als 24 Stunden ebenfalls, mit der Meldung „Ein einzelner Tag kann nicht mehr als 24 Stunden enthalten.“

Überall, wo das System Ihnen eine Dauer anzeigt, tut es das als Stunden und Minuten mit Doppelpunkt: `161:42` bedeutet 161 Stunden und 42 Minuten, nicht 161 Stunden und 42 Hundertstel. Die einzige Stelle mit Dezimalstunden ist die Zahl für die Rechnungsstellung auf **Meine Zeit**, und dort steht es ausgeschrieben dabei.

## Ein Timer auf einem Arbeitselement

So werden die meisten Stunden erfasst. Der Timer läuft auf dem Arbeitselement, und was er erfasst, zählt automatisch in Ihrem Monat mit.

### Einen Timer starten

1. Öffnen Sie das Arbeitselement.
2. Scrollen Sie nach unten zum Aktivitätsbereich. Darüber, auf der rechten Seite, steht die Schaltfläche **Timer starten**.
3. Klicken Sie darauf. Die Schaltfläche wird zu **Timer stoppen**, und daneben läuft die Zeit hoch, in der Form `12m 5s`.

**Timer starten** sehen Sie nur, wenn zweierlei zutrifft: Sie sind eine der Personen, denen das Arbeitselement zugewiesen ist, und das Arbeitselement ist in einem Status, in dem Timer erlaubt sind. Wenn Sie weder zugewiesen noch Administrator des Projekts sind, werden Ihnen weder **Timer starten** noch **Arbeit erfassen** angezeigt. Wenn Sie die Arbeit machen, aber nicht auf dem Arbeitselement stehen, bitten Sie darum, dass es Ihnen zugewiesen wird. Einen Timer für jemand anderen zu starten, ist nicht möglich.

Sobald irgendwo ein Timer läuft, erscheint in der Leiste am oberen Rand jeder Seite eine Uhr mit einem grünen Punkt. Klicken Sie darauf, dann nennt ein kleines Feld das Arbeitselement, den Startzeitpunkt des Timers und die Zeit unter **Verstrichen**, und es zeigt eine rote Schaltfläche **Timer stoppen**. Diese Uhr schaut nur in den Workspace, in dem Sie gerade sind. Ein Timer, der in einem anderen Workspace läuft, zählt trotzdem, blockiert den Monat trotzdem und taucht in dieser Uhr nicht auf — siehe den Hinweis am Ende dieses Abschnitts.

In der Listen- und in der Board-Ansicht gibt es außerdem eine kleine Start-Schaltfläche in der Zeile, neben dem Status, für Arbeitselemente, die Ihnen zugewiesen sind.

### Einen Timer stoppen

1. Klicken Sie auf **Timer stoppen** (auf dem Arbeitselement, in der Listenzeile oder in der Uhr am oberen Rand der Seite).
2. Auf dem Arbeitselement und in Listenzeilen öffnet sich ein kleines Fenster mit der Frage „Woran haben Sie gearbeitet? (optional)“. Schreiben Sie eine Notiz oder lassen Sie es leer.
3. Klicken Sie auf **Speichern**.

Erfasst wird die ganze Spanne vom Start bis zum Stopp. Von dem Kaffee zwischendurch weiß der Timer nichts. Wenn Sie mit der Arbeit aufgehört, den Timer aber nicht gestoppt haben, korrigieren Sie den Eintrag hinterher.

### Was ein laufender Timer zählt

Nichts, solange er läuft.

- Er trägt nichts zu **Arbeitselemente** bei, nichts zum **Ist** und nichts zu Ihrem **Saldo**.
- Erst wenn Sie ihn stoppen, werden daraus Stunden. In diesem Moment entsteht seine Dauer.
- Auf „Stunden im Detail“ steht ein laufender Timer mit dem Hinweis „Läuft noch — hat noch keine Dauer und zählt nicht“.
- Ein Monat lässt sich nicht einreichen, solange darin noch einer Ihrer Timer läuft. **Meine Zeit** sagt es so: „Auf einem Ihrer Arbeitselemente läuft noch ein Timer — in diesem oder einem anderen Workspace. Stoppen Sie ihn, dann können Sie den Monat einreichen.“

Es kann immer nur ein Timer laufen. Wenn Sie einen zweiten starten, wird der erste in diesem Moment für Sie gestoppt und seine Zeit erfasst. Vorher warnt Sie nichts; wenn der erste eigentlich weiterlaufen sollte, prüfen Sie ihn hinterher.

### Ein Timer, der weiterläuft

Ein Timer, der über Nacht weiterläuft, würde die ganze Nacht in Ihren Monat schreiben. Damit das nicht passiert, prüft das System stündlich und beendet jeden Timer, der länger als zehn Stunden läuft. Es beendet ihn bei genau zehn Stunden und setzt `[automatically stopped]` vor die Notiz.

Zehn Stunden sind eine Obergrenze, keine Messung. Niemand weiß, wann Sie tatsächlich aufgehört haben. Auf „Stunden im Detail“ ist der Eintrag mit „— vom System beendet, muss korrigiert werden“ gekennzeichnet, und er muss auf dem Arbeitselement korrigiert werden, bevor der Monat eingereicht wird.

### Auf welchen Tag die Stunden fallen

Eine Stunde zählt an dem Tag, an dem ihr Timer **gestartet** wurde. Eine Sitzung, die am 31. März um 23:40 beginnt und am 1. April um 00:20 endet, liegt vollständig im März.

Der Tag wird in Ihrer eigenen Zeitzone bestimmt — der aus Ihrem Dienstverhältnis, oder Wien, wenn keine hinterlegt ist. Es ist nicht die Zeitzone Ihres Computers und nicht die der lesenden Person. Am Monatsende ist das wichtig: Stunden aus einer späten Sitzung am letzten Tag des Monats gehören in diesen Monat, und wenn der Monat bereits eingereicht ist, kommen sie gar nicht mehr hinein.

Stunden zählen dort, wo Sie sie erfasst haben. Das Unternehmen führt in Plane mehr als einen Workspace, und die Stunden aus allen werden in Ihrem Monat zusammengezählt. Deshalb kann Ihr Monat größer sein als das, was ein einzelnes Projekt zeigt.

### Wie Timer-Stunden gerundet werden

Timer werden in Sekunden geführt. Für jeden Tag und jedes Projekt werden die Sekunden zuerst zusammengezählt und erst am Ende einmal auf die nächste Minute gerundet.

Drei Sitzungen von je 25 Minuten 20 Sekunden am selben Tag auf demselben Arbeitselement ergeben 76 Minuten, nicht 75. Würde jede Sitzung für sich gerundet, gingen jedes Mal ein paar Sekunden verloren, und über einen Monat wird daraus echte Zeit, die Sie gearbeitet haben und die Ihnen nicht gutgeschrieben wurde.

### Timer-Stunden korrigieren oder entfernen

Timer-Stunden werden auf dem Arbeitselement korrigiert, auf das sie erfasst wurden, nicht auf **Meine Zeit**.

1. Öffnen Sie das Arbeitselement und gehen Sie im Aktivitätsbereich auf den Reiter **Arbeitsberichte**.
2. Suchen Sie den Eintrag. Bei jedem steht, wer ihn erfasst hat, wie lange er dauert und wann er beginnt und endet.
3. Klicken Sie darunter auf **Bearbeiten**. **Start**, **Ende** und die Beschreibung lassen sich dann ändern.
4. Ändern Sie, was falsch ist, und klicken Sie auf **Speichern**.

Die Dauer ergibt sich aus **Start** und **Ende**; um zu ändern, wie lange etwas gedauert hat, verschieben Sie also die Endzeit. Ein Eintrag von weniger als einer Minute wird abgelehnt, mit „Die Endzeit muss nach der Startzeit liegen.“

Um einen Eintrag ganz herauszunehmen, klicken Sie darunter auf **Löschen** und bestätigen Sie. Die Rückfrage sagt deutlich, dass sich das nicht rückgängig machen lässt, und so ist es auch: Der Eintrag ist weg.

Ihre eigenen Einträge dürfen Sie bearbeiten und löschen. Ein Projektadministrator darf die Einträge aller bearbeiten und löschen.

## Stunden ohne Arbeitselement

Hinter mancher Arbeitszeit steht kein Arbeitselement: eine Teambesprechung, die Spesenabrechnung, eine Schulung, eine Reise. Hierhin gehört sie.

### Was hierher gehört und was nicht

Der Bildschirm sagt es in einer Zeile: „Stunden, die auf keinem Arbeitselement liegen — Besprechungen, Verwaltung, Schulung, Reisen. Sie zählen für Ihren Monat mit. Stunden auf Arbeitselementen kommen von den dortigen Timern und werden hier nicht geändert.“

**Abwesenheiten gehören nicht hierher.** Wenn Sie im Krankenstand waren, auf Urlaub oder aus einem anderen Grund abwesend, erfassen Sie das nicht als **Verwaltung**. Es würde als gearbeitete Stunden zählen, es würde den Tag so ausgleichen, dass nichts auffällt, und es käme nie auf Ihr Urlaubskonto und nie als Abwesenheit in die Lohnverrechnung. Abwesenheiten werden auf dem Bildschirm **Abwesenheiten** erfasst — siehe „Abwesenheit von der Arbeit“ und „Urlaub“.

### Stunden zu einem Tag hinzufügen

1. Öffnen Sie **Meine Zeit** in der Seitenleiste.
2. Suchen Sie den Tag. Klicken Sie entweder in der Tagestabelle auf das Datum — jedes Datum ist eine Schaltfläche, mit einem blassen Stift daneben — oder rechts oben auf **Zeit für heute erfassen**.
3. Es öffnet sich ein Fenster, oben steht der Tag ausgeschrieben: „Di., 10. März 2026“. Prüfen Sie das Jahr. Es steht dort, weil die Schaltfläche und die Monatspfeile Sie weiter bringen können, als Sie wollten.
4. Tippen Sie unter **Dauer** die Länge ein. Als Hinweis steht `1:30` im Feld. Siehe [Eine Dauer schreiben](#eine-dauer-schreiben).
5. Wählen Sie unter **Art** zwischen **Interne Besprechung**, **Schulung**, **Verwaltung**, **Reisezeit** und **Rufbereitschaft**. Voreingestellt ist **Verwaltung**.
6. Schreiben Sie unter **Notiz**, wofür die Zeit aufgewendet wurde. Das ist freiwillig, aber ein Monat voller Einträge, die nichts sagen, ist ein Monat, den später niemand prüfen kann.
7. Klicken Sie auf **Hinzufügen**. Eine kleine Meldung sagt **Hinzugefügt**. Der Eintrag erscheint in der Liste darüber, und die Summe am Fuß der Liste, beschriftet mit **Stunden ohne Arbeitselement**, steigt.

Nach dem Klick auf **Hinzufügen** werden **Dauer** und **Notiz** geleert, damit Sie den nächsten Eintrag tippen können. **Art** bleibt so stehen, wie Sie es gelassen haben. Wenn Sie eine Besprechung hinzugefügt haben und der nächste Eintrag die Spesenabrechnung ist, stellen Sie das Feld selbst wieder auf **Verwaltung** zurück.

Zwei Dinge, die Sie wissen sollten, bevor Sie tippen:

- **Die Eingabetaste bewirkt nichts.** Hier gibt es keine Tastenkombination. Sie müssen auf **Hinzufügen** klicken.
- **Wenn Sie das Fenster schließen, geht alles verloren, was Sie nicht hinzugefügt haben.** Sobald in **Dauer** oder **Notiz** etwas steht, erscheint links unten ein oranger Hinweis: „Noch nicht hinzugefügt. Klicken Sie auf Hinzufügen, sonst geht es beim Schließen verloren.“ Ein Klick auf **Schließen**, die Escape-Taste und ein Klick auf die dunkle Fläche außerhalb des Fensters verwerfen es alle drei, ohne noch einmal nachzufragen.

**Zeit für heute erfassen** führt immer zu heute, im laufenden Monat, egal welchen Monat Sie gerade angesehen haben. Wenn Sie den Jänner ansehen und darauf klicken, springt die Seite in diesen Monat und öffnet den heutigen Tag. Um Zeit an einem anderen Tag zu erfassen, gehen Sie mit den Pfeilen neben dem Monatsnamen zu diesem Monat und klicken Sie auf das Datum.

### Was im Fenster steht

| Was Sie sehen                                                                                                                       | Was es ist                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Eine Zeile: eine Dauer, eine Art, eine Notiz                                                                                        | Ein Eintrag. Die Art ist eine der fünf Auswahlmöglichkeiten, oder **Importiert** für etwas, das aus einer Datei übernommen wurde |
| Die Kennzeichnung **Importiert** am Ende einer Zeile                                                                                | Der Eintrag kam aus einer Tabelle, nicht aus diesem Fenster                                                                      |
| Eine Dauer mit einem Minus davor, etwa `-1:00`                                                                                      | Eine Korrektur, die Stunden vom Tag wegnimmt. Solche kommen nur aus einer Datei; nichts, was Sie hier eintippen, kann abziehen   |
| **Stunden ohne Arbeitselement**, am Fuß der Liste                                                                                   | Die Summe der Zeilen darüber, und sonst nichts                                                                                   |
| „Hier wurde noch nichts hinzugefügt. Stunden, die auf Arbeitselementen erfasst sind, zählen mit, werden hier aber nicht angezeigt.“ | An diesem Tag gibt es keine Stunden dieser Art. Es heißt nicht, dass nicht gearbeitet wurde                                      |

### Die zwei Zahlen in diesem Fenster sollen nicht übereinstimmen

Wenn in Ihrem Dienstverhältnis steht, dass Ihre Anwesenheit aufgezeichnet wird, gibt es oben im selben Fenster ein zweites Feld mit der Überschrift **Wann Sie bei der Arbeit waren** und einer eigenen Zahl rechts. Man liest die beiden leicht als ein und dasselbe. Das sind sie nicht.

- Die Zahl oben sagt, **wann Sie bei der Arbeit waren** — Beginn, Ende und Pause. Das ist eine eigene Aufzeichnung, die geführt wird, weil das Gesetz sie verlangt. Sie zählt nicht zu Ihren Stunden und bewegt Ihren Saldo nicht. Siehe „Wann Sie bei der Arbeit waren“.
- Die Liste darunter enthält **nur die Stunden ohne Arbeitselement**.
- Die Stunden aus Ihren Timern zählen in Ihrem Monat mit, werden in diesem Fenster aber überhaupt nicht angezeigt.

Ein Tag mit acht Stunden Timer-Arbeit sagt deshalb „Hier wurde noch nichts hinzugefügt.“, und ein Tag mit 7:30 Anwesenheit zeigt in der Liste vielleicht 1:30. Beides ist kein Fehler, und es muss nichts getan werden, damit die Zahlen zusammenpassen. Um alles zu einem Tag nebeneinander zu sehen, nehmen Sie die Tagestabelle auf **Meine Zeit**, und für die Aufschlüsselung Eintrag für Eintrag „Stunden im Detail“.

### Einen Eintrag korrigieren

Ein Eintrag lässt sich nicht bearbeiten. Auf den Zeilen gibt es keinen Stift. Um eine falsche Dauer, eine falsche Art oder eine falsche Notiz zu korrigieren, entfernen Sie den Eintrag und fügen Sie ihn neu hinzu. Das geht so lange, wie der Monat nicht eingereicht ist.

### Einen Eintrag entfernen

**Einen Eintrag zu entfernen, lässt sich nicht rückgängig machen.** Es gibt nirgends ein Rückgängig. Die Stunden sind vom Tag und aus dem Monat verschwunden, und wenn das ein Versehen war, müssen Sie sie neu eintippen.

1. Am rechten Ende der Zeile steht ein kleines Papierkorb-Symbol. Es ist ein kleines Ziel, und jede Zeile hat eines; prüfen Sie deshalb, ob Sie in der richtigen Zeile sind, bevor Sie darauf klicken.
2. Klicken Sie darauf. Es öffnet sich eine Rückfrage mit der Überschrift **Diese Stunden entfernen?** und dem Text „1:30 für Interne Besprechung entfällt an diesem Tag und im Monatswert.“
3. Klicken Sie auf **Entfernen**, um es zu tun, oder auf **Abbrechen**, um den Eintrag zu behalten.

Danach kommt keine Meldung. Die Zeile verschwindet aus der Liste und die Summen sinken; daran erkennen Sie, dass es geklappt hat.

Das Papierkorb-Symbol sehen Sie nicht an einem Tag in einem Monat, der nicht mehr offen ist, und auch nicht bei einem Eintrag, den ein abgeschlossener Monat bereits gezählt hat.

### Welche Tage Sie öffnen können

- **Jeden Tag des Monats, den Sie gerade ansehen**, solange der Monat nicht eingereicht ist.
- **Tage, die noch kommen.** Sie sind zunächst ausgeblendet. Unter der Tabelle steht eine Schaltfläche **Rest des Monats anzeigen**, mit der Anzahl der ausgeblendeten Tage dahinter. Klicken Sie darauf, dann erscheinen sie; sie lassen sich öffnen und nehmen Stunden an wie jeder andere Tag. Nichts hindert Sie daran, einen Tag zu erfassen, bevor er stattgefunden hat.
- **Jeden alten Monat, der nie eingereicht wurde.** Das ist Absicht: So werden Monate aus der Zeit nachgetragen, bevor das Unternehmen Plane verwendet hat. Ein alter Monat bleibt offen, bis ihn jemand einreicht.
- **Tage in einem Monat, der eingereicht, genehmigt oder abgeschlossen ist**, lassen sich auch öffnen, aber nur zum Anschauen. Siehe unten.

## Stunden, die jemand für Sie erfasst

Stunden können in Ihren Monat kommen, ohne dass Sie sie dort eingetragen haben. Es gibt drei Wege, und alle drei sind für Sie sichtbar.

**Jemand erfasst Arbeit auf einem Arbeitselement für Sie.** Auf einem Arbeitselement steht neben **Timer starten** die Schaltfläche **Arbeit erfassen**. Sie öffnet ein kleines Feld mit **Start**, **Ende** und einer Beschreibung und erfasst eine Arbeitsspanne, ohne dass ein Timer gelaufen ist. Ein Projektadministrator sieht zusätzlich das Feld **Arbeit erfassen für**, mit dem er den Eintrag einem anderen Mitglied des Projekts zuschreiben kann. So erfasst, gehören die Stunden Ihnen: Sie zählen in Ihrem Monat, an dem Tag, auf den die **Start**-Zeit fällt, genau so, als hätten Sie den Timer laufen lassen. Sie erscheinen im Reiter **Arbeitsberichte** dieses Arbeitselements, mit dem Namen der Person, der die Zeit gehört.

Über dasselbe Feld erfassen Sie Arbeit, die Sie ohne Timer gemacht haben — eine Besprechung zu einem Arbeitselement oder einen Nachmittag, an dem Sie vergessen haben, auf Start zu klicken. Voreingestellt ist eine Stunde, die jetzt endet. Ändern Sie **Start** und **Ende**, ergänzen Sie eine Beschreibung und klicken Sie auf **Speichern**.

**Jemand übernimmt Stunden aus einer Datei.** Die Teamleitung kann Stunden aus einer Tabelle einlesen und in die Monate der einzelnen Personen schreiben. Sie kommen als Stunden ohne Arbeitselement an, tragen in der Zeile die Kennzeichnung **Importiert** und werden meist mit der Art **Importiert** angezeigt. Siehe „Stunden von anderswo übernehmen“.

**Ein Projektadministrator stoppt einen Timer, den Sie haben laufen lassen.** Im Reiter **Arbeitsberichte** eines Arbeitselements sieht ein Administrator neben jeder Person, deren Timer dort läuft, eine Stopp-Schaltfläche. Die Zeit bis zu diesem Moment wird als Ihre erfasst.

Eines geht von keinem Bildschirm aus: Niemand kann Stunden ohne Arbeitselement für Sie in Ihren Tag eintippen. Dieses Fenster betrifft immer den eigenen Tag, auch bei der Teamleitung. Stunden dieser Art für jemand anderen kommen über den Import hinein.

## Wenn der Monat eingereicht ist

Solange ein Monat **Nicht abgegeben** oder **Wieder geöffnet** ist, steht Ihnen alles auf dieser Seite offen. Sobald Sie auf **Einreichen** klicken, können Sie ihn nicht mehr ändern — und alles darin auch nicht, ob es aus einem Timer, aus dem Tagesfenster oder aus einer Datei stammt.

Sie können jeden Tag weiterhin öffnen und ansehen. Statt des Formulars sehen Sie:

> Dieser Monat ist nicht mehr offen, seine Stunden lassen sich deshalb nicht mehr ändern. Bitten Sie die Teamleitung, ihn wieder zu öffnen, wenn etwas korrigiert werden muss.

Es gibt keine Schaltfläche **Hinzufügen** und keine Papierkorb-Symbole.

Von der anderen Seite gilt dasselbe. Ein Timer, der in einen Monat hinein gestartet, gestoppt, bearbeitet oder gelöscht wird, der eingereicht, genehmigt oder abgeschlossen ist, wird abgelehnt, mit „Diese Stunden fallen in einen Monat, der bereits abgeschlossen ist. Öffnen Sie ihn zuerst wieder, wenn sie wirklich dorthin gehören.“

Wenn Sie einen Tag offen hatten, während jemand den Monat eingereicht oder abgeschlossen hat, bekommen Sie beim Hinzufügen eine Meldung mit der Überschrift **Nicht durchgeführt**:

> März 2026 ist eingereicht, deshalb lassen sich seine Einträge nicht mehr ändern. Bitten Sie die Teamleitung, ihn unter Teamzeit wieder zu öffnen.

Etwas in einem eingereichten Monat zu korrigieren heißt, zuerst darum zu bitten, dass der Monat wieder geöffnet wird. „Der Monat, von offen bis abgeschlossen“ erklärt das.

## Ein Monat, durchgerechnet

Anna arbeitet von Montag bis Freitag und schuldet an jedem Arbeitstag 7 Stunden 42 Minuten. Ihr Monat hat 21 Arbeitstage. Einer davon ist ein Feiertag, und sie nimmt zwei Urlaubstage; tatsächlich bei der Arbeit ist sie also an 18 Tagen.

**Was sie schuldet.**

```
21 Arbeitstage × 7:42 = 161:42
```

Der Feiertag verringert das nicht, und der Urlaub auch nicht. Nichts verringert das, was Sie arbeiten müssen. Abwesenheiten und Feiertage werden stattdessen zum **Ist** dazugezählt, damit die Stundenspalte, die in die Lohnverrechnung geht, die Stunden sind, für die sie bezahlt wird. Ihr Plus oder Minus kommt so oder so gleich heraus.

**Was sie erfasst hat.** An den 18 Tagen, an denen sie bei der Arbeit war, ergaben ihre Timer 133:00, und sie hat 6:00 an Stunden ohne Arbeitselement hinzugefügt — drei Teambesprechungen und etwas Verwaltung.

**Was der Monat zählt.**

|                                  |            |
| -------------------------------- | ---------- |
| Arbeitselemente (Timer)          | 133:00     |
| Ohne Arbeitselement (eingetippt) | 6:00       |
| Feiertag                         | 7:42       |
| Zwei Urlaubstage                 | 15:24      |
| **Ist**                          | **162:06** |
| **Soll**                         | **161:42** |
| **Saldo**                        | **+0:24**  |

Sie hat für den Monat 24 Minuten Vorsprung.

**Ein Tag daraus.** Am Dienstag, dem 10. März, liefen ihre Timer 5 Stunden 30 Minuten, sie saß eine Stunde in einer Teambesprechung und verbrachte eine halbe Stunde mit der Spesenabrechnung. Sie öffnet den Tag, fügt `1:00` als **Interne Besprechung** mit der Notiz „Sprint-Planung“ hinzu und `0:30` als **Verwaltung** mit der Notiz „Spesen März“. Am Fuß der Liste steht bei **Stunden ohne Arbeitselement** `1:30`. Ihre Tageszeile lautet dann:

| Tag           | Art des Tages | Soll | Arbeitselemente | Ohne Arbeitselement | Abwesend | Ist  | Saldo |
| ------------- | ------------- | ---- | --------------- | ------------------- | -------- | ---- | ----- |
| Di., 10. März | Arbeitstag    | 7:42 | 5:30            | 1:30                | 0:00     | 7:00 | -0:42 |

`5:30 + 1:30 = 7:00`, und `7:00 − 7:42 = −0:42`. An diesem Tag fehlen ihr 42 Minuten. Über den Monat gleicht es sich aus.

**Wenn Sie uns Ihre Stunden selbst in Rechnung stellen**, gibt es für Sie kein Tagessoll; Ihr **Saldo** ist deshalb jeden Tag 0:00, und ein Feiertag ist für Sie nichts wert. Alles, was Sie erfassen, zählt trotzdem, und daraus wird Ihre Rechnung geschrieben. „Personen und ihre Dienstverhältnisse“ erklärt, welche Vereinbarung welche ist.

## Wenn Sie nicht weiterkommen

- Um die Zahlen in Ihrem eigenen Monat zu verstehen und zu wissen, was am Monatsende zu tun ist: „Meine Zeit — Ihr eigener Monat“ und „Der Monat, von offen bis abgeschlossen“.
- Zum Feld mit Beginn, Ende und Pause oben am Tag: „Wann Sie bei der Arbeit waren“.
- Um jeden Eintrag zu sehen, aus dem ein Monat besteht, Zeile für Zeile: „Stunden im Detail“.
- Für alles rund um Abwesenheit — Krankenstand, Urlaub oder ein anderer Grund: „Abwesenheit von der Arbeit“ und „Urlaub“.
- Was ein Feiertag für Sie wert ist: „Feiertage“.
- Für Stunden, die aus einer Tabelle eingelesen werden: „Stunden von anderswo übernehmen“.
- Wenn eine Zahl falsch aussieht und nichts davon es erklärt: „Wenn etwas schiefgeht“.

Alles, wofür ein Monat wieder geöffnet, ein Eintrag aus einem abgeschlossenen Monat genommen oder Stunden für jemand anderen erfasst werden müssen, läuft über die Teamleitung. Fragen Sie dort nach.
