# 5. Operations guide

[← Security guide](04-security-guide.md) · [Overview](README.md) · Next: [Telegram bot recipe →](06-telegram-recipe.md)

For whoever runs the Plane server. Everything here is done on the server, with the API container's shell; none of it is exposed to the web.

- [Deploying](#deploying)
- [Registering an app](#registering-an-app)
- [Managing apps](#managing-apps)
- [Settings](#settings)
- [Ending connections](#ending-connections)
- [The audit log](#the-audit-log)
- [Retention and clean-up](#retention-and-clean-up)
- [Behind a proxy](#behind-a-proxy)
- [Troubleshooting](#troubleshooting)

---

## Deploying

The feature adds one Django app (`agent`) with six tables, a daily clean-up task and new routes under `/api/agent/`. To deploy:

1. **Build and roll out** the API image as usual.
2. **Apply the migration:** `python manage.py migrate` (creates `agent.0001_initial` and `agent.0002_idempotency_keys`; nothing existing is altered).
3. **Restart the Celery worker and beat** so they pick up the new clean-up task (`plane.agent.tasks.purge_expired_agent_records`, daily at 04:30 UTC).
4. **Check `WEB_URL`** is set to the address people open Plane at (for example `https://plane.example.com`). It is used to build the link people are sent; without it the link request fails with `server_error`.
5. **Deploy the web app** (it contains the approval screen and _Connected apps_).

Nothing is switched on for anyone until you register an app. With none registered, the endpoints exist but every call is refused.

## Registering an app

Inside the API container:

```bash
python manage.py agent_client create \
    --name "Check-in bot" \
    --description "Daily check-ins over Telegram" \
    --redirect-uri https://bot.example.com/plane/callback \
    --scope profile --scope time:read --scope work_items:read
```

Output:

```
Registered Check-in bot.
  client_id:     plane_client_Ab3…
  client_secret: plane_cs_9xK…
The secret is shown only now. Store it in the app's secret store.
```

- **The secret is shown once.** Only its SHA-256 hash is stored; there is no way to read it back. Hand it to the app's developer through your secret-sharing channel, not by email or chat.
- `--redirect-uri` (repeatable) is the **exact** address people are sent back to. Matching is character-for-character: no wildcards, no prefix matching, no query-string flexibility. Use `https`; plain `http` is accepted only for `localhost`, `127.0.0.1` and `::1`, for development. No fragments, no credentials in the address.
- `--scope` (repeatable) is the **ceiling**: the most this app may ever ask for. Omit it and the app is allowed only the **read-only** scopes (`profile`, `time:read`, `leave:read`, `work_items:read`): the scopes that change things (`work_items:write`, `time:write`) are never a default and must be named on purpose. Give an app only what its purpose needs. If the app asks for less, that is fine; if it asks for more, the request is refused.

To let an app act for people (create work items, comment, attach files, start timers, add hours) name the write scopes as well:

```bash
python manage.py agent_client update plane_client_Ab3… \
    --set-scopes profile time:read work_items:read work_items:write time:write
```

This only raises the **ceiling**. A person still has to approve each write scope on the approval screen, and connections that already exist keep what they were given: the person connects again to grant more. Grant write scopes only to an app whose developers have read the [Security guide](04-security-guide.md#4a-acting-on-a-persons-behalf).

Register **separate apps for development and production.**

## Managing apps

```bash
python manage.py agent_client list
```

Shows each app, whether it is active, how many live connections it has, its redirect addresses and scopes.

| Task                             | Command                                                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Add or remove a redirect address | `agent_client update <client_id> --add-redirect-uri <uri> [--remove-redirect-uri <uri>]`                                             |
| Change the ceiling of scopes     | `agent_client update <client_id> --set-scopes profile time:read` (does not change existing connections, which keep what was granted) |
| Switch an app off                | `agent_client deactivate <client_id>`                                                                                                |
| Switch it back on                | `agent_client activate <client_id>`                                                                                                  |
| Replace the secret               | `agent_client rotate-secret <client_id>`                                                                                             |

### Rotating the secret

`rotate-secret` prints a new secret and **invalidates the old one immediately**. Existing connections are unaffected — tokens do not depend on the secret — but the app cannot refresh until it is given the new one, so coordinate the change: give the developer the new secret, deploy it, then (if needed) re-run the command only once. Rotate at once if the secret may have leaked.

### Switching an app off

`deactivate` makes every token of that app fail on its next call and refuses its link requests and refreshes. Connections are not deleted; `activate` brings them back. Use it as the emergency stop.

## Settings

Environment variables for the API (all optional; the defaults are deliberate):

| Variable                              | Default          | Meaning                                                                                                                                                       |
| ------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WEB_URL`                             | — (**required**) | Public address of the web app; the base of the link people are sent.                                                                                          |
| `AGENT_REQUEST_LIFETIME_SECONDS`      | `600`            | How long the link given to a person stays valid.                                                                                                              |
| `AGENT_CODE_LIFETIME_SECONDS`         | `60`             | How long the code from an approval can be exchanged.                                                                                                          |
| `AGENT_ACCESS_TOKEN_LIFETIME_SECONDS` | `3600`           | Access token lifetime.                                                                                                                                        |
| `AGENT_REFRESH_TOKEN_LIFETIME_DAYS`   | `90`             | Refresh token lifetime (replaced on every use).                                                                                                               |
| `AGENT_GRANT_MAX_AGE_DAYS`            | `365`            | A connection ends this long after it was made, however active. `0` removes the limit.                                                                         |
| `AGENT_REFRESH_REUSE_LEEWAY_SECONDS`  | `10`             | A spent refresh token presented again within this window is treated as a retry; later, as theft.                                                              |
| `AGENT_AUDIT_RETENTION_DAYS`          | `180`            | How long audit lines are kept.                                                                                                                                |
| `AGENT_GRANT_RATE_LIMIT`              | `120/minute`     | Per connection (one person). DRF rate syntax.                                                                                                                 |
| `AGENT_CLIENT_RATE_LIMIT`             | `1200/minute`    | Per app, across everyone.                                                                                                                                     |
| `AGENT_WRITE_RATE_LIMIT`              | `30/minute`      | Writes (`POST`, `PATCH`) per connection.                                                                                                                      |
| `AGENT_IDEMPOTENCY_RETENTION_HOURS`   | `24`             | How long a repeated write with the same `Idempotency-Key` is answered with the first answer.                                                                  |
| `AGENT_MAX_BACKDATE_DAYS`             | `31`             | How far back an app may add hours (never the future, never a settled month).                                                                                  |
| `AGENT_OAUTH_RATE_LIMIT`              | `60/minute`      | The OAuth endpoints, per source address.                                                                                                                      |
| `NUM_PROXIES`                         | unset            | Number of reverse proxies in front of Plane. **Set it** so rate limits and the audit log see the real client address — see [Behind a proxy](#behind-a-proxy). |

Shortening a lifetime applies to tokens issued afterwards.

## Ending connections

| Who                      | How                                                                 | Effect                                                                 |
| ------------------------ | ------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| The person               | _Profile → Connected apps → Revoke_                                 | Their connection ends at once. Their other connections are unaffected. |
| The app                  | `POST /api/agent/v1/oauth/revoke/`                                  | Ends the connection of that token.                                     |
| You — one person         | `agent_client revoke-grants <client_id> --email person@example.com` | Ends that person's connections to that app.                            |
| You — everyone on an app | `agent_client revoke-grants <client_id>`                            | Ends every connection of that app.                                     |
| You — an app             | `agent_client deactivate <client_id>`                               | App-wide stop; connections are kept but unusable.                      |
| Automatically            | Person deactivated; token replayed; code used twice; limit reached  | Calls fail; replay and double use end the connection permanently.      |

In every case, **the next call with a token of that connection fails** (`401 invalid_token`); nothing needs to expire first. When a person leaves the company, deactivating their Plane account is enough to cut every connection.

If you restore the database from an old backup, connections that had been revoked after the backup was taken come back to life. After a restore, end all connections (`revoke-grants` for each app) and let people reconnect.

## The audit log

Table `agent_audit_logs`. One row per event, **without content**: no query strings, request bodies or responses.

| Column                             | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `created_at`                       | When.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `event`                            | `request` (a link was registered), `approved`, `denied`, `linked` (code exchanged), `refreshed`, `refresh_retry` (an exact retry inside the leeway), `reuse_detected` (a spent refresh token replayed — connection ended), `revoked` (with `detail.reason`: `user`, `client`, `admin`, `code_reuse`, `token_reuse`, `superseded` — the same person linked the same chat account again), `api` (a call), `write` (a change; `detail.action` is e.g. `work_item.create`, `work_item.update`, `comment.create`, `attachment.create`, `timer.start`, `timer.stop`, `time_entry.create`, and the ids it touched — never content). |
| `client_id`, `grant_id`, `user_id` | Whom it concerned.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `method`, `path`, `status_code`    | For `api` events.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `ip_address`, `user_agent`         | The caller's.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `detail`                           | Small JSON; never personal content.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

Examples:

```sql
-- What did one person's connections do in the last day?
SELECT created_at, event, method, path, status_code
FROM agent_audit_logs
WHERE user_id = '<user uuid>' AND created_at > now() - interval '1 day'
ORDER BY created_at DESC;

-- Any replayed tokens (stolen or buggy clients)?
SELECT created_at, client_id, grant_id, ip_address FROM agent_audit_logs
WHERE event = 'reuse_detected' ORDER BY created_at DESC;

-- Which connections have not been used for 60 days?
SELECT g.id, u.email, c.name, g.last_used_at
FROM agent_grants g JOIN users u ON u.id = g.user_id JOIN agent_clients c ON c.id = g.client_id
WHERE g.revoked_at IS NULL AND (g.last_used_at IS NULL OR g.last_used_at < now() - interval '60 days');
```

`last_used_at` on a connection is updated at most every five minutes. Failed authentications (unknown token, no header) are **not** logged, so that a flood of bad calls cannot become a flood of rows; they show up in the web server's access log.

## Retention and clean-up

A daily task (04:30 UTC) deletes sign-in requests and tokens that expired more than seven days ago, expired idempotency keys, and audit lines older than `AGENT_AUDIT_RETENTION_DAYS`. **Connections are never deleted** — a revoked connection stays with `revoked_at` and `revoked_reason`, because "who had access and when it ended" is the question an audit asks.

The audit log contains caller IP addresses and user agents. Set the retention to what your data-protection policy allows.

**One table does hold content, briefly.** To answer a repeated request with the first answer, `agent_idempotency_keys` stores the response body of each successful change for `AGENT_IDEMPOTENCY_RETENTION_HOURS` (24 by default). That body can contain a work item's description or a comment's text. It is deleted when the key expires (the daily task also removes expired ones), and it is the only place a connected app's content is kept outside the work item itself. Shorten the window if that matters to your policy; do not go below the longest time an app might retry.

**CRM.** Timers and hours an app writes are mirrored to the CRM (when that integration is on) by the same signals as ones from the web app. A bad write by a bot is therefore also a bad write in the CRM; that is one more reason to keep the write scopes to apps whose developers have read the security guide.

## Behind a proxy

- **Trailing slashes.** Every route ends in `/`. Do not configure the proxy to strip them.
- **The `Authorization` header** must reach Plane unchanged. Standard nginx/Caddy/Traefik/ALB set-ups do this; some API gateways do not.
- **`X-Forwarded-For` and `NUM_PROXIES`.** Rate limiting of the OAuth endpoints, and the audit log, use the caller's address. `X-Forwarded-For` is partly written by the caller, so Plane believes only the entry your own proxy added, counted from the end: that is what `NUM_PROXIES` (the number of reverse proxies in front of Plane) tells it. **If `NUM_PROXIES` is not set, Plane ignores the header and uses the address of the connection itself** — which behind a proxy is the proxy. Everybody then shares one allowance (a noisy client can exhaust the OAuth limit for all), and the audit log records the proxy's address. Set `NUM_PROXIES`.
- **Do not log request bodies** at the proxy for `/api/agent/v1/oauth/…`: they carry the client secret and tokens. The OAuth endpoints accept credentials in headers or body, never in the address, precisely so that ordinary access logs do not capture them.
- The link people are sent contains a one-time, ten-minute identifier in its path; it appears in access logs. It is single-use and short-lived, so it is of no use after the person acts.

## Troubleshooting

| Symptom                                                                          | Likely cause                                                                                                                                      | Fix                                                                                                   |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Link request returns `500 server_error`                                          | `WEB_URL` not set in the API environment.                                                                                                         | Set it and restart the API.                                                                           |
| Link request returns `401 invalid_client`                                        | Wrong secret (it may have been rotated), wrong client id, or the app is switched off.                                                             | `agent_client list`; rotate the secret if lost; `activate`.                                           |
| Link request returns `400` "redirect_uri is not one of the addresses registered" | Not a character-for-character match (trailing slash, `http` vs `https`, port, case of the host).                                                  | `agent_client update … --add-redirect-uri`.                                                           |
| `invalid_scope`                                                                  | The app asked for a scope outside its registration.                                                                                               | `agent_client update … --set-scopes …`.                                                               |
| The person opens the link and Plane says it expired                              | Older than 10 minutes, already approved/cancelled, or the app was switched off.                                                                   | The app requests a new link.                                                                          |
| `invalid_grant` on the code exchange                                             | More than 60 seconds passed; the verifier or `redirect_uri` differs from the request; the code was already used (this also ends the connection).  | Start the link flow again.                                                                            |
| Everything works, then `invalid_grant` on refresh for one person                 | Revoked by them or by you; the 365-day limit passed; their account was deactivated; a token was replayed (see `reuse_detected` in the audit log). | The person connects again. If replays recur, look for an app that refreshes from two workers at once. |
| `429` on the OAuth endpoints for no apparent reason                              | Proxy hides client addresses (`NUM_PROXIES` not set).                                                                                             | Set `NUM_PROXIES`.                                                                                    |
| `403 insufficient_scope`                                                         | The connection was made without that scope.                                                                                                       | The person connects again with it.                                                                    |
| A person says "my bot stopped"                                                   | Check _Connected apps_ for that person; check the audit log for `revoked`/`reuse_detected`.                                                       | —                                                                                                     |

---

[← Security guide](04-security-guide.md) · [Overview](README.md) · Next: [Telegram bot recipe →](06-telegram-recipe.md)
