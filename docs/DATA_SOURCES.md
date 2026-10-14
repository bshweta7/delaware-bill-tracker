# Data sources

Every external request the app makes, how it is cached, and what can go wrong. None of these sources needs an API key. They're public pages and endpoints, so their format can change without notice.

## Endpoints

All legis.delaware.gov requests send the `User-Agent` from `config.REQUEST_HEADERS` and time out after 60 seconds.

| Data | Request | Module | Cache (in app) | Retries |
|---|---|---|---|---|
| Districts for an address | `GET https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress` with `benchmark=Public_AR_Current`, `vintage=Current_Current`, `layers=all` | `districts.py` | **None**, deliberately (privacy) | None |
| Senators | `POST /json/Senate/GetSenators` | `legis_api.py` | 24 hours (`cached_roster`) | Up to 4 retries with backoff on 429/5xx |
| Representatives | `POST /json/House/GetRepresentatives` | `legis_api.py` | 24 hours (`cached_roster`) | As above |
| Sponsorships | `POST /json/AssemblyMember/GetSponsoredLegislation` with `personId`, `assemblyId` | `legis_api.py` | 1 hour (`cached_sponsorships`) | As above |
| Profile | `GET /LegislatorDetail?personId=…` (HTML; redirects to `/AssemblyMember/{GA}/{Name}`) | `legislators.py` | 24 hours (`cached_profile`) | None |
| Roll call votes | `GET /rss/RssFeeds/RollCalls?personId=…&assemblyId=…` (RSS) | `legislators.py` | 1 hour (`cached_roll_calls`) | 5 attempts when the reply isn't XML (see below) |
| Every bill in the session | `GET /AllLegislation` (to read the current General Assembly number), then `POST /json/AllLegislation/GetAllLegislation`, 20 rows per page, 4 pages at a time | `legis_api.py`, run by `pipeline.py` | Written to `data/legislation.csv`; the app caches the loaded file until it changes | Up to 4 retries with backoff |

The grid endpoints need a `sort` form field, even an empty one. Without it the site redirects to an error page.

## Caching and freshness

The cache is Streamlit's in-memory `st.cache_data`. It is per server process, shared by all visitors, and emptied when the process restarts.

| What the page shows | How fresh |
|---|---|
| Who represents each district | Up to 24 hours old |
| Contact details, committees, years of service | Up to 24 hours old |
| Sponsorships | Up to 1 hour old; the page shows when they were fetched |
| Roll call votes | Up to 1 hour old; the page shows when they were fetched |
| Whether each bill passed, its family and topic | As of the last `python -m billtracker.pipeline` run; the page shows the CSV's date |

Because sponsorships are live but bill outcomes come from the CSV, a legislator can have sponsored a bill the CSV doesn't contain yet. The page counts those and says they will be included after the next refresh. Pass counts can also lag: a bill signed after the last refresh still shows its old stage.

## Known limitations

**legis.delaware.gov**
- **The roll call feed is flaky.** About half of requests (more under concurrent load) return an HTML "Page not found" page with status 200 instead of RSS. The app retries up to 5 times with backoff (1, 2, 4, 8 s), then shows the votes as unavailable.
- **The roll call feed has no total**, so the app can't confirm a feed is complete. It can only detect outright failures.
- **The Senate feed includes votes to confirm the governor's nominees.** These have no bill; the app labels them "Confirm {name}".
- **Years of service are free text** typed by staff, in many formats ("House, 2010 - Present", "Senate, February 15, 2025 - Present", several terms with leadership posts in one line). The parser handles every format used by the members of the 153rd General Assembly. One profile lists no dates. The original text is always shown next to the parsed years, which are counted in whole years.
- **Profiles are parsed from HTML**, so a site redesign would break them.
- **Roster completeness:** both chambers have fixed sizes (21 Senate and 41 House districts, Delaware Constitution art. II, sec. 2), and vacant seats are still listed. The app warns when a district is missing and errors if a response holds fewer rows than its `Total`.

**US Census geocoder**
- **Only the first match is used**, and the page shows the matched address so the visitor can check it.
- **Some addresses won't match**, such as PO boxes, very new construction or misspelled streets. Those visitors can pick their districts from the list instead.
- **District boundaries are the Census Bureau's current vintage.** At the one address checked (Legislative Hall, Dover) they matched the state's own district map layer (FirstMap), but nothing checks this automatically.

**Elections**
- The next general election is calculated, not fetched: Delaware elects legislators in even years, on the Tuesday after the first Monday in November.
- Every House seat is up each time. Senate terms are staggered, and the app has no source for which Senate seats are up, so it links to elections.delaware.gov.

**Bill data (CSV)**
- Topics come from keyword rules, so some bills are misfiled.
- The list endpoint gives only a "last action" date, not a full history.
