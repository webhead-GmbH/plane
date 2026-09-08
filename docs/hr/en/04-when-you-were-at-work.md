# When you were at work

This page is for anybody who sees a box headed **When you were at work** when they open a day, and is not sure what it is for. It explains what that box records, why the figure it shows does not match your hours and is not supposed to, who has it switched on, and what changes once a month is no longer open.

If you have never seen that box, it is not being kept for you, and you can skip this page.

## Contents

- [What this record is](#what-this-record-is)
- [Whether it is switched on for you](#whether-it-is-switched-on-for-you)
- [Recording a day, step by step](#recording-a-day-step-by-step)
- [The four things it asks](#the-four-things-it-asks)
- [The figure on the right of the box](#the-figure-on-the-right-of-the-box)
- [Where you worked, and the count for the year](#where-you-worked-and-the-count-for-the-year)
- [Why the two totals do not agree](#why-the-two-totals-do-not-agree)
- [Correcting a day, and removing one](#correcting-a-day-and-removing-one)
- [Days that run past midnight](#days-that-run-past-midnight)
- [When it will not save](#when-it-will-not-save)
- [A month worked through, with the sums](#a-month-worked-through-with-the-sums)
- [What happens when the month is no longer open](#what-happens-when-the-month-is-no-longer-open)
- [If you get stuck](#if-you-get-stuck)

## What this record is

It answers one question: **when were you at work on this day**. A start, an end, how long you broke for, and where you were.

It does not ask what the time went on. That is a different record — the hours, which come from the timers on work items and from anything you type into the same dialog underneath this box. The line under the heading says so on screen:

> Start, end and breaks for this day. It is a separate record and does not count towards your hours.

Read that literally. Nothing you put in this box changes **Worked**, and nothing changes **Balance**. Recording that you were at work from 08:45 to 17:00 does not credit you seven and a half hours. If you were expecting it to, that expectation is the single most common misunderstanding about this screen, and the rest of this page is mostly about it.

There is **one record per day**. If you went home at lunchtime and came back in the evening, that is one day with a longer break, not two records. There is no way to record two separate stretches on the same day.

## Whether it is switched on for you

Whether this record is kept is part of your terms, alongside things like the length of your working day. It is off unless somebody has deliberately turned it on. So some people in the company open a day and see this box, and others never will.

You do not turn it on yourself, and it is not on the form where the rest of somebody's terms are set. If you think it should be on for you, or should not be, ask whoever looks after the team.

One consequence is worth knowing. Whether the box appears is decided by your terms **as they stand today**. Whether the day you are recording is accepted is decided by your terms **as they stood on that day**. If attendance was switched on for you part-way through a year, opening a day from before that will show you the fields, let you fill them in, and then refuse to save with the message _Attendance is not recorded for this person._ That is not a fault. It means the record was not being kept on the day you are looking at.

## Recording a day, step by step

The box lives inside the dialog you get when you open one day of the month on **My time**.

1. Go to **My time**. You see the month, then a table with one row for each day.
2. Find the day. If it is a day still to come, press **Show the rest of the month (3 days)** at the foot of the table first — days that have not happened yet are hidden. If it is in another month, step to that month with the arrows beside the month name; the dialog will not open for a day outside the month on screen.
3. Click the date at the left of the row. A small pencil appears beside it when you hover. The dialog opens, headed with the day and the year, for example **Tue 10 Mar 2026**.
   - There is a shortcut for today: the **Record time for today** button at the top right. It jumps the page to the current month and opens today, whichever month you were looking at. That is deliberate, but it does look like the button ignored where you were.
4. The box headed **When you were at work** is the first thing inside the dialog, above the hours.
5. Fill in the four fields (next section) and press **Record**. The button reads **Update** instead if something is already recorded for that day.
6. A small **Saved** message appears at the corner of the screen, and a figure appears at the top right of the box — the length of the day, breaks taken off.
7. Press **Close** when you are done.

Two things to watch while you are in there.

- **The box has its own save.** The **Add** button at the bottom of the dialog belongs to the hours underneath. It does nothing at all to these four fields. If you fill in the times and press **Add**, the times are not saved.
- **Closing throws away anything not saved.** **Close**, the Escape key, and clicking the dark area outside the dialog all do the same thing, with no second chance. While the fields say something that has not been saved, an amber line appears in the box: **Not saved yet. Save these times, or they are lost when you close.** It is a warning, not a guard.

## The four things it asks

| Field                | What to type          | Notes                                                                                                                  |
| -------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **From**             | The time you started  | Required. Leave the rest empty and it still saves.                                                                     |
| **To**               | The time you finished | May be left empty. Empty means the day has no end yet — it does **not** mean you finished at midnight.                 |
| **Break (minutes)**  | A count of minutes    | `30` means half an hour. Not a length of time: typing `0:30` is refused. Leave it empty for no break.                  |
| **Where you worked** | One of three choices  | **At the office**, **Working from home**, **Somewhere else**. A day with nothing recorded starts on **At the office**. |

Two traps in **Break (minutes)**, both real:

- It is the only field on this screen where a bare number means minutes. In the hours underneath, a bare number means hours. `30` here is half an hour; `30` down there would be thirty hours.
- Anything over **480** (eight hours) will not save, and the message you get back does not say so. It reads **That did not go through** with _The payload is not valid_ underneath, and pressing the button again does exactly the same thing every time. Keep the break under eight hours.

If you leave **To** empty, the top right of the box reads **No end time yet** instead of a length, and the day counts as zero minutes until you come back and fill the end in.

## The figure on the right of the box

Once a day has been recorded, a figure appears at the top right of the box, for example `7:30`. It is the length of the day with the break taken off.

It is worked out once, when you save, and never recalculated afterwards. The arithmetic is:

> (end − start) − break

Anna is in from 08:45 to 17:00 and takes 45 minutes for lunch.

|                | Minutes               |
| -------------- | --------------------- |
| 08:45 to 17:00 | 495                   |
| Break          | −45                   |
| **Shown as**   | **450, that is 7:30** |

Two details behind that:

- The times are read in the timezone recorded against you — Europe/Vienna unless somebody has said otherwise — and the zone is stored with the day. That is what makes the two days a year when the clocks change come out right, rather than an hour long or an hour short.
- A day you change later is marked in the record as corrected afterwards, so a correction is never mistaken for what was first written down.

The figure appears nowhere else. There is no column for it in the month table, and no total for the month on any screen. To check whether a day has a record at all, you have to open that day.

## Where you worked, and the count for the year

**Where you worked** is not a note. Days marked **Working from home** are counted, and the count is a figure that goes to payroll.

On **My time**, once you have at least one such day, a line appears under the figures: **From home this year: 12**. That number counts:

- every day of yours recorded as **Working from home**,
- across the whole calendar year of the month you are looking at — not the month, and not only up to today,
- as a count of days, not hours. A day counts once, however long it was.

It changes the moment you change a day's **Where you worked**, including for days months in the past, because it is counted from the days themselves each time it is shown.

The other two choices are not counted anywhere. They are still worth setting correctly: where each day was worked goes into the file the month is sent out in.

## Why the two totals do not agree

Open a day and you will often see two figures within a few centimetres of each other:

- at the top right of this box, something like `7:30`
- lower down, beside **Hours with no work item**, something like `1:30`

**They are two different records of two different things, and nobody is expected to make them match.**

| Figure                      | What it counts                                                         | What it leaves out                                 |
| --------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------- |
| The one in this box         | The whole time you were at work that day, breaks taken off             | Nothing — but it says only _when_, never _what on_ |
| **Hours with no work item** | Only the hours you typed in by hand: meetings, admin, training, travel | Every hour that came from a timer on a work item   |

The hours from work-item timers — usually most of the day — are counted towards your month but are **not shown in this dialog at all**. That is why a day with eight hours of timed work can still say, underneath, **Nothing has been added here yet. Hours recorded on work items are counted, but are not shown here.** The day row behind the dialog, on **My time**, is where both appear side by side: **Work items** and **No work item** are separate columns there.

So the gap between the two figures is normal, and it is meant to be there. Do not invent an entry to close it. If your day at work was 8:00 and the hours you accounted for come to 7:30, the half hour is not missing — it is coffee, corridor conversations, and the ordinary difference between being present and being booked to something.

If the two are wildly apart — hours away from each other, day after day — that is worth mentioning to whoever looks after the team. Nothing on any screen compares them for you.

## Correcting a day, and removing one

Unlike the hours underneath, an attendance day **can** be corrected in place. Open the day, change whatever is wrong, press **Update**. You get **Saved** and the figure on the right is worked out again.

That is almost always what you want. **Remove** is for a day that should not have a record at all — a day you were not at work.

**Removing cannot be undone.** The start, the end and the break are gone, and there is no way to bring them back from within the system.

To remove a day:

1. Press the small bin icon in the box. It is named **Remove**.
2. A dialog opens: **Remove this attendance record?**, with the sentence _The start, end and break for this day are removed and cannot be brought back. If the times are wrong, change them and save instead._
3. Press **Cancel** to stop, or **Remove** to go through with it. While it runs the button reads **Removing…**.
4. You get **Removed**, and the box goes back to empty fields with the button reading **Record**.

## Days that run past midnight

If **To** is earlier than **From**, the day is taken to have run past midnight. Nothing asks you about this; it is read from the two times.

An amber line appears straight away, before you save:

> **This runs past midnight and comes to 9:30. Check the end time if that is not right.**

The length it names is worked out exactly the way saving works it out, break included, so it is the figure that would actually be recorded. If it looks wrong, the end time is wrong. Typing `07:00` when you meant `17:00` is the ordinary cause.

A start and an end at exactly the same time is left alone — it is read as somebody typing the same time twice, not as a twenty-four-hour day.

## When it will not save

Some problems are caught before anything is sent, and appear in red under the fields:

| What you see                         | What it means                                                                                                           |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **Say what time you started.**       | **From** is empty. It is the one field that is required. An end time is not.                                            |
| **Give the break in whole minutes.** | The break is not a whole number of minutes — a decimal, a negative, or letters. Type `30`. Leave it empty for no break. |

The rest come back from the system as a message headed **That did not go through**. These are in English whatever language the rest of the screen is in.

| Message                                                                                                                           | What it means                                                                                  | What to do                                                                   |
| --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| _That time did not happen on that date — the clocks went forward over it._                                                        | On the spring clock change, the hour between two and three in the morning does not exist.      | Use a time that happened.                                                    |
| _The times and breaks do not leave any time worked. Check them over._                                                             | The break is longer than the day, or the end is before the start in a way that leaves nothing. | Check all three fields.                                                      |
| _That is more than a day. If the work ran past midnight, say so._                                                                 | The times come to over twenty-four hours.                                                      | Check the end time.                                                          |
| _Attendance is not recorded for this person._                                                                                     | This record was not being kept for you on the day you are recording.                           | See [Whether it is switched on for you](#whether-it-is-switched-on-for-you). |
| _The payload is not valid_                                                                                                        | Almost always a break over 480 minutes. Pressing again will not help.                          | Bring the break under eight hours.                                           |
| _March 2026 has been handed in, so its records can no longer change. Ask whoever looks after the team to reopen it on Team time._ | Somebody handed in or closed the month while you had the dialog open.                          | Close the dialog. The month is settled now.                                  |

There is one failure that says nothing at all. If the box cannot fetch what is already recorded for the day — a dropped connection, usually — it shows empty fields and a button reading **Record**, exactly as it would for a day with nothing on it. Pressing **Record** then tries to add a second record for a day that already has one, which is not allowed, and you get **That did not go through** every time you try. If a day you are sure you recorded comes up blank and will not save, close the dialog, open the day again, and see whether the record reappears.

## A month worked through, with the sums

Anna works Monday to Friday and owes **7:42** on each of those days — 462 minutes. Her attendance is recorded. March has 21 working days for her. One public holiday falls on a Friday she works, and she takes two days of leave.

**What the month expects of her**

|             | Sum                   | Total                      |
| ----------- | --------------------- | -------------------------- |
| **To work** | 21 days × 462 minutes | 9,702 minutes — **161:42** |

The public holiday and the leave do **not** come off that figure. They are added to what she is credited with instead.

**What she is credited with**

| Column on the day table             | Sum                       | Total                      |
| ----------------------------------- | ------------------------- | -------------------------- |
| **Work items** (timers)             | —                         | 7,200 minutes — **120:00** |
| **No work item** (typed in by hand) | —                         | 1,116 minutes — **18:36**  |
| **Time off** — the holiday          | 1 day × 462               | 462 minutes — **7:42**     |
| **Time off** — two days of leave    | 2 days × 462              | 924 minutes — **15:24**    |
| **Worked**                          | 7,200 + 1,116 + 462 + 924 | 9,702 minutes — **161:42** |
| **Balance**                         | 161:42 − 161:42           | **0:00**                   |

**What her attendance says, over the same month**

Take away the holiday and the two days of leave and Anna was actually at work on 18 days. On a typical one she was in at 08:30, left at 17:00, and took 30 minutes.

|                | Minutes            |
| -------------- | ------------------ |
| 08:30 to 17:00 | 510                |
| Break          | −30                |
| One day        | 480 — **8:00**     |
| 18 days        | 8,640 — **144:00** |

Now compare that with what she accounted for on those same 18 days: 7,200 + 1,116 = 8,316 minutes, that is **138:36**.

> 8,640 − 8,316 = 324 minutes = **5:24** across the month, about eighteen minutes a day.

Anna's month is exactly right. Her balance is 0:00 and her hours are complete. The 5:24 is the ordinary difference between the time she was at work and the time she booked to something, and nothing anywhere asks her to close it.

Note also that her 144:00 of attendance is nowhere near her 161:42 **Worked** — and cannot be, because 23:06 of **Worked** is a holiday and leave, days she was not at work at all. Comparing the attendance total against **Worked** will mislead you every time. Compare it, if you compare it at all, against the hours on the days you were actually there.

## What happens when the month is no longer open

A month can be changed while it says **Not handed in** or **Reopened**. Once it is **Handed in**, **Agreed** or **Closed**, its records stop moving — attendance included. That is the point of handing a month in: the figures somebody has read cannot change underneath them afterwards.

The dialog that appears when you press **Hand in** says so: _Once March 2026 is handed in, you cannot change its hours, time off or attendance yourself. Ask whoever looks after the team if something needs correcting._

| What the month says | Can you record or change a day? |
| ------------------- | ------------------------------- |
| **Not handed in**   | Yes                             |
| **Reopened**        | Yes                             |
| **Handed in**       | No                              |
| **Agreed**          | No                              |
| **Closed**          | No                              |

You can still open every day and read it. The box changes from four fields to one grey line:

- with a record — **08:45 to 17:00, 7:30. This month is no longer open, so it cannot be changed.**
- with none — **Nothing was recorded for this day, and the month is no longer open.**

There are no fields, no **Record** button and no **Remove** button. Trying anyway from a stale screen gives you the refusal above, which names which of the three states the month is in.

If something in a settled month genuinely has to be corrected, it can only be done by having the month reopened first. Ask whoever looks after the team. Once a month is reopened it behaves as an open month again, and the day can be corrected in the ordinary way.

Two things that are allowed, and surprise people:

- **Days that have not happened yet.** Press **Show the rest of the month** and a future day opens and accepts a record like any other. Nothing stops you.
- **Old months that were never handed in.** They stay open indefinitely, and stay fully changeable. That is how months from before the company used this system get filled in.

Finally: this dialog is always about **your own** day. There is no way here to record attendance for somebody else, and no screen anywhere in the system lets one person type another person's start and end times by hand.

## If you get stuck

- For the month as a whole, the figures at the top and what each column means: **My time — your own month**.
- For the hours underneath this box — meetings, admin, travel, and how to enter and correct them: **Recording hours**.
- For the full list of every hour counted in a month, including the timed ones this dialog does not show: **Hours in detail**.
- For handing in, what each state means, and getting a month reopened: **The month, from open to closed**.
- For leave and sickness, which never go in this dialog: **Time away from work** and **Leave**.
- For a message you cannot get past: **When something goes wrong**.

If none of that answers it, ask whoever looks after the team. They can see everyone's months and can reopen one.
