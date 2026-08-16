"""Evaluate the strongest ETF-positioning candidate and its causal ablations."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FACTORS = ROOT / "factors"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FACTORS))

from backtest import Backtest  # noqa: E402
from filters import Filters  # noqa: E402
from indicator import Indicator  # noqa: E402
from portfolio import Portfolio  # noqa: E402
from etf_strategies.backtesting import (  # noqa: E402
    build_tradable_universe,
    forward_ic_detail,
    run_shared_backtest,
    summarize_forward_ic,
)
from etf_strategies.config import ResearchConfig  # noqa: E402
from etf_strategies.diagnostics import (  # noqa: E402
    calendar_returns,
    controlled_signal_events,
    factor_regressions,
    paired_ic_diagnostics,
    paired_return_diagnostics,
    portfolio_exposure_diagnostics,
    scoped_signal_events,
)
from etf_strategies.market import MarketPanels  # noqa: E402
from etf_strategies.universe import load_verified_master  # noqa: E402
from run_research import _paths, log  # noqa: E402


def write_candidate_report(result_dir: Path, primary_cost_bps: int = 10) -> None:
    """Write the causal verdict from already persisted diagnostic tables."""

    perf = pd.read_csv(result_dir / "candidate_backtest_summary.csv")
    ic = pd.read_csv(result_dir / "candidate_forward_ic.csv")
    inc_ret = pd.read_csv(result_dir / "incremental_return_tests.csv")
    inc_ic = pd.read_csv(result_dir / "incremental_ic_tests.csv")
    regressions = pd.read_csv(result_dir / "factor_regressions.csv")
    exposures = pd.read_csv(result_dir / "portfolio_exposures.csv")

    net = perf[perf["fee_bps"].eq(primary_cost_bps)].pivot(
        index="strategy", columns="sample", values=["ann_return", "sharpe"]
    )
    net.columns = [f"{metric}_{sample}" for metric, sample in net.columns]
    net = net.reset_index().sort_values("sharpe_full", ascending=False)
    ic21 = ic[ic["horizon_days"].eq(21)].sort_values("mean_ic", ascending=False)
    attribution = regressions[regressions["sample"].isin(["full", "post_2021"])][
        [
            "strategy", "sample", "annual_alpha_arithmetic", "market_beta",
            "small_tilt", "tech_tilt", "r_squared",
        ]
    ]
    inc_ret = inc_ret[
        [
            "structural", "baseline", "sample", "return_correlation",
            "incremental_ann_return", "incremental_sharpe", "incremental_mean_t_nw",
        ]
    ]
    inc_ic21 = inc_ic[inc_ic["horizon_days"].eq(21)]

    lines = [
        "# Diagnóstico causal — família CCP/consenso",
        "",
        "## Conclusão",
        "",
        "**Não foi encontrado um fator de ETF aprovado como alpha robusto.** O CCP original parece forte "
        "na amostra cheia, mas concentra o resultado antes de 2022, tem correlação de 0,95 com o consenso "
        "simples e carrega beta de mercado material. A restrição a ETFs específicos destrói o retorno. "
        "O universo passivo melhora o consenso cheio, mas o alpha residual pós-2021 continua negativo. "
        "A residualização point-in-time reduz as exposições, porém não restaura estabilidade recente.",
        "",
        "A evidência que permanece é mais estreita: CCP melhora o IC de curto/médio prazo sobre consenso "
        "no universo amplo, mas o ganho incremental de carteira não é estatisticamente confiável. Isso é "
        "uma pista de ranking, não um motor causal validado.",
        "",
        "## Status das especificações (10 bps one-way)",
        "",
        net.round(4).to_markdown(index=False),
        "",
        "## IC de 21 pregões",
        "",
        ic21.round(4).to_markdown(index=False),
        "",
        "## CCP menos baseline de consenso",
        "",
        inc_ret.round(4).to_markdown(index=False),
        "",
        "### IC incremental pareado — 21 pregões",
        "",
        inc_ic21.round(4).to_markdown(index=False),
        "",
        "## Atribuição sistemática",
        "",
        attribution.round(4).to_markdown(index=False),
        "",
        "## Construção das pernas",
        "",
        exposures.round(4).to_markdown(index=False),
        "",
        "## Consistência com a literatura",
        "",
        "- Angelini, Iqbal e Jivraj documentam conviction + consensus para ações de hedge funds e destacam "
        "a seleção de gestores de horizonte longo; isso justifica o baseline, mas não garante a extensão a ETFs: "
        "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3459526",
        "- Rhinesmith documenta doubling down em posições acionárias e exige controles contra reversal/best ideas; "
        "o resultado negativo aqui mostra que a transposição ao ETF sleeve não se confirmou: "
        "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2491636",
        "- Khomyn, Putniņš e Zoican ligam liquidez do ETF a clientelas de horizonte curto; isso sustenta usar churn "
        "como característica do holder, não interpretar liquidez/consenso como alpha por si só: "
        "https://academic.oup.com/rfs/article/37/10/3092/7738093",
        "- Cella, Ellul e Giannetti encontram amplificação e reversão durante stress para ativos dominados por "
        "investidores de horizonte curto; por isso fragilidade foi testada condicionalmente, não como long contínuo: "
        "https://academic.oup.com/rfs/article/26/7/1607/1608561",
        "",
        "## Leitura correta",
        "",
        "- `ccp` e `consensus` são hipóteses pré-especificadas no memo;",
        "- `*_specific` e o split passivo são restrições de universo antecipadas pelo memo/projeto;",
        "- `*_controlled` é diagnóstico exploratório posterior, residualizado por características públicas "
        "na data do filing; não é holdout intocado;",
        "- nenhum resultado autoriza escolher hiperparâmetros ou promover um metasignal sem uma nova amostra "
        "fora do período usado aqui.",
    ]
    (result_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    cfg = ResearchConfig()
    paths = _paths()
    result_dir = HERE / "results" / "candidate_diagnostics"
    result_dir.mkdir(parents=True, exist_ok=True)

    master = load_verified_master(paths["master"], equity_only=True)
    master["is_specific"] = master["etf_style"].isin(cfg.specific_styles)
    market = MarketPanels(
        paths["etf_adjusted"], paths["etf_raw"], paths["etf_volume"],
        paths["common_adjusted"], paths["common_map"], paths["benchmark"], master,
    )
    events = pd.read_parquet(HERE / "data" / "signal_events.parquet")
    variants = pd.concat(
        [
            scoped_signal_events(
                events, master, "ccp", "ccp_specific", cfg.specific_styles
            ),
            scoped_signal_events(
                events, master, "consensus", "consensus_specific", cfg.specific_styles
            ),
            scoped_signal_events(
                events, master, "ccp", "ccp_passive",
                require_column="is_passive_equity_etf",
            ),
            scoped_signal_events(
                events, master, "consensus", "consensus_passive",
                require_column="is_passive_equity_etf",
            ),
        ],
        ignore_index=True,
    )
    log("building public-characteristic controlled scores")
    controlled = controlled_signal_events(
        events,
        master,
        market,
        {"ccp": "ccp_controlled", "consensus": "consensus_controlled"},
    )
    candidate_events = pd.concat(
        [
            events[events["signal_name"].isin(["ccp", "consensus"])],
            variants,
            controlled,
        ],
        ignore_index=True,
    )
    names = [
        "ccp", "consensus",
        "ccp_specific", "consensus_specific",
        "ccp_passive", "consensus_passive",
        "ccp_controlled", "consensus_controlled",
    ]
    universe = build_tradable_universe(market, Filters, cfg)
    performance, returns, portfolios = run_shared_backtest(
        candidate_events, market, universe, names,
        Indicator, Portfolio, Backtest, cfg, master,
    )
    log("candidate portfolios complete; computing event ICs")
    raw_ic = forward_ic_detail(
        candidate_events, market.prices, cfg.forward_horizons_days, master
    )
    ic = summarize_forward_ic(raw_ic)
    pairs = (
        ("ccp", "consensus"),
        ("ccp_specific", "consensus_specific"),
        ("ccp_passive", "consensus_passive"),
        ("ccp_controlled", "consensus_controlled"),
    )

    performance.to_csv(result_dir / "candidate_backtest_summary.csv", index=False)
    returns.to_csv(result_dir / "candidate_backtest_returns.csv", index=False)
    ic.to_csv(result_dir / "candidate_forward_ic.csv", index=False)
    paired_return_diagnostics(returns, pairs, cfg.primary_cost_bps).to_csv(
        result_dir / "incremental_return_tests.csv", index=False
    )
    paired_ic_diagnostics(raw_ic, pairs).to_csv(
        result_dir / "incremental_ic_tests.csv", index=False
    )
    portfolio_exposure_diagnostics(portfolios).to_csv(
        result_dir / "portfolio_exposures.csv", index=False
    )
    factor_regressions(returns, market.returns, cfg.primary_cost_bps).to_csv(
        result_dir / "factor_regressions.csv", index=False
    )
    calendar_returns(returns, cfg.primary_cost_bps).to_csv(
        result_dir / "calendar_returns.csv", index=False
    )
    write_candidate_report(result_dir, cfg.primary_cost_bps)
    log(f"candidate diagnostics done | {result_dir}")


if __name__ == "__main__":
    main()
