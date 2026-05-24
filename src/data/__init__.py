import pandas as pd

from src.data.filters import detect_limit_price, detect_suspension
from src.data.storage import load_parquet, save_parquet
from src.data.universe import apply_data_filters, resolve_universe

OHLCV_SCHEMA = ["date", "code", "open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame) -> bool:
    missing = [col for col in OHLCV_SCHEMA if col not in df.columns]
    if missing:
        raise ValueError(f"缺少必要列: {missing}")
    return True


__all__ = [
    "OHLCV_SCHEMA",
    "apply_data_filters",
    "detect_limit_price",
    "detect_suspension",
    "load_parquet",
    "resolve_universe",
    "save_parquet",
    "validate_ohlcv",
]
