# data-quality-check — the audit trail of the 13F ↔ market-data merge

Every data-quality diagnostic run on the factor layer, with scripts,
results and verdicts. Each check answers a specific "can I trust this?"
question with a number, not an opinion. All findings dated 2026-08-16.

## Checks in this folder

### 1. `crosswalk_audit.py` → `results/AUDIT_REPORT.md`

**Question:** the CUSIP→ticker map is static and tickers change — how much
damage do CUSIP reassignments and ticker recycling actually do?

**Design:** (A) reassignment events = same issuer stem (`cusip6`),
instrument A dies exactly when B is born (gap ≤ 2 quarters, ≥5 holders
both sides) → every holder of A is a FAKE exit; contamination rate =
fake exits ÷ true exit flow (sampled in-base). (B) recycling suspects =
mapped tickers whose Yahoo history starts >100 days after the instrument
first appears in filings.

**Verdict:**
- Reassignment: 1,574 events / 51 quarters, ~348 fake exits/quarter vs
  ~160k true → **0.22% contamination**. exit_rate / dbreadth / births are
  safe without correction; full pair list in `results/reassignment_events.csv`
  for optional stitching.
- Recycling: 176/3,927 tickers (4.5%) flagged — known spin-offs/IPOs
  (DOW, LEVI, ONTO, S). Failure mode is **closed** (Yahoo does not stitch
  the old company's history under a recycled symbol → no-price windows are
  excluded by the px≥$1 decision filter): exclusion, never mispricing.
- Ticker RENAMES (FB→META) are correct by construction: CUSIP is the key,
  the map points to the current symbol, Yahoo reindexes full history
  under it.

### 2. `etf_universe_check.py`

**Question:** do ETF instruments leak into the tradable universe or the
signals?

**Verdict:** never tradable (1 of 7,886 audited ETF CUSIPs in the
crosswalk; 0 ETF tickers in the price panel) — but ETF lines are ~12–15%
of book VALUE inside filings and inflate conviction thresholds. Whether
that matters → check 3.

### 3. `vote_ranking_check.py`

**Question:** does purging ETF lines from book weights change who the
conviction census votes for?

**Verdict:** 18.5% of individual votes change and +17% stock votes are
freed (bets hidden behind SPY) — yet the per-stock ranking is invariant
(rank corr 0.974, top-100 overlap 97/100) and the paired signal delta is
t=+0.08 over 50 quarters (`factors/champion_noetf`). **Innocuous
contamination**: uniform bias cannot distort a rank-based signal.
Contrast: untreated stock splits are DIFFERENTIAL distortion and did
require a fix (see check 4).

## Related checks living elsewhere (pointers)

- **Modal-atom split detector** — `factors/general_predictive_signals/
  signal_defs.py` + `run_signals.py`: Yahoo's raw Close is retroactively
  split-adjusted, so price-based split detection is impossible; splits
  are detected from the holders' own share-count atoms (validated 6/6 on
  famous splits). The one contamination that IS differential and needed
  fixing.
- **Bad-print poisoning** — found via `factors/copycat_pop` (a
  +100,000%/day Yahoo print made every event in 2024Q4 look like
  −17.67%): fixed project-wide by median (not mean) universe benchmarks
  and ±50% clipping of window returns in all event studies.
- **Survivorship boundary** — documented in `factors/general_plan/
  run_all.py` docstring and quantified in
  `factors/fund_performance` (delisted names absent from Yahoo; signals
  computed on the full 13F cross-section, returns restricted to the
  mappable set; bias direction: against the short leg, slightly for the
  long).
- **Coverage logging** — every module logs the mapped fraction of book
  value per quarter (~70–85%).
- **ETF instrument flag list** — `factors/ETF_strat/data/
  etf_universe_flags.csv` (Nasdaq directory + SEC N-CEN + OpenFIGI,
  ticker-recycling handled, 106 false matches blocked).

## One-line summary for the report

> The 13F↔Yahoo merge is keyed on CUSIP and mapped to current tickers by
> issuer name: renames are correct by construction, recycling fails
> closed, and the one real blind spot — same-issuer CUSIP changes — is
> audited at 0.22% of exit flow with the full event list on disk.
