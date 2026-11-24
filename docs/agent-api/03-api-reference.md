# 3. API reference

[← Connecting a person](02-connecting-a-person.md) · [Overview](README.md) · Next: [Security guide →](04-security-guide.md)

The OAuth endpoints (linking, refresh, revoke) are in [Connecting a person](02-connecting-a-person.md). This page covers the data endpoints. The same information, machine-readable, is in [`openapi.yaml`](openapi.yaml).

- [Conventions](#conventions)
- [Profile](#profile) — `GET /me/`
- [Working days](#working-days) — `GET /me/day/`, `GET /me/days/`
- [Hours and timer](#hours-and-timer) — `GET /me/time/`, `GET /me/timer/`
- [Leave](#leave) — `GET /me/leave/`, `GET /me/absences/`
- [Projects and work items](#projects-and-work-items) — `GET /projects/`, `GET /work-items/`, `GET /workspaces/{slug}/work-items/{ref}/`
- [Making changes](#making-changes) — the rules, idempotency, dry runs, errors
- [What the person can pick from](#what-the-person-can-pick-from) — members, states, labels
- [Work items: create and change](#work-items-create-and-change) — create, change, comment, attach
- [Time: timer and hours](#time-timer-and-hours) — start, stop, add hours

---

## Conventions

### Base URL and versioning

```
https://<your plane>/api/agent/v1/
```

- **Trailing slashes are required** on every path.
- `v1` changes only in compatible ways: new endpoints, new optional parameters, **new fields in responses**. Ignore fields you do not know; do not fail on them. A breaking change would be a new `v2`.
- Reads are `GET`. Changes are `POST` and `PATCH`, need a write scope, and are described under [Making changes](#making-changes). Any other method answers `405`.

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
| 405  | `method_not_allowed` | The path does not take that method.                                                                                                       | —                                                                                  |
| 429  | `rate_limited`       | Too many calls. `Retry-After` is in seconds.                                                                                              | Wait that long; do not hammer.                                                     |

### Rate limits

| Limit                                    | Default                 |
| ---------------------------------------- | ----------------------- |
| Per connection (one person's tokens)     | 120 requests a minute   |
| Writes (`POST`, `PATCH`), per connection | 30 requests a minute    |
| Per app, across everybody                | 1,200 requests a minute |
| OAuth endpoints, per source address      | 60 requests a minute    |

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
- The same path also takes `PATCH` to change the work item — see [Making changes](#making-changes).

---

## Making changes

Everything above reads. The endpoints below change something, always **as the connected person**, with the same rules the web app applies to them and the same effects: the work item gets its number, its activity entry, its notifications and its webhooks, and shows in Plane under the person's name. An app is not given a looser way in.

They need a **write scope** (`work_items:write`, `time:write`), which the person approved on the approval screen ("Can make changes"), and the app must have been registered for it ([Operations](05-operations.md#registering-an-app)).

### The rules every change follows

| Rule                             | What it means for you                                                                                                                                                                                                                                |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **JSON in** (files: multipart)   | `Content-Type: application/json`. Anything else is `415`.                                                                                                                                                                                            |
| **Strict fields**                | Only the fields listed for an endpoint are accepted. An unknown field — `created_by`, `is_draft`, `description_html`, anything — is `400`, not ignored. You cannot set what you were not meant to set.                                               |
| **Plain text becomes safe HTML** | Descriptions and comments are sent as **plain text**. Plane escapes every character before storing it: `<script>` arrives as the visible text `<script>`. Blank lines separate paragraphs; single line breaks are kept.                              |
| **`Idempotency-Key`**            | **Required** on every request that would otherwise happen twice when you retry (create a work item, comment, attach a file, add hours). See below.                                                                                                   |
| **`?dry_run=true`**              | On creating and changing a work item: check everything, change nothing, and say what _would_ happen. Use it to show the person what you are about to do and ask them to confirm.                                                                     |
| **Roles**                        | The person's role in the project decides. Members and admins may create and change; guests may only comment on what they can see. A project the person is not in answers `404`, like one that does not exist; one they are a guest in answers `403`. |
| **Limits**                       | Writes are limited to **30 a minute per connection** (default), far below reads. Over the limit is `429` with `Retry-After`.                                                                                                                         |
| **Audit**                        | Each change is written to the audit log with the **ids** of what it touched — never its content — so the person and the administrator can see what the bot did.                                                                                      |

### Idempotency: doing it once

Chat apps retry: a webhook is delivered twice, a model calls a tool again, a reply is lost on the way. Each of those would otherwise create a second work item, a second comment, another hour on somebody's month.

Send an `Idempotency-Key` header naming **the one action you intend** — 8 to 128 printable characters, no spaces. A UUID is ideal, and so is something stable from the source of the request (for Telegram: `tg-<update_id>-create`).

```
POST /workspaces/acme/projects/…/work-items/
Idempotency-Key: tg-884412-create
```

| You send                                              | You get                                                                                                  |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| A key for the first time                              | The action is done; the answer is kept for 24 hours.                                                     |
| The **same key and the same request** again           | The **first answer again** (same status, same body) with `Idempotent-Replay: true`, and nothing is done. |
| The same key with a **different** request             | `422 idempotency_key_reused`. Use a new key for a new action.                                            |
| The same key while the first is still being worked on | `409 request_in_progress` with `Retry-After`. Wait and repeat.                                           |
| A key whose request was **refused** (4xx)             | Nothing is kept: fix the request and send it again with the same key.                                    |

Keys belong to one connection; two people's keys never collide. Only successful answers are kept. Without a key, these endpoints answer `400`.

Changing a work item (`PATCH`), starting a timer and stopping it do not need a key: doing the same thing twice changes nothing the second time.

### Asking first: `dry_run`

```bash
curl -sS -X POST "$PLANE/api/agent/v1/workspaces/acme/projects/$PROJECT/work-items/?dry_run=true" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Fix the header on mobile", "priority": "high", "assignees": ["f62bf509-…"]}'
```

```json
{
  "dry_run": true,
  "valid": true,
  "would_create": {
    "project": { "id": "10005b47-…", "name": "Website relaunch", "identifier": "WEB" },
    "name": "Fix the header on mobile",
    "description": "",
    "priority": "high",
    "state": { "id": "9e8df6d5-…", "name": "Backlog", "group": "backlog" },
    "assignees": [{ "id": "f62bf509-…", "display_name": "Pat Person" }],
    "labels": [],
    "start_date": null,
    "target_date": null
  }
}
```

It runs **every check the real request would** (permissions, assignee membership, dates), so `valid: true` means the real request will succeed unless something changes in between. The preview uses Plane's own words — the person's name, the state's name — so the confirmation you show is true to what will happen, not what you hope will.

### Errors specific to changes

| HTTP | `error`                  | Meaning                                                                                                   | What to do                                                      |
| ---- | ------------------------ | --------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 400  | `invalid_request`        | A field is missing, malformed, unknown or not allowed; `fields` may name which.                           | Fix it.                                                         |
| 403  | `forbidden`              | The person's role in the project does not allow this.                                                     | Tell the person; do not retry.                                  |
| 403  | `not_assigned`           | Starting a timer on work the person is not assigned to.                                                   | Assign them first, or tell them.                                |
| 404  | `not_found`              | No such project or work item, **or the person cannot see it.**                                            | —                                                               |
| 409  | `state_not_allowed`      | A timer cannot be started in the work item's current state (the project decides which states allow time). | Move it to a state that does, or tell the person.               |
| 409  | `timer_running`          | The change would move work to a state where time cannot be tracked while a timer is running on it.        | Stop the timer first (`POST /me/timer/stop/`).                  |
| 409  | `month_settled`          | Hours would land in a month that has already been settled; `period_start` says which.                     | A person must reopen the month in Plane; do not work around it. |
| 409  | `request_in_progress`    | See idempotency.                                                                                          | Wait, repeat.                                                   |
| 413  | `file_too_large`         | The file is over the size limit; `limit` is in bytes.                                                     | Tell the person.                                                |
| 400  | `file_type_not_allowed`  | The file type is not accepted (SVG images are refused outright).                                          | Tell the person.                                                |
| 422  | `idempotency_key_reused` | See idempotency.                                                                                          | Use a new key.                                                  |
| 502  | `storage_unavailable`    | The file could not be saved (Plane's storage or Google Drive).                                            | Retry later; nothing was stored.                                |

---

## What the person can pick from

Before an app creates work it needs to know who can be assigned and which states and labels exist. These read endpoints answer for **projects the person is a member of** (anything else is `404`).

**Scope:** `work_items:read`.

### `GET /workspaces/{slug}/projects/{project_id}/members/`

```json
{
  "results": [
    { "id": "f62bf509-…", "display_name": "Pat Person", "role": "member", "can_be_assigned": true },
    { "id": "5d6c1e88-…", "display_name": "Guest Gina", "role": "guest", "can_be_assigned": false }
  ]
}
```

Active members only, people (not bots), by name. Guests are listed but cannot be assigned work. **Find a person by matching the name the human gave you against this list in your own code; do not let a language model invent an id** — pass it only an id that appeared here.

### `GET /workspaces/{slug}/projects/{project_id}/states/`

```json
{
  "results": [
    { "id": "93837d28-…", "name": "Backlog", "group": "backlog", "default": true },
    { "id": "e1a0b2c4-…", "name": "In progress", "group": "started", "default": false },
    { "id": "c7d19f30-…", "name": "Done", "group": "completed", "default": false }
  ]
}
```

### `GET /workspaces/{slug}/projects/{project_id}/labels/`

```json
{ "results": [{ "id": "7a54d0cf-…", "name": "bug", "color": "#ff0000" }] }
```

---

## Work items: create and change

### `POST /workspaces/{slug}/projects/{project_id}/work-items/`

**Scope:** `work_items:write` · **Needs:** `Idempotency-Key` · **Role:** admin or member of the project · **Supports:** `?dry_run=true`

| Field                       | Type              | Required | Meaning                                                                                                                          |
| --------------------------- | ----------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `name`                      | string, ≤ 255     | yes      | The title.                                                                                                                       |
| `description`               | string, ≤ 20,000  | no       | **Plain text.** Blank lines separate paragraphs.                                                                                 |
| `priority`                  | string            | no       | `urgent`, `high`, `medium`, `low`, `none` (default `none`).                                                                      |
| `state`                     | id                | no       | A state of this project; default is the project's default state.                                                                 |
| `assignees`                 | list of ids, ≤ 20 | no       | Project members who can be assigned (not guests). If none is given, Plane assigns the project's default assignee, if it has one. |
| `labels`                    | list of ids, ≤ 20 | no       | Labels of this project.                                                                                                          |
| `start_date`, `target_date` | `YYYY-MM-DD`      | no       | `start_date` must not be after `target_date`.                                                                                    |

**`201`** — the new work item, in the [same shape as reading one](#get-workspacesslugwork-itemsref) (reference, link, description, comments):

```json
{
  "id": "df9faeac-226f-4c40-9c88-ff8bd97d2647",
  "ref": "WEB-1",
  "url": "https://plane.example.com/acme/browse/WEB-1/",
  "name": "Fix the header on mobile",
  "priority": "high",
  "state": { "id": "93837d28-…", "name": "Backlog", "group": "backlog" },
  "assignees": [{ "id": "f62bf509-…", "display_name": "Pat Person" }],
  "description": "The logo overlaps the menu.\nSee the Figma frame.",
  "comments": [],
  "…": "…"
}
```

Reply to the person with `url`: it is the link to the work item in Plane. Their name is on it as its creator.

### `PATCH /workspaces/{slug}/work-items/{ref}/`

**Scope:** `work_items:write` · **Role:** admin or member of the project · **Supports:** `?dry_run=true` · No key needed.

Change one or more of these; send at least one:

| Field                               | Meaning                                                                                                                                                    |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                              | New title.                                                                                                                                                 |
| `priority`                          | `urgent`, `high`, `medium`, `low`, `none`.                                                                                                                 |
| `state`                             | A state id of this work item's project. (Completing sets the completion time, as in the web app.)                                                          |
| `start_date`, `target_date`         | `YYYY-MM-DD`, or `null` to clear.                                                                                                                          |
| `add_assignees`, `remove_assignees` | Lists of user ids. **You add and remove; you never send the whole list**, so an app that does not know who is already on a work item cannot take them off. |
| `add_labels`, `remove_labels`       | Lists of label ids, likewise.                                                                                                                              |

```json
{
  "changed": {
    "priority": { "from": "low", "to": "high" },
    "assignees": { "from": ["f62bf509-…"], "to": ["5d6c1e88-…", "f62bf509-…"] }
  },
  "work_item": { "ref": "WEB-1", "…": "the work item as it is now" }
}
```

`changed` lists only what actually changed (and is `{}` if nothing did — the same change twice is harmless). The description **cannot** be changed here; add a comment instead.

Moving a work item to a state where time cannot be tracked while a timer is running on it is refused (`409 timer_running`), exactly as in the web app.

With `?dry_run=true`: `{"dry_run": true, "valid": true, "ref": "WEB-1", "would_change": {…}}`, nothing is changed.

### `POST /workspaces/{slug}/work-items/{ref}/comments/`

**Scope:** `work_items:write` · **Needs:** `Idempotency-Key` · **Role:** any member of the project who can see the work item (guests may comment on work they can see)

| Field  | Type             | Required | Meaning                         |
| ------ | ---------------- | -------- | ------------------------------- |
| `text` | string, ≤ 10,000 | yes      | The comment, as **plain text**. |

**`201`**: `{"id": "…", "work_item": "WEB-1", "author": "Pat Person", "created_at": "…", "text": "…"}`. The comment is the person's own, with the same notification and activity as one written in Plane.

### `POST /workspaces/{slug}/work-items/{ref}/attachments/`

**Scope:** `work_items:write` · **Needs:** `Idempotency-Key` · **Role:** admin or member of the project

Send the file as `multipart/form-data` in a field named **`file`** — nothing else. Plane puts it **where the web app would**: in the workspace's Google Drive folder for the work item if Drive is set up for the workspace, otherwise in Plane's own file storage.

```bash
curl -sS -X POST "$PLANE/api/agent/v1/workspaces/acme/work-items/WEB-1/attachments/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Idempotency-Key: tg-884413-file" \
  -F "file=@screenshot.png;type=image/png"
```

```json
{
  "work_item": "WEB-1",
  "url": "https://plane.example.com/acme/browse/WEB-1/",
  "file": { "id": "…", "name": "screenshot.png", "type": "image/png", "size": 183402, "storage": "plane", "link": null }
}
```

`storage` is `plane` or `google_drive` (then `link` is the file's address in Drive). Rules:

- **Size**: at most the server's attachment limit (5 MB by default; the administrator can raise it). Over it is `413 file_too_large`, with the limit in bytes. A file just under the limit can still be refused earlier, by the server's overall request-size guard, because the multipart wrapping adds a little: that answer is `413` with `{"error": "REQUEST_BODY_TOO_LARGE", …}`, not in the usual shape. Treat any `413` as "too big".
- **Types**: the web app's allow-list (images, documents, audio, video, archives of common kinds). **SVG images are refused** — they can carry scripts.
- **Name**: any directory part (`../../x`) is removed; only the file name is kept.
- Telegram bots can download files up to 20 MB through the normal Bot API, so the server's limit is the one that bites.

---

## Time: timer and hours

If the workspace has the CRM integration switched on, a timer or hours written through the API are mirrored to the CRM exactly like ones entered in the web app; there is no separate path that skips it.

### `POST /me/timer/start/`

**Scope:** `time:write` · No key needed.

```json
{ "workspace": "acme", "work_item": "WEB-1" }
```

The rules are the web app's:

- only an **assignee** may start a timer on a work item (`403 not_assigned`);
- only while the work item is in a state where **time may be tracked** — a project and workspace setting (`409 state_not_allowed`);
- a person has **one timer at a time, across every workspace**: starting one **ends the one already running**, wherever it is. The answer says so in `stopped_previous`, so the bot can tell the person;
- starting a timer that is **already running on that same work item** changes nothing and answers `200` with `already_running: true`.

**`201`**:

```json
{
  "started": true,
  "already_running": false,
  "stopped_previous": {
    "started_at": "2026-03-04T08:05:00+00:00",
    "elapsed_minutes": 50,
    "work_item": { "ref": "WEB-1", "…": "…" }
  },
  "timer": {
    "started_at": "2026-03-04T09:00:00+00:00",
    "elapsed_minutes": 0,
    "note": "",
    "work_item": { "ref": "WEB-2", "…": "…" }
  }
}
```

`work_item` inside `timer` is only filled in if the connection also has `work_items:read`.

### `POST /me/timer/stop/`

**Scope:** `time:write` · No key needed.

Stops the person's running timer, wherever it is. Optional body: `{"note": "header fix"}` — what the time was spent on (≤ 500 characters). With no timer running: `404 not_found`.

```json
{ "stopped": true, "minutes": 55, "started_at": "2026-03-04T08:05:00+00:00", "work_item": { "ref": "WEB-1", "…": "…" } }
```

### `POST /me/time-entries/`

**Scope:** `time:write` · **Needs:** `Idempotency-Key` · **Role:** admin or member of the project

Add hours the person worked on a work item, for today or a recent day.

| Field       | Type           | Required | Meaning                                                                                                       |
| ----------- | -------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `workspace` | string         | yes      | The workspace slug.                                                                                           |
| `work_item` | string         | yes      | Short reference or id.                                                                                        |
| `minutes`   | integer 1–1440 | yes      | A whole number. Not a string, not a fraction.                                                                 |
| `date`      | `YYYY-MM-DD`   | no       | The day, **in the person's own time zone**. Default: today. Not in the future, and no more than 31 days back. |
| `note`      | string, ≤ 500  | no       | What it was.                                                                                                  |

**`201`**: `{"id": "…", "date": "2026-03-04", "minutes": 90, "note": "", "work_item": {…}}` (`work_item` only with `work_items:read`).

These hours count in the person's month exactly like hours they enter by hand. **They are never added to a month that has been settled** (handed in, approved or closed): `409 month_settled`. Those figures have been read by somebody; a person has to reopen the month in Plane first. Time is money here — confirm with the person before adding it, and never add hours the person did not state.

---

[← Connecting a person](02-connecting-a-person.md) · [Overview](README.md) · Next: [Security guide →](04-security-guide.md)
