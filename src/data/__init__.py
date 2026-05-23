import pandas as pd

from src.data.filters import detect_limit_price, detect_suspension
from src.data.storage import load_parquet, save_parquet

OHLCV_SCHEMA = ["date", "code", "open", "high", "low", "close", "volume"]


def validate_ohlcv(df: pd.DataFrame) -> bool:
    missing = [col for col in OHLCV_SCHEMA if col not in df.columns]
    if missing:
        raise ValueError(f"缺少必要列: {missing}")
    return True


__all__ = [
    "OHLCV_SCHEMA",
    "detect_limit_price",
    "detect_suspension",
    "load_parquet",
    "save_parquet",
    "validate_ohlcv",
]
