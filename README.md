# Your Delaware Legislators

**Version 0.1.0, public beta.** Find your Delaware state senator and representative and see what they've been doing in the General Assembly.

1. Enter a Delaware address, or pick your districts from a list.
2. See your state senator and representative.
3. View their contact details, years of service, committees, the legislation they sponsored and every roll call vote.
4. Follow links to the official records on [legis.delaware.gov](https://legis.delaware.gov).

This is not an official State of Delaware site.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m billtracker.pipeline      # download the session's bills -> data/legislation.csv (a few minutes)
streamlit run app.py                # open the page
```

Legislator details, sponsorships and votes are fetched live when someone looks a legislator up. The bill data in `data/legislation.csv` (which bills passed, how they group into families, their topics) is refreshed only when you rerun `python -m billtracker.pipeline`. There's deliberately no refresh button on the public page.

Run the tests with `pytest`. They don't touch the network.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): modules, data flow, address privacy, tests
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md): every external endpoint, caching, data freshness and known limitations
- [docs/DEFERRED_FEATURES.md](docs/DEFERRED_FEATURES.md): what 0.1.0 removed from the earlier bill tracker, and ideas for later
