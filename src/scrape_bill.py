import requests

url = "https://legis.delaware.gov/BillDetail?LegislationId=141874"

headers = {
    "User-Agent": "Mozilla/5.0",
}

response = requests.get(url, headers=headers)
html = response.text

# inspect html (temporary)
with open("bill.html", "w", encoding="utf-8") as f:
    f.write(html)
