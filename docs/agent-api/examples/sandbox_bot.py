# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A stand-in for a chat bot, to try the Plane Agent API before the real bot exists.

It does what the real bot will do, with a web page instead of a chat:

* links a person (OAuth with PKCE: you click "Connect", Plane asks you, you press Allow);
* keeps the access token fresh (the refresh token works once, so refreshing is serialised);
* calls any endpoint for that person and shows the answer, with a form for the one flow
  that matters most: preview a new work item with `dry_run`, then create it;
* listens for Plane's events at /plane/events, checks the signature exactly as the events
  guide says, and shows what arrived.

It is a **test tool and a reading copy**, not something to deploy: tokens live in memory only,
it speaks plain HTTP and it listens on this computer only. Nothing but the Python standard
library is used, so a bot developer can read it top to bottom.

Run it (from `docs/agent-api/examples`)::

    python sandbox_bot.py --client-id plane_client_... --client-secret plane_cs_... \\
        --webhook-secret plane_whsec_... --web http://localhost:3100

then open the address it prints. The same values can come from the environment
(PLANE_CLIENT_ID, PLANE_CLIENT_SECRET, PLANE_WEBHOOK_SECRET, PLANE_API, PLANE_WEB, SANDBOX_PORT).
"""

# Python imports
import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALL_SCOPES = "profile time:read leave:read work_items:read work_items:write time:write team:read"
TOLERANCE_SECONDS = 300


class Config:
    api = "http://localhost:8000/api/agent/v1"
    web = ""
    client_id = ""
    client_secret = ""
    webhook_secret = ""
    scope = ALL_SCOPES
    port = 8920
    key = secrets.token_urlsafe(24)  # what the cockpit's own cookie must carry


class State:
    """Everything the bot remembers. In memory: restart it and connect again."""

    lock = threading.RLock()
    refresh_lock = threading.Lock()
    pending = {}  # state -> code verifier of a link that was started
    tokens = None  # {"access", "refresh", "expires_at", "scope"}
    account = None
    events = []  # newest first
    seen = set()  # delivery ids already handled: a retry carries the same one


# --- Talking to Plane ---------------------------------------------------------


def basic():
    raw = f"{Config.client_id}:{Config.client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def request(method, url, *, headers=None, body=None, form=None):
    """One HTTP call. Returns (status, parsed body). Never raises for an HTTP error status."""
    data, headers = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except urllib.error.URLError as error:
        return 0, {"error": "unreachable", "error_description": str(error.reason)}
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def pkce_pair():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def start_link():
    """Ask Plane for a link for a person, and return where to send them."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    status, body = request(
        "POST",
        f"{Config.api}/oauth/requests/",
        headers=basic(),
        body={
            "redirect_uri": f"http://localhost:{Config.port}/callback",
            "scope": Config.scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "account_provider": "sandbox",
            "account_id": "browser",
            "account_name": "Sandbox bot",
        },
    )
    if status != 201:
        raise RuntimeError(f"Plane refused the link request ({status}): {body}")
    with State.lock:
        State.pending[state] = verifier
    url = body["authorization_url"]
    if Config.web:
        # In development the address Plane builds can differ from the one the web app is served on.
        parts = urllib.parse.urlsplit(url)
        web = urllib.parse.urlsplit(Config.web)
        url = urllib.parse.urlunsplit((web.scheme, web.netloc, parts.path, parts.query, ""))
    return url


def finish_link(code, state):
    with State.lock:
        verifier = State.pending.pop(state, None)
    if verifier is None:
        raise RuntimeError("Unknown or already used state: start again with Connect.")
    status, body = request(
        "POST",
        f"{Config.api}/oauth/token/",
        headers=basic(),
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"http://localhost:{Config.port}/callback",
            "code_verifier": verifier,
        },
    )
    if status != 200:
        raise RuntimeError(f"Plane refused the code ({status}): {body}")
    store(body)
    status, me = request("GET", f"{Config.api}/me/", headers=bearer())
    with State.lock:
        State.account = me if status == 200 else None


def store(body):
    with State.lock:
        State.tokens = {
            "access": body["access_token"],
            "refresh": body["refresh_token"],
            "expires_at": time.time() + int(body["expires_in"]),
            "scope": body.get("scope", ""),
        }


def ensure_token():
    """A fresh access token, refreshing first when it is about to end.

    The refresh token works once and is replaced by the answer, so two callers must never refresh
    at the same time: the second would present a spent token, which Plane treats as theft.
    """
    with State.refresh_lock:
        with State.lock:
            tokens = State.tokens
        if tokens is None:
            return None
        if tokens["expires_at"] - time.time() > 60:
            return tokens["access"]
        status, body = request(
            "POST",
            f"{Config.api}/oauth/token/",
            headers=basic(),
            form={"grant_type": "refresh_token", "refresh_token": tokens["refresh"]},
        )
        if status != 200:
            with State.lock:
                State.tokens = None  # invalid_grant: the connection is over, the person connects again
            return None
        store(body)  # the new refresh token is saved before the new access token is used
        return body["access_token"]


def bearer():
    token = ensure_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def call(method, path, body=None, *, idempotency_key=None, dry_run=False):
    if not path.startswith("/") or "://" in path or ".." in path:
        return 400, {"error": "invalid_request", "error_description": "Give a path such as /me/day/."}
    headers = bearer()
    if not headers:
        return 401, {"error": "not_connected", "error_description": "Connect first."}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if dry_run:
        path += ("&" if "?" in path else "?") + "dry_run=true"
    return request(method, Config.api + path, headers=headers, body=body)


def disconnect():
    with State.lock:
        tokens, State.tokens, State.account = State.tokens, None, None
    if tokens:
        request("POST", f"{Config.api}/oauth/revoke/", headers=basic(), form={"token": tokens["refresh"]})


# --- Plane's events -----------------------------------------------------------


def is_from_plane(secret: str, headers, body: bytes) -> bool:
    """The check the events guide describes: raw body, timestamp window, constant-time compare."""
    timestamp = headers.get("X-Plane-Agent-Timestamp", "")
    received = headers.get("X-Plane-Agent-Signature", "")
    try:
        if abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("v1=" + mac, received)


def receive_event(headers, body):
    """Returns the HTTP status to answer with."""
    verified = bool(Config.webhook_secret) and is_from_plane(Config.webhook_secret, headers, body)
    if not verified:
        remember({"verified": False, "type": headers.get("X-Plane-Agent-Event", "?"), "summary": "REFUSED: bad signature"})
        return 401
    delivery = headers.get("X-Plane-Agent-Delivery", "")
    with State.lock:
        if delivery in State.seen:
            return 200  # a retry of something already handled
        State.seen.add(delivery)
    try:
        event = json.loads(body)
    except ValueError:
        return 400
    data = event.get("data") or {}
    item = data.get("work_item") or {}
    summary = item.get("ref") or data.get("reason") or data.get("message") or ""
    remember({"verified": True, "type": event.get("type"), "summary": summary, "id": event.get("id"), "event": event})
    return 204  # answered at once; a real bot would queue the work and do it afterwards


def remember(entry):
    entry["at"] = time.strftime("%H:%M:%S")
    with State.lock:
        State.events.insert(0, entry)
        del State.events[200:]


# --- The cockpit --------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Plane Agent API sandbox</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light dark; --b: #8884; --muted: #888; --ok: #1a7f37; --bad: #c62828; }
  body { font: 14px/1.45 system-ui, sans-serif; margin: 0 auto; max-width: 980px; padding: 16px; }
  h1 { font-size: 18px; margin: 0 0 4px } h2 { font-size: 14px; margin: 20px 0 6px }
  .muted { color: var(--muted) } .ok { color: var(--ok) } .bad { color: var(--bad) }
  section { border: 1px solid var(--b); border-radius: 8px; padding: 12px; margin-top: 12px }
  button, select, input, textarea { font: inherit; padding: 5px 9px; border: 1px solid var(--b); border-radius: 6px; background: transparent; color: inherit }
  button { cursor: pointer } button.primary { background: #2563eb; border-color: #2563eb; color: #fff }
  button:disabled { opacity: .5; cursor: default }
  .row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0 }
  pre { background: #8881; border-radius: 6px; padding: 10px; overflow: auto; max-height: 360px; margin: 6px 0 0; white-space: pre-wrap; word-break: break-word }
  table { border-collapse: collapse; width: 100% } td, th { text-align: start; padding: 3px 8px; border-bottom: 1px solid var(--b); font-size: 13px }
  label { display: block; margin: 6px 0 2px; font-size: 12px; color: var(--muted) }
  input, textarea, select { width: 100%; box-sizing: border-box } .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr } }
</style></head><body>
<h1>Plane Agent API sandbox</h1>
<div class="muted">A stand-in for the chat bot. Not for production: tokens are kept in memory only.</div>

<section id="connection"><div id="status">…</div>
  <div class="row"><button class="primary" id="connect">Connect to Plane</button><button id="disconnect">Disconnect</button></div>
</section>

<section><h2 style="margin-top:0">Read</h2>
  <div class="row" id="presets"></div>
  <div class="row"><select id="method" style="width:90px"><option>GET</option><option>POST</option><option>PATCH</option></select>
    <input id="path" placeholder="/me/day/" style="flex:1"><button id="run" class="primary">Send</button></div>
  <textarea id="body" rows="3" placeholder='JSON body for POST and PATCH, for example {"name": "…"}'></textarea>
  <div class="row"><label style="margin:0"><input type="checkbox" id="dry" style="width:auto"> dry_run (preview a create or change, nothing is done)</label></div>
  <div id="result" class="muted">The answer appears here.</div><pre id="answer" hidden></pre>
</section>

<section><h2 style="margin-top:0">Create a work item, asking first</h2>
  <div class="muted">What the bot does: preview with <code>dry_run</code>, show it, and only create after you confirm.</div>
  <div class="grid"><div><label>Project</label><select id="project"></select></div>
  <div><label>Assign to</label><select id="assignee"><option value="">nobody</option></select></div></div>
  <label>Name</label><input id="name" value="Sandbox test task">
  <label>Description (plain text)</label><textarea id="description" rows="2">Created from the Plane Agent API sandbox.</textarea>
  <div class="row"><button id="preview">Preview</button><button id="create" class="primary" disabled>Create it</button></div>
  <pre id="createAnswer" hidden></pre>
</section>

<section><h2 style="margin-top:0">Events from Plane</h2>
  <div class="muted">Plane calls <code id="hook"></code>. A real change by somebody else shows up here within seconds.</div>
  <table><thead><tr><th>Time</th><th>Type</th><th>Signature</th><th>About</th></tr></thead><tbody id="events"></tbody></table>
</section>

<script>
const $ = (id) => document.getElementById(id);
let context = { workspace: null };
const PRESETS = [
  ["Me", "GET", "/me/"], ["Today", "GET", "/me/day/"], ["Next 7 days", "GET", "/me/days/"], ["Hours, last week", "GET", "/me/time/"],
  ["Timer", "GET", "/me/timer/"], ["Leave", "GET", "/me/leave/"], ["Projects", "GET", "/projects/"],
  ["My open work", "GET", "/work-items/?assignee=me&state_group=backlog,unstarted,started&order_by=target_date"],
  ["Team", "GET", "/team/"], ["Team workload", "GET", "/team/workload/?include=days"],
];
for (const [label, method, path] of PRESETS) {
  const b = document.createElement("button"); b.textContent = label;
  b.onclick = () => { $("method").value = method; $("path").value = path; send(); };
  $("presets").appendChild(b);
}
async function api(url, options) {
  const r = await fetch(url, Object.assign({ credentials: "same-origin", headers: { "Content-Type": "application/json" } }, options));
  return r.json();
}
function show(el, status, body) {
  el.hidden = false; el.textContent = (status ? "HTTP " + status + "\n" : "") + JSON.stringify(body, null, 2);
}
async function send() {
  const method = $("method").value, path = $("path").value.trim();
  let body = null;
  if ($("body").value.trim()) { try { body = JSON.parse($("body").value); } catch (e) { $("result").textContent = "The body is not valid JSON."; return; } }
  $("result").textContent = "…";
  const key = method === "GET" ? null : crypto.randomUUID();
  const r = await api("/api/call", { method: "POST", body: JSON.stringify({ method, path, body, key, dry_run: $("dry").checked }) });
  $("result").textContent = method + " " + path + (key ? "  (Idempotency-Key " + key.slice(0, 8) + "…)" : "");
  show($("answer"), r.status, r.body);
}
$("run").onclick = send;
$("connect").onclick = () => { location.href = "/connect"; };
$("disconnect").onclick = async () => { await api("/api/disconnect", { method: "POST", body: "{}" }); refresh(); };

let previewed = null;
function createBody() {
  const body = { name: $("name").value, description: $("description").value };
  if ($("assignee").value) body.assignees = [$("assignee").value];
  return body;
}
function createPath() { const p = JSON.parse($("project").value || "null"); return p && "/workspaces/" + p.workspace + "/projects/" + p.id + "/work-items/"; }
$("preview").onclick = async () => {
  const path = createPath(); if (!path) { return show($("createAnswer"), 0, "Connect first, and pick a project."); }
  const r = await api("/api/call", { method: "POST", body: JSON.stringify({ method: "POST", path, body: createBody(), key: crypto.randomUUID(), dry_run: true }) });
  show($("createAnswer"), r.status, r.body); previewed = r.status < 300 ? { path, body: createBody(), key: crypto.randomUUID() } : null;
  $("create").disabled = !previewed;
};
$("create").onclick = async () => {
  if (!previewed) return; $("create").disabled = true;
  const r = await api("/api/call", { method: "POST", body: JSON.stringify({ method: "POST", path: previewed.path, body: previewed.body, key: previewed.key }) });
  show($("createAnswer"), r.status, r.body); previewed = null;
};
$("project").onchange = async () => {
  const p = JSON.parse($("project").value || "null"); $("assignee").length = 1; if (!p) return;
  const r = await api("/api/call", { method: "POST", body: JSON.stringify({ method: "GET", path: "/workspaces/" + p.workspace + "/projects/" + p.id + "/members/" }) });
  for (const m of (r.body && r.body.results) || []) if (m.can_be_assigned) { const o = new Option(m.display_name, m.id); $("assignee").add(o); }
};

async function refresh() {
  const s = await api("/api/status");
  $("hook").textContent = s.hook;
  if (!s.connected) {
    $("status").innerHTML = '<span class="bad">Not connected.</span> Press “Connect to Plane”: you will be sent to Plane to approve, then brought back here.';
    $("disconnect").disabled = true; $("connect").disabled = false; return;
  }
  $("connect").disabled = true; $("disconnect").disabled = false;
  $("status").innerHTML = '<span class="ok">Connected</span> as <b></b> · scopes: <span class="muted"></span> · access token valid for ' + s.expires_in + ' s';
  $("status").querySelector("b").textContent = (s.account && s.account.display_name) || "?";
  $("status").querySelector(".muted").textContent = s.scope;
  if ($("project").options.length === 0) {
    const r = await api("/api/call", { method: "POST", body: JSON.stringify({ method: "GET", path: "/projects/" }) });
    for (const p of (r.body && r.body.results) || []) $("project").add(new Option(p.workspace + " / " + p.name, JSON.stringify({ workspace: p.workspace, id: p.id })));
    $("project").onchange();
  }
}
async function events() {
  const r = await api("/api/events"); const tb = $("events"); tb.replaceChildren();
  for (const e of r.events) {
    const tr = tb.insertRow();
    tr.insertCell().textContent = e.at; tr.insertCell().textContent = e.type;
    const c = tr.insertCell(); c.textContent = e.verified ? "✓ verified" : "✗ refused"; c.className = e.verified ? "ok" : "bad";
    tr.insertCell().textContent = e.summary || "";
  }
  if (!r.events.length) tb.insertRow().insertCell().textContent = "Nothing yet.";
}
refresh(); events(); setInterval(events, 2000); setInterval(refresh, 30000);
</script></body></html>"""


def render_page():
    return PAGE.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "SandboxBot/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("  " + fmt % args + "\n")

    # -- plumbing

    def reply(self, status, body=b"", content_type="application/json", headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location, headers=None):
        self.reply(302, b"", headers={"Location": location, **(headers or {})})

    def host_ok(self):
        # Refuses a page on another site that has pointed a name of its own at this computer (DNS rebinding).
        return self.headers.get("Host", "") in (f"localhost:{Config.port}", f"127.0.0.1:{Config.port}")

    def has_key(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get("sandbox")
        return bool(morsel) and hmac.compare_digest(morsel.value, Config.key)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(min(length, 1_000_000))

    def deny(self):
        self.reply(
            403,
            b"Open the address that sandbox_bot.py printed in its window: it carries a one-time key.",
            "text/plain; charset=utf-8",
        )

    # -- routes

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/callback":
            return self.callback(query)
        if not self.host_ok():
            return self.reply(421, b"Wrong host name.", "text/plain")
        if url.path == "/" and query.get("k") and hmac.compare_digest(query["k"][0], Config.key):
            cookie = f"sandbox={Config.key}; Path=/; HttpOnly; SameSite=Strict"
            return self.redirect("/", {"Set-Cookie": cookie})
        if not self.has_key():
            return self.deny()
        if url.path == "/":
            return self.reply(200, render_page(), "text/html; charset=utf-8")
        if url.path == "/connect":
            try:
                return self.redirect(start_link())
            except RuntimeError as error:
                return self.reply(502, str(error).encode(), "text/plain; charset=utf-8")
        if url.path == "/api/status":
            with State.lock:
                tokens, account = State.tokens, State.account
            hook = f"http://host.docker.internal:{Config.port}/plane/events"
            if not tokens:
                return self.reply(200, {"connected": False, "hook": hook})
            return self.reply(
                200,
                {
                    "connected": True,
                    "account": account,
                    "scope": tokens["scope"],
                    "expires_in": max(int(tokens["expires_at"] - time.time()), 0),
                    "hook": hook,
                },
            )
        if url.path == "/api/events":
            with State.lock:
                shown = [{k: v for k, v in e.items() if k != "event"} for e in State.events]
            return self.reply(200, {"events": shown})
        self.reply(404, {"error": "not_found"})

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/plane/events":  # Plane, not a browser: authenticated by the signature
            return self.reply(receive_event(self.headers, self.read_body()))
        if not (self.host_ok() and self.has_key()):
            return self.deny()
        try:
            payload = json.loads(self.read_body() or b"{}")
        except ValueError:
            return self.reply(400, {"error": "invalid_request"})
        if url.path == "/api/call":
            method = str(payload.get("method", "GET")).upper()
            if method not in ("GET", "POST", "PATCH"):
                return self.reply(400, {"error": "invalid_request"})
            status, body = call(
                method,
                str(payload.get("path", "")),
                payload.get("body"),
                idempotency_key=payload.get("key"),
                dry_run=bool(payload.get("dry_run")),
            )
            return self.reply(200, {"status": status, "body": body})
        if url.path == "/api/disconnect":
            disconnect()
            return self.reply(200, {"ok": True})
        self.reply(404, {"error": "not_found"})

    def callback(self, query):
        """Where Plane sends the person's browser after they decide."""
        page = "text/plain; charset=utf-8"
        if query.get("error"):
            return self.reply(200, f"Not connected: {query['error'][0]}. Go back and try again.".encode(), page)
        try:
            finish_link(query.get("code", [""])[0], query.get("state", [""])[0])
        except RuntimeError as error:
            return self.reply(400, str(error).encode(), page)
        self.redirect("/")  # the cookie set when the cockpit was opened goes along


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    env = os.environ.get
    parser.add_argument("--client-id", default=env("PLANE_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=env("PLANE_CLIENT_SECRET", ""))
    parser.add_argument("--webhook-secret", default=env("PLANE_WEBHOOK_SECRET", ""))
    parser.add_argument("--plane", default=env("PLANE_API", "http://localhost:8000"), help="Plane's address (API).")
    parser.add_argument("--web", default=env("PLANE_WEB", ""), help="Where Plane's web app is served, if the link Plane builds differs.")
    parser.add_argument("--scope", default=ALL_SCOPES)
    parser.add_argument("--port", type=int, default=int(env("SANDBOX_PORT", "8920")))
    args = parser.parse_args()
    if not (args.client_id and args.client_secret):
        parser.error("--client-id and --client-secret are needed (an administrator registers the app with `agent_client create`).")

    Config.api = args.plane.rstrip("/") + "/api/agent/v1"
    Config.web, Config.client_id, Config.client_secret = args.web, args.client_id, args.client_secret
    Config.webhook_secret, Config.scope, Config.port = args.webhook_secret, args.scope, args.port

    server = ThreadingHTTPServer(("127.0.0.1", Config.port), Handler)
    print(f"\nSandbox bot is listening.\n\n  Open:   http://localhost:{Config.port}/?k={Config.key}\n")
    print(f"  Plane:  {Config.api}")
    print(f"  Events: Plane should call http://host.docker.internal:{Config.port}/plane/events (from a container)")
    if not Config.webhook_secret:
        print("  (no --webhook-secret: events will be shown as refused)")
    print("\nStop with Ctrl+C.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
