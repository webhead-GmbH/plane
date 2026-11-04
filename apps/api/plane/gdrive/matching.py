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

The team names a project's folder after its identifier and its name, as in
"209 - ATTN-SEEKR Webseite" (the identifier is the project's number in the CRM).
A folder named that way for the project is its folder, whatever the name after
the dash has drifted to; one named for another project's number is never linked
by itself, however alike the names.
"""

# Python imports
import re
import unicodedata
from difflib import SequenceMatcher

# Words a company's name carries or drops without becoming another company's.
LEGAL_FORMS = {"gmbh", "mbh", "ag", "kg", "og", "ug", "gbr", "eu", "ek", "e", "u", "k", "co", "se", "ltd", "inc", "llc"}
# A letter off counts as a slip only in a name at least this long; in a short one it is another name.
MIN_LENGTH_FOR_A_SLIP = 6
# A folder named for another project's number is offered at most this alike, never as a sure thing.
ANOTHER_NUMBER_AT_MOST = 0.8
# "209 - ATTN-SEEKR Webseite": a project number, then a dash (any kind), then the name.
NUMBERED = re.compile(r"\s*(\d+)\s*[-–—]\s*(?=\S)")


def folder_name_for(identifier, name):
    """The name the team gives a project's folder: "209 - ATTN-SEEKR Webseite"."""
    identifier, name = (identifier or "").strip(), " ".join((name or "").split())
    return f"{identifier} - {name}" if identifier else name


def _number(folder_name):
    """The project number a folder is named for, or None for a folder named some other way."""
    found = NUMBERED.match(folder_name or "")
    return int(found.group(1)) if found else None


def _word_prefix(identifier):
    # A word needs the spaces round the dash, or "ATTN-SEEKR" would be project ATTN's folder.
    return re.compile(rf"\s*{re.escape(identifier)}\s+[-–—]\s+(?=\S)", re.IGNORECASE)


def carries_identifier(identifier, folder_name):
    """Whether the folder is named the team's way for this project: its identifier, a dash, a name."""
    identifier = (identifier or "").strip()
    if not identifier:
        return False
    if identifier.isdigit():
        return _number(folder_name) == int(identifier)
    return _word_prefix(identifier).match(folder_name or "") is not None


def bare_name(identifier, folder_name):
    """The folder's name without the project number (or this project's identifier) in front of it."""
    folder_name = folder_name or ""
    found = NUMBERED.match(folder_name)
    if found:
        return folder_name[found.end() :]
    identifier = (identifier or "").strip()
    if identifier and not identifier.isdigit():
        found = _word_prefix(identifier).match(folder_name)
        if found:
            return folder_name[found.end() :]
    return folder_name


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


def project_score(project_name, folder_name, identifier=""):
    """How alike a folder is to the project, from 0 to 1; a folder named with its identifier is 1."""
    if carries_identifier(identifier, folder_name):
        return 1.0
    value = score(project_name, bare_name(identifier, folder_name))
    if _number(folder_name) is not None:
        value = min(value, ANOTHER_NUMBER_AT_MOST)
    return value


def rank(project_name, folders, limit=5, floor=0.5, identifier=""):
    """The folders most like the project, best first, each with its score."""
    scored = [(folder, project_score(project_name, folder["name"], identifier)) for folder in folders]
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


def clear_matches(project_name, folders, identifier=""):
    """The folders plainly the project's.

    Those named with its identifier; failing any, those named with no project
    number that carry its name, give or take a slip of the keyboard.
    """
    own = [folder for folder in folders if carries_identifier(identifier, folder["name"])]
    if own:
        return own
    return [
        folder
        for folder in folders
        if _number(folder["name"]) is None and same_name(project_name, bare_name(identifier, folder["name"]))
    ]


def confident_match(project_name, folders, identifier=""):
    """The one folder that is clearly the project's, or None if there is none or more than one."""
    matches = clear_matches(project_name, folders, identifier)
    return matches[0] if len(matches) == 1 else None


def looks_taken(project_name, folders, identifier=""):
    """Whether a folder carries the project's identifier or its name, so that a new one would sit beside it."""
    return any(
        carries_identifier(identifier, folder["name"]) or same_name(project_name, bare_name(identifier, folder["name"]))
        for folder in folders
    )
