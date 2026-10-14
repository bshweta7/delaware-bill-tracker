import base64
from datetime import date

import pandas as pd
import pytest

from billtracker import legislators, pipeline, stats
from billtracker.families import build_families
from billtracker.legis_api import LegisApiError, LegisClient


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


def full_roster() -> pd.DataFrame:
    return pd.DataFrame(
        [legislators.tidy_roster_row(roster_row(d, person_id=d), "Senate") for d in range(1, 22)]
        + [legislators.tidy_roster_row(roster_row(d, person_id=100 + d), "House") for d in range(1, 42)]
    )


def test_missing_districts():
    seats = full_roster()
    assert legislators.missing_districts(seats) == {}
    gappy = seats.drop(seats[(seats["chamber"] == "House") & seats["district"].isin([4, 40])].index)
    assert legislators.missing_districts(gappy) == {"House": [4, 40]}


def test_find_seat():
    seats = full_roster()
    assert legislators.find_seat(seats, "House", 41)["person_id"] == 141
    assert legislators.find_seat(seats, "Senate", 22) is None


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


# ------------------------------------------------------------------ roll calls

ROLL_CALL_RSS = """<rss version="2.0"><channel>
<item>
  <guid isPermaLink="false">101</guid>
  <link>https://legis.delaware.gov/BillDetail?legislationId=2</link>
  <category>Vote Type - No</category>
  <title>HS 1 for HB 1 w/ HA 1</title>
  <description><![CDATA[AN ACT RELATING TO SCHOOLS.<br><br>Voted: N<br>Pass Req.: SM<br>Yes: 30<br>No: 9<br>Absent: 2<br>N/V: 0]]></description>
  <pubDate>Wed, 01 Jul 2026 05:32:47 -0400</pubDate>
</item>
<item>
  <guid isPermaLink="false">100</guid>
  <link>https://legis.delaware.gov/Nomination?nominationId=7</link>
  <category>Vote Type - Absent</category>
  <title>Pat Smith</title>
  <description><![CDATA[PatSmith]]></description>
  <pubDate>Tue, 30 Jun 2026 15:00:00 -0400</pubDate>
</item>
<item>
  <guid isPermaLink="false">99</guid>
  <link>https://legis.delaware.gov/BillDetail?legislationId=5</link>
  <category>Vote Type - Yes</category>
  <title>SB 7</title>
  <description><![CDATA[AN ACT RELATING TO FIREARMS.<br><br>Voted: Y<br>Yes: 21<br>No: 0<br>Absent: 0]]></description>
  <pubDate>Mon, 29 Jun 2026 12:00:00 -0400</pubDate>
</item>
</channel></rss>"""


def test_parse_roll_calls():
    votes = legislators.parse_roll_calls(ROLL_CALL_RSS)
    assert list(votes["roll_call_id"]) == [101, 100, 99]  # newest first
    first = votes.iloc[0]
    assert first["vote"] == "No"
    assert first["legislation_id"] == 2
    assert first["kind"] == "Legislation"
    assert first["title"] == "AN ACT RELATING TO SCHOOLS."
    assert (first["total_yes"], first["total_no"], first["total_absent"]) == (30, 9, 2)
    assert first["date"] == pd.Timestamp("2026-07-01 05:32:47")

    nomination = votes.iloc[1]
    assert nomination["kind"] == "Nomination"
    assert nomination["title"] == "Confirm Pat Smith"
    assert pd.isna(nomination["legislation_id"])


def test_vote_record():
    record = stats.vote_record(legislators.parse_roll_calls(ROLL_CALL_RSS), legislators.MISSED_VOTES)
    assert record.roll_calls == 3
    assert record.counts == {"No": 1, "Absent": 1, "Yes": 1}
    assert record.missed == 1
    assert record.participation_rate == pytest.approx(2 / 3)


class FlakyFeedSession:
    """Answers with the site's HTML error page a few times before the real feed."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        response = FakeResponse(None)
        if self.calls <= self.failures:
            response.headers, response.text = {"Content-Type": "text/html"}, "<html><title>Page not found</title>"
        else:
            response.headers, response.text = {"Content-Type": "application/xml"}, ROLL_CALL_RSS
        return response


def test_fetch_roll_calls_retries_error_pages():
    session = FlakyFeedSession(failures=2)
    votes = legislators.fetch_roll_calls(10, 153, session=session, retry_delay=0)
    assert len(votes) == 3
    assert session.calls == 3


def test_fetch_roll_calls_gives_up_without_a_final_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(legislators.time, "sleep", sleeps.append)
    session = FlakyFeedSession(failures=legislators.FEED_ATTEMPTS)
    with pytest.raises(LegisApiError, match="error page"):
        legislators.fetch_roll_calls(10, 153, session=session, retry_delay=1)
    assert session.calls == legislators.FEED_ATTEMPTS
    assert sleeps == [1, 2, 4, 8]  # backoff between attempts, none after the last


# ------------------------------------------------------------------- elections

@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 14), date(2026, 11, 3)),
        (date(2026, 11, 3), date(2026, 11, 3)),   # election day itself
        (date(2026, 11, 4), date(2028, 11, 7)),
        (date(2027, 3, 1), date(2028, 11, 7)),
        (date(2030, 1, 1), date(2030, 11, 5)),
    ],
)
def test_next_general_election(today, expected):
    assert legislators.next_general_election(today) == expected
