# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which existing Drive folder a project's name is most likely to mean.

Folder names drift from project names in small ways — an extra space, a dash
instead of a space, a letter missing, a year on the end — so they are compared
after both are reduced to their letters and digits, and scored rather than
required to be equal, to put the likely folders first.

Linking without asking is held to more: the same name give or take spacing,
punctuation, a company form or one letter, and no other folder like it. A
folder that only looks alike ("Gruber", "Fischer Gruber" for "Fisch Gruber")
may be another client's, and a file put there by mistake is a file shown to them.
"""

# Python imports
import re
import unicodedata
from difflib import SequenceMatcher

# Words a company's name carries or drops without becoming another company's.
LEGAL_FORMS = {"gmbh", "mbh", "ag", "kg", "og", "ug", "gbr", "eu", "ek", "e", "u", "k", "co", "se", "ltd", "inc", "llc"}
# A letter off counts as a slip only in a name at least this long; in a short one it is another name.
MIN_LENGTH_FOR_A_SLIP = 6


def normalize(name):
    """Lower case, accents gone, and every run of other characters one space."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = text.replace("ß", "ss")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def score(project_name, folder_name):
    """How alike the two names are, from 0 to 1."""
    a, b = normalize(project_name), normalize(folder_name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    a_flat, b_flat = a.replace(" ", ""), b.replace(" ", "")
    if a_flat == b_flat:
        # "Fisch Gruber" and "fisch-gruber" and "FischGruber" are the same name.
        return 0.99
    best = max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, a_flat, b_flat).ratio())
    short, long = sorted((a_flat, b_flat), key=len)
    if len(short) >= 4 and short in long:
        # One name inside the other, e.g. a year or a client on the end: alike in
        # proportion to how much of the longer name the shorter one is.
        best = max(best, 0.8 + 0.15 * len(short) / len(long))
    return round(best, 3)


def rank(project_name, folders, limit=5, floor=0.5):
    """The folders most like the project's name, best first, each with its score."""
    scored = [(folder, score(project_name, folder["name"])) for folder in folders]
    scored = [item for item in scored if item[1] >= floor]
    scored.sort(key=lambda item: (-item[1], item[0]["name"].lower()))
    return scored[:limit]


def _core(name):
    """The letters and digits that have to agree: no spaces, punctuation or company form."""
    return "".join(word for word in normalize(name).split() if word not in LEGAL_FORMS)


def _one_letter_apart(a, b):
    """Whether one letter added, dropped or changed turns one into the other."""
    if len(a) > len(b):
        a, b = b, a
    if len(b) - len(a) > 1:
        return False
    i = j = slips = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            slips += 1
            if slips > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
            continue
        i += 1
        j += 1
    return slips + (len(a) - i) + (len(b) - j) <= 1


def same_name(project_name, folder_name):
    """Whether the folder carries the project's own name, give or take a slip of the keyboard."""
    a, b = _core(project_name), _core(folder_name)
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= MIN_LENGTH_FOR_A_SLIP and _one_letter_apart(a, b)


def confident_match(project_name, folders):
    """The one folder that is clearly the project's, or None if there is none or more than one."""
    matches = [folder for folder in folders if same_name(project_name, folder["name"])]
    return matches[0] if len(matches) == 1 else None
