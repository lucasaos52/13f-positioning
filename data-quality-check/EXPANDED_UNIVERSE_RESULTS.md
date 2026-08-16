# Expanded-universe robustness table (crosswalk fix, 2026-08-16)

The name-match coverage hole (63% → 85.4% of non-ETF value mapped; top-250
CUSIPs hand-mapped and verified; caches stitched surgically) — and what
happened to every headline when re-run on the expanded universe. The
selection of the old universe was quasi-random w.r.t. signals (EDGAR name
formatting does not predict returns), so the pre-registered expectation
was: LEVELS move where mega-caps matter, VERDICTS stay.

| result | old universe | expanded universe | verdict |
|---|---|---|---|
| fund_performance: median excess | −5.0%/yr | **−3.3%/yr** | level moved as predicted (mega-winners restored); directional story intact (median loses, before fees) |
| fund_performance: funds with IR>0 | 7% | **13%** | industry ceiling still low |
| fund_performance: eligible big funds | 938 | **1,597** | the eligibility bias healed (+70% more funds pass coverage filters) |
| fund_performance: skill persistence | +0.131 | **+0.251** | higher but still far from tradable; smart-money verdicts unchanged (see wbreadth below) |
| wbreadth (graveyard spot-check): sigmoid effect | t=+0.06 | **t=+0.19** | dead stays dead — supports not re-running the graveyard |
| wbreadth: electorate effect | t=+0.90 | **t=−0.15** | zero stays zero |
| champion new_conviction (resid) | t=+3.67/+3.83/+3.27 | **t=+3.44, Sharpe 0.99** | in band — headline holds |
| champion halving stability | — | **t=+3.45 / +2.79 (two random halves)** | survives a random 50% coverage cut → the quasi-random hole could not flip verdicts |
| score model: new_conv joint λ | t=+3.26 | **t=+3.04** | holds — 13F premium vs 6 classical simultaneous |
| score model: dbreadth joint λ | t=+4.62 | **t=+4.01** | holds; FM still wins the combiner race (0.86, A>C t=+1.96) |
| pressure×vol autopsy (interactions) | E4 delta t=+2.06 then killed | **E4 delta t=+0.77** — the flicker died with fuller coverage | non-promotion vindicated; all 5 prereg still unconfirmed; champion replicated again at t=+3.78 in-module |
| flow instrument (fire stage 1) | t=+13.8 | **t=+20.9** (32.5% vs 16.2% sold) | STRONGER with complete books — as predicted; pecking nuance: liquidity-ordering now ~flat (−0.02, t=−3.6) → 'approximately pro-rata' is the accurate description |
| stress_short daily: delta @5d | t=−2.16 (22q, overlay candidate) | **t=+0.37 (49q); dead even in its own 2020+ window (t=−0.50)** | RETRACTED — the one flip of the campaign: the old result was an eligibility-selection artifact; the funnel had already declined promotion |

| MFP (E=WX): validation + H1-H6 | validated; H3/H4/H5 dead | **identical** (placebo +0.59→−0.16; H3 t=−1.05) | verdicts intact |

| breadth_universes (graveyard #3) | deltas ~0 | **still ~0** (t=+0.52/−0.12) | dead stays dead |
| ICA demand (rev thesis) | t=+1.28, placebo −0.72, stab 81% | **t=+1.29, placebo −0.77, stab 81%** | most stable result of the campaign; verdict intact |

| 17-signal catalogue: new_conviction | t=+3.27, Sharpe 0.97 | **t=+3.54, Sharpe 1.08** | 6th in-band replication; catalogue ranking preserved |
| champion_noetf (ETF purge seal) | t=+0.08 | **t=−0.25** | still innocuous |

| new_positioning: new_conv (7th replication) | — | **t=+3.63, Sharpe 1.12** | band 3.3–3.8 across 7 implementations, 2 universes |
| SSI validation vs real short interest | corr +0.47 | **corr +0.55** | 2nd instrument STRENGTHENED by complete books |

| patient universe (graveyard #4) | rejected (t=−1.72) | **rejected harder (t=−2.35/−3.25)**; champion 8th replication t=+3.45/3.97 | dead stays dead |
| copycat: hangover + graph stability | t=−2.5; stab 0.94 | **hangover holds; stab 0.94 identical** | instrument stable |
| NMF latent strategies | K=12, corr(daysADV)+0.20 | **K=10, corr +0.18** | structure stable |

**CAMPAIGN CLOSED: 24 re-runs — 21 verdicts stable, 2 instruments STRENGTHENED (flow t=13.8→20.9; SSI corr 0.47→0.55), 1 marginal result RETRACTED (stress_short — an eligibility-selection artifact the funnel had already quarantined). The champion replicated 8 times across two universes, band t=3.3–4.0.**

## What was fixed (summary)

1. Hand-curated map for the top ~230 unmapped CUSIPs by value (65% of the
   $8.5T hole): LLY, GOOG, JPM, BRK-A/B, UNH, XOM, COST, IBM… — plus ~165
   consolidations (alternate instrument_ids of already-priced companies).
2. 61 new tickers fetched from Yahoo; caches stitched by hand (a naive
   MarketData call would have refetched all ~4k tickers). Map pruned to
   match cache columns exactly (3,988 = 3,988).
3. Residual: 11 tickers Yahoo-throttled (MMC, K, BK, HES, HOLX, CTRA
   alive; DFS/ANSS/TPX/CYBR/FYBR delisted/renamed) + the tail (~2-3k
   small CUSIPs, OpenFIGI job delegated) + delisted names (CRSP-tier,
   structural). Coverage ladder to ~93% free / ~98% with CRSP documented.

## Files

- `fix_crosswalk_top.py` — the fix (hand map + fetch + stitch)
- `notebooks/data/cm_map_wide_v1.csv` — pre-fix map backup
- `rerun_champion_expanded.py` + `results/CHAMPION_EXPANDED.md`
- re-run logs in each module's folder (`run_expanded.log`)
