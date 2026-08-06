from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data import OHLCV_SCHEMA
from data.fetcher import (
    fetch_all_stocks,
    fetch_daily,
    fetch_daily_batch,
    fetch_fundamentals,
    fetch_index_constituents,
    fetch_index_daily,
)


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
            "pre_close": [10.0, 10.3, 10.8, 10.6, 11.0],
            "vol": [1_000_000, 1_200_000, 900_000, 1_500_000, 1_100_000],
        }
    )


@pytest.fixture
def mock_api(fake_tushare_data):
    """mock tushare pro_api。"""
    with patch("data.fetcher.ts") as mock_ts:
        mock_api = MagicMock()
        mock_api.daily.return_value = fake_tushare_data
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


def test_fetch_daily_returns_ohlcv(mock_api):
    """fetch_daily 应返回 OHLCV schema 的超集，并包含 pre_close。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert set(OHLCV_SCHEMA).issubset(df.columns)
    assert "pre_close" in df.columns
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


def test_fetch_daily_maps_pre_close(mock_api):
    """tushare pre_close 列应正确映射。"""
    with patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert df["pre_close"].iloc[0] == 10.0
    assert df["pre_close"].iloc[1] == 10.3


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
    assert set(OHLCV_SCHEMA).issubset(df.columns)
    assert "pre_close" in df.columns
    assert len(df) == 0


def test_fetch_daily_no_token_raises():
    """未设置 TUSHARE_TOKEN 应抛出 ValueError。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TUSHARE_TOKEN 未设置"):
            fetch_daily("000001", "2024-01-01", "2024-01-01")


# --- fetch_index_daily ---


def test_fetch_index_daily_includes_pre_close():
    """fetch_index_daily 应返回含 pre_close 的 OHLCV 超集。"""
    mock_api = MagicMock()
    mock_api.index_daily.return_value = pd.DataFrame(
        {
            "ts_code": ["000300.SH"] * 2,
            "trade_date": ["20260105", "20260106"],
            "open": [4000.0, 4050.0],
            "high": [4020.0, 4070.0],
            "low": [3980.0, 4040.0],
            "close": [4010.0, 4060.0],
            "pre_close": [3990.0, 4010.0],
            "vol": [1_000_000, 1_200_000],
        }
    )
    with (
        patch("data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        df = fetch_index_daily("000300", "2026-01-05", "2026-01-06")
    assert set(OHLCV_SCHEMA).issubset(df.columns)
    assert df["pre_close"].iloc[0] == 3990.0
    assert df["pre_close"].iloc[1] == 4010.0


def test_fetch_daily_retries_on_temporary_unavailable(mock_api, fake_tushare_data):
    """proxy 瞬时 'service temporarily unavailable' 应重试后成功。"""
    responses = [
        Exception("service temporarily unavailable"),
        Exception("service temporarily unavailable"),
        fake_tushare_data,
    ]
    mock_api.daily.side_effect = responses
    with (
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
        patch("data.fetcher.time.sleep") as mock_sleep,
    ):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert len(df) == 5
    assert mock_api.daily.call_count == 3
    assert mock_sleep.call_count == 2


def test_fetch_daily_retries_on_rate_limit_message(mock_api, fake_tushare_data):
    """tushare 官方限频错误文本「每分钟最多访问该接口X次」应触发重试。"""
    responses = [
        Exception("抱歉，您每分钟最多访问该接口500次"),
        fake_tushare_data,
    ]
    mock_api.daily.side_effect = responses
    with (
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
        patch("data.fetcher.time.sleep") as mock_sleep,
    ):
        df = fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert len(df) == 5
    assert mock_api.daily.call_count == 2
    assert mock_sleep.call_count == 1


def test_fetch_daily_does_not_retry_on_token_error(mock_api):
    """token 错误等确定性错误不应重试，直接抛出。"""
    mock_api.daily.side_effect = Exception("token不对")
    with (
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
        patch("data.fetcher.time.sleep") as mock_sleep,
    ):
        with pytest.raises(Exception, match="token不对"):
            fetch_daily("000001", "2024-01-02", "2024-01-08")
    assert mock_api.daily.call_count == 1
    mock_sleep.assert_not_called()


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
        patch("data.fetcher.ts") as mock_ts,
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
        patch("data.fetcher.ts") as mock_ts,
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
        patch("data.fetcher.ts") as mock_ts,
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
        patch("data.fetcher.ts") as mock_ts,
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
        patch("data.fetcher.ts") as mock_ts,
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
        patch("data.fetcher.ts") as mock_ts,
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

    with patch("data.fetcher.fetch_daily") as mock_fetch:
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

    with patch("data.fetcher.fetch_daily", return_value=other_df) as mock_fetch:
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
    """未缓存的 API 调用间应有 sleep（默认串行）。"""
    with (
        patch("data.fetcher.fetch_daily", return_value=fake_daily_df),
        patch("data.fetcher.time.sleep") as mock_sleep,
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


def test_fetch_daily_batch_concurrent_workers_sleep_per_worker(tmp_path, fake_daily_df):
    """workers>1 时并发拉取：每 worker 每次 API 调用后 sleep，结果正常拼接。"""

    def make_df(code):
        df = fake_daily_df.copy()
        df["code"] = code
        return df

    with (
        patch(
            "data.fetcher.fetch_daily",
            side_effect=lambda code, *a, **k: make_df(code),
        ),
        patch("data.fetcher.time.sleep") as mock_sleep,
    ):
        result = fetch_daily_batch(
            ["000001", "600519", "000858"],
            "2024-01-01",
            "2024-01-31",
            raw_dir=tmp_path,
            sleep_sec=0.5,
            workers=3,
        )
    assert len(result) == 6
    assert set(result["code"].unique()) == {"000001", "600519", "000858"}
    # 并发：3 个 worker 各 sleep 1 次（串行下是 2 次）
    assert mock_sleep.call_count == 3


def test_fetch_daily_batch_worker_failure_propagates(tmp_path, fake_daily_df):
    """并发下某只股票拉取失败应抛出异常，不静默吞掉。"""
    fake_daily_df.to_parquet(tmp_path / "000001.parquet", index=False)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch("data.fetcher.fetch_daily", side_effect=boom) as mock_fetch:
        with pytest.raises(RuntimeError, match="boom"):
            fetch_daily_batch(
                ["000001", "600519"],
                "2024-01-01",
                "2024-01-31",
                raw_dir=tmp_path,
                workers=2,
            )
    # 有缓存的不调 API；未缓存的 600519 被尝试拉取
    mock_fetch.assert_called_once_with("600519", "2024-01-01", "2024-01-31")


# --- fetch_all_stocks ---


def test_fetch_all_stocks_returns_dataframe(tmp_path):
    """应返回排除 ST 和北交所（含 920 新代码段）的股票列表。"""
    mock_api = MagicMock()
    mock_api.stock_basic.return_value = pd.DataFrame(
        {
            "ts_code": [
                "000001.SZ",
                "600519.SH",
                "000004.SZ",
                "830001.BJ",
                "920000.BJ",
            ],
            "name": ["平安银行", "贵州茅台", "*ST国华", "某北交所", "北交所920"],
            "industry": ["银行", "白酒", "软件", "制造", "制造"],
            "market": ["主板", "主板", "主板", "北交所", "北交所"],
            "list_date": ["19910403", "20010827", "19901201", "20210101", "20240101"],
        }
    )
    with (
        patch("data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_all_stocks(date="2026-05-22", cache_dir=tmp_path)
    assert "000001" in result["code"].values
    assert "600519" in result["code"].values
    # ST should be excluded
    assert "*ST国华" not in result["name"].values
    # 北交所 (830/920) should be excluded
    assert "830001" not in result["code"].values
    assert "920000" not in result["code"].values


def test_fetch_all_stocks_excludes_bse_43x(tmp_path):
    """北交所 43 开头代码（原新三板平移，如 430047）应被排除。"""
    mock_api = MagicMock()
    mock_api.stock_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "430047.BJ", "600519.SH"],
            "name": ["平安银行", "诺思兰德", "贵州茅台"],
            "industry": ["银行", "医药", "白酒"],
            "market": ["主板", "北交所", "主板"],
            "list_date": ["19910403", "20141103", "20010827"],
        }
    )
    with (
        patch("data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_all_stocks(date="2026-05-22", cache_dir=tmp_path)
    assert "000001" in result["code"].values
    assert "600519" in result["code"].values
    assert "430047" not in result["code"].values


def test_fetch_all_stocks_uses_cache(tmp_path):
    """缓存存在时不应调用 API。"""
    cache_file = tmp_path / "all_stocks_2026-05-22.parquet"
    pd.DataFrame({"code": ["000001"], "name": ["平安银行"]}).to_parquet(
        cache_file, index=False
    )
    with patch("data.fetcher.ts") as mock_ts:
        result = fetch_all_stocks(date="2026-05-22", cache_dir=tmp_path)
    assert list(result["code"]) == ["000001"]
    mock_ts.pro_api.assert_not_called()


# --- fetch_fundamentals ---


def test_fetch_fundamentals_returns_dataframe(tmp_path):
    """应返回包含 code, pe, pb, total_mv, circ_mv, turnover_rate 的 DataFrame。"""
    mock_api = MagicMock()
    mock_api.daily_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600519.SH"],
            "trade_date": ["20260522", "20260522"],
            "pe": [5.5, 30.2],
            "pb": [0.6, 10.1],
            "total_mv": [2000000.0, 5000000.0],  # 万元
            "circ_mv": [1500000.0, 4000000.0],   # 万元
            "turnover_rate": [1.2, 0.5],
        }
    )
    with (
        patch("data.fetcher.ts") as mock_ts,
        patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"}),
    ):
        mock_ts.pro_api.return_value = mock_api
        result = fetch_fundamentals("2026-05-22", cache_dir=tmp_path)
    assert list(result.columns) == [
        "code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"
    ]
    assert result["code"].iloc[0] == "000001"
    # total_mv should be converted from 万元 to 亿元
    assert result["total_mv"].iloc[0] == 200.0
    assert result["circ_mv"].iloc[0] == 150.0
    assert result["turnover_rate"].iloc[0] == 1.2


def test_fetch_fundamentals_uses_cache(tmp_path):
    """缓存存在时不应调用 API。"""
    cache_dir = tmp_path / "fundamentals"
    cache_dir.mkdir()
    cache_file = cache_dir / "20260522.parquet"
    pd.DataFrame({"code": ["000001"], "pe": [5.5]}).to_parquet(cache_file, index=False)
    with patch("data.fetcher.ts") as mock_ts:
        result = fetch_fundamentals("2026-05-22", cache_dir=cache_dir)
    assert list(result["code"]) == ["000001"]
    mock_ts.pro_api.assert_not_called()
