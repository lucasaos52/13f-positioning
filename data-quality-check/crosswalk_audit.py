"""Crosswalk audit: how much damage do CUSIP reassignments and ticker
recycling/mismatch actually do to the factor layer?

    python run_audit.py

TEST A - CUSIP REASSIGNMENT (the blind spot): same issuer stem (cusip6),
instrument A dies exactly when instrument B is born (gap <= 2 quarters),
both with real holder bases. At the switch quarter every holder of A
looks like an EXIT and every holder of B like an ENTRY - fake flow that
contaminates exit_rate, dbreadth, births/deaths. Output: number of
events, holder-slots and dollars involved, and the contamination RATE
against the true total exit flow (measured on sampled quarters).

TEST B - TICKER RECYCLING / NAME-MATCH ERRORS: mapped tickers whose
Yahoo price history starts materially AFTER the instrument first appears
in filings. Two readings: harmless IPO-timing (instrument is young too)
vs SUSPECT (old instrument mapped to a young ticker = the old company's
holdings priced with the new company's prices in overlapping windows).
The px>=1-at-decision filter excludes NaN windows, so the dangerous set
is only where BOTH have data - measured here directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
for sub in ("", "general_plan"):
    sys.path.insert(0, str(HERE.parent / sub))

import panel as pn                                  # noqa: E402
from run_all import load_market, log                # noqa: E402

RESULTS = HERE / "results"
GAP_MAX = 2          # quarters between death of A and birth of B
MIN_HOLDERS = 5


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    cmap, mdta = load_market()
    dates = mdta.prices.index

    qs = [q for q in pn.quarters()
          if pd.Timestamp("2013-06-30") <= q <= dates[-1]]
    qidx = {q: i for i, q in enumerate(qs)}
    log(f"{len(qs)} quarters")

    # ---- instrument life table ---------------------------------------- #
    rows = {}
    holders_prev = None
    exit_flow_samples = []
    for i, q in enumerate(qs):
        try:
            d = pn._load_quarter(str(q)[:10])
        except Exception:
            continue
        g = d.groupby("instrument_id")
        agg = pd.DataFrame({
            "hold": g["filer_id"].nunique(),
            "val": g["value_usd"].sum(),
            "c6": g["cusip6"].first()})
        for j, r in agg.iterrows():
            if j not in rows:
                rows[j] = {"first": i, "last": i, "c6": r["c6"],
                           "h_first": int(r["hold"]),
                           "v_first": float(r["val"]),
                           "h_last": int(r["hold"]),
                           "v_last": float(r["val"])}
            else:
                rows[j]["last"] = i
                rows[j]["h_last"] = int(r["hold"])
                rows[j]["v_last"] = float(r["val"])
        # sample the TRUE total exit flow every 8 quarters for the base rate
        hol = g["filer_id"].agg(set)
        if holders_prev is not None and i % 8 == 4:
            total_exits = 0
            total_val = 0.0
            common_ids = holders_prev.index
            for j in common_ids:
                cur_set = hol.get(j)
                if cur_set is None:
                    total_exits += len(holders_prev[j])
                else:
                    total_exits += len(holders_prev[j] - cur_set)
            exit_flow_samples.append({"period": q, "exits": total_exits})
        holders_prev = hol
        if i % 10 == 0:
            log(f"{q.date()} vida: {len(rows)} instrumentos")

    life = pd.DataFrame(rows).T
    life.index.name = "instrument_id"
    log(f"vida construida: {len(life)} instrumentos")

    # ---- TEST A: reassignment pairs ----------------------------------- #
    ev = []
    for c6, g in life.groupby("c6"):
        if len(g) < 2:
            continue
        g = g.sort_values("first")
        for a in range(len(g)):
            for b in range(len(g)):
                if a == b:
                    continue
                A, B = g.iloc[a], g.iloc[b]
                gap = B["first"] - A["last"]
                if 0 <= gap <= GAP_MAX \
                        and A["h_last"] >= MIN_HOLDERS \
                        and B["h_first"] >= MIN_HOLDERS \
                        and A["last"] < len(qs) - 1 \
                        and B["first"] > 0:
                    ev.append({
                        "c6": c6,
                        "old": A.name, "new": B.name,
                        "switch_q": str(qs[A["last"]].date()),
                        "gap": int(gap),
                        "holders_old": int(A["h_last"]),
                        "holders_new": int(B["h_first"]),
                        "value_old_usd": float(A["v_last"]),
                        "tk_old": cmap.get(A.name, ""),
                        "tk_new": cmap.get(B.name, "")})
    eva = pd.DataFrame(ev).drop_duplicates(["old", "new"])
    eva.to_csv(RESULTS / "reassignment_events.csv", index=False)

    # ---- TEST B: ticker start-date mismatch --------------------------- #
    first_px = {}
    for t in mdta.prices_raw.columns:
        fv = mdta.prices_raw[t].first_valid_index()
        if fv is not None:
            first_px[t] = fv
    sus = []
    for j, t in cmap.items():
        if j not in life.index or t not in first_px:
            continue
        inst_first = qs[int(life.loc[j, "first"])]
        px_first = first_px[t]
        lag_days = (px_first - inst_first).days
        if lag_days > 100:
            sus.append({
                "instrument_id": j, "ticker": t,
                "inst_first_q": str(inst_first.date()),
                "px_first": str(px_first.date()),
                "lag_days": int(lag_days),
                "v_last": float(life.loc[j, "v_last"]),
                "h_last": int(life.loc[j, "h_last"])})
    susd = pd.DataFrame(sus).sort_values("lag_days", ascending=False)
    susd.to_csv(RESULTS / "ticker_start_mismatch.csv", index=False)

    # ---- report -------------------------------------------------------- #
    n_q = len(qs) - 1
    exits_per_q = (np.mean([e["exits"] for e in exit_flow_samples])
                   if exit_flow_samples else np.nan)
    L = ["# Crosswalk audit - CUSIP reassignment e ticker recycling", "",
         f"- {len(life)} instrumentos, {len(qs)} trimestres", "",
         "## TESTE A - reassignment de CUSIP (exodo/nascimento falsos)", ""]
    if len(eva):
        fake_slots = eva["holders_old"].sum()
        per_q = fake_slots / n_q
        L += [f"- eventos detectados (mesmo cusip6, morte->nascimento, "
              f"gap<={GAP_MAX} tri, >= {MIN_HOLDERS} holders): "
              f"**{len(eva)}** em {n_q} trimestres "
              f"(~{len(eva) / (n_q / 4):.1f}/ano)",
              f"- holder-slots envolvidos (saidas FALSAS): "
              f"{fake_slots:,} total = ~{per_q:,.0f}/tri",
              f"- fluxo VERDADEIRO de saidas (amostrado): "
              f"~{exits_per_q:,.0f} saidas/tri",
              f"- **taxa de contaminacao das saidas: "
              f"{per_q / exits_per_q:.2%}**",
              f"- valor mediano por evento: "
              f"${eva['value_old_usd'].median() / 1e6:,.0f}M; maiores:",
              eva.nlargest(8, "value_old_usd")[
                  ["c6", "old", "new", "switch_q", "holders_old",
                   "value_old_usd", "tk_old", "tk_new"]]
              .assign(value_old_usd=lambda d:
                      (d["value_old_usd"] / 1e9).round(2))
              .rename(columns={"value_old_usd": "val_bi"})
              .to_markdown(index=False), ""]
    else:
        L.append("- NENHUM evento detectado")
    L += ["## TESTE B - ticker com historico Yahoo comecando DEPOIS do "
          "instrumento (suspeitos de recycling/mismatch)", ""]
    if len(susd):
        big_sus = susd[susd["v_last"] >= 100e6]
        L += [f"- suspeitos (lag > 100 dias): {len(susd)} de "
              f"{len(cmap)} mapeados ({len(susd) / len(cmap):.1%}); com "
              f"valor >= $100M: {len(big_sus)}",
              f"- NOTA: janelas sem preco sao excluidas pelo filtro "
              f"px>=1 na decisao - o dano real e so quando o instrumento "
              f"VELHO e negociado com precos do ticker NOVO; casos: ",
              big_sus.head(10)[["instrument_id", "ticker", "inst_first_q",
                                "px_first", "lag_days", "h_last"]]
              .to_markdown(index=False)]
    else:
        L.append("- nenhum suspeito")
    (RESULTS / "AUDIT_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
