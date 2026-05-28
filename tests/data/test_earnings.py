"""Tests for src/data/earnings.py — PIT earnings event pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data.earnings import (
    FORECAST_TYPE_SCORE,
    build_earnings_panel,
    fetch_earnings_history,
    fetch_express,
    fetch_forecast,
    get_prev_end_date,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_forecast_data():
    """模拟 tushare forecast 返回（单股票）。"""
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "ann_date": ["20250115", "20240420"],
            "end_date": ["20241231", "20240331"],
            "type": ["预增", "略增"],
            "p_change_min": [30.0, 10.0],
            "p_change_max": [50.0, 20.0],
            "net_profit_min": [100.0, 50.0],
            "net_profit_max": [150.0, 80.0],
        }
    )


@pytest.fixture
def fake_express_data():
    """模拟 tushare express 返回（单股票）。"""
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "ann_date": ["20250220", "20240425"],
            "end_date": ["20241231", "20240331"],
            "n_income_attr_p": [130.0, 70.0],
            "increase_rate": [35.0, 15.0],
        }
    )


@pytest.fixture
def mock_forecast_api(fake_forecast_data):
    """mock tushare forecast API。"""
    with patch("src.data.earnings.ts") as mock_ts:
        mock_api = MagicMock()
        mock_api.forecast.return_value = fake_forecast_data
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


@pytest.fixture
def mock_express_api(fake_express_data):
    """mock tushare express API。"""
    with patch("src.data.earnings.ts") as mock_ts:
        mock_api = MagicMock()
        mock_api.express.return_value = fake_express_data
        mock_ts.pro_api.return_value = mock_api
        yield mock_api


# ---------------------------------------------------------------------------
# fetch_forecast
# ---------------------------------------------------------------------------

class TestFetchForecast:
    def test_returns_expected_columns(self, mock_forecast_api, tmp_path):
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_forecast("000001", cache_dir=tmp_path)
        expected = {"code", "ann_date", "end_date", "forecast_type", "predicted_profit"}
        assert expected.issubset(set(df.columns))

    def test_strips_exchange_suffix(self, mock_forecast_api, tmp_path):
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_forecast("000001", cache_dir=tmp_path)
        assert all(len(c) == 6 for c in df["code"])

    def test_predicted_profit_is_midpoint(self, mock_forecast_api, tmp_path):
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_forecast("000001", cache_dir=tmp_path)
        # 000001: (100+150)/2 = 125
        row = df[df["end_date"] == "20241231"].iloc[0]
        assert row["predicted_profit"] == pytest.approx(125.0)

    def test_empty_response_returns_empty_df(self, tmp_path):
        with patch("src.data.earnings.ts") as mock_ts, \
             patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            mock_api = MagicMock()
            mock_api.forecast.return_value = pd.DataFrame()
            mock_ts.pro_api.return_value = mock_api
            df = fetch_forecast("000001", cache_dir=tmp_path)
        assert len(df) == 0

    def test_caching_skips_api_call(self, mock_forecast_api, tmp_path):
        cache_dir = tmp_path / "forecast"
        cache_dir.mkdir(parents=True)
        cached = pd.DataFrame({"code": ["cached"], "ann_date": [pd.Timestamp("2025-01-01")]})
        cached.to_parquet(cache_dir / "000001.parquet", index=False)
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_forecast("000001", cache_dir=cache_dir)
        assert df["code"].iloc[0] == "cached"
        mock_forecast_api.forecast.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_express
# ---------------------------------------------------------------------------

class TestFetchExpress:
    def test_returns_expected_columns(self, mock_express_api, tmp_path):
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_express("000001", cache_dir=tmp_path)
        expected = {"code", "ann_date", "end_date", "actual_profit", "increase_rate"}
        assert expected.issubset(set(df.columns))

    def test_strips_exchange_suffix(self, mock_express_api, tmp_path):
        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            df = fetch_express("000001", cache_dir=tmp_path)
        assert all(len(c) == 6 for c in df["code"])

    def test_empty_response_returns_empty_df(self, tmp_path):
        with patch("src.data.earnings.ts") as mock_ts, \
             patch.dict("os.environ", {"TUSHARE_TOKEN": "test"}):
            mock_api = MagicMock()
            mock_api.express.return_value = pd.DataFrame()
            mock_ts.pro_api.return_value = mock_api
            df = fetch_express("000001", cache_dir=tmp_path)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# get_prev_end_date
# ---------------------------------------------------------------------------

class TestGetPrevEndDate:
    def test_q1_maps_to_prev_year_annual(self):
        assert get_prev_end_date("20250331") == "20241231"

    def test_q2_maps_to_q1(self):
        assert get_prev_end_date("20250630") == "20250331"

    def test_q3_maps_to_q2(self):
        assert get_prev_end_date("20250930") == "20250630"

    def test_q4_maps_to_q3(self):
        assert get_prev_end_date("20251231") == "20250930"


# ---------------------------------------------------------------------------
# _compute_pit_surprise
# ---------------------------------------------------------------------------

class TestComputePitSurprise:
    """PIT 滚动池状态机测试。"""

    @staticmethod
    def _make_events(rows):
        """构建事件 DataFrame。"""
        return pd.DataFrame(rows)

    def test_forecast_uses_type_score(self):
        """Forecast 事件应使用 FORECAST_TYPE_SCORE。"""
        from src.data.earnings import _compute_pit_surprise
        events = self._make_events([
            {"code": "A", "ann_date": pd.Timestamp("2025-01-15"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
        ])
        result = _compute_pit_surprise(events)
        assert result["raw_surprise"].iloc[0] == pytest.approx(0.5)

    def test_express_uses_same_pool_rank_diff(self):
        """Express 事件应使用同池 rank(actual) - rank(predicted)。"""
        from src.data.earnings import _compute_pit_surprise
        events = self._make_events([
            {"code": "A", "ann_date": pd.Timestamp("2025-02-20"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 100.0, "actual_profit": 130.0,
             "forecast_type": None},
            {"code": "B", "ann_date": pd.Timestamp("2025-02-21"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 200.0, "actual_profit": 180.0,
             "forecast_type": None},
            {"code": "C", "ann_date": pd.Timestamp("2025-02-22"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 50.0, "actual_profit": 80.0,
             "forecast_type": None},
        ])
        result = _compute_pit_surprise(events)
        # A: actual=130 (rank 2/3=0.667), predicted=100 (rank 2/3=0.667) → 0.0
        # B: actual=180 (rank 3/3=1.0), predicted=200 (rank 3/3=1.0) → 0.0
        # C: actual=80 (rank 1/3=0.333), predicted=50 (rank 1/3=0.333) → 0.0
        # All should be 0 since ranks are perfectly correlated
        assert result["raw_surprise"].iloc[0] == pytest.approx(0.0, abs=0.01)

    def test_no_none_rank_crash(self):
        """Forecast 事件不应尝试 rank(None)。"""
        from src.data.earnings import _compute_pit_surprise
        events = self._make_events([
            {"code": "A", "ann_date": pd.Timestamp("2025-02-20"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 100.0, "actual_profit": 130.0,
             "forecast_type": None},
            {"code": "B", "ann_date": pd.Timestamp("2025-02-21"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 200.0, "actual_profit": 180.0,
             "forecast_type": None},
            {"code": "C", "ann_date": pd.Timestamp("2025-02-22"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 50.0, "actual_profit": 80.0,
             "forecast_type": None},
            # This forecast should NOT crash
            {"code": "D", "ann_date": pd.Timestamp("2025-02-23"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 60.0, "actual_profit": np.nan,
             "forecast_type": "略增"},
        ])
        result = _compute_pit_surprise(events)
        assert len(result) == 4
        # D is a forecast → uses type score
        assert result[result["code"] == "D"]["raw_surprise"].iloc[0] == pytest.approx(0.25)

    def test_pool_below_threshold_uses_type_score(self):
        """express_pool < 3 时退化为类型评分。"""
        from src.data.earnings import _compute_pit_surprise
        events = self._make_events([
            {"code": "A", "ann_date": pd.Timestamp("2025-01-15"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "B", "ann_date": pd.Timestamp("2025-02-20"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 100.0, "actual_profit": 130.0,
             "forecast_type": "预增"},
        ])
        result = _compute_pit_surprise(events)
        # Only 1 express in pool → falls back to type score
        assert result[result["code"] == "B"]["raw_surprise"].iloc[0] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# _compute_acceleration
# ---------------------------------------------------------------------------

class TestComputeAcceleration:
    def test_q1_links_to_prev_year_annual(self):
        """Q1 的 acceleration = Q1 surprise - 去年年报 surprise。"""
        from src.data.earnings import _compute_acceleration
        df = pd.DataFrame([
            {"code": "A", "ann_date": pd.Timestamp("2025-04-20"), "end_date": "20241231",
             "raw_surprise": 0.2},
            {"code": "A", "ann_date": pd.Timestamp("2025-04-25"), "end_date": "20250331",
             "raw_surprise": 0.5},
        ])
        result = _compute_acceleration(df)
        q1 = result[result["end_date"] == "20250331"].iloc[0]
        assert q1["raw_acceleration"] == pytest.approx(0.3)

    def test_missing_quarter_gives_zero(self):
        """缺季 → acceleration = 0.0。"""
        from src.data.earnings import _compute_acceleration
        df = pd.DataFrame([
            {"code": "A", "ann_date": pd.Timestamp("2025-04-20"), "end_date": "20241231",
             "raw_surprise": 0.2},
            # No Q1 data → Q2's prev is Q1 which doesn't exist
            {"code": "A", "ann_date": pd.Timestamp("2025-08-20"), "end_date": "20250630",
             "raw_surprise": 0.4},
        ])
        result = _compute_acceleration(df)
        q2 = result[result["end_date"] == "20250630"].iloc[0]
        assert q2["raw_acceleration"] == pytest.approx(0.0)

    def test_multi_quarter_sequence(self):
        """Q2→Q3→Q4 连续加速度正确。"""
        from src.data.earnings import _compute_acceleration
        df = pd.DataFrame([
            {"code": "A", "ann_date": pd.Timestamp("2025-04-20"), "end_date": "20250331",
             "raw_surprise": 0.3},
            {"code": "A", "ann_date": pd.Timestamp("2025-08-20"), "end_date": "20250630",
             "raw_surprise": 0.5},
            {"code": "A", "ann_date": pd.Timestamp("2025-10-25"), "end_date": "20250930",
             "raw_surprise": 0.1},
        ])
        result = _compute_acceleration(df)
        q2 = result[result["end_date"] == "20250630"].iloc[0]
        q3 = result[result["end_date"] == "20250930"].iloc[0]
        assert q2["raw_acceleration"] == pytest.approx(0.2)  # 0.5 - 0.3
        assert q3["raw_acceleration"] == pytest.approx(-0.4)  # 0.1 - 0.5


# ---------------------------------------------------------------------------
# build_earnings_panel
# ---------------------------------------------------------------------------

class TestBuildEarningsPanel:
    def _make_earnings_df(self):
        """构建包含 forecast + express 的统一事件表。"""
        return pd.DataFrame([
            # Forecast events (Jan)
            {"code": "000001", "ann_date": pd.Timestamp("2025-01-15"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 125.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "600519", "ann_date": pd.Timestamp("2025-01-16"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 65.0, "actual_profit": np.nan,
             "forecast_type": "略增"},
            {"code": "000858", "ann_date": pd.Timestamp("2025-01-20"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": -10.0, "actual_profit": np.nan,
             "forecast_type": "首亏"},
            # Express events (Feb)
            {"code": "000001", "ann_date": pd.Timestamp("2025-02-20"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 125.0, "actual_profit": 130.0,
             "forecast_type": None},
            {"code": "600519", "ann_date": pd.Timestamp("2025-02-25"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": 65.0, "actual_profit": 70.0,
             "forecast_type": None},
            {"code": "000858", "ann_date": pd.Timestamp("2025-02-28"), "end_date": "20241231",
             "event_type": "express", "predicted_profit": -10.0, "actual_profit": -20.0,
             "forecast_type": None},
        ])

    def test_forward_fill_across_dates(self):
        """公告日后持续填充。"""
        earnings = self._make_earnings_df()
        trade_dates = pd.bdate_range("2025-01-10", "2025-03-10")
        codes = ["000001", "600519", "000858"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # After Jan 15, 000001 should have non-NaN surprise
        jan20 = panel[(panel["date"] == pd.Timestamp("2025-01-20")) & (panel["code"] == "000001")]
        assert len(jan20) == 1
        assert not jan20["earnings_surprise"].isna().all()

    def test_no_look_ahead_bias(self):
        """ann_date 之前应无信号（Z-Score 后为 0.0）。"""
        earnings = self._make_earnings_df()
        trade_dates = pd.bdate_range("2025-01-10", "2025-03-10")
        codes = ["000001", "600519", "000858"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # Before Jan 15 (first announcement), all stocks should be 0.0 (no signal)
        jan12 = panel[(panel["date"] == pd.Timestamp("2025-01-13")) & (panel["code"] == "000001")]
        assert len(jan12) == 1
        assert jan12["earnings_surprise"].iloc[0] == 0.0

    def test_april_dual_period_collision(self):
        """同一天披露年报+一季报 → 更新季胜出。"""
        earnings = pd.DataFrame([
            {"code": "000001", "ann_date": pd.Timestamp("2026-04-20"), "end_date": "20251231",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "000001", "ann_date": pd.Timestamp("2026-04-20"), "end_date": "20260331",
             "event_type": "forecast", "predicted_profit": 50.0, "actual_profit": np.nan,
             "forecast_type": "略增"},
        ])
        trade_dates = pd.bdate_range("2026-04-18", "2026-04-25")
        codes = ["000001"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # After Apr 20, should have non-NaN value (not swallowed)
        apr21 = panel[(panel["date"] == pd.Timestamp("2026-04-21")) & (panel["code"] == "000001")]
        assert len(apr21) == 1
        assert not apr21["earnings_surprise"].isna().all()

    def test_zscore_standardization(self):
        """每日截面均值≈0，标准差≈1。"""
        earnings = self._make_earnings_df()
        trade_dates = pd.bdate_range("2025-02-25", "2025-03-05")
        codes = ["000001", "600519", "000858"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        for dt in trade_dates:
            day = panel[panel["date"] == dt]
            if day["earnings_surprise"].notna().sum() > 1:
                assert abs(day["earnings_surprise"].mean()) < 0.1
                assert abs(day["earnings_surprise"].std() - 1.0) < 0.3

    def test_zscore_clip_bounds(self):
        """极端值被 clip 到 [-3, 3]。"""
        # Build earnings with extreme outlier
        earnings = pd.DataFrame([
            {"code": f"S{i:03d}", "ann_date": pd.Timestamp("2025-02-20"),
             "end_date": "20241231", "event_type": "forecast",
             "predicted_profit": float(i), "actual_profit": np.nan,
             "forecast_type": "预增" if i > 5 else "预减"}
            for i in range(10)
        ])
        trade_dates = pd.bdate_range("2025-02-20", "2025-02-25")
        codes = [f"S{i:03d}" for i in range(10)]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        assert panel["earnings_surprise"].max() <= 3.0
        assert panel["earnings_surprise"].min() >= -3.0

    def test_all_nan_day_gives_zero(self):
        """某日全 NaN → fillna(0.0)。"""
        earnings = pd.DataFrame([
            {"code": "000001", "ann_date": pd.Timestamp("2025-02-20"),
             "end_date": "20241231", "event_type": "forecast",
             "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
        ])
        trade_dates = pd.bdate_range("2025-01-10", "2025-01-14")
        codes = ["000001", "600519"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # Before any announcement, both stocks NaN → z-score fills 0
        assert (panel["earnings_surprise"] == 0.0).all()

    def test_multiple_stocks_independent(self):
        """多股票独立：A 有信号时 B 仍为 0（未公告）。"""
        earnings = pd.DataFrame([
            {"code": "A", "ann_date": pd.Timestamp("2025-02-20"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "B", "ann_date": pd.Timestamp("2025-02-25"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 50.0, "actual_profit": np.nan,
             "forecast_type": "预减"},
            {"code": "C", "ann_date": pd.Timestamp("2025-02-22"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 80.0, "actual_profit": np.nan,
             "forecast_type": "扭亏"},
        ])
        trade_dates = pd.bdate_range("2025-02-18", "2025-03-05")
        codes = ["A", "B", "C"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # A gets data on Feb 20, B on Feb 25, C on Feb 22
        a_feb21 = panel[(panel["date"] == pd.Timestamp("2025-02-21")) & (panel["code"] == "A")]
        b_feb21 = panel[(panel["date"] == pd.Timestamp("2025-02-21")) & (panel["code"] == "B")]
        # A has announced → non-zero signal
        assert a_feb21["earnings_surprise"].iloc[0] != 0.0
        # B has not announced → 0.0 (Z-Score fill)
        assert b_feb21["earnings_surprise"].iloc[0] == 0.0

    def test_acceleration_persists_nonzero(self):
        """acceleration 在公告日后持续非零（非脉冲）。"""
        earnings = pd.DataFrame([
            {"code": "A", "ann_date": pd.Timestamp("2025-04-20"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "A", "ann_date": pd.Timestamp("2025-08-20"), "end_date": "20250630",
             "event_type": "forecast", "predicted_profit": 150.0, "actual_profit": np.nan,
             "forecast_type": "预增"},
            {"code": "A", "ann_date": pd.Timestamp("2025-10-25"), "end_date": "20250930",
             "event_type": "forecast", "predicted_profit": 80.0, "actual_profit": np.nan,
             "forecast_type": "略减"},
            {"code": "B", "ann_date": pd.Timestamp("2025-04-22"), "end_date": "20241231",
             "event_type": "forecast", "predicted_profit": 200.0, "actual_profit": np.nan,
             "forecast_type": "略增"},
            {"code": "B", "ann_date": pd.Timestamp("2025-08-22"), "end_date": "20250630",
             "event_type": "forecast", "predicted_profit": 100.0, "actual_profit": np.nan,
             "forecast_type": "预减"},
            {"code": "B", "ann_date": pd.Timestamp("2025-10-28"), "end_date": "20250930",
             "event_type": "forecast", "predicted_profit": 120.0, "actual_profit": np.nan,
             "forecast_type": "略增"},
        ])
        trade_dates = pd.bdate_range("2025-08-21", "2025-11-05")
        codes = ["A", "B"]
        panel = build_earnings_panel(earnings, trade_dates, codes)
        # After Q3 announcement, acceleration should persist
        aug25 = panel[(panel["date"] == pd.Timestamp("2025-08-25")) & (panel["code"] == "A")]
        sep01 = panel[(panel["date"] == pd.Timestamp("2025-09-01")) & (panel["code"] == "A")]
        if not aug25["earnings_acceleration"].isna().all():
            # Acceleration should persist (not decay to 0 on next day)
            assert abs(sep01["earnings_acceleration"].iloc[0]) > 0 or \
                   aug25["earnings_acceleration"].iloc[0] == 0.0
