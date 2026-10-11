"""Read and write the tracker's data files under ``data/``."""

from pathlib import Path

import pandas as pd

from billtracker import config
from billtracker.families import build_families

DATE_COLUMNS = ["introduced", "last_action"]


def save_items(items: pd.DataFrame, path: Path = config.LEGISLATION_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items.to_csv(path, index=False)


def load_items(path: Path = config.LEGISLATION_CSV) -> pd.DataFrame:
    """Every piece of legislation (one row each), as written by the pipeline."""
    items = pd.read_csv(path, parse_dates=DATE_COLUMNS)
    text_columns = ["sponsor", "short_title", "long_title", "synopsis", "parent_code"]
    items[text_columns] = items[text_columns].astype("object").where(items[text_columns].notna(), None)
    return items


def load_families(path: Path = config.LEGISLATION_CSV) -> pd.DataFrame:
    """One row per bill/resolution family."""
    return build_families(load_items(path))


def load_watchlist(path: Path = config.WATCHLIST_FILE) -> set[int]:
    """Legislation ids listed one per line; blank lines and '#' comments are ignored."""
    if not path.exists():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(int(line))
    return ids
