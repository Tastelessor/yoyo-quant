"""策略 × 股票池矩阵回测。

对每组 (pool_group, strategy) 运行完整回测管道，收集绩效指标，
用于对比不同策略在不同板块/行业的表现。
"""

from __future__ import annotations

import logging
import warnings

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable
from src.strategies.registry import get_strategy

logger = logging.getLogger(__name__)


def run_matrix(
    pool_groups: dict[str, list[str]],
    strategy_specs: list[dict],
    data: pd.DataFrame,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
) -> pd.DataFrame:
    """策略 × 股票池交叉回测，每个组合运行一遍完整管道。

    Parameters
    ----------
    pool_groups : dict
        命名股票池，如 ``{"银行": ["601939", "601398"], "科技": ["688981"]}``。
    strategy_specs : list[dict]
        策略规格列表，每项含 ``name`` 和可选的 ``params``::

            [{"name": "reversed_gtja_vwap"},
             {"name": "gtja_momentum", "params": {"rebalance": 10, "top_n": 5}}]

    data : DataFrame
        全量 OHLCV 数据，含 limit_up/limit_down/is_suspended 标注列。
    capital : float
        初始资金。
    max_weight : float
        单只股票仓位上限。

    Returns
    -------
    DataFrame
        每行一个 (strategy, pool) 组合的绩效指标。
    """
    if not pool_groups or not strategy_specs:
        return pd.DataFrame()

    rows = []
    for pool_name, pool_codes in pool_groups.items():
        pool_data = data[data["code"].isin(pool_codes)]
        if pool_data.empty:
            warnings.warn(
                f"Pool {pool_name!r} is empty or has no matching rows in data",
                stacklevel=2,
            )
            for spec in strategy_specs:
                rows.append(_nan_row(spec["name"], pool_name))
            continue

        prices = pool_data[["date", "code", "close"]]

        for spec in strategy_specs:
            strategy_name = spec["name"]
            params = spec.get("params") or {}

            try:
                strategy = get_strategy(strategy_name, **params)
            except KeyError:
                warnings.warn(
                    f"Unknown strategy: {strategy_name!r}",
                    stacklevel=2,
                )
                rows.append(_nan_row(strategy_name, pool_name))
                continue

            try:
                signals = strategy.generate_signal(pool_data)
                filtered = filter_tradable(pool_data, signals)
                final = enforce_t1(filtered)
                positions = equal_weight(final, prices, capital=capital)
                positions = apply_position_limit(positions, max_weight=max_weight)
                engine = BacktestEngine(capital=capital)
                result = engine.run(positions, prices)
                metrics = result["metrics"]
            except Exception:
                logger.warning(
                    "Matrix run failed for strategy=%s pool=%s",
                    strategy_name,
                    pool_name,
                    exc_info=True,
                )
                metrics = _zero_metrics()

            rows.append({
                "strategy": strategy_name,
                "pool": pool_name,
                **metrics,
            })

    return pd.DataFrame(rows)


def _nan_row(strategy: str, pool: str) -> dict:
    """构造 NaN metrics 行（pool 为空或策略不存在）。"""
    return {
        "strategy": strategy,
        "pool": pool,
        "total_return": float("nan"),
        "annual_return": float("nan"),
        "sharpe_ratio": float("nan"),
        "max_drawdown": float("nan"),
        "win_rate": float("nan"),
        "trade_count": float("nan"),
    }


def _zero_metrics() -> dict:
    """构造零值 metrics（策略执行异常）。"""
    return {
        "total_return": 0.0,
        "annual_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "trade_count": 0,
    }


def pivot_matrix(
    results: pd.DataFrame,
    metric: str = "sharpe_ratio",
) -> pd.DataFrame:
    """透视成 pool × strategy 矩阵，方便画热力图。

    Parameters
    ----------
    results : DataFrame
        ``run_matrix`` 的输出。
    metric : str
        要透视的指标列名。

    Returns
    -------
    DataFrame
        index=pool, columns=strategy, values=metric。
    """
    if results.empty:
        return pd.DataFrame()
    return results.pivot(index="pool", columns="strategy", values=metric)


def best_per_pool(
    results: pd.DataFrame,
    metric: str = "sharpe_ratio",
) -> pd.DataFrame:
    """每个股票池中指定指标最优的策略。

    Parameters
    ----------
    results : DataFrame
        ``run_matrix`` 的输出。
    metric : str
        排序依据的指标名。

    Returns
    -------
    DataFrame
        每行是 (pool, strategy, metric_value)。
    """
    if results.empty:
        return pd.DataFrame()
    idx = results.groupby("pool")[metric].idxmax()
    return results.loc[idx, ["pool", "strategy", metric]].reset_index(drop=True)
