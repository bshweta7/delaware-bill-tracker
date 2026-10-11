"""Fetch the current session's legislation and write ``data/legislation.csv``.

Run from the project root:

    python -m billtracker.pipeline                  # current session
    python -m billtracker.pipeline --assembly 152   # a past session
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from billtracker import config
from billtracker.categories import categorize
from billtracker.families import assign_families, build_families
from billtracker.legis_api import LegisClient
from billtracker.normalize import normalize_rows
from billtracker.stages import RESOLUTION_TYPES
from billtracker.storage import save_items

CSV_COLUMNS = [
    "legislation_id", "assembly", "code", "display_code", "type", "chamber",
    "sponsor", "short_title", "long_title", "synopsis", "status", "stage",
    "introduced", "last_action", "parent_code", "family_code", "family_id",
    "category", "url",
]


def categorize_items(items: pd.DataFrame) -> pd.DataFrame:
    """Categorize each item, then give every family member its family's category.

    Amendments have little text of their own, so they inherit from the family
    rather than being categorized on their own.
    """
    items = items.copy()
    items["category"] = [
        categorize(row.short_title, row.long_title, row.synopsis, row.type in RESOLUTION_TYPES)
        for row in items.itertuples()
    ]
    family_category = build_families(items).set_index("family_id")["category"]
    items["category"] = items["family_id"].map(family_category)
    return items


def build_items(raw_rows: list[dict]) -> pd.DataFrame:
    """Raw API rows -> one tidy, linked, categorized row per piece of legislation."""
    items = assign_families(normalize_rows(raw_rows))
    items = categorize_items(items)
    return items[CSV_COLUMNS].sort_values(["family_code", "introduced"]).reset_index(drop=True)


def refresh(assembly_id: int | None = None, client: LegisClient | None = None) -> pd.DataFrame:
    """Fetch, process and save a session. Returns the saved items."""
    client = client or LegisClient()
    assembly_id = assembly_id or client.current_assembly_id()
    items = build_items(client.fetch_all_legislation(assembly_id))
    save_items(items)
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Delaware legislation to CSV.")
    parser.add_argument("--assembly", type=int, help="General Assembly number (default: current).")
    parser.add_argument("--from-json", type=Path, help="Build from a saved list of raw API rows instead.")
    args = parser.parse_args()

    if args.from_json:
        items = build_items(json.loads(args.from_json.read_text(encoding="utf-8")))
        save_items(items)
    else:
        items = refresh(args.assembly)
    print(f"Saved {len(items)} items to {config.LEGISLATION_CSV}")


if __name__ == "__main__":
    main()
