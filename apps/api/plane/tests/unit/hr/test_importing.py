# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading a length of time out of somebody else's spreadsheet."""

# Third-party imports
import pytest

# Module imports
from plane.hr.services.importing import _as_minutes, _length_column

pytestmark = [pytest.mark.unit]


class TestLengthsFromASpreadsheet:
    """What a bare number in a length column means.

    The heading decides. Reading an hours column as minutes divides every
    imported month by sixty, and because the result is still a plausible number
    of minutes nothing downstream would flag it — the month would simply be
    wrong, permanently, for every person in the file.
    """

    def test_an_hours_column_is_read_as_hours(self):
        assert _as_minutes(*_length_column({"hours": "7.7"})) == 462
        assert _as_minutes(*_length_column({"hours": "8"})) == 480
        assert _as_minutes(*_length_column({"stunden": "6,42"})) == 385

    def test_a_minutes_column_is_read_as_minutes(self):
        assert _as_minutes(*_length_column({"minutes": "462"})) == 462
        assert _as_minutes(*_length_column({"minuten": "480"})) == 480

    def test_a_clock_time_says_what_it_is_under_either_heading(self):
        assert _as_minutes(*_length_column({"hours": "7:42"})) == 462
        assert _as_minutes(*_length_column({"minutes": "7:42"})) == 462

    def test_a_sheet_carrying_both_is_read_the_precise_way(self):
        # Minutes cannot lose a remainder; hours can.
        assert _as_minutes(*_length_column({"minutes": "463", "hours": "7.7"})) == 463

    def test_decimal_hours_round_rather_than_truncate(self):
        # 7.99 hours is 479 minutes, not 479 with the remainder dropped to 478.
        assert _as_minutes(*_length_column({"hours": "7.99"})) == 479
        assert _as_minutes(*_length_column({"hours": "0.5"})) == 30

    def test_a_negative_correction_survives_either_way(self):
        assert _as_minutes(*_length_column({"hours": "-1.5"})) == -90
        assert _as_minutes(*_length_column({"minutes": "-90"})) == -90
        assert _as_minutes(*_length_column({"hours": "-1:30"})) == -90

    def test_nothing_readable_is_refused_rather_than_guessed(self):
        assert _as_minutes(*_length_column({})) is None
        assert _as_minutes(*_length_column({"hours": "half a day"})) is None
        assert _as_minutes(*_length_column({"hours": ""})) is None
