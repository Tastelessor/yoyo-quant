"""Walk-forward validation for strategy backtesting.

Splits data into rolling train/test windows, runs the full pipeline
on each test window, and collects per-period metrics.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.portfolio.allocator import equal_weight
from src.risk.tradability import enforce_t1, filter_tradable


def generate_windows(
    dates: pd.DatetimeIndex | pd.Series,
    train_months: int = 12,
    test_months: int = 3,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Generate rolling train/test date windows.

    Parameters
    ----------
    dates : DatetimeIndex or Series
        All available trading dates, sorted.
    train_months : int
        Training window length in months.
    test_months : int
        Test window length in months.

    Returns
    -------
    list of (train_start, train_end, test_start, test_end)
    """
    dates = pd.DatetimeIndex(sorted(dates))
    if len(dates) == 0:
        return []

    start = dates[0]
    end = dates[-1]
    windows = []
    current = start

    while True:
        train_start = current
        train_end = train_start + pd.DateOffset(months=train_months)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(months=test_months)

        if test_end > end:
            break

        windows.append((train_start, train_end, test_start, test_end))
        current = current + pd.DateOffset(months=test_months)

    return windows


def walk_forward_backtest(
    data: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame],
    train_months: int = 12,
    test_months: int = 3,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    exposure_fn: Callable[[pd.DatetimeIndex], pd.Series] | None = None,
) -> pd.DataFrame:
    """Run walk-forward backtest with rolling train/test windows.

    Parameters
    ----------
    data : DataFrame
        Stock data with columns: date, code, open, high, low, close, volume.
    signal_fn : callable
        ``(train_data, test_data) -> signals_df``. Called with training data
        for parameter estimation and test data for signal generation.
        Returns DataFrame with columns: date, code, signal, confidence.
    train_months : int
        Training window in months.
    test_months : int
        Test window in months.
    capital : float
        Initial capital.
    max_weight : float
        Maximum weight per position.
    exposure_fn : callable or None
        ``(dates) -> Series`` returning exposure fraction per date.
        If None, full exposure is used.

    Returns
    -------
    DataFrame
        One row per test period with columns: period, train_start, train_end,
        test_start, test_end, total_return, annual_return, sharpe_ratio,
        max_drawdown, win_rate, trade_count.
    """
    all_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    windows = generate_windows(all_dates, train_months, test_months)

    if not windows:
        return pd.DataFrame()

    results = []

    for i, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
        train_data = data[
            (data["date"] >= train_start) & (data["date"] <= train_end)
        ].copy()
        test_data = data[
            (data["date"] >= test_start) & (data["date"] <= test_end)
        ].copy()

        if test_data.empty:
            continue

        # Generate signals (signal_fn can re-estimate params on train_data)
        signals = signal_fn(train_data, test_data)

        if signals.empty:
            results.append({
                "period": i, "train_start": train_start, "train_end": train_end,
                "test_start": test_start, "test_end": test_end,
                "total_return": 0.0, "annual_return": 0.0, "sharpe_ratio": 0.0,
                "max_drawdown": 0.0, "win_rate": 0.0, "trade_count": 0,
            })
            continue

        # Filter tradability on test data
        signals = filter_tradable(test_data, signals)
        signals = enforce_t1(signals)

        # Compute exposure for test period
        exposure = None
        if exposure_fn is not None:
            test_dates = pd.DatetimeIndex(sorted(test_data["date"].unique()))
            exposure = exposure_fn(test_dates)

        # Allocate positions
        prices = test_data[["date", "code", "close"]].drop_duplicates()
        positions = equal_weight(signals, prices, capital=capital, exposure=exposure)

        # Apply position limit
        from src.risk.position_limit import apply_position_limit
        positions = apply_position_limit(positions, max_weight=max_weight)

        # Run backtest
        engine = BacktestEngine(capital=capital)
        result = engine.run(positions, prices)
        m = result["metrics"]

        results.append({
            "period": i, "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
            "total_return": m["total_return"],
            "annual_return": m["annual_return"],
            "sharpe_ratio": m["sharpe_ratio"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m["win_rate"],
            "trade_count": m["trade_count"],
        })

    return pd.DataFrame(results)
