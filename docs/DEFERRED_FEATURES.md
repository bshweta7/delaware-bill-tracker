# Deferred features

Version 0.1.0 narrowed the Delaware Bill Tracker to one page: Your Delaware Legislators. This lists what was removed and ideas for later. Nothing here is planned or promised.

## Removed in 0.1.0

The removed code is preserved in git history. The last commit with everything in place is `11b9712` (the merge of PR #2 into `dev`). The tabs and filters were removed from the page in one commit, and each backing module in a commit of its own (`git log --grep "chore: remove"`); that is where to start when restoring one.

| Feature | What it did | Removed code |
|---|---|---|
| **Overview tab** | Headline numbers for the session, stage-by-stage chart, outcomes and pass rate by topic, most active sponsors | `app.py` |
| **Timeline tab** | New legislation per week, bills enacted over time, topic-by-month heatmap | `app.py` |
| **Categories tab** | Per-topic stats, AI trend briefing, every bill in the topic | `app.py` |
| **Bill explorer tab** | Searchable table of every bill, with its family (substitutes, amendments), co-sponsors and "what happens next" | `app.py`, `billtracker/bill_detail.py` |
| **Sidebar filters** | Search, category, type, chamber, outcome, hide ceremonial resolutions | `app.py` |
| **AI summaries** | Plain-language Claude summaries of each bill and a trend briefing per topic, cached in `data/summaries.json`; CLI `python -m billtracker.summaries` | `billtracker/summaries.py`, the `anthropic` dependency |
| **Watchlist** | Filter to bills listed in `data/watchlist.txt` (that file, with 22 bill ids, was removed too) | `billtracker/storage.py`, `data/watchlist.txt` |
| **Dashboard statistics and charts** | Aggregations and Altair charts behind the removed tabs | `billtracker/stats.py`, `billtracker/charts.py` |
| **In-app data refresh** | "Refresh from legis.delaware.gov" button and first-run "Download legislation" button | `app.py`; run `python -m billtracker.pipeline` instead |

The data pipeline, bill families and topic categories are all **kept**, because the legislators page needs them to dedupe sponsorships and report outcomes and topics.

## Possible future enhancements

From the original goal for the legislators page:
- **Which Senate seats are up at an election.** Senate terms are staggered, so this needs a source such as the Department of Elections or Ballotpedia. Today the page links to elections.delaware.gov.
- **Campaign promises and candidate background.** These would come from campaign sites and news, so every claim needs a citation.

Operations, for a public site:
- **Scheduled data refresh**, for example a daily cron job running the pipeline, so the bill data doesn't depend on someone remembering.
- **A shared cache that survives restarts.** The current in-memory cache is per process; more traffic or several workers would mean more requests to legis.delaware.gov.
- **Monitoring of the upstream sources**, especially the flaky roll call feed and the free-text service field, to catch format changes.

Possible features to bring back, narrowed to a legislator:
- **Bill detail** for a legislator's own bills: family, co-sponsors and next step (from the removed Bill explorer).
- **Plain-language summaries** of the bills a legislator sponsored (from the removed AI summaries). They would need labeling and a review policy before going public.
- **Following specific bills or legislators** (from the removed watchlist), which would need accounts or local storage.

Known rough edges to fix:
- The page says "153th General Assembly" instead of "153rd". The ordinal suffix was never handled; this predates 0.1.0.
