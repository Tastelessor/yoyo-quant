"""analysis/factor_monitor 单元测试（因子生命周期监控 Task 2）。

覆盖：
- run_state_machine：候选/防抖/冷启动/反向/NaN/空/参数校验
- 持久化：save_state / load_state / save_changes（追加去重、备份、schema）
"""

import numpy as np
import pandas as pd
import pytest

from analysis.factor_monitor import (
    STATE_COLS,
    load_state,
    run_state_machine,
    save_changes,
    save_state,
)

# --- run_state_machine ---


def test_state_machine_transitions():
    t_series = pd.Series([3.0] * 25 + [1.5] * 25 + [0.5] * 25)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert states.iloc[24] == "active"
    assert states.iloc[25] == "active"  # 候选 decaying 未满 20 日 → 维持
    assert states.iloc[49] == "decaying"
    assert states.iloc[74] == "dead"


def test_state_machine_reverse():
    t_series = pd.Series([-3.0] * 25)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert states.iloc[-1] == "reverse"


def test_state_machine_cold_start():
    # 首日即按候选状态初始化（无历史）
    t_series = pd.Series([3.0, 3.0])
    states = run_state_machine(t_series, min_sustain=20)
    assert states.iloc[0] == "active"


def test_state_machine_short_burst_keeps_state():
    # 候选状态短暂偏离（< min_sustain）不切换
    t_series = pd.Series([3.0] * 10 + [1.5] * 2 + [3.0] * 10)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert (states == "active").all()


def test_state_machine_candidate_recovery():
    # dead 中 t 回升至 decaying，满 20 日后切 decaying（而非跳回 active）
    t_series = pd.Series([0.5] * 30 + [1.5] * 25)
    states = run_state_machine(t_series, t_active=2.0, t_decay=1.0, min_sustain=20)
    assert states.iloc[40] == "dead"  # 候选 decaying 未满 20 日 → 维持
    assert states.iloc[54] == "decaying"


def test_state_machine_nan_is_dead():
    # NaN 不满足任何阈值 → dead（数据不足视为失效）
    t_series = pd.Series([np.nan, np.nan])
    states = run_state_machine(t_series, min_sustain=20)
    assert states.iloc[-1] == "dead"


def test_state_machine_empty():
    states = run_state_machine(pd.Series([], dtype=float), min_sustain=20)
    assert isinstance(states, pd.Series)
    assert len(states) == 0


def test_state_machine_invalid_min_sustain():
    with pytest.raises(ValueError):
        run_state_machine(pd.Series([1.0]), min_sustain=0)


def test_state_machine_returns_string_series():
    states = run_state_machine(pd.Series([3.0, 3.0]), min_sustain=1)
    assert isinstance(states.iloc[0], str)
    pd.testing.assert_index_equal(states.index, pd.RangeIndex(2))


# --- 持久化 ---


def _state_df(n, start="2026-01-01", factor="f1", fwd=5):
    dates = pd.date_range(start, periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "factor": [factor] * n,
            "fwd_window": [fwd] * n,
            "ic": np.linspace(0.05, 0.01, n),
            "rolling_ic": np.linspace(0.04, 0.02, n),
            "rolling_ir": np.linspace(0.6, 0.2, n),
            "t_stat": np.linspace(3.0, 0.5, n),
            "state": ["active"] * n,
            "sustain_days": list(range(1, n + 1)),
        }
    )


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "state.parquet"
    df = _state_df(10)
    save_state(df, path)
    pd.testing.assert_frame_equal(load_state(path), df)


def test_state_append_dedup(tmp_path):
    path = tmp_path / "state.parquet"
    save_state(_state_df(10), path)
    second = _state_df(15)  # 前 10 日同键重叠（新值覆盖），后 5 日新增
    save_state(second, path)
    loaded = load_state(path)
    assert len(loaded) == 15
    assert loaded.duplicated(subset=["date", "factor", "fwd_window"]).sum() == 0
    # 重叠日被 second 覆盖（keep="last"）
    row = loaded[loaded["date"] == second["date"].iloc[9]].iloc[0]
    assert row["t_stat"] == pytest.approx(second["t_stat"].iloc[9])


def test_state_schema_and_dtypes(tmp_path):
    path = tmp_path / "state.parquet"
    save_state(_state_df(3), path)
    loaded = load_state(path)
    assert list(loaded.columns) == STATE_COLS
    assert pd.api.types.is_datetime64_any_dtype(loaded["date"])
    assert loaded["state"].dtype == object
    assert loaded["fwd_window"].dtype == "int64"


def test_load_state_missing_returns_empty(tmp_path):
    loaded = load_state(tmp_path / "nope.parquet")
    assert isinstance(loaded, pd.DataFrame)
    assert len(loaded) == 0
    assert list(loaded.columns) == STATE_COLS


def test_save_state_backs_up_previous(tmp_path):
    path = tmp_path / "state.parquet"
    save_state(_state_df(5), path)
    save_state(_state_df(8), path)
    assert (tmp_path / "state.bak.parquet").exists()


def test_save_changes_append(tmp_path):
    path = tmp_path / "changes.parquet"
    c1 = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01"]),
            "factor": ["f1"],
            "fwd_window": [5],
            "old_state": ["active"],
            "new_state": ["decaying"],
        }
    )
    save_changes(c1, path)
    c2 = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-02-01"]),
            "factor": ["f1"],
            "fwd_window": [5],
            "old_state": ["decaying"],
            "new_state": ["dead"],
        }
    )
    save_changes(c2, path)
    loaded = pd.read_parquet(path)
    assert len(loaded) == 2
    assert loaded["new_state"].tolist() == ["decaying", "dead"]
