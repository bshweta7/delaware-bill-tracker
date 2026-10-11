"""Delaware Bill Tracker: a Streamlit dashboard.

    streamlit run app.py
"""

import anthropic
import pandas as pd
import streamlit as st

from billtracker import charts, config, stats
from billtracker.bill_detail import fetch_bill_detail
from billtracker.categories import CATEGORIES, CEREMONIAL
from billtracker.families import build_families
from billtracker.pipeline import refresh
from billtracker.stages import STAGE_ORDER
from billtracker.storage import load_items, load_watchlist
from billtracker.summaries import (
    BILL_SYSTEM_PROMPT,
    ClaudeSummarizer,
    SummaryStore,
    bill_prompt,
    text_hash,
)

st.set_page_config(page_title="Delaware Bill Tracker", page_icon="🏛️", layout="wide")

MAX_CATEGORY_LIST = 100


# ---------------------------------------------------------------- data loading

@st.cache_data(show_spinner="Loading legislation…")
def load_data(csv_mtime: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load items and families. `csv_mtime` is only a cache key, so a refresh reloads."""
    items = load_items()
    return items, build_families(items)


@st.cache_data(show_spinner="Fetching sponsors from legis.delaware.gov…", ttl=3600)
def cached_bill_detail(legislation_id: int) -> dict:
    return fetch_bill_detail(legislation_id)


def theme_mode() -> str:
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", None) or "light"


def run_refresh() -> None:
    with st.spinner("Downloading every bill in the current session (this can take several minutes)…"):
        refresh()
    st.cache_data.clear()
    st.rerun()


if not config.LEGISLATION_CSV.exists():
    st.title("Delaware Bill Tracker")
    st.info("No data yet. Download the current session from legis.delaware.gov to get started.")
    if st.button("Download legislation", type="primary"):
        run_refresh()
    st.stop()

items, families = load_data(config.LEGISLATION_CSV.stat().st_mtime)
summary_store = SummaryStore()
bill_summaries = summary_store.bill_summaries()
trend_summaries = summary_store.category_summaries()
watchlist = load_watchlist()
mode = theme_mode()
assembly = int(items["assembly"].iloc[0])


# --------------------------------------------------------------------- sidebar

def watched_family_ids() -> set[int]:
    """Watchlist entries may be substitutes or amendments; track their whole family."""
    return set(items.loc[items["legislation_id"].isin(watchlist), "family_id"])


with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search", placeholder="Bill number, title, sponsor…")
    selected_categories = st.multiselect("Category", CATEGORIES)
    selected_types = st.multiselect("Type", sorted(families["type"].unique()))
    chamber = st.segmented_control("Chamber of origin", ["House", "Senate"])
    selected_outcomes = st.multiselect("Outcome", charts.OUTCOMES)
    hide_ceremonial = st.toggle("Hide ceremonial resolutions", value=False)
    watchlist_only = st.toggle(
        f"Watchlist only ({len(watched_family_ids())})",
        value=False,
        disabled=not watchlist,
        help=f"Legislation ids listed in {config.WATCHLIST_FILE.relative_to(config.PROJECT_ROOT)}.",
    )

    st.divider()
    refreshed = pd.Timestamp(config.LEGISLATION_CSV.stat().st_mtime, unit="s", tz="UTC")
    st.caption(
        f"{assembly}th General Assembly · data from "
        f"{refreshed.tz_convert('America/New_York'):%b %d, %Y %I:%M %p}"
    )
    if st.button("Refresh from legis.delaware.gov", width="stretch"):
        run_refresh()


def apply_filters(frame: pd.DataFrame) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    if search:
        haystack = (
            frame[["display_code", "family_code", "short_title", "long_title", "sponsor"]]
            .fillna("")
            .agg(" ".join, axis=1)
        )
        mask &= haystack.str.contains(search, case=False, regex=False)
    if selected_categories:
        mask &= frame["category"].isin(selected_categories)
    if selected_types:
        mask &= frame["type"].isin(selected_types)
    if chamber:
        mask &= frame["chamber"] == chamber
    if selected_outcomes:
        mask &= frame["stage"].map(stats.outcome).isin(selected_outcomes)
    if hide_ceremonial:
        mask &= frame["category"] != CEREMONIAL
    if watchlist_only:
        mask &= frame["family_id"].isin(watched_family_ids())
    return frame[mask]


shown_families = apply_filters(families)
shown_items = items[items["family_id"].isin(shown_families["family_id"])]


# ---------------------------------------------------------------------- header

st.title("Delaware Bill Tracker")
st.caption(
    f"Every bill, resolution, substitute and amendment in the {assembly}th Delaware "
    "General Assembly, grouped into families and sorted by topic."
)

if shown_families.empty:
    st.warning("No legislation matches these filters.")
    st.stop()

summary = stats.overview(shown_families, shown_items)
kpis = st.columns(6)
kpis[0].metric("Bills & resolutions", f"{summary.families:,}")
kpis[1].metric("Bills enacted", f"{summary.enacted:,}", f"{summary.bill_enactment_rate:.0%} of bills", delta_color="off", delta_arrow="off")
kpis[2].metric("Resolutions adopted", f"{summary.adopted:,}")
kpis[3].metric("Still in progress", f"{summary.still_moving:,}")
kpis[4].metric("Amendments filed", f"{summary.amendments:,}")
kpis[5].metric("Substitutes filed", f"{summary.substitutes:,}")

overview_tab, timeline_tab, category_tab, explorer_tab = st.tabs(
    ["Overview", "Timeline", "Categories", "Bill explorer"]
)
category_table = stats.category_breakdown(shown_families)
category_order = list(category_table["category"])


# -------------------------------------------------------------------- overview

with overview_tab:
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Where legislation stands")
        stage_outcomes = {stage: stats.outcome(stage) for stage in STAGE_ORDER}
        st.altair_chart(
            charts.stage_bars(stats.stage_counts(shown_families), stage_outcomes, mode),
            width="stretch",
        )
        st.caption("Each family counts once, at the stage of its latest version.")
    with right:
        st.subheader("Topics")
        st.altair_chart(
            charts.category_outcome_bars(stats.category_outcomes(shown_families), category_order, mode),
            width="stretch",
        )

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Pass rate by topic")
        st.dataframe(
            category_table,
            hide_index=True,
            width="stretch",
            column_config={
                "category": "Category",
                "total": st.column_config.NumberColumn("Total"),
                "passed": st.column_config.NumberColumn("Passed"),
                "pass_rate": st.column_config.ProgressColumn("Pass rate", format="percent", min_value=0, max_value=1),
            },
        )
    with right:
        st.subheader("Most active sponsors")
        st.dataframe(
            stats.top_sponsors(shown_families),
            hide_index=True,
            width="stretch",
            column_config={"sponsor": "Primary sponsor", "bills": "Bills", "enacted": "Enacted"},
        )


# -------------------------------------------------------------------- timeline

with timeline_tab:
    st.subheader("New legislation per week")
    st.altair_chart(charts.weekly_activity_bars(stats.weekly_introductions(shown_items), mode), width="stretch")
    st.caption("Counts every item filed, including the substitutes and amendments in each family.")

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Bills enacted over time")
        cumulative = stats.cumulative_enactments(shown_families)
        if cumulative.empty:
            st.info("No enacted bills match these filters.")
        else:
            st.altair_chart(charts.cumulative_line(cumulative, mode), width="stretch")
            st.caption("Dated by each bill's most recent action, usually the governor's signature.")
    with right:
        st.subheader("Topics by month introduced")
        st.altair_chart(
            charts.category_month_heatmap(stats.monthly_category_activity(shown_families), category_order, mode),
            width="stretch",
        )


# ------------------------------------------------------------------ categories

with category_tab:
    default_category = next((c for c in category_order if c != CEREMONIAL), category_order[0])
    category = st.selectbox("Category", category_order, index=category_order.index(default_category))
    in_category = shown_families[shown_families["category"] == category]
    row = category_table.set_index("category").loc[category]

    cols = st.columns(4)
    cols[0].metric("Bills & resolutions", int(row["total"]))
    cols[1].metric("Passed", int(row["passed"]))
    cols[2].metric("Pass rate", f"{row['pass_rate']:.0%}")
    cols[3].metric("Still in progress", int(in_category["stage"].map(stats.outcome).eq("In progress").sum()))

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Trends")
        if category in trend_summaries:
            st.markdown(trend_summaries[category])
            st.caption("AI-generated by Claude from this session's bills in the category. Verify before citing.")
        else:
            st.info("No trend summary yet. Run `python -m billtracker.summaries` to generate one.")
    with right:
        st.subheader("Introduced by month")
        st.altair_chart(charts.monthly_bars(stats.monthly_category_activity(in_category), mode), width="stretch")

    st.subheader("Bills in this category")
    newest_first = in_category.sort_values("introduced", ascending=False)
    if len(newest_first) > MAX_CATEGORY_LIST:
        st.caption(f"Showing the {MAX_CATEGORY_LIST} most recent. Use the Bill explorer for the full list.")
    for family in newest_first.head(MAX_CATEGORY_LIST).itertuples():
        title = family.short_title or family.long_title or ""
        with st.expander(f"**{family.display_code}** · {title} · _{family.stage}_"):
            st.write(bill_summaries.get(family.family_id) or family.synopsis or family.long_title)
            st.caption(f"Sponsor: {family.sponsor or 'n/a'} · [View on legis.delaware.gov]({family.url})")


# --------------------------------------------------------------- bill explorer

def summarize_one(family: pd.Series) -> None:
    """Generate and cache one bill's summary on demand."""
    prompt = bill_prompt(family)
    try:
        summary_text = ClaudeSummarizer()(BILL_SYSTEM_PROMPT, prompt, "low")
    except anthropic.AuthenticationError:
        st.error("Claude API credentials are missing or invalid. Set ANTHROPIC_API_KEY and restart.")
        return
    except anthropic.RateLimitError:
        st.error("Rate limited by the Claude API. Try again in a minute.")
        return
    except anthropic.APIConnectionError:
        st.error("Couldn't reach the Claude API. Check your connection.")
        return
    except anthropic.AnthropicError as error:  # missing key, server errors, etc.
        st.error(f"Couldn't generate a summary: {error}")
        return
    if summary_text is None:
        st.warning("Claude declined to summarize this bill.")
        return
    summary_store.put("bills", family["family_id"], text_hash(prompt), summary_text, config.SUMMARY_MODEL)
    summary_store.save()
    st.rerun()


def show_family(family: pd.Series) -> None:
    st.subheader(f"{family['display_code']}: {family['short_title'] or ''}")
    st.markdown(
        f":blue-badge[{family['category']}] :gray-badge[{family['stage']}] "
        f":gray-badge[{family['chamber']}] :gray-badge[Sponsor: {family['sponsor'] or 'n/a'}]"
    )

    ai_summary = bill_summaries.get(family["family_id"])
    if ai_summary:
        st.markdown(f"**Summary** (AI-generated)\n\n{ai_summary}")
    elif st.button("Summarize with Claude", key=f"summarize-{family['family_id']}"):
        summarize_one(family)

    members = stats.family_members(items, family["family_id"])
    st.markdown(f"**Family** ({len(members)} items: the original, its substitutes, and amendments)")
    st.dataframe(
        members[["code", "type", "stage", "status", "sponsor", "introduced", "url"]],
        hide_index=True,
        width="stretch",
        column_config={
            "code": "Legislation",
            "type": "Type",
            "stage": "Stage",
            "status": "Raw status",
            "sponsor": "Sponsor",
            "introduced": st.column_config.DateColumn("Introduced", format="MMM D, YYYY"),
            "url": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )

    with st.expander("Synopsis and long title", expanded=not ai_summary):
        st.markdown(f"**Synopsis**\n\n{family['synopsis'] or '—'}")
        st.markdown(f"**Long title**\n\n{family['long_title'] or '—'}")

    if st.toggle("Show full sponsor list and next step", key=f"detail-{family['family_id']}"):
        try:
            detail = cached_bill_detail(int(family["lead_id"]))
        except Exception as error:  # network/site errors shouldn't break the page
            st.error(f"Couldn't load the bill page: {error}")
        else:
            st.markdown(
                f"- **Additional sponsors:** {detail['additional_sponsors'] or '—'}\n"
                f"- **Co-sponsors:** {detail['cosponsors'] or '—'}\n"
                f"- **What typically happens next:** {detail['next_step'] or '—'}"
            )
    st.link_button("Open on legis.delaware.gov", family["url"])


with explorer_tab:
    table = shown_families.sort_values("last_action", ascending=False).reset_index(drop=True)
    table["ai_summary"] = table["family_id"].map(bill_summaries).notna()
    st.caption(f"{len(table):,} bills & resolutions. Select a row to see its details and related legislation.")
    event = st.dataframe(
        table[[
            "display_code", "short_title", "category", "stage", "sponsor",
            "introduced", "last_action", "substitute_count", "amendment_count", "ai_summary",
        ]],
        hide_index=True,
        width="stretch",
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        key="explorer",
        column_config={
            "display_code": "Legislation",
            "short_title": st.column_config.TextColumn("Title", width="large"),
            "category": "Category",
            "stage": "Stage",
            "sponsor": "Sponsor",
            "introduced": st.column_config.DateColumn("Introduced", format="MMM D, YYYY"),
            "last_action": st.column_config.DateColumn("Last action", format="MMM D, YYYY"),
            "substitute_count": st.column_config.NumberColumn("Subs", help="Substitutes filed"),
            "amendment_count": st.column_config.NumberColumn("Amds", help="Amendments filed"),
            "ai_summary": st.column_config.CheckboxColumn("AI summary"),
        },
    )
    selected_rows = event.selection.rows
    if selected_rows:
        st.divider()
        show_family(table.iloc[selected_rows[0]])
