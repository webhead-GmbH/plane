# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Making text from another app safe to show to a person who is about to trust it.

The consent screen shows who is asking to be connected: a chat account's name and
handle, typed by a stranger and passed on by the app. Somebody who wants to be
approved by mistake has every reason to make that text look like something it is
not, and the cheapest way is invisible characters: a right-to-left override can
make a handle display backwards, a zero-width space can make two different names
look the same.

Everything between the app and the screen goes through here. Letters, digits and
punctuation of every script are kept — a Persian name is the common case, not an
exception — and so are the joiners Persian and emoji need.
"""

# Python imports
import re
import unicodedata

# Characters that change how text is laid out or that show nothing at all. The two
# joiners (zero-width non-joiner and joiner) are deliberately absent: Persian
# spelling and emoji need them.
_JOINERS = "‌‍"

_INVISIBLE = re.compile(
    "["
    "؜"  # Arabic letter mark
    "​"  # zero-width space
    "‎‏"  # left-to-right and right-to-left marks
    "  "  # line and paragraph separators
    "‪-‮"  # embeddings and overrides
    "⁠-⁤"  # word joiner and invisible operators
    "⁦-⁩"  # isolates
    "﻿"  # byte order mark
    "]"
)


def clean_display_text(value, max_length):
    """The text as it may be shown: normalised, with nothing invisible, on one line, capped."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _INVISIBLE.sub("", text)
    # Control characters (newlines and tabs included) become spaces, then runs of
    # space collapse, so a name cannot take more than one line of the screen.
    text = "".join(
        " " if unicodedata.category(char).startswith("C") and char not in _JOINERS else char for char in text
    )
    text = " ".join(text.split())
    return text[:max_length].strip()
