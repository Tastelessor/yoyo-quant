import numpy as np
import pandas as pd
import pytest

from src.factors.volatility import calc_hv


@pytest.fixture
def sample_ohlcv():
    """生成一段稳定价格数据用于测试。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(30) * 0.5)
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, 30),
        }
    )


def test_hv_returns_series(sample_ohlcv):
    """calc_hv 应返回 Series，长度与输入一致。"""
    result = calc_hv(sample_ohlcv, window=20)
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_ohlcv)


def test_hv_first_window_is_nan(sample_ohlcv):
    """前 window 个值应为 NaN（shift(1) 产生额外 NaN + 窗口不足）。"""
    result = calc_hv(sample_ohlcv, window=20)
    assert result.iloc[:20].isna().all()
    assert result.iloc[20:].notna().all()


def test_hv_values_positive(sample_ohlcv):
    """有效 HV 值应为非负。"""
    result = calc_hv(sample_ohlcv, window=20)
    valid = result.dropna()
    assert (valid >= 0).all()


def test_hv_constant_price_is_zero():
    """价格不变时 HV 应为 0。"""
    dates = pd.date_range("2024-01-01", periods=25, freq="B")
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
    result = calc_hv(df, window=20)
    valid = result.dropna()
    assert np.allclose(valid, 0.0)


def test_hv_annualized_factor():
    """验证年化因子 sqrt(252) 正确应用。"""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    # 交替涨跌场景：前 20 个 log_return 有波动
    close = [100 + (i % 2) * 2 for i in range(30)]
    df = pd.DataFrame(
        {
            "date": dates,
            "code": "000001.SZ",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000_000,
        }
    )
    result = calc_hv(df, window=20)
    val = result.iloc[20]
    # 手动算：log_returns[1:21] 的 std * sqrt(252)
    log_ret = np.log(np.array(close[1:]) / np.array(close[:-1]))
    expected = np.std(log_ret[1:21], ddof=1) * np.sqrt(252)
    assert np.isclose(val, expected, atol=1e-10)


def test_hv_multiple_codes():
    """多只股票应分别计算。"""
    dates = pd.date_range("2024-01-01", periods=25, freq="B")
    np.random.seed(42)
    close_a = 100 + np.cumsum(np.random.randn(25) * 0.5)
    np.random.seed(99)
    close_b = 200 + np.cumsum(np.random.randn(25) * 2.0)
    df = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "code": ["000001.SZ"] * 25 + ["000002.SZ"] * 25,
            "open": np.concatenate([close_a - 0.2, close_b - 0.5]),
            "high": np.concatenate([close_a + 0.5, close_b + 1.0]),
            "low": np.concatenate([close_a - 0.5, close_b - 1.0]),
            "close": np.concatenate([close_a, close_b]),
            "volume": [1_000_000] * 50,
        }
    )
    result = calc_hv(df, window=20)
    assert len(result) == 50
    # 两只股票各自有有效值，且 HV 不同
    assert result.iloc[20] != result.iloc[45]
