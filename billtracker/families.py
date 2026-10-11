"""Group legislation into families: an original bill or resolution plus its
substitutes and amendments.

Relationships are encoded in display codes:

    HB 233                       an original bill
    HB 472 w/ HA 1               the same bill, noting an attached amendment
    HS 1 for HB 457              a substitute that replaces HB 457
    HA 1 to HS 1 for HB 233      an amendment to that substitute
    HA 1 to HA 1 to HS 1 ...     an amendment to an amendment

Stripping the " w/ ..." / " -HA ..." suffix gives a canonical code that is
unique within a session. Peeling off "XA n to" / "XS n for" prefixes gives the
parent, and repeating that reaches the root of the family.
"""

import re

import pandas as pd

from billtracker.stages import SUBSTITUTED

_SUFFIX = re.compile(r"\s+(?:w/|-).*$")
_PARENT = re.compile(r"^[HS][AS] \d+ (?:to|for) (?P<parent>.+)$")
_SUBSTITUTE = re.compile(r"^[HS]S \d+ for ")


def canonical_code(display_code: str) -> str:
    """'HB 471 w/ HA 1, HA 2' -> 'HB 471'."""
    return _SUFFIX.sub("", display_code).strip()


def parent_code(code: str) -> str | None:
    """Immediate parent of a canonical code, or None for an original bill/resolution."""
    match = _PARENT.match(code)
    return match.group("parent") if match else None


def root_code(code: str) -> str:
    """The original bill/resolution at the root of a code's family."""
    while (parent := parent_code(code)) is not None:
        code = parent
    return code


def is_substitute(code: str) -> bool:
    return bool(_SUBSTITUTE.match(code))


def substitute_depth(code: str) -> int:
    """How many substitutions deep a code is: 'HS 2 for HB 5' -> 1, 'HB 5' -> 0."""
    return code.count(" for ")


def assign_families(items: pd.DataFrame) -> pd.DataFrame:
    """Add ``parent_code``, ``family_code`` and ``family_id`` columns to normalized items.

    ``family_id`` is the LegislationId of the root item. If the root isn't in the
    data (it shouldn't happen within one session), the item's own id is used.
    """
    items = items.copy()
    items["parent_code"] = items["code"].map(parent_code)
    items["family_code"] = items["code"].map(root_code)
    id_by_code = dict(zip(items["code"], items["legislation_id"]))
    items["family_id"] = [
        id_by_code.get(family_code, own_id)
        for family_code, own_id in zip(items["family_code"], items["legislation_id"])
    ]
    return items


def _first_text(*values) -> str | None:
    """First value that is a non-empty string (pandas uses NaN for missing text)."""
    return next((value for value in values if isinstance(value, str) and value), None)


def pick_lead(members: pd.DataFrame) -> pd.Series:
    """The version of a family that is "live": the newest substitute that hasn't
    itself been replaced, or the original if it was never substituted."""
    versions = members[members["type"] != "Amendment"]
    live = versions[versions["stage"] != SUBSTITUTED]
    candidates = live if not live.empty else versions
    if candidates.empty:  # family made only of amendments (orphaned root)
        candidates = members
    ranked = candidates.assign(depth=candidates["code"].map(substitute_depth))
    return ranked.sort_values(["depth", "introduced"]).iloc[-1]


def build_families(items: pd.DataFrame) -> pd.DataFrame:
    """One row per family, described by its lead version, with member counts."""
    rows = []
    for family_id, members in items.groupby("family_id", sort=False):
        lead = pick_lead(members)
        root = members[members["legislation_id"] == family_id]
        root = root.iloc[0] if not root.empty else lead
        rows.append(
            {
                "family_id": family_id,
                "family_code": root["code"],
                "lead_id": lead["legislation_id"],
                "display_code": lead["code"],
                "type": root["type"],
                "chamber": root["chamber"],
                "sponsor": lead["sponsor"],
                # Substitutes often have no short title of their own.
                "short_title": _first_text(lead["short_title"], root["short_title"]),
                "long_title": _first_text(lead["long_title"], root["long_title"]),
                "synopsis": _first_text(lead["synopsis"], root["synopsis"]),
                "status": lead["status"],
                "stage": lead["stage"],
                "category": lead["category"],
                "introduced": members["introduced"].min(),
                "last_action": members["last_action"].max(),
                "substitute_count": int(members["code"].map(is_substitute).sum()),
                "amendment_count": int((members["type"] == "Amendment").sum()),
                "url": lead["url"],
            }
        )
    return pd.DataFrame(rows)
