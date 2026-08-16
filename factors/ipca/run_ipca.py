"""IPCA (Kelly-Pruitt-Su 2019, "Characteristics are covariances") on the
score_model characteristic panel: latent factors whose loadings are
instrumented by the 10 observable characteristics (6 classical + 4 13F).

    python run_ipca.py

WHY THIS ON TOP OF FAMA-MACBETH. FM asks "does the characteristic
predict returns?". IPCA asks the deeper question: does it predict
*because* it lines up stocks on a common latent factor (so the premium
is compensation for factor exposure), or does the premium survive
orthogonally to every latent factor the characteristics can span
(alpha)? Loadings are beta_{i,t} = z_{i,t}' Gamma, estimated jointly
with factors f_{t+1} by alternating least squares on the managed-
portfolio moments (W_t = Z'Z/N_t, x_t = Z'r/N_t) - the KPS estimator.

IMPLEMENTATION VERIFIED against the authors' reference package
(github.com/bkelly-lab/ipca), 2026-08-16. Three fixes vs the first cut:
  - Gamma step re-weights each quarter by N_t (Numer and Denom both
    multiplied by val_obs[t] in the reference = asset-level least
    squares); the first cut weighted quarters equally.
  - The alpha test is now the KPS test proper: unrestricted model with
    the intercept as a pre-specified factor (PSF = 1), Gamma_alpha the
    last column of Gamma, Walpha = Gamma_alpha'Gamma_alpha, p-value by
    wild residual bootstrap (scalar Student-t(5) multiplier times a
    time-resampled residual vector, refitting the unrestricted model
    per draw - the reference's BS_Walpha design). The portfolio-level
    spanning regression is kept as a secondary, interpretable line.
  - Convergence on max|dGamma| (tol 1e-5) and the reference sign
    convention (each factor's time-series mean positive).

HONEST LIMITATION, stated up front: KPS fit 600+ monthly observations;
we have ~50 quarterly ones. Risk-premium point estimates are noisy;
what IS answerable here: (1) R2 structure at K=1..4; (2) the Walpha
alpha test; (3) the OOS ranking race vs the unrestricted FM combiner,
restricted (z'Gamma*lambda) and unrestricted (+ z'Gamma_alpha) legs.
A "const" instrument column is included so factor 1 can absorb the
equal-weight market, as in KPS. Rotation is not identified; only the
spanned space is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = Path(__file__).resolve().parent
for sub in ("score_model", "general_plan", "fire_calendar",
            "manager_factor_positioning"):
    sys.path.insert(0, str(HERE.parent / sub))

from backtest_gp import nw_tstat                    # noqa: E402
from run_all import log                             # noqa: E402
from run_score import PREDICTORS, build_panels      # noqa: E402

RESULTS = HERE / "results"
MIN_HIST = 12
KS = (1, 2, 3, 4)
NDRAWS = 500
COLS = ["const"] + PREDICTORS          # L = 11 instruments
TOL, MAX_ITER = 1e-5, 10_000


def moments(panels):
    """Per-quarter managed-portfolio moments W_t (LxL), x_t (L,), plus
    n_t and the stacked asset frames for R2. Scaling by N_t matches the
    reference _build_portfolio."""
    out = []
    for p, X, fwd in panels:
        df = pd.concat([X, fwd.rename("f")], axis=1).dropna()
        Z = np.column_stack([np.ones(len(df)), df[PREDICTORS].values])
        r = df["f"].values
        n = len(df)
        out.append((p, Z.T @ Z / n, Z.T @ r / n, Z, r, n))
    return out


def _identify(Gb, F):
    """Reference identification: Gamma_beta orthonormal, FF' diagonal
    descending, factor means positive."""
    R1 = np.linalg.cholesky(Gb.T @ Gb).T                 # upper
    R2, _, _ = np.linalg.svd(R1 @ F @ F.T @ R1.T)
    Gb = np.linalg.solve(R1.T, Gb.T).T @ R2              # Gb R1^-1 R2
    F = R2.T @ (R1 @ F)
    sg = np.sign(F.mean(axis=1))
    sg[sg == 0] = 1.0
    return Gb * sg, F * sg[:, None]


def als(mom, K, intercept=False, tol=TOL, max_iter=MAX_ITER):
    """KPS ALS on managed-portfolio moments, mirroring the reference
    _ALS_fit_portfolio (N_t-weighted Gamma step; intercept as a
    pre-specified factor identically one)."""
    L = len(COLS)
    Kt = K + int(intercept)
    X_mat = np.column_stack([x for _, _, x, _, _, _ in mom])
    U, _, _ = np.linalg.svd(X_mat, full_matrices=False)
    G = U[:, :Kt].copy()
    for _ in range(max_iter):
        Gb = G[:, :K]
        if intercept:
            Ga = G[:, K]
            F = np.column_stack([
                np.linalg.solve(Gb.T @ W @ Gb, Gb.T @ (x - W @ Ga))
                for _, W, x, _, _, _ in mom])
            Ftil = np.vstack([F, np.ones(F.shape[1])])
        else:
            F = np.column_stack([
                np.linalg.solve(Gb.T @ W @ Gb, Gb.T @ x)
                for _, W, x, _, _, _ in mom])
            Ftil = F
        num = np.zeros(L * Kt)
        den = np.zeros((L * Kt, L * Kt))
        for t, (_, W, x, _, _, n) in enumerate(mom):
            f = Ftil[:, t]
            num += np.kron(x, f) * n
            den += np.kron(W, np.outer(f, f)) * n
        G_new = np.linalg.solve(den, num).reshape(L, Kt)
        Gb_new, F = _identify(G_new[:, :K], F)
        G_new = np.column_stack([Gb_new, G_new[:, K:]]) if intercept \
            else Gb_new
        if np.max(np.abs(G_new - G)) < tol:
            G = G_new
            break
        G = G_new
    return G, F


def walpha_test(mom, K, ndraws=NDRAWS, seed=7):
    """Reference BS_Walpha: wild bootstrap of Gamma_alpha = 0."""
    G, F = als(mom, K, intercept=True)
    walpha = float(G[:, -1] @ G[:, -1])
    T = len(mom)
    Ftil = np.vstack([F, np.ones(T)])
    d = np.column_stack([mom[t][2] - mom[t][1] @ G @ Ftil[:, t]
                         for t in range(T)])
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(ndraws):
        mom_b = []
        for t, (p, W, _, Z, r, n) in enumerate(mom):
            x_b = W @ G[:, :K] @ F[:, t] \
                + rng.standard_t(5) * d[:, rng.integers(T)]
            mom_b.append((p, W, x_b, Z, r, n))
        G_b, _ = als(mom_b, K, intercept=True, tol=1e-4, max_iter=2000)
        if float(G_b[:, -1] @ G_b[:, -1]) > walpha:
            exceed += 1
    return walpha, exceed / ndraws, G, F


def r2_asset(mom, G, F, lam=None):
    """Asset-level R2: total (realised f_t) or predictive (constant
    lambda)."""
    sse, sst = 0.0, 0.0
    for t, (_, _, _, Z, r, _) in enumerate(mom):
        f = F[:, t] if lam is None else lam
        e = r - Z @ G @ f
        sse += float(e @ e)
        sst += float(r @ r)
    return 1.0 - sse / sst


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    panels = build_panels()
    mom = moments(panels)
    T = len(mom)
    log(f"{T} quarters in panel")

    L = [f"# IPCA (Kelly-Pruitt-Su) on the 10-characteristic panel - "
         f"{T} quarters, instruments: const + {', '.join(PREDICTORS)}",
         "", "ALS verified line-by-line against the reference package "
         "(bkelly-lab/ipca): N_t-weighted Gamma step, intercept as "
         "pre-specified factor, Walpha wild bootstrap (t5 multiplier, "
         f"{NDRAWS} draws).", ""]

    # ---- (1) R2 structure + (2) the KPS alpha test -------------------- #
    L += ["## In-sample fit and the alpha question", "",
          "| K | total R2 | predictive R2 | Walpha (Gamma_a'Gamma_a) | "
          "bootstrap p | new_conv managed-pf alpha t (secondary) |",
          "|---|---|---|---|---|---|"]
    i_nc = COLS.index("new_conv")
    x_nc = np.array([x[i_nc] for _, _, x, _, _, _ in mom])
    for K in KS:
        G, F = als(mom, K)
        lam = F.mean(axis=1)
        r2t = r2_asset(mom, G, F)
        r2p = r2_asset(mom, G, F, lam)
        wa, pval, G_u, F_u = walpha_test(mom, K)
        A = np.column_stack([np.ones(T), F.T])
        b, *_ = np.linalg.lstsq(A, x_nc, rcond=None)
        resid = x_nc - A @ b
        t_a = b[0] / (resid.std(ddof=K + 1) / np.sqrt(T)) \
            if resid.std() > 0 else np.nan
        L.append(f"| {K} | {r2t:.3f} | {r2p:.4f} | {wa:.2e} | "
                 f"**{pval:.3f}** | t={t_a:+.2f} |")
        log(f"K={K}: total R2 {r2t:.3f}, pred R2 {r2p:.4f}, "
            f"Walpha p={pval:.3f}, spanning t {t_a:+.2f}")
    L += ["",
          "Reading: total R2 = common factor structure in the managed "
          "returns; predictive R2 = what a constant risk premium "
          "explains. Walpha is the KPS test of Gamma_alpha = 0: a "
          "small p-value means the characteristics carry premium NOT "
          "explained by exposure to the K latent factors (alpha). The "
          "secondary column is the interpretable version: time-series "
          "alpha of the new_conv-managed portfolio on the factors.", ""]

    # ---- (3) OOS ranking race vs the FM combiner ---------------------- #
    rows = []
    for ti in range(MIN_HIST, T):
        G_r, F_r = als(mom[:ti], K=3)
        lam_r = F_r.mean(axis=1)
        G_u, F_u = als(mom[:ti], K=3, intercept=True)
        lam_u = F_u.mean(axis=1)
        p, X, fwd = panels[ti]
        df = pd.concat([X, fwd.rename("f")], axis=1).dropna()
        Z = np.column_stack([np.ones(len(df)), df[PREDICTORS].values])
        er_r = pd.Series(Z @ G_r @ lam_r, index=df.index)
        er_u = pd.Series(Z @ (G_u[:, :3] @ lam_u + G_u[:, 3]),
                         index=df.index)
        rng = np.random.default_rng(int(p.value) % (2**32) + 7)
        jit = pd.Series(rng.uniform(0, 1e-9, len(df)), index=df.index)
        row = {"period": p}
        for nm, er in [("r", er_r), ("u", er_u)]:
            q5 = pd.qcut((er + jit).rank(), 5, labels=False)
            g = df.groupby(q5)["f"].mean()
            row[f"spread_{nm}"] = g.get(4, np.nan) - g.get(0, np.nan)
            row[f"ic_{nm}"] = sps.spearmanr(er, df["f"])[0]
        rows.append(row)
        log(f"OOS {p.date()}: restricted {row['spread_r']:+.4f} "
            f"unrestricted {row['spread_u']:+.4f}")
    E = pd.DataFrame(rows)
    E.to_csv(RESULTS / "ipca_oos.csv", index=False)
    L += ["## OOS ranking race (K=3, expanding, same protocol as the "
          "A/B/C combiner race)", ""]
    for nm, lbl in [("r", "restricted E[r]=z'Gamma*lambda (risk only)"),
                    ("u", "unrestricted + z'Gamma_alpha (risk + alpha)")]:
        sp = E[f"spread_{nm}"]
        L.append(f"- **{lbl}**: spread {sp.mean():+.4f}/qtr "
                 f"(t={nw_tstat(sp):+.2f}), Sharpe "
                 f"{sp.mean() / sp.std() * 2:+.2f}, "
                 f"IC {E[f'ic_{nm}'].mean():+.4f}")
    dl = (E["spread_u"] - E["spread_r"]).dropna()
    L += [f"- delta unrestricted vs restricted: {dl.mean():+.4f}/qtr "
          f"(t={nw_tstat(dl):+.2f})",
          "- reference on the same protocol: A (FM/Lewellen) Sharpe "
          "0.86, C (naive rank-average) 0.74 - expanded universe",
          "",
          "If Walpha rejects, the alpha leg should be where the OOS "
          "ranking power lives - the two results check each other."]
    (RESULTS / "IPCA_REPORT.md").write_text("\n".join(L), encoding="utf-8")
    log("done -> results/")


if __name__ == "__main__":
    main()
