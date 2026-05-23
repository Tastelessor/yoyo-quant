import os
from pathlib import Path
from typing import Any

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

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
    raw = api.daily(
        ts_code=ts_code,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
    )

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])

    df = raw.rename(columns={"trade_date": "date", "vol": "volume"})
    df["code"] = code
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "code", "open", "high", "low", "close", "volume"]]
