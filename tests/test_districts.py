import pytest

from billtracker.districts import AddressNotFound, parse_geocoder_response


def geocoder_payload(state="10", upper="17", lower="32"):
    geographies = {"States": [{"STATE": state}]}
    if upper:
        geographies["2026 State Legislative Districts - Upper"] = [{"BASENAME": upper}]
    if lower:
        geographies["2026 State Legislative Districts - Lower"] = [{"BASENAME": lower}]
    return {"result": {"addressMatches": [
        {"matchedAddress": "411 LEGISLATIVE AVE, DOVER, DE, 19901", "geographies": geographies}
    ]}}


def test_parse_geocoder_response():
    match = parse_geocoder_response(geocoder_payload())
    assert (match.senate_district, match.house_district) == (17, 32)
    assert match.matched_address == "411 LEGISLATIVE AVE, DOVER, DE, 19901"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"result": {"addressMatches": []}}, "couldn't find"),
        (geocoder_payload(state="11"), "isn't in Delaware"),
        (geocoder_payload(lower=None), "Couldn't find the legislative districts"),
    ],
)
def test_parse_geocoder_response_errors(payload, message):
    with pytest.raises(AddressNotFound, match=message):
        parse_geocoder_response(payload)
