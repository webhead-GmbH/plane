# 7. Events

[← Telegram bot recipe](06-telegram-recipe.md) · [Overview](README.md)

Events let Plane tell your app that something happened, so it does not have to keep asking. "Ana was given WEB-12" arrives as one signed request to an address you provide, a moment after it happens.

- [What an event is (and is not)](#what-an-event-is-and-is-not)
- [Setting it up](#setting-it-up)
- [What you receive](#what-you-receive)
- [Verifying the signature](#verifying-the-signature)
- [Answering, retries and duplicates](#answering-retries-and-duplicates)
- [The events](#the-events)
- [Missing events: reconcile](#missing-events-reconcile)
- [A checklist](#a-checklist)

---

## What an event is (and is not)

An event is a **hint**, not a record. It says _that_ something happened to a work item of one connected person, by id, and nothing more: no title, no description, no names, no dates. To learn what changed you ask for the work item with that person's own token (`GET /workspaces/{slug}/work-items/{id}/`, using the id from the event), and Plane decides again, at that moment, what they may see.

That has three consequences you can rely on:

- An event can never carry anything its person could not read, and one that arrives late cannot reveal what the person has since lost sight of: the fetch answers `404`.
- A leaked signing secret reveals that somebody was assigned something, not what.
- Events are **at least once**. A delivery that is not accepted is retried for about half an hour and then given up on, so an event can be late, can arrive twice, and after an outage can be missing. [Reconcile](#missing-events-reconcile) when it matters.

Events are about **the person who connected your app**, never about colleagues. A manager's app does not hear about their team's work this way.

## Setting it up

**An administrator** gives your app an address and a secret (you cannot set either yourself):

```bash
python manage.py agent_client webhook plane_client_Ab3… --url https://bot.example.com/plane/events
```

```
  address:   https://bot.example.com/plane/events (on)
  failures:  0 in a row
  secret:    plane_whsec_9b1f…
```

Give the secret to the developer through a secret-sharing channel; it is not stored in Plane's database (it is derived), and `--show-secret` prints it again. `--new-secret` replaces it at once. `--off` stops events.

The address must be:

- **HTTPS**, with a certificate that verifies. (Plain `http://` is accepted only for a host the operator has listed in `WEBHOOK_ALLOWED_HOSTS`, for a bot on the same private network.)
- **Reachable from the Plane server.** An address that resolves to an internal or private network is refused unless the operator has allowed it (`WEBHOOK_ALLOWED_IPS` / `WEBHOOK_ALLOWED_HOSTS`, the settings Plane's own webhooks use). The check is made when the address is set and again on every delivery, and the connection goes to the address that was checked.
- **Free of credentials and fragments.** Put secrets in the signature, not in the URL.

Plane does **not follow redirects**: a `3xx` is a failed delivery. Give the final address.

Which events a connection receives depends on what the person approved: the `work_item.*` events need the **`work_items:read`** scope (the person has already agreed that your app may see their work items); `connection.revoked` is always sent. There is no scope for events themselves.

## What you receive

A `POST` with a JSON body and these headers:

| Header                    | Value                                                                                         |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| `Content-Type`            | `application/json`                                                                            |
| `User-Agent`              | `Plane-Agent-Events/1`                                                                        |
| `X-Plane-Agent-Event`     | The event type, for example `work_item.assigned`.                                             |
| `X-Plane-Agent-Delivery`  | The event's id. **The same on every retry**: use it to drop repeats.                          |
| `X-Plane-Agent-Timestamp` | Unix time in seconds when **this attempt** was sent. A retry has a fresh one.                 |
| `X-Plane-Agent-Signature` | `v1=` followed by a hex HMAC-SHA256. See [Verifying the signature](#verifying-the-signature). |

```json
{
  "connection": { "account": { "id": "424242", "provider": "telegram" }, "id": "1d20cd10-5209-4a05-ace0-62ca76ddf447" },
  "created_at": "2026-03-04T08:05:00.123456+00:00",
  "data": {
    "work_item": { "id": "6a9c…", "project_id": "3f2e…", "ref": "WEB-12" },
    "workspace": "acme"
  },
  "id": "0c1f7a52-8e54-4d0a-9d1c-5f1f3b1e0a77",
  "type": "work_item.assigned"
}
```

- `id` is the event's id, and is also in `X-Plane-Agent-Delivery`.
- **Fetch by `work_item.id`**, not by `ref`. The `ref` (`WEB-12`) is for showing to people: an administrator can change a project's identifier, and an event that waited for a retry would then carry a reference that no longer exists. The id never changes.
- `connection.account` is the chat account **you** gave when you asked for the link (`account_provider`, `account_id`): that is how you find the person to tell. `connection.id` identifies the connection.
- `data` depends on the type, see [The events](#the-events).
- Keys are in alphabetical order and the body has no extra spaces. **Do not rely on that**: verify the signature against the bytes you received, not against JSON you serialise again.
- New fields may appear in `v1`; ignore the ones you do not know.

## Verifying the signature

Anyone who learns your address can send you a request that looks like an event. The signature is how you know it came from Plane. **Verify it before you do anything else with the request.**

1. Read the **raw body bytes** exactly as received (before any JSON parsing; a framework that parses first usually hands you something you cannot re-create byte for byte).
2. Take `X-Plane-Agent-Timestamp`. If it differs from your clock by more than **five minutes**, refuse the request. That stops somebody replaying a request they once captured.
3. Compute `HMAC-SHA256(secret, timestamp + "." + body)` and write it as lowercase hex, prefixed with `v1=`. `secret` is the whole string you were given, `plane_whsec_…` included, as text.
4. Compare it with `X-Plane-Agent-Signature` **in constant time**. A plain `==` leaks, a byte at a time, how much of a guess was right.

```python
import hashlib
import hmac
import time

TOLERANCE_SECONDS = 300

def is_from_plane(secret: str, headers, body: bytes) -> bool:
    timestamp = headers.get("X-Plane-Agent-Timestamp", "")
    received = headers.get("X-Plane-Agent-Signature", "")
    try:
        if abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("v1=" + mac, received)
```

```js
const crypto = require("node:crypto");

function isFromPlane(secret, headers, rawBody /* Buffer */) {
  const timestamp = headers["x-plane-agent-timestamp"] || "";
  const received = headers["x-plane-agent-signature"] || "";
  if (!/^\d+$/.test(timestamp) || Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const mac = crypto
    .createHmac("sha256", secret)
    .update(Buffer.concat([Buffer.from(timestamp + "."), rawBody]))
    .digest("hex");
  const expected = Buffer.from("v1=" + mac);
  const actual = Buffer.from(received);
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}
```

A request that fails verification gets `401` (or is simply dropped) and is **not** acted on. When the administrator changes the secret (`--new-secret`) deliveries signed with the old one stop verifying at once: have the new secret ready first, or accept both for a few minutes.

## Answering, retries and duplicates

- **Answer `2xx` quickly** (Plane waits ten seconds), and do the work afterwards: put the event on a queue and return. A slow handler is a failed delivery.
- Any other answer, a timeout or a connection error is a failure. Plane tries again after **30 seconds, 2 minutes and then three times at 10 minutes**, six attempts in all (about half an hour), and then gives up on that event. Each attempt is signed afresh.
- Plane **never reads your answer's body**. Do not use it to say anything.
- **Expect duplicates.** Keep the ids of events you have handled (for a day is plenty) and ignore a repeat. A retry carries the same `id`; a second change to the same work item is a new event with a new id.
- **If your address keeps failing**, Plane stops using it: after **10 events in a row** could not be delivered at all, events are switched off for your app until the administrator sets the address again (`agent_client webhook … --url`). Your app is then back to polling, which still works. One accepted delivery resets the count.
- Events for a person who is not connected any more are not sent.

## The events

### `work_item.assigned` and `work_item.unassigned`

The person was put on a work item, or taken off it, **by somebody else**. (What they do themselves, through your own app or in Plane, is not news to them and is not sent.)

`data`: `{ "workspace": "acme", "work_item": { "id": "…", "ref": "WEB-12", "project_id": "…" } }`

Next: fetch the work item (by `work_item.id`) and tell the person. For `unassigned` the person may still see the item; if not, the fetch is `404` and there is nothing to show.

### `work_item.due_date_changed` and `work_item.state_changed`

The due date, or the state, of a work item the person is **assigned to** was changed by somebody else. The event does not say to what: fetch the item (`target_date`, `state`).

`data`: as above. One event per work item and kind for each change Plane records at once; two edits a minute apart are two events.

### `connection.revoked`

The person's connection to your app has ended and **you did not end it**. Delete their tokens and stored data, and say so in the chat if you can.

`data`: `{ "reason": "user" }` where the reason is:

| `reason`   | Meaning                                                                                                                                                          |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user`     | The person disconnected your app in _Profile → Connected apps_.                                                                                                  |
| `admin`    | An administrator ended it.                                                                                                                                       |
| `security` | A token was replayed (a copy was used after the real one): Plane ended the connection to protect the person. Tell them, and do not reconnect them automatically. |

It is **not** sent when you ended the connection yourself (`/oauth/revoke/`), or when the person linked the same chat account again, which replaces the old connection. It is sent even though the connection is over: that it ended is the news. Connections that end because they reached their age limit or because the person's account was deactivated are not announced; you find out when a refresh fails with `invalid_grant`.

## Missing events: reconcile

Because events can be late or lost, treat them as a reason to look, not as the data:

- **On start-up and every few hours**, list what changed since you last looked: `GET /work-items/?assignee=me&updated_since=<time>` for each connected person, and compare with what you have told them.
- **When an event arrives**, fetch the item and decide from the _item_, not from the event type: "assigned" for something that is already finished, or already handed back, is not worth a message.
- Keep your own record of what you have told each person (by work item id and what you said), so a reconcile does not repeat it.

## A checklist

- [ ] The secret is in a secret store, not in the repository.
- [ ] The signature is verified, over the raw body, in constant time, **before** parsing or acting.
- [ ] The timestamp is checked (five minutes).
- [ ] The handler answers `2xx` in a second or two and works afterwards.
- [ ] Repeats are dropped by event id.
- [ ] Nothing is trusted from the event but the ids; the details are fetched with the person's token.
- [ ] `connection.revoked` deletes the person's tokens.
- [ ] A reconcile runs on start-up and periodically.

---

[← Telegram bot recipe](06-telegram-recipe.md) · [Overview](README.md)
