# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which Drive files a piece of text points at."""

# Third-party imports
import pytest

# Module imports
from plane.gdrive.references import references

pytestmark = pytest.mark.unit

PLANE_ID = "5b0a6dae-4049-4e5d-890f-3f4cd2d24706"


def test_an_image_is_found_by_its_plane_id():
    html = f'<image-component src="gdrive-{PLANE_ID}" width="267px"></image-component>'
    assert references(html) == {f"plane:{PLANE_ID}"}


def test_a_file_link_is_found_by_its_google_id():
    html = (
        '<p><a target="_blank" href="https://drive.google.com/file/d/1ZI--OWb2GSlApQczZezac2S0mqKxgfcs/view?usp=drivesdk"'
        ' rel="noopener">intercept-main.zip</a></p>'
    )
    assert references(html) == {"google:1ZI--OWb2GSlApQczZezac2S0mqKxgfcs"}


def test_a_google_docs_link_counts_too():
    html = '<a href="https://docs.google.com/document/d/1AbCdEfGhIjKlMn/edit?usp=drivesdk">Brief</a>'
    assert references(html) == {"google:1AbCdEfGhIjKlMn"}


def test_plane_assets_and_other_links_do_not():
    html = (
        '<image-component src="1b32bbef-6064-4a82-892e-8bd20a97c6a6"></image-component>'
        '<a href="https://example.com/d/1AbCdEfGhIjKlMn">elsewhere</a>'
    )
    assert references(html) == frozenset()


def test_empty_text_points_at_nothing():
    assert references(None) == frozenset()
    assert references("") == frozenset()
