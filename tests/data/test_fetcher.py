from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data import OHLCV_SCHEMA
from src.data.fetcher import fetch_daily


@pytest.fixture
def fake_tushare_data():
    """模拟 tushare daily 返回的数据。"""
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": ["20240102", "20240103", "20240104", "20240105", "20240108"],
            "open": [10.0, 10.5, 10.3, 10.8, 11.0],
            "close": [10.3, 10.8, 10.6, 11.0, 11.2],
            "high": [10.5, 11.0, 10.9, 11.2, 11.5],
            "low": [9.8, 10.2, 10.1, 10.6, 10.8],
            "vol": [1_000_000, 1_200_000, 900_000, 1_500_000, 1_100_000],
        }
    )


@pytest.fixture
def mock_api(fake_tushare_data):
    """mock tushare pro_api。"""
    with patch("src.data.fetcher.ts") as mock_ts:
        mock_api = MagicMock()
        mock_api.daily.return_value = fake_tushare_data
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


def test_fetch_daily_returns_ohlcv(mock_api):
    """fetch_daily 应返回符合 OHLCV schema 的 DataFrame。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert list(df.columns) == OHLCV_SCHEMA
    assert len(df) == 5


def test_fetch_daily_column_mapping(mock_api):
    """tushare 列名应正确映射。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["code"].iloc[0] == "000001"
    assert df["open"].iloc[0] == 10.0
    assert df["close"].iloc[0] == 10.3
    assert df["high"].iloc[0] == 10.5
    assert df["low"].iloc[0] == 9.8
    assert df["volume"].iloc[0] == 1_000_000


def test_fetch_daily_date_dtype(mock_api):
    """date 列应为 datetime64 类型。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_fetch_daily_passes_params(mock_api):
    """应正确传递参数给 tushare。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        fetch_daily("600519", "2024-01-01", "2024-12-31")
    mock_api.daily.assert_called_once_with(
        ts_code="600519.SH",
        start_date="20240101",
        end_date="20241231",
    )


def test_fetch_daily_sorted_by_date(mock_api, fake_tushare_data):
    """结果应按日期排序。"""
    shuffled = fake_tushare_data.sample(frac=1, random_state=42)
    mock_api.daily.return_value = shuffled
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["date"].is_monotonic_increasing


def test_fetch_daily_empty_returns_schema(mock_api):
    """空数据应返回带正确列的空 DataFrame。"""
    mock_api.daily.return_value = pd.DataFrame()
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-01", "2024-01-01")
    assert list(df.columns) == OHLCV_SCHEMA
    assert len(df) == 0


def test_fetch_daily_no_token_raises():
    """未设置 TUSHARE_TOKEN 应抛出 ValueError。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TUSHARE_TOKEN 未设置"):
            fetch_daily("000001", "2024-01-01", "2024-01-01")
