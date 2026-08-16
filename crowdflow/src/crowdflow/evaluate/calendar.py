"""The point-in-time rebalance calendar.

The 45-day deadline is where most 13F backtests get their timing, and it is the
wrong number. It is a *floor*: filings arrive across a long right tail, late
filers are systematically different from prompt ones, and amendments arrive
months later. Assuming the deadline means assuming a quarter's positioning was
fully visible on day 45 when in practice a material fraction of the universe
had not filed.

So the calendar is derived from the data instead of from the regulation.

For each report period ``p`` we compute, at each candidate rebalance date, the
fraction of the *selected universe* whose filing for ``p`` was publicly
accepted by that date. The period activates on the first rebalance date where
that coverage clears a threshold. The signal for ``p`` is then constructed from
the bitemporal store as of exactly that date - not as of today, not as of the
deadline - and held until the next period activates.

Three consequences, all of them intended:

* the activation lag is an *output*, reported per quarter, not an assumption;
* a quarter in which the universe files late gets used late, automatically;
* a restatement filed after activation never enters the signal that was traded,
  because the store is queried at the activation date and nothing later exists
  from that vantage point.

A further ``implementation_lag_days`` separates the moment the information is
readable from the moment it is traded. One business day is the default: it is
the smallest lag that cannot be accused of assuming same-instant execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Activation:
    period_end: pd.Timestamp
    activation_date: pd.Timestamp  # signal readable
    trade_date: pd.Timestamp  # signal tradeable
    coverage: float
    n_filed: int
    n_expected: int
    lag_days: int


def rebalance_dates(start: str | pd.Timestamp, end: str | pd.Timestamp, freq: str = "M") -> pd.DatetimeIndex:
    """Month-end (or quarter-end) business dates."""
    alias = {"M": "BME", "Q": "BQE", "W": "W-FRI"}.get(freq, freq)
    return pd.bdate_range(start, end, freq=alias)


def build_activation_schedule(
    revisions: pd.DataFrame,
    universe: pd.DataFrame,
    candidate_dates: pd.DatetimeIndex,
    coverage_threshold: float = 0.80,
    implementation_lag_days: int = 1,
    max_wait_days: int = 150,
) -> pd.DataFrame:
    """When each report period becomes usable, given who is in the universe.

    ``max_wait_days`` is a backstop: if a quarter never reaches the coverage
    threshold - which happens when the universe contains a chronically late
    filer - we activate anyway rather than dropping the quarter, and flag the
    shortfall. Silently skipping quarters would be a subtle survivorship
    filter on periods.
    """
    rev = revisions.copy()
    rev["period_end"] = pd.to_datetime(rev["period_end"])
    rev["knowledge_ts"] = pd.to_datetime(rev["knowledge_ts"])
    # Only original filings count toward coverage. An amendment does not make a
    # quarter more visible; it revises something already visible.
    originals = rev[~rev["form"].astype(str).str.endswith("/A")]
    first_seen = originals.groupby(["filer_id", "period_end"])["knowledge_ts"].min()

    rows: list[Activation] = []
    for period, grp in universe.groupby("period_end", sort=True):
        period = pd.Timestamp(period)
        members = list(grp["filer_id"].unique())
        seen = first_seen.reindex(
            pd.MultiIndex.from_product([members, [period]], names=["filer_id", "period_end"])
        ).dropna()
        if seen.empty:
            continue
        n_expected = len(members)

        window = candidate_dates[
            (candidate_dates > period) & (candidate_dates <= period + pd.Timedelta(days=max_wait_days))
        ]
        chosen = None
        for d in window:
            cov = (seen <= d).sum() / n_expected
            if cov >= coverage_threshold:
                chosen = (d, cov, int((seen <= d).sum()))
                break
        if chosen is None:
            if len(window) == 0:
                continue
            d = window[-1]
            chosen = (d, (seen <= d).sum() / n_expected, int((seen <= d).sum()))
            log.warning(
                "%s never reached %.0f%% coverage; activating at %s with %.0f%%",
                period.date(),
                100 * coverage_threshold,
                d.date(),
                100 * chosen[1],
            )

        act_date, cov, n_filed = chosen
        trade = pd.bdate_range(act_date, periods=implementation_lag_days + 1)[-1]
        rows.append(
            Activation(
                period_end=period,
                activation_date=act_date,
                trade_date=trade,
                coverage=float(cov),
                n_filed=n_filed,
                n_expected=n_expected,
                lag_days=int((act_date - period).days),
            )
        )

    out = pd.DataFrame([r.__dict__ for r in rows])
    if not out.empty:
        # Monotonicity: a later quarter must not activate before an earlier one,
        # or the signal series would go backwards in time.
        out = out.sort_values("period_end")
        out["trade_date"] = out["trade_date"].cummax()
        log.info(
            "activation lag: median %d days, p90 %d, max %d",
            int(out["lag_days"].median()),
            int(out["lag_days"].quantile(0.9)),
            int(out["lag_days"].max()),
        )
    return out


def assign_signal_periods(
    month_ends: pd.DatetimeIndex, schedule: pd.DataFrame, staleness_cap_days: int = 200
) -> pd.DataFrame:
    """Map each rebalance month to the report period whose signal is live.

    Between activations the signal is held constant, which is the honest
    representation of a quarterly dataset in a monthly framework: no
    interpolation, no smoothing forward, and an explicit staleness cap so that
    a gap in the filing record produces missing exposure rather than a stale
    position held indefinitely.
    """
    sched = schedule.sort_values("trade_date")
    rows = []
    for d in month_ends:
        live = sched[sched["trade_date"] <= d]
        if live.empty:
            continue
        row = live.iloc[-1]
        age = (d - row["trade_date"]).days
        rows.append(
            {
                "rebalance_date": d,
                "period_end": row["period_end"],
                "signal_age_days": age,
                "stale": age > staleness_cap_days,
            }
        )
    return pd.DataFrame(rows)
