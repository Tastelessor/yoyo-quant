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


# ---------------------------------------------------------------------------
# Task 4: moneyflow 数据管线
# ---------------------------------------------------------------------------


def test_fetch_moneyflow_by_date_shape_and_cache(monkeypatch, tmp_path):
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600519.SH"],
            "trade_date": ["20250102", "20250102"],
            "buy_sm_vol": [100, 200],
            "buy_sm_amount": [10.0, 20.0],
            "sell_sm_vol": [50, 60],
            "sell_sm_amount": [5.0, 6.0],
            "buy_md_vol": [30, 40],
            "buy_md_amount": [3.0, 4.0],
            "sell_md_vol": [10, 20],
            "sell_md_amount": [1.0, 2.0],
            "buy_lg_vol": [20, 30],
            "buy_lg_amount": [2.0, 3.0],
            "sell_lg_vol": [5, 10],
            "sell_lg_amount": [0.5, 1.0],
            "buy_elg_vol": [10, 5],
            "buy_elg_amount": [1.0, 0.5],
            "sell_elg_vol": [2, 3],
            "sell_elg_amount": [0.2, 0.3],
            "net_mf_vol": [90, 150],
            "net_mf_amount": [9.0, 15.0],
        }
    )
    calls = []

    class FakeApi:
        def moneyflow(self, **kwargs):
            calls.append(kwargs)
            return raw

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(
        mf_mod, "ts", type("TS", (), {"pro_api": lambda t, token: FakeApi()})()
    )
    monkeypatch.setattr(mf_mod, "_PROXY_URL", "http://mock")

    df = mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns)[:3] == ["date", "code", "buy_sm_vol"]
    assert "net_mf_amount" in df.columns
    assert df["date"].iloc[0] == pd.Timestamp("2025-01-02")
    assert set(df["code"]) == {"000001", "600519"}
    assert df["net_mf_amount"].tolist() == [9.0, 15.0]  # 万元保持
    # 缓存命中不再调用
    mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert len(calls) == 1


def test_fetch_moneyflow_by_date_empty(monkeypatch, tmp_path):
    class FakeApi:
        def moneyflow(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(
        mf_mod, "ts", type("TS", (), {"pro_api": lambda t, token: FakeApi()})()
    )
    df = mf_mod.fetch_moneyflow_by_date("2025-01-02", cache_dir=tmp_path)
    assert list(df.columns) == ["date", "code"]  # 空表仍保有基础列


def test_build_moneyflow_panel_merges_dates(monkeypatch, tmp_path):
    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["20250102"],
            "buy_sm_vol": [100],
            "buy_sm_amount": [10.0],
            "sell_sm_vol": [50],
            "sell_sm_amount": [5.0],
            "buy_md_vol": [30],
            "buy_md_amount": [3.0],
            "sell_md_vol": [10],
            "sell_md_amount": [1.0],
            "buy_lg_vol": [20],
            "buy_lg_amount": [2.0],
            "sell_lg_vol": [5],
            "sell_lg_amount": [0.5],
            "buy_elg_vol": [10],
            "buy_elg_amount": [1.0],
            "sell_elg_vol": [2],
            "sell_elg_amount": [0.2],
            "net_mf_vol": [90],
            "net_mf_amount": [9.0],
        }
    )

    class FakeApi:
        def moneyflow(self, **kwargs):
            # 按 trade_date 参数返回对应日期数据
            td = kwargs.get("trade_date", "")
            return raw.assign(trade_date=td)

    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")
    import data.moneyflow as mf_mod

    monkeypatch.setattr(
        mf_mod, "ts", type("TS", (), {"pro_api": lambda t, token: FakeApi()})()
    )
    monkeypatch.setattr(
        mf_mod,
        "fetch_trade_dates",
        lambda start, end: [pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03")],
    )
    panel = mf_mod.build_moneyflow_panel(
        "2025-01-02", "2025-01-03", cache_dir=tmp_path, sleep_sec=0
    )
    assert len(panel) == 2
    assert sorted(panel["date"].unique()) == [
        pd.Timestamp("2025-01-02"),
        pd.Timestamp("2025-01-03"),
    ]
    assert "net_mf_amount" in panel.columns
