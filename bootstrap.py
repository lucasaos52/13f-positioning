"""One-command environment and data bootstrap.

    python bootstrap.py            # run every missing stage, in order
    python bootstrap.py --status   # show what exists / what is missing
    python bootstrap.py --stage N  # run one stage explicitly

Idempotent: each stage checks its own output and is skipped when the
output already exists. A fresh clone reaches a runnable state with:

    1. deps      pip install -r requirements.txt  (+ crowdflow package)
    2. edgar     SEC bulk 13F datasets via the crowdflow CLI
                 (needs CROWDFLOW_USER_AGENT="Name email@domain.com")
    3. quarters  point-in-time quarterly store (factors/general_plan/
                 prep_quarters.py) built from the EDGAR lake
    4. crosswalk CUSIP -> current-ticker map (notebooks/
                 prep_universe_wide.py)
    5. prices    Yahoo price/volume panels (auto-fetched on first use
                 by factors/market_data.py; this stage just warms it)

Then run the experiment pipeline:  python run_experiments.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def _run(cmd, cwd=ROOT):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    subprocess.run([str(c) for c in cmd], cwd=str(cwd), check=True)


def _nonempty(p: Path, pattern: str = "*") -> bool:
    return p.exists() and any(p.glob(pattern))


STAGES = []


def stage(n, name, check, run):
    STAGES.append((n, name, check, run))


stage(1, "python dependencies",
      lambda: _has_deps(),
      lambda: (_run([PY, "-m", "pip", "install", "-r",
                     "requirements.txt"]),
               _run([PY, "-m", "pip", "install", "-e", "crowdflow"])))


def _has_deps() -> bool:
    try:
        import pandas, sklearn, matplotlib, yfinance  # noqa: F401
        return True
    except Exception:
        return False


stage(2, "EDGAR data lake (crowdflow datasets)",
      lambda: _nonempty(ROOT / "crowdflow" / "data"),
      lambda: _check_ua() or _run(
          [PY, "-c",
           "from crowdflow.cli import main; import sys;"
           "sys.argv=['crowdflow','datasets','--cross-validate','25',"
           "'-v']; main()"], cwd=ROOT / "crowdflow"))


def _check_ua():
    if not os.environ.get("CROWDFLOW_USER_AGENT"):
        raise SystemExit(
            'set CROWDFLOW_USER_AGENT="Name email@domain.com" first '
            "(SEC requires a contact address; no credentials needed)")


stage(3, "quarterly point-in-time store",
      lambda: _nonempty(ROOT / "factors/general_plan/data/quarters",
                        "q_*.parquet"),
      lambda: _run([PY, "factors/general_plan/prep_quarters.py"]))

stage(4, "CUSIP->ticker crosswalk (+hand-curated corrections)",
      lambda: (ROOT / "notebooks/data/cm_map_wide.csv").exists(),
      lambda: (_run([PY, "notebooks/prep_universe_wide.py"]),
               _run([PY, "notebooks/apply_handmap.py"])))

stage(5, "price panels (Yahoo, auto-cached)",
      lambda: _nonempty(ROOT / "factors" / "data", "prices_*"),
      lambda: _run([PY, "-c",
                    "import sys; sys.path.insert(0,"
                    "'factors/general_plan');"
                    "from run_all import load_market; load_market();"
                    "print('price cache ready')"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stage", type=int)
    a = ap.parse_args()
    for n, name, check, run in STAGES:
        ok = check()
        if a.status:
            print(f"[{'x' if ok else ' '}] stage {n}: {name}")
            continue
        if a.stage is not None and a.stage != n:
            continue
        if ok and a.stage is None:
            print(f"skip  stage {n}: {name} (already built)")
            continue
        print(f"RUN   stage {n}: {name}")
        run()
    if not a.status:
        print("\nbootstrap complete -> python run_experiments.py")


if __name__ == "__main__":
    main()
