# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
An attachment with no declared type gets its type from its name.

The web client declares the type it reads from a file's content, and plain-text
formats have nothing there to read: a .txt, .csv or .md file arrived with an empty
type and was turned away as "Invalid file type."
"""

import pytest
from django.conf import settings

from plane.utils.attachment_type import TYPE_BY_EXTENSION, attachment_type


@pytest.mark.unit
class TestAttachmentType:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("notes.txt", "text/plain"),
            ("build.log", "text/plain"),
            ("README.md", "text/markdown"),
            ("guide.markdown", "text/markdown"),
            ("export.csv", "text/csv"),
            ("data.json", "application/json"),
            ("feed.xml", "application/xml"),
            ("dump.sql", "application/x-sql"),
        ],
    )
    def test_a_plain_text_file_is_typed_by_its_extension(self, name, expected):
        assert attachment_type(name, "") == expected

    def test_the_case_of_the_extension_does_not_matter(self):
        assert attachment_type("REPORT.CSV", "") == "text/csv"

    @pytest.mark.parametrize("declared", ["", None, False])
    def test_an_empty_declared_type_in_any_form_counts_as_none(self, declared):
        assert attachment_type("notes.txt", declared) == "text/plain"

    def test_a_declared_type_is_never_replaced_by_the_name(self):
        # Content that says it is a program stays one, whatever the file is called.
        assert attachment_type("notes.txt", "application/x-msdownload") == "application/x-msdownload"

    @pytest.mark.parametrize("name", ["page.html", "run.sh", "logo.svg", "archive", ".env", "", None])
    def test_a_name_that_names_no_plain_text_format_gives_no_type(self, name):
        assert attachment_type(name, "") is None

    def test_every_type_read_from_a_name_is_one_attachments_allow(self):
        assert set(TYPE_BY_EXTENSION.values()) <= set(settings.ATTACHMENT_MIME_TYPES)
