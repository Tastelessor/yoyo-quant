"""Continuous backtest — single-pass, no train/test split.

For strategies with fixed parameters (no model fitting), run the full
signal → allocate → backtest pipeline in one pass over the entire dataset.
Produces a realistic equity curve without walk-forward windowing artifacts.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from src.backtest.engine import TradingCost
from src.backtest.pipeline import run_pipeline


def compute_continuous_metrics(equity_curve: pd.DataFrame, capital: float) -> dict:
    """Compute overall metrics from a continuous equity curve.

    Parameters
    ----------
    equity_curve : DataFrame
        Columns: date, equity.
    capital : float
        Initial capital.

    Returns
    -------
    dict
        total_return, annual_return, sharpe_ratio, max_drawdown.
    """
    if equity_curve.empty:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        }

    eq = equity_curve.sort_values("date").reset_index(drop=True)
    eq_vals = eq["equity"].values

    total_return = (eq_vals[-1] - capital) / capital if capital > 0 else 0.0
    n_days = len(eq_vals)
    if n_days > 1 and total_return > -1:
        annual_return = (1 + total_return) ** (252 / n_days) - 1
    else:
        annual_return = 0.0

    daily_returns = np.diff(eq_vals) / eq_vals[:-1]
    daily_rf = 0.03 / 252
    excess = daily_returns - daily_rf
    std = excess.std()
    if len(excess) > 1 and std > 1e-10:
        sharpe = float(excess.mean() / std * np.sqrt(252))
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(eq_vals)
    drawdown = (eq_vals - peak) / np.where(peak > 0, peak, 1)
    max_drawdown = float(abs(drawdown.min()))

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
    }


def continuous_backtest(
    data: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame], pd.DataFrame],
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    exposure_fn: Callable[[pd.DatetimeIndex], pd.Series] | None = None,
    industry_map: dict[str, str] | None = None,
    max_industry_weight: float = 0.30,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    atr_stop_loss: dict | None = None,
    trading_cost: TradingCost | None = None,
    circuit_breaker: object | None = None,
    dead_zone: float = 0.0,
    rebalance_days: int | None = None,
) -> dict:
    """Run a single-pass continuous backtest.

    Unlike walk-forward, the signal function is called once on the full
    dataset. No train/test split, no parameter re-estimation.

    Parameters
    ----------
    data : DataFrame
        Stock data with columns: date, code, open, high, low, close, volume.
    signal_fn : callable
        ``(data) -> signals_df``. Called once on the full dataset.
        Returns DataFrame with columns: date, code, signal, confidence.
    capital : float
        Initial capital.
    max_weight : float
        Maximum weight per position.
    exposure_fn : callable or None
        ``(dates) -> Series`` returning exposure fraction per date.
    industry_map : dict or None
        Mapping from stock code to industry name.
    max_industry_weight : float
        Maximum weight per industry. Default 0.30 (30%).
    stop_loss : float | None
        Stop-loss threshold. None to disable.
    take_profit : float | None
        Take-profit threshold. None to disable.
    atr_stop_loss : dict | None
        ATR stop-loss config. None to disable.
    trading_cost : TradingCost | None
        Trading friction parameters.
    circuit_breaker : object | None
        Drawdown circuit breaker.
    dead_zone : float
        Position smoothing dead-zone threshold.
    rebalance_days : int | None
        If provided, only generate signals on dates where the trading day
        index is a multiple of this number. Reduces turnover for strategies
        that don't need daily signal updates.

    Returns
    -------
    dict
        "overall": dict with total_return, annual_return, sharpe_ratio, max_drawdown.
        "equity_curve": DataFrame (date, equity).
        "trades": DataFrame of executed trades.
    """
    empty_result = {
        "overall": {
            "total_return": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
        },
        "equity_curve": pd.DataFrame(columns=["date", "equity"]),
        "trades": pd.DataFrame(),
    }

    if data.empty:
        return empty_result

    # Generate signals once on full dataset
    signals = signal_fn(data)
    if signals.empty:
        return empty_result

    # Compute exposure
    all_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    exposure = None
    if exposure_fn is not None:
        exposure = exposure_fn(all_dates)

    # Run the unified pipeline: filter tradability -> equal weight ->
    # smoother (dead-zone) -> industry cap -> position limit -> engine.
    # rebalance_days sparsifies signals before allocation (inside pipeline).
    result = run_pipeline(
        signals,
        data,
        capital,
        max_weight=max_weight,
        exposure=exposure,
        industry_map=industry_map,
        max_industry_weight=max_industry_weight,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr_stop_loss=atr_stop_loss,
        trading_cost=trading_cost,
        circuit_breaker=circuit_breaker,
        dead_zone=dead_zone,
        rebalance_days=rebalance_days,
    )

    return {
        "overall": compute_continuous_metrics(result["equity_curve"], capital),
        "equity_curve": result["equity_curve"],
        "trades": result["trades"],
    }
