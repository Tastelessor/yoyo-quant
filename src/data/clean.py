"""行情数据清洗入口。

将原始 OHLCV 数据标注为含 limit_up / limit_down / is_suspended 的
清洗后市场数据，供回测 / 实盘管道与风控模块使用。
"""

from __future__ import annotations

import pandas as pd

from data.filters import detect_limit_price, detect_suspension


def clean_market_data(
    df: pd.DataFrame,
    trade_dates: pd.DatetimeIndex | list | None = None,
) -> pd.DataFrame:
    """清洗行情数据：标注涨跌停、补齐并标注停牌日。

    依次执行 detect_suspension（补齐缺失交易日网格 + volume==0 标注）
    与 detect_limit_price（pre_close 优先、按板块区分涨跌停幅度）。

    Parameters
    ----------
    df : DataFrame
        原始 OHLCV 数据，必须包含 date, code, close, volume 列；
        含 pre_close 列时涨跌停判定更准确（fetch_daily 会返回）。
    trade_dates : DatetimeIndex | list | None
        交易日序列，传给 detect_suspension 用于补齐停牌日。
        None 时从 df 内推断。

    Returns
    -------
    DataFrame
        含 limit_up / limit_down / is_suspended 三列，按 (code, date)
        升序排序，停牌日已补齐为 is_suspended=True 的行。
    """
    result = detect_suspension(df, trade_dates=trade_dates)
    return detect_limit_price(result)
