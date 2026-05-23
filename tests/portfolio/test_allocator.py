"""Portfolio allocator tests."""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.allocator import equal_weight


@pytest.fixture
def buy_signals():
    """Multiple buy signals on same date."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-02"]),
            "code": ["000001", "600519", "000858"],
            "signal": [1, 1, 1],
            "confidence": [0.8, 0.9, 0.7],
        }
    )


@pytest.fixture
def mixed_signals():
    """Buy, sell, and hold signals."""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-02"]),
            "code": ["000001", "600519", "000858"],
            "signal": [1, -1, 0],
            "confidence": [0.8, 0.9, 0.5],
        }
    )


@pytest.fixture
def prices():
    """Price data for share calculation."""
    dates = pd.to_datetime(["2024-01-02"] * 3)
    return pd.DataFrame(
        {
            "date": dates,
            "code": ["000001", "600519", "000858"],
            "close": [10.0, 1800.0, 50.0],
        }
    )


def test_equal_weight_returns_dataframe(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=100_000)
    assert isinstance(result, pd.DataFrame)


def test_equal_weight_has_required_columns(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=100_000)
    assert set(result.columns) == {"date", "code", "weight", "shares"}


def test_equal_weight_allocates_equally(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=100_000)
    weights = result["weight"].values
    # 3 stocks, each gets 1/3
    np.testing.assert_allclose(weights, 1 / 3, atol=1e-8)


def test_equal_weight_ignores_non_buy_signals(mixed_signals, prices):
    result = equal_weight(mixed_signals, prices, capital=100_000)
    # Only 000001 has signal=1
    assert len(result) == 1
    assert result.iloc[0]["code"] == "000001"
    assert result.iloc[0]["weight"] == 1.0


def test_equal_weight_calculates_shares(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=100_000)
    # Each stock gets 100000/3 = 33333.33
    # 000001: 33333.33 / 10.0 = 3333.33 → round down to 100s → 3300
    row = result[result["code"] == "000001"].iloc[0]
    assert row["shares"] == 3300


def test_equal_weight_shares_round_to_100(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=100_000)
    for _, row in result.iterrows():
        assert row["shares"] % 100 == 0, f"shares {row['shares']} not rounded to 100"


def test_equal_weight_zero_capital(buy_signals, prices):
    result = equal_weight(buy_signals, prices, capital=0)
    assert (result["shares"] == 0).all()
    assert (result["weight"] == 0).all()


def test_equal_weight_empty_signals(prices):
    empty = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
    result = equal_weight(empty, prices, capital=100_000)
    assert len(result) == 0


def test_equal_weight_multi_day_signals(prices):
    """Two days of signals, each day independent."""
    signals = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "code": ["000001", "600519", "000001", "000858"],
            "signal": [1, 1, 1, 1],
            "confidence": [0.8, 0.9, 0.7, 0.6],
        }
    )
    prices_multi = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]
            ),
            "code": ["000001", "600519", "000001", "000858"],
            "close": [10.0, 1800.0, 10.5, 50.0],
        }
    )
    result = equal_weight(signals, prices_multi, capital=100_000)
    dates = result["date"].unique()
    assert len(dates) == 2
    # Day 1: 2 stocks, each 50%
    day1 = result[result["date"] == pd.Timestamp("2024-01-02")]
    np.testing.assert_allclose(day1["weight"].values, 0.5, atol=1e-8)
