"""Lightweight backtest engine tests."""

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine


@pytest.fixture
def prices():
    """5 days of prices for 2 stocks."""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    )
    return pd.DataFrame(
        {
            "date": dates.tolist() * 2,
            "code": ["000001"] * 5 + ["600519"] * 5,
            "close": [10.0, 10.5, 11.0, 10.8, 11.2, 1800.0, 1810.0, 1790.0, 1820.0, 1850.0],
        }
    )


@pytest.fixture
def buy_signals():
    """Buy on day 1, hold rest."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "code": ["000001"],
            "signal": [1],
            "confidence": [0.8],
        }
    )


@pytest.fixture
def buy_sell_signals():
    """Buy on day 2, sell on day 4."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-05"]),
            "code": ["000001", "000001"],
            "signal": [1, -1],
            "confidence": [0.8, 0.9],
        }
    )


def test_engine_init():
    engine = BacktestEngine(capital=100_000)
    assert engine.initial_capital == 100_000
    assert engine.cash == 100_000


def test_run_returns_dict(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    assert isinstance(result, dict)
    assert "trades" in result
    assert "equity_curve" in result
    assert "metrics" in result


def test_trades_has_required_columns(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    trades = result["trades"]
    assert set(trades.columns) == {"date", "code", "action", "price", "shares", "pnl"}


def test_equity_curve_has_required_columns(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    eq = result["equity_curve"]
    assert set(eq.columns) == {"date", "equity", "cash", "position_value", "returns"}


def test_metrics_has_required_keys(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    metrics = result["metrics"]
    expected = {"total_return", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "trade_count"}
    assert set(metrics.keys()) == expected


def test_buy_generates_trade(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    trades = result["trades"]
    buys = trades[trades["action"] == "buy"]
    assert len(buys) == 1
    assert buys.iloc[0]["code"] == "000001"


def test_sell_generates_trade(prices, buy_sell_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_signals, prices)
    trades = result["trades"]
    assert len(trades) == 2  # 1 buy + 1 sell
    assert set(trades["action"]) == {"buy", "sell"}


def test_equity_starts_at_capital(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    eq = result["equity_curve"]
    assert eq.iloc[0]["equity"] == 100_000.0


def test_equity_changes_after_buy(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    eq = result["equity_curve"]
    # After buying, cash drops, equity tracks price changes
    assert eq.iloc[1]["cash"] < 100_000
    assert eq.iloc[1]["position_value"] > 0


def test_no_signals_no_trades(prices):
    engine = BacktestEngine(capital=100_000)
    empty_signals = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
    result = engine.run(empty_signals, prices)
    assert len(result["trades"]) == 0
    # Equity stays flat
    eq = result["equity_curve"]
    assert (eq["equity"] == 100_000).all()


def test_total_return_zero_when_no_trades(prices):
    engine = BacktestEngine(capital=100_000)
    empty_signals = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
    result = engine.run(empty_signals, prices)
    assert result["metrics"]["total_return"] == 0.0


def test_total_return_positive_on_profit(prices, buy_sell_signals):
    """Buy at 10.0, sell at 10.8 → profit."""
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_signals, prices)
    metrics = result["metrics"]
    assert metrics["total_return"] > 0


def test_trade_count(prices, buy_sell_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_sell_signals, prices)
    assert result["metrics"]["trade_count"] == 2


def test_shares_round_to_100(prices, buy_signals):
    engine = BacktestEngine(capital=100_000)
    result = engine.run(buy_signals, prices)
    for _, row in result["trades"].iterrows():
        assert row["shares"] % 100 == 0
