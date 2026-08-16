"""Patient-capital universe test (Cremers-Pareek 2016): do the votes of
LONG-HORIZON managers carry more/longer-lived information?

    python run_patient.py            # full sample
    python run_patient.py --smoke    # last ~12 quarters

The one universe variant the project had NOT tested: U1-U3 used high
turnover, active share and past performance (all failed). This one filters
on HOLDING DURATION only - no performance filter anywhere (that piece was
killed three times: U3, EB skill weights, smart-money family).

WHY it could escape the timing curse that killed every follower strategy:
disclosure staleness is relative to the trader's horizon. For a manager who
turns the book in 3 months, D+45 has consumed ~50% of the horizon - the
filing is a trace. For one who holds 3 years, D+45 is ~4% - the position is
still essentially fresh. The disclosure lag hurts patient managers least.

PRE-REGISTERED (before any return was seen):
  P1  paired delta spread(signal on patient universe) - spread(full
      universe) >= 0 at q+1, for new_conviction (resid) and dbreadth;
  P2  the patient advantage DECAYS SLOWER: delta at q+2 (second quarter
      alone, skip-one) should be >= delta at q+1. This is the distinctive
      Cremers-Pareek signature - patient capital's edge lives at longer
      horizons - and it is the opposite of what stale-information noise
      would produce.
  Known risk, measured not assumed: patient managers trade rarely, so the
  filtered signal loses votes (the U1 failure mode: 68 funds). The vote
  counts per quarter are logged for exactly this diagnosis.

Manager duration = value-weighted mean AGE of current positions (quarters
held consecutively), from the same incremental age state as new_positioning.
Ages are left-censored at the start of the sample, which affects all
managers alike; classification only starts after 8 quarters of warm-up.
Patient = top tercile of duration among managers with >= 10 positions.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
LAG = 45
WARMUP = 8          # quarters of age state before classifying
MIN_POS_CLASS = 10  # positions needed to classify a manager's duration
MIN_PATIENT = 150   # patient set floor per quarter


def residualise(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    df = pd.concat([y.rename("y"), X], axis=1).replace(
        [np.inf, -np.inf], np.nan)
    ok = df.notna().all(axis=1)
    if ok.sum() < 30:
        return y - y.mean()
    A = np.column_stack([np.ones(ok.sum()), df.loc[ok, X.columns].values])
    try:
        b, *_ = np.linalg.lstsq(A, df.loc[ok, "y"].values, rcond=None)
    except np.linalg.LinAlgError:
        return y - y.mean()
    r = y.copy()
    r[ok] = df.loc[ok, "y"].values - A @ b
    r[~ok] = np.nan
    return r


def split_factor(cur: pd.DataFrame, prev: pd.DataFrame) -> pd.Series:
    pair = cur.merge(prev, on=["filer_id", "instrument_id"],
                     suffixes=("_c", "_p"))
    pair = pair[(pair["shares_p"] > 0) & (pair["shares_c"] > 0)]
    pair["ratio"] = (pair["shares_c"] / pair["shares_p"]).round(3)
    fac = {}
    for j, g in pair.groupby("instrument_id"):
        if len(g) < 10:
            continue
        counts = g["ratio"].value_counts()
        mode, k = counts.index[0], counts.iloc[0]
        k2 = counts.iloc[1] if len(counts) > 1 else 0
        if abs(mode - 1) > 0.15 and (k >= 0.10 * len(g)
                                     or (k >= 30 and k >= 2.5 * k2)):
            fac[j] = float(mode)
    return pd.Series(fac, dtype=float)


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    shares = mc.shares_panel(dates, mdta.tickers, mdta.prices, mdta.prices_raw)
    mcap = mc.mktcap_panel(mdta.prices_raw, shares)
    cmap_s = pd.Series(cmap)

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        # keep the age warm-up honest even in smoke: start earlier
        qs = qs[-(12 + WARMUP):]
    log(f"{len(qs)} quarters")

    age = pd.Series(dtype=np.int16)
    age_warm = 0
    rows: list[dict] = []

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        dec = p + pd.Timedelta(days=LAG)
        if dec >= dates[-1] - pd.Timedelta(days=95):
            continue
        cur = pn.snapshot_as_of(p, dec)
        prev = pn.snapshot_as_of(p1, dec)
        if min(len(cur), len(prev)) < 1000:
            continue
        di = dates.searchsorted(dec, side="right") - 1
        di_p = dates.searchsorted(p, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di_p]
        mc_d = mcap.iloc[di]

        fac_i = split_factor(cur, prev)
        fac_t = (pd.DataFrame({"t": cmap_s.reindex(fac_i.index),
                               "f": fac_i.values})
                 .dropna().groupby("t")["f"].first())

        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                value=("value_usd", "sum"), sh=("shares", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)
        key = pd.MultiIndex.from_frame(pc[["filer_id", "ticker"]])
        a_now = pd.Series(age.reindex(key).values, index=pc.index) \
            .fillna(0).astype(int)

        # ---- manager duration and the patient tercile --------------------- #
        patient = None
        if age_warm >= WARMUP:
            d = pc.assign(a=a_now)
            npos = d.groupby("filer_id")["ticker"].transform("size")
            d = d[npos >= MIN_POS_CLASS]
            g = d.groupby("filer_id")
            dur = (d.assign(va=d["value"] * d["a"]).groupby("filer_id")["va"]
                   .sum() / g["value"].sum())
            thr = dur.quantile(2 / 3)
            pat = dur.index[dur >= thr]
            if len(pat) >= MIN_PATIENT:
                patient = set(pat)

        # ---- new_conviction votes per manager (universe-independent) ----- #
        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        thr_w = pc_w.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pp[["filer_id", "ticker", "sh"]],
                        on=["filer_id", "ticker"], how="left",
                        suffixes=("", "_p"))
        m5["sh_p_adj"] = m5["sh_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["sh_p"].isna() | (m5["sh"] >= 1.25 * m5["sh_p_adj"])
        votes = m5[(m5["w"] >= thr_w.values) & grew][["filer_id", "ticker"]]

        n_c = pc.groupby("ticker")["filer_id"].nunique()
        n_p = pp.groupby("ticker")["filer_id"].nunique()
        idx = n_c.index.union(n_p.index)

        def build_signals(univ: set | None):
            """new_conv + dbreadth counted over one manager universe."""
            if univ is None:
                v, c, pr = votes, pc, pp
            else:
                v = votes[votes["filer_id"].isin(univ)]
                c = pc[pc["filer_id"].isin(univ)]
                pr = pp[pp["filer_id"].isin(univ)]
            nf = max(float(c["filer_id"].nunique()), 1.0)
            nc_ = (v.groupby("ticker")["filer_id"].nunique()
                   .reindex(idx).fillna(0) / nf)
            common = np.intersect1d(c["filer_id"].unique(),
                                    pr["filer_id"].unique())
            cc = c[c["filer_id"].isin(common)] \
                .groupby("ticker")["filer_id"].nunique()
            pcm = pr[pr["filer_id"].isin(common)] \
                .groupby("ticker")["filer_id"].nunique()
            db = (cc.reindex(idx).fillna(0)
                  - pcm.reindex(idx).fillna(0)) / max(len(common), 1)
            return nc_, db, int(len(v)), int(nf)

        nc_full, db_full, v_full, m_full = build_signals(None)
        if patient is None:
            age_update = True
        else:
            nc_pat, db_pat, v_pat, m_pat = build_signals(patient)
            age_update = True

            # ---- evaluation ------------------------------------------------ #
            n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)],
                              axis=1).max(axis=1).fillna(0)
            uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)
                      & (n_max >= 5)]
            ctrl = pd.DataFrame({
                "lm": np.log(pd.Series(uni.map(mc_d), index=uni)),
                "la": np.log(pd.Series(uni.map(adv_d), index=uni))})
            dec1 = qs[qi + 1] + pd.Timedelta(days=LAG) \
                if qi + 1 < len(qs) else None
            dec2 = qs[qi + 2] + pd.Timedelta(days=LAG) \
                if qi + 2 < len(qs) else None
            fwd = {}
            if dec1 is not None and dec1 < dates[-1]:
                fwd["q1"] = forward_return(cum, dates, dec,
                                           min(dec1, dates[-1])).reindex(uni)
            if dec2 is not None and dec1 is not None and dec2 < dates[-1]:
                fwd["q2"] = forward_return(cum, dates, dec1,
                                           min(dec2, dates[-1])).reindex(uni)
            rng = np.random.default_rng(int(p.value) % (2**32))

            def spread(s, f):
                df = pd.concat([s.rename("s"), f.rename("f")], axis=1).dropna()
                if len(df) < 150:
                    return np.nan
                jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
                q5 = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
                gg = df.groupby(q5)["f"].mean()
                return gg.get(4, np.nan) - gg.get(0, np.nan)

            for sig_name, s_full, s_pat, resid in [
                    ("new_conv", nc_full, nc_pat, True),
                    ("dbreadth", db_full, db_pat, False)]:
                sf = s_full.reindex(uni)
                sp = s_pat.reindex(uni)
                if resid:
                    sf = residualise(sf.rank(pct=True), ctrl)
                    sp = residualise(sp.rank(pct=True), ctrl)
                for hz, f in fwd.items():
                    rows.append({
                        "period": p, "signal": sig_name, "horizon": hz,
                        "spread_full": spread(sf, f),
                        "spread_patient": spread(sp, f),
                        "n_mgr_patient": m_pat, "n_mgr_full": m_full,
                        "votes_patient": v_pat, "votes_full": v_full})
            log(f"{p.date()}: patient {m_pat}/{m_full} mgrs, "
                f"votes {v_pat}/{v_full}")

        # ---- age update --------------------------------------------------- #
        if age_update:
            held_key = pd.MultiIndex.from_frame(pc[["filer_id", "ticker"]])
            age = pd.Series(a_now.values + 1, index=held_key) \
                .clip(upper=12).astype(np.int16)
            age_warm += 1

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "patient_events.csv", index=False)
    ev["delta"] = ev["spread_patient"] - ev["spread_full"]

    L = ["# patient_universe - capital paciente (Cremers-Pareek)", "",
         "Filtro: tercil superior de duracao de holding (idade media VW das "
         "posicoes). SEM filtro de performance. Pre-registro: P1 delta>=0 em "
         "q+1; P2 delta(q+2) >= delta(q+1) (decaimento mais lento).", ""]
    if len(ev):
        L += [f"- gestores pacientes/tri: {ev['n_mgr_patient'].mean():.0f} "
              f"de {ev['n_mgr_full'].mean():.0f}; votos new_conv: "
              f"{ev['votes_patient'].mean():.0f} de "
              f"{ev['votes_full'].mean():.0f}", ""]
        for (sig, hz), g in ev.groupby(["signal", "horizon"]):
            d = g["delta"].dropna()
            L.append(
                f"- **{sig} @ {hz}**: full {g['spread_full'].mean():+.4f} "
                f"(t={nw_tstat(g['spread_full']):+.2f}) | patient "
                f"{g['spread_patient'].mean():+.4f} "
                f"(t={nw_tstat(g['spread_patient']):+.2f}) | delta "
                f"{d.mean():+.4f} (t={nw_tstat(d):+.2f}, {len(d)} tri)")
        # P2: does the patient advantage decay slower?
        piv = ev.pivot_table(index=["period", "signal"], columns="horizon",
                             values="delta")
        if {"q1", "q2"}.issubset(piv.columns):
            dd = (piv["q2"] - piv["q1"]).dropna()
            L += ["", f"- **P2 (assinatura Cremers-Pareek)**: "
                  f"delta(q2)-delta(q1) = {dd.mean():+.4f} "
                  f"(t={nw_tstat(dd.reset_index(drop=True)):+.2f}) - "
                  f"esperado >= 0"]
    (RESULTS / "PATIENT_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
