"""Altair chart for a legislator's sponsored legislation by topic and outcome.

Colors come from a colorblind-validated categorical palette, assigned in a
fixed order so an outcome keeps its color in every chart.
Light and dark mode use separately tuned steps of the same hues.
"""

import altair as alt
import pandas as pd

OUTCOMES = ["Passed", "In progress", "Did not pass"]

PALETTES = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a"],
        "surface": "#ffffff",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70"],
        "surface": "#0e1117",
    },
}

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
