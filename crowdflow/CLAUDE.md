# CLAUDE.md

Context for agent sessions in this repository.

## What this is

A 13F positioning factor with a **dynamically selected manager universe**. The
universe is re-derived each quarter from a rule that ranks managers on their
lagged capacity to transmit demand shocks into prices, rather than being a
hand-picked list. Selection never uses realised performance.

This is a take-home for a quant research role. The author has to defend every
choice in a 60-minute technical session, so **explanations matter as much as
code**. When you change something, say why in the docstring, not just in chat.

## Status

79 tests pass, and the **data layer has now been built and validated against
real EDGAR end to end**: the full 2013Q2-2026Q1 base (58.0M curated positions,
397,833 filings, 16,327 filers) lives in `data/20_curated`, built by
`crowdflow datasets` with acceptance timestamps from the submissions API.
`docs/BASE_VALIDATION.md` (regenerable via `scripts/validate_base.py`) pins
it: PIT mechanics sampled clean on the real archive, raw-parser-vs-DERA
cross-validation at 100%, Berkshire anchors to the dollar, filing-lag and
acceptance-timezone behaviour matching independent measurements.

The signal/backtest layers have NOT been run on real data yet — they still
need a price panel (see RUNBOOK step 3) and carry known issues listed in the
session memory (delisting returns unused, crosswalk resolve bug, cost-model
scaling). Backtest numbers anywhere in docs still describe the simulator.

## Architecture

```
src/crowdflow/
  config.py       frozen dataclasses; every parameter, SHA-fingerprinted per run
  ingest/
    client.py     EDGAR HTTP: rate limit, content-addressed disk cache, retries
    discovery.py  form.idx crawl + per-CIK submissions JSON (acceptance times)
    infotable.py  SGML envelope, XML and pre-2013 fixed-width parsers
    datasets.py   SEC DERA structured datasets + cross-validation vs raw filings
  curate/
    identifiers.py  CUSIP check digit, repair, security master
    filers.py       reporting groups (union-find), CIK succession
    bitemporal.py   THE POINT-IN-TIME STORE. Read this first.
    assemble.py     ordered curation stages + rejection ledger
  market/
    reference.py  price panel loaders (CRSP preferred, Stooq documented as biased)
    simulate.py   EDGAR-shaped fixture generator
  signal/
    footprint.py  impact / centrality / turnover per manager
    selection.py  eligibility, scoring, hysteresis
    factors.py    stock-level factors incl. Greenwood-Thesmar fragility
  evaluate/
    calendar.py     activation by observed coverage, not the 45-day deadline
    costs.py        half-spread + square-root impact + borrow
    engine.py       monthly loop, quantile and z-weighted portfolios
    metrics.py      Newey-West, deflated Sharpe
    attribution.py  regression on market/size/momentum/reversal/illiquidity
  report/memo.py  the deliverable PDF, built from artifacts on disk
```

Data lake is numbered `00_raw` → `40_results` because the interesting failures
happen *between* stages and a reviewer must be able to stop and read a layer.

## Invariants — do not break these

1. **`store.as_of(period_end, knowledge_date)` is the only way holdings enter
   the factor layer.** Nothing may read `store.holdings` directly to build a
   signal. Both the current and prior quarter are materialised at the *same*
   vantage, so a quarter-on-quarter change never mixes what was known then with
   what is known now.

2. **Amendment semantics come from the cover page, never from a guess.**
   `RESTATEMENT` replaces the filer's table for that period; `NEW HOLDINGS` is
   additive (a lapsed confidential-treatment order); missing is treated as
   restatement, the conservative choice. Getting `NEW HOLDINGS` wrong deletes a
   whole quarter's book and replaces it with a handful of rows, silently.

3. **Value scale is detected per filing, not read off the calendar.** The
   thousands-to-dollars cutover keys on the *filing* date, so 2022Q4 books filed
   in 2023 report whole dollars, and a tail of filers ignores the rule entirely.

4. **An amendment is a version, not a competing report.** It must never enter
   the largest-book contest in `build_reporting_groups`, or it subsumes its own
   original and the original vanishes from the revision log.

5. **Nothing is merged on name similarity.** `normalise_name`,
   `detect_cik_succession` and `detect_residual_duplication` only *propose*;
   merges require a human entry in `config/families.yaml`.

6. **Failures must be loud.** A parse that recovers zero rows while the cover
   page declares entries is a `PARSE FAILURE` warning, not an empty filing. A
   missing dataset quarter raises. Silent zeros are the bug class this
   repository exists to prevent.

## Running it

```bash
make setup && make test          # 63 tests, no network
make demo                        # full pipeline on generated fixtures, offline
```

Real data needs two things. EDGAR needs no credentials — only a contact address
in the User-Agent, or it returns 403:

```bash
export CROWDFLOW_USER_AGENT="Name email@domain.com"
crowdflow datasets --cross-validate 25 -v    # bulk path: ~50 zips -> curated store
crowdflow run --source dera --prices panel.csv --crosswalk xwalk.csv -v
# or, raw path (whole archive, one request per filing — hours):
crowdflow ingest --max-filers 50 -v          # cheap smoke test first
crowdflow run --prices panel.csv --crosswalk xwalk.csv -v
```

The price panel is the part that needs a subscription. See `docs/RUNBOOK.md` for
the CRSP column mapping — in particular use `ncusip` not `cusip`, and make sure
returns are delisting-inclusive, because forced liquidation on the way to a
delisting is one of the mechanisms the factor is trying to capture.

## Two ingestion paths, deliberately

`datasets.py` (DERA structured TSVs) is fast — about fifty downloads — and hands
over the `OTHERMANAGER` graph directly, but starts at 2013Q2 and makes you
inherit the SEC's parsing with no way to check it. `infotable.py` (raw filing
bytes) covers the whole archive and is auditable, but costs one request per
filing and the pre-2013 layouts vary by filing agent.

Both paths end in the **same** `20_curated` store, built by the same functions
(`classify_instrument`, `clean_cusip_column`, `build_reporting_groups`,
`derive_knowledge_ts`, the bulk twin of `resolve_value_scale`):
`crowdflow datasets` downloads, curates, and fetches `acceptanceDateTime` per
CIK (the one PIT field DERA lacks; `--no-acceptance` skips it at the cost of
one conservative day). `crowdflow run --source dera` then consumes that store
without touching the raw crawl.

The dataset URL scheme changed mid-archive and was probed against the live
server: calendar quarters through `2023q4`, a one-off `01jan2024-29feb2024`
stub, then rolling Mar–May / Jun–Aug / Sep–Nov / Dec–Feb receipt windows.
Requesting `2024q1` 404s — see `windows_between`.

`cross_validate()` re-parses a random sample of raw submissions and compares row
counts and value totals against DERA. Neither source can perform that check on
itself. **Agreement below 95% means stop and investigate before trusting
either.**

## Known gaps

- The raw-path parser has now been validated against real EDGAR: a 1,040-filing
  crawl parsed 100%, and 105 filings cross-checked against DERA matched row
  counts 105/105 (value differences fully explained by the option/debt filter).
  Pre-2013 coverage is still only as good as one real fixture; expect layout
  bugs there — the leading open-source parser reports ~93% success on that era,
  so 100% is not the target, *loud* failure is.
- CUSIP reassignment is implemented (the security master keys on `(cusip, date)`)
  but the fixtures contain no reassignment, so that path is untested end to end.
- Backtest numbers currently describe the simulator. Regenerate `docs/DATA.md`
  and the memo (`crowdflow report --real-data`) only after a real run.

## Conventions

- Code and documentation in English; the repository owner writes Portuguese, so
  chat can be Portuguese.
- Docstrings explain *why*, especially for anything that looks arbitrary. A
  reviewer will ask "why 0.40/0.40/0.20" and "why hysteresis at 25/35".
- Every data-quality decision is counted, not asserted — the rejection ledger
  goes to disk and `scripts/data_report.py` regenerates `docs/DATA.md` from it.
- New behaviour needs a test whose docstring states the failure mode it pins.
  Several existing tests exist only to document a bug that was already fixed;
  that is intentional.
