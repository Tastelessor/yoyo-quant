from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data import OHLCV_SCHEMA
from src.data.fetcher import fetch_daily, fetch_daily_batch, fetch_index_constituents


@pytest.fixture
def fake_tushare_data():
    """模拟 tushare daily 返回的数据。"""
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": ["20240102", "20240103", "20240104", "20240105", "20240108"],
            "open": [10.0, 10.5, 10.3, 10.8, 11.0],
            "close": [10.3, 10.8, 10.6, 11.0, 11.2],
            "high": [10.5, 11.0, 10.9, 11.2, 11.5],
            "low": [9.8, 10.2, 10.1, 10.6, 10.8],
            "vol": [1_000_000, 1_200_000, 900_000, 1_500_000, 1_100_000],
        }
    )


@pytest.fixture
def mock_api(fake_tushare_data):
    """mock tushare pro_api。"""
    with patch("src.data.fetcher.ts") as mock_ts:
        mock_api = MagicMock()
        mock_api.daily.return_value = fake_tushare_data
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


def test_fetch_daily_returns_ohlcv(mock_api):
    """fetch_daily 应返回符合 OHLCV schema 的 DataFrame。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert list(df.columns) == OHLCV_SCHEMA
    assert len(df) == 5


def test_fetch_daily_column_mapping(mock_api):
    """tushare 列名应正确映射。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["code"].iloc[0] == "000001"
    assert df["open"].iloc[0] == 10.0
    assert df["close"].iloc[0] == 10.3
    assert df["high"].iloc[0] == 10.5
    assert df["low"].iloc[0] == 9.8
    assert df["volume"].iloc[0] == 1_000_000


def test_fetch_daily_date_dtype(mock_api):
    """date 列应为 datetime64 类型。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_fetch_daily_passes_params(mock_api):
    """应正确传递参数给 tushare。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        fetch_daily("600519", "2024-01-01", "2024-12-31")
    mock_api.daily.assert_called_once_with(
        ts_code="600519.SH",
        start_date="20240101",
        end_date="20241231",
    )


def test_fetch_daily_sorted_by_date(mock_api, fake_tushare_data):
    """结果应按日期排序。"""
    shuffled = fake_tushare_data.sample(frac=1, random_state=42)
    mock_api.daily.return_value = shuffled
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["date"].is_monotonic_increasing


def test_fetch_daily_empty_returns_schema(mock_api):
    """空数据应返回带正确列的空 DataFrame。"""
    mock_api.daily.return_value = pd.DataFrame()
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-01", "2024-01-01")
    assert list(df.columns) == OHLCV_SCHEMA
    assert len(df) == 0


def test_fetch_daily_no_token_raises():
    """未设置 TUSHARE_TOKEN 应抛出 ValueError。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TUSHARE_TOKEN 未设置"):
            fetch_daily("000001", "2024-01-01", "2024-01-01")


# --- fetch_index_constituents ---


@pytest.fixture
def mock_index_weight_data():
    """模拟 tushare index_weight 返回的数据。"""
    return pd.DataFrame(
        {
            "trade_date": ["20260523"] * 4,
            "con_code": ["000001.SZ", "600519.SH", "000858.SZ", "601318.SH"],
            "weight": [1.5, 2.0, 0.8, 1.2],
        }
    )


def test_fetch_index_constituents_returns_list(tmp_path):
    """应返回去后缀的 6 位代码列表。"""
    mock_api = MagicMock()
    mock_api.index_weight.return_value = pd.DataFrame(
        {
            "trade_date": ["20260523"] * 4,
            "con_code": ["000001.SZ", "600519.SH", "000858.SZ", "601318.SH"],
            "weight": [1.5, 2.0, 0.8, 1.2],
        }
    )
    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_index_constituents("000905.SH", "2026-05-23", cache_dir=tmp_path)
    assert sorted(result) == ["000001", "000858", "600519", "601318"]


def test_fetch_index_constituents_deduplicates(tmp_path):
    """重复成分股应去重。"""
    mock_api = MagicMock()
    mock_api.index_weight.return_value = pd.DataFrame(
        {
            "trade_date": ["20260523", "20260522"],
            "con_code": ["000001.SZ", "000001.SZ"],
            "weight": [1.5, 1.5],
        }
    )
    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_index_constituents("000905.SH", "2026-05-23", cache_dir=tmp_path)
    assert result == ["000001"]


def test_fetch_index_constituents_strips_suffix(tmp_path):
    """SH/SZ 后缀应被正确剥离。"""
    mock_api = MagicMock()
    mock_api.index_weight.return_value = pd.DataFrame(
        {
            "trade_date": ["20260523"] * 3,
            "con_code": ["000001.SZ", "600519.SH", "688981.SH"],
            "weight": [1.0, 1.0, 1.0],
        }
    )
    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_index_constituents("000905.SH", "2026-05-23", cache_dir=tmp_path)
    assert all(len(c) == 6 for c in result)
    assert "000001" in result
    assert "600519" in result
    assert "688981" in result


def test_fetch_index_constituents_empty_returns_empty(tmp_path):
    """空数据应返回空列表。"""
    mock_api = MagicMock()
    mock_api.index_weight.return_value = pd.DataFrame()
    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_index_constituents("000905.SH", "2026-05-23", cache_dir=tmp_path)
    assert result == []


def test_fetch_index_constituents_no_token_raises():
    """未设置 TUSHARE_TOKEN 应抛出 ValueError。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TUSHARE_TOKEN 未设置"):
            fetch_index_constituents("000905.SH", "2026-05-23", cache_dir="/tmp/test")


def test_fetch_index_constituents_uses_cache(tmp_path):
    """缓存存在时不应调用 API。"""
    cache_dir = tmp_path / "index"
    cache_dir.mkdir()
    cache_file = cache_dir / "000905.SH_2026-05-23.parquet"
    pd.DataFrame({"code": ["000001", "600519"]}).to_parquet(cache_file, index=False)

    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        result = fetch_index_constituents(
            "000905.SH", "2026-05-23", cache_dir=cache_dir
        )
    assert result == ["000001", "600519"]
    mock_ts.pro_api.assert_not_called()


def test_fetch_index_constituents_saves_cache(tmp_path):
    """API 调用后应保存缓存文件。"""
    mock_api = MagicMock()
    mock_api.index_weight.return_value = pd.DataFrame(
        {
            "trade_date": ["20260523"] * 4,
            "con_code": ["000001.SZ", "600519.SH", "000858.SZ", "601318.SH"],
            "weight": [1.5, 2.0, 0.8, 1.2],
        }
    )
    with (
        patch("src.data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        fetch_index_constituents("000905.SH", "2026-05-23", cache_dir=tmp_path)
    cache_file = tmp_path / "000905.SH_2026-05-23.parquet"
    assert cache_file.exists()
    cached = pd.read_parquet(cache_file)
    assert sorted(cached["code"].tolist()) == ["000001", "000858", "600519", "601318"]


# --- fetch_daily_batch ---


@pytest.fixture
def fake_daily_df():
    """单只股票的日线数据。"""
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["000001"] * 2,
            "open": [10.0, 10.5],
            "high": [10.5, 11.0],
            "low": [9.8, 10.2],
            "close": [10.3, 10.8],
            "volume": [1_000_000, 1_200_000],
        }
    )


def test_fetch_daily_batch_uses_cache(tmp_path, fake_daily_df):
    """缓存命中时不应调用 fetch_daily。"""
    for code in ["000001", "600519"]:
        df = fake_daily_df.copy()
        df["code"] = code
        df.to_parquet(tmp_path / f"{code}.parquet", index=False)

    with patch("src.data.fetcher.fetch_daily") as mock_fetch:
        result = fetch_daily_batch(
            ["000001", "600519"], "2024-01-01", "2024-01-31", raw_dir=tmp_path
        )
    mock_fetch.assert_not_called()
    assert len(result) == 4


def test_fetch_daily_batch_fetches_uncached(tmp_path, fake_daily_df):
    """未缓存的股票应调用 fetch_daily。"""
    fake_daily_df.to_parquet(tmp_path / "000001.parquet", index=False)

    other_df = fake_daily_df.copy()
    other_df["code"] = "600519"

    with patch("src.data.fetcher.fetch_daily", return_value=other_df) as mock_fetch:
        result = fetch_daily_batch(
            ["000001", "600519"],
            "2024-01-01",
            "2024-01-31",
            raw_dir=tmp_path,
            sleep_sec=0,
        )
    mock_fetch.assert_called_once_with("600519", "2024-01-01", "2024-01-31")
    assert len(result) == 4


def test_fetch_daily_batch_returns_concatenated(tmp_path, fake_daily_df):
    """应返回所有股票拼接后的 DataFrame。"""
    for code in ["000001", "600519", "000858"]:
        df = fake_daily_df.copy()
        df["code"] = code
        df.to_parquet(tmp_path / f"{code}.parquet", index=False)

    result = fetch_daily_batch(
        ["000001", "600519", "000858"], "2024-01-01", "2024-01-31", raw_dir=tmp_path
    )
    assert set(result["code"].unique()) == {"000001", "600519", "000858"}
    assert len(result) == 6


def test_fetch_daily_batch_sleeps_between_uncached(tmp_path, fake_daily_df):
    """未缓存的 API 调用间应有 sleep。"""
    with (
        patch("src.data.fetcher.fetch_daily", return_value=fake_daily_df),
        patch("src.data.fetcher.time.sleep") as mock_sleep,
    ):
        fetch_daily_batch(
            ["000001", "600519", "000858"],
            "2024-01-01",
            "2024-01-31",
            raw_dir=tmp_path,
            sleep_sec=0.5,
        )
    assert mock_sleep.call_count == 2  # 2 sleeps between 3 uncached calls
    mock_sleep.assert_called_with(0.5)
