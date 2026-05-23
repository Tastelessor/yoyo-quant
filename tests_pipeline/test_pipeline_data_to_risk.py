"""管道测试：data → factors → strategies → risk 完整数据流。

用 mock 数据验证模块间串联是否正确，不依赖外部 API。
"""

import numpy as np
import pandas as pd
import pytest

from src.data.filters import detect_limit_price, detect_suspension
from src.factors.volatility import calc_hv
from src.risk.tradability import enforce_t1, filter_tradable
from src.strategies.mean_reversion import mean_reversion_signal


@pytest.fixture
def multi_stock_ohlcv():
    """多只股票、包含涨跌停和停牌的行情数据。"""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    np.random.seed(42)

    # 股票 A：正常波动
    close_a = 100 + np.cumsum(np.random.randn(30) * 0.5)
    # 股票 B：先涨后跌，触发涨跌停
    close_b = np.concatenate([np.full(20, 10.0), [11.0, 12.1, 13.31, 9.0, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5]])
    # 股票 C：有停牌日（volume=0）
    close_c = 50 + np.cumsum(np.random.randn(30) * 0.3)
    vol_c = np.full(30, 1_000_000)
    vol_c[15] = 0  # 第 16 天停牌

    def make_stock(code, close, vol_base=1_000_000):
        vol = np.full(len(close), vol_base) if isinstance(vol_base, int) else vol_base
        return pd.DataFrame(
            {
                "date": dates[: len(close)],
                "code": code,
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": vol,
            }
        )

    return pd.concat(
        [
            make_stock("000001.SZ", close_a),
            make_stock("000002.SZ", close_b),
            make_stock("000003.SZ", close_c, vol_base=vol_c),
        ],
        ignore_index=True,
    )


def test_full_pipeline_produces_valid_signals(multi_stock_ohlcv):
    """完整管道应输出结构合法的过滤后信号。"""
    # Step 1: data 层标注市场状态
    market = detect_limit_price(multi_stock_ohlcv)
    market = detect_suspension(market)

    assert "limit_up" in market.columns
    assert "limit_down" in market.columns
    assert "is_suspended" in market.columns

    # Step 2: factors 层计算 HV
    hv = calc_hv(multi_stock_ohlcv, window=20)
    assert isinstance(hv, pd.Series)
    assert len(hv) == len(multi_stock_ohlcv)

    # Step 3: strategies 层生成信号
    signals = mean_reversion_signal(multi_stock_ohlcv, window=20)
    assert set(signals.columns) == {"date", "code", "signal", "confidence"}
    assert set(signals["signal"].unique()).issubset({-1, 0, 1})

    # Step 4: risk 层过滤不可交易信号
    filtered = filter_tradable(market, signals)
    assert set(filtered.columns) == {"date", "code", "signal", "confidence"}

    # Step 5: risk 层执行 T+1
    final = enforce_t1(filtered)
    assert set(final.columns) == {"date", "code", "signal", "confidence"}
    assert set(final["signal"].unique()).issubset({-1, 0, 1})
    assert (final["confidence"] >= 0).all()
    assert (final["confidence"] <= 1).all()


def test_pipeline_preserves_multi_stock_independence(multi_stock_ohlcv):
    """管道中多只股票应独立计算，不互相污染。"""
    market = detect_limit_price(multi_stock_ohlcv)
    market = detect_suspension(market)
    signals = mean_reversion_signal(multi_stock_ohlcv, window=20)
    filtered = filter_tradable(market, signals)

    # 每只股票的信号数量应与原始数据行数一致
    for code in ["000001.SZ", "000002.SZ", "000003.SZ"]:
        input_rows = len(multi_stock_ohlcv[multi_stock_ohlcv["code"] == code])
        output_rows = len(filtered[filtered["code"] == code])
        assert input_rows == output_rows, f"{code} 行数不一致: {input_rows} vs {output_rows}"


def test_pipeline_filters_limit_up_buy(multi_stock_ohlcv):
    """涨停日的买入信号应被管道过滤。"""
    market = detect_limit_price(multi_stock_ohlcv)
    market = detect_suspension(market)
    signals = mean_reversion_signal(multi_stock_ohlcv, window=20)
    filtered = filter_tradable(market, signals)

    # 找到涨停日
    limit_up_days = market[market["limit_up"]]
    for _, row in limit_up_days.iterrows():
        day_signal = filtered[
            (filtered["date"] == row["date"]) & (filtered["code"] == row["code"])
        ]
        if not day_signal.empty:
            # 涨停日的买入信号应被置为 0
            assert day_signal["signal"].iloc[0] != 1, (
                f"涨停日 {row['date']} {row['code']} 仍有买入信号"
            )


def test_pipeline_suspension_blocks_all_signals(multi_stock_ohlcv):
    """停牌日的所有信号应被管道过滤。"""
    market = detect_limit_price(multi_stock_ohlcv)
    market = detect_suspension(market)
    signals = mean_reversion_signal(multi_stock_ohlcv, window=20)
    filtered = filter_tradable(market, signals)

    suspended_days = market[market["is_suspended"]]
    for _, row in suspended_days.iterrows():
        day_signal = filtered[
            (filtered["date"] == row["date"]) & (filtered["code"] == row["code"])
        ]
        if not day_signal.empty:
            assert day_signal["signal"].iloc[0] == 0, (
                f"停牌日 {row['date']} {row['code']} 仍有信号"
            )
