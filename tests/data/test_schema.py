import pandas as pd
import pytest

from data import OHLCV_SCHEMA, validate_ohlcv


def test_ohlcv_schema():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "code": ["000001.SZ", "000001.SZ"],
            "open": [10.0, 10.5],
            "high": [10.5, 11.0],
            "low": [9.8, 10.2],
            "close": [10.3, 10.8],
            "volume": [1000000, 1200000],
        }
    )
    assert validate_ohlcv(df) is True
    assert list(df.columns) == OHLCV_SCHEMA


def test_empty_data():
    df = pd.DataFrame(columns=OHLCV_SCHEMA)
    assert validate_ohlcv(df) is True
    assert len(df) == 0


def test_missing_columns():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"]),
            "code": ["000001.SZ"],
        }
    )
    with pytest.raises(ValueError, match="缺少必要列"):
        validate_ohlcv(df)
