"""Top-5 from the external doc `new_positionog_gpt` (13F_positioning_new_factors),
adapted to the existing infra and evaluated under the SAME protocol as
general_predictive_signals (decision at p+45d, event-driven PIT snapshots,
quintiles EW/VW, NW(4) t, Spearman IC).

    python run_np.py            # full sample
    python run_np.py --smoke    # last ~14 quarters

The five, and what was adapted (each choice defensible in review):

S1  CORRELATION-ADJUSTED BREADTH (doc #2).  GLS consensus IB = 1'C^-1 x.
    Key simplification: the denominator sqrt(1'C^-1 1) is constant per
    quarter, so cross-sectional ranks depend only on v = C^-1 1 - a fixed
    per-manager weight vector that downweights managers whose historical
    trade-sign vectors are correlated with the crowd. C is the cosine
    matrix of trailing 8-quarter trade-sign vectors (sparse rows are
    near-mean-zero, so cosine ~ correlation), shrunk 25% to the identity
    for invertibility (T is small). Managers without enough history get
    weight 1.0 (unit prior = assumed independent). The informative test is
    the PAIRED delta against the raw vote count on the same sample - if
    discounting redundancy adds nothing, cab == votes.

S2  POSITION-AGE / COHORT FLOW (doc #4).  Age of each (filer,ticker) edge
    is accumulated incrementally across the quarter loop (each quarter's
    snapshot taken at its own decision date, so ages only use information
    that was public in sequence). Cohort a = age as of the PRIOR quarter
    (0 = brand-new position), capped at 4+. Cohort flow = sum of dIO of
    edges in that cohort. Output is the alpha-per-age curve - the doc's
    g(age) is NOT fitted (that would be in-sample); we report the raw
    curve and let monotonicity speak.

S3  EXTENSIVE x INTENSIVE (doc #10).  extensive = (births - deaths) /
    prior holders (this is net_entry, already tested - kept as reference);
    NEW content is intensive = net dIO of INCUMBENT holders only, and
    agreement = z(ext) * z(int) per quarter. The 2x2 map says consensus
    (+,+) vs transfer (+,-).

S4  SIGNED FRAGILITY (doc #6).  Pressure_i = sum_m flow_m * value_prev[m,i]
    / ADV_i with flow = the validated implied-flow instrument (fire_calendar,
    t=+13.8 vs realized sales). Fragility_i = b_i' Cov(f) b_i computed
    WITHOUT forming the MxM covariance: with F the trailing (demeaned)
    flow panel, b'Cov(f)b = mean_tau[(F_tau' b_i)^2] - one groupby per
    trailing quarter. signed_frag = pressure * sqrt(fragility). Paired
    test vs pressure alone answers "does the fragility multiplier add
    anything"; a flow-permutation placebo (doc's falsification #3) must
    kill both. Sign pre-registration: given the distress=INFORMATION
    finding of this project, negative pressure predicts CONTINUATION
    (negative next-q return), not reversal.

S5  HEADROOM x NEW_CONVICTION (doc #13).  w_max[m] = mean of trailing
    per-quarter q95 of the manager's own position weights (>=4 quarters of
    history, strictly before t). BuyCapacity_i = sum over CURRENT buyers of
    max(w_max - w, 0) * AUM / ADV_i. cont_score = rank(new_conviction) *
    rank(buycap). Paired against new_conviction alone (the champion core):
    the interaction only earns its place if the paired delta is positive.

Neutralisation follows the theorem test of signal_defs: signed flow/delta
constructions are raw-headline (monkey books give zero everywhere, no
mechanical size link); positive-scale constructions built on top-decile
membership or dollar-capacity/ADV (new_conv, cont_score, buycap) are
theorem -> residual headline. Both versions computed for everything.
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy import stats as sps
from scipy.linalg import cho_factor, cho_solve

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "general_predictive_signals", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
TRAIL = 8            # quarters of history for C (S1), Cov(f) (S4), w_max (S5)
MIN_Q_HIST = 3       # manager must appear in >= this many trailing quarters
MIN_TRADES = 20      # ... with >= this many trades total (S1)
SHRINK = 0.25        # identity shrinkage on C
MIN_FLOW_Q = 6       # trailing quarters before fragility is computed
MIN_WMAX_Q = 4       # trailing quarters before headroom is computed

THEOREM = {          # residual on log(mktcap)+log(ADV) is the headline?
    "cab_sum": False, "cab_norm": False, "votes_sum": False, "ti_like": False,
    "cohort0": False, "cohort1": False, "cohort2": False, "cohort3": False,
    "cohort4p": False,
    "intensive": False, "agreement": False, "extensive": False,
    "pressure": False, "signed_frag": False, "press_placebo": False,
    "buycap": True, "new_conv": True, "cont_score": True,
}
PAIRS = [            # paired deltas: does the refinement beat its base?
    ("cab_norm", "ti_like", "raw"),
    ("cab_sum", "votes_sum", "raw"),
    ("signed_frag", "pressure", "raw"),
    ("cont_score", "new_conv", "resid"),
]


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
    """Modal-atom split detector (validated 6/6 on famous splits): an
    untouched holder's cur/prev share ratio equals the split factor
    exactly, and dozens of holders on the same rounded atom is no
    coincidence. Returns factor per instrument_id (prev -> cur units)."""
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


def gls_weights(trail: pd.DataFrame) -> pd.Series:
    """v = C^-1 1 over the trailing trade-sign matrix. trail columns:
    filer_id, col (quarter|ticker), sign."""
    cnt = trail.groupby("filer_id").agg(n=("sign", "size"),
                                        q=("qtag", "nunique"))
    keep = cnt.index[(cnt["n"] >= MIN_TRADES) & (cnt["q"] >= MIN_Q_HIST)]
    if len(keep) > 4000:      # bound the Cholesky; drop the least active
        keep = cnt.loc[keep, "n"].nlargest(4000).index
    t = trail[trail["filer_id"].isin(keep)]
    if t["filer_id"].nunique() < 50:
        return pd.Series(dtype=float)
    mcat = pd.Categorical(t["filer_id"])
    ccat = pd.Categorical(t["col"])
    A = sparse.coo_matrix(
        (t["sign"].astype(np.float32),
         (mcat.codes, ccat.codes)),
        shape=(len(mcat.categories), len(ccat.categories))).tocsr()
    rn = np.sqrt(np.asarray(A.multiply(A).sum(axis=1)).ravel())
    rn[rn == 0] = 1.0
    An = sparse.diags(1.0 / rn) @ A
    C = np.asarray((An @ An.T).todense(), dtype=np.float64)
    np.fill_diagonal(C, 1.0)
    Cs = (1 - SHRINK) * C + SHRINK * np.eye(len(C))
    try:
        v = cho_solve(cho_factor(Cs), np.ones(len(Cs)))
    except np.linalg.LinAlgError:
        v = np.linalg.solve(Cs + 0.1 * np.eye(len(Cs)), np.ones(len(Cs)))
    return pd.Series(v, index=mcat.categories)


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
        qs = qs[-14:]
    log(f"{len(qs)} quarters")

    # rolling state (all strictly-past information at each use)
    age = pd.Series(dtype=np.int16)          # (filer,ticker) -> consecutive q held
    age_warm = 0                             # quarters of accumulated age state
    hist_signs: deque = deque(maxlen=TRAIL)  # per-q trade signs (S1)
    hist_flows: deque = deque(maxlen=TRAIL)  # per-q implied flows (S4)
    hist_q95: deque = deque(maxlen=TRAIL)    # per-q q95 book weight (S5)

    events: dict[tuple, list] = {}
    paired_rows: list[dict] = []

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
        di_p1 = dates.searchsorted(p1, side="right") - 1
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di]
        mc_d = mcap.iloc[di] if len(mcap) else pd.Series(dtype=float)
        so_c = shares.iloc[di_p] if len(shares) else pd.Series(dtype=float)
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]

        fac_i = split_factor(cur, prev)
        # instrument-level factor -> ticker level (first non-null per ticker)
        fac_t = (pd.DataFrame({"t": cmap_s.reindex(fac_i.index),
                               "f": fac_i.values})
                 .dropna().groupby("t")["f"].first())

        # ---- (filer, ticker) pair table with deltas ---------------------- #
        def to_pairs(df):
            d = df[["filer_id", "instrument_id", "shares", "value_usd"]].copy()
            d["ticker"] = d["instrument_id"].map(cmap)
            d = d.dropna(subset=["ticker"])
            return d.groupby(["filer_id", "ticker"], as_index=False).agg(
                shares=("shares", "sum"), value=("value_usd", "sum"))

        pc, pp = to_pairs(cur), to_pairs(prev)
        pair = pc.merge(pp, on=["filer_id", "ticker"], how="outer",
                        suffixes=("_c", "_p"))
        fac_row = pair["ticker"].map(fac_t).fillna(1.0)
        sh_p_adj = pair["shares_p"].fillna(0.0) * fac_row
        pair["dsh"] = pair["shares_c"].fillna(0.0) - sh_p_adj
        so_row = pair["ticker"].map(so_c)
        pair["dio"] = (pair["dsh"] / so_row).replace(
            [np.inf, -np.inf], np.nan)
        pair["is_new"] = pair["shares_c"].notna() & pair["shares_p"].isna()
        pair["is_exit"] = pair["shares_c"].isna() & pair["shares_p"].notna()
        pair["existing"] = pair["shares_c"].notna() & pair["shares_p"].notna()

        n_filers = float(cur["filer_id"].nunique())
        n_c = pc.groupby("ticker")["filer_id"].nunique()
        n_p = pp.groupby("ticker")["filer_id"].nunique()
        idx = n_c.index.union(n_p.index)
        byt = pd.DataFrame(index=idx)

        # ---- S2: cohort flows by position age ---------------------------- #
        key = pd.MultiIndex.from_frame(pair[["filer_id", "ticker"]])
        a_prev = pd.Series(age.reindex(key).values, index=pair.index) \
            .fillna(0).astype(int)
        cohort = a_prev.clip(upper=4)          # 0 = new, 4 = 4+ quarters
        traded = pair["dio"].notna() & (pair["dio"] != 0)
        for a in range(5):
            name = f"cohort{a}" if a < 4 else "cohort4p"
            if age_warm < 5:   # ages unidentified until 5q of state
                byt[name] = np.nan
                continue
            sel = traded & (cohort == a)
            byt[name] = pair.loc[sel].groupby("ticker")["dio"].sum() \
                .reindex(idx)

        # ---- S3: extensive x intensive ----------------------------------- #
        births = pair[pair["is_new"]].groupby("ticker").size()
        deaths = pair[pair["is_exit"]].groupby("ticker").size()
        base = n_p.reindex(idx).clip(lower=1)
        byt["extensive"] = (births.reindex(idx).fillna(0)
                            - deaths.reindex(idx).fillna(0)) / base
        byt["intensive"] = pair[pair["existing"] & traded] \
            .groupby("ticker")["dio"].sum().reindex(idx).fillna(0.0)
        ze = (byt["extensive"] - byt["extensive"].mean()) \
            / byt["extensive"].std()
        zi = (byt["intensive"] - byt["intensive"].mean()) \
            / byt["intensive"].std()
        byt["agreement"] = ze * zi

        # ---- S1: correlation-adjusted breadth ---------------------------- #
        cur_signs = pair.loc[traded, ["filer_id", "ticker"]].copy()
        cur_signs["sign"] = np.sign(pair.loc[traded, "dio"]).astype(np.int8)
        v = pd.Series(dtype=float)
        if len(hist_signs) >= 4:
            trail = pd.concat(hist_signs, ignore_index=True)
            v = gls_weights(trail)
        if len(v):
            w_m = cur_signs["filer_id"].map(v).fillna(1.0)  # unit prior
            cs = cur_signs.assign(wv=w_m * cur_signs["sign"],
                                  wa=w_m.abs())
            g = cs.groupby("ticker")
            byt["cab_sum"] = g["wv"].sum().reindex(idx)
            byt["cab_norm"] = (g["wv"].sum() / g["wa"].sum()).reindex(idx)
        else:
            byt["cab_sum"] = np.nan
            byt["cab_norm"] = np.nan
        gv = cur_signs.groupby("ticker")["sign"]
        byt["votes_sum"] = gv.sum().reindex(idx)
        byt["ti_like"] = (gv.sum() / gv.size()).reindex(idx)
        n_active = gv.size().reindex(idx).fillna(0)
        hs = cur_signs.copy()
        hs["qtag"] = str(p.date())
        hs["col"] = hs["qtag"] + "|" + hs["ticker"]
        hist_signs.append(hs)                  # AFTER use: C is strictly past

        # ---- S4: signed fragility ---------------------------------------- #
        fl = implied_flows(cur, prev, cmap, ret_q)
        adv_i = pd.Series(idx.map(adv_d), index=idx)

        def dollar_pressure(flows: pd.Series) -> pd.Series:
            rows = pair[pair["value_p"].notna()].copy()
            f_row = rows["filer_id"].map(flows)
            rows = rows[f_row.notna()]
            rows["press"] = f_row.loc[rows.index] * rows["value_p"]
            # no covered holder = factually zero pressure, not missing
            out = rows.groupby("ticker")["press"].sum() \
                .reindex(idx).fillna(0.0)
            return (out / adv_i).replace([np.inf, -np.inf], np.nan)

        byt["pressure"] = dollar_pressure(fl["flow"]) if len(fl) else np.nan
        rng = np.random.default_rng(int(p.value) % (2**32))
        if len(fl):
            perm = pd.Series(rng.permutation(fl["flow"].values),
                             index=fl.index)
            byt["press_placebo"] = dollar_pressure(perm)
        else:
            byt["press_placebo"] = np.nan
        if len(hist_flows) >= MIN_FLOW_Q:
            F = pd.concat(list(hist_flows), axis=1)
            Fd = F.sub(F.mean(axis=1), axis=0).fillna(0.0)
            z2 = pd.Series(0.0, index=idx)
            for col in Fd.columns:
                z = dollar_pressure(Fd[col])
                z2 = z2.add(z.pow(2), fill_value=0.0)
            frag = z2 / Fd.shape[1]
            byt["signed_frag"] = byt["pressure"] * np.sqrt(frag.reindex(idx))
        else:
            byt["signed_frag"] = np.nan
        if len(fl):
            hist_flows.append(fl["flow"].rename(str(p.date())))

        # ---- S5: headroom x new_conviction ------------------------------- #
        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        npos = pc_w.groupby("filer_id")["w"].transform("size")
        q95_now = pc_w[npos >= 15].groupby("filer_id")["w"].quantile(0.95)
        wmax = pd.Series(dtype=float)
        if len(hist_q95) >= MIN_WMAX_Q:
            W = pd.concat(list(hist_q95), axis=1)
            wmax = W.mean(axis=1)[W.notna().sum(axis=1) >= MIN_WMAX_Q]
        # new_conviction (same construction as signal_defs, ticker level)
        thr = pc_w.groupby("filer_id")["w"].transform(
            lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pair[["filer_id", "ticker", "shares_p", "dio",
                              "is_new"]], on=["filer_id", "ticker"],
                        how="left")
        m5["shares_p_adj"] = m5["shares_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["is_new"].fillna(True) \
            | (m5["shares"] >= 1.25 * m5["shares_p_adj"])
        top = m5[(m5["w"] >= thr.values) & grew]
        byt["new_conv"] = (top.groupby("ticker")["filer_id"].nunique()
                           .reindex(idx).fillna(0) / n_filers)
        if len(wmax):
            buyers = m5[(m5["dio"].fillna(0) > 0)
                        & m5["filer_id"].isin(wmax.index)].copy()
            hr = (buyers["filer_id"].map(wmax) - buyers["w"]).clip(lower=0)
            aum = buyers["filer_id"].map(
                pc.groupby("filer_id")["value"].sum())
            buyers["cap"] = hr * aum
            bc = buyers.groupby("ticker")["cap"].sum().reindex(idx)
            byt["buycap"] = (bc / adv_i).replace([np.inf, -np.inf], np.nan)
            byt["cont_score"] = (byt["new_conv"].rank(pct=True)
                                 * byt["buycap"].rank(pct=True).fillna(0.0))
        else:
            byt["buycap"] = np.nan
            byt["cont_score"] = np.nan
        if len(q95_now):
            hist_q95.append(q95_now.rename(str(p.date())))

        # ---- update age state (for the NEXT quarter's cohorts) ----------- #
        held = pair.loc[pair["shares_c"].notna(), ["filer_id", "ticker"]]
        held_key = pd.MultiIndex.from_frame(held)
        new_age = pd.Series(a_prev[pair["shares_c"].notna()].values + 1,
                            index=held_key).clip(upper=10).astype(np.int16)
        age = new_age
        age_warm += 1

        # ---- evaluate ----------------------------------------------------- #
        # visibility floor: crowds need a minimal crowd (max of cur/prev
        # holders, so a fully-exited name still counts)
        n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)],
                          axis=1).max(axis=1).fillna(0)
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0)
                  & (n_max >= 5) & (n_active >= 3)]
        byt = byt.loc[uni]
        ctrl = pd.DataFrame({
            "log_mktcap": np.log(pd.Series(uni.map(mc_d), index=uni)),
            "log_adv": np.log(pd.Series(uni.map(adv_d), index=uni))})

        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1]))
        fwd = fwd.reindex(uni)

        ranks: dict[tuple, pd.Series] = {}
        for name in THEOREM:
            s = byt[name].replace([np.inf, -np.inf], np.nan)
            if s.notna().sum() < 150:
                continue
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            r_raw = s.rank(pct=True)
            r_res = residualise(r_raw, ctrl).rank(pct=True)
            for ver, r in [("raw", r_raw), ("resid", r_res)]:
                ranks[(name, ver)] = r
                df = pd.concat([r.rename("s"), fwd.rename("f")],
                               axis=1).dropna()
                if len(df) < 150:
                    continue
                jit = pd.Series(rng.uniform(0, 1e-9, len(df)),
                                index=df.index)
                q = pd.qcut((df["s"] + jit).rank(), 5, labels=False) + 1
                ew = df.groupby(q)["f"].mean()
                w = pd.Series(df.index.map(mc_d), index=df.index).fillna(0.0)
                vw = df.assign(w=w).groupby(q).apply(
                    lambda g: np.average(g["f"], weights=g["w"])
                    if g["w"].sum() > 0 else np.nan)
                events.setdefault((name, ver), []).append({
                    "period": p,
                    "spread_ew": ew.get(5, np.nan) - ew.get(1, np.nan),
                    "spread_vw": vw.get(5, np.nan) - vw.get(1, np.nan),
                    "ic": sps.spearmanr(df["s"], df["f"])[0],
                    "mono": float(np.mean(np.diff(
                        [ew.get(k, np.nan) for k in range(1, 6)]) >= 0)),
                    "n": len(df)})

        # paired deltas on the COMMON sample (the honest comparison)
        for a, b, ver in PAIRS:
            ra, rb = ranks.get((a, ver)), ranks.get((b, ver))
            if ra is None or rb is None:
                continue
            df = pd.concat([ra.rename("a"), rb.rename("b"),
                            fwd.rename("f")], axis=1).dropna()
            if len(df) < 150:
                continue

            def spread(col):
                q = pd.qcut(df[col].rank(method="first"), 5, labels=False)
                g = df.groupby(q)["f"].mean()
                return g.get(4, np.nan) - g.get(0, np.nan)

            paired_rows.append({
                "period": p, "pair": f"{a} vs {b} ({ver})",
                "d_ic": sps.spearmanr(df["a"], df["f"])[0]
                - sps.spearmanr(df["b"], df["f"])[0],
                "d_spread": spread("a") - spread("b"), "n": len(df)})

        log(f"{p.date()}: uni {len(uni)}, gls_m {len(v)}, "
            f"flows {len(fl)}, wmax {len(wmax)}")

    # ---- aggregate -------------------------------------------------------- #
    rows = []
    for (name, ver), evs in events.items():
        e = pd.DataFrame(evs)
        rows.append({
            "signal": name, "version": ver,
            "headline": (ver == "resid") == THEOREM[name],
            "n_events": len(e),
            "spread_ew_q": e["spread_ew"].mean(),
            "t_ew": nw_tstat(e["spread_ew"]),
            "sharpe_ew": (e["spread_ew"].mean() / e["spread_ew"].std()
                          * np.sqrt(4)),
            "spread_vw_q": e["spread_vw"].mean(),
            "t_vw": nw_tstat(e["spread_vw"]),
            "ic": e["ic"].mean(),
            "ic_ir": (e["ic"].mean() / e["ic"].std()
                      if e["ic"].std() > 0 else np.nan),
            "mono": e["mono"].mean()})
    summ = (pd.DataFrame(rows)
            .sort_values(["headline", "t_ew"], ascending=[False, False]))
    summ.to_csv(RESULTS / "np_summary.csv", index=False)
    pr = pd.DataFrame(paired_rows)
    pr.to_csv(RESULTS / "np_paired.csv", index=False)

    L = ["# new_positioning - top-5 do doc externo, protocolo unico", "",
         "Mesma regua de general_predictive_signals: PIT em D+45, "
         "quintis EW/VW, NW(4), IC. Headline fixado pelo teste do "
         "teorema ANTES dos retornos.", "",
         "## Sumario (headline primeiro, por t EW)", ""]
    cols = ["signal", "version", "spread_ew_q", "t_ew", "sharpe_ew",
            "spread_vw_q", "t_vw", "ic", "ic_ir", "mono", "n_events"]
    L.append(summ[summ["headline"]][cols].round(4).to_markdown(index=False))
    L += ["", "## Versao alternativa", "",
          summ[~summ["headline"]][cols].round(4).to_markdown(index=False)]
    L += ["", "## Deltas pareados (refinamento - base, amostra comum)", ""]
    if len(pr):
        for pname, g in pr.groupby("pair"):
            L.append(f"- **{pname}**: dIC {g['d_ic'].mean():+.4f} "
                     f"(t={nw_tstat(g['d_ic']):+.2f}), dSpread "
                     f"{g['d_spread'].mean():+.4f}/tri "
                     f"(t={nw_tstat(g['d_spread']):+.2f}), "
                     f"{len(g)} tri")
    L += ["", "## Curva de alpha por idade da posicao (cohort, raw)", ""]
    for a in ["cohort0", "cohort1", "cohort2", "cohort3", "cohort4p"]:
        e = events.get((a, "raw"))
        if e:
            df = pd.DataFrame(e)
            L.append(f"- {a}: spread {df['spread_ew'].mean():+.4f}/tri "
                     f"t={nw_tstat(df['spread_ew']):+.2f} "
                     f"IC {df['ic'].mean():+.3f}")
    L += ["", "## Placebo de fluxo (press_placebo deve ser ~0)", ""]
    e = events.get(("press_placebo", "raw"))
    if e:
        df = pd.DataFrame(e)
        L.append(f"- press_placebo: spread {df['spread_ew'].mean():+.4f} "
                 f"t={nw_tstat(df['spread_ew']):+.2f} (tese em pressure: "
                 f"t deve ser maior em modulo)")
    (RESULTS / "NP_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
