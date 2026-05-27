import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_PROXY_URL = "http://124.222.60.121:8020/"


def _to_ts_code(code: str) -> str:
    """将纯数字代码转换为 tushare 格式 (000001 -> 000001.SZ)。"""
    if code.startswith("6"):
        return f"{code}.SH"
    return f"{code}.SZ"


def fetch_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """获取 A 股日线行情 (tushare)。

    Parameters
    ----------
    code : str
        股票代码，如 "000001"。
    start : str
        开始日期，格式 "YYYY-MM-DD"。
    end : str
        结束日期，格式 "YYYY-MM-DD"。

    Returns
    -------
    DataFrame
        符合 OHLCV schema 的日线数据。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_code = _to_ts_code(code)

    # Retry with backoff on rate limit
    raw = None
    for attempt in range(3):
        try:
            raw = api.daily(
                ts_code=ts_code,
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
            )
            break
        except Exception as e:
            if "过快" in str(e) or "频率" in str(e):
                wait = 2 ** (attempt + 1)
                logger.warning("Rate limited on %s, retrying in %ds...", code, wait)
                time.sleep(wait)
            else:
                raise

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["date", "code", "open", "high", "low", "close", "volume"]
        )

    df = raw.rename(columns={"trade_date": "date", "vol": "volume"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "code", "open", "high", "low", "close", "volume"]]


def fetch_index_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """获取指数日线行情 (tushare index_daily)。

    Parameters
    ----------
    code : str
        指数代码，如 "000300"（沪深300）。
    start : str
        开始日期，格式 "YYYY-MM-DD"。
    end : str
        结束日期，格式 "YYYY-MM-DD"。

    Returns
    -------
    DataFrame
        包含 date, code, open, high, low, close, volume 列。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    ts_code = _to_ts_code(code)
    raw = api.index_daily(
        ts_code=ts_code,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
    )

    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["date", "code", "open", "high", "low", "close", "volume"]
        )

    df = raw.rename(columns={"trade_date": "date", "vol": "volume"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "code", "open", "high", "low", "close", "volume"]]


def fetch_index_constituents(
    index_code: str,
    date: str | None = None,
    cache_dir: Path | str | None = None,
) -> list[str]:
    """获取指数成分股代码列表 (tushare index_weight)。

    Parameters
    ----------
    index_code : str
        指数代码，如 "000905.SH"（中证500）。
    date : str | None
        快照日期，格式 "YYYY-MM-DD"。None 时不传日期过滤。
    cache_dir : Path | str | None
        缓存目录。None 时使用 data/raw/index/。

    Returns
    -------
    list[str]
        去重后的 6 位股票代码列表。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")

    if cache_dir is None:
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "index"
    else:
        cache_dir = Path(cache_dir)

    date_tag = date or "latest"
    cache_file = cache_dir / f"{index_code}_{date_tag}.parquet"

    if cache_file.exists():
        cached = pd.read_parquet(cache_file)
        return list(cached["code"])

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL

    raw = api.index_weight(index_code=index_code)

    if raw is None or raw.empty:
        return []

    # Filter to specific date if requested, otherwise use latest
    if date is not None:
        date_str = date.replace("-", "")
        filtered = raw[raw["trade_date"] == date_str]
        if not filtered.empty:
            raw = filtered
        # else: date not found, fall back to latest snapshot
        else:
            latest_date = raw["trade_date"].max()
            raw = raw[raw["trade_date"] == latest_date]
    else:
        latest_date = raw["trade_date"].max()
        raw = raw[raw["trade_date"] == latest_date]

    if raw.empty:
        return []

    codes = raw["con_code"].str.split(".").str[0].unique().tolist()

    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"code": sorted(codes)}).to_parquet(cache_file, index=False)

    return sorted(codes)


def fetch_daily_batch(
    codes: list[str],
    start: str,
    end: str,
    raw_dir: Path | str,
    sleep_sec: float = 0.5,
    progress: bool = True,
) -> pd.DataFrame:
    """批量获取日线行情，带缓存和限速。

    对每只股票先检查 parquet 缓存，未命中时调用 fetch_daily 并保存。
    未缓存的 API 调用间会 sleep 以尊重频率限制。

    Parameters
    ----------
    codes : list[str]
        股票代码列表。
    start, end : str
        日期范围，格式 "YYYY-MM-DD"。
    raw_dir : Path | str
        parquet 缓存目录。
    sleep_sec : float
        未缓存 API 调用间的 sleep 秒数。
    progress : bool
        是否每 50 只打印进度。

    Returns
    -------
    DataFrame
        所有股票拼接后的 OHLCV 数据。
    """
    from src.data.storage import save_parquet

    raw_dir = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    fetched = 0

    for i, code in enumerate(codes):
        cache_path = raw_dir / f"{code}.parquet"
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
        else:
            df = fetch_daily(code, start, end)
            save_parquet(df, cache_path)
            fetched += 1
            if fetched > 1 and sleep_sec > 0:
                time.sleep(sleep_sec)
        frames.append(df)

        if progress and (i + 1) % 50 == 0:
            logger.info(
                "Loaded %d / %d stocks (%d fetched from API)",
                i + 1,
                len(codes),
                fetched,
            )

    if not frames:
        return pd.DataFrame(
            columns=["date", "code", "open", "high", "low", "close", "volume"]
        )

    return pd.concat(frames, ignore_index=True)
