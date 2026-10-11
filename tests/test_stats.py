import pandas as pd
import pytest

from billtracker import pipeline, stats
from billtracker.families import build_families


@pytest.fixture
def items(raw_rows):
    return pipeline.build_items(raw_rows)


@pytest.fixture
def families(items):
    return build_families(items)


def test_overview(families, items):
    summary = stats.overview(families, items)
    assert summary.families == 3
    assert summary.bills == 2
    assert summary.resolutions == 1
    assert summary.enacted == 1
    assert summary.adopted == 1
    assert summary.still_moving == 1
    assert summary.amendments == 2
    assert summary.substitutes == 1
    assert summary.bill_enactment_rate == 0.5


def test_outcome_groups():
    assert stats.outcome("Enacted") == "Passed"
    assert stats.outcome("Adopted") == "Passed"
    assert stats.outcome("Vetoed") == "Did not pass"
    assert stats.outcome("In Committee") == "In progress"


def test_stage_counts_are_in_pipeline_order(families):
    counts = stats.stage_counts(families)
    assert list(counts["stage"]) == ["In Committee", "Enacted", "Adopted"]
    assert counts["count"].sum() == len(families)


def test_category_breakdown(families):
    table = stats.category_breakdown(families).set_index("category")
    assert table.loc["Education", "total"] == 1
    assert table.loc["Education", "pass_rate"] == 1.0
    assert table.loc["Public Safety & Justice", "passed"] == 0


def test_weekly_introductions_counts_every_item(items):
    weekly = stats.weekly_introductions(items)
    assert weekly["count"].sum() == len(items)
    assert set(weekly["kind"]) <= set(stats.ACTIVITY_KINDS)
    assert (weekly["week"].dt.dayofweek == 0).all()  # weeks start on Monday


def test_cumulative_enactments_only_counts_bills(families):
    cumulative = stats.cumulative_enactments(families)
    assert cumulative["enacted"].tolist() == [1]


def test_top_sponsors(families):
    sponsors = stats.top_sponsors(families)
    assert set(sponsors["sponsor"]) == {"Smith", "Jones"}  # the resolution's sponsor is excluded


def test_family_members_sorted_oldest_first(items):
    members = stats.family_members(items, family_id=1)
    assert members["code"].iloc[0] == "HB 1"
    assert len(members) == 4
    assert members["introduced"].is_monotonic_increasing


def test_monthly_category_activity(families):
    monthly = stats.monthly_category_activity(families)
    assert monthly["count"].sum() == len(families)
    assert (monthly["month"] == pd.Timestamp("2025-01-01")).all()
