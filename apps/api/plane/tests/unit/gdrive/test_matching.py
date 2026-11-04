# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Matching a project's name to the Drive folder it most likely means."""

import pytest

from plane.gdrive.client import folder_id_from
from plane.gdrive.matching import (
    ANOTHER_NUMBER_AT_MOST,
    bare_name,
    carries_identifier,
    confident_match,
    folder_name_for,
    looks_taken,
    normalize,
    rank,
    score,
)

pytestmark = [pytest.mark.unit]


def folders(*names):
    return [{"id": f"id-{index}", "name": name} for index, name in enumerate(names)]


class TestScore:
    @pytest.mark.parametrize(
        ("project", "folder"),
        [
            ("Fisch Gruber", "fisch-gruber"),
            ("Fisch Gruber", "Fisch  Gruber "),
            ("FischGruber", "Fisch Gruber"),
            ("Café Müller", "Cafe Muller"),
            ("Straße", "Strasse"),
        ],
    )
    def test_the_same_name_written_differently_is_a_match(self, project, folder):
        assert score(project, folder) >= 0.99

    def test_a_letter_off_still_scores_high(self):
        assert score("Webhead Website", "Webhed Website") > 0.9

    def test_a_year_on_the_end_still_scores_high(self):
        assert score("Mustermann", "Mustermann 2024") >= 0.88

    def test_unrelated_names_score_low(self):
        assert score("Fisch Gruber", "Bäckerei Huber") < 0.6

    def test_empty_names_score_nothing(self):
        assert score("", "anything") == 0.0
        assert normalize("  --  ") == ""


class TestChoosing:
    def test_the_best_folders_come_first(self):
        ranked = rank("Fisch Gruber", folders("Huber", "fisch-gruber", "Fisch Gruber Archiv"))
        assert [folder["name"] for folder, _ in ranked][:2] == ["fisch-gruber", "Fisch Gruber Archiv"]

    def test_a_clear_winner_is_chosen(self):
        assert confident_match("Fisch Gruber", folders("Huber", "fisch-gruber"))["name"] == "fisch-gruber"

    def test_two_close_folders_are_not_chosen_between(self):
        assert confident_match("Webhead", folders("Webhead 2023", "Webhead 2024")) is None

    def test_nothing_alike_chooses_nothing(self):
        assert confident_match("Fisch Gruber", folders("Huber", "Maier")) is None

    @pytest.mark.parametrize(
        "folder", ["Fisch Gruber GmbH", "fisch-gruber e.U.", "Fish Gruber", "Fisch  Grubber", "FISCH_GRUBER"]
    )
    def test_the_same_name_give_or_take_a_slip_is_chosen(self, folder):
        assert confident_match("Fisch Gruber", folders(folder, "Huber"))["name"] == folder

    @pytest.mark.parametrize("folder", ["Gruber", "Fischer Gruber", "Fisch Gruber Archiv", "Fisch Gruber 2024"])
    def test_a_name_that_only_looks_alike_is_offered_not_chosen(self, folder):
        # Each could be another client's folder; it is suggested, never linked by itself.
        assert confident_match("Fisch Gruber", folders(folder)) is None
        assert rank("Fisch Gruber", folders(folder))

    def test_a_letter_off_in_a_short_name_is_another_name(self):
        assert confident_match("Lang", folders("Lange")) is None

    def test_two_folders_with_the_name_are_not_chosen_between(self):
        assert confident_match("Fisch Gruber", folders("Fisch-Gruber", "Fisch Gruber GmbH")) is None


class TestTeamFolderNames:
    """Folders named "<identifier> - <name>", the way the team names them in Drive."""

    def test_a_new_folder_is_named_with_the_identifier_and_the_name(self):
        assert folder_name_for("209", "ATTN-SEEKR  Webseite ") == "209 - ATTN-SEEKR Webseite"
        assert folder_name_for("", "Fisch Gruber") == "Fisch Gruber"

    @pytest.mark.parametrize(
        ("identifier", "project", "folder"),
        [
            ("288", "Alias Immo", "288 - Alias"),
            ("286", "BTS Bohrtechnik", "286 - BTS"),
            ("68", "Group Austria", "68 - Group Austria - Michaela Baumgartner"),
            ("288", "Something else entirely", "288 – Alias"),
            ("288", "Alias Immo", "288-Alias"),
        ],
    )
    def test_a_folder_named_with_the_projects_number_is_its_folder(self, identifier, project, folder):
        # The name after the dash drifts; the number is the project's.
        assert confident_match(project, folders(folder, "Huber"), identifier=identifier)["name"] == folder

    def test_the_number_must_be_the_whole_number(self):
        assert confident_match("Alias", folders("2880 - Alias", "28 - Alias"), identifier="288") is None
        assert carries_identifier("68", "068 - Group Austria")

    def test_a_number_that_is_part_of_the_name_is_not_a_project_number(self):
        assert not carries_identifier("3", "3D Druck GmbH")
        assert bare_name("3", "3D Druck GmbH") == "3D Druck GmbH"

    def test_two_folders_with_the_projects_number_are_not_chosen_between(self):
        assert confident_match("Alias Immo", folders("288 - Alias", "288 - Alias Immo"), identifier="288") is None
        assert looks_taken("Alias Immo", folders("288 - Alias", "288 - Alias Immo"), identifier="288")

    def test_the_folder_with_the_number_wins_over_one_with_only_the_name(self):
        match = confident_match("Biohof Radl", folders("Biohof Radl", "284 - Biohof Radl GmbH"), identifier="284")
        assert match["name"] == "284 - Biohof Radl GmbH"

    def test_a_folder_named_the_old_way_still_matches_by_name(self):
        match = confident_match("Biohof Radl", folders("Biohof Radl", "Huber"), identifier="284")
        assert match["name"] == "Biohof Radl"

    def test_another_projects_number_is_offered_never_chosen(self):
        # Same name, other number: perhaps a slip, perhaps the client's other project.
        candidates = folders("290 - Biohof Radl")
        assert confident_match("Biohof Radl", candidates, identifier="284") is None
        assert rank("Biohof Radl", candidates, identifier="284")[0][1] == ANOTHER_NUMBER_AT_MOST
        assert looks_taken("Biohof Radl", candidates, identifier="284")

    def test_the_projects_own_folder_comes_first_with_full_marks(self):
        ranked = rank("Alias Immo", folders("Alias Immo Archiv", "288 - Alias"), identifier="288")
        assert [(folder["name"], value) for folder, value in ranked][0] == ("288 - Alias", 1.0)

    def test_a_word_identifier_needs_the_spaces_round_the_dash(self):
        assert carries_identifier("PSTEC", "pstec - Plane sync test")
        assert not carries_identifier("ATTN", "ATTN-SEEKR Webseite")
        assert bare_name("PSTEC", "PSTEC - Plane sync test") == "Plane sync test"


class TestFolderLinks:
    @pytest.mark.parametrize(
        "text",
        [
            "https://drive.google.com/drive/folders/1AbC_dEf-GhIjKlMnOp",
            "https://drive.google.com/drive/u/1/folders/1AbC_dEf-GhIjKlMnOp?usp=sharing",
            "https://drive.google.com/open?id=1AbC_dEf-GhIjKlMnOp",
            "1AbC_dEf-GhIjKlMnOp",
        ],
    )
    def test_a_folder_id_is_read_out_of_a_pasted_link(self, text):
        assert folder_id_from(text) == "1AbC_dEf-GhIjKlMnOp"

    def test_text_that_is_not_a_link_gives_nothing(self):
        assert folder_id_from("projects / webhead") is None
