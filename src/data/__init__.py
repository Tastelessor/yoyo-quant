import pandas as pd

from src.data.earnings import build_earnings_panel, fetch_earnings_history
from src.data.filters import detect_limit_price, detect_suspension
from src.data.storage import load_parquet, save_parquet
from src.data.trade_calendar import (
    TRADE_CAL_SCHEMA,
    fetch_trade_calendar,
    fetch_trade_dates,
    is_trading_day,
)
from src.data.universe import apply_data_filters, resolve_universe

OHLCV_SCHEMA = ["date", "code", "open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame) -> bool:
    missing = [col for col in OHLCV_SCHEMA if col not in df.columns]
    if missing:
        raise ValueError(f"缺少必要列: {missing}")
    return True


__all__ = [
    "OHLCV_SCHEMA",
    "TRADE_CAL_SCHEMA",
    "apply_data_filters",
    "build_earnings_panel",
    "fetch_earnings_history",
    "detect_limit_price",
    "detect_suspension",
    "fetch_trade_calendar",
    "fetch_trade_dates",
    "is_trading_day",
    "load_parquet",
    "resolve_universe",
    "save_parquet",
    "validate_ohlcv",
]
