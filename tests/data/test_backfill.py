"""tests/data/test_backfill.py — backfill 批量拉取调度测试。

mock 单日函数与交易日历，不依赖网络/tushare。
"""
import pandas as pd
import pytest

from data.backfill import (
    backfill_range,
    fetch_fundamentals_range,
    fetch_moneyflow_range,
)


def _dates(n: int) -> pd.DatetimeIndex:
    """返回从 2023-08-07（周一）起 n 个连续工作日。"""
    return pd.DatetimeIndex(pd.to_datetime([f"2023-08-{7 + i:02d}" for i in range(n)]))


def _ok_frame() -> pd.DataFrame:
    return pd.DataFrame({"a": [1]})


def test_backfill_all_success_single_round(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(3))
    calls = []

    def fetch_day(d):
        calls.append(d)
        return _ok_frame()

    result = backfill_range(fetch_day, "2023-08-07", "2023-08-09", round_pause=0)
    assert result == {"total": 3, "success": 3, "failed": []}
    # 一轮完成：只调用 total 次，无第二轮
    assert calls == ["2023-08-07", "2023-08-08", "2023-08-09"]


def test_backfill_partial_failure_second_round(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(4))
    fail_once = {"2023-08-08": 1, "2023-08-10": 1}
    calls = []

    def fetch_day(d):
        calls.append(d)
        if fail_once.get(d, 0) > 0:
            fail_once[d] -= 1
            raise RuntimeError("proxy timeout")
        return _ok_frame()

    result = backfill_range(fetch_day, "2023-08-07", "2023-08-10", round_pause=0)
    assert result["total"] == 4
    assert result["success"] == 4
    assert result["failed"] == []
    # 第 1 轮 4 次 + 第 2 轮仅补拉 2 个失败日
    assert len(calls) == 6


def test_backfill_max_rounds_exhausted(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(3))

    def fetch_day(d):
        raise RuntimeError("always fail")

    result = backfill_range(
        fetch_day, "2023-08-07", "2023-08-09", max_rounds=2, round_pause=0
    )
    assert result["total"] == 3
    assert result["success"] == 0
    assert sorted(result["failed"]) == ["2023-08-07", "2023-08-08", "2023-08-09"]


def test_backfill_empty_dataframe_is_failure(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(2))

    def fetch_day(d):
        return pd.DataFrame()

    result = backfill_range(
        fetch_day, "2023-08-07", "2023-08-08", max_rounds=1, round_pause=0
    )
    assert result["success"] == 0
    assert sorted(result["failed"]) == ["2023-08-07", "2023-08-08"]


def test_backfill_round_pause_zero_no_sleep(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(2))
    monkeypatch.setattr(
        "data.backfill.time.sleep",
        lambda s: pytest.fail("round_pause=0 不应触发 sleep"),
    )

    def fetch_day(d):
        return _ok_frame()

    result = backfill_range(fetch_day, "2023-08-07", "2023-08-08", round_pause=0)
    assert result["success"] == 2


def test_backfill_sleep_between_rounds(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(2))
    slept = []
    monkeypatch.setattr("data.backfill.time.sleep", slept.append)
    fail_once = {"2023-08-08": 1}

    def fetch_day(d):
        if fail_once.get(d, 0) > 0:
            fail_once[d] -= 1
            raise RuntimeError("boom")
        return _ok_frame()

    result = backfill_range(fetch_day, "2023-08-07", "2023-08-08", round_pause=5)
    assert result["success"] == 2
    # 仅第 1 轮后有失败时 sleep 一次（第 2 轮全成功不再 sleep）
    assert slept == [5]


def test_fetch_fundamentals_range_smoke(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(2))
    seen = []

    def fake_fetch_fundamentals(d):
        seen.append(d)
        return _ok_frame()

    monkeypatch.setattr("data.backfill.fetch_fundamentals", fake_fetch_fundamentals)

    result = fetch_fundamentals_range("2023-08-07", "2023-08-08", round_pause=0)
    assert result["success"] == 2
    assert result["failed"] == []
    assert seen == ["2023-08-07", "2023-08-08"]


def test_fetch_moneyflow_range_smoke(monkeypatch):
    monkeypatch.setattr("data.backfill.fetch_trade_dates", lambda s, e: _dates(2))
    seen = []

    def fake_fetch_moneyflow(d):
        seen.append(d)
        return _ok_frame()

    monkeypatch.setattr("data.backfill.fetch_moneyflow_by_date", fake_fetch_moneyflow)

    result = fetch_moneyflow_range("2023-08-07", "2023-08-08", round_pause=0)
    assert result["success"] == 2
    assert result["failed"] == []
    assert seen == ["2023-08-07", "2023-08-08"]
