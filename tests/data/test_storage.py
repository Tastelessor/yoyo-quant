import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.storage import load_parquet, save_parquet


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "code": ["000001.SZ", "000001.SZ", "000001.SZ"],
            "open": [10.0, 10.5, 10.3],
            "high": [10.5, 11.0, 10.9],
            "low": [9.8, 10.2, 10.1],
            "close": [10.3, 10.8, 10.6],
            "volume": [1_000_000, 1_200_000, 900_000],
        }
    )


def test_save_load_roundtrip(sample_df):
    """保存再加载应完全一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.parquet"
        save_parquet(sample_df, path)
        loaded = load_parquet(path)
        pd.testing.assert_frame_equal(loaded, sample_df)


def test_save_creates_parent_dirs(sample_df):
    """保存时应自动创建父目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "dir" / "test.parquet"
        save_parquet(sample_df, path)
        assert path.exists()
        loaded = load_parquet(path)
        assert len(loaded) == 3


def test_save_preserves_dtypes(sample_df):
    """保存再加载应保留列类型。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.parquet"
        save_parquet(sample_df, path)
        loaded = load_parquet(path)
        assert pd.api.types.is_datetime64_any_dtype(loaded["date"])
        assert pd.api.types.is_string_dtype(loaded["code"])
        assert pd.api.types.is_float_dtype(loaded["open"])
        assert pd.api.types.is_integer_dtype(loaded["volume"])


def test_load_nonexistent_raises():
    """加载不存在的文件应抛出 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        load_parquet(Path("/nonexistent/path/data.parquet"))


def test_save_empty_df():
    """保存空 DataFrame 应正常工作。"""
    empty = pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "empty.parquet"
        save_parquet(empty, path)
        loaded = load_parquet(path)
        assert len(loaded) == 0
        assert list(loaded.columns) == list(empty.columns)
