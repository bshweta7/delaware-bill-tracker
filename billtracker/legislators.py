"""Legislators: who represents each district."""

import re

import pandas as pd

from billtracker import config
from billtracker.legis_api import LegisClient

CHAMBERS = ["Senate", "House"]
TITLES = {"Senate": "Senator", "House": "Representative"}
PARTIES = {"D": "Democrat", "R": "Republican"}


# ---------------------------------------------------------------------- roster

def roster(client: LegisClient | None = None) -> pd.DataFrame:
    """Every current seat in both chambers, one row per district (vacant seats included)."""
    client = client or LegisClient()
    rows = [
        tidy_roster_row(row, chamber)
        for chamber in CHAMBERS
        for row in client.fetch_legislators(chamber)
    ]
    return pd.DataFrame(rows).sort_values(["chamber", "district"]).reset_index(drop=True)


def tidy_roster_row(row: dict, chamber: str) -> dict:
    person_id = row["PersonId"]
    name = re.sub(r"\s+", " ", row["PersonFullName"] or "").strip() or None
    return {
        "person_id": person_id,
        "name": name or "Vacant",
        "last_name": (row["PersonLastName"] or "").strip() or None,
        "chamber": chamber,
        "district": int(row["DistrictNumber"]),
        "party": row["PartyCode"],
        "role": row["MemberTypeName"] if row["IsLeadershipRole"] else None,
        "profile_url": config.legislator_url(person_id) if person_id else None,
        "caucus_url": row["LegislatorDetailLink"],
    }


def label(member: pd.Series | dict) -> str:
    """'Sen. Trey Paradee (D), District 17'"""
    prefix = "Sen." if member["chamber"] == "Senate" else "Rep."
    party = f" ({member['party']})" if isinstance(member["party"], str) else ""
    return f"{prefix} {member['name']}{party}, District {member['district']}"
