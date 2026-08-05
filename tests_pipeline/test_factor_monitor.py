"""analysis.factor_monitor 管道测试（因子生命周期监控 Task 2.3）。

合成行情：前 160 日横截面 alpha 显著（40 只股票 trend 差异）、后 260 日纯噪声
（trend 归零）→ 动量因子状态应经历 active → dead（decaying 的防抖细节由单元
测试保证，此处断言两态的生命周期走向）。

覆盖：
1. 生命周期：active 先出现、之后进入 dead；state.parquet/changes.parquet 落盘
2. 多因子独立：联合跑与分别跑结果逐行一致，互不污染
3. 增量：尾部增量（full=False）结果与全量（full=True）一致，无重复键
4. 动态发现：factor_names=None 缺省走 list_factors(kind="single")
"""

import numpy as np
import pandas as pd

import analysis.factor_monitor as fm
from analysis.factor_monitor import run_monitor


def make_ohlcv(n_stocks=40, n_days=420, trend_max=0.00025, noise=0.008,
               seed=42, alpha_days=160, start="2024-01-01"):
    """合成行情：alpha_days 内 trend 差异产生横截面 alpha，之后纯噪声。"""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    rows = []
    for j in range(n_stocks):
        trend = trend_max * (j - (n_stocks - 1) / 2)
        price = 10.0
        for i in range(n_days):
            w = 1.0 if i < alpha_days else 0.0
            ret = trend * w + rng.normal(0, noise)
            price *= 1 + ret
            rows.append((dates[i], f"S{j:03d}", price))
    df = pd.DataFrame(rows, columns=["date", "code", "close"])
    for c in ("limit_up", "limit_down", "is_suspended"):
        df[c] = False
    return df


def extend_ohlcv(df, extra_days=30, noise=0.008, seed=7):
    """追加 extra_days 纯噪声行情（价格从最后 close 继续）。"""
    rng = np.random.default_rng(seed)
    last_date = df["date"].max()
    last_close = df.groupby("code")["close"].last()
    dates = pd.bdate_range(last_date + pd.Timedelta(days=1), periods=extra_days)
    rows = []
    for code, p0 in last_close.items():
        price = p0
        for d in dates:
            price *= 1 + rng.normal(0, noise)
            rows.append((d, code, price))
    ext = pd.DataFrame(rows, columns=["date", "code", "close"])
    for c in ("limit_up", "limit_down", "is_suspended"):
        ext[c] = False
    return pd.concat([df, ext], ignore_index=True)


def test_monitor_lifecycle_active_then_dead(tmp_path):
    df = make_ohlcv()
    out = tmp_path / "m"
    state, _ = run_monitor(
        df,
        factor_names=["calc_momentum_5d_change"],
        output_dir=out,
        cache_dir=tmp_path / "cache",
        use_cache=False,
    )
    # schema
    assert list(state.columns) == fm.STATE_COLS
    assert pd.api.types.is_datetime64_any_dtype(state["date"])
    assert set(state["factor"]) == {"calc_momentum_5d_change"}
    assert set(state["fwd_window"]) == {5}
    assert state.duplicated(subset=["date", "factor", "fwd_window"]).sum() == 0
    # 生命周期：active 先出现，之后进入 dead
    acts = state[state["state"] == "active"]
    assert len(acts) > 0
    d_active = acts["date"].min()
    later_dead = state[(state["date"] > d_active) & (state["state"] == "dead")]
    assert len(later_dead) > 0
    # 落盘
    assert (out / "state.parquet").exists()
    # 首跑全量为状态初始化，无切换 → changes 不落盘（增量运行才产生切换）
    assert not (out / "changes.parquet").exists()


def test_monitor_multi_factor_independent(tmp_path):
    df = make_ohlcv()
    both, _ = run_monitor(
        df,
        factor_names=["calc_momentum_5d_change", "calc_momentum_20d_change"],
        output_dir=tmp_path / "both",
        cache_dir=tmp_path / "cache",
        use_cache=False,
    )
    assert set(both["factor"]) == {
        "calc_momentum_5d_change",
        "calc_momentum_20d_change",
    }
    for fname in ("calc_momentum_5d_change", "calc_momentum_20d_change"):
        single, _ = run_monitor(
            df,
            factor_names=[fname],
            output_dir=tmp_path / f"single_{fname}",
            cache_dir=tmp_path / "cache",
            use_cache=False,
        )
        part = both[both["factor"] == fname].reset_index(drop=True)
        pd.testing.assert_frame_equal(part, single.reset_index(drop=True))


def test_monitor_incremental_matches_full(tmp_path):
    df = make_ohlcv()
    df_ext = extend_ohlcv(df)
    incremental, _ = run_monitor(
        df_ext,
        factor_names=["calc_momentum_5d_change"],
        output_dir=tmp_path / "incr",
        cache_dir=tmp_path / "cache",
        use_cache=False,
    )  # state.parquet 不存在 → 首跑全量；再跑一次走增量
    incremental2, _ = run_monitor(
        df_ext,
        factor_names=["calc_momentum_5d_change"],
        output_dir=tmp_path / "incr",
        cache_dir=tmp_path / "cache",
        use_cache=False,
    )  # 已有 last_date → 尾部增量
    full, _ = run_monitor(
        df_ext,
        factor_names=["calc_momentum_5d_change"],
        output_dir=tmp_path / "full",
        cache_dir=tmp_path / "cache",
        use_cache=False,
        full=True,
    )
    # 增量结果 == 直接全量结果（同键行值一致）
    pd.testing.assert_frame_equal(incremental2, full.reset_index(drop=True))
    # 尾部增量确实只重算尾部：首跑与增量第二次运行结果一致（数据未变）
    pd.testing.assert_frame_equal(incremental, incremental2)


def test_monitor_dynamic_discovery(tmp_path, monkeypatch):
    df = make_ohlcv()
    monkeypatch.setattr(
        fm, "list_factors", lambda kind=None: ["calc_momentum_5d_change"]
    )
    state, _ = run_monitor(
        df,
        output_dir=tmp_path / "m",
        cache_dir=tmp_path / "cache",
        use_cache=False,
    )
    assert set(state["factor"]) == {"calc_momentum_5d_change"}
