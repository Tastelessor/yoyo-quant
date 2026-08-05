"""清洗入口测试：clean_market_data 标注三列并补齐停牌日。"""

import pandas as pd
import pytest

from data.clean import clean_market_data


@pytest.fixture
def raw_multi_stock():
    """两只股票，A 缺 2024-01-04（停牌），B 完整。"""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])

    def make(code, close_start):
        return pd.DataFrame(
            {
                "date": dates,
                "code": [code] * 4,
                "open": [close_start + i * 0.1 for i in range(4)],
                "high": [close_start + i * 0.1 + 0.5 for i in range(4)],
                "low": [close_start + i * 0.1 - 0.5 for i in range(4)],
                "close": [close_start + i * 0.1 for i in range(4)],
                "pre_close": [close_start + (i - 1) * 0.1 for i in range(4)],
                "volume": [1_000_000.0] * 4,
            }
        )

    df_a = make("A", 10.0)
    df_a = df_a[df_a["date"] != pd.Timestamp("2024-01-04")]
    df_b = make("B", 20.0)
    return pd.concat([df_a, df_b], ignore_index=True)


def test_clean_market_data_adds_three_bool_columns(raw_multi_stock):
    """输出应包含 limit_up / limit_down / is_suspended 三列且为 bool。"""
    trade_dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    result = clean_market_data(raw_multi_stock, trade_dates=trade_dates)
    for col in ("limit_up", "limit_down", "is_suspended"):
        assert col in result.columns
        assert result[col].dtype == bool, f"{col} dtype 应为 bool"


def test_clean_market_data_fills_suspension_gaps(raw_multi_stock):
    """停牌日应补齐为 is_suspended=True 的行。"""
    trade_dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    result = clean_market_data(raw_multi_stock, trade_dates=trade_dates)
    row = result[
        (result["code"] == "A") & (result["date"] == pd.Timestamp("2024-01-04"))
    ]
    assert len(row) == 1
    assert bool(row["is_suspended"].iloc[0])
    assert pd.isna(row["close"].iloc[0])
    # B 的 01-04 不是停牌
    row_b = result[
        (result["code"] == "B") & (result["date"] == pd.Timestamp("2024-01-04"))
    ]
    assert not bool(row_b["is_suspended"].iloc[0])


def test_clean_market_data_sorted_no_duplicates(raw_multi_stock):
    """输出应按 (code, date) 排序且无重复行。"""
    trade_dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    result = clean_market_data(raw_multi_stock, trade_dates=trade_dates)
    assert not result.duplicated(subset=["date", "code"]).any()
    grouped = result.groupby("code", sort=False)
    for _, grp in grouped:
        assert grp["date"].is_monotonic_increasing


def test_clean_market_data_detects_limit_move():
    """接近涨停幅度的行情应被标为 limit_up。"""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["600000.SH"] * 2,
            "open": [10.0, 10.0],
            "high": [10.0, 11.0],
            "low": [10.0, 10.0],
            "close": [10.0, 11.0],
            "pre_close": [10.0, 10.0],
            "volume": [1_000_000.0, 1_000_000.0],
        }
    )
    result = clean_market_data(df, trade_dates=df["date"])
    assert bool(result.loc[1, "limit_up"])
