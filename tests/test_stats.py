import pytest

from billtracker import pipeline, stats
from billtracker.families import build_families


@pytest.fixture
def items(raw_rows):
    return pipeline.build_items(raw_rows)


@pytest.fixture
def families(items):
    return build_families(items)


def test_outcome_groups():
    assert stats.outcome("Enacted") == "Passed"
    assert stats.outcome("Adopted") == "Passed"
    assert stats.outcome("Vetoed") == "Did not pass"
    assert stats.outcome("In Committee") == "In progress"


def test_category_outcomes(families):
    table = stats.category_outcomes(families)
    assert set(zip(table["category"], table["outcome"], table["count"])) == {
        ("Education", "Passed", 1),
        ("Public Safety & Justice", "In progress", 1),
        ("Ceremonial & Recognition", "Passed", 1),
    }
