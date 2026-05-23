import pandas as pd
import pytest

from src.data.filters import detect_limit_price, detect_suspension


@pytest.fixture
def ohlcv_data():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
            ),
            "code": "000001.SZ",
            "open": [10.0, 11.0, 12.1, 10.0, 10.0],
            "high": [11.0, 12.1, 13.31, 10.0, 10.5],
            "low": [10.0, 11.0, 12.1, 9.0, 9.5],
            "close": [11.0, 12.1, 13.31, 9.0, 10.0],
            "volume": [1_000_000, 1_200_000, 500_000, 800_000, 0],
        }
    )


# --- detect_limit_price ---


def test_detect_limit_up(ohlcv_data):
    """涨 10% 应标记为涨停。"""
    result = detect_limit_price(ohlcv_data)
    # 10.0 → 11.0 = +10% → limit_up
    assert bool(result.loc[1, "limit_up"])
    # 11.0 → 12.1 = +10% → limit_up
    assert bool(result.loc[2, "limit_up"])


def test_detect_limit_down(ohlcv_data):
    """跌 10% 应标记为跌停。"""
    result = detect_limit_price(ohlcv_data)
    # 12.1 → 9.0 ≈ -25.6% → limit_down
    assert bool(result.loc[3, "limit_down"])


def test_first_day_no_limit(ohlcv_data):
    """首日无前收盘，不应判定涨跌停。"""
    result = detect_limit_price(ohlcv_data)
    assert not bool(result.loc[0, "limit_up"])
    assert not bool(result.loc[0, "limit_down"])


def test_no_limit_within_range(ohlcv_data):
    """涨跌幅 >= 10% 应标记。"""
    result = detect_limit_price(ohlcv_data)
    # 9.0 → 10.0 = +11.1% >= 10% → limit_up
    assert bool(result.loc[4, "limit_up"])


# --- detect_suspension ---


def test_detect_suspension(ohlcv_data):
    """成交量为 0 应标记为停牌。"""
    result = detect_suspension(ohlcv_data)
    assert bool(result.loc[4, "is_suspended"])
    assert not bool(result.loc[0, "is_suspended"])
