"""Benchmark attribution.

A positioning factor built from institutional holdings is *a priori* exposed to
things that already have names. Managers hold large liquid stocks, so the
signal picks up size. Crowded buying follows past winners, so it picks up
momentum. Demand pressure that reverses is short-term reversal by another
route. A raw Sharpe that survives none of these controls is not a finding.

So every factor return series is regressed on a benchmark set, and what is
reported is the intercept - the part the benchmark does not explain - with a
HAC standard error.

Two things about the benchmark set, stated plainly because they matter for how
much the alpha is worth:

* The benchmark factors here are **built from the same price panel** as the
  strategy, not downloaded. That keeps the pipeline runnable from a clean clone
  with one data source, and it keeps the universe consistent - a proxy built
  from the same names is a *tighter* control than a market-wide series covering
  stocks the strategy could never trade. It is still a proxy. Against real
  data, prefer the Fama-French and AQR series and treat these as a fallback;
  ``load_external_benchmarks`` accepts them directly.
* Attribution answers "is this distinct?", not "is this real?". A factor can
  clear every control here and still be an artefact of a short sample, which is
  what the deflated Sharpe and the sub-period breakdown are for.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

BENCHMARK_COLS = ["mkt", "smb", "mom", "strev", "illiq"]


# --------------------------------------------------------------------------- #
def _spread(panel: pd.DataFrame, sort_col: str, ret_col: str, q: float = 0.3) -> pd.Series:
    """Top-minus-bottom tercile spread of ``ret_col`` sorted on ``sort_col``."""
    def one(g: pd.DataFrame) -> float:
        g = g.dropna(subset=[sort_col, ret_col])
        if len(g) < 10:
            return np.nan
        lo, hi = g[sort_col].quantile(q), g[sort_col].quantile(1 - q)
        top = g.loc[g[sort_col] >= hi, ret_col].mean()
        bot = g.loc[g[sort_col] <= lo, ret_col].mean()
        return float(top - bot)

    return panel.groupby("month").apply(one, include_groups=False)


def build_benchmarks(returns: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Monthly proxy factors from the price panel.

    ``returns`` needs: instrument_id, month, and a return column (``ret_m`` as
    produced by ``monthly_returns``, or ``ret``).
    ``reference`` needs: instrument_id, period_end, mktcap, amihud.

    Momentum is 12-month return skipping the most recent month, which is the
    standard construction - the skip is what separates momentum from short-term
    reversal rather than blending the two.
    """
    r = returns.copy()
    if "ret" not in r.columns:
        ret_col = next((c for c in ("ret_m", "return", "monthly_ret") if c in r.columns), None)
        if ret_col is None:
            raise KeyError(f"no return column in {list(r.columns)}")
        r = r.rename(columns={ret_col: "ret"})
    r["month"] = pd.PeriodIndex(r["month"], freq="M") if not isinstance(
        r["month"].dtype, pd.PeriodDtype
    ) else r["month"]
    r = r.sort_values(["instrument_id", "month"])

    g = r.groupby("instrument_id")["ret"]
    r["ret_lag1"] = g.shift(1)
    r["mom_12_2"] = (
        g.shift(2).add(1).groupby(r["instrument_id"]).rolling(11, min_periods=8).apply(
            np.prod, raw=True
        ).reset_index(level=0, drop=True)
        - 1
    )

    # Characteristics are as of the prior quarter end, so they are known when
    # the month's return begins.
    ref = reference[["instrument_id", "period_end", "mktcap", "amihud"]].copy()
    ref["month"] = pd.PeriodIndex(pd.to_datetime(ref["period_end"]), freq="M")
    ref = ref.sort_values("month")
    r = pd.merge_asof(
        r.sort_values("month"),
        ref.sort_values("month"),
        on="month",
        by="instrument_id",
        direction="backward",
        allow_exact_matches=False,
    )
    r["log_mktcap"] = np.log(r["mktcap"].clip(lower=1))
    r["log_amihud"] = np.log(r["amihud"].clip(lower=1e-14))

    bench = pd.DataFrame(
        {
            "mkt": r.groupby("month")["ret"].mean(),  # equal-weight, no risk-free
            "smb": -_spread(r, "log_mktcap", "ret"),  # small minus big
            "mom": _spread(r, "mom_12_2", "ret"),
            "strev": -_spread(r, "ret_lag1", "ret"),  # losers minus winners
            "illiq": _spread(r, "log_amihud", "ret"),
        }
    )
    return bench.reset_index().rename(columns={"index": "month"})


def load_external_benchmarks(path: str) -> pd.DataFrame:
    """Read a vendor benchmark file (Fama-French, AQR) instead of the proxies.

    Expects a ``month`` column plus one column per factor, in decimal returns.
    Percent-quoted files (the Fama-French default) are detected and rescaled,
    because silently regressing decimal returns on percent factors produces
    betas 100x too small and an alpha that looks wonderful.
    """
    df = pd.read_csv(path)
    df["month"] = pd.PeriodIndex(df["month"].astype(str), freq="M")
    num = df.select_dtypes("number")
    if num.abs().median().median() > 0.5:
        log.warning("benchmark values look like percent; dividing by 100")
        df[num.columns] = num / 100.0
    return df


# --------------------------------------------------------------------------- #
def _ols_nw(y: np.ndarray, X: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients with Newey-West standard errors.

    Written out rather than pulled from statsmodels so the HAC weighting is
    visible and the repository has one fewer dependency.
    """
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta

    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)  # Bartlett
        Xe_t, Xe_tL = X[L:] * e[L:, None], X[:-L] * e[:-L, None]
        G = Xe_t.T @ Xe_tL
        S += w * (G + G.T)

    cov = XtX_inv @ S @ XtX_inv
    return beta, np.sqrt(np.maximum(np.diag(cov), 0.0))


def attribute(
    factor_returns: pd.Series,
    benchmarks: pd.DataFrame,
    cols: list[str] | None = None,
    nw_lags: int = 6,
    periods_per_year: int = 12,
) -> dict:
    """Regress one factor's net returns on the benchmark set.

    Returns the annualised intercept, its HAC t-statistic, the betas, and the
    R-squared. A high R-squared with an insignificant alpha is the outcome that
    should kill a factor, and it is reported as prominently as the alpha.
    """
    cols = [c for c in (cols or BENCHMARK_COLS) if c in benchmarks.columns]
    fr = factor_returns.rename("y").to_frame().reset_index()
    fr.columns = ["month", "y"]
    df = fr.merge(benchmarks, on="month", how="inner").dropna(subset=["y"] + cols)
    if len(df) < 24:
        return {"n": len(df), "note": "too few overlapping months to attribute"}

    y = df["y"].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(dtype=float) for c in cols])
    beta, se = _ols_nw(y, X, nw_lags)

    resid = y - X @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((resid**2).sum()) / ss_tot if ss_tot > 0 else np.nan

    out = {
        "n": len(df),
        "alpha_ann": float(beta[0] * periods_per_year),
        "alpha_t_nw": float(beta[0] / se[0]) if se[0] > 0 else np.nan,
        "r2": float(r2),
        "resid_vol_ann": float(resid.std(ddof=len(cols) + 1) * np.sqrt(periods_per_year)),
    }
    for i, c in enumerate(cols, start=1):
        out[f"beta_{c}"] = float(beta[i])
        out[f"t_{c}"] = float(beta[i] / se[i]) if se[i] > 0 else np.nan
    return out


def attribution_table(
    results: dict[str, dict],
    benchmarks: pd.DataFrame,
    cols: list[str] | None = None,
    nw_lags: int = 6,
) -> pd.DataFrame:
    """One row per factor: raw return, benchmark-adjusted alpha, exposures."""
    rows = []
    for name, res in results.items():
        panel = res.get("panel")
        if panel is None or panel.empty:
            continue
        s = panel.set_index("month")["net_ret"]
        att = attribute(s, benchmarks, cols, nw_lags)
        if "note" in att:
            rows.append({"factor": name, **att})
            continue
        rows.append(
            {
                "factor": name,
                "months": att["n"],
                "raw_ann": float(s.mean() * 12),
                "alpha_ann": att["alpha_ann"],
                "alpha_t_nw": att["alpha_t_nw"],
                "r2": att["r2"],
                **{k: v for k, v in att.items() if k.startswith("beta_")},
            }
        )
    return pd.DataFrame(rows)
