# crowdflow

A 13F positioning factor built on a **dynamically selected manager universe**.

Instead of fixing a list of famous managers, the universe is re-derived every
quarter from the filings themselves: managers are ranked on their lagged
capacity to transmit common demand shocks into equity prices, and the top names
by that score form the universe for the following quarter. Selection is never
based on realised performance.

---

## Quick start

```bash
git clone <repo> && cd crowdflow
make setup          # editable install + dev extras
make test           # 79 tests, no network required
make demo           # full pipeline against generated EDGAR fixtures
```

`make demo` needs no network, no SEC credentials and no vendor data. It
generates EDGAR-shaped bytes, seeds them into the HTTP cache, and runs ingest →
curate → universe → factors → backtest end to end.

**The demo numbers describe the simulator, not markets.** They exist to prove
the pipeline runs and to exercise the parser and the point-in-time layer against
data whose ground truth is known. Nothing in the demo output is evidence about
any factor.

---

## Running against real data

Two external inputs are required.

### 1. SEC EDGAR

EDGAR rejects requests without a real contact address in the User-Agent, so set
one before ingesting:

```bash
export CROWDFLOW_USER_AGENT="Your Name your.email@domain.com"
make ingest
```

Requests are rate-limited to 6/s against the SEC's 10/s ceiling, and every
response is cached on disk content-addressed, so a re-run costs nothing.

### 2. A price and identifier panel

EDGAR gives positions in CUSIPs and dollars. It does not give returns, volumes,
shares outstanding or split factors, and it does not tell you which CUSIP maps
to which security over time. Supply both:

**Price panel** — CSV with columns

| column | meaning |
|---|---|
| `instrument_id` | stable security identifier (PERMNO, FIGI, …) |
| `date` | trading date |
| `price` | close, unadjusted |
| `volume` | shares traded |
| `shares_outstanding` | for market cap |
| `cum_split_factor` | cumulative split adjustment |
| `ret` | total return, delisting-inclusive |

**Crosswalk** — CSV mapping `cusip` → `instrument_id`, ideally dated
(`start_date`, `end_date`), because CUSIPs are reassigned.

CRSP is the right source: it is survivorship-free and handles delisting returns,
which matter here because forced liquidation is one of the mechanisms the factor
is trying to capture. A free source (`StooqLoader`) is included and is
explicitly documented as survivorship-biased — usable for plumbing, not for
inference.

```bash
make run PRICES=path/to/panel.csv CROSSWALK=path/to/crosswalk.csv
```

Full sequence, including a cheap first pass that validates the crawl before
committing to hours of it: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## Layout

```
src/crowdflow/
  config.py            frozen dataclasses; every parameter, fingerprinted per run
  ingest/              EDGAR client, full-index discovery, SGML/XML parsing
  curate/              identifiers, filer resolution, the bitemporal store
  market/              price reference data, and the fixture generator
  signal/              manager footprint, universe selection, stock factors
  evaluate/            rebalance calendar, costs, backtest engine, metrics
  report/              memo generation
  pipeline.py          the five stages, wired
data/
  00_raw/              cached EDGAR responses (content-addressed, gzipped)
  10_parsed/           filing manifest
  20_curated/          holdings store, revision log, ledger, audits
  30_features/         footprints, scores, universe, factors
  40_results/          backtest output
```

Stages are numbered because the interesting failures happen *between* them.
Each stage writes its output to disk so a reviewer can stop and read the layer
rather than trusting the layer above it.

---

## Point-in-time discipline

Every 13F fact carries two dates, and conflating them is the standard way a 13F
backtest acquires lookahead:

- **valid time** — the quarter the positions describe (`period_end`);
- **transaction time** — the instant the fact became public (`knowledge_ts`,
  derived from EDGAR's `acceptanceDateTime`, interpreted Eastern and rolled to
  the next session when acceptance is after the close).

The store answers exactly one question:

```python
store.as_of(period_end, knowledge_date)
```

and the factor layer is not permitted to reach around it. Both the current and
prior quarter are always materialised at the same vantage, so a
quarter-on-quarter position change never mixes what was known then with what is
known now.

Three specifics this gets right, each with tests:

- **The 45-day deadline is a floor, not a schedule.** A quarter activates on the
  first rebalance date where a threshold share of the *selected universe* has
  actually filed, with a hard backstop so one chronically late filer cannot
  stall the period.
- **Amendments restate history.** `RESTATEMENT` replaces the table;
  `NEW HOLDINGS` is additive and is what a lapsed confidential-treatment order
  looks like. An amendment is a later *version* of a filing, never a competing
  report — it can neither subsume its own original nor survive when the filing
  it amends is subsumed.
- **Confidential treatment means the positions were genuinely not public.** The
  store reproduces that ignorance instead of backfilling it.

See [`docs/DATA.md`](docs/DATA.md) for the audit, regenerable with
`make data-report`.

---

## Configuration

`config/default.yaml` holds every parameter. A run is fully described by that
file plus a git SHA; the config's SHA-256 fingerprint is stamped on each
artifact. Environment overrides: `CROWDFLOW_USER_AGENT`, `CROWDFLOW_DATA_ROOT`,
`CROWDFLOW_OFFLINE`.

`config/families.yaml` holds manual filer-family merges. It is empty by default
and deliberately so: name similarity is not evidence of a shared investment
process, and an unverified merge destroys the independence the factor measures.

---

## Commands

| command | what it does |
|---|---|
| `make test` | test suite, no network |
| `make demo` | generate fixtures, run everything offline |
| `crowdflow datasets` | bulk path: ~50 DERA zips → the curated store (2013Q2+) |
| `make ingest` | raw path: crawl EDGAR per filing (whole archive, hours) |
| `make run PRICES=… CROSSWALK=…` | full pipeline on real data |
| `crowdflow run --source dera --prices … --crosswalk …` | full pipeline on the store `crowdflow datasets` built |
| `make data-report` | regenerate `docs/DATA.md` |
| `make report` | build the memo PDF |
| `make lint` | ruff |

Individual stages are also available: `crowdflow ingest`, `crowdflow curate`,
`crowdflow run`, `crowdflow demo`, `crowdflow report`.

Both ingestion paths converge on the same curated store, built by the same
functions, which is what makes `crowdflow datasets --cross-validate N`
meaningful: it re-parses N raw submissions and compares them row-for-row
against the SEC's own extraction. Neither source can perform that check on
itself.
