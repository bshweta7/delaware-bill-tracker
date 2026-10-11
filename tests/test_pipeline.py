import pandas as pd

from billtracker import pipeline, storage
from billtracker.normalize import normalize_row, parse_ms_date
from tests.conftest import make_raw_row


def test_parse_ms_date_converts_to_delaware_time():
    # 2025-07-01 03:00 UTC is 2025-06-30 23:00 in Delaware (EDT).
    assert parse_ms_date("/Date(1751338800000)/") == pd.Timestamp("2025-06-30 23:00")
    assert parse_ms_date(None) is None
    assert parse_ms_date("not a date") is None


def test_normalize_row():
    row = normalize_row(make_raw_row(9, "SS 1 for SB 5 w/ HA 1", type_name="Substitute", status="Passed House"))
    assert row["code"] == "SS 1 for SB 5"
    assert row["display_code"] == "SS 1 for SB 5 w/ HA 1"
    assert row["type"] == "Substitute"
    assert row["chamber"] == "Senate"
    assert row["stage"] == "Passed One Chamber"
    assert row["url"].endswith("LegislationId=9")


def test_build_items_links_and_categorizes(raw_rows):
    items = pipeline.build_items(raw_rows)
    assert list(items.columns) == pipeline.CSV_COLUMNS

    items = items.set_index("code")
    # Amendments inherit their family's category rather than being categorized alone.
    assert items.loc["HA 1 to HS 1 for HB 1", "category"] == "Education"
    assert items.loc["SB 7", "category"] == "Public Safety & Justice"
    assert items.loc["HCR 3", "category"] == "Ceremonial & Recognition"
    assert items.loc["HA 1 to HS 1 for HB 1", "family_code"] == "HB 1"


def test_csv_round_trip(raw_rows, tmp_path):
    path = tmp_path / "legislation.csv"
    storage.save_items(pipeline.build_items(raw_rows), path)

    items = storage.load_items(path)
    families = storage.load_families(path)

    assert len(items) == len(raw_rows)
    assert pd.api.types.is_datetime64_any_dtype(items["introduced"])
    assert set(families["family_code"]) == {"HB 1", "SB 7", "HCR 3"}


def test_load_watchlist_ignores_blanks_and_comments(tmp_path):
    path = tmp_path / "watchlist.txt"
    path.write_text("142655\n\n# a comment\n142724  # inline note\n")
    assert storage.load_watchlist(path) == {142655, 142724}
    assert storage.load_watchlist(tmp_path / "missing.txt") == set()
