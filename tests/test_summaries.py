from types import SimpleNamespace

import pytest

from billtracker import pipeline
from billtracker.families import build_families
from billtracker.summaries import (
    ClaudeSummarizer,
    SummaryStore,
    summarize_bills,
    summarize_categories,
)


class FakeSummarizer:
    """Records calls and returns a canned summary."""

    def __init__(self, reply: str | None = "A summary."):
        self.reply = reply
        self.calls = []

    def __call__(self, system, prompt, effort="low"):
        self.calls.append(prompt)
        return self.reply


@pytest.fixture
def families(raw_rows):
    return build_families(pipeline.build_items(raw_rows))


def test_summarize_bills_writes_and_then_reuses_cache(families, tmp_path):
    store = SummaryStore(tmp_path / "summaries.json")
    summarizer = FakeSummarizer()

    assert summarize_bills(families, store, summarizer, max_workers=1) == len(families)
    assert summarize_bills(families, store, summarizer, max_workers=1) == 0  # all cached
    assert len(summarizer.calls) == len(families)

    reloaded = SummaryStore(tmp_path / "summaries.json")
    assert reloaded.bill_summaries() == {fid: "A summary." for fid in families["family_id"]}


def test_changed_text_is_resummarized(families, tmp_path):
    store = SummaryStore(tmp_path / "summaries.json")
    summarize_bills(families, store, FakeSummarizer(), max_workers=1)

    changed = families.copy()
    changed.loc[0, "synopsis"] = "A brand new synopsis."
    summarizer = FakeSummarizer("Updated.")
    assert summarize_bills(changed, store, summarizer, max_workers=1) == 1
    assert store.bill_summaries()[changed.loc[0, "family_id"]] == "Updated."


def test_limit_and_declined_summaries(families, tmp_path):
    store = SummaryStore(tmp_path / "summaries.json")
    assert summarize_bills(families, store, FakeSummarizer(None), max_workers=1) == 0
    assert store.bill_summaries() == {}
    assert summarize_bills(families, store, FakeSummarizer(), limit=1, max_workers=1) == 1


def test_summarize_categories_includes_bill_summaries(families, tmp_path):
    store = SummaryStore(tmp_path / "summaries.json")
    summarize_bills(families, store, FakeSummarizer("Bill gist."), max_workers=1)

    summarizer = FakeSummarizer("Trends.")
    written = summarize_categories(families, store, summarizer)

    assert written == families["category"].nunique()
    assert all("Bill gist." in prompt for prompt in summarizer.calls)
    assert summarize_categories(families, store, summarizer) == 0  # cached


def _fake_client(stop_reason: str, blocks: list) -> SimpleNamespace:
    response = SimpleNamespace(stop_reason=stop_reason, content=blocks)
    create = lambda **kwargs: response  # noqa: E731
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_claude_summarizer_returns_only_text_blocks():
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="  The summary.  "),
    ]
    summarizer = ClaudeSummarizer(client=_fake_client("end_turn", blocks))
    assert summarizer("system", "prompt") == "The summary."


def test_claude_summarizer_returns_none_on_refusal():
    summarizer = ClaudeSummarizer(client=_fake_client("refusal", []))
    assert summarizer("system", "prompt") is None
