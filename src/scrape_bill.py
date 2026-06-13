import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL = "https://legis.delaware.gov"

headers = {
    "User-Agent": "Mozilla/5.0",
}

def get_url(legislation_id):
    return f"{BASE_URL}/BillDetail?LegislationId={legislation_id}"

def fetch_bill_soup(legislation_id):
    """
    Fetch a Delaware bill detail page and return it as a BeautifulSoup object.

    Args:
        legislation_id: Delaware General Assembly legislation ID.

    Returns:
        BeautifulSoup representation of the bill detail page.
    """
    url = get_url(legislation_id)
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_info_value(soup, label_text):
    """
    Extract the value associated with a labeled field on the bill detail page.

    Args:
        soup: BeautifulSoup object containing the bill page.
        label_text: Label text to search for (e.g. 'Status:').

    Returns:
        The associated value as a string, or None if the label is not found.
    """
    labels = soup.find_all("label")

    for label in labels:
        if label_text in label.get_text():
            parent = label.find_parent("div", class_="info-group")
            if parent:
                value = parent.find("div", class_="info-value")
                if value:
                    return value.get_text(" ", strip=True)

    return None

def parse_bill(legislation_id):
    """
    Parse key metadata from a Delaware bill detail page.

    Args:
        legislation_id: Delaware General Assembly legislation ID.

    Returns:
        Dictionary containing extracted bill metadata.
    """
    soup = fetch_bill_soup(legislation_id)

    return {
        "bill_number": soup.find("h2").get_text(strip=True),
        "long_title": get_info_value(soup, "Long Title:"),
        "synopsis": get_info_value(soup, "Original Synopsis:"),
        "primary_sponsor": get_info_value(soup, "Primary Sponsor:"),
        "additional_sponsors": get_info_value(soup, "Additional Sponsor(s):"),
        "cosponsors": get_info_value(soup, "Co-Sponsor(s):"),

        "status": get_info_value(soup, "Status:"),
        "next_step": get_info_value(soup, "What typically happens next?"),
        "effective_date": get_info_value(soup, "Effective Date"),

        "legislation_id": legislation_id,
        "url": get_url(legislation_id),
    }


def print_bill_dict(bill_dict):
    """
        Print a bill metadata dictionary in a readable format.

        Args:
            bill_dict: Dictionary returned by parse_bill().
    """
    for key, value in bill_dict.items():
        print(f"{key.upper()}: {value}")


legis_ids = [
    141874,
    142724
]

bills = []
for legis_id in legis_ids:
    bills.append(parse_bill(legis_id))

df = pd.DataFrame(bills)
print(df)

df.to_csv("bills.csv", index=False)