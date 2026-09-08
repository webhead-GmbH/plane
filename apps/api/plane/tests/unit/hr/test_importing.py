# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading a length of time out of somebody else's spreadsheet."""

# Third-party imports
import pytest

# Module imports
from plane.hr.services.importing import _as_minutes, _length_column, parse, separator_of

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


class TestWhicheverWayTheSheetWasSaved:
    """Which character a spreadsheet put between its columns.

    Excel uses the list separator of the machine it was saved on, and on a
    German or Austrian Windows that is a semicolon. Read with a comma, such a
    file has one column, every row fails at once, and the person is told their
    file is wrong when it is the one their own spreadsheet just made.
    """

    def test_a_comma_file_reads_as_columns(self):
        assert separator_of("email,date,hours\na@b.test,2026-01-01,7:42") == ","

    def test_a_semicolon_file_reads_as_columns(self):
        assert separator_of("email;date;hours\na@b.test;2026-01-01;7:42") == ";"

    def test_a_tab_file_reads_as_columns(self):
        assert separator_of("email\tdate\thours\na@b.test\t2026-01-01\t7:42") == "\t"

    def test_a_comma_inside_a_note_does_not_decide_it(self):
        heading = "email;date;hours;note"
        row = "a@b.test;2026-01-01;7:42;Meeting, then travel, then more travel"
        assert separator_of(heading + "\n" + row) == ";"

    def test_the_same_rows_come_out_of_either_file(self):
        comma = parse("email,date,hours\na@b.test,2026-01-01,7:42\n", "csv")
        semicolon = parse("email;date;hours\na@b.test;2026-01-01;7:42\n", "csv")
        assert comma == semicolon
        assert comma[0]["hours"] == "7:42"
