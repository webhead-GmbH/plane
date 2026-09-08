# Bringing hours in from somewhere else

This page is for whoever looks after the team, when hours, absences or balances were recorded somewhere else — an old spreadsheet, the system used before this one — and they need to end up in here. It explains the three kinds of file, what the headings have to say, how the check works before anything is written, and how to take a whole file back out again. It assumes your spreadsheet came out of Excel.

Only whoever looks after the team can use this screen. If that is not you, the page you want is "My time — your own month".

## What is on this page

- [Where the screen is](#where-the-screen-is)
- [The three kinds of file](#the-three-kinds-of-file)
- [Start from the template](#start-from-the-template)
- [What each column means](#what-each-column-means)
- [How a length of time is read](#how-a-length-of-time-is-read)
- [How a date is read](#how-a-date-is-read)
- [The check, before anything is written](#the-check-before-anything-is-written)
- [Why a row was refused or skipped](#why-a-row-was-refused-or-skipped)
- [Applying](#applying)
- [What applying does not do](#what-applying-does-not-do)
- [Undoing a whole file](#undoing-a-whole-file)
- [A worked example](#a-worked-example)
- [Decide how far back to go, before you start](#decide-how-far-back-to-go-before-you-start)
- [Things that catch people out](#things-that-catch-people-out)
- [If you get stuck](#if-you-get-stuck)

## Where the screen is

1. In the sidebar, open **My time**.
2. At the top right of that screen, open the **…** menu and choose **Everyone’s hours**. You are now on **Team time**.
3. In the row of links beside the month name, choose **Bring earlier records in**.

The screen opens with one line of grey text under the heading, a bordered card with a dropdown and two buttons, and at the bottom a list headed **Files brought in before**. If nothing has ever been brought in, that list reads **Nothing has been brought in yet.**

If you see **This is not yours to see** instead of the card, your account is not set up as somebody who looks after the team. Ask for that to be changed on the **People** screen.

Do not drag a file onto the card. There is nothing here that catches a dropped file, so the browser leaves this page and opens the file instead, and you have to find your way back. Use the **Choose a file** button.

## The three kinds of file

The dropdown is labelled **What the file holds**. It has three options, and it decides how your file is read.

| Option                | What it writes                                                      | Where it shows up afterwards                                                 |
| --------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Hours**             | Hours somebody worked on a given day, with no work item behind them | On that person's day, under **Hours with no work item**, tagged **Imported** |
| **Absences**          | Days somebody was away, already agreed                              | On the **Absences** screen, in the state **Agreed**                          |
| **Starting balances** | The figure a person's running balance starts from                   | On that person's record, under **Starting balance**                          |

Two things about the dropdown are worth knowing before you start.

It always opens on **Hours**, and it never resets itself. The commonest first mistake is to choose **Absences**, press **Download a template**, fill the template in, and then press **Choose a file** without going back to the dropdown. The file is then read as hours, it has no `date` column, and every single row comes back as **Cannot be read**. Set the dropdown, then choose the file, in that order.

The check that follows names the kind it used. The heading above the checked rows reads, for example, _maerz-2026.csv, read as Hours_. Read that line before you read anything else. If it says the wrong word, nothing has been written; set the dropdown properly and choose the file again.

## Start from the template

Press **Download a template** with the right kind chosen. A small CSV file lands in your downloads, named after the kind: `time_entries-template.csv`, `absences-template.csv` or `opening_balances-template.csv`. It has the heading row and one example row, so you can see the shape.

Open it, delete the example row, paste your own rows in, and save it. The template is written so that Excel opens it without mangling umlauts in names.

You may also bring your own file. It has to be a `.csv` file or an Excel `.xlsx` workbook, and no larger than 5 MB. In a workbook, only the sheet it opens on is read, and the column headings must be its first row — anything on a second sheet is ignored without a word.

A CSV file may separate its columns with commas, semicolons or tabs. Whichever of the three appears most often in the heading line is the one used. This matters because Excel on a German or Austrian Windows saves CSV with semicolons; such a file is read correctly here.

## What each column means

Headings are matched after the spaces are trimmed, capitals are lowered, and any remaining spaces are turned into underscores. So `Email`, `EMAIL` and `email` all work, and `Start Date` becomes `start_date`.

A hyphen is not touched. **`E-Mail` is not recognised as a heading.** That is how the column is spelled in German, and it is what an existing office spreadsheet is most likely to have at the top of it. If every row comes back saying nobody logs in as nothing, the heading is the thing to look at, not the addresses. Write it `email`.

The order of the columns does not matter. Extra columns are ignored.

### Hours

| Heading                  | Required         | What goes in it                                                                  |
| ------------------------ | ---------------- | -------------------------------------------------------------------------------- |
| `email`                  | Yes              | The address the person signs in with. `e_mail` also works for this kind of file. |
| `date`                   | Yes              | The day the hours were worked. `datum` also works.                               |
| `hours` **or** `minutes` | Yes, one of them | How long. See the next section. `stunden`, `std` and `minuten` also work.        |
| `note`                   | No               | Kept with the entry and shown beside it. `notiz` also works.                     |

### Absences

| Heading      | Required | What goes in it                                                   |
| ------------ | -------- | ----------------------------------------------------------------- |
| `email`      | Yes      | The address the person signs in with.                             |
| `start_date` | Yes      | First day away. `von` also works.                                 |
| `end_date`   | No       | Last day away. Leave it empty for a single day. `bis` also works. |
| `type`       | Yes      | The code for the reason. `art` also works.                        |

The codes set up as standard are `urlaub` (annual leave), `krankenstand` (sick leave), `zeitausgleich` (time off in lieu), `pflegefreistellung` (care leave), `dienstverhinderung` (other justified absence) and `unbezahlt` (unpaid leave). The list your company actually has is on the **Absences** screen, under **Reasons**.

An absence brought in this way is written as already **Agreed**, in whole days. On the **Absences** screen its **Reason** column reads the name of the type followed by "Imported from a previous system.", which is how you tell an imported row from one somebody asked for. Half days cannot be brought in; record those on the **Absences** screen by hand.

How long each absence is worth is worked out from that person's working week, not from the number of days in the range. A week of leave for somebody who works Monday to Wednesday costs three days, not five.

### Starting balances

| Heading                  | Required         | What goes in it                                                                                                                                                                                                                                                                                                                                      |
| ------------------------ | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `email`                  | Yes              | The address the person signs in with.                                                                                                                                                                                                                                                                                                                |
| `date`                   | Yes              | The day the balance applies from. `effective_on` also works.                                                                                                                                                                                                                                                                                         |
| `hours` **or** `minutes` | Yes, one of them | The balance itself. A minus sign means they are behind. Zero is allowed.                                                                                                                                                                                                                                                                             |
| `basis`                  | Yes              | Where the figure came from, in words. `grundlage` also works. A row with this cell empty is refused.                                                                                                                                                                                                                                                 |
| `kind`                   | No               | `time` for hours, `leave` for leave, `overtime` for overtime to be paid. Empty means `time`.                                                                                                                                                                                                                                                         |
| `confidence`             | No               | How sure the figure is: `documented` or `exact` records it as **Taken from records**, `reconstructed` as **Worked out from other records**, `estimated` as **Estimated**, `agreed` as **From a conversation with them**. An empty cell, or any other word, is recorded as **From a conversation with them**, and a misspelling here is not reported. |

**Only a balance of kind `time` is counted anywhere.** A balance brought in as `leave` or `overtime` is stored and shown on the person's record, and no calculation reads it. Leave for the year is set per person on the **People** screen, with **Add a leave year** and **Leave for the year**. If you bring everybody's remaining leave over from the old spreadsheet as a starting balance, it will look accepted and it will do nothing.

## How a length of time is read

**The column heading decides what a plain number means. The number itself never does.**

- Under an `hours` heading, `7.7` means seven hours and forty-two minutes.
- Under a `minutes` heading, `462` means the same thing.
- Written `7:42`, it means the same under either heading, because it says what it is.

So `462` under an `hours` heading is 462 hours, which is more than a day, and the row is refused. And `7.7` under a `minutes` heading is seven minutes, and is written without complaint.

Other rules that have been settled:

| You write    | Under `hours`                                       | Under `minutes`                          |
| ------------ | --------------------------------------------------- | ---------------------------------------- |
| `8`          | 8:00                                                | 0:08                                     |
| `0.5`        | 0:30                                                | 0:00 — a fraction of a minute is dropped |
| `7.99`       | 7:59 — 479.4 minutes, rounded to the nearest minute | 0:07                                     |
| `6,42`       | 6:25 — a comma is accepted as the decimal point     | 0:06                                     |
| `-1.5`       | −1:30                                               | −0:01                                    |
| `-1:30`      | −1:30                                               | −1:30                                    |
| `half a day` | refused                                             | refused                                  |

A decimal under an `hours` heading is rounded to the nearest minute. A decimal under a `minutes` heading has its fraction thrown away, which is why an hours figure put under a `minutes` heading comes out as a handful of minutes and looks like nothing at all.

If a file has both a `hours` and a `minutes` column with something in them, the minutes column is used, because minutes cannot lose a remainder.

A negative length is allowed, and is how a correction is brought in. Zero is not: a row of zero hours is refused, because zero would have to mean something and nobody can say what. Leave the day out of the file instead.

Nothing may come to more than 24 hours in one day, in either direction.

## How a date is read

Three ways of writing a date are read:

- `2026-03-02`
- `02.03.2026`
- `02/03/2026`

**Take care with the third one.** A date with slashes is read day first, always, with no way for the file to say otherwise. `03/04/2026` is 3 April, not 4 March. A file that came out of an English-language system, where that would have meant 4 March, is read a month out and every row still comes back as **Will be written**. Nothing warns you. If your file has slashed dates, change the column to `2026-03-02` form before you upload it.

In an Excel workbook, a real date cell is used as it stands.

Any date the reader cannot make sense of gives you **The date could not be read.** — which is a refusal you can see and fix. A date read the wrong way round is not.

## The check, before anything is written

Press **Choose a file** and pick the file. It is uploaded and read, and **nothing is written**. A panel appears between the card and the list, headed with your file name and the kind it was read as, and under that: _Nothing has been written yet. Rows are added to whatever is already recorded for those days, so a day brought in twice counts twice. To correct a file that is already in, undo it first instead of bringing in a corrected copy._

### The three counts

| Count               | What it counts                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| **will be written** | Rows that passed every check. Only these are written when you apply.                                   |
| **cannot be read**  | Rows with something wrong in them. They are never written, and applying does not stop because of them. |
| **skipped**         | Rows for a month that is no longer open. Also never written.                                           |

The three always add up to the number of data rows in the file.

### The table

Three columns: **Row**, **What happens** and **Detail**. The rows are grouped, not left in file order — everything that **Cannot be read** first, then everything **Skipped**, then everything that **Will be written**. Within each group the file's own order is kept.

**Row** is the line number in the spreadsheet, counting the heading row as line 1. It is the same number Excel shows down the left-hand side, which is what you are looking at while you fix the file. Row 9 is the ninth line of the file, which is the eighth line of your data. The first data row is always Row 2.

**Detail** says one of two things. For a row that cannot be used, it is the reason. For a row that will be written, it is a short description of what is about to be stored, so that the number on the apply button is something you can check rather than something you have to trust:

- An hours row shows the date, written with the year, and the length: _2 Mar 2026 · 7:42_.
- An absence row shows **only its first day**. A single day off and a fortnight of leave look exactly the same here. Since imported absences are written as already agreed and draw down somebody's leave, check the end dates in your own file before you apply, because this table will not show them to you.
- A starting balance shows the date and the figure — except that **a balance of zero shows no figure at all**. A file that starts everybody at zero is therefore a column of bare dates. That is correct, and it is not an empty row.

The table scrolls inside its own box. There is no search and no filter, so for a long file, scroll.

### Leaving it and coming back

**Leave it for now** closes the panel. It does not delete anything and it does not undo anything. The file stays in **Files brought in before** in the state **Waiting to be applied**, and you can bring the panel back at any time with **Open it again** on that row.

Because of that, a file you uploaded twice by mistake is two rows waiting to be applied, and applying both would write everything twice.

## Why a row was refused or skipped

These are the exact sentences you will see in the **Detail** column.

| What it says                                                                                                                   | What is wrong                                                                    | What to do                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Nobody here logs in as {address}. Add the person under People, or correct the address in the file.                             | The address is blank, misspelt, or belongs to somebody with no employment record | Correct the file, or set the person up on **People** first. If it names nothing at all, look at the heading — see `E-Mail` above |
| The date could not be read.                                                                                                    | The date cell is empty, or in a form not recognised                              | Write it as `2026-03-02` or `02.03.2026`                                                                                         |
| The start date could not be read.                                                                                              | Same, on an absences file                                                        | Same                                                                                                                             |
| The amount of time could not be read, or it is zero. Every row needs a length of time — leave the day out of the file instead. | The length cell is empty, unreadable, or zero                                    | Put a real length in, or delete the row                                                                                          |
| That is more than 24 hours in one day. Check whether the number is hours or minutes, and that the column heading matches.      | The row comes to more than 24 hours either way                                   | Usually a minute figure sitting under an `hours` heading                                                                         |
| That month is no longer open, so nothing more can go into it. Ask for it to be reopened if this has to go in.                  | The month has been handed in, agreed or closed. This is a **skip**, not an error | If it genuinely has to go in, reopen that person's month on **Team time** first, then upload the file again                      |
| The balance could not be read.                                                                                                 | On a starting-balance file, the balance cell is empty or unreadable              | Write it as `12:30`, `-12:30` or a decimal. Zero is fine here                                                                    |
| The kind column must say time, leave or overtime.                                                                              | The `kind` cell holds some other word                                            | Use one of those three. An empty cell is fine and means hours                                                                    |
| The basis column is empty. Write where the figure came from, for example: from the old leave spreadsheet.                      | The `basis` cell is empty, and it is required                                    | Say where the number came from, in words                                                                                         |
| It ends before it starts.                                                                                                      | `end_date` is earlier than `start_date`                                          | Swap them, or clear the end date for a single day                                                                                |
| No reason for being away has the code "{code}". The codes are on the **Absences** screen, under **Reasons**.                   | The `type` cell is not one of the codes set up here                              | Use one of them, or add the reason first                                                                                         |

Note that "that month is no longer open" is said about a month that has merely been **Handed in**, as well as one that is **Agreed** or **Closed**. All three have stopped being recalculated, so nothing new can be counted into any of them.

## Applying

**Applying writes the rows. There is no confirmation step: one press and it is done.** It can be undone as a whole file, but only under the conditions in the next section but one, so read the check first.

1. Read the heading and make sure it names the kind you meant.
2. Read the counts. If **cannot be read** or **skipped** is not zero, look at those rows and decide whether to fix the file and start again.
3. Press the button, which reads **Apply 22 rows** — the number is however many will be written. If nothing can be used it reads **Apply 0 rows** and cannot be pressed.
4. A green message appears: **Applied**, and under it **22 rows written**. The panel closes. In **Files brought in before** the file now shows **Applied**, with **Undo** beside it.

The number in the message is what was actually written, and it should match the number on the button.

If a red message appears instead — **That did not go through** — nothing was written, and the panel stays open so you lose nothing. See "Things that catch people out" below for what the sentences mean.

**Apply on the same day you check.** Whether a month is still open is decided when the file is _checked_, and it is not asked again when the file is _applied_. A file checked on Monday and applied on Friday, with somebody's month handed in on the Wednesday, writes its rows into that month — where nothing will ever count them, and nobody will see why the month is short. If a checked file has been sitting for more than a day, upload it again rather than pressing **Open it again**.

## What applying does not do

**It does not recalculate anybody's month.** The rows are written straight away, but the figures on **My time** and **Team time** are worked out again only when somebody opens that month. For the current month and the one before it, that also happens by itself once an hour. For anything older, nothing changes on screen until somebody steps to that month.

So if you bring in last spring and then go and look at last spring, you will see it. If you look at the figure on some summary first, you may see nothing and conclude the import failed. It did not. Do not bring the file in a second time — check **Files brought in before** instead, where the file will say **Applied**.

**It does not reach the customer billing system.** Imported hours are deliberately written as hours with no work item behind them, so they are never mirrored into invoicing. Bringing in three years of history does not replay three years of invoices.

**It does not stop you bringing the same day in twice.** Two rows for the same person and day write two entries and the day adds up to both. The only guard is against uploading the byte-for-byte identical file after it has been applied, which is refused with "This exact file has already been applied." A file that differs by one character is a different file and will happily write its rows a second time.

## Undoing a whole file

Undo removes everything one file wrote, and nothing else. It is per file, not per row.

**It cannot be done at all once any of what the file wrote has been counted into a closed month.** Not partly: the whole undo is refused and nothing is removed. The dialog you are about to see says as much.

1. Find the file in **Files brought in before**. Only a file showing **Applied** has an **Undo** beside it.
2. Press **Undo**. A dialog opens, headed **Undo maerz-2026.csv?**, saying: _Everything this file wrote is taken back out, and nothing else is touched. If any of it has been counted into a month that is now closed, nothing is taken out until that month is reopened._
3. Type an answer to **Why is it being undone?** It is required — the button stays greyed out until you have typed something. What you type is kept with the file, with your name and the time.
4. Press **Undo it**. **Leave it as it is** closes the dialog and does nothing.
5. A green message: **Undone**, and under it **22 rows removed**. The file's state becomes **Undone** and it has no buttons beside it any more.

If instead you get **That did not go through** with "Some of this has been counted into a month that is now closed. Reopen the month first.", then part of what the file wrote is inside a closed month. Nothing has been removed. Reopen that person's month with **Reopen** on **Team time**, come back and undo, then close the month again.

Undoing does not recalculate anybody's month either. The same rule as above applies.

A file that has been undone may be corrected and brought in again. The identical-file guard only looks at files that are currently applied.

There is no way to remove a row from **Files brought in before**. Every file ever uploaded stays listed, newest first, including ones that failed. The rows carry no date, so two uploads of `maerz-2026.csv` look identical. Before you press **Undo** on one of two rows with the same name, press **Open it again** on the other one and check which is which — undoing the wrong one deletes a month of hours that were correct.

## A worked example

Anna works Monday to Friday and owes **7:42** a day. That is 462 minutes. Her March has 21 working days, one of which is a public holiday, and she took two days of leave. Her March was recorded in the old spreadsheet and never went into this system.

**What she owes for the month.** 21 working days × 7:42 = 9702 minutes = **161:42**. Public holidays and leave do not reduce this. **To work** stays at 161:42 whatever happens.

**What has to come from the file.** She was actually at a desk on 21 − 1 − 2 = **18 days**. Those are the only days that belong in the hours file. The public holiday is credited from the **Public holidays** calendar, and the two days of leave are credited from the **Absences** screen. Both are added to **Worked**, not taken off **To work**.

**The file.** Sofia, who runs the month, presses **Download a template** with **Hours** chosen and pastes Anna's 18 days into it, plus five days for a colleague, plus a stray day from February. Twenty-four data rows, so spreadsheet lines 2 to 25.

**The check.** She presses **Choose a file**. Nothing is written. The panel reads _maerz-2026.csv, read as Hours_, and:

- **22 will be written**
- **1 cannot be read**
- **1 skipped**

| Row | What happens    | Detail                                                                                                           |
| --- | --------------- | ---------------------------------------------------------------------------------------------------------------- |
| 9   | Cannot be read  | Nobody here logs in as anna.berger@exampel.com. Add the person under People, or correct the address in the file. |
| 25  | Skipped         | That month is no longer open, so nothing more can go into it. Ask for it to be reopened if this has to go in.    |
| 2   | Will be written | 2 Mar 2026 · 7:42                                                                                                |
| 3   | Will be written | 3 Mar 2026 · 7:42                                                                                                |

Row 9 is line 9 of the spreadsheet — the eighth line of data — and the address is misspelt. Row 25 is the February day, and February has already been closed.

**Applying.** She presses **Apply 22 rows** and gets **Applied** / **22 rows written**.

**What Anna's March now shows,** once somebody opens March:

|                                                  | Minutes            | Shown as   |
| ------------------------------------------------ | ------------------ | ---------- |
| 17 days brought in (one row of hers was refused) | 17 × 462 = 7854    | 130:54     |
| The public holiday                               | 462                | 7:42       |
| Two days of leave                                | 2 × 462 = 924      | 15:24      |
| **Worked**                                       | 9240               | **154:00** |
| **To work**                                      | 9702               | **161:42** |
| **Balance**                                      | 9240 − 9702 = −462 | **−7:42**  |

The missing 7:42 is the one day whose email address was misspelt.

**Fixing the one row.** Sofia corrects the address, saves _only that one row_ as a new file, uploads it, gets "1 will be written" and presses **Apply 1 row**. March now shows **Worked** 161:42, **To work** 161:42, **Balance** 0:00.

She must not upload the whole corrected file. It differs by one character from the one already applied, so the identical-file guard will not stop it, and all its good rows would go in again on top of the ones already there — Anna's March would come out at nearly twice her hours.

**What would have happened had the file listed all 21 working days,** the public holiday and the two days of leave included, with every row written. Hours from the file: 21 × 462 = 9702. Plus the holiday, 462. Plus the leave, 924. **Worked** = 11088 minutes = **184:48**, against **To work** of 161:42 — a **Balance** of **+23:06** for a month Anna in fact finished exactly level. The days off are already paid for. Do not put them in the hours file as well.

## Decide how far back to go, before you start

Three things follow from bringing old months in, and all three are easier to decide now than to unpick later.

**Months are closed in order.** Each month opens on what the month before it closed with. Once a month holds days with anything in them — and an applied import gives it exactly that — the month after it cannot be closed until it has been closed itself. If you bring in two years of history to give the balance a past, those twenty-four months now have to be handed in, agreed and closed in order, oldest first, before you can close the month payroll is waiting for.

**A balance starts counting on the day of its starting balance.** Hours dated before that day are checked, written, and visible if somebody opens the month — and they never reach the running balance. Everything before that date is deliberately out of scope. If there is no starting balance for somebody, counting begins at their hire date.

**So do it in this order:** decide the earliest day you want the running balance to count from, bring the hours and absences in first, then record the starting balance on that day. Bringing the balances in first and the three years of spreadsheets afterwards makes the older half of the work inert.

## Things that catch people out

**"The payload is not valid".** This one sentence appears on a starting-balance file and means something specific: somebody in the file already has a starting balance recorded for that day and that kind, or two rows in your file are for the same person, kind and day. Only one is allowed. Nothing at all was written — not that row, not any other row in the file — so take the duplicate out and apply again, or correct the existing figure on the person's record instead. The rows still show **Will be written**, because this is not something the check looks for.

**"That file is larger than this accepts".** Over 5 MB. Save it as CSV rather than a workbook, or split it.

**"The file could not be read. Check it is a CSV or XLSX".** Nothing could be got out of the file at all — a damaged workbook, an empty file, something renamed. The file is still listed, forever, as **Could not be read**. Re-save it from the spreadsheet.

**"This import has not been checked, or has already been applied".** Somebody else applied that file first, from another browser. Reload the page and look at the file's state.

**Every row says nobody logs in as nothing.** The `email` heading is not being recognised. `E-Mail` is the usual cause.

**A whole file read as the wrong kind.** The dropdown was left on **Hours**. Nothing was written; set it and choose the file again.

**A person's figures have not moved.** They are recalculated when somebody opens that month. See "What applying does not do".

**Somebody's To work and Balance stay at 0:00.** Two of the four arrangements — **Remote, full time, invoices us** and **Remote, part time, invoices us** — record no hours the person owes. For them **To work** is 0:00 and so is **Balance**, however many hours you bring in. **Worked** does go up. That is correct, not a failed import. "People and their terms" explains the arrangements.

**Correcting a single imported row.** There is no way to edit one. The person themselves can remove it from their own day on **My time** while their month is still open — imported hours show there with a small **Imported** tag. Otherwise, undo the whole file and bring in a corrected one.

## If you get stuck

- To see what was actually written for somebody, and on which days, use **Hours in detail** — "Hours in detail" explains that screen.
- To reopen a month so an import can go into it, or so an undo can happen, use **Reopen** on **Team time** — "The month, from open to closed" explains what reopening does and what it costs.
- To set somebody up before their rows can be matched, or to record a starting balance or a leave year by hand, use **People** — "People and their terms".
- For what an imported absence does to a month and to the leave account, see "Time away from work" and "Leave".
- For what a public holiday is worth to each person, see "Public holidays".
- For a refusal not listed here, see "When something goes wrong".

If a file behaves in a way this page does not describe, do not apply it a second time to see whether it takes. Leave it, and ask whoever looks after the team.
