# When something goes wrong

This page is for anybody who pressed a button and was told no. It lists every message the working-time screens can put in front of you, says what each one means, why it happened, and what to do next. Find the words you saw, read that entry, and stop. You are not meant to read this page from beginning to end.

## Contents

- [The three places a message appears](#the-three-places-a-message-appears)
- [Messages about a month that is no longer open](#messages-about-a-month-that-is-no-longer-open)
- [Messages when you hand your month in](#messages-when-you-hand-your-month-in)
- [Messages when a month is agreed, closed or reopened](#messages-when-a-month-is-agreed-closed-or-reopened)
- [Messages when you record hours](#messages-when-you-record-hours)
- [Messages when you record when you were at work](#messages-when-you-record-when-you-were-at-work)
- [Messages about time away from work](#messages-about-time-away-from-work)
- [Messages about people, terms, rates, leave and starting balances](#messages-about-people-terms-rates-leave-and-starting-balances)
- [Messages about public holidays](#messages-about-public-holidays)
- [Messages when you bring records in from a file](#messages-when-you-bring-records-in-from-a-file)
- [Messages that fill the whole page](#messages-that-fill-the-whole-page)
- [Messages that were written for a programmer](#messages-that-were-written-for-a-programmer)
- [Messages that mean nothing is wrong](#messages-that-mean-nothing-is-wrong)
- [Things that go wrong without saying anything](#things-that-go-wrong-without-saying-anything)
- [A worked example: a month that would not close](#a-worked-example-a-month-that-would-not-close)
- [If you get stuck](#if-you-get-stuck)

---

## The three places a message appears

There are only three, and they mean different things.

| Where it appears                              | What it looks like                                    | What it means                                                                                                                                                        |
| --------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A red line under the boxes you are filling in | Small red text, just above the buttons of the dialog  | Nothing has been sent anywhere. The screen itself will not send it until you change what you typed. Nothing has been saved and nothing has been lost.                |
| A red box in the corner of the screen         | A short bold title, and a sentence underneath         | Something was sent and the system said no. Nothing was saved. The sentence underneath is the part that matters — the bold title is nearly always the same few words. |
| A message filling the middle of the page      | A title, a sentence, sometimes a **Try again** button | The page could not be shown at all.                                                                                                                                  |

Two things are worth knowing before you look anything up.

**The bold title tells you almost nothing.** It is one of: **That did not go through**, **That could not be saved**, **That could not be done**, **That could not be settled**, **Not handed in**, **Could not bring it up to date**. Read the sentence below it.

**A few sentences come back in English even when the rest of your screen is in German.** That is not a fault and it does not mean something is broken. The entries below give the English wording, because that is what you will see.

If the sentence underneath is **Please try again.** or **Try again in a moment.**, the system had nothing to tell you. That is usually the connection, not you. Wait a few seconds and press the button once more. If it keeps happening, say so — see [If you get stuck](#if-you-get-stuck).

---

## Messages about a month that is no longer open

These are the commonest messages in the whole system, and they all mean one thing: the month you are trying to change has moved on. A month goes through **Not handed in**, **Handed in**, **Agreed**, **Closed**. Only a month that is **Not handed in** or **Reopened** can be changed.

### **"March 2026 has been closed, so its records can no longer change. Ask whoever looks after the team to reopen it on Team time."**

The month name is the month the day belongs to. The word in the middle is one of **handed in**, **agreed** or **closed**, whichever the month actually is.

**Why it happened.** You tried to add, change or remove hours, an attendance record or an absence on a day inside that month. The month has stopped being recalculated, so anything written into it now would sit in the records and never reach the figures. Rather than accept it quietly and let it vanish, the system refuses it.

**What to do.** Nothing you can do on your own. Ask whoever looks after the team to reopen the month on **Team time**. When it is open again, make your change, and it will be closed again afterwards.

### **"The month this belongs to has been closed. Reopen it if the record genuinely needs to change."**

Almost the same thing, in the case where the record itself was stamped when the month was closed rather than the day being worked out afresh. Same answer: ask for the month to be reopened.

### **"This month is no longer open, so its hours cannot be changed. Ask whoever looks after the team to reopen it if something needs correcting."**

This one is not a refusal — it is a notice inside the day dialog, where the boxes for adding hours would be. It appears the moment you open a day in a month that is **Handed in**, **Agreed** or **Closed**. There is nothing to press. The hours already on the day are still listed, and you can still read them.

### **"Nothing was recorded for this day, and the month is no longer open."**

The same notice in the **When you were at work** box. There was no start and end time for that day, and it is now too late to add one.

### **"This month is closed. Reopen it if it genuinely needs to change."**

You chose **Bring up to date** from the **…** menu on **My time** for a month that is no longer open.

Note the wording: it says "closed" whether the month is **Handed in**, **Agreed** or **Closed**. All three mean the same thing here — the figures have stopped moving on purpose. **Bring up to date** only does anything to a month that is still open.

---

## Messages when you hand your month in

### The **Hand in** button is not there at all

Not a fault. The button only exists while the month is still yours to change. Once you have handed it in, the button disappears and the word beside your figures changes to **Handed in**. Nothing has gone wrong and there is nothing else for you to do.

### **"The month is not over yet. It can be handed in once it has ended."**

This is a small label that appears when you rest the pointer on a greyed-out **Hand in** button. On a phone or tablet you may not be able to see it at all, which is why it is written out here.

**Why it happened.** The month has not finished. A month is handed in whole. If it were handed in on the 20th, the hours you were expected to work on the remaining days would be frozen as a shortfall, and anything you logged after that would never be counted.

**What to do.** Wait until the first day of the next month, then hand it in.

### **"A timer is still running on one of your work items, in this or another workspace. Stop it, then hand the month in."**

**Why it happened.** A timer somewhere has been started and never stopped. A running timer has no length, so any total including it would be out of date the moment anybody read it.

**What to do.** Find the timer and stop it. **Hours in detail** lists your month's hours and marks the ones that are still running with **Still running — it has no length yet and counts nothing**. Open that work item and stop the timer there. Then come back to **My time** and press **Hand in**.

The same sentence appears as a note beside your figures on **My time**, worded as **"A timer is still running on one of your work items, in this or another workspace. Stop it, then you can hand the month in."**

### **"Only an open month can be submitted."**

You pressed **Hand in** on a month that is no longer **Not handed in** or **Reopened** — usually because the page had been open for a while and somebody had already dealt with the month. Reload the page and look at the word beside your figures.

### **"This month is still running. It can be closed from 2026-04-01."**

The same rule as the greyed-out button, arriving from the system rather than from the screen. The date given is the first day after the month ends. Wait until then.

---

## Messages when a month is agreed, closed or reopened

These appear on **Team time** and only to whoever looks after the team. The bold title is **That did not go through**.

### **"Only a submitted month can be approved."**

**Agree** was pressed on a month that is no longer **Handed in**. Almost always the table on your screen is out of date: somebody else agreed it, or the person put it back. The table refetches itself after every action, so look at the row again. It will now say what actually happened.

### **"Approving your own month is not a decision. Ask someone else."**

**Why it happened.** You pressed **Agree** on your own row. Agreeing a month is one person confirming another person's figures, so the system will not let anybody do it to themselves — being the manager makes no difference.

**What is worth knowing.** The **Agree** button is shown on your own row exactly as on everybody else's, and it fails every time. There is no way past it on that screen: **Close** needs a month that is **Agreed**, and **Reopen** needs one that is **Closed**. Until a second person is made a manager, your own month cannot be agreed or closed at all.

**What to do.** Ask for a second person to be given **Looks after the team** on the **People** page, and have them agree your month.

### **"Only an approved month can be closed."**

**Close** was pressed on a month that is not **Agreed**. Reload; agree it first.

### **"October 2026 has not been closed yet, and this month opens on what that one closes with. Close it first, or the balance carried into this month starts again from nothing."**

**Why it happened.** Months are closed oldest first. Each closed month hands its **Running balance** on to the next one. Skip a month and the next one starts from zero, and every month after it is wrong.

**What to do.** Step back to the month named, close that one, then come forward again. If several months are outstanding, close them in order from the oldest.

An earlier month does not block you if it holds nothing at all — nobody was employed yet, or no day in it had hours either expected or worked. It does block you, however empty it looks, if it has ever been closed and then reopened.

### **"Some days are marked for review because hours counted earlier are no longer there. Settle those before closing the month."**

**Why it happened.** Hours that this month had already counted are gone — most often because somebody deleted a work item, which takes every timer on it. The figures still include those hours. The system will not close a month over that quietly, because a frozen figure nobody can account for is the one thing that makes the whole record untrustworthy.

**What to do.**

1. On **Team time**, look at the row for that person. The button reads **Look at those days**, and there is an orange warning triangle beside their name. Press either.
2. A dialog opens listing each affected day, with what the day **Counts as ... now**.
3. For each day, type into **What happened?** and press **Settle this day**. What you write is kept with the day, and the person it is about can read it.
4. When the dialog says **Nothing left to look at. This month can be closed.**, close it and press **Close** on the row.

Settling a day does not put the hours back. If they should still count, have them recorded again first, then settle the day.

### **"Only a closed month can be reopened."**

**Reopen** was pressed on a month that is not **Closed**. Reload the page.

### **"Say why the month is being reopened."** and **"Say what was decided about this day."**

The reason box was empty. Both dialogs keep the confirm button switched off until you type something, so you should not normally see these. If you do, type a sentence and press the button again.

### Before you press **Agree**: it cannot be taken back

**Agree** acts the moment you press it. There is no confirmation, and there is no step from **Agreed** back to **Handed in**.

If you agree the wrong row, the only way to undo it is to close that month and then reopen it with a written reason — and closing can itself be refused, by any of the messages above. Read the name in the row before you press.

**Close** is different: it asks first, and a closed month can be reopened.

---

## Messages when you record hours

These appear in the day dialog, which opens from **Record time for today** on **My time** or by pressing a day in the table.

### **"Say how long it was: 1:30, 7h, or 90m. A number on its own does not say whether you mean hours or minutes."**

**Why it happened.** You typed a bare number into **How long** — 20, say. In that box a bare number would be read as hours, and in the **Break (minutes)** box just above it a bare number is minutes. Somebody coming out of a twenty-minute meeting types 20 and means neither reliably, so the system asks which you meant rather than recording twenty hours.

**What to do.** Write it one of these ways.

| You mean                      | Type            |
| ----------------------------- | --------------- |
| Twenty minutes                | `20m` or `0:20` |
| One and a half hours          | `1:30` or `1.5` |
| Seven hours                   | `7h` or `7:00`  |
| Seven hours forty-two minutes | `7:42` or `7.7` |

### **"Say how long it was. Type 1:30 or 1.5."**

The same box, but what you typed could not be read at all, or came to zero. Retype it in one of the forms above. Zero is not accepted: an entry of no time is not a record of anything.

### **"An entry of no time is not a record of anything."**

The same thing, arriving from the system instead of from the screen. Type a real length.

### **"A single day cannot hold more than 24 hours."**

You typed something over 24 hours — `25:00` is readable, so the screen lets it through and the system refuses it. Check what you meant. If a piece of work really ran across two days, record it as two entries, one on each day.

### **"Remove these hours?"** — read this before you press **Remove**

Removing hours cannot be undone. The dialog tells you exactly what goes: for example, **"1:30 of Internal meeting comes off this day and off the month's total."** If that is not what you meant to remove, press **Cancel**.

### **"Not added yet. Press Add, or it is lost when you close."**

An amber warning, not an error. You have typed something into **How long** or **Note** and have not pressed **Add**. Closing the dialog now throws it away. Press **Add**.

---

## Messages when you record when you were at work

These appear in the **When you were at work** box at the top of the day dialog. It only appears for people whose terms say attendance is kept.

### **"Say what time you started."**

**From** is empty. Fill it in. An end time is not required — a day with a start and no end shows as **No end time yet**.

### **"Give the break in whole minutes."**

**Break (minutes)** holds something that is not a whole number of minutes — `1.5`, `-10`, or letters. Type `30` for half an hour. Leave the box empty if there was no break.

### **"That time did not happen on that date — the clocks went forward over it."**

Once a year the clocks go forward and an hour of that night does not exist. You have typed a time inside that missing hour. Check the time and retype it.

### **"The times and breaks do not leave any time worked. Check them over."**

Either the end time is before the start time, or the breaks add up to more than the day. Check all three boxes.

If the work genuinely ran past midnight, the box says so itself with **"Counted as running past midnight."** and shows you the length it would save, as **"This runs past midnight and comes to 9:15. Check the end time if that is not right."** Read that figure before you save.

### **"That is more than a day. If the work ran past midnight, say so."**

What you typed comes to more than 24 hours.

### **"Attendance is not recorded for this person."**

The terms this person works under do not keep a record of when they were at work, so there is nowhere to put it. If that is wrong, it is changed on the **People** page.

### **"Remove this attendance record?"** — read this before you press **Remove**

This cannot be undone: **"The start, end and break for this day are removed and cannot be brought back. If the times are wrong, change them and save instead."** Changing the times and pressing **Update** is nearly always what you want.

### **Record** keeps failing on a day that looks empty

If the box shows empty **From** and **To** fields and a button reading **Record**, and pressing it gives **That did not go through** every time, the day may already have a record that did not load. Only one record per day is allowed, so a second one is refused.

Close the dialog, reload the page in the browser, and open the day again. The times that were already there should now be visible, and the button will read **Update**.

---

## Messages about time away from work

These appear on the **Absences** screen. The bold title is **That could not be saved**, or **That could not be done** inside the **Reasons** dialog.

### **"The last day cannot come before the first."**

A red line under the dates in the dialog. **Last day away** is earlier than **First day away**. Correct one of them. Moving the first day past the last one makes it a single day instead.

### **"That is not a length of time. Try 3:30, 3.5, or 90m for ninety minutes."**

You chose **A set number of hours a day** and typed something into **Hours away each day** that could not be read. Use one of the forms shown.

### **"No reasons set up yet"**

Where the **Reason** list should be. Nothing can be recorded until at least one reason exists. Whoever looks after the team opens **Reasons** and adds one, or brings a retired one back.

### **"Deciding on your own absence is not a decision. Ask someone else."**

You pressed **Agree** or **Refuse** on your own absence. Even somebody who looks after the team cannot decide their own. Ask a colleague who also looks after the team.

### **"This has already been decided. Ask for it to be changed."**

You tried to change your own absence after it had been agreed or refused. Ask whoever looks after the team to change it.

### **"Only a request that is still open can be decided."**

**Agree** or **Refuse** was pressed on something that is no longer **Asked for** — usually because two people acted at the same time. Reload the page and look at the **State** column.

### **"Say why it is being refused."**

The **Why** box in the refusal dialog was empty. Type a sentence. What you write is kept with the record, and nobody is told automatically, so tell the person as well.

### **"3 absences are recorded with this reason, so it cannot be deleted — the record of them would stop making sense. Press Retire instead: it disappears from the list of reasons somebody can choose, and the existing ones stay readable."**

You pressed the bin beside a reason in the **Reasons** dialog. The count is the real number of absences filed under it.

**What to do.** Press **Retire** instead. The reason stops being offered when somebody records a new absence, and every absence already filed under it stays exactly as it is. **Bring back** puts it on the list again later.

### **"The payload is not valid"** when adding a reason

You typed a **Code** that already exists exactly. Codes are stored in capitals, and the box turns whatever you type into capitals, so `urlaub` and `URLAUB` are both stored as `URLAUB`.

**What to do.** Look down the **Code** column first. If the reason is already there but retired, press **Bring back** rather than adding it again.

One trap worth knowing: the codes that came with the system are in small letters — `urlaub`, `krankenstand` and so on — so typing `urlaub` does **not** clash with the existing one. It quietly creates a _second_, different reason that does not come off the leave account. Check the list before you add anything.

### There is no way for most people to reach the **Absences** screen

Only somebody who looks after the team has a link to it. If you want a day off, there is at present no button of your own to press: tell whoever looks after the team, and they will record it. This is not a fault on your side and nothing you do will find the screen.

---

## Messages about people, terms, rates, leave and starting balances

These appear on the **People** page and in the dialogs it opens.

### Red lines under the boxes, before anything is sent

| Message                                                                                                                                   | What it means                                                                                                              |
| ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **"One of the days is not a length of time. Type 7:42 or 7.7, or leave it blank."**                                                       | One of the seven weekday boxes holds something unreadable. Clear the days that are not worked rather than typing 0.        |
| **"Say when this person started, so their first month knows where to begin."**                                                            | **Started on** is empty.                                                                                                   |
| **"Fill in at least one day, so their month has something to be measured against. Leave the days they do not work blank."**               | All seven weekday boxes are empty.                                                                                         |
| **"A CRM staff id is a whole number. Leave it empty to match on the email address instead."**                                             | The **CRM staff id** box holds something that is not a positive whole number.                                              |
| **"Say which day this rate starts."**                                                                                                     | **From** is empty in the rate dialog.                                                                                      |
| **"Write the amount as a number, like 65 or 65.50."**                                                                                     | The amount is empty, negative, or not a number.                                                                            |
| **"Say when the leave year starts and ends."**                                                                                            | **Leave year from** or **Leave year to** is empty.                                                                         |
| **"The leave year cannot end before it starts."**                                                                                         | The two dates are the wrong way round.                                                                                     |
| **"Write the time as 200:00, 200 or 12000m."**                                                                                            | **Leave for the year** or **Carried over** could not be read.                                                              |
| **"There is already a leave year covering these dates."**                                                                                 | The dates overlap a leave year already on the list. Change one of the existing years rather than laying a new one over it. |
| **"Say how much. Type -12:30 or -12.5, or leave off the minus for a surplus."**                                                           | The **Balance** box in the starting-balance dialog could not be read.                                                      |
| **"Say what this figure is based on. A number nobody can account for is one nobody can defend when the person it belongs to disagrees."** | **What it is based on** is empty. It is required.                                                                          |
| **"Say which day this balance applies from."**                                                                                            | **Applies from** is empty.                                                                                                 |

Only the first problem found is shown. Fix it, press the button again, and the next one appears if there is one.

### **"You don't have the required permissions."**

You are not somebody who looks after the team, and what you pressed is only theirs to do. Nothing was saved. Ask whoever looks after the team.

### **"This is the only person who looks after the team. Taking it away would leave nobody able to reach anyone's month, and nobody able to give it back. Make somebody else a manager first."**

You tried to switch **Looks after the team** off for the only person who has it, or to mark that person as having left.

**Why it matters.** The setting can only be given by somebody who already looks after the team. Take it from the last one and nobody can reach anyone's month and nobody can hand it back.

**What to do.** Give a second person **Looks after the team** first, save, then make the change you wanted.

### **"This overlaps a contract already recorded for this person. End the previous one first, so each day has exactly one set of terms."**

You added terms starting on a date already covered by the terms this person is on. Every day must have exactly one set of terms.

**What to do.** Open the terms already recorded, put an end date on them the day before the new ones start, save, then add the new ones.

### **"A closed month was worked out against these terms. Reopen the month first if they genuinely need to change."**

and

### **"A closed month was worked out against this schedule. Reopen the month first if it genuinely needs to change."**

**Why it happened.** A month that has been closed was worked out against these terms or this working week. Changing them now would change what that frozen month says it was derived from — the one record that has to still explain the figures a year later.

**What to do.** If the change genuinely has to reach that month, reopen it on **Team time** first, make the change, then close the month again. If the change is only meant to apply from now on, add a new set of terms or a new working week starting on the day it takes effect, rather than editing the old one.

### **"This entitlement has been agreed with the person. Record a further adjustment rather than editing what was agreed."**

The leave year has been held as final. **Hold as final** cannot be undone. Add a further leave year, or a starting balance for leave, rather than editing the one that was agreed.

### **"Only the person a balance belongs to can agree it."**

**This is right** on a starting balance can only be pressed by the person the balance belongs to. Not even somebody who looks after the team can tick it for them. Ask the person to open **My time**, open **Starting balance** from the **…** menu, and press it themselves.

### **"That figure has already been replaced by a corrected one."**

Somebody recorded a correction while your screen was open. Reload; the corrected figure will be on the list.

### **"Say what the corrected figure is based on."**

**What it is based on** was empty when you saved a correction. It is required for a correction exactly as for the original.

### A starting balance cannot be deleted

There is no way to remove a starting balance anywhere in the system, and **Correct this figure** keeps the same **What for** — so a figure recorded under the wrong heading stays there.

The dialog remembers **What for**, **Applies from** and **How sure** from the last one you recorded, and clears only the amount and the basis. If you record an hours balance and then a leave balance one after the other, check **What for** before pressing **Record it** the second time.

---

## Messages about public holidays

### **"Give the day a date and a name."**

A red line under the **Add a day off for everyone** boxes. Fill in both.

### **"Christmas Eve is already on this day."**

There is already a holiday on that date, in the year currently shown. Either pick another date, or change the day that is already there — its length can be switched with **Make it half a day** / **Make it a whole day**, and a granted day can be removed.

### **"The fields calendar, date must make a unique set."**

This one is written for a programmer, and it means the same thing as the message above: **there is already a holiday on that date** — but in a _different year_ from the one on screen. The check the screen does itself only looks at the year you are looking at.

**What to do.** Step to the year the date belongs to with the year arrows and look at the list. The day is already there. Change it if it needs changing, and do not add a second one. Do not nudge the date by a day to get past the message — that puts a company holiday on the wrong day.

### **"You don't have the required permissions."** after pressing **Add**

Everybody can read the list of public holidays. Only somebody who looks after the team can change it, and the **Add a day off for everyone** panel and the row buttons are shown to everybody anyway.

Nothing was saved. Do not press **Add** again — it will fail the same way. Ask whoever looks after the team to add the day.

### **"Not found."** after pressing **Remove this day**

Somebody else had already removed it. Reload the page.

### **"Remove this day?"** — read this before you confirm

The dialog says what happens: **"Christmas Eve stops being a holiday. Everybody who works that day is expected to work it again."** For each person, the day goes from counting as hours worked to being a day they owe hours on.

---

## Messages when you bring records in from a file

These appear on **Bring earlier records in**.

### Reasons in the **Detail** column, one per row

Nothing has been written when these appear. The file has been read and checked, and this is what would happen. Rows marked **Cannot be read** are refused; rows marked **Skipped** are passed over; rows marked **Will be written** are the only ones **Apply** touches.

| What the **Detail** cell says                                                                                                        | What to do                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **"Nobody here logs in as anna@example.com. Add the person under People, or correct the address in the file."**                      | The address is blank, misspelt, or belongs to somebody with no employment record.                                 |
| **"The date could not be read."**                                                                                                    | Write it as `2026-03-02`.                                                                                         |
| **"The start date could not be read."**                                                                                              | The same, in the start-date column of an absences file.                                                           |
| **"The amount of time could not be read, or it is zero. Every row needs a length of time — leave the day out of the file instead."** | Put a real length in, or delete the row.                                                                          |
| **"That is more than 24 hours in one day. Check whether the number is hours or minutes, and that the column heading matches."**      | Nearly always minutes sitting under an `hours` heading.                                                           |
| **"That month is no longer open, so nothing more can go into it. Ask for it to be reopened if this has to go in."**                  | The row is **Skipped**, not refused. If it must go in, have the month reopened first, then upload the file again. |
| **"The balance could not be read."**                                                                                                 | Write it as `12:30`, `-12:30` or a decimal.                                                                       |
| **"The kind column must say time, leave or overtime."**                                                                              | Use one of those three words. An empty cell is read as time.                                                      |
| **"The basis column is empty. Write where the figure came from, for example: from the old leave spreadsheet."**                      | Required for every starting balance.                                                                              |
| **"It ends before it starts."**                                                                                                      | The end date is earlier than the start date. An empty end date is fine and means one day.                         |
| **"No reason for being away has the code 'URLAUB'. The codes are on the Absences screen, under Reasons."**                           | Use a code from that list, or have the reason added first.                                                        |

Row numbers in the **Row** column count the heading row as row 1, so the first row of data is row 2 — the same numbering your spreadsheet shows.

### **"This exact file has already been applied."**

The identical file, of the same kind, is already in. Nothing needs doing — the records are there. Look for it under **Files brought in before**.

### **"That file is larger than this accepts."**

Over 5 MB. Save it as CSV rather than a workbook, or split it in two.

### **"The file could not be read. Check it is a CSV or XLSX."**

Nothing in the file could be understood: a damaged workbook, an empty file, or something that is not a spreadsheet at all. The file appears in the list as **Could not be read**. Open it in your spreadsheet program, check the headings are on the very first row, and save it again as CSV.

Only the sheet the workbook opens on is read.

### **"This import has not been checked, or has already been applied."**

**Apply** was pressed on a file that is no longer **Waiting to be applied** — most often somebody else applied it first, from another browser. Reload the page and look at the file's state.

### **"Only an import that was applied can be undone."**

**Undo** was pressed on a file that is not **Applied**. Reload the page.

### **"Say why the import is being undone."**

The reason box was empty. The button stays switched off until you type something, so you should not normally see this.

### **"Some of this has been counted into a month that is now closed. Reopen the month first."**

**Why it happened.** Part of what this file wrote sits inside a month that has since been closed. Those figures have been agreed with somebody, and quietly removing what they were based on is not an undo.

**What to do.** Reopen that month on **Team time**, come back and press **Undo it**, then close the month again.

### **"The payload is not valid"** after pressing **Apply**

This one is written for a programmer. On this screen it means one thing in practice: a **starting balance** in the file collides with one already recorded for the same person, the same **What for** and the same date — or the file holds two such rows itself.

The whole file is written in one go, so **nothing at all** went in. The file stays as **Waiting to be applied**. Pressing **Apply** again will fail in exactly the same way.

**What to do.** Take the duplicate row out of the file and upload it again, or correct the balance already on record from the **People** page.

### Before you press **Apply**: rows are added, not merged

The screen says so: **"Rows are added to whatever is already recorded for those days, so a day brought in twice counts twice. To correct a file that is already in, undo it first instead of bringing in a corrected copy."**

If you have already applied a file and then find a mistake in it, undo that file first. Uploading a corrected copy on top adds a second set of hours to every day.

---

## Messages that fill the whole page

### **"This is not yours to see"**

With one of these underneath, depending on which screen you are on:

- **"Everyone's hours are only readable by whoever looks after the team. Your own month is on My time."**
- **"Only whoever looks after the team can change who is employed and on what terms."**
- **"Only whoever looks after the team can bring earlier records in."**
- **"There is no employment record for you here, so there is nothing to show. Ask whoever looks after the team to set one up."**

**Why it happened.** You followed a link to a screen that is only for whoever looks after the team. This happens most often from the small **Team time** link at the top of **Hours in detail** — most people are sent to **Hours in detail** from their own **…** menu, and the only link on that page leads somewhere they may not go.

You have not done anything wrong and you have not lost access to anything. There is deliberately no **Try again** button, because asking again would be refused again.

**What to do.** Use the browser's back button, or go to **My time**.

### **"No employment record here"** / **"Your hours are not being tracked yet. If they should be, ask whoever looks after the team to set you up."**

You have an account, but nobody has created an employment record for you, so there are no hours to show.

This is also what somebody sees after they have been marked as having left. Their months stay readable to whoever looks after the team; their own way in closes.

**What to do.** If your hours should be counted, ask whoever looks after the team to add you on the **People** page.

### **"This could not be loaded"** / **"Something went wrong on the way. Try again, and tell whoever looks after the team if it keeps happening."**

Something failed on the way to the server — the connection, or the server itself. It is deliberately worded differently from the message above so the two are not confused.

**What to do.** Press **Try again**. If it keeps happening, say so.

### **"Nobody has an employment record yet. Add people on the People page and their hours start counting."**

On **Team time**, when nobody is set up. Not a fault. Somebody needs to be added on **People** first.

---

## Messages that were written for a programmer

Four sentences can reach you that nobody wrote for a reader. They are worth recognising so you do not read anything into them.

| What you see                                      | What it actually means                                                                                                                                                             |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **"The payload is not valid"**                    | Something you are adding already exists — the same person and day, the same date, the same code. Nothing was saved. Look for the thing already on the list before adding it again. |
| **"Please provide valid detail"**                 | One of the values sent could not be used. Check what you typed.                                                                                                                    |
| **"The required object does not exist."**         | The record was removed while your screen was open. Reload the page.                                                                                                                |
| **"Something went wrong please try again later"** | The server itself failed. Nothing was saved. Try once more; if it repeats, report it.                                                                                              |

You may also see **"Not found."**, **"No such month, or not yours to read."** or **"No such day."** These all mean the same: the thing you acted on is not there any more, or was never yours to act on. Reload the page.

---

## Messages that mean nothing is wrong

Some messages look like failures and are not.

| What you see                                                                                                         | What it means                                                                                                                                                                     |
| -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **"Nothing has been added here yet. Hours recorded on work items are counted, but are not shown here."**             | The day has no **Hours with no work item**. Hours from timers on work items are counted in your month but are not listed in this box. It does not mean no work was done that day. |
| **"This day has not happened yet."**                                                                                 | A day later in the month. It will fill in when it arrives.                                                                                                                        |
| **"No absences recorded for this month."**                                                                           | Nobody in view was away. Step to another month, or clear the person filter.                                                                                                       |
| **"No days for this year yet. Until they are added, every public holiday in it counts as an ordinary working day."** | The calendar has no days for that year. This one does matter — see the note below.                                                                                                |
| **"No hours were recorded on a work item in this month. Check the month shown at the top."**                         | On **Hours in detail**. Nothing was logged against a work item, or you are looking at the wrong month.                                                                            |
| **"No starting balance has been recorded yet, so counting begins from zero."**                                       | Normal for anybody who started after the system did.                                                                                                                              |
| **"No rate on record. A statement for this person will show hours and no amount."**                                  | No rate has been recorded. Only matters for the people who invoice their own hours.                                                                                               |
| **"No rate on record for you yet, so this shows the hours only. Ask whoever looks after the team."**                 | The same, seen from your own **Before you invoice** panel.                                                                                                                        |
| **"Nothing left to look at. This month can be closed."**                                                             | Every flagged day has been settled.                                                                                                                                               |
| **"This month is not closed yet, so these figures can still move. Wait until it is closed before you invoice."**     | Not a fault — a warning. Do not write an invoice from a figure that can still change.                                                                                             |

**The empty holiday year is worth acting on.** A year with no days in it means every public holiday in that year is treated as an ordinary working day, and each one shows up as a full day's shortfall against everybody who works it. If the year that matters is empty, the days have to be added by hand on **Public holidays**.

---

## Things that go wrong without saying anything

These give you no message at all, which makes them harder to recognise than any refusal.

### The **Before you invoice** panel is missing

If the figures behind it cannot be fetched, the whole panel disappears with no message and no gap. It also does not appear at all for anybody who is not on one of the two arrangements that invoice their own hours.

**Do not work the figure out yourself and invoice it.** Reload the page. If it still is not there, and you know it should be, ask whoever looks after the team for the month's figure before you write anything.

### A download replaces the whole application with a page of text

**Download as CSV** and **Download as Excel** open in the same tab. When the file arrives you never notice. When it does not — your session has expired, or you may not read that month — the application is replaced by a page of raw text.

**What to do.** Press the browser's back button. If your session had expired, sign in again first.

On **Team time**, the download menu is shown even on a screen that has just told you **This is not yours to see**. Pressing it there will do exactly this.

### The **Whose hours** list on **Hours in detail** has only **My hours** in it

If the list of colleagues cannot be fetched, the box is left holding only your own entry and nothing says why. It looks identical to nobody else being set up.

**What to do.** Reload the page before concluding anything about who is employed or about your own access.

### The **People** page shows one row and warns about your own hours

If you reach **People** without looking after the team, you get the whole page with a single row — yourself — assembled out of requests that were refused. Your own **Hours a week** cell may read **Not set up** when your week is set, and the rates dialog may say no rate is recorded when one is.

**Nothing on that screen is a reliable statement about your own employment.** Your own month, worked out from the real records, is on **My time**.

### A timer that was left running has been cut short

An entry marked **— stopped by the system, needs correcting** on **Hours in detail** was left running and was closed automatically after ten hours.

That ten hours is a limit, not time that was worked. Nobody but you knows when you actually stopped.

**What to do.** Correct the entry on the work item before the month is handed in. Ten hours nobody worked, left in the figures, is a large error in one day.

---

## A worked example: a month that would not close

Anna is on site, full time. Her working week is Monday to Friday, and each of those days she owes **7:42** — seven hours forty-two minutes. March 2026 has 21 working days for her. One public holiday falls on a Tuesday, and she takes two days of leave.

**What she has To work for the month.**

```
21 working days x 7:42  =  161:42
```

A public holiday does not lower this, and neither does leave. **To work** stays 161:42.

**What counts as Worked.**

The public holiday and the two days of leave are each added to **Worked** at a full day's length, rather than being taken off **To work**. That is what keeps the hours going to payroll the hours she is paid for, and it still leaves her **Balance** right.

```
18 ordinary days worked to plan   18 x 7:42  =  138:36
1 public holiday                   1 x 7:42  =    7:42
2 days of leave                    2 x 7:42  =   15:24
                                   Worked    =  161:42
```

```
Balance = Worked 161:42  -  To work 161:42  =  0:00
```

Her month comes out level, and the small note under **Worked** reads **"includes 23:06 away or on holiday"** — the holiday and the two leave days added together.

**Then a work item is deleted.**

Somebody tidies up a project and deletes a work item Anna had logged 6:30 against on 11 March. Those hours were already counted into her month.

```
Worked   161:42  -  6:30  =  155:12
Balance  155:12  -  161:42  =  -6:30
```

Her day table now shows **Hours counted here earlier are no longer there** against 11 March, and her figures carry the note **"Some days need looking at — hours that were counted before are no longer there. Whoever looks after the team has to settle them before the month can be closed."**

**What happens next.**

Anna hands the month in. It is agreed. Whoever looks after the team presses **Close** and is told:

> **"Some days are marked for review because hours counted earlier are no longer there. Settle those before closing the month."**

They press **Look at those days**, which lists 11 March and says **Counts as 0:00 now**. They have two choices.

1. If the 6:30 should still count, Anna records it again — as **Hours with no work item** on 11 March, if the work item is gone for good. Her **Worked** goes back to 161:42 and her **Balance** back to 0:00. The day is then settled with a note saying what happened.
2. If those hours were logged in error and should not count, the day is settled with a note saying so. Her month closes at **Balance −6:30**, and that shortfall is carried into April as her **Running balance**.

Either way, somebody has written down what happened, and the closed figure can be explained a year later. Settling the day on its own does not put the hours back.

---

## If you get stuck

If your message is not on this page, or the answer here did not work, ask whoever looks after the team. They can reopen a month, change terms, record an absence and settle a flagged day — which covers nearly everything an ordinary refusal asks for.

When you ask, three things make it quick to answer: which screen you were on, what you pressed, and the sentence you saw written out word for word. A photograph of the message is fine.

The other pages of this handbook, if the question turns out to be about how something works rather than about a message:

- **Start here** — what the system is for and how to find your way round it.
- **My time — your own month** — your own figures, and what each of them counts.
- **Recording hours** — putting in hours that are not on a work item.
- **When you were at work** — start and end times, and breaks.
- **Hours in detail** — where a month's hours actually went, entry by entry.
- **The month, from open to closed** — what happens between **Not handed in** and **Closed**, and who does each step.
- **Team time — everybody's month** — agreeing, closing and reopening months.
- **People and their terms** — employment records, working weeks, rates.
- **Time away from work** — recording and deciding absences.
- **Leave** — how leave is counted and what a day of it is worth.
- **Public holidays** — the days nobody works, and which of them are half.
- **Bringing hours in from somewhere else** — reading records out of a spreadsheet.
