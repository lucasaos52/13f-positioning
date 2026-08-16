"""Window-Dressing Supply Forecast (doc idea #8, adapted).

    python run_wd.py            # full sample
    python run_wd.py --smoke    # last ~12 quarter-ends

CAUSAL CHAIN (the whole point - no state without an arrow):
    quarter-end photo is public
      -> reputational incentive to not show embarrassing losers
      -> predictable SELLING of intra-quarter losers in the last days
         before the photo, by managers with a HISTORY of doing exactly that
      -> price pressure into quarter-end on those specific losers
      -> REVERSAL in the first days of the new quarter (temporary pressure,
         not information - the signature that separates window dressing
         from plain loser momentum).

UNIVERSE (user-specified, and it is the right call causally): only ACTIVE
managers plausibly image-conscious - AUM BELOW the median of eligible
filers (index giants and ETF-like vehicles do not window-dress; the
below-median cut removes them by construction) AND reasonable turnover
(churn >= 10%/quarter - a book that never trades cannot dress anything).

PROPENSITY (learned per manager, strictly past): over the trailing 8
transitions, WD_m = mean of [sell rate among that quarter's LOSERS minus
sell rate among WINNERS]. Positive = this manager systematically dumps
losers into the photo. Needs >= 4 observations. The learning snapshots are
taken at their own decision dates (q-1 + 50d), all public ~40 days before
the signal date, so nothing leaks.

SIGNAL, 10 trading days before quarter-end E (books of q-1 public by then):
    loser_i        = return from prior quarter-end to signal date <= -10%
    WDSell_i       = sum_m w_mi(q-1) * max(WD_m, 0)   over filtered managers
    WDPressure_i   = WDSell_i / ADV_i                 within losers only

PRE-REGISTERED TESTS (within LOSERS, hi vs lo WDPressure tercile - the
within-loser design kills the momentum confound by construction):
    P1 pressure window (signal date -> quarter-end): delta NEGATIVE;
    P2 reversal window (quarter-end -> +7 trading days): delta POSITIVE;
    P3 placebo: WD_m permuted across managers -> both die;
    P4 Q4 stronger than Q1-Q3 (year-end photo matters most; if the effect
       lived ONLY in Q4 it could be tax-loss selling instead - present in
       all quarters AND stronger in Q4 is the window-dressing signature).
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from backtest_gp import nw_tstat                    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LEAD_TD = 10          # signal this many trading days before quarter-end
REV_TD = 7            # reversal window into the new quarter
LOSER_CUT = -0.10
CHURN_MIN = 0.10
WD_TRAIL = 8
WD_MIN_OBS = 4
DEC_LAG = 50


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    px_all = mdta.prices_raw

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=30)]
    if smoke:
        qs = qs[-(12 + WD_TRAIL):]
    log(f"{len(qs)} quarters")

    wd_hist: dict = defaultdict(lambda: deque(maxlen=WD_TRAIL))
    churn_last: dict = {}
    rows: list[dict] = []

    def to_pairs(df):
        d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
        d["ticker"] = d["instrument_id"].map(cmap)
        d = d.dropna(subset=["ticker"])
        return d.groupby(["filer_id", "ticker"], as_index=False).agg(
            value=("value_usd", "sum"), sh=("shares", "sum"))

    for qi in range(2, len(qs)):
        q, q1, q2 = qs[qi], qs[qi - 1], qs[qi - 2]

        # ---- 1. update WD propensity with transition q2 -> q1 ------------- #
        # snapshots at q1's own decision date: public ~40d before the signal
        dec1 = q1 + pd.Timedelta(days=DEC_LAG)
        if dec1 >= dates[-1]:
            break
        curp = pn.snapshot_as_of(q1, dec1)
        prvp = pn.snapshot_as_of(q2, dec1)
        if min(len(curp), len(prvp)) < 1000:
            continue
        pc1, pc2 = to_pairs(curp), to_pairs(prvp)
        i_q1 = dates.searchsorted(q1, side="right") - 1
        i_q2 = dates.searchsorted(q2, side="right") - 1
        ret_q1 = cum.iloc[i_q1] - cum.iloc[i_q2]      # stock return in q1

        tr = pc2.merge(pc1, on=["filer_id", "ticker"], how="left",
                       suffixes=("_o", "_n"))
        tr["sold"] = (tr["sh_n"].fillna(0.0) < tr["sh_o"]).astype(float)
        tr["r"] = tr["ticker"].map(ret_q1)
        tr = tr[tr["r"].notna()]
        tr["loser"] = tr["r"] <= LOSER_CUT
        tr["winner"] = tr["r"] >= -LOSER_CUT
        g = tr.groupby("filer_id")
        nl = g["loser"].sum()
        nw_ = g["winner"].sum()
        sl = tr[tr["loser"]].groupby("filer_id")["sold"].mean()
        sw = tr[tr["winner"]].groupby("filer_id")["sold"].mean()
        ok_m = nl[(nl >= 3) & (nw_ >= 3)].index
        for m in ok_m:
            wd_hist[m].append(float(sl.get(m, 0.0) - sw.get(m, 0.0)))
        churn = (g["sold"].mean()
                 + (pc1.groupby("filer_id").size()
                    .sub(g.size(), fill_value=0).clip(lower=0)
                    / g.size().clip(lower=1)) * 0.0)   # sell-side churn
        churn_last.update(churn.to_dict())

        # ---- 2. event: the photo at quarter-end q ------------------------- #
        ie = dates.searchsorted(q, side="right") - 1    # last td <= q (E)
        ds = ie - LEAD_TD                               # signal date
        if ds <= i_q1 or ie + REV_TD + 1 >= len(dates):
            continue
        book = to_pairs(pn.snapshot_as_of(q1, dates[ds]))
        if len(book) < 1000:
            continue
        aum = book.groupby("filer_id")["value"].sum()
        npos = book.groupby("filer_id").size()
        elig = aum[(npos >= 15)]
        med_aum = elig.median()
        # user filter: ACTIVE, image-conscious universe - below-median AUM
        # and a book that actually trades
        wd_m = {m: float(np.mean(h)) for m, h in wd_hist.items()
                if len(h) >= WD_MIN_OBS}
        keep = [m for m in elig.index
                if m in wd_m and elig[m] < med_aum
                and churn_last.get(m, 0.0) >= CHURN_MIN]
        if len(keep) < 100:
            continue
        wd_s = pd.Series({m: max(wd_m[m], 0.0) for m in keep})

        # losers as of the signal date (intra-quarter return so far)
        r_sofar = cum.iloc[ds] - cum.iloc[i_q1]
        adv_d = adv.iloc[ds]
        px_d = px_all.iloc[ds]
        losers = r_sofar.index[(r_sofar <= LOSER_CUT)
                               & (px_d >= 1.0) & adv_d.gt(0)]
        if len(losers) < 60:
            continue

        bk = book[book["filer_id"].isin(keep)].copy()
        tot = bk.groupby("filer_id")["value"].transform("sum")
        bk["w"] = bk["value"] / tot.replace(0, np.nan)
        rng = np.random.default_rng(int(q.value) % (2**32))
        perm = pd.Series(rng.permutation(wd_s.values), index=wd_s.index)

        def pressure(weights: pd.Series) -> pd.Series:
            s = bk.assign(x=bk["filer_id"].map(weights) * bk["w"]
                          * bk["filer_id"].map(aum)) \
                .groupby("ticker")["x"].sum()
            out = s.reindex(losers).fillna(0.0) / adv_d.reindex(losers)
            return out.replace([np.inf, -np.inf], np.nan)

        wdp = pressure(wd_s)
        wdp_pl = pressure(perm)

        press = (cum.iloc[ie] - cum.iloc[ds]).reindex(losers)
        rev = (cum.iloc[ie + REV_TD] - cum.iloc[ie]).reindex(losers)
        press = (press - press.median()).clip(-0.5, 0.5)   # within-loser
        rev = (rev - rev.median()).clip(-0.5, 0.5)

        def hilo(sig, out):
            df = pd.concat([sig.rename("s"), out.rename("o")],
                           axis=1).dropna()
            if len(df) < 60:
                return np.nan
            ter = pd.qcut(df["s"].rank(method="first"), 3, labels=False)
            return float(df["o"][ter == 2].mean()
                         - df["o"][ter == 0].mean())

        rows.append({
            "period": q, "is_q4": q.month == 12,
            "n_losers": len(losers), "n_mgrs": len(keep),
            "d_press": hilo(wdp, press), "d_rev": hilo(wdp, rev),
            "pl_press": hilo(wdp_pl, press), "pl_rev": hilo(wdp_pl, rev)})
        log(f"{q.date()}: {len(keep)} WD-elegiveis, {len(losers)} losers, "
            f"d_press {rows[-1]['d_press']}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "wd_events.csv", index=False)

    L = ["# window_dressing - oferta previsivel na foto de fim de tri", "",
         "Universo: gestores ativos (AUM < mediana + churn >= 10%/tri) com "
         "propensao WD aprendida em 8 tri estritamente passados. Teste "
         "DENTRO dos losers (mata o confound de momentum): tercil alto vs "
         "baixo de WDPressure.", ""]
    if len(ev):
        L.append(f"- {len(ev)} trimestres | media {ev['n_mgrs'].mean():.0f} "
                 f"gestores WD-elegiveis, {ev['n_losers'].mean():.0f} "
                 f"losers/tri\n")
        for col, lbl, exp in [
                ("d_press", "P1 pressao (ds -> quarter-end)", "NEGATIVO"),
                ("d_rev", "P2 reversao (quarter-end -> +7td)", "POSITIVO"),
                ("pl_press", "P3a placebo pressao (WD permutado)", "~0"),
                ("pl_rev", "P3b placebo reversao", "~0")]:
            s = ev[col].dropna()
            L.append(f"- **{lbl}**: {s.mean():+.4f} "
                     f"(t={nw_tstat(s):+.2f}) - esperado {exp}")
        for col in ("d_press", "d_rev"):
            q4 = ev[ev["is_q4"]][col].dropna()
            rest = ev[~ev["is_q4"]][col].dropna()
            L.append(f"- **P4 {col}**: Q4 {q4.mean():+.4f} "
                     f"({len(q4)} anos) vs Q1-Q3 {rest.mean():+.4f} "
                     f"(t={nw_tstat(rest):+.2f})")
    (RESULTS / "WD_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
