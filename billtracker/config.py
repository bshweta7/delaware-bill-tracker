"""Project-wide settings: site URLs and file locations."""

from pathlib import Path

BASE_URL = "https://legis.delaware.gov"
ALL_LEGISLATION_URL = f"{BASE_URL}/json/AllLegislation/GetAllLegislation"
ALL_LEGISLATION_PAGE = f"{BASE_URL}/AllLegislation"
LEGISLATOR_ROSTER_URLS = {
    "Senate": f"{BASE_URL}/json/Senate/GetSenators",
    "House": f"{BASE_URL}/json/House/GetRepresentatives",
}
SPONSORED_LEGISLATION_URL = f"{BASE_URL}/json/AssemblyMember/GetSponsoredLegislation"
ROLL_CALL_FEED_URL = f"{BASE_URL}/rss/RssFeeds/RollCalls"

# Free, keyless US Census geocoder; returns state legislative districts for an address.
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"

# The site ignores larger page sizes and always returns at most 20 rows.
PAGE_SIZE = 20
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (delaware-bill-tracker)"}
REQUEST_TIMEOUT_SECONDS = 60

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LEGISLATION_CSV = DATA_DIR / "legislation.csv"


def bill_url(legislation_id: int) -> str:
    return f"{BASE_URL}/BillDetail?LegislationId={legislation_id}"


def legislator_url(person_id: int) -> str:
    return f"{BASE_URL}/LegislatorDetail?personId={person_id}"
