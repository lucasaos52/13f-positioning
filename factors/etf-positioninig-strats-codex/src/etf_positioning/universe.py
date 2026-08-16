"""ETF security classification and manager-behaviour flags.

The ETF strategies need two universes that should not be conflated:

* securities: identify exchange-traded products, then distinguish equity ETFs
  from bond, commodity, inverse and leveraged vehicles;
* filers: retain the broad point-in-time 13F population and describe how each
  manager uses ETFs.  ETF intensity does not identify a passive asset manager:
  Vanguard can report underlying stocks directly, while a macro hedge fund can
  hold mostly ETFs.  We therefore never create a hand-picked "passive manager"
  list from ETF intensity.

The curated ``instrument_class == 'fund'`` flag is a high-recall candidate
screen.  A verified ETF master remains mandatory for production look-through.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import ResearchConfig


ETF_HINT = re.compile(
    r"\b(?:ETF|ISHARES|SPDR|VANGUARD|INVESCO|PROSHARES|DIREXION|WISDOMTREE|"
    r"SELECT SECTOR|EXCHANGE TRADED|INDEX SHS|PORTFOLIO SHS)\b",
    re.IGNORECASE,
)
BOND_HINT = re.compile(
    r"\b(?:BOND|TREAS|TRSY|MUNI|MBS|AGG|FIXED INCOME|CORP(?:ORATE)? BD|"
    r"HIGH YIELD|HI YD|TIPS|FLOATING RATE)\b",
    re.IGNORECASE,
)
COMMODITY_HINT = re.compile(
    r"\b(?:GOLD|SILVER|OIL|CRUDE|NATURAL GAS|COMMODIT|PALLADIUM|PLATINUM)\b",
    re.IGNORECASE,
)
LEVERAGED_HINT = re.compile(
    r"\b(?:2X|3X|ULTRA|INVERSE|BEAR|SHORT|LEVERAGED)\b",
    re.IGNORECASE,
)
THEMATIC_HINT = re.compile(
    r"\b(?:CLEAN|SOLAR|ROBOT|CYBER|GENOMIC|INNOVATION|CANNABIS|BLOCKCHAIN|"
    r"ARTIFICIAL INTELLIGENCE|SEMICONDUCTOR|BIOTECH|CLOUD|LITHIUM|URANIUM)\b",
    re.IGNORECASE,
)
SECTOR_HINT = re.compile(
    r"\b(?:ENERGY|FINANCIAL|TECHNOLOGY|HEALTH|UTILIT|INDUSTRIAL|MATERIAL|"
    r"REAL ESTATE|CONSUMER|COMMUNICATION|SEMICONDUCTOR|BIOTECH)\b",
    re.IGNORECASE,
)
BROAD_HINT = re.compile(
    r"\b(?:S&P ?500|TOTAL (?:STK|STOCK|MARKET)|RUSSELL (?:1000|2000|3000)|"
    r"MSCI (?:USA|EAFE|WORLD)|BROAD MARKET|LARGE CAP|MID CAP|SMALL CAP)\b",
    re.IGNORECASE,
)


def classify_etfs(securities: pd.DataFrame) -> pd.DataFrame:
    """Classify ETF candidates with explicit confidence and asset class.

    Expected columns are ``instrument_id``, issuer/title text and optionally
    ``instrument_class``, ``ticker``, ``is_etf`` and vendor classifications.
    Vendor fields win. Text inference is retained as ``candidate`` rather than
    silently promoted to verified status.
    """

    df = securities.copy()
    issuer = df.get("issuer", pd.Series("", index=df.index)).fillna("").astype(str)
    title = df.get("title_of_class", df.get("title", pd.Series("", index=df.index)))
    title = title.fillna("").astype(str)
    text = issuer + " " + title
    explicit = df.get("is_etf", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    curated = df.get("instrument_class", pd.Series("", index=df.index)).eq("fund")
    hinted = text.str.contains(ETF_HINT, na=False)
    df["etf_candidate"] = explicit | curated | hinted

    vendor_asset = df.get("asset_class", pd.Series(pd.NA, index=df.index, dtype="object"))
    inferred = np.select(
        [
            text.str.contains(BOND_HINT, na=False),
            text.str.contains(COMMODITY_HINT, na=False),
        ],
        ["fixed_income", "commodity"],
        default="equity",
    )
    df["etf_asset_class"] = vendor_asset.where(vendor_asset.notna(), inferred)
    df.loc[~df["etf_candidate"], "etf_asset_class"] = "not_etf"

    vendor_style = df.get("etf_style", pd.Series(pd.NA, index=df.index, dtype="object"))
    style = np.select(
        [
            text.str.contains(LEVERAGED_HINT, na=False),
            text.str.contains(THEMATIC_HINT, na=False),
            text.str.contains(SECTOR_HINT, na=False),
            text.str.contains(BROAD_HINT, na=False),
        ],
        ["leveraged_inverse", "thematic", "sector", "broad"],
        default="other",
    )
    df["etf_style"] = vendor_style.where(vendor_style.notna(), style)
    df.loc[~df["etf_candidate"], "etf_style"] = "not_etf"

    has_vendor = explicit | vendor_asset.notna() | df.get(
        "ticker", pd.Series(pd.NA, index=df.index)
    ).notna()
    df["etf_confidence"] = np.select(
        [explicit, has_vendor & df["etf_candidate"], curated, hinted],
        ["verified", "mapped", "curated_candidate", "text_candidate"],
        default="not_etf",
    )
    return df


def _manager_turnover(holdings: pd.DataFrame) -> pd.Series:
    """Quarterly minimum-buys-or-sells turnover on reported dollar holdings.

    This is a holdings-based behaviour proxy, not investor cash flow.  Values
    are normalized by the average adjacent-quarter book.  Using the minimum of
    buys and sells avoids classifying pure AUM growth as churn.
    """

    keys = ["filer_id", "period_end", "instrument_id"]
    h = holdings.groupby(keys, as_index=False)["value_usd"].sum()
    wide = h.pivot_table(
        index=["filer_id", "instrument_id"], columns="period_end", values="value_usd", fill_value=0.0
    )
    periods = list(wide.columns)
    rows: list[tuple[str, pd.Timestamp, float]] = []
    for prev, cur in zip(periods[:-1], periods[1:]):
        delta = wide[cur] - wide[prev]
        buys = delta.clip(lower=0).groupby(level=0).sum()
        sells = (-delta.clip(upper=0)).groupby(level=0).sum()
        b0 = wide[prev].groupby(level=0).sum()
        b1 = wide[cur].groupby(level=0).sum()
        traded = pd.concat([buys.rename("buys"), sells.rename("sells")], axis=1).fillna(0.0)
        turn = traded.min(axis=1) / ((b0 + b1) / 2).replace(0, np.nan)
        rows.extend((f, pd.Timestamp(cur), float(v)) for f, v in turn.dropna().items())
    if not rows:
        return pd.Series(dtype=float, name="turnover")
    out = pd.DataFrame(rows, columns=["filer_id", "period_end", "turnover"])
    return out.set_index(["filer_id", "period_end"])["turnover"]


def build_manager_features(
    holdings: pd.DataFrame,
    etf_master: pd.DataFrame,
    config: ResearchConfig | None = None,
) -> pd.DataFrame:
    """One row per manager-quarter with ETF usage and portfolio diagnostics."""

    cfg = config or ResearchConfig()
    required = {"filer_id", "period_end", "instrument_id", "value_usd"}
    missing = required - set(holdings)
    if missing:
        raise ValueError(f"holdings missing columns: {sorted(missing)}")
    h = holdings.copy()
    h["period_end"] = pd.to_datetime(h["period_end"])
    flags = etf_master.drop_duplicates("instrument_id").set_index("instrument_id")
    h["is_etf"] = h["instrument_id"].map(flags["etf_candidate"]).fillna(False)
    h["is_equity_etf"] = (
        h["is_etf"]
        & h["instrument_id"].map(flags["etf_asset_class"]).eq("equity")
    )

    grp = h.groupby(["filer_id", "period_end"])
    out = grp.agg(
        aum_13f_equity_usd=("value_usd", "sum"),
        n_positions=("instrument_id", "nunique"),
        largest_position_usd=("value_usd", "max"),
    )
    etf_value = h[h["is_etf"]].groupby(["filer_id", "period_end"])["value_usd"].sum()
    eq_etf_value = h[h["is_equity_etf"]].groupby(["filer_id", "period_end"])["value_usd"].sum()
    out["etf_value_usd"] = etf_value.reindex(out.index, fill_value=0.0)
    out["equity_etf_value_usd"] = eq_etf_value.reindex(out.index, fill_value=0.0)
    out["etf_intensity"] = out["etf_value_usd"] / out["aum_13f_equity_usd"].replace(0, np.nan)
    out["equity_etf_intensity"] = (
        out["equity_etf_value_usd"] / out["aum_13f_equity_usd"].replace(0, np.nan)
    )
    out["top1_weight"] = out["largest_position_usd"] / out["aum_13f_equity_usd"].replace(0, np.nan)
    out = out.join(_manager_turnover(h), how="left")
    out["eligible_base"] = (
        (out["aum_13f_equity_usd"] >= cfg.min_manager_book_usd)
        & (out["n_positions"] >= cfg.min_manager_positions)
    )
    return out.reset_index()


def manager_style_flags(
    features: pd.DataFrame, config: ResearchConfig | None = None
) -> pd.DataFrame:
    """Add descriptive, point-in-time manager styles and lagged run-proneness.

    ``transient`` uses only the manager's observations strictly before the
    labelled quarter.  ETF intensity labels current implementation style; they
    deliberately do not claim legal passive/active status.
    """

    cfg = config or ResearchConfig()
    out = features.sort_values(["filer_id", "period_end"]).copy()
    x = out["etf_intensity"].fillna(0.0)
    out["manager_style"] = np.select(
        [x <= cfg.direct_specialist_threshold, x >= cfg.etf_specialist_threshold],
        ["direct_stock_specialist", "etf_allocator"],
        default="mixed",
    )
    out["passive_manager"] = pd.NA
    out["passive_manager_reason"] = "not inferred from 13F ETF intensity"

    def lagged_percentile(s: pd.Series) -> pd.Series:
        vals = s.to_numpy(dtype=float)
        ranks = np.full(len(vals), np.nan)
        for i in range(len(vals)):
            hist = vals[:i]
            hist = hist[np.isfinite(hist)]
            if len(hist) >= 4 and np.isfinite(vals[i]):
                ranks[i] = (hist <= vals[i]).mean()
        return pd.Series(ranks, index=s.index)

    out["turnover_history_pct"] = (
        out.groupby("filer_id", group_keys=False)["turnover"].apply(lagged_percentile)
    )
    out["transient"] = out["turnover_history_pct"] >= cfg.transient_turnover_quantile
    return out


def manager_quality_weights(features: pd.DataFrame) -> pd.DataFrame:
    """Pre-specified Strategy #8 weights, based only on lagged ETF intensity.

    The neutral column is the mandatory ablation.  ``direct_tilt`` is a soft
    implementation of the Sherrill et al. result; ``direct_specialist`` is a
    deliberately coarse robustness portfolio.  These are manager-quality
    proxies, not declarations that a filer is legally active or passive.
    """

    required = {"filer_id", "period_end", "etf_intensity", "eligible_base"}
    missing = required - set(features)
    if missing:
        raise ValueError(f"features missing columns: {sorted(missing)}")
    out = features.sort_values(["filer_id", "period_end"])[
        ["filer_id", "period_end", "etf_intensity", "eligible_base"]
    ].copy()
    out["lag_etf_intensity"] = out.groupby("filer_id")["etf_intensity"].shift(1)
    eligible = out["eligible_base"].fillna(False).astype(float)
    out["weight_neutral"] = eligible
    out["weight_direct_tilt"] = (
        1.0 - out["lag_etf_intensity"].clip(0.0, 1.0)
    ).fillna(0.0) * eligible
    out["weight_direct_specialist"] = (
        out["lag_etf_intensity"].le(0.05) & out["lag_etf_intensity"].notna()
    ).astype(float) * eligible
    return out
