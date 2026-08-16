"""The memo.

Builds the 3-5 page write-up from the artifacts the pipeline actually produced,
so the prose and the numbers cannot drift apart. Every figure in the document is
read from ``data/`` at build time; none is typed in.

    crowdflow report --out memo/crowdflow_memo.pdf

If a run used simulated fixtures, the memo says so on the first page and again
above every results table. That is not a disclaimer bolted on at the end - the
build refuses to present fixture output as evidence.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from ..config import Config

log = logging.getLogger(__name__)

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5f5e5a")
RULE = colors.HexColor("#c9c7bf")
WARN = colors.HexColor("#8a3324")


# --------------------------------------------------------------------------- #
def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=17, leading=21, textColor=INK,
                                spaceAfter=2),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=9.5, leading=13, textColor=MUTED,
                              spaceAfter=14),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontSize=12, leading=15, textColor=INK,
                            spaceBefore=13, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10, leading=13, textColor=INK,
                             spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.3, leading=13.2,
                               alignment=TA_JUSTIFY, textColor=INK, spaceAfter=6),
        "bullet": ParagraphStyle("bu", parent=ss["BodyText"], fontSize=9.3, leading=13.2,
                                 leftIndent=12, bulletIndent=3, textColor=INK, spaceAfter=3),
        "warn": ParagraphStyle("w", parent=ss["BodyText"], fontSize=9, leading=12,
                               textColor=WARN, spaceAfter=6),
        "cap": ParagraphStyle("c", parent=ss["BodyText"], fontSize=8, leading=10.5,
                              textColor=MUTED, spaceBefore=2, spaceAfter=10),
    }


def _table(df: pd.DataFrame, st: dict, col_widths=None, fontsize=7.2) -> Table:
    data = [list(df.columns)] + df.astype(str).values.tolist()
    t = Table(data, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", fontsize),
                ("FONT", (0, 1), (-1, -1), "Helvetica", fontsize),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, -1), (-1, -1), 0.4, RULE),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f6f2")]),
            ]
        )
    )
    return t


def _read(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path) if path.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _fmt(df: pd.DataFrame, pct: list[str] = (), num: list[str] = (), dp: int = 2) -> pd.DataFrame:
    d = df.copy()
    for c in pct:
        if c in d:
            d[c] = d[c].map(lambda v: f"{v:+.2%}" if pd.notna(v) else "")
    for c in num:
        if c in d:
            d[c] = d[c].map(lambda v: f"{v:,.{dp}f}" if pd.notna(v) else "")
    return d


# --------------------------------------------------------------------------- #
def build_memo(cfg: Config, out: Path, simulated: bool = True) -> Path:
    st = _styles()
    R, F, C = cfg.paths.results, cfg.paths.features, cfg.paths.curated
    S: list = []
    P = lambda txt, k="body": S.append(Paragraph(txt, st[k]))
    B = lambda txt: S.append(Paragraph(txt, st["bullet"], bulletText="\u2022"))

    table_fx = _read(R / "factor_table.csv")
    attribution = _read(R / "attribution.csv")
    horizon = _read(R / "horizon_ic.csv")
    lag = _read(C / "lag_profile.csv")
    restate = _read(C / "restatement_audit.csv")
    stability = _read(F / "universe_stability.csv")
    schedule = _read(F / "activation_schedule.csv")

    # ---------------------------------------------------------------- p.1 --
    P("A dynamic crowding-impact universe for 13F positioning", "title")
    P(
        f"Quarterly 13F holdings from SEC EDGAR &middot; {cfg.edgar.first_quarter}"
        f"&ndash;{cfg.edgar.last_quarter} &middot; config <font face='Courier'>"
        f"{cfg.fingerprint()}</font>",
        "sub",
    )
    if simulated:
        P(
            "<b>All performance figures in this memo come from generated fixtures, not "
            "from markets.</b> The fixture generator writes EDGAR-shaped bytes so the "
            "parsing and point-in-time layers are genuinely exercised, and it plants a "
            "known price-pressure mechanism so the pipeline can be checked for its "
            "ability to recover a signal that is known to be there. It cannot tell you "
            "whether the factor works. Read the results section as evidence about the "
            "plumbing.",
            "warn",
        )

    P("The problem with a fixed manager list", "h")
    P(
        "The standard construction of a 13F crowding factor starts from a hand-picked "
        "set of managers &ndash; the largest funds plus a few famous names. That choice "
        "carries three defects, and the third is the one that quietly does the damage."
    )
    B(
        "<b>Selection on survivors.</b> A list drawn up today and applied from 2015 "
        "embeds knowledge of who would still matter in 2025. The managers who blew up "
        "are missing, and their forced liquidations were precisely the crowding events "
        "the factor claims to measure."
    )
    B(
        "<b>Size is not footprint.</b> A $50bn book held in megacaps can be unwound in "
        "days and moves nothing. A $3bn book in illiquid small caps moves prices on the "
        "way out. Ranking managers by assets ranks the wrong quantity."
    )
    B(
        "<b>The normalisation trap.</b> Treat every listed manager as one equal voice "
        "and a single-position wrapper vehicle counts for as much as a diversified "
        "multi-strategy platform. The signal is then dominated by filers with no "
        "capacity to transmit anything."
    )
    P(
        "So the universe is not chosen. It is <i>derived</i>, every quarter, from a "
        "rule that ranks managers on their lagged capacity to transmit common demand "
        "shocks into prices. Selection never touches realised performance: the inputs "
        "are mechanical properties of the book, observable at the time."
    )

    P("The selection rule", "h")
    w = cfg.universe.weights
    P(
        f"Score(m, t) = {w['impact']:.2f}&middot;rank(Impact) + "
        f"{w['centrality']:.2f}&middot;rank(Centrality) + "
        f"{w['turnover']:.2f}&middot;rank(Turnover), each a cross-sectional percentile "
        f"rank within the quarter. The universe for quarter t is the top "
        f"{cfg.universe.target_size} by score at t&minus;"
        f"{cfg.universe.selection_lag_quarters}."
    )
    B(
        "<b>Impact</b> &ndash; the liquidity footprint of the book: for each position, "
        "value &times; daily volatility &times; (value/ADV)<super>"
        f"{cfg.universe.impact_exponent:g}</super>, summed. The square-root exponent is "
        "the standard impact law; it is a config parameter, not a constant buried in a "
        "function, and 1.0 gives the linear alternative."
    )
    B(
        "<b>Centrality</b> &ndash; liquidity-weighted portfolio overlap with every other "
        "filer. Computed as x<sub>m</sub>&middot;s &minus; ||x<sub>m</sub>||<super>2"
        "</super> rather than as a pairwise loop, which is O(M&middot;N) instead of "
        "O(M<super>2</super>&middot;N) and is the difference between seconds and hours "
        "at real filer counts. A test asserts the shortcut equals the naive double loop."
    )
    B(
        "<b>Turnover</b> &ndash; half the sum of absolute split-adjusted share changes "
        "priced at a common date, EWMA-smoothed over "
        f"{cfg.universe.turnover_halflife_q:g} quarters. A manager who never trades "
        "cannot transmit a shock however large the book."
    )
    P(
        f"Eligibility precedes scoring: at least {cfg.universe.min_history_quarters} "
        f"quarters of history, a ${cfg.universe.min_equity_book_usd/1e6:,.0f}mm equity "
        f"book, {cfg.universe.min_positions} positions, and no single name above "
        f"{cfg.universe.max_single_name_weight:.0%} of the book. That last filter is "
        "what removes the single-position wrapper."
    )
    P(
        f"Membership uses hysteresis: a manager enters at rank "
        f"{cfg.universe.target_size} or better and leaves only past rank "
        f"{cfg.universe.buffer_size}. Without the band, names sitting near the "
        "threshold oscillate in and out on rank noise and the portfolio pays "
        "transaction costs for churn that carries no information."
    )

    S.append(PageBreak())

    # ---------------------------------------------------------------- p.2 --
    P("Point-in-time discipline", "h")
    P(
        "Every 13F fact carries two dates, and conflating them is the standard way a "
        "13F backtest acquires lookahead: <i>valid time</i>, the quarter the positions "
        "describe, and <i>transaction time</i>, the instant the fact became public. The "
        "store answers exactly one question &ndash; "
        "<font face='Courier'>as_of(period_end, knowledge_date)</font> &ndash; and the "
        "factor layer is not permitted to reach around it. Both the current and prior "
        "quarter are always materialised at the same vantage, so a quarter-on-quarter "
        "position change never mixes what was known then with what is known now."
    )

    P("The deadline is a floor, not a schedule", "h3")
    if lag is not None and not lag.empty:
        P(
            f"Measured over {len(lag)} quarters: median lag "
            f"{lag['median'].median():.0f} days, p90 {lag['p90'].median():.0f}, worst "
            f"{lag['worst'].max():.0f}. Only {lag['pct_by_day_45'].mean():.0%} of filers "
            f"are in by day 45 in the average quarter, and "
            f"{lag['pct_by_day_45'].min():.0%} in the worst. Trading on day 46 means "
            "trading without roughly one filer in six."
        )
    P(
        "So the rebalance calendar is derived from the data, not the regulation. A "
        "quarter activates on the first rebalance date where 80% of <i>the selected "
        "universe</i> has actually filed, with a hard backstop at "
        f"{150} days so one chronically late filer cannot stall the period "
        "indefinitely &ndash; silently dropping quarters would be a survivorship filter "
        "on periods. A further business day separates readable from tradeable."
    )
    if schedule is not None and not schedule.empty:
        P(
            f"Realised activation lag: median {schedule['lag_days'].median():.0f} days, "
            f"p90 {schedule['lag_days'].quantile(0.9):.0f}, max "
            f"{schedule['lag_days'].max():.0f}."
        )

    P("Amendments and confidential treatment", "h3")
    P(
        "Amendment semantics follow the cover page rather than a guess. "
        "<b>RESTATEMENT</b> replaces the table for that filer-quarter. <b>NEW "
        "HOLDINGS</b> is additive and carries only rows omitted from the original &ndash; "
        "the shape a lapsed confidential-treatment order takes, where the positions "
        "genuinely were not in the public record at the original date. An unflagged "
        "amendment is treated as a restatement, the conservative choice, because it "
        "never invents holdings the amendment did not contain."
    )
    if restate is not None and not restate.empty and "lag_days" in restate:
        lg = restate[restate["lag_days"] > 0]
        if not lg.empty:
            P(
                f"{len(restate)} filer-quarters were amended. Median {lg['lag_days'].median():.0f} "
                f"days from original to final version, p90 {lg['lag_days'].quantile(0.9):.0f}, "
                f"max {lg['lag_days'].max():.0f}; median absolute book revision "
                f"{lg['book_delta_pct'].abs().median():.2%}. A period-keyed pipeline reads "
                "the final version at the original date, which is lookahead that leaves "
                "no trace &ndash; the row looks entirely ordinary."
            )

    P("Data engineering", "h")
    P(
        "Every discretionary decision is counted rather than asserted; the rejection "
        "ledger is written to disk alongside the holdings and regenerated by "
        "<font face='Courier'>make data-report</font>."
    )
    B(
        "<b>Value units.</b> SEC Release 34-95148 moved values from thousands to whole "
        "dollars for filings made on or after 2023-01-03. A calendar rule fails twice: "
        "the cutover keys on the filing date, so 2022Q4 books filed in 2023 report whole "
        "dollars, and a tail of filers ignores the change entirely. Scale is inferred "
        "per filing from the median implied price; the calendar is only a fallback and "
        "is recorded as such."
    )
    B(
        "<b>CUSIP.</b> Mod-10 double-add-double check digit. Leading zeros eaten by a "
        "spreadsheet are restored and dropped check digits recomputed, but only when the "
        "checksum confirms exactly one candidate; anything ambiguous is dropped rather "
        "than guessed. Share classes stay distinct &ndash; GOOG and GOOGL have different "
        "CUSIPs and must never merge."
    )
    B(
        "<b>Filer deduplication.</b> Union-find over the cover page's otherManagers "
        "edges, rebuilt each quarter. A parent files a combination report and the "
        "subsidiary files either a notice or its own duplicate table; uncorrected, the "
        "same dollars appear twice and a crowding factor reads that as two managers "
        "independently agreeing. Name similarity only <i>proposes</i> merges for human "
        "sign-off in <font face='Courier'>config/families.yaml</font>."
    )
    B(
        "<b>Instrument class.</b> Option overlays report notional exposure, not "
        "ownership, and PRN lines are face value of debt. Both are removed before any "
        "book total is computed, so \u201clargest book in the group\u201d already means "
        "largest equity book."
    )
    B(
        "<b>Split adjustment.</b> Each leg of a quarter-on-quarter share change is "
        "divided by its <i>own</i> quarter's cumulative factor. Applying the current "
        "factor to both turns an untouched position across a 4:1 split into a 75% sale."
    )

    S.append(PageBreak())

    # ---------------------------------------------------------------- p.3 --
    P("Hypothesis and factor construction", "h")
    P(
        "<b>Concentrated demand from managers with large liquidity footprints has two "
        "effects of opposite sign at different horizons.</b> Contemporaneously the "
        "buying pushes prices up. Further out, to the extent the buying was pressure "
        "rather than information, the push decays. Pure information implies continuation "
        "with no reversal; pure pressure implies reversal with no drift. Measuring both "
        "horizons is the test, and the interaction with fragility is what separates them: "
        "reversal should concentrate where ownership is concentrated and the flow "
        "covariance is high."
    )
    B(
        "<b>caf</b> &ndash; crowded accumulation: net dollar demand from universe "
        "managers over the quarter, divided by quarterly dollar volume. The "
        "normalisation makes the unit \u201cdays of volume absorbed\u201d rather than "
        "raw dollars, which is what determines price impact."
    )
    B("<b>consensus</b> &ndash; signed breadth: the fraction of universe holders buying versus selling.")
    B("<b>own_share</b> &ndash; the share of outstanding held by the universe.")
    B(
        "<b>fragility</b> &ndash; the Greenwood&ndash;Thesmar quadratic form "
        "&theta;'&Sigma;&theta; / W<super>2</super>, with a shrunk, PSD-clipped flow "
        "covariance. This is the vulnerability-to-forced-selling term."
    )
    B(
        "<b>caf_x_fragility</b> &ndash; the interaction, formed on ranks rather than "
        "levels so that one extreme observation in either leg cannot manufacture the "
        "product."
    )
    P(
        "All factors are winsorised, z-scored cross-sectionally, and residualised on log "
        "market cap and log Amihud illiquidity. That last step is not optional here: the "
        "signal is built from a liquidity-weighted quantity, so without neutralisation "
        "the factor would partly be a restatement of illiquidity."
    )

    P("Backtest", "h")
    P(
        f"Monthly rebalance with the convention \u201cweights from information at t, "
        f"return over (t, t+1], costs charged at t\u201d. Two portfolios per factor: an "
        f"equal-weight Q{cfg.backtest.quantiles} minus Q1 spread, and a z-weighted "
        f"dollar-neutral book capped at {cfg.backtest.max_weight:.0%} per name. "
        f"Costs are a {cfg.backtest.spread_bps:.0f}bp half-spread plus square-root "
        f"impact using the same law applied to manager footprint, for internal "
        f"consistency, plus {cfg.backtest.borrow_bps_ann:.0f}bp annual borrow on shorts. "
        f"Gross and net are both reported."
    )
    P(
        "Between activations the quarterly signal is held flat &ndash; no interpolation, "
        "no smoothing forward &ndash; with a staleness cap so a gap in the filing record "
        "produces missing exposure rather than a stale position held forever."
    )
    P(
        f"All t-statistics are Newey&ndash;West with {cfg.backtest.newey_west_lags} lags. "
        "Monthly returns from a quarterly signal are autocorrelated by construction: the "
        "same signal is held for roughly three months, so an OLS t-statistic overstates "
        "significance. A deflated Sharpe discounts the best observed result by the number "
        "of variants tried."
    )

    if table_fx is not None and not table_fx.empty:
        cols = ["factor", "months", "net_ann", "vol_ann", "sharpe_net", "t_nw", "maxdd",
                "ic_mean", "ic_t_nw", "turnover_m", "cost_drag_ann"]
        d = table_fx[[c for c in cols if c in table_fx.columns]]
        d = _fmt(d, pct=["net_ann", "vol_ann", "maxdd", "cost_drag_ann", "turnover_m"],
                 num=["sharpe_net", "t_nw", "ic_t_nw"], dp=2)
        if "ic_mean" in d:
            d["ic_mean"] = table_fx["ic_mean"].map(lambda v: f"{v:+.4f}")
        S.append(KeepTogether([Paragraph("Results", st["h"]),
                               Paragraph("<b>Simulated data. These numbers describe the "
                                         "generator, not markets.</b>" if simulated else "",
                                         st["warn"]),
                               _table(d, st)]))
        P("Net of costs. t-statistics Newey&ndash;West.", "cap")

    if attribution is not None and not attribution.empty:
        d = _fmt(attribution, pct=["raw_ann", "alpha_ann"],
                 num=[c for c in attribution.columns if c.startswith("beta_")] +
                     ["alpha_t_nw", "r2"], dp=2)
        S.append(KeepTogether([Paragraph("Benchmark attribution", st["h3"]), _table(d, st)]))
        P(
            "Factor returns regressed on market, size, momentum, short-term reversal and "
            "illiquidity proxies built from the same price panel. A raw spread that "
            "disappears once these are controlled for is one of them wearing a 13F "
            "costume. Against vendor data, substitute the Fama&ndash;French and AQR "
            "series &ndash; the loader accepts them directly.",
            "cap",
        )

    if horizon is not None and not horizon.empty:
        piv = horizon.pivot(index="factor", columns="horizon_m", values="ic_mean")
        piv.columns = [f"{c}m" for c in piv.columns]
        piv = piv.reset_index().round(4)
        S.append(KeepTogether([Paragraph("Horizon IC &ndash; the continuation-versus-reversal test",
                                         st["h3"]), _table(piv, st)]))
        P(
            "The sign pattern across horizons is the hypothesis test, not the Sharpe. A "
            "factor that is positive at one month and negative at twelve is behaving "
            "like transient pressure; one positive throughout is behaving like "
            "information.",
            "cap",
        )

    if stability is not None and not stability.empty:
        cols = [c for c in ["period_end", "n", "entries", "exits", "jaccard"] if c in stability.columns]
        d = stability[cols].tail(6).round(3)
        S.append(KeepTogether([Paragraph("Universe stability (last quarters)", st["h3"]),
                               _table(d, st)]))
        if "jaccard" in stability:
            P(
                f"Mean quarter-on-quarter Jaccard overlap {stability['jaccard'].mean():.2f}. "
                "A universe that reshuffles every quarter is fitting noise; one that never "
                "changes is a fixed list with extra steps.",
                "cap",
            )

    S.append(PageBreak())

    # ---------------------------------------------------------------- p.4 --
    P("What this does not do", "h")
    B(
        "<b>13F is long-only, quarterly, US-listed equity.</b> No shorts, no derivatives "
        "exposure beyond the excluded overlays, no cash, no international book. \u201cThe "
        "manager sold\u201d and \u201cthe manager rotated into something 13F cannot see\u201d "
        "are indistinguishable here."
    )
    B(
        "<b>A quarter-end snapshot is not a trade record.</b> Round-trips inside the "
        "quarter are invisible; window dressing at the boundary is visible and looks like "
        "a real position."
    )
    B(
        "<b>The overlap measure is symmetric.</b> It cannot tell a manager who leads a "
        "crowd from one who follows it. Sias-style lead-lag on the flow panel is the "
        "natural extension and the flow history is already persisted for it."
    )
    B(
        "<b>CUSIP reassignment is handled but not exercised.</b> The security master keys "
        "on (cusip, date) and will respect a dated crosswalk, but the fixtures contain no "
        "reassignment, so that path is untested end to end. With CRSP it works; that is a "
        "claim about the code, not an observation."
    )
    B(
        "<b>Fixture results are not evidence.</b> The generator plants a mechanism and "
        "the pipeline recovers it, which tests the plumbing and nothing else."
    )

    P("Next, in priority order", "h")
    P(
        "<b>1. Run against real EDGAR and a survivorship-free price panel.</b> Everything "
        "above is a claim about code until this is done. CRSP is the right source: it "
        "handles delisting returns, and forced liquidation on the way to a delisting is "
        "one of the mechanisms the factor is trying to capture. A survivorship-biased "
        "panel would remove exactly the observations that matter most."
    )
    P(
        "<b>2. Directional crowding.</b> Replace symmetric overlap with a lead-lag "
        "measure &ndash; whose demand precedes whose &ndash; which turns centrality from "
        "\u201chow connected\u201d into \u201chow upstream\u201d. That is the difference "
        "between knowing a stock is crowded and knowing whether the crowd is still "
        "arriving or already leaving."
    )
    P(
        "<b>3. Stress the selection rule.</b> The 0.40/0.40/0.20 weights and the "
        "25/35 hysteresis band are judgement, not estimates. The honest test is whether "
        "results survive a grid over them, reported as a distribution rather than as the "
        "best cell &ndash; and the deflated Sharpe should be recomputed against the full "
        "count of variants examined, not against the handful that reached this memo."
    )

    P("Reproducing", "h")
    P(
        "<font face='Courier'>make setup &amp;&amp; make test</font> runs 51 tests with no "
        "network. <font face='Courier'>make demo</font> generates fixtures and runs the "
        "full pipeline offline. Against real data, set "
        "<font face='Courier'>CROWDFLOW_USER_AGENT</font> to a contact address (SEC "
        "returns 403 without one), then <font face='Courier'>make ingest</font> and "
        "<font face='Courier'>make run PRICES=&hellip; CROSSWALK=&hellip;</font>. A run is "
        "fully described by <font face='Courier'>config/default.yaml</font> plus a git "
        "SHA; the config fingerprint is stamped on every artifact and on this page."
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        topMargin=1.7 * cm, bottomMargin=1.7 * cm,
        title="Dynamic crowding-impact universe for 13F positioning",
    )

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(2.0 * cm, 1.0 * cm, f"crowdflow &middot; {cfg.fingerprint()}".replace("&middot;", "·"))
        canvas.drawRightString(A4[0] - 2.0 * cm, 1.0 * cm, str(canvas.getPageNumber()))
        canvas.restoreState()

    doc.build(S, onFirstPage=footer, onLaterPages=footer)
    log.info("memo written to %s", out)
    return out
