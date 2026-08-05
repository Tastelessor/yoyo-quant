"""Unified backtest pipeline — single orchestration entry point.

Centralizes the pipeline chain that used to be hand-written in four places
(walk_forward, continuous, param_sweep, pool_matrix):

    filter_tradable → enforce_t1 → [rebalance sparsify] → equal_weight
    → [smoother] → [industry_cap] → [position_limit] → BacktestEngine

Public API
----------
build_positions : signals → (positions, prices); the portfolio half of the
    chain (filter → allocate → smooth), excluding industry cap and position
    limit. Used by multi-silo walk-forward for per-silo positions.
run_backtest    : (positions, prices) → BacktestEngine result dict.
run_pipeline    : full chain signals → positions → engine result, returns a
    single dict with positions / carry_positions / prices / trades /
    equity_curve / metrics. Used by walk-forward, continuous, param_sweep
    and pool_matrix.
"""

from __future__ import annotations

import pandas as pd

from src.backtest.engine import BacktestEngine, TradingCost
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable


def build_positions(
    signals: pd.DataFrame,
    data: pd.DataFrame,
    capital: float,
    *,
    exposure: pd.Series | None = None,
    dead_zone: float = 0.0,
    prev_positions: pd.DataFrame | None = None,
    rebalance_days: int | None = None,
    market_data: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build target positions from signals (portfolio half of the pipeline).

    Chain: filter_tradable → enforce_t1 → [rebalance sparsify] →
    equal_weight → [smoother]. Industry cap and position limit are NOT
    applied here — callers apply them (see :func:`run_pipeline`).

    Parameters
    ----------
    signals : DataFrame
        Signal data (date, code, signal, confidence).
    data : DataFrame
        Market data (date, code, open, high, low, close, volume,
        limit_up, limit_down, is_suspended).
    capital : float
        Capital to allocate per date.
    exposure : Series | None
        Per-date exposure fraction (indexed by date).
    dead_zone : float
        Position smoothing dead-zone threshold. When > 0, applies
        :func:`src.portfolio.smoother.smooth_positions` with
        ``prev_positions`` as the cold-start state.
    prev_positions : DataFrame | None
        Previous period's ending positions for smoother cold start.
        Only used when ``dead_zone > 0``.
    rebalance_days : int | None
        If provided, only keep every N-th signal date (turnover control).
    market_data : DataFrame | None
        Full market data used to look up the previous period's last-day
        prices for smoother cold start. Defaults to ``data``. Walk-forward
        callers pass the full dataset so cross-period prices are available.

    Returns
    -------
    (positions, prices)
        positions : DataFrame (date, code, weight, shares)
        prices : DataFrame (date, code, close), deduplicated
    """
    prices = data[["date", "code", "close"]].drop_duplicates()

    signals = filter_tradable(data, signals)
    signals = enforce_t1(signals)

    # Sparsify signals on a fixed cadence before allocation
    if rebalance_days is not None:
        signal_dates = sorted(signals["date"].unique())
        keep_dates = set(
            signal_dates[i] for i in range(0, len(signal_dates), rebalance_days)
        )
        signals = signals[signals["date"].isin(keep_dates)]

    positions = equal_weight(signals, prices, capital=capital, exposure=exposure)

    if dead_zone > 0:
        from src.portfolio.smoother import smooth_positions

        # Include previous period's last-day prices so the smoother can
        # forward-fill close for resurrected stocks.
        md = data if market_data is None else market_data
        smooth_prices = prices
        if prev_positions is not None and not prev_positions.empty:
            prev_date = prev_positions["date"].max()
            prev_day_prices = md[md["date"] == prev_date][
                ["date", "code", "close"]
            ].drop_duplicates()
            if not prev_day_prices.empty:
                smooth_prices = pd.concat(
                    [prices, prev_day_prices], ignore_index=True
                ).drop_duplicates(subset=["date", "code"], keep="last")

        positions = smooth_positions(
            positions,
            prev_positions,
            smooth_prices,
            capital=capital,
            exposure=exposure,
            dead_zone=dead_zone,
        )

    return positions, prices


def run_backtest(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    data: pd.DataFrame | None = None,
    *,
    capital: float = 1_000_000,
    starting_capital: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    atr_stop_loss: dict | None = None,
    trading_cost: TradingCost | None = None,
    circuit_breaker: object | None = None,
) -> dict:
    """Run the backtest engine on pre-built positions.

    Parameters
    ----------
    positions : DataFrame
        Target positions (date, code, weight, shares).
    prices : DataFrame
        Price data (date, code, close).
    data : DataFrame | None
        Full OHLCV market data. Required when ``atr_stop_loss`` is enabled.
    capital : float
        Initial capital for the engine.
    starting_capital : float | None
        Override initial capital (walk-forward capital chaining).

    Returns
    -------
    dict
        BacktestEngine.run() result: trades, equity_curve, metrics.
    """
    engine = BacktestEngine(
        capital=capital,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr_stop_loss=atr_stop_loss,
        trading_cost=trading_cost,
        circuit_breaker=circuit_breaker,
    )
    return engine.run(
        positions, prices, market_data=data, starting_capital=starting_capital
    )


def run_pipeline(
    signals: pd.DataFrame,
    data: pd.DataFrame,
    capital: float = 1_000_000,
    *,
    max_weight: float = 0.3,
    exposure: pd.Series | None = None,
    industry_map: dict[str, str] | None = None,
    max_industry_weight: float = 0.30,
    dead_zone: float = 0.0,
    prev_positions: pd.DataFrame | None = None,
    rebalance_days: int | None = None,
    market_data: pd.DataFrame | None = None,
    starting_capital: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    atr_stop_loss: dict | None = None,
    trading_cost: TradingCost | None = None,
    circuit_breaker: object | None = None,
) -> dict:
    """Run the full pipeline: signals → positions → engine result.

    Chain: filter_tradable → enforce_t1 → [rebalance sparsify] →
    equal_weight → [smoother] → [industry_cap] → position_limit →
    BacktestEngine.

    Parameters
    ----------
    signals : DataFrame
        Signal data (date, code, signal, confidence).
    data : DataFrame
        Market data used for tradability filtering, price extraction and
        engine market data (unless ``market_data`` is given).
    capital : float
        Capital to allocate and initial engine capital.
    max_weight : float
        Maximum weight per position (position limit).
    exposure : Series | None
        Per-date exposure fraction (indexed by date).
    industry_map : dict | None
        Code → industry mapping. If provided, applies per-industry cap.
    max_industry_weight : float
        Maximum weight per industry. Default 0.30.
    dead_zone : float
        Position smoothing dead-zone threshold (0 disables smoothing).
    prev_positions : DataFrame | None
        Previous period's ending positions for smoother cold start.
    rebalance_days : int | None
        If provided, only keep every N-th signal date.
    market_data : DataFrame | None
        Full OHLCV market data for the engine (defaults to ``data``).
    starting_capital : float | None
        Override initial capital (walk-forward capital chaining).
    stop_loss / take_profit / atr_stop_loss / trading_cost / circuit_breaker
        Forwarded to the BacktestEngine.

    Returns
    -------
    dict
        Keys: positions (final), carry_positions (pre-cap/pre-limit state
        used for cross-period smoother cold start), prices, trades,
        equity_curve, metrics.
    """
    positions, prices = build_positions(
        signals,
        data,
        capital,
        exposure=exposure,
        dead_zone=dead_zone,
        prev_positions=prev_positions,
        rebalance_days=rebalance_days,
        market_data=market_data,
    )
    carry_positions = positions.copy()

    # Industry cap + position limit (post-smoothing portfolio constraints)
    if industry_map is not None:
        from src.portfolio.industry_cap import apply_industry_cap

        positions = apply_industry_cap(positions, industry_map, max_industry_weight)
    positions = apply_position_limit(positions, max_weight=max_weight)

    md = data if market_data is None else market_data
    result = run_backtest(
        positions,
        prices,
        md,
        capital=capital,
        starting_capital=starting_capital,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr_stop_loss=atr_stop_loss,
        trading_cost=trading_cost,
        circuit_breaker=circuit_breaker,
    )
    result["positions"] = positions
    result["carry_positions"] = carry_positions
    result["prices"] = prices
    return result
