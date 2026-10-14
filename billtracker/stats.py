"""Aggregations behind the legislators page. Pure pandas, so they're easy to test."""

from dataclasses import dataclass

import pandas as pd

from billtracker.stages import DEAD_STAGES, SUCCESS_STAGES


def outcome(stage: str) -> str:
    """Collapse a stage into Passed / Stalled / In progress."""
    if stage in SUCCESS_STAGES:
        return "Passed"
    if stage in DEAD_STAGES:
        return "Did not pass"
    return "In progress"


def category_outcomes(families: pd.DataFrame) -> pd.DataFrame:
    """Long table of (category, outcome, count) for a stacked bar."""
    return (
        families.assign(outcome=families["stage"].map(outcome))
        .groupby(["category", "outcome"])
        .size()
        .reset_index(name="count")
    )


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
