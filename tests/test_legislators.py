from billtracker import legislators
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
