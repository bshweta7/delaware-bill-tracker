import requests
from bs4 import BeautifulSoup

url = "https://legis.delaware.gov/BillDetail?LegislationId=141874"

headers = {
    "User-Agent": "Mozilla/5.0",
}

response = requests.get(url, headers=headers)
html = response.text
soup = BeautifulSoup(html, "html.parser")


def get_info_value(soup, label_text):
    labels = soup.find_all("label")

    for label in labels:
        if label_text in label.get_text():
            parent = label.find_parent("div", class_="info-group")
            if parent:
                value = parent.find("div", class_="info-value")
                if value:
                    return value.get_text(" ", strip=True)

    return None

bill = {
    "bill_name": soup.find("h2").get_text(strip=True),
    "status": get_info_value(soup, "Status:"),
    "introduced_on": get_info_value(soup, "Introduced on:"),
    "long_title": get_info_value(soup, "Long Title:")
}

print(bill)