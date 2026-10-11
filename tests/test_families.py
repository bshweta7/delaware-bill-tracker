import pytest

from billtracker.families import (
    assign_families,
    build_families,
    canonical_code,
    is_substitute,
    parent_code,
    root_code,
)
from billtracker.normalize import normalize_rows


@pytest.mark.parametrize(
    ("display_code", "expected"),
    [
        ("HB 472", "HB 472"),
        ("HB 471 w/ HA 1, HA 2, HA 3", "HB 471"),
        ("HB 445 w/ HA 1 + SA 3", "HB 445"),
        ("HB 442 -HA 1", "HB 442"),
        ("HS 1 for HB 50 w/ HA 1 + SA 1 + HA 2", "HS 1 for HB 50"),
        ("HCR 157 w/ HA 1", "HCR 157"),
    ],
)
def test_canonical_code_strips_attached_amendments(display_code, expected):
    assert canonical_code(display_code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("HB 5", None),
        ("SCR 12", None),
        ("HS 1 for HB 5", "HB 5"),
        ("SA 2 to SB 106", "SB 106"),
        ("HA 1 to HS 1 for HB 1", "HS 1 for HB 1"),
        ("HA 1 to HA 1 to HS 1 for HB 233", "HA 1 to HS 1 for HB 233"),
    ],
)
def test_parent_code(code, expected):
    assert parent_code(code) == expected


def test_root_code_walks_the_whole_chain():
    assert root_code("HA 1 to HA 1 to HS 1 for HB 233") == "HB 233"
    assert root_code("SB 9") == "SB 9"


def test_is_substitute():
    assert is_substitute("SS 1 for SB 5")
    assert not is_substitute("SA 1 to SS 1 for SB 5")
    assert not is_substitute("SB 5")


def test_assign_families_links_every_member_to_the_root(raw_rows):
    items = assign_families(normalize_rows(raw_rows))
    family_of = dict(zip(items["code"], items["family_id"]))
    assert family_of["HB 1"] == 1
    assert family_of["HS 1 for HB 1"] == 1
    assert family_of["HA 1 to HA 1 to HS 1 for HB 1"] == 1
    assert family_of["SB 7"] == 5


def test_build_families_uses_the_live_substitute_as_lead(raw_rows):
    items = assign_families(normalize_rows(raw_rows))
    items["category"] = "Education"
    families = build_families(items).set_index("family_code")

    hb1 = families.loc["HB 1"]
    assert hb1["display_code"] == "HS 1 for HB 1"
    assert hb1["stage"] == "Enacted"
    assert hb1["synopsis"] == "Substitute synopsis."
    # The substitute has no short title, so the original's is used.
    assert hb1["short_title"] == "Example Title"
    assert hb1["substitute_count"] == 1
    assert hb1["amendment_count"] == 2
    assert hb1["introduced"] == items.loc[items["code"] == "HB 1", "introduced"].iloc[0]

    assert len(families) == 3
