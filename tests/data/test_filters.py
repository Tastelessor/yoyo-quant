import pandas as pd
import pytest

from data.filters import detect_limit_price, detect_suspension


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


# --- detect_limit_price: pre_close 优先 ---


def test_limit_price_prefers_pre_close_on_ex_dividend():
    """除权日应使用官方 pre_close 而非 shift(1)，避免误判跌停。

    10 送 10 场景：昨收 10.0，除权日官方前收调整为 5.0，当天收 5.2（+4%）。
    用 pre_close → 非涨跌停；若用 shift(1) → (5.2-10)/10 = -48% 误判跌停。
    """
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": "000001.SZ",
            "close": [10.0, 5.2],
            "pre_close": [10.0, 5.0],
        }
    )
    result = detect_limit_price(df)
    assert not bool(result.loc[1, "limit_up"])
    assert not bool(result.loc[1, "limit_down"])


def test_limit_price_falls_back_to_shift_without_pre_close():
    """无 pre_close 列时回退到 shift(1)（旧行为）。"""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": "000001.SZ",
            "close": [10.0, 5.2],
        }
    )
    result = detect_limit_price(df)
    # (5.2-10)/10 = -48% → 误判为跌停（旧行为保留）
    assert bool(result.loc[1, "limit_down"])


# --- detect_limit_price: 板块涨跌停幅度 ---


def test_limit_price_20pct_board_for_chinext_and_star():
    """创业板/科创板（300/301/302/688/689）涨 15% 未到 20% 板，不应标涨停。"""
    codes = [
        "300001.SZ",
        "301001.SZ",
        "302001.SZ",
        "688001.SH",
        "689001.SH",
        "600000.SH",
        "000001.SZ",
    ]
    rows = []
    for c in codes:
        rows.append(
            {
                "date": pd.Timestamp("2024-01-02"),
                "code": c,
                "close": 10.0,
                "pre_close": 10.0,
            }
        )
        rows.append(
            {
                "date": pd.Timestamp("2024-01-03"),
                "code": c,
                "close": 11.5,
                "pre_close": 10.0,
            }
        )
    df = pd.DataFrame(rows)
    result = detect_limit_price(df)
    second_day = result[result["date"] == pd.Timestamp("2024-01-03")]
    board_20 = {"300001.SZ", "301001.SZ", "302001.SZ", "688001.SH", "689001.SH"}
    for _, row in second_day.iterrows():
        if row["code"] in board_20:
            assert not bool(row["limit_up"]), f"{row['code']} 20% 板涨 15% 不应涨停"
        else:
            assert bool(row["limit_up"]), f"{row['code']} 10% 板涨 15% 应涨停"


def test_limit_price_rounding_to_fen():
    """涨停价按分四舍五入：pre_close=10.03 → 涨停价 11.03，收盘 11.03 应标涨停。

    10% 板：(11.03-10.03)/10.03 ≈ 9.97% < 10%，按涨幅判定会漏判。
    """
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["000001.SZ"] * 2,
            "close": [10.03, 11.03],  # 11.03 == round(10.03 * 1.10, 2)
            "pre_close": [10.00, 10.03],
        }
    )
    result = detect_limit_price(df)
    assert not bool(result.loc[0, "limit_up"])
    assert bool(result.loc[1, "limit_up"])


def test_limit_down_rounding_to_fen():
    """跌停价按分四舍五入：pre_close=10.03 → 跌停价 9.03，收盘 9.03 应标跌停。"""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["000001.SZ"] * 2,
            "close": [10.03, 9.03],  # 9.03 == round(10.03 * 0.90, 2)
            "pre_close": [10.00, 10.03],
        }
    )
    result = detect_limit_price(df)
    assert bool(result.loc[1, "limit_down"])


def test_limit_price_rounding_to_fen_20pct_board():
    """20% 板同规则：300001 pre_close=10.03 → 涨停价 round(12.036,2)=12.04。"""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["300001.SZ"] * 2,
            "close": [10.03, 12.04],
            "pre_close": [10.00, 10.03],
        }
    )
    result = detect_limit_price(df)
    assert not bool(result.loc[0, "limit_up"])
    assert bool(result.loc[1, "limit_up"])


# --- detect_suspension ---


def test_detect_suspension(ohlcv_data):
    """成交量为 0 应标记为停牌（原规则保留）。"""
    result = detect_suspension(ohlcv_data)
    assert bool(result.loc[4, "is_suspended"])
    assert not bool(result.loc[0, "is_suspended"])


# --- detect_suspension: 交易日网格补齐 ---


def test_suspension_fills_missing_trading_days():
    """缺失交易日应补齐一行并标 is_suspended=True；volume=0 行仍标停牌。"""
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
    )

    df_a = pd.DataFrame(
        {
            "date": dates,
            "code": ["A"] * 5,
            "close": [1.0] * 5,
            "volume": [100.0] * 5,
        }
    )
    df_a = df_a[df_a["date"] != pd.Timestamp("2024-01-04")]  # A 缺 01-04（停牌）

    df_b = pd.DataFrame(
        {
            "date": dates,
            "code": ["B"] * 5,
            "close": [1.0] * 5,
            "volume": [100.0] * 5,
        }
    )
    df_b.loc[df_b["date"] == pd.Timestamp("2024-01-04"), "volume"] = (
        0  # B 该日 volume=0
    )

    combined = pd.concat([df_a, df_b], ignore_index=True)
    result = detect_suspension(combined, trade_dates=dates)

    # A 的 01-04 被补齐
    row_a = result[
        (result["code"] == "A") & (result["date"] == pd.Timestamp("2024-01-04"))
    ]
    assert len(row_a) == 1
    assert bool(row_a["is_suspended"].iloc[0])
    assert pd.isna(row_a["close"].iloc[0])
    # B 的 01-04 原行 volume=0 仍标停牌
    row_b = result[
        (result["code"] == "B") & (result["date"] == pd.Timestamp("2024-01-04"))
    ]
    assert len(row_b) == 1
    assert bool(row_b["is_suspended"].iloc[0])
    # 每只股票补齐后 = 交易日网格行数
    for code in ["A", "B"]:
        assert len(result[result["code"] == code]) == len(dates)
    # 非停牌日不误标
    assert not bool(
        result[
            (result["code"] == "A") & (result["date"] == pd.Timestamp("2024-01-05"))
        ]["is_suspended"].iloc[0]
    )


def test_suspension_does_not_fill_before_first_date():
    """上市日之前的交易日不应补齐为停牌。"""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-03", "2024-01-08"]),  # 01-02 之前不补
            "code": ["C"] * 2,
            "close": [1.0, 1.1],
            "volume": [100.0, 100.0],
        }
    )
    trade_dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-08"])
    result = detect_suspension(df, trade_dates=trade_dates)
    assert pd.Timestamp("2024-01-02") not in set(result["date"])


def test_suspension_infers_grid_from_data_when_trade_dates_none():
    """trade_dates=None 时用所有股票日期的并集推断网格。"""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    df_a = pd.DataFrame(
        {
            "date": dates,
            "code": ["A"] * 3,
            "close": [1.0] * 3,
            "volume": [100.0] * 3,
        }
    )
    df_a = df_a[df_a["date"] != pd.Timestamp("2024-01-03")]
    df_b = pd.concat(
        [
            df_a,
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-03"]),
                    "code": ["B"],
                    "close": [1.0],
                    "volume": [100.0],
                }
            ),
        ],
        ignore_index=True,
    )
    combined = pd.concat([df_a, df_b], ignore_index=True)
    result = detect_suspension(combined)
    # A 缺 01-03，但 B 有 → 并集包含 01-03 → A 补齐
    row = result[
        (result["code"] == "A") & (result["date"] == pd.Timestamp("2024-01-03"))
    ]
    assert len(row) == 1
    assert bool(row["is_suspended"].iloc[0])


def test_suspension_preserves_existing_limit_flags_on_filled_rows():
    """先 detect_limit_price 再 detect_suspension 时，补齐行的 limit 列应为 False。"""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    df = pd.DataFrame(
        {
            "date": dates,
            "code": ["A"] * 2,
            "close": [10.0, 10.5],
            "volume": [100.0, 100.0],
            "pre_close": [10.0, 10.0],
        }
    )
    df = df[df["date"] != pd.Timestamp("2024-01-03")]
    df = detect_limit_price(df)
    result = detect_suspension(df, trade_dates=dates)
    row = result[result["date"] == pd.Timestamp("2024-01-03")]
    assert len(row) == 1
    assert not bool(row["limit_up"].iloc[0])
    assert not bool(row["limit_down"].iloc[0])
    assert bool(row["is_suspended"].iloc[0])
