"""Altair chart builders for the dashboard.

Colors come from a colorblind-validated categorical palette, assigned in a
fixed order so an outcome or kind keeps its color under every filter.
Light and dark mode use separately tuned steps of the same hues.
"""

import altair as alt
import pandas as pd

from billtracker.stats import ACTIVITY_KINDS

OUTCOMES = ["Passed", "In progress", "Did not pass"]

PALETTES = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a"],
        "sequential": ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
        "surface": "#ffffff",
        "muted": "#898781",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70"],
        "sequential": ["#0d366b", "#184f95", "#256abf", "#5598e7", "#9ec5f4"],
        "surface": "#0e1117",
        "muted": "#898781",
    },
}

BAR_CORNER_RADIUS = 4
SEGMENT_GAP = 2  # px of surface color between stacked segments


def _palette(mode: str) -> dict:
    return PALETTES.get(mode, PALETTES["light"])


def _series_scale(domain: list[str], mode: str) -> alt.Scale:
    return alt.Scale(domain=domain, range=_palette(mode)["series"][: len(domain)])


LABEL_LIMIT = 220  # px before axis/legend labels are truncated


def _legend_top() -> alt.Legend:
    return alt.Legend(orient="top", title=None, direction="horizontal", labelLimit=LABEL_LIMIT)


def _category_axis(sort: list[str]) -> alt.Y:
    return alt.Y("category:N", sort=sort, title=None, axis=alt.Axis(labelLimit=LABEL_LIMIT))


def stage_bars(stage_counts: pd.DataFrame, stage_outcomes: dict[str, str], mode: str) -> alt.Chart:
    """Horizontal bars of families per stage, colored by outcome group."""
    data = stage_counts.assign(outcome=stage_counts["stage"].map(stage_outcomes))
    return (
        alt.Chart(data)
        .mark_bar(cornerRadiusEnd=BAR_CORNER_RADIUS, height={"band": 0.7})
        .encode(
            y=alt.Y("stage:N", sort=list(data["stage"]), title=None, axis=alt.Axis(labelLimit=LABEL_LIMIT)),
            x=alt.X("count:Q", title="Bills & resolutions"),
            color=alt.Color("outcome:N", scale=_series_scale(OUTCOMES, mode), legend=_legend_top()),
            tooltip=[alt.Tooltip("stage:N", title="Stage"), alt.Tooltip("count:Q", title="Count")],
        )
        .properties(height=alt.Step(26))
    )


def category_outcome_bars(category_outcomes: pd.DataFrame, category_order: list[str], mode: str) -> alt.Chart:
    """Stacked horizontal bars: each category split into passed / in progress / stalled."""
    surface = _palette(mode)["surface"]
    return (
        alt.Chart(category_outcomes)
        .mark_bar(stroke=surface, strokeWidth=SEGMENT_GAP, height={"band": 0.7})
        .encode(
            y=_category_axis(category_order),
            x=alt.X("sum(count):Q", title="Bills & resolutions"),
            color=alt.Color("outcome:N", scale=_series_scale(OUTCOMES, mode), legend=_legend_top()),
            order=alt.Order("outcome_rank:Q"),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("outcome:N", title="Outcome"),
                alt.Tooltip("sum(count):Q", title="Count"),
            ],
        )
        .transform_calculate(outcome_rank=f"indexof({OUTCOMES}, datum.outcome)")
        .properties(height=alt.Step(26))
    )


def weekly_activity_bars(weekly: pd.DataFrame, mode: str) -> alt.Chart:
    """Stacked weekly bars of new legislation by kind."""
    surface = _palette(mode)["surface"]
    return (
        alt.Chart(weekly)
        .mark_bar(stroke=surface, strokeWidth=1)
        .encode(
            x=alt.X("week:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y("sum(count):Q", title="Introduced per week"),
            color=alt.Color("kind:N", scale=_series_scale(ACTIVITY_KINDS, mode), legend=_legend_top()),
            order=alt.Order("kind_rank:Q"),
            tooltip=[
                alt.Tooltip("week:T", title="Week of", format="%b %d, %Y"),
                alt.Tooltip("kind:N", title="Kind"),
                alt.Tooltip("sum(count):Q", title="Introduced"),
            ],
        )
        .transform_calculate(kind_rank=f"indexof({ACTIVITY_KINDS}, datum.kind)")
        .properties(height=280)
    )


def cumulative_line(cumulative: pd.DataFrame, mode: str) -> alt.Chart:
    """Running total of enacted bills, with a hover rule and tooltip."""
    color = _palette(mode)["series"][0]
    base = alt.Chart(cumulative).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %Y")),
        y=alt.Y("enacted:Q", title="Bills enacted (cumulative)"),
    )
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False)
    line = base.mark_line(color=color, strokeWidth=2, interpolate="step-after")
    points = base.mark_point(color=color, filled=True, size=70).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("enacted:Q", title="Enacted so far"),
        ],
    ).add_params(hover)
    rule = base.mark_rule(color=_palette(mode)["muted"]).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0))
    ).transform_filter(hover)
    return (line + rule + points).properties(height=280)


def category_month_heatmap(monthly: pd.DataFrame, category_order: list[str], mode: str) -> alt.Chart:
    """Heatmap of new bills & resolutions per category per month (one-hue sequential scale)."""
    surface = _palette(mode)["surface"]
    return (
        alt.Chart(monthly)
        .mark_rect(stroke=surface, strokeWidth=SEGMENT_GAP, cornerRadius=2)
        .encode(
            x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)),
            y=_category_axis(category_order),
            color=alt.Color(
                "count:Q",
                scale=alt.Scale(range=_palette(mode)["sequential"]),
                legend=alt.Legend(title="Introduced", orient="top"),
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("yearmonth(month):T", title="Month", format="%B %Y"),
                alt.Tooltip("count:Q", title="Introduced"),
            ],
        )
        .properties(height=alt.Step(24))
    )


def monthly_bars(monthly: pd.DataFrame, mode: str) -> alt.Chart:
    """Single-series monthly bars for one category."""
    color = _palette(mode)["series"][0]
    return (
        alt.Chart(monthly)
        .mark_bar(color=color, cornerRadiusEnd=BAR_CORNER_RADIUS)
        .encode(
            x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=0)),
            y=alt.Y("sum(count):Q", title="Introduced"),
            tooltip=[
                alt.Tooltip("yearmonth(month):T", title="Month", format="%B %Y"),
                alt.Tooltip("sum(count):Q", title="Introduced"),
            ],
        )
        .properties(height=220)
    )
