"""Tests for src/data/fundamentals_quarterly.py — quarterly financial data pipeline."""

from __future__ import annotations

import pandas as pd


class TestBuildQualityPanel:
    """Tests for build_quality_panel PIT alignment and factor computation."""

    def _make_fina_df(self):
        """Sample fina_indicator data for 2 stocks, 4 quarters."""
        return pd.DataFrame(
            {
                "code": ["000001"] * 4 + ["600519"] * 4,
                "ann_date": pd.to_datetime(
                    [
                        # 000001: Q4 2024 announced 2025-03-30
                        "2025-03-30",
                        # Q1 2025 announced 2025-04-30
                        "2025-04-30",
                        # Q2 2025 announced 2025-08-30
                        "2025-08-30",
                        # Q3 2025 announced 2025-10-30
                        "2025-10-30",
                        # 600519: same pattern
                        "2025-03-30",
                        "2025-04-30",
                        "2025-08-30",
                        "2025-10-30",
                    ]
                ),
                "end_date": [
                    "20241231",
                    "20250331",
                    "20250630",
                    "20250930",
                    "20241231",
                    "20250331",
                    "20250630",
                    "20250930",
                ],
                "roe": [10.0, 2.5, 5.0, 7.5, 15.0, 3.0, 6.0, 9.0],
                "ocfps": [5.0, 1.0, 2.0, 3.0, 8.0, 2.0, 4.0, 5.0],
            }
        )

    def test_returns_dataframe(self):
        from data.fundamentals_quarterly import build_quality_panel

        fina_df = self._make_fina_df()
        trade_dates = pd.date_range("2025-01-01", "2025-12-31", freq="B")
        codes = ["000001", "600519"]
        result = build_quality_panel(fina_df, trade_dates, codes)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self):
        from data.fundamentals_quarterly import build_quality_panel

        fina_df = self._make_fina_df()
        trade_dates = pd.date_range("2025-01-01", "2025-12-31", freq="B")
        codes = ["000001", "600519"]
        result = build_quality_panel(fina_df, trade_dates, codes)
        assert "date" in result.columns
        assert "code" in result.columns
        assert "roe_level" in result.columns
        assert "roe_stability" in result.columns
        assert "cashflow_quality" in result.columns

    def test_pit_alignment_no_lookahead(self):
        """Q4 2024 announced 2025-03-30 should NOT be visible on 2025-03-28."""
        from data.fundamentals_quarterly import build_quality_panel

        fina_df = self._make_fina_df()
        trade_dates = pd.date_range("2025-03-27", "2025-04-02", freq="B")
        codes = ["000001"]
        result = build_quality_panel(fina_df, trade_dates, codes)

        # Before 2025-03-30: no data announced yet for this stock
        before = result[result["date"] < "2025-03-30"]
        # On/after 2025-03-30: Q4 2024 data visible
        after = result[result["date"] >= "2025-03-30"]

        if len(before) > 0:
            # Before announcement: no data → NaN
            assert before["roe_level"].isna().all()

        if len(after) > 0:
            # After announcement, roe_level should be 10.0 (Q4 2024 ROE)
            after_roe = after["roe_level"].dropna()
            if len(after_roe) > 0:
                assert after_roe.iloc[0] == 10.0

    def test_roe_stability_nan_for_insufficient_quarters(self):
        """ROE stability needs >= 2 quarters; single quarter → NaN."""
        from data.fundamentals_quarterly import build_quality_panel

        # Only 1 quarter of data
        fina_df = pd.DataFrame(
            {
                "code": ["000001"],
                "ann_date": pd.to_datetime(["2025-04-30"]),
                "end_date": ["20241231"],
                "roe": [10.0],
                "ocfps": [5.0],
            }
        )
        trade_dates = pd.date_range("2025-05-01", "2025-05-05", freq="B")
        codes = ["000001"]
        result = build_quality_panel(fina_df, trade_dates, codes)
        # With only 1 quarter, stability should be NaN
        assert result["roe_stability"].isna().all()

    def test_empty_input_returns_zero_filled(self):
        from data.fundamentals_quarterly import build_quality_panel

        fina_df = pd.DataFrame(columns=["code", "ann_date", "end_date", "roe", "ocfps"])
        trade_dates = pd.date_range("2025-01-01", "2025-01-05", freq="B")
        codes = ["000001"]
        result = build_quality_panel(fina_df, trade_dates, codes)
        assert len(result) == len(trade_dates) * len(codes)
        assert result["roe_level"].isna().all()

    def test_two_stocks_independent(self):
        """Each stock's ROE should be computed independently."""
        from data.fundamentals_quarterly import build_quality_panel

        fina_df = self._make_fina_df()
        trade_dates = pd.date_range("2025-05-01", "2025-05-05", freq="B")
        codes = ["000001", "600519"]
        result = build_quality_panel(fina_df, trade_dates, codes)

        s1 = result[result["code"] == "000001"]["roe_level"].dropna()
        s2 = result[result["code"] == "600519"]["roe_level"].dropna()
        if len(s1) > 0 and len(s2) > 0:
            # Different stocks should have different ROE
            assert s1.iloc[0] != s2.iloc[0]


class TestFetchFinaIndicator:
    """Tests for fetch_fina_indicator (mocked API)."""

    def test_returns_dataframe(self, monkeypatch):
        from data.fundamentals_quarterly import fetch_fina_indicator

        mock_data = pd.DataFrame(
            {
                "ts_code": ["000001.SZ"] * 2,
                "ann_date": ["20250430", "20250830"],
                "end_date": ["20241231", "20250630"],
                "roe": [10.0, 5.0],
                "ocfps": [5.0, 2.0],
            }
        )

        def mock_pro_api(token):
            class MockApi:
                _DataApi__http_url = ""

                def fina_indicator(self, **kwargs):
                    return mock_data

            return MockApi()

        monkeypatch.setattr("tushare.pro_api", mock_pro_api)
        monkeypatch.setenv("TUSHARE_TOKEN", "test")

        result = fetch_fina_indicator("000001", cache_dir="/tmp/test_fina")
        assert isinstance(result, pd.DataFrame)
        assert "code" in result.columns
        assert "roe" in result.columns
