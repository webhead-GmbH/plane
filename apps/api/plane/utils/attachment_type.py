# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os

# Plain-text formats: their content carries no signature to recognise them by. The web
# client reads a file's type from its content and declares none for these, so their
# type has to come from the name. Every value is in ATTACHMENT_MIME_TYPES.
TYPE_BY_EXTENSION = {
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".sql": "application/x-sql",
}


def attachment_type(name, declared_type):
    """
    The type to check an attachment against ATTACHMENT_MIME_TYPES with, and to store it under.

    A declared type is returned as it is: a file whose content says what it is never
    gets relabelled by its name. Only when none is declared is the type read from the
    extension, and only for the formats above. None when neither gives one.
    """
    if declared_type:
        return declared_type
    return TYPE_BY_EXTENSION.get(os.path.splitext(name or "")[1].lower())
