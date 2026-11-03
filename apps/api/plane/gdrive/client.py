# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Google sign-in tokens and the handful of Drive calls Plane makes.

Written against the REST API with ``requests`` rather than the Google client
library: it is a dozen calls, and the library is a large dependency to keep
current for them.

Every call acts as the Google account a workspace admin connected. Files are
created as that account, inside folders the team already shares, so they land in
the company's Drive and count against its storage, not the Plane server's.
"""

# Python imports
import logging
import re
from urllib.parse import urlencode

# Third party imports
import requests

# Django imports
from django.core.cache import cache

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
# Full Drive access: the project folders already exist, so Plane has to be able
# to see them, and the narrower drive.file scope only reaches files Plane made.
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,size,webViewLink,iconLink,thumbnailLink,parents,trashed,driveId"
TIMEOUT = 30

# Folder ids and the ids inside Drive links are URL-safe base64.
_ID_IN_LINK = re.compile(r"(?:/folders/|/d/|[?&]id=)([A-Za-z0-9_-]{10,})")
_BARE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")


class DriveError(Exception):
    """A call to Google that did not do what was asked.

    ``reason`` is Google's own reason code where it gave one (``notFound``,
    ``insufficientFilePermissions``, ``invalid_grant`` …), so callers can tell a
    revoked connection from a missing folder.
    """

    def __init__(self, message, status=None, reason=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.reason = reason


def _error_from(response):
    try:
        body = response.json()
    except ValueError:
        return DriveError(f"Google answered {response.status_code}.", response.status_code)
    error = body.get("error")
    if isinstance(error, dict):
        reasons = [item.get("reason") for item in error.get("errors", []) if item.get("reason")]
        return DriveError(error.get("message") or str(error), response.status_code, reasons[0] if reasons else None)
    # The token endpoint answers {"error": "invalid_grant", "error_description": "..."}.
    return DriveError(body.get("error_description") or str(error), response.status_code, error)


def folder_id_from(text):
    """A folder id out of a pasted Drive link, or the id itself; None if neither."""
    text = (text or "").strip()
    match = _ID_IN_LINK.search(text)
    if match:
        return match.group(1)
    return text if _BARE_ID.match(text) else None


def escape_query(value):
    """A value for a single-quoted string in a Drive search query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def authorization_url(client_id, redirect_uri, state):
    """Where to send the admin to let Plane use their Drive."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        # A refresh token, so Plane keeps working after the admin's session ends,
        # and asked for every time: Google only sends one on a fresh consent.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id, client_secret, code, redirect_uri):
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        raise _error_from(response)
    return response.json()


def revoke(token):
    """Tell Google the token is no longer wanted. Best effort: disconnecting goes ahead either way."""
    try:
        requests.post(REVOKE_URL, data={"token": token}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("Could not revoke the Google Drive token: %s", exc)


class DriveClient:
    """Drive calls made as the account a workspace connected."""

    def __init__(self, connection):
        self.connection = connection

    # ─── Tokens ────────────────────────────────────────────────────────────

    def _cache_key(self):
        return f"gdrive:access-token:{self.connection.id}"

    def _access_token(self, force_refresh=False):
        if not force_refresh:
            token = cache.get(self._cache_key())
            if token:
                return token
        refresh_token = self.connection.get_refresh_token()
        if not refresh_token:
            raise DriveError("Google Drive is not connected.", reason="not_connected")
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.connection.client_id,
                "client_secret": self.connection.get_client_secret(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            raise _error_from(response)
        body = response.json()
        token = body["access_token"]
        # A minute short of Google's own expiry, so a token is never used in its last seconds.
        cache.set(self._cache_key(), token, max(int(body.get("expires_in", 3600)) - 60, 60))
        return token

    def _request(self, method, url, *, retry=True, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = f"Bearer {self._access_token()}"
        kwargs.setdefault("timeout", TIMEOUT)
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as exc:
            raise DriveError(f"Google Drive could not be reached: {exc}") from exc
        if response.status_code == 401 and retry:
            # The cached token was revoked or expired early; one fresh try.
            self._access_token(force_refresh=True)
            return self._request(method, url, retry=False, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise _error_from(response)
        return response

    # ─── Reading ───────────────────────────────────────────────────────────

    def about(self):
        return self._request("GET", f"{API}/about", params={"fields": "user(emailAddress,displayName)"}).json()

    def get(self, file_id, fields=FILE_FIELDS):
        return self._request(
            "GET", f"{API}/files/{file_id}", params={"fields": fields, "supportsAllDrives": "true"}
        ).json()

    def _list(self, query, fields="nextPageToken,files(id,name)", order_by="name", extra=None):
        found, token = [], None
        while True:
            params = {
                "q": query,
                "fields": fields,
                "pageSize": 1000,
                "orderBy": order_by,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "corpora": "allDrives",
                **(extra or {}),
            }
            if token:
                params["pageToken"] = token
            body = self._request("GET", f"{API}/files", params=params).json()
            found.extend(body.get("files", []))
            token = body.get("nextPageToken")
            if not token:
                return found

    def list_folders(self, parent_id):
        """The folders directly inside one folder, by name."""
        query = f"'{escape_query(parent_id)}' in parents and mimeType='{FOLDER_MIME}' and trashed=false"
        if parent_id == "root":
            # My Drive's root is not in any shared drive, and allDrives would refuse it.
            return self._list(query, extra={"corpora": "user"})
        return self._list(query)

    def shared_with_me_folders(self):
        return self._list(f"sharedWithMe and mimeType='{FOLDER_MIME}' and trashed=false", extra={"corpora": "user"})

    def shared_drives(self):
        found, token = [], None
        while True:
            params = {"pageSize": 100, "fields": "nextPageToken,drives(id,name)"}
            if token:
                params["pageToken"] = token
            body = self._request("GET", f"{API}/drives", params=params).json()
            found.extend(body.get("drives", []))
            token = body.get("nextPageToken")
            if not token:
                return found

    def path_of(self, folder_id, limit=12):
        """The folder's names from the top of its drive down, for showing where it is."""
        names, current = [], folder_id
        for _ in range(limit):
            meta = self.get(current, fields="id,name,parents,driveId")
            parents = meta.get("parents") or []
            if meta.get("driveId") and meta["id"] == meta["driveId"]:
                drive = self._request("GET", f"{API}/drives/{meta['driveId']}", params={"fields": "name"}).json()
                names.append(drive.get("name") or meta.get("name", ""))
                break
            names.append(meta.get("name", ""))
            if not parents:
                break
            current = parents[0]
        return list(reversed(names))

    def find_folder(self, parent_id, name):
        query = (
            f"'{escape_query(parent_id)}' in parents and name='{escape_query(name)}' "
            f"and mimeType='{FOLDER_MIME}' and trashed=false"
        )
        found = self._list(query, fields="files(id,name)", order_by="createdTime")
        return found[0] if found else None

    # ─── Writing ───────────────────────────────────────────────────────────

    def create_folder(self, parent_id, name):
        return self._request(
            "POST",
            f"{API}/files",
            params={"supportsAllDrives": "true", "fields": "id,name,webViewLink"},
            json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        ).json()

    def ensure_folder(self, parent_id, name):
        return self.find_folder(parent_id, name) or self.create_folder(parent_id, name)

    def trash(self, file_id):
        self._request("PATCH", f"{API}/files/{file_id}", params={"supportsAllDrives": "true"}, json={"trashed": True})

    # ─── Uploads ───────────────────────────────────────────────────────────

    def start_upload(self, parent_id, name, mime_type, size, origin=None):
        """A resumable upload session for one file; returns the session URL.

        The bytes go to that URL in chunks, from the browser where Google allows
        it. ``origin`` is the browser's origin: Google only answers the browser's
        cross-origin requests to a session opened on a server if the opening
        request names it.
        """
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": mime_type or "application/octet-stream",
            "X-Upload-Content-Length": str(size),
        }
        if origin:
            headers["Origin"] = origin
        response = self._request(
            "POST",
            f"{UPLOAD_API}/files",
            params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": FILE_FIELDS},
            headers=headers,
            json={"name": name, "parents": [parent_id]},
        )
        location = response.headers.get("Location")
        if not location:
            raise DriveError("Google did not open an upload session.")
        return location

    @staticmethod
    def _session_answer(response):
        """(finished, bytes Google has, file) from an answer on an upload session."""
        if response.status_code in (200, 201):
            return True, None, response.json()
        if response.status_code == 308:
            received = response.headers.get("Range")
            # "bytes=0-1048575": the last byte held, inclusive.
            return False, int(received.rsplit("-", 1)[1]) + 1 if received else 0, None
        raise _error_from(response)

    def upload_status(self, session_url, size):
        """Ask the session how much it has. The session URL is its own credential."""
        try:
            response = requests.put(
                session_url, headers={"Content-Range": f"bytes */{size}", "Content-Length": "0"}, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise DriveError(f"Google Drive could not be reached: {exc}") from exc
        return self._session_answer(response)

    def upload_chunk(self, session_url, data, start, total):
        """Pass one chunk on, for a browser Google would not take it from directly."""
        end = start + len(data) - 1
        try:
            response = requests.put(
                session_url,
                data=data,
                headers={"Content-Range": f"bytes {start}-{end}/{total}", "Content-Length": str(len(data))},
                timeout=120,
            )
        except requests.RequestException as exc:
            raise DriveError(f"Google Drive could not be reached: {exc}") from exc
        return self._session_answer(response)

    # ─── Showing files ─────────────────────────────────────────────────────

    def thumbnail(self, file_id, size):
        """A resized image of the file, or None where Google has none (yet)."""
        meta = self.get(file_id, fields="thumbnailLink,mimeType,size")
        link = meta.get("thumbnailLink")
        if not link:
            return None
        # Thumbnail links end in "=s220"; any size can be asked for.
        link = re.sub(r"=s\d+(-c)?$", f"=s{int(size)}", link)
        try:
            response = requests.get(link, headers={"Authorization": f"Bearer {self._access_token()}"}, timeout=TIMEOUT)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        return response.content, response.headers.get("Content-Type", "image/jpeg")

    def content(self, file_id):
        """The file's own bytes, streamed."""
        return self._request(
            "GET",
            f"{API}/files/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            stream=True,
            timeout=60,
        )
