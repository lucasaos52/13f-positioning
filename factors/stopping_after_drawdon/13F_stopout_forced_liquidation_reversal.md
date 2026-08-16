---
title: "13F Stop-Out / Forced-Liquidation Reversal"
subtitle: "A tactical research framework to infer distressed managers, latent liquidation and post-fire-sale reversal from 13F + daily market data"
author: "Quant research memo"
date: "16 August 2026"
geometry: margin=0.72in
fontsize: 10.5pt
header-includes:
  - |
    \usepackage{booktabs}
    \usepackage{longtable}
    \usepackage{array}
    \usepackage{xcolor}
    \usepackage{amsmath}
    \usepackage{amssymb}
    \usepackage{hyperref}
    \usepackage{enumitem}
    \hypersetup{colorlinks=true,linkcolor=black,citecolor=black,urlcolor=blue}
---

# Executive recommendation

The idea is **worth testing**, but the naive version is not the one I would trade.

The naive story is:

> a manager's portfolio suffers a brutal drawdown -> the fund hits an internal risk limit / margin constraint / redemption shock -> it is forced to sell -> its holdings become temporarily cheap -> buy the holdings.

The problem is that the current 13F project has already found an important warning: the quarterly `distress_mom` experiment did **not** show fast mean reversion. Forced-selling names continued to underperform for roughly a year, with only weak reversal much later. Therefore a simple rule such as `manager drawdown -> buy holdings` is contradicted by the current project at quarterly horizons.

The better version is **tactical and state-dependent**:

$$
\boxed{
\text{manager distress}
\rightarrow
\text{active forced liquidation}
\rightarrow
\text{temporary price pressure}
\rightarrow
\text{liquidation exhaustion}
\rightarrow
\text{reversal}
}
$$

The key research problem is therefore **not merely to detect drawdown**. It is to infer three latent objects in real time:

1. **which managers are actually distressed**;
2. **which managers are actively liquidating their 13F equity sleeve**;
3. **when the liquidation pressure has peaked and is exhausting**.

The most senior-quant implementation is to treat the entire cross-section of stock returns as an **inverse problem**. Given the public holdings matrix, infer the sparse set of managers whose liquidation would best explain the abnormal return vector observed that day:

$$
\boxed{
\mathbf r_t^{\perp} = - A_t \boldsymbol\ell_t + \boldsymbol\epsilon_t
}
$$

where:

- $\mathbf r_t^{\perp}$ = factor-residual stock returns;
- $A_t$ = disclosed ownership scaled by liquidity;
- $\ell_{m,t}\ge0$ = latent liquidation intensity of manager $m$;
- $\epsilon_t$ = fundamental / idiosyncratic return component.

Then use the manager's synthetic drawdown as a **prior** on $\ell_{m,t}$, not as the trading signal itself.

Finally, trade the stocks with high inferred liquidation pressure **only after the pressure is estimated to be exhausting**.

This is materially different from the Bonacich/network experiment already run in the project. The previous network test was essentially `ownership structure -> return`. This proposal is:

$$
\boxed{
\text{observed manager-level loss}
+ \text{ownership network}
+ \text{return-vector alignment}
\rightarrow \text{latent forced flow}
\rightarrow \text{exhaustion reversal}
}
$$

That gives the network a directional shock and a falsifiable intermediate mechanism.

---

# 1. Why this is genuinely different from what has already been tested

The current 13F research already contains several nearby ideas:

- a validated **implicit manager flow** estimator based on change in equity AUM versus the return of a frozen book;
- `distress_mom`, where distressed sellers subsequently underperformed;
- Bonacich / common-owner network vulnerability;
- a fire-sale calendar showing that distressed managers tend to sell equities approximately **pro rata**, rather than using a strong pecking order;
- an explicit conclusion that static state variables are weak unless attached to a directional mechanism.

It also contains a critical empirical result:

> the pre-registered Coval-Stafford-style short-horizon reversal hypothesis failed at the quarterly frequency; forced-selling names showed continuation over the next several quarters.

Therefore the proposed project must **not** be sold internally as "another fire-sale reversal factor." The new research question is narrower:

> **Can 13F holdings plus daily prices identify a short-lived forced-liquidation episode and its exhaustion point, even though quarterly distressed ownership predicts longer-horizon continuation?**

Those two facts can coexist.

A stock can experience:

1. information-driven deterioration that persists for months;
2. a superimposed forced-flow discount over a few days;
3. a partial tactical rebound after the flow ends;
4. continued medium-horizon fundamental underperformance afterward.

The desired trade is only component (2) -> (3).

---

# 2. What the literature says that is directly relevant

## 2.1 Hedge-fund losses can mechanically produce equity liquidations

Ben-David, Franzoni and Moussawi (2012, *Review of Financial Studies*) use 13F holdings matched to hedge-fund information around the 2007-2009 crisis. They document a very large reduction in hedge-fund equity holdings and conclude that **investor redemptions and margin calls were primary drivers**. They also find forced deleveraging concentrated in relatively liquid and volatile stocks.

This matters because it supports the exact causal bridge required here:

$$
\text{losses} \rightarrow \text{funding pressure} \rightarrow \text{equity selling}.
$$

It also warns against assuming that the manager sells the "worst" or most illiquid stock first. Under funding stress, liquid positions may be sold precisely because they are easiest to monetize.

## 2.2 Distressed mega hedge funds are explicitly front-run

Agarwal, Aragon, Nanda and Wei (2025, *Review of Financial Studies*) is almost exactly on point. The authors study stocks expected to be sold by distressed mega hedge funds. Their published abstract reports:

- anticipatory institutional selling in stocks expected to be liquidated;
- increased short interest;
- lower abnormal returns while selling is anticipated;
- subsequent reversal;
- no comparable result for nondistressed mega hedge funds or distressed non-mega hedge funds.

In the earlier public working-paper version, a hedge fund is classified as distressed when its quarterly return is both **negative** and in the **bottom quartile** of hedge-fund returns.

The important difference for the current project is data availability. That paper observes external fund-performance information. Here the goal is to build a **13F-plus-price proxy for fund distress**.

## 2.3 Fire-sale discounts can reverse after forced supply disappears

Coval and Stafford (2007, *Journal of Financial Economics*) identify forced trades associated with mutual-fund distress. Poor performance induces outflows, which induce portfolio sales; the associated price pressure is temporary enough to generate reversal patterns.

Chen, Hanson, Hong and Stein (2008) further study whether hedge funds profit from predictable mutual-fund distress. Their evidence is more consistent with contemporaneous/front-running exploitation than with a strategy that waits a long time after the fire sale.

This reinforces the tactical framing: the economic rent should be largest around the **liquidation window**, not a generic quarterly sort.

## 2.4 Ownership structure tells us where a funding shock can propagate

Greenwood and Thesmar (2011, *Journal of Financial Economics*) define stock-price fragility from two objects:

1. ownership concentration;
2. the variance-covariance matrix of liquidity shocks of the owners.

An asset is fragile when its current owners are likely to need liquidity at the same time. Their framework is directly useful here, but the current project can make it more directional by combining ownership with a contemporaneous distress estimate.

## 2.5 Predatory trading is part of the mechanism

Brunnermeier and Pedersen's predatory-trading framework studies traders who exploit another investor's need to reduce positions. This provides a second source of temporary price pressure:

$$
\text{forced seller}
\rightarrow
\text{anticipated forced seller}
\rightarrow
\text{front-runners also sell}
\rightarrow
\text{overshoot}.
$$

This is especially relevant for large, visible managers with public holdings.

---

# 3. Core causal model

The research should explicitly separate four latent stages.

## State 0 - Normal

The manager's equity sleeve behaves within its ordinary risk envelope.

## State 1 - Distressed

The manager has experienced an unusually severe portfolio loss or drawdown, but there is no evidence yet that the portfolio is being mechanically liquidated.

## State 2 - Liquidating

The cross-section of returns of the manager's disclosed holdings begins to look like a **common sale vector**. Stocks with greater expected sale pressure underperform, volume increases, and the pattern is too aligned with the ownership/liquidity vector to be explained by ordinary covariance alone.

## State 3 - Exhausted

The estimated liquidation intensity peaks and falls. Price pressure stabilizes despite still-high volume and/or still-negative manager-level P&L. This is the candidate point for the long reversal trade.

A useful conceptual model is therefore:

$$
S_{m,t} \in \{N,D,L,E\}
$$

with transitions

$$
N \rightarrow D \rightarrow L \rightarrow E \rightarrow N.
$$

A Hidden Markov Model is possible, but a **Hidden Semi-Markov Model (HSMM)** is conceptually better because liquidation episodes have duration and do not switch randomly every day.

---

# 4. First problem: which 13F filers should be eligible?

The user's intuition is right: a manager whose holdings are persistent from quarter to quarter is more usable than an institution whose disclosed book is merely a passive index or a tiny observable slice of a much broader multi-asset portfolio.

However, the current project already showed that "smart money" filtering hurts. The filter here should therefore be **structural**, not based on skill.

## 4.1 Eligibility features

For each filer $m$, compute:

### Holdings persistence

- NDCG / rank persistence;
- fraction of positions surviving one quarter;
- share-weight overlap;
- top-10 overlap.

### Turnover

$$
Turnover_{m,q}
=
\frac12\sum_i|w_{mi,q}-w^{drift}_{mi,q-1}|.
$$

Reject extremely passive index-like managers and extremely unstable books where the previous 13F is almost useless intraquarter.

### Concentration

- HHI;
- top-5 and top-10 portfolio share;
- effective number of names $1/HHI$.

A concentrated active manager gives a cleaner synthetic P&L and a cleaner liquidation footprint.

### Passive similarity

Compare the book with broad benchmarks / major ETFs:

$$
PassiveSimilarity_m = corr(w_m,w_{benchmark})
$$

or cosine similarity / active share.

This is not a claim that active managers are "smarter." It is simply a measurement-quality screen: a passive-like filer is unlikely to hit an idiosyncratic discretionary hard stop in the sense being modeled.

## 4.2 Do not make the filter too narrow

Recommended design:

- create an **eligibility score**;
- run the signal on the full eligible universe;
- separately report effect by concentration / persistence / size buckets.

Do not optimize a hard cutoff on Sharpe.

---

# 5. Reconstruct a synthetic daily manager book

This is the first essential implementation block.

Suppose the latest public quarter-end holdings for manager $m$ are $w_{mi,q}$.

Between quarter-end observations, drift the weights using daily price returns:

$$
\tilde w_{mi,t}
=
\frac{w_{mi,q}\prod_{s=q+1}^{t}(1+r_{i,s})}
{\sum_j w_{mj,q}\prod_{s=q+1}^{t}(1+r_{j,s})}.
$$

The synthetic long-equity sleeve return is:

$$
R^{L}_{m,t}
=
\sum_i \tilde w_{mi,t-1}r_{i,t}.
$$

Construct the cumulative NAV:

$$
V_{m,t}=V_{m,t-1}(1+R^L_{m,t}).
$$

Then synthetic drawdown is

$$
DD_{m,t}
=
\frac{V_{m,t}}
{\max_{s\le t}V_{m,s}}-1.
$$

## Important limitation

This is **not the hedge fund return**.

13F does not reveal:

- shorts;
- many derivatives;
- cash;
- non-US assets;
- private assets;
- leverage;
- intraquarter trading.

Call the object what it is:

> **synthetic disclosed-long-equity drawdown**.

The thesis is not that it reconstructs fund NAV perfectly. The thesis is that for a selected subset of persistent equity managers it may be a useful **stress proxy**.

---

# 6. Raw drawdown is not enough: residualize the book

A manager whose tech holdings fall 10% because Nasdaq falls 10% is not necessarily being stopped out.

The more useful quantity is the return of the disclosed book after removing broad common moves.

For each stock:

$$
r_{i,t}
=
\beta_{i,t}^{\top}f_t+r_{i,t}^{\perp}.
$$

Start with a robust, simple model:

- market;
- industry / sector;
- optional size, momentum, beta / low-vol factors.

Then:

$$
R^{\perp}_{m,t}
=
\sum_i \tilde w_{mi,t-1}r_{i,t}^{\perp}.
$$

Build both:

1. raw drawdown;
2. residual drawdown.

The second is more relevant for an idiosyncratic manager stop.

---

# 7. Use the covariance matrix correctly

The original intuition was "maybe when all the fund's stocks become correlated." That is useful, but a senior implementation should ask:

> **Are the holdings moving together more than the covariance model says they should, and is the direction of that movement aligned with a plausible liquidation vector?**

## 7.1 Forecast covariance

Estimate a daily residual covariance matrix $\Sigma_t$ using one of:

1. EWMA covariance;
2. Ledoit-Wolf shrinkage;
3. factor covariance + diagonal specific risk;
4. a more advanced similarity/covariance forecast later.

Avoid a raw sample covariance for large books.

Manager forecast volatility is:

$$
\sigma^2_{m,t}
=
\tilde w_{m,t}^{\top}\Sigma_t\tilde w_{m,t}.
$$

Standardized manager shock:

$$
z^{book}_{m,t}
=
\frac{R_{m,t}^{\perp}}
{\sigma_{m,t}}.
$$

## 7.2 Pain breadth

Measure how much of the book is losing simultaneously:

$$
PainBreadth_{m,t}
=
\sum_i \tilde w_{mi,t}
\mathbf 1(r^{\perp}_{i,t}<-c\sigma_{i,t}).
$$

A 5% book loss driven by one 40%-weight stock is different from a 5% loss where 85% of the holdings are down together.

## 7.3 Correlation surprise

One simple diagnostic is the ratio:

$$
CorrShock_{m,t}
=
\frac{\tilde w_m'\Sigma_t\tilde w_m}
{\sum_i \tilde w_{mi}^2\sigma_{i,t}^2}.
$$

The denominator keeps only individual variances. The ratio grows as cross-correlations rise.

Use a through-time z-score rather than the raw level.

## 7.4 PCA coherence

For the manager's holdings, take a rolling window of residual returns and compute the covariance/eigenvalues:

$$
C_{m,t}=V\Lambda V'.
$$

Define:

$$
PCShare_{m,t}=\frac{\lambda_1}{\sum_j\lambda_j}.
$$

A sudden rise indicates that previously idiosyncratic positions are becoming a one-factor basket.

But **PCShare alone is not evidence of liquidation**. The key extra test is alignment.

---

# 8. The key improvement: liquidation-vector alignment

If a manager must raise cash quickly, a first-order prediction is that sale pressure is related to the amount of each stock held and its trading capacity.

Define the manager-stock liquidation exposure:

$$
a_{im,t}
=
\frac{DollarHolding_{mi,t}}
{ADV_{i,t}}.
$$

Possible refinements:

- free-float adjustment;
- square-root impact scaling;
- cap at extreme Days-ADV;
- manager's historical propensity to sell that name.

Now ask whether the return vector of the manager's holdings is aligned with $-a_{m,t}$.

## 8.1 Simple within-manager pressure regression

For each manager/day or manager/short window:

$$
r_{i,t}^{\perp}
=
\alpha_{m,t}
-
\lambda_{m,t}a_{im,t}
+u_{i,t},
\qquad i\in H_m.
$$

Interpretation:

- large positive $\lambda_{m,t}$: stocks that would be more painful for this manager to liquidate are underperforming more;
- high $R^2$: the cross-section looks like a liquidation footprint.

This is much stronger than simply saying "all stocks are correlated."

## 8.2 PCA alignment

Let $v_{1,m,t}$ be the first eigenvector of residual returns across the manager's holdings.

Define:

$$
Alignment_{m,t}
=
\left|
\cos(v_{1,m,t},a_{m,t})
\right|.
$$

The combination

$$
PCShare \times Alignment
$$

asks whether the newly emergent common mode looks specifically like a **holdings/liquidity liquidation mode**.

---

# 9. Build an ex-post forced-liquidation label first

Before trying to trade daily, prove that the 13F data can identify something resembling a stop-out.

The project already has a validated manager-level implicit flow estimator. Use the next 13F only as a **training/validation label**, never as a contemporaneous trading input.

For manager $m$ in quarter $q$, construct:

## 9.1 Implied funding shock

$$
FlowShock_{m,q}
=
\frac{AUM^{13F}_{m,q}
-AUM^{13F,\ frozen}_{m,q}}
{AUM^{13F}_{m,q-1}}.
$$

Use the project's existing implementation.

## 9.2 Sell breadth

$$
SellBreadth_{m,q}
=
\frac{\#\{i:\Delta Shares_{mi,q}<0\}}
{\#\{i:Shares_{mi,q-1}>0\}}.
$$

## 9.3 Pro-rata liquidation fit

If a fund is raising cash rather than expressing many stock-specific views, reductions should be relatively proportional to initial holdings.

Estimate:

$$
SellDollar_{mi,q}
=
\alpha_{m,q}
+
\beta_{m,q}HoldingDollar_{mi,q-1}
+\epsilon_{mi,q}.
$$

or in percentage terms:

$$
\frac{\Delta Shares_{mi,q}}
{Shares_{mi,q-1}}
\approx c_{m,q}.
$$

Record:

- slope;
- $R^2$;
- dispersion of percentage reductions.

This connects directly to the current project's result that distressed equity selling was approximately pro rata.

## 9.4 Candidate label

Do not hard-code one definition as truth. Compare several labels.

Example:

$$
ForcedSale_{m,q}=1
$$

if the manager is simultaneously in:

- bottom decile/quintile of implied flow;
- top quintile of sell breadth;
- high pro-rata fit;
- large total reduction in the equity sleeve.

Then ask whether the **daily distress features measured before the next 13F** predict this label.

That is the first falsification gate.

---

# 10. Baseline model: a simple stop-risk score

Start with an intentionally transparent model.

For manager $m$ at day $t$:

$$
StopRisk_{m,t}
=
\beta_1 z(DD^{raw}_{m,t})
+\beta_2 z(DD^{\perp}_{m,t})
+\beta_3 z(PainBreadth_{m,t})
+\beta_4 z(CorrShock_{m,t})
+\beta_5 z(PCShare_{m,t})
+\beta_6 z(Alignment_{m,t}).
$$

Possible additional terms:

- recent volatility shock;
- concentration;
- Days-ADV of the book;
- manager size / public visibility;
- recent prior implied flow state.

Use either:

- fixed equal weights initially;
- logistic regression trained only on prior forced-sale labels;
- ridge logistic regression to control collinearity.

The first target is **not future return**. The first target is:

$$
P(ForcedSale_{m,q+1}=1|X_{m,t}).
$$

---

# 11. Better model: manager liquidation hazard

A stop-out is an event-time problem.

Define a daily hazard:

$$
h_{m,t}
=
P(T_m=t\mid T_m\ge t, X_{m,t}).
$$

Use:

- discrete-time logistic hazard;
- Cox model as a robustness check;
- manager random effects / frailty if enough history exists.

Covariates should be lagged and point-in-time.

The important output is a daily probability:

$$
p^{distress}_{m,t}.
$$

This is still only the **prior probability of forced selling**. It is not yet sufficient for the buy signal.

---

# 12. Hidden-state version: Normal -> Distress -> Liquidation -> Exhaustion

A richer formulation is a four-state HSMM.

Observation vector:

$$
y_{m,t}=
\begin{bmatrix}
DD^{\perp}_{m,t}\\
z^{book}_{m,t}\\
PainBreadth_{m,t}\\
CorrShock_{m,t}\\
PCShare_{m,t}\\
Alignment_{m,t}\\
VolumeFootprint_{m,t}
\end{bmatrix}.
$$

Latent state:

$$
S_{m,t}\in\{Normal,Distress,Liquidation,Exhaustion\}.
$$

Why HSMM rather than ordinary HMM:

- liquidation episodes have duration;
- a one-day switch from liquidation to normal and back is economically implausible;
- state-duration distributions can encode this persistence directly.

The output required for trading is:

$$
P(S_{m,t}=Liquidation|\mathcal F_t)
$$

and

$$
P(S_{m,t}=Exhaustion|\mathcal F_t).
$$

---

# 13. Main recommended model: inverse liquidation from the stock-return cross-section

This is the version I would expect a strong senior quant researcher to find most interesting.

Let:

- $N$ = stocks;
- $M$ = eligible managers;
- $W_t\in\mathbb R^{M\times N}$ = manager-stock dollar ownership;
- $D_t$ = diagonal matrix of stock trading capacity / liquidity.

Define:

$$
A_t=D_t^{-1}W_t'.
$$

Thus $A_t\in\mathbb R^{N\times M}$ and column $m$ is the **predicted cross-sectional price-pressure shape** generated by liquidation of manager $m$.

Let $\ell_{m,t}\ge0$ be the latent amount/intensity manager $m$ is liquidating.

Then:

$$
\boxed{
\mathbf r_t^{\perp}
=
-\kappa A_t\boldsymbol\ell_t
+
\boldsymbol\epsilon_t
}
$$

where $\kappa$ is price-impact scale.

## 13.1 Sparse nonnegative inverse problem

On a normal day, most managers are not being stopped out. Therefore $\ell_t$ should be sparse and nonnegative.

Estimate:

$$
\hat{\boldsymbol\ell}_t
=
\arg\min_{\ell\ge0}
\left
\{
(\mathbf r_t^{\perp}+A_t\ell)'
\Omega_t^{-1}
(\mathbf r_t^{\perp}+A_t\ell)
+\lambda_1\|\ell\|_1
+\lambda_2\|\ell\|_2^2
\right\}.
$$

This is a **nonnegative elastic-net / GLS inverse problem**.

- $L_1$ creates sparsity: few managers are liquidating.
- $L_2$ stabilizes highly overlapping holdings.
- $\Omega_t$ accounts for ordinary residual return covariance.

## 13.2 Inject the drawdown as a prior

The synthetic drawdown should change the penalty applied to each manager:

$$
\lambda_{m,t}
=
\lambda_0\exp(-\gamma DistressScore_{m,t}).
$$

A manager with no drawdown receives a large penalty and is unlikely to be selected as a liquidator.

A severely distressed manager receives a smaller penalty.

Then solve:

$$
\hat\ell_t
=
\arg\min_{\ell\ge0}
\left
\{
(\mathbf r_t^{\perp}+A_t\ell)'
\Omega_t^{-1}
(\mathbf r_t^{\perp}+A_t\ell)
+\sum_m\lambda_{m,t}\ell_m
+\lambda_2\|\ell\|_2^2
\right\}.
$$

This is much better than setting `stop = drawdown < -10%`.

The model asks:

> Given who is currently distressed, which sparse combination of those managers' disclosed portfolios best explains today's abnormal stock-return vector?

---

# 14. Why the covariance matrix matters in the inverse model

Without covariance adjustment, the algorithm can falsely call a liquidation whenever a whole sector falls.

Let:

$$
\Omega_t=Cov(\epsilon_t)
$$

be a forecast residual covariance matrix after removing market/sector/style factors.

Cholesky-whiten the problem:

$$
\tilde r_t=L_t^{-1}r_t^{\perp},
\qquad
\tilde A_t=L_t^{-1}A_t,
$$

where

$$
\Omega_t=L_tL_t'.
$$

Now solve approximately:

$$
\tilde r_t=-\tilde A_t\ell_t+\tilde\epsilon_t.
$$

Interpretation:

> Only the component of the cross-sectional move that is unusual **relative to expected covariance** is allowed to identify a stop-out.

This is the correct answer to the original "all of the fund's stocks became correlated" intuition.

Raw correlation is insufficient; **covariance-adjusted alignment with the manager's liquidation vector** is the stronger diagnostic.

---

# 15. Dynamic version: latent liquidation intensity as a state-space process

Forced selling usually persists for several sessions.

Model:

$$
r_t^{\perp}=-A_t\ell_t+\epsilon_t
$$

and

$$
\ell_t=\rho\ell_{t-1}+u_t,
\qquad \ell_t\ge0.
$$

Possible estimation approaches:

- constrained Kalman-like filtering after transformation;
- particle filter;
- MAP filtering with nonnegative elastic-net each day plus temporal penalty;
- fused lasso:

$$
\lambda_{TV}\|\ell_t-\ell_{t-1}\|_1.
$$

A practical objective is:

$$
\min_{\ell_t\ge0}
Loss_t(\ell_t)
+\lambda_1\|\ell_t\|_1
+\lambda_2\|\ell_t\|_2^2
+\lambda_{TV}\|\ell_t-\ell_{t-1}\|_1.
$$

This produces a daily **liquidation intensity path** for every manager.

---

# 16. Convert manager liquidation into stock-level pressure

Once $\hat\ell_t$ exists:

$$
\boxed{
Pressure_{i,t}
=
[A_t\hat\ell_t]_i
}
$$

This is estimated non-fundamental sell pressure on stock $i$ coming from currently distressed institutional owners.

A more impact-aware version can use square-root impact:

$$
Pressure_{i,t}
=
\sum_m
\hat\ell_{m,t}
\sigma_{i,t}
\sqrt{
\frac{ExpectedSellDollar_{mi,t}}
{ADV_{i,t}}
}.
$$

Do not over-engineer impact in V1. First establish monotonicity between the simple score and realized future holding reductions / abnormal returns.

---

# 17. Distinguish forced-flow moves from stock-specific information

This is essential because the current project found that distress selling can contain information.

A stock can be down because:

1. the manager is selling it mechanically;
2. the stock is fundamentally bad and the manager is correctly selling it;
3. both.

The tactical long wants mostly (1).

## 17.1 Leave-one-out manager basket

For stock $i$ held by manager $m$:

$$
R^{LOO}_{m,-i,t}
=
\sum_{j\ne i}
\tilde w_{mj,t}r_{j,t}^{\perp}.
$$

If stock $i$ falls together with the rest of the manager's unrelated residual book, the flow interpretation is stronger.

If stock $i$ collapses alone and the other holdings are stable, the information interpretation is stronger.

## 17.2 Cross-sectional fit

Use the return-pressure regression residual:

$$
InfoResidual_{i,t}
=
r_{i,t}^{\perp}
+\hat\kappa Pressure_{i,t}.
$$

A very negative residual even after accounting for forced pressure indicates likely stock-specific bad information.

Penalize such names in the reversal trade.

## 17.3 Multiple-holder triangulation

A stock held by several **independently distressed** managers has a cleaner forced-flow story if those managers are exposed to different industries/strategies but all face stress simultaneously.

Conversely, if every distressed manager is simply a technology manager during a technology fundamental shock, residualization and covariance controls must do the heavy lifting.

---

# 18. The crucial trade timing: do not buy during the liquidation

The biggest expected mistake in this project is entering too early.

The literature on front-running distressed funds and the current project's own `distress_mom` results both suggest that prices can keep falling while supply is active.

Therefore separate:

## Signal A - Active liquidation / continuation

When

$$
\hat\ell_{m,t}\uparrow
$$

and stock pressure is increasing, the predicted direction is still **down**.

This can be tested as a short-horizon short / avoid signal.

## Signal B - Exhaustion reversal

The long entry should require evidence that liquidation intensity has peaked.

Possible exhaustion conditions:

### Intensity peak

$$
\hat\ell_{m,t-1}>Q_{95}(\ell_m)
$$

and

$$
\Delta\hat\ell_{m,t}<0.
$$

### Pressure deceleration

$$
\Delta Pressure_{i,t}<0
$$

while the manager remains distressed.

### Volume climax

Abnormal volume is extreme but no longer generates proportional negative residual return.

Define an impact ratio:

$$
ImpactEfficiency_{i,t}
=
\frac{-r^{\perp}_{i,t}}
{AbnormalVolume_{i,t}}.
$$

A sharp fall in impact efficiency after a pressure spike can indicate that buyers are absorbing supply.

### First positive residual reversal

Require a positive residual day or positive intraday/close-to-close reversal after the pressure peak.

The first production version should test several entry rules rather than assume one.

---

# 19. Candidate final stock signal

Define:

$$
PeakPressure_{i,t}
=
\max_{s\in[t-k,t]} Pressure_{i,s}.
$$

Define an exhaustion score:

$$
Exhaustion_{i,t}
=
z(PeakPressure_{i,t})
-z(Pressure_{i,t})
+z(VolumeClimax_{i,t})
+z(PriceStabilization_{i,t}).
$$

Define a non-information score:

$$
NonInfo_{i,t}
=
+z(Corr(r_i^{\perp},R^{LOO}_{m,-i}))
-z(|InfoResidual_{i,t}|).
$$

Then:

$$
\boxed{
StopoutReversal_{i,t}
=
PeakPressure_{i,t}
\times Exhaustion_{i,t}
\times NonInfo_{i,t}
}
$$

For multiple distressed holders, aggregate manager contributions before standardization.

A simpler robust V1 is preferable:

$$
Score_{i,t}
=
PeakPressure_{i,t}
\times
\mathbf1(Pressure\ decreasing)
\times
\mathbf1(r^{\perp}_{i,t}>0).
$$

---

# 20. Three trading architectures to test

## Architecture 1 - Pure post-stop long

Long only stocks in the top bucket of `StopoutReversal`.

This matches the original intuition and avoids short borrow.

Holding periods:

- 1 day;
- 3 days;
- 5 days;
- 10 days;
- 20 days.

## Architecture 2 - Two-stage tactical trade

### Phase A

Short / underweight while inferred liquidation intensity is accelerating.

### Phase B

Flip long after exhaustion.

This directly tests the causal path and may explain why a quarterly strategy sees continuation even if a narrow post-exhaustion rebound exists.

## Architecture 3 - Cross-sectional factor

Each day rank stocks by reversal score and construct:

$$
FSR_t
=
R(Top\ Decile)_t-R(Bottom\ Decile)_t.
$$

Neutralize:

- beta;
- sector;
- optional size / momentum.

Report raw and factor-adjusted returns separately.

---

# 21. Research hypotheses in the correct causal order

Do **not** jump directly to Sharpe.

## H1 - Synthetic distress predicts realized broad selling

Managers with extreme synthetic residual drawdowns should subsequently show:

- larger negative implied flow;
- higher sell breadth;
- stronger pro-rata reduction.

If H1 fails, stop.

## H2 - Correlated residual pain improves distress identification

Conditional on the same synthetic drawdown, managers with high `PainBreadth`, `CorrShock` and `PCShare x Alignment` should be more likely to exhibit the forced-sale label.

If not, raw drawdown is sufficient and the covariance machinery adds no information.

## H3 - Inverse-model liquidation intensity predicts actual next holdings changes

For stocks with high estimated pressure:

$$
Pressure_{i,t}
\rightarrow
\Delta Shares_{i,q+1}<0.
$$

This is the strongest mechanism validation available with the existing data.

## H4 - Active liquidation predicts short-horizon continuation

While $\hat\ell$ is rising, high-pressure stocks should underperform matched controls.

This should be expected if the model is detecting real supply.

## H5 - Exhaustion predicts tactical reversal

After $\hat\ell$ peaks and decays, the same stocks should outperform matched controls over 1-20 trading days.

This is the actual alpha hypothesis.

## H6 - Reversal is stronger when the move is more clearly non-informational

The rebound should be stronger when:

- leave-one-out basket coherence is high;
- pressure-model fit is high;
- stock-specific residual after predicted pressure is small;
- manager ownership / ADV is large;
- the distressed manager is large / visible.

## H7 - Medium-horizon continuation can coexist with tactical reversal

After the first 5-20 days, measure returns through 1-4 quarters.

A plausible shape is:

$$
\text{selloff}
\rightarrow
\text{5-10d bounce}
\rightarrow
\text{longer-horizon weakness}.
$$

If observed, it reconciles this strategy with the existing `distress_mom` result.

---

# 22. Placebos and falsification tests

This research needs unusually aggressive falsification because the latent state is unobserved.

## 22.1 Distressed-manager placebo

Take managers with equally bad synthetic drawdowns but **no subsequent broad selling** in the next 13F.

The liquidation footprint should be much weaker.

## 22.2 Ownership shuffle

Shuffle manager-stock edges while preserving manager and stock degrees.

The inverse model should lose predictive power.

## 22.3 Same stock, nondistressed owner placebo

Compare two otherwise similar stocks with comparable momentum/liquidity, one heavily owned by currently distressed managers and one not.

The distressed-ownership stock should exhibit stronger pressure/reversal pattern.

## 22.4 Sector shock placebo

Repeat after aggressive sector/factor residualization.

If the signal disappears completely, it may just be detecting sector crashes.

## 22.5 Random drawdown timing

Shift each manager's distress series by random quarters/days.

Mechanism statistics and alpha should disappear.

## 22.6 Future filing leakage test

The next 13F may be used only to construct labels in training/evaluation.

At prediction time, the system must use `snapshot_as_of` with only filings already public on that date.

## 22.7 Mega / visibility interaction

The 2025 RFS paper finds anticipatory trading particularly for distressed **mega** hedge funds whose public holdings are visible. Test the interaction:

$$
Distress\times Size/Visibility.
$$

Do not impose it ex ante as a hard filter.

## 22.8 Holding-staleness interaction

If the latest 13F is very stale or the manager historically has high turnover, the inferred liquidation vector should be less accurate.

The effect should decay monotonically with a staleness score.

This is a strong validity check.

---

# 23. Matching / identification design for the return test

For each high-pressure stock-event, construct controls matched on:

- market cap;
- ADV / Amihud;
- sector;
- beta;
- prior 1d / 5d / 20d residual return;
- volatility;
- institutional ownership;
- earnings proximity if available.

Then estimate event-time abnormal returns:

$$
CAR[-5,+20].
$$

Plot separately by:

1. manager distress decile;
2. liquidation intensity decile;
3. exhaustion score;
4. ownership/ADV;
5. manager visibility.

The desired signature is not simply a positive average return. It is a **shape**:

- deterioration into the inferred liquidation;
- trough around peak pressure;
- rebound after estimated exhaustion.

---

# 24. Manager-level event study

The cleanest visualization in the entire project may be manager-centered.

For every ex-post forced-sale event:

1. estimate the day $t^*$ of minimum synthetic NAV / maximum inferred liquidation;
2. align days around $t^*$;
3. plot:
   - synthetic long-book DD;
   - residual DD;
   - $\hat\ell_{m,t}$;
   - pain breadth;
   - correlation shock;
   - PCShare;
   - realized abnormal return of high-pressure holdings;
   - subsequent 13F sell breadth.

If the framework is real, the average chart should look like:

```text
manager loss worsens
        |
        v
breadth/correlation shock rises
        |
        v
latent liquidation intensity spikes
        |
        v
high-pressure holdings underperform
        |
        v
liquidation intensity rolls over
        |
        v
short-horizon rebound
```

If this shape is absent, there is no reason to proceed to a production factor.

---

# 25. Practical covariance choices

## V1 - Factor model + diagonal specific risk

Best first choice. Stable and interpretable.

## V2 - EWMA residual covariance

Easy and responsive to crises.

## V3 - Ledoit-Wolf shrinkage

Useful for moderately large stock universes.

## V4 - Similarity-based covariance forecasting

Potential later extension. The attached tactical-allocation research cites Cartea, Cucuringu, Jennings and Zhang's similarity-based covariance forecasting work. This is interesting if stress episodes resemble historical covariance states, but it is not necessary for the first implementation.

### Recommendation

Do **not** let covariance sophistication delay the mechanism test.

The minimum viable model is:

$$
\text{market/sector residuals}
+\text{EWMA/shrinkage covariance}
+\text{nonnegative ridge/elastic-net inverse flow}.
$$

---

# 26. What should count as a "stop"?

A hard stop is not directly observable in 13F.

Therefore the research should use the language:

> **inferred forced-liquidation episode**

rather than claiming that an internal hard-stop rule was literally triggered.

Several mechanisms can generate the same observable pattern:

- internal drawdown stop;
- VaR/risk-budget reduction;
- prime-broker margin call;
- investor redemption;
- leverage reduction;
- gross/net exposure cut;
- fund closure.

From a trading perspective these can be pooled if they produce the same key causal object:

$$
\text{non-informational urgent supply}.
$$

The labels should therefore be mechanism-agnostic at first.

---

# 27. A particularly strong extension: infer a manager's hidden stop threshold

Once ex-post forced-sale events exist, estimate each manager's historical stress threshold.

For manager $m$, observe the synthetic residual drawdown just before labeled forced-sale quarters:

$$
\{DD^{\perp}_{m,e}\}_{e=1}^{E_m}.
$$

Use hierarchical shrinkage:

$$
\theta_m
\sim
N(\mu_{cluster(m)},\tau^2)
$$

where $\theta_m$ is the latent stop threshold.

Managers with little history shrink toward peers with similar:

- concentration;
- turnover;
- style;
- size;
- liquidity profile.

Then daily stop proximity is:

$$
StopDistance_{m,t}
=
\frac{DD^{\perp}_{m,t}-\hat\theta_m}
{SE(\hat\theta_m)}.
$$

This turns the user's original intuition - "assume a hard stop" - into an empirically calibrated probabilistic threshold instead of an arbitrary `-10%` rule.

---

# 28. Another strong extension: common stop-out modes

Managers may be stopped out together because they own similar books.

Let manager residual synthetic returns be:

$$
\mathbf R_t^M=W_t\mathbf r_t^{\perp}.
$$

Estimate a manager covariance matrix:

$$
\Sigma^M_t=Cov(\mathbf R^M).
$$

Or use the covariance of inferred liquidation intensities:

$$
\Sigma^{\ell}=Cov(\hat\ell_t).
$$

Eigendecompose:

$$
\Sigma^{\ell}=Q\Lambda Q'.
$$

The leading eigenvectors identify **common deleveraging clusters** - groups of managers that tend to liquidate together.

Then map the cluster back to stocks:

$$
StockMode_k=W'Q_k.
$$

This is a directional upgrade to the earlier static network work because the eigenmodes are estimated from **liquidation states**, not merely common ownership.

---

# 29. Potential factor definitions

## 29.1 Active Liquidation Pressure (ALP)

$$
ALP_{i,t}=Pressure_{i,t}.
$$

Prior: negative next 1-5 day return while pressure rises.

## 29.2 Liquidation Exhaustion Reversal (LER)

$$
LER_{i,t}
=PeakPressure_{i,t}
\times Exhaustion_{i,t}
\times NonInfo_{i,t}.
$$

Prior: positive 1-20 day return.

## 29.3 Stop-Out Fragility (SOF)

$$
SOF_{i,t}
=
\sum_m
p^{distress}_{m,t}
\frac{HoldingDollar_{mi,t}}{ADV_{i,t}}.
$$

This is a state/risk measure, not necessarily a directional factor.

## 29.4 Common Deleveraging Mode Exposure

If $Q_1$ is the dominant manager liquidation mode:

$$
CDM_{i,t}
=[W_t'Q_1]_i.
$$

Use only when the mode itself receives a negative contemporaneous shock.

---

# 30. Evaluation metrics

Because the event is tactical, quarterly Sharpe alone is a poor diagnostic.

Report:

## Mechanism metrics

- AUC / PR-AUC for future forced-sale labels;
- correlation of $\hat\ell_{m,t}$ with next-quarter sell breadth;
- correlation with implied manager flow;
- monotonicity of actual $\Delta Shares$ versus pressure buckets;
- pressure-regression $R^2$.

## Event-trading metrics

- CAR at 1, 3, 5, 10, 20 days;
- hit rate;
- reversal magnitude from event trough;
- drawdown before entry;
- turnover;
- capacity / ADV;
- beta/sector exposures.

## Portfolio metrics

- gross and net Sharpe;
- max DD;
- skew;
- turnover;
- factor alpha;
- correlation with `distress_mom`, `new_conviction` and the existing combo.

The best outcome may not be a standalone high-Sharpe factor. It may be an **entry-timing overlay** for the existing distress machinery.

---

# 31. Most important reconciliation with the current `distress_mom`

This project should explicitly test whether the following decomposition is true:

$$
ObservedReturn
=
InformationComponent
+TemporaryForcedFlowComponent.
$$

Suppose the information component is -15% over one year while the forced-flow component is -5% over five days and then recovers +3%.

A quarterly backtest sees mostly continuation.

A tactical daily strategy can still earn the +3% reversal if it enters only after the temporary component peaks.

This is the central research justification.

If no short-horizon rebound exists after correctly identified exhaustion, accept the result: the project's existing conclusion that distressed selling is information-dominated remains the right one.

---

# 32. Recommended experiment ladder

## Experiment 0 - Data sanity

For eligible managers, reconstruct daily synthetic book returns and verify:

- no split/corporate-action artifacts;
- realistic volatility;
- stable drifted weights;
- no future holdings used.

## Experiment 1 - Does synthetic DD predict future selling?

Target:

- implied flow;
- sell breadth;
- pro-rata score.

This is the make-or-break test.

## Experiment 2 - Add covariance/coherence

Compare models:

1. drawdown only;
2. drawdown + pain breadth;
3. + correlation shock;
4. + PCShare;
5. + liquidation-vector alignment.

Require genuine out-of-sample incremental value.

## Experiment 3 - Inverse liquidation model

Estimate daily $\hat\ell_{m,t}$.

Test whether it forecasts:

- next holding reductions;
- next 1-5 day abnormal stock returns.

## Experiment 4 - Exhaustion event study

Define several exhaustion rules without looking at returns after entry.

Plot CAR[-10,+20].

## Experiment 5 - Production factor

Only if the event study is structurally convincing:

- PIT holdings;
- daily rebalance;
- costs;
- impact;
- borrow if short phase is included.

---

# 33. A clean minimum viable implementation

If speed matters, implement this first:

### Manager universe

- hedge-fund-like / active filers;
- moderate-to-high holdings persistence;
- remove obvious passive/index institutions.

### Daily manager stress

$$
Stress_{m,t}
=
-z(DD^{\perp}_{m,t})
+z(PainBreadth_{m,t}).
$$

### Stock pressure

$$
SOF_{i,t}
=
\sum_m
\mathbf1(Stress_{m,t}>2)
\frac{HoldingDollar_{mi}}{ADV_i}.
$$

### Active liquidation check

Require high negative 3-day residual return of the predicted pressure basket.

### Exhaustion

Enter when:

- pressure basket had an extreme prior 3-5 day loss;
- latest residual return turns positive;
- abnormal volume remains elevated or begins to fall.

### Target

Next 1/3/5/10 day factor-neutral returns.

This MVP is crude but can tell within a day or two of coding whether there is any tactical shape worth modeling.

---

# 34. The version I would ultimately build

The production research architecture would be:

```text
PIT 13F ownership matrix W_t
        |
        +------------------------+
        |                        |
        v                        v
synthetic manager PnL      stock factor model
        |                        |
        v                        v
manager distress prior     residual returns r^perp_t
        |                        |
        +-----------+------------+
                    |
                    v
      covariance-whitened inverse problem

        r^perp_t = - A_t l_t + epsilon_t

                    |
                    v
         latent liquidation intensity l_t
                    |
          +---------+----------+
          |                    |
          v                    v
 active pressure          exhaustion detector
   (short/avoid)                |
                               v
                    post-stop reversal score
                               |
                               v
                      sector/beta-neutral book
```

This is a coherent causal research program, not simply another 13F sort.

---

# 35. Priority ranking of the methods

| Priority | Method | Why |
|---|---|---|
| **1** | Synthetic residual DD -> next-quarter forced-sale label | cheapest causal gate; proves the basic premise |
| **2** | Pain breadth + covariance surprise | directly tests the user's "whole book goes down together" idea |
| **3** | Liquidation-vector alignment | distinguishes common market crash from manager-specific unwind |
| **4** | Sparse inverse liquidation model | strongest senior-quant formulation; identifies who is liquidating from stock returns |
| **5** | Exhaustion state / tactical rebound | actual alpha target |
| **6** | HSMM / dynamic state-space | valuable after the simple mechanism is established |
| **7** | Common liquidation eigenmodes | sophisticated extension after daily $\ell_t$ is reliable |

---

# 36. What would make me kill the idea

Kill or materially downgrade the project if any of these happen:

1. synthetic residual drawdown does not predict subsequent broad selling;
2. next-quarter sells are highly stock-specific rather than broad/pro-rata in the relevant manager sample;
3. covariance/alignment features do not separate true future sellers from bad-P&L non-sellers;
4. inferred pressure does not forecast actual reductions in holdings;
5. high-pressure names keep underperforming even after every reasonable exhaustion definition;
6. the effect is entirely explained by market/sector/momentum;
7. the reversal disappears after excluding earnings/news-heavy names or after realistic costs.

A negative result would still be useful: it would reinforce the current project's conclusion that modern distressed 13F selling is predominantly information-bearing rather than a temporary mechanical discount.

---

# 37. Bottom line

The raw idea is good, but the alpha hypothesis should be reformulated.

Do **not** build:

$$
\text{fund drawdown} \rightarrow \text{buy its stocks}.
$$

Build:

$$
\boxed{
\text{synthetic manager drawdown}
\rightarrow
\text{probability of forced liquidation}
\rightarrow
\text{cross-sectional liquidation footprint}
\rightarrow
\text{latent liquidation intensity}
\rightarrow
\text{exhaustion}
\rightarrow
\text{buy the temporary discount}
}
$$

The most differentiated component is the inverse model:

$$
\boxed{
\mathbf r_t^{\perp}=-D_{ADV,t}^{-1}W_t'\boldsymbol\ell_t+\epsilon_t
}
$$

estimated with covariance whitening, nonnegativity, sparsity, and a drawdown-dependent prior.

That formulation uses exactly what is special about the dataset:

- public manager-stock holdings;
- strong holdings persistence;
- daily stock prices;
- real point-in-time filing timestamps;
- the already validated manager-level implied-flow instrument;
- the project's evidence that forced equity reductions are often broad/pro-rata.

It also gives a clean reason why the earlier static network experiment could fail while this one can work: **the network is no longer being asked to predict direction by itself. A live stress shock activates it.**

---

# References and research trail

1. **Agarwal, V.; Aragon, G. O.; Nanda, V.; Wei, K. (2025).** *Anticipatory Trading Against Distressed Mega Hedge Funds*. Review of Financial Studies 38(12), 3626-3672. DOI: 10.1093/rfs/hhaf082. Published paper: https://academic.oup.com/rfs/article/38/12/3626/8277028 . Public working-paper version used for methodological details: https://www.rsm.nl/fileadmin/Faculty-Research/Departments/Finance/PAM_2023/3_Anticipatory_Trading_Vikram_Nanda_1_.pdf

2. **Ben-David, I.; Franzoni, F.; Moussawi, R. (2012).** *Hedge Fund Stock Trading in the Financial Crisis of 2007-2009*. Review of Financial Studies 25(1), 1-54. DOI: 10.1093/rfs/hhr114. https://academic.oup.com/rfs/article/25/1/1/1574411

3. **Coval, J.; Stafford, E. (2007).** *Asset Fire Sales (and Purchases) in Equity Markets*. Journal of Financial Economics 86, 479-512. NBER working-paper version: https://www.nber.org/papers/w11357

4. **Chen, J.; Hanson, S.; Hong, H.; Stein, J. (2008).** *Do Hedge Funds Profit from Mutual-Fund Distress?* NBER Working Paper 13786. https://www.nber.org/papers/w13786

5. **Greenwood, R.; Thesmar, D. (2011).** *Stock Price Fragility*. Journal of Financial Economics 102(3), 471-490. DOI: 10.1016/j.jfineco.2011.06.003. https://www.sciencedirect.com/science/article/abs/pii/S0304405X11001474

6. **Brunnermeier, M. K.; Pedersen, L. H. (2005).** *Predatory Trading*. Journal of Finance 60(4), 1825-1863. Working-paper page: https://www.nber.org/papers/w10755

7. **Current project source.** *Fator de Posicionamento 13F - Conclusoes consolidadas*, 14-16 August 2026. Key internal findings used here: validated implied manager flow; distressed managers' broad selling; pro-rata equity liquidation; static network fragility without a live shock was weak; quarterly fire-sale reversal failed while `distress_mom` continuation was strong.

8. **Oliveira, D. C.; Sandfelder, D.; Fujita, A.; Dong, X.; Cucuringu, M. (2025).** *Tactical Asset Allocation with Macroeconomic Regime Detection*. arXiv:2503.11499v2. Relevant only as a methodological reference for probabilistic state/regime modeling and transition structures, not as evidence for the 13F stop-out mechanism.
