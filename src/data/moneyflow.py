"""data/moneyflow.py — 个股资金流数据管线（tushare moneyflow）。

仿 data/earnings.py：fetch（按交易日拉全市场，单次 ≤6000 行）+ 清洗
（ts_code 拆分、trade_date 转 date）+ parquet 缓存 + 面板化。
金额单位保持万元（与 daily_basic 的 circ_mv 万元同单位，可直接相除）。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import tushare as ts
from dotenv import load_dotenv

from data.trade_calendar import fetch_trade_dates

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

#: moneyflow 接口金额/量字段（全部保留，因子层按需取列）
_MF_COLS = [
    "buy_sm_vol",
    "buy_sm_amount",
    "sell_sm_vol",
    "sell_sm_amount",
    "buy_md_vol",
    "buy_md_amount",
    "sell_md_vol",
    "sell_md_amount",
    "buy_lg_vol",
    "buy_lg_amount",
    "sell_lg_vol",
    "sell_lg_amount",
    "buy_elg_vol",
    "buy_elg_amount",
    "sell_elg_vol",
    "sell_elg_amount",
    "net_mf_vol",
    "net_mf_amount",
]

_PROXY_URL = "https://quantdata888.duckdns.org"


def _default_cache_dir() -> Path:
    """默认缓存目录 data/raw/moneyflow/。"""
    return Path(__file__).resolve().parents[2] / "data" / "raw" / "moneyflow"


def fetch_moneyflow_by_date(
    date: str,
    cache_dir: Path | str | None = None,
) -> pd.DataFrame:
    """拉取单日全市场个股资金流（tushare moneyflow）。

    Parameters
    ----------
    date : str
        交易日期 "YYYY-MM-DD"。
    cache_dir : Path | None
        缓存目录；None 用 ``data/raw/moneyflow/``。

    Returns
    -------
    DataFrame
        列：date, code + ``_MF_COLS``（金额万元）。缓存命中直接读 parquet。
    """
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise ValueError("TUSHARE_TOKEN 未设置，请在 .env 中配置")
    cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
    date_str = date.replace("-", "")
    cache_file = cache_dir / f"{date_str}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    api = ts.pro_api(token)
    api._DataApi__http_url = _PROXY_URL
    raw = api.moneyflow(trade_date=date_str)

    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "code"])

    df = raw.rename(columns={"ts_code": "code", "trade_date": "date"})
    df["code"] = df["code"].str.split(".").str[0]
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    out = df[["date", "code"] + _MF_COLS]

    cache_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache_file, index=False)
    return out


def build_moneyflow_panel(
    start: str,
    end: str,
    cache_dir: Path | str | None = None,
    sleep_sec: float = 0.3,
) -> pd.DataFrame:
    """批量拉取区间内每个交易日的资金流，合并为长表。

    Parameters
    ----------
    start / end : str
        日期范围 "YYYY-MM-DD"。
    cache_dir : Path | None
        缓存目录（透传 fetch_moneyflow_by_date）。
    sleep_sec : float
        未缓存调用之间的限频 sleep 秒数。

    Returns
    -------
    DataFrame
        date/code + ``_MF_COLS`` 长表（已按 date 升序排序）。
    """
    dates = fetch_trade_dates(start, end)
    frames = []
    for d in dates:
        frames.append(fetch_moneyflow_by_date(str(d.date()), cache_dir=cache_dir))
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    if not frames:
        return pd.DataFrame(columns=["date", "code"] + _MF_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values("date").reset_index(drop=True)
