"""Run the dashboard's Your legislators tab against stubbed data, with no network."""

from datetime import date

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from billtracker import config, districts, legislators, pipeline, storage, summaries
from billtracker.districts import DistrictMatch
from tests.test_legislators import ROLL_CALL_RSS, roster_row

APP = str(config.PROJECT_ROOT / "app.py")


class Stubs:
    """What the stubbed network calls return; tests override fields to simulate failures."""

    def __init__(self):
        self.roster = pd.DataFrame([
            legislators.tidy_roster_row(roster_row(17, person_id=10, name="Jane Doe"), "Senate"),
            legislators.tidy_roster_row(roster_row(32, person_id=20, name="John Roe"), "House"),
        ])
        self.profile = legislators.Profile(
            email="Jane.Doe@delaware.gov",
            service_text="House, 2012 to 2018 Senate, 2018 to present",
            terms=legislators.parse_service("House, 2012 to 2018 Senate, 2018 to present"),
            committees=[("Education", "Chair")],
        )
        self.sponsorships = legislators.tidy_sponsorships([
            {"LegislationId": 2, "SponsorTypeName": "Primary Sponsor"},
            {"LegislationId": 5, "SponsorTypeName": "CoSponsor"},
        ])
        self.votes = legislators.parse_roll_calls(ROLL_CALL_RSS)
        self.match = DistrictMatch("411 LEGISLATIVE AVE, DOVER, DE, 19901", 17, 32)
        self.address_lookups = []

    @staticmethod
    def _result(value):
        if isinstance(value, Exception):
            raise value
        return value

    def find_districts(self, address):
        self.address_lookups.append(address)
        return self._result(self.match)


# The real loaders, captured before tests patch them to read from a temporary directory.
_load_items = storage.load_items
_SummaryStore = summaries.SummaryStore


@pytest.fixture
def stubs(monkeypatch, tmp_path, raw_rows):
    csv = tmp_path / "legislation.csv"
    storage.save_items(pipeline.build_items(raw_rows), csv)
    monkeypatch.setattr(config, "LEGISLATION_CSV", csv)
    monkeypatch.setattr(storage, "load_items", lambda: _load_items(csv))
    monkeypatch.setattr(storage, "load_watchlist", lambda: set())
    monkeypatch.setattr(summaries, "SummaryStore", lambda: _SummaryStore(tmp_path / "summaries.json"))

    stubs = Stubs()
    monkeypatch.setattr(legislators, "roster", lambda: stubs._result(stubs.roster))
    monkeypatch.setattr(legislators, "fetch_profile", lambda person_id: stubs._result(stubs.profile))
    monkeypatch.setattr(legislators, "sponsored_legislation",
                        lambda person_id, assembly_id: stubs._result(stubs.sponsorships))
    monkeypatch.setattr(legislators, "fetch_roll_calls",
                        lambda person_id, assembly_id: stubs._result(stubs.votes))
    monkeypatch.setattr(districts, "find_districts", stubs.find_districts)
    st.cache_data.clear()  # cached results would otherwise leak between tests
    yield stubs
    st.cache_data.clear()


def run_app() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception, app.exception
    return app


def look_up_address(app: AppTest, address: str = "411 Legislative Ave, Dover, DE") -> AppTest:
    next(box for box in app.text_input if box.label == "Home address").input(address)
    next(button for button in app.button if button.label == "Find my legislators").click()
    app.run()
    assert not app.exception, app.exception
    return app


def pick_from_list(app: AppTest, senate: int | None = None, house: int | None = None) -> AppTest:
    app.segmented_control[0].set_value("Pick from a list").run()
    senate_box, house_box = (box for box in app.selectbox if box.label.startswith("Your state"))
    senate_box.set_value(senate)
    house_box.set_value(house)
    app.run()
    assert not app.exception, app.exception
    return app


def texts(app: AppTest) -> str:
    """Every piece of visible text, for substring checks."""
    elements = [*app.markdown, *app.caption, *app.subheader, *app.info, *app.warning, *app.error]
    return "\n".join(element.value for element in elements)


def metrics(app: AppTest) -> dict[str, tuple[str, str]]:
    return {metric.label: (metric.value, metric.delta) for metric in app.metric}


def test_address_lookup_shows_both_legislators(stubs):
    app = look_up_address(run_app())
    assert stubs.address_lookups == ["411 Legislative Ave, Dover, DE"]
    shown = texts(app)
    assert "Senator Jane Doe" in shown
    assert "Representative John Roe" in shown


def test_district_missing_from_roster_warns_instead_of_crashing(stubs):
    stubs.match = DistrictMatch("1 MAIN ST, DOVER, DE, 19901", 17, 33)  # no House District 33 in the roster
    app = look_up_address(run_app())
    shown = texts(app)
    assert "Couldn't find who represents House District 33" in shown
    assert "Senator Jane Doe" in shown  # the senator still shows
    assert "didn't list a House member for districts" in shown  # the stub roster is incomplete


def test_years_served_skips_a_break_in_service(stubs):
    service = "House of Representatives, 2002 to 2006 Senate, 2010 to present"
    stubs.profile = legislators.Profile(service_text=service, terms=legislators.parse_service(service))
    first_took_office, served = metrics(pick_from_list(run_app(), senate=17))["First took office"]
    assert first_took_office == "2002"
    assert served == f"{date.today().year - 2010 + 4} years served"  # 2002-2006, then 2010 on
