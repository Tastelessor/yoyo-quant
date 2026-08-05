"""权威交易日历（tushare trade_cal）。

P1-01：为数据层提供权威交易日历接口，替代从行情 ``data["date"].unique()`` 推断
交易日的做法。停牌日/节假日缺失会导致 PIT 面板网格错位（build_earnings_panel /
build_quality_panel 的 trade_dates 网格），本模块是这些网格的权威来源。

公开接口
--------
fetch_trade_calendar : 拉取并缓存交易所完整日历（含节假日/周末标记）
fetch_trade_dates    : 返回 [start, end] 区间内的交易日 DatetimeIndex
is_trading_day       : 判断某日是否为交易日

数据来源为 tushare ``trade_cal``（沪深交易所官方日历），parquet 缓存于
``data/raw/trade_cal/{exchange}.parquet``。缓存为一次全量拉取
[1990-01-01, 2030-12-31]，覆盖历史回测与"今天是否交易日"判断。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_PROXY_URL = "https://quantdata888.duckdns.org"

# 一次全量拉取的覆盖区间（tushare trade_cal 参数，按年分片）
_FETCH_START_YEAR = 1990
_FETCH_END_YEAR = 2030

# 交易日历契约列（tushare 原始列序）
TRADE_CAL_SCHEMA = ["exchange", "cal_date", "is_open", "pretrade_date"]


def _to_naive(value: str | pd.Timestamp) -> pd.Timestamp:
    """归一化到无时区日期，便于与缓存中的 naive cal_date 比较。"""
    ts = pd.Timestamp(value)
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _fetch_calendar_by_year(api, exchange: str) -> pd.DataFrame:
    """按年分片拉取交易日历，规避 tushare 单次行数限制导致的静默截断。

    未公布的未来年份返回空，直接跳过；全部为空时返回空 DataFrame。
    """
    frames: list[pd.DataFrame] = []
    for year in range(_FETCH_START_YEAR, _FETCH_END_YEAR + 1):
        raw = api.trade_cal(
            exchange=exchange,
            start_date=f"{year}0101",
            end_date=f"{year}1231",
        )
        if raw is None or raw.empty:
            continue
        frames.append(raw[TRADE_CAL_SCHEMA])
    if not frames:
        return pd.DataFrame(columns=TRADE_CAL_SCHEMA)
    return pd.concat(frames, ignore_index=True)


def fetch_trade_calendar(
    exchange: str = "SSE",
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """拉取并缓存交易所完整交易日历（tushare trade_cal）。

    Parameters
    ----------
    exchange : str
        交易所代码，沪深 A 股取 "SSE"（与 "SZSE" 节假日一致）。默认 "SSE"。
    cache_dir : Path | str | None
        缓存目录。None 时使用 data/raw/trade_cal/。

    Returns
    -------
    DataFrame
        列：exchange, cal_date, is_open, pretrade_date。
        cal_date 为 datetime64（升序、无重复），is_open 为 int（1=开市, 0=闭市）。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "trade_cal"
    else:
        cache_dir = Path(cache_dir)

    cache_file = cache_dir / f"{exchange}.parquet"
    if cache_file.exists():
        cached = pd.read_parquet(cache_file)
        missing = [c for c in TRADE_CAL_SCHEMA if c not in cached.columns]
        if missing:
            raise ValueError(
                f"交易日历缓存 {cache_file} 缺少列 {missing}，请删除该文件后重新拉取"
            )
        if not cached.empty and cached["cal_date"].min() > pd.Timestamp("1991-01-01"):
            logger.warning(
                "交易日历缓存 %s 起始日 %s 偏晚（可能被截断），建议删除后重新拉取",
                cache_file,
                cached["cal_date"].min().date(),
            )
        return cached

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    raw = _fetch_calendar_by_year(api, exchange)

    if raw is None or raw.empty:
        return pd.DataFrame(columns=TRADE_CAL_SCHEMA)

    df = raw[TRADE_CAL_SCHEMA].copy()
    df["cal_date"] = pd.to_datetime(df["cal_date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["cal_date"])
    df = (
        df.sort_values("cal_date")
        .drop_duplicates(subset=["cal_date"])
        .reset_index(drop=True)
    )

    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_file, index=False)
    return df


def fetch_trade_dates(
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    exchange: str = "SSE",
    cache_dir: Path | str | None = None,
) -> pd.DatetimeIndex:
    """返回 [start, end] 闭区间内的交易日序列（is_open=1）。

    Parameters
    ----------
    start, end : str | pd.Timestamp | None
        闭区间边界，格式 "YYYY-MM-DD" 或 Timestamp。None 表示不设边界。
    exchange : str
        交易所代码，默认 "SSE"。
    cache_dir : Path | str | None
        缓存目录，透传给 :func:`fetch_trade_calendar`。

    Returns
    -------
    pd.DatetimeIndex
        升序、无重复的交易日（datetime64）。区间内无交易日时为空。
    """
    cal = fetch_trade_calendar(exchange=exchange, cache_dir=cache_dir)
    dates = cal.loc[cal["is_open"] == 1, "cal_date"]

    if start is not None:
        dates = dates[dates >= _to_naive(start)]
    if end is not None:
        dates = dates[dates <= _to_naive(end)]

    return pd.DatetimeIndex(dates)


def is_trading_day(
    date: str | pd.Timestamp,
    exchange: str = "SSE",
    cache_dir: Path | str | None = None,
) -> bool:
    """判断某日是否为交易所交易日。

    Parameters
    ----------
    date : str | pd.Timestamp
        待判断日期（仅日期部分参与判断）。
    exchange : str
        交易所代码，默认 "SSE"。
    cache_dir : Path | str | None
        缓存目录，透传给 :func:`fetch_trade_calendar`。

    Returns
    -------
    bool
        True 表示开市；周末、节假日或不在日历中的日期返回 False。
    """
    cal = fetch_trade_calendar(exchange=exchange, cache_dir=cache_dir)
    target = _to_naive(date).normalize()
    match = cal.loc[cal["cal_date"] == target, "is_open"]
    if match.empty:
        return False
    return bool(match.iloc[0] == 1)
