# 2. Connecting a person

[← Concepts](01-concepts.md) · [Overview](README.md) · Next: [API reference →](03-api-reference.md)

This is the complete linking flow. It follows **OAuth 2.0** (RFC 6749) with three standard hardening extensions, so a client library written for OAuth works against it unchanged:

- **Pushed authorization requests** (RFC 9126) — your server registers the request first; the person only carries an opaque link.
- **PKCE** (RFC 7636, `S256` only) — a code is useless without the verifier only your server holds.
- **Refresh token rotation with replay detection** (OAuth 2.0 Security Best Current Practice).

There is no login screen in this flow. The person is already signed in to Plane in their browser; that is the only place they ever type anything.

All endpoints below are under `…/api/agent/v1/oauth/` and **must be called with the trailing slash**.

## The flow

```mermaid
sequenceDiagram
    autonumber
    participant P as Person
    participant B as Your server
    participant X as Plane

    Note over B: make state, verifier, challenge
    B->>X: POST /oauth/requests/
    X-->>B: 201 authorization_url
    B->>P: send the link
    P->>X: GET link (web app) — shows who is asking and for what
    P->>X: Allow (POST /api/agent/connect/…/approve/)
    X-->>P: redirect → redirect_uri?code=…&state=…
    P->>B: GET redirect_uri?code=…&state=…
    Note over B: check state; find the pending link it belongs to
    B->>X: POST /oauth/token/ (grant_type=authorization_code)
    X-->>B: 200 access_token + refresh_token
```

## Step 1 — Register the request

`POST /api/agent/v1/oauth/requests/`

**Authentication:** your client id and secret, as HTTP Basic (`-u "$CLIENT_ID:$CLIENT_SECRET"`) — recommended — or as `client_id` and `client_secret` body fields. Never in the address.

**Body:** JSON or form-encoded.

| Field                   | Required | Meaning                                                                                                                                                                                    |
| ----------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `redirect_uri`          | yes      | Where to send the person after they decide. **Must match, character for character, one of the addresses registered for your app.** No prefix or pattern matching.                          |
| `scope`                 | yes      | Space-separated scopes, e.g. `profile time:read`. Each must be known and within what your app was registered for.                                                                          |
| `state`                 | yes      | Any string up to 512 characters that **you** generate and keep. It comes back unchanged on the redirect; it is how you know which pending link a callback belongs to. Make it unguessable. |
| `code_challenge`        | yes      | `BASE64URL(SHA256(verifier))` without padding: exactly 43 characters.                                                                                                                      |
| `code_challenge_method` | yes      | Must be `S256`. `plain` is refused.                                                                                                                                                        |
| `account_provider`      | yes      | Which kind of chat account is being linked: lower-case letters, digits, `-` or `_`, up to 32. E.g. `telegram`.                                                                             |
| `account_id`            | yes      | The chat account's **stable numeric id** (up to 64 characters). For Telegram, the user id — not the username, which can change hands.                                                      |
| `account_username`      | no       | The handle, for display (up to 64).                                                                                                                                                        |
| `account_name`          | no       | The display name, for display (up to 120).                                                                                                                                                 |

The `account_*` fields are shown to the person on the approval screen and later in _Connected apps_, so they can tell what they are linking and notice a link they did not start. Plane strips control characters and invisible or direction-overriding characters from them (so a handle cannot be made to read backwards); letters of every script, including the zero-width joiner Persian spelling needs, are kept. **They are not verified by Plane** — they are your statement. See [Link phishing](#link-phishing-and-how-to-prevent-it).

**Make the verifier and challenge:**

```python
import base64, hashlib, secrets

verifier = secrets.token_urlsafe(48)            # 43–128 chars of A–Z a–z 0–9 - . _ ~
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode("ascii")).digest()
).rstrip(b"=").decode("ascii")
```

```js
import { randomBytes, createHash } from "node:crypto";

const verifier = randomBytes(48).toString("base64url");
const challenge = createHash("sha256").update(verifier).digest("base64url");
```

**Response `201`:**

```json
{
  "authorization_url": "https://plane.example.com/connect/agent/plane_ar_8f3…",
  "expires_in": 600
}
```

Store, against `state`: the verifier, the chat account, the time, and (if you use one) the chat to reply in. Then give the person `authorization_url`.

## Step 2 — Give the person the link

Send it in the chat. In Telegram an inline-keyboard **URL button** is best (the person sees only your label, and the link is not pasted into the chat history as text).

Do not shorten it, do not open it for them, do not follow it from your server: it must be opened in **their** browser, where they are signed in to Plane. If they are not signed in, Plane asks them to sign in first and is built to bring them back to the same screen afterwards. If it does not, they simply open the link again; it stays valid for ten minutes.

What the person sees:

- the app's name,
- the chat account being linked (provider, handle, name, id),
- the **Plane account** they will be linking it to (their name and email),
- the exact list of access they are granting, in plain words,
- a warning to continue only if they started this themselves from the app and the chat account shown is theirs.

The page refuses to work inside a frame (clickjacking protection) and sends no referrer.

## Step 3 — The callback

When the person presses **Allow**, their browser goes to your `redirect_uri` with two extra query parameters:

```
https://bot.example.com/plane/callback?code=plane_ac_…&state=<your state>
```

If they press **Cancel**:

```
https://bot.example.com/plane/callback?error=access_denied&state=<your state>
```

If the link expired or was already used, the person sees an error in Plane and **your callback is not called** — time out your pending links yourself (a few minutes past `expires_in`).

On callback:

1. Look up `state` among your pending links. **No match, or already used → reject.** This is your protection against someone feeding your callback a code of their choosing.
2. If `error` is present, tell the person and drop the pending link.
3. Exchange the `code` immediately (step 4). The code lives 60 seconds.
4. Do not log the full callback URL — it contains the code.

> **Callback page content.** The callback is opened in the person's browser; show them something friendly ("Connected — you can go back to Telegram") and, for chat apps, hand off as described in [the next section](#link-phishing-and-how-to-prevent-it).

## Step 4 — Exchange the code

`POST /api/agent/v1/oauth/token/` — form-encoded (JSON is also accepted).

| Field              | Meaning                                              |
| ------------------ | ---------------------------------------------------- |
| `grant_type`       | `authorization_code`                                 |
| `code`             | From the callback.                                   |
| `redirect_uri`     | The same value you registered the request with.      |
| `code_verifier`    | The verifier whose challenge you registered.         |
| client credentials | HTTP Basic, or `client_id` + `client_secret` fields. |

**Response `200`** (`Cache-Control: no-store`):

```json
{
  "access_token": "plane_at_…",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "plane_rt_…",
  "scope": "profile time:read work_items:read"
}
```

Check `scope`: it is what was actually granted. Store both tokens **encrypted**, against the person.

Then identify the person: `GET /api/agent/v1/me/` returns their Plane `id`, name and workspaces, and the chat account the connection is for. That `id` is how your own database knows which employee this chat is.

**Linking again replaces.** If the same person links the same chat account (same `account_provider` and `account_id`) to your app again, the earlier connection is ended and its tokens stop working — so "reconnect" never leaves an old, unused refresh token alive. A different chat account, or a different person, is a separate connection.

**The code is spent even if you fail.** A wrong verifier or `redirect_uri` burns the code; using a code a second time **ends the connection it created**. If anything goes wrong, start again from step 1.

## Calling the API

```
GET /api/agent/v1/me/day/ HTTP/1.1
Host: plane.example.com
Authorization: Bearer plane_at_…
```

Details, parameters and responses are in the [API reference](03-api-reference.md). Tokens go **only** in the `Authorization` header. A token in the address is ignored (and would be written to logs on its way).

## Refreshing

`POST /api/agent/v1/oauth/token/`

| Field              | Meaning                    |
| ------------------ | -------------------------- |
| `grant_type`       | `refresh_token`            |
| `refresh_token`    | The current refresh token. |
| client credentials | As above.                  |

The response has the same shape as in step 4, with **a new access token and a new refresh token**.

Rules you must design for:

1. **A refresh token works once.** After you use it, the old one is dead. Persist the new refresh token **before** you use the new access token.
2. **Refresh when needed, not on a timer for all users.** Refresh a person's token when you are about to call for them and the access token has less than a minute left, or when a call returns `401 invalid_token`.
3. **Do not refresh the same token from two workers at once.** Take a lock per person. The server forgives an exact retry within **10 seconds** of the first use (and hands out a fresh pair), so a lost response is survivable; anything later is treated as theft.
4. **Replay ends the connection.** If a spent refresh token is presented again after those 10 seconds, Plane assumes it was copied, **revokes the whole connection** (both holders are locked out) and logs it. You will see `invalid_grant`.
5. **On `invalid_grant`, stop and ask the person to connect again.** Do not retry in a loop. It means the connection was revoked, expired (365 days), replayed, or the person was deactivated.
6. Refresh tokens expire after 90 days of not being used; an app that calls at least every three months never reaches that.

## Ending a connection

- **The person** does it in Plane: _Profile → Connected apps → Revoke_. Takes effect on your next call, which will return `401 invalid_token`.
- **Your app** can do it: `POST /api/agent/v1/oauth/revoke/` with `token=<refresh token>` (client credentials as above). This ends the connection and every token under it. With an _access_ token, only that token is revoked. Unknown tokens are not an error (RFC 7009) — always `200`. Do this when the person says "disconnect" in the chat.
- **An administrator** can end one person's, or every connection of your app, or switch your app off ([how](05-operations.md#ending-connections)).

When any of these happens, delete the person's stored tokens.

## Link phishing, and how to prevent it

The consent screen shows the person _your claim_ about the chat account. An attacker could start a link from **their own** chat, then send the resulting link to a colleague hoping they press Allow without reading — attaching the **attacker's** chat to the **colleague's** Plane account.

Plane makes this hard to do by accident: the link names the chat account in large letters, shows which Plane account will be linked, and warns. Your app should close the gap properly. For chat apps, **bind the connection to whoever finishes the flow in the same chat that started it**:

1. When the person starts the flow in the chat, record their chat id with the pending link (`state`).
2. On callback, do not mark the connection active yet. Instead, send the browser to a deep link into the chat carrying a one-time **claim** value, e.g. Telegram `https://t.me/<your_bot>?start=<claim>`.
3. When the bot receives `/start <claim>`, accept it **only if the chat id that sent it equals the chat id that started the link**. Otherwise discard the connection (revoke the tokens) and tell the person.

An attacker who forwards their link gets a callback that deep-links into _the colleague's_ Telegram, where the bot sees a different chat id than the one that started the flow, and refuses. The [Telegram recipe](06-telegram-recipe.md) shows this end to end.

Also: always put the **stable numeric id** in `account_id`, never the username; the person can see and compare it.

## Errors

OAuth endpoints answer with the shape RFC 6749 §5.2 defines:

```json
{ "error": "invalid_grant", "error_description": "The code has expired or has already been used." }
```

| `error`                  | HTTP | When                                                                                                                                | What to do                                                                     |
| ------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `invalid_request`        | 400  | Missing or malformed field, an address that is not registered, `plain` challenge, unreadable body.                                  | Fix the request.                                                               |
| `invalid_scope`          | 400  | Unknown scope, or one your app was not registered for.                                                                              | Ask for less, or have the administrator widen the app.                         |
| `invalid_client`         | 401  | Wrong or missing client credentials, unknown or switched-off app. (Same answer whichever it is.)                                    | Check your credentials; contact the administrator if the app was switched off. |
| `invalid_grant`          | 400  | Code expired/used/wrong verifier/wrong redirect address; refresh token spent/expired/revoked; connection ended; person deactivated. | Start the link flow again. Never retry the same code or token.                 |
| `unsupported_grant_type` | 400  | `grant_type` is not `authorization_code` or `refresh_token`.                                                                        | Fix the request.                                                               |
| `rate_limited`           | 429  | More than 60 calls a minute to the OAuth endpoints from one address. `Retry-After` says when.                                       | Back off.                                                                      |
| `server_error`           | 500  | Plane does not know its own web address (`WEB_URL` unset).                                                                          | Tell the administrator.                                                        |

`401` responses to the OAuth endpoints carry `WWW-Authenticate: Basic`. Every response is `Cache-Control: no-store`.

---

[← Concepts](01-concepts.md) · [Overview](README.md) · Next: [API reference →](03-api-reference.md)
