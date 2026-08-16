"""Crosswalk fix, fast path (deadline mode): hand-curated CUSIP->ticker
map for the top ~230 unmapped instruments by value (~65% of the $8.5T
non-ETF hole), merge into cm_map_wide.csv (with v1 backup), fetch Yahoo
prices ONLY for genuinely new tickers, and STITCH the MarketData caches
by hand (a naive MarketData call with the expanded universe would
cache-miss and refetch all ~4k tickers - hours we don't have).

    python fix_crosswalk_top.py

Every mapping below was read off the EDGAR issuer name by a human who
knows the companies; BBG-id rows are alternate instrument_ids of
already-mapped companies (consolidation: they map to tickers already in
the price panel, zero fetch cost). Renamed companies map to the CURRENT
ticker (Yahoo reindexes history): Anthem->ELV, Kellogg->K,
AmerisourceBergen->COR, Cabot->CTRA, Chesapeake->EXE, Raytheon->RTX.
Untradable/ambiguous rows (Hershey class B, Liberty tracking stocks,
MultiPlan) are deliberately SKIPPED - fail closed.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "data"
FD = ROOT / "factors" / "data"

HAND_MAP = {
    # ---- top 60 by value ------------------------------------------------
    "532457108": "LLY", "02079K107": "GOOG", "46625H100": "JPM",
    "084670702": "BRK-B", "91324P102": "UNH", "30231G102": "XOM",
    "22160K105": "COST", "060505104": "BAC", "742718109": "PG",
    "002824100": "ABT", "17275R102": "CSCO", "718172109": "PM",
    "580135101": "MCD", "874039100": "TSM", "459200101": "IBM",
    "084670108": "BRK-A", "882508104": "TXN", "038222105": "AMAT",
    "75513E101": "RTX", "254687106": "DIS", "BBG000BLZRJ2": "MS",
    "438516106": "HON", "BBG001S5N8V8": "AAPL", "907818108": "UNP",
    "BBG001S5TZJ6": "NVDA", "615369105": "MCO", "808513105": "SCHW",
    "BBG001S5TD05": "MSFT", "09290D101": "BLK", "548661107": "LOW",
    "053015103": "ADP", "040413205": "ANET", "512807306": "LRCX",
    "45866F104": "ICE", "14040H105": "COF", "94106L109": "WM",
    "571748102": "MMC", "03027X100": "AMT", "82509L107": "SHOP",
    "036752103": "ELV", "G0403H108": "AON", "11271J107": "BN",
    "BBG000BPH459": "MSFT", "884903808": "TRI", "21037T109": "CEG",
    "452308109": "ITW", "22788C105": "CRWD", "609207105": "MDLZ",
    "780087102": "RY", "BBG001S5PQL7": "AMZN", "BBG000BBJQV0": "NVDA",
    "127387108": "CDNS", "363576109": "AJG", "26875P101": "EOG",
    "03769M106": "APO", "291011104": "EMR", "BBG000B9XRY4": "AAPL",
    "88579Y101": "MMM", "70450Y103": "PYPL", "G3643J108": "FLUT",
    # ---- rows 61-250 ----------------------------------------------------
    "67103H107": "ORLY", "V7780T103": "RCL", "693475105": "PNC",
    "674599105": "OXY", "009158106": "APD", "74762E102": "PWR",
    "H42097107": "UBS", "253868103": "DLR", "N07059210": "ASML",
    "03073E105": "COR", "43300A203": "HLT", "902973304": "USB",
    "828806109": "SPG", "891160509": "TD", "806857108": "SLB",
    "136385101": "CNQ", "285512109": "EA", "BBG001S5STL8": "LLY",
    "BBG009S39JY5": "GOOGL", "G51502105": "JCI", "136375102": "CNI",
    "075887109": "BDX", "37045V100": "GM", "770700102": "HOOD",
    "064058100": "BK", "G6683N103": "NU", "571903202": "MAR",
    "BBG000BVPV84": "AMZN", "760759100": "RSG", "025537101": "AEP",
    "816851109": "SRE", "81141R100": "SE", "22822V101": "CCI",
    "874054109": "TTWO", "45168D104": "IDXX", "BBG001SQCQC5": "META",
    "56585A102": "MPC", "89832Q109": "TFC", "026874784": "AIG",
    "03076C106": "AMP", "BBG009S3NB21": "GOOG", "01609W102": "BABA",
    "36266G107": "GEHC", "594972408": "MSTR", "G87052109": "TEL",
    "384802104": "GWW", "925652109": "VICI", "69331C108": "PCG",
    "G7997R103": "STX", "BBG009S39JX6": "GOOGL", "744573106": "PEG",
    "609839105": "MPWR", "31620M106": "FIS", "42809H107": "HES",
    "934423104": "WBD", "063671101": "BMO", "345370860": "F",
    "BBG000BFYCD5": "CNA", "46266C105": "IQV", "87612G101": "TRGP",
    "922475108": "VEEV", "BBG00KHY5SY8": "AVGO", "192446102": "CTSH",
    "BBG001S90346": "BRK-B", "G0450A105": "ACGL", "573284106": "MLM",
    "416515104": "HIG", "929160109": "VMC", "962879102": "WPM",
    "064149107": "BNS", "538034109": "LYV", "BBG001SQKGD7": "TSLA",
    "049468101": "TEAM", "929740108": "WAB", "21871X109": "CRBG",
    "BBG000MM2P62": "META", "370334104": "GIS", "053484101": "AVB",
    "BBG001S8CRC3": "JPM", "46284V101": "IRM", "744320102": "PRU",
    "16119P108": "CHTR", "80004C200": "SNDK", "136069101": "CM",
    "06849F108": "B", "37940X102": "GPN", "679580100": "ODFL",
    "857477103": "STT", "BBG00KHY5S69": "AVGO", "29476L107": "EQR",
    "910047109": "UAL", "88262P102": "TPL", "50212V100": "LPLA",
    "11133T103": "BR", "45841N107": "IBKR", "BBG001SRCFY3": "V",
    "881624209": "TEVA", "H2906T109": "GRMN", "030420103": "AWK",
    "459506101": "IFF", "G96629103": "WTW", "254709108": "DFS",
    "G0593M107": "AZN", "56501R106": "MFC", "40434L105": "HPQ",
    "487836108": "K", "76131D103": "QSR", "256677105": "DG",
    "281020107": "EIX", "969904101": "WSM", "55261F104": "MTB",
    "G8473T100": "STE", "745867101": "PHM", "518439104": "EL",
    "693506107": "PPG", "03662Q105": "ANSS", "351858105": "FNV",
    "BBG001S6P675": "MU", "165167735": "EXE", "BBG019PD35Z0": "NEE",
    "457152106": "INGM", "844741108": "LUV", "12503M108": "CBOE",
    "754730109": "RJF", "955306105": "WST", "174610105": "CFG",
    "74251V102": "PFG", "88023U101": "TPX", "74144T108": "TROW",
    "30040W108": "ES", "199908104": "FIX", "084423102": "WRB",
    "N00985106": "AER", "19247G107": "COHR", "BBG000F1ZSQ2": "MA",
    "983793100": "XPO", "36168Q104": "GFL", "29273V100": "ET",
    "780259305": "SHEL", "BBG001S9KRQ7": "COST", "172062101": "CINF",
    "59522J103": "MAA", "D18190898": "DB", "H11356104": "BG",
    "695156109": "PKG", "293792107": "EPD", "422806208": "HEI",
    "BBG001SCNW31": "AZN", "M2682V108": "CYBR", "015271109": "ARE",
    "BBG000DWG505": "BRK-B", "297178105": "ESS", "BBG001S5SHQ9": "JNJ",
    "98980L101": "ZM", "25754A201": "DPZ", "BBG000PSKYX7": "V",
    "00827B106": "AFRM", "55024U109": "LITE", "436440101": "HOLX",
    "BBG001S5NNL6": "AMGN", "31946M103": "FCNCA", "78467J100": "SSNC",
    "N53745100": "LYB", "302130109": "EXPD", "BBG000N9MNX3": "TSLA",
    "127097103": "CTRA", "113004105": "BAM", "216648501": "COO",
    "BBG001SKNNS6": "MA", "N3168P101": "FER", "BBG000DMBXR2": "JPM",
    "BBG001S69V32": "XOM", "BBG001S5SLM4": "KLAC", "147528103": "CASY",
    "912008109": "USFD", "35909D109": "FYBR", "09581B103": "OWL",
    "65249B109": "NWSA", "665859104": "NTRS",
}


def main() -> None:
    cmap = pd.read_csv(NB / "cm_map_wide.csv", dtype=str) \
        .set_index("instrument_id")["ticker"]
    backup = NB / "cm_map_wide_v1.csv"
    if not backup.exists():
        shutil.copy(NB / "cm_map_wide.csv", backup)
    add = {k: v for k, v in HAND_MAP.items() if k not in cmap.index}
    new_map = pd.concat([cmap, pd.Series(add, name="ticker")])
    new_map.index.name = "instrument_id"
    new_map.rename("ticker").to_csv(NB / "cm_map_wide.csv")
    print(f"map: {len(cmap)} -> {len(new_map)} (+{len(add)})")

    new_tk = sorted(set(HAND_MAP.values()) - set(cmap.unique()))
    print(f"tickers to fetch ({len(new_tk)}): {new_tk}")

    import yfinance as yf
    adj = yf.download(new_tk, start="2012-06-01", auto_adjust=True,
                      progress=False)["Close"]
    raw = yf.download(new_tk, start="2012-06-01", auto_adjust=False,
                      progress=False)
    rawc, vol = raw["Close"], raw["Volume"]
    got = [t for t in new_tk if t in adj.columns
           and adj[t].notna().sum() > 100]
    print(f"fetched with data: {len(got)}/{len(new_tk)}")

    # stitch caches: old panel + new columns, under the NEW count name
    for kind, newdf in [("prices", adj), ("prices_raw", rawc),
                        ("volume", vol)]:
        old_files = sorted(FD.glob(f"{kind}_3927tk_*.csv"))
        old = pd.read_csv(old_files[-1], index_col=0, parse_dates=True)
        merged = old.join(newdf[got].reindex(old.index), how="left")
        n = merged.shape[1]
        suffix = old_files[-1].name.split("tk_")[1]
        out = FD / f"{kind}_{n}tk_{suffix}"
        merged.to_csv(out)
        print(f"{out.name}: {old.shape[1]} -> {n} tickers")


if __name__ == "__main__":
    main()
