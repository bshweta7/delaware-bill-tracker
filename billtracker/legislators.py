"""Legislators: who they are and how long they've served.

The roster comes from a JSON endpoint (see ``legis_api``). A legislator's
profile (years of service, committees, contact details) is only published
as an HTML page, which this module fetches and parses on demand.
"""

import base64
import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import requests
from bs4 import BeautifulSoup

from billtracker import config
from billtracker.legis_api import LegisClient

CHAMBERS = ["Senate", "House"]
TITLES = {"Senate": "Senator", "House": "Representative"}
PARTIES = {"D": "Democrat", "R": "Republican"}
NO_BIOGRAPHY = "Contact for more information"


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


# --------------------------------------------------------------------- profile

@dataclass
class Term:
    chamber: str
    start_year: int
    end_year: int | None  # None while still serving


@dataclass
class Profile:
    email: str | None = None
    phone: str | None = None
    service_text: str | None = None  # as written on the site
    terms: list[Term] = field(default_factory=list)
    committees: list[tuple[str, str]] = field(default_factory=list)  # (committee, role)
    biography: str | None = None
    photo: bytes | None = None

    @property
    def first_elected(self) -> int | None:
        """Year the legislator first joined either chamber, if the site says."""
        return min((term.start_year for term in self.terms), default=None)

    def years_in_office(self, today: date) -> int | None:
        return today.year - self.first_elected if self.first_elected else None


# Service is free text typed by staff, in many styles:
#   "House, 2010 - Present", "House 12/21/2023 - Present", "Senate, February 15, 2025 - Present",
#   "Senate, 2012 to present Senate Minority Leader, 2018 to present House of Representatives, 2002 to 2012"
# Leadership posts ("House Minority Whip, 2010 to 2012") start with a chamber name
# but aren't followed directly by a date, so they don't match.
_TERM = re.compile(
    r"\b(?P<chamber>House of Representatives|House|Senate)\s*,?\s*"
    r"(?:[A-Z][a-z]+\.? \d{1,2},\s*|\d{1,2}/\d{1,2}/)?"  # optional month-day prefix
    r"(?P<start>\d{4})\s*(?:-|–|to)\s*(?P<end>present|\d{4})",
    re.IGNORECASE,
)


def parse_service(text: str | None) -> list[Term]:
    terms = []
    for match in _TERM.finditer(text or ""):
        chamber = "Senate" if match["chamber"].lower() == "senate" else "House"
        end = match["end"]
        terms.append(Term(chamber, int(match["start"]), None if end.lower() == "present" else int(end)))
    return terms


def _section(soup: BeautifulSoup, heading: str):
    for h3 in soup.find_all("h3", class_="section-head"):
        if h3.get_text(strip=True) == heading:
            return h3.find_parent("section")
    return None


def _labeled_value(soup: BeautifulSoup, label_text: str) -> str | None:
    for label_tag in soup.find_all("label"):
        if label_tag.get_text(strip=True) == label_text:
            value = label_tag.find_next_sibling()
            text = value.get_text(" ", strip=True) if value else ""
            return text or None
    return None


def _photo_bytes(soup: BeautifulSoup) -> bytes | None:
    image = soup.find("img", class_="img-avatar")
    source = image.get("src", "") if image else ""
    if not source.startswith("data:") or "base64," not in source:
        return None
    try:
        return base64.b64decode(source.split("base64,", 1)[1])
    except ValueError:
        return None


def parse_profile(html: str) -> Profile:
    soup = BeautifulSoup(html, "html.parser")

    service = _section(soup, "Legislative Service")
    service_text = " ".join(p.get_text(" ", strip=True) for p in service.find_all("p")) if service else ""
    service_text = re.sub(r"\s+", " ", service_text).strip() or None

    committees = []
    committee_section = _section(soup, "Committees")
    for item in committee_section.find_all("li") if committee_section else []:
        link = item.find("a")
        name = link.get_text(" ", strip=True) if link else item.get_text(" ", strip=True)
        role = item.get_text(" ", strip=True).removeprefix(name).strip(" ,") or "Member"
        committees.append((name, role))

    phone = _labeled_value(soup, "Phone")
    biography = _labeled_value(soup, "Biography")
    return Profile(
        email=_labeled_value(soup, "Email"),
        phone=re.sub(r"^.*Phone:\s*", "", phone) if phone else None,
        service_text=service_text,
        terms=parse_service(service_text),
        committees=committees,
        biography=None if biography in (None, NO_BIOGRAPHY) else biography,
        photo=_photo_bytes(soup),
    )


def fetch_profile(person_id: int, session: requests.Session | None = None) -> Profile:
    session = session or requests.Session()
    response = session.get(
        config.legislator_url(person_id),
        headers=config.REQUEST_HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_profile(response.text)
