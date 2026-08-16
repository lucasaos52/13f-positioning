"""Signal factory: 17 positioning signals, each with its neutralisation
verdict decided by ONE criterion, stated per signal:

    THEOREM TEST: would the signal correlate with size/liquidity in a world
    of dart-throwing managers (zero information, value-weighted random
    books)? If YES, the correlation is construction, not choice - carries
    zero information by mathematics - and the ex-ante residual against
    log(mktcap) + log(dollar ADV) is the headline version. If NO, the raw
    signal is the headline: any size/style correlation is then an empirical
    hypothesis (channel or confounder), which belongs to the EX-POST ladder,
    never to ex-ante deletion (deleting is irreversible and unidentified -
    it cannot distinguish "signal is momentum in drag" from "the mechanism
    works through returns").

Both versions are computed and evaluated for every signal regardless: for
non-theorem signals the two should roughly agree (and that agreement is
itself a diagnostic); for theorem signals the gap measures the mechanical
part. Nothing is decided by which version backtests better - the headline
flag is set HERE, before any return is seen.

Every signal is built from two point-in-time snapshots (both materialised
at the same decision date) plus market context strictly before the decision
date. Quantity units everywhere (shares, counts, ratios) - value units mix
price into quantity and manufacture R2 (nowcasting plan §2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SignalMeta:
    name: str
    theorem: bool                 # ex-ante residual is the headline?
    expected: str                 # literature target / expected sign
    why: str                      # one-line neutralisation justification
    extra_controls: list = field(default_factory=list)


CATALOGUE: dict[str, SignalMeta] = {}


def _reg(meta: SignalMeta):
    CATALOGUE[meta.name] = meta


# --------------------------------------------------------------------------- #
# A. Breadth family - Chen, Hong & Stein (2002)
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "dbreadth", theorem=False,
    expected="CHS 2002: +6.38%/12m decile spread (~1.6%/q); replicated here at +1.65%/q",
    why="Delta of a ratio: monkey books give dBreadth ~ 0 for every stock - "
        "no mechanical size link. Raw is headline; momentum overlap is a "
        "channel hypothesis, judged ex post."))

_reg(SignalMeta(
    "dbreadth_common", theorem=False,
    expected="CHS variant; common-filer lesson: delta over common filers only "
             "removes universe-churn noise",
    why="Same as dbreadth; restricting to filers present in both quarters "
        "removes AUM-growth composition flow (the VI-flip lesson)."))

_reg(SignalMeta(
    "breadth_level", theorem=True,
    expected="CHS: LEVELS are weak; expected ~null after size",
    why="THEOREM: with finite dart books allocated by value weights, "
        "P(stock held) rises with mktcap by construction - the level IS a "
        "size measure. Residual is headline."))

# --------------------------------------------------------------------------- #
# B. Ownership levels and changes - the declared nulls
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "dio", theorem=False,
    expected="Chincarini et al.: no significant alpha (declared null)",
    why="Delta of IO ratio, split-safe with contemporaneous SO; monkey "
        "world gives 0 everywhere. Raw."))

_reg(SignalMeta(
    "pso", theorem=False,
    expected="Chincarini et al.: PSO carries no alpha (declared null)",
    why="NOT a theorem: monkey value-weight books give IO% CONSTANT across "
        "stocks. The empirical size correlation (Gompers-Metrick) is "
        "institutional PREFERENCE - behaviour, not arithmetic - so it is "
        "tested ex post, not deleted ex ante."))

# --------------------------------------------------------------------------- #
# C. Crowding / capacity - Brown-Howard-Lundblad, Chincarini
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "days_adv", theorem=True,
    expected="BHL/Chincarini: raw VW FF3 alpha spread +1.44%/mo (t=9.67); "
             "Amihud-adjusted +0.89 - we replicated the point (+1.46) already",
    why="THEOREM: ADV sits in the denominator; monkey books give "
        "days_adv = const/turnover-velocity - a liquidity screen with zero "
        "information. Residual (= ownership choice given liquidity) is "
        "headline; raw kept for the literature row."))

_reg(SignalMeta(
    "d_days_adv", theorem=True,
    expected="no direct published number; crowding freshness (E3 logic: "
             "capacity measures rot fast) implies short-horizon info",
    why="THEOREM inherited from days_adv (same denominator)."))

_reg(SignalMeta(
    "herf_holders", theorem=True,
    expected="Greenwood-Thesmar fragility direction: concentrated ownership "
             "-> fire-sale tail; sign ambiguous unconditionally",
    why="THEOREM: HHI of holder shares falls mechanically as n_holders "
        "grows, and n_holders grows with size by construction. Controls "
        "include log(n_holders).", extra_controls=["log_n_holders"]))

# --------------------------------------------------------------------------- #
# D. Conviction / best ideas - Anton, Cohen & Polk (2021)
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "conviction_top", theorem=True,
    expected="ACP best ideas: +2.8-4.5%/yr, 6-factor alpha 25-36 bps/mo",
    why="THEOREM - and a correction: the first classification said 'every "
        "book has a top decile relative to itself, no size link'. Wrong. "
        "Apply the monkey test properly: in value-weighted dart books, "
        "WHICH stocks occupy every top decile? The mega caps, mechanically. "
        "Raw top-decile membership is a popularity/size count; ACP "
        "themselves define conviction as tilt NET of market weight. "
        "Residual is headline. (The data agreed - raw sorts negative, "
        "residual replicates ACP direction - but the reclassification "
        "stands on the monkey argument, which needs no returns.)"))

_reg(SignalMeta(
    "new_conviction", theorem=True,
    expected="ACP + flow: conviction expressed by NEW/raised positions; "
             "fresher subset of best ideas",
    why="Same THEOREM as conviction_top (same top-decile membership "
        "construction)."))

# --------------------------------------------------------------------------- #
# E. Trading imbalances at HONEST timing - Miori-Cucuringu, our replica
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "ti", theorem=False,
    expected="paper's contrarian edge lives INSIDE the disclosure window "
             "(our replica): honest-timing expectation ~0 or follow(+)",
    why="Bounded ratio in [-1,1] per stock; count-based, no size mechanics."))

_reg(SignalMeta(
    "vi", theorem=False,
    expected="same as ti; volume version (composition-flow sensitive)",
    why="Bounded ratio; volume-based but normalised within stock."))

# --------------------------------------------------------------------------- #
# F. Entry / exit structure - the long-only short-constraint channel
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "entry_rate", theorem=False,
    expected="CHS mechanism: new holders = optimists arriving; positive",
    why="Count ratio vs prior holder base; monkey churn is symmetric "
        "across stocks."))

_reg(SignalMeta(
    "exit_rate", theorem=False,
    expected="complete exits are the strongest negative statement a "
             "long-only book can make (the only 'short' it has); NEGATIVE",
    why="Same construction as entry_rate."))

_reg(SignalMeta(
    "net_entry", theorem=False,
    expected="entry minus exit; CHS direction, positive",
    why="Difference of two symmetric count ratios."))

# --------------------------------------------------------------------------- #
# G. Demand persistence and the ragged edge - Sias; Christoffersen
# --------------------------------------------------------------------------- #
_reg(SignalMeta(
    "dio_2q", theorem=False,
    expected="Sias (2004): institutional demand is persistent and predicts "
             "returns; 2-quarter cumulated demand, positive",
    why="Sum of two split-safe IO deltas; no size mechanics."))

_reg(SignalMeta(
    "late_minus_early_dio", theorem=False,
    expected="Christoffersen-Danesh-Musto: strategic LATE filers hide "
             "information; their demand minus early filers' demand should "
             "carry the informative component. Original construction.",
    why="Difference of two same-quarter demand aggregates - any size "
        "effect hits both terms identically and cancels."))

_reg(SignalMeta(
    "conf_reveal", theorem=False,
    expected="Agarwal et al. 2013: confidential holdings outperform up to "
             "12m (~5.9%/yr for restatement reveals). Low coverage - "
             "evaluated as flagged-group excess, not quintiles",
    why="Binary event flag; no cross-sectional scale at all."))


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def build_all(cur: pd.DataFrame, prev: pd.DataFrame, prev2: pd.DataFrame,
              so_cur: pd.Series, so_prev: pd.Series, so_prev2: pd.Series,
              early_filers: set, new_holdings_instr: pd.Index,
              min_holders: int = 5,
              split_fac: pd.Series | None = None) -> pd.DataFrame:
    """All 17 signals per instrument_id for one decision date.

    cur/prev/prev2: snapshots at the SAME decision date. so_*: shares
    outstanding indexed by instrument (contemporaneous to each period).
    early_filers: filers whose CURRENT-quarter original arrived <= p+40d.
    new_holdings_instr: instruments revealed via NEW HOLDINGS amendments
    in the last 4 quarters (the confidential-treatment reveals).
    """
    n_filers = float(cur["filer_id"].nunique())
    n_filers_prev = float(prev["filer_id"].nunique())

    # split factor (prev-quarter shares -> current units), applied ONLY to
    # share-DELTA constructions below. IO-ratio signals stay on raw shares
    # with contemporaneous SO (already split-safe); counts are unit-free.
    if split_fac is None:
        split_fac = pd.Series(dtype=float)
    def _fac(instr: pd.Series) -> pd.Series:
        return instr.map(split_fac).fillna(1.0)

    g_c = cur.groupby("instrument_id")
    g_p = prev.groupby("instrument_id")
    sh_c, sh_p = g_c["shares"].sum(), g_p["shares"].sum()
    n_c, n_p = g_c["filer_id"].nunique(), g_p["filer_id"].nunique()
    val_c = g_c["value_usd"].sum()

    idx = sh_c.index.union(sh_p.index)
    out = pd.DataFrame(index=idx)

    # A. breadth
    out["breadth_level"] = (n_c / n_filers).reindex(idx)
    out["dbreadth"] = (n_c.reindex(idx).fillna(0) / n_filers
                       - n_p.reindex(idx).fillna(0) / n_filers_prev)
    common = np.intersect1d(cur["filer_id"].unique(), prev["filer_id"].unique())
    cc = cur[cur["filer_id"].isin(common)].groupby("instrument_id")["filer_id"].nunique()
    pc = prev[prev["filer_id"].isin(common)].groupby("instrument_id")["filer_id"].nunique()
    out["dbreadth_common"] = (cc.reindex(idx).fillna(0)
                              - pc.reindex(idx).fillna(0)) / len(common)

    # B. ownership (IO ratio, contemporaneous SO -> split-safe)
    io_c = (sh_c / so_cur.reindex(sh_c.index)).replace([np.inf, -np.inf], np.nan)
    io_p = (sh_p / so_prev.reindex(sh_p.index)).replace([np.inf, -np.inf], np.nan)
    io_c, io_p = io_c[(io_c > 0) & (io_c < 1.5)], io_p[(io_p > 0) & (io_p < 1.5)]
    out["pso"] = io_c.reindex(idx)
    out["dio"] = (io_c.reindex(idx) - io_p.reindex(idx))

    # C. crowding (value over the caller-supplied dollar ADV, joined later -
    #    here we store the numerator; run script divides by ADV and builds
    #    the deltas so ADV is measured at ONE date for both quarters)
    out["inst_value"] = val_c.reindex(idx)
    out["inst_value_prev"] = g_p["value_usd"].sum().reindex(idx)

    # holder concentration within the stock
    w2 = cur.assign(w2=(cur["shares"] /
                        cur.groupby("instrument_id")["shares"].transform("sum")) ** 2)
    out["herf_holders"] = w2.groupby("instrument_id")["w2"].sum().reindex(idx)
    out["log_n_holders"] = np.log1p(n_c.reindex(idx))

    # D. conviction: top-decile-of-own-book membership counts
    cur2 = cur.assign(w=cur["value_usd"] /
                      cur.groupby("filer_id")["value_usd"].transform("sum"))
    thr = cur2.groupby("filer_id")["w"].transform(lambda s: s.quantile(0.9))
    top = cur2[cur2["w"] >= thr]
    out["conviction_top"] = (top.groupby("instrument_id")["filer_id"].nunique()
                             .reindex(idx).fillna(0) / n_filers)
    m = cur2.merge(prev[["filer_id", "instrument_id", "shares"]],
                   on=["filer_id", "instrument_id"], how="left",
                   suffixes=("", "_p"))
    m["thr"] = thr.values          # left merge preserves cur2 row order
    m["shares_p"] = m["shares_p"] * _fac(m["instrument_id"])
    grew = m[(m["shares_p"].isna()) | (m["shares"] >= 1.25 * m["shares_p"])]
    grew_top = grew[grew["w"] >= grew["thr"]]
    out["new_conviction"] = (grew_top.groupby("instrument_id")["filer_id"]
                             .nunique().reindex(idx).fillna(0) / n_filers)

    # E. imbalances, all-filers deltas (paper definition), honest timing,
    #    prev shares rescaled to current units (split adjustment)
    prev_adj = prev.set_index(["filer_id", "instrument_id"])["shares"] \
        * _fac(prev["instrument_id"]).values
    d = (cur.set_index(["filer_id", "instrument_id"])["shares"]
         .sub(prev_adj, fill_value=0.0))
    d = d[d != 0].reset_index()
    buys = d[d["shares"] > 0].groupby("instrument_id")["shares"]
    sells = d[d["shares"] < 0].groupby("instrument_id")["shares"]
    bvol, svol = buys.sum(), sells.sum().abs()
    bn, sn = buys.size(), sells.size()
    out["ti"] = ((bn.reindex(idx).fillna(0) - sn.reindex(idx).fillna(0))
                 / (bn.reindex(idx).fillna(0) + sn.reindex(idx).fillna(0))
                 .replace(0, np.nan))
    out["vi"] = ((bvol.reindex(idx).fillna(0) - svol.reindex(idx).fillna(0))
                 / (bvol.reindex(idx).fillna(0) + svol.reindex(idx).fillna(0))
                 .replace(0, np.nan))
    out["n_active"] = (bn.reindex(idx).fillna(0) + sn.reindex(idx).fillna(0))

    # F. entry / exit
    prev_hold = prev.groupby("instrument_id")["filer_id"].agg(set)
    cur_hold = cur.groupby("instrument_id")["filer_id"].agg(set)
    ent, exi = {}, {}
    for j in idx:
        pj = prev_hold.get(j, set())
        cj = cur_hold.get(j, set())
        base = max(len(pj), 1)
        ent[j] = len(cj - pj) / base
        exi[j] = len(pj - cj) / base
    out["entry_rate"] = pd.Series(ent)
    out["exit_rate"] = pd.Series(exi)
    out["net_entry"] = out["entry_rate"] - out["exit_rate"]

    # G. persistence + ragged edge
    if prev2 is not None and len(prev2):
        sh_p2 = prev2.groupby("instrument_id")["shares"].sum()
        io_p2 = (sh_p2 / so_prev2.reindex(sh_p2.index)).replace(
            [np.inf, -np.inf], np.nan)
        io_p2 = io_p2[(io_p2 > 0) & (io_p2 < 1.5)]
        out["dio_2q"] = out["dio"] + (io_p.reindex(idx) - io_p2.reindex(idx))
    else:
        out["dio_2q"] = np.nan

    late = cur[~cur["filer_id"].isin(early_filers)]
    early = cur[cur["filer_id"].isin(early_filers)]
    prev_l = prev[~prev["filer_id"].isin(early_filers)]
    prev_e = prev[prev["filer_id"].isin(early_filers)]

    def dsh(a, b):
        cur_sh = a.groupby("instrument_id")["shares"].sum()
        prv_sh = b.groupby("instrument_id")["shares"].sum()
        prv_sh = prv_sh * prv_sh.index.to_series().map(split_fac).fillna(1.0)
        return cur_sh.sub(prv_sh, fill_value=0.0)
    base = (sh_p * sh_p.index.to_series().map(split_fac).fillna(1.0)) \
        .reindex(idx).replace(0, np.nan)
    out["late_minus_early_dio"] = (dsh(late, prev_l).reindex(idx).fillna(0)
                                   - dsh(early, prev_e).reindex(idx).fillna(0)) / base

    out["conf_reveal"] = out.index.isin(new_holdings_instr).astype(float)

    # visibility floor: signals about crowds need a minimal crowd. Use the
    # MAX of current and prior holder counts - a name fully exited this
    # quarter (n_c=0) is the most informative exit observation there is,
    # and filtering on current holders alone would silently drop it.
    n_max = pd.concat([n_c.reindex(idx), n_p.reindex(idx)], axis=1).max(axis=1)
    out = out[n_max.fillna(0) >= min_holders]
    return out
