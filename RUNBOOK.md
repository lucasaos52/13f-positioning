# Running against real data

Everything in `docs/DATA.md` and the memo was produced from generated fixtures.
This is the sequence that replaces them with real numbers.

## What you need, and what you do not

**EDGAR needs no credentials.** 13F filings are public. The SEC's only
requirement is a User-Agent header carrying a contact address, so that they can
reach you if your crawler misbehaves. That is identification, not
authentication — there is no account and no password.

```bash
export CROWDFLOW_USER_AGENT="Your Name your.email@domain.com"
```

Without it EDGAR returns 403 on every request, and the client warns you at
startup rather than letting you discover it 200 requests in.

**The price panel does need a subscription.** CRSP through WRDS is the right
source. Those credentials are institutional and usually tied to your university
or employer login — keep them in your own environment. This pipeline never asks
for them: you export the data yourself and hand the pipeline two CSV files.

---

## Step 1 — prove the plumbing on a small slice

A full 13F history is tens of thousands of filers and millions of holdings rows.
Do not start there. Crawl two years and the most prolific filers first:

```bash
crowdflow ingest --first-quarter 2022Q1 --last-quarter 2023Q4 --max-filers 50 -v
```

Expect roughly ten minutes. What you are checking:

- the User-Agent is accepted (no 403s in the log);
- `form.idx` parses — the manifest is non-empty and the form mix looks like
  `13F-HR` dominant with a minority of `13F-HR/A` and `13F-NT`;
- `acceptanceDateTime` came back populated, since that is what the whole
  point-in-time layer runs on.

`--max-filers` keeps the busiest filers, which is a severe size-and-longevity
bias. It exists to prove the pipeline works. Never report a number computed
under it.

## Step 2 — curate the slice and read the ledger

```bash
crowdflow curate --first-quarter 2022Q1 --last-quarter 2023Q4 -v
```

Then generate the audit and read it before going further:

```bash
python scripts/data_report.py --out docs/DATA_real.md \
  --first-quarter 2022Q1 --last-quarter 2023Q4 \
  --label "SEC EDGAR, 50 filers, 2022-2023"
```

Four things in that report tell you whether the parse is sound:

| Check | Healthy | If not |
|---|---|---|
| parse failures | 0 | inspect the failing accessions in the ledger |
| `cusip_unresolved` | under ~0.5% of rows | your filers may hold many foreign or unlisted lines |
| `scale_source = calendar` | a small minority | detection is failing; check implied prices |
| filed by day 45 | 75–90% | far outside that, check the acceptance timestamps parsed |

Real EDGAR will be messier than the fixtures. Rejection counts that are larger
than the fixture run are expected; counts that are *zero* where the fixtures had
some are the suspicious case, because it usually means a filter silently stopped
matching.

## Step 3 — export the price panel

Two files from CRSP (or your vendor).

**Price panel** — daily, one row per security-day:

| column | CRSP source | notes |
|---|---|---|
| `instrument_id` | `permno` | stable across ticker and CUSIP changes |
| `date` | `date` | trading days only |
| `price` | `abs(prc)` | CRSP negates when it is a bid/ask midpoint |
| `volume` | `vol` | shares |
| `shares_outstanding` | `shrout` × 1000 | CRSP reports in thousands |
| `cum_split_factor` | `cfacshr` | cumulative share adjustment |
| `ret` | `ret` | **delisting-inclusive** — use `dlret` where `ret` is missing |

That last row is the one that matters most for this factor. Forced liquidation
on the way to a delisting is one of the mechanisms the signal is trying to
capture; a panel that drops delisted names removes exactly the observations that
carry the effect.

**Crosswalk** — CUSIP to instrument, dated:

| column | CRSP source |
|---|---|
| `cusip` | `ncusip` (the *historical* CUSIP, not `cusip`) |
| `instrument_id` | `permno` |
| `start` | `namedt` |
| `end` | `nameendt` |

Use `ncusip`, not `cusip`. CRSP's `cusip` field is the security's *current*
identifier; `ncusip` is what it was at the time, which is what a 13F filed in
2016 actually contains. Getting this wrong silently mismaps every name that
changed identifier during the sample.

## Step 4 — the full run

```bash
export CROWDFLOW_USER_AGENT="Your Name your.email@domain.com"
crowdflow ingest -v                    # hours; resumable, the cache is on disk
crowdflow run --prices crsp_panel.csv --crosswalk crsp_xwalk.csv -v
```

Ingest is resumable. Every response is cached content-addressed on disk, so an
interrupted crawl costs you nothing — re-running skips everything already
fetched. Rate limiting is 6 requests per second against the SEC's ceiling of 10.

## Step 5 — regenerate the deliverables

```bash
python scripts/data_report.py --out docs/DATA.md --label "SEC EDGAR"
crowdflow report --out memo/crowdflow_memo.pdf --real-data
```

`--real-data` drops the simulated-data warnings from the memo. Pass it only
after a real run: the flag exists so that a fixture memo cannot be mistaken for
an evidential one, and passing it early defeats the point.

---

## Reading the output honestly

When the real numbers arrive, look at these before the Sharpe:

1. **The attribution table.** If `alpha_t_nw` is small and `r2` is high, the
   factor is a repackaging of size, momentum, reversal or illiquidity. That is
   the result that should kill it, and it is not a failure of the work — it is
   the work doing its job.
2. **The horizon IC sign pattern.** Positive at one month and negative at twelve
   is transient price pressure. Positive throughout is information. Flat is
   noise. This is the hypothesis test; the Sharpe is not.
3. **The yearly breakdown.** A factor carried by one or two years across a
   ten-year sample has not been demonstrated, whatever the pooled t-statistic
   says.
4. **The deflated Sharpe.** Recompute it against every variant you actually
   examined, not just the ones that reached the memo. The correction only works
   if the trial count is honest.
