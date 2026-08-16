# Data layer audit

Source: SEC EDGAR, DERA structured datasets, 2013Q2-2026Q1, acceptance times from submissions API. Quarters 2013Q2 to 2026Q1. Config fingerprint `d19553a22002`.


Every figure below is produced by `scripts/data_report.py` from the same objects the factor layer consumes. Nothing here is hand-copied.


## 1. Filing ledger

One row per document fetched, recording how it was parsed and why any of it was discarded. A filing is never silently dropped.

| stage | count |
|---|---|
| filings discovered | 397,833 |
| 13F-NT notices (no table by design) | 84,767 |
| 13F-HR/A amendments | 16,078 |
| parsed with an information table | 312,074 |
| tables fully rejected by class/id filters | 943 |
| parse failures | 0 |
| holdings rows retained | 58,032,157 |
| rows dropped: option overlays | 6,610,955 |
| rows dropped: debt (sshPrnamtType=PRN) | 965,597 |
| rows dropped: duplicate group reporting | 21,093,542 |


Option overlays and principal amounts are removed *before* any book total is computed. A `putCall` line reports notional exposure, not ownership, and a PRN line is face value of debt. Leaving them in inflates the book and distorts every downstream size ranking.


## 2. Value units

| period year | scale=1 | scale=1000 |
|---|---|---|
| 1987 | 0 | 1 |
| 2002 | 0 | 4 |
| 2003 | 0 | 5 |
| 2004 | 0 | 4 |
| 2005 | 0 | 4 |
| 2006 | 3 | 10 |
| 2007 | 12 | 24 |
| 2008 | 16 | 33 |
| 2009 | 17 | 56 |
| 2010 | 25 | 94 |
| 2011 | 28 | 169 |
| 2012 | 37 | 340 |
| 2013 | 284 | 11482 |
| 2014 | 439 | 16285 |
| 2015 | 438 | 17411 |
| 2016 | 443 | 17893 |
| 2017 | 441 | 18757 |
| 2018 | 513 | 20185 |
| 2019 | 643 | 21325 |
| 2020 | 778 | 22861 |
| 2021 | 1011 | 25571 |
| 2022 | 7367 | 22052 |
| 2023 | 27101 | 3060 |
| 2024 | 29511 | 2263 |
| 2025 | 32521 | 1701 |
| 2026 | 8503 | 353 |


SEC Release 34-95148 moved 13F values from thousands to whole dollars for filings made **on or after 2023-01-03**. Two things defeat a calendar rule:

1. the cutover keys on the *filing* date, not the period - a 2022Q4 book is filed in 2023 and reports whole dollars, so the period year is the wrong key;
2. 7377 filings after the cutover still report thousands.

Scale is therefore inferred per filing from the median implied price (`value / shares`): whole dollars land in a normal equity band, thousands land three orders of magnitude below. The calendar is only a last resort, recorded in the ledger as `scale_source='calendar'`.

| scale decided by | filings |
|---|---|
| detected | 302,071 |
| calendar | 9,984 |
| plausibility | 19 |


## 3. CUSIP hygiene

| outcome | rows |
|---|---|
| clean on arrival | 112,366,463 (99.88%) |
| leading zero restored | 48,099 (0.04%) |
| check digit reconstructed | 63,417 (0.06%) |
| unrecoverable, dropped | 25,739 (0.02%) |


The two corruption modes that actually occur are a leading zero eaten by a spreadsheet and a truncated check digit. Both are repaired only when the mod-10 double-add-double checksum confirms exactly one candidate; anything ambiguous is dropped rather than guessed. Share classes stay distinct - GOOG (02079K107) and GOOGL (02079K305) must never merge.


## 4. Filer deduplication

|  | count |
|---|---|
| distinct CIKs filing | 16,327 |
| filers after group resolution | 12,538 |
| duplicate holdings rows removed | 21,093,542 |


A parent files a combination report listing subsidiaries under `<otherManagers>`; the subsidiary files either a 13F-NT notice or - the dangerous case - its own duplicate table. Union-find over those edges, rebuilt every quarter because group membership changes, keeps one filing per group. Uncorrected, the same dollars appear twice and a crowding factor reads that as two managers independently agreeing.

Name-based clustering only *proposes* merges for human review (`config/families.yaml`); it never merges automatically, because distinct legal entities routinely share a brand.


579 candidate CIK successions detected (418 clean handoffs). A manager that re-registers under a new CIK is invisible to the otherManagers graph: its history is truncated at the handover, so the minimum-history screen rejects a manager that has been filing for a decade, and the universe records a spurious exit and entry mid-sample. These are proposals for review, never automatic merges.


| predecessor_name | predecessor_last_q | successor_name | successor_first_q | name_similarity |
|---|---|---|---|---|
| Alken Asset Management LLP | 2014Q3 | Alken Asset Management Ltd. | 2014Q4 | 1.00 |
| SIGULER GUFF ADVISERS, LLC | 2022Q4 | Siguler Guff Advisers, LLC | 2023Q1 | 1.00 |
| Sarofim Fayez | 2013Q3 | Fayez Sarofim & Co | 2013Q4 | 1.00 |
| CHUBB CORP | 2015Q4 | CHUBB LTD | 2016Q1 | 1.00 |
| Jump Trading, LLC | 2019Q1 | JUMP TRADING, LLC | 2019Q2 | 1.00 |
| PRINCETON CAPITAL MANAGEMENT INC | 2017Q3 | PRINCETON CAPITAL MANAGEMENT LLC | 2017Q4 | 1.00 |
| CAXTON ASSOCIATES LP | 2024Q4 | CAXTON ASSOCIATES LLP | 2025Q1 | 1.00 |
| Spot Trading L.L.C | 2017Q1 | SPOT TRADING L.L.C. | 2017Q2 | 1.00 |


## 5. Filing lag: the 45-day rule is a floor, not a schedule

| statistic | value |
|---|---|
| median lag (days) | 43 |
| p90 | 46 |
| p99 | 1378 |
| worst observed | 12831 |
| filed by day 45, mean quarter | 54.7% |
| filed by day 45, worst quarter | 0.0% |


Trading on day 46 would use a book that roughly 45% of filers had not yet disclosed. The rebalance calendar therefore activates a quarter on the first rebalance date where a threshold share of *the selected universe* has actually filed, with a hard backstop so a chronically late filer cannot stall the period indefinitely.


## 6. Amendments: where lookahead hides

| statistic | value |
|---|---|
| amended filer-quarters | 10,423 |
|   RESTATEMENT (replaces the table) | 7,926 |
|   NEW HOLDINGS (additive) | 2,923 |
| median days, original to final | 46 |
| p90 | 477 |
| max | 3683 |
| median absolute book revision | 2.17% |
| largest book revision | 1687046.65% |


Amendment semantics follow the cover page rather than a guess:

- **RESTATEMENT** - the amendment's table replaces everything previously on file for that (filer, period).
- **NEW HOLDINGS** - the table is additive and carries only rows omitted from the original, which is the shape a lapsed confidential-treatment order takes. Those positions genuinely did not exist in the public record at the original date.
- missing or unparseable - treated as a restatement, the conservative choice, because it never invents holdings the amendment did not contain.

A period-keyed pipeline reads the final version at the original date. That is lookahead, and it is invisible: the row looks entirely ordinary.


Largest revisions:


| filer_id | period_end | first_knowledge | final_knowledge | lag_days | amendment_types | book_delta_pct |
|---|---|---|---|---|---|---|
| CIK0001525212 | 2020-03-31 | 2020-04-13 | 2020-04-22 | 9 | NEW HOLDINGS | +1687046.65% |
| CIK0001608376 | 2019-09-30 | 2019-10-28 | 2019-11-14 | 17 | NEW HOLDINGS | +1036763.64% |
| CIK0001319111 | 2014-06-30 | 2014-07-29 | 2014-07-31 | 2 | RESTATEMENT | +380039.05% |
| CIK0000314969 | 2020-09-30 | 2020-11-06 | 2020-11-13 | 7 | RESTATEMENT | +291534.93% |
| CIK0001386935 | 2021-06-30 | 2021-08-06 | 2021-08-07 | 1 | RESTATEMENT | +197258.21% |
| CIK0002040405 | 2026-03-31 | 2026-05-06 | 2026-05-08 | 2 | RESTATEMENT | +165215.05% |


## 7. Point-in-time: one quarter, read from six different days

Quarter 2021-06-30, as a researcher would have seen it:


| days after quarter end | as of | filers visible | positions | book USD bn |
|---|---|---|---|---|
| 30 | 2021-07-30 | 1608 | 346591 | 1,877.10 |
| 45 | 2021-08-14 | 4046 | 958256 | 9,000.90 |
| 60 | 2021-08-29 | 5236 | 1199430 | 16,969.10 |
| 75 | 2021-09-13 | 5253 | 1204937 | 16,980.40 |
| 120 | 2021-10-28 | 5273 | 1208725 | 17,032.70 |
| 400 | 2022-08-04 | 5312 | 1215708 | 17,043.30 |


This is the one query the entire factor layer is built on:

```python
store.as_of(period_end, knowledge_date)
```

`knowledge_date` comes from EDGAR's `acceptanceDateTime`, interpreted in Eastern time and rolled to the next session when acceptance is after the close. Filing date is not used: it is a date, not an instant, and it does not say whether the market could have acted that day.

Both the current and prior quarter are always materialised at the *same* vantage date, so a quarter-on-quarter position change never mixes what was known then with what is known now.


## Reproducing this report

```bash
make data-report            # against whatever config/default.yaml points at
make demo && make data-report ARGS='--offline'   # against generated fixtures
```

The audits themselves are library functions, not report code: `store.filing_lag_profile()`, `store.restatement_audit()` and `detect_residual_duplication()` are importable and tested, so the same checks can run inside a scheduled job rather than only when someone remembers to look.

