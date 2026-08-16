"""Synthetic EDGAR fixtures and a matching market panel.

Purpose, stated plainly: this module exists so that the pipeline can be run,
tested and demonstrated end-to-end without network access, and so that the
parsing and point-in-time layers can be validated against data whose ground
truth is known. It is **not** a source of evidence about the factor. Any
performance number produced from simulated data is a statement about the
simulator, not about markets, and is labelled as such everywhere it appears.

What it does provide that real data cannot: a known answer. The simulator plants
a specific mechanism - correlated institutional demand causes temporary price
pressure that partially reverses - and the backtest is required to recover it.
If the pipeline cannot find a signal that was deliberately planted, the
pipeline is broken. That is a genuine test, and it is the reason the generator
writes real EDGAR bytes rather than tidy dataframes: the SGML envelope, the
namespaced XML, the thousands/dollars unit change, the late filings, the
restatements and the confidential-treatment amendments are all reproduced, so
the ingestion code is exercised rather than bypassed.

Deliberate imperfections planted in the fixtures, each mirroring a real EDGAR
pathology and each with a test that asserts the pipeline survives it:

* a slice of CUSIPs with the check digit stripped or leading zero eaten;
* pre-2023 filings in thousands, post-cutover in whole dollars, plus a few
  non-compliant stragglers on the wrong side of the line;
* option overlays (``putCall``) and debt lines (``PRN``) mixed into the table;
* 13F-NT notices and combination reports that double-report a manager;
* a fat right tail of filing lags beyond the 45-day deadline;
* restatement and additive amendments arriving up to a year late.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..curate.identifiers import cusip_check_digit
from ..ingest.client import EDGAR_BASE, EDGAR_DATA

log = logging.getLogger(__name__)


@dataclass
class SimSpec:
    n_stocks: int = 300
    n_managers: int = 110
    start: str = "2015-01-01"
    end: str = "2024-12-31"
    n_style_groups: int = 6
    seed: int = 20240614

    # Mechanism strengths (in daily return units).
    pressure_impact: float = 0.055  # contemporaneous push per unit crowded demand
    pressure_reversal: float = 0.62  # fraction of the push that decays back
    reversal_halflife_d: float = 170.0
    momentum_carry: float = 0.045  # genuine persistent-demand component

    # EDGAR pathology rates.
    p_late_filing: float = 0.16
    p_amendment: float = 0.07
    p_confidential: float = 0.02
    p_bad_cusip: float = 0.03
    p_notice: float = 0.05
    p_unit_noncompliant: float = 0.02
    frac_in_families: float = 0.20  # managers that file as part of a parent/child group


def _mk_cusip(rng: np.random.Generator, i: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    body = f"{i:06d}"[-6:] + "".join(rng.choice(list(alphabet), 2))
    return body + cusip_check_digit(body)


# --------------------------------------------------------------------------- #
class Simulator:
    def __init__(self, spec: SimSpec | None = None) -> None:
        self.spec = spec or SimSpec()
        self.rng = np.random.default_rng(self.spec.seed)

    # ------------------------------------------------------------------ #
    def build_securities(self) -> pd.DataFrame:
        s, rng = self.spec, self.rng
        n = s.n_stocks
        # Heavy-tailed size distribution: a handful of megacaps, a long tail of
        # small caps, which is what makes the liquidity weighting bite.
        log_cap = rng.normal(21.5, 1.9, n)
        cap0 = np.exp(log_cap)
        price0 = np.exp(rng.normal(3.4, 0.7, n)).clip(3, 900)
        turnover_ann = np.exp(rng.normal(0.25, 0.55, n)).clip(0.15, 12.0)
        return pd.DataFrame(
            {
                "instrument_id": [f"SEC{i:04d}" for i in range(n)],
                "cusip": [_mk_cusip(rng, i) for i in range(n)],
                "issuer": [f"SYNTHETIC ISSUER {i:04d} INC" for i in range(n)],
                "title_of_class": "COM",
                "price0": price0,
                "mktcap0": cap0,
                "shares_out": cap0 / price0,
                "turnover_ann": turnover_ann,
                "beta": rng.normal(1.0, 0.35, n).clip(0.2, 2.2),
                "idio_vol": np.exp(rng.normal(-4.05, 0.4, n)).clip(0.004, 0.09),
                "style": rng.integers(0, s.n_style_groups, n),
            }
        )

    def build_managers(self) -> pd.DataFrame:
        s, rng = self.spec, self.rng
        m = s.n_managers
        book = np.exp(rng.normal(21.0, 1.6, m)).clip(1.5e8, 4e11)
        return pd.DataFrame(
            {
                "cik": 1_000_000 + np.arange(m) * 7 + rng.integers(0, 5, m),
                "name": [f"SYNTHETIC ADVISORS {i:03d} LP" for i in range(m)],
                "book0": book,
                "n_pos": rng.integers(12, 140, m),
                "style": rng.integers(0, s.n_style_groups, m),
                # Crowd followers trade with their style group; independents do not.
                "herding": rng.beta(2.2, 2.0, m),
                "turnover_q": rng.gamma(2.0, 0.055, m).clip(0.01, 0.55),
                "smallcap_tilt": rng.beta(2.0, 3.0, m),
            }
        )

    # ------------------------------------------------------------------ #
    def build_holdings(self, secs: pd.DataFrame, mgrs: pd.DataFrame, quarters: pd.PeriodIndex) -> pd.DataFrame:
        """Manager-quarter-stock share positions with persistent style tilts."""
        rng = self.rng
        rows = []
        cap_rank = secs["mktcap0"].rank(pct=True).to_numpy()

        # One shared demand path per style group per quarter, so that managers
        # in the same group crowd into the same names at the same time.
        self._style_shocks = {
            g: rng.normal(0, 0.09, (len(quarters), len(secs)))
            for g in range(self.spec.n_style_groups)
        }

        for mi, mgr in mgrs.iterrows():
            # Preference: own style group, tilted toward small caps by taste.
            pref = np.where(secs["style"].to_numpy() == mgr["style"], 2.4, 1.0)
            pref = pref * np.exp(-mgr["smallcap_tilt"] * 2.5 * cap_rank) * np.exp(
                rng.normal(0, 0.7, len(secs))
            )
            pref = pref / pref.sum()
            n_pos = min(int(mgr["n_pos"]), len(secs))
            picks = rng.choice(len(secs), size=n_pos, replace=False, p=pref)

            w = rng.dirichlet(np.full(len(picks), 0.85))
            book = mgr["book0"]
            # Demand shocks are autocorrelated across quarters. This is the
            # mechanism the factor is supposed to detect: Sias-style persistent
            # institutional demand, where this quarter's accumulation is the
            # first leg of a multi-quarter reallocation rather than a one-off.
            # Without it there is no predictable component at all and the
            # backtest can only ever recover noise.
            rho = 0.35 + 0.35 * mgr["herding"]
            shock = np.zeros(len(picks))
            style_pull = self._style_shocks.get(int(mgr["style"]))
            for qi, q in enumerate(quarters):
                drift = np.exp(rng.normal(0.004, 0.06))
                book *= drift
                eps = rng.normal(0, mgr["turnover_q"], len(picks))
                shock = rho * shock + np.sqrt(max(1 - rho**2, 0.05)) * eps
                # Herding: part of the shock is shared with the style group,
                # which is what creates genuine overlap between managers.
                if style_pull is not None:
                    shock = shock + mgr["herding"] * 0.6 * style_pull[qi][picks]
                w = np.abs(w * np.exp(shock))
                w = w / w.sum()
                dollars = book * w
                rows.append(
                    pd.DataFrame(
                        {
                            "mgr_idx": mi,
                            "quarter": q,
                            "sec_idx": picks,
                            "dollars": dollars,
                        }
                    )
                )
        return pd.concat(rows, ignore_index=True)

    # ------------------------------------------------------------------ #
    def build_prices(
        self, secs: pd.DataFrame, holdings: pd.DataFrame, quarters: pd.PeriodIndex
    ) -> pd.DataFrame:
        """Daily panel where crowded demand pushes prices and then partly unwinds."""
        s, rng = self.spec, self.rng
        dates = pd.bdate_range(s.start, s.end)
        n_d, n_s = len(dates), len(secs)

        mkt = rng.normal(0.0003, 0.010, n_d)
        style_f = rng.normal(0, 0.006, (n_d, s.n_style_groups))
        idio = rng.normal(0, 1, (n_d, n_s)) * secs["idio_vol"].to_numpy()
        beta = secs["beta"].to_numpy()
        style_idx = secs["style"].to_numpy()

        base = mkt[:, None] * beta[None, :] + style_f[:, style_idx] + idio

        # Aggregate quarterly demand per stock, in units of quarterly dollar volume.
        dollar_vol_q = (
            secs["mktcap0"].to_numpy() * secs["turnover_ann"].to_numpy() / 4.0
        )
        demand = holdings.groupby(["quarter", "sec_idx"])["dollars"].sum().unstack(fill_value=0.0)
        demand = demand.reindex(columns=range(n_s), fill_value=0.0).sort_index()
        flow = demand.diff().fillna(0.0).to_numpy() / dollar_vol_q[None, :]
        flow = np.clip(flow, -1.5, 1.5)

        # Map each quarter's flow onto its trading days, then let the pressure
        # accumulate over the quarter and decay with a half-life afterwards.
        q_of_day = pd.PeriodIndex(dates, freq="Q")
        pressure = np.zeros((n_d, n_s))
        decay = 0.5 ** (1.0 / s.reversal_halflife_d)
        carry = np.zeros(n_s)
        qpos = {q: i for i, q in enumerate(demand.index)}

        for t in range(n_d):
            qi = qpos.get(q_of_day[t])
            impulse = flow[qi] / 63.0 if qi is not None else np.zeros(n_s)
            push = s.pressure_impact * impulse
            base[t] += push + s.momentum_carry * impulse
            carry = carry * decay + push * s.pressure_reversal
            base[t] -= carry * (1.0 - decay)

        prices = secs["price0"].to_numpy()[None, :] * np.exp(np.cumsum(base, axis=0))
        shares_out = secs["shares_out"].to_numpy()[None, :] * np.ones((n_d, 1))

        # Splits: a few names split, which is the trap the share-delta code must survive.
        cum_split = np.ones((n_d, n_s))
        for j in rng.choice(n_s, size=max(2, n_s // 25), replace=False):
            t = int(rng.integers(int(n_d * 0.2), int(n_d * 0.9)))
            k = float(rng.choice([2.0, 3.0, 4.0, 10.0]))
            cum_split[t:, j] *= k
            prices[t:, j] /= k
            shares_out[t:, j] *= k

        adv_shares = (
            secs["mktcap0"].to_numpy() * secs["turnover_ann"].to_numpy() / 252.0
        ) / secs["price0"].to_numpy()
        volume = adv_shares[None, :] * np.exp(rng.normal(0, 0.45, (n_d, n_s))) * cum_split

        panel = pd.DataFrame(
            {
                "instrument_id": np.repeat(secs["instrument_id"].to_numpy(), n_d),
                "date": np.tile(dates.to_numpy(), n_s),
                "price": prices.T.ravel(),
                "volume": volume.T.ravel(),
                "shares_outstanding": shares_out.T.ravel(),
                "cum_split_factor": cum_split.T.ravel(),
            }
        )
        panel["ret"] = panel.groupby("instrument_id")["price"].pct_change()
        return panel

    # ------------------------------------------------------------------ #
    # EDGAR fixture writing
    # ------------------------------------------------------------------ #
    def _filing_lag(self) -> int:
        """Days from period end to acceptance. Right-skewed, deadline-clustered."""
        rng = self.rng
        if rng.random() < self.spec.p_late_filing:
            return int(45 + rng.gamma(2.0, 14.0))
        return int(np.clip(rng.normal(40, 7), 10, 45))

    def write_fixtures(
        self,
        client,
        secs: pd.DataFrame,
        mgrs: pd.DataFrame,
        holdings: pd.DataFrame,
        panel: pd.DataFrame,
    ) -> dict:
        """Seed the client cache with EDGAR-shaped bytes for the whole history."""
        rng = self.rng
        qend_price = (
            panel.assign(q=panel["date"].dt.to_period("Q"))
            .sort_values("date")
            .groupby(["instrument_id", "q"])
            .last()["price"]
        )
        sec_by_idx = secs.reset_index(drop=True)
        manifest_rows: list[dict] = []
        per_cik: dict[int, list[dict]] = {}

        # --- filer families ------------------------------------------------ #
        # Some managers file as a group: a parent files a combination report
        # listing subsidiary CIKs under <otherManagers> and reporting their
        # positions, while the subsidiary either files a 13F-NT notice or - the
        # dangerous case - files its own duplicate holdings table. Both dollars
        # then sit in the record and a naive pipeline counts them twice, which
        # for a crowding factor reads as two managers independently agreeing.
        n_fam = int(len(mgrs) * self.spec.frac_in_families) // 2
        fam_pool = list(rng.permutation(len(mgrs))[: n_fam * 2])
        parent_of: dict[int, int] = {}
        children_of: dict[int, list[int]] = {}
        book_by_mgr = holdings.groupby("mgr_idx")["dollars"].sum()
        for a, b in zip(fam_pool[::2], fam_pool[1::2]):
            # The aggregator is the larger book, as it is in practice.
            a, b = (int(a), int(b))
            if book_by_mgr.get(b, 0.0) > book_by_mgr.get(a, 0.0):
                a, b = b, a
            parent_of[b] = a
            children_of.setdefault(a, []).append(b)
        # A subsidiary that files a notice rather than a duplicate table.
        notice_subsidiary = {c: bool(rng.random() < 0.5) for c in parent_of}

        grouped = holdings.groupby(["mgr_idx", "quarter"])
        for (mi, q), grp in grouped:
            mgr = mgrs.iloc[int(mi)]
            cik = int(mgr["cik"])
            period_end = q.end_time.normalize()
            lag = self._filing_lag()
            accept = period_end + pd.Timedelta(days=lag)
            # Filers submit during the ET business day. EDGAR stamps
            # acceptanceDateTime in UTC, so the fixture converts rather than
            # writing an ET hour under a Z suffix - otherwise the fixtures would
            # encode the very mistake the parser is meant to survive.
            accept = accept + pd.Timedelta(
                hours=int(rng.integers(9, 18)) + 4, minutes=int(rng.integers(0, 60))
            )

            seq = len(per_cik.get(cik, [])) + 1
            accession = f"{cik:010d}-{accept.year % 100:02d}-{seq:06d}"

            kids = children_of.get(int(mi), [])
            other_cik = [int(mgrs.iloc[k]["cik"]) for k in kids]
            is_child = int(mi) in parent_of
            is_notice = (rng.random() < self.spec.p_notice and seq > 2) or (
                is_child and notice_subsidiary[int(mi)]
            )
            confidential = rng.random() < self.spec.p_confidential

            src = grp
            if other_cik:
                # A combination report carries the group's positions, so the
                # subsidiary's dollars appear here as well as in its own filing.
                extra = holdings[
                    holdings["mgr_idx"].isin(kids) & (holdings["quarter"] == q)
                ]
                if len(extra):
                    src = pd.concat([grp, extra], ignore_index=True)

            rows = []
            for r in src.itertuples():
                sec = sec_by_idx.iloc[int(r.sec_idx)]
                px = qend_price.get((sec["instrument_id"], q), sec["price0"])
                shares = max(1.0, r.dollars / max(px, 0.01))
                rows.append(
                    {
                        "issuer": sec["issuer"],
                        "cls": sec["title_of_class"],
                        "cusip": sec["cusip"],
                        "value": r.dollars,
                        "shares": shares,
                        "stype": "SH",
                        "putcall": None,
                    }
                )

            # Contaminate: option overlays and a debt line, as real tables have.
            for _ in range(int(rng.integers(0, 4))):
                sec = sec_by_idx.iloc[int(rng.integers(0, len(sec_by_idx)))]
                rows.append(
                    {
                        "issuer": sec["issuer"],
                        "cls": sec["title_of_class"],
                        "cusip": sec["cusip"],
                        "value": float(rng.uniform(1e6, 5e7)),
                        "shares": float(rng.uniform(1e4, 5e5)),
                        "stype": "SH",
                        "putcall": str(rng.choice(["PUT", "CALL"])),
                    }
                )
            if rng.random() < 0.15:
                sec = sec_by_idx.iloc[int(rng.integers(0, len(sec_by_idx)))]
                rows.append(
                    {
                        "issuer": sec["issuer"] + " 4.25% NOTE 2029",
                        "cls": "NOTE",
                        "cusip": sec["cusip"],
                        "value": float(rng.uniform(1e6, 8e7)),
                        "shares": float(rng.uniform(1e6, 5e7)),
                        "stype": "PRN",
                        "putcall": None,
                    }
                )

            withheld: list[dict] = []
            if confidential and len(rows) > 10:
                k = int(rng.integers(1, 5))
                withheld = rows[:k]
                rows = rows[k:]

            body = self._render_submission(
                cik=cik,
                name=str(mgr["name"]),
                accession=accession,
                period_end=period_end,
                accept=accept,
                rows=[] if is_notice else rows,
                report_type=(
                    "13F NOTICE"
                    if is_notice
                    else ("13F COMBINATION REPORT" if other_cik else "13F HOLDINGS REPORT")
                ),
                confidential=confidential,
                amendment=None,
                other_managers=other_cik,
            )
            url = f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}.txt"
            client.cache_put(url, body)

            rec = {
                "cik": cik,
                "company": str(mgr["name"]),
                "form": "13F-NT" if is_notice else "13F-HR",
                "accession": accession,
                "period": str(period_end.date()),
                "filing_date": str(accept.date()),
                "acceptance_dt": accept.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            }
            per_cik.setdefault(cik, []).append(rec)
            manifest_rows.append(rec)

            # Amendments -------------------------------------------------- #
            wants_amendment = withheld or (rng.random() < self.spec.p_amendment and not is_notice)
            if wants_amendment:
                a_lag = int(rng.integers(60, 400)) if withheld else int(rng.integers(20, 260))
                a_accept = accept + pd.Timedelta(days=a_lag, hours=int(rng.integers(0, 12)))
                a_seq = len(per_cik[cik]) + 1
                a_accession = f"{cik:010d}-{a_accept.year % 100:02d}-{a_seq:06d}"
                if withheld:
                    a_type, a_rows = "NEW HOLDINGS", withheld
                else:
                    a_type = "RESTATEMENT"
                    a_rows = [dict(r) for r in rows]
                    for r in a_rows[: max(1, len(a_rows) // 8)]:
                        r["shares"] *= float(rng.uniform(0.6, 1.5))
                        r["value"] *= float(rng.uniform(0.6, 1.5))
                a_body = self._render_submission(
                    cik=cik,
                    name=str(mgr["name"]),
                    accession=a_accession,
                    period_end=period_end,
                    accept=a_accept,
                    rows=a_rows,
                    report_type="13F HOLDINGS REPORT",
                    confidential=False,
                    amendment=(a_type, 1),
                )
                a_url = f"{EDGAR_BASE}/Archives/edgar/data/{cik}/{a_accession.replace('-', '')}/{a_accession}.txt"
                client.cache_put(a_url, a_body)
                a_rec = {
                    "cik": cik,
                    "company": str(mgr["name"]),
                    "form": "13F-HR/A",
                    "accession": a_accession,
                    "period": str(period_end.date()),
                    "filing_date": str(a_accept.date()),
                    "acceptance_dt": a_accept.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                }
                per_cik[cik].append(a_rec)
                manifest_rows.append(a_rec)

        self._write_indices(client, manifest_rows, per_cik)
        return {"filings": len(manifest_rows), "ciks": len(per_cik)}

    # ------------------------------------------------------------------ #
    def _render_submission(
        self,
        *,
        cik: int,
        name: str,
        accession: str,
        period_end: pd.Timestamp,
        accept: pd.Timestamp,
        rows: list[dict],
        report_type: str,
        confidential: bool,
        amendment: tuple[str, int] | None,
        other_managers: list[int] | None = None,
    ) -> bytes:
        """Emit a real SGML submission with a namespaced XML information table."""
        rng = self.rng
        thousands = accept < pd.Timestamp("2023-01-03")
        if rng.random() < self.spec.p_unit_noncompliant:
            thousands = not thousands
        scale = 1000.0 if thousands else 1.0

        amend_block = ""
        if amendment:
            a_type, a_no = amendment
            amend_block = (
                f"<amendmentNo>{a_no}</amendmentNo>"
                f"<amendmentInfo><amendmentType>{a_type}</amendmentType></amendmentInfo>"
            )

        total_value = sum(r["value"] for r in rows) / scale
        om_block = ""
        if other_managers:
            inner = "".join(
                f"<otherManager><cik>{c:010d}</cik>"
                f"<form13FFileNumber>028-{c % 100000:05d}</form13FFileNumber>"
                f"<name>SYNTHETIC ADVISORS {c % 1000:03d} LP</name></otherManager>"
                for c in other_managers
            )
            om_block = f"<otherManagers>{inner}</otherManagers>"
        cover = f"""<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">
 <headerData><submissionType>{'13F-HR/A' if amendment else ('13F-NT' if not rows else '13F-HR')}</submissionType>
  <filerInfo><periodOfReport>{period_end.strftime('%m-%d-%Y')}</periodOfReport>
   <filer><credentials><cik>{cik:010d}</cik></credentials></filer></filerInfo></headerData>
 <formData>
  <coverPage><reportCalendarOrQuarter>{period_end.strftime('%m-%d-%Y')}</reportCalendarOrQuarter>
   {amend_block}
   <filingManager><name>{name}</name></filingManager>
   <reportType>{report_type}</reportType>
   <isConfidentialOmitted>{'true' if confidential else 'false'}</isConfidentialOmitted>
   {om_block}
  </coverPage>
  <summaryPage><otherIncludedManagersCount>{len(other_managers or [])}</otherIncludedManagersCount>
   <tableEntryTotal>{len(rows)}</tableEntryTotal>
   <tableValueTotal>{total_value:.0f}</tableValueTotal>
   <isConfidentialOmitted>{'true' if confidential else 'false'}</isConfidentialOmitted>
  </summaryPage>
 </formData>
</edgarSubmission>"""

        entries = []
        for r in rows:
            cusip = r["cusip"]
            u = rng.random()
            if u < self.spec.p_bad_cusip:  # the two real corruption modes
                cusip = cusip[:8] if u < self.spec.p_bad_cusip / 2 else cusip.lstrip("0")
            pc = f"<putCall>{r['putcall']}</putCall>" if r["putcall"] else ""
            entries.append(
                f"""  <infoTable>
   <nameOfIssuer>{r['issuer']}</nameOfIssuer>
   <titleOfClass>{r['cls']}</titleOfClass>
   <cusip>{cusip}</cusip>
   <value>{r['value'] / scale:.0f}</value>
   <shrsOrPrnAmt><sshPrnamt>{r['shares']:.0f}</sshPrnamt><sshPrnamtType>{r['stype']}</sshPrnamtType></shrsOrPrnAmt>
   {pc}
   <investmentDiscretion>SOLE</investmentDiscretion>
   <votingAuthority><Sole>{r['shares']:.0f}</Sole><Shared>0</Shared><None>0</None></votingAuthority>
  </infoTable>"""
            )
        table = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">\n'
            + "\n".join(entries)
            + "\n</informationTable>"
        )

        sgml = f"""<SEC-DOCUMENT>{accession}.txt : {accept:%Y%m%d}
<SEC-HEADER>{accession}.hdr.sgml : {accept:%Y%m%d}
ACCEPTANCE-DATETIME:{accept:%Y%m%d%H%M%S}
CONFORMED PERIOD OF REPORT:\t{period_end:%Y%m%d}
FILED AS OF DATE:\t\t{accept:%Y%m%d}
</SEC-HEADER>
<DOCUMENT>
<TYPE>{'13F-HR/A' if amendment else ('13F-NT' if not rows else '13F-HR')}
<SEQUENCE>1
<FILENAME>primary_doc.xml
<TEXT>
{cover}
</TEXT>
</DOCUMENT>
"""
        if rows:
            sgml += f"""<DOCUMENT>
<TYPE>INFORMATION TABLE
<SEQUENCE>2
<FILENAME>infotable.xml
<TEXT>
{table}
</TEXT>
</DOCUMENT>
"""
        sgml += "</SEC-DOCUMENT>\n"
        return sgml.encode("utf-8")

    # ------------------------------------------------------------------ #
    def _write_indices(self, client, manifest_rows: list[dict], per_cik: dict[int, list[dict]]) -> None:
        df = pd.DataFrame(manifest_rows)
        df["filing_q"] = pd.PeriodIndex(pd.to_datetime(df["filing_date"]), freq="Q")

        for q, grp in df.groupby("filing_q"):
            header = (
                "Form Type   Company Name"
                + " " * 50
                + "CIK         Date Filed  File Name\n"
            )
            rule = "-" * 140 + "\n"
            body = []
            for r in grp.itertuples():
                path = f"edgar/data/{r.cik}/{r.accession}.txt"
                body.append(
                    f"{r.form:<12}{r.company[:60]:<62}{r.cik:<12}{r.filing_date:<12}{path}\n"
                )
            content = (
                "Description:           Master Index of EDGAR Dissemination Feed by Form Type\n"
                f"Last Data Received:    {q.end_time:%B %d, %Y}\n\n\n"
                + header
                + rule
                + "".join(body)
            )
            url = f"{EDGAR_BASE}/Archives/edgar/full-index/{q.year}/QTR{q.quarter}/form.idx"
            client.cache_put(url, content.encode("utf-8"))

        for cik, recs in per_cik.items():
            recent = {
                "accessionNumber": [r["accession"] for r in recs],
                "filingDate": [r["filing_date"] for r in recs],
                "reportDate": [r["period"] for r in recs],
                "acceptanceDateTime": [r["acceptance_dt"] for r in recs],
                "form": [r["form"] for r in recs],
                "primaryDocument": ["primary_doc.xml"] * len(recs),
            }
            blob = {"cik": str(cik), "name": recs[0]["company"], "filings": {"recent": recent, "files": []}}
            client.cache_put(f"{EDGAR_DATA}/submissions/CIK{cik:010d}.json", json.dumps(blob).encode())


# --------------------------------------------------------------------------- #
def generate_world(client, spec: SimSpec | None = None) -> dict:
    """Build the whole synthetic world and seed the EDGAR cache."""
    sim = Simulator(spec)
    s = sim.spec
    quarters = pd.period_range(s.start, s.end, freq="Q")

    secs = sim.build_securities()
    mgrs = sim.build_managers()
    holdings = sim.build_holdings(secs, mgrs, quarters)
    panel = sim.build_prices(secs, holdings, quarters)
    stats = sim.write_fixtures(client, secs, mgrs, holdings, panel)

    # The crosswalk a real run would supply from CRSP or a vendor: it is the
    # bridge from the CUSIP a filer typed to the instrument the price panel
    # knows about, and it is dated so that reassignment could be expressed.
    crosswalk = pd.DataFrame(
        {
            "cusip": secs["cusip"],
            "instrument_id": secs["instrument_id"],
            "ticker": secs["instrument_id"],
            "start": "1900-01-01",
            "end": "2999-12-31",
            "sec_type": "common",
        }
    )

    log.info("simulated %d filings from %d filers", stats["filings"], stats["ciks"])
    return {
        "securities": secs,
        "managers": mgrs,
        "panel": panel,
        "crosswalk": crosswalk,
        "quarters": quarters,
        **stats,
    }
