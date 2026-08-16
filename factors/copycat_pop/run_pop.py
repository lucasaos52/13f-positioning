"""Copycat pop triage: do a copied leader's NEW positions pop in the days
right after his filing becomes public?

    python run_pop.py            # full sample
    python run_pop.py --smoke    # last ~12 quarters

WHY the prior is decent (all internal evidence):
  - the quarterly copycat HANGOVER (t=-2.53, placebo clean) is the echo of
    a pop: newly-copied names underperform the NEXT quarter, which requires
    something to have pushed them up around disclosure;
  - our Miori-Cucuringu replication located the ti/vi edge INSIDE the
    disclosure window (honest quarterly timing ~ 0);
  - the shadow-AUM graph (stability 0.94) tells us ex-ante WHICH filings
    have follower capital watching - a cross-sectional prediction generic
    event studies cannot make.

DESIGN (daily closes; the acceptance-to-close granularity is the point of
the exercise - if the effect is intraday-only we WANT to see that as death):
  event   = original quarter-p filing of a leader with positive trailing
            shadow AUM (computed from quarters <= p-1 only - the copy
            behaviour observable before any quarter-p filing arrives);
  tickers = the leader's NEW positions (book at p minus book at p-1);
  entry   = close of the first trading day STRICTLY AFTER filing_date
            (after-hours acceptances are the norm - conservative);
  windows = +1, +3, +5, +10 trading days from entry, excess vs the
            cross-sectional mean of the price universe over the same days;
            diagnostic day0 = close(t0-1) -> close(t0) (the announcement
            move itself, not tradable at the close clock).

PRE-REGISTERED cross-section and placebos:
  gradient  events split by shadow_AUM(leader)/ADV(ticker) terciles -
            the pop must be increasing in follower capital per liquidity;
  placebo A filings by eligible managers with ~zero shadow AUM (no
            followers): their new positions must NOT pop;
  placebo B entry shifted 5 trading days BEFORE the filing date: the
            information is not public there - any "effect" is quarter-end
            contamination, not disclosure.

DEATH RULES (declared before running the full sample):
  (1) high-saum excess at +3/+5 not positive -> no pop at daily clock;
  (2) no gradient vs placebo A -> effect is not copycat, just newness;
  (3) all of the effect in day0/+1 with nothing left at +3/+5 -> the
      window exists but closed for a daily engine (still a finding: dates
      the death of the 2015-era anomaly).
Inference: events cluster on filing dates, so everything is aggregated to
quarter means first; NW(4) t across quarters.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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
N_LEADERS = 300
TRAIL = 4
SNAP_LAG = 80          # one late snapshot per quarter captures ~all filings
HORIZONS = [1, 3, 5, 10]


def main(smoke: bool = False) -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index
    cum = mdta.returns.cumsum()
    adv = mdta.dollar_volume.rolling(63, min_periods=20).median()
    px_all = mdta.prices_raw
    meta = pd.read_parquet(pn.QDIR / "filings_meta.parquet")
    orig = meta[~meta["is_amendment"]].copy()
    orig["filing_date"] = pd.to_datetime(orig["filing_date"])

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1] - pd.Timedelta(days=120)]
    if smoke:
        qs = qs[-12:]
    log(f"{len(qs)} quarters")

    excess_hist: dict[tuple, list] = defaultdict(list)
    leaders_prev_new = None
    leaders_prev: list = []
    saum_past = pd.Series(dtype=float)      # shadow AUM from quarters <= p-1
    umean_cache: dict[tuple, float] = {}
    rows: list[dict] = []

    for qi in range(1, len(qs)):
        p, p1 = qs[qi], qs[qi - 1]
        snap_d = p + pd.Timedelta(days=SNAP_LAG)
        if snap_d >= dates[-1] - pd.Timedelta(days=15):
            break
        cur = pn.snapshot_as_of(p, snap_d)
        prev = pn.snapshot_as_of(p1, snap_d)
        if min(len(cur), len(prev)) < 1000:
            continue
        g = cur.groupby("filer_id")["value_usd"]
        stats = pd.DataFrame({"aum": g.sum(), "n": g.size()})
        elig = stats[(stats["n"].between(15, 500)) & (stats["aum"] >= 250e6)]
        leaders = elig.nlargest(N_LEADERS, "aum").index.tolist()
        cur_sets = cur.groupby("filer_id")["instrument_id"].agg(frozenset)
        prev_sets = prev.groupby("filer_id")["instrument_id"].agg(frozenset)
        new = {f: cur_sets[f] - prev_sets.get(f, frozenset())
               for f in cur_sets.index}

        # ---- events for quarter p use saum from quarters <= p-1 ---------- #
        if len(saum_past) >= 30:
            fm = orig[orig["period_end"] == p] \
                .groupby("filer_id")["filing_date"].min()
            hi_cut = saum_past.quantile(2 / 3)
            zero_leaders = [A for A in leaders
                            if saum_past.get(A, 0.0) <= 0.0]
            di_dec = dates.searchsorted(p + pd.Timedelta(days=45),
                                        side="right") - 1
            adv_d = adv.iloc[di_dec]
            px_d = px_all.iloc[di_dec]
            uni_ok = px_d >= 1.0

            def emit(A, kind, sa):
                f = fm.get(A)
                if f is None or pd.isna(f):
                    return
                ti0 = dates.searchsorted(f, side="right")   # 1st day AFTER f
                if ti0 + 12 >= len(dates) or ti0 < 6:
                    return
                for j in new.get(A, frozenset()):
                    t = cmap.get(j)
                    if t is None or t not in cum.columns:
                        continue
                    if not bool(uni_ok.get(t, False)):
                        continue
                    a_t = adv_d.get(t, np.nan)
                    if not np.isfinite(a_t) or a_t <= 0:
                        continue
                    # Yahoo bad prints (0.001 -> 1.0 = +100,000%/day) both
                    # poison a MEAN benchmark and fabricate event returns:
                    # benchmark is the cross-sectional MEDIAN (robust) and
                    # every individual window return is clipped to +-50%.
                    def wret(i0, h):
                        return float(np.clip(cum[t].iloc[i0 + h]
                                             - cum[t].iloc[i0], -0.5, 0.5))

                    r = {"period": p, "kind": kind, "leader": A,
                         "ticker": t, "sa_adv": sa / a_t,
                         "day0": wret(ti0 - 1, 1)}
                    for h in HORIZONS:
                        key = (ti0, h)
                        if key not in umean_cache:
                            w = (cum.iloc[ti0 + h] - cum.iloc[ti0])
                            umean_cache[key] = float(
                                w[uni_ok.reindex(w.index).fillna(False)]
                                .median())
                        r[f"ex{h}"] = wret(ti0, h) - umean_cache[key]
                        # placebo B: same window shifted 5 days before f
                        kb = (ti0 - 5, h)
                        if kb not in umean_cache:
                            w = (cum.iloc[ti0 - 5 + h] - cum.iloc[ti0 - 5])
                            umean_cache[kb] = float(
                                w[uni_ok.reindex(w.index).fillna(False)]
                                .median())
                        r[f"pre{h}"] = wret(ti0 - 5, h) - umean_cache[kb]
                    rows.append(r)

            n_hi = 0
            for A in saum_past.index:
                sa = float(saum_past[A])
                if sa >= hi_cut and A in new:
                    emit(A, "copied", sa)
                    n_hi += 1
            rng = np.random.default_rng(qi)
            for A in rng.permutation(zero_leaders)[:n_hi]:
                emit(A, "placebo_nofollow", 0.0)
            log(f"{p.date()}: {n_hi} copied leaders, "
                f"{len(saum_past)} with saum")

        # ---- update copy graph (same construction as run_copycat) -------- #
        if leaders_prev_new:
            followers = [f for f in elig.index if f not in leaders_prev]
            for B in followers:
                nb = new.get(B, frozenset())
                if len(nb) < 3:
                    continue
                raw = {A: len(nb & la) / len(nb)
                       for A, la in leaders_prev_new.items() if la}
                if not raw:
                    continue
                base = np.mean(list(raw.values()))
                for A, v in raw.items():
                    if v - base > 0:
                        excess_hist[(B, A)].append((qi, v - base))
        saum = defaultdict(float)
        for (B, A), hist in excess_hist.items():
            recent = [v for (qq, v) in hist if qi - TRAIL <= qq <= qi]
            if recent and B in elig.index:
                saum[A] += float(elig.loc[B, "aum"]) * float(np.mean(recent))
        saum_past = pd.Series(saum, dtype=float)
        leaders_prev_new = {A: new.get(A, frozenset()) for A in leaders}
        leaders_prev = leaders

    ev = pd.DataFrame(rows)
    ev.to_csv(RESULTS / "pop_events.csv", index=False)

    L = ["# copycat_pop - triagem do pop pos-filing (closes diarios)", "",
         f"- {len(ev)} eventos-ticker | "
         f"{ev['period'].nunique() if len(ev) else 0} trimestres", ""]
    if len(ev):
        # aggregate to quarter means first (events cluster on filing dates)
        for kind, gk in ev.groupby("kind"):
            tag = "TESE (lideres copiados)" if kind == "copied" \
                else "placebo A (sem seguidores)"
            L += [f"## {tag}", ""]
            q_ = gk.groupby("period")
            L.append(f"- day0 (anuncio, nao-tradavel): "
                     f"{gk['day0'].mean():+.4f} "
                     f"(t={nw_tstat(q_['day0'].mean()):+.2f})")
            for h in HORIZONS:
                m = q_[f"ex{h}"].mean()
                L.append(f"- excesso +{h}d: {gk[f'ex{h}'].mean():+.4f} "
                         f"(t={nw_tstat(m):+.2f})")
            for h in (3, 5):
                m = q_[f"pre{h}"].mean()
                L.append(f"- placebo B (janela -5d) +{h}d: "
                         f"{gk[f'pre{h}'].mean():+.4f} "
                         f"(t={nw_tstat(m):+.2f})")
            L.append("")
        cop = ev[ev["kind"] == "copied"].copy()
        if len(cop) > 500:
            L += ["## gradiente pre-registrado: sa_adv "
                  "(shadow AUM do lider / ADV do papel)", ""]
            cop["ter"] = cop.groupby("period")["sa_adv"] \
                .transform(lambda s: pd.qcut(s.rank(method="first"), 3,
                                             labels=False))
            for h in (1, 3, 5):
                by = cop.groupby(["period", "ter"])[f"ex{h}"].mean() \
                    .unstack()
                d = (by[2] - by[0]).dropna()
                L.append(f"- +{h}d tercil alto - baixo: {d.mean():+.4f} "
                         f"(t={nw_tstat(d):+.2f}) | "
                         f"terciles: {by[0].mean():+.4f} / "
                         f"{by[1].mean():+.4f} / {by[2].mean():+.4f}")
    (RESULTS / "POP_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    main(**vars(ap.parse_args()))
