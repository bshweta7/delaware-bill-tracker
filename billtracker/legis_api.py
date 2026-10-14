"""Client for the JSON endpoints behind legis.delaware.gov.

The All Legislation page loads its grid from
``POST /json/AllLegislation/GetAllLegislation``. It is paged (20 rows max per
page) and filtered by General Assembly number.
"""

import re
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from billtracker import config

# The site is slow (several seconds per page) and occasionally times out, so
# retry failed requests with backoff. The listing POST is a read, safe to repeat.
RETRY_POLICY = Retry(
    total=4,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=None,  # retry POST too
)


class LegisApiError(RuntimeError):
    """Raised when the site returns something other than the expected JSON."""


class LegisClient:
    def __init__(self, session: requests.Session | None = None, max_workers: int = 4):
        if session is None:
            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=RETRY_POLICY))
        self.session = session
        self.session.headers.update(config.REQUEST_HEADERS)
        self.max_workers = max_workers

    def current_assembly_id(self) -> int:
        """Read the current General Assembly number from the All Legislation page."""
        response = self.session.get(
            config.ALL_LEGISLATION_PAGE, timeout=config.REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        match = re.search(
            r'id="SelectedGeneralAssemblyId"[^>]*value="(\d+)"', response.text
        )
        if not match:
            raise LegisApiError("Could not find the current General Assembly id.")
        return int(match.group(1))

    def _post_grid(self, url: str, data: dict, description: str) -> dict:
        """POST to one of the site's grid endpoints and return its ``{"Data", "Total"}`` payload."""
        # `sort` must be present (even empty) or the server redirects to an error page.
        response = self.session.post(
            url,
            data={"sort": "", **data},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as error:
            raise LegisApiError(
                f"{description} returned non-JSON (HTTP {response.status_code})."
            ) from error
        if payload.get("Errors"):
            raise LegisApiError(f"{description} returned errors: {payload['Errors']}")
        return payload

    def fetch_page(self, assembly_id: int, page: int) -> dict:
        """Fetch one page of legislation. Returns the raw ``{"Data", "Total"}`` payload."""
        return self._post_grid(
            config.ALL_LEGISLATION_URL,
            {"page": page, "pageSize": config.PAGE_SIZE, "selectedGA": assembly_id},
            f"Page {page}",
        )

    def fetch_all_legislation(self, assembly_id: int) -> list[dict]:
        """Fetch every piece of legislation (bills, resolutions, amendments...) in a session."""
        first_page = self.fetch_page(assembly_id, 1)
        total = first_page["Total"]
        page_count = -(-total // config.PAGE_SIZE)  # ceiling division

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            later_pages = pool.map(
                lambda page: self.fetch_page(assembly_id, page)["Data"],
                range(2, page_count + 1),
            )
            rows = first_page["Data"] + [row for page in later_pages for row in page]

        # De-duplicate in case rows shift between pages while we are fetching.
        unique_rows = {row["LegislationId"]: row for row in rows}
        return list(unique_rows.values())

    def fetch_legislators(self, chamber: str) -> list[dict]:
        """The current members of one chamber ("Senate" or "House"), one row per district."""
        payload = self._post_grid(
            config.LEGISLATOR_ROSTER_URLS[chamber],
            {"page": 1, "pageSize": 100},
            f"{chamber} roster",
        )
        if len(payload["Data"]) < payload["Total"]:
            raise LegisApiError(
                f"The {chamber} roster was truncated ({len(payload['Data'])} of {payload['Total']} rows)."
            )
        return payload["Data"]

    def fetch_sponsored_legislation(self, person_id: int, assembly_id: int) -> list[dict]:
        """Everything a legislator sponsored or co-sponsored in a session.

        Unlike the All Legislation endpoint, this one honors large page sizes.
        """
        payload = self._post_grid(
            config.SPONSORED_LEGISLATION_URL,
            {"page": 1, "pageSize": 2000, "personId": person_id, "assemblyId": assembly_id},
            f"Sponsored legislation for person {person_id}",
        )
        if len(payload["Data"]) < payload["Total"]:
            raise LegisApiError(
                f"Sponsored legislation for person {person_id} was truncated "
                f"({len(payload['Data'])} of {payload['Total']} rows)."
            )
        return payload["Data"]
