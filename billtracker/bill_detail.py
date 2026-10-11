"""Scrape fields that only appear on a bill's detail page.

The All Legislation endpoint covers most metadata, but the full sponsor list
and "what typically happens next" are only on ``/BillDetail``. The app fetches
these on demand for the bill a user is looking at.
"""

import requests
from bs4 import BeautifulSoup

from billtracker import config

DETAIL_FIELDS = {
    "primary_sponsor": "Primary Sponsor:",
    "additional_sponsors": "Additional Sponsor(s):",
    "cosponsors": "Co-Sponsor(s):",
    "next_step": "What typically happens next?",
    "effective_date": "Effective Date",
}


def get_info_value(soup: BeautifulSoup, label_text: str) -> str | None:
    """Return the value next to a labeled field on the detail page, or None if absent."""
    for label in soup.find_all("label"):
        if label_text in label.get_text():
            group = label.find_parent("div", class_="info-group")
            value = group.find("div", class_="info-value") if group else None
            if value:
                return value.get_text(" ", strip=True)
    return None


def parse_bill_detail(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    return {field: get_info_value(soup, label) for field, label in DETAIL_FIELDS.items()}


def fetch_bill_detail(legislation_id: int, session: requests.Session | None = None) -> dict:
    session = session or requests.Session()
    response = session.get(
        config.bill_url(legislation_id),
        headers=config.REQUEST_HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_bill_detail(response.text)
