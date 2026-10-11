"""Map the site's raw status names onto a small set of ordered stages.

The site reports either an outcome ("Passed", "Signed", "Stricken"...) or, for
legislation sitting in committee, just the committee's name ("Education",
"Judiciary"...). Anything we don't recognize is therefore treated as a
committee.
"""

IN_COMMITTEE = "In Committee"
OUT_OF_COMMITTEE = "Out of Committee"
PASSED_ONE_CHAMBER = "Passed One Chamber"
PASSED_BOTH_CHAMBERS = "Passed Both Chambers"
ENACTED = "Enacted"
ADOPTED = "Adopted"
VETOED = "Vetoed"
DEFEATED = "Defeated"
TABLED = "Tabled"
STRICKEN = "Stricken"
SUBSTITUTED = "Substituted"
PENDING = "Pending"

# Order used for sorting and charts: progress first, then dead ends.
STAGE_ORDER = [
    IN_COMMITTEE,
    OUT_OF_COMMITTEE,
    PASSED_ONE_CHAMBER,
    PASSED_BOTH_CHAMBERS,
    ENACTED,
    ADOPTED,
    PENDING,
    VETOED,
    DEFEATED,
    TABLED,
    STRICKEN,
    SUBSTITUTED,
]

# Stages where the legislation achieved what it set out to do.
SUCCESS_STAGES = {ENACTED, ADOPTED}
# Stages where the legislation can no longer advance (in this form).
DEAD_STAGES = {VETOED, DEFEATED, TABLED, STRICKEN, SUBSTITUTED}

AMENDMENT_TYPE = "Amendment"
RESOLUTION_TYPES = {"Resolution", "Concurrent Resolution", "Joint Resolution"}

_FIXED_STATUSES = {
    "Out of Committee": OUT_OF_COMMITTEE,
    "Passed House": PASSED_ONE_CHAMBER,
    "Passed Senate": PASSED_ONE_CHAMBER,
    "Signed": ENACTED,
    "Enact w/o Sign": ENACTED,
    "Veto Overridden": ENACTED,
    "Approved": ENACTED,
    "Vetoed": VETOED,
    "Defeated": DEFEATED,
    "LOT": TABLED,  # Laid On Table
    "Stricken": STRICKEN,
    "Lieu/Substituted": SUBSTITUTED,
    "PWB": PENDING,  # amendment Placed With Bill, awaiting a floor vote
}


def stage_for(status: str | None, legislation_type: str) -> str:
    """Translate one raw status into a stage, given the kind of legislation."""
    if status == "Passed":
        if legislation_type == AMENDMENT_TYPE or legislation_type in RESOLUTION_TYPES:
            return ADOPTED
        return PASSED_BOTH_CHAMBERS
    if status in _FIXED_STATUSES:
        return _FIXED_STATUSES[status]
    return IN_COMMITTEE
