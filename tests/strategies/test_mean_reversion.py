import numpy as np
import pandas as pd
import pytest

from src.strategies.mean_reversion import mean_reversion_signal


@pytest.fixture
def price_above_upper_band():
    """价格突然跳升远超上轨 → 应产生卖出信号。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    # 前 25 天稳定在 100，后 5 天跳到 110
    close = np.concatenate([np.full(25, 100.0), np.full(5, 110.0)])
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000,
        }
    )


@pytest.fixture
def price_below_lower_band():
    """价格突然跳水远超下轨 → 应产生买入信号。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    close = np.concatenate([np.full(25, 100.0), np.full(5, 90.0)])
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000,
        }
    )


def test_signal_returns_dataframe():
    """应返回 DataFrame。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(df)


def test_signal_has_required_columns():
    """输出应包含 date, code, signal, confidence 列。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    assert "date" in result.columns
    assert "code" in result.columns
    assert "signal" in result.columns
    assert "confidence" in result.columns


def test_signal_values_valid():
    """signal 只能是 -1, 0, 1。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    assert set(result["signal"].unique()).issubset({-1, 0, 1})


def test_confidence_range():
    """confidence 应在 [0, 1] 范围内。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    assert (result["confidence"] >= 0).all()
    assert (result["confidence"] <= 1).all()


def test_no_signal_when_stable():
    """价格稳定不变时不应产生交易信号。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    assert (result["signal"] == 0).all()


def test_buy_signal_below_lower_band(price_below_lower_band):
    """价格跌破下轨时应产生买入信号。"""
    result = mean_reversion_signal(price_below_lower_band)
    buy_signals = result[result["signal"] == 1]
    assert len(buy_signals) > 0


def test_sell_signal_above_upper_band(price_above_upper_band):
    """价格突破上轨时应产生卖出信号。"""
    result = mean_reversion_signal(price_above_upper_band)
    sell_signals = result[result["signal"] == -1]
    assert len(sell_signals) > 0


def test_signal_preserves_date_code():
    """输出应保留原始 date 和 code。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
    )
    result = mean_reversion_signal(df)
    pd.testing.assert_series_equal(result["date"], df["date"])
    assert (result["code"] == "000001.SZ").all()
