# 3. API reference

[← Connecting a person](02-connecting-a-person.md) · [Overview](README.md) · Next: [Security guide →](04-security-guide.md)

The OAuth endpoints (linking, refresh, revoke) are in [Connecting a person](02-connecting-a-person.md). This page covers the data endpoints. The same information, machine-readable, is in [`openapi.yaml`](openapi.yaml).

- [Conventions](#conventions)
- [Profile](#profile) — `GET /me/`
- [Working days](#working-days) — `GET /me/day/`, `GET /me/days/`
- [Hours and timer](#hours-and-timer) — `GET /me/time/`, `GET /me/timer/`
- [Leave](#leave) — `GET /me/leave/`, `GET /me/absences/`
- [Projects and work items](#projects-and-work-items) — `GET /projects/`, `GET /work-items/`, `GET /workspaces/{slug}/work-items/{ref}/`

---

## Conventions

### Base URL and versioning

```
https://<your plane>/api/agent/v1/
```

- **Trailing slashes are required** on every path.
- `v1` changes only in compatible ways: new endpoints, new optional parameters, **new fields in responses**. Ignore fields you do not know; do not fail on them. A breaking change would be a new `v2`.
- Everything in this version is a `GET`, except the OAuth endpoints. Other methods answer `405`.

### Authentication

```
Authorization: Bearer plane_at_…
```

Only in the header. See [Connecting a person](02-connecting-a-person.md) for obtaining and refreshing tokens. Session cookies and API keys are **not** accepted here, and these tokens are not accepted anywhere else in Plane.

### Responses

- JSON, UTF-8. Every response carries `Cache-Control: no-store`.
- Success is `200`. The body is an object (lists are wrapped: `{"results": […]}`), never a bare array, so fields can be added later.
- Names are `snake_case`. Absent optional values are `null`, not missing.

### Errors

Every error — apart from framework-level failures of a proxy in front of Plane — has this shape:

```json
{ "error": "not_found", "error_description": "No such item, or it is not visible to you." }
```

`error` is a stable code for programs; `error_description` is for humans and may be reworded. Some add context (`scope`, `fields`).

| HTTP | `error`              | Meaning                                                                                                                                   | What to do                                                                         |
| ---- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 400  | `invalid_request`    | A parameter is malformed or out of range (the description says which).                                                                    | Fix the call.                                                                      |
| 401  | `unauthorized`       | No `Authorization` header.                                                                                                                | Send a token.                                                                      |
| 401  | `invalid_token`      | Token unknown, expired, revoked; the connection or app ended; the person deactivated. `WWW-Authenticate: Bearer … error="invalid_token"`. | Refresh once; if that fails with `invalid_grant`, ask the person to connect again. |
| 403  | `insufficient_scope` | The connection was not given the scope this endpoint needs; `"scope"` names it.                                                           | Ask the person to connect again with that scope — or do without.                   |
| 404  | `not_found`          | No such item **or it is not visible to this person**. The two are indistinguishable on purpose.                                           | —                                                                                  |
| 405  | `method_not_allowed` | Not a `GET`.                                                                                                                              | —                                                                                  |
| 429  | `rate_limited`       | Too many calls. `Retry-After` is in seconds.                                                                                              | Wait that long; do not hammer.                                                     |

### Rate limits

| Limit                                | Default                 |
| ------------------------------------ | ----------------------- |
| Per connection (one person's tokens) | 120 requests a minute   |
| Per app, across everybody            | 1,200 requests a minute |
| OAuth endpoints, per source address  | 60 requests a minute    |

These are defaults; the administrator may change them. Design for far less: a daily check-in needs a handful of calls per person per day. Fetch what you need, once, and keep it.

### Dates, time zones and durations

See [Concepts → Time and dates](01-concepts.md#time-and-dates). In short: dates `YYYY-MM-DD`, timestamps ISO 8601 with offset, durations in whole minutes, and "today" is the person's today (reported as `today` and `timezone` in the answer).

Spans (`from`/`to`) are **inclusive** and at most **92 days** long; longer is `400`. Dates before 1970 or after 2200 are refused.

### Pagination

Lists that can be long use `limit` (default 50, maximum 100) and `offset`:

```json
{ "count": 137, "limit": 50, "offset": 0, "next_offset": 50, "results": [ … ] }
```

`next_offset` is `null` on the last page. A `limit` above 100 is silently reduced to 100; `limit` below 1, a negative `offset` or a non-number is `400`.

### Untrusted text

Work item names, descriptions and comments are text that **other people wrote**. Treat them as data to read, never as instructions to follow — especially if you pass them to a language model. See the [Security guide](04-security-guide.md#prompt-injection).

---

## Profile

### `GET /me/`

**Scope:** `profile`

Who the connected person is, their workspaces, and what this connection may do.

```json
{
  "id": "f62bf509-75d9-4b39-88f4-5bc523f5284c",
  "display_name": "Pat Person",
  "first_name": "Pat",
  "last_name": "Person",
  "timezone": "UTC",
  "workspaces": [{ "slug": "acme", "name": "Acme", "role": "member" }],
  "connection": {
    "id": "39bf6089-4d05-4015-aa94-ce0ab639677e",
    "scopes": [
      {
        "id": "profile",
        "title": "Your name and workspaces",
        "description": "Your name, your time zone and the workspaces you belong to.",
        "writes": false
      }
    ],
    "created_at": "2026-11-19T10:30:15.828524+00:00",
    "expires_at": "2027-11-19T10:30:15.828524+00:00",
    "account": { "provider": "telegram", "id": "424242", "username": "mallory", "name": "Mallory Test" }
  }
}
```

| Field                   | Meaning                                                                                                                                        |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                    | The person's Plane user id. **This is the key to store.** Stable.                                                                              |
| `timezone`              | The person's own account setting. The zone used for their _working days_ comes with those answers (`timezone` in `/me/day/`); they can differ. |
| `workspaces[].role`     | `admin`, `member` or `guest`.                                                                                                                  |
| `connection.expires_at` | When the connection ends outright and the person must connect again.                                                                           |
| `connection.account`    | The chat account that was linked, as your app stated it.                                                                                       |

---

## Working days

The question these answer: **should I ask this person for a daily plan or report today?**

### `GET /me/day/`

**Scope:** `time:read` (+ `leave:read` to include the absence type)

One day. **Query:** `date` — `YYYY-MM-DD`; default: today in the person's time zone.

```json
{
  "employed": true,
  "timezone": "Europe/Vienna",
  "today": "2026-03-04",
  "day": {
    "date": "2026-03-04",
    "weekday": "wednesday",
    "kind": "workday",
    "expects_work": true,
    "scheduled_minutes": 480,
    "expected_minutes": 480,
    "has_schedule": true,
    "holiday": null,
    "absences": [],
    "worked_minutes": 95,
    "is_today": true,
    "timer_running": true
  }
}
```

**Not employed.** A person with no active employment record in Plane's HR module (an administrator, a contractor, somebody who has left) gets:

```json
{ "employed": false, "timezone": "UTC", "date": "2026-03-04", "day": null }
```

This is a normal answer, not an error. There is no schedule to consult, so the bot cannot know their working days; decide what to do (usually: do not run the daily check-in for them).

#### The day object

| Field               | Type           | Meaning                                                                                                                                                                         |
| ------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `date`, `weekday`   | string         | The day; `weekday` is `monday`…`sunday`.                                                                                                                                        |
| `kind`              | string         | What the day is for this person — see below.                                                                                                                                    |
| `expects_work`      | boolean        | **`true` if any working time is expected after public holidays and approved absences.** This is the field to branch on.                                                         |
| `scheduled_minutes` | integer        | What their work schedule says for this weekday, before anything else.                                                                                                           |
| `expected_minutes`  | integer        | `scheduled_minutes` minus the share taken by a public holiday and by approved absence (never below 0).                                                                          |
| `has_schedule`      | boolean        | `false` means no work schedule covers this day at all — a gap in the records, **not** a day off. `expects_work` is `false` then, but you should not treat the person as "away". |
| `holiday`           | object \| null | `{"name": "Easter Monday", "fraction": 1.0}`; `fraction` is 0.5 for a half holiday. The name is English where available, else German.                                           |
| `absences`          | array          | The **approved** absences covering the day (see below). Usually 0 or 1.                                                                                                         |
| `worked_minutes`    | integer        | Finished hours on work items plus hours entered by hand for this date. _`/me/day/` only._                                                                                       |
| `is_today`          | boolean        | _`/me/day/` only._                                                                                                                                                              |
| `timer_running`     | boolean        | Whether the person has a timer running right now (not necessarily on this date). _`/me/day/` only._                                                                             |

#### `kind`

| Value                 | Meaning                                                                                                                                   | `expects_work` |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| `workday`             | An ordinary working day.                                                                                                                  | `true`         |
| `non_working_day`     | The schedule has no work this weekday (weekend, a part-time person's day off). A public holiday on such a day is still `non_working_day`. | `false`        |
| `public_holiday`      | A full public holiday on a day they would have worked.                                                                                    | `false`        |
| `half_public_holiday` | Half a public holiday (for example Christmas Eve); the other half is a working half-day.                                                  | `true`         |
| `absence`             | Approved time off for the whole of a working day.                                                                                         | `false`        |
| `partial_absence`     | Approved time off for part of the day (a half day, or some hours).                                                                        | `true`         |

#### Absences on a day

```json
{ "granularity": "half_day", "half": "morning", "minutes": null, "type": { "code": "urlaub", "name": "Annual leave" } }
```

| Field         | Meaning                                                                                                                         |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `granularity` | `full_day`, `half_day` or `hours`.                                                                                              |
| `half`        | `morning` or `afternoon` for a half day; otherwise `null`.                                                                      |
| `minutes`     | Minutes off, for `hours`; otherwise `null`.                                                                                     |
| `type`        | `{code, name}` — **only if the connection has `leave:read`.** Without it the key is absent, because the type can be sick leave. |

Only **approved** absences count. A request still waiting for approval, or rejected, does not change the day.

### `GET /me/days/`

**Scope:** `time:read` (+ `leave:read`)

A span of days — for "who is in this week", or "will they have the working days to finish this by next week". **Query:** `from`, `to` (inclusive, ≤ 92 days). Default: seven days starting today.

```json
{
  "employed": true,
  "timezone": "Europe/Vienna",
  "today": "2026-03-04",
  "from": "2026-03-02",
  "to": "2026-03-08",
  "expected_minutes": 1200,
  "working_days": 3,
  "days": [
    {
      "date": "2026-03-02",
      "weekday": "monday",
      "kind": "workday",
      "expects_work": true,
      "scheduled_minutes": 480,
      "expected_minutes": 480,
      "has_schedule": true,
      "holiday": null,
      "absences": []
    },
    {
      "date": "2026-03-04",
      "weekday": "wednesday",
      "kind": "public_holiday",
      "expects_work": false,
      "scheduled_minutes": 480,
      "expected_minutes": 0,
      "has_schedule": true,
      "holiday": { "name": "Test Holiday", "fraction": 1.0 },
      "absences": []
    },
    {
      "date": "2026-03-06",
      "weekday": "friday",
      "kind": "partial_absence",
      "expects_work": true,
      "scheduled_minutes": 480,
      "expected_minutes": 240,
      "has_schedule": true,
      "holiday": null,
      "absences": [
        {
          "granularity": "half_day",
          "half": "morning",
          "minutes": null,
          "type": { "code": "urlaub", "name": "Annual leave" }
        }
      ]
    }
  ]
}
```

(Abbreviated: the real answer lists every day in the span.)

`expected_minutes` (top level) is the total working time expected across the span, and `working_days` the number of days with `expects_work: true` — the two figures a capacity estimate needs. For a person who is not employed: `{"employed": false, "from": …, "to": …, "days": []}`.

---

## Hours and timer

### `GET /me/time/`

**Scope:** `time:read` (+ `work_items:read` to name the work items)

How much the person worked in a span, per day and per work item. **Query:** `from`, `to` (inclusive, ≤ 92 days). Default: the last seven days ending today.

```json
{
  "from": "2026-03-02",
  "to": "2026-03-08",
  "timezone": "Europe/Vienna",
  "employed": true,
  "total_minutes": 95,
  "work_item_minutes": 95,
  "other_minutes": 0,
  "days": [{ "date": "2026-03-03", "minutes": 95, "work_item_minutes": 95, "other_minutes": 0 }],
  "work_items": [
    {
      "minutes": 95,
      "entries": 1,
      "work_item": { "id": "df9faeac-…", "ref": "WEB-1", "name": "Fix the header on mobile", "…": "…" }
    }
  ],
  "timer": {
    "started_at": "2026-03-04T08:05:00+00:00",
    "elapsed_minutes": 50,
    "note": "",
    "work_item": { "ref": "WEB-1", "name": "Fix the header on mobile", "…": "…" }
  }
}
```

| Field               | Meaning                                                                                                                                                                                                                                                                                                                                       |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `work_item_minutes` | Hours from timers and manual entries **on work items**.                                                                                                                                                                                                                                                                                       |
| `other_minutes`     | Hours entered by hand with no work item (meetings, admin, training).                                                                                                                                                                                                                                                                          |
| `total_minutes`     | The sum. Agrees with _My time_ in Plane: hours are summed per day per project and rounded once.                                                                                                                                                                                                                                               |
| `days`              | Only days that have hours.                                                                                                                                                                                                                                                                                                                    |
| `work_items`        | `null` unless the connection has `work_items:read`. Largest first, at most 50. Each `work_item` is the [work item summary](#work-item-summary), or `null` if the person can no longer see it — the time still counts, it is just not named. Per-item minutes are rounded individually, so they may differ from the totals by a minute or two. |
| `timer`             | The running timer, if any (not limited to the span). `work_item` is `null` without `work_items:read`.                                                                                                                                                                                                                                         |

A running timer's minutes are **not** in any total until it stops.

### `GET /me/timer/`

**Scope:** `time:read` (+ `work_items:read`)

What the person's timer is running on right now. A person can have only one timer, across all workspaces.

```json
{
  "running": true,
  "timer": {
    "started_at": "2026-03-04T08:05:00+00:00",
    "elapsed_minutes": 50,
    "note": "",
    "work_item": { "ref": "WEB-1", "name": "Fix the header on mobile", "…": "…" }
  }
}
```

No timer: `{"running": false, "timer": null}`. `note` is the text the person typed on the timer.

---

## Leave

### `GET /me/leave/`

**Scope:** `leave:read`

How much annual leave is left in the current leave year. All amounts are in **minutes**; divide by the person's daily schedule to get days (a 480-minute day: 12,000 minutes is 25 days).

```json
{
  "employed": true,
  "keeps_leave_account": true,
  "leave": {
    "leave_year_start": "2026-01-01",
    "leave_year_end": "2026-12-31",
    "granted_minutes": 12000,
    "taken_minutes": 720,
    "remaining_minutes": 11280,
    "is_final": false
  }
}
```

- `taken_minutes` counts **approved** absences only, by Plane's own arithmetic (a public holiday inside a booked week costs no leave).
- `remaining_minutes` is signed: negative means leave was allowed in advance.
- `leave` is `null` when no entitlement is on record for this year ("nobody has said what it is" — not zero), or when the person's contract keeps no leave account (`keeps_leave_account: false`).

### `GET /me/absences/`

**Scope:** `leave:read`

The person's **approved** absences that touch a span. **Query:** `from`, `to` (≤ 92 days). Default: thirty days starting today.

```json
{
  "employed": true,
  "from": "2026-03-01",
  "to": "2026-03-31",
  "absences": [
    {
      "start_date": "2026-03-05",
      "end_date": "2026-03-05",
      "type": { "code": "urlaub", "name": "Annual leave" },
      "granularity": "full_day",
      "start_half": null,
      "end_half": null,
      "minutes_per_day": null
    },
    {
      "start_date": "2026-03-06",
      "end_date": "2026-03-06",
      "type": { "code": "urlaub", "name": "Annual leave" },
      "granularity": "half_day",
      "start_half": "morning",
      "end_half": "morning",
      "minutes_per_day": null
    }
  ]
}
```

`type.code` is the stable identifier; the standard ones are `urlaub` (annual leave), `krankenstand` (sick leave), `zeitausgleich` (time off in lieu), `pflegefreistellung` (care leave), `dienstverhinderung` (other justified absence) and `unbezahlt` (unpaid leave), but a company can add its own. **The reason a person gave is never returned.**

---

## Projects and work items

What the person can see is exactly what they see in Plane: projects they are an active member of; within them, everything for members, and — for a _guest_ — only the work they created unless the project lets guests see everything. Drafts, archived items, items in archived projects, work waiting for triage and deleted work are not included. Visibility is evaluated on every call.

### Work item summary

The shape used in lists, in `/me/time/` and in `/me/timer/`:

```json
{
  "id": "df9faeac-226f-4c40-9c88-ff8bd97d2647",
  "ref": "WEB-1",
  "url": "https://plane.example.com/acme/browse/WEB-1/",
  "name": "Fix the header on mobile",
  "workspace": "acme",
  "project": { "id": "10005b47-…", "name": "Website relaunch", "identifier": "WEB" },
  "state": { "id": "9e8df6d5-…", "name": "Started", "group": "started" },
  "priority": "high",
  "start_date": null,
  "target_date": "2026-03-10",
  "estimate": null,
  "assignees": [{ "id": "f62bf509-…", "display_name": "Pat Person" }],
  "labels": [],
  "parent": null,
  "created_at": "2026-11-19T10:31:05.203365+00:00",
  "updated_at": "2026-11-19T10:31:05.203378+00:00",
  "completed_at": null,
  "my_logged_minutes": 95
}
```

| Field               | Meaning                                                                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ref`               | The short name people use: project identifier and number. Unique within a workspace. Use it when you talk to the person; use `id` as your stable key. |
| `url`               | Link to open it in Plane. Hand this to the person; do not fetch it.                                                                                   |
| `state.group`       | `backlog`, `unstarted`, `started`, `completed` or `cancelled` — the stage, independent of how the project names its states.                           |
| `priority`          | `urgent`, `high`, `medium`, `low` or `none`.                                                                                                          |
| `target_date`       | The due date.                                                                                                                                         |
| `estimate`          | The estimate value as the project defines it, or `null`.                                                                                              |
| `parent`            | The id of the parent work item, if any.                                                                                                               |
| `my_logged_minutes` | Finished time **the connected person** logged on it. Other people's time is never included.                                                           |

### `GET /projects/`

**Scope:** `work_items:read`

The projects the person is an active member of. **Query:** `workspace` — a workspace slug, to narrow.

```json
{
  "results": [
    {
      "id": "10005b47-…",
      "name": "Website relaunch",
      "identifier": "WEB",
      "workspace": "acme",
      "description": "",
      "role": "member"
    }
  ]
}
```

`role` is the person's role in that project: `admin`, `member` or `guest`.

### `GET /work-items/`

**Scope:** `work_items:read`

Work items across the person's projects. All filters combine with AND.

| Query                     | Values                                                                                            | Meaning                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `assignee`                | `me`                                                                                              | Only work assigned to the connected person. (`me` is the only value; there is no way to ask about someone else.) |
| `state_group`             | comma list of `backlog`, `unstarted`, `started`, `completed`, `cancelled`                         | Stage. "Their open work" is `backlog,unstarted,started`.                                                         |
| `priority`                | comma list of `urgent`, `high`, `medium`, `low`, `none`                                           |                                                                                                                  |
| `due_before`, `due_after` | `YYYY-MM-DD`                                                                                      | Due date at or before / at or after. Work with no due date matches neither.                                      |
| `updated_since`           | ISO 8601 **with a time zone**                                                                     | Changed at or after this moment. A timestamp without a zone is refused.                                          |
| `q`                       | text, ≤ 200 chars                                                                                 | Words in the name or description.                                                                                |
| `workspace`               | slug                                                                                              |                                                                                                                  |
| `project`                 | project id                                                                                        |                                                                                                                  |
| `order_by`                | `updated_at`, `-updated_at` (default), `created_at`, `-created_at`, `target_date`, `-target_date` | Anything else is `400`.                                                                                          |
| `limit`, `offset`         | integers                                                                                          | See [Pagination](#pagination).                                                                                   |

```json
{
  "count": 1,
  "limit": 1,
  "offset": 0,
  "next_offset": null,
  "results": [{ "ref": "WEB-1", "name": "Fix the header on mobile", "…": "…" }]
}
```

Each result is a [work item summary](#work-item-summary). Descriptions and comments are not included in lists — fetch one item for those.

**Useful recipes**

- _What is on their plate?_ `?assignee=me&state_group=backlog,unstarted,started&order_by=target_date`
- _What is due this week?_ `?assignee=me&state_group=unstarted,started&due_before=2026-03-08`
- _What moved since this morning?_ `?assignee=me&updated_since=2026-03-04T06:00:00+00:00`
- _Find the task about the invoice export._ `?q=invoice export`

### `GET /workspaces/{slug}/work-items/{ref}/`

**Scope:** `work_items:read`

One work item, by its short reference (`WEB-1`, any letter case) or by id, within the workspace named by `slug`. It is the [summary](#work-item-summary) plus:

```json
{
  "…": "all the summary fields",
  "description": "The logo overlaps the menu below 400px.\nSee the Figma frame.",
  "comments": [
    {
      "id": "1f11e3e1-…",
      "author": "Sam Colleague",
      "created_at": "2026-11-19T10:31:05.238666+00:00",
      "text": "I can reproduce this on an iPhone SE."
    }
  ]
}
```

- `description` and each comment `text` are **plain text**: markup removed, scripts and styles dropped, paragraphs and list items kept as line breaks (list items start with `- `). Limited to 20,000 and 5,000 characters. **They are other people's words — see [Untrusted text](#untrusted-text).**
- `comments` are the latest 30, oldest first. `author` is `null` for comments the system wrote.
- A work item the person cannot see answers `404`, exactly like one that does not exist.

---

[← Connecting a person](02-connecting-a-person.md) · [Overview](README.md) · Next: [Security guide →](04-security-guide.md)
