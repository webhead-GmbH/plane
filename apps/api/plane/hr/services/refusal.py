# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A refusal written for the person who will read it.

The module says no to a great many things, and until now it said so by raising
``ValueError``. The views then echoed ``str(exc)`` back to the caller, which
worked because every one of those had been written by hand for exactly that
purpose — "Say why the import is being undone", "Only CSV and XLSX can be read".

The trouble is that ``ValueError`` is not ours. A spreadsheet reader raises it on
a corrupt file, ``int()`` raises it on a bad string, and the message that comes
with those is written for a developer: a file path, a sheet name, a row of
somebody's data. Echoing one of those to whoever uploaded the file hands them
part of the inside of the server, and no ``except`` clause can tell the two
apart because they are the same type.

So a refusal meant for a person gets its own type. The views answer with these
and nothing else; anything else that goes wrong reaches the ordinary handler,
which logs it and says something generic.
"""


class Refused(Exception):
    """Something the module will not do, and the reason a person should read.

    ``conflict`` distinguishes "this cannot be done in the state things are in"
    from "what you sent cannot be used" — 409 against 400 — because the first is
    worth retrying after something changes and the second is not.
    """

    def __init__(self, message, conflict=False):
        super().__init__(message)
        self.message = message
        self.conflict = conflict
