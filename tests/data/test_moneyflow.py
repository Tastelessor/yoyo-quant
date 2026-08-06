"""tests/data/test_moneyflow.py — moneyflow 数据管线 + fetch_fundamentals 扩展单测。"""
from __future__ import annotations

import pandas as pd

from data.fetcher import fetch_fundamentals

# ---------------------------------------------------------------------------
# Task 1: fetch_fundamentals 扩展 circ_mv / turnover_rate
# ---------------------------------------------------------------------------


def test_fetch_fundamentals_includes_circ_mv_and_turnover(monkeypatch, tmp_path):
    """daily_basic 返回含 circ_mv/turnover_rate；circ_mv 转亿元、turnover 原样。"""
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600519.SH"],
            "trade_date": ["20250102", "20250102"],
            "pe": [5.0, 30.0],
            "pb": [0.8, 10.0],
            "total_mv": [20_000_000, 200_000_000],  # 万元 → 2000 / 20000 亿元
            "circ_mv": [15_000_000, 180_000_000],   # 万元 → 1500 / 18000 亿元
            "turnover_rate": [1.5, 0.3],
        }
    )
    calls = {}

    class FakeApi:
        def daily_basic(self, **kwargs):
            calls.update(kwargs)
            return raw

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.fetcher as fetcher_mod

    monkeypatch.setattr(
        fetcher_mod, "ts", type("TS", (), {"pro_api": lambda t, token: FakeApi()})()
    )
    monkeypatch.setattr(fetcher_mod, "_PROXY_URL", "http://mock")

    df = fetch_fundamentals("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns) == [
        "code", "pe", "pb", "total_mv", "circ_mv", "turnover_rate"
    ]
    assert df["circ_mv"].tolist() == [1500.0, 18000.0]  # 万元 → 亿元
    assert df["total_mv"].tolist() == [2000.0, 20000.0]  # 既有逻辑保持
    assert df["turnover_rate"].tolist() == [1.5, 0.3]  # 原样
    assert "circ_mv" in calls["fields"] and "turnover_rate" in calls["fields"]
    assert set(df["code"]) == {"000001", "600519"}


def test_fetch_fundamentals_cache_hit_skips_api(monkeypatch, tmp_path):
    """缓存命中时不再调用 API，且返回列完整（含新字段）。"""
    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    (tmp_path / "20250102.parquet").write_bytes(
        pd.DataFrame(
            {
                "code": ["000001"],
                "pe": [5.0],
                "pb": [0.8],
                "total_mv": [2000.0],
                "circ_mv": [1500.0],
                "turnover_rate": [1.5],
            }
        ).to_parquet()
    )
    called = []

    class FakeApi:
        def daily_basic(self, **kwargs):
            called.append(kwargs)
            return pd.DataFrame()

    import data.fetcher as fetcher_mod

    monkeypatch.setattr(
        fetcher_mod, "ts", type("TS", (), {"pro_api": lambda t, token: FakeApi()})()
    )

    df = fetch_fundamentals("2025-01-02", cache_dir=tmp_path)
    assert called == []  # 未调 API
    assert "circ_mv" in df.columns and "turnover_rate" in df.columns
