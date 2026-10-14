"""Your Delaware Legislators: find your state senator and representative and see their record.

    streamlit run app.py
"""

from datetime import date

import pandas as pd
import streamlit as st

from billtracker import __version__, charts, config, legislators, stats
from billtracker.districts import AddressNotFound, find_districts
from billtracker.families import build_families
from billtracker.storage import load_items

st.set_page_config(page_title="Your Delaware Legislators", page_icon="🏛️", layout="wide")


# ---------------------------------------------------------------- data loading

@st.cache_data(show_spinner="Loading legislation…")
def load_data(csv_mtime: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load items and families. `csv_mtime` is only a cache key, so a refresh reloads."""
    items = load_items()
    return items, build_families(items)


@st.cache_data(show_spinner="Loading legislators…", ttl=86400)
def cached_roster() -> pd.DataFrame:
    return legislators.roster()


@st.cache_data(show_spinner="Loading legislator profile…", ttl=86400)
def cached_profile(person_id: int) -> legislators.Profile:
    return legislators.fetch_profile(person_id)


@st.cache_data(show_spinner="Loading sponsored legislation…", ttl=3600)
def cached_sponsorships(person_id: int, assembly_id: int) -> tuple[pd.DataFrame, pd.Timestamp]:
    """The legislator's sponsorships, and when they were fetched."""
    return legislators.sponsored_legislation(person_id, assembly_id), now_local()


@st.cache_data(show_spinner="Loading roll call votes…", ttl=3600)
def cached_roll_calls(person_id: int, assembly_id: int) -> tuple[pd.DataFrame, pd.Timestamp]:
    """The legislator's roll call votes, and when they were fetched."""
    return legislators.fetch_roll_calls(person_id, assembly_id), now_local()


def now_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/New_York")


def as_of(timestamp: pd.Timestamp) -> str:
    return f"{timestamp.tz_convert('America/New_York'):%b %d, %Y %I:%M %p}"


def theme_mode() -> str:
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", None) or "light"


if not config.LEGISLATION_CSV.exists():
    st.title("Your Delaware Legislators")
    st.info("This site's bill data isn't available right now. Please check back later.")
    st.stop()

items, families = load_data(config.LEGISLATION_CSV.stat().st_mtime)
refreshed = pd.Timestamp(config.LEGISLATION_CSV.stat().st_mtime, unit="s", tz="UTC")
mode = theme_mode()
assembly = int(items["assembly"].iloc[0])


# ------------------------------------------------------------------------ page

BILL_TABLE_COLUMNS = {
    "display_code": "Legislation",
    "short_title": st.column_config.TextColumn("Title", width="large"),
    "category": "Category",
    "stage": "Stage",
    "last_action": st.column_config.DateColumn("Last action", format="MMM D, YYYY"),
    "url": st.column_config.LinkColumn("Link", display_text="Open"),
}


ADDRESS_PRIVACY = (
    "Your address is sent over HTTPS to the US Census Bureau's geocoder, which returns your "
    "districts; the Census Bureau's own privacy policy covers what it keeps. This app doesn't "
    "save your address to disk, log it or cache it for other visitors. It stays in memory only "
    "for your browser session, so the form and result keep showing, and is discarded when the session "
    "ends, shortly after you close the tab."
)


def choose_districts(seats: pd.DataFrame) -> tuple[int | None, int | None]:
    """Ask for an address (or a manual pick). Returns (senate district, house district)."""
    method = st.segmented_control(
        "Find your legislators", ["By home address", "Pick from a list"], default="By home address"
    )
    if method == "Pick from a list":
        labels = {(row["chamber"], row["district"]): legislators.label(row) for _, row in seats.iterrows()}
        left, right = st.columns(2)
        senate = left.selectbox(
            "Your state senator", sorted(seats.loc[seats["chamber"] == "Senate", "district"]),
            index=None, format_func=lambda district: labels[("Senate", district)],
        )
        house = right.selectbox(
            "Your state representative", sorted(seats.loc[seats["chamber"] == "House", "district"]),
            index=None, format_func=lambda district: labels[("House", district)],
        )
        return senate, house

    with st.form("address"):
        address = st.text_input(
            "Home address", placeholder="411 Legislative Ave, Dover, DE 19901",
            help=ADDRESS_PRIVACY,
        )
        submitted = st.form_submit_button("Find my legislators", type="primary")
    if submitted and address.strip():
        try:
            with st.spinner("Looking up your districts…"):
                st.session_state["district_match"] = find_districts(address.strip())
        except AddressNotFound as error:
            st.session_state.pop("district_match", None)
            st.warning(str(error))
        except Exception as error:  # network errors shouldn't break the page
            st.session_state.pop("district_match", None)
            st.error(f"Couldn't reach the address lookup service: {error}")
    match = st.session_state.get("district_match")
    if match is None:
        return None, None
    st.caption(
        f"Districts for **{match.matched_address.title()}**: "
        f"Senate District {match.senate_district}, House District {match.house_district}."
    )
    return match.senate_district, match.house_district


def election_note(chamber: str, next_election: date) -> str:
    when = f"{next_election:%B} {next_election.day}, {next_election.year}"
    if chamber == "House":
        return (
            f"Representatives serve two-year terms, so every House seat is on the ballot "
            f"at each general election. The next one is **{when}**."
        )
    return (
        f"Senators serve four-year terms on a staggered schedule, so not every Senate seat "
        f"is on the ballot at each election. The next general election is **{when}**; check "
        f"[elections.delaware.gov](https://elections.delaware.gov) to see whether this seat is up."
    )


UNAVAILABLE = "Unavailable"
PARTICIPATION_NOTE = (
    "Share of roll calls where they voted Yes or No. Both \"Absent\" and \"Not Voting\" (present but "
    "didn't vote) count as missed. The record doesn't say why: absences can be excused, and members "
    "sometimes don't vote on purpose, for example over a conflict of interest."
)
SPONSOR_METRICS = ["Primary sponsor", "Additional primary sponsor", "Co-sponsored"]
NOT_LOADED = (
    "Couldn't load {what} from legis.delaware.gov, so it isn't shown here. "
    "This doesn't mean there is none. Try again later."
)


def show_legislator(member: pd.Series) -> None:
    if pd.isna(member["person_id"]):
        st.info(f"{member['chamber']} District {member['district']} is currently vacant.")
        return
    person_id = int(member["person_id"])
    today = date.today()

    # Each source is None when it couldn't be loaded, so the page can say "unavailable"
    # instead of showing an empty record that looks like a real zero.
    try:
        profile = cached_profile(person_id)
    except Exception as error:  # network/site errors shouldn't break the page
        st.error(f"Couldn't load the legislator's profile: {error}")
        profile = None

    photo, about = st.columns([1, 5], gap="medium")
    if profile and profile.photo:
        photo.image(profile.photo, width="stretch")
    with about:
        title = legislators.TITLES[member["chamber"]]
        party = legislators.PARTIES.get(member["party"], member["party"] or "")
        st.subheader(f"{title} {member['name']}")
        badges = [f":blue-badge[{party}]", f":gray-badge[{member['chamber']} District {member['district']}]"]
        if isinstance(member["role"], str):
            badges.append(f":violet-badge[{member['role']}]")
        st.markdown(" ".join(badges))
        contact = [f"[Profile on legis.delaware.gov]({member['profile_url']})"]
        if profile and profile.email:
            contact.insert(0, f"✉️ [{profile.email}](mailto:{profile.email})")
        if profile and profile.phone:
            contact.insert(1, f"📞 {profile.phone}")
        if isinstance(member["caucus_url"], str):
            contact.append(f"[Caucus page]({member['caucus_url']})")
        st.markdown(" · ".join(contact))

    try:
        sponsorships, sponsorships_fetched = cached_sponsorships(person_id, assembly)
    except Exception as error:
        st.error(f"Couldn't load sponsored legislation: {error}")
        sponsorships = sponsored = None
    else:
        sponsored = stats.sponsored_families(sponsorships, items, families)
    try:
        votes, votes_fetched = cached_roll_calls(person_id, assembly)
    except Exception as error:
        st.error(f"Couldn't load roll call votes: {error}")
        votes = votes_fetched = None

    next_election = legislators.next_general_election(today)
    years = profile.years_served(today) if profile else None
    first_took_office = (profile.first_elected or "—") if profile else UNAVAILABLE
    cols = st.columns(5)
    cols[0].metric(
        "First took office", first_took_office,
        f"{years} year{'s' if years != 1 else ''} served" if years is not None else None,
        delta_color="off", delta_arrow="off",
        help="From the Legislative Service text on their profile. Years served add up each term, "
        "in whole years, and leave out any breaks in service.",
    )
    if sponsored is None:
        for col, name in zip(cols[1:4], SPONSOR_METRICS):
            col.metric(name, UNAVAILABLE)
    else:
        record = stats.sponsor_record(sponsored)
        cols[1].metric(
            "Primary sponsor", record.primary,
            f"{record.primary_passed} passed ({record.primary_pass_rate:.0%})" if record.primary else None,
            delta_color="off", delta_arrow="off", help="Bills and resolutions they introduced as the lead sponsor.",
        )
        cols[2].metric(
            "Additional primary sponsor", record.additional_primary,
            f"{record.additional_primary_passed} passed" if record.additional_primary else None,
            delta_color="off", delta_arrow="off",
            help="Listed as a primary sponsor alongside the lead sponsor, so shared rather than theirs alone.",
        )
        cols[3].metric("Co-sponsored", record.cosponsored)
    if votes is None:
        cols[4].metric("Roll calls voted", UNAVAILABLE)
    elif not votes.empty:
        vote_summary = stats.vote_record(votes, legislators.MISSED_VOTES)
        cols[4].metric(
            "Roll calls voted", f"{vote_summary.participation_rate:.0%}",
            f"missed {vote_summary.missed} of {vote_summary.roll_calls:,}", delta_color="off", delta_arrow="off",
            help=PARTICIPATION_NOTE,
        )
    if sponsored is not None:
        st.caption(
            f"For the {assembly}th General Assembly; a bill and its substitutes count once. **Passed** means "
            "enacted (bills) or adopted (resolutions). Anything still moving counts as not passed, so the "
            f"share grows through a session. Sponsorships fetched live {as_of(sponsorships_fetched)}; "
            f"whether each passed comes from the bill data downloaded {as_of(refreshed)}."
        )
        not_in_data = stats.sponsorships_not_in_data(sponsorships, items)
        if not_in_data:
            st.warning(
                f"{not_in_data} item{'s' if not_in_data > 1 else ''} they sponsored "
                f"{'are' if not_in_data > 1 else 'is'} newer than the downloaded bill data (from "
                f"{as_of(refreshed)}) and not counted above. They'll be included after the next data refresh."
            )

    st.markdown(f"**Next election.** {election_note(member['chamber'], next_election)}")

    show_profile_details(profile)
    show_sponsored(sponsored)
    show_votes(votes, votes_fetched, person_id)


def show_profile_details(profile: legislators.Profile | None) -> None:
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Legislative service**")
        if profile is None:
            st.write(NOT_LOADED.format(what="their profile"))
            return
        st.write(profile.service_text or "Not listed.")
        if profile.service_text and not profile.terms:
            st.caption("Couldn't read the years of service from the site's wording.")
    with right:
        st.markdown("**Committees**")
        if profile.committees:
            st.markdown("\n".join(f"- {name}, {role}" for name, role in profile.committees))
        else:
            st.write("None listed.")
    if profile.biography:
        with st.expander("Biography (from their legislative profile)"):
            st.write(profile.biography)


def show_sponsored(sponsored: pd.DataFrame | None) -> None:
    if sponsored is None:
        st.markdown("#### Legislation they sponsored")
        st.write(NOT_LOADED.format(what="the legislation they sponsored"))
        return
    led = sponsored[sponsored["role"] != "Co-sponsor"]
    st.markdown(f"#### Legislation they sponsored ({len(led)})")
    if led.empty:
        st.write("None this session.")
    else:
        roles = led["role"].value_counts()
        st.caption(
            f"As primary sponsor: {roles.get('Primary sponsor', 0)} · as an additional primary sponsor, "
            f"shared with the lead: {roles.get('Additional primary sponsor', 0)}. The Role column says which."
        )
        topics = stats.category_outcomes(led)
        topic_order = list(topics.groupby("category")["count"].sum().sort_values(ascending=False).index)
        st.altair_chart(charts.category_outcome_bars(topics, topic_order, mode), width="stretch")
        st.dataframe(
            led[list(BILL_TABLE_COLUMNS) + ["role"]],
            hide_index=True, width="stretch",
            column_config=BILL_TABLE_COLUMNS | {"role": "Role"},
        )

    cosponsored = sponsored[sponsored["role"] == "Co-sponsor"]
    with st.expander(f"Legislation they co-sponsored ({len(cosponsored)})"):
        st.dataframe(cosponsored[list(BILL_TABLE_COLUMNS)], hide_index=True, width="stretch", column_config=BILL_TABLE_COLUMNS)


def show_votes(votes: pd.DataFrame | None, fetched: pd.Timestamp | None, person_id: int) -> None:
    st.markdown("#### Voting record")
    if votes is None:
        st.write(NOT_LOADED.format(what="their roll call votes"))
        return
    if votes.empty:
        st.write("The roll call feed lists no votes for them this session.")
        return
    vote_summary = stats.vote_record(votes, legislators.MISSED_VOTES)
    counts = " · ".join(f"{choice}: {vote_summary.counts.get(choice, 0):,}" for choice in legislators.VOTE_CHOICES)
    st.caption(f"{vote_summary.roll_calls:,} roll calls this session, fetched live {as_of(fetched)}. {counts}")
    st.caption(PARTICIPATION_NOTE)
    show = st.segmented_control(
        "Show votes", ["No votes", "Missed votes", "All"], default="No votes", key=f"votes-{person_id}",
    )
    if show == "No votes":
        shown = votes[votes["vote"] == "No"]
    elif show == "Missed votes":
        shown = votes[votes["vote"].isin(legislators.MISSED_VOTES)]
    else:
        shown = votes
    st.dataframe(
        shown[["date", "motion", "title", "vote", "total_yes", "total_no", "url"]],
        hide_index=True, width="stretch",
        column_config={
            "date": st.column_config.DatetimeColumn("Date", format="MMM D, YYYY"),
            "motion": "Legislation",
            "title": st.column_config.TextColumn("Title", width="large"),
            "vote": "Their vote",
            "total_yes": st.column_config.NumberColumn("Yes (all)"),
            "total_no": st.column_config.NumberColumn("No (all)"),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )


st.title("Your Delaware Legislators")
st.caption(
    f"Find your state senator and representative and see what they've been doing in the "
    f"{assembly}th General Assembly."
)
try:
    seats = cached_roster()
except Exception as error:
    st.error(f"Couldn't load the list of legislators: {error}")
    seats = None
if seats is not None:
    for chamber, gaps in legislators.missing_districts(seats).items():
        st.warning(
            f"legis.delaware.gov didn't list a {chamber} member for district"
            f"{'s' if len(gaps) > 1 else ''} {', '.join(map(str, gaps))}, so the list may be incomplete."
        )
    senate_district, house_district = choose_districts(seats)
    chosen = []
    for chamber, district in (("Senate", senate_district), ("House", house_district)):
        if district is None:
            continue
        member = legislators.find_seat(seats, chamber, district)
        if member is None:
            st.warning(f"Couldn't find who represents {chamber} District {district} on legis.delaware.gov.")
        else:
            chosen.append(member)
    if chosen:
        for panel, member in zip(st.tabs([legislators.label(m) for m in chosen]), chosen):
            with panel:
                show_legislator(member)

st.divider()
st.caption(
    f"Version {__version__} (public beta). Legislator details, sponsorships and votes come live from "
    f"[legis.delaware.gov](https://legis.delaware.gov); bill outcomes from data downloaded {as_of(refreshed)}. "
    "Address lookup by the US Census Bureau geocoder. This is not an official State of Delaware site."
)
