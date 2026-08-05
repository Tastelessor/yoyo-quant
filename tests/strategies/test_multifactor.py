import numpy as np
import pandas as pd

from strategies.builtin.multifactor import multifactor_signal


def _make_multi_stock_data(n_days=60, n_stocks=5):
    """合成多股票行情数据。"""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    for i in range(n_stocks):
        code = f"{600000 + i}"
        price = 10.0 + i * 2 + np.cumsum(np.random.randn(n_days) * 0.3)
        price = np.maximum(price, 1.0)
        for j, d in enumerate(dates):
            rows.append({
                "date": d,
                "code": code,
                "open": price[j],
                "high": price[j] * 1.02,
                "low": price[j] * 0.98,
                "close": price[j],
                "volume": float(np.random.randint(1_000_000, 5_000_000)),
            })
    return pd.DataFrame(rows)


def _make_data_with_trend(n_days=60, n_stocks=3):
    """合成有明确强弱分化的多股票数据。"""
    np.random.seed(42)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    rows = []
    trends = [0.1, 0.0, -0.1]  # 强、中、弱
    for i, trend in enumerate(trends[:n_stocks]):
        code = f"{600000 + i}"
        price = 10.0 + np.cumsum(np.random.randn(n_days) * 0.2 + trend)
        price = np.maximum(price, 1.0)
        for j, d in enumerate(dates):
            rows.append({
                "date": d,
                "code": code,
                "open": price[j],
                "high": price[j] * 1.02,
                "low": price[j] * 0.98,
                "close": price[j],
                "volume": float(np.random.randint(1_000_000, 5_000_000)),
            })
    return pd.DataFrame(rows)


# --- 基础接口 ---


def test_returns_dataframe():
    """应返回 DataFrame。"""
    data = _make_data_with_trend()
    result = multifactor_signal(data)
    assert isinstance(result, pd.DataFrame)


def test_has_required_columns():
    """应包含必要列。"""
    data = _make_data_with_trend()
    result = multifactor_signal(data)
    assert set(result.columns) == {"date", "code", "signal", "confidence"}


def test_signal_values_valid():
    """signal 值应为 -1, 0, 1。"""
    data = _make_data_with_trend()
    result = multifactor_signal(data)
    assert result["signal"].isin([-1, 0, 1]).all()


def test_confidence_range():
    """confidence 应在 0-1 之间。"""
    data = _make_data_with_trend()
    result = multifactor_signal(data)
    assert (result["confidence"] >= 0).all()
    assert (result["confidence"] <= 1).all()


# --- 选股逻辑 ---


def test_buys_top_ranked():
    """应买入排名最高的股票。"""
    data = _make_data_with_trend(n_days=60, n_stocks=3)
    result = multifactor_signal(data, top_n=1, rebalance=20)
    buy_stocks = set(result[result["signal"] == 1]["code"].unique())
    # 600000 有正趋势，应被买入
    assert "600000" in buy_stocks


def test_sells_bottom_ranked():
    """应卖出排名最低的股票。"""
    data = _make_data_with_trend(n_days=60, n_stocks=3)
    result = multifactor_signal(data, top_n=1, bottom_n=1, rebalance=20)
    sell_stocks = set(result[result["signal"] == -1]["code"].unique())
    # 600002 有负趋势，应被卖出
    assert "600002" in sell_stocks


def test_rebalance_frequency():
    """再平衡频率应影响信号数量。"""
    data = _make_data_with_trend(n_days=60, n_stocks=3)
    r5 = multifactor_signal(data, rebalance=5)
    r20 = multifactor_signal(data, rebalance=20)
    # 频繁再平衡应产生更多信号
    assert (r5["signal"] != 0).sum() >= (r20["signal"] != 0).sum()


def test_no_signal_before_min_window():
    """窗口不足时不应产生信号。"""
    data = _make_data_with_trend(n_days=10, n_stocks=3)
    result = multifactor_signal(data, momentum_window=20)
    assert (result["signal"] != 0).sum() == 0


def test_custom_weights():
    """应支持自定义因子权重。"""
    data = _make_data_with_trend()
    result = multifactor_signal(
        data,
        weights={"momentum": 1.0, "rsi": 0.0, "volatility": 0.0, "volume": 0.0},
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(data)


def test_top_n_zero():
    """top_n=0 不应买入。"""
    data = _make_data_with_trend()
    result = multifactor_signal(data, top_n=0)
    assert (result["signal"] == 1).sum() == 0
