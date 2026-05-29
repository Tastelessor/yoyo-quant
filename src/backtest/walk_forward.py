"""Walk-forward validation for strategy backtesting.

Splits data into rolling train/test windows, runs the full pipeline
on each test window, and collects per-period metrics.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine, TradingCost
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


def compute_overall_metrics(
    equity_curve: pd.DataFrame,
    per_period: pd.DataFrame,
    capital: float,
) -> dict:
    """Compute correct overall metrics from a continuous equity curve.

    Parameters
    ----------
    equity_curve : DataFrame
        Columns: date, equity. Spans all walk-forward periods with
        chained capital (each period starts where the previous ended).
    per_period : DataFrame
        Per-period results with total_return column.
    capital : float
        Initial capital.

    Returns
    -------
    dict
        total_return, annual_return, sharpe_ratio, max_drawdown,
        per_period_sharpe_mean, per_period_sharpe_std.
    """
    if equity_curve.empty:
        return {
            "total_return": 0.0, "annual_return": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0,
            "per_period_sharpe_mean": 0.0, "per_period_sharpe_std": 0.0,
        }

    eq = equity_curve.sort_values("date").reset_index(drop=True)
    initial = capital
    final = eq["equity"].iloc[-1]

    # Compound return
    total_return = (final - initial) / initial if initial > 0 else 0.0

    # Annualized return
    n_days = len(eq)
    if n_days > 1 and total_return > -1:
        annual_return = (1 + total_return) ** (252 / n_days) - 1
    else:
        annual_return = 0.0

    # Sharpe from continuous daily returns
    eq_vals = eq["equity"].values
    daily_returns = np.diff(eq_vals) / eq_vals[:-1]
    daily_rf = 0.03 / 252
    excess = daily_returns - daily_rf
    std = excess.std()
    if len(excess) > 1 and std > 1e-10:
        sharpe = float(excess.mean() / std * np.sqrt(252))
    else:
        sharpe = 0.0

    # Max drawdown from continuous equity
    peak = np.maximum.accumulate(eq_vals)
    drawdown = (eq_vals - peak) / np.where(peak > 0, peak, 1)
    max_drawdown = float(abs(drawdown.min()))

    # Per-period consistency stats
    pp_sharpes = per_period["sharpe_ratio"]
    pp_sharpe_mean = float(pp_sharpes.mean()) if len(pp_sharpes) > 0 else 0.0
    pp_sharpe_std = float(pp_sharpes.std()) if len(pp_sharpes) > 1 else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "per_period_sharpe_mean": pp_sharpe_mean,
        "per_period_sharpe_std": pp_sharpe_std,
    }


def walk_forward_backtest(
    data: pd.DataFrame,
    signal_fn: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame],
    train_months: int = 12,
    test_months: int = 3,
    capital: float = 1_000_000,
    max_weight: float = 0.3,
    exposure_fn: Callable[[pd.DatetimeIndex], pd.Series] | None = None,
    stock_selector_fn: Callable[[pd.DataFrame], dict] | None = None,
    industry_map: dict[str, str] | None = None,
    max_industry_weight: float = 0.30,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    atr_stop_loss: dict | None = None,
    trading_cost: TradingCost | None = None,
    circuit_breaker: object | None = None,
    dead_zone: float = 0.0,
) -> dict:
    """Run walk-forward backtest with rolling train/test windows.

    Capital chains across periods: each period starts with the previous
    period's ending equity. Overall metrics (Sharpe, annual return, MaxDD)
    are computed from the continuous equity curve.

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
    stock_selector_fn : callable or None
        ``(factor_df) -> dict[Timestamp, list[str]]`` returning per-date
        stock pool. If None, all stocks in data are used. The selector
        receives the full data DataFrame so rolling lookback works correctly.
    industry_map : dict or None
        Mapping from stock code to industry name. If provided, applies
        per-industry weight cap after equal-weight allocation.
    max_industry_weight : float
        Maximum weight per industry. Default 0.30 (30%).
    stop_loss : float | None
        Stop-loss threshold (e.g. -0.15). None to disable.
    take_profit : float | None
        Take-profit threshold (e.g. 0.05). None to disable.
    atr_stop_loss : dict | None
        ATR stop-loss config with keys ``atr_multiplier`` and ``atr_window``.
        None to disable.
    trading_cost : TradingCost | None
        Trading friction parameters. None disables all friction.
    circuit_breaker : DrawdownCircuitBreaker | None
        If provided, monitors equity curve across periods and compresses
        exposure during drawdowns. Overrides ``exposure_fn`` when set.
    dead_zone : float
        Position smoothing dead-zone threshold. When > 0, weights that
        change less than this amount are held from the previous day.
        Default 0.0 (disabled). Typical value: 0.01 (1%).

    Returns
    -------
    dict
        "per_period": DataFrame with one row per test period.
        "overall": dict with total_return, annual_return, sharpe_ratio,
            max_drawdown, per_period_sharpe_mean, per_period_sharpe_std.
        "equity_curve": DataFrame (date, equity) spanning all periods
            with chained capital.
    """
    all_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    windows = generate_windows(all_dates, train_months, test_months)

    empty_result = {
        "per_period": pd.DataFrame(),
        "overall": {
            "total_return": 0.0, "annual_return": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0,
            "per_period_sharpe_mean": 0.0, "per_period_sharpe_std": 0.0,
        },
        "equity_curve": pd.DataFrame(columns=["date", "equity"]),
    }

    if not windows:
        return empty_result

    results = []
    equity_rows = []  # (date, equity) across all periods
    prev_positions = None
    running_capital = capital

    for i, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
        train_data = data[
            (data["date"] >= train_start) & (data["date"] <= train_end)
        ].copy()
        test_data = data[
            (data["date"] >= test_start) & (data["date"] <= test_end)
        ].copy()

        if test_data.empty:
            continue

        # Apply dynamic stock selection if provided
        if stock_selector_fn is not None:
            pool = stock_selector_fn(data)
            test_dates_set = set(test_data["date"].unique())
            pool_filtered = {
                d: codes
                for d, codes in pool.items()
                if d in test_dates_set
            }
            mask = pd.Series(False, index=test_data.index)
            for d, allowed in pool_filtered.items():
                mask = mask | (
                    (test_data["date"] == d) & (test_data["code"].isin(allowed))
                )
            test_data = test_data[mask].copy()
            if test_data.empty:
                results.append({
                    "period": i, "train_start": train_start,
                    "train_end": train_end, "test_start": test_start,
                    "test_end": test_end, "total_return": 0.0,
                    "annual_return": 0.0, "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0, "win_rate": 0.0, "trade_count": 0,
                })
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

        # Allocate positions using running capital (chained from previous period)
        prices = test_data[["date", "code", "close"]].drop_duplicates()
        positions = equal_weight(signals, prices, capital=running_capital, exposure=exposure)

        # Position smoothing (dead-zone state machine)
        if dead_zone > 0:
            from src.portfolio.smoother import smooth_positions

            # Include previous period's last-day prices so the smoother
            # can forward-fill close for resurrected stocks.
            smooth_prices = prices
            if prev_positions is not None and not prev_positions.empty:
                prev_date = prev_positions["date"].max()
                prev_day_prices = data[data["date"] == prev_date][
                    ["date", "code", "close"]
                ].drop_duplicates()
                if not prev_day_prices.empty:
                    smooth_prices = pd.concat(
                        [prices, prev_day_prices], ignore_index=True
                    ).drop_duplicates(subset=["date", "code"], keep="last")

            positions = smooth_positions(
                positions, prev_positions, smooth_prices,
                capital=running_capital, exposure=exposure, dead_zone=dead_zone,
            )
        prev_positions = positions.copy()

        # Apply industry cap if mapping provided
        if industry_map is not None:
            from src.portfolio.industry_cap import apply_industry_cap
            positions = apply_industry_cap(
                positions, industry_map, max_industry_weight
            )

        # Apply position limit
        from src.risk.position_limit import apply_position_limit
        positions = apply_position_limit(positions, max_weight=max_weight)

        # Run backtest with chained capital
        engine = BacktestEngine(
            capital=running_capital,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_stop_loss=atr_stop_loss,
            trading_cost=trading_cost,
            circuit_breaker=circuit_breaker,
        )
        result = engine.run(positions, prices, market_data=data,
                           starting_capital=running_capital)
        m = result["metrics"]

        # Collect equity curve entries (skip first row — it duplicates prev period end)
        eq = result["equity_curve"]
        if equity_rows and not eq.empty:
            eq = eq.iloc[1:]  # drop overlap with previous period's last row
        for _, row in eq.iterrows():
            equity_rows.append({"date": row["date"], "equity": row["equity"]})

        # Chain capital to next period
        if not eq.empty:
            running_capital = eq["equity"].iloc[-1]
        else:
            running_capital = running_capital * (1 + m["total_return"])

        results.append({
            "period": i, "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
            "total_return": m["total_return"],
            "annual_return": m["annual_return"],
            "sharpe_ratio": m["sharpe_ratio"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m["win_rate"],
            "trade_count": m["trade_count"],
            "total_cost": m["total_cost"],
            "cost_ratio": m["cost_ratio"],
        })

    per_period = pd.DataFrame(results)
    equity_curve = pd.DataFrame(equity_rows, columns=["date", "equity"])
    overall = compute_overall_metrics(equity_curve, per_period, capital)

    return {
        "per_period": per_period,
        "overall": overall,
        "equity_curve": equity_curve,
    }


def _run_silo_pipeline(
    test_data: pd.DataFrame,
    signal_fn: Callable,
    train_data: pd.DataFrame,
    capital: float,
    exposure: pd.Series | None,
    dead_zone: float,
    prev_positions: pd.DataFrame | None,
    data: pd.DataFrame,
    silo_capital: float,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Run one silo's full pipeline: signal -> filter -> allocate -> smooth.

    Returns (positions, new_prev_positions).
    """
    from src.portfolio.smoother import smooth_positions

    signals = signal_fn(train_data, test_data)
    if signals.empty:
        return pd.DataFrame(columns=["date", "code", "weight", "shares"]), prev_positions

    signals = filter_tradable(test_data, signals)
    signals = enforce_t1(signals)

    prices = test_data[["date", "code", "close"]].drop_duplicates()
    positions = equal_weight(signals, prices, capital=silo_capital, exposure=exposure)

    if dead_zone > 0:
        smooth_prices = prices
        if prev_positions is not None and not prev_positions.empty:
            prev_date = prev_positions["date"].max()
            prev_day_prices = data[data["date"] == prev_date][
                ["date", "code", "close"]
            ].drop_duplicates()
            if not prev_day_prices.empty:
                smooth_prices = pd.concat(
                    [prices, prev_day_prices], ignore_index=True
                ).drop_duplicates(subset=["date", "code"], keep="last")

        positions = smooth_positions(
            positions, prev_positions, smooth_prices,
            capital=silo_capital, exposure=exposure, dead_zone=dead_zone,
        )

    return positions, positions.copy() if not positions.empty else prev_positions


def _merge_silo_positions(
    silo_positions: list[pd.DataFrame],
    silo_weights: list[float],
    prices: pd.DataFrame,
    capital: float,
    exposure: pd.Series | None,
) -> pd.DataFrame:
    """Merge multiple silo positions at the weight level.

    Each silo's weight is scaled by its silo_weight fraction.
    Overlapping (date, code) pairs get their scaled weights summed.
    Final weights are normalized per date to sum to 1.0.
    """
    if not silo_positions:
        return pd.DataFrame(columns=["date", "code", "weight", "shares"])

    # Scale each silo's weights by its allocation fraction
    scaled_frames = []
    for pos, sw in zip(silo_positions, silo_weights):
        if pos.empty:
            continue
        p = pos[["date", "code", "weight"]].copy()
        p["weight"] = p["weight"] * sw
        scaled_frames.append(p)

    if not scaled_frames:
        return pd.DataFrame(columns=["date", "code", "weight", "shares"])

    # Outer join merge: sum weights for overlapping (date, code)
    merged = scaled_frames[0]
    for frame in scaled_frames[1:]:
        merged = merged.merge(frame, on=["date", "code"], how="outer", suffixes=("", "_r"))
        merged["weight"] = merged["weight"].fillna(0.0) + merged["weight_r"].fillna(0.0)
        merged = merged.drop(columns=["weight_r"])

    # Normalize weights per date to sum to 1.0
    date_sums = merged.groupby("date")["weight"].transform("sum")
    date_sums = date_sums.replace(0.0, 1.0)  # avoid division by zero
    merged["weight"] = merged["weight"] / date_sums

    # Recompute shares — select only key + weight before merging with prices
    merged = merged[["date", "code", "weight"]].merge(prices, on=["date", "code"], how="left")
    if exposure is not None:
        exposure_df = exposure.rename("exposure").reset_index()
        exposure_df.columns = ["date", "exposure"]
        merged = merged.merge(exposure_df, on="date", how="left")
        merged["exposure"] = merged["exposure"].fillna(1.0)
    else:
        merged["exposure"] = 1.0

    merged["shares"] = (
        np.floor(capital * merged["exposure"] * merged["weight"] / merged["close"] / 100) * 100
    ).clip(lower=0).fillna(0).astype(int)

    return merged[["date", "code", "weight", "shares"]]


def walk_forward_multi_silo(
    data: pd.DataFrame,
    silos: list[dict],
    train_months: int = 12,
    test_months: int = 3,
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
) -> dict:
    """Walk-forward backtest with Multi-Silo independent sub-portfolios.

    Each silo runs its own signal -> filter -> allocate -> smooth pipeline
    independently. Positions are merged at the weight level (outer join),
    then fed into a single BacktestEngine. Capital chains across periods.

    Parameters
    ----------
    data : DataFrame
        Stock data with columns: date, code, open, high, low, close, volume.
    silos : list of dict
        Each silo config has keys:
        - "signal_fn": callable(train_data, test_data) -> signals_df
        - "weight": float, capital allocation fraction (should sum to 1.0)
        - "name": str, optional label for debugging
    train_months, test_months, capital, max_weight, exposure_fn,
    industry_map, max_industry_weight, stop_loss, take_profit,
    atr_stop_loss, trading_cost, circuit_breaker, dead_zone
        Same as walk_forward_backtest.

    Returns
    -------
    dict
        "per_period": DataFrame with one row per test period.
        "overall": dict with total_return, annual_return, sharpe_ratio,
            max_drawdown, per_period_sharpe_mean, per_period_sharpe_std.
        "equity_curve": DataFrame (date, equity) spanning all periods.
    """
    all_dates = pd.DatetimeIndex(sorted(data["date"].unique()))
    windows = generate_windows(all_dates, train_months, test_months)

    empty_result = {
        "per_period": pd.DataFrame(),
        "overall": {
            "total_return": 0.0, "annual_return": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0,
            "per_period_sharpe_mean": 0.0, "per_period_sharpe_std": 0.0,
        },
        "equity_curve": pd.DataFrame(columns=["date", "equity"]),
    }

    if not windows:
        return empty_result

    results = []
    equity_rows = []
    silo_prev_positions: list[pd.DataFrame | None] = [None] * len(silos)
    silo_weight_fractions = [s["weight"] for s in silos]
    running_capital = capital

    for i, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
        train_data = data[
            (data["date"] >= train_start) & (data["date"] <= train_end)
        ].copy()
        test_data = data[
            (data["date"] >= test_start) & (data["date"] <= test_end)
        ].copy()

        if test_data.empty:
            continue

        # Compute exposure for test period
        exposure = None
        if exposure_fn is not None:
            test_dates = pd.DatetimeIndex(sorted(test_data["date"].unique()))
            exposure = exposure_fn(test_dates)

        prices = test_data[["date", "code", "close"]].drop_duplicates()

        # Run each silo independently using running capital
        silo_positions_list = []
        for j, silo in enumerate(silos):
            silo_capital = running_capital * silo["weight"]
            pos, new_prev = _run_silo_pipeline(
                test_data, silo["signal_fn"], train_data,
                running_capital, exposure, dead_zone,
                silo_prev_positions[j], data, silo_capital,
            )
            silo_positions_list.append(pos)
            silo_prev_positions[j] = new_prev

        # Merge silos at weight level
        positions = _merge_silo_positions(
            silo_positions_list, silo_weight_fractions, prices, running_capital, exposure,
        )

        if positions.empty:
            results.append({
                "period": i, "train_start": train_start, "train_end": train_end,
                "test_start": test_start, "test_end": test_end,
                "total_return": 0.0, "annual_return": 0.0, "sharpe_ratio": 0.0,
                "max_drawdown": 0.0, "win_rate": 0.0, "trade_count": 0,
            })
            continue

        # Apply industry cap on merged portfolio
        if industry_map is not None:
            from src.portfolio.industry_cap import apply_industry_cap
            positions = apply_industry_cap(
                positions, industry_map, max_industry_weight
            )

        # Apply position limit on merged portfolio
        from src.risk.position_limit import apply_position_limit
        positions = apply_position_limit(positions, max_weight=max_weight)

        # Run single backtest engine with chained capital
        engine = BacktestEngine(
            capital=running_capital,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_stop_loss=atr_stop_loss,
            trading_cost=trading_cost,
            circuit_breaker=circuit_breaker,
        )
        result = engine.run(positions, prices, market_data=data,
                           starting_capital=running_capital)
        m = result["metrics"]

        # Collect equity curve
        eq = result["equity_curve"]
        if equity_rows and not eq.empty:
            eq = eq.iloc[1:]
        for _, row in eq.iterrows():
            equity_rows.append({"date": row["date"], "equity": row["equity"]})

        if not eq.empty:
            running_capital = eq["equity"].iloc[-1]
        else:
            running_capital = running_capital * (1 + m["total_return"])

        results.append({
            "period": i, "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
            "total_return": m["total_return"],
            "annual_return": m["annual_return"],
            "sharpe_ratio": m["sharpe_ratio"],
            "max_drawdown": m["max_drawdown"],
            "win_rate": m["win_rate"],
            "trade_count": m["trade_count"],
            "total_cost": m["total_cost"],
            "cost_ratio": m["cost_ratio"],
        })

    per_period = pd.DataFrame(results)
    equity_curve = pd.DataFrame(equity_rows, columns=["date", "equity"])
    overall = compute_overall_metrics(equity_curve, per_period, capital)

    return {
        "per_period": per_period,
        "overall": overall,
        "equity_curve": equity_curve,
    }
