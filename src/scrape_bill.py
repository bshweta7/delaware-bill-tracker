import requests
from bs4 import BeautifulSoup

BASE_URL = "https://legis.delaware.gov"

headers = {
    "User-Agent": "Mozilla/5.0",
}

def fetch_bill_soup(legislation_id):
    """
    Fetch a Delaware bill detail page and return it as a BeautifulSoup object.

    Args:
        legislation_id: Delaware General Assembly legislation ID.

    Returns:
        BeautifulSoup representation of the bill detail page.
    """
    url = f"{BASE_URL}/BillDetail?LegislationId={legislation_id}"
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
        "legislation_id": legislation_id,
        "bill_name": soup.find("h2").get_text(strip=True),
        "status": get_info_value(soup, "Status:"),
        "introduced_on": get_info_value(soup, "Introduced on:"),
        "long_title": get_info_value(soup, "Long Title:"),
    }


bill = parse_bill(141874)
print(bill)