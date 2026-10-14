import base64
from datetime import date

import pytest

from billtracker import legislators, pipeline, stats
from billtracker.families import build_families
from billtracker.legis_api import LegisClient


# ---------------------------------------------------------------------- roster

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def roster_row(district, person_id=10, name="Jane  Q. Doe", party="D", leader=False):
    return {
        "PersonId": person_id, "PersonFullName": name, "PersonLastName": "Doe",
        "DistrictNumber": district, "PartyCode": party, "IsLeadershipRole": leader,
        "MemberTypeName": "Majority Whip" if leader else "Senator",
        "LegislatorDetailLink": "https://example.org/caucus",
    }


class RosterSession:
    headers = {}

    def post(self, url, data, **kwargs):
        if "GetSenators" in url:
            return FakeResponse({"Data": [roster_row(2, leader=True), roster_row(1, person_id=11)], "Total": 2})
        return FakeResponse({"Data": [roster_row(1, person_id=None, name=None, party=None)], "Total": 1})


def test_roster():
    seats = legislators.roster(LegisClient(session=RosterSession()))
    assert list(zip(seats["chamber"], seats["district"])) == [("House", 1), ("Senate", 1), ("Senate", 2)]
    vacant, _, leader = (row for _, row in seats.iterrows())
    assert vacant["name"] == "Vacant"
    assert legislators.label(vacant) == "Rep. Vacant, District 1"
    assert leader["name"] == "Jane Q. Doe"
    assert leader["role"] == "Majority Whip"
    assert leader["profile_url"] == "https://legis.delaware.gov/LegislatorDetail?personId=10"
    assert legislators.label(leader) == "Sen. Jane Q. Doe (D), District 2"


# --------------------------------------------------------------------- profile

PHOTO = b"\x89PNG fake image bytes"

PROFILE_HTML = f"""
<h2>Senator Jane Q. Doe (D)</h2>
<img class="img-avatar" src="data:image;base64,{base64.b64encode(PHOTO).decode()}" />
<div><label>Address</label><div>411 Legislative Ave.</div></div>
<div class="info-phone"><label>Phone</label><div>Leghall Phone: 302-744-4000</div></div>
<div class="info-group"><label>Email</label><div><a>Jane.Doe@delaware.gov</a></div></div>
<section><h3 class="section-head">Legislative Service</h3>
  <p>Senate, 2018 to present Senate Majority Whip, 2020 to present House of Representatives, 2012 to 2018</p>
</section>
<section><h3 class="section-head">Background</h3>
  <div><label class="info-label">Biography</label><div>Sen. Doe represents the 99th District.</div></div>
</section>
<section><h3 class="section-head">Committees</h3>
  <ul class="content-list">
    <li><a href="/CommitteeDetail/1">Elections &amp; Government Affairs</a>, Chair</li>
    <li><a href="/JointFinance">Joint Finance</a>, Member</li>
  </ul>
</section>
"""


@pytest.mark.parametrize(
    "text, expected",
    [
        ("House, 2010 - Present", [("House", 2010, None)]),
        ("House 12/21/2023 - Present", [("House", 2023, None)]),
        ("House,\xa02018 - present", [("House", 2018, None)]),
        ("House of Representatives, 2024 - Present", [("House", 2024, None)]),
        ("Senate, February 15, 2025 - Present", [("Senate", 2025, None)]),
        (
            "Senate, 2012 to present Senate Minority Leader, 2018 to present "
            "House of Representatives, 2002 to 2012 House Minority Whip, 2010 to 2012",
            [("Senate", 2012, None), ("House", 2002, 2012)],
        ),
        ("Contact for more information", []),
        (None, []),
    ],
)
def test_parse_service(text, expected):
    terms = legislators.parse_service(text)
    assert [(t.chamber, t.start_year, t.end_year) for t in terms] == expected


def test_parse_profile():
    profile = legislators.parse_profile(PROFILE_HTML)
    assert profile.email == "Jane.Doe@delaware.gov"
    assert profile.phone == "302-744-4000"
    assert profile.first_elected == 2012
    assert profile.years_in_office(date(2026, 10, 14)) == 14
    assert profile.committees == [("Elections & Government Affairs", "Chair"), ("Joint Finance", "Member")]
    assert profile.biography == "Sen. Doe represents the 99th District."
    assert profile.photo == PHOTO


def test_parse_profile_without_details():
    html = PROFILE_HTML.replace("Sen. Doe represents the 99th District.", legislators.NO_BIOGRAPHY)
    html = html.replace('src="data:image', 'src="/placeholder.png" data-x="')
    profile = legislators.parse_profile(html)
    assert profile.biography is None
    assert profile.photo is None


# ---------------------------------------------------------------- sponsorships

@pytest.fixture
def items(raw_rows):
    return pipeline.build_items(raw_rows)


def test_sponsored_families_collapses_a_family_to_its_strongest_role(items):
    families = build_families(items)
    sponsorships = legislators.tidy_sponsorships([
        {"LegislationId": 1, "SponsorTypeName": "CoSponsor"},        # HB 1
        {"LegislationId": 2, "SponsorTypeName": "Primary Sponsor"},  # HS 1 for HB 1
        {"LegislationId": 5, "SponsorTypeName": "CoSponsor"},        # SB 7
        {"LegislationId": 999, "SponsorTypeName": "CoSponsor"},      # not in our data
    ])
    sponsored = stats.sponsored_families(sponsorships, items, families)
    assert dict(zip(sponsored["family_code"], sponsored["role"])) == {"HB 1": "Primary sponsor", "SB 7": "Co-sponsor"}

    record = stats.sponsor_record(sponsored)
    assert (record.primary, record.primary_passed, record.cosponsored) == (1, 1, 1)
    assert record.primary_pass_rate == 1.0
