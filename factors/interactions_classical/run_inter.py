"""Interactions 13F signal x CLASSICAL stock characteristic - the dedicated
double-sort exercise the project had not run.

    python run_inter.py            # full sample
    python run_inter.py --smoke    # last ~12 quarters

FIVE pre-registered interactions (theory first, no sweep). For each, the
conditioning variable, the bucket where the signal should be STRONGER, and
the expected sign of the paired delta were fixed before any return was seen:

  E1  new_conviction  x  mktcap      stronger in SMALL (limits to arbitrage;
                                     CHS report their effect in small caps)
  E2  dbreadth        x  IO level    stronger in LOW IO (Nagel 2005: binding
                                     short constraints keep pessimists out
                                     exactly where institutions are absent -
                                     note this predicts the OPPOSITE of the
                                     naive "more institutions = better data")
  E3  distress_supply x  ADV         MORE NEGATIVE in ILLIQUID (price impact
                                     of forced selling scales with 1/depth)
  E4  pressure        x  vol126      stronger continuation in HIGH VOL
                                     (flow moves price where price is loose)
  E5  exit_rate       x  momentum    MORE NEGATIVE in LOSERS (institutional
                                     exodus + downtrend = continuation, the
                                     distress_mom lesson at the holder-count
                                     margin)

Protocol per quarter (same clock as everything else - decision p+45d, PIT
snapshots, EW quintiles):
  - UNCONDITIONAL spread: quintiles of the signal on the full universe;
  - CONDITIONAL: universe cut into terciles of the conditioner, signal
    re-ranked WITHIN each tercile, spread per tercile;
  - the verdict statistic is the PAIRED DELTA per quarter,
    spread(target tercile) - spread(unconditional), NW(4) t on the series.

Discipline: 5 tests -> Bonferroni; a delta only counts as confirmed at
|t| >= 2.57 (0.05/5 two-sided) with the PRE-REGISTERED sign; |t| >= 1.96 with
the right sign is reported as suggestive. Everything else is noise and says
the unconditional signal is the honest version.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan", "fire_calendar"):
    sys.path.insert(0, str(HERE.parent / sub))

import market_cap as mc                             # noqa: E402
import panel as pn                                  # noqa: E402
from backtest_gp import forward_return, nw_tstat    # noqa: E402
from run_all import load_market, log                # noqa: E402
from run_fire import implied_flows                  # noqa: E402

RESULTS = HERE / "results"
LAG = 45
DISTRESS_FLOW = -0.10

# (signal, conditioner, target tercile 0/1/2, expected delta sign, rationale)
EXPERIMENTS = [
    ("new_conv", "mktcap", 0, +1, "limits to arbitrage: small"),
    ("dbreadth", "io", 0, +1, "Nagel 2005: low-IO short constraints"),
    ("distress", "adv", 0, -1, "impact of forced selling: illiquid"),
    ("pressure", "vol", 2, +1, "flow moves price where vol is high"),
    ("exit_rate", "mom", 0, -1, "exodus in losers: continuation"),
]

# Identification checks for E4, EXPLORATORY (no Bonferroni claim): is the
# vol effect actually size/illiquidity in disguise? (a) condition pressure
# on ADV and mktcap directly - note the signal already divides by ADV, so
# these ask whether the denominator should be convex; (b) condition on
# vol RESIDUALISED on log(ADV)+log(mktcap) - if the gradient survives on
# the orthogonal part of vol, the multiplier is valuation uncertainty,
# not size/liquidity in drag.
EXPLORE = [
    ("pressure", "adv", 0, +1, "illiquid tercile"),
    ("pressure", "mktcap", 0, +1, "small tercile"),
    ("pressure", "vol_resid", 2, +1, "vol orthogonal to size/ADV"),
    # THE MOMENTUM-IN-DRAG CHECK (Zhang 2006 information uncertainty):
    # flow = dAUM - performance, so outflow managers held losers and
    # pressure inherits a past-return tilt; "continuation stronger in high
    # vol" is documented for MOMENTUM under information uncertainty. If
    # pressure is momentum in drag, orthogonalising it to mom(12-1),
    # strev(1m) and the flow-window quarter return kills the T2 gradient.
    # If the gradient survives, the flow story stands on its own feet as
    # a microfoundation, not a repackaging.
    ("pressure_o", "vol", 2, +1, "pressure orth. to mom/strev/retq"),
    ("pressure_o", "vol_resid", 2, +1, "double-orthogonal version"),
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
    """Modal-atom split detector (see run_np.py for the full rationale)."""
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
        qs = qs[-12:]
    log(f"{len(qs)} quarters, {len(EXPERIMENTS)} pre-registered interactions")

    rows: list[dict] = []
    contam: list[dict] = []          # corr(pressure, past returns) per quarter
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
        px, adv_d = mdta.prices_raw.iloc[di], adv.iloc[di_p]
        mc_d = mcap.iloc[di]
        so_c = shares.iloc[di_p]
        ret_q = cum.iloc[di_p] - cum.iloc[di_p1]

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
        pair = pc.merge(pp, on=["filer_id", "ticker"], how="outer",
                        suffixes=("_c", "_p"))
        n_c = pc.groupby("ticker")["filer_id"].nunique()
        n_p = pp.groupby("ticker")["filer_id"].nunique()
        idx = n_c.index.union(n_p.index)
        n_filers = float(cur["filer_id"].nunique())
        sig = pd.DataFrame(index=idx)

        # ---- signals ------------------------------------------------------ #
        # dbreadth over COMMON filers (common-filers variant)
        common = np.intersect1d(pc["filer_id"].unique(), pp["filer_id"].unique())
        cc = pc[pc["filer_id"].isin(common)].groupby("ticker")["filer_id"].nunique()
        pcm = pp[pp["filer_id"].isin(common)].groupby("ticker")["filer_id"].nunique()
        sig["dbreadth"] = (cc.reindex(idx).fillna(0)
                           - pcm.reindex(idx).fillna(0)) / len(common)

        # exit_rate
        is_exit = pair["value_c"].isna() & pair["value_p"].notna()
        deaths = pair[is_exit].groupby("ticker").size()
        sig["exit_rate"] = (deaths.reindex(idx).fillna(0)
                            / n_p.reindex(idx).clip(lower=1))

        # new_conviction (same construction as run_np S5)
        pc_w = pc.copy()
        book = pc_w.groupby("filer_id")["value"].transform("sum")
        pc_w["w"] = pc_w["value"] / book.replace(0, np.nan)
        thr = pc_w.groupby("filer_id")["w"].transform(lambda s: s.quantile(0.9))
        m5 = pc_w.merge(pair[["filer_id", "ticker", "sh_p"]],
                        on=["filer_id", "ticker"], how="left")
        m5["sh_p_adj"] = m5["sh_p"].fillna(0.0) \
            * m5["ticker"].map(fac_t).fillna(1.0)
        grew = m5["sh_p"].isna() | (m5["sh"] >= 1.25 * m5["sh_p_adj"])
        top = m5[(m5["w"] >= thr.values) & grew]
        sig["new_conv"] = (top.groupby("ticker")["filer_id"].nunique()
                           .reindex(idx).fillna(0) / n_filers)

        # implied flows -> pressure and distress supply (fire construction)
        fl = implied_flows(cur, prev, cmap, ret_q)
        adv_i = pd.Series(idx.map(adv_d), index=idx)
        rows_p = pair[pair["value_p"].notna()].copy()
        f_row = rows_p["filer_id"].map(fl["flow"]) if len(fl) else pd.Series(
            np.nan, index=rows_p.index)
        rows_p = rows_p[f_row.notna()]
        rows_p["press"] = f_row.loc[rows_p.index] * rows_p["value_p"]
        sig["pressure"] = (rows_p.groupby("ticker")["press"].sum()
                           .reindex(idx).fillna(0.0) / adv_i) \
            .replace([np.inf, -np.inf], np.nan)

        distressed = fl.index[fl["flow"] < DISTRESS_FLOW] if len(fl) else []
        if len(distressed) >= 10:
            s = pc[pc["filer_id"].isin(distressed)].copy()
            s["advj"] = s["ticker"].map(adv_d)
            s = s.dropna(subset=["advj"])
            s["peck"] = s.groupby("filer_id")["advj"].rank(pct=True)
            fmag = fl["flow"].abs().reindex(s["filer_id"]).values
            aumc = fl["aum_cur"].reindex(s["filer_id"]).values
            s["sup"] = fmag * aumc * (s["value"] / s.groupby("filer_id")
                                      ["value"].transform("sum")) * s["peck"]
            sup = s.groupby("ticker")["sup"].sum()
            sig["distress"] = (sup.reindex(idx).fillna(0.0) / adv_i) \
                .replace([np.inf, -np.inf], np.nan)
        else:
            sig["distress"] = np.nan

        # ---- conditioners (classical characteristics, PIT at dec) -------- #
        io = (pc.groupby("ticker")["sh"].sum().reindex(idx)
              / pd.Series(idx.map(so_c), index=idx)).replace(
            [np.inf, -np.inf], np.nan)
        mom_r = (mdta.prices.iloc[max(di_p - 21, 0)]
                 / mdta.prices.iloc[max(di_p - 252, 0)] - 1.0)
        vol = mdta.returns.iloc[max(di_p - 126, 0):di_p].std()
        cond = pd.DataFrame({
            "mktcap": pd.Series(idx.map(mc_d), index=idx),
            "io": io.where((io > 0) & (io < 1.5)),
            "adv": adv_i,
            "vol": pd.Series(idx.map(vol), index=idx),
            "mom": pd.Series(idx.map(mom_r), index=idx)})
        cond["vol_resid"] = residualise(
            cond["vol"].rank(pct=True),
            pd.DataFrame({"la": np.log(cond["adv"]),
                          "lm": np.log(cond["mktcap"])}))
        strev_r = (mdta.prices.iloc[di_p]
                   / mdta.prices.iloc[max(di_p - 21, 0)] - 1.0)
        cond["strev"] = pd.Series(idx.map(strev_r), index=idx)
        cond["retq"] = pd.Series(idx.map(ret_q), index=idx)
        sig["pressure_o"] = sig["pressure"]     # residualised at eval time
        okc = sig["pressure"].notna() & cond["mom"].notna() \
            & cond["retq"].notna()
        if okc.sum() > 300:
            contam.append({
                "period": p,
                "c_mom": sps.spearmanr(sig.loc[okc, "pressure"],
                                       cond.loc[okc, "mom"])[0],
                "c_retq": sps.spearmanr(sig.loc[okc, "pressure"],
                                        cond.loc[okc, "retq"])[0]})

        # ---- evaluate ----------------------------------------------------- #
        n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)],
                          axis=1).max(axis=1).fillna(0)
        uni = idx[(pd.Series(idx.map(px), index=idx) >= 1.0) & (n_max >= 5)]
        nxt = qs[qi + 1] + pd.Timedelta(days=LAG) if qi + 1 < len(qs) \
            else dates[-1]
        fwd = forward_return(cum, dates, dec, min(nxt, dates[-1])).reindex(uni)
        rng = np.random.default_rng(int(p.value) % (2**32))

        def spread(s, f):
            df = pd.concat([s.rename("s"), f.rename("f")], axis=1).dropna()
            if len(df) < 90:
                return np.nan, 0
            jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
            q = pd.qcut((df["s"] + jit).rank(), 5, labels=False)
            g = df.groupby(q)["f"].mean()
            return g.get(4, np.nan) - g.get(0, np.nan), len(df)

        for name, cvar, tgt, esign, _ in EXPERIMENTS + EXPLORE:
            s = sig[name].reindex(uni).replace([np.inf, -np.inf], np.nan)
            if s.notna().sum() < 300:
                continue
            s = s.clip(s.quantile(0.01), s.quantile(0.99))
            if name == "pressure_o":
                ctrl_m = pd.DataFrame({
                    "mom": cond["mom"].reindex(uni).rank(pct=True),
                    "strev": cond["strev"].reindex(uni).rank(pct=True),
                    "retq": cond["retq"].reindex(uni).rank(pct=True)})
                s = residualise(s.rank(pct=True), ctrl_m)
            if name == "new_conv":
                # THEOREM signal: the honest version is the residual (raw
                # top-decile membership is a mega-cap count). Without this
                # the E1 delta would measure "residualisation works", not
                # "limits to arbitrage" - the smoke run showed exactly that
                # (unconditional raw negative, all three terciles positive).
                ctrl = pd.DataFrame({
                    "log_mktcap": np.log(cond["mktcap"].reindex(uni)),
                    "log_adv": np.log(cond["adv"].reindex(uni))})
                s = residualise(s.rank(pct=True), ctrl)
            c = cond[cvar].reindex(uni)
            ok = s.notna() & c.notna() & fwd.notna()
            if ok.sum() < 450:
                continue
            su, cu, fu = s[ok], c[ok], fwd[ok]
            sp_u, n_u = spread(su, fu)
            ter = pd.qcut(cu.rank(method="first"), 3, labels=False)
            sp_t = {}
            for t3 in range(3):
                m_ = ter == t3
                sp_t[t3], _n = spread(su[m_], fu[m_])
            rows.append({
                "period": p, "exp": f"{name}|{cvar}",
                "spread_uncond": sp_u,
                "spread_t0": sp_t[0], "spread_t1": sp_t[1],
                "spread_t2": sp_t[2],
                "delta": sp_t[tgt] - sp_u, "n": n_u})
        log(f"{p.date()}: uni {len(uni)}, flows {len(fl)}")

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "inter_events.csv", index=False)

    L = ["# interactions_classical - 13F x caracteristica classica", "",
         "5 interacoes pre-registradas (sinal, condicionador, tercil alvo, "
         "sinal esperado do delta). Estatistica-veredito: delta pareado "
         "spread(tercil alvo) - spread(incondicional), NW(4). Bonferroni "
         "5 testes: confirmado |t|>=2.57 com sinal certo; sugestivo "
         "|t|>=1.96.", ""]
    def block(exps, formal: bool):
        out = []
        for name, cvar, tgt, esign, why in exps:
            g = ev[ev["exp"] == f"{name}|{cvar}"]
            if not len(g):
                out.append(f"- **{name} x {cvar}**: sem eventos suficientes")
                continue
            t_d = nw_tstat(g["delta"])
            okd = np.sign(g["delta"].mean()) == esign
            if formal:
                verdict = ("CONFIRMADO" if okd and abs(t_d) >= 2.57 else
                           "sugestivo" if okd and abs(t_d) >= 1.96 else
                           "NAO confirma")
            else:
                verdict = "exploratorio - sem claim formal"
            out += [f"## {name} x {cvar} ({why})", "",
                    f"- incondicional: {g['spread_uncond'].mean():+.4f}/tri "
                    f"(t={nw_tstat(g['spread_uncond']):+.2f})",
                    f"- terciles {cvar} T0/T1/T2: "
                    f"{g['spread_t0'].mean():+.4f} / "
                    f"{g['spread_t1'].mean():+.4f} / "
                    f"{g['spread_t2'].mean():+.4f} (alvo: T{tgt})",
                    f"- **delta pareado**: {g['delta'].mean():+.4f}/tri "
                    f"(t={t_d:+.2f}, esperado "
                    f"{'+' if esign > 0 else '-'}) -> **{verdict}** "
                    f"({len(g)} tri)", ""]
        return out

    L += block(EXPERIMENTS, formal=True)
    L += ["", "# Identificacao do E4 (EXPLORATORIO, motivado pos-resultado)",
          "", "Pergunta: o efeito de vol e size/iliquidez disfarcada? "
          "Se pressure x ADV/mktcap replicar o gradiente e vol_resid nao, "
          "era liquidez; se vol_resid segurar, e incerteza de valuation.", ""]
    L += block(EXPLORE, formal=False)
    if contam:
        cdf = pd.DataFrame(contam)
        L += ["", "## Contaminacao de pressure por retornos passados",
              f"- corr(pressure, mom 12-1) media: {cdf['c_mom'].mean():+.3f}",
              f"- corr(pressure, retorno do tri do fluxo): "
              f"{cdf['c_retq'].mean():+.3f}",
              "- se altas, o sort de pressure e parcialmente um sort de "
              "momentum - dai a necessidade do pressure_o"]
    (RESULTS / "INTER_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
