# Examples

## `sandbox_bot.py`: try the API before the real bot exists

A small web page that behaves like the chat bot will: it links you to Plane, calls the API for you, asks before creating things, and receives Plane's events. It is a **test tool and a reading copy**, not something to deploy: tokens are kept in memory only, it speaks plain HTTP and it listens on this computer only. Only the Python standard library is used (Python 3.9 or newer), so a bot developer can read it from top to bottom: the OAuth link with PKCE, token refresh (serialised, because a refresh token works once), the `dry_run` then confirm flow with an `Idempotency-Key`, and the signature check from the [events guide](../07-events.md#verifying-the-signature).

### 1. Register the app (on the Plane server)

On the _Connected apps_ page of the admin app (**Add app**), or with the command:

```bash
python manage.py agent_client create \
    --name "Sandbox bot" \
    --redirect-uri http://localhost:8920/callback \
    --scope profile --scope time:read --scope leave:read --scope work_items:read \
    --scope work_items:write --scope time:write --scope team:read
```

Keep the `client_id` and `client_secret` it prints. Leave out `--scope work_items:write --scope time:write` to try the API read-only, and `--scope team:read` if you do not want it to see the team.

### 2. Optional: let Plane tell the sandbox about events

On the app's page (_Manage → Events_) set the address and use **Send a test message**, or with the command:

```bash
python manage.py agent_client webhook <client_id> --url http://host.docker.internal:8920/plane/events
```

It prints the signing secret. If Plane runs in Docker and the sandbox runs on your computer, the container reaches your computer as `host.docker.internal`, and Plane only sends plain `http://` to a host the operator has trusted: set `WEBHOOK_ALLOWED_HOSTS=host.docker.internal` in the API's environment and restart the API and the Celery worker. Check that it works with:

```bash
python manage.py agent_client webhook <client_id> --send-test
```

The sandbox shows a verified `webhook.test` in its event list.

### 3. Run it

```bash
python sandbox_bot.py --client-id plane_client_… --client-secret plane_cs_… \
    --webhook-secret plane_whsec_… --plane http://localhost:8000 --web http://localhost:3100
```

`--plane` is where the API answers. `--web` is where the Plane web app is served, for when the link Plane builds (from `WEB_URL`) points somewhere else, as it often does in development. The values can also come from `PLANE_CLIENT_ID`, `PLANE_CLIENT_SECRET`, `PLANE_WEBHOOK_SECRET`, `PLANE_API`, `PLANE_WEB` and `SANDBOX_PORT`.

It prints an address with a one-time key in it. **Open that address in the browser where you are signed in to Plane.** Press _Connect to Plane_, check the screen Plane shows you, press _Allow_, and you are back in the sandbox.

### What to try

- **Read:** the buttons call `/me/day/`, `/work-items/`, `/team/workload/` and so on and show the answer as it is. The box below them sends any request you type.
- **Ask first:** pick a project, name a task and press _Preview_. Plane answers what it would create (`dry_run`) and nothing exists yet. _Create it_ then makes it, with an `Idempotency-Key`, and the answer carries the link to the new work item.
- **Events:** change the due date, state or assignees of a work item assigned to you while signed in as **somebody else** (a private window works) and the event appears in the list within seconds. Things you change yourself are not announced to you.
- **A connection ending:** disconnect from _Profile → Connected apps_ in Plane, and a `connection.revoked` event arrives (if the app has an address for events).

### Safe by default

The page only answers to the address that carries the key (a cookie that other sites cannot send), checks the `Host` header against name-rebinding, and listens on `127.0.0.1`. `/plane/events` is the one open door, and it answers `2xx` only to a request whose signature verifies.
