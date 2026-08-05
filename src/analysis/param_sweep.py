"""参数敏感性分析：网格搜索 + 结果排序。

遍历参数空间，对每组参数跑完整回测管道，输出绩效指标 DataFrame。
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Callable

import pandas as pd

from backtest.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def build_grid(param_grid: dict[str, list]) -> list[dict]:
    """生成参数空间的所有组合。

    Parameters
    ----------
    param_grid : dict
        参数名到候选值列表的映射，如 {"window": [10, 20], "num_std": [1.5, 2.0]}。

    Returns
    -------
    list[dict]
        每个元素是一组参数，如 [{"window": 10, "num_std": 1.5}, ...]。
    """
    if not param_grid:
        return []
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def run_sweep(
    signal_gen: Callable,
    param_grid: dict[str, list],
    data: pd.DataFrame,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
) -> pd.DataFrame:
    """遍历参数空间，对每组参数执行完整回测管道。

    管道：signal_gen → filter_tradable → enforce_t1 → equal_weight
          → apply_position_limit → BacktestEngine → metrics

    Parameters
    ----------
    signal_gen : callable
        信号生成函数，签名 (data, **params)
        -> DataFrame(date, code, signal, confidence)。
    param_grid : dict
        参数名到候选值列表的映射。
    data : DataFrame
        行情数据（含 limit_up, limit_down, is_suspended 等标注列）。
    capital : float
        初始资金。
    max_weight : float
        单只股票仓位上限。

    Returns
    -------
    DataFrame
        每行一组参数 + 对应的绩效指标。
    """
    grid = build_grid(param_grid)
    if not grid:
        return pd.DataFrame()

    rows = []
    for params in grid:
        try:
            metrics = _run_single(signal_gen, data, params, capital, max_weight)
        except Exception as e:
            logger.warning("Sweep failed for %s: %s", params, e)
            metrics = {
                "total_return": 0.0,
                "annual_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
            }
        row = {**params, **metrics}
        rows.append(row)

    return pd.DataFrame(rows)


def _run_single(
    signal_gen: Callable,
    data: pd.DataFrame,
    params: dict,
    capital: float,
    max_weight: float,
) -> dict:
    """执行单组参数的完整回测管道，返回绩效指标。"""
    signals = signal_gen(data, **params)
    result = run_pipeline(signals, data, capital, max_weight=max_weight)
    return result["metrics"]


def best_result(
    results: pd.DataFrame,
    metric: str = "sharpe_ratio",
) -> pd.Series:
    """从 sweep 结果中选出指定指标最优的一行。

    Parameters
    ----------
    results : DataFrame
        run_sweep 的输出。
    metric : str
        排序依据的指标名，默认 sharpe_ratio。

    Returns
    -------
    Series
        最优行。空 DataFrame 返回空 Series。
    """
    if results.empty:
        return pd.Series(dtype=float)
    idx = results[metric].idxmax()
    return results.loc[idx]
