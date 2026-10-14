from types import SimpleNamespace

import pytest

from billtracker.bill_detail import parse_bill_detail
from billtracker.legis_api import LegisApiError, LegisClient


class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200):
        self.payload = payload
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


class FakeSession:
    """Serves 45 rows of legislation across 20-row pages."""

    def __init__(self, total=45):
        self.headers = {}
        self.rows = [{"LegislationId": i} for i in range(total)]
        self.requested_pages = []

    def post(self, url, data, **kwargs):
        page = data["page"]
        self.requested_pages.append(page)
        start = (page - 1) * 20
        return FakeResponse({"Data": self.rows[start:start + 20], "Total": len(self.rows), "Errors": None})

    def get(self, url, **kwargs):
        return FakeResponse(text='<input id="SelectedGeneralAssemblyId" type="hidden" value="153" />')


def test_fetch_all_legislation_reads_every_page():
    session = FakeSession(total=45)
    rows = LegisClient(session=session).fetch_all_legislation(153)
    assert sorted(row["LegislationId"] for row in rows) == list(range(45))
    assert sorted(session.requested_pages) == [1, 2, 3]


def test_current_assembly_id():
    assert LegisClient(session=FakeSession()).current_assembly_id() == 153


def test_non_json_response_raises():
    session = FakeSession()
    session.post = lambda *args, **kwargs: FakeResponse(payload=None, status_code=302)
    with pytest.raises(LegisApiError):
        LegisClient(session=session).fetch_page(153, 1)


def test_parse_bill_detail():
    html = """
    <div class="info-group"><label>Primary Sponsor:</label><div class="info-value">Rep. Smith</div></div>
    <div class="info-group"><label>Co-Sponsor(s):</label><div class="info-value"><a>Sen. Jones</a><a>Sen. Lee</a></div></div>
    """
    detail = parse_bill_detail(html)
    assert detail["primary_sponsor"] == "Rep. Smith"
    assert detail["cosponsors"] == "Sen. Jones Sen. Lee"
    assert detail["next_step"] is None


class GridSession:
    """Serves one fixed payload for every grid POST and records the form data."""

    def __init__(self, payload):
        self.headers = {}
        self.payload = payload
        self.posts = []

    def post(self, url, data, **kwargs):
        self.posts.append((url, data))
        return FakeResponse(self.payload)


def test_fetch_legislators_uses_the_chamber_endpoint():
    session = GridSession({"Data": [{"PersonId": 1}], "Total": 1, "Errors": None})
    assert LegisClient(session=session).fetch_legislators("Senate") == [{"PersonId": 1}]
    url, data = session.posts[0]
    assert url.endswith("/json/Senate/GetSenators")
    assert data["sort"] == ""  # the site errors without it


def test_fetch_sponsored_legislation():
    rows = [{"LegislationId": 1, "SponsorTypeName": "CoSponsor"}]
    session = GridSession({"Data": rows, "Total": 1, "Errors": None})
    assert LegisClient(session=session).fetch_sponsored_legislation(10, 153) == rows
    assert session.posts[0][1] | {"pageSize": None} == {
        "sort": "", "page": 1, "pageSize": None, "personId": 10, "assemblyId": 153,
    }


def test_fetch_sponsored_legislation_rejects_truncated_results():
    rows = [{"LegislationId": 1, "SponsorTypeName": "CoSponsor"}]
    session = GridSession({"Data": rows, "Total": 5, "Errors": None})
    with pytest.raises(LegisApiError, match="truncated"):
        LegisClient(session=session).fetch_sponsored_legislation(10, 153)
