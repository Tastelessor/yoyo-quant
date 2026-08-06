"""因子 OOS 验证（Phase B）：walk-forward 窗口 + 选因子 + bootstrap 零分布。

纯函数、无状态，对齐 ``factors.ops.evaluation`` 的契约风格。不 import
``backtest.walk_forward``（避免回测链耦合）；窗口语义与其一致：
train 紧贴 test、滑窗步长 = test_months。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_oos_windows(
    dates: pd.DatetimeIndex | pd.Series,
    *,
    train_months: int = 12,
    test_months: int = 1,
) -> list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """生成 walk-forward 的 (train, test) 交易日窗口对。

    Parameters
    ----------
    dates : DatetimeIndex | Series
        全部可用交易日，升序（内部会去重排序）。
    train_months : int
        train 期长度（日历月）。
    test_months : int
        test 期长度（日历月）；滑窗步长 = test_months（窗口不重叠、连续推进）。

    Returns
    -------
    list of (train_idx, test_idx)
        每期返回两个实际交易日 DatetimeIndex（升序）。train 与 test 严格
        不相交且 train 紧贴 test；test 终点超出数据末日的期不产生。
    """
    if not isinstance(train_months, int) or train_months < 1:
        raise ValueError(f"train_months 必须为正整数，收到 {train_months!r}")
    if not isinstance(test_months, int) or test_months < 1:
        raise ValueError(f"test_months 必须为正整数，收到 {test_months!r}")
    dates = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(dates))))
    if len(dates) == 0:
        return []

    windows: list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]] = []
    cur = dates[0]
    while True:
        train_end_cal = cur + pd.DateOffset(months=train_months)
        test_start_cal = train_end_cal + pd.Timedelta(days=1)
        test_end_cal = test_start_cal + pd.DateOffset(months=test_months)
        if test_end_cal > dates[-1]:
            break
        train = dates[(dates >= cur) & (dates <= train_end_cal)]
        test = dates[(dates >= test_start_cal) & (dates <= test_end_cal)]
        if len(train) == 0 or len(test) == 0:
            cur = cur + pd.DateOffset(months=test_months)
            continue
        windows.append((train, test))
        cur = cur + pd.DateOffset(months=test_months)
    return windows


def select_top_factors(
    stats: pd.DataFrame,
    top_k: int,
    *,
    min_t: float | None = None,
) -> list[str]:
    """按 |t_stat| 降序选 top-K 因子（train 期选择机制的一部分）。

    Parameters
    ----------
    stats : DataFrame
        每因子一行，须含 ``factor`` / ``t_stat`` 列。
    top_k : int
        返回上限（>= 1）。
    min_t : float | None
        给定时过滤 |t_stat| < min_t 的因子。

    Returns
    -------
    list[str]
        按 |t_stat| 降序的因子名；t_stat 为 NaN 的因子不参与
        排序与选择（恒被剔除）。空输入返回空列表。
    """
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError(f"top_k 必须为正整数，收到 {top_k!r}")
    if min_t is not None and min_t <= 0:
        raise ValueError(f"min_t 必须为正数，收到 {min_t!r}")
    if stats.empty:
        return []
    for col in ("factor", "t_stat"):
        if col not in stats.columns:
            raise ValueError(f"stats 缺少列 {col!r}")
    df = stats[["factor", "t_stat"]].drop_duplicates("factor")
    df = df.dropna(subset=["t_stat"])
    if min_t is not None:
        df = df[df["t_stat"].abs() >= min_t]
    df = df.sort_values(
        by=["t_stat"], key=lambda s: s.abs(), ascending=False, na_position="last"
    )
    return df["factor"].head(top_k).tolist()


def compute_test_period_stats(
    ic_series: pd.Series,
    *,
    min_days: int = 5,
) -> dict:
    """test 期日频 IC 序列 → 汇总统计。

    Parameters
    ----------
    ic_series : Series
        日频 IC 时序（``compute_ic`` 输出，index 为升序日期）。
    min_days : int
        test 期有效天数下限；低于该值 ic_t 为 NaN、sig=False。

    Returns
    -------
    dict
        ``ic_mean`` / ``ic_t``（= mean/std×√n，std=0 → inf）/
        ``ic_n`` / ``sig``（|ic_t| > 2）。
    """
    if not isinstance(min_days, int) or min_days < 1:
        raise ValueError(f"min_days 必须为正整数，收到 {min_days!r}")
    vals = ic_series.dropna()
    n = int(len(vals))
    if n < min_days:
        return {"ic_mean": float(vals.mean()) if n else float("nan"),
                "ic_t": float("nan"), "ic_n": n, "sig": False}
    mean = float(vals.mean())
    std = float(vals.std(ddof=1))
    if std == 0 or vals.nunique() <= 1:
        return {"ic_mean": mean, "ic_t": float("inf"), "ic_n": n, "sig": True}
    ic_t = mean / std * np.sqrt(n)
    return {"ic_mean": mean, "ic_t": ic_t, "ic_n": n, "sig": bool(abs(ic_t) > 2.0)}


def bootstrap_t_distribution(
    ic_series: pd.Series,
    n_iters: int,
    t_window: int,
    *,
    seed: int | None = None,
) -> np.ndarray:
    """train 期 IC 序列打乱重排 → t 统计量零分布（多重检验修正）。

    破坏 IC 的时序结构但保留其分布形态，每次打乱后取尾部 ``t_window``
    个样本的 t = mean/std×√n——与 monitor 的滚动 t 同口径。零分布的
    |t| 高分位即"纯随机下 t 能多大"的参考线。

    Parameters
    ----------
    ic_series : Series
        train 段日频 IC 时序（state 长表 ic 列切片）。
    n_iters : int
        打乱次数（>= 1）。
    t_window : int
        尾部窗口（交易日，>= 2）。
    seed : int | None
        随机种子，保证可复现。

    Returns
    -------
    ndarray
        长度 ``n_iters`` 的 t 统计量零分布。
    """
    if not isinstance(n_iters, int) or n_iters < 1:
        raise ValueError(f"n_iters 必须为正整数，收到 {n_iters!r}")
    if not isinstance(t_window, int) or t_window < 2:
        raise ValueError(f"t_window 必须为 >= 2 的整数，收到 {t_window!r}")
    values = ic_series.dropna().to_numpy(dtype=float)
    if values.size < t_window:
        return np.full(n_iters, np.nan)
    rng = np.random.default_rng(seed)
    out = np.empty(n_iters)
    for i in range(n_iters):
        w = rng.permutation(values)[-t_window:]
        std = w.std(ddof=1)
        out[i] = np.inf if std == 0 else w.mean() / std * np.sqrt(len(w))
    return out
