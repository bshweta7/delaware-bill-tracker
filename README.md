# Delaware Bill Tracker

A Streamlit dashboard for every bill and resolution in the current Delaware General Assembly. Data comes from [legis.delaware.gov](https://legis.delaware.gov). The tracker:

- links each bill to its substitutes and amendments, so related legislation is grouped into a single **family**
- sorts legislation into topic categories (Education, Environment & Energy, Health…)
- shows how activity unfolds over the session
- generates plain-language **AI summaries** of each bill, and trend briefings for each category, with Claude
- looks up **your legislators** from your home address, with their sponsorship record, voting record, years in office and next election

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m billtracker.pipeline      # download the session -> data/legislation.csv (a few minutes; the site is slow)
streamlit run app.py                # open the dashboard
```

AI summaries are optional and need Claude API credentials (`ANTHROPIC_API_KEY`):

```bash
python -m billtracker.summaries --limit 20   # try a few first
python -m billtracker.summaries              # everything not yet summarized, plus category trends
```

Summaries are cached in `data/summaries.json`. A bill is only re-summarized if its title, synopsis or status changes. You can also generate a single bill's summary from the dashboard.

Run the tests with `pytest`.

## The dashboard

| Tab | What it shows |
|---|---|
| **Overview** | Headline numbers, where legislation stands (stage by stage), outcomes by topic, pass rate by topic, most active sponsors |
| **Timeline** | New legislation per week (bills / resolutions / amendments & substitutes), bills enacted over time, a topic-by-month heatmap |
| **Categories** | Per-topic stats, the AI trends briefing, and every bill in the topic with its summary |
| **Bill explorer** | A searchable, sortable table. Select a bill to see its summary, its full family (original, substitutes, amendments), its sponsors and its next step |
| **Your legislators** | Enter a home address (or pick from a list) to find your state senator and representative. For each: contact details, committees, years in office, the legislation they sponsored, split into lead (primary) sponsor, additional primary sponsor and co-sponsor (with how much passed, and topics), every roll call vote (filter to their "no" votes or missed votes), and when their seat is next on the ballot |

The sidebar filters every tab by search text, category, type, chamber, outcome, ceremonial resolutions and your watchlist. To add bills to the watchlist, put their legislation ids in `data/watchlist.txt`, one per line (the id is the number in a bill page's `LegislationId=` URL).

## How it works

```
legis.delaware.gov ──► legis_api ──► normalize ──► families ──► categories ──► data/legislation.csv
                                                                                    │
                       summaries (Claude) ◄─────────────────────────────────────────┤
                       data/summaries.json ──────────────────────────────► app.py ◄─┘
```

| Module | Responsibility |
|---|---|
| `billtracker/legis_api.py` | Pages through `POST /json/AllLegislation/GetAllLegislation` (20 rows per page, fetched in parallel) |
| `billtracker/normalize.py` | Raw JSON → tidy rows: dates, types, chamber, stage |
| `billtracker/stages.py` | Maps the site's statuses (including committee names) to ordered stages |
| `billtracker/families.py` | Parses display codes (`HA 1 to HS 1 for HB 233`) to link amendments and substitutes back to the original bill |
| `billtracker/categories.py` | Rule-based topics from keywords and the Delaware Code titles a bill amends |
| `billtracker/stats.py` | Pure-pandas aggregations used by the dashboard |
| `billtracker/charts.py` | Altair charts (colorblind-validated palette, light and dark) |
| `billtracker/summaries.py` | Claude summaries with a hash-keyed JSON cache |
| `billtracker/bill_detail.py` | Scrapes co-sponsors and "what happens next" from a bill page, on demand |
| `billtracker/districts.py` | Address → Senate and House district, via the US Census geocoder |
| `billtracker/legislators.py` | Legislator roster, profile pages (service, committees, contact), sponsorships and the roll call vote feed, on demand |
| `billtracker/pipeline.py` | CLI that ties fetching and processing together |

### The CSV

`data/legislation.csv` has one row per item: each bill, resolution, substitute and amendment. The `family_id` and `family_code` columns tie each item to its original bill. The other columns are: code, type, chamber, sponsor, short/long title, synopsis, raw status, stage, introduced date, last action date, category and URL.

### Caveats

- Categories come from keyword rules, not a human. They're right most of the time, but expect some misfiled bills.
- The site's "last action" date is the only action date the list endpoint provides. The "enacted over time" chart uses it as a stand-in for the signing date.
- AI summaries are generated from each bill's title and synopsis, not its full text.
- The **Your legislators** tab fetches live from legis.delaware.gov when you open a legislator, rather than from the CSV. Address lookups go to the [US Census geocoder](https://geocoding.geo.census.gov/) (free, no key). The app doesn't cache, log or write addresses to disk; an address stays in server memory only for that visitor's browser session.
- "Years in office" is read from the free-text "Legislative Service" field on each profile, so it's only as accurate as that text.
- The app can't yet tell which Senate seats are up at a given election (senators serve staggered four-year terms), so it links to the Department of Elections instead.
