"""集成测试：验证 tushare API 可达性与数据结构。

需要真实 TUSHARE_TOKEN，未设置时自动跳过。
运行方式：TUSHARE_TOKEN=xxx pytest tests/data/test_fetcher_integration.py -v
"""

import os

import pandas as pd
import pytest

ts = pytest.importorskip("tushare", reason="tushare 未安装，跳过集成测试")
from src.data.fetcher import fetch_daily  # noqa: E402

EXPECTED_COLUMNS = ["date", "code", "open", "high", "low", "close", "volume"]

pytestmark = pytest.mark.skipif(
    not os.environ.get("TUSHARE_TOKEN"),
    reason="TUSHARE_TOKEN 未设置，跳过集成测试",
)


def test_api_reachable():
    """tushare API 应可正常返回数据。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert len(df) > 0, "API 返回了空数据，可能连接失败"


def test_columns_match_schema():
    """返回的 DataFrame 列名应严格匹配 OHLCV schema。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert list(df.columns) == EXPECTED_COLUMNS


def test_date_is_datetime():
    """date 列应为 datetime64 类型。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_code_is_string():
    """code 列应为字符串类型。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["code"].dtype == "object"
    assert all(df["code"] == "000001")


def test_ohlcv_columns_are_numeric():
    """open/high/low/close/volume 应为数值类型。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    for col in ["open", "high", "low", "close", "volume"]:
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} 不是数值类型"


def test_sorted_by_date():
    """结果应按日期升序排列。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["date"].is_monotonic_increasing


def test_no_null_in_ohlcv():
    """OHLCV 核心字段不应有空值。"""
    df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    for col in ["open", "high", "low", "close", "volume"]:
        assert df[col].notna().all(), f"{col} 存在空值"


def test_sh_stock_mapping():
    """沪市股票（600519）应正确获取。"""
    df = fetch_daily("600519", "2024-01-02", "2024-01-08")
    assert len(df) > 0
    assert all(df["code"] == "600519")
