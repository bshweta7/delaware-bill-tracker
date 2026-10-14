"""Project-wide settings: site URLs, file locations, and model choices."""

from pathlib import Path

BASE_URL = "https://legis.delaware.gov"
ALL_LEGISLATION_URL = f"{BASE_URL}/json/AllLegislation/GetAllLegislation"
ALL_LEGISLATION_PAGE = f"{BASE_URL}/AllLegislation"
LEGISLATOR_ROSTER_URLS = {
    "Senate": f"{BASE_URL}/json/Senate/GetSenators",
    "House": f"{BASE_URL}/json/House/GetRepresentatives",
}
SPONSORED_LEGISLATION_URL = f"{BASE_URL}/json/AssemblyMember/GetSponsoredLegislation"

# The site ignores larger page sizes and always returns at most 20 rows.
PAGE_SIZE = 20
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (delaware-bill-tracker)"}
REQUEST_TIMEOUT_SECONDS = 60

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LEGISLATION_CSV = DATA_DIR / "legislation.csv"
SUMMARIES_JSON = DATA_DIR / "summaries.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.txt"

SUMMARY_MODEL = "claude-opus-5-5"


def bill_url(legislation_id: int) -> str:
    return f"{BASE_URL}/BillDetail?LegislationId={legislation_id}"
