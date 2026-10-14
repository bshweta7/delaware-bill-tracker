"""Find a Delaware address's state Senate and House districts.

Uses the US Census Bureau geocoder, which is free, needs no API key, and returns
the current state legislative districts for a matched address in one request.
"""

from dataclasses import dataclass

import requests

from billtracker import config

DELAWARE_FIPS = "10"
UPPER_LAYER = "State Legislative Districts - Upper"  # Senate
LOWER_LAYER = "State Legislative Districts - Lower"  # House


class AddressNotFound(ValueError):
    """The geocoder couldn't match the address, or it isn't in Delaware."""


@dataclass(frozen=True)
class DistrictMatch:
    matched_address: str
    senate_district: int
    house_district: int


def _district(geographies: dict, layer_suffix: str) -> int | None:
    # Layer names carry the vintage year ("2026 State Legislative Districts - Upper").
    for name, features in geographies.items():
        if name.endswith(layer_suffix) and features:
            return int(features[0]["BASENAME"])
    return None


def parse_geocoder_response(payload: dict) -> DistrictMatch:
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        raise AddressNotFound("We couldn't find that address. Check the street, town and ZIP code.")
    match = matches[0]
    geographies = match.get("geographies", {})
    states = geographies.get("States", [])
    if not states or states[0].get("STATE") != DELAWARE_FIPS:
        raise AddressNotFound(f"{match['matchedAddress']} isn't in Delaware.")
    senate = _district(geographies, UPPER_LAYER)
    house = _district(geographies, LOWER_LAYER)
    if senate is None or house is None:
        raise AddressNotFound(f"Couldn't find the legislative districts for {match['matchedAddress']}.")
    return DistrictMatch(match["matchedAddress"], senate, house)


def find_districts(address: str, session: requests.Session | None = None) -> DistrictMatch:
    session = session or requests.Session()
    response = session.get(
        config.CENSUS_GEOCODER_URL,
        params={
            "address": address,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "layers": "all",
            "format": "json",
        },
        headers=config.REQUEST_HEADERS,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_geocoder_response(response.json())
