"""The experiment pipeline (esteira), in dependency order.

    python run_experiments.py            # full pipeline
    python run_experiments.py --quick    # core results only (~1h)
    python run_experiments.py --list     # show the plan
    python run_experiments.py --only ncb_catalogue fire

Each entry is (name, script, purpose). Scripts are standalone and
idempotent where they cache (panels/parquets); re-runs are cheap after
the first pass. Results land in each module's results/ directory;
paper tables/figures regenerate from them.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

#           name            script                                   core?
PIPELINE = [
    # --- signal layer -------------------------------------------------- #
    ("ncb_catalogue", "factors/general_predictive_signals/run_signals.py",
     True),   # 17-signal catalogue, NCB headline
    ("fire", "factors/fire_calendar/run_fire.py", True),
    #          flow instrument + forced-sale mechanism
    ("interactions", "factors/interactions_classical/run_inter.py", False),
    ("mfp", "factors/manager_factor_positioning/run_mfp.py", False),
    # --- combining layer ----------------------------------------------- #
    ("score_model", "factors/score_model/run_score.py", True),
    ("ipca", "factors/ipca/run_ipca.py", False),
    ("ml_positioning", "factors/ml_positioning/run_ml.py", False),
    # --- hyperparameter surfaces --------------------------------------- #
    ("ncb_surface", "factors/champion_hyperopt/run_hyperopt.py", True),
    ("fss_surface", "factors/distress_hyperopt/run_dh.py", True),
    # --- engine input panels ------------------------------------------- #
    ("ncb_panel", "factors/champion/run_champion_bt.py", True),
    #          NCB daily signal panel (engine input)
    ("fss_panel", "factors/reversao_condicional/run_reversal.py", True),
    #          FSS/reversal daily panel (engine input)
    ("ssi", "factors/ssi/run_ssi.py", False),
    ("ica", "factors/ica_demand/run_ica.py", False),
    ("copycat", "factors/copycat/run_copycat.py", False),
    ("nmf", "factors/original_methods/nmf_crowding.py", False),
    # --- production engine --------------------------------------------- #
    ("suite", "factors/production_suite/run_suite.py", True),
    ("engine_final", "factors/production_suite/run_final_engine.py",
     True),   # FSS + combo + paper table T1
    ("long_only", "factors/production_suite/run_long_only.py", True),
    ("lo_surface", "factors/production_suite/run_lo_hyperopt.py", False),
    # --- context ------------------------------------------------------- #
    ("fund_performance", "factors/fund_performance/run_perf.py", False),
    # --- paper assets -------------------------------------------------- #
    ("paper_stats", "docs/paper/make_stats.py", True),
    ("paper_figs", "docs/paper/make_figs.py", True),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="core results only")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    todo = [(n, s) for n, s, core in PIPELINE
            if (not a.quick or core)
            and (a.only is None or n in a.only)]
    if a.list:
        for n, s in todo:
            print(f"{n:18s} {s}")
        return
    for n, s in todo:
        t0 = time.time()
        print(f"\n=== {n} ({s}) ===")
        r = subprocess.run([PY, s], cwd=str(ROOT))
        status = "ok" if r.returncode == 0 else f"FAILED ({r.returncode})"
        print(f"=== {n}: {status} in {time.time() - t0:,.0f}s ===")
        if r.returncode != 0:
            print("stopping (fix and re-run; completed stages are cached)")
            sys.exit(1)
    print("\npipeline complete. Paper: docs/paper/ (pdflatex main.tex)")


if __name__ == "__main__":
    main()
