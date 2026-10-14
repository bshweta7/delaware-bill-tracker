"""Aggregations behind the dashboard. Pure pandas, so they're easy to test."""

from dataclasses import dataclass

import pandas as pd

from billtracker.stages import DEAD_STAGES, STAGE_ORDER, SUCCESS_STAGES

ACTIVITY_KINDS = ["Bills", "Resolutions", "Amendments & substitutes"]


@dataclass(frozen=True)
class Overview:
    families: int
    bills: int
    resolutions: int
    enacted: int
    adopted: int
    still_moving: int
    amendments: int
    substitutes: int

    @property
    def bill_enactment_rate(self) -> float:
        return self.enacted / self.bills if self.bills else 0.0


def outcome(stage: str) -> str:
    """Collapse a stage into Passed / Stalled / In progress."""
    if stage in SUCCESS_STAGES:
        return "Passed"
    if stage in DEAD_STAGES:
        return "Did not pass"
    return "In progress"


def overview(families: pd.DataFrame, items: pd.DataFrame) -> Overview:
    is_bill = families["type"] == "Bill"
    return Overview(
        families=len(families),
        bills=int(is_bill.sum()),
        resolutions=int((~is_bill).sum()),
        enacted=int((is_bill & (families["stage"] == "Enacted")).sum()),
        adopted=int((families["stage"] == "Adopted").sum()),
        still_moving=int(families["stage"].map(outcome).eq("In progress").sum()),
        amendments=int((items["type"] == "Amendment").sum()),
        substitutes=int((items["type"] == "Substitute").sum()),
    )


def stage_counts(families: pd.DataFrame) -> pd.DataFrame:
    """Families per stage, in pipeline order, omitting empty stages."""
    counts = families["stage"].value_counts()
    ordered = [stage for stage in STAGE_ORDER if stage in counts.index]
    return pd.DataFrame({"stage": ordered, "count": [int(counts[s]) for s in ordered]})


def category_breakdown(families: pd.DataFrame) -> pd.DataFrame:
    """Per category: total families, how many passed, and the pass rate."""
    table = (
        families.assign(passed=families["stage"].isin(SUCCESS_STAGES))
        .groupby("category")
        .agg(total=("family_id", "size"), passed=("passed", "sum"))
        .reset_index()
    )
    table["pass_rate"] = table["passed"] / table["total"]
    return table.sort_values("total", ascending=False, ignore_index=True)


def category_outcomes(families: pd.DataFrame) -> pd.DataFrame:
    """Long table of (category, outcome, count) for a stacked bar."""
    return (
        families.assign(outcome=families["stage"].map(outcome))
        .groupby(["category", "outcome"])
        .size()
        .reset_index(name="count")
    )


def activity_kind(legislation_type: str) -> str:
    if legislation_type == "Bill":
        return "Bills"
    if legislation_type in ("Amendment", "Substitute"):
        return "Amendments & substitutes"
    return "Resolutions"


def weekly_introductions(items: pd.DataFrame) -> pd.DataFrame:
    """Items introduced per week, split into bills / resolutions / amendments & substitutes."""
    dated = items.dropna(subset=["introduced"])
    return (
        dated.assign(
            week=dated["introduced"].dt.to_period("W-SUN").dt.start_time,
            kind=dated["type"].map(activity_kind),
        )
        .groupby(["week", "kind"])
        .size()
        .reset_index(name="count")
    )


def cumulative_enactments(families: pd.DataFrame) -> pd.DataFrame:
    """Running total of bills enacted, dated by their last action (the signing)."""
    is_enacted_bill = (families["type"] == "Bill") & (families["stage"] == "Enacted")
    enacted = families[is_enacted_bill].dropna(subset=["last_action"])
    daily = enacted.groupby(enacted["last_action"].dt.normalize()).size()
    return pd.DataFrame({"date": daily.index, "enacted": daily.cumsum().to_numpy()})


def monthly_category_activity(families: pd.DataFrame) -> pd.DataFrame:
    """Families introduced per (category, month), for a heatmap."""
    dated = families.dropna(subset=["introduced"])
    return (
        dated.assign(month=dated["introduced"].dt.to_period("M").dt.start_time)
        .groupby(["category", "month"])
        .size()
        .reset_index(name="count")
    )


def top_sponsors(families: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Primary sponsors with the most bills, and how many of those passed."""
    bills = families[(families["type"] == "Bill") & families["sponsor"].notna()]
    table = (
        bills.assign(enacted=bills["stage"] == "Enacted")
        .groupby("sponsor")
        .agg(bills=("family_id", "size"), enacted=("enacted", "sum"))
        .reset_index()
        .sort_values(["bills", "enacted"], ascending=False)
    )
    return table.head(n).reset_index(drop=True)


def family_members(items: pd.DataFrame, family_id: int) -> pd.DataFrame:
    """Every item in one family (original, substitutes, amendments), oldest first."""
    members = items[items["family_id"] == family_id]
    return members.sort_values("introduced").reset_index(drop=True)


# ------------------------------------------------------------------ legislators

SPONSOR_ROLE_ORDER = ["Primary sponsor", "Additional primary sponsor", "Co-sponsor"]


@dataclass(frozen=True)
class SponsorRecord:
    """Families by the legislator's role on them. "Passed" means enacted or adopted."""

    primary: int  # they were the lead sponsor
    primary_passed: int
    additional_primary: int  # listed as a primary sponsor alongside the lead
    additional_primary_passed: int
    cosponsored: int

    @property
    def primary_pass_rate(self) -> float:
        """Share of the families they led that passed, counting ones still in progress as not passed."""
        return self.primary_passed / self.primary if self.primary else 0.0


def sponsored_families(sponsorships: pd.DataFrame, items: pd.DataFrame, families: pd.DataFrame) -> pd.DataFrame:
    """The families a legislator sponsored, with their strongest role on each.

    Sponsorship can be on the original bill or on a substitute, so each is
    mapped to its family; a legislator who sponsored both counts once.
    """
    family_of = items.set_index("legislation_id")["family_id"]
    rank = {role: position for position, role in enumerate(SPONSOR_ROLE_ORDER)}
    linked = sponsorships.assign(
        family_id=sponsorships["legislation_id"].map(family_of),
        rank=sponsorships["role"].map(rank).fillna(len(rank)),
    ).dropna(subset=["family_id"])
    strongest = linked.sort_values("rank").drop_duplicates("family_id")[["family_id", "role"]]
    strongest["family_id"] = strongest["family_id"].astype(families["family_id"].dtype)
    sponsored = families.merge(strongest, on="family_id")
    return sponsored.sort_values("last_action", ascending=False, ignore_index=True)


def sponsorships_not_in_data(sponsorships: pd.DataFrame, items: pd.DataFrame) -> int:
    """Sponsorships of legislation missing from our data, usually filed since the last refresh."""
    return int((~sponsorships["legislation_id"].isin(items["legislation_id"])).sum())


def sponsor_record(sponsored: pd.DataFrame) -> SponsorRecord:
    passed = sponsored["stage"].isin(SUCCESS_STAGES)
    is_primary = sponsored["role"] == "Primary sponsor"
    is_additional = sponsored["role"] == "Additional primary sponsor"
    return SponsorRecord(
        primary=int(is_primary.sum()),
        primary_passed=int((is_primary & passed).sum()),
        additional_primary=int(is_additional.sum()),
        additional_primary_passed=int((is_additional & passed).sum()),
        cosponsored=int((sponsored["role"] == "Co-sponsor").sum()),
    )


@dataclass(frozen=True)
class VoteRecord:
    roll_calls: int
    counts: dict[str, int]  # vote choice -> count
    missed: int

    @property
    def participation_rate(self) -> float:
        return 1 - self.missed / self.roll_calls if self.roll_calls else 0.0


def vote_record(votes: pd.DataFrame, missed_choices: set[str]) -> VoteRecord:
    counts = votes["vote"].value_counts()
    return VoteRecord(
        roll_calls=len(votes),
        counts={choice: int(count) for choice, count in counts.items()},
        missed=int(votes["vote"].isin(missed_choices).sum()),
    )
