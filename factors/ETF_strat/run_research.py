"""Build filing-time ETF signals, run shared backtests and write the report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
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
    forward_ic,
    run_shared_backtest,
)
from etf_strategies.config import ResearchConfig  # noqa: E402
from etf_strategies.market import MarketPanels  # noqa: E402
from etf_strategies.panel import (  # noqa: E402
    build_event_panel,
    build_manager_updates,
    expand_daily_fragility,
    initialize_manager_etf_state,
)
from etf_strategies.pit import PITQuarterStore  # noqa: E402
from etf_strategies.signals import ABLATION_SIGNALS, PRIMARY_SIGNALS  # noqa: E402
from etf_strategies.universe import build_universe_audit, load_verified_master  # noqa: E402


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} - {message}", flush=True)


def _paths() -> dict[str, Path]:
    legacy = FACTORS / "etf-positioninig-strats-codex"
    return {
        "master": HERE / "data" / "etf_universe_confirmed.csv",
        "candidate_audit": legacy / "data" / "fund_candidate_audit.csv",
        "etf_adjusted": HERE / "data" / "etf_prices_adjusted.csv.gz",
        "etf_raw": HERE / "data" / "etf_prices_raw.csv.gz",
        "etf_volume": HERE / "data" / "etf_volume.csv.gz",
        "common_adjusted": FACTORS / "data" / "prices_3927tk_20120601_20260816.csv",
        "common_map": ROOT / "notebooks" / "data" / "cm_map_wide.csv",
        "benchmark": FACTORS / "data" / "bench_SPY_IRX_20120601_20260816.csv",
        "quarters": FACTORS / "general_plan" / "data" / "quarters",
    }


def write_report(
    config: ResearchConfig,
    universe_summary: pd.DataFrame,
    coverage: pd.DataFrame,
    events: pd.DataFrame,
    performance: pd.DataFrame,
    ic: pd.DataFrame,
    out_path: Path,
) -> None:
    primary_perf = performance[
        performance["fee_bps"].eq(config.primary_cost_bps)
        & performance["sample"].eq("full")
        & performance["strategy"].isin(PRIMARY_SIGNALS)
    ].copy()
    cols = ["strategy", "ann_return", "ann_vol", "sharpe", "max_drawdown", "ann_turnover"]
    primary_perf = primary_perf[[c for c in cols if c in primary_perf]].round(4)
    ic21 = ic[ic["horizon_days"].eq(21) & ic["signal_name"].isin(PRIMARY_SIGNALS)].round(4)
    gross = performance[
        performance["fee_bps"].eq(0)
        & performance["sample"].eq("full")
        & performance["strategy"].isin(PRIMARY_SIGNALS)
    ][["strategy", "ann_return"]].rename(columns={"ann_return": "gross_ann_return"})
    verdict = primary_perf.merge(
        ic21[["signal_name", "mean_ic", "ic_t_nw"]],
        left_on="strategy", right_on="signal_name", how="left",
    )
    verdict = verdict.merge(gross, on="strategy", how="left")
    subperiod_returns = performance[
        performance["fee_bps"].eq(config.primary_cost_bps)
        & performance["strategy"].isin(PRIMARY_SIGNALS)
        & performance["sample"].isin(["pre_2022", "post_2021"])
    ].pivot(index="strategy", columns="sample", values="ann_return")
    subperiod_sharpes = performance[
        performance["fee_bps"].eq(config.primary_cost_bps)
        & performance["strategy"].isin(PRIMARY_SIGNALS)
        & performance["sample"].isin(["pre_2022", "post_2021"])
    ].pivot(index="strategy", columns="sample", values="sharpe").rename(
        columns={"pre_2022": "pre_2022_sharpe", "post_2021": "post_2021_sharpe"}
    )
    verdict = verdict.join(subperiod_returns, on="strategy").join(subperiod_sharpes, on="strategy")
    for col in ("pre_2022", "post_2021"):
        if col not in verdict:
            verdict[col] = np.nan
    for col in ("pre_2022_sharpe", "post_2021_sharpe"):
        if col not in verdict:
            verdict[col] = np.nan
    verdict["verdict"] = "reprovado"
    suggestive = (
        verdict["ic_t_nw"].ge(1.64)
        & verdict["mean_ic"].gt(0)
        & verdict["gross_ann_return"].gt(0)
    )
    verdict.loc[suggestive, "verdict"] = "sugestivo; não aprovado"
    stable = (
        verdict["sharpe"].ge(config.min_full_net_sharpe)
        & verdict["ic_t_nw"].ge(config.min_ic_tstat)
        & verdict["pre_2022_sharpe"].ge(config.min_subperiod_net_sharpe)
        & verdict["post_2021_sharpe"].ge(config.min_subperiod_net_sharpe)
    )
    verdict.loc[stable, "verdict"] = "aprovado"
    verdict_table = verdict[
        [
            "strategy", "gross_ann_return", "ann_return", "sharpe", "mean_ic", "ic_t_nw",
            "pre_2022", "pre_2022_sharpe", "post_2021", "post_2021_sharpe", "verdict",
        ]
    ].rename(columns={"ann_return": "net_ann_return_10bps"}).round(4)
    approved = verdict.loc[verdict["verdict"].eq("aprovado"), "strategy"].tolist()
    strongest = verdict.sort_values("sharpe", ascending=False).iloc[0] if not verdict.empty else None
    if approved:
        executive = (
            f"Passaram o gate de robustez: {', '.join(f'`{name}`' for name in approved)}. "
            "A aprovação exige Sharpe líquido cheio, IC e Sharpe mínimo nos dois subperíodos."
        )
    elif strongest is not None:
        executive = (
            "**Nenhuma estratégia foi aprovada como alpha robusto.** "
            f"A melhor hipótese primária no período cheio foi `{strongest['strategy']}` "
            f"(Sharpe líquido {strongest['sharpe']:.2f}), mas falhou no gate de estabilidade. "
            "A decomposição de universo, baseline causal e fatores de mercado está em "
            "`results/candidate_diagnostics/REPORT.md`."
        )
    else:
        executive = "**Nenhuma estratégia produziu carteira elegível.**"
    u = universe_summary.iloc[0]
    lines = [
        "# ETF positioning — resultado point-in-time",
        "",
        "## Conclusão executiva",
        "",
        "Foram implementadas as cinco hipóteses do memo com atualização gestor a gestor na data real do filing. "
        + executive + " O universo negociável usa somente ETFs de ações com CUSIP/ticker verificados e "
        "preços históricos pinados.",
        "",
        "## Universo",
        "",
        f"- candidatos marcados como `fund` na 13F: {int(u['candidate_instruments']):,};",
        f"- ETFs de ações verificados no universo primário: {int(u['verified_equity_etfs']):,};",
        f"- cobertura histórica em valor da triagem `fund`: {u['verified_value_coverage']:.1%};",
        "- candidatos sem verificação permanecem em quarentena; `fund` não é sinônimo de ETF;",
        "- identidade do ETF é estática, mas elegibilidade de preço/liquidez é calculada apenas com dados disponíveis no evento.",
        "",
        "Essa é uma escolha deliberada de precisão sobre recall. Ampliar por regex misturaria CEFs, BDCs e ações comuns "
        "e contaminaria adoção/consenso. A sensibilidade completa está em `data/universe_candidate_audit.csv`.",
        "",
        "## Relógio e construção",
        "",
        "- restatements substituem o livro por CIK; `NEW HOLDINGS` posterior é aditivo; CIKs irmãos só são somados depois;",
        "- como o parquet preserva data, não hora, o livro selecionado do gestor é liberado conservadoramente na última data de filing selecionada;",
        "- `Trade` e churn usam pesos driftados por total return; posições sem ticker recebem SPY apenas no denominador de drift;",
        "- entrada ocorre no primeiro pregão após o filing e o motor compartilhado ainda aplica `weights.shift(1)` ao P&L;",
        "- custos principais: 10 bps one-way, com escada 0/5/10/20 bps.",
        "",
        f"Eventos materializados: {events.loc[events['signal_name'].eq('sticky_quality'), 'available_date'].nunique():,} "
        f"datas de filing e {events['available_date'].nunique():,} datas totais após incluir gatilhos diários de fragilidade, "
        f"em {events['period_end'].nunique():,} trimestres. Cobertura mediana de retorno no drift: "
        f"{coverage['return_mapping_coverage'].median():.1%} do valor anterior no universo bruto e "
        f"{coverage['return_mapping_coverage_selected'].median():.1%} entre gestores usados nos sinais de churn.",
        "",
        f"O cutoff de cobertura por gestor é {config.min_manager_return_coverage:.0%}. A sensibilidade em "
        "`data/manager_coverage_sensitivity.csv` mostra por que 80% não foi adotado: o cross-section mediano "
        "cai para cerca de 69 gestores, abaixo do mínimo de 100 releases; 50% preserva mediana próxima de 1,8 mil. "
        "A cobertura imperfeita continua sendo uma limitação, não uma variável escondida.",
        "",
        "## Hipóteses primárias — backtest LS",
        "",
        primary_perf.to_markdown(index=False) if not primary_perf.empty else "Sem portfolios elegíveis.",
        "",
        "## Decisão e estabilidade",
        "",
        verdict_table.to_markdown(index=False) if not verdict_table.empty else "Sem decisão.",
        "",
        f"Gate: Sharpe líquido cheio ≥ {config.min_full_net_sharpe:.2f}, t(IC 21d) ≥ "
        f"{config.min_ic_tstat:.2f} e Sharpe líquido ≥ {config.min_subperiod_net_sharpe:.2f} "
        "tanto pré-2022 quanto pós-2021.",
        "",
        "## IC de 21 pregões",
        "",
        ic21.to_markdown(index=False) if not ic21.empty else "Sem eventos suficientes.",
        "",
        "## Interpretação das cinco ideias",
        "",
        "1. `sticky_quality`: demanda líquida em peso, ponderada por 1 menos o percentil do churn suavizado em quatro trimestres. "
        "`sticky_raw` e `sticky_specificity` são as ablações.",
        "2. `double_down_specific`: compras por gestores sticky após underperformance residual do ETF. O primário exclui broad ETFs; "
        "`double_down_all` testa a restrição.",
        "3. `abnormal_adoption`: mudança no residual de log-breadth após controlar ownership divulgado, momentum, vol, beta, ADV, preço, idade e estilo. "
        "`abnormal_level` e new-holder breadth são ablações.",
        "4. `ccp`: conviction dentro do ETF sleeve × quality × persistência consecutiva truncada em quatro trimestres; consensus puro é a comparação.",
        "5. Fragilidade nunca é tratada como alpha incondicional: `fragility_stress` protege contra holders de alto churn em stress de mercado e "
        "`fragility_reversal` compra fragilidade apenas após choque residual negativo.",
        "",
        "## Limitações que permanecem",
        "",
        "- o universo verificado privilegia grandes ETFs sobreviventes e cobre poucos produtos temáticos;",
        "- 13F mostra holdings long trimestrais, não intenção, short, criação/resgate primário nem AUM econômico total do gestor;",
        "- timestamps intradiários foram perdidos no parquet e por isso a implementação atrasa, mas nunca antecipa, emendas;",
        "- eventos de filing próximos se sobrepõem; ICs usam Newey–West, mas devem ser lidos junto com estabilidade temporal e turnover;",
        "- nenhum metasignal é promovido antes de componentes individuais mostrarem robustez fora da amostra.",
        "",
        f"Config fingerprint: `{config.fingerprint()}`.",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(smoke: bool = False) -> None:
    cfg = ResearchConfig(
        start_period="2024-06-30" if smoke else ResearchConfig.start_period,
        min_released_managers=30 if smoke else ResearchConfig.min_released_managers,
    )
    paths = _paths()
    data_dir = HERE / ("data_smoke" if smoke else "data")
    result_dir = HERE / ("results_smoke" if smoke else "results")
    data_dir.mkdir(exist_ok=True)
    result_dir.mkdir(exist_ok=True)

    master = load_verified_master(paths["master"], equity_only=True)
    master["is_specific"] = master["etf_style"].isin(cfg.specific_styles)
    candidate_audit, universe_summary = build_universe_audit(paths["candidate_audit"], master)
    candidate_audit.to_csv(data_dir / "universe_candidate_audit.csv", index=False)
    universe_summary.to_csv(data_dir / "universe_summary.csv", index=False)
    master.to_csv(data_dir / "etf_universe_verified.csv", index=False)
    log(
        f"universe: {master['ticker'].nunique():,} verified equity ETF products "
        f"({len(master):,} CUSIP/FIGI aliases); candidates remain quarantined"
    )

    market = MarketPanels(
        paths["etf_adjusted"], paths["etf_raw"], paths["etf_volume"],
        paths["common_adjusted"], paths["common_map"], paths["benchmark"], master,
    )
    store = PITQuarterStore(paths["quarters"])
    all_periods = [p for p in store.quarters() if p <= market.prices.index.max()]
    start = pd.Timestamp(cfg.start_period)
    current_periods = [p for p in all_periods if p >= start]
    if smoke:
        current_periods = current_periods[-8:]
    if not current_periods:
        raise RuntimeError("no test periods")
    first_idx = all_periods.index(current_periods[0])
    if first_idx == 0:
        raise RuntimeError("a predecessor quarter is required")
    previous_period = all_periods[first_idx - 1]
    previous = store.snapshot(previous_period, previous_period + pd.Timedelta(days=cfg.snapshot_lag_days))
    previous_state, previous_stats = initialize_manager_etf_state(previous, master, cfg)
    previous_abnormal = pd.Series(
        np.nan, index=master["ticker"].drop_duplicates(), dtype=float
    )
    churn_history: dict[str, list[float]] = {}
    event_parts, manager_parts, coverage_rows = [], [], []

    for period in current_periods:
        current = store.snapshot(period, period + pd.Timedelta(days=cfg.snapshot_lag_days))
        instrument_returns = market.instrument_total_returns(previous_period, period)
        residual = market.residual_quarter_return(previous_period, period)
        updates, next_state, metrics, coverage = build_manager_updates(
            current, previous, previous_state, previous_stats, master,
            instrument_returns, market.spy_period_return(previous_period, period),
            churn_history, residual, cfg,
        )
        events, next_abnormal = build_event_panel(
            period, updates, previous_state, previous_abnormal, market, master, cfg
        )
        if not events.empty:
            event_parts.append(events)
        metrics = metrics.reset_index().assign(period_end=period)
        manager_parts.append(metrics)
        coverage_rows.append({"period_end": period, **coverage, "n_events": events["available_date"].nunique()})
        log(
            f"{period.date()} managers={int(coverage['n_current_managers']):,} "
            f"eligible={int(coverage['n_eligible_managers']):,} events={events['available_date'].nunique():,} "
            f"drift coverage={coverage['return_mapping_coverage']:.1%}"
        )
        previous_period, previous = period, current
        previous_state, previous_stats = next_state, metrics.set_index("filer_id")
        previous_abnormal = next_abnormal

    events = pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    if events.empty:
        raise RuntimeError("no filing-time signal events were produced")
    events = expand_daily_fragility(events, market, master)
    managers = pd.concat(manager_parts, ignore_index=True)
    coverage = pd.DataFrame(coverage_rows)
    events.to_parquet(data_dir / "signal_events.parquet", index=False)
    managers.to_parquet(data_dir / "manager_quality.parquet", index=False)
    coverage.to_csv(data_dir / "coverage_by_quarter.csv", index=False)
    sensitivity_parts = []
    for threshold in (0.40, 0.50, 0.60, 0.70, 0.80):
        g = managers[
            managers["eligible"] & managers["return_mapping_coverage"].ge(threshold)
        ].groupby("period_end").size().rename("n_managers").reset_index()
        g["min_return_coverage"] = threshold
        sensitivity_parts.append(g)
    pd.concat(sensitivity_parts, ignore_index=True).to_csv(
        data_dir / "manager_coverage_sensitivity.csv", index=False
    )

    universe = build_tradable_universe(market, Filters, cfg)
    signal_names = [*PRIMARY_SIGNALS, *ABLATION_SIGNALS]
    performance, returns, _ = run_shared_backtest(
        events, market, universe, signal_names, Indicator, Portfolio, Backtest, cfg, master
    )
    ic = forward_ic(events, market.prices, cfg.forward_horizons_days, master)
    performance.to_csv(result_dir / "backtest_summary.csv", index=False)
    returns.to_csv(result_dir / "backtest_returns.csv", index=False)
    ic.to_csv(result_dir / "forward_ic.csv", index=False)
    (result_dir / "run_config.json").write_text(
        json.dumps({**cfg.__dict__, "fingerprint": cfg.fingerprint()}, indent=2, default=list),
        encoding="utf-8",
    )
    write_report(cfg, universe_summary, coverage, events, performance, ic, result_dir / "REPORT.md")
    log(f"done | config={cfg.fingerprint()} | report={result_dir / 'REPORT.md'}")


def rerun_backtest(smoke: bool = False) -> None:
    """Re-run portfolio mechanics from already materialized PIT events."""

    cfg = ResearchConfig(
        start_period="2024-06-30" if smoke else ResearchConfig.start_period,
        min_released_managers=30 if smoke else ResearchConfig.min_released_managers,
    )
    paths = _paths()
    data_dir = HERE / ("data_smoke" if smoke else "data")
    result_dir = HERE / ("results_smoke" if smoke else "results")
    master = load_verified_master(paths["master"], equity_only=True)
    master["is_specific"] = master["etf_style"].isin(cfg.specific_styles)
    market = MarketPanels(
        paths["etf_adjusted"], paths["etf_raw"], paths["etf_volume"],
        paths["common_adjusted"], paths["common_map"], paths["benchmark"], master,
    )
    events = pd.read_parquet(data_dir / "signal_events.parquet")
    universe = build_tradable_universe(market, Filters, cfg)
    performance, returns, _ = run_shared_backtest(
        events, market, universe, [*PRIMARY_SIGNALS, *ABLATION_SIGNALS],
        Indicator, Portfolio, Backtest, cfg, master,
    )
    ic = forward_ic(events, market.prices, cfg.forward_horizons_days, master)
    performance.to_csv(result_dir / "backtest_summary.csv", index=False)
    returns.to_csv(result_dir / "backtest_returns.csv", index=False)
    ic.to_csv(result_dir / "forward_ic.csv", index=False)
    write_report(
        cfg,
        pd.read_csv(data_dir / "universe_summary.csv"),
        pd.read_csv(data_dir / "coverage_by_quarter.csv"),
        events,
        performance,
        ic,
        result_dir / "REPORT.md",
    )
    log(f"backtest-only done | report={result_dir / 'REPORT.md'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--backtest-only", action="store_true")
    args = parser.parse_args()
    if args.backtest_only:
        rerun_backtest(smoke=args.smoke)
    else:
        run(smoke=args.smoke)
