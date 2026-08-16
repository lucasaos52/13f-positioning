# Base validation

Store: 58,032,157 positions, 271,621 filings, 12,538 filers, 1987-03-31 to 2026-03-31. Config fingerprint `d19553a22002`.


## 1. Integrity

- [PASS] every report quarter present — 98 quarters, missing: none
- [PASS] filings per covered quarter in a sane band — min 2870 (2013Q2), max 7792 (2025Q4)
- [PASS] no single filing's book above $8tn (unit-inflation catch) — 0 filings above $8tn; 74 above $1tn (expected: the index complexes)
- [PASS] every holdings row versioned by a revision — 0 orphan rows
- [PASS] no null knowledge_ts — 0 null
- [PASS] ledger statuses complete — {'ok': 312074, 'no_table': 84816, 'all_rows_rejected': 943}
- [PASS] no negative position values — 0 negative rows

## 2. Point-in-time mechanics (sampled from the real archive)

- [PASS] nothing visible before first disclosure — 0/200 sampled (filer, period) leaked early
- [PASS] no amendment visible before its acceptance — 0/179 sampled amendments leaked
  (of 179 checked, 177 are part of the final view; the rest were themselves superseded by later versions — expected, not an error)
- [PASS] visibility monotone in knowledge time — 0 regressions across 4 quarters x 14 vantages
- [PASS] no filing knowable before its own quarter ends — 0 violations

## 3. External anchors (numbers this pipeline did not produce)

- [PASS] median filing lag ~= the 45-day deadline — median 41d; independent study of the same archive reports ~45d
- [PASS] on-time share consistent with the deadline being binding — 94.4% by the business-day-rolled deadline (+1 session); 91.1% within calendar day 46; independent study: ~93%
  share filing at the deadline (day 45+roll): 22.7% — the study reports 48.2% on exactly day 45, i.e. the deadline is the modal choice. Directional agreement expected.
- [PASS] acceptanceDateTime is UTC (three-band same-day pattern) — same-day share 15-17h raw: 97.5% (pre-cutoff), 22-23h raw: 22.0% (post-cutoff, rolled), 0-2h raw: 87.2% (prev-evening ET, wraps to the UTC date)
  filings released after the 16:00 ET close: 24.7% (the 50-manager study reports 49.1%; big managers file later) — post-close filings are tradeable next session only, which derive_knowledge_ts enforces.
- [PASS] amendment share in the published ballpark — 4.6% of filings are 13F-HR/A; the independent study reports 15.9% on a hand-picked sample of 50 large managers - amendment-prone by construction; the full universe runs lower
  amendment lag: median 115d, p90 597d (study: median 136d, p90 412d)
- [PASS] both amendment types observed and typed from the cover page — {'RESTATEMENT': 10853, 'NEW HOLDINGS': 5170, '(blank)': 55}
- [PASS] Berkshire 2023Q4 book matches the publicly known ~$352bn — $351.9bn from 42 positions
- [PASS] Berkshire 2023Q4 AAPL matches the publicly known ~$174bn — $174.3bn
- [PASS] Berkshire 2024Q4 AAPL aggregates its multi-line slices to ~$75.1bn — $75.1bn from 12 as-filed lines collapsed to 1 position(s); the independent study reports 12 lines summing to $75.1bn
- [PASS] value scale: era-consistent split with measured non-compliance — filed<=2021: 98.28% in thousands (167,520 filings); filed>=2024: 94.04% in dollars (86,087)
  scale decided by detection (not calendar) for 96.8% of filings; non-compliant filers are exactly why the calendar alone is not trusted.
- [PASS] 2022Q4 boundary: detection separates compliant dollars from the still-in-thousands tail (both real) — 17.5% of 7,632 boundary filings still in thousands - measured non-compliance in the first quarter of the dollar rule. A pipeline trusting the calendar reads these books 1000x too small

## 4. Cross-validation against independently parsed submissions

- [PASS] raw parser and DERA agree on >=95% of sampled filings — 100.0% of 40 sampled (0 fetch failures excluded)

---

**0 failure(s).**
