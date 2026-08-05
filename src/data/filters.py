"""A 股市场状态标注。

为行情数据附加涨跌停、停牌等布尔列，供下游模块使用。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 创业板 / 科创板涨跌停幅度为 20% 的代码前缀
_LIMIT_20PCT_PREFIXES = ("300", "301", "302", "688", "689")


def detect_limit_price(
    df: pd.DataFrame,
    limit_pct: float = 0.10,
) -> pd.DataFrame:
    """检测涨跌停。

    判定规则：收盘价达到涨跌停价（前收盘按涨跌停幅度四舍五入到分）即判定。

    前收盘优先取 ``pre_close`` 列（tushare 官方前收，除权除息日已调整），
    缺失时回退为 ``groupby(code)`` 的 ``close.shift(1)``（旧行为，
    除权日会误判，仅作兼容兜底）。

    涨跌停幅度按板块区分：创业板/科创板（300/301/302/688/689 前缀）为
    20%，其余板块取 ``limit_pct``（默认 10%）。ST（5%）、北交所（30%）
    不在本函数支持范围内，应在上游股票池过滤。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, close 列；含 pre_close 列时优先使用。
    limit_pct : float
        非创业板/科创板的涨跌停幅度，默认 0.10（10%）。

    Returns
    -------
    DataFrame
        原 df 增加 limit_up (bool) 和 limit_down (bool) 列，
        按 (code, date) 升序排序。
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    if "pre_close" in df.columns:
        prev_close = df["pre_close"]
    else:
        prev_close = df.groupby("code")["close"].shift(1)

    has_prev = prev_close.notna() & (prev_close != 0)

    limit_pct_arr = np.where(
        df["code"].astype(str).str.startswith(_LIMIT_20PCT_PREFIXES),
        0.20,
        limit_pct,
    )

    # 涨跌停价 = round(前收盘 × (1 ± 幅度), 2)（四舍五入到分）；
    # 用价格比较而非涨幅比较，避免 pre_close 含奇数分时
    # （如 10.03 → 涨停价 11.03，涨幅仅 9.97%）漏判。
    # 0.001 容差吸收浮点误差（最小价位 0.01，不会误标）。
    limit_up_price = np.round(prev_close * (1 + limit_pct_arr), 2)
    limit_down_price = np.round(prev_close * (1 - limit_pct_arr), 2)
    limit_up = (df["close"] >= limit_up_price - 0.001) & has_prev
    limit_down = (df["close"] <= limit_down_price + 0.001) & has_prev

    df = df.copy()
    df["limit_up"] = limit_up
    df["limit_down"] = limit_down
    return df


def detect_suspension(
    df: pd.DataFrame,
    trade_dates: pd.DatetimeIndex | list | None = None,
) -> pd.DataFrame:
    """检测停牌日。

    两重判定：
    1. 现有行中 ``volume == 0`` 标为停牌（保留旧规则）；
    2. 按交易日网格补齐缺失交易日：tushare ``daily`` 对停牌日无记录，
       只有补齐行才能让下游（filter_tradable 等）看到停牌。补齐行的
       OHLCV / pre_close 为 NaN、volume 为 0（保持 volume==0 规则幂等，
       二次运行仍被识别为停牌），is_suspended=True；已存在的
       limit_up / limit_down 列在补齐行上填 False。

    每只股票只在首行日期（上市日/拉取起点）之后补齐，之前不补。
    网格上界裁剪到数据实际最大日期：调用方可能传自然日/未来日期的
    交易日序列（如 ``fetch_full_market`` 的 END=今天），行情未覆盖到
    网格上界时，不裁剪会把全市场最后若干交易日误标为停牌；停牌至今的
    股票缺失日仍会补到全市场最新数据日。

    Parameters
    ----------
    df : DataFrame
        必须包含 date, code, volume 列。
    trade_dates : DatetimeIndex | list | None
        交易日序列（升序）。None 时用 df 内所有股票 date 的并集推断
        （节假日不在任何股票数据中，自动排除）。

    Returns
    -------
    DataFrame
        原 df 增加 is_suspended (bool) 列并补齐停牌行，
        按 (code, date) 升序排序。
    """
    df = df.copy()
    df["is_suspended"] = df["volume"] == 0

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    if trade_dates is None:
        grid_dates = sorted(df["date"].unique())
    else:

        def _to_naive(value: pd.Timestamp) -> pd.Timestamp:
            ts = pd.Timestamp(value)
            return ts.tz_localize(None) if ts.tzinfo is not None else ts

        grid_dates = sorted({_to_naive(d) for d in trade_dates})
    grid_index = pd.DatetimeIndex(grid_dates)
    # 上界裁剪到数据实际最大日期：调用方可能传自然日/未来日期的交易日网格
    # （如 fetch_full_market 的 END=今天），行情数据未覆盖到网格上界时，
    # 不裁剪会把全市场最后若干交易日误标为停牌。
    grid_hi = min(grid_index.max(), df["date"].max())

    # MultiIndex 一次性网格化补齐（全市场量级下避免逐股票 Python 循环 + concat）：
    # 每只股票 × 全部交易日展开，缺失格即为停牌补齐行。
    # 输入 (code, date) 应唯一（同一股票同一天只有一条行情），重复行防御性去重。
    unique = df.drop_duplicates(subset=["code", "date"])
    full_grid = pd.MultiIndex.from_product(
        [unique["code"].unique(), grid_index], names=["code", "date"]
    )
    result = unique.set_index(["code", "date"]).reindex(full_grid).reset_index()
    # 每只股票首行日期（上市日/拉取起点）之前不补
    lo_map = unique.groupby("code")["date"].min()
    result = result[result["date"] >= result["code"].map(lo_map)]
    result = result[result["date"] <= grid_hi]
    # 补齐行（reindex 产生的 NaN 行）：volume 填 0 保持 volume==0 规则幂等
    # （二次运行仍能被识别为停牌）；is_suspended 填 True；limit 列填 False
    result["is_suspended"] = result["is_suspended"].fillna(True)
    result["volume"] = result["volume"].fillna(0.0)
    for col in ("limit_up", "limit_down"):
        if col in result.columns:
            result[col] = result[col].fillna(False)

    return result.sort_values(["code", "date"]).reset_index(drop=True)
