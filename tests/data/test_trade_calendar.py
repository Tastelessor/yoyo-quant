"""Tests for the authoritative trading calendar (src/data/trade_calendar.py).

Coverage per project spec:
- normal path: schema / dtype / sorting / dedup
- boundary: empty range, no matching dates, missing token
- type assertions: cal_date datetime64, DatetimeIndex output
- PIT panel alignment: holidays/weekends must NOT appear in panel grid
  (the core P1-01 fix: trade_dates come from the calendar, not market data)
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data.trade_calendar import (
    TRADE_CAL_SCHEMA,
    fetch_trade_calendar,
    fetch_trade_dates,
    is_trading_day,
)


@pytest.fixture
def fake_calendar():
    """SSE calendar for 2025-01 (weekends + New Year + Spring Festival closed)."""
    rows = [
        ("20250101", 0, "20241231"),  # 元旦 闭市
        ("20250102", 1, "20241231"),  # 交易日
        ("20250103", 1, "20250102"),
        ("20250104", 0, "20250103"),  # 周六
        ("20250105", 0, "20250103"),  # 周日
        ("20250106", 1, "20250103"),
        ("20250107", 1, "20250106"),
        ("20250128", 0, "20250127"),  # 春节闭市（模拟）
        ("20250129", 0, "20250127"),
        ("20250130", 0, "20250127"),
        ("20250131", 0, "20250127"),
        ("20250205", 1, "20250127"),
    ]
    return pd.DataFrame(
        {
            "cal_date": [r[0] for r in rows],
            "exchange": ["SSE"] * len(rows),
            "is_open": [r[1] for r in rows],
            "pretrade_date": [r[2] for r in rows],
        }
    )


@pytest.fixture
def mock_api(fake_calendar):
    """mock tushare pro_api trade_cal，按年分片返回 fake_calendar。"""
    with patch("data.trade_calendar.ts") as mock_ts:
        mock_api = MagicMock()
        cal = fake_calendar.copy()
        cal["cal_date"] = pd.to_datetime(cal["cal_date"], format="%Y%m%d")

        def side_effect(exchange, start_date, end_date):
            start = pd.Timestamp(start_date)
            end = pd.Timestamp(end_date)
            sub = cal[(cal["cal_date"] >= start) & (cal["cal_date"] <= end)]
            return sub.reset_index(drop=True)

        mock_api.trade_cal.side_effect = side_effect
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


def _token_env():
    return patch.dict("os.environ", {"TUSHARE_TOKEN": "test_token"})


# ---------- fetch_trade_calendar ----------


def test_fetch_trade_calendar_schema_and_dtype(mock_api, tmp_path):
    """应返回符合 TRADE_CAL_SCHEMA 的 DataFrame，cal_date 为 datetime64。"""
    with _token_env():
        df = fetch_trade_calendar(cache_dir=tmp_path)
    assert list(df.columns) == TRADE_CAL_SCHEMA
    assert pd.api.types.is_datetime64_any_dtype(df["cal_date"])
    assert df["exchange"].iloc[0] == "SSE"
    assert sorted(df["is_open"].unique()) in ([0, 1], [False, True])


def test_fetch_trade_calendar_sorted_no_dup(mock_api, tmp_path):
    """输出应按 cal_date 升序且无重复。"""
    with _token_env():
        df = fetch_trade_calendar(cache_dir=tmp_path)
    assert df["cal_date"].is_monotonic_increasing
    assert df["cal_date"].is_unique


def test_fetch_trade_calendar_passes_params(mock_api, tmp_path):
    """应按年分片传递 exchange 与年份范围参数给 tushare。"""
    with _token_env():
        fetch_trade_calendar(exchange="SSE", cache_dir=tmp_path)
    calls = mock_api.trade_cal.call_args_list
    assert len(calls) == 41  # 1990..2030 每年一次
    assert calls[0].kwargs == {
        "exchange": "SSE",
        "start_date": "19900101",
        "end_date": "19901231",
    }
    assert calls[-1].kwargs == {
        "exchange": "SSE",
        "start_date": "20300101",
        "end_date": "20301231",
    }


def test_fetch_trade_calendar_caches_parquet(mock_api, tmp_path):
    """缓存命中时不应再次调用 API。"""
    with _token_env():
        fetch_trade_calendar(cache_dir=tmp_path)
    n_calls = mock_api.trade_cal.call_count
    assert n_calls == 41  # 首次全量按年分片
    assert (tmp_path / "SSE.parquet").exists()
    with _token_env():
        fetch_trade_calendar(cache_dir=tmp_path)
    assert mock_api.trade_cal.call_count == n_calls  # 命中缓存不再调 API


def test_fetch_trade_calendar_cache_schema_and_dtype(mock_api, tmp_path):
    """缓存读回后 cal_date 仍为 datetime64、is_open 仍为 int（dtype 契约）。"""
    with _token_env():
        fetch_trade_calendar(cache_dir=tmp_path)
    cached = pd.read_parquet(tmp_path / "SSE.parquet")
    assert list(cached.columns) == TRADE_CAL_SCHEMA
    assert pd.api.types.is_datetime64_any_dtype(cached["cal_date"])
    assert pd.api.types.is_integer_dtype(cached["is_open"])


def test_fetch_trade_calendar_corrupt_cache_raises(mock_api, tmp_path):
    """缓存缺列时应抛 ValueError 而非静默使用坏数据。"""
    (tmp_path / "SSE.parquet").parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cal_date": ["20250101"]}).to_parquet(
        tmp_path / "SSE.parquet", index=False
    )
    with _token_env():
        with pytest.raises(ValueError, match="缺少列"):
            fetch_trade_calendar(cache_dir=tmp_path)


def test_fetch_trade_calendar_missing_token(tmp_path):
    """缺少 TUSHARE_TOKEN 应抛 ValueError。"""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="TUSHARE_TOKEN"):
            fetch_trade_calendar(cache_dir=tmp_path)


def test_fetch_trade_calendar_empty_result(mock_api, tmp_path):
    """API 返回空时不应崩溃，返回空 DataFrame。"""
    mock_api.trade_cal.side_effect = None
    mock_api.trade_cal.return_value = pd.DataFrame(
        columns=["exchange", "cal_date", "is_open", "pretrade_date"]
    )
    with _token_env():
        df = fetch_trade_calendar(cache_dir=tmp_path)
    assert df.empty
    assert list(df.columns) == TRADE_CAL_SCHEMA
    assert not (tmp_path / "SSE.parquet").exists()  # 空结果不写缓存


# ---------- fetch_trade_dates ----------


def test_fetch_trade_dates_returns_only_open_days(mock_api, tmp_path):
    """应只返回 is_open=1 的日期，排除周末与节假日。"""
    with _token_env():
        dates = fetch_trade_dates("2025-01-01", "2025-02-05", cache_dir=tmp_path)
    expected = pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-02-05"]
    )
    assert dates.equals(expected)


def test_fetch_trade_dates_dtype_sorted(mock_api, tmp_path):
    """返回 DatetimeIndex，datetime64 dtype，升序无重复。"""
    with _token_env():
        dates = fetch_trade_dates("2025-01-01", "2025-02-05", cache_dir=tmp_path)
    assert isinstance(dates, pd.DatetimeIndex)
    assert dates.is_monotonic_increasing
    assert dates.is_unique


def test_fetch_trade_dates_range_filter(mock_api, tmp_path):
    """start/end 应闭区间截取。"""
    with _token_env():
        dates = fetch_trade_dates("2025-01-03", "2025-01-06", cache_dir=tmp_path)
    assert dates.equals(pd.DatetimeIndex(["2025-01-03", "2025-01-06"]))


def test_fetch_trade_dates_no_trading_day_in_range(mock_api, tmp_path):
    """区间内无交易日应返回空 DatetimeIndex。"""
    with _token_env():
        dates = fetch_trade_dates("2025-01-28", "2025-01-31", cache_dir=tmp_path)
    assert len(dates) == 0


def test_fetch_trade_dates_reversed_range(mock_api, tmp_path):
    """start > end 应返回空 DatetimeIndex 而非报错。"""
    with _token_env():
        dates = fetch_trade_dates("2025-02-05", "2025-01-01", cache_dir=tmp_path)
    assert len(dates) == 0


def test_fetch_trade_dates_no_args_returns_all(mock_api, tmp_path):
    """不传 start/end 应返回全部交易日。"""
    with _token_env():
        dates = fetch_trade_dates(cache_dir=tmp_path)
    assert len(dates) == 5  # 12 个日历日中 5 个交易日


def test_fetch_trade_dates_accepts_tz_aware_bounds(mock_api, tmp_path):
    """tz-aware 的 start/end 应归一化后参与比较，不抛 ValueError。"""
    tz = pd.Timestamp("2025-01-03", tz="Asia/Shanghai")
    with _token_env():
        dates = fetch_trade_dates(tz, tz, cache_dir=tmp_path)
    assert dates.equals(pd.DatetimeIndex(["2025-01-03"]))


# ---------- is_trading_day ----------


def test_is_trading_day(mock_api, tmp_path):
    """交易日 True；周末/节假日/非日历日 False。"""
    with _token_env():
        assert is_trading_day("2025-01-02", cache_dir=tmp_path) is True
        assert is_trading_day(pd.Timestamp("2025-01-03"), cache_dir=tmp_path) is True
        assert is_trading_day("2025-01-04", cache_dir=tmp_path) is False  # 周六
        assert is_trading_day("2025-01-05", cache_dir=tmp_path) is False  # 周日
        assert is_trading_day("2025-01-01", cache_dir=tmp_path) is False  # 元旦
        assert is_trading_day("2025-01-29", cache_dir=tmp_path) is False  # 春节
        assert is_trading_day("2025-03-15", cache_dir=tmp_path) is False  # 不在日历


def test_is_trading_day_tz_aware(mock_api, tmp_path):
    """tz-aware 输入应归一化到 naive 日期后判断，不抛 ValueError。"""
    with _token_env():
        assert (
            is_trading_day(
                pd.Timestamp("2025-01-02", tz="Asia/Shanghai"), cache_dir=tmp_path
            )
            is True
        )


def test_is_trading_day_empty_calendar(mock_api, tmp_path):
    """日历为空时任意日期返回 False。"""
    mock_api.trade_cal.side_effect = None
    mock_api.trade_cal.return_value = pd.DataFrame(
        columns=["exchange", "cal_date", "is_open", "pretrade_date"]
    )
    with _token_env():
        assert is_trading_day("2025-01-02", cache_dir=tmp_path) is False


# ---------- PIT panel alignment (P1-01 core fix) ----------


def test_trade_dates_drive_pit_panel_grid(mock_api, tmp_path):
    """用日历生成 trade_dates 时，节假日/周末不得出现在 PIT 面板网格。"""
    from data.earnings import build_earnings_panel

    with _token_env():
        trade_dates = fetch_trade_dates("2025-01-01", "2025-02-05", cache_dir=tmp_path)

    earnings = pd.DataFrame(
        {
            "code": ["000001"],
            "ann_date": ["2025-01-03"],
            "end_date": ["20241231"],
            "event_type": ["forecast"],
            "predicted_profit": [1.0],
            "actual_profit": [None],
            "forecast_type": ["预增"],
        }
    )
    panel = build_earnings_panel(earnings, trade_dates, ["000001"])

    grid_dates = panel["date"].dt.normalize().unique()
    assert set(grid_dates) == set(trade_dates)
    assert pd.Timestamp("2025-01-01") not in grid_dates  # 元旦
    assert pd.Timestamp("2025-01-04") not in grid_dates  # 周六
    assert pd.Timestamp("2025-01-29") not in grid_dates  # 春节
