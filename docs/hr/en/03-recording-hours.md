# Recording hours

This page is for anybody who has to get their working hours into the system and has never been shown how. It covers the three ways hours reach a month, how to write down a length of time, and how to add, correct and remove what you have recorded. If you want to know what the figures on your month mean, read "My time — your own month" instead.

## Contents

- [The three ways hours reach your month](#the-three-ways-hours-reach-your-month)
- [Writing a length of time](#writing-a-length-of-time)
- [A timer on a work item](#a-timer-on-a-work-item)
- [Hours with no work item](#hours-with-no-work-item)
- [Hours somebody records for you](#hours-somebody-records-for-you)
- [Once the month has been handed in](#once-the-month-has-been-handed-in)
- [A month, worked through](#a-month-worked-through)
- [If you get stuck](#if-you-get-stuck)

## The three ways hours reach your month

Every hour counted in your month arrives in one of three ways.

| How the hours arrive                                       | Where you do it                              | Which column they land in on **My time**                             |
| ---------------------------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------- |
| A timer you start and stop on a work item                  | The work item itself                         | **Work items**                                                       |
| Hours you type in for a day, with no work item behind them | **My time**, by opening the day              | **No work item**                                                     |
| Hours somebody records for you                             | On a work item, or from a file they bring in | **Work items** or **No work item**, depending on which they recorded |

Two other things also count towards **Worked**, and neither of them is recorded on this page: time off, and public holidays. They are covered by "Time away from work" and "Public holidays".

The columns are on the day table on **My time**. Reading across one day: **To work** is what you owe that day, **Work items** and **No work item** are the two kinds of hours you recorded, **Time off** is absence and public holidays, **Worked** is all of those added together, and **Balance** is **Worked** minus **To work**.

## Writing a length of time

Wherever the system asks you how long something took, it accepts several ways of writing it. These are the ones it reads.

| What you type    | What is recorded   | Note                                                |
| ---------------- | ------------------ | --------------------------------------------------- |
| `1:30`           | 1 hour 30 minutes  | Hours and minutes. The minutes must be 00 to 59     |
| `7:42`           | 7 hours 42 minutes |                                                     |
| `1.5` or `1,5`   | 1 hour 30 minutes  | Decimal hours. A comma works as well as a full stop |
| `7.7`            | 7 hours 42 minutes | Decimal hours, rounded to the nearest minute        |
| `7h`             | 7 hours            |                                                     |
| `90m` or `90min` | 90 minutes         |                                                     |

A number on its own is refused. If you type `20` and press **Add**, you are told:

> Say how long it was: 1:30, 7h, or 90m. A number on its own does not say whether you mean hours or minutes.

This is deliberate. Twenty minutes and twenty hours are both plausible, and the system will not guess. Write `20m` for twenty minutes or `20:00` for twenty hours.

Anything else it cannot read gets a shorter message:

> Say how long it was. Type 1:30 or 1.5.

Two limits apply to hours you type in for a day. An entry of no time at all is refused. So is a single entry longer than 24 hours, with the message "A single day cannot hold more than 24 hours."

Everywhere the system shows you a length, it shows it as hours and minutes with a colon: `161:42` means 161 hours and 42 minutes, not 161 hours and 42 hundredths. The one place you will see decimal hours is the invoice figure on **My time**, which says so in words.

## A timer on a work item

This is how most hours are recorded. The timer runs on the work item, and what it records is counted in your month automatically.

### Starting a timer

1. Open the work item.
2. Scroll to the activity area at the bottom. Above it, on the right, there is a **Start timer** button.
3. Press it. The button becomes **Stop timer**, with the time counting up beside it in the form `12m 5s`.

You will not see **Start timer** at all unless two things are true: you are one of the people the work item is assigned to, and the work item is in a state where timers are allowed. If you are neither an assignee nor an administrator of the project, neither **Start timer** nor **Log work** is shown to you at all. If you are doing the work but are not on the work item, ask for it to be assigned to you. There is no way to start a timer on somebody else's behalf.

Once a timer is running anywhere, a clock appears in the bar across the top of every page, with a green dot on it. Press it and a small panel names the work item, when the timer started, the time **Elapsed**, and a red **Stop timer** button. This clock only looks in the workspace you are currently in. A timer running in another workspace still counts, still blocks the month, and will not show up in this clock — see the warning at the end of this section.

There is also a small start button on rows in the list and board views, next to the state, for work items assigned to you.

### Stopping a timer

1. Press **Stop timer** (either on the work item, on the list row, or in the clock at the top of the page).
2. On the work item and on list rows, a small box opens asking "What did you work on? (optional)". Type a note or leave it empty.
3. Press **Save**.

The time recorded is the whole stretch from when you started to when you stopped. It does not know about the coffee you made in the middle. If you stopped work and did not stop the timer, correct the entry afterwards.

### What a running timer counts

Nothing, while it is running.

- It adds nothing to **Work items**, nothing to **Worked**, and nothing to your **Balance**.
- It becomes hours only when you stop it. That is the moment its length exists.
- On "Hours in detail" a running timer is listed with the note "Still running — it has no length yet and counts nothing".
- A month cannot be handed in while one of your timers is still running in it. **My time** says so: "A timer is still running on one of your work items, in this or another workspace. Stop it, then you can hand the month in."

You can only have one timer running at a time. If you start a second one, the first is stopped for you at that moment and its time is recorded. Nothing warns you first, so if you were meant to keep the first one going, check it afterwards.

### A timer left running

A timer left running overnight would write the whole night into your month. To stop that, the system checks every hour and closes any timer that has been running for more than ten hours. It closes it at exactly ten hours and puts `[automatically stopped]` at the front of the note.

Ten hours is a limit, not a measurement. Nobody knows when you actually stopped. On "Hours in detail" the entry is marked "— stopped by the system, needs correcting", and it needs correcting on the work item before the month is handed in.

### Which day the hours land on

An hour counts on the day its timer **started**. A session begun at 23:40 on 31 March and stopped at 00:20 on 1 April sits wholly in March.

The day is worked out in your own timezone — the one on your employment record, or Vienna if none is set. It is not your computer's timezone and not the reader's. This matters at the end of a month: hours from a late session on the last day of the month belong to that month, and if the month has already been handed in they cannot go in at all.

Hours count wherever you logged them. The company keeps more than one workspace in Plane, and hours from all of them are added together in your month. That is why your month can be larger than what any single project shows.

### How timer hours are rounded

Timers are kept in seconds. For each day and each project, the seconds are added up first and rounded to the nearest minute once, at the end.

Three sessions of 25 minutes 20 seconds on the same work item on the same day come to 76 minutes, not 75. Rounding each session on its own would lose a few seconds every time, and over a month that becomes real time you worked and were not credited with.

### Correcting or removing timer hours

Timer hours are corrected on the work item they were logged against, not on **My time**.

1. Open the work item and go to the **Worklogs** tab in the activity area.
2. Find the entry. Each one shows who logged it, how long, and the start and end times.
3. Press **Edit** under it. **Start**, **End** and the description become editable.
4. Change what is wrong and press **Save**.

The length is worked out from **Start** and **End**, so to change how long something took, move the end time. An entry shorter than a minute is refused with "End time must be after the start time."

To take an entry out entirely, press **Delete** under it and confirm. The confirmation says plainly that this cannot be undone, and it cannot: the entry is gone.

You may edit and delete your own entries. A project administrator may edit and delete anybody's.

## Hours with no work item

Some working time has no work item behind it: a team meeting, expenses, a training course, a journey. This is where it goes.

### What belongs here, and what does not

The screen says it in one line: "Hours that are not on a work item — meetings, admin, training, travel. They count towards your month. Hours on work items come from the timers there and are not changed here."

**Time off does not belong here.** If you were ill, or on leave, or away for any other reason, do not record it as **Administration**. It would count as hours you worked, it would balance the day so that nothing looks wrong, and it would never touch your leave account or reach payroll as time off. Time off is recorded on the Absences screen — see "Time away from work" and "Leave".

### Adding hours to a day

1. Open **My time** from the sidebar.
2. Find the day. Either press the date in the day table — every date is a button, with a faint pencil beside it — or press **Record time for today** at the top right.
3. A box opens with the day at the top, written out in full: "Tue 10 Mar 2026". Check the year. It is shown because the button and the month arrows can move you further than you meant to go.
4. In **How long**, type the length. The box shows `1:30` as a hint. See [Writing a length of time](#writing-a-length-of-time).
5. In **What it was**, choose from **Internal meeting**, **Training**, **Administration**, **Travel** and **On call**. It starts on **Administration**.
6. In **Note**, write what the time was spent on. This is optional, but a month of entries all saying nothing is a month nobody can check later.
7. Press **Add**. A small message says **Added**. The entry appears in the list above, and the total at the foot of the list, labelled **Hours with no work item**, goes up.

After you press **Add**, **How long** and **Note** are emptied so you can type the next one. **What it was** stays where you left it. If you have added a meeting and the next entry is expenses, change the box back to **Administration** yourself.

Two things to know before you start typing:

- **Pressing Enter does nothing.** There is no keyboard shortcut here. You have to press **Add**.
- **Closing the box throws away anything you have not added.** Whenever there is something in **How long** or **Note**, an amber warning appears at the bottom left: "Not added yet. Press Add, or it is lost when you close." Pressing **Close**, pressing Escape, and clicking on the dark area outside the box all discard it without asking again.

**Record time for today** always goes to today, in the current month, whichever month you were looking at when you pressed it. If you were looking at January and press it, the page moves to this month and opens today. To record time on some other day, step to that month with the arrows beside the month name and press the date.

### Reading what is in the box

| What you see                                                                                         | What it is                                                                                                       |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| A row: a length, a kind, a note                                                                      | One entry. The kind is one of the five choices, or **Imported** for something brought in from a file             |
| An **Imported** label at the end of a row                                                            | The entry came in from a spreadsheet, not from this box                                                          |
| A length with a minus in front, such as `-1:00`                                                      | A correction that takes hours off the day. These can only arrive from a file; nothing you type here can subtract |
| **Hours with no work item**, at the foot of the list                                                 | The total of the rows above it, and nothing else                                                                 |
| "Nothing has been added here yet. Hours recorded on work items are counted, but are not shown here." | No hours of this kind on this day. It does not mean no work was done                                             |

### The two figures in this box are not meant to agree

If your terms say your attendance is kept, there is a second box at the top of the same window, headed **When you were at work**, with a figure of its own on the right. It is easy to read the two as one thing. They are not.

- The figure at the top is **when you were at work** — start, end and break. It is a separate record kept because the law asks for it. It does not count towards your hours and it does not move your balance. See "When you were at work".
- The list underneath is **only the hours with no work item**.
- The hours from your timers are counted in your month but are not shown in this window at all.

So a day with eight hours of timer work will say "Nothing has been added here yet." and a day recorded as 7:30 at work may show 1:30 in the list. Neither is a mistake, and nothing has to be done to make them match. To see everything on a day side by side, use the day table on **My time**, and for the entry-by-entry breakdown, "Hours in detail".

### Correcting an entry

An entry cannot be edited. There is no pencil on the rows. To correct a wrong length, a wrong kind or a wrong note, remove the entry and add it again. That is possible for as long as the month has not been handed in.

### Removing an entry

**Removing an entry cannot be undone.** There is no undo anywhere. The hours are gone from the day and from the month, and if that was a mistake you have to type them in again.

1. At the right-hand end of the row there is a small bin icon. It is a small target, and every row has one, so check you are on the right row before you press it.
2. Press it. A confirmation opens, headed **Remove these hours?**, saying "1:30 of Internal meeting comes off this day and off the month's total."
3. Press **Remove** to go ahead, or **Cancel** to keep the entry.

There is no message afterwards. The row disappears from the list and the totals drop, which is how you know it worked.

You will not see the bin icon on a day in a month that is no longer open, or on an entry that a closed month has already counted.

### Which days you can open

- **Any day of the month you are looking at**, as long as the month has not been handed in.
- **Days still to come.** They are hidden at first. Under the table there is a button reading **Show the rest of the month**, with the number of hidden days after it. Press it and they appear, and they open and accept hours like any other day. Nothing stops you recording a day before it has happened.
- **Any old month that was never handed in.** This is on purpose: it is how months from before the company used Plane are filled in. An old month stays open until somebody hands it in.
- **Days in a month that has been handed in, agreed or closed** open too, but only to look at. See below.

## Hours somebody records for you

Hours can arrive in your month without you putting them there. There are three ways, and all three are visible to you.

**Somebody logs work on a work item for you.** On a work item, next to **Start timer**, there is a **Log work** button. It opens a small panel with **Start**, **End** and a description, and it records a stretch of work without a timer having run. A project administrator also sees a field called **Log work for**, which lets them record the entry against another member of the project. Recorded that way, the hours are yours: they count in your month, on the day the **Start** time falls on, exactly as if you had run the timer. They appear under the **Worklogs** tab of that work item with the name of whoever the time belongs to.

The same panel is how you record work you did without a timer — a meeting on a work item, or an afternoon where you forgot to press start. The defaults are one hour ending now. Change **Start** and **End**, add a description, and press **Save**.

**Somebody brings hours in from a file.** Whoever looks after the team can read hours out of a spreadsheet and write them into people's months. Those arrive as hours with no work item, carry an **Imported** label on the row, and are usually shown as the kind **Imported**. See "Bringing hours in from somewhere else".

**A project administrator stops a timer you left running.** On the **Worklogs** tab of a work item, an administrator sees a stop button beside anybody whose timer is running there. The time up to that moment is recorded as yours.

One thing that is not possible from any screen: nobody can type hours with no work item into your day for you. That box is always about your own day, even for whoever looks after the team. Hours of that kind for somebody else go in through the import.

## Once the month has been handed in

While a month is **Not handed in** or **Reopened**, everything on this page is available to you. Once you press **Hand in**, it stops being yours to change — and so does everything in it, whether it came from a timer, from the day box, or from a file.

You can still open any day and look. What you see instead of the form is:

> This month is no longer open, so its hours cannot be changed. Ask whoever looks after the team to reopen it if something needs correcting.

There is no **Add** button and there are no bin icons.

The same applies from the other side. A timer started, stopped, edited or deleted into a month that has been handed in, agreed or closed is refused with "These hours fall in a month that has already been settled. Reopen it first if they genuinely belong there."

If you had a day open while somebody handed the month in or closed it, adding anything gives you a message headed **That did not go through**, saying:

> March 2026 has been handed in, so its records can no longer change. Ask whoever looks after the team to reopen it on Team time.

Correcting something in a month that has been handed in means asking for the month to be reopened first. "The month, from open to closed" explains that.

## A month, worked through

Anna works Monday to Friday and owes 7 hours 42 minutes on each working day. Her month has 21 working days. One of them is a public holiday and she takes two days of leave, so she is actually at work on 18 of them.

**What she owes.**

```
21 working days × 7:42 = 161:42
```

The public holiday does not reduce this, and neither does the leave. Nothing reduces what you have to work. Time off and public holidays are added to **Worked** instead, so that the hours column sent to payroll is the hours she is paid for. Her over-or-under figure comes out the same either way.

**What she recorded.** Over the 18 days she was at work, her timers came to 133:00 and she added 6:00 of hours with no work item — three team meetings and some admin.

**What the month counts.**

|                         |            |
| ----------------------- | ---------- |
| Work items (timers)     | 133:00     |
| No work item (typed in) | 6:00       |
| Public holiday          | 7:42       |
| Two days of leave       | 15:24      |
| **Worked**              | **162:06** |
| **To work**             | **161:42** |
| **Balance**             | **+0:24**  |

She is 24 minutes ahead for the month.

**One day of it.** On Tuesday 10 March she ran timers for 5 hours 30 minutes, sat in a team meeting for an hour and spent half an hour on expenses. She opens the day, adds `1:00` as **Internal meeting** with the note "Sprint planning", and `0:30` as **Administration** with the note "March expenses". The foot of the list, **Hours with no work item**, reads `1:30`. Her day row then reads:

| Day        | What it was | To work | Work items | No work item | Time off | Worked | Balance |
| ---------- | ----------- | ------- | ---------- | ------------ | -------- | ------ | ------- |
| Tue 10 Mar | Working day | 7:42    | 5:30       | 1:30         | 0:00     | 7:00   | -0:42   |

`5:30 + 1:30 = 7:00`, and `7:00 − 7:42 = −0:42`. She is 42 minutes short on that day. Over the month it comes out even.

**If you invoice us for your own hours**, no hours are expected of you each day, so your **Balance** is 0:00 every day and a public holiday is worth nothing to you. Everything you record still counts, and it is the figure your invoice is written from. "People and their terms" explains which arrangement is which.

## If you get stuck

- To understand the figures on your own month, and what to do at the end of it: "My time — your own month" and "The month, from open to closed".
- For the start, end and break box at the top of the day: "When you were at work".
- To see every entry that made up a month, one line at a time: "Hours in detail".
- For anything to do with being away — illness, leave, or any other reason: "Time away from work" and "Leave".
- For what a public holiday is worth to you: "Public holidays".
- For hours read out of a spreadsheet: "Bringing hours in from somewhere else".
- If a figure looks wrong and none of the above explains it: "When something goes wrong".

Anything that needs a month reopened, an entry taken out of a closed month, or hours recorded for somebody else has to go through whoever looks after the team. Ask them.
