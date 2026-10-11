"""AI summaries of bills and category trends, generated with Claude.

Summaries are cached in ``data/summaries.json`` and keyed by a hash of the text
they were generated from, so re-running only calls the API for bills whose
title or synopsis changed (for example, when a substitute is introduced).

Run from the project root:

    python -m billtracker.summaries            # summarize everything missing
    python -m billtracker.summaries --limit 20 # try a small batch first
"""

import argparse
import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import pandas as pd

from billtracker import config
from billtracker.storage import load_families

BILL_SYSTEM_PROMPT = (
    "You summarize Delaware General Assembly legislation for a public bill "
    "tracker. Write for a general reader in plain language. Say what the "
    "legislation would do and who it affects in 2-3 sentences. No preamble, "
    "no headings, no markdown. Do not speculate beyond the text provided."
)

TREND_SYSTEM_PROMPT = (
    "You analyze Delaware General Assembly legislation for a public bill "
    "tracker. Given every bill in one topic category this session, write a "
    "short trends briefing in plain language: 1) the main themes lawmakers "
    "are pursuing, 2) notable or high-impact bills (cite them by number, "
    "e.g. HB 233), and 3) what has actually passed or been signed versus "
    "what is stalled. Use at most three short paragraphs and no markdown "
    "headings. Ground every claim in the bills provided."
)

# Keep trend prompts to a reasonable size for the busiest categories.
MAX_BILLS_PER_TREND = 250

Summarizer = Callable[[str, str, str], str | None]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def bill_prompt(family: pd.Series) -> str:
    return (
        f"Legislation: {family['display_code']}\n"
        f"Short title: {family['short_title'] or 'n/a'}\n"
        f"Long title: {family['long_title'] or 'n/a'}\n"
        f"Synopsis: {family['synopsis'] or 'n/a'}\n"
        f"Current status: {family['status']}"
    )


def trend_prompt(category: str, families: pd.DataFrame) -> str:
    lines = [
        f"- {row.display_code} [{row.stage}]: {row.short_title or row.long_title}"
        + (f" | {row.ai_summary}" if isinstance(row.ai_summary, str) and row.ai_summary else "")
        for row in families.head(MAX_BILLS_PER_TREND).itertuples()
    ]
    return f"Category: {category}\nBills ({len(families)} total):\n" + "\n".join(lines)


class ClaudeSummarizer:
    """Thin wrapper around the Messages API that returns plain summary text."""

    def __init__(self, client: anthropic.Anthropic | None = None, model: str = config.SUMMARY_MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def __call__(self, system: str, prompt: str, effort: str = "low") -> str | None:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
            # If a safety classifier declines, retry on a fallback model server-side.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return None
        text = "".join(block.text for block in response.content if block.type == "text")
        return text.strip() or None


class SummaryStore:
    """JSON cache of generated summaries: ``{"bills": {...}, "categories": {...}}``."""

    def __init__(self, path: Path = config.SUMMARIES_JSON):
        self.path = path
        self.data = {"bills": {}, "categories": {}}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def get(self, section: str, key: str, source_hash: str) -> str | None:
        entry = self.data[section].get(str(key))
        if entry and entry["hash"] == source_hash:
            return entry["summary"]
        return None

    def put(self, section: str, key: str, source_hash: str, summary: str, model: str) -> None:
        self.data[section][str(key)] = {"hash": source_hash, "summary": summary, "model": model}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8")

    def bill_summaries(self) -> dict[int, str]:
        return {int(key): entry["summary"] for key, entry in self.data["bills"].items()}

    def category_summaries(self) -> dict[str, str]:
        return {key: entry["summary"] for key, entry in self.data["categories"].items()}


def summarize_bills(
    families: pd.DataFrame,
    store: SummaryStore,
    summarize: Summarizer,
    model: str = config.SUMMARY_MODEL,
    limit: int | None = None,
    max_workers: int = 4,
) -> int:
    """Summarize each family's lead legislation. Returns how many new summaries were written."""
    pending = []
    for _, family in families.iterrows():
        prompt = bill_prompt(family)
        source_hash = text_hash(prompt)
        if store.get("bills", family["family_id"], source_hash) is None:
            pending.append((family["family_id"], prompt, source_hash))
    if limit is not None:
        pending = pending[:limit]

    def run(job):
        family_id, prompt, source_hash = job
        return family_id, source_hash, summarize(BILL_SYSTEM_PROMPT, prompt, "low")

    written = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for family_id, source_hash, summary in pool.map(run, pending):
            if summary:
                store.put("bills", family_id, source_hash, summary, model)
                written += 1
                if written % 25 == 0:
                    store.save()  # don't lose progress on a long run
    store.save()
    return written


def summarize_categories(
    families: pd.DataFrame,
    store: SummaryStore,
    summarize: Summarizer,
    model: str = config.SUMMARY_MODEL,
) -> int:
    """Write one trends briefing per category. Returns how many were (re)generated."""
    bill_summaries = store.bill_summaries()
    families = families.assign(ai_summary=families["family_id"].map(bill_summaries))

    written = 0
    for category, group in families.groupby("category"):
        group = group.sort_values("introduced", ascending=False)
        prompt = trend_prompt(category, group)
        source_hash = text_hash(prompt)
        if store.get("categories", category, source_hash) is not None:
            continue
        summary = summarize(TREND_SYSTEM_PROMPT, prompt, "medium")
        if summary:
            store.put("categories", category, source_hash, summary, model)
            written += 1
    store.save()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI summaries with Claude.")
    parser.add_argument("--limit", type=int, help="Summarize at most this many bills.")
    parser.add_argument("--skip-trends", action="store_true", help="Only summarize bills.")
    args = parser.parse_args()

    families = load_families()
    store = SummaryStore()
    summarizer = ClaudeSummarizer()

    bills_written = summarize_bills(families, store, summarizer, limit=args.limit)
    print(f"Wrote {bills_written} bill summaries.")
    if not args.skip_trends:
        trends_written = summarize_categories(families, store, summarizer)
        print(f"Wrote {trends_written} category trend summaries.")


if __name__ == "__main__":
    main()
