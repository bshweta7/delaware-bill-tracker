import math

import pytest

from billtracker.categories import CEREMONIAL, OTHER, categorize, code_titles
from billtracker.stages import stage_for


@pytest.mark.parametrize(
    ("status", "legislation_type", "expected"),
    [
        ("Passed", "Bill", "Passed Both Chambers"),
        ("Passed", "Concurrent Resolution", "Adopted"),
        ("Passed", "Amendment", "Adopted"),
        ("Passed House", "Bill", "Passed One Chamber"),
        ("Signed", "Bill", "Enacted"),
        ("Veto Overridden", "Bill", "Enacted"),
        ("Lieu/Substituted", "Bill", "Substituted"),
        ("LOT", "Bill", "Tabled"),
        ("PWB", "Amendment", "Pending"),
        ("Judiciary", "Bill", "In Committee"),  # committee names are statuses too
        ("Some Brand New Committee", "Bill", "In Committee"),
    ],
)
def test_stage_for(status, legislation_type, expected):
    assert stage_for(status, legislation_type) == expected


def test_code_titles_reads_single_and_multiple_titles():
    assert code_titles("AN ACT TO AMEND TITLE 14 OF THE DELAWARE CODE") == [14]
    assert code_titles("AN ACT TO AMEND TITLES 11 AND 29 OF THE DELAWARE CODE") == [11, 29]
    assert code_titles("AN ACT TO AMEND TITLES 9, 16 AND 22") == [9, 16, 22]
    assert code_titles("A JOINT RESOLUTION") == []


def test_categorize_uses_code_title_when_keywords_are_absent():
    assert categorize(None, "AN ACT TO AMEND TITLE 30 OF THE DELAWARE CODE.", None) == "Taxes & Budget"


def test_categorize_prefers_strong_keywords():
    category = categorize(
        "Charter Schools/Enrollment",
        "AN ACT TO AMEND TITLE 14 OF THE DELAWARE CODE RELATING TO CHARTER SCHOOLS.",
        "This Act changes how students enroll in charter schools.",
    )
    assert category == "Education"


def test_ceremonial_only_applies_to_resolutions():
    title = "RECOGNIZING MAY 2025 AS MENTAL HEALTH AWARENESS MONTH."
    assert categorize(None, title, None, is_resolution=True) == CEREMONIAL
    assert categorize(None, title, None, is_resolution=False) == "Health"


def test_categorize_handles_missing_text():
    assert categorize(None, None, None) == OTHER
    assert categorize(math.nan, math.nan, math.nan) == OTHER  # pandas missing values
