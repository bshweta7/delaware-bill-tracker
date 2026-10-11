"""Turn raw rows from the All Legislation endpoint into a tidy DataFrame."""

import re

import pandas as pd

from billtracker import config
from billtracker.families import canonical_code
from billtracker.stages import stage_for

LEGISLATION_TYPES = {
    1: "Bill",
    2: "Resolution",
    3: "Concurrent Resolution",
    4: "Joint Resolution",
    5: "Amendment",
    6: "Substitute",
}

_MS_DATE = re.compile(r"/Date\((-?\d+)\)/")
LOCAL_TIMEZONE = "America/New_York"


def parse_ms_date(value: str | None) -> pd.Timestamp | None:
    """'/Date(1782419826587)/' -> a timezone-naive local timestamp, or None."""
    match = _MS_DATE.match(value or "")
    if not match:
        return None
    utc = pd.Timestamp(int(match.group(1)), unit="ms", tz="UTC")
    return utc.tz_convert(LOCAL_TIMEZONE).tz_localize(None)


def chamber_of_origin(code: str) -> str:
    return {"H": "House", "S": "Senate"}.get(code[:1], "Unknown")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def normalize_row(row: dict) -> dict:
    code = canonical_code(row["LegislationDisplayCode"])
    legislation_type = LEGISLATION_TYPES.get(row["LegislationTypeId"], "Other")
    return {
        "legislation_id": row["LegislationId"],
        "assembly": row["AssemblyNumber"],
        "code": code,
        "display_code": row["LegislationDisplayCode"],
        "type": legislation_type,
        "chamber": chamber_of_origin(code),
        "sponsor": row["Sponsor"],
        "short_title": clean_text(row["ShortTitle"]),
        "long_title": clean_text(row["LongTitle"]),
        "synopsis": clean_text(row["Synopsis"]),
        "status": row["StatusName"],
        "stage": stage_for(row["StatusName"], legislation_type),
        "introduced": parse_ms_date(row["IntroductionDateTime"]),
        "last_action": parse_ms_date(row["LegislationStatusDateTime"]),
        "url": config.bill_url(row["LegislationId"]),
    }


def normalize_rows(rows: list[dict]) -> pd.DataFrame:
    items = pd.DataFrame([normalize_row(row) for row in rows])
    for column in ("introduced", "last_action"):
        items[column] = pd.to_datetime(items[column])
    return items
