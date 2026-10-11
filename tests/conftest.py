import pytest

TYPE_IDS = {"Bill": 1, "Resolution": 2, "Concurrent Resolution": 3, "Amendment": 5, "Substitute": 6}


def make_raw_row(
    legislation_id: int,
    display_code: str,
    type_name: str = "Bill",
    status: str = "Signed",
    introduced_ms: int = 1_735_833_600_000,  # 2025-01-02 16:00 UTC
    status_ms: int | None = 1_751_328_000_000,  # 2025-07-01 00:00 UTC
    short_title: str | None = "Example Title",
    long_title: str | None = "AN ACT TO AMEND TITLE 14 OF THE DELAWARE CODE RELATING TO SCHOOLS.",
    synopsis: str | None = "This Act changes school rules.",
    sponsor: str | None = "Smith",
) -> dict:
    """A row shaped like the GetAllLegislation endpoint's JSON."""
    return {
        "LegislationId": legislation_id,
        "LegislationDisplayCode": display_code,
        "LegislationTypeId": TYPE_IDS[type_name],
        "AssemblyNumber": 153,
        "Sponsor": sponsor,
        "ShortTitle": short_title,
        "LongTitle": long_title,
        "Synopsis": synopsis,
        "StatusName": status,
        "IntroductionDateTime": f"/Date({introduced_ms})/",
        "LegislationStatusDateTime": f"/Date({status_ms})/" if status_ms else None,
    }


@pytest.fixture
def raw_rows() -> list[dict]:
    """A small session: one bill with a substitute and amendments, a plain bill, and a resolution."""
    day = 86_400_000
    start = 1_735_833_600_000
    return [
        make_raw_row(1, "HB 1", status="Lieu/Substituted", introduced_ms=start),
        make_raw_row(
            2, "HS 1 for HB 1 w/ HA 1", type_name="Substitute", status="Signed",
            introduced_ms=start + 7 * day, short_title=None, synopsis="Substitute synopsis.",
        ),
        make_raw_row(3, "HA 1 to HS 1 for HB 1", type_name="Amendment", status="Passed",
                     introduced_ms=start + 8 * day, long_title="HA 1 to HS 1 for HB 1", synopsis=None),
        make_raw_row(4, "HA 1 to HA 1 to HS 1 for HB 1", type_name="Amendment", status="Stricken",
                     introduced_ms=start + 9 * day, long_title=None, synopsis=None),
        make_raw_row(
            5, "SB 7", status="Judiciary", introduced_ms=start + 14 * day, status_ms=None,
            short_title="Firearm Storage", sponsor="Jones",
            long_title="AN ACT TO AMEND TITLE 11 OF THE DELAWARE CODE RELATING TO FIREARMS.",
            synopsis="This Act requires safe storage of firearms.",
        ),
        make_raw_row(
            6, "HCR 3", type_name="Concurrent Resolution", status="Passed",
            introduced_ms=start + 15 * day, short_title=None, sponsor="Lee",
            long_title="RECOGNIZING MAY 2025 AS MENTAL HEALTH AWARENESS MONTH.", synopsis=None,
        ),
    ]
