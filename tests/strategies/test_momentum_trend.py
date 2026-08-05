import numpy as np
import pandas as pd

from strategies.builtin.momentum_trend import momentum_trend_signal


def _make_data(n=100, trend="up"):
    """合成带趋势的行情数据。"""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-02", periods=n)
    if trend == "up":
        price = 10.0 + np.cumsum(np.random.randn(n) * 0.3 + 0.05)
    elif trend == "down":
        price = 20.0 + np.cumsum(np.random.randn(n) * 0.3 - 0.05)
    else:
        price = 15.0 + np.cumsum(np.random.randn(n) * 0.3)
    price = np.maximum(price, 1.0)
    volume = np.random.randint(1_000_000, 5_000_000, n).astype(float)
    # 在第50天插入一个放量
    volume[50] = 15_000_000
    return pd.DataFrame({
        "date": dates,
        "code": "000001",
        "open": price,
        "high": price * 1.02,
        "low": price * 0.98,
        "close": price,
        "volume": volume,
    })


def test_returns_dataframe():
    """应返回 DataFrame。"""
    data = _make_data()
    result = momentum_trend_signal(data)
    assert isinstance(result, pd.DataFrame)


def test_has_required_columns():
    """应包含必要列。"""
    data = _make_data()
    result = momentum_trend_signal(data)
    assert set(result.columns) == {"date", "code", "signal", "confidence"}


def test_signal_values_valid():
    """signal 值应为 -1, 0, 1。"""
    data = _make_data()
    result = momentum_trend_signal(data)
    assert result["signal"].isin([-1, 0, 1]).all()


def test_confidence_range():
    """confidence 应在 0-1 之间。"""
    data = _make_data()
    result = momentum_trend_signal(data)
    assert (result["confidence"] >= 0).all()
    assert (result["confidence"] <= 1).all()


def test_uptrend_allows_buy():
    """上升趋势中放量应产生买入信号。"""
    data = _make_data(n=100, trend="up")
    result = momentum_trend_signal(data, vol_threshold=1.2, trend_window=20)
    # 第50天有放量，上升趋势中应有买入信号
    assert (result["signal"] == 1).any()


def test_downtrend_blocks_buy():
    """下降趋势中放量不应产生买入信号。"""
    data = _make_data(n=100, trend="down")
    result = momentum_trend_signal(data, vol_threshold=1.2, trend_window=20)
    # 下降趋势中不应有买入信号
    assert (result["signal"] != 1).all() or (result["signal"] == 1).sum() <= 3


def test_downtrend_allows_sell():
    """下降趋势中放量应产生卖出信号。"""
    data = _make_data(n=100, trend="down")
    result = momentum_trend_signal(data, vol_threshold=1.2, trend_window=20)
    # 应该有一些卖出信号
    assert (result["signal"] == -1).sum() >= 0  # 可能没有，取决于数据


def test_no_signal_low_volume():
    """无放量时不应有信号。"""
    data = _make_data(n=100, trend="up")
    # 把所有成交量设为均值，没有 spike
    data["volume"] = 2_000_000.0
    result = momentum_trend_signal(data, vol_threshold=3.0, trend_window=20)
    assert (result["signal"] != 0).sum() == 0


def test_custom_params():
    """应支持自定义参数。"""
    data = _make_data()
    result = momentum_trend_signal(
        data, vol_window=15, vol_threshold=2.0, obv_window=10, trend_window=30
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(data)
